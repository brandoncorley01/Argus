"""Schemas for the Micro-Live Institution API (Phase 13).

No schema in this module has a field capable of carrying a credential
VALUE. ``CredentialReferenceRead`` intentionally has no ``value`` field.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MicroLiveStatusRead(BaseModel):
    live_capable_architecture: bool
    credentials_configured: bool
    live_execution_active: bool
    paper_provider_default: bool
    activation_state: str
    state_version: int
    global_kill_switch_active: bool
    active_capital_policy_version: int | None
    adapter_count: int
    enabled_adapter_count: int
    disclaimer: str


class ActivationStateRead(BaseModel):
    activation_state: str
    state_version: int
    credentials_configured: bool
    live_execution_active: bool
    live_capable_architecture: bool
    paper_provider_default: bool
    updated_at: datetime
    evidence: dict[str, Any]


class ActivationTransitionRequest(BaseModel):
    target_state: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=1024)
    evidence: dict[str, Any] | None = None


class ActivationTransitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_state: str | None
    to_state: str
    previous_state_version: int
    new_state_version: int
    reason: str | None
    evidence: dict[str, Any]
    changed_at: datetime


class CredentialReferenceCreate(BaseModel):
    provider_key: str = Field(min_length=1, max_length=64)
    ref_name: str = Field(min_length=1, max_length=128)
    purpose: str = Field(min_length=1, max_length=256)


class CredentialReferenceRead(BaseModel):
    """Never includes the secret value — only the reference NAME and presence."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_key: str
    ref_name: str
    purpose: str
    is_present_cached: bool
    last_validated_at: datetime | None
    created_at: datetime


class KillSwitchSet(BaseModel):
    scope_type: str = Field(pattern="^(global|provider|account|portfolio|strategy|instrument)$")
    scope_id: str | None = None
    active: bool
    reason: str | None = None


class KillSwitchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope_type: str
    scope_id: str | None
    active: bool
    reason: str | None
    activated_at: datetime | None
    cleared_at: datetime | None
    created_at: datetime


class MicroCapitalPolicyUpsert(BaseModel):
    max_deployable_capital: Decimal = Field(gt=0)
    max_order_notional: Decimal = Field(gt=0)
    max_daily_loss: Decimal = Field(gt=0)
    max_concurrent_exposure: Decimal = Field(gt=0)
    max_provider_exposure: Decimal = Field(gt=0)
    max_strategy_exposure: Decimal = Field(gt=0)


class MicroCapitalPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    max_deployable_capital: Decimal
    max_order_notional: Decimal
    max_daily_loss: Decimal
    max_concurrent_exposure: Decimal
    max_provider_exposure: Decimal
    max_strategy_exposure: Decimal
    is_active: bool
    created_at: datetime


class ReconciliationRunCreate(BaseModel):
    provider_key: str = Field(min_length=1, max_length=64)
    authoritative_state: dict[str, Any]
    comparison_state: dict[str, Any]


class ReconciliationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_key: str
    status: str
    discrepancies: list[Any]
    started_at: datetime
    completed_at: datetime | None


class ReconciliationDiscrepancyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    kind: str
    detail: dict[str, Any]
    resolved: bool
    created_at: datetime


class AdapterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_key: str
    display_name: str
    provider_kind: str
    environment: str
    is_default: bool
    is_enabled: bool
    verification_status: str
    supports_live: bool
    description: str | None


class DryRunOrderValidate(BaseModel):
    quantity: Decimal = Field(gt=0)
    reference_price: Decimal = Field(gt=0)


class DryRunOrderResult(BaseModel):
    would_be_allowed: bool
    blocking_codes: list[str]
    notional: str
    policy_version: int
    activation_state: str
    note: str
