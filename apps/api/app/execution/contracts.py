"""Execution provider contracts (Phase 12) — paper trading only.

Defines the provider-neutral surface every execution provider must
implement. No provider in this codebase may reach a real brokerage or
exchange account; ``ExecutionEnvironment.LIVE`` is defined for forward
compatibility only and is rejected everywhere it is checked.
"""

from __future__ import annotations

import enum
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


class OrderSide(enum.StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(enum.StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(enum.StrEnum):
    GTC = "gtc"
    IOC = "ioc"
    DAY = "day"


class OrderStatus(enum.StrEnum):
    PENDING_NEW = "pending_new"
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


TERMINAL_ORDER_STATUSES = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    }
)


class ExecutionEnvironment(enum.StrEnum):
    """``LIVE`` is reserved for a future, explicitly-approved phase.

    No provider registered in this codebase implements ``LIVE``. The gateway
    rejects any intent that is not paper/deterministic_test (see AGENTS.md).
    """

    PAPER = "paper"
    DETERMINISTIC_TEST = "deterministic_test"
    LIVE = "live"


class ProviderKind(enum.StrEnum):
    PAPER = "paper"
    DETERMINISTIC_TEST = "deterministic_test"
    TESTNET_STUB = "testnet_stub"


class ExecutionProviderError(Exception):
    """Base error for execution provider / gateway failures. Fail closed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class UnsupportedOperationError(ExecutionProviderError):
    def __init__(self, operation: str, provider_key: str) -> None:
        super().__init__(
            "unsupported_operation",
            f"Provider '{provider_key}' does not support operation '{operation}'",
        )


class OrderRejectedError(ExecutionProviderError):
    def __init__(self, reason: str) -> None:
        super().__init__("order_rejected", reason)


@dataclass(frozen=True)
class ProviderCapabilities:
    """Explicit capability flags. Absence of a capability must fail closed."""

    supports_market_orders: bool = True
    supports_limit_orders: bool = True
    supports_cancel: bool = True
    supports_replace: bool = False
    supports_partial_fills: bool = True
    supports_fractional_qty: bool = True
    supports_short_selling: bool = False
    supports_margin: bool = False
    supports_leverage: bool = False
    supports_live_trading: bool = False
    max_open_orders: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrderIntent:
    """Provider-neutral order request.

    ``provider_id``, ``environment``, ``portfolio_id``, and
    ``strategy_version_id`` are stamped/validated by the gateway.
    """

    client_order_id: str
    portfolio_id: uuid.UUID
    provider_id: uuid.UUID
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    idempotency_key: str
    limit_price: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    environment: ExecutionEnvironment = ExecutionEnvironment.PAPER
    strategy_version_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderState:
    """Provider-reported order state. Persisted by the caller, not the provider."""

    provider_order_id: str
    client_order_id: str
    status: OrderStatus
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    avg_fill_price: Decimal | None
    limit_price: Decimal | None
    reject_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FillEvent:
    provider_order_id: str
    fill_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal
    fee: Decimal
    sequence: int
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    liquidity: str = "simulated"


@dataclass
class ProviderHealth:
    status: str  # healthy | degraded | unhealthy
    detail: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ExecutionProvider(ABC):
    """Provider-neutral execution surface.

    Providers that cannot honor an operation must raise
    :class:`UnsupportedOperationError` rather than silently no-op.
    """

    provider_key: str
    kind: ProviderKind

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def health(self) -> ProviderHealth: ...

    @abstractmethod
    def readiness(self) -> bool: ...

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    @abstractmethod
    def account_state(self, portfolio_id: uuid.UUID) -> dict[str, Any]: ...

    @abstractmethod
    def balances(self, portfolio_id: uuid.UUID) -> dict[str, Any]: ...

    @abstractmethod
    def buying_power(self, portfolio_id: uuid.UUID) -> Decimal: ...

    @abstractmethod
    def positions(self, portfolio_id: uuid.UUID) -> list[dict[str, Any]]: ...

    @abstractmethod
    def submit_order(self, intent: OrderIntent) -> tuple[OrderState, list[FillEvent]]: ...

    @abstractmethod
    def cancel_order(self, provider_order_id: str) -> OrderState: ...

    @abstractmethod
    def replace_order(
        self,
        provider_order_id: str,
        *,
        quantity: Decimal | None = None,
        limit_price: Decimal | None = None,
    ) -> OrderState: ...

    @abstractmethod
    def get_order(self, provider_order_id: str) -> OrderState: ...

    @abstractmethod
    def get_open_orders(self, portfolio_id: uuid.UUID) -> list[OrderState]: ...

    @abstractmethod
    def get_fills(self, provider_order_id: str | None = None) -> list[FillEvent]: ...

    @abstractmethod
    def reconcile(self, portfolio_id: uuid.UUID) -> dict[str, Any]: ...

    def _unsupported(self, operation: str) -> None:
        raise UnsupportedOperationError(operation, self.provider_key)
