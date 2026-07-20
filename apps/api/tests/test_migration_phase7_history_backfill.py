"""Phase 7 migration: ordered history version backfill and SystemState reconcile."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import InternalError

from alembic import command
from app.core.settings import clear_settings_cache, get_settings
from app.db.session import reset_engine

API_ROOT = Path(__file__).resolve().parents[1]
PHASE6_REVISION = "c6a1f0e9d2b8"
PHASE7_REVISION = "a7b8c9d0e1f2"
HEAD_REVISION = "c9d0e1f2a3b4"


def _alembic_config() -> Config:
    return Config(str(API_ROOT / "alembic.ini"))


def _engine():
    clear_settings_cache()
    reset_engine()
    return create_engine(get_settings().database_url)


def _downgrade_to_phase6(cfg: Config) -> None:
    command.downgrade(cfg, PHASE6_REVISION)


def _insert_phase6_state_and_history(
    conn,
    *,
    mode: str,
    history: list[tuple[str | None, str, datetime]],
) -> uuid.UUID:
    state_id = uuid.uuid4()
    conn.execute(
        text(
            """
            DELETE FROM operating_mode_history;
            DELETE FROM system_states;
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO system_states (id, singleton_key, current_mode, reason)
            VALUES (:id, 'current', CAST(:mode AS operating_mode), 'legacy')
            """
        ),
        {"id": state_id, "mode": mode},
    )
    for from_mode, to_mode, changed_at in history:
        conn.execute(
            text(
                """
                INSERT INTO operating_mode_history
                    (id, from_mode, to_mode, changed_at, reason)
                VALUES (
                    :id,
                    CAST(:from_mode AS operating_mode),
                    CAST(:to_mode AS operating_mode),
                    :changed_at,
                    'legacy'
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "from_mode": from_mode,
                "to_mode": to_mode,
                "changed_at": changed_at,
            },
        )
    return state_id


def test_backfill_empty_history_sets_state_version_zero() -> None:
    cfg = _alembic_config()
    engine = _engine()
    _downgrade_to_phase6(cfg)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM operating_mode_history"))
        conn.execute(text("DELETE FROM system_states"))
        conn.execute(
            text(
                """
                INSERT INTO system_states (id, singleton_key, current_mode, reason)
                VALUES (:id, 'current', 'OFF', 'bootstrap')
                """
            ),
            {"id": uuid.uuid4()},
        )

    command.upgrade(cfg, PHASE7_REVISION)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == PHASE7_REVISION
        state_version = conn.execute(
            text("SELECT state_version FROM system_states WHERE singleton_key = 'current'")
        ).scalar_one()
        assert state_version == 0
        mode = conn.execute(
            text("SELECT current_mode::text FROM system_states WHERE singleton_key = 'current'")
        ).scalar_one()
        assert mode == "OFF"
        hist = conn.execute(text("SELECT COUNT(*) FROM operating_mode_history")).scalar_one()
        assert hist == 0

    reset_engine()
    clear_settings_cache()


def test_backfill_one_and_many_rows_monotonic_with_tiebreak() -> None:
    cfg = _alembic_config()
    engine = _engine()
    _downgrade_to_phase6(cfg)

    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    same = t0 + timedelta(minutes=1)
    id_a = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    id_b = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM operating_mode_history"))
        conn.execute(text("DELETE FROM system_states"))
        conn.execute(
            text(
                """
                INSERT INTO system_states (id, singleton_key, current_mode, reason)
                VALUES (:id, 'current', 'SAFE_MODE', 'legacy')
                """
            ),
            {"id": uuid.uuid4()},
        )
        # Identical timestamps: id ASC tie-break => id_a before id_b.
        rows = [
            (uuid.uuid4(), None, "OFF", t0),
            (id_a, "OFF", "OBSERVE", same),
            (id_b, "OBSERVE", "SAFE_MODE", same),
        ]
        for hid, frm, to, ts in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO operating_mode_history
                        (id, from_mode, to_mode, changed_at, reason)
                    VALUES (
                        :id,
                        CAST(:frm AS operating_mode),
                        CAST(:to AS operating_mode),
                        :ts,
                        'legacy'
                    )
                    """
                ),
                {"id": hid, "frm": frm, "to": to, "ts": ts},
            )

    command.upgrade(cfg, PHASE7_REVISION)

    with engine.connect() as conn:
        hist = list(
            conn.execute(
                text(
                    """
                    SELECT id, previous_state_version, new_state_version, to_mode::text
                    FROM operating_mode_history
                    ORDER BY new_state_version ASC
                    """
                )
            )
        )
        assert len(hist) == 3
        assert [r.previous_state_version for r in hist] == [0, 1, 2]
        assert [r.new_state_version for r in hist] == [1, 2, 3]
        assert hist[1].id == id_a
        assert hist[2].id == id_b
        assert hist[2].to_mode == "SAFE_MODE"
        state = conn.execute(
            text(
                """
                SELECT state_version, current_mode::text
                FROM system_states WHERE singleton_key = 'current'
                """
            )
        ).one()
        assert state.state_version == 3
        assert state.current_mode == "SAFE_MODE"

    # Downgrade / re-upgrade preserves reconciliation after re-backfill.
    command.downgrade(cfg, PHASE6_REVISION)
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == HEAD_REVISION
        )
        assert (
            conn.execute(
                text("SELECT state_version FROM system_states WHERE singleton_key = 'current'")
            ).scalar_one()
            == 3
        )

    reset_engine()
    clear_settings_cache()


def test_backfill_stale_system_state_version_reconciled() -> None:
    cfg = _alembic_config()
    engine = _engine()
    _downgrade_to_phase6(cfg)
    t0 = datetime(2026, 2, 1, tzinfo=UTC)
    with engine.begin() as conn:
        _insert_phase6_state_and_history(
            conn,
            mode="OBSERVE",
            history=[
                (None, "OFF", t0),
                ("OFF", "OBSERVE", t0 + timedelta(seconds=1)),
            ],
        )

    command.upgrade(cfg, PHASE7_REVISION)
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT state_version FROM system_states WHERE singleton_key = 'current'")
            ).scalar_one()
            == 2
        )
        assert (
            conn.execute(
                text("SELECT current_mode::text FROM system_states WHERE singleton_key = 'current'")
            ).scalar_one()
            == "OBSERVE"
        )

    reset_engine()
    clear_settings_cache()


def test_backfill_inconsistent_history_tip_fails_migration() -> None:
    cfg = _alembic_config()
    engine = _engine()
    _downgrade_to_phase6(cfg)
    t0 = datetime(2026, 3, 1, tzinfo=UTC)
    with engine.begin() as conn:
        _insert_phase6_state_and_history(
            conn,
            mode="OFF",
            history=[(None, "OFF", t0), ("OFF", "OBSERVE", t0 + timedelta(seconds=1))],
        )

    with pytest.raises((InternalError, Exception)) as exc:
        command.upgrade(cfg, PHASE7_REVISION)
    assert "disagrees" in str(exc.value).lower() or "refused" in str(exc.value).lower()

    # Repair DB to a known head for subsequent tests.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM operating_mode_history"))
        conn.execute(text("DELETE FROM system_states"))
    command.upgrade(cfg, "head")
    reset_engine()
    clear_settings_cache()


def test_clean_database_base_to_head_includes_phase7() -> None:
    cfg = _alembic_config()
    engine = _engine()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == HEAD_REVISION
        )
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
        assert "operating_mode_idempotency" in tables
        assert "registered_services" in tables
        assert "health_heartbeats" in tables
    reset_engine()
    clear_settings_cache()
