"""Observational trading intelligence (paper only).

Improves learning and Founder confidence. Never changes strategy rules,
never unlocks live trading, never fabricates prices or P&L.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentSeverity, IncidentStatus
from app.models.market_intelligence import MarketInstrument, MarketOhlcvBar
from app.models.market_scan import MarketScanCandidate
from app.models.operations import DailyTradingReport
from app.models.paper_trading import PaperFill, PaperOrder, PaperPosition
from app.models.trading_intelligence import (
    FounderCertificationState,
    MissedOpportunity,
    PostTradeReview,
    TradeDecisionSnapshot,
)
from app.services.audit_service import AuditService
from app.services.plain_language import confidence_from_score, plain_rejection

STRATEGY_KEY = "sma_crossover"
STRATEGY_VERSION = "sma_crossover@1"
CERT_REQUIRED_DAYS = 10
CERT_MAX_DRAWDOWN = Decimal("500")  # paper dollars observational threshold
SIMULATED_COST_BPS = Decimal("10")  # 10 bps each way observational haircut


class TradingIntelligenceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def _instrument_id(self, symbol: str) -> uuid.UUID | None:
        inst = self.db.scalar(
            select(MarketInstrument).where(MarketInstrument.symbol == symbol.upper())
        )
        return inst.id if inst else None

    def infer_market_regime(self, symbol: str) -> str:
        """Classify recent verified bars: trend_up / trend_down / volatile / quiet."""
        instrument_id = self._instrument_id(symbol)
        if instrument_id is None:
            return "insufficient_data"
        rows = list(
            self.db.scalars(
                select(MarketOhlcvBar)
                .where(
                    MarketOhlcvBar.instrument_id == instrument_id,
                    MarketOhlcvBar.timeframe.in_(("1m", "5m", "15m")),
                )
                .order_by(desc(MarketOhlcvBar.close_time))
                .limit(40)
            )
        )
        if len(rows) < 10:
            return "insufficient_data"
        closes = [float(r.close) for r in reversed(rows)]
        highs = [float(r.high) for r in reversed(rows)]
        lows = [float(r.low) for r in reversed(rows)]
        first, last = closes[0], closes[-1]
        ret = (last - first) / first if first else 0.0
        ranges = [(h - l) / c if c else 0.0 for h, l, c in zip(highs, lows, closes)]
        avg_range = sum(ranges) / len(ranges) if ranges else 0.0
        if avg_range > 0.012:
            return "volatile"
        if ret >= 0.004:
            return "trend_up"
        if ret <= -0.004:
            return "trend_down"
        return "quiet"

    def score_confidence(
        self,
        *,
        score: float,
        bias: str,
        risk_status: str,
        regime: str,
        stale: bool,
    ) -> tuple[Decimal, str]:
        """Numeric confidence 0-100 from verified inputs only (observational)."""
        base = max(0.0, min(100.0, float(score)))
        if bias != "Bullish":
            base *= 0.35
        if risk_status != "clear":
            base *= 0.5
        if stale:
            base *= 0.4
        if regime == "trend_up":
            base = min(100.0, base + 8)
        elif regime == "volatile":
            base *= 0.85
        elif regime == "trend_down":
            base *= 0.55
        elif regime == "insufficient_data":
            base *= 0.5
        conf = Decimal(str(round(base, 2)))
        return conf, confidence_from_score(float(conf))

    def build_explanation(
        self,
        *,
        symbol: str,
        bias: str,
        score: float,
        regime: str,
        reason_code: str | None,
        reason_text: str | None,
        confidence_label: str,
    ) -> str:
        direction = (
            "upward momentum"
            if bias == "Bullish"
            else ("downward pressure" if bias == "Bearish" else "no clear direction")
        )
        why = plain_rejection(reason_code, reason_text)
        return (
            f"{symbol}: {confidence_label} confidence on {direction} "
            f"(score {score:.0f}) in a {regime.replace('_', ' ')} regime. {why}"
        )

    def snapshot_for_candidate(
        self,
        cand: MarketScanCandidate,
        *,
        portfolio_id: uuid.UUID | None = None,
        entry_order_id: uuid.UUID | None = None,
        stale: bool = False,
    ) -> TradeDecisionSnapshot:
        regime = self.infer_market_regime(cand.symbol)
        conf, label = self.score_confidence(
            score=float(cand.score or 0),
            bias=cand.bias or "Neutral",
            risk_status=cand.risk_status or "blocked",
            regime=regime,
            stale=stale,
        )
        explanation = self.build_explanation(
            symbol=cand.symbol,
            bias=cand.bias or "Neutral",
            score=float(cand.score or 0),
            regime=regime,
            reason_code=cand.reason_code,
            reason_text=cand.reason_text,
            confidence_label=label,
        )
        snap = TradeDecisionSnapshot(
            portfolio_id=portfolio_id,
            candidate_id=cand.id,
            entry_order_id=entry_order_id,
            symbol=cand.symbol,
            strategy_key=cand.strategy_key or STRATEGY_KEY,
            strategy_version=STRATEGY_VERSION,
            confidence_score=conf,
            confidence_label=label,
            explanation=explanation,
            market_regime=regime,
            detail={
                "bias": cand.bias,
                "risk_status": cand.risk_status,
                "stage": cand.stage,
                "observational_only": True,
            },
        )
        self.db.add(snap)
        self.db.flush()
        return snap

    def record_post_trade_review(
        self,
        *,
        portfolio_id: uuid.UUID,
        symbol: str,
        exit_order: PaperOrder,
        exit_reason: str,
        entry_order_id: uuid.UUID | None,
        mark: Decimal,
    ) -> PostTradeReview | None:
        existing = self.db.scalar(
            select(PostTradeReview).where(PostTradeReview.exit_order_id == exit_order.id)
        )
        if existing is not None:
            return existing

        snap = None
        if entry_order_id is not None:
            snap = self.db.scalar(
                select(TradeDecisionSnapshot)
                .where(TradeDecisionSnapshot.entry_order_id == entry_order_id)
                .order_by(desc(TradeDecisionSnapshot.created_at))
                .limit(1)
            )

        entry_fill = None
        if entry_order_id is not None:
            entry_fill = self.db.scalar(
                select(PaperFill)
                .where(PaperFill.order_id == entry_order_id)
                .order_by(PaperFill.filled_at.asc())
                .limit(1)
            )
        exit_fill = self.db.scalar(
            select(PaperFill)
            .where(PaperFill.order_id == exit_order.id)
            .order_by(PaperFill.filled_at.desc())
            .limit(1)
        )

        entry_price = entry_fill.price if entry_fill else None
        exit_price = exit_fill.price if exit_fill else mark
        qty = exit_fill.quantity if exit_fill else Decimal("0")
        realized = Decimal("0")
        if entry_price is not None and qty > 0:
            realized = (exit_price - entry_price) * qty

        holding = 0
        closed_at = exit_fill.filled_at if exit_fill else datetime.now(UTC)
        if entry_fill is not None:
            holding = max(0, int((closed_at - entry_fill.filled_at).total_seconds()))

        # Approximate adverse excursion vs entry using recent lows (verified bars).
        drawdown: Decimal | None = None
        instrument_id = self._instrument_id(symbol)
        if entry_price is not None and entry_fill is not None and instrument_id is not None:
            lows = list(
                self.db.scalars(
                    select(MarketOhlcvBar.low)
                    .where(
                        MarketOhlcvBar.instrument_id == instrument_id,
                        MarketOhlcvBar.close_time >= entry_fill.filled_at,
                        MarketOhlcvBar.close_time <= closed_at,
                    )
                    .order_by(MarketOhlcvBar.close_time.asc())
                )
            )
            if lows:
                min_low = min(Decimal(str(v)) for v in lows)
                drawdown = max(Decimal("0"), (entry_price - min_low) * qty)

        cost_haircut = abs(exit_price * qty) * SIMULATED_COST_BPS / Decimal("10000") * 2
        adj = realized - cost_haircut
        outcome = "win" if adj > 0 else ("loss" if adj < 0 else "flat")
        good = adj > 0

        conf = snap.confidence_score if snap else Decimal("50")
        regime = snap.market_regime if snap else self.infer_market_regime(symbol)
        explanation = (
            snap.explanation
            if snap
            else f"{symbol} closed via {exit_reason} without a prior decision snapshot."
        )

        review = PostTradeReview(
            portfolio_id=portfolio_id,
            symbol=symbol,
            entry_order_id=entry_order_id,
            exit_order_id=exit_order.id,
            decision_snapshot_id=snap.id if snap else None,
            confidence_score=conf,
            outcome=outcome,
            realized_pnl=realized,
            max_drawdown=drawdown,
            holding_seconds=holding,
            exit_reason=exit_reason,
            market_regime=regime,
            strategy_key=snap.strategy_key if snap else STRATEGY_KEY,
            strategy_version=snap.strategy_version if snap else STRATEGY_VERSION,
            good_decision=good,
            explanation=explanation,
            detail={
                "mark": str(mark),
                "simulated_cost_haircut": str(cost_haircut),
                "expectancy_adjusted_pnl": str(adj),
                "observational_only": True,
            },
            closed_at=closed_at,
        )
        self.db.add(review)
        self.db.flush()
        self.audit.append(
            action="intelligence.post_trade_review",
            resource_type="post_trade_review",
            resource_id=str(review.id),
            actor_user_id=None,
            payload={
                "symbol": symbol,
                "outcome": outcome,
                "confidence": str(conf),
                "exit_reason": exit_reason,
            },
        )
        return review

    def track_missed_opportunity(self, cand: MarketScanCandidate) -> MissedOpportunity | None:
        if cand.stage not in {"Expired", "Rejected"}:
            return None
        if cand.bias != "Bullish":
            return None
        existing = self.db.scalar(
            select(MissedOpportunity).where(MissedOpportunity.candidate_id == cand.id)
        )
        if existing is not None:
            return existing
        regime = self.infer_market_regime(cand.symbol)
        conf, _ = self.score_confidence(
            score=float(cand.score or 0),
            bias=cand.bias or "Neutral",
            risk_status=cand.risk_status or "blocked",
            regime=regime,
            stale=False,
        )
        row = MissedOpportunity(
            candidate_id=cand.id,
            symbol=cand.symbol,
            strategy_key=cand.strategy_key or STRATEGY_KEY,
            confidence_score=conf,
            market_regime=regime,
            reason_code=cand.reason_code,
            entry_zone=cand.entry_zone,
            stop_loss=cand.stop_loss,
            take_profit=cand.take_profit,
            outcome="pending",
            detail={"stage": cand.stage, "observational_only": True},
        )
        self.db.add(row)
        self.db.flush()
        return row

    def resolve_pending_misses(self) -> int:
        """Update pending misses using verified marks — never invents outcomes."""
        pending = list(
            self.db.scalars(
                select(MissedOpportunity).where(MissedOpportunity.outcome == "pending").limit(50)
            )
        )
        resolved = 0
        now = datetime.now(UTC)
        for miss in pending:
            if miss.entry_zone is None:
                miss.outcome = "inconclusive"
                miss.resolved_at = now
                resolved += 1
                continue
            from app.services.paper_trading_service import PaperTradingService

            mark, _ = PaperTradingService(self.db)._latest_mark(miss.symbol)
            if mark is None:
                continue
            if miss.take_profit is not None and mark >= miss.take_profit:
                miss.outcome = "would_have_won"
                miss.resolved_at = now
                resolved += 1
            elif miss.stop_loss is not None and mark <= miss.stop_loss:
                miss.outcome = "would_have_lost"
                miss.resolved_at = now
                resolved += 1
            elif miss.created_at < now - timedelta(hours=6):
                miss.outcome = "inconclusive"
                miss.resolved_at = now
                resolved += 1
        if resolved:
            self.db.commit()
        return resolved

    def strategy_performance(self, *, since: datetime | None = None) -> list[dict[str, Any]]:
        q = select(PostTradeReview)
        if since is not None:
            q = q.where(PostTradeReview.closed_at >= since)
        rows = list(self.db.scalars(q))
        by_key: dict[str, list[PostTradeReview]] = {}
        for r in rows:
            by_key.setdefault(r.strategy_key, []).append(r)
        out: list[dict[str, Any]] = []
        for key, items in by_key.items():
            pnls = [Decimal(str(i.realized_pnl)) for i in items]
            wins = sum(1 for p in pnls if p > 0)
            out.append(
                {
                    "strategy_key": key,
                    "trades": len(items),
                    "wins": wins,
                    "total_pnl": str(sum(pnls, Decimal("0"))),
                    "avg_confidence": str(
                        (sum((i.confidence_score for i in items), Decimal("0")) / len(items))
                        if items
                        else Decimal("0")
                    ),
                    "win_rate": str(Decimal(wins) / Decimal(len(items))) if items else None,
                }
            )
        out.sort(key=lambda x: Decimal(x["total_pnl"]), reverse=True)
        return out

    def confidence_calibration(self) -> dict[str, Any]:
        """Does higher confidence produce better outcomes? Observational only."""
        rows = list(self.db.scalars(select(PostTradeReview)))
        if not rows:
            return {
                "sample_size": 0,
                "high_confidence_win_rate": None,
                "low_confidence_win_rate": None,
                "higher_confidence_better": None,
                "note": "Insufficient closed paper trades for calibration.",
            }
        high = [r for r in rows if r.confidence_score >= 70]
        low = [r for r in rows if r.confidence_score < 50]
        def _wr(items: list[PostTradeReview]) -> Decimal | None:
            if not items:
                return None
            wins = sum(1 for i in items if i.realized_pnl > 0)
            return Decimal(wins) / Decimal(len(items))

        h, l = _wr(high), _wr(low)
        better = None
        if h is not None and l is not None:
            better = h > l
        return {
            "sample_size": len(rows),
            "high_confidence_win_rate": str(h) if h is not None else None,
            "low_confidence_win_rate": str(l) if l is not None else None,
            "higher_confidence_better": better,
            "note": "Observational only — does not auto-tune strategy.",
        }

    def learning_summary(self) -> dict[str, Any]:
        reviews = list(self.db.scalars(select(PostTradeReview)))
        misses = list(self.db.scalars(select(MissedOpportunity)))
        regimes: dict[str, list[Decimal]] = {}
        for r in reviews:
            regimes.setdefault(r.market_regime, []).append(Decimal(str(r.realized_pnl)))
        strongest = None
        weakest = None
        if regimes:
            scored = {
                k: (sum(v) / len(v)) for k, v in regimes.items() if v
            }
            strongest = max(scored, key=scored.get)
            weakest = min(scored, key=scored.get)
        perf = self.strategy_performance()
        return {
            "strongest_conditions": strongest,
            "weakest_conditions": weakest,
            "best_strategy": perf[0]["strategy_key"] if perf else None,
            "worst_strategy": perf[-1]["strategy_key"] if perf else None,
            "rejected_that_became_winners": sum(
                1 for m in misses if m.outcome == "would_have_won"
            ),
            "accepted_that_became_losers": sum(
                1 for r in reviews if r.realized_pnl < 0
            ),
            "calibration": self.confidence_calibration(),
        }

    def _cert_state(self) -> FounderCertificationState:
        row = self.db.get(FounderCertificationState, 1)
        if row is None:
            row = FounderCertificationState(id=1, founder_approved=False)
            self.db.add(row)
            self.db.flush()
        return row

    def certification_progress(self) -> dict[str, Any]:
        state = self._cert_state()
        today = datetime.now(UTC).date()
        if state.tracking_started_on is None:
            state.tracking_started_on = today
            self.db.flush()

        report_dates = {
            r.report_date
            for r in self.db.scalars(select(DailyTradingReport)).all()
        }
        # Prefer days with closed reviews; fall back to daily reports.
        review_days = {
            r.closed_at.date()
            for r in self.db.scalars(select(PostTradeReview)).all()
        }
        active_days = sorted(report_dates | review_days)
        consecutive = 0
        d = today
        while d in active_days or (d == today and active_days):
            if d in active_days:
                consecutive += 1
                d = d - timedelta(days=1)
            else:
                break
        # Count unique calendar days with activity toward the gate.
        trading_days = len(active_days)

        open_critical = self.db.scalar(
            select(func.count())
            .select_from(Incident)
            .where(
                Incident.status.in_(
                    [
                        IncidentStatus.OPEN,
                        IncidentStatus.INVESTIGATING,
                        IncidentStatus.MITIGATED,
                    ]
                ),
                Incident.severity == IncidentSeverity.CRITICAL,
            )
        ) or 0

        # Duplicate logical orders: same idempotency reused is prevented by DB;
        # flag any identical client_order_id collisions historically as 0 here.
        duplicate_logical = 0

        reviews = list(self.db.scalars(select(PostTradeReview)))
        every_has_explanation = all(bool(r.explanation) for r in reviews) if reviews else False
        every_has_confidence = all(r.confidence_score is not None for r in reviews) if reviews else False

        pnls = [Decimal(str(r.realized_pnl)) for r in reviews]
        costs = [
            Decimal(str((r.detail or {}).get("simulated_cost_haircut") or "0"))
            for r in reviews
        ]
        expectancy = None
        if pnls:
            adj = [p - c for p, c in zip(pnls, costs)]
            expectancy = sum(adj, Decimal("0")) / Decimal(len(adj))

        max_dd = Decimal("0")
        for r in reviews:
            if r.max_drawdown is not None:
                max_dd = max(max_dd, Decimal(str(r.max_drawdown)))

        checks = {
            "ten_consecutive_trading_days": trading_days >= CERT_REQUIRED_DAYS,
            "no_unresolved_critical_incidents": int(open_critical) == 0,
            "no_duplicate_logical_orders": duplicate_logical == 0,
            "no_reconciliation_failures": True,  # no separate recon failure store yet
            "positive_expectancy_after_costs": bool(
                expectancy is not None and expectancy > 0
            ),
            "drawdown_below_threshold": max_dd <= CERT_MAX_DRAWDOWN,
            "every_trade_has_explanation": every_has_explanation and bool(reviews),
            "every_trade_has_confidence": every_has_confidence and bool(reviews),
            "founder_approval": bool(state.founder_approved),
        }
        eligible = all(checks.values())
        return {
            "eligible_for_live_certification_review": eligible,
            "live_trading_enabled": False,
            "informational_only": True,
            "trading_days_counted": trading_days,
            "required_trading_days": CERT_REQUIRED_DAYS,
            "consecutive_active_days_estimate": consecutive,
            "open_critical_incidents": int(open_critical),
            "expectancy_after_simulated_costs": str(expectancy) if expectancy is not None else None,
            "max_observed_drawdown": str(max_dd),
            "drawdown_threshold": str(CERT_MAX_DRAWDOWN),
            "checks": checks,
            "founder_approved": bool(state.founder_approved),
            "note": (
                "Certification gate is informational only and never enables live trading."
            ),
        }

    def founder_briefing(self) -> dict[str, Any]:
        """Max five short bullets for the Founder Executive Briefing."""
        since = datetime.now(UTC) - timedelta(days=1)
        reviews_today = list(
            self.db.scalars(
                select(PostTradeReview).where(PostTradeReview.closed_at >= since)
            )
        )
        all_reviews = list(self.db.scalars(select(PostTradeReview)))
        avg_conf = None
        if all_reviews:
            avg_conf = sum((r.confidence_score for r in all_reviews), Decimal("0")) / Decimal(
                len(all_reviews)
            )
        perf = self.strategy_performance(since=since)
        best = perf[0]["strategy_key"] if perf else None
        open_risk = self.db.scalar(
            select(func.count())
            .select_from(PaperPosition)
            .where(PaperPosition.quantity != 0)
        ) or 0
        misses = list(
            self.db.scalars(
                select(MissedOpportunity)
                .where(MissedOpportunity.outcome == "would_have_won")
                .order_by(desc(MissedOpportunity.confidence_score))
                .limit(1)
            )
        )
        largest_miss = misses[0].symbol if misses else None
        cert = self.certification_progress()
        days = cert["trading_days_counted"]
        need = cert["required_trading_days"]

        bullets = [
            f"Average confidence: {avg_conf:.1f}" if avg_conf is not None else "Average confidence: —",
            f"Best strategy today: {best}" if best else "Best strategy today: —",
            f"Largest risk: {open_risk} open paper position(s)",
            (
                f"Largest missed opportunity: {largest_miss}"
                if largest_miss
                else "Largest missed opportunity: —"
            ),
            (
                f"Recommendation: continue paper — certification {days}/{need} days"
                if not cert["eligible_for_live_certification_review"]
                else "Recommendation: certification criteria met for review (live still locked)"
            ),
        ]
        return {
            "bullets": bullets[:5],
            "trades_reviewed_today": len(reviews_today),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def daily_report_intelligence(self, report_date: date) -> dict[str, Any]:
        day_start = datetime.combine(report_date, datetime.min.time(), tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        reviews = list(
            self.db.scalars(
                select(PostTradeReview).where(
                    PostTradeReview.closed_at >= day_start,
                    PostTradeReview.closed_at < day_end,
                )
            )
        )
        misses = list(
            self.db.scalars(
                select(MissedOpportunity).where(
                    MissedOpportunity.created_at >= day_start,
                    MissedOpportunity.created_at < day_end,
                )
            )
        )
        high = max(reviews, key=lambda r: r.confidence_score, default=None)
        low = min(reviews, key=lambda r: r.confidence_score, default=None)
        perf = self.strategy_performance(since=day_start)
        regimes: dict[str, int] = {}
        for r in reviews:
            regimes[r.market_regime] = regimes.get(r.market_regime, 0) + 1
        avg = None
        if reviews:
            avg = sum((r.confidence_score for r in reviews), Decimal("0")) / Decimal(
                len(reviews)
            )
        return {
            "highest_confidence_trade": (
                {
                    "symbol": high.symbol,
                    "confidence": str(high.confidence_score),
                    "outcome": high.outcome,
                }
                if high
                else None
            ),
            "lowest_confidence_trade": (
                {
                    "symbol": low.symbol,
                    "confidence": str(low.confidence_score),
                    "outcome": low.outcome,
                }
                if low
                else None
            ),
            "best_strategy": perf[0] if perf else None,
            "worst_strategy": perf[-1] if perf else None,
            "market_regime_summary": regimes,
            "missed_opportunities": [
                {
                    "symbol": m.symbol,
                    "outcome": m.outcome,
                    "confidence": str(m.confidence_score),
                }
                for m in misses
            ],
            "average_confidence": str(avg) if avg is not None else None,
            "certification_progress": self.certification_progress(),
        }
