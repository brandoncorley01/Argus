"""Market scan / opportunity instrumentation for the Founder Command Center.

Observation-only: records scan cycles, candidates, and decision events derived
from persisted market instruments and OHLCV bars. Does not place orders or
bypass risk controls.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarketScanCycle(Base):
    __tablename__ = "market_scan_cycles"
    __table_args__ = (Index("ix_market_scan_cycles_started", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'15m'"))
    strategy_key: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'sma_crossover'")
    )
    symbols_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    symbols_scanned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    candidates_found: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    current_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rejection_counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    pipeline_counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MarketScanCandidate(Base):
    __tablename__ = "market_scan_candidates"
    __table_args__ = (
        Index("ix_market_scan_candidates_cycle", "cycle_id"),
        Index("ix_market_scan_candidates_stage", "stage"),
        Index("ix_market_scan_candidates_score", "score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market_scan_cycles.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    bias: Mapped[str] = mapped_column(String(16), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    risk_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    entry_zone: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    market_data_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class MarketScanEvent(Base):
    __tablename__ = "market_scan_events"
    __table_args__ = (
        Index("ix_market_scan_events_occurred", "occurred_at"),
        Index("ix_market_scan_events_cycle", "cycle_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market_scan_cycles.id"), nullable=True
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market_scan_candidates.id"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    component: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    strategy_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
