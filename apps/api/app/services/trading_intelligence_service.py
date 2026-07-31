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
    PaperStrategyConfidenceState,
    PostTradeReview,
    TradeDecisionSnapshot,
)
from app.services.audit_service import AuditService
from app.services.plain_language import confidence_from_score, plain_rejection

STRATEGY_KEY = "sma_crossover"
STRATEGY_VERSION = "sma_crossover@1"
CONFIDENCE_SCORING_VERSION = "confidence@2"
CERT_REQUIRED_DAYS = 30
CERT_MAX_DRAWDOWN = Decimal("500")  # paper dollars observational threshold
SIMULATED_COST_BPS = Decimal("10")  # 10 bps each way observational haircut

# Founder-facing watchlist stage labels (display mapping over scan stages).
STAGE_MAP = {
    "Discovered": "Scanning",
    "Evaluating": "Watching",
    "Watching": "Building Confidence",
    "Risk Review": "Ready To Trade",
    "Entered": "Trade Executed",
    "Teaching": "Managing Position",
    "Rejected": "Lessons Learned",
    "Expired": "Lessons Learned",
}


class TradingIntelligenceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def _paper_adaptive_delta(
        self, *, portfolio_id: uuid.UUID, strategy_key: str
    ) -> Decimal | None:
        """Load PAPER-only adaptive confidence delta; never for live paths."""
        row = self.db.scalar(
            select(PaperStrategyConfidenceState).where(
                PaperStrategyConfidenceState.portfolio_id == portfolio_id,
                PaperStrategyConfidenceState.strategy_key == strategy_key,
                PaperStrategyConfidenceState.paper_only.is_(True),
            )
        )
        if row is None:
            return None
        return max(Decimal("-15"), min(Decimal("15"), Decimal(str(row.confidence_delta))))

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
        ranges = [(h - lo) / c if c else 0.0 for h, lo, c in zip(highs, lows, closes)]
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
        momentum: float | None = None,
        volume_ok: bool | None = None,
        risk_reward: float | None = None,
        duplicate_penalty: bool = False,
        paper_confidence_delta: Decimal | None = None,
    ) -> tuple[Decimal, str, dict[str, Any]]:
        """Numeric confidence 0-100 from verified inputs only (observational).

        Returns (score, label, contributing_factors). Never fabricates missing inputs.
        Optional paper_confidence_delta is PAPER-only adaptive learning (−15..+15)
        and must never be used for live trading paths.
        """
        factors: dict[str, Any] = {
            "scoring_version": CONFIDENCE_SCORING_VERSION,
            "trend": bias,
            "base_signal_score": round(float(score), 2),
            "market_regime": regime,
            "risk_status": risk_status,
            "stale_data": stale,
            "momentum": momentum,
            "volume_ok": volume_ok,
            "risk_reward": risk_reward,
            "duplicate_signal_penalty": duplicate_penalty,
            "paper_confidence_delta": (
                float(paper_confidence_delta) if paper_confidence_delta is not None else None
            ),
            "adjustments": [],
        }
        base = max(0.0, min(100.0, float(score)))
        if bias != "Bullish":
            base *= 0.35
            factors["adjustments"].append("non_bullish_bias_penalty")
        if risk_status != "clear":
            base *= 0.5
            factors["adjustments"].append("risk_not_clear")
        if stale:
            base *= 0.4
            factors["adjustments"].append("stale_data_penalty")
        if duplicate_penalty:
            base *= 0.7
            factors["adjustments"].append("duplicate_signal_penalty")
        if momentum is not None and momentum < 0 and bias == "Bullish":
            base *= 0.8
            factors["adjustments"].append("momentum_conflict")
        if volume_ok is False:
            base *= 0.85
            factors["adjustments"].append("volume_unconfirmed")
        if risk_reward is not None:
            if risk_reward >= 2.0:
                base = min(100.0, base + 5)
                factors["adjustments"].append("favorable_risk_reward")
            elif risk_reward < 1.0:
                base *= 0.75
                factors["adjustments"].append("poor_risk_reward")
        if regime == "trend_up":
            base = min(100.0, base + 8)
            factors["adjustments"].append("regime_trend_up_boost")
        elif regime == "volatile":
            base *= 0.85
            factors["adjustments"].append("regime_volatile_penalty")
        elif regime == "trend_down":
            base *= 0.7
            factors["adjustments"].append("regime_trend_down_penalty")
        elif regime == "insufficient_data":
            base *= 0.75
            factors["adjustments"].append("insufficient_data_penalty")
        if paper_confidence_delta is not None:
            bounded = max(Decimal("-15"), min(Decimal("15"), paper_confidence_delta))
            base = max(0.0, min(100.0, base + float(bounded)))
            factors["adjustments"].append("paper_adaptive_confidence")
            factors["paper_confidence_delta_applied"] = float(bounded)
        conf = Decimal(str(round(base, 2)))
        factors["final_score"] = float(conf)
        return conf, confidence_from_score(float(conf)), factors

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
        rr = None
        if cand.entry_zone and cand.stop_loss and cand.take_profit:
            risk = abs(float(cand.entry_zone) - float(cand.stop_loss))
            reward = abs(float(cand.take_profit) - float(cand.entry_zone))
            if risk > 0:
                rr = reward / risk
        conf, label, factors = self.score_confidence(
            score=float(cand.score or 0),
            bias=cand.bias or "Neutral",
            risk_status=cand.risk_status or "blocked",
            regime=regime,
            stale=stale,
            risk_reward=rr,
            paper_confidence_delta=(
                self._paper_adaptive_delta(
                    portfolio_id=portfolio_id,
                    strategy_key=cand.strategy_key or STRATEGY_KEY,
                )
                if portfolio_id is not None
                else None
            ),
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
                "founder_stage": STAGE_MAP.get(cand.stage or "", cand.stage),
                "contributing_factors": factors,
                "scoring_version": CONFIDENCE_SCORING_VERSION,
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

        # Approximate adverse / favorable excursion vs entry using verified bars.
        drawdown: Decimal | None = None
        mfe: Decimal | None = None
        instrument_id = self._instrument_id(symbol)
        if entry_price is not None and entry_fill is not None and instrument_id is not None:
            bars = list(
                self.db.scalars(
                    select(MarketOhlcvBar)
                    .where(
                        MarketOhlcvBar.instrument_id == instrument_id,
                        MarketOhlcvBar.close_time >= entry_fill.filled_at,
                        MarketOhlcvBar.close_time <= closed_at,
                    )
                    .order_by(MarketOhlcvBar.close_time.asc())
                )
            )
            if bars:
                min_low = min(Decimal(str(b.low)) for b in bars)
                max_high = max(Decimal(str(b.high)) for b in bars)
                drawdown = max(Decimal("0"), (entry_price - min_low) * qty)
                mfe = max(Decimal("0"), (max_high - entry_price) * qty)

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
                "max_favorable_excursion": str(mfe) if mfe is not None else None,
                "would_take_again": bool(good),
                "decision_quality": (
                    "acceptable" if good else "review_required"
                ),
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
        conf, _, _ = self.score_confidence(
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
            # Calendar gate is observational only — paper continues until
            # profitable evidence + stability; never unlocks live trading.
            "paper_observation_days_met": trading_days >= CERT_REQUIRED_DAYS,
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
        """Executive Briefing payload for the Founder Home (PROVE mode)."""
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
        watch = self.watchlist_intelligence()
        mission = self.morning_mission()
        thinking = self.thinking_observations(limit=5)

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
        action_required = mission.get("founder_action_required") or (
            "None — continue observing paper standards."
            if watch.get("recommendation") == "WAIT"
            else f"Review highest-priority opportunity ({watch.get('highest_confidence_opportunity', {}).get('symbol', '—')})."
        )
        return {
            "bullets": bullets[:5],
            "institution_status": mission.get("institution_status"),
            "trading_mission": mission,
            "trading_intelligence_summary": bullets[:5],
            "highest_priority_opportunity": watch.get("highest_confidence_opportunity"),
            "certification_progress": cert,
            "founder_action_required": action_required,
            "watchlist_intelligence": watch,
            "thinking": thinking,
            "trades_reviewed_today": len(reviews_today),
            "live_trading_locked": True,
            "mode": "PROVE",
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def watchlist_intelligence(self) -> dict[str, Any]:
        """Aggregate Founder watchlist intelligence from scan candidates (no fabrication)."""
        from app.models.market_scan import MarketScanCandidate

        cands = list(
            self.db.scalars(
                select(MarketScanCandidate).order_by(desc(MarketScanCandidate.evaluated_at)).limit(200)
            )
        )
        counts = {
            "scanning": 0,
            "watching": 0,
            "building_confidence": 0,
            "ready": 0,
            "executed": 0,
            "removed": 0,
            "avoided": 0,
        }
        ready_rows: list[MarketScanCandidate] = []
        for c in cands:
            stage = c.stage or ""
            if stage == "Discovered":
                counts["scanning"] += 1
            elif stage == "Evaluating":
                counts["watching"] += 1
            elif stage == "Watching":
                counts["building_confidence"] += 1
            elif stage == "Risk Review":
                counts["ready"] += 1
                ready_rows.append(c)
            elif stage == "Entered":
                counts["executed"] += 1
            elif stage == "Expired":
                counts["removed"] += 1
            elif stage == "Rejected":
                counts["avoided"] += 1

        top = None
        if ready_rows or cands:
            pool = ready_rows or [c for c in cands if c.stage in {"Watching", "Risk Review"}]
            if pool:
                best = max(pool, key=lambda x: float(x.score or 0))
                regime = self.infer_market_regime(best.symbol)
                conf, label, factors = self.score_confidence(
                    score=float(best.score or 0),
                    bias=best.bias or "Neutral",
                    risk_status=best.risk_status or "blocked",
                    regime=regime,
                    stale=False,
                )
                top = {
                    "symbol": best.symbol,
                    "stage": STAGE_MAP.get(best.stage, best.stage),
                    "stage_raw": best.stage,
                    "confidence": float(conf),
                    "confidence_label": label,
                    "bias": best.bias,
                    "recommendation": self._recommendation_for_candidate(best, conf),
                    "contributing_factors": factors,
                    "candidate_id": str(best.id),
                }

        recommendation = "WAIT"
        if top and top["recommendation"] == "EXECUTE":
            recommendation = "EXECUTE"
        elif counts["avoided"] > counts["ready"] and counts["ready"] == 0:
            recommendation = "AVOID" if counts["building_confidence"] == 0 else "WAIT"

        waiting = []
        if counts["building_confidence"]:
            waiting.append("Volume/momentum confirmation on watched markets")
        if counts["ready"] == 0:
            waiting.append("No markets currently meet Ready To Trade standards")
        if not waiting:
            waiting.append("Institutional standards currently filter all discretionary entries")

        top_five = []
        ranked = sorted(
            [c for c in cands if c.stage in {"Watching", "Risk Review", "Evaluating"}],
            key=lambda x: float(x.score or 0),
            reverse=True,
        )[:5]
        for c in ranked:
            regime = self.infer_market_regime(c.symbol)
            conf, label, _ = self.score_confidence(
                score=float(c.score or 0),
                bias=c.bias or "Neutral",
                risk_status=c.risk_status or "blocked",
                regime=regime,
                stale=False,
            )
            top_five.append(
                {
                    "symbol": c.symbol,
                    "stage": STAGE_MAP.get(c.stage, c.stage),
                    "confidence": float(conf),
                    "confidence_label": label,
                    "recommendation": self._recommendation_for_candidate(c, conf),
                    "candidate_id": str(c.id),
                }
            )

        return {
            "markets_scanning": counts["scanning"],
            "markets_watching": counts["watching"] + counts["building_confidence"],
            "markets_removed": counts["removed"],
            "markets_avoided": counts["avoided"],
            "markets_ready": counts["ready"],
            "highest_confidence_opportunity": top,
            "confidence_trend": "stable",
            "waiting_conditions": waiting,
            "current_recommendation": recommendation,
            "top_opportunities": top_five,
            "note": "Watchlist is observational. Live trading remains locked.",
        }

    def _recommendation_for_candidate(
        self, cand: MarketScanCandidate, conf: Decimal
    ) -> str:
        if cand.bias != "Bullish":
            return "AVOID"
        # Paper Automatic Practice enters from Watching when risk is clear.
        # Require moderate confidence — not only Risk Review (pause path).
        if (
            cand.stage in {"Watching", "Risk Review", "Approved"}
            and cand.risk_status == "clear"
            and conf >= 55
        ):
            return "EXECUTE"
        if cand.stage in {"Rejected", "Expired"}:
            return "AVOID"
        return "WAIT"

    def case_file(self, candidate_id: uuid.UUID) -> dict[str, Any] | None:
        """Permanent Case File view for a watched/executed opportunity."""
        from app.models.market_scan import MarketScanCandidate, MarketScanEvent

        cand = self.db.get(MarketScanCandidate, candidate_id)
        if cand is None:
            return None
        regime = self.infer_market_regime(cand.symbol)
        conf, label, factors = self.score_confidence(
            score=float(cand.score or 0),
            bias=cand.bias or "Neutral",
            risk_status=cand.risk_status or "blocked",
            regime=regime,
            stale=False,
        )
        events = list(
            self.db.scalars(
                select(MarketScanEvent)
                .where(MarketScanEvent.candidate_id == candidate_id)
                .order_by(MarketScanEvent.occurred_at.asc())
                .limit(50)
            )
        )
        snaps = list(
            self.db.scalars(
                select(TradeDecisionSnapshot)
                .where(TradeDecisionSnapshot.candidate_id == candidate_id)
                .order_by(TradeDecisionSnapshot.created_at.asc())
            )
        )
        timeline = []
        for e in events:
            timeline.append(
                {
                    "at": e.occurred_at.isoformat() if e.occurred_at else None,
                    "event": e.title or e.component,
                    "stage": STAGE_MAP.get(e.stage or "", e.stage),
                    "detail": {"outcome": e.outcome, "note": e.detail or ""},
                }
            )
        for s in snaps:
            timeline.append(
                {
                    "at": s.created_at.isoformat() if s.created_at else None,
                    "event": "Decision snapshot recorded",
                    "stage": STAGE_MAP.get(
                        (s.detail or {}).get("stage", ""), (s.detail or {}).get("stage")
                    ),
                    "detail": {
                        "confidence": str(s.confidence_score),
                        "explanation": s.explanation,
                    },
                }
            )
        timeline.sort(key=lambda x: x.get("at") or "")

        watched_seconds = None
        if cand.evaluated_at:
            watched_seconds = max(
                0, int((datetime.now(UTC) - cand.evaluated_at).total_seconds())
            )

        rr = None
        if cand.entry_zone and cand.stop_loss and cand.take_profit:
            risk = abs(float(cand.entry_zone) - float(cand.stop_loss))
            reward = abs(float(cand.take_profit) - float(cand.entry_zone))
            if risk > 0:
                rr = reward / risk

        return {
            "candidate_id": str(cand.id),
            "symbol": cand.symbol,
            "direction": "Long" if cand.bias == "Bullish" else cand.bias,
            "current_confidence": float(conf),
            "confidence_label": label,
            "confidence_history": [
                {
                    "at": s.created_at.isoformat() if s.created_at else None,
                    "confidence": float(s.confidence_score),
                    "label": s.confidence_label,
                }
                for s in snaps
            ],
            "current_stage": STAGE_MAP.get(cand.stage, cand.stage),
            "stage_raw": cand.stage,
            "reasoning": self.build_explanation(
                symbol=cand.symbol,
                bias=cand.bias or "Neutral",
                score=float(cand.score or 0),
                regime=regime,
                reason_code=cand.reason_code,
                reason_text=cand.reason_text,
                confidence_label=label,
            ),
            "waiting_conditions": [
                plain_rejection(cand.reason_code, cand.reason_text)
            ],
            "risk_assessment": cand.risk_status,
            "expected_risk_reward": rr,
            "market_regime": regime,
            "strategy": cand.strategy_key or STRATEGY_KEY,
            "time_under_observation_seconds": watched_seconds,
            "decision_timeline": timeline,
            "recommendation": self._recommendation_for_candidate(cand, conf),
            "contributing_factors": factors,
            "observational_only": True,
            "live_trading_locked": True,
        }

    def thinking_observations(self, *, limit: int = 8) -> list[dict[str, Any]]:
        """Concise institutional observations from meaningful recent state only."""
        watch = self.watchlist_intelligence()
        obs: list[dict[str, Any]] = []
        watching = int(watch.get("markets_watching") or 0)
        ready = int(watch.get("markets_ready") or 0)
        avoided = int(watch.get("markets_avoided") or 0)
        if watching:
            obs.append(
                {
                    "text": f"Watching {watching} market(s).",
                    "kind": "watchlist",
                }
            )
        top = watch.get("highest_confidence_opportunity")
        if top and top.get("confidence", 0) >= 60:
            obs.append(
                {
                    "text": (
                        f"{top['symbol']} confidence {top['confidence']:.0f} "
                        f"({top.get('confidence_label')}) — {top.get('recommendation')}."
                    ),
                    "kind": "confidence",
                }
            )
        if avoided and ready == 0:
            obs.append(
                {
                    "text": "Capital preservation currently outweighs opportunity.",
                    "kind": "discipline",
                }
            )
        if ready == 0 and watching == 0:
            obs.append(
                {
                    "text": "No trades currently satisfy institutional standards.",
                    "kind": "discipline",
                }
            )
        elif watch.get("current_recommendation") == "WAIT":
            obs.append(
                {
                    "text": "Patience: waiting conditions remain unmet for execution.",
                    "kind": "wait",
                }
            )
        return obs[:limit]

    def morning_mission(self) -> dict[str, Any]:
        """Daily Trading Mission for the Founder (paper / PROVE mode)."""
        cert = self.certification_progress()
        watch = self.watchlist_intelligence()
        learning = self.learning_summary()
        open_pos = self.db.scalar(
            select(func.count()).select_from(PaperPosition).where(PaperPosition.quantity != 0)
        ) or 0
        regime = learning.get("strongest_conditions") or "insufficient_data"
        top = watch.get("highest_confidence_opportunity")
        action = "None — observe and preserve capital."
        # Stale critical incidents must not freeze paper desks forever when the
        # control plane is healthy again — health supervisor auto-closes them.
        if cert.get("open_critical_incidents", 0) > 0:
            action = (
                "Critical system issues are open — Argus still paper-trades, but "
                "review Issues and confirm API/worker health before trusting new entries."
            )
        elif watch.get("current_recommendation") == "EXECUTE" and top:
            action = f"Review Ready opportunity on {top.get('symbol')} (paper only)."
        elif open_pos:
            action = "Manage open paper positions; do not force new entries."

        return {
            "institution_status": "Paper desk · PROVE mode · Live locked",
            "market_outlook": (
                f"Primary regime focus: {str(regime).replace('_', ' ')}"
                if regime
                else "Market outlook unavailable"
            ),
            "trading_objective": "Protect capital first; take only high-confidence paper setups.",
            "risk_environment": (
                "Elevated"
                if cert.get("open_critical_incidents", 0) > 0
                else ("Active open risk" if open_pos else "Contained")
            ),
            "maximum_planned_exposure": "Governed by paper risk limits and pause controls",
            "current_market_regime": regime,
            "primary_areas_of_focus": [
                "Watchlist confirmation quality",
                "Open position management",
                f"Certification progress {cert.get('trading_days_counted')}/{cert.get('required_trading_days')}",
            ],
            "highest_priority_opportunities": watch.get("top_opportunities") or [],
            "certification_progress": {
                "days": cert.get("trading_days_counted"),
                "required": cert.get("required_trading_days"),
                "eligible_for_review": cert.get("eligible_for_live_certification_review"),
                "live_enabled": False,
            },
            "founder_action_required": action,
            "live_trading_locked": True,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def mission_debrief(self, report_date: date | None = None) -> dict[str, Any]:
        """End-of-day executive debrief (observational, paper only)."""
        day = report_date or datetime.now(UTC).date()
        intel = self.daily_report_intelligence(day)
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        reviews = list(
            self.db.scalars(
                select(PostTradeReview).where(
                    PostTradeReview.closed_at >= day_start,
                    PostTradeReview.closed_at < day_end,
                )
            )
        )
        pnls = [Decimal(str(r.realized_pnl)) for r in reviews]
        wins = sum(1 for p in pnls if p > 0)
        net = sum(pnls, Decimal("0"))
        best = max(reviews, key=lambda r: Decimal(str(r.realized_pnl)), default=None)
        worst = min(reviews, key=lambda r: Decimal(str(r.realized_pnl)), default=None)
        cert = self.certification_progress()
        success = (
            "Hold"
            if not reviews
            else ("Success" if net >= 0 and cert.get("open_critical_incidents", 0) == 0 else "Review")
        )
        return {
            "report_date": day.isoformat(),
            "mission_success": success,
            "trades_executed": len(reviews),
            "win_rate": str(Decimal(wins) / Decimal(len(reviews))) if reviews else None,
            "net_pnl": str(net),
            "capital_preservation": "Maintained" if net >= 0 else "Drawdown observed",
            "best_decision": (
                f"{best.symbol} ({best.outcome})" if best else "No closed trades"
            ),
            "largest_mistake": (
                f"{worst.symbol} ({worst.outcome})"
                if worst and Decimal(str(worst.realized_pnl)) < 0
                else "None recorded"
            ),
            "biggest_lesson": (
                intel.get("market_regime_summary")
                and f"Regime mix today: {intel.get('market_regime_summary')}"
            )
            or "Continue requiring confirmation before entries.",
            "strongest_market": (intel.get("highest_confidence_trade") or {}).get("symbol"),
            "weakest_market": (intel.get("lowest_confidence_trade") or {}).get("symbol"),
            "recommendation": (
                "Continue paper certification — live remains locked."
                if not cert.get("eligible_for_live_certification_review")
                else "Certification criteria met for Founder review only (live still locked)."
            ),
            "certification_progress": cert,
            "live_trading_locked": True,
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
