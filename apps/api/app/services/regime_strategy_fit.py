"""Map market regimes to strategy families that historically fit them.

Paper/research guidance only — never unlocks live trading, never bypasses
risk controls, and never claims profitability without validation evidence.
"""

from __future__ import annotations

from typing import Any

# Preferred regimes per strategy_key (research class or paper detector key).
STRATEGY_REGIME_FIT: dict[str, frozenset[str]] = {
    "grid_trading": frozenset({"quiet"}),
    "range_mean_reversion": frozenset({"quiet"}),
    "dca": frozenset({"volatile", "trend_down"}),
    "dip_pullback_reversal": frozenset({"volatile", "trend_down", "trend_up"}),
    "trend_momentum": frozenset({"trend_up", "trend_down"}),
    "momentum_continuation": frozenset({"trend_up"}),
    "breakout": frozenset({"trend_up", "volatile"}),
    "sma_crossover": frozenset({"trend_up"}),
    "cross_venue_arb": frozenset({"quiet", "volatile", "trend_up", "trend_down"}),
    "buy_and_hold": frozenset({"trend_up"}),
    "peak_exhaustion_protection": frozenset({"volatile", "trend_up"}),
}

# Misfit regimes that should reduce confidence (capital preservation).
STRATEGY_REGIME_MISFIT: dict[str, frozenset[str]] = {
    "grid_trading": frozenset({"trend_up", "trend_down", "volatile"}),
    "range_mean_reversion": frozenset({"trend_up", "trend_down"}),
    "dca": frozenset({"quiet"}),
    "trend_momentum": frozenset({"quiet"}),
    "momentum_continuation": frozenset({"quiet", "trend_down"}),
    "breakout": frozenset({"quiet", "trend_down"}),
    "sma_crossover": frozenset({"quiet", "trend_down"}),
    "cross_venue_arb": frozenset({"insufficient_data"}),
}


def regime_strategy_adjustment(
    *, strategy_key: str | None, regime: str
) -> tuple[float, str | None]:
    """Return (multiplier, adjustment_code) for observational confidence.

    Multiplier is 1.0 when unknown/unmapped. Fit boosts slightly; misfit
    penalizes so Argus prefers the strategy family that matches the regime.
    """
    key = (strategy_key or "").strip().lower()
    reg = (regime or "insufficient_data").strip().lower()
    if not key or reg == "insufficient_data":
        return 1.0, None
    fit = STRATEGY_REGIME_FIT.get(key)
    misfit = STRATEGY_REGIME_MISFIT.get(key)
    if fit and reg in fit:
        return 1.12, "regime_strategy_fit_boost"
    if misfit and reg in misfit:
        return 0.88, "regime_strategy_misfit_penalty"
    return 1.0, None


def describe_strategy_family(strategy_key: str | None) -> str:
    """Founder-facing short label for Alpha Radar / coaching UI."""
    key = (strategy_key or "").strip().lower()
    labels = {
        "sma_crossover": "Momentum (SMA)",
        "grid_trading": "Grid (range)",
        "dca": "DCA (dip average)",
        "trend_momentum": "Trend / momentum (RSI+MACD)",
        "cross_venue_arb": "Cross-venue spread",
        "momentum_continuation": "Momentum continuation",
        "breakout": "Breakout",
        "dip_pullback_reversal": "Dip / pullback",
        "range_mean_reversion": "Range mean reversion",
        "peak_exhaustion_protection": "Peak protection",
        "buy_and_hold": "Buy and hold",
    }
    return labels.get(key, strategy_key or "unknown")


def strategy_catalog() -> list[dict[str, Any]]:
    """Honest catalog of built-in families and intended regimes (no P&L claims)."""
    return [
        {
            "strategy_key": "grid_trading",
            "family": "grid",
            "best_regimes": sorted(STRATEGY_REGIME_FIT["grid_trading"]),
            "summary": "Grid of buys near range lows and trims near highs in sideways markets.",
            "paper_detector": True,
            "research_class": True,
            "live_execution": False,
        },
        {
            "strategy_key": "dca",
            "family": "dca",
            "best_regimes": sorted(STRATEGY_REGIME_FIT["dca"]),
            "summary": "Fixed-interval buys with larger safety-order steps on dips.",
            "paper_detector": True,
            "research_class": True,
            "live_execution": False,
        },
        {
            "strategy_key": "trend_momentum",
            "family": "trend_momentum",
            "best_regimes": sorted(STRATEGY_REGIME_FIT["trend_momentum"]),
            "summary": "RSI + MACD confirmation to ride strong directional moves.",
            "paper_detector": True,
            "research_class": True,
            "live_execution": False,
        },
        {
            "strategy_key": "cross_venue_arb",
            "family": "arbitrage",
            "best_regimes": sorted(STRATEGY_REGIME_FIT["cross_venue_arb"]),
            "summary": (
                "Captures verified primary-vs-secondary venue discounts. "
                "Stays flat without a real secondary price series; "
                "no live multi-exchange execution."
            ),
            "paper_detector": True,
            "research_class": True,
            "live_execution": False,
        },
        {
            "strategy_key": "sma_crossover",
            "family": "trend_momentum",
            "best_regimes": sorted(STRATEGY_REGIME_FIT["sma_crossover"]),
            "summary": "Classic fast/slow SMA crossover momentum probe.",
            "paper_detector": False,
            "research_class": True,
            "live_execution": False,
        },
    ]
