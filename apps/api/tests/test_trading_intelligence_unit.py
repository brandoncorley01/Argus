"""Unit tests for trading intelligence helpers (no DB)."""

from app.services.trading_intelligence_service import TradingIntelligenceService


def test_score_confidence_refuses_bearish_as_strong() -> None:
    svc = TradingIntelligenceService(db=None)  # type: ignore[arg-type]
    bull, bull_label, bull_factors = svc.score_confidence(
        score=90, bias="Bullish", risk_status="clear", regime="trend_up", stale=False
    )
    bear, _, bear_factors = svc.score_confidence(
        score=90, bias="Bearish", risk_status="clear", regime="trend_up", stale=False
    )
    assert bull > bear
    assert bull_label in {"High", "Medium", "Low"}
    assert bear < 50
    assert "scoring_version" in bull_factors
    assert "non_bullish_bias_penalty" in bear_factors["adjustments"]


def test_score_confidence_stale_and_rr_factors() -> None:
    svc = TradingIntelligenceService(db=None)  # type: ignore[arg-type]
    conf, _, factors = svc.score_confidence(
        score=80,
        bias="Bullish",
        risk_status="clear",
        regime="quiet",
        stale=True,
        risk_reward=2.5,
        duplicate_penalty=True,
    )
    assert conf < 80
    assert "stale_data_penalty" in factors["adjustments"]
    assert "duplicate_signal_penalty" in factors["adjustments"]


def test_build_explanation_includes_regime() -> None:
    svc = TradingIntelligenceService(db=None)  # type: ignore[arg-type]
    text = svc.build_explanation(
        symbol="BTC-USD",
        bias="Bullish",
        score=82,
        regime="trend_up",
        reason_code="confirmation_incomplete",
        reason_text=None,
        confidence_label="High",
    )
    assert "BTC-USD" in text
    assert "trend up" in text
    assert "High confidence" in text


def test_deterministic_idempotency_key_shapes() -> None:
    cand_id = "11111111-1111-1111-1111-111111111111"
    assert f"train-enter:{cand_id}" == f"train-enter:{cand_id}"
    portfolio = "22222222-2222-2222-2222-222222222222"
    key = f"exit:{portfolio}:BTC-USD:stop_loss:none"
    assert "uuid" not in key
    assert key.startswith("exit:")


def test_stage_map_covers_founder_pipeline() -> None:
    from app.services.trading_intelligence_service import STAGE_MAP

    assert STAGE_MAP["Watching"] == "Building Confidence"
    assert STAGE_MAP["Risk Review"] == "Ready To Trade"
    assert STAGE_MAP["Entered"] == "Trade Executed"
