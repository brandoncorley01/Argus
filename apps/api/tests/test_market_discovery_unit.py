"""Unit tests for Coinbase market discovery classify/rank helpers (no network)."""

from decimal import Decimal

from app.services.market_discovery_service import (
    RankedMarket,
    classify_opportunity,
    rank_score_for,
)


def test_classify_peak_exhaustion_on_extended_high() -> None:
    label = classify_opportunity(
        last=Decimal("112"),
        open_24h=Decimal("100"),
        high_24h=Decimal("112.5"),
        low_24h=Decimal("99"),
        change_pct=Decimal("0.12"),
        range_pct=Decimal("0.12"),
    )
    assert label == "peak_exhaustion"


def test_classify_late_stage_chase() -> None:
    label = classify_opportunity(
        last=Decimal("109"),
        open_24h=Decimal("100"),
        high_24h=Decimal("109.5"),
        low_24h=Decimal("99"),
        change_pct=Decimal("0.09"),
        range_pct=Decimal("0.10"),
    )
    assert label == "late_stage_chase"


def test_classify_pullback_retest() -> None:
    label = classify_opportunity(
        last=Decimal("104"),
        open_24h=Decimal("100"),
        high_24h=Decimal("108"),
        low_24h=Decimal("99"),
        change_pct=Decimal("0.04"),
        range_pct=Decimal("0.09"),
    )
    assert label == "pullback_retest"


def test_classify_early_breakout() -> None:
    label = classify_opportunity(
        last=Decimal("105"),
        open_24h=Decimal("100"),
        high_24h=Decimal("105.5"),
        low_24h=Decimal("99"),
        change_pct=Decimal("0.05"),
        range_pct=Decimal("0.05"),
    )
    assert label == "early_breakout"


def test_classify_breakout_continuation() -> None:
    label = classify_opportunity(
        last=Decimal("105"),
        open_24h=Decimal("100"),
        high_24h=Decimal("105.5"),
        low_24h=Decimal("99"),
        change_pct=Decimal("0.05"),
        range_pct=Decimal("0.07"),
    )
    assert label == "breakout_continuation"


def test_rank_score_penalizes_exhaustion() -> None:
    base = RankedMarket(
        symbol="AAA-USD",
        dollar_volume=Decimal("5000000"),
        last=Decimal("10"),
        open_24h=Decimal("9"),
        high_24h=Decimal("10.2"),
        low_24h=Decimal("8.8"),
        change_pct=Decimal("0.10"),
        range_pct=Decimal("0.14"),
        relative_volume=Decimal("2"),
        spread_pct=Decimal("0.002"),
        opportunity_class="early_breakout",
        rank_score=Decimal("0"),
    )
    good = rank_score_for(base)
    bad = rank_score_for(
        RankedMarket(
            **{
                **base.__dict__,
                "opportunity_class": "peak_exhaustion",
                "rank_score": Decimal("0"),
            }
        )
    )
    assert good > bad
