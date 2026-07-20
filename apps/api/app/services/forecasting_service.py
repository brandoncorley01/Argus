"""Deterministic forecasting service (Phase 14).

Every scenario output is a pure, deterministic function of caller-supplied
``inputs``. There is no random number generation, no external market data
fetch, and no implicit claim about real future performance — every
generated scenario carries an explicit ``assumption_note`` restating that
it is a hypothetical projection derived only from the inputs provided.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.treasury import ForecastScenario, ForecastScenarioType
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal

_ASSUMPTION_NOTE = (
    "Deterministic projection computed only from the inputs supplied. Not a "
    "market prediction, not investment advice, and not a claim about real "
    "future performance."
)


class ForecastingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _dec(inputs: dict[str, Any], key: str) -> Decimal:
    if key not in inputs:
        raise ForecastingError("missing_input", f"Missing required input: {key}")
    try:
        return Decimal(str(inputs[key]))
    except (InvalidOperation, ValueError) as exc:
        raise ForecastingError("invalid_input", f"Input '{key}' must be numeric") from exc


def _int(inputs: dict[str, Any], key: str) -> int:
    if key not in inputs:
        raise ForecastingError("missing_input", f"Missing required input: {key}")
    try:
        return int(inputs[key])
    except (TypeError, ValueError) as exc:
        raise ForecastingError("invalid_input", f"Input '{key}' must be an integer") from exc


class ForecastingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def list_scenarios(self, *, scenario_type: str | None = None) -> list[ForecastScenario]:
        stmt = select(ForecastScenario).order_by(ForecastScenario.as_of.desc())
        if scenario_type is not None:
            stmt = stmt.where(ForecastScenario.scenario_type == scenario_type)
        return list(self.db.scalars(stmt))

    def get_scenario(self, scenario_id: Any) -> ForecastScenario:
        row = self.db.get(ForecastScenario, scenario_id)
        if row is None:
            raise ForecastingError("not_found", f"Forecast scenario {scenario_id} not found")
        return row

    def create_scenario(
        self,
        *,
        name: str,
        scenario_type: str,
        inputs: dict[str, Any],
        actor: AuthenticatedPrincipal,
    ) -> ForecastScenario:
        try:
            type_enum = ForecastScenarioType(scenario_type)
        except ValueError as exc:
            raise ForecastingError(
                "invalid_scenario_type", f"Unknown scenario_type: {scenario_type}"
            ) from exc

        outputs = self._compute(type_enum, inputs)
        row = ForecastScenario(
            name=name,
            scenario_type=type_enum.value,
            as_of=_utcnow(),
            inputs=inputs,
            outputs=outputs,
            is_deterministic=True,
            generated_by_user_id=actor.user.id,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="treasury.forecast.generate",
            resource_type="forecast_scenario",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"scenario_type": type_enum.value, "name": name},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def _compute(
        self, scenario_type: ForecastScenarioType, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        if scenario_type is ForecastScenarioType.CASH_FLOW:
            return self._compute_cash_flow(inputs)
        if scenario_type is ForecastScenarioType.CAPITAL_REQUIREMENT:
            return self._compute_capital_requirement(inputs)
        if scenario_type is ForecastScenarioType.DRAWDOWN:
            return self._compute_drawdown(inputs)
        if scenario_type is ForecastScenarioType.PROVIDER_OUTAGE:
            return self._compute_provider_outage(inputs)
        if scenario_type is ForecastScenarioType.STRATEGY_SUSPENSION:
            return self._compute_strategy_suspension(inputs)
        raise ForecastingError("invalid_scenario_type", f"Unhandled scenario_type: {scenario_type}")

    def _compute_cash_flow(self, inputs: dict[str, Any]) -> dict[str, Any]:
        starting_balance = _dec(inputs, "starting_balance")
        periods = _int(inputs, "periods")
        net_flow_per_period = _dec(inputs, "net_flow_per_period")
        if periods < 0 or periods > 3650:
            raise ForecastingError("invalid_input", "periods must be between 0 and 3650")
        balances = []
        running = starting_balance
        for _ in range(periods):
            running = running + net_flow_per_period
            balances.append(str(running))
        return {
            "projected_balances": balances,
            "ending_balance": str(running),
            "assumption_note": _ASSUMPTION_NOTE,
        }

    def _compute_capital_requirement(self, inputs: dict[str, Any]) -> dict[str, Any]:
        target_allocations_total = _dec(inputs, "target_allocations_total")
        buffer_pct = _dec(inputs, "buffer_pct")
        required_capital = target_allocations_total * (Decimal("1") + buffer_pct)
        return {
            "required_capital": str(required_capital),
            "buffer_amount": str(required_capital - target_allocations_total),
            "assumption_note": _ASSUMPTION_NOTE,
        }

    def _compute_drawdown(self, inputs: dict[str, Any]) -> dict[str, Any]:
        starting_balance = _dec(inputs, "starting_balance")
        max_drawdown_pct = _dec(inputs, "max_drawdown_pct")
        if max_drawdown_pct < 0 or max_drawdown_pct > 1:
            raise ForecastingError("invalid_input", "max_drawdown_pct must be between 0 and 1")
        loss_amount = starting_balance * max_drawdown_pct
        return {
            "floor_balance": str(starting_balance - loss_amount),
            "loss_amount": str(loss_amount),
            "assumption_note": _ASSUMPTION_NOTE,
        }

    def _compute_provider_outage(self, inputs: dict[str, Any]) -> dict[str, Any]:
        affected_provider_exposure = _dec(inputs, "affected_provider_exposure")
        outage_days = _int(inputs, "outage_days")
        daily_capital_cost_pct = _dec(inputs, "daily_capital_cost_pct")
        if outage_days < 0 or outage_days > 365:
            raise ForecastingError("invalid_input", "outage_days must be between 0 and 365")
        estimated_cost = affected_provider_exposure * daily_capital_cost_pct * Decimal(outage_days)
        return {
            "estimated_cost": str(estimated_cost),
            "outage_days": outage_days,
            "assumption_note": _ASSUMPTION_NOTE,
        }

    def _compute_strategy_suspension(self, inputs: dict[str, Any]) -> dict[str, Any]:
        strategy_allocation = _dec(inputs, "strategy_allocation")
        remaining_days_in_period = _int(inputs, "remaining_days_in_period")
        expected_daily_return_pct = _dec(inputs, "expected_daily_return_pct")
        if remaining_days_in_period < 0 or remaining_days_in_period > 3650:
            raise ForecastingError(
                "invalid_input", "remaining_days_in_period must be between 0 and 3650"
            )
        days = Decimal(remaining_days_in_period)
        foregone = strategy_allocation * expected_daily_return_pct * days
        return {
            "foregone_return_estimate": str(foregone),
            "note": (
                "Hypothetical foregone-return estimate derived purely from the "
                "supplied expected_daily_return_pct input — not a validated or "
                "observed strategy return."
            ),
            "assumption_note": _ASSUMPTION_NOTE,
        }
