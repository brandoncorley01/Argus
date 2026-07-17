"""PostgreSQL concurrency tests for operating-mode transitions."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import reset_engine
from app.models import (
    AuditEvent,
    AuthSession,
    InstitutionalRole,
    OperatingMode,
    OperatingModeHistory,
    SystemState,
    User,
    UserRole,
)
from app.services.audit_service import AuditError, AuditService
from app.services.auth_service import AuthenticatedPrincipal
from app.services.operating_mode_service import OperatingModeError, OperatingModeService


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _make_engine():
    clear_settings_cache()
    reset_engine()
    return create_engine(get_settings().database_url, pool_size=8, max_overflow=4)


def _bootstrap_founder(session: Session) -> tuple[User, AuthSession]:
    user = User(
        username=_unique("p7f"),
        email=None,
        password_hash="unused",
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role=InstitutionalRole.FOUNDER))
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        expires_at=datetime.now(UTC),
    )
    session.add(auth_session)
    session.commit()
    return user, auth_session


def _principal(user: User, auth_session: AuthSession) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user=user,
        roles=frozenset({InstitutionalRole.FOUNDER}),
        session=auth_session,
    )


def _cleanup_mode_tables(session: Session) -> None:
    session.execute(text("UPDATE system_states SET last_history_id = NULL"))
    session.execute(text("DELETE FROM operating_mode_idempotency"))
    session.execute(
        text(
            "ALTER TABLE operating_mode_history "
            "DISABLE TRIGGER trg_operating_mode_history_immutability"
        )
    )
    session.execute(text("DELETE FROM operating_mode_history"))
    session.execute(
        text(
            "ALTER TABLE operating_mode_history "
            "ENABLE TRIGGER trg_operating_mode_history_immutability"
        )
    )
    session.execute(text("DELETE FROM system_states"))
    session.execute(
        text(
            """
            DELETE FROM audit_events
            WHERE action LIKE 'operating_mode.%'
               OR resource_type IN ('operating_mode', 'system_state')
            """
        )
    )
    session.commit()


def test_concurrent_competing_transitions_one_winner() -> None:
    engine = _make_engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    setup = factory()
    try:
        _cleanup_mode_tables(setup)
        user, auth_session = _bootstrap_founder(setup)
        actor = _principal(user, auth_session)
        OperatingModeService(setup).initialize(actor=actor)
    finally:
        setup.close()

    def worker(target: OperatingMode, key: str) -> tuple[str, str | None]:
        session = factory()
        try:
            svc = OperatingModeService(session)
            result = svc.transition(
                actor=_principal(user, auth_session),
                target_mode=target,
                reason=f"to-{target.value}",
                idempotency_key=key,
                expected_state_version=1,
            )
            return ("ok", result["current_mode"])
        except OperatingModeError as exc:
            return (exc.code, None)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(worker, OperatingMode.OBSERVE, _unique("a")),
            pool.submit(worker, OperatingMode.SAFE_MODE, _unique("b")),
        ]
        outcomes = [f.result() for f in as_completed(futures)]

    verify = factory()
    try:
        state = verify.scalars(
            select(SystemState).where(SystemState.singleton_key == "current")
        ).one()
        assert state.state_version == 2
        assert state.current_mode in {OperatingMode.OBSERVE, OperatingMode.SAFE_MODE}
        history_count = verify.scalar(
            select(func.count()).select_from(OperatingModeHistory)
        )
        assert history_count == 2  # init + one transition
        assert sum(1 for code, _ in outcomes if code == "ok") == 1
        assert sum(1 for code, _ in outcomes if code == "stale_state") == 1
    finally:
        verify.close()
        engine.dispose()
        reset_engine()
        clear_settings_cache()


def test_concurrent_same_idempotency_key_replay() -> None:
    engine = _make_engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    setup = factory()
    key = _unique("same")
    try:
        _cleanup_mode_tables(setup)
        user, auth_session = _bootstrap_founder(setup)
        actor = _principal(user, auth_session)
        OperatingModeService(setup).initialize(actor=actor)
    finally:
        setup.close()

    def worker() -> dict:
        session = factory()
        try:
            return OperatingModeService(session).transition(
                actor=_principal(user, auth_session),
                target_mode=OperatingMode.OBSERVE,
                reason="observe",
                idempotency_key=key,
            )
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: worker(), range(4)))

    history_ids = {r["history_id"] for r in results}
    assert len(history_ids) == 1
    verify = factory()
    try:
        state = verify.scalars(
            select(SystemState).where(SystemState.singleton_key == "current")
        ).one()
        assert state.current_mode == OperatingMode.OBSERVE
        assert state.state_version == 2
        history_count = verify.scalar(
            select(func.count()).select_from(OperatingModeHistory)
        )
        assert history_count == 2
    finally:
        verify.close()
        engine.dispose()
        reset_engine()
        clear_settings_cache()


def test_concurrent_emergency_vs_ordinary() -> None:
    engine = _make_engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    setup = factory()
    try:
        _cleanup_mode_tables(setup)
        user, auth_session = _bootstrap_founder(setup)
        actor = _principal(user, auth_session)
        OperatingModeService(setup).initialize(actor=actor)
    finally:
        setup.close()

    def ordinary() -> str:
        session = factory()
        try:
            OperatingModeService(session).transition(
                actor=_principal(user, auth_session),
                target_mode=OperatingMode.OBSERVE,
                reason="observe",
                idempotency_key=_unique("ord"),
                expected_state_version=1,
            )
            return "ok"
        except OperatingModeError as exc:
            return exc.code
        finally:
            session.close()

    def emergency() -> str:
        session = factory()
        try:
            OperatingModeService(session).emergency_stop(
                actor=_principal(user, auth_session),
                reason="halt",
                idempotency_key=_unique("em"),
                expected_state_version=1,
            )
            return "ok"
        except OperatingModeError as exc:
            return exc.code
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(ordinary)
        f2 = pool.submit(emergency)
        codes = {f1.result(), f2.result()}

    verify = factory()
    try:
        state = verify.scalars(
            select(SystemState).where(SystemState.singleton_key == "current")
        ).one()
        assert state.state_version == 2
        assert "ok" in codes
        assert "stale_state" in codes
        assert state.current_mode in {OperatingMode.OBSERVE, OperatingMode.EMERGENCY_STOP}
        audit_count = verify.scalar(select(func.count()).select_from(AuditEvent))
        assert audit_count is not None and audit_count >= 2
    finally:
        verify.close()
        engine.dispose()
        reset_engine()
        clear_settings_cache()


def test_concurrent_initialize_exactly_once() -> None:
    engine = _make_engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    setup = factory()
    try:
        _cleanup_mode_tables(setup)
        user, auth_session = _bootstrap_founder(setup)
    finally:
        setup.close()

    def worker() -> tuple[str, int | None]:
        session = factory()
        try:
            state = OperatingModeService(session).initialize(
                actor=_principal(user, auth_session),
                request_id=_unique("req"),
            )
            return ("ok", state.state_version)
        except Exception as exc:  # noqa: BLE001 — assert no raw integrity leakage
            return (type(exc).__name__, None)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: worker(), range(8)))

    assert all(code == "ok" for code, _ in results)
    versions = {version for _, version in results}
    assert versions == {1}

    verify = factory()
    try:
        states = list(verify.scalars(select(SystemState)))
        assert len(states) == 1
        assert states[0].current_mode == OperatingMode.OFF
        assert states[0].state_version == 1
        history_count = verify.scalar(
            select(func.count()).select_from(OperatingModeHistory)
        )
        assert history_count == 1
        init_audits = verify.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == "operating_mode.initialized",
                AuditEvent.resource_id == str(states[0].id),
            )
        )
        assert init_audits == 1

        # Later initialize remains idempotent.
        again = OperatingModeService(verify).initialize(
            actor=_principal(user, auth_session)
        )
        assert again.id == states[0].id
        assert (
            verify.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.action == "operating_mode.initialized",
                    AuditEvent.resource_id == str(states[0].id),
                )
            )
            == 1
        )
    finally:
        verify.close()

    # Audit fault injection still rolls back initialization on a clean DB.
    fault = factory()
    try:
        _cleanup_mode_tables(fault)
        user2, auth2 = _bootstrap_founder(fault)
        with patch.object(AuditService, "append", side_effect=AuditError("forced")):
            with pytest.raises(OperatingModeError) as exc:
                OperatingModeService(fault).initialize(actor=_principal(user2, auth2))
            assert exc.value.code == "audit_unavailable"
        assert fault.scalars(select(SystemState)).first() is None
        assert fault.scalar(select(func.count()).select_from(OperatingModeHistory)) == 0
    finally:
        fault.close()
        engine.dispose()
        reset_engine()
        clear_settings_cache()
