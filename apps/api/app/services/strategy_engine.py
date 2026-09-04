"""Deterministic research engines for Strategy Laboratory — no live trading."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from dataclasses import asdict, dataclass
from typing import Any

STRATEGY_REGISTRY: dict[str, type] = {}


class StrategyEngineError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class Bar:
    open_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class ExecutionAssumptions:
    commission_bps: float = 0.0
    fee_bps: float = 0.0
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    latency_bars: int = 0
    liquidity_fraction: float = 1.0
    allow_partial_fills: bool = True
    max_position_notional: float = 1_000_000.0
    max_capital: float = 100_000.0


@dataclass
class Trade:
    bar_index: int
    side: str
    quantity: float
    price: float
    notional: float
    costs: float


@dataclass
class BacktestResult:
    metrics: dict[str, float]
    equity_curve: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    diagnostics: dict[str, Any]


class BuyAndHoldStrategy:
    def target_exposure(self, bars: list[Bar], i: int, params: dict[str, Any]) -> float:
        _ = bars, params
        return 1.0 if i >= 0 else 0.0


class SmaCrossoverStrategy:
    def target_exposure(self, bars: list[Bar], i: int, params: dict[str, Any]) -> float:
        fast = int(params.get("fast", 5))
        slow = int(params.get("slow", 20))
        if fast < 1 or slow < 1 or fast >= slow:
            raise StrategyEngineError(
                "invalid_parameters",
                "sma_crossover requires 1 <= fast < slow",
            )
        if i + 1 < slow:
            return 0.0
        closes = [b.close for b in bars[: i + 1]]
        fast_ma = sum(closes[-fast:]) / fast
        slow_ma = sum(closes[-slow:]) / slow
        return 1.0 if fast_ma > slow_ma else 0.0


def _ema(values: list[float], n: int) -> float | None:
    if n < 1 or len(values) < n:
        return None
    k = 2.0 / (n + 1.0)
    ema = sum(values[:n]) / n
    for v in values[n:]:
        ema = (v * k) + (ema * (1.0 - k))
    return ema


def _rsi(closes: list[float], period: int) -> float | None:
    if period < 1 or len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    window = closes[-(period + 1) :]
    for a, b in zip(window[:-1], window[1:], strict=True):
        delta = b - a
        if delta >= 0:
            gains += delta
        else:
            losses += -delta
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss < 1e-12:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class GridTradingStrategy:
    """Range grid: higher long exposure near range lows, lower near highs.

    Best for sideways / quiet markets. Stays flat when the lookback range is
    too wide (trending) so capital is not forced into a broken grid.
    """

    def target_exposure(self, bars: list[Bar], i: int, params: dict[str, Any]) -> float:
        lookback = int(params.get("lookback", 40))
        max_range_pct = float(params.get("max_range_pct", 0.08))
        min_levels = int(params.get("grid_levels", 8))
        if lookback < 5 or min_levels < 2:
            raise StrategyEngineError(
                "invalid_parameters",
                "grid_trading requires lookback >= 5 and grid_levels >= 2",
            )
        if i + 1 < lookback:
            return 0.0
        window = bars[i + 1 - lookback : i + 1]
        hi = max(b.high for b in window)
        lo = min(b.low for b in window)
        price = bars[i].close
        if hi <= lo or price <= 0:
            return 0.0
        width_pct = (hi - lo) / price
        if width_pct > max_range_pct or width_pct < 1e-6:
            return 0.0  # not a tradable sideways grid
        # 1.0 at range low → 0.0 at range high (long-only grid accumulation).
        pos = (hi - price) / (hi - lo)
        return max(0.0, min(1.0, pos))


class DcaStrategy:
    """Dollar-cost averaging with optional dip safety-order acceleration.

    Builds exposure on a fixed bar interval and increases step size when
    price dips from a recent peak — lowers average entry without shorts.
    """

    def target_exposure(self, bars: list[Bar], i: int, params: dict[str, Any]) -> float:
        interval = int(params.get("interval_bars", 5))
        base_step = float(params.get("base_step", 0.05))
        safety_dip_pct = float(params.get("safety_dip_pct", 0.03))
        safety_multiplier = float(params.get("safety_multiplier", 2.0))
        max_exposure = float(params.get("max_exposure", 1.0))
        peak_lookback = int(params.get("peak_lookback", 20))
        if interval < 1 or base_step <= 0 or max_exposure <= 0:
            raise StrategyEngineError(
                "invalid_parameters",
                "dca requires interval_bars >= 1, base_step > 0, max_exposure > 0",
            )
        max_exposure = max(0.0, min(1.0, max_exposure))
        exposure = 0.0
        peak = bars[0].close if bars else 0.0
        for j in range(0, i + 1):
            price = bars[j].close
            start = max(0, j + 1 - peak_lookback)
            peak = max(b.close for b in bars[start : j + 1])
            if j % interval != 0:
                continue
            step = base_step
            if peak > 0 and (peak - price) / peak >= safety_dip_pct:
                step = base_step * max(1.0, safety_multiplier)
            exposure = min(max_exposure, exposure + step)
        return max(0.0, min(1.0, exposure))


class TrendMomentumStrategy:
    """Trend / momentum: RSI confirmation plus MACD line vs signal.

    Long when RSI is in momentum band and MACD is above its signal (bullish
    histogram). Flat otherwise. Designed for strong directional regimes.
    """

    def target_exposure(self, bars: list[Bar], i: int, params: dict[str, Any]) -> float:
        rsi_period = int(params.get("rsi_period", 14))
        rsi_entry = float(params.get("rsi_entry", 55.0))
        rsi_exit = float(params.get("rsi_exit", 45.0))
        macd_fast = int(params.get("macd_fast", 12))
        macd_slow = int(params.get("macd_slow", 26))
        macd_signal = int(params.get("macd_signal", 9))
        if not (1 <= macd_fast < macd_slow):
            raise StrategyEngineError(
                "invalid_parameters",
                "trend_momentum requires 1 <= macd_fast < macd_slow",
            )
        if rsi_period < 2 or macd_signal < 1:
            raise StrategyEngineError(
                "invalid_parameters",
                "trend_momentum requires rsi_period >= 2 and macd_signal >= 1",
            )
        need = max(rsi_period + 1, macd_slow + macd_signal)
        if i + 1 < need:
            return 0.0
        closes = [b.close for b in bars[: i + 1]]
        rsi = _rsi(closes, rsi_period)
        if rsi is None:
            return 0.0
        # MACD line series then signal EMA of MACD values (no look-ahead).
        macd_series: list[float] = []
        for k in range(macd_slow - 1, len(closes)):
            slice_closes = closes[: k + 1]
            fast_ema = _ema(slice_closes, macd_fast)
            slow_ema = _ema(slice_closes, macd_slow)
            if fast_ema is None or slow_ema is None:
                continue
            macd_series.append(fast_ema - slow_ema)
        if len(macd_series) < macd_signal:
            return 0.0
        signal = _ema(macd_series, macd_signal)
        if signal is None:
            return 0.0
        macd_line = macd_series[-1]
        bullish = rsi >= rsi_entry and macd_line > signal
        if bullish:
            return 1.0
        if rsi <= rsi_exit or macd_line < signal:
            return 0.0
        return 0.0


class CrossVenueArbStrategy:
    """Research-only cross-venue spread capture (long primary when discounted).

    Requires an explicit ``secondary_closes`` series aligned to bars (same
    length). Does **not** invent venue prices. Without a verified secondary
    series the strategy stays flat. Live multi-exchange execution remains
    forbidden; this engine is for paper/research evidence only.
    """

    def target_exposure(self, bars: list[Bar], i: int, params: dict[str, Any]) -> float:
        secondary = params.get("secondary_closes")
        if not isinstance(secondary, list) or len(secondary) != len(bars):
            return 0.0
        min_spread_bps = float(params.get("min_spread_bps", 15.0))
        exit_spread_bps = float(params.get("exit_spread_bps", 5.0))
        max_exposure = float(params.get("max_exposure", 0.5))
        max_exposure = max(0.0, min(1.0, max_exposure))
        if min_spread_bps < 0 or exit_spread_bps < 0:
            raise StrategyEngineError(
                "invalid_parameters",
                "cross_venue_arb spreads must be non-negative",
            )
        primary = bars[i].close
        try:
            other = float(secondary[i])
        except (TypeError, ValueError):
            return 0.0
        if primary <= 0 or other <= 0:
            return 0.0
        # Positive when secondary is richer than primary (buy cheap venue).
        spread_bps = ((other - primary) / primary) * 10_000.0
        if spread_bps >= min_spread_bps:
            return max_exposure
        if spread_bps <= exit_spread_bps:
            return 0.0
        # Hold prior stance within the band: approximate with mid-band rule.
        mid = (min_spread_bps + exit_spread_bps) / 2.0
        return max_exposure if spread_bps >= mid else 0.0


def _register_builtin() -> None:
    STRATEGY_REGISTRY["buy_and_hold"] = BuyAndHoldStrategy
    STRATEGY_REGISTRY["sma_crossover"] = SmaCrossoverStrategy
    STRATEGY_REGISTRY["grid_trading"] = GridTradingStrategy
    STRATEGY_REGISTRY["dca"] = DcaStrategy
    STRATEGY_REGISTRY["trend_momentum"] = TrendMomentumStrategy
    STRATEGY_REGISTRY["cross_venue_arb"] = CrossVenueArbStrategy


_register_builtin()


def get_strategy(strategy_class: str) -> Any:
    if strategy_class not in STRATEGY_REGISTRY:
        raise StrategyEngineError(
            "unknown_strategy_class",
            f"Strategy class not in research registry: {strategy_class}",
        )
    return STRATEGY_REGISTRY[strategy_class]()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def hash_request(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def hash_result(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def assumptions_to_dict(assumptions: ExecutionAssumptions) -> dict[str, Any]:
    return asdict(assumptions)


def _cost_rate(assumptions: ExecutionAssumptions) -> float:
    return (
        assumptions.commission_bps
        + assumptions.fee_bps
        + assumptions.spread_bps
        + assumptions.slippage_bps
    ) / 10_000.0


def _compute_metrics(
    equity: list[float],
    exposures: list[float],
    trades: list[Trade],
) -> dict[str, float]:
    if not equity:
        return {
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe_like": 0.0,
            "turnover": 0.0,
            "avg_exposure": 0.0,
            "trade_count": 0.0,
            "win_rate": 0.0,
        }

    start = equity[0]
    end = equity[-1]
    total_return = (end / start) - 1.0 if start else 0.0

    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)

    returns: list[float] = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        returns.append((equity[i] / prev) - 1.0 if prev else 0.0)

    if len(returns) >= 2:
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(var)
        sharpe_like = (mean_r / std) * math.sqrt(len(returns)) if std > 1e-12 else 0.0
    else:
        sharpe_like = 0.0

    turnover = sum(abs(t.notional) for t in trades)
    if start > 0 and len(equity) > 1:
        turnover = turnover / (start * (len(equity) - 1))
    else:
        turnover = 0.0

    avg_exposure = sum(exposures) / len(exposures) if exposures else 0.0

    # Pair buy/sell PnL for win rate (long-only round trips)
    wins = 0
    closed = 0
    entry_price: float | None = None
    for trade in trades:
        if trade.side == "buy":
            entry_price = trade.price
        elif trade.side == "sell" and entry_price is not None:
            closed += 1
            if trade.price > entry_price:
                wins += 1
            entry_price = None
    win_rate = (wins / closed) if closed else 0.0

    return {
        "total_return": float(total_return),
        "max_drawdown": float(max_dd),
        "sharpe_like": float(sharpe_like),
        "turnover": float(turnover),
        "avg_exposure": float(avg_exposure),
        "trade_count": float(len(trades)),
        "win_rate": float(win_rate),
    }


def run_bar_backtest(
    bars: list[Bar],
    strategy_class: str,
    params: dict[str, Any],
    assumptions: ExecutionAssumptions,
    seed: int = 42,
) -> BacktestResult:
    """Long-only bar backtest. Signals use only bars[i] and earlier (no look-ahead)."""
    _ = seed  # reserved for stochastic extensions; deterministic strategies ignore it
    if not bars:
        raise StrategyEngineError("empty_bars", "Backtest requires at least one bar")

    strategy = get_strategy(strategy_class)
    capital = float(assumptions.max_capital)
    cash = capital
    position_qty = 0.0
    cost_rate = _cost_rate(assumptions)
    latency = max(0, int(assumptions.latency_bars))

    equity_curve: list[dict[str, Any]] = []
    equity_values: list[float] = []
    exposures: list[float] = []
    trades: list[Trade] = []
    pending_target: float | None = None
    pending_ready_at = -1

    for i, bar in enumerate(bars):
        # Apply delayed target from earlier signal
        if pending_target is not None and i >= pending_ready_at:
            target = max(0.0, min(1.0, pending_target))
            mark = bar.open
            position_value = position_qty * mark
            target_notional = min(
                capital * target,
                assumptions.max_position_notional,
                cash + position_value,
            )
            delta_notional = target_notional - position_value
            max_trade = bar.volume * mark * assumptions.liquidity_fraction
            if abs(delta_notional) > max_trade:
                if not assumptions.allow_partial_fills:
                    delta_notional = 0.0
                else:
                    delta_notional = math.copysign(max_trade, delta_notional)

            if abs(delta_notional) > 1e-12 and mark > 0:
                qty = delta_notional / mark
                costs = abs(delta_notional) * cost_rate
                if qty > 0:
                    cash -= delta_notional + costs
                    position_qty += qty
                    trades.append(
                        Trade(
                            bar_index=i,
                            side="buy",
                            quantity=qty,
                            price=mark,
                            notional=delta_notional,
                            costs=costs,
                        )
                    )
                else:
                    sell_qty = min(position_qty, abs(qty))
                    sell_notional = sell_qty * mark
                    cash += sell_notional - costs
                    position_qty -= sell_qty
                    trades.append(
                        Trade(
                            bar_index=i,
                            side="sell",
                            quantity=sell_qty,
                            price=mark,
                            notional=sell_notional,
                            costs=costs,
                        )
                    )
            pending_target = None

        # Signal at close of bar i — executed after latency on a later bar open
        desired = strategy.target_exposure(bars, i, params)
        desired = max(0.0, min(1.0, float(desired)))
        pending_target = desired
        pending_ready_at = i + 1 + latency

        equity = cash + position_qty * bar.close
        equity_values.append(equity)
        exposure = (position_qty * bar.close / equity) if equity > 0 else 0.0
        exposures.append(max(0.0, min(1.0, exposure)))
        equity_curve.append(
            {
                "bar_index": i,
                "open_time": bar.open_time,
                "equity": equity,
                "exposure": exposures[-1],
            }
        )

    metrics = _compute_metrics(equity_values, exposures, trades)
    trade_dicts = [asdict(t) for t in trades]
    diagnostics = {
        "strategy_class": strategy_class,
        "params": params,
        "assumptions": assumptions_to_dict(assumptions),
        "bar_count": len(bars),
        "seed": seed,
        "long_only": True,
        "look_ahead_protected": True,
    }
    return BacktestResult(
        metrics=metrics,
        equity_curve=equity_curve,
        trades=trade_dicts,
        diagnostics=diagnostics,
    )


def run_walk_forward(
    bars: list[Bar],
    strategy_class: str,
    params: dict[str, Any],
    assumptions: ExecutionAssumptions,
    seed: int = 42,
    train_frac: float = 0.6,
    val_frac: float = 0.2,
    test_frac: float = 0.2,
    n_windows: int = 1,
    step_frac: float = 0.1,
) -> dict[str, Any]:
    """Walk-forward with explicit IS/OOS separation.

    ``n_windows=1``: single chronological train+val (IS) / test (OOS) split.
    ``n_windows>1``: rolling windows; primary metrics = mean of per-window OOS
    (never in-sample). Optional per-fold re-optimization via params keys
    ``_optimize_grid`` and ``_optimize_budget``.
    """
    total = train_frac + val_frac + test_frac
    if abs(total - 1.0) > 1e-9:
        raise StrategyEngineError(
            "invalid_split",
            "train_frac + val_frac + test_frac must equal 1.0",
        )
    if any(f < 0 for f in (train_frac, val_frac, test_frac, step_frac)):
        raise StrategyEngineError("invalid_split", "Fractions must be non-negative")
    if n_windows < 1:
        raise StrategyEngineError("invalid_split", "n_windows must be >= 1")
    n = len(bars)
    if n < 10:
        raise StrategyEngineError(
            "insufficient_bars", "Need at least 10 bars for walk-forward"
        )

    window_len = n if n_windows == 1 else max(10, int(n * 0.5))
    step = n if n_windows == 1 else max(1, int(n * step_frac))

    folds: list[dict[str, Any]] = []
    oos_metric_rows: list[dict[str, float]] = []
    last_oos_result: BacktestResult | None = None

    start = 0
    for fold_idx in range(n_windows):
        end = n if n_windows == 1 else start + window_len
        if end > n:
            break
        slice_bars = bars if n_windows == 1 else bars[start:end]
        m = len(slice_bars)
        train_end = max(2, int(m * train_frac))
        val_end = max(train_end + 1, int(m * (train_frac + val_frac)))
        val_end = min(val_end, m - 1)
        is_bars = slice_bars[:val_end]
        oos_bars = slice_bars[val_end:]
        if len(oos_bars) < 1:
            break

        fold_params = dict(params)
        optimize_grid = fold_params.pop("_optimize_grid", None)
        optimize_budget = int(fold_params.pop("_optimize_budget", 0) or 0)
        if isinstance(optimize_grid, dict) and optimize_budget > 0:
            train_only = is_bars[:train_end] if train_end < len(is_bars) else is_bars
            opt = run_optimization(
                train_only,
                strategy_class,
                assumptions,
                optimize_grid,
                max_trials=optimize_budget,
                seed=seed + fold_idx,
            )
            fold_params = {**fold_params, **(opt.get("best_params") or {})}

        is_result = run_bar_backtest(
            is_bars, strategy_class, fold_params, assumptions, seed
        )
        oos_result = run_bar_backtest(
            oos_bars, strategy_class, fold_params, assumptions, seed
        )
        last_oos_result = oos_result
        folds.append(
            {
                "fold": fold_idx,
                "start": start,
                "end": end,
                "train_end": train_end,
                "val_end": val_end,
                "is_bar_count": len(is_bars),
                "oos_bar_count": len(oos_bars),
                "params": fold_params,
                "in_sample_metrics": is_result.metrics,
                "out_of_sample_metrics": oos_result.metrics,
            }
        )
        oos_metric_rows.append(oos_result.metrics)
        if n_windows == 1:
            break
        start += step
        if start + window_len > n:
            break

    if not folds or last_oos_result is None:
        raise StrategyEngineError(
            "insufficient_bars", "Could not form walk-forward folds"
        )

    keys = oos_metric_rows[0].keys()
    agg = {
        k: float(
            sum(float(row.get(k, 0.0)) for row in oos_metric_rows) / len(oos_metric_rows)
        )
        for k in keys
    }

    return {
        "metrics": agg,
        "equity_curve": last_oos_result.equity_curve,
        "trades": last_oos_result.trades,
        "diagnostics": {
            **last_oos_result.diagnostics,
            "split": {
                "train_frac": train_frac,
                "val_frac": val_frac,
                "test_frac": test_frac,
                "n_windows": n_windows,
                "step_frac": step_frac,
                "folds": len(folds),
                "is_bar_count": folds[0]["is_bar_count"],
                "oos_bar_count": folds[0]["oos_bar_count"]
                if n_windows == 1
                else sum(f["oos_bar_count"] for f in folds),
                "train_end": folds[0]["train_end"],
                "val_end": folds[0]["val_end"],
            },
            "folds": [
                {
                    "fold": f["fold"],
                    "is_bar_count": f["is_bar_count"],
                    "oos_bar_count": f["oos_bar_count"],
                    "params": f["params"],
                }
                for f in folds
            ],
            "in_sample_reported_as_oos": False,
        },
        "in_sample_metrics": folds[0]["in_sample_metrics"],
        "out_of_sample_metrics": agg,
    }


def _expand_param_grid(param_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    if not param_grid:
        return [{}]
    keys = sorted(param_grid.keys())
    values = [param_grid[k] for k in keys]
    for v in values:
        if not isinstance(v, list) or len(v) == 0:
            raise StrategyEngineError(
                "invalid_param_grid",
                "Each param_grid value must be a non-empty list",
            )
    combos: list[dict[str, Any]] = []
    for product in itertools.product(*values):
        combos.append(dict(zip(keys, product, strict=True)))
    return combos


def run_optimization(
    bars: list[Bar],
    strategy_class: str,
    assumptions: ExecutionAssumptions,
    param_grid: dict[str, list[Any]],
    max_trials: int,
    seed: int = 42,
) -> dict[str, Any]:
    """Hard-budget grid search. Rejects unbounded or over-budget grids."""
    if max_trials is None or int(max_trials) < 1:
        raise StrategyEngineError(
            "unbounded_budget",
            "Optimization requires a positive max_trials budget",
        )
    max_trials = int(max_trials)
    combos = _expand_param_grid(param_grid)
    if len(combos) > max_trials:
        raise StrategyEngineError(
            "unbounded_budget",
            f"Param grid expands to {len(combos)} trials exceeding max_trials={max_trials}",
        )

    trials: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for idx, params in enumerate(combos):
        result = run_bar_backtest(bars, strategy_class, params, assumptions, seed + idx)
        trial = {
            "params": params,
            "metrics": result.metrics,
            "result_hash": hash_result(
                {
                    "metrics": result.metrics,
                    "equity_curve": result.equity_curve,
                    "trades": result.trades,
                }
            ),
        }
        trials.append(trial)
        if best is None or result.metrics["total_return"] > best["metrics"]["total_return"]:
            best = trial

    return {
        "metrics": best["metrics"] if best else {},
        "equity_curve": [],
        "trades": [],
        "diagnostics": {
            "strategy_class": strategy_class,
            "trial_count": len(trials),
            "max_trials": max_trials,
            "best": best,
            "trials": trials,
            "seed": seed,
        },
        "in_sample_metrics": {},
        "out_of_sample_metrics": {},
    }


def run_monte_carlo(
    equity_or_returns: list[float],
    n_sims: int,
    seed: int = 42,
) -> dict[str, Any]:
    """Return-sequence shuffle Monte Carlo with confidence intervals."""
    if n_sims < 1:
        raise StrategyEngineError("invalid_n_sims", "n_sims must be >= 1")
    if len(equity_or_returns) < 2:
        raise StrategyEngineError(
            "insufficient_series",
            "Monte Carlo needs at least 2 equity/return points",
        )

    # Detect equity vs returns: equity levels are typically all positive and large
    series = list(equity_or_returns)
    looks_like_equity = all(v > 0 for v in series) and max(series) > 1.5
    if looks_like_equity:
        returns = [
            (series[i] / series[i - 1]) - 1.0 if series[i - 1] else 0.0
            for i in range(1, len(series))
        ]
        start_equity = series[0]
    else:
        returns = series
        start_equity = 1.0

    rng = random.Random(seed)
    terminal: list[float] = []
    max_drawdowns: list[float] = []

    for _ in range(n_sims):
        shuffled = returns[:]
        rng.shuffle(shuffled)
        equity = start_equity
        path = [equity]
        peak = equity
        max_dd = 0.0
        for r in shuffled:
            equity = equity * (1.0 + r)
            path.append(equity)
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)
        terminal.append(equity)
        max_drawdowns.append(max_dd)

    terminal_sorted = sorted(terminal)
    dd_sorted = sorted(max_drawdowns)

    def _percentile(sorted_vals: list[float], p: float) -> float:
        if not sorted_vals:
            return 0.0
        idx = min(len(sorted_vals) - 1, max(0, int(round((p / 100.0) * (len(sorted_vals) - 1)))))
        return sorted_vals[idx]

    metrics = {
        "total_return": (sum(terminal) / len(terminal) / start_equity) - 1.0,
        "max_drawdown": sum(max_drawdowns) / len(max_drawdowns),
        "sharpe_like": 0.0,
        "turnover": 0.0,
        "avg_exposure": 0.0,
        "trade_count": 0.0,
        "win_rate": 0.0,
        "terminal_mean": sum(terminal) / len(terminal),
        "ci_5": _percentile(terminal_sorted, 5),
        "ci_50": _percentile(terminal_sorted, 50),
        "ci_95": _percentile(terminal_sorted, 95),
        "max_drawdown_ci_95": _percentile(dd_sorted, 95),
    }
    return {
        "metrics": metrics,
        "equity_curve": [],
        "trades": [],
        "diagnostics": {
            "n_sims": n_sims,
            "seed": seed,
            "method": "return_sequence_shuffle",
            "input_kind": "equity" if looks_like_equity else "returns",
            "confidence_intervals": {
                "terminal_5": metrics["ci_5"],
                "terminal_50": metrics["ci_50"],
                "terminal_95": metrics["ci_95"],
                "max_drawdown_95": metrics["max_drawdown_ci_95"],
            },
        },
        "in_sample_metrics": {},
        "out_of_sample_metrics": {},
    }


def run_sensitivity(
    bars: list[Bar],
    strategy_class: str,
    params: dict[str, Any],
    assumptions: ExecutionAssumptions,
    param_name: str,
    deltas: list[float],
    seed: int = 42,
) -> dict[str, Any]:
    if param_name not in params:
        raise StrategyEngineError(
            "unknown_param",
            f"Parameter {param_name!r} not present in params",
        )
    if not deltas:
        raise StrategyEngineError("empty_deltas", "Sensitivity requires non-empty deltas")

    base_value = float(params[param_name])
    points: list[dict[str, Any]] = []
    for d in deltas:
        trial_params = dict(params)
        trial_params[param_name] = base_value + float(d)
        try:
            result = run_bar_backtest(
                bars, strategy_class, trial_params, assumptions, seed
            )
            points.append(
                {
                    "delta": float(d),
                    "param_value": trial_params[param_name],
                    "metrics": result.metrics,
                }
            )
        except StrategyEngineError as exc:
            points.append(
                {
                    "delta": float(d),
                    "param_value": trial_params[param_name],
                    "error": {"code": exc.code, "message": exc.message},
                }
            )

    return {
        "metrics": points[0]["metrics"] if points and "metrics" in points[0] else {},
        "equity_curve": [],
        "trades": [],
        "diagnostics": {
            "param_name": param_name,
            "base_value": base_value,
            "deltas": deltas,
            "points": points,
            "seed": seed,
        },
        "in_sample_metrics": {},
        "out_of_sample_metrics": {},
    }


def bars_from_dicts(raw: list[dict[str, Any]]) -> list[Bar]:
    out: list[Bar] = []
    for row in raw:
        out.append(
            Bar(
                open_time=str(row["open_time"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0)),
            )
        )
    return out
