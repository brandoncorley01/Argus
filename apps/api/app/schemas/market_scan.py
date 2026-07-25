"""Schemas for market scan Command Center APIs (observation only)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScanCycleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    timeframe: str
    strategy_key: str
    symbols_total: int
    symbols_scanned: int
    candidates_found: int
    current_symbol: str | None
    started_at: datetime
    completed_at: datetime | None
    next_scheduled_at: datetime | None
    correlation_id: str
    rejection_counts: dict[str, Any] = Field(default_factory=dict)
    pipeline_counts: dict[str, Any] = Field(default_factory=dict)


class ScanCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cycle_id: uuid.UUID
    symbol: str
    timeframe: str
    strategy_key: str
    bias: str
    stage: str
    score: Decimal
    risk_status: str
    reason_code: str | None
    reason_text: str | None
    current_price: Decimal | None
    entry_zone: Decimal | None
    stop_loss: Decimal | None
    take_profit: Decimal | None
    market_data_at: datetime | None
    evaluated_at: datetime


class ScanEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cycle_id: uuid.UUID | None
    candidate_id: uuid.UUID | None
    occurred_at: datetime
    component: str
    symbol: str | None
    stage: str | None
    outcome: str
    reason_code: str | None
    title: str
    detail: str
    strategy_key: str | None
    correlation_id: str


class ScanStatusRead(BaseModel):
    scanner_state: str
    cycle: ScanCycleRead | None
    symbols_monitored: int
    market_data_at: datetime | None
    market_data_age_seconds: int | None
    market_data_stale: bool
    pause_new_entries_active: bool
    kill_switch_active: bool
    trading_allowed: bool
    last_decision: ScanEventRead | None
    pipeline_counts: dict[str, Any]
    rejection_counts: dict[str, Any]
    next_scheduled_at: datetime | None
    worker_note: str


class ScanBarRead(BaseModel):
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None


class ScanBarsResponse(BaseModel):
    symbol: str
    timeframe: str | None
    available: bool
    bars: list[ScanBarRead]


class TeachSignalRequest(BaseModel):
    """Founder teaching signal for paper — does not place orders."""

    signal: str = Field(
        description="interested | not_interested | needs_more_data | looks_wrong"
    )
    symbol: str = Field(min_length=1, max_length=64)
    candidate_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class TeachSignalResponse(BaseModel):
    ok: bool
    message: str
    event_id: uuid.UUID | None = None


class ScanRunResponse(BaseModel):
    cycle: ScanCycleRead
