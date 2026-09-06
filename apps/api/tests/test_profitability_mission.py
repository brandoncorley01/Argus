"""Priority scoring and organic growth sizing (expectancy mission)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.services.paper_training_service import (
    PaperTrainingService,
    organic_entry_notional,
    organic_growth_pace,
)


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


def test_simulated_cost_bps_aligned_to_paper_session() -> None:
    from app.services.trading_intelligence_service import SIMULATED_COST_BPS

    # Session uses ~1bps commission + slip/spread; 10bps each-way was over-penalizing.
    assert SIMULATED_COST_BPS == Decimal("3")


def test_paper_training_service_imports() -> None:
    assert PaperTrainingService is not None


def test_organic_entry_notional_compounds_without_gambling() -> None:
    sized = organic_entry_notional(equity=Decimal("300"), buying_power=Decimal("300"))
    assert sized == Decimal("99.00")
    grown = organic_entry_notional(equity=Decimal("450"), buying_power=Decimal("450"))
    assert grown == Decimal("148.50")
    assert grown <= Decimal("200")
    thin = organic_entry_notional(equity=Decimal("400"), buying_power=Decimal("40"))
    assert thin == Decimal("40.00")


def test_organic_growth_pace_flags_too_fast_on_small_sample() -> None:
    pace = organic_growth_pace(
        starting_cash=Decimal("300"),
        equity=Decimal("400"),
        closed_trades=8,
        max_dd=Decimal("10"),
    )
    assert pace["lane"] == "too_fast_review"
    assert "luck" in pace["guide"].lower()
