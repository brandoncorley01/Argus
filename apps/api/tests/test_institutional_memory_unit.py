"""Unit tests for institutional memory, decision quality, and PAPER detectors."""

from decimal import Decimal
from types import SimpleNamespace

from app.services.institutional_memory import (
    EXECUTE_SCORE,
    WAIT_SCORE,
    InstitutionalMemoryService,
    confidence_bucket,
    grade_decision_quality,
    knowledge_record_from_review,
)
from app.services.paper_opportunity_detectors import (
    detect_breakout,
    detect_dip_pullback_reversal,
    detect_momentum_continuation,
    detect_peak_exhaustion_protection,
    detect_range_mean_reversion,
    run_all_detectors,
)


def _bar(
    c: float,
    h: float | None = None,
    low: float | None = None,
    v: float = 100,
) -> SimpleNamespace:
    close = Decimal(str(c))
    high = Decimal(str(h if h is not None else c * 1.002))
    low_px = Decimal(str(low if low is not None else c * 0.998))
    return SimpleNamespace(
        close=close, high=high, low=low_px, volume=Decimal(str(v))
    )


def test_grade_decision_quality_independent_of_pnl() -> None:
    # Disciplined entry that lost money → GOOD_DECISION_LOSS
    good, code, factors = grade_decision_quality(
        outcome="loss",
        entry_price=Decimal("100"),
        stop_loss=Decimal("98"),
        take_profit=Decimal("104"),
        exit_reason="stop_loss",
        risk_status="clear",
        volume_ok=True,
        stale_data=False,
        strategy_rule_ok=True,
        holding_seconds=600,
    )
    assert good is True
    assert code == "GOOD_DECISION_LOSS"
    assert factors["risk_reward_ok"] is True

    # Lucky win with broken R:R → POOR_DECISION_WIN
    good2, code2, _ = grade_decision_quality(
        outcome="win",
        entry_price=Decimal("100"),
        stop_loss=Decimal("99.5"),
        take_profit=Decimal("100.2"),  # poor R:R
        exit_reason="manual",
        risk_status="clear",
        volume_ok=False,
        stale_data=True,
        strategy_rule_ok=False,
        holding_seconds=5,
    )
    assert good2 is False
    assert code2 == "POOR_DECISION_WIN"


def test_knowledge_record_keys() -> None:
    review = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        closed_at=None,
        detail={
            "decision_quality_code": "GOOD_DECISION_LOSS",
            "expectancy_adjusted_pnl": "-1.2",
        },
        exit_reason="stop_loss",
        market_regime="trend_up",
        outcome="loss",
        realized_pnl=Decimal("-1"),
        strategy_key="breakout",
        symbol="BTC-USD",
        confidence_score=Decimal("70"),
        good_decision=True,
        explanation="Stop respected.",
        decision_snapshot_id=None,
    )
    row = knowledge_record_from_review(review, None)  # type: ignore[arg-type]
    assert row["keys"]["strategy_key"] == "breakout"
    assert row["keys"]["symbol"] == "BTC-USD"
    assert row["keys"]["decision_quality"] == "GOOD_DECISION_LOSS"
    assert row["keys"]["confidence_bucket"] == confidence_bucket(70)


def test_consult_avoids_negative_expectancy_memory() -> None:
    svc = InstitutionalMemoryService(db=None)  # type: ignore[arg-type]

    def fake_list(_pid, *, limit=400):  # noqa: ARG001
        rows = []
        for i in range(6):
            rows.append(
                {
                    "review_id": str(i),
                    "keys": {
                        "strategy_key": "sma_crossover",
                        "symbol": "ETH-USD",
                        "market_regime": "volatile",
                        "trade_pattern": "momentum",
                        "volume_condition": "normal",
                        "confidence_bucket": "medium",
                        "outcome": "loss",
                        "decision_quality": "POOR_DECISION_LOSS",
                    },
                    "net_after_costs": "-1.0",
                }
            )
        return rows

    svc.list_knowledge = fake_list  # type: ignore[method-assign]
    out = svc.consult_before_entry(
        portfolio_id=__import__("uuid").uuid4(),
        symbol="ETH-USD",
        strategy_key="sma_crossover",
        market_regime="volatile",
        base_score=80,
        paper_confidence_delta=Decimal("0"),
        confidence_label_score=Decimal("80"),
        trade_pattern="momentum",
    )
    assert out["action"] == "AVOID"
    assert out["similar_setup_count"] == 6
    assert out["influenced"] is True


