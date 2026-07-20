"""Deterministic test execution provider — fixture-oriented, no external deps."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.execution.contracts import ExecutionEnvironment, ProviderKind
from app.execution.providers.paper import PaperExecutionProvider


class DeterministicTestProvider(PaperExecutionProvider):
    """Same simulation core as paper, distinct environment identity for tests."""

    provider_key = "deterministic_test"
    kind = ProviderKind.DETERMINISTIC_TEST

    def __init__(
        self,
        db: Session | None = None,
        *,
        seed: int = 1,
        assumptions: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            db,
            seed=seed,
            assumptions=assumptions or {"commission_bps": 0, "slippage_bps": 0},
        )
        self._environment = ExecutionEnvironment.DETERMINISTIC_TEST
