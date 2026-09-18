"""Paper Training Lab — coaching / automatic practice for simulated trades only.

Never unlocks live trading. Automatic entries still go through paper risk checks,
pause-new-entries, and kill switch.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.market_intelligence import MarketInstrument, MarketOhlcvBar
from app.models.market_scan import MarketScanCandidate
from app.models.paper_trading import PaperOrder, PaperPortfolio, PaperPosition
from app.models.paper_training import (
    PaperCoachingDecision,
    PaperTradeFeedback,
    PaperTrainingSettings,
)
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal
from app.services.paper_trading_service import (
    PAPER_MARK_STALE_AFTER,
    PaperTradingError,
    PaperTradingService,
)
from app.services.plain_language import (
    BIAS_PLAIN,
    STAGE_PLAIN,
    confidence_from_score,
    plain_rejection,
    readiness_action,
)

MIN_BARS = 25
# Match anticipated live connected-account size for Founder learning.
FOUNDER_LEARNING_DESK_NAME = "Founder Learning Desk"
LEARNING_STARTING_CASH = Decimal("300")
# Sweet spot: meaningful per-trade size, but never drain cash available.
# ~$100 on a $300 book (≈1/3) — reserve gate stops a fully locked desk.
LEARNING_DEFAULT_NOTIONAL = Decimal("100")
# Cap per-entry size so organic compound never becomes a single-bet gamble.
LEARNING_MAX_NOTIONAL = Decimal("150")
# Target ~1/3 of equity per entry (matches $100 on $300 start).
LEARNING_NOTIONAL_EQUITY_FRACTION = Decimal("0.33")
# Keep ≥40% of equity as free cash (floor $100) so the desk grows
# *available* cash for redeploy / other uses — not just mark-to-market equity.
LEARNING_CASH_RESERVE_FRACTION = Decimal("0.40")
LEARNING_MIN_CASH_RESERVE = Decimal("100")
# Hard ceiling on capital sitting in open positions vs equity.
LEARNING_MAX_DEPLOYED_FRACTION = Decimal("0.55")
# Legacy practice size that produced ~$0.25 days; auto-upgraded when cash allows.
LEGACY_TINY_NOTIONAL = Decimal("30")
# Dig-out: keep trading with remaining cash (never invents capital).
MIN_DIG_OUT_CASH = Decimal("5")
DIG_OUT_NOTIONAL_FRACTION = Decimal("0.25")  # up to 25% of remaining buying power
# Take-profit must clear at least this reward:risk multiple of stop distance.
MIN_TAKE_PROFIT_R = Decimal("2")
# Floor stop distance so 2R targets cannot collapse into micro-scalps.
MIN_STOP_DISTANCE_PCT = Decimal("0.015")  # 1.5%
# At the standard $100 size, require $3 planned reward. Organic sizing can
# safely step down while rebuilding cash, so scale the floor with notional
# while never accepting less than $1 of planned upside.
MIN_EXPECTED_REWARD_USD = Decimal("3")
MIN_SCALED_EXPECTED_REWARD_USD = Decimal("1")
# Do not take-profit a brand-new entry in the same automation pass.
TAKE_PROFIT_MIN_HOLD_SECONDS = 120
# Founder desk: bank half the position at +1R so cash frees for dips
# while the runner can still seek the full take-profit.
SCALE_OUT_R = Decimal("1")
SCALE_OUT_HOLD_SECONDS = 180
SCALE_OUT_FRACTION = Decimal("0.5")
# After partial bank, close the runner at +1.5R so the $300 desk recycles
# instead of sitting full until a distant 2R target (paper only).
RUNNER_BANK_R = Decimal("1.5")
RUNNER_BANK_HOLD_SECONDS = 600
# Stale green: held a long time with modest progress — free the slot.
STALE_BANK_R = Decimal("0.75")
STALE_BANK_HOLD_SECONDS = 14400  # 4 hours
MICRO_MAX_HOLD_SECONDS = 14400  # 4 hours; recycle if the micro thesis did not resolve
# Founder primaries can also freeze a slot (ETHFI-class deadlock). Same recycle.
FOUNDER_MAX_HOLD_SECONDS = 14400
# Time-exits may use a last public close older than the 8m stop/target mark.
TIME_EXIT_MARK_MAX_AGE = timedelta(hours=24)
MICRO_MIN_TAKE_PROFIT_R = Decimal("1.5")
MICRO_COST_BPS_RT = Decimal("6")
MICRO_MIN_NET_REWARD_USD = Decimal("0.75")
STRATEGY_EXPLORATION_SAMPLE = 5
# Desk must beat idle cash before digging deeper on a red day.
DESK_CASH_BENCHMARK_MIN_TRADES = 10
ENTRY_CANDIDATE_MAX_AGE = PAPER_MARK_STALE_AFTER


def candidate_market_data_is_fresh(
    *,
    evaluated_at: datetime | None,
    market_data_at: datetime | None,
    now: datetime,
) -> bool:
    cutoff = now - ENTRY_CANDIDATE_MAX_AGE
    return bool(
        evaluated_at is not None
        and evaluated_at >= cutoff
        and market_data_at is not None
        and market_data_at >= cutoff
    )


def strategy_loses_to_cash(
    *, trades: int, expectancy_after_costs: Decimal | None
) -> bool:
    """True when a sampled strategy's net expectancy fails to beat idle cash (0)."""
    return (
        trades >= STRATEGY_EXPLORATION_SAMPLE
        and expectancy_after_costs is not None
        and expectancy_after_costs <= 0
    )


def desk_should_sit_vs_cash(
    *,
    closed_trades: int,
    total_pnl: Decimal | None,
    today_equity_pnl: Decimal | None,
    open_positions: int = 0,
) -> bool:
    """Capital-preservation brake: do not add to a red book that is already behind cash.

    Idle cash has ~0 expectancy. If the Founder desk is underwater after reseeds,
    today is also red, and risk is still on, new entries pause. Once the book is
    flat, sitting forever cannot beat cash — allow a new attempt (EGA sizing and
    strategy filters still apply).
    """
    if int(open_positions or 0) <= 0:
        return False
    if closed_trades < DESK_CASH_BENCHMARK_MIN_TRADES:
        return False
    if total_pnl is None or total_pnl > 0:
        return False
    if today_equity_pnl is None:
        return closed_trades >= 20 and total_pnl < 0
    return today_equity_pnl < 0


def strategy_portfolio_priority_adjustment(
    *, trades: int, expectancy_after_costs: Decimal | None
) -> float:
    """Balance controlled strategy exploration with proven net expectancy.

    Untested strategies receive a bounded exploration boost. Sampled strategies
    that lose to cash are hard-blocked elsewhere; this penalty still demotes
    them in ranking if they somehow reach the candidate pool.
    """
    if trades < STRATEGY_EXPLORATION_SAMPLE:
        return float((STRATEGY_EXPLORATION_SAMPLE - max(0, trades)) * 3)
    if expectancy_after_costs is None:
        return 0.0
    if expectancy_after_costs > 0:
        return min(15.0, float(expectancy_after_costs * Decimal("3")))
    # Losing to cash: heavy demotion (entry loop also hard-skips these).
    loss_penalty = Decimal("25") + min(
        Decimal("40"), abs(expectancy_after_costs) * Decimal("40")
    )
    evidence_penalty = min(Decimal("20"), Decimal(trades) / Decimal("5"))
    return -float(loss_penalty + evidence_penalty)


def cash_reserve_target(*, equity: Decimal) -> Decimal:
    """Minimum free cash the Founder desk should keep uninvested."""
    if equity <= 0:
        return LEARNING_MIN_CASH_RESERVE
    pct = (equity * LEARNING_CASH_RESERVE_FRACTION).quantize(Decimal("0.01"))
    return max(LEARNING_MIN_CASH_RESERVE, pct)


def organic_entry_notional(*, equity: Decimal, buying_power: Decimal) -> Decimal:
    """Size for organic growth: ~1/3 equity, never breach cash reserve.

    Steps size up as the book grows and down when cash is thin — paper only.
    Returns 0 when a new entry would violate the liquidity sweet spot.
    """
    if equity <= 0 or buying_power <= 0:
        return Decimal("0")
    reserve = cash_reserve_target(equity=equity)
    deployable = (buying_power - reserve).quantize(Decimal("0.01"))
    if deployable < MIN_DIG_OUT_CASH:
        return Decimal("0")
    invested = max(Decimal("0"), equity - buying_power)
    if equity > 0 and (invested / equity) >= LEARNING_MAX_DEPLOYED_FRACTION:
        return Decimal("0")
    target = (equity * LEARNING_NOTIONAL_EQUITY_FRACTION).quantize(Decimal("0.01"))
    target = max(MIN_DIG_OUT_CASH, min(target, LEARNING_MAX_NOTIONAL))
    return min(target, deployable).quantize(Decimal("0.01"))


def organic_growth_pace(
    *,
    starting_cash: Decimal,
    equity: Decimal,
    closed_trades: int,
    max_dd: Decimal | None,
    cash_available: Decimal | None = None,
) -> dict[str, Any]:
    """Honest growth lane — milestones, not get-rich promises."""
    net = (equity - starting_cash).quantize(Decimal("0.01"))
    pct = (
        ((equity - starting_cash) / starting_cash * Decimal("100")).quantize(
            Decimal("0.1")
        )
        if starting_cash > 0
        else Decimal("0")
    )
    reserve = cash_reserve_target(equity=equity)
    cash = (
        cash_available.quantize(Decimal("0.01"))
        if cash_available is not None
        else None
    )
    liquidity_ok = cash is None or cash >= reserve
    # Checkpoints assume steady paper practice, not calendar miracles.
    if cash is not None and cash < reserve and equity >= LEARNING_MIN_CASH_RESERVE:
        lane = "rebuild_liquidity"
        guide = (
            f"Cash available ${cash} is below the ~{int(LEARNING_CASH_RESERVE_FRACTION * 100)}% "
            f"liquidity target (${reserve}). Bank winners / free slots before "
            "new size — grow free cash, not just equity marks."
        )
    elif closed_trades < 5:
        lane = "building_sample"
        guide = (
            "Organic growth needs a sample first — aim for 5+ closed paper trades "
            "before judging the curve."
        )
    elif max_dd is not None and starting_cash > 0 and max_dd > starting_cash * Decimal(
        "0.25"
    ):
        lane = "protect"
        guide = (
            "Drawdown is large vs starting cash — prioritize capital preservation "
            "over faster growth."
        )
    elif pct >= Decimal("25") and closed_trades < 20:
        lane = "too_fast_review"
        guide = (
            "Equity jumped quickly on a small sample — treat as luck until more "
            "trades confirm expectancy. Do not size up aggressively."
        )
    elif net > 0:
        lane = "organic"
        guide = (
            "Healthy lane: keep ~40%+ as cash available, invest a measured slice, "
            "bank partial winners, redeploy into dips. Grow free cash and equity "
            "together — not day-to-day doubles."
        )
    elif net < 0:
        lane = "recovery"
        guide = (
            "Below start — cut risk, keep exits honest, rebuild with high-quality "
            "setups only."
        )
    else:
        lane = "flat"
        guide = "Flat vs start — focus on expectancy and clean exits before growing size."
    return {
        "starting_cash": starting_cash,
        "equity": equity.quantize(Decimal("0.01")),
        "cash_available": cash,
        "cash_reserve_target": reserve,
        "liquidity_ok": liquidity_ok,
        "net_vs_start": net,
        "growth_pct": pct,
        "lane": lane,
        "guide": guide,
        "checkpoints": {
            "after_20_trades": "Seek positive expectancy after costs (not a $ target).",
            "after_40_trades": "Equity above start with drawdown under ~15% of start.",
            "liquidity": (
                f"Keep ≥{int(LEARNING_CASH_RESERVE_FRACTION * 100)}% equity "
                f"(min ${LEARNING_MIN_CASH_RESERVE}) as cash available."
            ),
            "never": "Do not chase +50% in a few days — that trains gambling.",
        },
        "disclaimer": (
            "Paper only. These lanes guide learning pace; they do not promise profit "
            "or unlock live trading."
        ),
    }


