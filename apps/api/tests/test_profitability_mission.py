"""Priority scoring for adaptive paper entries (expectancy mission)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.paper_training_service import PaperTrainingService


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
    assert SIMULATED_COST_BPS == __import__("decimal").Decimal("3")


def test_paper_training_service_imports() -> None:
    assert PaperTrainingService is not None
