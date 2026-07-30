"""Host-sleep / downtime continuity helpers.

Argus is local-first. When the Founder PC sleeps or hibernates, ARQ cron
stops. On wake (or worker restart) we detect wall-clock gaps and force a
price refresh + scan so paper automation resumes without Founder attention.

Does not fabricate market data or trading activity.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# Health cycles run every 30s. A gap well above that means the host slept,
# the worker was suspended, or the process was down.
DEFAULT_GAP_THRESHOLD = timedelta(seconds=90)


def utcnow() -> datetime:
    return datetime.now(UTC)


def wall_clock_gap(
    previous: datetime | None,
    now: datetime | None = None,
) -> timedelta | None:
    """Return elapsed wall time since *previous*, or None if unknown."""
    if previous is None:
        return None
    current = now or utcnow()
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    gap = current - previous
    return gap if gap.total_seconds() >= 0 else timedelta(0)


def should_catch_up_after_gap(
    gap: timedelta | None,
    *,
    threshold: timedelta = DEFAULT_GAP_THRESHOLD,
) -> bool:
    """True when the wall-clock gap implies the host/worker was suspended."""
    if gap is None:
        return False
    return gap >= threshold


def format_gap_seconds(gap: timedelta | None) -> float | None:
    if gap is None:
        return None
    return round(gap.total_seconds(), 3)