def normalize_exit_levels(
    price: Decimal,
    stop: Decimal | None,
    target: Decimal | None,
    *,
    min_stop_pct: Decimal = MIN_STOP_DISTANCE_PCT,
    min_r: Decimal = MIN_TAKE_PROFIT_R,
) -> tuple[Decimal, Decimal]:
    """Widen microscopic stops and enforce a minimum reward:risk target."""
    if price <= 0:
        raise ValueError("price must be positive")
    min_risk = price * min_stop_pct
    if stop is None or stop >= price:
        stop = price - min_risk
    else:
        risk = price - stop
        if risk < min_risk:
            stop = price - min_risk
    risk = price - stop
    if risk <= 0:
        stop = price - min_risk
        risk = min_risk
    min_target = price + (risk * min_r)
    if target is None or target < min_target:
        target = min_target
    return stop, target


def expected_reward_usd(
    *, price: Decimal, target: Decimal, notional: Decimal
) -> Decimal:
    """Dollar reward implied by notional at the planned take-profit."""
    if price <= 0 or notional <= 0 or target <= price:
        return Decimal("0")
    return (notional * ((target - price) / price)).quantize(Decimal("0.01"))


def expected_reward_floor_usd(
    *, notional: Decimal, strategy_key: str | None = None
) -> Decimal:
    """Meaningful reward floor proportional to governed organic sizing."""
    if notional <= 0:
        return MIN_EXPECTED_REWARD_USD
    if strategy_key in {"range_micro", "trend_pullback_micro"}:
        scaled_micro = (
            Decimal("1.50") * notional / LEARNING_DEFAULT_NOTIONAL
        ).quantize(Decimal("0.01"))
        return max(MICRO_MIN_NET_REWARD_USD, scaled_micro)
    scaled = (
        MIN_EXPECTED_REWARD_USD * notional / LEARNING_DEFAULT_NOTIONAL
    ).quantize(Decimal("0.01"))
    return min(
        MIN_EXPECTED_REWARD_USD,
        max(MIN_SCALED_EXPECTED_REWARD_USD, scaled),
    )


FEEDBACK_CODES = {
    "good_decision",
    "bad_decision",
    "entered_too_early",
    "entered_too_late",
    "exited_too_early",
    "exited_too_late",
    "risk_too_high",
    "position_too_small",
    "position_too_large",
    "agree_rejection",
    "disagree_rejection",
    "personal_note",
}


class PaperTrainingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class PaperTrainingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.paper = PaperTradingService(db)

    def get_or_create_settings(self, portfolio_id: uuid.UUID) -> PaperTrainingSettings:
        row = self.db.scalar(
            select(PaperTrainingSettings).where(
                PaperTrainingSettings.portfolio_id == portfolio_id
            )
        )
        if row:
            return row
        row = PaperTrainingSettings(
            portfolio_id=portfolio_id,
            mode="coaching",
            default_notional=LEARNING_DEFAULT_NOTIONAL,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def set_mode(
        self,
        portfolio_id: uuid.UUID,
        *,
        mode: str,
        actor: AuthenticatedPrincipal,
        default_notional: Decimal | None = None,
    ) -> PaperTrainingSettings:
        if mode not in {"automatic", "coaching"}:
            raise PaperTrainingError("invalid_mode", "Mode must be automatic or coaching")
        row = self.get_or_create_settings(portfolio_id)
        row.mode = mode
        if default_notional is not None:
            if default_notional <= 0:
                raise PaperTrainingError("invalid_notional", "Paper investment must be positive")
            row.default_notional = default_notional
        self.audit.append(
            action="paper.training.mode",
            resource_type="paper_training_settings",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"mode": mode, "default_notional": str(row.default_notional)},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def candle_readiness(self) -> list[dict[str, Any]]:
        instruments = list(
            self.db.scalars(
                select(MarketInstrument)
                .where(MarketInstrument.is_active.is_(True))
                .order_by(MarketInstrument.symbol.asc())
            )
        )
        rows: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        for inst in instruments:
            bar_count = self.db.scalar(
                select(func.count())
                .select_from(MarketOhlcvBar)
                .where(MarketOhlcvBar.instrument_id == inst.id)
            ) or 0
            latest = self.db.scalar(
                select(MarketOhlcvBar)
                .where(MarketOhlcvBar.instrument_id == inst.id)
                .order_by(desc(MarketOhlcvBar.close_time))
                .limit(1)
            )
            age_sec = None
            stale = True
            if latest is not None:
                age_sec = int((now - latest.close_time).total_seconds())
                stale = age_sec > 6 * 3600
            ready = bar_count >= MIN_BARS and not stale
            rows.append(
                {
                    "symbol": inst.symbol,
                    "bar_count": int(bar_count),
                    "min_required": MIN_BARS,
                    "latest_close_time": latest.close_time if latest else None,
                    "latest_close": latest.close if latest else None,
                    "age_seconds": age_sec,
                    "stale": stale if latest else True,
                    "ready": ready,
                    "next_step": readiness_action(
                        bar_count=int(bar_count),
                        min_bars=MIN_BARS,
                        stale=bool(stale if latest else True),
                        has_instrument=True,
                    ),
                }
            )
        if not rows:
            rows.append(
                {
                    "symbol": None,
                    "bar_count": 0,
                    "min_required": MIN_BARS,
                    "latest_close_time": None,
                    "latest_close": None,
                    "age_seconds": None,
                    "stale": True,
                    "ready": False,
                    "next_step": readiness_action(
                        bar_count=0, min_bars=MIN_BARS, stale=True, has_instrument=False
                    ),
                }
            )
        return rows

    def founder_candidate(self, cand: MarketScanCandidate) -> dict[str, Any]:
        score = float(cand.score)
        price = cand.current_price
        stop = cand.stop_loss
        target = cand.take_profit
        planned_risk = None
        planned_reward = None
        if price is not None and stop is not None:
            planned_risk = abs(price - stop)
        if price is not None and target is not None:
            planned_reward = abs(target - price)
        return {
            "id": cand.id,
            "symbol": cand.symbol,
            "outlook": BIAS_PLAIN.get(cand.bias, cand.bias),
            "bias": cand.bias,
            "current_price": price,
            "confidence": confidence_from_score(score),
            "score": cand.score,
            "stage": STAGE_PLAIN.get(cand.stage, cand.stage),
            "stage_raw": cand.stage,
            "decision": self._decision_label(cand.stage),
            "why": plain_rejection(cand.reason_code, cand.reason_text),
            "reason_code": cand.reason_code,
            "waiting_for": self._waiting_for(cand),
            "entry_zone": cand.entry_zone,
            "stop_loss": stop,
            "take_profit": target,
            "planned_risk_per_unit": planned_risk,
            "planned_reward_per_unit": planned_reward,
            "timeframe": cand.timeframe,
            "strategy_key": cand.strategy_key,
            "risk_status": cand.risk_status,
            "evaluated_at": cand.evaluated_at,
            "market_data_at": cand.market_data_at,
        }

    def _decision_label(self, stage: str) -> str:
        if stage in {"Watching", "Evaluating"}:
            return "Watching"
        if stage == "Risk Review":
            return "Ready"
        if stage == "Approved":
            return "Ready"
        if stage == "Entered":
            return "Ready"
        if stage == "Expired":
            return "Expired"
        return "Rejected"

    def _waiting_for(self, cand: MarketScanCandidate) -> str:
        if cand.stage == "Rejected":
            return "Nothing — this idea was skipped."
        if cand.reason_code == "insufficient_history":
            return "More recent price history."
        if cand.stage == "Watching":
            return "One more confirming price update before a paper entry is considered."
        if cand.stage == "Risk Review":
            return "Risk checks or Founder coaching approval."
        return "Argus is still evaluating."

    def coaching_take(
        self,
        *,
        portfolio_id: uuid.UUID,
        candidate_id: uuid.UUID,
        actor: AuthenticatedPrincipal,
        note: str | None = None,
    ) -> dict[str, Any]:
        settings = self.get_or_create_settings(portfolio_id)
        cand = self.db.get(MarketScanCandidate, candidate_id)
        if cand is None:
            raise PaperTrainingError("candidate_missing", "That trade idea was not found.")
        if cand.stage == "Rejected":
            raise PaperTrainingError(
                "candidate_rejected",
                "This idea was already rejected. Teaching feedback can still be saved.",
            )
        order = self._open_paper_from_candidate(
            portfolio_id=portfolio_id,
            cand=cand,
            notional=settings.default_notional,
            actor=actor,
        )
        decision = PaperCoachingDecision(
            portfolio_id=portfolio_id,
            candidate_id=cand.id,
            symbol=cand.symbol,
            action="take",
            note=note,
            resulting_order_id=order.id,
            actor_user_id=actor.user.id,
            detail={
                "mode": settings.mode,
                "stop_loss": str(cand.stop_loss) if cand.stop_loss is not None else None,
                "take_profit": (
                    str(cand.take_profit) if cand.take_profit is not None else None
                ),
            },
        )
        self.db.add(decision)
        cand.stage = "Entered"
        self.audit.append(
            action="paper.training.coaching_take",
            resource_type="paper_order",
            resource_id=str(order.id),
            actor_user_id=actor.user.id,
            payload={"symbol": cand.symbol, "candidate_id": str(cand.id)},
        )
        self.db.commit()
        return {"order_id": order.id, "decision_id": decision.id, "symbol": cand.symbol}

    def coaching_skip(
        self,
        *,
        portfolio_id: uuid.UUID,
        candidate_id: uuid.UUID,
        actor: AuthenticatedPrincipal,
        note: str | None = None,
    ) -> dict[str, Any]:
        cand = self.db.get(MarketScanCandidate, candidate_id)
        if cand is None:
            raise PaperTrainingError("candidate_missing", "That trade idea was not found.")
        decision = PaperCoachingDecision(
            portfolio_id=portfolio_id,
            candidate_id=cand.id,
            symbol=cand.symbol,
            action="skip",
            note=note,
            actor_user_id=actor.user.id,
            detail={},
        )
        self.db.add(decision)
        cand.stage = "Expired"
        self.audit.append(
            action="paper.training.coaching_skip",
            resource_type="market_scan_candidate",
            resource_id=str(cand.id),
            actor_user_id=actor.user.id,
            payload={"symbol": cand.symbol},
        )
        self.db.commit()
        return {"decision_id": decision.id, "symbol": cand.symbol}

    def record_feedback(
        self,
        *,
        portfolio_id: uuid.UUID,
        actor: AuthenticatedPrincipal,
        feedback_code: str,
        symbol: str,
        fill_id: uuid.UUID | None = None,
        candidate_id: uuid.UUID | None = None,
        note: str | None = None,
        strategy_key: str | None = None,
    ) -> PaperTradeFeedback:
        if feedback_code not in FEEDBACK_CODES:
            raise PaperTrainingError(
                "invalid_feedback",
                "Unknown feedback choice.",
            )
        row = PaperTradeFeedback(
            portfolio_id=portfolio_id,
            fill_id=fill_id,
            candidate_id=candidate_id,
            symbol=symbol.upper(),
            feedback_code=feedback_code,
            note=note,
            strategy_key=strategy_key,
            actor_user_id=actor.user.id,
            detail={},
        )
        self.db.add(row)
        self.audit.append(
            action="paper.training.feedback",
            resource_type="paper_trade_feedback",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={
                "feedback_code": feedback_code,
                "symbol": symbol.upper(),
                "fill_id": str(fill_id) if fill_id else None,
            },
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def scorecard(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        closed = self.paper.list_closed_trades(portfolio_id, limit=200)
        pnls = [Decimal(str(t["realized_pnl"])) for t in closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        feedback_count = self.db.scalar(
            select(func.count())
            .select_from(PaperTradeFeedback)
            .where(PaperTradeFeedback.portfolio_id == portfolio_id)
        ) or 0
        total_pnl = sum(pnls, Decimal("0"))
        win_rate = (Decimal(len(wins)) / Decimal(len(pnls))) if pnls else None
        avg_win = (sum(wins, Decimal("0")) / Decimal(len(wins))) if wins else None
        avg_loss = (sum(losses, Decimal("0")) / Decimal(len(losses))) if losses else None
        gross_wins = sum(wins, Decimal("0"))
        gross_losses = abs(sum(losses, Decimal("0")))
        profit_factor = (
            (gross_wins / gross_losses) if gross_losses > 0 else None
        )
        # Simple drawdown proxy from cumulative closed PnL path
        equity = Decimal("0")
        peak = Decimal("0")
        max_dd = Decimal("0")
        chrono = list(reversed(pnls))
        for p in chrono:
            equity += p
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        portfolio = self.db.get(PaperPortfolio, portfolio_id)
        starting = LEARNING_STARTING_CASH
        equity_now = LEARNING_STARTING_CASH
        cash_now: Decimal | None = None
        account_total_pnl = total_pnl
        if portfolio is not None:
            try:
                summary = self.paper.portfolio_summary(portfolio_id)
                starting = Decimal(str(summary.get("starting_cash") or starting))
                equity_now = Decimal(
                    str(summary.get("total_account_value") or portfolio.cash_balance)
                )
                cash_now = Decimal(
                    str(
                        portfolio.cash_balance
                        - (portfolio.reserved_cash or Decimal("0"))
                    )
                )
                account_total_pnl = Decimal(
                    str(summary.get("total_pnl") or Decimal("0"))
                )
            except Exception:  # noqa: BLE001
                equity_now = Decimal(str(portfolio.cash_balance or starting))
                cash_now = Decimal(str(portfolio.cash_balance or 0))
                starting = LEARNING_STARTING_CASH
        growth = organic_growth_pace(
            starting_cash=starting,
            equity=equity_now,
            closed_trades=len(pnls),
            max_dd=max_dd if pnls else None,
            cash_available=cash_now,
        )
        from app.services.equity_growth_algorithm import plan_equity_growth

        ega = plan_equity_growth(
            starting_cash=starting,
            equity=equity_now,
            buying_power=cash_now if cash_now is not None else Decimal("0"),
            closed_trades=len(pnls),
            max_dd=max_dd if pnls else None,
            total_pnl=account_total_pnl,
        )
        readiness = self._live_readiness(
            closed_count=len(pnls),
            win_rate=win_rate,
            feedback_count=int(feedback_count),
            max_dd=max_dd,
            profit_factor=profit_factor,
            total_pnl=account_total_pnl,
        )
        return {
            "paper_trades_completed": len(pnls),
            "win_rate": win_rate,
            "total_paper_pnl": account_total_pnl,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "profit_factor": profit_factor,
            "maximum_drawdown": max_dd if pnls else None,
            "trades_with_founder_feedback": int(feedback_count),
            "live_readiness": readiness["status"],
            "live_readiness_detail": readiness["detail"],
            "organic_growth": growth,
            "equity_growth_algorithm": ega,
            "disclaimer": (
                "Paper results are simulated. Live readiness never unlocks live trading."
            ),
        }

    def _live_readiness(
        self,
        *,
        closed_count: int,
        win_rate: Decimal | None,
        feedback_count: int,
        max_dd: Decimal,
        profit_factor: Decimal | None,
        total_pnl: Decimal | None = None,
    ) -> dict[str, str]:
        if closed_count < 5:
            return {
                "status": "Not Enough Evidence",
                "detail": "Complete at least 5 closed paper trades before judging consistency.",
            }
        if closed_count < 20:
            return {
                "status": "Early Testing",
                "detail": (
                    "Paper training continues — no calendar cutoff. Keep practicing "
                    "until results are consistently profitable and stable. Live stays locked."
                ),
            }
        issues = []
        if total_pnl is not None and total_pnl <= 0:
            issues.append(
                "account equity has not grown after costs and paper cash reseeds"
            )
        if win_rate is not None and win_rate < Decimal("0.4"):
            issues.append("win rate below 40%")
        if profit_factor is not None and profit_factor < Decimal("1"):
            issues.append("losses outweigh wins")
        if max_dd > Decimal("500"):
            issues.append("drawdown is large for this paper size")
        if feedback_count < 5:
            issues.append("few Founder feedback notes")
        if issues:
            return {
                "status": "Needs Improvement",
                "detail": "Issues: " + "; ".join(issues) + ". Paper continues until fixed.",
            }
        if (
            closed_count >= 40
            and feedback_count >= 15
            and profit_factor is not None
            and profit_factor >= Decimal("1.2")
            and win_rate is not None
            and win_rate >= Decimal("0.45")
            and total_pnl is not None
            and total_pnl > 0
        ):
            return {
                "status": "Eligible for Formal Live Review",
                "detail": (
                    "Paper evidence looks substantial and profitable. Live trading still "
                    "requires the existing formal authorization path — this status does "
                    "not unlock it. Paper practice continues until Founder certifies."
                ),
            }
        return {
            "status": "Consistent in Paper",
            "detail": (
                "Paper results look steadier. Continue Automatic Practice until "
                "profitability and bug stability are proven. Live remains locked."
            ),
        }

    def iter_automation_portfolio_ids(self) -> list[uuid.UUID]:
        """Portfolios that must receive stop/target exits and/or auto-entry.

        Never use ``select(PaperPortfolio).limit(N)`` — fixture books created
        earlier starve the Founder's live paper book from automation (stops
        never fire; automatic mode never enters).
        """
        open_ids = set(
            self.db.scalars(
                select(PaperPosition.portfolio_id).where(PaperPosition.quantity != 0)
            ).all()
        )
        auto_ids = set(
            self.db.scalars(
                select(PaperTrainingSettings.portfolio_id).where(
                    PaperTrainingSettings.mode == "automatic"
                )
            ).all()
        )
        return list(open_ids | auto_ids)

    def maybe_auto_enter_from_scan(
        self,
        *,
        portfolio_id: uuid.UUID,
        actor: AuthenticatedPrincipal | None,
        allowed_strategy_keys: set[str] | None = None,
        excluded_strategy_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """If Automatic Practice is on, enter clear Watching candidates (paper only)."""
        settings = self.get_or_create_settings(portfolio_id)
        if settings.mode != "automatic":
            return []
        # General and dedicated Micro workers may wake together. Serialize each
        # portfolio's entry decision so cash/slot checks cannot race.
        portfolio = self.db.scalar(
            select(PaperPortfolio)
            .where(PaperPortfolio.id == portfolio_id)
            .with_for_update(skip_locked=True)
        )
        if portfolio is None or portfolio.kill_switch_active or portfolio.pause_new_entries_active:
            return []
        # Fixture/test books left on "automatic" flooded the worker (75+ Train
        # positions) and exhausted the Founder desk. New entries are Founder-only.
        if (portfolio.name or "") != FOUNDER_LEARNING_DESK_NAME:
            return []
        # Do not grind a depleted learning desk — size down to remaining cash
        # instead of refusing all entries (empty books destroy expectancy learning).
        buying_power = portfolio.cash_balance - (portfolio.reserved_cash or Decimal("0"))
        total_pnl: Decimal | None = None
        starting_cash = LEARNING_STARTING_CASH
        try:
            summary = self.paper.portfolio_summary(portfolio_id)
            equity = Decimal(
                str(summary.get("total_account_value") or buying_power)
            )
            raw_total = summary.get("total_pnl")
            if raw_total is not None:
                total_pnl = Decimal(str(raw_total))
            starting_cash = Decimal(
                str(summary.get("starting_cash") or starting_cash)
            )
        except Exception:  # noqa: BLE001
            equity = buying_power

        from app.services.equity_growth_algorithm import (
            equity_growth_entry_notional,
            plan_equity_growth,
            strategy_eligible_for_growth,
        )

        closed_n = len(self.paper.list_closed_trades(portfolio_id, limit=200))
        ega_plan = plan_equity_growth(
            starting_cash=starting_cash,
            equity=equity,
            buying_power=buying_power,
            closed_trades=closed_n,
            max_dd=None,
            total_pnl=total_pnl,
        )
        ega_lane = str(ega_plan.get("lane") or "flat")
        # EGA owns deploy size when trading is allowed; reserve floors still win.
        entry_notional = Decimal(str(ega_plan.get("base_entry_notional") or 0))
        reserve = cash_reserve_target(equity=equity)
        if entry_notional <= 0:
            # Distinguish liquidity rebuild vs genuine reserve hold.
            reason = (
                "ega_lane_hold"
                if ega_lane in {"rebuild_liquidity", "protect"}
                and buying_power >= reserve
                else "cash_reserve_hold"
            )
            self._emit_decision_event(
                symbol="*",
                outcome="info",
                title=(
                    "EGA holding cash — growth lane pause"
                    if reason == "ega_lane_hold"
                    else "Holding cash available — liquidity target"
                ),
                detail=(
                    f"EGA lane={ega_lane}; cash available ${buying_power:.2f}; "
                    f"reserve ${reserve:.2f}; equity ${equity:.2f}. "
                    "New entries pause; exits still run. Paper only."
                ),
                reason_code=reason,
            )
            return []
        if buying_power < MIN_DIG_OUT_CASH:
            self._emit_decision_event(
                symbol="*",
                outcome="info",
                title="Paper capital too low for new entries",
                detail=(
                    f"Cash available is ${buying_power:.2f}; automatic entries need "
                    f"at least ${MIN_DIG_OUT_CASH:.2f}. "
                    "Open positions can still exit. "
                    "Use Reseed learning desk to restore $300 practice cash."
                ),
                reason_code="insufficient_paper_cash",
            )
            return []
        if settings.default_notional != entry_notional:
            prev = settings.default_notional
            settings.default_notional = entry_notional
            self.db.commit()
            if entry_notional > prev:
                self._emit_decision_event(
                    symbol="*",
                    outcome="info",
                    title="EGA size stepped up with equity lane",
                    detail=(
                        f"Equity Growth Algorithm: entries now ${entry_notional:.2f} "
                        f"(lane={ega_lane}, equity ${equity:.2f}, reserve "
                        f"${reserve:.2f}). Paper only."
                    ),
                    reason_code="ega_size_up",
                )
            elif entry_notional < prev:
                self._emit_decision_event(
                    symbol="*",
                    outcome="info",
                    title="EGA size reduced for capital preservation",
                    detail=(
                        f"Lane={ega_lane}; buying power ${buying_power:.2f}; "
                        f"reserve ${reserve:.2f}; entries now ${entry_notional:.2f} "
                        "(paper only)."
                    ),
                    reason_code="ega_size_down",
                )
        # Cap concurrent Founder risk — EGA tightens while underwater/protecting.
        max_open = int(ega_plan.get("max_open_positions") or 2)
        open_count = self.db.scalar(
            select(func.count())
            .select_from(PaperPosition)
            .where(
                PaperPosition.portfolio_id == portfolio_id,
                PaperPosition.quantity != 0,
            )
        ) or 0
        if int(open_count) >= max_open:
            self._emit_decision_event(
                symbol="*",
                outcome="info",
                title="Paper book full — waiting for exits",
                detail=(
                    f"{int(open_count)} open paper positions (EGA max {max_open}, "
                    f"lane={ega_lane}). "
                    "New entries pause until a position closes; exits still run."
                ),
                reason_code="max_open_positions",
            )
            return []

        # Beat idle cash / HODL: do not add to a red underwater book. If already
        # flat, the desk is idle cash — blocking entries until midnight is a deadlock.
        today_equity_pnl: Decimal | None = None
        try:
            day_eq = self.paper.day_equity_pnl(portfolio_id)
            raw_day = day_eq.get("today_equity_pnl")
            if raw_day is not None:
                today_equity_pnl = Decimal(str(raw_day))
        except Exception:  # noqa: BLE001
            today_equity_pnl = None
        if desk_should_sit_vs_cash(
            closed_trades=closed_n,
            total_pnl=total_pnl,
            today_equity_pnl=today_equity_pnl,
            open_positions=int(open_count),
        ):
            day_txt = (
                f"${today_equity_pnl:+.2f}"
                if today_equity_pnl is not None
                else "unavailable"
            )
            tot_txt = f"${total_pnl:+.2f}" if total_pnl is not None else "n/a"
            self._emit_decision_event(
                symbol="*",
                outcome="info",
                title="Sitting in cash — losing to idle hold",
                detail=(
                    f"Total P/L {tot_txt} after reseeds; today's equity P/L "
                    f"{day_txt}; {int(open_count)} open. Not adding risk until "
                    "exits flatten the book or the day turns. Paper only."
                ),
                reason_code="sit_in_cash_vs_hodl",
            )
            return []

        opened: list[dict[str, Any]] = []
        # Wide freshness-first pool. Ordering by score alone let stale SMA@95
        # crowd out live detectors (range/breakout/momentum/catalyst) forever.
        now = datetime.now(UTC)
        pool = list(
            self.db.scalars(
                select(MarketScanCandidate)
                .where(
                    MarketScanCandidate.stage == "Watching",
                    MarketScanCandidate.risk_status == "clear",
                    MarketScanCandidate.bias == "Bullish",
                )
                .order_by(desc(MarketScanCandidate.evaluated_at))
                .limit(200)
            )
        )
        fresh = [
            c
            for c in pool
            if candidate_market_data_is_fresh(
                evaluated_at=c.evaluated_at,
                market_data_at=c.market_data_at,
                now=now,
            )
        ]
        # Never fall back to stale candidates. A missed entry is safer than a
        # paper order whose stop/target is based on old short-timeframe data.
        cands = fresh
        allowed = (
            {key.lower() for key in allowed_strategy_keys}
            if allowed_strategy_keys is not None
            else None
        )
        excluded = {key.lower() for key in (excluded_strategy_keys or set())}
        if allowed is not None:
            cands = [
                c for c in cands if (c.strategy_key or "").lower() in allowed
            ]
        if excluded:
            cands = [
                c for c in cands if (c.strategy_key or "").lower() not in excluded
            ]
        if not cands:
            return []
        cands = [c for c in cands if float(c.score or 0) >= 50.0] or cands

        # Adaptive priority: hard primary (breakout/momentum/…) outranks Micro;
        # Micro outranks soft primary (range_mean / SMA) so Micro can actually
        # reach paper entry instead of being permanently crowded out.
        from app.services.paper_opportunity_detectors import MICRO_STRATEGY_KEYS
        from app.services.trading_intelligence_service import TradingIntelligenceService

        _HARD_PRIMARY = {
            "momentum_continuation",
            "breakout",
            "dip_pullback_reversal",
            "catalyst_retest",
        }
        intelligence = TradingIntelligenceService(self.db)
        performance_rows = intelligence.strategy_performance(
            portfolio_id=portfolio_id
        )
        performance_by_strategy = {
            str(row.get("strategy_key") or ""): row for row in performance_rows
        }

        def _portfolio_adjustment(sk: str) -> float:
            evidence = performance_by_strategy.get(sk)
            if evidence is None:
                return strategy_portfolio_priority_adjustment(
                    trades=0, expectancy_after_costs=None
                )
            raw_expectancy = evidence.get("expectancy")
            expectancy = (
                Decimal(str(raw_expectancy))
                if raw_expectancy is not None
                else None
            )
            return strategy_portfolio_priority_adjustment(
                trades=int(evidence.get("trades") or 0),
                expectancy_after_costs=expectancy,
            )

        def _strategy_tier(sk: str) -> int:
            if sk in _HARD_PRIMARY:
                return 3
            if sk in MICRO_STRATEGY_KEYS:
                return 2
            if sk == "range_mean_reversion":
                return 1
            return 0  # sma / unknown

        def _entry_priority(c: MarketScanCandidate) -> float:
            base = float(c.score or 0)
            sk = (c.strategy_key or "").lower()
            if sk == "sma_crossover" or not sk:
                base = min(base, 68.0)
            elif sk in MICRO_STRATEGY_KEYS:
                base += 8.0
            elif sk in _HARD_PRIMARY:
                base += 14.0
            else:
                base += 10.0
            if sk == "catalyst_retest":
                base += 4.0
            return base + _portfolio_adjustment(sk)

        def _better_for_symbol(
            a: MarketScanCandidate, b: MarketScanCandidate
        ) -> MarketScanCandidate:
            """Higher-tier strategy wins unless the lower tier clearly dominates."""
            pa, pb = _entry_priority(a), _entry_priority(b)
            ska = (a.strategy_key or "").lower()
            skb = (b.strategy_key or "").lower()
            ta, tb = _strategy_tier(ska), _strategy_tier(skb)
            if ta != tb:
                # Need +12 score-priority to overturn tier (keeps hard primary safe).
                if ta > tb:
                    return a if pa + 12.0 >= pb else b
                return b if pb + 12.0 >= pa else a
            return a if pa >= pb else b

        cands = sorted(cands, key=_entry_priority, reverse=True)
        # One best strategy per symbol.
        best_by_symbol: dict[str, MarketScanCandidate] = {}
        deferred_micro: list[tuple[str, str]] = []
        for c in cands:
            prior = best_by_symbol.get(c.symbol)
            if prior is None:
                best_by_symbol[c.symbol] = c
                continue
            winner = _better_for_symbol(c, prior)
            loser = prior if winner is c else c
            best_by_symbol[c.symbol] = winner
            lose_sk = (loser.strategy_key or "").lower()
            win_sk = (winner.strategy_key or "").lower()
            if lose_sk in MICRO_STRATEGY_KEYS and win_sk not in MICRO_STRATEGY_KEYS:
                deferred_micro.append((c.symbol, win_sk))
        cands = sorted(best_by_symbol.values(), key=_entry_priority, reverse=True)[:24]
        open_syms = {
            p.symbol
            for p in self.db.scalars(
                select(PaperPosition).where(
                    PaperPosition.portfolio_id == portfolio_id,
                    PaperPosition.quantity != 0,
                )
            )
        }
        # Cool-off after exit so the same symbol is not flipped every minute.
        recently_exited = self._symbols_exited_since(
            portfolio_id, within_seconds=120
        )
        resolved = self._resolve_actor(actor, portfolio)
        if resolved is None:
            return []

        # Surface real deferral reasons (not silent drops).
        for sym, winner_sk in deferred_micro[:8]:
            self._emit_decision_event(
                symbol=sym,
                outcome="info",
                title=f"Micro deferred on {sym}",
                detail=(
                    f"Micro setup present but {winner_sk} owns this symbol "
                    "(hard primary / larger opportunity). Paper only."
                ),
                reason_code="micro_deferred_for_primary",
            )
        from app.services.institutional_memory import InstitutionalMemoryService

        memory = InstitutionalMemoryService(self.db)

        for cand in cands:
            if cand.symbol in open_syms:
                continue
            if cand.symbol in recently_exited:
                continue
            if (cand.bias or "") != "Bullish":
                # Long-only: never convert bearish/neutral probes into buys.
                continue
            cand_detail = dict(cand.detail or {})
            strategy_key = (cand.strategy_key or "sma_crossover").lower()
            strategy_evidence = performance_by_strategy.get(strategy_key)
            strategy_trades = int((strategy_evidence or {}).get("trades") or 0)
            raw_expectancy = (strategy_evidence or {}).get("expectancy")
            strategy_expectancy = (
                Decimal(str(raw_expectancy))
                if raw_expectancy is not None
                else None
            )
            cand_detail["strategy_portfolio"] = {
                "trades": strategy_trades,
                "expectancy_after_costs": raw_expectancy,
                "priority_adjustment": _portfolio_adjustment(strategy_key),
                "exploration_sample_target": STRATEGY_EXPLORATION_SAMPLE,
                "founder_portfolio_only": True,
            }
            cand.detail = cand_detail
            if strategy_loses_to_cash(
                trades=strategy_trades,
                expectancy_after_costs=strategy_expectancy,
            ):
                self._emit_decision_event(
                    symbol=cand.symbol,
                    outcome="info",
                    title=f"Strategy loses to cash — skip {cand.symbol}",
                    detail=(
                        f"{strategy_key} has {strategy_trades} closed trades with "
                        f"expectancy {strategy_expectancy} after costs "
                        "(≤ idle cash). Sitting out until evidence turns."
                    ),
                    reason_code="strategy_loses_to_cash",
                )
                continue
            if not strategy_eligible_for_growth(
                trades=strategy_trades,
                expectancy_after_costs=strategy_expectancy,
                lane=ega_lane,
                total_pnl=total_pnl,
            ):
                self._emit_decision_event(
                    symbol=cand.symbol,
                    outcome="info",
                    title=f"EGA filters {strategy_key} on {cand.symbol}",
                    detail=(
                        f"Lane={ega_lane}: only positive-expectancy or "
                        f"under-sampled strategies may deploy while recovering. "
                        f"trades={strategy_trades}, expectancy={strategy_expectancy}."
                    ),
                    reason_code="ega_strategy_filter",
                )
                continue
            cand_notional = equity_growth_entry_notional(
                equity=equity,
                buying_power=buying_power,
                lane=ega_lane,
                trades=strategy_trades,
                expectancy_after_costs=strategy_expectancy,
            )
            if cand_notional <= 0:
                self._emit_decision_event(
                    symbol=cand.symbol,
                    outcome="info",
                    title=f"EGA size zero for {cand.symbol}",
                    detail=(
                        f"Lane={ega_lane} × expectancy sizing yielded no deployable "
                        f"notional for {strategy_key}."
                    ),
                    reason_code="ega_size_zero",
                )
                continue
            # Do not chase extreme peak tips (PAPER discipline). Extended
            # late-stage runners stay eligible — memory + reward gates still apply.
            disc_class = str(
                cand_detail.get("discovery_opportunity_class")
                or cand_detail.get("trade_pattern")
                or ""
            )
            if disc_class == "peak_exhaustion":
                self._emit_decision_event(
                    symbol=cand.symbol,
                    outcome="info",
                    title=f"Discovery avoid tip on {cand.symbol}",
                    detail=(
                        "Labeled peak exhaustion — waiting for pullback/retest, "
                        "not buying the absolute high."
                    ),
                    reason_code="discovery_chase_avoid",
                )
                continue

            # Catalyst-retest playbook: BTC must be supportive; optional positive
            # headline tag (never invents news — only matches stored headlines).
            if (cand.strategy_key or "") == "catalyst_retest":
                btc_regime = intelligence.infer_market_regime("BTC-USD")
                if btc_regime in {"trend_down", "volatile"}:
                    self._emit_decision_event(
                        symbol=cand.symbol,
                        outcome="info",
                        title=f"BTC not supportive for {cand.symbol}",
                        detail=(
                            f"catalyst_retest requires supportive BTC; "
                            f"BTC regime={btc_regime}."
                        ),
                        reason_code="btc_regime_block",
                    )
                    continue
                news_hit = self._positive_catalyst_headline(cand.symbol)
                cand_detail["catalyst_news"] = news_hit
                if news_hit.get("found"):
                    cand_detail["catalyst_classified"] = "positive_keyword"
                    # Soft score boost when a matching headline exists.
                    try:
                        cand.score = min(
                            Decimal("98"),
                            Decimal(str(cand.score or 0)) + Decimal("4"),
                        )
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    cand_detail["catalyst_classified"] = "price_volume_only"
                cand.detail = cand_detail

            # --- Institutional memory consult BEFORE paper entry (PAPER only) ---
            regime = intelligence.infer_market_regime(cand.symbol)
            delta = intelligence._paper_adaptive_delta(
                portfolio_id=portfolio_id,
                strategy_key=cand.strategy_key or "sma_crossover",
            )
            rr = None
            if cand.entry_zone and cand.stop_loss and cand.take_profit:
                risk = abs(float(cand.entry_zone) - float(cand.stop_loss))
                reward = abs(float(cand.take_profit) - float(cand.entry_zone))
                if risk > 0:
                    rr = reward / risk
            conf, _label, factors = intelligence.score_confidence(
                score=float(cand.score or 0),
                bias=cand.bias or "Neutral",
                risk_status=cand.risk_status or "blocked",
                regime=regime,
                stale=False,
                risk_reward=rr,
                paper_confidence_delta=delta,
            )
            vol_cond = "normal"
            if factors.get("volume_ok") is True or cand_detail.get("relative_volume_high"):
                vol_cond = "elevated"
            elif factors.get("volume_ok") is False:
                vol_cond = "thin"
            consult = memory.consult_before_entry(
                portfolio_id=portfolio_id,
                symbol=cand.symbol,
                strategy_key=cand.strategy_key or "sma_crossover",
                market_regime=regime,
                base_score=float(cand.score or 0),
                paper_confidence_delta=delta,
                confidence_label_score=conf,
                volume_condition=vol_cond,
                trade_pattern=str(
                    cand_detail.get("trade_pattern")
                    or cand_detail.get("discovery_opportunity_class")
                    or cand_detail.get("pattern")
                    or ""
                )
                or None,
            )
            action = str(consult.get("action") or "WAIT")
            if action != "EXECUTE":
                self.audit.append(
                    action="paper.training.memory_gate",
                    resource_type="market_scan_candidate",
                    resource_id=str(cand.id),
                    actor_user_id=resolved.user.id,
                    payload={
                        "symbol": cand.symbol,
                        "gate_action": action,
                        "learned_opportunity_score": consult.get(
                            "learned_opportunity_score"
                        ),
                        "similar_setup_count": consult.get("similar_setup_count"),
                        "evidence_strength": consult.get("evidence_strength"),
                        "prior_review_ids": consult.get("prior_review_ids"),
                        "paper_only": True,
                    },
                )
                self._emit_decision_event(
                    symbol=cand.symbol,
                    outcome="info",
                    title=f"Memory {action.lower()} on {cand.symbol}",
                    detail=(
                        f"Learned score {consult.get('learned_opportunity_score')}; "
                        f"similar setups {consult.get('similar_setup_count')}; "
                        f"evidence {consult.get('evidence_strength')}. No paper order."
                    ),
                    reason_code=f"memory_{action.lower()}",
                )
                continue
            # Refuse penny economics: normalize stops/targets, then require a
            # meaningful planned dollar reward at the desk notional.
            entry_px = cand.current_price or cand.entry_zone
            if entry_px is None or entry_px <= 0:
                continue
            is_micro = (cand.strategy_key or "") in {
                "range_micro",
                "trend_pullback_micro",
            }
            norm_stop, norm_target = normalize_exit_levels(
                entry_px,
                cand.stop_loss,
                cand.take_profit,
                min_r=(
                    MICRO_MIN_TAKE_PROFIT_R if is_micro else MIN_TAKE_PROFIT_R
                ),
            )
            reward_usd = expected_reward_usd(
                price=entry_px,
                target=norm_target,
                notional=cand_notional,
            )
            reward_floor = expected_reward_floor_usd(
                notional=cand_notional,
                strategy_key=cand.strategy_key,
            )
            reward_after_costs = (
                reward_usd
                - (
                    cand_notional
                    * MICRO_COST_BPS_RT
                    / Decimal("10000")
                ).quantize(Decimal("0.01"))
                if is_micro
                else reward_usd
            )
            if reward_after_costs < reward_floor:
                self._emit_decision_event(
                    symbol=cand.symbol,
                    outcome="info",
                    title=f"Skipped thin target on {cand.symbol}",
                    detail=(
                        f"Planned net reward ${reward_after_costs} is below the "
                        f"${reward_floor} size-adjusted minimum at "
                        f"${cand_notional} notional. "
                        "Waiting for a setup with real dollar upside."
                    ),
                    reason_code="reward_too_small",
                )
                continue
            # Persist normalized levels onto the candidate for the exit plan.
            cand.stop_loss = norm_stop
            cand.take_profit = norm_target
            try:
                order = self._open_paper_from_candidate(
                    portfolio_id=portfolio_id,
                    cand=cand,
                    notional=cand_notional,
                    actor=resolved,
                    memory_consult=consult,
                )
                cand.stage = "Entered"
                opened.append(
                    {
                        "symbol": cand.symbol,
                        "order_id": str(order.id),
                        "memory_action": action,
                        "learned_opportunity_score": consult.get(
                            "learned_opportunity_score"
                        ),
                        "ega_notional": str(cand_notional),
                        "ega_lane": ega_lane,
                    }
                )
                open_syms.add(cand.symbol)
                if len(open_syms) >= max_open:
                    break
                buying_power = (buying_power - cand_notional).quantize(Decimal("0.01"))
                entry_notional = equity_growth_entry_notional(
                    equity=equity,
                    buying_power=buying_power,
                    lane=ega_lane,
                )
                if entry_notional <= 0:
                    break
                self.audit.append(
                    action="paper.training.auto_enter",
                    resource_type="paper_order",
                    resource_id=str(order.id),
                    actor_user_id=resolved.user.id,
                    payload={
                        "symbol": cand.symbol,
                        "candidate_id": str(cand.id),
                        "institutional_memory": consult,
                        "strategy_portfolio": cand_detail.get("strategy_portfolio"),
                        "ega": {
                            "version": ega_plan.get("version"),
                            "lane": ega_lane,
                            "notional": str(cand_notional),
                        },
                        "paper_only": True,
                    },
                )
                self._emit_decision_event(
                    symbol=cand.symbol,
                    outcome="entered",
                    title=f"Entered {cand.symbol}",
                    detail=(
                        f"Opened a ${cand_notional} paper long after memory "
                        f"EXECUTE (score {consult.get('learned_opportunity_score')}; "
                        f"EGA lane={ega_lane}). "
                        f"Stop {cand.stop_loss}; target {cand.take_profit}."
                    ),
                    reason_code="auto_enter",
                )
            except (PaperTradingError, PaperTrainingError) as exc:
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                self.audit.append(
                    action="paper.training.auto_enter_failed",
                    resource_type="market_scan_candidate",
                    resource_id=str(cand.id),
                    actor_user_id=resolved.user.id,
                    payload={
                        "symbol": cand.symbol,
                        "error": getattr(exc, "message", str(exc))[:240],
                    },
                )
                continue
            except Exception as exc:  # noqa: BLE001 — never poison the scan session
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                self.audit.append(
                    action="paper.training.auto_enter_failed",
                    resource_type="market_scan_candidate",
                    resource_id=str(cand.id),
                    actor_user_id=resolved.user.id,
                    payload={
                        "symbol": cand.symbol,
                        "error": str(exc)[:240],
                    },
                )
                continue
        if opened:
            self.db.commit()
        return opened

    def _resolve_actor(
        self,
        actor: AuthenticatedPrincipal | None,
        portfolio: PaperPortfolio,
    ) -> AuthenticatedPrincipal | None:
        if actor is not None:
            return actor
        from types import SimpleNamespace

        from sqlalchemy.orm import selectinload

        from app.models import InstitutionalRole, User

        user = self.db.get(User, portfolio.owner_user_id)
        if user is None:
            user = self.db.scalars(
                select(User).options(selectinload(User.roles)).limit(1)
            ).first()
        if user is None:
            return None
        return AuthenticatedPrincipal(
            user=user,
            session=SimpleNamespace(id=None),  # type: ignore[arg-type]
            roles=frozenset({InstitutionalRole.FOUNDER}),
        )

    def _open_paper_from_candidate(
        self,
        *,
        portfolio_id: uuid.UUID,
        cand: MarketScanCandidate,
        notional: Decimal,
        actor: AuthenticatedPrincipal,
        memory_consult: dict[str, Any] | None = None,
    ) -> PaperOrder:
        price = cand.current_price
        if price is None or price <= 0:
            raise PaperTrainingError(
                "no_price",
                "No trustworthy current price is available for a paper entry.",
            )
        qty = (notional / price).quantize(Decimal("0.00000001"))
        if qty <= 0:
            raise PaperTrainingError("qty_zero", "Paper investment size is too small.")
        if (cand.bias or "") != "Bullish":
            raise PaperTrainingError(
                "long_only_bias",
                "Long-only paper mode refuses bearish or neutral signals as buys.",
            )
        stop, target = normalize_exit_levels(
            price, cand.stop_loss, cand.take_profit
        )
        order = self.paper.submit_order(
            portfolio_id=portfolio_id,
            actor=actor,
            symbol=cand.symbol,
            side="buy",
            order_type="market",
            quantity=qty,
            limit_price=price,
            idempotency_key=f"train-enter:{cand.id}",
        )
        # Persist planned exit levels on the entry order (paper only).
        self.paper._event(
            order,
            "paper_exit_plan",
            order.status,
            order.status,
            {
                "candidate_id": str(cand.id),
                "stop_loss": str(stop),
                "take_profit": str(target),
                "initial_stop_loss": str(stop),
                "entry_zone": str(cand.entry_zone) if cand.entry_zone is not None else str(price),
                "institutional_memory": memory_consult,
                "strategy_key": cand.strategy_key,
                "playbook": (cand.detail or {}).get("playbook") or cand.strategy_key,
                "trade_pattern": (cand.detail or {}).get("trade_pattern")
                or (cand.detail or {}).get("pattern"),
                "discovery_source": (cand.detail or {}).get("discovery_source"),
                "discovery_opportunity_class": (cand.detail or {}).get(
                    "discovery_opportunity_class"
                ),
                "discovered_market": bool((cand.detail or {}).get("discovered_market")),
                "catalyst_news": (cand.detail or {}).get("catalyst_news"),
                "catalyst_classified": (cand.detail or {}).get("catalyst_classified"),
                "scaled_out": False,
            },
        )
        try:
            from app.services.trading_intelligence_service import TradingIntelligenceService

            with self.db.begin_nested():
                TradingIntelligenceService(self.db).snapshot_for_candidate(
                    cand,
                    portfolio_id=portfolio_id,
                    entry_order_id=order.id,
                    stale=False,
                    memory_consult=memory_consult,
                )
        except Exception:  # noqa: BLE001 — intelligence must never block paper entry
            pass
        self.db.commit()
        self.db.refresh(order)
        return order

    def open_position_symbols_for_strategies(
        self, *, portfolio_id: uuid.UUID, strategy_keys: set[str]
    ) -> list[str]:
        """Return open symbols whose active entry plan belongs to a strategy lane."""
        symbols: list[str] = []
        for pos in self.paper.list_positions(portfolio_id):
            if not pos.quantity or pos.quantity <= 0:
                continue
            plan = self.paper._exit_plan_levels(portfolio_id, pos.symbol)
            if str(plan.get("strategy_key") or "") in strategy_keys:
                symbols.append(pos.symbol)
        return symbols

    def evaluate_paper_exits(
        self,
        *,
        portfolio_id: uuid.UUID,
        actor: AuthenticatedPrincipal | None = None,
        allowed_strategy_keys: set[str] | None = None,
        excluded_strategy_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Close paper longs when verified marks hit stored stop or target.

        Never invents prices. Never touches live execution. Exits remain allowed
        even when pause_new_entries is active.
        """
        portfolio = self.db.get(PaperPortfolio, portfolio_id)
        if portfolio is None or portfolio.kill_switch_active:
            return []
        resolved = self._resolve_actor(actor, portfolio)
        if resolved is None:
            return []
        closed: list[dict[str, Any]] = []
        positions = [
            p
            for p in self.paper.list_positions(portfolio_id)
            if p.quantity and p.quantity > 0
        ]
        for pos in positions:
            plan = self.paper._exit_plan_levels(portfolio_id, pos.symbol)
            strategy_key = str(plan.get("strategy_key") or "")
            if allowed_strategy_keys is not None and strategy_key not in allowed_strategy_keys:
                continue
            if excluded_strategy_keys is not None and strategy_key in excluded_strategy_keys:
                continue
            is_micro = strategy_key in {"range_micro", "trend_pullback_micro"}
            stop = plan.get("stop_loss")
            target = plan.get("take_profit")
            if stop is None and target is None:
                continue
            avg = getattr(pos, "average_cost", None)
            # Do not re-normalize an already-trailed stop above entry — that
            # would wipe the ratchet back to a fresh 1.5% protective stop.
            if (
                avg is not None
                and avg > 0
                and (stop is None or stop < avg)
            ):
                stop, target = normalize_exit_levels(
                    avg,
                    stop,
                    target,
                    min_r=(
                        MICRO_MIN_TAKE_PROFIT_R
                        if is_micro
                        else MIN_TAKE_PROFIT_R
                    ),
                )
            mark, mark_at = self.paper._latest_mark(pos.symbol)
            held_seconds = self._position_held_seconds(portfolio_id, pos.symbol)
            now = datetime.now(UTC)
            mark_age = (now - mark_at) if mark_at is not None else None
            fresh = (
                mark is not None
                and mark_at is not None
                and mark_age is not None
                and mark_age <= PAPER_MARK_STALE_AFTER
            )
            force_time_exit: str | None = None
            if not fresh:
                overdue = None
                if is_micro and held_seconds >= float(MICRO_MAX_HOLD_SECONDS):
                    overdue = "micro_time_exit"
                elif (
                    (getattr(portfolio, "name", None) or "")
                    == FOUNDER_LEARNING_DESK_NAME
                    and held_seconds >= float(FOUNDER_MAX_HOLD_SECONDS)
                ):
                    overdue = "stale_time_exit"
                usable_stale = (
                    mark is not None
                    and mark_at is not None
                    and mark_age is not None
                    and mark_age <= TIME_EXIT_MARK_MAX_AGE
                )
                if overdue and usable_stale:
                    force_time_exit = overdue
                else:
                    continue
            # Trail only after meaningful progress — early BE at +1R clipped winners
            # into noise exits and destroyed expectancy (paper only; live locked).
            planned_stop = stop
            ratcheted = False
            risk_unit: Decimal | None = None
            r_mult: Decimal | None = None
            if avg is not None and avg > 0:
                initial_stop = plan.get("initial_stop_loss")
                if initial_stop is None and stop is not None and stop < avg:
                    initial_stop = stop
                if initial_stop is not None and initial_stop < avg:
                    risk_unit = avg - initial_stop
                else:
                    risk_unit = avg * MIN_STOP_DISTANCE_PCT
                if risk_unit is not None and risk_unit > 0:
                    r_mult = (mark - avg) / risk_unit
            if (
                not force_time_exit
                and avg is not None
                and avg > 0
                and stop is not None
                and stop < avg
                and risk_unit is not None
                and risk_unit > 0
                and r_mult is not None
            ):
                if r_mult >= Decimal("2"):
                    trail = avg + risk_unit  # lock ~1R
                    if trail > stop:
                        stop = trail
                        ratcheted = True
                elif r_mult >= Decimal("1.5"):
                    trail = avg + (risk_unit * Decimal("0.5"))
                    if trail > stop:
                        stop = trail
                        ratcheted = True
            # Founder desk: bank half at +1R so cash returns for dip redeploys.
            # Full runners still seek the planned take-profit on the remainder.
            if (
                not force_time_exit
                and (getattr(portfolio, "name", None) or "") == FOUNDER_LEARNING_DESK_NAME
                and not bool(plan.get("scaled_out"))
                and avg is not None
                and avg > 0
                and risk_unit is not None
                and risk_unit > 0
                and r_mult is not None
                and r_mult >= SCALE_OUT_R
                and held_seconds >= float(SCALE_OUT_HOLD_SECONDS)
            ):
                half = (abs(pos.quantity) * SCALE_OUT_FRACTION).quantize(
                    Decimal("0.00000001")
                )
                if half > 0 and half < abs(pos.quantity):
                    entry_order_id = plan.get("entry_order_id")
                    entry_key = str(entry_order_id) if entry_order_id else "none"
                    try:
                        order = self.paper.submit_order(
                            portfolio_id=portfolio_id,
                            actor=resolved,
                            symbol=pos.symbol,
                            side="sell",
                            order_type="market",
                            quantity=half,
                            limit_price=mark,
                            idempotency_key=(
                                f"exit:{portfolio_id}:{pos.symbol}:"
                                f"scale_out:{entry_key}"
                            ),
                        )
                    except Exception as exc:  # noqa: BLE001
                        try:
                            self.db.rollback()
                        except Exception:  # noqa: BLE001
                            pass
                        self.audit.append(
                            action="paper.training.auto_exit_failed",
                            resource_type="paper_position",
                            resource_id=str(pos.id),
                            actor_user_id=resolved.user.id,
                            payload={
                                "symbol": pos.symbol,
                                "reason": "scale_out",
                                "mark": str(mark),
                                "error": str(exc)[:240],
                            },
                        )
                        continue
                    if entry_order_id is not None:
                        entry_order = self.db.get(PaperOrder, entry_order_id)
                        if entry_order is not None:
                            self.paper._event(
                                entry_order,
                                "paper_exit_plan",
                                entry_order.status,
                                entry_order.status,
                                {
                                    "stop_loss": str(stop) if stop is not None else None,
                                    "take_profit": (
                                        str(target) if target is not None else None
                                    ),
                                    "initial_stop_loss": str(
                                        plan.get("initial_stop_loss") or planned_stop
                                    )
                                    if (plan.get("initial_stop_loss") or planned_stop)
                                    else None,
                                    "entry_zone": str(avg),
                                    "scaled_out": True,
                                    "strategy_key": plan.get("strategy_key"),
                                },
                            )
                    self.paper._event(
                        order,
                        "paper_exit_triggered",
                        order.status,
                        order.status,
                        {
                            "reason": "scale_out",
                            "mark": str(mark),
                            "quantity": str(half),
                            "stop_loss": str(stop) if stop is not None else None,
                            "take_profit": (
                                str(target) if target is not None else None
                            ),
                        },
                    )
                    self.audit.append(
                        action="paper.training.auto_exit",
                        resource_type="paper_order",
                        resource_id=str(order.id),
                        actor_user_id=resolved.user.id,
                        payload={
                            "symbol": pos.symbol,
                            "reason": "scale_out",
                            "mark": str(mark),
                            "quantity": str(half),
                        },
                    )
                    self._emit_decision_event(
                        portfolio_id=portfolio_id,
                        symbol=pos.symbol,
                        outcome="exited",
                        title=f"Banked partial profit on {pos.symbol}",
                        detail=(
                            f"Sold half at {mark} after +{SCALE_OUT_R}R so cash "
                            "can redeploy into dips; runner still open."
                        ),
                        reason_code="scale_out",
                    )
                    closed.append(
                        {
                            "symbol": pos.symbol,
                            "order_id": str(order.id),
                            "reason": "scale_out",
                            "mark": str(mark),
                        }
                    )
                    continue
            if (
                not force_time_exit
                and ratcheted
                and planned_stop is not None
                and stop is not None
                and stop > planned_stop
                and mark > stop
            ):
                entry_order_id = plan.get("entry_order_id")
                if entry_order_id is not None:
                    entry_order = self.db.get(PaperOrder, entry_order_id)
                    if entry_order is not None:
                        self.paper._event(
                            entry_order,
                            "paper_exit_plan",
                            entry_order.status,
                            entry_order.status,
                            {
                                "stop_loss": str(stop),
                                "take_profit": (
                                    str(target) if target is not None else None
                                ),
                                "initial_stop_loss": str(
                                    plan.get("initial_stop_loss") or planned_stop
                                )
                                if (plan.get("initial_stop_loss") or planned_stop)
                                else None,
                                "trailed": True,
                                "scaled_out": bool(plan.get("scaled_out")),
                                "entry_zone": str(avg),
                                "strategy_key": plan.get("strategy_key"),
                            },
                        )
                        try:
                            self.db.commit()
                        except Exception:  # noqa: BLE001
                            try:
                                self.db.rollback()
                            except Exception:  # noqa: BLE001
                                pass
                # Fall through — take-profit / stop may still apply this pass.
            reason: str | None = force_time_exit
            if reason is None and stop is not None and mark <= stop:
                reason = (
                    "trailing_stop"
                    if planned_stop is not None and stop > planned_stop
                    else "stop_loss"
                )
            elif target is not None and mark >= target:
                held_ok = held_seconds >= float(TAKE_PROFIT_MIN_HOLD_SECONDS)
                if held_ok:
                    reason = "take_profit"
            elif (
                (getattr(portfolio, "name", None) or "") == FOUNDER_LEARNING_DESK_NAME
                and bool(plan.get("scaled_out"))
                and r_mult is not None
                and r_mult >= RUNNER_BANK_R
                and held_seconds >= float(RUNNER_BANK_HOLD_SECONDS)
            ):
                # Recycle capital: don't sit full waiting for distant 2R after
                # already banking half.
                reason = "runner_bank"
            elif (
                (getattr(portfolio, "name", None) or "") == FOUNDER_LEARNING_DESK_NAME
                and r_mult is not None
                and r_mult >= STALE_BANK_R
                and held_seconds >= float(STALE_BANK_HOLD_SECONDS)
            ):
                reason = "stale_bank"
            elif is_micro and held_seconds >= float(MICRO_MAX_HOLD_SECONDS):
                # A short-timeframe thesis that has not resolved within four
                # hours is no longer the setup that was entered. Close it using
                # a verified public mark so capital and learning can recycle.
                reason = "micro_time_exit"
            elif (
                (getattr(portfolio, "name", None) or "") == FOUNDER_LEARNING_DESK_NAME
                and held_seconds >= float(FOUNDER_MAX_HOLD_SECONDS)
            ):
                reason = "stale_time_exit"
            elif self._catalyst_momentum_weakened(
                portfolio_id=portfolio_id,
                symbol=pos.symbol,
                entry_order_id=plan.get("entry_order_id"),
                mark=mark,
                avg=avg,
            ):
                held_ok = held_seconds >= 600.0
                if held_ok:
                    reason = "momentum_fade"
            if reason is None:
                continue
            entry_order_id = plan.get("entry_order_id")
            entry_key = str(entry_order_id) if entry_order_id else "none"
            try:
                order = self.paper.submit_order(
                    portfolio_id=portfolio_id,
                    actor=resolved,
                    symbol=pos.symbol,
                    side="sell",
                    order_type="market",
                    quantity=abs(pos.quantity),
                    limit_price=mark,
                    idempotency_key=(
                        f"exit:{portfolio_id}:{pos.symbol}:{reason}:{entry_key}"
                    ),
                )
            except PaperTradingError as exc:
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                self.audit.append(
                    action="paper.training.auto_exit_failed",
                    resource_type="paper_position",
                    resource_id=str(pos.id),
                    actor_user_id=resolved.user.id,
                    payload={
                        "symbol": pos.symbol,
                        "reason": reason,
                        "mark": str(mark),
                        "error": getattr(exc, "message", str(exc))[:240],
                    },
                )
                try:
                    from app.models import IncidentSeverity
                    from app.services.incident_service import IncidentService

                    with self.db.begin_nested():
                        IncidentService(self.db).open_system_incident(
                            title=f"Paper auto-exit failed for {pos.symbol}",
                            description=(
                                f"Automated {reason} exit could not submit. "
                                f"{getattr(exc, 'message', str(exc))[:240]}"
                            ),
                            severity=IncidentSeverity.HIGH,
                            correlation_key=(
                                f"paper-auto-exit:{portfolio_id}:{pos.symbol}"
                            ),
                            commit=False,
                        )
                except Exception:  # noqa: BLE001
                    pass
                continue
            except Exception as exc:  # noqa: BLE001
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                self.audit.append(
                    action="paper.training.auto_exit_failed",
                    resource_type="paper_position",
                    resource_id=str(pos.id),
                    actor_user_id=resolved.user.id,
                    payload={
                        "symbol": pos.symbol,
                        "reason": reason,
                        "mark": str(mark),
                        "error": str(exc)[:240],
                    },
                )
                continue
            self.paper._event(
                order,
                "paper_exit_triggered",
                order.status,
                order.status,
                {
                    "reason": reason,
                    "mark": str(mark),
                    "stop_loss": str(stop) if stop is not None else None,
                    "take_profit": str(target) if target is not None else None,
                },
            )
            self.audit.append(
                action="paper.training.auto_exit",
                resource_type="paper_order",
                resource_id=str(order.id),
                actor_user_id=resolved.user.id,
                payload={
                    "symbol": pos.symbol,
                    "reason": reason,
                    "mark": str(mark),
                },
            )
            why = (
                f"Stop-loss hit at {mark} (stop {stop})."
                if reason == "stop_loss"
                else (
                    f"Trailing stop hit at {mark} (stop {stop})."
                    if reason == "trailing_stop"
                    else (
                        f"Momentum faded at {mark}."
                        if reason == "momentum_fade"
                        else (
                            f"Micro thesis expired after {MICRO_MAX_HOLD_SECONDS // 3600}h "
                            f"at mark {mark}."
                            if reason == "micro_time_exit"
                            else (
                            f"Time-stop after {FOUNDER_MAX_HOLD_SECONDS // 3600}h "
                            f"at mark {mark} (slot recycle)."
                            if reason == "stale_time_exit"
                            else (
                            f"Banked runner at {mark} after +{RUNNER_BANK_R}R "
                            "(capital recycle)."
                            if reason == "runner_bank"
                            else (
                                f"Stale-bank exit at {mark} after long hold "
                                f"with +{STALE_BANK_R}R progress."
                                if reason == "stale_bank"
                                else f"Take-profit hit at {mark} (target {target})."
                            )
                            )
                            )
                        )
                    )
                )
            )
            self._emit_decision_event(
                portfolio_id=portfolio_id,
                symbol=pos.symbol,
                outcome="exited",
                title=f"Exited {pos.symbol} ({reason.replace('_', ' ')})",
                detail=why,
                reason_code=reason,
            )
            try:
                from app.services.trading_intelligence_service import (
                    TradingIntelligenceService,
                )

                with self.db.begin_nested():
                    TradingIntelligenceService(self.db).record_post_trade_review(
                        portfolio_id=portfolio_id,
                        symbol=pos.symbol,
                        exit_order=order,
                        exit_reason=reason,
                        entry_order_id=(
                            uuid.UUID(str(entry_order_id)) if entry_order_id else None
                        ),
                        mark=mark,
                    )
            except Exception:  # noqa: BLE001 — review must not block exit
                pass
            closed.append(
                {
                    "symbol": pos.symbol,
                    "order_id": str(order.id),
                    "reason": reason,
                    "mark": str(mark),
                }
            )
        if closed:
            self.db.commit()
        return closed

    def _positive_catalyst_headline(self, symbol: str) -> dict[str, Any]:
        """Best-effort keyword match against stored news (never invents headlines)."""
        from app.models.market_intelligence import MarketNewsItem

        base = symbol.upper().split("-")[0]
        if not base or len(base) < 2:
            return {"found": False}
        positive = (
            "surge",
            "rally",
            "partnership",
            "listing",
            "approval",
            "upgrade",
            "adoption",
            "inflow",
            "record",
            "breakthrough",
            "launch",
        )
        negative = (
            "hack",
            "exploit",
            "ban",
            "lawsuit",
            "sec charge",
            "collapse",
            "insolvent",
            "delist",
        )
        cutoff = datetime.now(UTC).timestamp() - 72 * 3600
        cutoff_dt = datetime.fromtimestamp(cutoff, tz=UTC)
        rows = list(
            self.db.scalars(
                select(MarketNewsItem)
                .where(MarketNewsItem.published_at >= cutoff_dt)
                .order_by(desc(MarketNewsItem.published_at))
                .limit(80)
            )
        )
        base_l = base.lower()
        for row in rows:
            text = f"{row.headline} {row.body or ''}".lower()
            if base_l not in text:
                continue
            if any(n in text for n in negative):
                return {
                    "found": True,
                    "positive": False,
                    "headline": row.headline[:240],
                }
            if any(p in text for p in positive):
                return {
                    "found": True,
                    "positive": True,
                    "headline": row.headline[:240],
                }
            return {
                "found": True,
                "positive": None,
                "headline": row.headline[:240],
            }
        return {"found": False}

    def _catalyst_momentum_weakened(
        self,
        *,
        portfolio_id: uuid.UUID,
        symbol: str,
        entry_order_id: Any,
        mark: Decimal,
        avg: Decimal | None,
    ) -> bool:
        """Exit catalyst_retest longs when short momentum rolls over while still green."""
        if avg is None or avg <= 0 or mark <= avg or entry_order_id is None:
            return False
        from app.models.paper_trading import PaperOrderEvent

        payload = self.db.execute(
            select(PaperOrderEvent.payload)
            .where(
                PaperOrderEvent.order_id == entry_order_id,
                PaperOrderEvent.event_type == "paper_exit_plan",
            )
            .order_by(PaperOrderEvent.occurred_at.desc())
            .limit(1)
        ).scalar()
        if not isinstance(payload, dict):
            return False
        strategy = str(payload.get("strategy_key") or payload.get("playbook") or "")
        pattern = str(
            payload.get("trade_pattern")
            or payload.get("discovery_opportunity_class")
            or ""
        )
        if strategy != "catalyst_retest" and pattern != "catalyst_retest":
            return False

        from app.models.market_intelligence import MarketInstrument, MarketOhlcvBar

        inst = self.db.scalar(
            select(MarketInstrument).where(MarketInstrument.symbol == symbol.upper())
        )
        if inst is None:
            return False
        rows = list(
            self.db.scalars(
                select(MarketOhlcvBar)
                .where(
                    MarketOhlcvBar.instrument_id == inst.id,
                    MarketOhlcvBar.timeframe.in_(("1m", "5m")),
                )
                .order_by(MarketOhlcvBar.close_time.desc())
                .limit(16)
            )
        )
        if len(rows) < 12:
            return False
        closes = [Decimal(str(r.close)) for r in reversed(rows)]
        fast = sum(closes[-5:], Decimal("0")) / Decimal("5")
        slow = sum(closes[-12:], Decimal("0")) / Decimal("12")
        # Require giveback from the recent local peak — do not exit merely because
        # a short SMA dipped while price is still grinding higher.
        peak = max(closes[-8:])
        giveback = peak > 0 and mark <= peak * Decimal("0.995")
        return giveback and fast < slow * Decimal("0.997")

    def _position_held_seconds(self, portfolio_id: uuid.UUID, symbol: str) -> float:
        """Seconds since the latest buy fill for this open symbol."""
        from app.models.paper_trading import PaperFill

        filled_at = self.db.scalar(
            select(PaperFill.filled_at)
            .where(
                PaperFill.portfolio_id == portfolio_id,
                PaperFill.symbol == symbol.upper(),
                PaperFill.side == "buy",
            )
            .order_by(PaperFill.filled_at.desc())
            .limit(1)
        )
        if filled_at is None or not isinstance(filled_at, datetime):
            return 0.0
        if filled_at.tzinfo is None:
            filled_at = filled_at.replace(tzinfo=UTC)
        return max(0.0, (datetime.now(UTC) - filled_at).total_seconds())

    def _symbols_exited_since(
        self, portfolio_id: uuid.UUID, *, within_seconds: int
    ) -> set[str]:
        """Symbols with a paper sell fill inside the cool-off window."""
        from app.models.paper_trading import PaperFill

        cutoff = datetime.now(UTC).timestamp() - within_seconds
        cutoff_dt = datetime.fromtimestamp(cutoff, tz=UTC)
        rows = self.db.scalars(
            select(PaperFill.symbol)
            .where(
                PaperFill.portfolio_id == portfolio_id,
                PaperFill.side == "sell",
                PaperFill.filled_at >= cutoff_dt,
            )
            .distinct()
        )
        return {str(s).upper() for s in rows}

    def _emit_decision_event(
        self,
        *,
        portfolio_id: uuid.UUID | None = None,
        symbol: str,
        outcome: str,
        title: str,
        detail: str,
        reason_code: str,
    ) -> None:
        """Write enter/exit into market_scan_events so the Decided pane can show why."""
        try:
            from app.models.market_scan import MarketScanEvent

            if portfolio_id is None:
                portfolio_id = self.db.scalar(
                    select(PaperPortfolio.id).where(
                        PaperPortfolio.name == FOUNDER_LEARNING_DESK_NAME
                    )
                )
            portfolio = (
                self.db.get(PaperPortfolio, portfolio_id)
                if portfolio_id is not None
                else None
            )
            if (
                portfolio is None
                or (portfolio.name or "") != FOUNDER_LEARNING_DESK_NAME
            ):
                return
            now = datetime.now(UTC)
            recent = self.db.scalar(
                select(MarketScanEvent.id)
                .where(
                    MarketScanEvent.component == "paper_training",
                    MarketScanEvent.symbol == symbol,
                    MarketScanEvent.outcome == outcome,
                    MarketScanEvent.reason_code == reason_code,
                    MarketScanEvent.occurred_at >= now - timedelta(minutes=5),
                )
                .order_by(desc(MarketScanEvent.occurred_at))
                .limit(1)
            )
            if recent is not None:
                return
            self.db.add(
                MarketScanEvent(
                    cycle_id=None,
                    candidate_id=None,
                    component="paper_training",
                    symbol=symbol,
                    stage="Entered" if outcome == "entered" else "Exited",
                    outcome=outcome,
                    reason_code=reason_code,
                    title=title,
                    detail=detail[:500],
                    strategy_key="sma_crossover",
                    correlation_id=f"paper-{outcome}-{symbol}-{uuid.uuid4().hex[:10]}",
                    occurred_at=now,
                    payload={"portfolio_id": str(portfolio_id)},
                )
            )
        except Exception:  # noqa: BLE001 — UI stream must never block trading
            pass

    def ensure_learning_desk(
        self, *, actor: AuthenticatedPrincipal
    ) -> PaperPortfolio:
        """Return the canonical $300 Founder Learning Desk (create if missing)."""
        existing = self.db.scalar(
            select(PaperPortfolio).where(
                PaperPortfolio.name == FOUNDER_LEARNING_DESK_NAME
            )
        )
        if existing is not None:
            self._upgrade_legacy_tiny_notional(existing)
            return existing
        portfolio = self.paper.create_portfolio(
            name=FOUNDER_LEARNING_DESK_NAME,
            initial_cash=LEARNING_STARTING_CASH,
            actor=actor,
        )
        settings = self.get_or_create_settings(portfolio.id)
        settings.mode = "automatic"
        settings.default_notional = LEARNING_DEFAULT_NOTIONAL
        self.db.commit()
        self.db.refresh(portfolio)
        return portfolio

    def _upgrade_legacy_tiny_notional(self, portfolio: PaperPortfolio) -> None:
        """Bump legacy $30 practice size when the desk still has enough cash.

        Dig-out desks with reduced cash are left alone so notional stays
        within buying power.
        """
        settings = self.get_or_create_settings(portfolio.id)
        if settings.default_notional > LEGACY_TINY_NOTIONAL:
            return
        buying_power = portfolio.cash_balance - (
            portfolio.reserved_cash or Decimal("0")
        )
        if buying_power < LEARNING_DEFAULT_NOTIONAL:
            return
        previous = settings.default_notional
        settings.default_notional = LEARNING_DEFAULT_NOTIONAL
        self.audit.append(
            action="paper.training.notional_upgraded",
            resource_type="paper_portfolio",
            resource_id=str(portfolio.id),
            actor_user_id=portfolio.owner_user_id,
            payload={
                "previous_default_notional": str(previous),
                "default_notional": str(LEARNING_DEFAULT_NOTIONAL),
                "reason": "legacy_tiny_notional_unacceptable_daily_pnl",
                "paper_only": True,
            },
        )
        self.db.commit()

    def reseed_learning_desk(
        self,
        portfolio_id: uuid.UUID,
        *,
        actor: AuthenticatedPrincipal,
        starting_cash: Decimal = LEARNING_STARTING_CASH,
        default_notional: Decimal = LEARNING_DEFAULT_NOTIONAL,
    ) -> dict[str, Any]:
        """Flatten open paper risk and reset cash to the learning starting size.

        Live trading remains locked. Used so Founder practice mirrors ~$300 live.
        Preserves trade history (does not delete orders) so audit stays intact.
        """
        portfolio = self.db.get(PaperPortfolio, portfolio_id)
        if portfolio is None:
            raise PaperTrainingError("portfolio_not_found", str(portfolio_id))
        cleared: list[str] = []
        for pos in list(self.paper.list_positions(portfolio_id)):
            if not pos.quantity or pos.quantity == 0:
                continue
            # Flat without deleting order history (FK-safe).
            pos.quantity = Decimal("0")
            cleared.append(pos.symbol)
        portfolio = self.paper.get_portfolio(portfolio_id)
        portfolio.reserved_cash = Decimal("0")
        delta = starting_cash - portfolio.cash_balance
        portfolio.cash_balance = starting_cash
        if delta != 0 or cleared:
            from app.models.paper_trading import PaperCashLedger

            self.db.add(
                PaperCashLedger(
                    portfolio_id=portfolio.id,
                    entry_type="learning_reseed",
                    amount=delta,
                    balance_after=starting_cash,
                    note=(
                        f"Founder learning desk reseeded to ${starting_cash} "
                        f"(cleared {', '.join(cleared) or 'none'}; paper only; live locked)."
                    ),
                )
            )
        try:
            from app.execution.providers.paper import PaperExecutionProvider

            # Prefer the live gateway instance so reseed cannot leave a stale
            # in-memory book that later provider_syncs old cash back to DB.
            runtime = self.paper.gateway.get_provider("internal_paper")
            if isinstance(runtime, PaperExecutionProvider):
                runtime.reset_account(portfolio.id, cash=starting_cash)
            else:
                PaperExecutionProvider(self.db).reset_account(
                    portfolio.id, cash=starting_cash
                )
        except Exception:  # noqa: BLE001 — DB cash is source of truth for UI
            pass
        settings = self.get_or_create_settings(portfolio_id)
        settings.mode = "automatic"
        settings.default_notional = default_notional
        self.audit.append(
            action="paper.training.learning_reseed",
            resource_type="paper_portfolio",
            resource_id=str(portfolio_id),
            actor_user_id=actor.user.id,
            payload={
                "starting_cash": str(starting_cash),
                "default_notional": str(default_notional),
                "cleared_symbols": cleared,
            },
        )
        self.db.commit()
        return {
            "portfolio_id": str(portfolio_id),
            "cash_balance": str(starting_cash),
            "default_notional": str(default_notional),
            "cleared_symbols": cleared,
            "reseed_count": self.count_learning_reseeds(portfolio_id),
            "dig_out_count": self.count_learning_dig_outs(portfolio_id),
            "recovery_pressure": self.recovery_pressure(portfolio_id),
        }

    def count_learning_reseeds(self, portfolio_id: uuid.UUID) -> int:
        from app.models.paper_trading import PaperCashLedger

        return int(
            self.db.scalar(
                select(func.count())
                .select_from(PaperCashLedger)
                .where(
                    PaperCashLedger.portfolio_id == portfolio_id,
                    PaperCashLedger.entry_type == "learning_reseed",
                )
            )
            or 0
        )

    def count_learning_dig_outs(self, portfolio_id: uuid.UUID) -> int:
        from app.models.paper_trading import PaperCashLedger

        return int(
            self.db.scalar(
                select(func.count())
                .select_from(PaperCashLedger)
                .where(
                    PaperCashLedger.portfolio_id == portfolio_id,
                    PaperCashLedger.entry_type == "learning_dig_out",
                )
            )
            or 0
        )

    def recovery_pressure(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        reseeds = self.count_learning_reseeds(portfolio_id)
        dig_outs = self.count_learning_dig_outs(portfolio_id)
        level = "ok"
        note = "No reseed pressure yet — paper recovery is healthy."
        if reseeds >= 5:
            level = "critical"
            note = (
                f"{reseeds} reseeds recorded. Argus is repeatedly exhausting paper capital "
                "— treat this as overall training failure until expectancy improves."
            )
        elif reseeds >= 3:
            level = "elevated"
            note = (
                f"{reseeds} reseeds recorded. Prefer Dig out with remaining cash "
                "before another full reset."
            )
        elif reseeds >= 1:
            level = "watch"
            note = (
                f"{reseeds} reseed(s) on this desk. Dig-out attempts: {dig_outs}."
            )
        return {
            "level": level,
            "reseed_count": reseeds,
            "dig_out_count": dig_outs,
            "note": note,
            "paper_only": True,
        }

    def dig_out_with_remaining(
        self,
        portfolio_id: uuid.UUID,
        *,
        actor: AuthenticatedPrincipal,
    ) -> dict[str, Any]:
        """Continue paper learning with remaining cash — no invented capital."""
        portfolio = self.db.get(PaperPortfolio, portfolio_id)
        if portfolio is None:
            raise PaperTrainingError("portfolio_not_found", str(portfolio_id))
        buying_power = portfolio.cash_balance - (portfolio.reserved_cash or Decimal("0"))
        if buying_power < MIN_DIG_OUT_CASH:
            raise PaperTrainingError(
                "insufficient_cash_for_dig_out",
                (
                    f"Only ${buying_power:.2f} available. Need at least "
                    f"${MIN_DIG_OUT_CASH:.2f} to dig out — use Reseed for a fresh $300 book."
                ),
            )
        raw = (buying_power * DIG_OUT_NOTIONAL_FRACTION).quantize(Decimal("0.01"))
        notional = max(MIN_DIG_OUT_CASH, min(LEARNING_DEFAULT_NOTIONAL, raw))
        if notional > buying_power:
            notional = buying_power.quantize(Decimal("0.01"))
        settings = self.get_or_create_settings(portfolio_id)
        settings.mode = "automatic"
        settings.default_notional = notional
        if portfolio.pause_new_entries_active:
            portfolio.pause_new_entries_active = False
        from app.models.paper_trading import PaperCashLedger

        self.db.add(
            PaperCashLedger(
                portfolio_id=portfolio.id,
                entry_type="learning_dig_out",
                amount=Decimal("0"),
                balance_after=portfolio.cash_balance,
                note=(
                    f"Dig-out with remaining ${buying_power:.2f}; "
                    f"practice size set to ${notional:.2f} (paper only; live locked)."
                ),
            )
        )
        self.audit.append(
            action="paper.training.learning_dig_out",
            resource_type="paper_portfolio",
            resource_id=str(portfolio_id),
            actor_user_id=actor.user.id,
            payload={
                "buying_power": str(buying_power),
                "default_notional": str(notional),
                "cash_balance": str(portfolio.cash_balance),
            },
        )
        self._emit_decision_event(
            symbol="*",
            outcome="info",
            title="Dig-out mode enabled",
            detail=(
                f"Argus will keep practicing with ${buying_power:.2f} remaining "
                f"(${notional:.2f} per entry). No cash was added."
            ),
            reason_code="learning_dig_out",
        )
        self.db.commit()
        pressure = self.recovery_pressure(portfolio_id)
        return {
            "portfolio_id": str(portfolio_id),
            "cash_balance": str(portfolio.cash_balance),
            "buying_power": str(buying_power),
            "default_notional": str(notional),
            "mode": "automatic",
            "reseed_count": pressure["reseed_count"],
            "dig_out_count": pressure["dig_out_count"],
            "recovery_pressure": pressure,
            "cash_added": False,
            "live_trading_enabled": False,
        }

    def trade_lesson_for_candidate(self, cand: MarketScanCandidate) -> dict[str, Any]:
        return {
            "phase": "before",
            "what_argus_sees": plain_rejection(cand.reason_code, cand.reason_text),
            "why_it_may_work": (
                "Momentum rules see a favorable short-term setup."
                if cand.bias == "Bullish" and cand.stage != "Rejected"
                else "Argus does not currently see a workable entry."
            ),
            "what_could_fail": (
                "Prices may reverse, data may go stale, or risk limits may block entry."
            ),
            "planned_entry": cand.entry_zone,
            "planned_stop": cand.stop_loss,
            "planned_target": cand.take_profit,
            "conditions": self._waiting_for(cand),
        }
