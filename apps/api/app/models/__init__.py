from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


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
    SECURITY = "security"
    AUDIT = "audit"
    AUTHENTICATION = "authentication"
    FEATURE_GOVERNANCE = "feature_governance"
    OTHER = "other"


class VersionLifecycleStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


class DraftAuthority(enum.StrEnum):
    """Who may create/edit DRAFT versions for a configuration/policy document.

    FOUNDER may always draft, regardless of this setting. OPERATOR may draft
    only when the document is explicitly set to FOUNDER_OR_OPERATOR. This is
    independent of governance-critical policy kinds, which always require
    FOUNDER regardless of draft_authority (see GovernanceService).
    """

    FOUNDER_ONLY = "FOUNDER_ONLY"
    FOUNDER_OR_OPERATOR = "FOUNDER_OR_OPERATOR"


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


class ServiceKind(enum.StrEnum):
    POSTGRES = "postgres"
    REDIS = "redis"
    API = "api"
    WORKER = "worker"
    SUPERVISOR = "supervisor"
    OTHER = "other"


class ServiceCriticality(enum.StrEnum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    INFORMATIONAL = "informational"


class WorkerInstanceStatus(enum.StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    STALE = "stale"


class ProtectiveActionType(enum.StrEnum):
    RECOMMEND_SAFE_MODE = "recommend_safe_mode"
    ENTER_SAFE_MODE = "enter_safe_mode"
    RECOMMEND_OBSERVE_ONLY = "recommend_observe_only"
    ESCALATE_INCIDENT = "escalate_incident"


class ProtectiveActionStatus(enum.StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    DISMISSED = "dismissed"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class IncidentLifecycleEventType(enum.StrEnum):
    OPENED = "opened"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    CLOSED = "closed"
    NOTE = "note"
    SEVERITY_CHANGED = "severity_changed"


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
version_lifecycle_status_enum = Enum(
    VersionLifecycleStatus,
    name="version_lifecycle_status",
    values_callable=_enum_values,
    native_enum=True,
)
draft_authority_enum = Enum(
    DraftAuthority,
    name="draft_authority",
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
service_kind_enum = Enum(
    ServiceKind,
    name="service_kind",
    values_callable=_enum_values,
    native_enum=True,
)
service_criticality_enum = Enum(
    ServiceCriticality,
    name="service_criticality",
    values_callable=_enum_values,
    native_enum=True,
)
worker_instance_status_enum = Enum(
    WorkerInstanceStatus,
    name="worker_instance_status",
    values_callable=_enum_values,
    native_enum=True,
)
protective_action_type_enum = Enum(
    ProtectiveActionType,
    name="protective_action_type",
    values_callable=_enum_values,
    native_enum=True,
)
protective_action_status_enum = Enum(
    ProtectiveActionStatus,
    name="protective_action_status",
    values_callable=_enum_values,
    native_enum=True,
)
incident_lifecycle_event_type_enum = Enum(
    IncidentLifecycleEventType,
    name="incident_lifecycle_event_type",
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
    # Widened to 256 to hold the `{document_key}@{version_number}` identity
    # pointer format (ADR-014), which can exceed the original 128-char budget.
    active_constitution_version: Mapped[str] = mapped_column(String(256), nullable=False)
    active_operating_policy_version: Mapped[str] = mapped_column(String(256), nullable=False)
    active_governance_version: Mapped[str] = mapped_column(String(256), nullable=False)
    active_treasury_policy_version: Mapped[str] = mapped_column(String(256), nullable=False)
    active_research_framework_version: Mapped[str] = mapped_column(String(256), nullable=False)
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


class AuthSession(Base):
    """Server-side session. Cookie carries opaque token; only token_hash is stored."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user: Mapped[User] = relationship()


class LoginAttempt(Base):
    """Failed/successful login attempts for lockout controls (no secrets stored)."""

    __tablename__ = "login_attempts"
    __table_args__ = (
        Index("ix_login_attempts_identifier_ip_time", "identifier", "ip_address", "attempted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identifier: Mapped[str] = mapped_column(String(320), nullable=False)
    ip_address: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'unknown'")
    )
    successful: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConfigurationDocument(Base):
    __tablename__ = "configuration_documents"
    __table_args__ = (
        UniqueConstraint("document_key", name="uq_configuration_documents_document_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_identifier: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default=text("'config.generic.v1'")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_retired: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    draft_authority: Mapped[DraftAuthority] = mapped_column(
        draft_authority_enum, nullable=False, server_default=text("'FOUNDER_ONLY'")
    )
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
            "document_id", "version_number", name="uq_configuration_versions_document_number"
        ),
        Index(
            "uq_configuration_versions_one_active_per_document",
            "document_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_configuration_versions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("configuration_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[VersionLifecycleStatus] = mapped_column(
        version_lifecycle_status_enum,
        nullable=False,
        server_default=text("'DRAFT'"),
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("configuration_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[ConfigurationDocument] = relationship(back_populates="versions")


_MAPPED_POLICY_KINDS_SQL = (
    "policy_kind IN ('constitution', 'operating', 'governance', 'treasury', 'research')"
)


class PolicyDocument(Base):
    __tablename__ = "policy_documents"
    __table_args__ = (
        UniqueConstraint("document_key", name="uq_policy_documents_document_key"),
        # At most one non-retired document per governance-mapped policy kind,
        # since each mapped kind projects to exactly one Institutional
        # Identity pointer field (see ADR-014).
        Index(
            "uq_policy_documents_one_per_mapped_kind",
            "policy_kind",
            unique=True,
            postgresql_where=text(f"is_retired = false AND {_MAPPED_POLICY_KINDS_SQL}"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    policy_kind: Mapped[PolicyKind] = mapped_column(policy_kind_enum, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_identifier: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default=text("'policy.generic.v1'")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_retired: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    draft_authority: Mapped[DraftAuthority] = mapped_column(
        draft_authority_enum, nullable=False, server_default=text("'FOUNDER_ONLY'")
    )
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
            "document_id", "version_number", name="uq_policy_versions_document_number"
        ),
        Index(
            "uq_policy_versions_one_active_per_document",
            "document_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_policy_versions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_documents.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[VersionLifecycleStatus] = mapped_column(
        version_lifecycle_status_enum,
        nullable=False,
        server_default=text("'DRAFT'"),
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policy_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
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
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_stop_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    recovery_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    last_history_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("operating_mode_history.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    active_policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_versions.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OperatingModeHistory(Base):
    """Append-only operating-mode transition evidence."""

    __tablename__ = "operating_mode_history"
    __table_args__ = (Index("ix_operating_mode_history_changed_at", "changed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_mode: Mapped[OperatingMode | None] = mapped_column(operating_mode_enum, nullable=True)
    to_mode: Mapped[OperatingMode] = mapped_column(operating_mode_enum, nullable=False)
    previous_state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    new_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_versions.id", ondelete="SET NULL"), nullable=True
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prerequisite_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class OperatingModeIdempotency(Base):
    """Durable idempotency records for operating-mode mutations."""

    __tablename__ = "operating_mode_idempotency"
    __table_args__ = (
        UniqueConstraint("idempotency_key_hash", name="uq_operating_mode_idempotency_key"),
        Index("ix_operating_mode_idempotency_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    history_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("operating_mode_history.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'committed'")
    )
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


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
        Index("ix_incidents_correlation_key", "correlation_key"),
        Index(
            "ix_incidents_open_correlation",
            "correlation_key",
            unique=True,
            postgresql_where=text("status::text IN ('open', 'investigating', 'mitigated')"),
        ),
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
    source_service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_services.id", ondelete="SET NULL"),
        nullable=True,
    )
    correlation_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    opened_by_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
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


class RegisteredService(Base):
    __tablename__ = "registered_services"
    __table_args__ = (
        UniqueConstraint("service_key", name="uq_registered_services_service_key"),
        CheckConstraint(
            "heartbeat_interval_seconds > 0",
            name="ck_registered_services_interval_positive",
        ),
        CheckConstraint(
            "heartbeat_timeout_seconds > heartbeat_interval_seconds",
            name="ck_registered_services_timeout_gt_interval",
        ),
        CheckConstraint(
            "expected_instance_count >= 0",
            name="ck_registered_services_expected_instances_nonneg",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    service_kind: Mapped[ServiceKind] = mapped_column(service_kind_enum, nullable=False)
    criticality: Mapped[ServiceCriticality] = mapped_column(
        service_criticality_enum, nullable=False
    )
    heartbeat_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    heartbeat_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_instance_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WorkerIdentity(Base):
    __tablename__ = "worker_identities"
    __table_args__ = (
        UniqueConstraint("worker_key", name="uq_worker_identities_worker_key"),
        Index("ix_worker_identities_service_id", "service_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_key: Mapped[str] = mapped_column(String(64), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_services.id", ondelete="RESTRICT"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WorkerInstance(Base):
    __tablename__ = "worker_instances"
    __table_args__ = (
        UniqueConstraint(
            "worker_identity_id",
            "instance_key",
            name="uq_worker_instances_identity_instance",
        ),
        Index("ix_worker_instances_last_seen_at", "last_seen_at"),
        Index("ix_worker_instances_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("worker_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    instance_key: Mapped[str] = mapped_column(String(128), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[WorkerInstanceStatus] = mapped_column(
        worker_instance_status_enum, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class HealthHeartbeat(Base):
    __tablename__ = "health_heartbeats"
    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "sequence_number",
            name="uq_health_heartbeats_service_sequence",
        ),
        Index("ix_health_heartbeats_service_received", "service_id", "received_at"),
        Index("ix_health_heartbeats_observed_at", "observed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_services.id", ondelete="RESTRICT"),
        nullable=False,
    )
    worker_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("worker_instances.id", ondelete="SET NULL"),
        nullable=True,
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[HealthStatus] = mapped_column(health_status_enum, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class HealthHeartbeatIdempotency(Base):
    __tablename__ = "health_heartbeat_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "idempotency_key_hash",
            name="uq_health_heartbeat_idempotency_service_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_services.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    heartbeat_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("health_heartbeats.id", ondelete="SET NULL"),
        nullable=True,
    )
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ServiceHealthProjection(Base):
    __tablename__ = "service_health_projections"
    __table_args__ = (
        CheckConstraint(
            "consecutive_failures >= 0",
            name="ck_service_health_projections_failures_nonneg",
        ),
    )

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_services.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[HealthStatus] = mapped_column(health_status_enum, nullable=False)
    last_heartbeat_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("health_heartbeats.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_sequence_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    evaluation_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InstitutionalHealthState(Base):
    __tablename__ = "institutional_health_state"
    __table_args__ = (
        CheckConstraint(
            "singleton_key = 'current'",
            name="ck_institutional_health_state_singleton",
        ),
    )

    singleton_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[HealthStatus] = mapped_column(health_status_enum, nullable=False)
    evaluation_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class HealthSupervisorLease(Base):
    __tablename__ = "health_supervisor_leases"
    __table_args__ = (
        CheckConstraint(
            "singleton_key = 'current'",
            name="ck_health_supervisor_leases_singleton",
        ),
    )

    singleton_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    holder_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("worker_instances.id", ondelete="SET NULL"),
        nullable=True,
    )
    lease_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_cycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_cycle_result: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class IncidentLifecycleEvent(Base):
    __tablename__ = "incident_lifecycle_events"
    __table_args__ = (
        Index("ix_incident_lifecycle_events_incident_occurred", "incident_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[IncidentLifecycleEventType] = mapped_column(
        incident_lifecycle_event_type_enum, nullable=False
    )
    from_status: Mapped[IncidentStatus | None] = mapped_column(incident_status_enum, nullable=True)
    to_status: Mapped[IncidentStatus | None] = mapped_column(incident_status_enum, nullable=True)
    from_severity: Mapped[IncidentSeverity | None] = mapped_column(
        incident_severity_enum, nullable=True
    )
    to_severity: Mapped[IncidentSeverity | None] = mapped_column(
        incident_severity_enum, nullable=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    opened_by_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProtectiveActionRecommendation(Base):
    __tablename__ = "protective_action_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key_hash",
            name="uq_protective_action_recommendations_idempotency",
        ),
        Index("ix_protective_action_recommendations_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action_type: Mapped[ProtectiveActionType] = mapped_column(
        protective_action_type_enum, nullable=False
    )
    status: Mapped[ProtectiveActionStatus] = mapped_column(
        protective_action_status_enum, nullable=False
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_services.id", ondelete="SET NULL"),
        nullable=True,
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    "AuthSession",
    "LoginAttempt",
    "AuditEvent",
    "ConfigurationDocument",
    "ConfigurationVersion",
    "PolicyDocument",
    "PolicyVersion",
    "FeatureRegistryEntry",
    "DepartmentCapability",
    "SystemState",
    "OperatingModeHistory",
    "OperatingModeIdempotency",
    "ServiceHealthEvent",
    "Incident",
    "RegisteredService",
    "WorkerIdentity",
    "WorkerInstance",
    "HealthHeartbeat",
    "HealthHeartbeatIdempotency",
    "ServiceHealthProjection",
    "InstitutionalHealthState",
    "HealthSupervisorLease",
    "IncidentLifecycleEvent",
    "ProtectiveActionRecommendation",
    "InstitutionalRole",
    "OperatingMode",
    "FeatureStatus",
    "FeatureActivationState",
    "PolicyKind",
    "VersionLifecycleStatus",
    "DraftAuthority",
    "HealthStatus",
    "IncidentSeverity",
    "IncidentStatus",
    "ServiceKind",
    "ServiceCriticality",
    "WorkerInstanceStatus",
    "ProtectiveActionType",
    "ProtectiveActionStatus",
    "IncidentLifecycleEventType",
    "MarketProvider",
    "MarketProviderHealth",
    "MarketInstrument",
    "MarketOhlcvBar",
    "MarketObservation",
    "MarketNewsItem",
    "MarketEconomicEvent",
    "MarketResearchItem",
    "MarketIngestionRun",
    "MarketQualityFinding",
    "MarketIngestionIdempotency",
    "MarketProviderKind",
    "ProviderHealthStatus",
    "ObservationChannel",
    "IngestionRunStatus",
    "QualityFindingKind",
]


# Phase 10 market intelligence models (re-exported for Alembic metadata)
from app.models.market_intelligence import (  # noqa: E402
    IngestionRunStatus,
    MarketEconomicEvent,
    MarketIngestionIdempotency,
    MarketIngestionRun,
    MarketInstrument,
    MarketNewsItem,
    MarketObservation,
    MarketOhlcvBar,
    MarketProvider,
    MarketProviderHealth,
    MarketProviderKind,
    MarketQualityFinding,
    MarketResearchItem,
    ObservationChannel,
    ProviderHealthStatus,
    QualityFindingKind,
)
