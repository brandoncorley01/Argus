"""H1 regression: legacy inactive versions must not become editable DRAFT."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.settings import clear_settings_cache, get_settings
from app.db.session import reset_engine
from app.models import (
    AuthSession,
    ConfigurationVersion,
    InstitutionalRole,
    PolicyVersion,
    User,
    VersionLifecycleStatus,
)
from app.services.auth_service import AuthenticatedPrincipal
from app.services.governance_service import GovernanceError, GovernanceService

API_ROOT = Path(__file__).resolve().parents[1]
PHASE5_REVISION = "5bb9b33b045b"
PHASE6_REVISION = "c6a1f0e9d2b8"
PHASE7_REVISION = "a7b8c9d0e1f2"


def _alembic_config() -> Config:
    return Config(str(API_ROOT / "alembic.ini"))


def test_legacy_inactive_versions_migrate_to_superseded_not_draft() -> None:
    """
    Representative pre-Phase-6 rows:
    - one ACTIVE (is_active=true)
    - one inactive (is_active=false)

    After upgrade:
    - active → ACTIVE
    - inactive → SUPERSEDED (never DRAFT)
    - superseded payload cannot be edited via GovernanceService
    """
    clear_settings_cache()
    reset_engine()
    cfg = _alembic_config()
    settings = get_settings()
    engine = create_engine(settings.database_url)

    command.downgrade(cfg, PHASE5_REVISION)

    with engine.begin() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == PHASE5_REVISION

        # Confirm Phase-5 shape still has is_active.
        cols = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'configuration_versions'
                    """
                )
            )
        }
        assert "is_active" in cols
        assert "status" not in cols

        cfg_doc_id = uuid.uuid4()
        cfg_active_id = uuid.uuid4()
        cfg_inactive_id = uuid.uuid4()
        pol_doc_id = uuid.uuid4()
        pol_active_id = uuid.uuid4()
        pol_inactive_id = uuid.uuid4()

        conn.execute(
            text(
                """
                INSERT INTO configuration_documents (id, document_key, name, description)
                VALUES (:id, :key, :name, NULL)
                """
            ),
            {"id": cfg_doc_id, "key": f"cfg.legacy.h1.{cfg_doc_id.hex[:8]}", "name": "Legacy Cfg"},
        )
        conn.execute(
            text(
                """
                INSERT INTO configuration_versions
                    (id, document_id, version_label, content, is_active)
                VALUES
                    (:active_id, :doc_id, 'legacy-active',
                     CAST(:active_content AS jsonb), true),
                    (:inactive_id, :doc_id, 'legacy-inactive',
                     CAST(:inactive_content AS jsonb), false)
                """
            ),
            {
                "doc_id": cfg_doc_id,
                "active_id": cfg_active_id,
                "inactive_id": cfg_inactive_id,
                "active_content": '{"phase":"5","role":"active"}',
                "inactive_content": '{"phase":"5","role":"inactive"}',
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO policy_documents (id, document_key, name, policy_kind, description)
                VALUES (:id, :key, :name, 'other', NULL)
                """
            ),
            {"id": pol_doc_id, "key": f"pol.legacy.h1.{pol_doc_id.hex[:8]}", "name": "Legacy Pol"},
        )
        conn.execute(
            text(
                """
                INSERT INTO policy_versions
                    (id, document_id, version_label, content, is_active)
                VALUES
                    (:active_id, :doc_id, 'legacy-active',
                     CAST(:active_content AS jsonb), true),
                    (:inactive_id, :doc_id, 'legacy-inactive',
                     CAST(:inactive_content AS jsonb), false)
                """
            ),
            {
                "doc_id": pol_doc_id,
                "active_id": pol_active_id,
                "inactive_id": pol_inactive_id,
                "active_content": '{"phase":"5","role":"active"}',
                "inactive_content": '{"phase":"5","role":"inactive"}',
            },
        )

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert head == PHASE7_REVISION

        cfg_rows = {
            row.version_label: row
            for row in conn.execute(
                text(
                    """
                    SELECT id, version_label, status::text AS status, payload_hash, superseded_at
                    FROM configuration_versions
                    WHERE document_id = :doc_id
                    """
                ),
                {"doc_id": cfg_doc_id},
            )
        }
        assert cfg_rows["legacy-active"].status == "ACTIVE"
        assert cfg_rows["legacy-inactive"].status == "SUPERSEDED"
        assert cfg_rows["legacy-inactive"].status != "DRAFT"
        assert cfg_rows["legacy-inactive"].superseded_at is not None
        assert cfg_rows["legacy-inactive"].payload_hash
        assert cfg_rows["legacy-active"].payload_hash

        pol_rows = {
            row.version_label: row
            for row in conn.execute(
                text(
                    """
                    SELECT id, version_label, status::text AS status, superseded_at
                    FROM policy_versions
                    WHERE document_id = :doc_id
                    """
                ),
                {"doc_id": pol_doc_id},
            )
        }
        assert pol_rows["legacy-active"].status == "ACTIVE"
        assert pol_rows["legacy-inactive"].status == "SUPERSEDED"
        assert pol_rows["legacy-inactive"].status != "DRAFT"
        assert pol_rows["legacy-inactive"].superseded_at is not None

    # Service-layer proof: migrated SUPERSEDED must not be editable.
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session: Session = SessionLocal()
    try:
        founder = User(
            username=f"h1_founder_{uuid.uuid4().hex[:8]}",
            email=None,
            password_hash="not-used-for-h1",
            is_active=True,
        )
        session.add(founder)
        session.flush()
        from app.models import UserRole

        session.add(UserRole(user_id=founder.id, role=InstitutionalRole.FOUNDER))
        fake_session = AuthSession(
            user_id=founder.id,
            token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            expires_at=datetime.now(UTC),
        )
        session.add(fake_session)
        session.commit()

        principal = AuthenticatedPrincipal(
            user=founder,
            roles=frozenset({InstitutionalRole.FOUNDER}),
            session=fake_session,
        )
        gov = GovernanceService(session)

        with pytest.raises(GovernanceError, match="Only DRAFT"):
            gov.update_configuration_draft(
                actor=principal,
                version_id=cfg_inactive_id,
                payload={"tamper": True},
            )
        session.rollback()

        with pytest.raises(GovernanceError, match="Only DRAFT"):
            gov.update_policy_draft(
                actor=principal,
                version_id=pol_inactive_id,
                payload={"tamper": True},
            )
        session.rollback()

        cfg_inactive = session.get(ConfigurationVersion, cfg_inactive_id)
        pol_inactive = session.get(PolicyVersion, pol_inactive_id)
        assert cfg_inactive is not None
        assert pol_inactive is not None
        assert cfg_inactive.status == VersionLifecycleStatus.SUPERSEDED
        assert pol_inactive.status == VersionLifecycleStatus.SUPERSEDED
        assert cfg_inactive.content == {"phase": "5", "role": "inactive"}
        assert pol_inactive.content == {"phase": "5", "role": "inactive"}
    finally:
        session.close()
        reset_engine()
        clear_settings_cache()
