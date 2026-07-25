"""Schemas for paper trading / execution gateway APIs."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_key: str
    display_name: str
    provider_kind: str
    environment: str
    is_default: bool
    is_enabled: bool
    capabilities: list[Any]
    description: str | None


class ProviderHealthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider_id: uuid.UUID
    status: str
    last_success_at: datetime | None
    last_error: str | None
    detail: dict[str, Any]


class ProviderWithHealth(BaseModel):
    provider: ProviderRead
    health: ProviderHealthRead | None


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    initial_cash: Decimal = Field(gt=0)
    currency: str = Field(default="USD", max_length=8)


class PortfolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    currency: str
    cash_balance: Decimal
    reserved_cash: Decimal
    status: str
    kill_switch_active: bool
    pause_new_entries_active: bool = False
    default_provider_id: uuid.UUID
    owner_user_id: uuid.UUID
    created_at: datetime


class KillSwitchRequest(BaseModel):
    active: bool


class PauseNewEntriesRequest(BaseModel):
    active: bool


class PortfolioSummaryRead(BaseModel):
    """Computed Founder-facing paper account snapshot. No fabricated marks."""

    portfolio_id: uuid.UUID
    currency: str
    cash_balance: Decimal
    reserved_cash: Decimal
    buying_power: Decimal
    committed_capital: Decimal
    total_account_value: Decimal
    total_account_value_basis: str = "cost"
    marks_complete: bool = False
    open_position_count: int
    kill_switch_active: bool
    pause_new_entries_active: bool
    status: str


class PositionSummaryRead(BaseModel):
    """Position row for Command Center. Unavailable marks stay null."""

    id: uuid.UUID
    symbol: str
    quantity: Decimal
    side: str
    average_cost: Decimal
    committed_capital: Decimal
    market_value: Decimal | None = None
    realized_pnl: Decimal
    unrealized_pnl: Decimal | None = None
    mark_price: Decimal | None = None
    pnl_percent: Decimal | None = None
    price_status: str = "unavailable"
    opened_at: datetime | None = None
    strategy_version_id: uuid.UUID | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    state: str


class ClosedTradeRead(BaseModel):
    """Sell fill with realized P&L from chronological fill replay."""

    fill_id: uuid.UUID
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    realized_pnl: Decimal
    filled_at: datetime
    holding_seconds: int | None = None
    exit_reason: str | None = None


class SessionCreate(BaseModel):
    strategy_version_id: uuid.UUID | None = None
    seed: int = 42
    assumptions: dict[str, Any] | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    strategy_version_id: uuid.UUID | None
    provider_id: uuid.UUID
    status: str
    seed: int
    assumptions: dict[str, Any]
    started_at: datetime
    ended_at: datetime | None


class OrderSubmit(BaseModel):
    symbol: str = Field(min_length=1, max_length=64)
    side: str = Field(pattern="^(buy|sell)$")
    order_type: str = Field(default="market", pattern="^(market|limit)$")
    quantity: Decimal = Field(gt=0)
    limit_price: Decimal | None = None
    session_id: uuid.UUID | None = None
    strategy_version_id: uuid.UUID | None = None
    client_order_id: str | None = None


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    provider_id: uuid.UUID
    session_id: uuid.UUID | None
    strategy_version_id: uuid.UUID | None
    client_order_id: str
    provider_order_id: str | None
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    filled_quantity: Decimal
    limit_price: Decimal | None
    average_fill_price: Decimal | None
    status: str
    environment: str
    reject_reason: str | None
    created_at: datetime


class FillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    filled_at: datetime


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal


class RiskLimitCreate(BaseModel):
    name: str
    limit_type: str
    threshold: Decimal = Field(gt=0)
    symbol: str | None = None


class RiskLimitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    limit_type: str
    threshold: Decimal
    symbol: str | None
    is_enabled: bool


class RiskBreachRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    limit_type: str
    message: str
    detail: dict[str, Any]
    detected_at: datetime


class ReportCreate(BaseModel):
    report_type: str = Field(default="account_statement")


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_type: str
    content: dict[str, Any]
    content_hash: str
    is_immutable: bool
    created_at: datetime


class CheckpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    sequence_number: int
    state_blob: dict[str, Any]
    created_at: datetime
