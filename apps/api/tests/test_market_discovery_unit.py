"""Unit tests for Coinbase market discovery classify/rank helpers (no network)."""

from decimal import Decimal

from app.services.market_discovery_service import (
    RankedMarket,
    classify_opportunity,
    rank_score_for,
)


def test_classify_peak_exhaustion_only_on_extreme_tip() -> None:
    label = classify_opportunity(
        last=Decimal("118.5"),
        open_24h=Decimal("100"),
        high_24h=Decimal("118.8"),
        low_24h=Decimal("99"),
        change_pct=Decimal("0.185"),
        range_pct=Decimal("0.19"),
    )
    assert label == "peak_exhaustion"


def test_classify_strong_day_near_high_is_breakout_not_rejected() -> None:
    # Former late_stage_chase zone (~9% up near high) must reach Radar as
    # breakout/continuation — not invisible "exhaustion".
    label = classify_opportunity(
        last=Decimal("109"),
        open_24h=Decimal("100"),
        high_24h=Decimal("109.5"),
        low_24h=Decimal("99"),
        change_pct=Decimal("0.09"),
        range_pct=Decimal("0.10"),
    )
    assert label == "breakout_continuation"


def test_classify_late_stage_chase_only_when_extended() -> None:
    label = classify_opportunity(
        last=Decimal("113"),
        open_24h=Decimal("100"),
        high_24h=Decimal("113.5"),
        low_24h=Decimal("99"),
        change_pct=Decimal("0.13"),
        range_pct=Decimal("0.14"),
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


def test_rank_score_penalizes_exhaustion_more_than_late_chase() -> None:
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
    late = rank_score_for(
        RankedMarket(
            **{
                **base.__dict__,
                "opportunity_class": "late_stage_chase",
                "rank_score": Decimal("0"),
            }
        )
    )
    peak = rank_score_for(
        RankedMarket(
            **{
                **base.__dict__,
                "opportunity_class": "peak_exhaustion",
                "rank_score": Decimal("0"),
            }
        )
    )
    assert good > late > peak
