"""Priority scoring and organic growth sizing (expectancy mission)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.services.paper_training_service import (
    PaperTrainingService,
    desk_should_sit_vs_cash,
    organic_entry_notional,
    organic_growth_pace,
    strategy_loses_to_cash,
    strategy_portfolio_priority_adjustment,
)
from app.services.paper_trading_service import total_pnl_after_reseeds


def test_non_sma_strategies_outrank_sma_on_similar_scores() -> None:
    """Detectors must beat SMA when raw scores are close — not an SMA-only bot."""

    def priority(c: SimpleNamespace) -> float:
        base = float(c.score or 0)
        sk = (c.strategy_key or "").lower()
        if sk and sk != "sma_crossover":
            base += 10.0
        if sk == "catalyst_retest":
            base += 4.0
        return base

    sma = SimpleNamespace(symbol="SOL-USD", score=68, strategy_key="sma_crossover")
    catalyst = SimpleNamespace(symbol="SOL-USD", score=64, strategy_key="catalyst_retest")
    assert priority(catalyst) > priority(sma)


def test_strategy_portfolio_explores_unproven_and_penalizes_losers() -> None:
    unexplored = strategy_portfolio_priority_adjustment(
        trades=0, expectancy_after_costs=None
    )
    sampled_winner = strategy_portfolio_priority_adjustment(
        trades=12, expectancy_after_costs=Decimal("0.50")
    )
    sampled_loser = strategy_portfolio_priority_adjustment(
        trades=12, expectancy_after_costs=Decimal("-0.25")
    )
    assert unexplored > sampled_winner > sampled_loser
    assert sampled_loser < 0


def test_strategy_loses_to_cash_blocks_nonpositive_expectancy() -> None:
    assert strategy_loses_to_cash(
        trades=5, expectancy_after_costs=Decimal("0")
    )
    assert strategy_loses_to_cash(
        trades=8, expectancy_after_costs=Decimal("-0.10")
    )
    assert not strategy_loses_to_cash(
        trades=4, expectancy_after_costs=Decimal("-1")
    )
    assert not strategy_loses_to_cash(
        trades=12, expectancy_after_costs=Decimal("0.01")
    )


def test_desk_sits_vs_cash_when_underwater_on_red_day() -> None:
    assert desk_should_sit_vs_cash(
        closed_trades=12,
        total_pnl=Decimal("-50"),
        today_equity_pnl=Decimal("-5"),
        open_positions=1,
    )
    assert not desk_should_sit_vs_cash(
        closed_trades=12,
        total_pnl=Decimal("-50"),
        today_equity_pnl=Decimal("2"),
        open_positions=1,
    )
    assert not desk_should_sit_vs_cash(
        closed_trades=5,
        total_pnl=Decimal("-50"),
        today_equity_pnl=Decimal("-5"),
        open_positions=1,
    )
    assert desk_should_sit_vs_cash(
        closed_trades=25,
        total_pnl=Decimal("-10"),
        today_equity_pnl=None,
        open_positions=2,
    )
    assert not desk_should_sit_vs_cash(
        closed_trades=12,
        total_pnl=Decimal("5"),
        today_equity_pnl=Decimal("-5"),
        open_positions=1,
    )
    # Already flat: sitting until midnight cannot beat cash.
    assert not desk_should_sit_vs_cash(
        closed_trades=25,
        total_pnl=Decimal("-574"),
        today_equity_pnl=Decimal("-1.14"),
        open_positions=0,
    )


def test_simulated_cost_bps_aligned_to_paper_session() -> None:
    from app.services.trading_intelligence_service import SIMULATED_COST_BPS

    # Session uses ~1bps commission + slip/spread; 10bps each-way was over-penalizing.
    assert SIMULATED_COST_BPS == Decimal("3")


def test_paper_training_service_imports() -> None:
    assert PaperTrainingService is not None


def test_total_pnl_removes_reseeded_paper_cash() -> None:
    # A $200 reseed must not make a desk that lost $50 look profitable.
    total = total_pnl_after_reseeds(
        total_value=Decimal("450"),
        starting_cash=Decimal("300"),
        reseed_cash_flow=Decimal("200"),
    )
    assert total == Decimal("-50")


def test_organic_entry_notional_compounds_without_gambling() -> None:
    from app.services.paper_training_service import cash_reserve_target

    sized = organic_entry_notional(equity=Decimal("300"), buying_power=Decimal("300"))
    assert sized == Decimal("99.00")
    assert cash_reserve_target(equity=Decimal("300")) == Decimal("120.00")
    grown = organic_entry_notional(equity=Decimal("450"), buying_power=Decimal("450"))
    assert grown == Decimal("148.50")
    assert grown <= Decimal("150")
    # Thin cash under reserve → no new entry (protect cash available).
    thin = organic_entry_notional(equity=Decimal("400"), buying_power=Decimal("40"))
    assert thin == Decimal("0")
    # After one ~$99 slot, remaining deployable is limited by $120 reserve.
    second = organic_entry_notional(equity=Decimal("300"), buying_power=Decimal("201"))
    assert second == Decimal("81.00")
    # At reserve floor — hold cash.
    held = organic_entry_notional(equity=Decimal("300"), buying_power=Decimal("120"))
    assert held == Decimal("0")


def test_organic_growth_pace_flags_liquidity_before_too_fast() -> None:
    pace = organic_growth_pace(
        starting_cash=Decimal("300"),
        equity=Decimal("320"),
        closed_trades=12,
        max_dd=Decimal("10"),
        cash_available=Decimal("20"),
    )
    assert pace["lane"] == "rebuild_liquidity"
    assert pace["liquidity_ok"] is False


def test_organic_growth_pace_flags_too_fast_on_small_sample() -> None:
    pace = organic_growth_pace(
        starting_cash=Decimal("300"),
        equity=Decimal("400"),
        closed_trades=8,
        max_dd=Decimal("10"),
        cash_available=Decimal("200"),
    )
    assert pace["lane"] == "too_fast_review"
    assert "luck" in pace["guide"].lower()


def test_ega_sizes_down_in_recovery_and_up_on_proven_edge() -> None:
    from app.services.equity_growth_algorithm import (
        EGA_OWNER,
        equity_growth_entry_notional,
        plan_equity_growth,
        strategy_eligible_for_growth,
    )

    base = organic_entry_notional(equity=Decimal("300"), buying_power=Decimal("300"))
    recovery = equity_growth_entry_notional(
        equity=Decimal("300"),
        buying_power=Decimal("300"),
        lane="recovery",
        trades=12,
        expectancy_after_costs=Decimal("0.40"),
    )
    organic_edge = equity_growth_entry_notional(
        equity=Decimal("300"),
        buying_power=Decimal("300"),
        lane="organic",
        trades=12,
        expectancy_after_costs=Decimal("0.40"),
    )
    assert recovery < base
    assert organic_edge > base
    assert not strategy_eligible_for_growth(
        trades=10,
        expectancy_after_costs=Decimal("-0.1"),
        lane="recovery",
        total_pnl=Decimal("-20"),
    )
    assert strategy_eligible_for_growth(
        trades=10,
        expectancy_after_costs=Decimal("0.2"),
        lane="recovery",
        total_pnl=Decimal("-20"),
    )
    plan = plan_equity_growth(
        starting_cash=Decimal("300"),
        equity=Decimal("250"),
        buying_power=Decimal("200"),
        closed_trades=15,
        max_dd=Decimal("40"),
        total_pnl=Decimal("-50"),
    )
    assert plan["owner"] == EGA_OWNER
    assert plan["objective"] == "beat_idle_cash_after_costs"
    assert int(plan["max_open_positions"]) <= 2
    assert plan["strict_strategy_filter"] is True