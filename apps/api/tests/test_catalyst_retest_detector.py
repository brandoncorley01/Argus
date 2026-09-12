"""Unit tests for the paper catalyst_retest detector."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.services.paper_opportunity_detectors import detect_catalyst_retest


def _bar(close: float, *, high: float | None = None, low: float | None = None, vol: float = 100.0):
    c = Decimal(str(close))
    return SimpleNamespace(
        close=c,
        high=Decimal(str(high if high is not None else close * 1.002)),
        low=Decimal(str(low if low is not None else close * 0.998)),
        volume=Decimal(str(vol)),
    )


def test_detect_catalyst_retest_finds_spike_pullback_reclaim() -> None:
    bars = []
    # Quiet base.
    for i in range(20):
        bars.append(_bar(100.0 + i * 0.01, vol=50.0))
    # Impulse ~9% with volume surge into ~109.
    for i in range(8):
        px = 100.2 + i * 1.15
        bars.append(_bar(px, high=px * 1.01, low=px * 0.99, vol=200.0))
    # Cool into retest zone (~3–5% off highs) then reclaim.
    bars.append(_bar(105.0, high=106.0, low=104.2, vol=120.0))
    bars.append(_bar(104.6, high=105.2, low=104.0, vol=110.0))
    bars.append(_bar(105.0, high=105.4, low=104.5, vol=115.0))
    bars.append(_bar(105.8, high=106.1, low=104.9, vol=130.0))  # reclaim

    sig = detect_catalyst_retest(bars)
    assert sig is not None
    assert sig.strategy_key == "catalyst_retest"
    assert sig.bias == "Bullish"
    assert sig.pattern == "catalyst_retest"
    assert sig.stop_loss is not None and sig.take_profit is not None
    assert Decimal(sig.detail["spike_pct"]) >= Decimal("0.06")


def test_detect_catalyst_retest_skips_quiet_tape() -> None:
    bars = [_bar(100.0 + (i % 3) * 0.05, vol=80.0) for i in range(40)]
    assert detect_catalyst_retest(bars) is None
