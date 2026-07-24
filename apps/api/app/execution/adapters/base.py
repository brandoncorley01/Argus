"""Shared base for optional live-adapter scaffolds (Phase 13).

``LiveAdapterBase`` implements the full :class:`ExecutionProvider` contract
in a way that never contacts a network and never submits a real order,
regardless of caller input. Concrete adapters (``coinbase.py``, ``kraken.py``,
``ibkr.py``) only need to declare identity metadata.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.execution.contracts import (
    ExecutionEnvironment,
    ExecutionProvider,
    FillEvent,
    LiveExecutionForbiddenError,
    OrderIntent,
    OrderState,
    ProviderCapabilities,
    ProviderHealth,
    ProviderKind,
    VerificationStatus,
)


@dataclass(frozen=True)
class AdapterDescriptor:
    """Institutional identity/capability metadata for an optional adapter.

    Purely descriptive — never used to bypass any gate.
    """

    provider_key: str
    display_name: str
    environment: ExecutionEnvironment
    verification_status: VerificationStatus
    required_credential_refs: tuple[str, ...]
    description: str


def normalize_events(raw_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Provider-neutral normalization stub for adapter fill/order events.

    No adapter in this codebase ever produces real events (no network calls
    are made), so this only normalizes fixture/mock payloads used in
    contract tests.
    """
    normalized: list[dict[str, Any]] = []
    for event in raw_events:
        normalized.append(
            {
                "kind": str(event.get("kind", "unknown")),
                "payload": dict(event.get("payload", {})),
            }
        )
    return normalized


class LiveAdapterBase(ExecutionProvider):
    """Deny-by-default adapter skeleton — never reaches a real account.

    Every method here fails safe: connectivity is always reported as
    ``disabled``/``credentials_unavailable``, and mutating operations either
    raise :class:`LiveExecutionForbiddenError` (``submit_order``) or
    :class:`UnsupportedOperationError` (everything else that would require a
    live account this codebase does not have).
    """

    kind = ProviderKind.LIVE_ADAPTER
    descriptor: AdapterDescriptor

    def __init__(self) -> None:
        self._connected = False

    def _sign_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Signing boundary stub — NEVER called with real network I/O.

        Concrete adapters would place HMAC/API-key signing here once
        credentials are configured and the adapter is certified. In this
        codebase it only raises, so no signature material is ever computed
        from a real secret value.
        """
        raise LiveExecutionForbiddenError(
            self.provider_key, "signing is disabled: no certified live path exists"
        )

    def connect(self) -> None:
        # Never opens a socket/HTTP session. Always reports disabled.
        self._connected = False

    def disconnect(self) -> None:
        self._connected = False

    def health(self) -> ProviderHealth:
        return ProviderHealth(status="disabled", detail="credentials_unavailable")

    def readiness(self) -> bool:
        return False

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_market_orders=False,
            supports_limit_orders=False,
            supports_cancel=False,
            supports_replace=False,
            supports_partial_fills=False,
            supports_fractional_qty=False,
            supports_short_selling=False,
            supports_margin=False,
            supports_leverage=False,
            supports_live_trading=False,
        )

    def account_state(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        return {"exists": False, "reason": "credentials_unavailable"}

    def balances(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        self._unsupported("balances")
        raise AssertionError("unreachable")

    def buying_power(self, portfolio_id: uuid.UUID) -> Decimal:
        self._unsupported("buying_power")
        raise AssertionError("unreachable")

    def positions(self, portfolio_id: uuid.UUID) -> list[dict[str, Any]]:
        self._unsupported("positions")
        raise AssertionError("unreachable")

    def submit_order(self, intent: OrderIntent) -> tuple[OrderState, list[FillEvent]]:
        raise LiveExecutionForbiddenError(
            self.provider_key, "no adapter in this codebase may submit live orders"
        )

    def cancel_order(self, provider_order_id: str) -> OrderState:
        self._unsupported("cancel_order")
        raise AssertionError("unreachable")

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
        self._unsupported("get_order")
        raise AssertionError("unreachable")

    def get_open_orders(self, portfolio_id: uuid.UUID) -> list[OrderState]:
        return []

    def get_fills(self, provider_order_id: str | None = None) -> list[FillEvent]:
        return []

    def reconcile(self, portfolio_id: uuid.UUID) -> dict[str, Any]:
        return {"status": "unavailable", "reason": "credentials_unavailable"}
