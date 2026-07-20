"""Pydantic schemas for Strategy Laboratory APIs (Phase 11)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyDocumentCreate(BaseModel):
    strategy_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    description: str | None = None
    tags: list[Any] = Field(default_factory=list)


class StrategyDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_key: str
    name: str
    description: str | None
    owner_user_id: uuid.UUID
    status: str
    tags: list[Any]
    created_at: datetime
    updated_at: datetime


class StrategyVersionCreate(BaseModel):
    version_label: str = Field(min_length=1, max_length=64)
    strategy_class: str = Field(min_length=1, max_length=128)
    parameters: dict[str, Any] = Field(default_factory=dict)
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
    code_ref: str | None = Field(default=None, max_length=256)
    change_summary: str | None = None


class StrategyVersionParametersUpdate(BaseModel):
    parameters: dict[str, Any]


class StrategyVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    version_label: str
    status: str
    strategy_class: str
    parameter_schema: dict[str, Any]
    parameters: dict[str, Any]
    code_ref: str
    content_hash: str
    change_summary: str | None
    is_immutable: bool
    created_by_user_id: uuid.UUID
    created_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    rejected_at: datetime | None
    suspended_at: datetime | None
    retired_at: datetime | None
    rejection_reason: str | None
    suspension_reason: str | None


class ReasonBody(BaseModel):
    reason: str = Field(min_length=1)


class ResearchDatasetCreate(BaseModel):
    dataset_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    provenance: str = Field(min_length=1)
    source_kind: str = Field(min_length=1, max_length=64)
    bars: list[dict[str, Any]] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ResearchDatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_key: str
    name: str
    provenance: str
    source_kind: str
    content_hash: str
    bar_count: int
    metadata_json: dict[str, Any]
    created_at: datetime


class ExecutionAssumptionsBody(BaseModel):
    commission_bps: float = 0.0
    fee_bps: float = 0.0
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    latency_bars: int = 0
    liquidity_fraction: float = 1.0
    allow_partial_fills: bool = True
    max_position_notional: float = 1_000_000.0
    max_capital: float = 100_000.0


class ResearchRunCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    strategy_version_id: uuid.UUID
    dataset_id: uuid.UUID
    execution_assumptions: ExecutionAssumptionsBody = Field(
        default_factory=ExecutionAssumptionsBody
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    random_seed: int = 42
    execute: bool = True


class ResearchRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    strategy_version_id: uuid.UUID
    dataset_id: uuid.UUID
    request_hash: str
    random_seed: int
    execution_assumptions: dict[str, Any]
    parameters: dict[str, Any]
    budget: dict[str, Any]
    cancel_requested: bool
    created_by_user_id: uuid.UUID
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_summary: str | None


class ResearchRunResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    is_immutable: bool
    metrics: dict[str, Any]
    equity_curve: list[Any]
    trades: list[Any]
    diagnostics: dict[str, Any]
    in_sample_metrics: dict[str, Any]
    out_of_sample_metrics: dict[str, Any]
    result_hash: str
    created_at: datetime


class ValidationReportCreate(BaseModel):
    strategy_version_id: uuid.UUID
    title: str = Field(min_length=1, max_length=256)
    verdict: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1)
    run_id: uuid.UUID | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class ValidationReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_version_id: uuid.UUID
    run_id: uuid.UUID | None
    title: str
    verdict: str
    summary: str
    evidence: dict[str, Any]
    created_by_user_id: uuid.UUID
    created_at: datetime


class StrategyComparisonCreate(BaseModel):
    dataset_id: uuid.UUID
    version_ids: list[uuid.UUID] = Field(min_length=2)
    execution_assumptions: ExecutionAssumptionsBody = Field(
        default_factory=ExecutionAssumptionsBody
    )


class StrategyComparisonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    version_ids: list[Any]
    assumptions_hash: str
    results: dict[str, Any]
    created_by_user_id: uuid.UUID
    created_at: datetime
