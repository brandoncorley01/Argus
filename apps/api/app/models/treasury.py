"""Phase 14 Treasury and Executive Analytics domain models.

Every row in this module represents SIMULATED / INTERNAL-PAPER capital only.
No table stores real money, and no code path in the accompanying service
layer can move real capital:

- ``treasury_accounts.is_simulated`` is database-constrained to ``true``.
- ``external_transfer_instructions.status`` is database-constrained to
  ``draft`` / ``proposed`` / ``cancelled`` only — there is no ``executed``
  or ``completed`` status anywhere in this schema. Execution is not merely
  permission-gated; it is structurally absent (see ADR-030).
- Attribution/KPI/report rows always carry an explicit
  ``environment_class`` (or equivalent) label so paper and live results can
  never be silently combined or mistaken for one another.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class TreasuryAccountClassification(enum.StrEnum):
    SIMULATED = "simulated"
    AVAILABLE = "available"
    ALLOCATED = "allocated"
    RESERVED = "reserved"
    DEPLOYED = "deployed"
    RESTRICTED = "restricted"
    UNSETTLED = "unsettled"
    EXTERNALLY_HELD = "externally_held"


class TreasuryAccountStatus(enum.StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class CapitalAllocationTargetType(enum.StrEnum):
    STRATEGY = "strategy"
    PORTFOLIO = "portfolio"
    PROVIDER = "provider"


class CapitalAllocationStatus(enum.StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    RELEASED = "released"


class CapitalReservationStatus(enum.StrEnum):
    ACTIVE = "active"
    RELEASED = "released"


class ExternalTransferDirection(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class ExternalTransferStatus(enum.StrEnum):
    """Deliberately has no ``executed``/``completed`` member.

    See ADR-030 and ``app.services.treasury_service`` — the model layer
    enumerates only draft/proposed/cancelled. Execution is not a reachable
    state, not merely a blocked transition.
    """

    DRAFT = "draft"
    PROPOSED = "proposed"
    CANCELLED = "cancelled"


class AttributionScope(enum.StrEnum):
    STRATEGY = "strategy"
    PORTFOLIO = "portfolio"
    INSTRUMENT = "instrument"
    PROVIDER = "provider"
    FEE = "fee"
    SLIPPAGE = "slippage"


class EnvironmentClass(enum.StrEnum):
    """Execution/financial environment label. Never combine across labels."""

    PAPER = "paper"
    SANDBOX = "sandbox"
    TESTNET = "testnet"
    LIVE = "live"
    SIMULATED = "simulated"


class InstitutionalReportType(enum.StrEnum):
    DAILY_BRIEF = "daily_brief"
    WEEKLY_EXECUTIVE = "weekly_executive"
    MONTHLY_PERFORMANCE = "monthly_performance"
    QUARTERLY_REVIEW = "quarterly_review"


class ForecastScenarioType(enum.StrEnum):
    CASH_FLOW = "cash_flow"
    CAPITAL_REQUIREMENT = "capital_requirement"
    DRAWDOWN = "drawdown"
    PROVIDER_OUTAGE = "provider_outage"
    STRATEGY_SUSPENSION = "strategy_suspension"


_ACCOUNT_CLASSIFICATIONS_SQL = (
    "classification IN ('simulated','available','allocated','reserved',"
    "'deployed','restricted','unsettled','externally_held')"
)
_TRANSFER_STATUSES_SQL = "status IN ('draft','proposed','cancelled')"


class TreasuryAccount(Base):
    """A simulated/paper institutional capital account.

    ``is_simulated`` is constrained ``true`` at the database level — this
    phase never creates or permits a real-capital account row.
    """

    __tablename__ = "treasury_accounts"
    __table_args__ = (
        UniqueConstraint("name", name="uq_treasury_accounts_name"),
        CheckConstraint(_ACCOUNT_CLASSIFICATIONS_SQL, name="ck_treasury_accounts_classification"),
        CheckConstraint("is_simulated = true", name="ck_treasury_accounts_simulated_only"),
        Index("ix_treasury_accounts_classification", "classification"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'USD'"))
    classification: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'simulated'")
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), nullable=False, server_default=text("0")
    )
    is_simulated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'active'")
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CapitalPool(Base):
    __tablename__ = "capital_pools"
    __table_args__ = (
        UniqueConstraint("account_id", "name", name="uq_capital_pools_account_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("treasury_accounts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    pool_type: Mapped[str] = mapped_column(String(64), nullable=False)
    balance: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CapitalAllocation(Base):
    __tablename__ = "capital_allocations"
    __table_args__ = (
        Index("ix_capital_allocations_pool_status", "pool_id", "status"),
        Index("ix_capital_allocations_target", "target_type", "target_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    pool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capital_pools.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'requested'")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    released_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CapitalReservation(Base):
    __tablename__ = "capital_reservations"
    __table_args__ = (Index("ix_capital_reservations_allocation", "allocation_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    allocation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capital_allocations.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'active'")
    )
    reserved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    released_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TreasuryLedgerEntry(Base):
    """Append-only internal ledger. Never represents an external transfer."""

    __tablename__ = "treasury_ledger_entries"
    __table_args__ = (Index("ix_treasury_ledger_entries_account", "account_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("treasury_accounts.id", ondelete="CASCADE"), nullable=False
    )
    pool_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capital_pools.id", ondelete="SET NULL"), nullable=True
    )
    allocation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capital_allocations.id", ondelete="SET NULL"), nullable=True
    )
    entry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExternalTransferInstruction(Base):
    """Draft/proposed/cancelled ONLY — execution is not a reachable state.

    This table records the *intent* to move capital externally so the
    analysis -> recommendation -> approval -> reservation -> internal ledger
    -> external transfer instruction boundary is auditable end-to-end, while
    guaranteeing (by omission, not merely by permission check) that no row
    can ever represent a completed external transfer. See ADR-030.
    """

    __tablename__ = "external_transfer_instructions"
    __table_args__ = (
        CheckConstraint(_TRANSFER_STATUSES_SQL, name="ck_external_transfer_instructions_status"),
        Index("ix_external_transfer_instructions_account", "account_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("treasury_accounts.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'USD'"))
    destination_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'draft'")
    )
    environment_label: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'simulated'")
    )
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    execution_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    proposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PerformanceAttributionSnapshot(Base):
    """Immutable point-in-time attribution evidence, always environment-labeled."""

    __tablename__ = "performance_attribution_snapshots"
    __table_args__ = (
        Index("ix_perf_attribution_scope_as_of", "scope", "as_of"),
        Index("ix_perf_attribution_environment", "environment_class"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    environment_class: Mapped[str] = mapped_column(String(32), nullable=False)
    amounts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    evidence_refs: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExecutiveKpiSnapshot(Base):
    """Evidence-backed KPI point. Never a fabricated or invented figure."""

    __tablename__ = "executive_kpi_snapshots"
    __table_args__ = (Index("ix_executive_kpi_key_as_of", "kpi_key", "as_of"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kpi_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    environment_class: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_refs: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    is_estimated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InstitutionalReport(Base):
    """Versioned, hashed, immutable report content with an environment disclaimer."""

    __tablename__ = "institutional_reports"
    __table_args__ = (
        UniqueConstraint(
            "report_type", "version", name="uq_institutional_reports_type_version"
        ),
        Index("ix_institutional_reports_type_created", "report_type", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_immutable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    environment_disclaimer: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ForecastScenario(Base):
    """Deterministic, input-driven projection. Never a real market prediction."""

    __tablename__ = "forecast_scenarios"
    __table_args__ = (Index("ix_forecast_scenarios_type_as_of", "scenario_type", "as_of"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scenario_type: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    outputs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_deterministic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "TreasuryAccountClassification",
    "TreasuryAccountStatus",
    "CapitalAllocationTargetType",
    "CapitalAllocationStatus",
    "CapitalReservationStatus",
    "ExternalTransferDirection",
    "ExternalTransferStatus",
    "AttributionScope",
    "EnvironmentClass",
    "InstitutionalReportType",
    "ForecastScenarioType",
    "TreasuryAccount",
    "CapitalPool",
    "CapitalAllocation",
    "CapitalReservation",
    "TreasuryLedgerEntry",
    "ExternalTransferInstruction",
    "PerformanceAttributionSnapshot",
    "ExecutiveKpiSnapshot",
    "InstitutionalReport",
    "ForecastScenario",
]
