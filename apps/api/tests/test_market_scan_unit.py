"""Unit tests for market scan evaluation helpers (no DB)."""

from decimal import Decimal

from app.services.strategy_engine import Bar, SmaCrossoverStrategy


def _bars(n: int, *, up: bool = True) -> list[Bar]:
    out: list[Bar] = []
    price = 100.0
    for i in range(n):
        price = price + (1.0 if up else -0.5)
        out.append(
            Bar(
                open_time=f"2026-01-01T00:{i:02d}:00Z",
                open=price - 0.2,
                high=price + 0.3,
                low=price - 0.4,
                close=price,
                volume=10.0,
            )
        )
    return out


def test_sma_crossover_bullish_on_uptrend() -> None:
    strategy = SmaCrossoverStrategy()
    bars = _bars(40, up=True)
    assert strategy.target_exposure(bars, len(bars) - 1, {"fast": 5, "slow": 20}) > 0


def test_sma_crossover_flat_when_insufficient_history() -> None:
    strategy = SmaCrossoverStrategy()
    bars = _bars(10, up=True)
    assert strategy.target_exposure(bars, len(bars) - 1, {"fast": 5, "slow": 20}) == 0.0


def test_score_decimal_stable() -> None:
    score = Decimal("70") + Decimal("25")
    assert score == Decimal("95")
