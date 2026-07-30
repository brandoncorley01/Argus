"""Paper Training Lab — coaching / automatic practice for simulated trades only.

Never unlocks live trading. Automatic entries still go through paper risk checks,
pause-new-entries, and kill switch.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
from app.services.paper_trading_service import PaperTradingError, PaperTradingService
from app.services.plain_language import (
    BIAS_PLAIN,
    STAGE_PLAIN,
    confidence_from_score,
    plain_rejection,
    readiness_action,
)

MIN_BARS = 25
# Match anticipated live connected-account size for Founder learning.
LEARNING_STARTING_CASH = Decimal("300")
LEARNING_DEFAULT_NOTIONAL = Decimal("30")  # ~10% of $300 book per practice entry
# Take-profit must clear at least this reward:risk multiple of stop distance.
MIN_TAKE_PROFIT_R = Decimal("2")
# Do not take-profit a brand-new entry in the same automation pass.
TAKE_PROFIT_MIN_HOLD_SECONDS = 120
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

        readiness = self._live_readiness(
            closed_count=len(pnls),
            win_rate=win_rate,
            feedback_count=int(feedback_count),
            max_dd=max_dd,
            profit_factor=profit_factor,
        )
        return {
            "paper_trades_completed": len(pnls),
            "win_rate": win_rate,
            "total_paper_pnl": total_pnl,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "profit_factor": profit_factor,
            "maximum_drawdown": max_dd if pnls else None,
            "trades_with_founder_feedback": int(feedback_count),
            "live_readiness": readiness["status"],
            "live_readiness_detail": readiness["detail"],
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
        self, *, portfolio_id: uuid.UUID, actor: AuthenticatedPrincipal | None
    ) -> list[dict[str, Any]]:
        """If Automatic Practice is on, enter clear Watching candidates (paper only)."""
        settings = self.get_or_create_settings(portfolio_id)
        if settings.mode != "automatic":
            return []
        portfolio = self.db.get(PaperPortfolio, portfolio_id)
        if portfolio is None or portfolio.kill_switch_active or portfolio.pause_new_entries_active:
            return []
        opened: list[dict[str, Any]] = []
        cands = list(
            self.db.scalars(
                select(MarketScanCandidate)
                .where(
                    MarketScanCandidate.stage == "Watching",
                    MarketScanCandidate.risk_status == "clear",
                )
                .order_by(desc(MarketScanCandidate.score))
                .limit(5)
            )
        )
        # Prefer freshest Watching candidates with usable score.
        cands = [
            c
            for c in cands
            if float(c.score or 0) >= 55.0
        ] or cands
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
            portfolio_id, within_seconds=600
        )
        resolved = self._resolve_actor(actor, portfolio)
        if resolved is None:
            return []
        for cand in cands:
            if cand.symbol in open_syms:
                continue
            if cand.symbol in recently_exited:
                continue
            if (cand.bias or "") != "Bullish":
                # Long-only: never convert bearish/neutral probes into buys.
                continue
            try:
                order = self._open_paper_from_candidate(
                    portfolio_id=portfolio_id,
                    cand=cand,
                    notional=settings.default_notional,
                    actor=resolved,
                )
                cand.stage = "Entered"
                opened.append({"symbol": cand.symbol, "order_id": str(order.id)})
                open_syms.add(cand.symbol)
                self.audit.append(
                    action="paper.training.auto_enter",
                    resource_type="paper_order",
                    resource_id=str(order.id),
                    actor_user_id=resolved.user.id,
                    payload={"symbol": cand.symbol, "candidate_id": str(cand.id)},
                )
                self._emit_decision_event(
                    symbol=cand.symbol,
                    outcome="entered",
                    title=f"Entered {cand.symbol}",
                    detail=(
                        f"Opened a ${settings.default_notional} paper long. "
                        f"Stop {cand.stop_loss}; target {cand.take_profit}."
                    ),
                    reason_code="auto_enter",
                )
            except (PaperTradingError, PaperTrainingError) as exc:
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
        stop = cand.stop_loss
        target = cand.take_profit
        if stop is None or stop >= price:
            stop = price * (Decimal("1") - Decimal("0.01"))
        if target is None or target <= price:
            risk = price - stop
            if risk <= 0:
                risk = price * Decimal("0.01")
            target = price + (risk * MIN_TAKE_PROFIT_R)
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
                "entry_zone": str(cand.entry_zone) if cand.entry_zone is not None else str(price),
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
                )
        except Exception:  # noqa: BLE001 — intelligence must never block paper entry
            pass
        self.db.commit()
        self.db.refresh(order)
        return order

    def evaluate_paper_exits(
        self, *, portfolio_id: uuid.UUID, actor: AuthenticatedPrincipal | None = None
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
            stop = plan.get("stop_loss")
            target = plan.get("take_profit")
            if (
                target is None
                and stop is not None
                and pos.average_cost
                and pos.average_cost > stop
            ):
                risk = pos.average_cost - stop
                target = pos.average_cost + (risk * MIN_TAKE_PROFIT_R)
            if stop is None and target is None:
                continue
            mark, _mark_at = self.paper._latest_mark(pos.symbol)
            if mark is None:
                continue
            reason: str | None = None
            if stop is not None and mark <= stop:
                reason = "stop_loss"
            elif target is not None and mark >= target:
                # Ultra-tight targets were closing entries in the same scan pass.
                # Stop-loss still fires immediately; take-profit needs a minimum hold.
                held_ok = self._position_held_seconds(portfolio_id, pos.symbol) >= (
                    TAKE_PROFIT_MIN_HOLD_SECONDS
                )
                if held_ok:
                    reason = "take_profit"
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
                else f"Take-profit hit at {mark} (target {target})."
            )
            self._emit_decision_event(
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
        symbol: str,
        outcome: str,
        title: str,
        detail: str,
        reason_code: str,
    ) -> None:
        """Write enter/exit into market_scan_events so the Decided pane can show why."""
        try:
            from app.models.market_scan import MarketScanEvent

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
                    occurred_at=datetime.now(UTC),
                    payload={},
                )
            )
        except Exception:  # noqa: BLE001 — UI stream must never block trading
            pass

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

            runtime = PaperExecutionProvider(self.db)
            runtime.ensure_account(portfolio.id, cash=starting_cash)
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
