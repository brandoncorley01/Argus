"""Internal Paper Execution Provider — default, no external account required."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.execution.contracts import (
    TERMINAL_ORDER_STATUSES,
    ExecutionEnvironment,
    ExecutionProvider,
    FillEvent,
    OrderIntent,
    OrderSide,
    OrderState,
    OrderStatus,
    ProviderCapabilities,
    ProviderHealth,
    ProviderKind,
)

# Process-local account store so provider instances share simulated state.
_ACCOUNT_STORE: dict[str, dict[str, Any]] = {}
_ORDER_INDEX: dict[str, str] = {}  # provider_order_id -> portfolio_key


def _portfolio_key(provider_key: str, portfolio_id: uuid.UUID) -> str:
    return f"{provider_key}:{portfolio_id}"


class PaperExecutionProvider(ExecutionProvider):
    """Simulated fills against an in-memory account view (service persists DB).

    Never contacts brokers or exchanges. Short selling is forbidden.
    """

    provider_key = "internal_paper"
    kind = ProviderKind.PAPER

    def __init__(
        self,
        db: Session | None = None,
        *,
        seed: int = 42,
        assumptions: dict[str, Any] | None = None,
    ) -> None:
        self._db = db
        self._seed = seed
        self._assumptions = assumptions or {}
        self._connected = False
        self._environment = ExecutionEnvironment.PAPER

    def configure(
        self, *, seed: int | None = None, assumptions: dict[str, Any] | None = None
    ) -> None:
        if seed is not None:
            self._seed = seed
        if assumptions is not None:
            self._assumptions = assumptions

    @property
    def environment(self) -> ExecutionEnvironment:
        return self._environment

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            status="healthy" if self._connected else "degraded",
            detail="external_account_required=false",
        )

    def readiness(self) -> bool:
        return self._connected

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_replace=False, supports_short_selling=False)

    def ensure_account(
        self, portfolio_id: uuid.UUID, *, cash: Decimal, currency: str = "USD"
    ) -> None:
        key = _portfolio_key(self.provider_key, portfolio_id)
        if key not in _ACCOUNT_STORE:
            _ACCOUNT_STORE[key] = {
                "cash": Decimal(cash),
                "reserved": Decimal("0"),
                "currency": currency,
                "positions": {},
                "orders": {},
                "fills": [],
            }

    def _acct(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        key = _portfolio_key(self.provider_key, portfolio_id)
        if key not in _ACCOUNT_STORE:
            raise KeyError(f"Account not initialized for {portfolio_id}")
        return _ACCOUNT_STORE[key]

    def account_state(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        key = _portfolio_key(self.provider_key, portfolio_id)
        acct = _ACCOUNT_STORE.get(key)
        if acct is None:
            return {"exists": False}
        return {
            "exists": True,
            "cash": str(acct["cash"]),
            "reserved": str(acct["reserved"]),
            "positions": len(acct["positions"]),
        }

    def balances(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        acct = self._acct(portfolio_id)
        cash = Decimal(acct["cash"])
        reserved = Decimal(acct["reserved"])
        return {
            "cash": cash,
            "reserved_cash": reserved,
            "buying_power": cash - reserved,
            "currency": acct["currency"],
        }

    def buying_power(self, portfolio_id: uuid.UUID) -> Decimal:
        return Decimal(self.balances(portfolio_id)["buying_power"])

    def positions(self, portfolio_id: uuid.UUID) -> list[dict[str, Any]]:
        acct = self._acct(portfolio_id)
        return [
            {
                "symbol": symbol,
                "quantity": Decimal(pos["qty"]),
                "average_cost": Decimal(pos["avg_cost"]),
            }
            for symbol, pos in acct["positions"].items()
        ]

    def _mark_price(self, intent: OrderIntent) -> Decimal:
        if intent.limit_price is not None:
            px = Decimal(intent.limit_price)
        else:
            h = abs(hash((self._seed, intent.symbol))) % 10_000
            px = Decimal("100") + Decimal(h) / Decimal("100")
        spread_bps = Decimal(str(self._assumptions.get("spread_bps", 0)))
        slip_bps = Decimal(str(self._assumptions.get("slippage_bps", 0)))
        adj = (spread_bps + slip_bps) / Decimal("10000")
        if intent.side == OrderSide.BUY:
            return px * (Decimal("1") + adj)
        return px * (Decimal("1") - adj)

    def _rejected(
        self, intent: OrderIntent, provider_order_id: str, reason: str
    ) -> tuple[OrderState, list[FillEvent]]:
        state = OrderState(
            provider_order_id=provider_order_id,
            client_order_id=intent.client_order_id,
            status=OrderStatus.REJECTED,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            filled_quantity=Decimal("0"),
            remaining_quantity=intent.quantity,
            avg_fill_price=None,
            limit_price=intent.limit_price,
            reject_reason=reason,
        )
        return state, []

    def submit_order(self, intent: OrderIntent) -> tuple[OrderState, list[FillEvent]]:
        if not self._connected:
            raise RuntimeError("provider not connected")
        acct = self._acct(intent.portfolio_id)
        provider_order_id = f"paper-{uuid.uuid4()}"

        if intent.side == OrderSide.SELL:
            pos = acct["positions"].get(intent.symbol, {"qty": Decimal("0")})
            if Decimal(pos["qty"]) < intent.quantity:
                state, fills = self._rejected(
                    intent, provider_order_id, "short_selling_forbidden"
                )
                acct["orders"][provider_order_id] = state
                _ORDER_INDEX[provider_order_id] = _portfolio_key(
                    self.provider_key, intent.portfolio_id
                )
                return state, fills

        mark = self._mark_price(intent)
        fee_bps = Decimal(str(self._assumptions.get("commission_bps", 0)))
        notional = mark * intent.quantity
        fee = notional * fee_bps / Decimal("10000")
        total_cost = notional + fee

        if intent.side == OrderSide.BUY and total_cost > (
            Decimal(acct["cash"]) - Decimal(acct["reserved"])
        ):
            state, fills = self._rejected(
                intent, provider_order_id, "insufficient_buying_power"
            )
            acct["orders"][provider_order_id] = state
            _ORDER_INDEX[provider_order_id] = _portfolio_key(
                self.provider_key, intent.portfolio_id
            )
            return state, fills

        fill_ratio = Decimal(str(self._assumptions.get("fill_ratio", 1)))
        fill_ratio = min(Decimal("1"), max(Decimal("0"), fill_ratio))
        fill_qty = (intent.quantity * fill_ratio).quantize(Decimal("0.00000001"))
        if fill_qty <= 0:
            state = OrderState(
                provider_order_id=provider_order_id,
                client_order_id=intent.client_order_id,
                status=OrderStatus.NEW,
                symbol=intent.symbol,
                side=intent.side,
                order_type=intent.order_type,
                quantity=intent.quantity,
                filled_quantity=Decimal("0"),
                remaining_quantity=intent.quantity,
                avg_fill_price=None,
                limit_price=intent.limit_price,
            )
            acct["orders"][provider_order_id] = state
            _ORDER_INDEX[provider_order_id] = _portfolio_key(
                self.provider_key, intent.portfolio_id
            )
            return state, []

        fill_notional = mark * fill_qty
        fill_fee = fill_notional * fee_bps / Decimal("10000")
        if intent.side == OrderSide.BUY:
            acct["cash"] = Decimal(acct["cash"]) - fill_notional - fill_fee
            pos = acct["positions"].get(
                intent.symbol, {"qty": Decimal("0"), "avg_cost": Decimal("0")}
            )
            old_qty = Decimal(pos["qty"])
            old_cost = Decimal(pos["avg_cost"])
            new_qty = old_qty + fill_qty
            new_avg = (
                ((old_qty * old_cost) + fill_notional) / new_qty
                if new_qty > 0
                else Decimal("0")
            )
            acct["positions"][intent.symbol] = {"qty": new_qty, "avg_cost": new_avg}
        else:
            pos = acct["positions"][intent.symbol]
            old_qty = Decimal(pos["qty"])
            avg = Decimal(pos["avg_cost"])
            acct["cash"] = Decimal(acct["cash"]) + fill_notional - fill_fee
            _ = (mark - avg) * fill_qty
            new_qty = old_qty - fill_qty
            if new_qty == 0:
                del acct["positions"][intent.symbol]
            else:
                acct["positions"][intent.symbol] = {"qty": new_qty, "avg_cost": avg}

        status = (
            OrderStatus.FILLED
            if fill_qty == intent.quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        state = OrderState(
            provider_order_id=provider_order_id,
            client_order_id=intent.client_order_id,
            status=status,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            filled_quantity=fill_qty,
            remaining_quantity=intent.quantity - fill_qty,
            avg_fill_price=mark,
            limit_price=intent.limit_price,
        )
        fill = FillEvent(
            provider_order_id=provider_order_id,
            fill_id=f"fill-{uuid.uuid4()}",
            symbol=intent.symbol,
            side=intent.side,
            quantity=fill_qty,
            price=mark,
            commission=Decimal("0"),
            fee=fill_fee,
            sequence=len(acct["fills"]) + 1,
        )
        acct["orders"][provider_order_id] = state
        acct["fills"].append(fill)
        _ORDER_INDEX[provider_order_id] = _portfolio_key(
            self.provider_key, intent.portfolio_id
        )
        return state, [fill]

    def cancel_order(self, provider_order_id: str) -> OrderState:
        key = _ORDER_INDEX.get(provider_order_id)
        if key is None or key not in _ACCOUNT_STORE:
            raise KeyError(provider_order_id)
        order: OrderState = _ACCOUNT_STORE[key]["orders"][provider_order_id]
        if order.status in TERMINAL_ORDER_STATUSES:
            return order
        order.status = OrderStatus.CANCELLED
        return order

    def replace_order(
        self,
        provider_order_id: str,
        *,
        quantity: Decimal | None = None,
        limit_price: Decimal | None = None,
    ) -> OrderState:
        self._unsupported("replace_order")
        raise AssertionError("unreachable")

    def get_order(self, provider_order_id: str) -> OrderState:
        key = _ORDER_INDEX[provider_order_id]
        order = _ACCOUNT_STORE[key]["orders"][provider_order_id]
        assert isinstance(order, OrderState)
        return order

    def get_open_orders(self, portfolio_id: uuid.UUID) -> list[OrderState]:
        acct = self._acct(portfolio_id)
        open_statuses = {
            OrderStatus.PENDING_NEW,
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED,
        }
        return [o for o in acct["orders"].values() if o.status in open_statuses]

    def get_fills(self, provider_order_id: str | None = None) -> list[FillEvent]:
        if provider_order_id is not None:
            key = _ORDER_INDEX.get(provider_order_id)
            if key is None:
                return []
            return [
                f
                for f in _ACCOUNT_STORE[key]["fills"]
                if f.provider_order_id == provider_order_id
            ]
        prefix = f"{self.provider_key}:"
        fills: list[FillEvent] = []
        for key, acct in _ACCOUNT_STORE.items():
            if key.startswith(prefix):
                fills.extend(acct["fills"])
        return fills

    def reconcile(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        bal = self.balances(portfolio_id)
        return {
            "cash": str(bal["cash"]),
            "positions": len(self.positions(portfolio_id)),
            "open_orders": len(self.get_open_orders(portfolio_id)),
        }
