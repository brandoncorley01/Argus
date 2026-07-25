"""Schemas for Paper Training Lab (paper only — never unlocks live)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TrainingSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    mode: str
    default_notional: Decimal
    updated_at: datetime


class TrainingSettingsUpdate(BaseModel):
    mode: str = Field(description="automatic | coaching")
    default_notional: Decimal | None = Field(default=None, gt=0)


class CoachingActionRequest(BaseModel):
    candidate_id: uuid.UUID
    note: str | None = Field(default=None, max_length=1000)


class CoachingActionResponse(BaseModel):
    ok: bool
    message: str
    order_id: uuid.UUID | None = None
    decision_id: uuid.UUID | None = None
    symbol: str | None = None


class FeedbackRequest(BaseModel):
    feedback_code: str
    symbol: str = Field(min_length=1, max_length=64)
    fill_id: uuid.UUID | None = None
    candidate_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)
    strategy_key: str | None = Field(default=None, max_length=64)


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    fill_id: uuid.UUID | None
    candidate_id: uuid.UUID | None
    symbol: str
    feedback_code: str
    note: str | None
    strategy_key: str | None
    created_at: datetime


class CandleReadinessRow(BaseModel):
    symbol: str | None
    bar_count: int
    min_required: int
    latest_close_time: datetime | None
    latest_close: Decimal | None
    age_seconds: int | None
    stale: bool
    ready: bool
    next_step: str


class FounderCandidateRead(BaseModel):
    id: uuid.UUID
    symbol: str
    outlook: str
    bias: str
    current_price: Decimal | None
    confidence: str
    score: Decimal
    stage: str
    stage_raw: str
    decision: str
    why: str
    reason_code: str | None
    waiting_for: str
    entry_zone: Decimal | None
    stop_loss: Decimal | None
    take_profit: Decimal | None
    planned_risk_per_unit: Decimal | None
    planned_reward_per_unit: Decimal | None
    timeframe: str
    strategy_key: str
    risk_status: str
    evaluated_at: datetime
    market_data_at: datetime | None
    lesson: dict[str, Any] | None = None


class ScorecardRead(BaseModel):
    paper_trades_completed: int
    win_rate: Decimal | None
    total_paper_pnl: Decimal
    average_win: Decimal | None
    average_loss: Decimal | None
    profit_factor: Decimal | None
    maximum_drawdown: Decimal | None
    trades_with_founder_feedback: int
    live_readiness: str
    live_readiness_detail: str
    disclaimer: str


class PriceRefreshResponse(BaseModel):
    ok: bool
    records_accepted: int
    bars_submitted: int
    symbols_requested: list[str]
    per_symbol_bars: dict[str, int]
    failed: list[dict[str, str]]
    next_step: str
    disclaimer: str
