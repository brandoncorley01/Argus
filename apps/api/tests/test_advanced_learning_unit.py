"""Unit tests for advanced paper learning helpers (no DB)."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.services.advanced_learning_service import (
    ADAPTIVE_DELTA_MAX,
    ADAPTIVE_DELTA_MIN,
    LEARNING_REQUIRED_DAYS,
    VOLUME_NEVER_TRIGGERS_TRADE,
    classify_trade_pattern,
)
from app.services.trading_intelligence_service import TradingIntelligenceService


def test_learning_constants_are_paper_safe() -> None:
    assert LEARNING_REQUIRED_DAYS == 20
    assert VOLUME_NEVER_TRIGGERS_TRADE is True
    assert ADAPTIVE_DELTA_MIN == Decimal("-15")
    assert ADAPTIVE_DELTA_MAX == Decimal("15")


def test_classify_dip_reversal_from_evidence() -> None:
    review = SimpleNamespace(
        detail={"exit_reason": "dip_reversal_target"},
        exit_reason="take_profit",
        market_regime="trend_down",
        outcome="win",
        realized_pnl=Decimal("12.5"),
    )
    assert classify_trade_pattern(review, None) == "dip_reversal"  # type: ignore[arg-type]


def test_classify_high_volume_breakout_from_snapshot_factors() -> None:
    review = SimpleNamespace(
        detail={},
        exit_reason="take_profit",
        market_regime="trend_up",
        outcome="win",
        realized_pnl=Decimal("8"),
    )
    snap = SimpleNamespace(
        detail={
            "contributing_factors": {
                "volume_ok": True,
                "adjustments": ["volume_confirmed"],
            }
        }
    )
    assert classify_trade_pattern(review, snap) == "high_volume_breakout"  # type: ignore[arg-type]


def test_paper_adaptive_confidence_bounded_in_score() -> None:
    svc = TradingIntelligenceService(db=None)  # type: ignore[arg-type]
    conf, _label, factors = svc.score_confidence(
        score=70,
        bias="Bullish",
        risk_status="clear",
        regime="quiet",
        stale=False,
        paper_confidence_delta=Decimal("40"),  # must clamp to +15
    )
    assert "paper_adaptive_confidence" in factors["adjustments"]
    assert factors["paper_confidence_delta_applied"] == 15.0
    assert float(conf) <= 100.0


def test_paper_adaptive_confidence_negative_bounded() -> None:
    svc = TradingIntelligenceService(db=None)  # type: ignore[arg-type]
    conf, _, factors = svc.score_confidence(
        score=80,
        bias="Bullish",
        risk_status="clear",
        regime="quiet",
        stale=False,
        paper_confidence_delta=Decimal("-50"),
    )
    assert factors["paper_confidence_delta_applied"] == -15.0
    assert float(conf) >= 0.0


def test_milestone_keys_cover_requirements() -> None:
    from app.services.advanced_learning_service import MILESTONE_DEFS

    keys = {k for k, _ in MILESTONE_DEFS}
    assert "first_profitable_trade" in keys
    assert "first_profitable_day" in keys
    assert "first_validated_strategy" in keys
    assert "first_successful_dip_reversal" in keys
    assert "first_successful_high_volume_breakout" in keys
    assert "positive_expectancy_after_fees" in keys
    assert "risk_discipline" in keys
    assert "day_20_completion" in keys


def test_content_hash_stable() -> None:
    from app.services.advanced_learning_service import _content_hash

    a = _content_hash({"x": 1, "y": [2, 3]})
    b = _content_hash({"y": [2, 3], "x": 1})
    assert a == b
    assert len(a) == 64


def test_classify_unclassified_when_no_pattern() -> None:
    review = SimpleNamespace(
        detail={},
        exit_reason="manual",
        market_regime="insufficient_data",
        outcome="flat",
        realized_pnl=Decimal("0"),
        closed_at=datetime(2026, 7, 31, tzinfo=UTC),
    )
    assert classify_trade_pattern(review, None) == "unclassified"  # type: ignore[arg-type]
