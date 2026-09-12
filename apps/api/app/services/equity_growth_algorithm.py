"""Cursor-owned Equity Growth Algorithm (EGA) — paper only.

Mission
-------
Grow Founder Learning Desk equity after costs and reseeds faster than idle cash
(~0 expectancy). Capital preservation brakes remain supreme; this module decides
*how* to deploy when trading is allowed.

Ownership
---------
Cursor is responsible for the success of this algorithm: design, implementation,
measurement, and iteration until paper evidence shows sustained equity growth —
or an honest failure report. Live trading stays locked. Do not claim profitability
without validation evidence.

Success criteria (evidence, not promises)
-----------------------------------------
1. Primary: ``total_pnl`` after reseeds > 0 with ≥20 closed paper trades.
2. Cash benchmark: do not dig equity deeper than idle cash on red days
   (desk sit gate remains authoritative).
3. Strategy quality: only scale size into strategies with positive expectancy
   after costs once the exploration sample is met.
4. Liquidity: never breach the ≥40% cash-available reserve / floors.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

EGA_VERSION = "1.0.0"
EGA_OWNER = "Cursor"

# Lane → fraction of base organic notional. Preserve capital when hurt.
_LANE_SIZE_FRACTION: dict[str, Decimal] = {
    "rebuild_liquidity": Decimal("0"),
    "protect": Decimal("0.55"),
    "recovery": Decimal("0.70"),
    "flat": Decimal("0.85"),
    "building_sample": Decimal("0.90"),
    "too_fast_review": Decimal("0.75"),
    "organic": Decimal("1.00"),
}


def lane_size_fraction(lane: str) -> Decimal:
    return _LANE_SIZE_FRACTION.get(lane, Decimal("0.85"))


def expectancy_size_multiplier(
    *,
    trades: int,
    expectancy_after_costs: Decimal | None,
    lane: str,
) -> Decimal:
    """Scale size to proven edge; shrink exploration while recovering."""
    from app.services.paper_training_service import (
        STRATEGY_EXPLORATION_SAMPLE,
        strategy_loses_to_cash,
    )

    if strategy_loses_to_cash(
        trades=trades, expectancy_after_costs=expectancy_after_costs
    ):
        return Decimal("0")
    if trades < STRATEGY_EXPLORATION_SAMPLE:
        if lane in {"protect", "recovery", "rebuild_liquidity"}:
            return Decimal("0.80")
        return Decimal("0.95")
    if expectancy_after_costs is None:
        return Decimal("0.90")
    if expectancy_after_costs >= Decimal("0.50"):
        return Decimal("1.20")
    if expectancy_after_costs >= Decimal("0.25"):
        return Decimal("1.12")
    if expectancy_after_costs > 0:
        return Decimal("1.05")
    return Decimal("0")


def ega_max_open_positions(*, lane: str, total_pnl: Decimal | None) -> int:
    """Concurrent risk budget for the growth algorithm."""
    if lane in {"rebuild_liquidity", "protect"}:
        return 1
    if lane == "recovery" or (total_pnl is not None and total_pnl <= 0):
        return 2
    if lane == "too_fast_review":
        return 2
    return 3


def strategy_eligible_for_growth(
    *,
    trades: int,
    expectancy_after_costs: Decimal | None,
    lane: str,
    total_pnl: Decimal | None,
) -> bool:
    """While underwater or protecting, only proven winners or thin exploration."""
    from app.services.paper_training_service import (
        STRATEGY_EXPLORATION_SAMPLE,
        strategy_loses_to_cash,
    )

    if strategy_loses_to_cash(
        trades=trades, expectancy_after_costs=expectancy_after_costs
    ):
        return False
    strict = lane in {"protect", "recovery", "rebuild_liquidity"} or (
        total_pnl is not None and total_pnl <= 0
    )
    if not strict:
        return True
    if trades < STRATEGY_EXPLORATION_SAMPLE:
        return True
    return (
        expectancy_after_costs is not None and expectancy_after_costs > 0
    )


def equity_growth_entry_notional(
    *,
    equity: Decimal,
    buying_power: Decimal,
    lane: str,
    trades: int = 0,
    expectancy_after_costs: Decimal | None = None,
) -> Decimal:
    """Deploy size = organic base × lane fraction × expectancy multiplier.

    Still hard-capped by cash reserve and ``LEARNING_MAX_NOTIONAL``.
    """
    from app.services.paper_training_service import (
        LEARNING_MAX_NOTIONAL,
        MIN_DIG_OUT_CASH,
        cash_reserve_target,
        organic_entry_notional,
    )

    base = organic_entry_notional(equity=equity, buying_power=buying_power)
    if base <= 0:
        return Decimal("0")
    lane_frac = lane_size_fraction(lane)
    if lane_frac <= 0:
        return Decimal("0")
    edge = expectancy_size_multiplier(
        trades=trades,
        expectancy_after_costs=expectancy_after_costs,
        lane=lane,
    )
    if edge <= 0:
        return Decimal("0")
    sized = (base * lane_frac * edge).quantize(Decimal("0.01"))
    if sized < MIN_DIG_OUT_CASH:
        return Decimal("0")
    reserve = cash_reserve_target(equity=equity)
    deployable = (buying_power - reserve).quantize(Decimal("0.01"))
    if deployable < MIN_DIG_OUT_CASH:
        return Decimal("0")
    return min(sized, deployable, LEARNING_MAX_NOTIONAL).quantize(Decimal("0.01"))


def plan_equity_growth(
    *,
    starting_cash: Decimal,
    equity: Decimal,
    buying_power: Decimal,
    closed_trades: int,
    max_dd: Decimal | None,
    total_pnl: Decimal | None,
) -> dict[str, Any]:
    """Compute the actionable EGA plan for this cycle (auditable)."""
    from app.services.paper_training_service import organic_growth_pace

    pace = organic_growth_pace(
        starting_cash=starting_cash,
        equity=equity,
        closed_trades=closed_trades,
        max_dd=max_dd,
        cash_available=buying_power,
    )
    lane = str(pace.get("lane") or "flat")
    base_notional = equity_growth_entry_notional(
        equity=equity,
        buying_power=buying_power,
        lane=lane,
    )
    return {
        "version": EGA_VERSION,
        "owner": EGA_OWNER,
        "objective": "beat_idle_cash_after_costs",
        "lane": lane,
        "lane_size_fraction": str(lane_size_fraction(lane)),
        "base_entry_notional": base_notional,
        "max_open_positions": ega_max_open_positions(
            lane=lane, total_pnl=total_pnl
        ),
        "strict_strategy_filter": lane
        in {"protect", "recovery", "rebuild_liquidity"}
        or (total_pnl is not None and total_pnl <= 0),
        "organic_growth": pace,
        "success_criteria": {
            "primary": "total_pnl_after_reseeds > 0 with ≥20 closed trades",
            "cash_benchmark": "do not add risk while losing to idle cash today",
            "liquidity": "keep ≥40% equity as cash available (floor $100)",
        },
        "disclaimer": (
            "Paper only. EGA sizes and filters risk; it does not promise profit "
            "or unlock live trading."
        ),
    }
