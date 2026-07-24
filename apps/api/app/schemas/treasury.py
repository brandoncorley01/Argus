"""Schemas for the Treasury and Executive Analytics API (Phase 14).

No schema in this module can represent a completed external transfer —
``ExternalTransferInstructionRead.status`` only ever reflects
``draft`` / ``proposed`` / ``cancelled``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- accounts / pools -----------------------------------------------------


class TreasuryAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    currency: str = Field(default="USD", min_length=1, max_length=8)
    classification: str = Field(default="simulated", min_length=1, max_length=32)
    description: str | None = None


class TreasuryAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    currency: str
    classification: str
    balance: Decimal
    is_simulated: bool
    status: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class TreasuryAccountFundRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    note: str | None = None


class CapitalPoolCreate(BaseModel):
    account_id: uuid.UUID
    name: str = Field(min_length=1, max_length=128)
    pool_type: str = Field(min_length=1, max_length=64)


class CapitalPoolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    pool_type: str
    balance: Decimal
    created_at: datetime
    updated_at: datetime


# --- allocations / reservations --------------------------------------------


class CapitalAllocationRequest(BaseModel):
    pool_id: uuid.UUID
    target_type: str = Field(pattern="^(strategy|portfolio|provider)$")
    target_id: str | None = Field(default=None, max_length=64)
    amount: Decimal = Field(gt=0)
    max_amount: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None


class CapitalAllocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pool_id: uuid.UUID
    target_type: str
    target_id: str | None
    amount: Decimal
    max_amount: Decimal | None
    status: str
    notes: str | None
    requested_at: datetime
    approved_at: datetime | None
    rejected_at: datetime | None
    rejection_reason: str | None
    released_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CapitalAllocationReject(BaseModel):
    reason: str = Field(min_length=1, max_length=1024)


class CapitalReservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    allocation_id: uuid.UUID
    amount: Decimal
    status: str
    reserved_at: datetime
    released_at: datetime | None
    created_at: datetime


# --- ledger -----------------------------------------------------------------


class TreasuryLedgerEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    pool_id: uuid.UUID | None
    allocation_id: uuid.UUID | None
    entry_type: str
    amount: Decimal
    balance_after: Decimal
    reference_type: str | None
    reference_id: str | None
    note: str | None
    created_at: datetime


# --- external transfer instructions (never executed) ------------------------


class ExternalTransferCreate(BaseModel):
    account_id: uuid.UUID
    direction: str = Field(pattern="^(inbound|outbound)$")
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=1, max_length=8)
    destination_reference: str = Field(min_length=1, max_length=256)


class ExternalTransferCancel(BaseModel):
    reason: str | None = None


class ExternalTransferInstructionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    direction: str
    amount: Decimal
    currency: str
    destination_reference: str
    status: str
    environment_label: str
    blocked_reason: str | None
    execution_attempted_at: datetime | None
    execution_attempt_count: int
    proposed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime


# --- attribution --------------------------------------------------------------


class AttributionSnapshotGenerate(BaseModel):
    scope: str = Field(pattern="^(strategy|portfolio|instrument|provider|fee|slippage)$")
    scope_ref: str | None = Field(default=None, max_length=128)
    environment_class: str = Field(pattern="^(paper|sandbox|testnet|live|simulated)$")


class AttributionSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    as_of: datetime
    scope: str
    scope_ref: str | None
    environment_class: str
    amounts: dict[str, Any]
    evidence_refs: list[Any]
    is_available: bool
    unavailable_reason: str | None
    created_at: datetime


# --- KPIs ------------------------------------------------------------------


class ExecutiveKpiSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    as_of: datetime
    kpi_key: str
    value: Decimal | None
    unit: str
    environment_class: str
    evidence_refs: list[Any]
    is_estimated: bool
    detail: dict[str, Any]
    created_at: datetime


# --- forecasts ---------------------------------------------------------------


class ForecastScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scenario_type: str = Field(
        pattern="^(cash_flow|capital_requirement|drawdown|provider_outage|strategy_suspension)$"
    )
    inputs: dict[str, Any]


class ForecastScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    scenario_type: str
    as_of: datetime
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    is_deterministic: bool
    created_at: datetime


# --- reports -----------------------------------------------------------------


class InstitutionalReportGenerate(BaseModel):
    report_type: str = Field(
        pattern="^(daily_brief|weekly_executive|monthly_performance|quarterly_review)$"
    )


class InstitutionalReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_type: str
    version: int
    as_of: datetime
    content: dict[str, Any]
    content_hash: str
    provenance: dict[str, Any]
    is_immutable: bool
    environment_disclaimer: str
    created_at: datetime


# --- summary ------------------------------------------------------------------


class TreasurySummaryRead(BaseModel):
    disclaimer: str
    total_simulated_balance: str
    account_count: int
    allocation_status_counts: dict[str, int]
    external_transfer_status_counts: dict[str, int]
    external_transfer_executed_count: int
    latest_kpis: list[ExecutiveKpiSnapshotRead]
    latest_paper_attribution: list[AttributionSnapshotRead]
    live_available: bool
    live_unavailable_reason: str
    latest_report: InstitutionalReportRead | None
