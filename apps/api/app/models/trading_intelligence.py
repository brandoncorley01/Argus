"""Observational trading intelligence — paper only, never unlocks live trading.

Stores confidence, explanations, regime, post-trade reviews, missed
opportunities, and Founder certification progress. Intelligence must not
automatically change strategy behavior.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
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


class TradeDecisionSnapshot(Base):
    """Point-in-time intelligence attached to a paper entry (or candidate)."""

    __tablename__ = "trade_decision_snapshots"
    __table_args__ = (
        Index("ix_trade_decision_symbol_created", "symbol", "created_at"),
        Index("ix_trade_decision_order", "entry_order_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_portfolios.id"), nullable=True
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market_scan_candidates.id"), nullable=True
    )
    entry_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_orders.id"), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'sma_crossover@1'")
    )
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    confidence_label: Mapped[str] = mapped_column(String(16), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    market_regime: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PostTradeReview(Base):
    """Self-evaluation after a completed paper trade."""

    __tablename__ = "post_trade_reviews"
    __table_args__ = (
        UniqueConstraint("exit_order_id", name="uq_post_trade_reviews_exit_order"),
        Index("ix_post_trade_reviews_symbol", "symbol", "closed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_portfolios.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_orders.id"), nullable=True
    )
    exit_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_orders.id"), nullable=False
    )
    decision_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trade_decision_snapshots.id"), nullable=True
    )
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    holding_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    exit_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    market_regime: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    good_decision: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MissedOpportunity(Base):
    """Rejected/expired signal that is tracked for observational learning."""

    __tablename__ = "missed_opportunities"
    __table_args__ = (
        Index("ix_missed_opportunities_symbol", "symbol", "created_at"),
        UniqueConstraint("candidate_id", name="uq_missed_opportunities_candidate"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market_scan_candidates.id"), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    market_regime: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_zone: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    # pending | would_have_won | would_have_lost | inconclusive
    outcome: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'pending'")
    )
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FounderCertificationState(Base):
    """Informational Live Certification gate — never enables live trading."""

    __tablename__ = "founder_certification_state"
    __table_args__ = (UniqueConstraint("id", name="uq_founder_certification_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default=text("1"))
    founder_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    founder_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    founder_approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    tracking_started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
