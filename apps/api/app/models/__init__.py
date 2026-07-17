from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy 2.x declarative base for Argus institutional models."""


class InstitutionalRole(enum.StrEnum):
    FOUNDER = "FOUNDER"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


class OperatingMode(enum.StrEnum):
    OFF = "OFF"
    OBSERVE = "OBSERVE"
    PAPER = "PAPER"
    MICRO_LIVE = "MICRO_LIVE"
    NORMAL_LIVE = "NORMAL_LIVE"
    SAFE_MODE = "SAFE_MODE"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class FeatureStatus(enum.StrEnum):
    PLANNED = "planned"
    SCAFFOLDED = "scaffolded"
    IMPLEMENTED = "implemented"
    VALIDATED = "validated"
    DEPRECATED = "deprecated"


class FeatureActivationState(enum.StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    LOCKED = "locked"


class PolicyKind(enum.StrEnum):
    CONSTITUTION = "constitution"
    OPERATING = "operating"
    GOVERNANCE = "governance"
    TREASURY = "treasury"
    RESEARCH = "research"
    OTHER = "other"


class HealthStatus(enum.StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class IncidentSeverity(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(enum.StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    CLOSED = "closed"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


institutional_role_enum = Enum(
    InstitutionalRole,
    name="institutional_role",
    values_callable=_enum_values,
    native_enum=True,
)
operating_mode_enum = Enum(
    OperatingMode,
    name="operating_mode",
    values_callable=_enum_values,
    native_enum=True,
)
feature_status_enum = Enum(
    FeatureStatus,
    name="feature_status",
    values_callable=_enum_values,
    native_enum=True,
)
feature_activation_state_enum = Enum(
    FeatureActivationState,
    name="feature_activation_state",
    values_callable=_enum_values,
    native_enum=True,
)
policy_kind_enum = Enum(
    PolicyKind,
    name="policy_kind",
    values_callable=_enum_values,
    native_enum=True,
)
health_status_enum = Enum(
    HealthStatus,
    name="health_status",
    values_callable=_enum_values,
    native_enum=True,
)
incident_severity_enum = Enum(
    IncidentSeverity,
    name="incident_severity",
    values_callable=_enum_values,
    native_enum=True,
)
incident_status_enum = Enum(
    IncidentStatus,
    name="incident_status",
    values_callable=_enum_values,
    native_enum=True,
)


class InstitutionalIdentity(Base):
    __tablename__ = "institutional_identities"
    __table_args__ = (
        UniqueConstraint("institution_id", name="uq_institutional_identities_institution_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_name: Mapped[str] = mapped_column(String(128), nullable=False)
    institution_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_version: Mapped[str] = mapped_column(String(64), nullable=False)
    founding_date: Mapped[date] = mapped_column(Date, nullable=False)
    active_constitution_version: Mapped[str] = mapped_column(String(128), nullable=False)
    active_operating_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    active_governance_version: Mapped[str] = mapped_column(String(128), nullable=False)
    active_treasury_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    active_research_framework_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    roles: Mapped[list[UserRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role", name="uq_user_roles_user_id_role"),
        Index("ix_user_roles_role", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[InstitutionalRole] = mapped_column(institutional_role_enum, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="roles")


class ConfigurationDocument(Base):
    __tablename__ = "configuration_documents"
    __table_args__ = (
        UniqueConstraint("document_key", name="uq_configuration_documents_document_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    versions: Mapped[list[ConfigurationVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class ConfigurationVersion(Base):
    __tablename__ = "configuration_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_label", name="uq_configuration_versions_document_version"
        ),
        Index(
            "uq_configuration_versions_one_active_per_document",
            "document_id",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("configuration_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[ConfigurationDocument] = relationship(back_populates="versions")


class PolicyDocument(Base):
    __tablename__ = "policy_documents"
    __table_args__ = (
        UniqueConstraint("document_key", name="uq_policy_documents_document_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    policy_kind: Mapped[PolicyKind] = mapped_column(policy_kind_enum, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    versions: Mapped[list[PolicyVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_label", name="uq_policy_versions_document_version"
        ),
        Index(
            "uq_policy_versions_one_active_per_document",
            "document_id",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_documents.id", ondelete="CASCADE"), nullable=False
    )
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[PolicyDocument] = relationship(back_populates="versions")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_action", "action"),
        Index("ix_audit_events_actor_user_id", "actor_user_id"),
        Index("ix_audit_events_resource", "resource_type", "resource_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mode_at_time: Mapped[OperatingMode | None] = mapped_column(operating_mode_enum, nullable=True)
    config_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("configuration_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_versions.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FeatureRegistryEntry(Base):
    __tablename__ = "feature_registry_entries"
    __table_args__ = (
        UniqueConstraint("feature_key", name="uq_feature_registry_entries_feature_key"),
        CheckConstraint(
            "capability_level >= 0 AND capability_level <= 6",
            name="ck_feature_registry_entries_capability_level",
        ),
        CheckConstraint(
            "(activation_state::text <> 'locked') OR "
            "(lock_reason IS NOT NULL AND length(trim(lock_reason)) > 0)",
            name="ck_feature_registry_entries_lock_reason_required",
        ),
        Index("ix_feature_registry_entries_activation_state", "activation_state"),
        Index("ix_feature_registry_entries_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_key: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[FeatureStatus] = mapped_column(feature_status_enum, nullable=False)
    capability_level: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    activation_state: Mapped[FeatureActivationState] = mapped_column(
        feature_activation_state_enum, nullable=False
    )
    lock_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependencies: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    last_reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DepartmentCapability(Base):
    __tablename__ = "department_capabilities"
    __table_args__ = (
        UniqueConstraint("department_key", name="uq_department_capabilities_department_key"),
        CheckConstraint(
            "capability_level >= 0 AND capability_level <= 6",
            name="ck_department_capabilities_capability_level",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_key: Mapped[str] = mapped_column(String(128), nullable=False)
    department_name: Mapped[str] = mapped_column(String(256), nullable=False)
    capability_level: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SystemState(Base):
    """Singleton current operating-mode row (enforced by singleton_key uniqueness)."""

    __tablename__ = "system_states"
    __table_args__ = (UniqueConstraint("singleton_key", name="uq_system_states_singleton_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    singleton_key: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'current'")
    )
    current_mode: Mapped[OperatingMode] = mapped_column(operating_mode_enum, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OperatingModeHistory(Base):
    __tablename__ = "operating_mode_history"
    __table_args__ = (Index("ix_operating_mode_history_changed_at", "changed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_mode: Mapped[OperatingMode | None] = mapped_column(operating_mode_enum, nullable=True)
    to_mode: Mapped[OperatingMode] = mapped_column(operating_mode_enum, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ServiceHealthEvent(Base):
    """Meaningful health-state events (not high-frequency probe samples)."""

    __tablename__ = "service_health_events"
    __table_args__ = (
        Index("ix_service_health_events_observed_at", "observed_at"),
        Index("ix_service_health_events_service_name", "service_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[HealthStatus] = mapped_column(health_status_enum, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_status", "status"),
        Index("ix_incidents_opened_at", "opened_at"),
        CheckConstraint(
            "(status::text <> 'closed') OR (closed_at IS NOT NULL)",
            name="ck_incidents_closed_requires_closed_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[IncidentSeverity] = mapped_column(incident_severity_enum, nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(incident_status_enum, nullable=False)
    related_mode: Mapped[OperatingMode | None] = mapped_column(operating_mode_enum, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


__all__ = [
    "Base",
    "InstitutionalIdentity",
    "User",
    "UserRole",
    "AuditEvent",
    "ConfigurationDocument",
    "ConfigurationVersion",
    "PolicyDocument",
    "PolicyVersion",
    "FeatureRegistryEntry",
    "DepartmentCapability",
    "SystemState",
    "OperatingModeHistory",
    "ServiceHealthEvent",
    "Incident",
    "InstitutionalRole",
    "OperatingMode",
    "FeatureStatus",
    "FeatureActivationState",
    "PolicyKind",
    "HealthStatus",
    "IncidentSeverity",
    "IncidentStatus",
]
