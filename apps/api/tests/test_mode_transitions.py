"""Unit tests for the operating-mode transition matrix."""

from __future__ import annotations

import pytest

from app.models import OperatingMode
from app.services.mode_transitions import (
    ALLOWED_TRANSITIONS,
    RISK_INCREASING_MODES,
    assert_transition,
    can_transition,
)


def test_all_modes_have_matrix_entries() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(OperatingMode)


def test_emergency_stop_only_recovers_to_off() -> None:
    assert ALLOWED_TRANSITIONS[OperatingMode.EMERGENCY_STOP] == frozenset({OperatingMode.OFF})


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (OperatingMode.OFF, OperatingMode.OBSERVE, True),
        (OperatingMode.OFF, OperatingMode.PAPER, False),
        (OperatingMode.OBSERVE, OperatingMode.PAPER, True),
        (OperatingMode.SAFE_MODE, OperatingMode.OBSERVE, True),
        (OperatingMode.EMERGENCY_STOP, OperatingMode.OBSERVE, False),
        (OperatingMode.EMERGENCY_STOP, OperatingMode.OFF, True),
        (OperatingMode.OFF, OperatingMode.OFF, False),
    ],
)
def test_can_transition_edges(
    current: OperatingMode, target: OperatingMode, allowed: bool
) -> None:
    assert can_transition(current, target) is allowed


def test_assert_transition_raises() -> None:
    with pytest.raises(ValueError, match="invalid transition"):
        assert_transition(OperatingMode.OFF, OperatingMode.NORMAL_LIVE)


def test_risk_increasing_modes() -> None:
    assert RISK_INCREASING_MODES == frozenset(
        {OperatingMode.PAPER, OperatingMode.MICRO_LIVE, OperatingMode.NORMAL_LIVE}
    )
