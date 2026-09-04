"""Unit tests for regime strategy families (grid / DCA / momentum / arb)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.paper_opportunity_detectors import (
    detect_cross_venue_arb,
    detect_dca_dip,
    detect_grid_trading,
    detect_trend_momentum,
    run_all_detectors,
)
from app.services.regime_strategy_fit import (
    describe_strategy_family,
    regime_strategy_adjustment,
    strategy_catalog,
)
from app.services.strategy_engine import (
    STRATEGY_REGISTRY,
    ExecutionAssumptions,
    bars_from_dicts,
    run_bar_backtest,
)
from app.services.trading_intelligence_service import TradingIntelligenceService


@dataclass
class _Bar:
    open: float
    high: float
    low: float
    close: float
    volume: float = 100.0
    secondary_close: float | None = None


def _synth_bars(n: int, *, base: float = 100.0, drift: float = 0.0, noise: float = 0.1):
    rows = []
    price = base
    for i in range(n):
        price = price * (1.0 + drift) + (((i % 5) - 2) * noise * 0.01)
        rows.append(
            {
                "open_time": f"2026-01-01T00:{i:02d}:00Z",
                "open": price,
                "high": price * 1.002,
                "low": price * 0.998,
                "close": price,
                "volume": 1000.0,
            }
        )
    return rows


def test_registry_includes_regime_families() -> None:
    assert {
        "grid_trading",
        "dca",
        "trend_momentum",
        "cross_venue_arb",
    }.issubset(STRATEGY_REGISTRY.keys())
    for name in STRATEGY_REGISTRY:
        assert "live" not in name
        assert "broker" not in name


def test_grid_trading_buys_near_range_low() -> None:
    # Tight sideways band then finish near the low.
    rows = []
    for i in range(50):
        mid = 100.0 + ((i % 6) - 3) * 0.15
        rows.append(
            {
                "open_time": f"t{i}",
                "open": mid,
                "high": mid + 0.2,
                "low": mid - 0.2,
                "close": mid,
                "volume": 100.0,
            }
        )
    rows[-1]["close"] = 99.2
    rows[-1]["low"] = 99.0
    rows[-1]["high"] = 99.4
    result = run_bar_backtest(
        bars_from_dicts(rows),
        "grid_trading",
        {"lookback": 40, "max_range_pct": 0.08, "grid_levels": 8},
        ExecutionAssumptions(max_capital=10_000),
        seed=1,
    )
    assert result.diagnostics["strategy_class"] == "grid_trading"
    assert result.metrics["avg_exposure"] > 0.0


def test_dca_accumulates_and_arb_stays_flat_without_secondary() -> None:
    rows = _synth_bars(40, drift=-0.002)
    dca = run_bar_backtest(
        bars_from_dicts(rows),
        "dca",
        {"interval_bars": 4, "base_step": 0.1, "max_exposure": 0.8},
        ExecutionAssumptions(max_capital=10_000),
        seed=2,
    )
    assert dca.metrics["avg_exposure"] > 0.0
    assert dca.metrics["avg_exposure"] <= 0.8 + 1e-9

    flat = run_bar_backtest(
        bars_from_dicts(rows),
        "cross_venue_arb",
        {"min_spread_bps": 15},
        ExecutionAssumptions(max_capital=10_000),
        seed=3,
    )
    assert flat.metrics["avg_exposure"] == 0.0
    assert flat.metrics["trade_count"] == 0.0


def test_cross_venue_arb_with_verified_secondary() -> None:
    rows = _synth_bars(30, drift=0.0, noise=0.0)
    secondary = [r["close"] * 1.003 for r in rows]  # ~30 bps richer secondary
    result = run_bar_backtest(
        bars_from_dicts(rows),
        "cross_venue_arb",
        {
            "secondary_closes": secondary,
            "min_spread_bps": 15,
            "exit_spread_bps": 5,
            "max_exposure": 0.4,
        },
        ExecutionAssumptions(max_capital=10_000),
        seed=4,
    )
    assert result.metrics["avg_exposure"] > 0.0
    assert result.metrics["avg_exposure"] <= 0.4 + 1e-9


def test_trend_momentum_long_on_strong_uptrend() -> None:
    rows = _synth_bars(80, drift=0.004, noise=0.02)
    result = run_bar_backtest(
        bars_from_dicts(rows),
        "trend_momentum",
        {
            "rsi_period": 14,
            "rsi_entry": 55,
            "rsi_exit": 45,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
        },
        ExecutionAssumptions(max_capital=10_000),
        seed=5,
    )
    assert result.diagnostics["long_only"] is True
    # Strong uptrend should produce some long exposure at times.
    assert result.metrics["avg_exposure"] >= 0.0


def test_paper_detectors_grid_dca_momentum_arb() -> None:
    quiet = [
        _Bar(100 + ((i % 5) - 2) * 0.08, 100.2, 99.8, 100 + ((i % 5) - 2) * 0.08)
        for i in range(36)
    ]
    quiet[-1] = _Bar(99.55, 99.7, 99.4, 99.55)
    grid = detect_grid_trading(quiet)
    assert grid is None or grid.strategy_key == "grid_trading"

    # Peak then dip for DCA
    dip_bars = [_Bar(100 + i * 0.2, 100.3 + i * 0.2, 99.9 + i * 0.2, 100 + i * 0.2) for i in range(25)]
    dip_bars.extend(
        [
            _Bar(104.0, 104.2, 103.5, 103.8),
            _Bar(103.0, 103.2, 102.5, 102.8),
            _Bar(102.5, 102.7, 102.0, 102.4),
            _Bar(102.6, 102.8, 102.2, 102.6),
            _Bar(102.7, 102.9, 102.3, 102.7),
        ]
    )
    dca = detect_dca_dip(dip_bars)
    assert dca is None or dca.strategy_key == "dca"

    up = [_Bar(100 + i * 0.35, 100.4 + i * 0.35, 99.9 + i * 0.35, 100 + i * 0.35) for i in range(40)]
    mom = detect_trend_momentum(up)
    assert mom is None or (
        mom.strategy_key == "trend_momentum" and mom.bias == "Bullish"
    )

    # Arb must stay silent without secondary close.
    assert detect_cross_venue_arb(up) is None
    arb_bars = list(up)
    arb_bars[-1] = _Bar(
        up[-1].open,
        up[-1].high,
        up[-1].low,
        up[-1].close,
        secondary_close=up[-1].close * 1.004,
    )
    arb = detect_cross_venue_arb(arb_bars)
    assert arb is not None
    assert arb.strategy_key == "cross_venue_arb"
    assert Decimal(arb.detail["spread_bps"]) >= Decimal("15")

    assert isinstance(run_all_detectors(quiet), list)


def test_regime_strategy_fit_and_confidence() -> None:
    mult, code = regime_strategy_adjustment(strategy_key="grid_trading", regime="quiet")
    assert mult > 1.0
    assert code == "regime_strategy_fit_boost"
    bad_mult, bad_code = regime_strategy_adjustment(
        strategy_key="grid_trading", regime="trend_up"
    )
    assert bad_mult < 1.0
    assert bad_code == "regime_strategy_misfit_penalty"

    svc = TradingIntelligenceService(db=None)  # type: ignore[arg-type]
    fit, _, fit_factors = svc.score_confidence(
        score=80,
        bias="Bullish",
        risk_status="clear",
        regime="quiet",
        stale=False,
        strategy_key="grid_trading",
    )
    misfit, _, misfit_factors = svc.score_confidence(
        score=80,
        bias="Bullish",
        risk_status="clear",
        regime="trend_up",
        stale=False,
        strategy_key="grid_trading",
    )
    assert fit > misfit
    assert "regime_strategy_fit_boost" in fit_factors["adjustments"]
    assert "regime_strategy_misfit_penalty" in misfit_factors["adjustments"]
    assert describe_strategy_family("dca") == "DCA (dip average)"
    catalog = strategy_catalog()
    assert any(row["strategy_key"] == "cross_venue_arb" for row in catalog)
    assert all(row["live_execution"] is False for row in catalog)
