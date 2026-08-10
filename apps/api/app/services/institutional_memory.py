"""Institutional memory for PAPER learning — reusable evidence from post-trade reviews.

PAPER-only. Never unlocks live trading. Used to consult prior lessons BEFORE
automatic paper entries so retained knowledge influences future decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.trading_intelligence import (
    PostTradeReview,
    TradeDecisionSnapshot,
)
from app.services.advanced_learning_service import (
    ADAPTIVE_DELTA_MAX,
    ADAPTIVE_DELTA_MIN,
    classify_trade_pattern,
)
from app.services.trading_intelligence_service import SIMULATED_COST_BPS

EXECUTE_SCORE = Decimal("62")
WAIT_SCORE = Decimal("48")
MIN_EVIDENCE_FOR_HARD_AVOID = 5
WEAK_EXPECTANCY = Decimal("-0.5")


def _dec(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _net_after_costs(review: PostTradeReview) -> Decimal:
    detail = dict(review.detail or {})
    if detail.get("expectancy_adjusted_pnl") is not None:
        return _dec(detail["expectancy_adjusted_pnl"])
    notional = abs(_dec(review.realized_pnl))
    # Fallback haircut if older rows lack adjusted pnl.
    haircut = notional * SIMULATED_COST_BPS / Decimal("10000") * 2
    return _dec(review.realized_pnl) - haircut


def confidence_bucket(score: Decimal | float | None) -> str:
    s = float(score or 50)
    if s >= 75:
        return "high"
    if s >= 55:
        return "medium"
    if s >= 40:
        return "low"
    return "very_low"


def volume_condition_from_detail(detail: dict[str, Any] | None) -> str:
    d = detail or {}
    factors = d.get("contributing_factors") if isinstance(d.get("contributing_factors"), dict) else {}
    if factors.get("volume_ok") is True or d.get("relative_volume_high") is True:
        return "elevated"
    if factors.get("volume_ok") is False:
        return "thin"
    rv = d.get("relative_volume") or factors.get("relative_volume")
    try:
        if rv is not None and float(rv) >= 1.5:
            return "elevated"
        if rv is not None and float(rv) < 0.7:
            return "thin"
    except (TypeError, ValueError):
        pass
    return "normal"


@dataclass(frozen=True)
class MemoryKey:
    strategy_key: str
    symbol: str
    market_regime: str
    trade_pattern: str
    volume_condition: str
    confidence_bucket: str
    outcome: str
    decision_quality: str

    def as_dict(self) -> dict[str, str]:
        return {
            "strategy_key": self.strategy_key,
            "symbol": self.symbol,
            "market_regime": self.market_regime,
            "trade_pattern": self.trade_pattern,
            "volume_condition": self.volume_condition,
            "confidence_bucket": self.confidence_bucket,
            "outcome": self.outcome,
            "decision_quality": self.decision_quality,
        }


def knowledge_record_from_review(
    review: PostTradeReview,
    snapshot: TradeDecisionSnapshot | None = None,
) -> dict[str, Any]:
    """Convert a completed PostTradeReview into structured reusable knowledge."""
    detail = dict(review.detail or {})
    snap_detail = dict(snapshot.detail) if snapshot and snapshot.detail else {}
    pattern = classify_trade_pattern(review, snapshot)
    dq = str(
        detail.get("decision_quality_code")
        or detail.get("decision_quality")
        or ("GOOD_DECISION" if review.good_decision else "POOR_DECISION")
    ).upper()
    # Normalize legacy labels into the four canonical codes when possible.
    if dq in {"ACCEPTABLE", "GOOD"}:
        dq = "GOOD_DECISION_WIN" if review.outcome == "win" else "GOOD_DECISION_LOSS"
    elif dq in {"REVIEW_REQUIRED", "POOR", "BAD"}:
        dq = "POOR_DECISION_WIN" if review.outcome == "win" else "POOR_DECISION_LOSS"
    key = MemoryKey(
        strategy_key=str(review.strategy_key or "unknown"),
        symbol=str(review.symbol or "*"),
        market_regime=str(review.market_regime or "unknown").lower(),
        trade_pattern=pattern,
        volume_condition=volume_condition_from_detail({**snap_detail, **detail}),
        confidence_bucket=confidence_bucket(review.confidence_score),
        outcome=str(review.outcome or "flat"),
        decision_quality=dq,
    )
    return {
        "review_id": str(review.id),
        "closed_at": review.closed_at.isoformat() if review.closed_at else None,
        "keys": key.as_dict(),
        "realized_pnl": str(review.realized_pnl),
        "net_after_costs": str(_net_after_costs(review)),
        "good_decision": review.good_decision,
        "explanation": (review.explanation or "")[:240],
        "paper_only": True,
    }


def grade_decision_quality(
    *,
    outcome: str,
    entry_price: Decimal | None,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    exit_reason: str,
    risk_status: str | None,
    volume_ok: bool | None,
    stale_data: bool,
    strategy_rule_ok: bool,
    holding_seconds: int,
) -> tuple[bool, str, dict[str, Any]]:
    """Grade process quality independently from profit/loss outcome.

    Returns (good_decision, quality_code, factors).
    quality_code is one of:
      GOOD_DECISION_WIN, GOOD_DECISION_LOSS, POOR_DECISION_WIN, POOR_DECISION_LOSS
    """
    factors: dict[str, Any] = {
        "entry_discipline": True,
        "strategy_rule_adherence": bool(strategy_rule_ok),
        "risk_reward_ok": True,
        "market_data_quality": not stale_data,
        "volume_liquidity_confirmation": volume_ok is not False,
        "position_risk_compliance": (risk_status or "clear") == "clear",
        "exit_discipline": True,
    }
    score = 0
    # Entry discipline: stop below entry for longs, target above entry.
    if entry_price is not None and entry_price > 0:
        if stop_loss is None or stop_loss >= entry_price:
            factors["entry_discipline"] = False
        else:
            score += 1
        if take_profit is None or take_profit <= entry_price:
            factors["entry_discipline"] = False
        else:
            score += 1
        if stop_loss is not None and take_profit is not None and stop_loss < entry_price:
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
            rr = float(reward / risk) if risk > 0 else 0.0
            factors["risk_reward"] = round(rr, 3)
            if rr >= 2.0:
                factors["risk_reward_ok"] = True
                score += 2
            elif rr >= 1.5:
                factors["risk_reward_ok"] = True
                score += 1
            else:
                factors["risk_reward_ok"] = False
    else:
        factors["entry_discipline"] = False

    if factors["strategy_rule_adherence"]:
        score += 1
    if factors["market_data_quality"]:
        score += 1
    if factors["volume_liquidity_confirmation"]:
        score += 1
    if factors["position_risk_compliance"]:
        score += 1

    reason = (exit_reason or "").lower()
    # Exit discipline: planned stop/target exits score higher than unexplained flips.
    if reason in {"stop_loss", "take_profit", "stop", "target"}:
        factors["exit_discipline"] = True
        score += 1
    elif reason in {"manual", "kill_switch", "flatten"}:
        factors["exit_discipline"] = True
    elif holding_seconds < 30 and reason not in {"stop_loss", "stop"}:
        factors["exit_discipline"] = False
        score -= 1
    else:
        factors["exit_discipline"] = True

    # Threshold: majority of process checks must pass.
    good = score >= 5 and factors["entry_discipline"] and factors["risk_reward_ok"]
    factors["process_score"] = score
    won = outcome == "win"
    if good and won:
        code = "GOOD_DECISION_WIN"
    elif good and not won:
        code = "GOOD_DECISION_LOSS"
    elif not good and won:
        code = "POOR_DECISION_WIN"
    else:
        code = "POOR_DECISION_LOSS"
    return good, code, factors


class InstitutionalMemoryService:
    """Retrieve and apply structured paper-learning memory before entry."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_knowledge(
        self, portfolio_id: UUID, *, limit: int = 200
    ) -> list[dict[str, Any]]:
        reviews = list(
            self.db.scalars(
                select(PostTradeReview)
                .where(PostTradeReview.portfolio_id == portfolio_id)
                .order_by(desc(PostTradeReview.closed_at))
                .limit(min(max(limit, 1), 500))
            )
        )
        out: list[dict[str, Any]] = []
        for r in reviews:
            snap = None
            if r.decision_snapshot_id:
                snap = self.db.get(TradeDecisionSnapshot, r.decision_snapshot_id)
            out.append(knowledge_record_from_review(r, snap))
        return out

    def knowledge_stats(self, portfolio_id: UUID) -> dict[str, Any]:
        knowledge = self.list_knowledge(portfolio_id, limit=500)
        retained = len(knowledge)
        reused = 0
        explained_loss = 0
        losses = 0
        quality_counts = {
            "GOOD_DECISION_WIN": 0,
            "GOOD_DECISION_LOSS": 0,
            "POOR_DECISION_WIN": 0,
            "POOR_DECISION_LOSS": 0,
        }
        for row in knowledge:
            keys = row.get("keys") or {}
            dq = str(keys.get("decision_quality") or "")
            if dq in quality_counts:
                quality_counts[dq] += 1
            if keys.get("outcome") == "loss":
                losses += 1
                if dq.startswith("GOOD_") or dq.startswith("POOR_"):
                    explained_loss += 1
            detail_reused = False
            # Count reuse markers from review detail if present via explanation tag.
            if "memory" in (row.get("explanation") or "").lower():
                detail_reused = True
            if detail_reused:
                reused += 1

        # Prefer explicit memory_influenced count from snapshots.
        snaps = list(
            self.db.scalars(
                select(TradeDecisionSnapshot)
                .where(TradeDecisionSnapshot.portfolio_id == portfolio_id)
                .order_by(desc(TradeDecisionSnapshot.created_at))
                .limit(300)
            )
        )
        influenced = 0
        for s in snaps:
            detail = dict(s.detail or {})
            mem = detail.get("institutional_memory") or detail.get("memory_consult")
            if isinstance(mem, dict) and mem.get("influenced"):
                influenced += 1
        reused = max(reused, influenced)
        reuse_rate = (
            Decimal(reused) / Decimal(max(1, len(snaps))) if snaps else Decimal("0")
        )
        good_n = (
            quality_counts["GOOD_DECISION_WIN"] + quality_counts["GOOD_DECISION_LOSS"]
        )
        total_q = sum(quality_counts.values()) or 1
        # Learning velocity: retained lessons per Academy day (cap display at day 20).
        velocity = Decimal(retained) / Decimal("20")
        return {
            "knowledge_retained": retained,
            "knowledge_reused": reused,
            "memory_reuse_rate": str(reuse_rate.quantize(Decimal("0.0001"))),
            "explained_loss_pct": str(
                (Decimal(explained_loss) / Decimal(losses)).quantize(Decimal("0.0001"))
                if losses
                else "0"
            ),
            "decision_quality": {
                **quality_counts,
                "good_decision_rate": str(
                    (Decimal(good_n) / Decimal(total_q)).quantize(Decimal("0.0001"))
                ),
            },
            "learning_velocity": str(velocity.quantize(Decimal("0.01"))),
            "snapshot_sample": len(snaps),
            "paper_only": True,
        }

    def consult_before_entry(
        self,
        *,
        portfolio_id: UUID,
        symbol: str,
        strategy_key: str,
        market_regime: str,
        base_score: float,
        paper_confidence_delta: Decimal | None,
        confidence_label_score: Decimal | None = None,
        volume_condition: str = "normal",
        trade_pattern: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve relevant prior evidence and produce EXECUTE / WAIT / AVOID."""
        knowledge = self.list_knowledge(portfolio_id, limit=400)
        regime = (market_regime or "unknown").lower()
        strategy = strategy_key or "unknown"
        pattern = (trade_pattern or "unclassified").lower()

        similar: list[dict[str, Any]] = []
        for row in knowledge:
            keys = row.get("keys") or {}
            score_match = 0
            if keys.get("strategy_key") == strategy:
                score_match += 3
            if keys.get("symbol") == symbol:
                score_match += 3
            if keys.get("market_regime") == regime:
                score_match += 2
            if keys.get("trade_pattern") == pattern:
                score_match += 2
            if keys.get("volume_condition") == volume_condition:
                score_match += 1
            if score_match >= 3:
                similar.append({**row, "_match": score_match})

        similar.sort(key=lambda r: r.get("_match", 0), reverse=True)
        similar = similar[:40]
        similar_count = len(similar)
        nets = [_dec(r.get("net_after_costs")) for r in similar]
        wins = sum(1 for n in nets if n > 0)
        win_rate = (
            Decimal(wins) / Decimal(similar_count) if similar_count else None
        )
        expectancy = (
            sum(nets, Decimal("0")) / Decimal(similar_count) if similar_count else None
        )

        # Strategy+regime slice regardless of symbol.
        strat_regime = [
            r
            for r in knowledge
            if (r.get("keys") or {}).get("strategy_key") == strategy
            and (r.get("keys") or {}).get("market_regime") == regime
        ]
        sr_nets = [_dec(r.get("net_after_costs")) for r in strat_regime]
        strategy_regime_expectancy = (
            sum(sr_nets, Decimal("0")) / Decimal(len(sr_nets)) if sr_nets else None
        )

        evidence_strength = "none"
        if similar_count >= 12:
            evidence_strength = "strong"
        elif similar_count >= 5:
            evidence_strength = "moderate"
        elif similar_count >= 2:
            evidence_strength = "thin"

        delta = paper_confidence_delta or Decimal("0")
        delta = max(ADAPTIVE_DELTA_MIN, min(ADAPTIVE_DELTA_MAX, delta))
        learned_adj = float(delta)
        if expectancy is not None and similar_count >= 3:
            if expectancy > Decimal("0.25"):
                learned_adj += 4
            elif expectancy < WEAK_EXPECTANCY:
                learned_adj -= 8
        if strategy_regime_expectancy is not None and len(sr_nets) >= 5:
            if strategy_regime_expectancy < WEAK_EXPECTANCY:
                learned_adj -= 6
            elif strategy_regime_expectancy > Decimal("0.25"):
                learned_adj += 3

        base = float(confidence_label_score) if confidence_label_score is not None else float(base_score)
        learned_score = Decimal(str(round(max(0.0, min(100.0, base + learned_adj)), 2)))

        action = "WAIT"
        if (
            similar_count >= MIN_EVIDENCE_FOR_HARD_AVOID
            and expectancy is not None
            and expectancy < WEAK_EXPECTANCY
        ):
            action = "AVOID"
        elif learned_score >= EXECUTE_SCORE:
            action = "EXECUTE"
        elif learned_score < WAIT_SCORE:
            action = "AVOID"
        else:
            action = "WAIT"

        prior_ids = [r["review_id"] for r in similar[:8] if r.get("review_id")]
        return {
            "action": action,
            "learned_opportunity_score": str(learned_score),
            "base_score": str(round(base, 2)),
            "learned_confidence_adjustment": str(round(learned_adj, 2)),
            "similar_setup_count": similar_count,
            "historical_win_rate": str(win_rate) if win_rate is not None else None,
            "expectancy_after_costs": str(expectancy) if expectancy is not None else None,
            "strategy_regime_expectancy": (
                str(strategy_regime_expectancy)
                if strategy_regime_expectancy is not None
                else None
            ),
            "evidence_strength": evidence_strength,
            "prior_review_ids": prior_ids,
            "influenced": similar_count > 0 or abs(float(delta)) > 0,
            "paper_only": True,
            "live_trading_enabled": False,
        }
