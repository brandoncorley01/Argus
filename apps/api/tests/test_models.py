from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.models import (
    AuditEvent,
    ConfigurationDocument,
    ConfigurationVersion,
    DepartmentCapability,
    FeatureActivationState,
    FeatureRegistryEntry,
    FeatureStatus,
    HealthStatus,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    InstitutionalIdentity,
    InstitutionalRole,
    OperatingMode,
    OperatingModeHistory,
    PolicyDocument,
    PolicyKind,
    PolicyVersion,
    ServiceHealthEvent,
    SystemState,
    User,
    UserRole,
)


@pytest.fixture
def db_session() -> Iterator[Session]:
    clear_settings_cache()
    reset_engine()
    get_settings()
    session = get_session_factory()()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
        reset_engine()
        clear_settings_cache()


def test_create_and_read_institutional_identity(db_session: Session) -> None:
    row = InstitutionalIdentity(
        institution_name="Argus",
        institution_id="argus-001-test",
        product_version="0.1.0-foundation",
        founding_date=date(2026, 7, 15),
        active_constitution_version="constitution-v0.1",
        active_operating_policy_version="operating-policy-v0.1",
        active_governance_version="governance-v0.1",
        active_treasury_policy_version="treasury-policy-v0.1",
        active_research_framework_version="research-framework-v0.1",
    )
    db_session.add(row)
    db_session.commit()

    loaded = db_session.get(InstitutionalIdentity, row.id)
    assert loaded is not None
    assert loaded.institution_name == "Argus"
    assert loaded.institution_id == "argus-001-test"


def test_user_role_create_and_unique_constraint(db_session: Session) -> None:
    user = User(
        username="founder_test",
        email="founder_test@example.com",
        password_hash="not-a-real-hash",
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role=InstitutionalRole.FOUNDER))
    db_session.commit()

    roles = list(db_session.scalars(select(UserRole).where(UserRole.user_id == user.id)))
    assert len(roles) == 1
    assert roles[0].role == InstitutionalRole.FOUNDER

    db_session.add(UserRole(user_id=user.id, role=InstitutionalRole.FOUNDER))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_username_rejected(db_session: Session) -> None:
    db_session.add(User(username="dup_user", email="a@example.com", password_hash="x"))
    db_session.commit()
    db_session.add(User(username="dup_user", email="b@example.com", password_hash="y"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_feature_locked_requires_lock_reason(db_session: Session) -> None:
    entry = FeatureRegistryEntry(
        feature_key="feat.test.locked",
        feature_name="Locked Feature",
        status=FeatureStatus.PLANNED,
        capability_level=1,
        version="0.1.0",
        activation_state=FeatureActivationState.LOCKED,
        lock_reason=None,
        dependencies=[],
        last_reviewed_at=datetime.now(UTC),
    )
    db_session.add(entry)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_feature_capability_level_bounds(db_session: Session) -> None:
    entry = FeatureRegistryEntry(
        feature_key="feat.test.bad_level",
        feature_name="Bad Level",
        status=FeatureStatus.PLANNED,
        capability_level=7,
        version="0.1.0",
        activation_state=FeatureActivationState.INACTIVE,
        dependencies=[],
        last_reviewed_at=datetime.now(UTC),
    )
    db_session.add(entry)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_one_active_configuration_version_per_document(db_session: Session) -> None:
    doc = ConfigurationDocument(document_key="cfg.test", name="Test Config")
    db_session.add(doc)
    db_session.flush()
    db_session.add(
        ConfigurationVersion(
            document_id=doc.id, version_label="v1", content={"a": 1}, is_active=True
        )
    )
    db_session.commit()
    db_session.add(
        ConfigurationVersion(
            document_id=doc.id, version_label="v2", content={"a": 2}, is_active=True
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_closed_incident_requires_closed_at(db_session: Session) -> None:
    incident = Incident(
        title="Test incident",
        severity=IncidentSeverity.HIGH,
        status=IncidentStatus.CLOSED,
        closed_at=None,
    )
    db_session.add(incident)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_system_state_singleton_and_mode_history(db_session: Session) -> None:
    state = SystemState(singleton_key="current", current_mode=OperatingMode.OFF, reason="bootstrap")
    db_session.add(state)
    db_session.add(
        OperatingModeHistory(from_mode=None, to_mode=OperatingMode.OFF, reason="initial")
    )
    db_session.add(
        ServiceHealthEvent(
            service_name="postgres",
            status=HealthStatus.HEALTHY,
            detail="meaningful event",
            observed_at=datetime.now(UTC),
        )
    )
    db_session.add(
        AuditEvent(
            action="system.bootstrap",
            resource_type="system_state",
            mode_at_time=OperatingMode.OFF,
            payload={"note": "phase3"},
        )
    )
    db_session.add(
        DepartmentCapability(
            department_key="governance",
            department_name="Governance",
            capability_level=1,
            last_reviewed_at=datetime.now(UTC),
        )
    )
    policy = PolicyDocument(
        document_key="pol.operating",
        name="Operating Policy",
        policy_kind=PolicyKind.OPERATING,
    )
    db_session.add(policy)
    db_session.flush()
    db_session.add(
        PolicyVersion(
            document_id=policy.id,
            version_label="operating-policy-v0.1",
            content={"summary": "baseline"},
            is_active=True,
        )
    )
    db_session.commit()

    db_session.add(SystemState(singleton_key="current", current_mode=OperatingMode.SAFE_MODE))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
