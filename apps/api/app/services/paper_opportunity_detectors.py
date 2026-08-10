"""Lightweight deterministic PAPER opportunity detectors from OHLCV bars.

PAPER observation only — never submits orders. Each detector returns the same
shape consumed by MarketScanService candidate creation so strategies compete
through Alpha Radar / scan pipeline alongside sma_crossover.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence


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


def _rr_levels(
    price: Decimal, *, stop: Decimal, min_r: Decimal = Decimal("2")
) -> tuple[Decimal, Decimal]:
    if stop >= price:
        stop = price * (Decimal("1") - Decimal("0.01"))
    risk = price - stop
    if risk <= 0:
        risk = price * Decimal("0.01")
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
    # Bearish/Neutral protection — does not open longs; scan stores as Neutral Rejected/Expired helper.
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


DETECTORS = (
    detect_momentum_continuation,
    detect_breakout,
    detect_dip_pullback_reversal,
    detect_range_mean_reversion,
    detect_peak_exhaustion_protection,
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
