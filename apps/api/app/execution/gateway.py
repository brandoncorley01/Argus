"""Execution Gateway — sole institutional path to execution providers."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.execution.contracts import (
    ExecutionEnvironment,
    ExecutionProvider,
    FillEvent,
    OrderIntent,
    OrderState,
)
from app.execution.providers.paper import PaperExecutionProvider
from app.execution.registry import DEFAULT_REGISTRY, ExecutionProviderRegistry


class ExecutionGatewayError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ExecutionGateway:
    """Validates intents, enforces kill switch / paper-only, routes to provider."""

    ALLOWED_ENVIRONMENTS = {
        ExecutionEnvironment.PAPER.value,
        ExecutionEnvironment.DETERMINISTIC_TEST.value,
    }

    def __init__(
        self,
        db: Session,
        registry: ExecutionProviderRegistry | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or DEFAULT_REGISTRY
        self._instances: dict[str, ExecutionProvider] = {}

    def get_provider(
        self,
        provider_key: str,
        *,
        seed: int = 42,
        assumptions: dict[str, Any] | None = None,
    ) -> ExecutionProvider:
        if provider_key not in self._instances:
            self._instances[provider_key] = self.registry.create(provider_key, self.db)
        provider = self._instances[provider_key]
        if isinstance(provider, PaperExecutionProvider):
            provider.configure(seed=seed, assumptions=assumptions)
        return provider

    def submit(
        self,
        *,
        provider_key: str,
        intent: OrderIntent,
        environment: str,
        kill_switch_active: bool,
        portfolio_status: str,
        cash: Decimal,
        seed: int = 42,
        assumptions: dict[str, Any] | None = None,
    ) -> tuple[OrderState, list[FillEvent]]:
        if environment not in self.ALLOWED_ENVIRONMENTS:
            raise ExecutionGatewayError(
                "live_execution_forbidden",
                "Execution Gateway rejects non-paper environments",
            )
        if kill_switch_active:
            raise ExecutionGatewayError("kill_switch", "Portfolio kill switch is active")
        if portfolio_status != "active":
            raise ExecutionGatewayError(
                "portfolio_inactive", f"Portfolio status is {portfolio_status}"
            )
        if intent.quantity <= 0:
            raise ExecutionGatewayError("invalid_quantity", "Quantity must be positive")
        if intent.environment.value not in self.ALLOWED_ENVIRONMENTS:
            raise ExecutionGatewayError(
                "live_execution_forbidden",
                "Order intent environment is not paper/test",
            )

        provider = self.get_provider(provider_key, seed=seed, assumptions=assumptions)
        if isinstance(provider, PaperExecutionProvider):
            if provider.environment.value not in self.ALLOWED_ENVIRONMENTS:
                raise ExecutionGatewayError(
                    "live_execution_forbidden",
                    "Provider environment is not paper/test",
                )
            provider.ensure_account(intent.portfolio_id, cash=cash)
        if not provider.readiness():
            provider.connect()
        return provider.submit_order(intent)

    def cancel(
        self,
        *,
        provider_key: str,
        provider_order_id: str,
        kill_switch_active: bool = False,
    ) -> OrderState:
        _ = kill_switch_active  # cancellations still allowed under kill switch
        provider = self.get_provider(provider_key)
        if not provider.readiness():
            provider.connect()
        return provider.cancel_order(provider_order_id)

    def reconcile(
        self, *, provider_key: str, portfolio_id: UUID
    ) -> dict[str, Any]:
        provider = self.get_provider(provider_key)
        if not provider.readiness():
            provider.connect()
        return provider.reconcile(portfolio_id)
