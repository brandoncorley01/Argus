"""Operating Mode State Machine service (Phase 7)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    InstitutionalRole,
    OperatingMode,
    OperatingModeHistory,
    OperatingModeIdempotency,
    SystemState,
)
from app.services.audit_service import AuditError, AuditService
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.mode_prerequisites import ModePrerequisiteEvaluator
from app.services.mode_transitions import (
    RISK_INCREASING_MODES,
    assert_transition,
    can_transition,
)


class OperatingModeError(RuntimeError):
    """Domain error for operating-mode operations."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(UTC)


def hash_idempotency_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def request_fingerprint(
    *,
    operation: str,
    target_mode: str,
    reason: str | None,
    incident_id: str | None,
    expected_state_version: int | None,
) -> str:
    payload = {
        "operation": operation,
        "target_mode": target_mode,
        "reason": reason or "",
        "incident_id": incident_id or "",
        "expected_state_version": expected_state_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class OperatingModeService:
    SINGLETON_KEY = "current"
    # Transaction-scoped advisory lock for singleton initialization (Option A).
    INIT_ADVISORY_LOCK_KEY = "argus.operating_mode.singleton"

    def __init__(self, session: Session) -> None:
        self._db = session
        self._audit = AuditService(session)
        self._prereqs = ModePrerequisiteEvaluator(session)

    def _map_integrity_error(self, exc: IntegrityError) -> OperatingModeError:
        """Map DB integrity failures to stable institutional error codes."""
        orig = getattr(exc, "orig", None)
        diag = getattr(orig, "diag", None)
        constraint = getattr(diag, "constraint_name", None) if diag is not None else None
        message = str(orig or exc).lower()
        if constraint == "uq_operating_mode_idempotency_key" or (
            "uq_operating_mode_idempotency_key" in message
        ):
            return OperatingModeError(
                "idempotency_conflict",
                "Idempotency key conflicted with a concurrent commit",
            )
        if constraint == "uq_system_states_singleton_key" or (
            "uq_system_states_singleton_key" in message
        ):
            return OperatingModeError(
                "institutional_state_conflict",
                "Concurrent SystemState creation conflicted; retry initialize",
            )
        if "incident_id" in message or (
            constraint is not None and "incident" in constraint
        ):
            return OperatingModeError(
                "invalid_reference",
                "Referenced incident does not exist",
            )
        if "policy_version" in message or (
            constraint is not None and "policy" in constraint
        ):
            return OperatingModeError(
                "invalid_reference",
                "Referenced policy version does not exist",
            )
        return OperatingModeError(
            "institutional_state_conflict",
            "Database integrity constraint rejected the operating-mode mutation",
        )

    def _require(
        self,
        actor: AuthenticatedPrincipal,
        *roles: InstitutionalRole,
        action: str,
        request_id: str | None,
    ) -> None:
        if actor.roles.isdisjoint(set(roles)):
            try:
                self._audit.append(
                    action="authz.denied",
                    resource_type="operating_mode",
                    actor_user_id=actor.user.id,
                    request_id=request_id,
                    payload={"action": action, "roles": [r.value for r in actor.roles]},
                )
                self._db.commit()
            except AuditError:
                self._db.rollback()
            raise AuthError("Forbidden")

    def _commit_with_audits(self, events: list[dict[str, Any]]) -> None:
        try:
            for event in events:
                self._audit.append(**event)
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise OperatingModeError(
                "audit_unavailable",
                "Audit persistence failed; operation aborted (fail-closed)",
            ) from None
        except Exception:
            self._db.rollback()
            raise

    def _lock_state(self) -> SystemState | None:
        self._db.execute(
            text(
                "SELECT id FROM system_states WHERE singleton_key = :key FOR UPDATE"
            ),
            {"key": self.SINGLETON_KEY},
        )
        return self._db.scalars(
            select(SystemState)
            .where(SystemState.singleton_key == self.SINGLETON_KEY)
            .execution_options(populate_existing=True)
        ).first()

    def get_state(self) -> SystemState:
        state = self._db.scalars(
            select(SystemState).where(SystemState.singleton_key == self.SINGLETON_KEY)
        ).first()
        if state is None:
            raise OperatingModeError(
                "institutional_state_missing",
                "Authoritative SystemState row is missing",
            )
        return state

    def initialize(
        self,
        *,
        actor: AuthenticatedPrincipal,
        request_id: str | None = None,
    ) -> SystemState:
        """Idempotent initialization: create OFF singleton if absent.

        Uses a transaction-scoped advisory lock so concurrent callers serialize:
        exactly one history row and one initialization audit are committed.
        """
        self._require(
            actor,
            InstitutionalRole.FOUNDER,
            action="operating_mode.initialize",
            request_id=request_id,
        )
        self._db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": self.INIT_ADVISORY_LOCK_KEY},
        )
        existing = self._db.scalars(
            select(SystemState)
            .where(SystemState.singleton_key == self.SINGLETON_KEY)
            .execution_options(populate_existing=True)
        ).first()
        if existing is not None:
            return existing

        history = OperatingModeHistory(
            from_mode=None,
            to_mode=OperatingMode.OFF,
            previous_state_version=0,
            new_state_version=1,
            changed_by_user_id=actor.user.id,
            reason="initialize",
            request_id=request_id,
            prerequisite_summary={"action": "initialize"},
        )
        self._db.add(history)
        try:
            self._db.flush()

            state = SystemState(
                singleton_key=self.SINGLETON_KEY,
                current_mode=OperatingMode.OFF,
                state_version=1,
                reason="initialize",
                emergency_stop_active=False,
                recovery_required=False,
                last_history_id=history.id,
                updated_by_user_id=actor.user.id,
            )
            self._db.add(state)
            self._db.flush()
            self._commit_with_audits(
                [
                    {
                        "action": "operating_mode.initialized",
                        "resource_type": "system_state",
                        "resource_id": str(state.id),
                        "actor_user_id": actor.user.id,
                        "request_id": request_id,
                        "mode_at_time": OperatingMode.OFF,
                        "payload": {
                            "state_version": state.state_version,
                            "current_mode": OperatingMode.OFF.value,
                        },
                    }
                ]
            )
            return state
        except IntegrityError as exc:
            self._db.rollback()
            recovered = self._db.scalars(
                select(SystemState).where(SystemState.singleton_key == self.SINGLETON_KEY)
            ).first()
            if recovered is not None:
                return recovered
            raise self._map_integrity_error(exc) from None
        except OperatingModeError:
            raise

    def list_history(self, *, limit: int = 50, offset: int = 0) -> list[OperatingModeHistory]:
        safe_limit = min(max(limit, 1), 200)
        safe_offset = max(offset, 0)
        return list(
            self._db.scalars(
                select(OperatingModeHistory)
                .order_by(OperatingModeHistory.changed_at.desc())
                .offset(safe_offset)
                .limit(safe_limit)
            )
        )

    def availability(self) -> list[dict[str, Any]]:
        return [
            {
                "mode": row.mode.value,
                "enterable": row.enterable,
                "required_authority": row.required_authority,
                "blocking_codes": row.blocking_codes,
                "required_policy": row.required_policy,
                "definitive": row.definitive,
                "notes": row.notes,
            }
            for row in self._prereqs.availability_matrix()
        ]

    def allowed_transitions(self) -> dict[str, Any]:
        state = self.get_state()
        from app.services.mode_transitions import RISK_INCREASING_MODES, allowed_targets

        structural = allowed_targets(state.current_mode)
        targets: list[dict[str, Any]] = []
        enterable_targets: list[str] = []
        for mode in structural:
            if state.current_mode == OperatingMode.EMERGENCY_STOP and mode != OperatingMode.OFF:
                blocking = ["recovery_requirements_not_met"]
                enterable = False
            else:
                prereq = self._prereqs.evaluate_entry(
                    current=state.current_mode,
                    target=mode,
                    is_emergency=False,
                    is_recovery=False,
                )
                blocking = list(prereq.blocking_codes)
                enterable = prereq.allowed
                if mode in RISK_INCREASING_MODES and "mode_unavailable" not in blocking:
                    blocking.append("mode_unavailable")
                    enterable = False
            targets.append(
                {
                    "mode": mode.value,
                    "structurally_allowed": True,
                    "enterable": enterable,
                    "blocking_codes": blocking,
                }
            )
            if enterable:
                enterable_targets.append(mode.value)

        return {
            "current_mode": state.current_mode.value,
            "state_version": state.state_version,
            "targets": targets,
            "structural_targets": [m.value for m in structural],
            "enterable_targets": enterable_targets,
        }

    def _authorize_transition(
        self,
        actor: AuthenticatedPrincipal,
        *,
        current: OperatingMode,
        target: OperatingMode,
        is_emergency: bool,
        is_recovery: bool,
        request_id: str | None,
    ) -> None:
        if is_emergency or is_recovery or target in RISK_INCREASING_MODES:
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                action=f"operating_mode.transition.{target.value}",
                request_id=request_id,
            )
            return
        if target == OperatingMode.OBSERVE:
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                action="operating_mode.transition.OBSERVE",
                request_id=request_id,
            )
            return
        # OFF / SAFE_MODE: Founder or Operator
        if target in {OperatingMode.OFF, OperatingMode.SAFE_MODE}:
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                InstitutionalRole.OPERATOR,
                action=f"operating_mode.transition.{target.value}",
                request_id=request_id,
            )
            return
        self._require(
            actor,
            InstitutionalRole.FOUNDER,
            action=f"operating_mode.transition.{target.value}",
            request_id=request_id,
        )

    def _audit_best_effort(
        self,
        *,
        action: str,
        actor: AuthenticatedPrincipal,
        request_id: str | None,
        payload: dict[str, Any],
        mode_at_time: OperatingMode | None = None,
    ) -> None:
        try:
            self._audit.append(
                action=action,
                resource_type="operating_mode",
                actor_user_id=actor.user.id,
                request_id=request_id,
                mode_at_time=mode_at_time,
                payload=payload,
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()

    def _lookup_idempotency(
        self,
        *,
        key_hash: str,
        fingerprint: str,
        operation: str,
        actor: AuthenticatedPrincipal | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any] | None:
        row = self._db.scalars(
            select(OperatingModeIdempotency).where(
                OperatingModeIdempotency.idempotency_key_hash == key_hash
            )
        ).first()
        if row is None:
            return None
        if row.request_fingerprint != fingerprint or row.operation != operation:
            if actor is not None:
                self._audit_best_effort(
                    action="operating_mode.idempotency_conflict",
                    actor=actor,
                    request_id=request_id,
                    payload={"operation": operation},
                )
            raise OperatingModeError(
                "idempotency_conflict",
                "Idempotency key reused with a different request payload",
            )
        if row.response_payload is not None:
            return dict(row.response_payload)
        raise OperatingModeError(
            "idempotency_conflict",
            "Idempotency record exists without a committed response payload",
        )

    def transition(
        self,
        *,
        actor: AuthenticatedPrincipal,
        target_mode: OperatingMode,
        reason: str,
        idempotency_key: str,
        request_id: str | None = None,
        incident_id: uuid.UUID | None = None,
        expected_state_version: int | None = None,
        is_emergency: bool = False,
        is_recovery: bool = False,
    ) -> dict[str, Any]:
        if not reason or not reason.strip():
            raise OperatingModeError("invalid_transition", "reason is required")
        if len(reason) > 2000:
            raise OperatingModeError("invalid_transition", "reason exceeds maximum length")
        if not idempotency_key or not idempotency_key.strip():
            raise OperatingModeError("invalid_transition", "Idempotency-Key is required")

        operation = (
            "emergency_stop"
            if is_emergency
            else "emergency_recover"
            if is_recovery
            else "transition"
        )
        key_hash = hash_idempotency_key(idempotency_key.strip())
        fingerprint = request_fingerprint(
            operation=operation,
            target_mode=target_mode.value,
            reason=reason.strip(),
            incident_id=str(incident_id) if incident_id else None,
            expected_state_version=expected_state_version,
        )

        # Authorize before lock (role checks do not depend on current mode).
        self._authorize_transition(
            actor,
            current=OperatingMode.OFF,
            target=target_mode,
            is_emergency=is_emergency,
            is_recovery=is_recovery,
            request_id=request_id,
        )

        # Fast path replay before lock (still re-checked under lock).
        replay = self._lookup_idempotency(
            key_hash=key_hash,
            fingerprint=fingerprint,
            operation=operation,
            actor=actor,
            request_id=request_id,
        )
        if replay is not None:
            self._audit_best_effort(
                action="operating_mode.idempotent_replay",
                actor=actor,
                request_id=request_id,
                payload={"operation": operation, "target_mode": target_mode.value},
            )
            return {**replay, "idempotent_replay": True}

        state = self._lock_state()
        if state is None:
            raise OperatingModeError(
                "institutional_state_missing",
                "Authoritative SystemState row is missing",
            )

        # Re-check idempotency under lock.
        replay = self._lookup_idempotency(
            key_hash=key_hash,
            fingerprint=fingerprint,
            operation=operation,
            actor=actor,
            request_id=request_id,
        )
        if replay is not None:
            return {**replay, "idempotent_replay": True}

        if expected_state_version is not None and state.state_version != expected_state_version:
            raise OperatingModeError(
                "stale_state",
                "expected_state_version does not match authoritative state",
            )

        current = state.current_mode

        if is_emergency:
            if target_mode != OperatingMode.EMERGENCY_STOP:
                raise OperatingModeError(
                    "invalid_transition",
                    "Emergency endpoint may only target EMERGENCY_STOP",
                )
        elif is_recovery:
            if current != OperatingMode.EMERGENCY_STOP or target_mode != OperatingMode.OFF:
                raise OperatingModeError(
                    "recovery_requirements_not_met",
                    "Recovery is only allowed from EMERGENCY_STOP to OFF",
                )
        else:
            if current == OperatingMode.EMERGENCY_STOP:
                raise OperatingModeError(
                    "recovery_requirements_not_met",
                    "Ordinary transitions are blocked while EMERGENCY_STOP is active",
                )
            try:
                assert_transition(current, target_mode)
            except ValueError as exc:
                raise OperatingModeError("invalid_transition", str(exc)) from exc

        # Structural matrix for emergency: allow from any mode.
        if is_emergency and current == OperatingMode.EMERGENCY_STOP:
            raise OperatingModeError(
                "invalid_transition",
                "Already in EMERGENCY_STOP",
            )

        if not is_emergency and not is_recovery and not can_transition(current, target_mode):
            raise OperatingModeError(
                "invalid_transition",
                f"invalid transition {current.value} -> {target_mode.value}",
            )

        prereq = self._prereqs.evaluate_entry(
            current=current,
            target=target_mode,
            is_emergency=is_emergency,
            is_recovery=is_recovery,
        )
        if not prereq.allowed:
            try:
                self._audit.append(
                    action="operating_mode.prerequisite_failed",
                    resource_type="operating_mode",
                    actor_user_id=actor.user.id,
                    request_id=request_id,
                    mode_at_time=current,
                    payload={
                        "target_mode": target_mode.value,
                        "blocking_codes": prereq.blocking_codes,
                    },
                )
                self._db.commit()
            except AuditError:
                self._db.rollback()
            raise OperatingModeError(
                "prerequisite_failed",
                "; ".join(prereq.blocking_codes) or "prerequisites not met",
            )

        # Attach active operating policy when present and hash-valid (optional for
        # protective/OBSERVE paths; risk-increasing modes already blocked above).
        policy = self._prereqs.resolve_active_operating_policy()

        previous_version = state.state_version
        new_version = previous_version + 1
        now = _utcnow()

        history = OperatingModeHistory(
            from_mode=current,
            to_mode=target_mode,
            previous_state_version=previous_version,
            new_state_version=new_version,
            changed_by_user_id=actor.user.id,
            reason=reason.strip(),
            request_id=request_id,
            policy_version_id=policy.id if policy else None,
            incident_id=incident_id,
            idempotency_key_hash=key_hash,
            request_fingerprint=fingerprint,
            prerequisite_summary=prereq.as_summary(),
            changed_at=now,
        )
        self._db.add(history)
        self._db.flush()

        state.current_mode = target_mode
        state.state_version = new_version
        state.reason = reason.strip()
        state.updated_by_user_id = actor.user.id
        state.updated_at = now
        state.last_history_id = history.id
        if policy is not None:
            state.active_policy_version_id = policy.id
        if target_mode == OperatingMode.EMERGENCY_STOP:
            state.emergency_stop_active = True
            state.recovery_required = True
        if is_recovery and target_mode == OperatingMode.OFF:
            state.emergency_stop_active = False
            state.recovery_required = False
        self._db.add(state)

        result = {
            "current_mode": target_mode.value,
            "previous_mode": current.value,
            "state_version": new_version,
            "previous_state_version": previous_version,
            "history_id": str(history.id),
            "emergency_stop_active": state.emergency_stop_active,
            "recovery_required": state.recovery_required,
            "reason": reason.strip(),
            "policy_version_id": str(policy.id) if policy else None,
        }

        idem = OperatingModeIdempotency(
            idempotency_key_hash=key_hash,
            request_fingerprint=fingerprint,
            operation=operation,
            history_id=history.id,
            status="committed",
            response_payload=result,
        )
        self._db.add(idem)

        audit_action = "operating_mode.transition_succeeded"
        if target_mode == OperatingMode.SAFE_MODE:
            audit_action = "operating_mode.safe_mode_entered"
        if target_mode == OperatingMode.EMERGENCY_STOP:
            audit_action = "operating_mode.emergency_stop_entered"
        if is_recovery:
            audit_action = "operating_mode.emergency_stop_cleared"

        try:
            self._commit_with_audits(
                [
                    {
                        "action": audit_action,
                        "resource_type": "system_state",
                        "resource_id": str(state.id),
                        "actor_user_id": actor.user.id,
                        "request_id": request_id,
                        "mode_at_time": target_mode,
                        "policy_version_id": policy.id if policy else None,
                        "payload": {
                            "previous_mode": current.value,
                            "new_mode": target_mode.value,
                            "previous_state_version": previous_version,
                            "new_state_version": new_version,
                            "history_id": str(history.id),
                            "operation": operation,
                        },
                    }
                ]
            )
        except IntegrityError as exc:
            self._db.rollback()
            mapped = self._map_integrity_error(exc)
            if mapped.code == "idempotency_conflict":
                replay = self._lookup_idempotency(
                    key_hash=key_hash,
                    fingerprint=fingerprint,
                    operation=operation,
                    actor=actor,
                    request_id=request_id,
                )
                if replay is not None:
                    return {**replay, "idempotent_replay": True}
            raise mapped from None
        return {**result, "idempotent_replay": False}

    def emergency_stop(
        self,
        *,
        actor: AuthenticatedPrincipal,
        reason: str,
        idempotency_key: str,
        request_id: str | None = None,
        incident_id: uuid.UUID | None = None,
        expected_state_version: int | None = None,
    ) -> dict[str, Any]:
        return self.transition(
            actor=actor,
            target_mode=OperatingMode.EMERGENCY_STOP,
            reason=reason,
            idempotency_key=idempotency_key,
            request_id=request_id,
            incident_id=incident_id,
            expected_state_version=expected_state_version,
            is_emergency=True,
        )

    def recover_from_emergency(
        self,
        *,
        actor: AuthenticatedPrincipal,
        reason: str,
        idempotency_key: str,
        request_id: str | None = None,
        expected_state_version: int | None = None,
    ) -> dict[str, Any]:
        return self.transition(
            actor=actor,
            target_mode=OperatingMode.OFF,
            reason=reason,
            idempotency_key=idempotency_key,
            request_id=request_id,
            expected_state_version=expected_state_version,
            is_recovery=True,
        )
