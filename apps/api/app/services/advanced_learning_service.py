"""Advanced paper learning engine — extends trading intelligence (PAPER only).

Evaluates 20-day paper-learning progress from verified fills/reviews/radar
inputs. Adaptive strategy confidence is bounded, auditable, reversible, and
never applied to live trading. High volume raises analysis priority only —
volume alone never triggers a trade. Day-20 readiness reports never enable live.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.market_intelligence import MarketInstrument, MarketOhlcvBar
from app.models.market_scan import MarketScanCandidate
from app.models.trading_intelligence import (
    PaperLearningDaySnapshot,
    PaperLearningMilestone,
    PaperLearningProgram,
    PaperLearningReadinessReport,
    PaperStrategyConfidenceState,
    PostTradeReview,
    TradeDecisionSnapshot,
)
from app.services.audit_service import AuditService
from app.services.trading_intelligence_service import (
    SIMULATED_COST_BPS,
    TradingIntelligenceService,
)

LEARNING_REQUIRED_DAYS = 20
ADAPTIVE_DELTA_MIN = Decimal("-15")
ADAPTIVE_DELTA_MAX = Decimal("15")
ADAPTIVE_MIN_TRADES = 5
VOLUME_RELATIVE_HIGH = Decimal("1.5")  # vs 20-bar average
VOLUME_NEVER_TRIGGERS_TRADE = True

MILESTONE_DEFS: list[tuple[str, str]] = [
    ("first_profitable_trade", "First profitable trade"),
    ("first_profitable_day", "First profitable day"),
    ("first_validated_strategy", "First validated strategy"),
    ("first_successful_dip_reversal", "First successful dip reversal"),
    ("first_successful_high_volume_breakout", "First successful high-volume breakout"),
    ("positive_expectancy_after_fees", "Positive expectancy after fees"),
    ("risk_discipline", "Risk-discipline milestone"),
    ("day_20_completion", "Day-20 completion"),
]


def _dec(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _as_str(value: Decimal | float | int | None, places: int = 4) -> str | None:
    if value is None:
        return None
    q = Decimal("1").scaleb(-places)
    return str(_dec(value).quantize(q))


def _content_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def classify_trade_pattern(review: PostTradeReview, snapshot: TradeDecisionSnapshot | None) -> str:
    """Best-effort pattern label from stored evidence only (no look-ahead)."""
    detail = dict(review.detail or {})
    snap_detail = dict(snapshot.detail) if snapshot and snapshot.detail else {}
    reason = str(
        detail.get("exit_reason")
        or detail.get("pattern")
        or review.exit_reason
        or ""
    ).lower()
    strategy = str(getattr(review, "strategy_key", "") or "").lower()
    regime = (review.market_regime or "").lower()
    text_blob = f"{reason} {strategy}"
    adjustments = snap_detail.get("contributing_factors", {}).get("adjustments") or []
    if not isinstance(adjustments, list):
        adjustments = []
    adj_text = " ".join(str(a) for a in adjustments).lower()
    volume_ok = snap_detail.get("contributing_factors", {}).get("volume_ok")
    won = review.outcome == "win" and review.realized_pnl > 0
    lost = review.realized_pnl < 0

    if "dip" in text_blob or "reversal" in text_blob or (
        regime == "trend_down" and ("bounce" in text_blob or "mean" in text_blob)
    ):
        return "dip_reversal" if won else "dip_reversal_attempt"
    if "range" in text_blob or regime == "quiet":
        return "range"
    if volume_ok is True or "volume" in adj_text or "breakout" in text_blob:
        if regime in {"trend_up", "volatile"} or "breakout" in text_blob:
            if won and (volume_ok is True or "volume" in adj_text):
                return "high_volume_breakout"
            return "breakout"
    if (
        "exhaust" in text_blob
        or "peak" in text_blob
        or "peak_fade" in text_blob
        or "fade_top" in text_blob
    ):
        return "peak_exhaustion"
    if "momentum" in text_blob or regime == "trend_up":
        return "momentum"
    if regime == "volatile":
        return "peak_exhaustion" if lost else "breakout"
    return "unclassified"


class AdvancedLearningService:
    """PAPER-only advanced learning cycle over existing intelligence evidence."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.intelligence = TradingIntelligenceService(db)
        self.audit = AuditService(db)

    # --- program lifecycle -------------------------------------------------

    def get_or_create_program(self, portfolio_id: uuid.UUID) -> PaperLearningProgram:
        row = self.db.scalar(
            select(PaperLearningProgram)
            .where(
                PaperLearningProgram.portfolio_id == portfolio_id,
                PaperLearningProgram.status == "active",
            )
            .order_by(desc(PaperLearningProgram.cycle_number))
            .limit(1)
        )
        if row is not None:
            return row
        latest = self.db.scalar(
            select(PaperLearningProgram)
            .where(PaperLearningProgram.portfolio_id == portfolio_id)
            .order_by(desc(PaperLearningProgram.cycle_number))
            .limit(1)
        )
        cycle = (latest.cycle_number + 1) if latest else 1
        # Anchor start to first review day when available (no look-ahead).
        first_review = self.db.scalar(
            select(PostTradeReview)
            .where(PostTradeReview.portfolio_id == portfolio_id)
            .order_by(PostTradeReview.closed_at.asc())
            .limit(1)
        )
        started = first_review.closed_at.date() if first_review else datetime.now(UTC).date()
        row = PaperLearningProgram(
            portfolio_id=portfolio_id,
            cycle_number=cycle,
            required_days=LEARNING_REQUIRED_DAYS,
            started_on=started,
            status="active",
            detail={"engine": "advanced_learning@1", "paper_only": True},
        )
        self.db.add(row)
        self.db.flush()
        for key, title in MILESTONE_DEFS:
            self.db.add(
                PaperLearningMilestone(
                    program_id=row.id,
                    portfolio_id=portfolio_id,
                    milestone_key=key,
                    title=title,
                    achieved=False,
                    evidence={},
                )
            )
        self.db.flush()
        self.audit.append(
            action="learning.program_started",
            resource_type="paper_learning_program",
            resource_id=str(row.id),
            payload={
                "portfolio_id": str(portfolio_id),
                "required_days": LEARNING_REQUIRED_DAYS,
                "started_on": started.isoformat(),
                "live_trading_enabled": False,
            },
        )
        self.db.flush()
        return row

    def learning_day_index(self, program: PaperLearningProgram, on: date | None = None) -> int:
        today = on or datetime.now(UTC).date()
        # Active calendar days with closed reviews in-window (evidence-based).
        reviews = list(
            self.db.scalars(
                select(PostTradeReview).where(
                    PostTradeReview.portfolio_id == program.portfolio_id,
                    PostTradeReview.closed_at >= datetime.combine(
                        program.started_on, datetime.min.time(), tzinfo=UTC
                    ),
                )
            )
        )
        days = sorted({r.closed_at.date() for r in reviews if r.closed_at.date() <= today})
        if not days:
            # Day 1 begins at program start even with no trades yet.
            elapsed = (today - program.started_on).days + 1
            return max(1, min(program.required_days, elapsed))
        return max(1, min(program.required_days, len(days)))

    # --- metrics from verified evidence ------------------------------------

    def _reviews_for_program(self, program: PaperLearningProgram) -> list[PostTradeReview]:
        start = datetime.combine(program.started_on, datetime.min.time(), tzinfo=UTC)
        end_day = program.started_on + timedelta(days=program.required_days)
        end = datetime.combine(end_day, datetime.max.time(), tzinfo=UTC)
        return list(
            self.db.scalars(
                select(PostTradeReview)
                .where(
                    PostTradeReview.portfolio_id == program.portfolio_id,
                    PostTradeReview.closed_at >= start,
                    PostTradeReview.closed_at <= end,
                )
                .order_by(PostTradeReview.closed_at.asc())
            )
        )

    def _net_after_costs(self, review: PostTradeReview) -> Decimal:
        detail = dict(review.detail or {})
        if "expectancy_adjusted_pnl" in detail:
            return _dec(detail["expectancy_adjusted_pnl"])
        if "simulated_cost_haircut" in detail:
            return _dec(review.realized_pnl) - _dec(detail["simulated_cost_haircut"])
        # Fallback observational haircut (same constant as intelligence service).
        haircut = abs(_dec(review.realized_pnl)) * SIMULATED_COST_BPS / Decimal("10000")
        return _dec(review.realized_pnl) - haircut

    def compute_core_metrics(self, program: PaperLearningProgram) -> dict[str, Any]:
        reviews = self._reviews_for_program(program)
        nets = [self._net_after_costs(r) for r in reviews]
        wins = [n for n in nets if n > 0]
        losses = [n for n in nets if n < 0]
        today = datetime.now(UTC).date()
        today_nets = [
            self._net_after_costs(r)
            for r in reviews
            if r.closed_at.date() == today
        ]
        total = sum(nets, Decimal("0"))
        day_pnl = sum(today_nets, Decimal("0"))
        win_rate = (Decimal(len(wins)) / Decimal(len(nets))) if nets else None
        gross_wins = sum(wins, Decimal("0"))
        gross_losses = abs(sum(losses, Decimal("0")))
        profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else None
        expectancy = (total / Decimal(len(nets))) if nets else None

        equity = Decimal("0")
        peak = Decimal("0")
        max_dd = Decimal("0")
        for n in nets:
            equity += n
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        by_strategy: dict[str, list[Decimal]] = {}
        by_coin: dict[str, list[Decimal]] = {}
        for r, n in zip(reviews, nets, strict=True):
            by_strategy.setdefault(r.strategy_key, []).append(n)
            by_coin.setdefault(r.symbol, []).append(n)

        def _leader(groups: dict[str, list[Decimal]]) -> str | None:
            if not groups:
                return None
            scored = {k: sum(v, Decimal("0")) for k, v in groups.items()}
            return max(scored, key=scored.get)

        leading_strategy = _leader(by_strategy)
        best_coin = _leader(by_coin)
        worst_strategy = None
        worst_coin = None
        if by_strategy:
            scored = {k: sum(v, Decimal("0")) for k, v in by_strategy.items()}
            worst_strategy = min(scored, key=scored.get)
        if by_coin:
            scored = {k: sum(v, Decimal("0")) for k, v in by_coin.items()}
            worst_coin = min(scored, key=scored.get)

        strategy_leaderboard = []
        for key, vals in by_strategy.items():
            w = sum(1 for v in vals if v > 0)
            strategy_leaderboard.append(
                {
                    "strategy_key": key,
                    "trades": len(vals),
                    "wins": w,
                    "win_rate": _as_str(Decimal(w) / Decimal(len(vals))) if vals else None,
                    "net_pnl_after_costs": _as_str(sum(vals, Decimal("0")), 8),
                    "paper_confidence_delta": _as_str(
                        self.paper_confidence_delta(program.portfolio_id, key)
                    ),
                }
            )
        strategy_leaderboard.sort(
            key=lambda row: Decimal(row["net_pnl_after_costs"] or "0"), reverse=True
        )

        calibration = self.intelligence.confidence_calibration()
        learning_confidence = self._learning_confidence(
            closed=len(nets),
            win_rate=win_rate,
            expectancy=expectancy,
            calibration=calibration,
        )
        readiness = self._readiness_score(
            day_index=self.learning_day_index(program),
            closed=len(nets),
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
            max_dd=max_dd,
            learning_confidence=learning_confidence,
        )

        good_vs_lucky = self._good_vs_lucky(reviews)
        lessons = self._recent_lessons(reviews)
        strategy_by_regime = self._strategy_by_regime(reviews)
        pattern_performance = self._pattern_performance(reviews)
        learning = self.intelligence.learning_summary()
        missed_and_rejected = {
            "rejected_that_became_winners": learning.get(
                "rejected_that_became_winners", 0
            ),
            "accepted_that_became_losers": learning.get(
                "accepted_that_became_losers", 0
            ),
            "strongest_conditions": learning.get("strongest_conditions"),
            "weakest_conditions": learning.get("weakest_conditions"),
            "note": (
                "Missed opportunities and rejected-candidate outcomes are "
                "observational PAPER evidence only."
            ),
        }

        return {
            "trades_closed": len(nets),
            "wins": len(wins),
            "losses": len(losses),
            "net_pnl_after_costs": total,
            "today_pnl_after_costs": day_pnl,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy_after_costs": expectancy,
            "max_drawdown": max_dd if nets else None,
            "leading_strategy": leading_strategy,
            "best_coin": best_coin,
            "worst_strategy": worst_strategy,
            "worst_coin": worst_coin,
            "learning_confidence": learning_confidence,
            "readiness_score": readiness,
            "strategy_leaderboard": strategy_leaderboard,
            "strategy_by_regime": strategy_by_regime,
            "pattern_performance": pattern_performance,
            "good_vs_lucky": good_vs_lucky,
            "missed_and_rejected": missed_and_rejected,
            "recent_lessons": lessons,
            "calibration": calibration,
            "cost_model_bps_each_way": str(SIMULATED_COST_BPS),
            "volume_never_triggers_trade": VOLUME_NEVER_TRIGGERS_TRADE,
        }

    def _learning_confidence(
        self,
        *,
        closed: int,
        win_rate: Decimal | None,
        expectancy: Decimal | None,
        calibration: dict[str, Any],
    ) -> Decimal:
        if closed <= 0:
            return Decimal("5")
        score = Decimal("20")
        score += min(Decimal("30"), Decimal(closed) * Decimal("2"))
        if win_rate is not None:
            score += win_rate * Decimal("25")
        if expectancy is not None and expectancy > 0:
            score += Decimal("15")
        if calibration.get("higher_confidence_better"):
            score += Decimal("10")
        return min(Decimal("100"), max(Decimal("0"), score))

    def _readiness_score(
        self,
        *,
        day_index: int,
        closed: int,
        win_rate: Decimal | None,
        profit_factor: Decimal | None,
        expectancy: Decimal | None,
        max_dd: Decimal,
        learning_confidence: Decimal,
    ) -> Decimal:
        day_part = (Decimal(day_index) / Decimal(LEARNING_REQUIRED_DAYS)) * Decimal("25")
        trade_part = min(Decimal("20"), Decimal(closed) * Decimal("1.5"))
        quality = Decimal("0")
        if win_rate is not None and win_rate >= Decimal("0.45"):
            quality += Decimal("15")
        if profit_factor is not None and profit_factor >= Decimal("1.2"):
            quality += Decimal("15")
        if expectancy is not None and expectancy > 0:
            quality += Decimal("10")
        if max_dd <= Decimal("500"):
            quality += Decimal("10")
        conf_part = learning_confidence * Decimal("0.05")
        return min(Decimal("100"), day_part + trade_part + quality + conf_part)

    def _good_vs_lucky(self, reviews: list[PostTradeReview]) -> dict[str, Any]:
        good_wins = 0
        lucky_wins = 0
        bad_losses = 0
        for r in reviews:
            if r.realized_pnl > 0:
                if r.good_decision is True:
                    good_wins += 1
                else:
                    lucky_wins += 1
            elif r.realized_pnl < 0 and r.good_decision is False:
                bad_losses += 1
        return {
            "good_decision_wins": good_wins,
            "lucky_or_unlabeled_wins": lucky_wins,
            "poor_decision_losses": bad_losses,
        }

    def _recent_lessons(self, reviews: list[PostTradeReview]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for r in reversed(reviews[-12:]):
            snap = None
            if r.decision_snapshot_id:
                snap = self.db.get(TradeDecisionSnapshot, r.decision_snapshot_id)
            pattern = classify_trade_pattern(r, snap)
            out.append(
                {
                    "id": str(r.id),
                    "at": r.closed_at.isoformat(),
                    "symbol": r.symbol,
                    "strategy": r.strategy_key,
                    "outcome": r.outcome,
                    "net_after_costs": _as_str(self._net_after_costs(r), 8),
                    "pattern": pattern,
                    "good_decision": r.good_decision,
                    "lesson": r.explanation[:240],
                    "confidence_score": _as_str(r.confidence_score),
                }
            )
        return out

    def _strategy_by_regime(self, reviews: list[PostTradeReview]) -> list[dict[str, Any]]:
        """Which strategies work under which market regimes (stored evidence only)."""
        buckets: dict[tuple[str, str], list[Decimal]] = {}
        for r in reviews:
            regime = (r.market_regime or "unknown").lower()
            key = (r.strategy_key, regime)
            buckets.setdefault(key, []).append(self._net_after_costs(r))
        rows: list[dict[str, Any]] = []
        for (strategy_key, regime), vals in buckets.items():
            wins = sum(1 for v in vals if v > 0)
            net = sum(vals, Decimal("0"))
            rows.append(
                {
                    "strategy_key": strategy_key,
                    "market_regime": regime,
                    "trades": len(vals),
                    "wins": wins,
                    "win_rate": _as_str(Decimal(wins) / Decimal(len(vals))) if vals else None,
                    "net_pnl_after_costs": _as_str(net, 8),
                    "expectancy_after_costs": _as_str(net / Decimal(len(vals)), 8)
                    if vals
                    else None,
                }
            )
        rows.sort(
            key=lambda row: Decimal(row["net_pnl_after_costs"] or "0"), reverse=True
        )
        return rows[:24]

    def _pattern_performance(self, reviews: list[PostTradeReview]) -> list[dict[str, Any]]:
        """Dip/breakout/momentum/range/peak evidence aggregated after costs."""
        buckets: dict[str, list[Decimal]] = {}
        for r in reviews:
            snap = (
                self.db.get(TradeDecisionSnapshot, r.decision_snapshot_id)
                if r.decision_snapshot_id
                else None
            )
            pattern = classify_trade_pattern(r, snap)
            buckets.setdefault(pattern, []).append(self._net_after_costs(r))
        rows: list[dict[str, Any]] = []
        for pattern, vals in buckets.items():
            wins = sum(1 for v in vals if v > 0)
            net = sum(vals, Decimal("0"))
            rows.append(
                {
                    "pattern": pattern,
                    "trades": len(vals),
                    "wins": wins,
                    "win_rate": _as_str(Decimal(wins) / Decimal(len(vals))) if vals else None,
                    "net_pnl_after_costs": _as_str(net, 8),
                }
            )
        rows.sort(
            key=lambda row: Decimal(row["net_pnl_after_costs"] or "0"), reverse=True
        )
        return rows

    # --- Opportunity Radar / volume inputs ---------------------------------

    def high_volume_learning_summary(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        """Use Opportunity Radar candidates + verified OHLCV volume as learning input.

        High relative volume raises analysis_priority only. Volume alone never
        triggers a trade (enforced here and documented on the pane).
        """
        candidates = list(
            self.db.scalars(
                select(MarketScanCandidate)
                .where(MarketScanCandidate.stage.notin_(("Rejected", "Expired")))
                .order_by(desc(MarketScanCandidate.evaluated_at))
                .limit(40)
            )
        )
        rows: list[dict[str, Any]] = []
        for c in candidates:
            vol = self._market_quality(c.symbol)
            priority = float(c.score or 0)
            if vol and vol.get("relative_volume") is not None:
                rv = float(vol["relative_volume"])
                if rv >= float(VOLUME_RELATIVE_HIGH):
                    # Volume raises analysis priority only — never a trade gate.
                    priority += min(20.0, (rv - 1.0) * 10.0)
            rows.append(
                {
                    "symbol": c.symbol,
                    "stage": c.stage,
                    "bias": c.bias,
                    "radar_score": _as_str(c.score) if c.score is not None else None,
                    "analysis_priority": round(priority, 2),
                    "relative_volume": vol.get("relative_volume") if vol else None,
                    "liquidity_ok": vol.get("liquidity_ok") if vol else None,
                    "volatility_pct": vol.get("volatility_pct") if vol else None,
                    "spread_proxy_pct": vol.get("spread_proxy_pct") if vol else None,
                    "activity_notional": vol.get("activity_notional") if vol else None,
                    "volume_triggers_trade": False,
                    "why": "High volume increases analysis priority only — never a trade trigger.",
                }
            )
        rows.sort(key=lambda r: r["analysis_priority"], reverse=True)
        high = [r for r in rows if (r["relative_volume"] or 0) >= float(VOLUME_RELATIVE_HIGH)]
        liquid = [r for r in high if r.get("liquidity_ok")]
        return {
            "volume_never_triggers_trade": True,
            "high_relative_volume_threshold": str(VOLUME_RELATIVE_HIGH),
            "radar_inputs_considered": len(rows),
            "high_volume_symbols": high[:8],
            "priority_queue": rows[:10],
            "market_quality_note": (
                "Liquidity, volatility, spread proxy (intrabar range/mid), and "
                "activity are derived from verified historical OHLCV only — no look-ahead."
            ),
            "findings": (
                f"{len(high)} Opportunity Radar symbols show elevated relative volume "
                f"({len(liquid)} with liquidity_ok); ranked higher for analysis, not auto-entry."
                if high
                else "No elevated relative-volume symbols in the current Opportunity Radar set."
            ),
        }

    def _relative_volume(self, symbol: str) -> dict[str, Any] | None:
        """Backward-compatible alias for market quality metrics."""
        return self._market_quality(symbol)

    def _market_quality(self, symbol: str) -> dict[str, Any] | None:
        """Relative volume + liquidity/volatility/spread/activity from historical bars."""
        instrument = self.db.scalar(
            select(MarketInstrument).where(MarketInstrument.symbol == symbol)
        )
        if instrument is None:
            return None
        bars = list(
            self.db.scalars(
                select(MarketOhlcvBar)
                .where(
                    MarketOhlcvBar.instrument_id == instrument.id,
                    MarketOhlcvBar.timeframe.in_(("1m", "5m")),
                    MarketOhlcvBar.volume.is_not(None),
                )
                .order_by(desc(MarketOhlcvBar.close_time))
                .limit(21)
            )
        )
        if len(bars) < 6:
            return {
                "relative_volume": None,
                "liquidity_ok": None,
                "volatility_pct": None,
                "spread_proxy_pct": None,
                "activity_notional": None,
                "note": "insufficient_volume_history",
            }
        # Use only bars available at evaluation time (already historical).
        latest = bars[0]
        hist = bars[1:21]
        hist_vols = [_dec(b.volume) for b in hist if b.volume is not None]
        if not hist_vols or latest.volume is None:
            return {
                "relative_volume": None,
                "liquidity_ok": False,
                "volatility_pct": None,
                "spread_proxy_pct": None,
                "activity_notional": None,
                "note": "missing_volume",
            }
        avg = sum(hist_vols, Decimal("0")) / Decimal(len(hist_vols))
        if avg <= 0:
            return {
                "relative_volume": None,
                "liquidity_ok": False,
                "volatility_pct": None,
                "spread_proxy_pct": None,
                "activity_notional": None,
                "note": "zero_avg_volume",
            }
        rel = _dec(latest.volume) / avg
        close = _dec(latest.close)
        mid = (_dec(latest.high) + _dec(latest.low)) / Decimal("2")
        spread_proxy = (
            ((_dec(latest.high) - _dec(latest.low)) / mid * Decimal("100"))
            if mid > 0
            else None
        )
        ranges: list[Decimal] = []
        for b in hist:
            c = _dec(b.close)
            if c > 0:
                ranges.append((_dec(b.high) - _dec(b.low)) / c * Decimal("100"))
        volatility = (
            sum(ranges, Decimal("0")) / Decimal(len(ranges)) if ranges else None
        )
        activity = float(_dec(latest.volume) * close) if close > 0 else None
        liquidity_ok = _dec(latest.volume) >= avg * Decimal("0.5") and _dec(
            latest.volume
        ) > 0
        return {
            "relative_volume": float(rel),
            "liquidity_ok": bool(liquidity_ok),
            "volatility_pct": float(volatility) if volatility is not None else None,
            "spread_proxy_pct": float(spread_proxy) if spread_proxy is not None else None,
            "activity_notional": activity,
            "latest_volume": float(_dec(latest.volume)),
            "avg_volume": float(avg),
            "look_ahead_bias": False,
        }

    # --- adaptive PAPER confidence -----------------------------------------

    def paper_confidence_delta(
        self, portfolio_id: uuid.UUID, strategy_key: str
    ) -> Decimal:
        row = self.db.scalar(
            select(PaperStrategyConfidenceState).where(
                PaperStrategyConfidenceState.portfolio_id == portfolio_id,
                PaperStrategyConfidenceState.strategy_key == strategy_key,
                PaperStrategyConfidenceState.paper_only.is_(True),
            )
        )
        if row is None:
            return Decimal("0")
        return max(ADAPTIVE_DELTA_MIN, min(ADAPTIVE_DELTA_MAX, _dec(row.confidence_delta)))

    def update_adaptive_confidence(self, program: PaperLearningProgram) -> list[dict[str, Any]]:
        """Adjust PAPER-only confidence deltas from expectancy evidence."""
        reviews = self._reviews_for_program(program)
        by_strategy: dict[str, list[PostTradeReview]] = {}
        for r in reviews:
            by_strategy.setdefault(r.strategy_key, []).append(r)
        changes: list[dict[str, Any]] = []
        for strategy_key, items in by_strategy.items():
            if len(items) < ADAPTIVE_MIN_TRADES:
                continue
            nets = [self._net_after_costs(r) for r in items]
            expectancy = sum(nets, Decimal("0")) / Decimal(len(nets))
            # Map expectancy into a bounded delta (−15..+15).
            raw = expectancy * Decimal("2")
            delta = max(ADAPTIVE_DELTA_MIN, min(ADAPTIVE_DELTA_MAX, raw))
            # Soften until more evidence.
            if len(items) < 10:
                delta = (delta * Decimal(len(items)) / Decimal("10")).quantize(
                    Decimal("0.01")
                )
            row = self.db.scalar(
                select(PaperStrategyConfidenceState).where(
                    PaperStrategyConfidenceState.portfolio_id == program.portfolio_id,
                    PaperStrategyConfidenceState.strategy_key == strategy_key,
                )
            )
            explanation = (
                f"PAPER adaptive delta from {len(items)} closed trades; "
                f"expectancy_after_costs={expectancy}. Bounded [{ADAPTIVE_DELTA_MIN},"
                f" {ADAPTIVE_DELTA_MAX}]. Reversible. Never applied to live trading."
            )
            if row is None:
                row = PaperStrategyConfidenceState(
                    portfolio_id=program.portfolio_id,
                    strategy_key=strategy_key,
                    confidence_delta=delta,
                    sample_trades=len(items),
                    explanation=explanation,
                    version=1,
                    reversible=True,
                    paper_only=True,
                    detail={
                        "expectancy_after_costs": str(expectancy),
                        "history": [],
                    },
                )
                self.db.add(row)
            else:
                if not row.reversible or not row.paper_only:
                    continue
                prior = _dec(row.confidence_delta)
                if prior == delta and row.sample_trades == len(items):
                    continue
                history = list(row.detail.get("history") or [])
                history.append(
                    {
                        "from": str(prior),
                        "to": str(delta),
                        "at": datetime.now(UTC).isoformat(),
                        "sample_trades": len(items),
                    }
                )
                row.confidence_delta = delta
                row.sample_trades = len(items)
                row.explanation = explanation
                row.version = int(row.version) + 1
                row.detail = {
                    **dict(row.detail or {}),
                    "expectancy_after_costs": str(expectancy),
                    "history": history[-20:],
                }
            self.db.flush()
            change = {
                "strategy_key": strategy_key,
                "confidence_delta": str(delta),
                "sample_trades": len(items),
                "version": int(row.version),
                "paper_only": True,
                "reversible": True,
            }
            changes.append(change)
            self.audit.append(
                action="learning.adaptive_confidence_updated",
                resource_type="paper_strategy_confidence_state",
                resource_id=str(row.id),
                payload={**change, "live_trading_enabled": False},
            )
        self.db.flush()
        return changes

    # --- milestones --------------------------------------------------------

    def evaluate_milestones(self, program: PaperLearningProgram) -> list[dict[str, Any]]:
        reviews = self._reviews_for_program(program)
        metrics = self.compute_core_metrics(program)
        day_index = self.learning_day_index(program)
        now = datetime.now(UTC)

        # Precompute evidence flags from stored reviews only.
        first_win = next((r for r in reviews if self._net_after_costs(r) > 0), None)
        day_totals: dict[date, Decimal] = {}
        for r in reviews:
            day_totals[r.closed_at.date()] = day_totals.get(
                r.closed_at.date(), Decimal("0")
            ) + self._net_after_costs(r)
        first_profitable_day = next(
            (d for d, v in sorted(day_totals.items()) if v > 0), None
        )
        validated_strategy = None
        for row in metrics["strategy_leaderboard"]:
            if (
                int(row["trades"]) >= 5
                and row["win_rate"] is not None
                and Decimal(row["win_rate"]) >= Decimal("0.5")
                and Decimal(row["net_pnl_after_costs"] or "0") > 0
            ):
                validated_strategy = row
                break

        dip_win = None
        hv_breakout = None
        for r in reviews:
            if self._net_after_costs(r) <= 0:
                continue
            snap = (
                self.db.get(TradeDecisionSnapshot, r.decision_snapshot_id)
                if r.decision_snapshot_id
                else None
            )
            pattern = classify_trade_pattern(r, snap)
            if pattern == "dip_reversal" and dip_win is None:
                dip_win = r
            if pattern == "high_volume_breakout" and hv_breakout is None:
                hv_breakout = r

        expectancy = metrics["expectancy_after_costs"]
        max_dd = metrics["max_drawdown"] or Decimal("0")
        risk_ok = (
            metrics["trades_closed"] >= 5
            and max_dd <= Decimal("500")
            and all(
                # No review without stop evidence is required; use exit reason presence.
                bool(r.exit_reason)
                for r in reviews
            )
        )

        checks: dict[str, tuple[bool, dict[str, Any]]] = {
            "first_profitable_trade": (
                first_win is not None,
                {
                    "review_id": str(first_win.id) if first_win else None,
                    "symbol": first_win.symbol if first_win else None,
                    "net": str(self._net_after_costs(first_win)) if first_win else None,
                },
            ),
            "first_profitable_day": (
                first_profitable_day is not None,
                {"day": first_profitable_day.isoformat() if first_profitable_day else None},
            ),
            "first_validated_strategy": (
                validated_strategy is not None,
                validated_strategy or {},
            ),
            "first_successful_dip_reversal": (
                dip_win is not None,
                {
                    "review_id": str(dip_win.id) if dip_win else None,
                    "symbol": dip_win.symbol if dip_win else None,
                },
            ),
            "first_successful_high_volume_breakout": (
                hv_breakout is not None,
                {
                    "review_id": str(hv_breakout.id) if hv_breakout else None,
                    "symbol": hv_breakout.symbol if hv_breakout else None,
                },
            ),
            "positive_expectancy_after_fees": (
                expectancy is not None and expectancy > 0 and metrics["trades_closed"] >= 5,
                {"expectancy_after_costs": _as_str(expectancy, 8)},
            ),
            "risk_discipline": (
                risk_ok,
                {"max_drawdown": _as_str(max_dd, 8), "trades": metrics["trades_closed"]},
            ),
            "day_20_completion": (
                day_index >= program.required_days,
                {"learning_day": day_index, "required_days": program.required_days},
            ),
        }

        out: list[dict[str, Any]] = []
        for key, title in MILESTONE_DEFS:
            row = self.db.scalar(
                select(PaperLearningMilestone).where(
                    PaperLearningMilestone.program_id == program.id,
                    PaperLearningMilestone.milestone_key == key,
                )
            )
            if row is None:
                row = PaperLearningMilestone(
                    program_id=program.id,
                    portfolio_id=program.portfolio_id,
                    milestone_key=key,
                    title=title,
                    achieved=False,
                    evidence={},
                )
                self.db.add(row)
                self.db.flush()
            achieved, evidence = checks[key]
            if achieved and not row.achieved:
                row.achieved = True
                row.achieved_at = now
                row.evidence = evidence
                self.audit.append(
                    action="learning.milestone_achieved",
                    resource_type="paper_learning_milestone",
                    resource_id=str(row.id),
                    payload={"milestone_key": key, "evidence": evidence},
                )
            elif not row.achieved:
                row.evidence = evidence
            out.append(
                {
                    "key": key,
                    "title": title,
                    "achieved": bool(row.achieved),
                    "achieved_at": row.achieved_at.isoformat() if row.achieved_at else None,
                    "evidence": row.evidence,
                }
            )
        self.db.flush()
        return out

    # --- day snapshot + readiness report -----------------------------------

    def upsert_today_snapshot(self, program: PaperLearningProgram) -> PaperLearningDaySnapshot:
        metrics = self.compute_core_metrics(program)
        today = datetime.now(UTC).date()
        day_index = self.learning_day_index(program, today)
        existing = self.db.scalar(
            select(PaperLearningDaySnapshot).where(
                PaperLearningDaySnapshot.program_id == program.id,
                PaperLearningDaySnapshot.day_date == today,
            )
        )
        payload = {
            "net_pnl_after_costs": metrics["net_pnl_after_costs"],
            "day_pnl_after_costs": metrics["today_pnl_after_costs"],
            "trades_closed": metrics["trades_closed"],
            "wins": metrics["wins"],
            "losses": metrics["losses"],
            "win_rate": metrics["win_rate"],
            "profit_factor": metrics["profit_factor"],
            "expectancy_after_costs": metrics["expectancy_after_costs"],
            "max_drawdown": metrics["max_drawdown"],
            "leading_strategy": metrics["leading_strategy"],
            "best_coin": metrics["best_coin"],
            "learning_confidence": metrics["learning_confidence"],
            "readiness_score": metrics["readiness_score"],
            "metrics": {
                "strategy_leaderboard": metrics["strategy_leaderboard"],
                "strategy_by_regime": metrics["strategy_by_regime"],
                "pattern_performance": metrics["pattern_performance"],
                "good_vs_lucky": metrics["good_vs_lucky"],
                "missed_and_rejected": metrics["missed_and_rejected"],
                "calibration": metrics["calibration"],
                "cost_model_bps_each_way": metrics["cost_model_bps_each_way"],
            },
        }
        if existing is None:
            existing = PaperLearningDaySnapshot(
                program_id=program.id,
                portfolio_id=program.portfolio_id,
                day_index=day_index,
                day_date=today,
                **payload,
            )
            self.db.add(existing)
        else:
            for k, v in payload.items():
                setattr(existing, k, v)
            existing.day_index = day_index
        self.db.flush()
        return existing

    def maybe_generate_readiness_report(
        self, program: PaperLearningProgram
    ) -> PaperLearningReadinessReport | None:
        day_index = self.learning_day_index(program)
        if day_index < program.required_days:
            return self.db.scalar(
                select(PaperLearningReadinessReport).where(
                    PaperLearningReadinessReport.program_id == program.id
                )
            )
        existing = self.db.scalar(
            select(PaperLearningReadinessReport).where(
                PaperLearningReadinessReport.program_id == program.id
            )
        )
        if existing is not None:
            return existing

        metrics = self.compute_core_metrics(program)
        milestones = self.evaluate_milestones(program)
        volume = self.high_volume_learning_summary(program.portfolio_id)
        learning = self.intelligence.learning_summary()
        misses = learning.get("rejected_that_became_winners", 0)
        ready = (
            metrics["trades_closed"] >= 10
            and metrics["expectancy_after_costs"] is not None
            and metrics["expectancy_after_costs"] > 0
            and (metrics["max_drawdown"] or Decimal("0")) <= Decimal("500")
            and metrics["readiness_score"] >= Decimal("60")
            and sum(1 for m in milestones if m["achieved"]) >= 5
        )
        body = {
            "learning_day": day_index,
            "required_days": program.required_days,
            "total_net_profitability_after_costs": _as_str(
                metrics["net_pnl_after_costs"], 8
            ),
            "best_strategy": metrics["leading_strategy"],
            "worst_strategy": metrics["worst_strategy"],
            "best_coin": metrics["best_coin"],
            "worst_coin": metrics["worst_coin"],
            "high_volume_findings": volume.get("findings"),
            "high_volume_symbols": volume.get("high_volume_symbols"),
            "dip_and_peak_findings": {
                "pattern_performance": [
                    p
                    for p in metrics["pattern_performance"]
                    if p["pattern"]
                    in {
                        "dip_reversal",
                        "dip_reversal_attempt",
                        "peak_exhaustion",
                        "high_volume_breakout",
                        "breakout",
                        "momentum",
                        "range",
                    }
                ],
                "lessons": [
                    x
                    for x in metrics["recent_lessons"]
                    if x["pattern"]
                    in {
                        "dip_reversal",
                        "dip_reversal_attempt",
                        "peak_exhaustion",
                        "high_volume_breakout",
                        "breakout",
                        "momentum",
                    }
                ][:8],
            },
            "strategy_by_market_conditions": metrics["strategy_by_regime"],
            "confidence_accuracy": metrics["calibration"],
            "good_vs_lucky": metrics["good_vs_lucky"],
            "drawdown_and_risk_discipline": {
                "max_drawdown": _as_str(metrics["max_drawdown"], 8),
                "risk_discipline_milestone": next(
                    (m for m in milestones if m["key"] == "risk_discipline"), None
                ),
            },
            "missed_opportunities": {
                "rejected_that_became_winners": misses,
                "accepted_that_became_losers": learning.get(
                    "accepted_that_became_losers", 0
                ),
                "strongest_conditions": learning.get("strongest_conditions"),
                "weakest_conditions": learning.get("weakest_conditions"),
            },
            "weaknesses_and_limitations": self._weaknesses(metrics, learning),
            "milestones": milestones,
            "ready_for_controlled_live_testing": ready,
            "live_trading_enabled": False,
            "disclaimer": (
                "This report never enables live trading. Controlled live testing "
                "requires separate Founder approval under Micro-Live governance."
            ),
        }
        summary = (
            f"Day {day_index}/{program.required_days} paper-learning complete. "
            f"Net after costs: {body['total_net_profitability_after_costs']}. "
            f"Ready for controlled live testing review: {'yes' if ready else 'no'}. "
            "Live trading remains disabled."
        )
        report = PaperLearningReadinessReport(
            program_id=program.id,
            portfolio_id=program.portfolio_id,
            report_date=datetime.now(UTC).date(),
            content_hash=_content_hash(body),
            ready_for_controlled_live_testing=ready,
            live_trading_enabled=False,
            summary=summary,
            body=body,
        )
        self.db.add(report)
        program.status = "completed"
        program.completed_on = datetime.now(UTC).date()
        self.db.flush()
        self.audit.append(
            action="learning.readiness_report_generated",
            resource_type="paper_learning_readiness_report",
            resource_id=str(report.id),
            payload={
                "ready_for_controlled_live_testing": ready,
                "live_trading_enabled": False,
                "content_hash": report.content_hash,
            },
        )
        self.db.flush()
        return report

    def _weaknesses(
        self, metrics: dict[str, Any], learning: dict[str, Any]
    ) -> list[str]:
        weaknesses: list[str] = []
        if metrics["trades_closed"] < 10:
            weaknesses.append("Too few closed paper trades for strong statistical claims.")
        if metrics["win_rate"] is not None and metrics["win_rate"] < Decimal("0.45"):
            weaknesses.append("Win rate below 45% in the learning window.")
        if metrics["expectancy_after_costs"] is not None and metrics[
            "expectancy_after_costs"
        ] <= 0:
            weaknesses.append("Expectancy after simulated fees is not positive.")
        if metrics["max_drawdown"] and metrics["max_drawdown"] > Decimal("300"):
            weaknesses.append("Drawdown is elevated relative to the paper desk size.")
        if learning.get("accepted_that_became_losers", 0) > learning.get(
            "rejected_that_became_winners", 0
        ):
            weaknesses.append("More accepted losers than rejected-that-won misses.")
        if not weaknesses:
            weaknesses.append(
                "No critical statistical weakness detected yet — continue monitoring."
            )
        return weaknesses

    # --- public pane + evaluate --------------------------------------------

    def pane(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        program = self.get_or_create_program(portfolio_id)
        metrics = self.compute_core_metrics(program)
        milestones = self.evaluate_milestones(program)
        volume = self.high_volume_learning_summary(portfolio_id)
        day_index = self.learning_day_index(program)
        report = self.db.scalar(
            select(PaperLearningReadinessReport).where(
                PaperLearningReadinessReport.program_id == program.id
            )
        )
        payload = {
            "program_id": str(program.id),
            "portfolio_id": str(portfolio_id),
            "learning_day": day_index,
            "required_days": program.required_days,
            "program_status": program.status,
            "started_on": program.started_on.isoformat(),
            "net_paper_profit": _as_str(metrics["net_pnl_after_costs"], 8),
            "today_pnl": _as_str(metrics["today_pnl_after_costs"], 8),
            "win_rate": _as_str(metrics["win_rate"]),
            "profit_factor": _as_str(metrics["profit_factor"]),
            "maximum_drawdown": _as_str(metrics["max_drawdown"], 8),
            "leading_strategy": metrics["leading_strategy"],
            "best_performing_coin": metrics["best_coin"],
            "learning_confidence": _as_str(metrics["learning_confidence"]),
            "readiness_score": _as_str(metrics["readiness_score"]),
            "strategy_leaderboard": metrics["strategy_leaderboard"],
            "strategy_by_regime": metrics["strategy_by_regime"],
            "pattern_performance": metrics["pattern_performance"],
            "high_volume_learning_summary": volume,
            "recent_trade_lessons": metrics["recent_lessons"],
            "learning_milestones": milestones,
            "good_vs_lucky": metrics["good_vs_lucky"],
            "missed_and_rejected": metrics["missed_and_rejected"],
            "confidence_calibration": metrics["calibration"],
            "expectancy_after_costs": _as_str(metrics["expectancy_after_costs"], 8),
            "cost_model_bps_each_way": metrics["cost_model_bps_each_way"],
            "readiness_report": (
                {
                    "id": str(report.id),
                    "summary": report.summary,
                    "ready_for_controlled_live_testing": report.ready_for_controlled_live_testing,
                    "live_trading_enabled": False,
                    "content_hash": report.content_hash,
                    "body": report.body,
                    "created_at": report.created_at.isoformat(),
                }
                if report
                else None
            ),
            "live_trading_enabled": False,
            "disclaimer": (
                "Advanced learning is PAPER-only. Profit is the mission; risk discipline "
                "protects the mission. Live trading is never auto-enabled."
            ),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        # Persist program/milestone bootstrap created during pane reads.
        try:
            self.db.commit()
        except Exception:  # noqa: BLE001
            self.db.rollback()
        return payload

    def evaluate_cycle(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        """Background/manual evaluation: snapshot, adaptive confidence, milestones, report."""
        program = self.get_or_create_program(portfolio_id)
        snap = self.upsert_today_snapshot(program)
        adaptive = self.update_adaptive_confidence(program)
        milestones = self.evaluate_milestones(program)
        report = self.maybe_generate_readiness_report(program)
        self.db.commit()
        return {
            "program_id": str(program.id),
            "day_index": snap.day_index,
            "day_date": snap.day_date.isoformat(),
            "adaptive_confidence_changes": adaptive,
            "milestones_achieved": sum(1 for m in milestones if m["achieved"]),
            "readiness_report_id": str(report.id) if report else None,
            "live_trading_enabled": False,
        }

    def readiness_report(self, portfolio_id: uuid.UUID) -> dict[str, Any] | None:
        program = self.get_or_create_program(portfolio_id)
        report = self.maybe_generate_readiness_report(program)
        self.db.commit()
        if report is None:
            return None
        return {
            "id": str(report.id),
            "program_id": str(program.id),
            "summary": report.summary,
            "ready_for_controlled_live_testing": report.ready_for_controlled_live_testing,
            "live_trading_enabled": False,
            "content_hash": report.content_hash,
            "body": report.body,
            "created_at": report.created_at.isoformat(),
        }

    def health_check(self) -> dict[str, Any]:
        """Lightweight probe: learning tables readable; live stays locked."""
        try:
            programs = list(
                self.db.scalars(
                    select(PaperLearningProgram)
                    .order_by(desc(PaperLearningProgram.created_at))
                    .limit(5)
                )
            )
            active = [p for p in programs if p.status == "active"]
            latest_snap = self.db.scalar(
                select(PaperLearningDaySnapshot)
                .order_by(desc(PaperLearningDaySnapshot.day_date))
                .limit(1)
            )
            milestone_count = len(
                list(self.db.scalars(select(PaperLearningMilestone).limit(1)))
            )
            status = "ok"
            detail = "Advanced learning tables reachable; PAPER-only engine ready."
            if not programs:
                status = "idle"
                detail = "No learning program yet — starts when a paper portfolio exists."
            return {
                "status": status,
                "detail": detail,
                "active_programs": len(active),
                "programs_seen": len(programs),
                "milestones_table_ok": milestone_count >= 0,
                "latest_snapshot_day": (
                    latest_snap.day_date.isoformat() if latest_snap else None
                ),
                "volume_never_triggers_trade": VOLUME_NEVER_TRIGGERS_TRADE,
                "live_trading_enabled": False,
                "paper_only": True,
            }
        except Exception as exc:  # noqa: BLE001 — probe must never crash callers
            return {
                "status": "failed",
                "detail": str(exc)[:200],
                "live_trading_enabled": False,
                "paper_only": True,
            }
