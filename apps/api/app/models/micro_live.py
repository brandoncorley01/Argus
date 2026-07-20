"""Phase 13 Micro-Live Institution domain models — deny-by-default.

No table in this module stores a credential VALUE. ``credential_references``
stores only a reference (an environment variable name) and a cached boolean
presence flag. No row anywhere in this module may represent an active,
certified live trading capability: ``live_activation_state`` starts and, in
this phase, can only ever return to ``PAPER_ONLY`` for real operation —
``MICRO_LIVE_ACTIVE`` has no reachable code path (see
``app.services.live_activation_service`` and ADR-029).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LiveActivationState(enum.StrEnum):
    """Phase 13's own state machine — independent of the global OperatingMode.

    ``MICRO_LIVE_ACTIVE`` is defined for architectural completeness only.
    ``live_activation_service`` refuses to ever set this state in Phase 13.
    """

    DISABLED = "DISABLED"
    PAPER_ONLY = "PAPER_ONLY"
    ADAPTER_CONFIGURED = "ADAPTER_CONFIGURED"
    CREDENTIAL_REFERENCE_CONFIGURED = "CREDENTIAL_REFERENCE_CONFIGURED"
    CONNECTION_VERIFIED = "CONNECTION_VERIFIED"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    SANDBOX_OR_TESTNET = "SANDBOX_OR_TESTNET"
    SHADOW_MODE = "SHADOW_MODE"
    MICRO_LIVE_ARMED = "MICRO_LIVE_ARMED"
    MICRO_LIVE_ACTIVE = "MICRO_LIVE_ACTIVE"
    SUSPENDED = "SUSPENDED"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    RECOVERY = "RECOVERY"


class KillSwitchScope(enum.StrEnum):
    GLOBAL = "global"
    PROVIDER = "provider"
    ACCOUNT = "account"
    PORTFOLIO = "portfolio"
    STRATEGY = "strategy"
    INSTRUMENT = "instrument"


class ReconciliationRunStatus(enum.StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LiveActivationStateRow(Base):
    """Singleton row — current Phase 13 activation posture."""

    __tablename__ = "live_activation_state"
    __table_args__ = (
        UniqueConstraint("singleton_key", name="uq_live_activation_state_singleton_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    singleton_key: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'current'")
    )
    current_state: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'PAPER_ONLY'")
    )
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class LiveActivationTransition(Base):
    """Append-only history of Phase 13 activation transitions."""

    __tablename__ = "live_activation_transitions"
    __table_args__ = (Index("ix_live_activation_transitions_changed_at", "changed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    from_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_state: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    new_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CredentialReference(Base):
    """A reference (env var name) to a credential — never the value itself."""

    __tablename__ = "credential_references"
    __table_args__ = (
        UniqueConstraint(
            "provider_key", "ref_name", name="uq_credential_references_provider_ref"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ref_name: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(256), nullable=False)
    is_present_cached: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class KillSwitch(Base):
    __tablename__ = "kill_switches"
    __table_args__ = (
        Index("ix_kill_switches_scope", "scope_type", "scope_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    activated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class MicroCapitalPolicy(Base):
    """Versioned capital ceilings for micro-live activation (conservative)."""

    __tablename__ = "micro_capital_policies"
    __table_args__ = (
        Index(
            "uq_micro_capital_policies_one_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    max_deployable_capital: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    max_order_notional: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    max_daily_loss: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    max_concurrent_exposure: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    max_provider_exposure: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    max_strategy_exposure: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (Index("ix_reconciliation_runs_started_at", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'running'")
    )
    discrepancies: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    initiated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReconciliationDiscrepancy(Base):
    __tablename__ = "reconciliation_discrepancies"
    __table_args__ = (Index("ix_reconciliation_discrepancies_run", "run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "LiveActivationState",
    "KillSwitchScope",
    "ReconciliationRunStatus",
    "LiveActivationStateRow",
    "LiveActivationTransition",
    "CredentialReference",
    "KillSwitch",
    "MicroCapitalPolicy",
    "ReconciliationRun",
    "ReconciliationDiscrepancy",
]
