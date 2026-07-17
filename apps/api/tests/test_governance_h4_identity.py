"""H4: Institutional Identity consistency and mapped-kind retirement policy."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import reset_engine
from app.models import (
    AuthSession,
    DraftAuthority,
    InstitutionalIdentity,
    InstitutionalRole,
    PolicyDocument,
    PolicyKind,
    PolicyVersion,
    User,
    UserRole,
    VersionLifecycleStatus,
)
from app.services.auth_service import AuthenticatedPrincipal
from app.services.governance_service import (
    GovernanceError,
    GovernanceService,
    identity_pointer,
)


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
        username=_unique("h4f"),
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


def _ensure_identity(session: Session) -> InstitutionalIdentity:
    existing = session.scalars(select(InstitutionalIdentity).limit(1)).first()
    if existing is not None:
        return existing
    row = InstitutionalIdentity(
        institution_name="Argus",
        institution_id=_unique("argus"),
        product_version="0.1.0",
        founding_date=date(2026, 7, 15),
        active_constitution_version="unset",
        active_operating_policy_version="unset",
        active_governance_version="unset",
        active_treasury_policy_version="unset",
        active_research_framework_version="unset",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _approved_mapped_version(
    session: Session,
    principal: AuthenticatedPrincipal,
    *,
    policy_kind: PolicyKind,
    schema_identifier: str,
    payload: dict,
) -> PolicyVersion:
    gov = GovernanceService(session)
    existing = session.scalars(
        select(PolicyDocument).where(
            PolicyDocument.policy_kind == policy_kind,
            PolicyDocument.is_retired.is_(False),
        )
    ).first()
    if existing is None:
        doc = gov.create_policy_document(
            actor=principal,
            document_key=_unique(f"pol.{policy_kind.value}"),
            name=f"{policy_kind.value} policy",
            policy_kind=policy_kind,
            description=None,
            schema_identifier=schema_identifier,
            draft_authority=DraftAuthority.FOUNDER_ONLY,
        )
        doc_id = doc.id
    else:
        doc_id = existing.id

    version = gov.create_policy_version(
        actor=principal,
        document_id=doc_id,
        payload={**payload, "_nonce": uuid.uuid4().hex},
    )
    gov.transition_policy_version(
        actor=principal,
        version_id=version.id,
        new_status=VersionLifecycleStatus.UNDER_REVIEW,
    )
    gov.transition_policy_version(
        actor=principal,
        version_id=version.id,
        new_status=VersionLifecycleStatus.APPROVED,
    )
    loaded = session.get(PolicyVersion, version.id)
    assert loaded is not None
    return loaded


def _approved_operating_version(
    session: Session, principal: AuthenticatedPrincipal, *, payload: dict
) -> PolicyVersion:
    return _approved_mapped_version(
        session,
        principal,
        policy_kind=PolicyKind.OPERATING,
        schema_identifier="policy.operating.v1",
        payload=payload,
    )


def test_identity_pointer_format() -> None:
    assert identity_pointer("pol.operating", 3) == "pol.operating@3"


def test_activation_updates_identity_with_stable_pointer(db: Session) -> None:
    principal = _founder(db)
    identity = _ensure_identity(db)
    version = _approved_operating_version(db, principal, payload={"summary": "ops-1"})
    gov = GovernanceService(db)
    activated = gov.activate_policy_version(actor=principal, version_id=version.id)
    db.refresh(identity)
    expected = identity_pointer(activated.document.document_key, activated.version_number)
    assert identity.active_operating_policy_version == expected
    assert activated.status == VersionLifecycleStatus.ACTIVE


def test_missing_identity_blocks_mapped_activation(db: Session) -> None:
    # Remove all identity rows for this assertion.
    for row in list(db.scalars(select(InstitutionalIdentity))):
        db.delete(row)
    db.commit()
    assert db.scalars(select(InstitutionalIdentity).limit(1)).first() is None

    principal = _founder(db)
    # Use RESEARCH to avoid collisions with OPERATING docs left by prior tests.
    version = _approved_mapped_version(
        db,
        principal,
        policy_kind=PolicyKind.RESEARCH,
        schema_identifier="policy.research.v1",
        payload={"summary": "no-id"},
    )
    gov = GovernanceService(db)
    with pytest.raises(GovernanceError, match="identity record missing"):
        gov.activate_policy_version(actor=principal, version_id=version.id)

    db.refresh(version)
    assert version.status == VersionLifecycleStatus.APPROVED


def test_cannot_retire_active_mapped_policy(db: Session) -> None:
    principal = _founder(db)
    _ensure_identity(db)
    version = _approved_mapped_version(
        db,
        principal,
        policy_kind=PolicyKind.GOVERNANCE,
        schema_identifier="policy.governance.v1",
        payload={"summary": "retire-block"},
    )
    gov = GovernanceService(db)
    activated = gov.activate_policy_version(actor=principal, version_id=version.id)
    with pytest.raises(GovernanceError, match="Cannot retire an ACTIVE mapped"):
        gov.transition_policy_version(
            actor=principal,
            version_id=activated.id,
            new_status=VersionLifecycleStatus.RETIRED,
        )
    db.refresh(activated)
    assert activated.status == VersionLifecycleStatus.ACTIVE


def test_supersession_updates_identity_pointer(db: Session) -> None:
    principal = _founder(db)
    identity = _ensure_identity(db)
    gov = GovernanceService(db)
    v1 = _approved_mapped_version(
        db,
        principal,
        policy_kind=PolicyKind.CONSTITUTION,
        schema_identifier="policy.constitution.v1",
        payload={"summary": "v1"},
    )
    doc_id = v1.document_id
    gov.activate_policy_version(actor=principal, version_id=v1.id)
    db.refresh(identity)
    first_pointer = identity.active_constitution_version

    v2 = gov.create_policy_version(
        actor=principal, document_id=doc_id, payload={"summary": "v2"}
    )
    gov.transition_policy_version(
        actor=principal,
        version_id=v2.id,
        new_status=VersionLifecycleStatus.UNDER_REVIEW,
    )
    gov.transition_policy_version(
        actor=principal,
        version_id=v2.id,
        new_status=VersionLifecycleStatus.APPROVED,
    )
    activated = gov.activate_policy_version(actor=principal, version_id=v2.id)
    db.refresh(identity)
    db.refresh(v1)
    assert v1.status == VersionLifecycleStatus.SUPERSEDED
    assert activated.status == VersionLifecycleStatus.ACTIVE
    assert identity.active_constitution_version == identity_pointer(
        activated.document.document_key, activated.version_number
    )
    assert identity.active_constitution_version != first_pointer


def test_duplicate_mapped_kind_document_rejected(db: Session) -> None:
    principal = _founder(db)
    gov = GovernanceService(db)
    existing = db.scalars(
        select(PolicyDocument).where(
            PolicyDocument.policy_kind == PolicyKind.TREASURY,
            PolicyDocument.is_retired.is_(False),
        )
    ).first()
    if existing is None:
        gov.create_policy_document(
            actor=principal,
            document_key=_unique("pol.treasury.a"),
            name="Treasury A",
            policy_kind=PolicyKind.TREASURY,
            description=None,
            schema_identifier="policy.treasury.v1",
        )
    # Second non-retired treasury document must violate unique index.
    doc_b = PolicyDocument(
        document_key=_unique("pol.treasury.b"),
        name="Treasury B",
        policy_kind=PolicyKind.TREASURY,
        schema_identifier="policy.treasury.v1",
        draft_authority=DraftAuthority.FOUNDER_ONLY,
    )
    db.add(doc_b)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
