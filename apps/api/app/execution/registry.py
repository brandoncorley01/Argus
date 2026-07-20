"""Execution provider registry (Phase 12).

Providers are constructed per-call from a factory so each provider can bind
to the current request's database session (paper provider) or remain fully
in-memory (deterministic test provider). No provider here reaches a real
brokerage account.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.execution.contracts import ExecutionProvider

if TYPE_CHECKING:
    pass

ProviderFactory = Callable[[Session], ExecutionProvider]


class ExecutionRegistryError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ExecutionProviderRegistry:
    """Simple in-process provider factory registry."""

    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, provider_key: str, factory: ProviderFactory) -> None:
        self._factories[provider_key] = factory

    def is_registered(self, provider_key: str) -> bool:
        return provider_key in self._factories

    def keys(self) -> list[str]:
        return sorted(self._factories.keys())

    def create(self, provider_key: str, db: Session) -> ExecutionProvider:
        factory = self._factories.get(provider_key)
        if factory is None:
            raise ExecutionRegistryError(
                "unknown_provider", f"No execution provider registered for key: {provider_key}"
            )
        return factory(db)


def _build_default_registry() -> ExecutionProviderRegistry:
    from app.execution.providers.deterministic_test import DeterministicTestProvider
    from app.execution.providers.paper import PaperExecutionProvider

    registry = ExecutionProviderRegistry()
    registry.register("internal_paper", lambda db: PaperExecutionProvider(db))
    registry.register("deterministic_test", lambda _db: DeterministicTestProvider())
    return registry


DEFAULT_REGISTRY = _build_default_registry()
