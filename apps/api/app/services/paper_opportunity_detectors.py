"""Lightweight deterministic PAPER opportunity detectors from OHLCV bars.

PAPER observation only — never submits orders. Each detector returns the same
shape consumed by MarketScanService candidate creation so strategies compete
through Alpha Radar / scan pipeline alongside sma_crossover.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class DetectorSignal:
    strategy_key: str
    bias: str  # Bullish | Bearish | Neutral
    score: Decimal
    reason_code: str | None
    reason_text: str
    stop_loss: Decimal | None
    take_profit: Decimal | None
    pattern: str
    detail: dict[str, Any]


def _closes(bars: Sequence[Any]) -> list[Decimal]:
    return [Decimal(str(b.close)) for b in bars]


def _highs(bars: Sequence[Any]) -> list[Decimal]:
    return [Decimal(str(b.high)) for b in bars]


def _lows(bars: Sequence[Any]) -> list[Decimal]:
    return [Decimal(str(b.low)) for b in bars]


def _vols(bars: Sequence[Any]) -> list[Decimal]:
    out: list[Decimal] = []
    for b in bars:
        v = getattr(b, "volume", None)
        out.append(Decimal(str(v)) if v is not None else Decimal("0"))
    return out


def _sma(values: list[Decimal], n: int) -> Decimal | None:
    if len(values) < n or n <= 0:
        return None
    return sum(values[-n:], Decimal("0")) / Decimal(n)


# Keep detector geometry aligned with paper-training economics:
# microscopic stops produced penny take-profits on the learning desk.
_MIN_STOP_DISTANCE_PCT = Decimal("0.015")  # 1.5%


def _rr_levels(
    price: Decimal, *, stop: Decimal, min_r: Decimal = Decimal("2")
) -> tuple[Decimal, Decimal]:
    min_risk = price * _MIN_STOP_DISTANCE_PCT
    if stop >= price:
        stop = price - min_risk
    risk = price - stop
    if risk < min_risk:
        stop = price - min_risk
        risk = min_risk
    if risk <= 0:
        risk = min_risk
        stop = price - risk
    target = price + (risk * min_r)
    return stop, target


def detect_momentum_continuation(bars: Sequence[Any]) -> DetectorSignal | None:
    if len(bars) < 25:
        return None
    closes = _closes(bars)
    price = closes[-1]
    fast = _sma(closes, 5)
    slow = _sma(closes, 12)
    if fast is None or slow is None or fast <= slow:
        return None
    # Continuation: higher lows over last 8 bars and positive 5-bar return.
    lows = _lows(bars)[-8:]
    if lows != sorted(lows):  # not strictly rising lows — allow soft check
        rising = sum(1 for i in range(1, len(lows)) if lows[i] >= lows[i - 1])
        if rising < 4:
            return None
    ret5 = (closes[-1] - closes[-6]) / closes[-6] if closes[-6] else Decimal("0")
    if ret5 < Decimal("0.004"):
        return None
    stop = min(_lows(bars)[-10:])
    stop, target = _rr_levels(price, stop=stop)
    score = Decimal("72") + min(Decimal("18"), ret5 * Decimal("800"))
    return DetectorSignal(
        strategy_key="momentum_continuation",
        bias="Bullish",
        score=min(Decimal("95"), score),
        reason_code=None,
        reason_text="Short-term momentum continuing with rising structure.",
        stop_loss=stop,
        take_profit=target,
        pattern="momentum",
        detail={"ret5": str(ret5), "fast_sma": str(fast), "slow_sma": str(slow)},
    )


def detect_breakout(bars: Sequence[Any]) -> DetectorSignal | None:
    if len(bars) < 30:
        return None
    closes = _closes(bars)
    highs = _highs(bars)
    vols = _vols(bars)
    price = closes[-1]
    prior_high = max(highs[-21:-1]) if len(highs) >= 22 else max(highs[:-1])
    if price <= prior_high:
        return None
    avg_vol = _sma(vols[:-1], 20) if len(vols) > 20 else _sma(vols, max(5, len(vols) - 1))
    vol_ok = bool(avg_vol and vols[-1] >= avg_vol * Decimal("1.2"))
    stop = min(_lows(bars)[-8:])
    stop, target = _rr_levels(price, stop=stop)
    score = Decimal("74") + (Decimal("8") if vol_ok else Decimal("0"))
    return DetectorSignal(
        strategy_key="breakout",
        bias="Bullish",
        score=min(Decimal("96"), score),
        reason_code=None,
        reason_text=(
            "Price broke above the recent range high"
            + (" with elevated volume." if vol_ok else ".")
        ),
        stop_loss=stop,
        take_profit=target,
        pattern="breakout" if not vol_ok else "high_volume_breakout",
        detail={
            "prior_high": str(prior_high),
            "volume_ok": vol_ok,
            "relative_volume": str((vols[-1] / avg_vol) if avg_vol else None),
        },
    )


def detect_dip_pullback_reversal(bars: Sequence[Any]) -> DetectorSignal | None:
    if len(bars) < 30:
        return None
    closes = _closes(bars)
    price = closes[-1]
    slow = _sma(closes, 20)
    if slow is None or price >= slow:
        return None
    # Pullback in an intermediate uptrend: 20-bar still above 40-bar when available.
    slower = _sma(closes, 40) if len(closes) >= 40 else None
    if slower is not None and slow < slower:
        return None
    recent_low = min(_lows(bars)[-6:])
    bounce = (price - recent_low) / recent_low if recent_low else Decimal("0")
    if bounce < Decimal("0.003") or bounce > Decimal("0.03"):
        return None
    # Reclaim of prior 3-bar mid.
    mid = sum(closes[-4:-1], Decimal("0")) / Decimal("3")
    if price < mid:
        return None
    stop = recent_low * Decimal("0.998")
    stop, target = _rr_levels(price, stop=stop)
    return DetectorSignal(
        strategy_key="dip_pullback_reversal",
        bias="Bullish",
        score=Decimal("71"),
        reason_code=None,
        reason_text="Dip/pullback bounce against a longer uptrend context.",
        stop_loss=stop,
        take_profit=target,
        pattern="dip_reversal",
        detail={"bounce": str(bounce), "slow_sma": str(slow)},
    )


def detect_range_mean_reversion(bars: Sequence[Any]) -> DetectorSignal | None:
    if len(bars) < 30:
        return None
    closes = _closes(bars)
    highs = _highs(bars)
    lows = _lows(bars)
    price = closes[-1]
    window_h = max(highs[-20:])
    window_l = min(lows[-20:])
    width = window_h - window_l
    if width <= 0 or (width / price) > Decimal("0.04"):
        return None  # too wide / trending
    mid = (window_h + window_l) / Decimal("2")
    # Buy near lower third of range.
    lower_third = window_l + (width * Decimal("0.33"))
    if price > lower_third:
        return None
    # Mean reversion target toward mid/upper — enforce min 2R vs stop under range low.
    stop = window_l * Decimal("0.997")
    stop, min_target = _rr_levels(price, stop=stop)
    target = max(min_target, mid)
    if target <= price:
        return None
    return DetectorSignal(
        strategy_key="range_mean_reversion",
        bias="Bullish",
        score=Decimal("68"),
        reason_code=None,
        reason_text="Price is near the bottom of a quiet range — mean-reversion watch.",
        stop_loss=stop,
        take_profit=target,
        pattern="range",
        detail={"range_high": str(window_h), "range_low": str(window_l), "mid": str(mid)},
    )


def detect_catalyst_retest(bars: Sequence[Any]) -> DetectorSignal | None:
    """Spike + volume surge → pullback off highs → reclaim (paper playbook).

    Mimics: coin spikes ~6–12%, volume elevates, price cools 2–8% from the
    impulse high, then reclaims short support. Does not invent news — scan
    detail tags the geometry so auto-enter can consult memory + optional headlines.
    """
    if len(bars) < 32:
        return None
    closes = _closes(bars)
    highs = _highs(bars)
    lows = _lows(bars)
    vols = _vols(bars)
    price = closes[-1]
    if price <= 0:
        return None

    lookback = closes[-36:]
    base = min(lookback[:-8]) if len(lookback) > 8 else lookback[0]
    if base <= 0:
        return None
    impulse_high = max(highs[-28:])
    spike_pct = (impulse_high - base) / base
    # ~6–18% impulse (covers "coin spikes ~9%" without requiring exact 9%).
    if spike_pct < Decimal("0.06") or spike_pct > Decimal("0.18"):
        return None

    dist_from_high = (impulse_high - price) / impulse_high
    # Still near the move, but not buying the tip — wait for retest zone.
    if dist_from_high < Decimal("0.015") or dist_from_high > Decimal("0.08"):
        return None

    # Volume surge on the impulse window vs prior baseline.
    impulse_vols = vols[-16:]
    prior_vols = vols[-36:-16] if len(vols) >= 36 else vols[:-16]
    if not prior_vols:
        return None
    avg_impulse = sum(impulse_vols, Decimal("0")) / Decimal(len(impulse_vols))
    avg_prior = sum(prior_vols, Decimal("0")) / Decimal(len(prior_vols))
    if avg_prior <= 0 or avg_impulse < avg_prior * Decimal("1.6"):
        return None
    rel_vol = avg_impulse / avg_prior

    # Retest confirmation: bounce off a recent swing low + reclaim 3-bar mid.
    retest_low = min(lows[-8:])
    bounce = (price - retest_low) / retest_low if retest_low > 0 else Decimal("0")
    if bounce < Decimal("0.002") or bounce > Decimal("0.04"):
        return None
    mid = sum(closes[-4:-1], Decimal("0")) / Decimal("3")
    if price < mid:
        return None
    # Structure still constructive vs 12-bar SMA.
    slow = _sma(closes, 12)
    if slow is None or price < slow * Decimal("0.995"):
        return None

    stop = retest_low * Decimal("0.997")
    stop, target = _rr_levels(price, stop=stop)
    score = Decimal("76") + min(Decimal("14"), (spike_pct - Decimal("0.06")) * Decimal("80"))
    if rel_vol >= Decimal("2"):
        score += Decimal("4")
    return DetectorSignal(
        strategy_key="catalyst_retest",
        bias="Bullish",
        score=min(Decimal("96"), score),
        reason_code=None,
        reason_text=(
            "Impulse + volume surge cooled into a retest; reclaiming short support "
            "(paper catalyst-retest playbook)."
        ),
        stop_loss=stop,
        take_profit=target,
        pattern="catalyst_retest",
        detail={
            "spike_pct": str(spike_pct),
            "dist_from_high": str(dist_from_high),
            "relative_volume": str(rel_vol),
            "relative_volume_high": True,
            "impulse_high": str(impulse_high),
            "retest_low": str(retest_low),
            "playbook": "catalyst_retest",
            "discovery_opportunity_class": "pullback_retest",
            "trade_pattern": "catalyst_retest",
        },
    )


def detect_peak_exhaustion_protection(bars: Sequence[Any]) -> DetectorSignal | None:
    """Protection signal: mark bullish exhaustion as Neutral/Rejected-style watch."""
    if len(bars) < 25:
        return None
    closes = _closes(bars)
    highs = _highs(bars)
    vols = _vols(bars)
    price = closes[-1]
    prior_high = max(highs[-16:-1])
    # Extended run into highs with weakening close vs high (upper wick pressure).
    ret8 = (closes[-1] - closes[-9]) / closes[-9] if closes[-9] else Decimal("0")
    if ret8 < Decimal("0.015"):
        return None
    last = bars[-1]
    high = Decimal(str(last.high))
    low = Decimal(str(last.low))
    if high <= low:
        return None
    upper_wick = (high - price) / (high - low)
    if upper_wick < Decimal("0.45"):
        return None
    avg_vol = _sma(vols[:-1], 15)
    vol_fade = bool(avg_vol and vols[-1] < avg_vol)
    # Bearish/Neutral protection — does not open longs; scan stores as
    # Neutral Rejected/Expired helper.
    return DetectorSignal(
        strategy_key="peak_exhaustion_protection",
        bias="Neutral",
        score=Decimal("40"),
        reason_code="peak_exhaustion",
        reason_text="Peak/exhaustion risk — protect capital; do not chase breakouts here.",
        stop_loss=None,
        take_profit=None,
        pattern="peak_exhaustion",
        detail={
            "ret8": str(ret8),
            "upper_wick": str(upper_wick),
            "volume_fade": vol_fade,
            "prior_high": str(prior_high),
            "protection_only": True,
        },
    )


# --- Micro Trading (paper only): smaller repeatable edges, cost-gated -----------

MICRO_STRATEGY_KEYS = frozenset({"range_micro", "trend_pullback_micro"})
# Round-trip simulated cost (matches trading_intelligence SIMULATED_COST_BPS=3).
_MICRO_COST_BPS_RT = Decimal("6")
_MICRO_ASSUMED_NOTIONAL = Decimal("100")
_MICRO_MIN_NET_USD = Decimal("1.50")
_MICRO_MIN_R = Decimal("1.5")


def _micro_net_edge_usd(
    *, price: Decimal, target: Decimal, notional: Decimal = _MICRO_ASSUMED_NOTIONAL
) -> Decimal | None:
    if price <= 0 or target <= price or notional <= 0:
        return None
    gross = notional * ((target - price) / price)
    cost = notional * (_MICRO_COST_BPS_RT / Decimal("10000"))
    return (gross - cost).quantize(Decimal("0.01"))


def _micro_abnormal_vol(bars: Sequence[Any], price: Decimal) -> bool:
    """Suppress micro during catalyst-like / abnormal short-term ranges."""
    if price <= 0 or len(bars) < 20:
        return True
    highs = _highs(bars)[-20:]
    lows = _lows(bars)[-20:]
    width = (max(highs) - min(lows)) / price
    return width > Decimal("0.08")


def _micro_strong_breakout(bars: Sequence[Any]) -> bool:
    """Primary breakout/momentum owns the tape — micro must not sell into it."""
    if len(bars) < 25:
        return False
    closes = _closes(bars)
    highs = _highs(bars)
    vols = _vols(bars)
    price = closes[-1]
    prior_high = max(highs[-21:-1]) if len(highs) >= 22 else max(highs[:-1])
    if price <= prior_high:
        return False
    avg_vol = _sma(vols[:-1], 15)
    if avg_vol and vols[-1] >= avg_vol * Decimal("1.4"):
        return True
    ret5 = (closes[-1] - closes[-6]) / closes[-6] if closes[-6] else Decimal("0")
    return ret5 >= Decimal("0.012")


def detect_range_micro(bars: Sequence[Any]) -> DetectorSignal | None:
    """RANGE MICRO: buy confirmed dips near local support in a quiet range."""
    if len(bars) < 30:
        return None
    if _micro_abnormal_vol(bars, _closes(bars)[-1]):
        return None
    if _micro_strong_breakout(bars):
        return None
    closes = _closes(bars)
    highs = _highs(bars)
    lows = _lows(bars)
    vols = _vols(bars)
    price = closes[-1]
    if price <= 0:
        return None
    window_h = max(highs[-16:])
    window_l = min(lows[-16:])
    width = window_h - window_l
    if width <= 0:
        return None
    width_pct = width / price
    # Quiet oscillating range — not a trend day.
    if width_pct < Decimal("0.008") or width_pct > Decimal("0.035"):
        return None
    # Flat-ish mid: 12-bar SMA near range midpoint.
    mid = (window_h + window_l) / Decimal("2")
    slow = _sma(closes, 12)
    if slow is None or abs(slow - mid) / price > Decimal("0.012"):
        return None
    lower = window_l + (width * Decimal("0.28"))
    if price > lower:
        return None
    # Confirmation: bounce off local low + volume not collapsing.
    retest_low = min(lows[-5:])
    bounce = (price - retest_low) / retest_low if retest_low > 0 else Decimal("0")
    if bounce < Decimal("0.0015") or bounce > Decimal("0.012"):
        return None
    avg_vol = _sma(vols[:-1], 12)
    if avg_vol and vols[-1] < avg_vol * Decimal("0.45"):
        return None
    stop = window_l * Decimal("0.996")
    stop, min_target = _rr_levels(price, stop=stop, min_r=_MICRO_MIN_R)
    # Sell into local strength — mid / upper third, never inventing a top.
    strength = window_l + (width * Decimal("0.72"))
    target = max(min_target, min(strength, mid + (width * Decimal("0.15"))))
    if target <= price:
        return None
    net = _micro_net_edge_usd(price=price, target=target)
    if net is None or net < _MICRO_MIN_NET_USD:
        return DetectorSignal(
            strategy_key="range_micro",
            bias="Neutral",
            score=Decimal("35"),
            reason_code="micro_cost_gate",
            reason_text=(
                "Range micro geometry present but expected net edge after costs "
                "is too small — no trade."
            ),
            stop_loss=stop,
            take_profit=target,
            pattern="micro_range",
            detail={
                "micro_subtype": "range_micro",
                "market_regime_hint": "quiet",
                "expected_net_edge_usd": str(net) if net is not None else None,
                "cost_bps_rt": str(_MICRO_COST_BPS_RT),
                "paper_only": True,
                "avoid": True,
            },
        )
    rr = (target - price) / (price - stop) if price > stop else None
    return DetectorSignal(
        strategy_key="range_micro",
        bias="Bullish",
        score=Decimal("66"),
        reason_code=None,
        reason_text=(
            "Range micro: confirmed dip near support; targeting local strength "
            f"(est. net ${net} after costs)."
        ),
        stop_loss=stop,
        take_profit=target,
        pattern="micro_range",
        detail={
            "micro_subtype": "range_micro",
            "market_regime_hint": "quiet",
            "range_high": str(window_h),
            "range_low": str(window_l),
            "entry_zone_low": str(window_l),
            "entry_zone_high": str(lower),
            "expected_net_edge_usd": str(net),
            "risk_reward": str(rr.quantize(Decimal("0.01"))) if rr else None,
            "cost_bps_rt": str(_MICRO_COST_BPS_RT),
            "paper_only": True,
            "playbook": "range_micro",
        },
    )


def detect_trend_pullback_micro(bars: Sequence[Any]) -> DetectorSignal | None:
    """TREND MICRO: in a bullish trend, buy a qualified short pullback."""
    if len(bars) < 30:
        return None
    closes = _closes(bars)
    price = closes[-1]
    if price <= 0 or _micro_abnormal_vol(bars, price):
        return None
    if _micro_strong_breakout(bars):
        return None
    highs = _highs(bars)
    lows = _lows(bars)
    vols = _vols(bars)
    fast = _sma(closes, 5)
    slow = _sma(closes, 12)
    if fast is None or slow is None or fast <= slow:
        return None
    # Established uptrend: price above slow SMA and higher swing structure.
    if price < slow:
        return None
    swing_lows = lows[-12:]
    rising = sum(1 for i in range(1, len(swing_lows)) if swing_lows[i] >= swing_lows[i - 1])
    if rising < 5:
        return None
    # Pullback: recent dip vs local high, not a breakdown.
    local_high = max(highs[-10:])
    pullback = (local_high - price) / local_high if local_high > 0 else Decimal("0")
    if pullback < Decimal("0.004") or pullback > Decimal("0.025"):
        return None
    # Confirmation: reclaim short mid after the dip.
    mid3 = sum(closes[-4:-1], Decimal("0")) / Decimal("3")
    if price < mid3:
        return None
    bounce_low = min(lows[-6:])
    bounce = (price - bounce_low) / bounce_low if bounce_low > 0 else Decimal("0")
    if bounce < Decimal("0.001") or bounce > Decimal("0.015"):
        return None
    avg_vol = _sma(vols[:-1], 12)
    if avg_vol and vols[-1] < avg_vol * Decimal("0.4"):
        return None
    stop = bounce_low * Decimal("0.995")
    stop, min_target = _rr_levels(price, stop=stop, min_r=_MICRO_MIN_R)
    # Exit into renewed strength toward recent high / modest extension.
    strength = local_high
    target = max(min_target, min(strength, price + (price - stop) * _MICRO_MIN_R))
    if target <= price:
        return None
    net = _micro_net_edge_usd(price=price, target=target)
    if net is None or net < _MICRO_MIN_NET_USD:
        return DetectorSignal(
            strategy_key="trend_pullback_micro",
            bias="Neutral",
            score=Decimal("35"),
            reason_code="micro_cost_gate",
            reason_text=(
                "Trend pullback micro seen but net edge after costs is insufficient."
            ),
            stop_loss=stop,
            take_profit=target,
            pattern="micro_trend_pullback",
            detail={
                "micro_subtype": "trend_pullback_micro",
                "market_regime_hint": "trend_up",
                "expected_net_edge_usd": str(net) if net is not None else None,
                "cost_bps_rt": str(_MICRO_COST_BPS_RT),
                "paper_only": True,
                "avoid": True,
            },
        )
    rr = (target - price) / (price - stop) if price > stop else None
    return DetectorSignal(
        strategy_key="trend_pullback_micro",
        bias="Bullish",
        score=Decimal("67"),
        reason_code=None,
        reason_text=(
            "Trend pullback micro: bullish structure, confirmed dip; "
            f"exit into strength (est. net ${net} after costs)."
        ),
        stop_loss=stop,
        take_profit=target,
        pattern="micro_trend_pullback",
        detail={
            "micro_subtype": "trend_pullback_micro",
            "market_regime_hint": "trend_up",
            "local_high": str(local_high),
            "entry_zone_low": str(bounce_low),
            "entry_zone_high": str(price),
            "expected_net_edge_usd": str(net),
            "risk_reward": str(rr.quantize(Decimal("0.01"))) if rr else None,
            "cost_bps_rt": str(_MICRO_COST_BPS_RT),
            "paper_only": True,
            "playbook": "trend_pullback_micro",
        },
    )


DETECTORS = (
    detect_momentum_continuation,
    detect_breakout,
    detect_dip_pullback_reversal,
    detect_catalyst_retest,
    detect_range_mean_reversion,
    detect_peak_exhaustion_protection,
    detect_range_micro,
    detect_trend_pullback_micro,
)


def run_all_detectors(bars: Sequence[Any]) -> list[DetectorSignal]:
    signals: list[DetectorSignal] = []
    for fn in DETECTORS:
        try:
            sig = fn(bars)
        except Exception:  # noqa: BLE001 — one detector must not kill the scan
            continue
        if sig is not None:
            signals.append(sig)
    return signals
