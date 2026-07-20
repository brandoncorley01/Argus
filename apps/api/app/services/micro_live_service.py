"""Micro-Live Institution facade (Phase 13) — honest status dashboard DTO.

This is the single source of truth read by ``GET /api/v1/micro-live/status``
and the EOC micro-live page. It never fabricates readiness and never claims
live trading is active.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.paper_trading import ExecutionProvider, ExecutionProviderHealth
from app.services.kill_switch_service import KillSwitchService
from app.services.live_activation_service import LiveActivationService


@dataclass
class MicroLiveStatus:
    live_capable_architecture: bool
    credentials_configured: bool
    live_execution_active: bool
    paper_provider_default: bool
    activation_state: str
    state_version: int
    global_kill_switch_active: bool
    active_capital_policy_version: int | None
    adapter_count: int
    enabled_adapter_count: int
    disclaimer: str


class MicroLiveService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.activation = LiveActivationService(db)
        self.kill_switches = KillSwitchService(db)

    def status(self) -> MicroLiveStatus:
        activation_status = self.activation.status()
        providers = list(
            self.db.scalars(
                select(ExecutionProvider).where(
                    ExecutionProvider.provider_kind == "live_adapter"
                )
            )
        )
        policy_version: int | None = None
        try:
            from app.services.micro_capital_service import MicroCapitalService

            policy_version = MicroCapitalService(self.db).get_active_policy().version
        except Exception:  # noqa: BLE001 — absence of a policy is honestly reported
            policy_version = None

        return MicroLiveStatus(
            live_capable_architecture=True,
            credentials_configured=activation_status.credentials_configured,
            live_execution_active=activation_status.live_execution_active,
            paper_provider_default=True,
            activation_state=activation_status.activation_state,
            state_version=activation_status.state_version,
            global_kill_switch_active=self.kill_switches.is_global_active(),
            active_capital_policy_version=policy_version,
            adapter_count=len(providers),
            enabled_adapter_count=sum(1 for p in providers if p.is_enabled),
            disclaimer=(
                "Live execution architecture is implemented but disabled by "
                "deny-by-default policy. No credentials are configured. The "
                "Internal Paper Execution Provider remains the default and "
                "only active execution path."
            ),
        )

    def list_adapters(self) -> list[tuple[ExecutionProvider, ExecutionProviderHealth | None]]:
        providers = list(
            self.db.scalars(
                select(ExecutionProvider).order_by(ExecutionProvider.provider_key)
            )
        )
        health = {
            h.provider_id: h for h in self.db.scalars(select(ExecutionProviderHealth)).all()
        }
        return [(p, health.get(p.id)) for p in providers]

    def dry_run_validate_order(
        self, *, quantity: Decimal, reference_price: Decimal
    ) -> dict[str, Any]:
        from app.services.micro_capital_service import MicroCapitalService

        activation_status = self.activation.status()
        global_kill = self.kill_switches.is_global_active()
        capital_result = MicroCapitalService(self.db).validate_order(
            quantity=quantity, reference_price=reference_price
        )

        blocking_codes = list(capital_result.blocking_codes)
        if global_kill:
            blocking_codes.append("global_kill_switch_active")
        if activation_status.activation_state != "MICRO_LIVE_ACTIVE":
            blocking_codes.append("live_execution_forbidden")

        return {
            "would_be_allowed": len(blocking_codes) == 0
            and activation_status.activation_state == "MICRO_LIVE_ACTIVE",
            "blocking_codes": blocking_codes,
            "notional": str(capital_result.notional),
            "policy_version": capital_result.policy_version,
            "activation_state": activation_status.activation_state,
            "note": "Dry-run only. No order is ever submitted by this endpoint.",
        }
