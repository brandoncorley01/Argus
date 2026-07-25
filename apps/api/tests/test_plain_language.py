"""Unit tests for Founder plain-language helpers."""

from app.services.plain_language import (
    confidence_from_score,
    plain_rejection,
    readiness_action,
)


def test_plain_rejection_known_code() -> None:
    text = plain_rejection("insufficient_history")
    assert "price history" in text.lower()


def test_plain_rejection_fallback() -> None:
    assert plain_rejection(None, "Custom reason.") == "Custom reason."


def test_confidence_bands() -> None:
    assert confidence_from_score(90) == "High"
    assert confidence_from_score(55) == "Medium"
    assert confidence_from_score(10) == "Low"


def test_readiness_action_missing_instrument() -> None:
    text = readiness_action(bar_count=0, min_bars=25, stale=True, has_instrument=False)
    assert "Register markets" in text or "price history" in text.lower()


def test_readiness_action_short_history() -> None:
    text = readiness_action(bar_count=3, min_bars=25, stale=False, has_instrument=True)
    assert "3 of 25" in text