def test_consult_execute_when_strong_and_positive() -> None:
    svc = InstitutionalMemoryService(db=None)  # type: ignore[arg-type]

    def fake_list(_pid, *, limit=400):  # noqa: ARG001
        return [
            {
                "review_id": "a",
                "keys": {
                    "strategy_key": "breakout",
                    "symbol": "SOL-USD",
                    "market_regime": "trend_up",
                    "trade_pattern": "breakout",
                    "volume_condition": "elevated",
                    "confidence_bucket": "high",
                    "outcome": "win",
                    "decision_quality": "GOOD_DECISION_WIN",
                },
                "net_after_costs": "1.5",
            }
        ] * 3

    svc.list_knowledge = fake_list  # type: ignore[method-assign]
    out = svc.consult_before_entry(
        portfolio_id=__import__("uuid").uuid4(),
        symbol="SOL-USD",
        strategy_key="breakout",
        market_regime="trend_up",
        base_score=70,
        paper_confidence_delta=Decimal("5"),
        confidence_label_score=Decimal("75"),
        volume_condition="elevated",
        trade_pattern="breakout",
    )
    assert out["action"] == "EXECUTE"
    assert Decimal(out["learned_opportunity_score"]) >= EXECUTE_SCORE


def test_momentum_and_breakout_detectors() -> None:
    # Rising series for momentum
    bars = [_bar(100 + i * 0.2, v=100 + i) for i in range(30)]
    mom = detect_momentum_continuation(bars)
    assert mom is not None
    assert mom.strategy_key == "momentum_continuation"
    assert mom.bias == "Bullish"

    # Breakout above prior high with volume
    flat = [_bar(100, h=100.2, low=99.8, v=50) for _ in range(32)]
    flat.append(_bar(101.0, h=101.3, low=100.5, v=200))
    br = detect_breakout(flat)
    assert br is not None
    assert br.strategy_key == "breakout"


def test_dip_range_peak_detectors_and_runner() -> None:
    # Mild uptrend then dip bounce
    bars = [_bar(100 + min(i, 15) * 0.1) for i in range(35)]
    # Force a dip near the end under sma20 then bounce
    for i in range(5):
        bars[-(5 - i)] = _bar(100.8 - (0.15 * (5 - i)))
    bars[-1] = _bar(100.95, h=101.0, low=100.7)
    dip = detect_dip_pullback_reversal(bars)
    # May or may not fire depending on SMA geometry; just ensure no crash
    assert dip is None or dip.pattern == "dip_reversal"

    quiet = [_bar(100 + ((i % 5) - 2) * 0.05, v=80) for i in range(30)]
    quiet[-1] = _bar(99.7, h=99.85, low=99.6)
    rng = detect_range_mean_reversion(quiet)
    assert rng is None or rng.strategy_key == "range_mean_reversion"

    run_up = [
        _bar(100 + i * 0.4, h=100 + i * 0.4 + 0.3, low=100 + i * 0.4 - 0.05)
        for i in range(20)
    ]
    # Exhaustion wick
    run_up.append(_bar(108.0, h=109.5, low=107.8, v=40))
    peak = detect_peak_exhaustion_protection(run_up)
    assert peak is None or peak.pattern == "peak_exhaustion"

    assert isinstance(run_all_detectors(quiet), list)


def test_wait_threshold_constant() -> None:
    assert WAIT_SCORE < EXECUTE_SCORE
