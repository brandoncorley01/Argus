"""Paper trading institutional service — gateway-mediated, no live brokers."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.execution.contracts import (
    ExecutionEnvironment,
    OrderIntent,
    OrderSide,
    OrderType,
)
from app.execution.gateway import ExecutionGateway, ExecutionGatewayError
from app.models.paper_trading import (
    ExecutionProvider,
    ExecutionProviderHealth,
    PaperCashLedger,
    PaperFill,
    PaperOrder,
    PaperOrderEvent,
    PaperOrderStatus,
    PaperPortfolio,
    PaperPosition,
    PaperReplayCheckpoint,
    PaperReport,
    PaperRiskBreach,
    PaperRiskLimit,
    PaperSession,
    PortfolioStatus,
    SessionStatus,
)
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal


class PaperTradingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


class PaperTradingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.gateway = ExecutionGateway(db)

    # --- providers ---

    def list_providers(self) -> list[tuple[ExecutionProvider, ExecutionProviderHealth | None]]:
        providers = list(
            self.db.scalars(select(ExecutionProvider).order_by(ExecutionProvider.provider_key))
        )
        health = {
            h.provider_id: h for h in self.db.scalars(select(ExecutionProviderHealth)).all()
        }
        return [(p, health.get(p.id)) for p in providers]

    def default_provider(self) -> ExecutionProvider:
        row = self.db.scalar(
            select(ExecutionProvider).where(ExecutionProvider.is_default.is_(True))
        )
        if row is None:
            raise PaperTradingError("provider_missing", "No default execution provider")
        return row

    def get_provider(self, provider_key: str) -> ExecutionProvider:
        row = self.db.scalar(
            select(ExecutionProvider).where(ExecutionProvider.provider_key == provider_key)
        )
        if row is None:
            raise PaperTradingError("provider_not_found", provider_key)
        return row

    # --- portfolios ---

    def create_portfolio(
        self,
        *,
        name: str,
        initial_cash: Decimal,
        actor: AuthenticatedPrincipal,
        currency: str = "USD",
    ) -> PaperPortfolio:
        provider = self.default_provider()
        portfolio = PaperPortfolio(
            name=name,
            currency=currency,
            cash_balance=initial_cash,
            reserved_cash=Decimal("0"),
            status=PortfolioStatus.ACTIVE.value,
            kill_switch_active=False,
            default_provider_id=provider.id,
            owner_user_id=actor.user.id,
        )
        self.db.add(portfolio)
        self.db.flush()
        self.db.add(
            PaperCashLedger(
                portfolio_id=portfolio.id,
                entry_type="initial_deposit",
                amount=initial_cash,
                balance_after=initial_cash,
                note="Paper virtual cash — not real capital",
            )
        )
        self.audit.append(
            action="paper.portfolio.create",
            resource_type="paper_portfolio",
            resource_id=str(portfolio.id),
            actor_user_id=actor.user.id,
            payload={"name": name, "initial_cash": str(initial_cash)},
        )
        self.db.commit()
        self.db.refresh(portfolio)
        return portfolio

    def list_portfolios(self) -> list[PaperPortfolio]:
        return list(
            self.db.scalars(select(PaperPortfolio).order_by(PaperPortfolio.created_at.desc()))
        )

    def get_portfolio(self, portfolio_id: uuid.UUID) -> PaperPortfolio:
        row = self.db.get(PaperPortfolio, portfolio_id)
        if row is None:
            raise PaperTradingError("portfolio_not_found", str(portfolio_id))
        return row

    def set_kill_switch(
        self, portfolio_id: uuid.UUID, *, active: bool, actor: AuthenticatedPrincipal
    ) -> PaperPortfolio:
        portfolio = self.get_portfolio(portfolio_id)
        portfolio.kill_switch_active = active
        if active:
            portfolio.status = PortfolioStatus.SUSPENDED.value
        elif portfolio.status == PortfolioStatus.SUSPENDED.value:
            portfolio.status = PortfolioStatus.ACTIVE.value
        self.audit.append(
            action="paper.kill_switch",
            resource_type="paper_portfolio",
            resource_id=str(portfolio.id),
            actor_user_id=actor.user.id,
            payload={"active": active},
        )
        self.db.commit()
        self.db.refresh(portfolio)
        return portfolio

    # --- sessions ---

    def open_session(
        self,
        *,
        portfolio_id: uuid.UUID,
        actor: AuthenticatedPrincipal,
        strategy_version_id: uuid.UUID | None = None,
        seed: int = 42,
        assumptions: dict[str, Any] | None = None,
    ) -> PaperSession:
        portfolio = self.get_portfolio(portfolio_id)
        session = PaperSession(
            portfolio_id=portfolio.id,
            strategy_version_id=strategy_version_id,
            provider_id=portfolio.default_provider_id,
            status=SessionStatus.OPEN.value,
            seed=seed,
            assumptions=assumptions or {
                "commission_bps": 1,
                "slippage_bps": 1,
                "spread_bps": 1,
                "fill_ratio": 1,
            },
            created_by_user_id=actor.user.id,
        )
        self.db.add(session)
        self.db.flush()
        self.audit.append(
            action="paper.session.open",
            resource_type="paper_session",
            resource_id=str(session.id),
            actor_user_id=actor.user.id,
            payload={"portfolio_id": str(portfolio_id)},
        )
        self.db.commit()
        self.db.refresh(session)
        return session

    def list_sessions(self, portfolio_id: uuid.UUID) -> list[PaperSession]:
        return list(
            self.db.scalars(
                select(PaperSession)
                .where(PaperSession.portfolio_id == portfolio_id)
                .order_by(PaperSession.started_at.desc())
            )
        )

    # --- risk ---

    def add_risk_limit(
        self,
        *,
        portfolio_id: uuid.UUID,
        name: str,
        limit_type: str,
        threshold: Decimal,
        actor: AuthenticatedPrincipal,
        symbol: str | None = None,
    ) -> PaperRiskLimit:
        self.get_portfolio(portfolio_id)
        limit = PaperRiskLimit(
            portfolio_id=portfolio_id,
            name=name,
            limit_type=limit_type,
            threshold=threshold,
            symbol=symbol,
        )
        self.db.add(limit)
        self.db.flush()
        self.audit.append(
            action="paper.risk_limit.create",
            resource_type="paper_risk_limit",
            resource_id=str(limit.id),
            actor_user_id=actor.user.id,
            payload={"limit_type": limit_type, "threshold": str(threshold)},
        )
        self.db.commit()
        self.db.refresh(limit)
        return limit

    def list_risk_limits(self, portfolio_id: uuid.UUID) -> list[PaperRiskLimit]:
        return list(
            self.db.scalars(
                select(PaperRiskLimit).where(PaperRiskLimit.portfolio_id == portfolio_id)
            )
        )

    def list_breaches(self, portfolio_id: uuid.UUID) -> list[PaperRiskBreach]:
        return list(
            self.db.scalars(
                select(PaperRiskBreach)
                .where(PaperRiskBreach.portfolio_id == portfolio_id)
                .order_by(PaperRiskBreach.detected_at.desc())
            )
        )

    def _check_pretrade(
        self,
        portfolio: PaperPortfolio,
        *,
        symbol: str,
        side: str,
        quantity: Decimal,
        ref_price: Decimal,
    ) -> None:
        notional = quantity * ref_price
        limits = [
            lim
            for lim in self.list_risk_limits(portfolio.id)
            if lim.is_enabled
        ]
        for lim in limits:
            if lim.limit_type == "notional" and notional > lim.threshold:
                self._breach(portfolio, lim, "notional_exceeded", notional, None)
                raise PaperTradingError("risk_blocked", "Notional limit exceeded")
            if lim.limit_type == "order_frequency":
                count = self.db.scalar(
                    select(func.count())
                    .select_from(PaperOrder)
                    .where(PaperOrder.portfolio_id == portfolio.id)
                ) or 0
                if count >= int(lim.threshold):
                    self._breach(portfolio, lim, "order_frequency", Decimal(count), None)
                    raise PaperTradingError("risk_blocked", "Order frequency limit exceeded")
            if lim.limit_type == "instrument" and lim.symbol == symbol:
                pos = self.db.scalar(
                    select(PaperPosition).where(
                        PaperPosition.portfolio_id == portfolio.id,
                        PaperPosition.symbol == symbol,
                    )
                )
                current = Decimal(pos.quantity) if pos else Decimal("0")
                projected = current + quantity if side == "buy" else current - quantity
                if projected > lim.threshold:
                    self._breach(portfolio, lim, "instrument_limit", projected, None)
                    raise PaperTradingError("risk_blocked", "Instrument limit exceeded")
            if lim.limit_type == "gross_exposure":
                positions = self.list_positions(portfolio.id)
                gross = sum(
                    (abs(p.quantity) * (p.average_cost or Decimal("0")) for p in positions),
                    Decimal("0"),
                ) + notional
                if gross > lim.threshold:
                    self._breach(portfolio, lim, "gross_exposure", gross, None)
                    raise PaperTradingError("risk_blocked", "Gross exposure limit exceeded")

    def _breach(
        self,
        portfolio: PaperPortfolio,
        lim: PaperRiskLimit | None,
        limit_type: str,
        value: Decimal,
        order_id: uuid.UUID | None,
    ) -> None:
        self.db.add(
            PaperRiskBreach(
                portfolio_id=portfolio.id,
                limit_id=lim.id if lim else None,
                limit_type=limit_type,
                message=f"{limit_type} breach value={value}",
                detail={"value": str(value)},
                order_id=order_id,
            )
        )

    # --- orders ---

    def submit_order(
        self,
        *,
        portfolio_id: uuid.UUID,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        actor: AuthenticatedPrincipal,
        limit_price: Decimal | None = None,
        session_id: uuid.UUID | None = None,
        strategy_version_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
        client_order_id: str | None = None,
    ) -> PaperOrder:
        portfolio = self.get_portfolio(portfolio_id)
        key = idempotency_key or str(uuid.uuid4())
        existing = self.db.scalar(
            select(PaperOrder).where(PaperOrder.idempotency_key == key)
        )
        if existing:
            return existing

        provider = self.db.get(ExecutionProvider, portfolio.default_provider_id)
        assert provider is not None
        assumptions: dict[str, Any] = {
            "commission_bps": 1,
            "slippage_bps": 1,
            "spread_bps": 1,
            "fill_ratio": 1,
        }
        seed = 42
        if session_id:
            session = self.db.get(PaperSession, session_id)
            if session is None or session.portfolio_id != portfolio.id:
                raise PaperTradingError("session_invalid", "Session not found for portfolio")
            assumptions = dict(session.assumptions or assumptions)
            seed = session.seed
            if strategy_version_id is None:
                strategy_version_id = session.strategy_version_id

        ref_price = limit_price or Decimal("100")
        self._check_pretrade(
            portfolio, symbol=symbol.upper(), side=side, quantity=quantity, ref_price=ref_price
        )

        client_id = client_order_id or str(uuid.uuid4())
        try:
            env = ExecutionEnvironment(provider.environment)
        except ValueError as exc:
            raise PaperTradingError(
                "live_execution_forbidden",
                f"Unsupported provider environment: {provider.environment}",
            ) from exc

        order = PaperOrder(
            portfolio_id=portfolio.id,
            provider_id=provider.id,
            session_id=session_id,
            strategy_version_id=strategy_version_id,
            client_order_id=client_id,
            idempotency_key=key,
            symbol=symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            status=PaperOrderStatus.PENDING.value,
            environment=provider.environment,
            created_by_user_id=actor.user.id,
        )
        self.db.add(order)
        self.db.flush()
        self._event(
            order,
            "submitted",
            None,
            PaperOrderStatus.PENDING.value,
            {"client_order_id": client_id},
        )

        try:
            result, fill_events = self.gateway.submit(
                provider_key=provider.provider_key,
                intent=OrderIntent(
                    portfolio_id=portfolio.id,
                    provider_id=provider.id,
                    symbol=order.symbol,
                    side=OrderSide(side),
                    order_type=OrderType(order_type),
                    quantity=quantity,
                    limit_price=limit_price,
                    client_order_id=client_id,
                    idempotency_key=key,
                    strategy_version_id=strategy_version_id,
                    session_id=session_id,
                    environment=env,
                ),
                environment=provider.environment,
                kill_switch_active=portfolio.kill_switch_active,
                portfolio_status=portfolio.status,
                cash=portfolio.cash_balance,
                seed=seed,
                assumptions=assumptions,
            )
        except ExecutionGatewayError as exc:
            order.status = PaperOrderStatus.REJECTED.value
            order.reject_reason = exc.message
            self._event(
                order,
                "rejected",
                PaperOrderStatus.PENDING.value,
                order.status,
                {"code": exc.code},
            )
            self.db.commit()
            self.db.refresh(order)
            raise PaperTradingError(exc.code, exc.message) from exc

        order.provider_order_id = result.provider_order_id
        order.status = result.status.value
        order.filled_quantity = result.filled_quantity
        order.average_fill_price = result.avg_fill_price
        order.reject_reason = result.reject_reason
        self._event(
            order,
            "provider_response",
            PaperOrderStatus.PENDING.value,
            order.status,
            {"provider_order_id": result.provider_order_id},
        )

        for fill in fill_events:
            prior = self.db.scalar(
                select(PaperFill).where(
                    PaperFill.provider_id == provider.id,
                    PaperFill.provider_fill_id == fill.fill_id,
                )
            )
            if prior:
                continue
            self.db.add(
                PaperFill(
                    order_id=order.id,
                    portfolio_id=portfolio.id,
                    provider_id=provider.id,
                    provider_fill_id=fill.fill_id,
                    symbol=fill.symbol,
                    side=fill.side.value,
                    quantity=fill.quantity,
                    price=fill.price,
                    fee=fill.fee + fill.commission,
                    filled_at=fill.occurred_at,
                )
            )

        runtime = self.gateway.get_provider(
            provider.provider_key, seed=seed, assumptions=assumptions
        )
        bal = runtime.balances(portfolio.id)
        cash = Decimal(bal["cash"])
        reserved = Decimal(bal["reserved_cash"])
        delta = cash - portfolio.cash_balance
        if delta != 0:
            self.db.add(
                PaperCashLedger(
                    portfolio_id=portfolio.id,
                    entry_type="provider_sync",
                    amount=delta,
                    balance_after=cash,
                    reference_type="paper_order",
                    reference_id=str(order.id),
                )
            )
        portfolio.cash_balance = cash
        portfolio.reserved_cash = reserved

        for ppos in runtime.positions(portfolio.id):
            symbol_key = str(ppos["symbol"])
            qty = Decimal(ppos["quantity"])
            avg = Decimal(ppos["average_cost"])
            row = self.db.scalar(
                select(PaperPosition).where(
                    PaperPosition.portfolio_id == portfolio.id,
                    PaperPosition.symbol == symbol_key,
                )
            )
            if row is None:
                self.db.add(
                    PaperPosition(
                        portfolio_id=portfolio.id,
                        symbol=symbol_key,
                        quantity=qty,
                        average_cost=avg,
                    )
                )
            else:
                row.quantity = qty
                row.average_cost = avg
        held = {str(p["symbol"]) for p in runtime.positions(portfolio.id)}
        for row in self.list_positions(portfolio.id):
            if row.symbol not in held:
                self.db.delete(row)

        self.audit.append(
            action="paper.order.submit",
            resource_type="paper_order",
            resource_id=str(order.id),
            actor_user_id=actor.user.id,
            payload={
                "symbol": order.symbol,
                "side": order.side,
                "status": order.status,
                "provider": provider.provider_key,
                "environment": order.environment,
            },
        )
        self.db.commit()
        self.db.refresh(order)
        return order

    def _apply_fill_to_portfolio(
        self,
        portfolio: PaperPortfolio,
        side: str,
        symbol: str,
        qty: Decimal,
        price: Decimal,
        fee: Decimal,
        order_id: uuid.UUID,
    ) -> None:
        pos = self.db.scalar(
            select(PaperPosition).where(
                PaperPosition.portfolio_id == portfolio.id,
                PaperPosition.symbol == symbol,
            )
        )
        if side == "buy":
            notional = qty * price
            if pos is None:
                self.db.add(
                    PaperPosition(
                        portfolio_id=portfolio.id,
                        symbol=symbol,
                        quantity=qty,
                        average_cost=price,
                    )
                )
            else:
                new_qty = pos.quantity + qty
                pos.average_cost = ((pos.quantity * pos.average_cost) + notional) / new_qty
                pos.quantity = new_qty
            self.db.add(
                PaperCashLedger(
                    portfolio_id=portfolio.id,
                    entry_type="fill_buy",
                    amount=-(notional + fee),
                    balance_after=portfolio.cash_balance - notional - fee,
                    reference_type="paper_order",
                    reference_id=str(order_id),
                )
            )
            portfolio.cash_balance = portfolio.cash_balance - notional - fee
        else:
            if pos is None or pos.quantity < qty:
                raise PaperTradingError("short_forbidden", "Cannot sell more than held")
            realized = (price - pos.average_cost) * qty
            pos.realized_pnl = pos.realized_pnl + realized
            pos.quantity = pos.quantity - qty
            notional = qty * price
            self.db.add(
                PaperCashLedger(
                    portfolio_id=portfolio.id,
                    entry_type="fill_sell",
                    amount=notional - fee,
                    balance_after=portfolio.cash_balance + notional - fee,
                    reference_type="paper_order",
                    reference_id=str(order_id),
                )
            )
            portfolio.cash_balance = portfolio.cash_balance + notional - fee

    def _event(
        self,
        order: PaperOrder,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        payload: dict[str, Any],
    ) -> None:
        seq = (
            self.db.scalar(
                select(func.coalesce(func.max(PaperOrderEvent.sequence_number), 0)).where(
                    PaperOrderEvent.order_id == order.id
                )
            )
            or 0
        ) + 1
        self.db.add(
            PaperOrderEvent(
                order_id=order.id,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                payload=payload,
                sequence_number=seq,
            )
        )

    def cancel_order(
        self, order_id: uuid.UUID, *, actor: AuthenticatedPrincipal
    ) -> PaperOrder:
        order = self.db.get(PaperOrder, order_id)
        if order is None:
            raise PaperTradingError("order_not_found", str(order_id))
        self.get_portfolio(order.portfolio_id)
        provider = self.db.get(ExecutionProvider, order.provider_id)
        assert provider is not None
        if not order.provider_order_id:
            raise PaperTradingError("order_not_ack", "No provider order id")
        result = self.gateway.cancel(
            provider_key=provider.provider_key,
            provider_order_id=order.provider_order_id,
        )
        prev = order.status
        order.status = result.status.value
        self._event(order, "cancelled", prev, order.status, {})
        self.audit.append(
            action="paper.order.cancel",
            resource_type="paper_order",
            resource_id=str(order.id),
            actor_user_id=actor.user.id,
            payload={},
        )
        self.db.commit()
        self.db.refresh(order)
        return order

    def list_orders(self, portfolio_id: uuid.UUID) -> list[PaperOrder]:
        return list(
            self.db.scalars(
                select(PaperOrder)
                .where(PaperOrder.portfolio_id == portfolio_id)
                .order_by(PaperOrder.created_at.desc())
            )
        )

    def list_fills(self, portfolio_id: uuid.UUID) -> list[PaperFill]:
        return list(
            self.db.scalars(
                select(PaperFill)
                .where(PaperFill.portfolio_id == portfolio_id)
                .order_by(PaperFill.filled_at.desc())
            )
        )

    def list_positions(self, portfolio_id: uuid.UUID) -> list[PaperPosition]:
        return list(
            self.db.scalars(
                select(PaperPosition).where(PaperPosition.portfolio_id == portfolio_id)
            )
        )

    # --- replay / reports ---

    def checkpoint_session(
        self, session_id: uuid.UUID, *, actor: AuthenticatedPrincipal
    ) -> PaperReplayCheckpoint:
        session = self.db.get(PaperSession, session_id)
        if session is None:
            raise PaperTradingError("session_not_found", str(session_id))
        portfolio = self.get_portfolio(session.portfolio_id)
        positions = [
            {
                "symbol": p.symbol,
                "quantity": str(p.quantity),
                "average_cost": str(p.average_cost),
                "realized_pnl": str(p.realized_pnl),
            }
            for p in self.list_positions(portfolio.id)
        ]
        seq = (
            self.db.scalar(
                select(func.coalesce(func.max(PaperReplayCheckpoint.sequence_number), 0)).where(
                    PaperReplayCheckpoint.session_id == session_id
                )
            )
            or 0
        ) + 1
        blob = {
            "cash_balance": str(portfolio.cash_balance),
            "positions": positions,
            "seed": session.seed,
            "assumptions": session.assumptions,
        }
        cp = PaperReplayCheckpoint(
            session_id=session_id, sequence_number=seq, state_blob=blob
        )
        self.db.add(cp)
        self.audit.append(
            action="paper.replay.checkpoint",
            resource_type="paper_session",
            resource_id=str(session_id),
            actor_user_id=actor.user.id,
            payload={"sequence": seq},
        )
        self.db.commit()
        self.db.refresh(cp)
        return cp

    def generate_report(
        self,
        *,
        portfolio_id: uuid.UUID,
        report_type: str,
        actor: AuthenticatedPrincipal,
    ) -> PaperReport:
        portfolio = self.get_portfolio(portfolio_id)
        content = {
            "portfolio_id": str(portfolio.id),
            "cash_balance": str(portfolio.cash_balance),
            "orders": [
                {
                    "id": str(o.id),
                    "symbol": o.symbol,
                    "side": o.side,
                    "status": o.status,
                    "quantity": str(o.quantity),
                    "filled": str(o.filled_quantity),
                }
                for o in self.list_orders(portfolio_id)
            ],
            "positions": [
                {
                    "symbol": p.symbol,
                    "quantity": str(p.quantity),
                    "average_cost": str(p.average_cost),
                    "realized_pnl": str(p.realized_pnl),
                }
                for p in self.list_positions(portfolio_id)
            ],
            "fills": [
                {
                    "id": str(f.id),
                    "symbol": f.symbol,
                    "qty": str(f.quantity),
                    "price": str(f.price),
                }
                for f in self.list_fills(portfolio_id)
            ],
            "generated_at": _utcnow().isoformat(),
            "disclaimer": "Paper trading — not real capital performance",
        }
        report = PaperReport(
            portfolio_id=portfolio_id,
            report_type=report_type,
            content=content,
            content_hash=_hash(content),
            is_immutable=True,
            created_by_user_id=actor.user.id,
        )
        self.db.add(report)
        self.db.flush()
        self.audit.append(
            action="paper.report.create",
            resource_type="paper_report",
            resource_id=str(report.id),
            actor_user_id=actor.user.id,
            payload={"report_type": report_type},
        )
        self.db.commit()
        self.db.refresh(report)
        return report

    def list_reports(self, portfolio_id: uuid.UUID) -> list[PaperReport]:
        return list(
            self.db.scalars(
                select(PaperReport)
                .where(PaperReport.portfolio_id == portfolio_id)
                .order_by(PaperReport.created_at.desc())
            )
        )
