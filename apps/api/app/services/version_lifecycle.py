from __future__ import annotations

from app.models import VersionLifecycleStatus

ALLOWED_TRANSITIONS: dict[VersionLifecycleStatus, set[VersionLifecycleStatus]] = {
    VersionLifecycleStatus.DRAFT: {VersionLifecycleStatus.UNDER_REVIEW},
    VersionLifecycleStatus.UNDER_REVIEW: {
        VersionLifecycleStatus.APPROVED,
        VersionLifecycleStatus.REJECTED,
        VersionLifecycleStatus.DRAFT,  # explicit return-to-draft
    },
    VersionLifecycleStatus.APPROVED: {
        VersionLifecycleStatus.ACTIVE,
        VersionLifecycleStatus.RETIRED,
    },
    VersionLifecycleStatus.ACTIVE: {
        VersionLifecycleStatus.SUPERSEDED,
        VersionLifecycleStatus.RETIRED,
    },
    VersionLifecycleStatus.SUPERSEDED: set(),
    VersionLifecycleStatus.REJECTED: set(),
    VersionLifecycleStatus.RETIRED: set(),
}


def can_transition(current: VersionLifecycleStatus, new: VersionLifecycleStatus) -> bool:
    return new in ALLOWED_TRANSITIONS.get(current, set())


def assert_transition(current: VersionLifecycleStatus, new: VersionLifecycleStatus) -> None:
    if not can_transition(current, new):
        raise ValueError(f"invalid transition {current.value} -> {new.value}")
