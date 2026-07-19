"""Centralized operating-mode transition matrix (Phase 7)."""

from __future__ import annotations

from app.models import OperatingMode

# Edges that are structurally allowed. Availability/prerequisites may still block.
ALLOWED_TRANSITIONS: dict[OperatingMode, frozenset[OperatingMode]] = {
    OperatingMode.OFF: frozenset(
        {
            OperatingMode.OBSERVE,
            OperatingMode.SAFE_MODE,
            OperatingMode.EMERGENCY_STOP,
        }
    ),
    OperatingMode.OBSERVE: frozenset(
        {
            OperatingMode.OFF,
            OperatingMode.SAFE_MODE,
            OperatingMode.EMERGENCY_STOP,
            OperatingMode.PAPER,  # blocked by prerequisites in Phase 7
        }
    ),
    OperatingMode.PAPER: frozenset(
        {
            OperatingMode.OBSERVE,
            OperatingMode.OFF,
            OperatingMode.SAFE_MODE,
            OperatingMode.EMERGENCY_STOP,
            OperatingMode.MICRO_LIVE,  # blocked by prerequisites
        }
    ),
    OperatingMode.MICRO_LIVE: frozenset(
        {
            OperatingMode.PAPER,
            OperatingMode.OBSERVE,
            OperatingMode.OFF,
            OperatingMode.SAFE_MODE,
            OperatingMode.EMERGENCY_STOP,
            OperatingMode.NORMAL_LIVE,  # blocked by prerequisites
        }
    ),
    OperatingMode.NORMAL_LIVE: frozenset(
        {
            OperatingMode.MICRO_LIVE,
            OperatingMode.PAPER,
            OperatingMode.OBSERVE,
            OperatingMode.OFF,
            OperatingMode.SAFE_MODE,
            OperatingMode.EMERGENCY_STOP,
        }
    ),
    OperatingMode.SAFE_MODE: frozenset(
        {
            OperatingMode.OFF,
            OperatingMode.OBSERVE,
            OperatingMode.EMERGENCY_STOP,
        }
    ),
    OperatingMode.EMERGENCY_STOP: frozenset(
        {
            OperatingMode.OFF,  # Founder recovery only
        }
    ),
}

# Modes that increase institutional execution risk (unavailable in Phase 7).
RISK_INCREASING_MODES = frozenset(
    {
        OperatingMode.PAPER,
        OperatingMode.MICRO_LIVE,
        OperatingMode.NORMAL_LIVE,
    }
)

# Protective transitions that bypass ordinary policy presence requirements.
PROTECTIVE_TARGETS = frozenset(
    {
        OperatingMode.OFF,
        OperatingMode.SAFE_MODE,
        OperatingMode.EMERGENCY_STOP,
    }
)

# Modes from which the health supervisor may protectively degrade into
# SAFE_MODE (Phase 8). OFF/SAFE_MODE/EMERGENCY_STOP are excluded: OFF and
# SAFE_MODE are already at-or-below the protective floor, and EMERGENCY_STOP
# requires Founder recovery rather than an automatic system transition.
DEGRADE_ELIGIBLE_MODES = frozenset(
    {
        OperatingMode.OBSERVE,
        OperatingMode.PAPER,
        OperatingMode.MICRO_LIVE,
        OperatingMode.NORMAL_LIVE,
    }
)


def can_transition(current: OperatingMode, target: OperatingMode) -> bool:
    if current == target:
        return False
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def allowed_targets(current: OperatingMode) -> list[OperatingMode]:
    return sorted(ALLOWED_TRANSITIONS.get(current, frozenset()), key=lambda m: m.value)


def assert_transition(current: OperatingMode, target: OperatingMode) -> None:
    if not can_transition(current, target):
        raise ValueError(f"invalid transition {current.value} -> {target.value}")
