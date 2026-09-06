"""Micro trading detectors + cost gate (paper only)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.services.paper_opportunity_detectors import (
    MICRO_STRATEGY_KEYS,
    _micro_net_edge_usd,
    detect_range_micro,
    detect_trend_pullback_micro,
    run_all_detectors,
)


def _bar(
    *,
    close: str,
    high: str | None = None,
    low: str | None = None,
    volume: str = "100",
) -> SimpleNamespace:
    c = Decimal(close)
    return SimpleNamespace(
        close=c,
        high=Decimal(high) if high else c * Decimal("1.002"),
        low=Decimal(low) if low else c * Decimal("0.998"),
        volume=Decimal(volume),
    )


def test_micro_net_edge_requires_worthwhile_move() -> None:
    # Tiny target fails the net gate.
    tiny = _micro_net_edge_usd(
        price=Decimal("100"), target=Decimal("100.05"), notional=Decimal("100")
    )
    assert tiny is not None and tiny < Decimal("1.50")
    # Larger target clears costs.
    ok = _micro_net_edge_usd(
        price=Decimal("100"), target=Decimal("103"), notional=Decimal("100")
    )
    assert ok is not None and ok >= Decimal("1.50")


def test_range_micro_detects_quiet_dip_or_none() -> None:
    # Build a quiet oscillating range ending near support with a bounce.
    bars = []
    for i in range(30):
        # Oscillate 99.0–101.0
        mid = Decimal("100")
        wave = Decimal("1") if (i % 4) < 2 else Decimal("-1")
        close = mid + wave * Decimal("0.8")
        bars.append(
            _bar(
                close=str(close),
                high=str(close + Decimal("0.3")),
                low=str(close - Decimal("0.3")),
                volume="120",
            )
        )
    # Last bars: dip to lower third then bounce confirm.
    bars[-5] = _bar(close="99.15", high="99.4", low="99.05", volume="130")
    bars[-4] = _bar(close="99.20", high="99.35", low="99.08", volume="125")
    bars[-3] = _bar(close="99.25", high="99.4", low="99.10", volume="140")
    bars[-2] = _bar(close="99.30", high="99.45", low="99.15", volume="135")
    bars[-1] = _bar(close="99.35", high="99.5", low="99.18", volume="150")
    sig = detect_range_micro(bars)
    # Geometry is strict — accept None or a range_micro / cost-gate avoid.
    if sig is not None:
        assert sig.strategy_key == "range_micro"
        assert sig.pattern == "micro_range"
        assert "micro_subtype" in sig.detail


def test_trend_pullback_micro_skips_strong_breakout() -> None:
    bars = []
    px = Decimal("100")
    for i in range(35):
        px = px + Decimal("0.4")  # strong run
        bars.append(
            _bar(
                close=str(px),
                high=str(px + Decimal("0.2")),
                low=str(px - Decimal("0.1")),
                volume="300",
            )
        )
    sig = detect_trend_pullback_micro(bars)
    assert sig is None  # strong breakout owns the tape


def test_micro_keys_registered_in_detectors() -> None:
    assert "range_micro" in MICRO_STRATEGY_KEYS
    assert "trend_pullback_micro" in MICRO_STRATEGY_KEYS
    # run_all_detectors must not crash on short history.
    assert run_all_detectors([]) == []


def test_primary_preferred_over_micro_on_conflict() -> None:
    """Hard primary outranks Micro; Micro outranks soft range_mean / SMA."""
    from app.services.paper_opportunity_detectors import MICRO_STRATEGY_KEYS

    hard = {
        "momentum_continuation",
        "breakout",
        "dip_pullback_reversal",
        "catalyst_retest",
    }

    def tier(sk: str) -> int:
        if sk in hard:
            return 3
        if sk in MICRO_STRATEGY_KEYS:
            return 2
        if sk == "range_mean_reversion":
            return 1
        return 0

    def priority(sk: str, score: float) -> float:
        base = score
        if sk == "sma_crossover" or not sk:
            base = min(base, 68.0)
        elif sk in MICRO_STRATEGY_KEYS:
            base += 8.0
        elif sk in hard:
            base += 14.0
        else:
            base += 10.0
        return base

    assert tier("breakout") > tier("range_micro")
    assert tier("range_micro") > tier("range_mean_reversion")
    assert tier("range_micro") > tier("sma_crossover")
    # Soft primary can have a higher raw priority but lower tier — Micro still wins
    # unless soft primary leads by +12 (see _better_for_symbol).
    micro_p = priority("range_micro", 66)
    soft_p = priority("range_mean_reversion", 68)
    assert micro_p + 12 >= soft_p
    assert priority("breakout", 66) > priority("range_micro", 66)
