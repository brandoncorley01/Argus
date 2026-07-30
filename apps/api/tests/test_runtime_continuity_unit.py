"""Unit tests for host-sleep / downtime continuity helpers."""

from datetime import UTC, datetime, timedelta

from app.services.runtime_continuity import (
    DEFAULT_GAP_THRESHOLD,
    format_gap_seconds,
    should_catch_up_after_gap,
    wall_clock_gap,
)


def test_wall_clock_gap_none_when_previous_missing() -> None:
    assert wall_clock_gap(None) is None


def test_wall_clock_gap_positive() -> None:
    previous = datetime(2026, 7, 30, 12, 0, 0, tzinfo=UTC)
    now = previous + timedelta(minutes=5)
    gap = wall_clock_gap(previous, now)
    assert gap == timedelta(minutes=5)


def test_should_catch_up_after_sleep_gap() -> None:
    assert should_catch_up_after_gap(timedelta(seconds=30)) is False
    assert should_catch_up_after_gap(DEFAULT_GAP_THRESHOLD) is True
    assert should_catch_up_after_gap(timedelta(minutes=10)) is True
    assert should_catch_up_after_gap(None) is False


def test_format_gap_seconds() -> None:
    assert format_gap_seconds(None) is None
    assert format_gap_seconds(timedelta(seconds=90)) == 90.0
