"""Operating-mode availability and prerequisite evaluation (Phase 7).

Phase 13 note: Argus's global ``OperatingMode`` state machine (this module)
and the Phase 13 ``live_activation_state`` machine
(``app.services.live_activation_service``) are deliberately independent.
``RISK_INCREASING_MODES`` (PAPER/MICRO_LIVE/NORMAL_LIVE) remains
unconditionally blocked here regardless of Phase 13 activation progress —
Phase 13 implements the micro-live *architecture* (adapters, credential
references, kill switches, capital policy, reconciliation) without unlocking
the global MICRO_LIVE operating mode. Entering the global ``MICRO_LIVE``
operating mode would require BOTH an unlocked ``feat.mode.micro_live``
registry entry AND ``live_activation_state.current_state ==
MICRO_LIVE_ACTIVE`` — and the latter has no reachable code path in this
phase (see ADR-029). ``feat.trading.live`` remains locked. ``NORMAL_LIVE``
is not unlocked by anything in Phase 13. The Phase 12 paper trading HTTP API
(``/api/v1/paper``) already operates independently of the OperatingMode
machine via the Execution Gateway's own paper/deterministic_test allowlist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    FeatureActivationState,
    FeatureRegistryEntry,
    OperatingMode,
    PolicyKind,
    PolicyVersion,
    VersionLifecycleStatus,
)
from app.services.mode_transitions import RISK_INCREASING_MODES
from app.services.payload_integrity import verify_payload_hash

# Feature keys that must remain locked for live/paper execution in v0.1.
LOCKED_EXECUTION_FEATURES = frozenset(
    {
        "feat.mode.micro_live",
        "feat.mode.normal_live",
        "feat.trading.live",
    }
)


@dataclass
class PrerequisiteResult:
    allowed: bool
    blocking_codes: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def as_summary(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blocking_codes": list(self.blocking_codes),
            "details": dict(self.details),
        }


@dataclass
class ModeAvailability:
    mode: OperatingMode
    enterable: bool
    required_authority: str
    blocking_codes: list[str]
    required_policy: str | None
    definitive: bool
    notes: str | None = None


class ModePrerequisiteEvaluator:
    def __init__(self, session: Session) -> None:
        self._db = session

    def evaluate_entry(
        self,
        *,
        current: OperatingMode,
        target: OperatingMode,
        is_emergency: bool = False,
        is_recovery: bool = False,
    ) -> PrerequisiteResult:
        codes: list[str] = []
        details: dict[str, Any] = {
            "current": current.value,
            "target": target.value,
            "is_emergency": is_emergency,
            "is_recovery": is_recovery,
        }

        if is_emergency and target == OperatingMode.EMERGENCY_STOP:
            # Emergency entry bypasses ordinary capability/policy readiness.
            return PrerequisiteResult(allowed=True, blocking_codes=[], details=details)

        if is_recovery and target == OperatingMode.OFF and current == OperatingMode.EMERGENCY_STOP:
            return PrerequisiteResult(allowed=True, blocking_codes=[], details=details)

        if target in RISK_INCREASING_MODES:
            codes.append("mode_unavailable")
            codes.append("execution_capability_not_implemented")
            details["phase7_policy"] = (
                "PAPER/MICRO_LIVE/NORMAL_LIVE unavailable at the OperatingMode layer"
            )
            if target == OperatingMode.MICRO_LIVE:
                details["phase13_policy"] = (
                    "Phase 13 implements the micro-live architecture behind its own "
                    "live_activation_state machine, but does not unlock this global "
                    "OperatingMode. Entry would require feat.mode.micro_live unlocked "
                    "AND live_activation_state == MICRO_LIVE_ACTIVE, and the latter has "
                    "no reachable code path in Phase 13 (see ADR-029)."
                )
            # Feature registry locks reinforce the unavailable posture.
            locked = self._locked_execution_features()
            if locked:
                codes.append("feature_registry_locked")
                details["locked_features"] = locked

        if target == OperatingMode.OBSERVE and current == OperatingMode.SAFE_MODE:
            # Phase 7: minimal recovery — Founder + reason enforced at service layer.
            details["recovery"] = "minimal_phase7"

        # Active operating policy integrity is required for risk-increasing modes only.
        if target in RISK_INCREASING_MODES:
            policy_check = self._check_active_operating_policy()
            if not policy_check.allowed:
                codes.extend(policy_check.blocking_codes)
                details["policy"] = policy_check.details

        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique_codes = []
        for code in codes:
            if code not in seen:
                seen.add(code)
                unique_codes.append(code)

        return PrerequisiteResult(
            allowed=len(unique_codes) == 0,
            blocking_codes=unique_codes,
            details=details,
        )

    def availability_matrix(self) -> list[ModeAvailability]:
        rows: list[ModeAvailability] = []
        for mode in OperatingMode:
            if mode in RISK_INCREASING_MODES:
                rows.append(
                    ModeAvailability(
                        mode=mode,
                        enterable=False,
                        required_authority="FOUNDER",
                        blocking_codes=[
                            "mode_unavailable",
                            "execution_capability_not_implemented",
                        ],
                        required_policy="policy.operating.v1",
                        definitive=True,
                        notes="Defined in enum; unavailable in Phase 7",
                    )
                )
            elif mode == OperatingMode.EMERGENCY_STOP:
                rows.append(
                    ModeAvailability(
                        mode=mode,
                        enterable=True,
                        required_authority="FOUNDER",
                        blocking_codes=[],
                        required_policy=None,
                        definitive=True,
                        notes="Protective override; Founder only",
                    )
                )
            elif mode == OperatingMode.SAFE_MODE:
                rows.append(
                    ModeAvailability(
                        mode=mode,
                        enterable=True,
                        required_authority="FOUNDER_OR_OPERATOR",
                        blocking_codes=[],
                        required_policy=None,
                        definitive=True,
                    )
                )
            elif mode == OperatingMode.OFF:
                rows.append(
                    ModeAvailability(
                        mode=mode,
                        enterable=True,
                        required_authority="FOUNDER_OR_OPERATOR",
                        blocking_codes=[],
                        required_policy=None,
                        definitive=True,
                    )
                )
            else:  # OBSERVE
                rows.append(
                    ModeAvailability(
                        mode=mode,
                        enterable=True,
                        required_authority="FOUNDER",
                        blocking_codes=[],
                        required_policy=None,
                        definitive=True,
                        notes="Enterable without active operating policy (D2)",
                    )
                )
        return rows

    def _locked_execution_features(self) -> list[str]:
        rows = list(
            self._db.scalars(
                select(FeatureRegistryEntry).where(
                    FeatureRegistryEntry.feature_key.in_(LOCKED_EXECUTION_FEATURES)
                )
            )
        )
        locked = [
            row.feature_key
            for row in rows
            if row.activation_state == FeatureActivationState.LOCKED
        ]
        # If registry rows are absent, treat as unavailable (honest unknown/unavailable).
        missing = sorted(LOCKED_EXECUTION_FEATURES - {r.feature_key for r in rows})
        return locked + [f"{key}:missing" for key in missing]

    def _check_active_operating_policy(self) -> PrerequisiteResult:
        active = self._db.scalars(
            select(PolicyVersion)
            .join(PolicyVersion.document)
            .where(
                PolicyVersion.status == VersionLifecycleStatus.ACTIVE,
            )
        ).all()
        operating = [
            row
            for row in active
            if row.document.policy_kind == PolicyKind.OPERATING
        ]
        if not operating:
            return PrerequisiteResult(
                allowed=False,
                blocking_codes=["policy_missing"],
                details={"policy_kind": PolicyKind.OPERATING.value},
            )
        version = operating[0]
        if not verify_payload_hash(version.content, version.payload_hash):
            return PrerequisiteResult(
                allowed=False,
                blocking_codes=["policy_integrity_failed"],
                details={"policy_version_id": str(version.id)},
            )
        return PrerequisiteResult(
            allowed=True,
            details={"policy_version_id": str(version.id)},
        )

    def resolve_active_operating_policy(self) -> PolicyVersion | None:
        """Return the ACTIVE operating policy if present and hash-valid; else None."""
        rows = self._db.scalars(
            select(PolicyVersion)
            .options(selectinload(PolicyVersion.document))
            .where(PolicyVersion.status == VersionLifecycleStatus.ACTIVE)
        ).all()
        for row in rows:
            if row.document.policy_kind != PolicyKind.OPERATING:
                continue
            if verify_payload_hash(row.content, row.payload_hash):
                return row
            return None
        return None
