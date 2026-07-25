"""Plain-language Founder copy for statuses, rejections, and readiness."""

from __future__ import annotations

REJECTION_PLAIN: dict[str, str] = {
    "insufficient_history": (
        "There is not enough recent price history to evaluate this strategy safely."
    ),
    "stale_data": "Market prices are too old. Argus will not open a trade until prices refresh.",
    "low_liquidity": "Recent trading volume is too low for a safe entry.",
    "weak_signal": "The move is not strong enough to meet Argus entry rules.",
    "confirmation_incomplete": "Argus is waiting for more confirmation before entering.",
    "excessive_volatility": "Price swings are too large for the allowed risk.",
    "poor_risk_reward": "The possible reward is too small compared with the risk.",
    "exposure_limit": "This would put too much paper money into one area.",
    "daily_risk_limit": "Daily paper risk limits are reached.",
    "pause_new_entries": "New paper entries are paused by the Founder.",
    "execution_unavailable": "Paper trading is blocked (kill switch or execution unavailable).",
    "no_instruments": "No markets are registered for scanning yet.",
}

STAGE_PLAIN: dict[str, str] = {
    "Discovered": "Just noticed",
    "Watching": "Watching",
    "Evaluating": "Checking",
    "Risk Review": "Checking risk",
    "Approved": "Ready",
    "Rejected": "Rejected",
    "Entered": "Entered (paper)",
    "Expired": "Expired",
    "Teaching": "Founder note",
}

BIAS_PLAIN: dict[str, str] = {
    "Bullish": "Price may rise",
    "Bearish": "Price may fall",
    "Neutral": "No clear direction",
}


def plain_rejection(code: str | None, fallback: str | None = None) -> str:
    if code and code in REJECTION_PLAIN:
        return REJECTION_PLAIN[code]
    if fallback:
        return fallback
    return "Argus decided not to take this setup."


def confidence_from_score(score: float) -> str:
    if score >= 80:
        return "High"
    if score >= 50:
        return "Medium"
    return "Low"


def readiness_action(*, bar_count: int, min_bars: int, stale: bool, has_instrument: bool) -> str:
    if not has_instrument:
        return (
            "Register markets under Advanced → Market, then keep Argus running "
            "while price history is collected."
        )
    if bar_count < min_bars:
        return (
            f"Argus has {bar_count} of {min_bars} recent price points needed. "
            "Keep Argus running while it collects data, or check the market-data connection "
            "under Advanced → Market."
        )
    if stale:
        return (
            "Prices are outdated. Check the market-data connection under Advanced → Market, "
            "then press Scan markets now."
        )
    return "Recent price history looks ready for evaluation."
