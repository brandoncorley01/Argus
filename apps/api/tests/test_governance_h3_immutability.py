"""H3: database-enforced immutability of published version payloads."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import reset_engine
from app.models import (
    AuthSession,
    ConfigurationDocument,
    ConfigurationVersion,
    DraftAuthority,
    InstitutionalRole,
    PolicyDocument,
    PolicyKind,
    PolicyVersion,
    User,
    UserRole,
    VersionLifecycleStatus,
)
from app.services.auth_service import AuthenticatedPrincipal
from app.services.governance_service import GovernanceError, GovernanceService
from app.services.payload_integrity import hash_payload


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@pytest.fixture
def db() -> Session:
    clear_settings_cache()
    reset_engine()
    engine = create_engine(get_settings().database_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
        engine.dispose()
        reset_engine()
        clear_settings_cache()


def _founder(session: Session) -> AuthenticatedPrincipal:
    user = User(
        username=_unique("h3f"),
        email=None,
        password_hash="unused",
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role=InstitutionalRole.FOUNDER))
    auth = AuthSession(
        user_id=user.id,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        expires_at=datetime.now(UTC),
    )
    session.add(auth)
    session.commit()
    return AuthenticatedPrincipal(
        user=user,
        roles=frozenset({InstitutionalRole.FOUNDER}),
        session=auth,
    )


def _cfg_version(
    session: Session, *, status: VersionLifecycleStatus, payload: dict
) -> ConfigurationVersion:
    doc = ConfigurationDocument(
        document_key=_unique("cfg.h3"),
        name="H3 Config",
        schema_identifier="config.generic.v1",
        draft_authority=DraftAuthority.FOUNDER_ONLY,
    )
    session.add(doc)
    session.flush()
    row = ConfigurationVersion(
        document_id=doc.id,
        version_number=1,
        version_label="v1",
        status=status,
        content=payload,
        payload_hash=hash_payload(payload),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _pol_version(
    session: Session, *, status: VersionLifecycleStatus, payload: dict
) -> PolicyVersion:
    doc = PolicyDocument(
        document_key=_unique("pol.h3"),
        name="H3 Policy",
        policy_kind=PolicyKind.OTHER,
        schema_identifier="policy.generic.v1",
        draft_authority=DraftAuthority.FOUNDER_ONLY,
    )
    session.add(doc)
    session.flush()
    row = PolicyVersion(
        document_id=doc.id,
        version_number=1,
        version_label="v1",
        status=status,
        content=payload,
        payload_hash=hash_payload(payload),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _assert_immutable_blocked(session: Session, mutate) -> None:
    with pytest.raises((DBAPIError, IntegrityError, StatementError)):
        mutate()
        session.commit()
    session.rollback()


def test_immutability_triggers_installed(db: Session) -> None:
    rows = db.execute(
        text("SELECT tgname FROM pg_trigger WHERE tgname LIKE 'trg_%immutability' ORDER BY 1")
    ).fetchall()
    names = {r[0] for r in rows}
    assert "trg_configuration_versions_immutability" in names
    assert "trg_policy_versions_immutability" in names


def test_draft_content_may_be_updated_via_service(db: Session) -> None:
    principal = _founder(db)
    gov = GovernanceService(db)
    doc = gov.create_configuration_document(
        actor=principal,
        document_key=_unique("cfg.h3.draft"),
        name="Draftable",
        description=None,
        schema_identifier="config.generic.v1",
        draft_authority=DraftAuthority.FOUNDER_ONLY,
    )
    version = gov.create_configuration_version(
        actor=principal,
        document_id=doc.id,
        payload={"a": 1},
    )
    updated = gov.update_configuration_draft(
        actor=principal,
        version_id=version.id,
        payload={"a": 2},
    )
    assert updated.status == VersionLifecycleStatus.DRAFT
    assert updated.content == {"a": 2}
    assert updated.payload_hash == hash_payload({"a": 2})


@pytest.mark.parametrize(
    "status",
    [
        VersionLifecycleStatus.UNDER_REVIEW,
        VersionLifecycleStatus.APPROVED,
        VersionLifecycleStatus.ACTIVE,
        VersionLifecycleStatus.SUPERSEDED,
        VersionLifecycleStatus.REJECTED,
        VersionLifecycleStatus.RETIRED,
    ],
)
def test_published_configuration_content_cannot_change(
    db: Session, status: VersionLifecycleStatus
) -> None:
    payload = {"locked": True, "status_seed": status.value}
    row = _cfg_version(db, status=status, payload=payload)
    original_hash = row.payload_hash

    def mutate_content() -> None:
        row.content = {"locked": False, "tampered": True}
        db.add(row)

    _assert_immutable_blocked(db, mutate_content)

    db.refresh(row)
    assert row.content == payload
    assert row.payload_hash == original_hash

    def mutate_hash() -> None:
        row.payload_hash = "0" * 64
        db.add(row)

    _assert_immutable_blocked(db, mutate_hash)
    db.refresh(row)
    assert row.payload_hash == original_hash


@pytest.mark.parametrize(
    "status",
    [
        VersionLifecycleStatus.UNDER_REVIEW,
        VersionLifecycleStatus.APPROVED,
        VersionLifecycleStatus.ACTIVE,
        VersionLifecycleStatus.SUPERSEDED,
        VersionLifecycleStatus.REJECTED,
        VersionLifecycleStatus.RETIRED,
    ],
)
def test_published_policy_content_cannot_change(
    db: Session, status: VersionLifecycleStatus
) -> None:
    payload = {"locked": True, "status_seed": status.value}
    row = _pol_version(db, status=status, payload=payload)

    def mutate() -> None:
        row.content = {"tampered": True}
        row.payload_hash = hash_payload({"tampered": True})
        db.add(row)

    _assert_immutable_blocked(db, mutate)
    db.refresh(row)
    assert row.content == payload


def test_direct_sql_update_blocked_for_active_configuration(db: Session) -> None:
    row = _cfg_version(
        db, status=VersionLifecycleStatus.ACTIVE, payload={"sql": "protected"}
    )
    with pytest.raises(DBAPIError):
        db.execute(
            text(
                "UPDATE configuration_versions "
                "SET content = CAST(:content AS jsonb), payload_hash = :ph "
                "WHERE id = :id"
            ),
            {
                "content": '{"sql":"tampered"}',
                "ph": "a" * 64,
                "id": row.id,
            },
        )
        db.commit()
    db.rollback()
    db.refresh(row)
    assert row.content == {"sql": "protected"}


def test_lifecycle_status_update_still_allowed(db: Session) -> None:
    """Status/attribution changes must not be blocked by the immutability trigger."""
    row = _cfg_version(
        db, status=VersionLifecycleStatus.APPROVED, payload={"ok": True}
    )
    row.status = VersionLifecycleStatus.ACTIVE
    row.activated_at = datetime.now(UTC)
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.status == VersionLifecycleStatus.ACTIVE
    assert row.content == {"ok": True}


def test_service_rejects_non_draft_edit(db: Session) -> None:
    principal = _founder(db)
    row = _cfg_version(
        db, status=VersionLifecycleStatus.UNDER_REVIEW, payload={"x": 1}
    )
    gov = GovernanceService(db)
    with pytest.raises(GovernanceError, match="Only DRAFT"):
        gov.update_configuration_draft(
            actor=principal,
            version_id=row.id,
            payload={"x": 2},
        )
