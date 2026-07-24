"""Phase 13 live-activation state machine — deny-by-default, Founder-gated.

This is Argus's OWN activation state machine, entirely separate from the
global ``OperatingMode`` machine (Phase 7). Reaching ``MICRO_LIVE_ACTIVE``
here is a *necessary but never sufficient* condition for the global
``OperatingMode`` to enter ``MICRO_LIVE`` — ``RISK_INCREASING_MODES`` still
blocks ``MICRO_LIVE``/``NORMAL_LIVE`` unconditionally at the OperatingMode
layer (see ``mode_prerequisites.py`` and ADR-029).

Critical invariant: **there is no code path in this module that can ever
set ``current_state`` to ``MICRO_LIVE_ACTIVE``.** The transition is
structurally defined (for architectural completeness) but is unconditionally
rejected before any other check runs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InstitutionalRole
from app.models.micro_live import (
    CredentialReference,
    LiveActivationState,
    LiveActivationStateRow,
    LiveActivationTransition,
)
from app.secrets.contracts import SecretsProvider
from app.secrets.env_provider import EnvSecretsProvider
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal

# Structurally allowed edges. Availability of a transition here does not mean
# it will succeed — Founder-authority and credential-presence gates below,
# and the unconditional MICRO_LIVE_ACTIVE block, run first.
ALLOWED_TRANSITIONS: dict[LiveActivationState, frozenset[LiveActivationState]] = {
    LiveActivationState.DISABLED: frozenset({LiveActivationState.PAPER_ONLY}),
    LiveActivationState.PAPER_ONLY: frozenset(
        {
            LiveActivationState.ADAPTER_CONFIGURED,
            LiveActivationState.SUSPENDED,
            LiveActivationState.EMERGENCY_STOP,
        }
    ),
    LiveActivationState.ADAPTER_CONFIGURED: frozenset(
        {
            LiveActivationState.CREDENTIAL_REFERENCE_CONFIGURED,
            LiveActivationState.PAPER_ONLY,
            LiveActivationState.SUSPENDED,
            LiveActivationState.EMERGENCY_STOP,
        }
    ),
    LiveActivationState.CREDENTIAL_REFERENCE_CONFIGURED: frozenset(
        {
            LiveActivationState.CONNECTION_VERIFIED,
            LiveActivationState.PAPER_ONLY,
            LiveActivationState.SUSPENDED,
            LiveActivationState.EMERGENCY_STOP,
        }
    ),
    LiveActivationState.CONNECTION_VERIFIED: frozenset(
        {
            LiveActivationState.OBSERVE_ONLY,
            LiveActivationState.PAPER_ONLY,
            LiveActivationState.SUSPENDED,
            LiveActivationState.EMERGENCY_STOP,
        }
    ),
    LiveActivationState.OBSERVE_ONLY: frozenset(
        {
            LiveActivationState.SANDBOX_OR_TESTNET,
            LiveActivationState.PAPER_ONLY,
            LiveActivationState.SUSPENDED,
            LiveActivationState.EMERGENCY_STOP,
        }
    ),
    LiveActivationState.SANDBOX_OR_TESTNET: frozenset(
        {
            LiveActivationState.SHADOW_MODE,
            LiveActivationState.OBSERVE_ONLY,
            LiveActivationState.PAPER_ONLY,
            LiveActivationState.SUSPENDED,
            LiveActivationState.EMERGENCY_STOP,
        }
    ),
    LiveActivationState.SHADOW_MODE: frozenset(
        {
            LiveActivationState.MICRO_LIVE_ARMED,
            LiveActivationState.SANDBOX_OR_TESTNET,
            LiveActivationState.PAPER_ONLY,
            LiveActivationState.SUSPENDED,
            LiveActivationState.EMERGENCY_STOP,
        }
    ),
    # MICRO_LIVE_ACTIVE is structurally reachable from MICRO_LIVE_ARMED for
    # future-phase documentation purposes only — `transition()` rejects it
    # unconditionally before this edge is ever consulted.
    LiveActivationState.MICRO_LIVE_ARMED: frozenset(
        {
            LiveActivationState.MICRO_LIVE_ACTIVE,
            LiveActivationState.SHADOW_MODE,
            LiveActivationState.PAPER_ONLY,
            LiveActivationState.SUSPENDED,
            LiveActivationState.EMERGENCY_STOP,
        }
    ),
    LiveActivationState.MICRO_LIVE_ACTIVE: frozenset(
        {
            LiveActivationState.SUSPENDED,
            LiveActivationState.EMERGENCY_STOP,
            LiveActivationState.PAPER_ONLY,
        }
    ),
    LiveActivationState.SUSPENDED: frozenset(
        {
            LiveActivationState.PAPER_ONLY,
            LiveActivationState.EMERGENCY_STOP,
            LiveActivationState.RECOVERY,
        }
    ),
    LiveActivationState.EMERGENCY_STOP: frozenset({LiveActivationState.RECOVERY}),
    LiveActivationState.RECOVERY: frozenset({LiveActivationState.PAPER_ONLY}),
}

# States that require Founder authority to enter.
FOUNDER_ONLY_STATES = frozenset(
    {
        LiveActivationState.SHADOW_MODE,
        LiveActivationState.MICRO_LIVE_ARMED,
        LiveActivationState.MICRO_LIVE_ACTIVE,
        LiveActivationState.EMERGENCY_STOP,
        LiveActivationState.RECOVERY,
    }
)

# States that require at least one present-and-validated credential reference.
CREDENTIALS_REQUIRED_STATES = frozenset(
    {
        LiveActivationState.CONNECTION_VERIFIED,
        LiveActivationState.OBSERVE_ONLY,
        LiveActivationState.SANDBOX_OR_TESTNET,
        LiveActivationState.SHADOW_MODE,
        LiveActivationState.MICRO_LIVE_ARMED,
        LiveActivationState.MICRO_LIVE_ACTIVE,
    }
)


class LiveActivationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class ActivationStatus:
    activation_state: str
    state_version: int
    credentials_configured: bool
    live_execution_active: bool
    live_capable_architecture: bool
    paper_provider_default: bool
    updated_at: datetime
    evidence: dict[str, Any] = field(default_factory=dict)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class LiveActivationService:
    def __init__(self, db: Session, secrets: SecretsProvider | None = None) -> None:
        self.db = db
        self.audit = AuditService(db)
        self._secrets = secrets or EnvSecretsProvider()

    def get_state_row(self) -> LiveActivationStateRow:
        row = self.db.scalar(
            select(LiveActivationStateRow).where(
                LiveActivationStateRow.singleton_key == "current"
            )
        )
        if row is None:
            row = LiveActivationStateRow(
                singleton_key="current",
                current_state=LiveActivationState.PAPER_ONLY.value,
                state_version=0,
                evidence={"reason": "auto_initialized"},
            )
            self.db.add(row)
            self.db.flush()
        return row

    def has_present_credential(self) -> bool:
        return (
            self.db.scalar(
                select(CredentialReference.id).where(
                    CredentialReference.is_present_cached.is_(True)
                )
            )
            is not None
        )

    def status(self) -> ActivationStatus:
        row = self.get_state_row()
        credentials_configured = self.has_present_credential()
        return ActivationStatus(
            activation_state=row.current_state,
            state_version=row.state_version,
            credentials_configured=credentials_configured,
            live_execution_active=row.current_state
            == LiveActivationState.MICRO_LIVE_ACTIVE.value,
            live_capable_architecture=True,
            paper_provider_default=True,
            updated_at=row.updated_at,
            evidence=dict(row.evidence or {}),
        )

    def list_transitions(self, *, limit: int = 100) -> list[LiveActivationTransition]:
        safe_limit = min(max(limit, 1), 500)
        return list(
            self.db.scalars(
                select(LiveActivationTransition)
                .order_by(LiveActivationTransition.changed_at.desc())
                .limit(safe_limit)
            )
        )

    def transition(
        self,
        *,
        target: str,
        reason: str,
        evidence: dict[str, Any] | None,
        actor: AuthenticatedPrincipal,
    ) -> LiveActivationStateRow:
        try:
            target_state = LiveActivationState(target)
        except ValueError as exc:
            raise LiveActivationError("invalid_state", f"Unknown state: {target}") from exc

        # Absolute institutional gate: no path — automated or Founder-invoked
        # — reaches MICRO_LIVE_ACTIVE in Phase 13. Checked before anything
        # else so no combination of role/credentials/evidence can bypass it.
        if target_state == LiveActivationState.MICRO_LIVE_ACTIVE:
            raise LiveActivationError(
                "live_execution_not_certified",
                "MICRO_LIVE_ACTIVE has no automated or manual activation path in "
                "Phase 13 (deny-by-default; live trading remains disabled)",
            )

        row = self.get_state_row()
        try:
            current_state = LiveActivationState(row.current_state)
        except ValueError as exc:
            raise LiveActivationError(
                "corrupt_state", f"Unknown persisted state: {row.current_state}"
            ) from exc

        if target_state not in ALLOWED_TRANSITIONS.get(current_state, frozenset()):
            raise LiveActivationError(
                "invalid_transition",
                f"Transition {current_state.value} -> {target_state.value} is not allowed",
            )

        if target_state in FOUNDER_ONLY_STATES and InstitutionalRole.FOUNDER not in actor.roles:
            raise LiveActivationError(
                "founder_required",
                f"Transition to {target_state.value} requires the Founder role",
            )

        if target_state in CREDENTIALS_REQUIRED_STATES and not self.has_present_credential():
            raise LiveActivationError(
                "credentials_required",
                "No present credential reference is configured; system remains "
                "PAPER_ONLY-operational without credentials",
            )

        if not reason or not reason.strip():
            raise LiveActivationError("reason_required", "A transition reason is required")

        previous_version = row.state_version
        new_version = previous_version + 1
        merged_evidence = dict(evidence or {})
        merged_evidence.setdefault("credentials_configured", self.has_present_credential())

        self.db.add(
            LiveActivationTransition(
                from_state=row.current_state,
                to_state=target_state.value,
                previous_state_version=previous_version,
                new_state_version=new_version,
                reason=reason.strip(),
                evidence=merged_evidence,
                changed_by_user_id=actor.user.id,
            )
        )
        row.current_state = target_state.value
        row.state_version = new_version
        row.evidence = merged_evidence
        row.updated_by_user_id = actor.user.id
        row.updated_at = _utcnow()

        self.audit.append(
            action="micro_live.activation.transition",
            resource_type="live_activation_state",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={
                "from_state": current_state.value,
                "to_state": target_state.value,
                "reason": reason.strip(),
            },
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    # --- credential references — REF NAMES ONLY, never values ---

    def list_credential_references(self) -> list[CredentialReference]:
        return list(
            self.db.scalars(
                select(CredentialReference).order_by(CredentialReference.created_at.desc())
            )
        )

    def create_credential_reference(
        self,
        *,
        provider_key: str,
        ref_name: str,
        purpose: str,
        actor: AuthenticatedPrincipal,
    ) -> CredentialReference:
        if not ref_name or not ref_name.strip():
            raise LiveActivationError("invalid_reference", "ref_name is required")
        existing = self.db.scalar(
            select(CredentialReference).where(
                CredentialReference.provider_key == provider_key,
                CredentialReference.ref_name == ref_name,
            )
        )
        if existing is not None:
            return existing

        row = CredentialReference(
            provider_key=provider_key,
            ref_name=ref_name.strip(),
            purpose=purpose,
            is_present_cached=False,
            created_by_user_id=actor.user.id,
        )
        self.db.add(row)
        self.db.flush()
        # Audit payload contains only the reference NAME, never a value.
        self.audit.append(
            action="micro_live.credential_reference.create",
            resource_type="credential_reference",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"provider_key": provider_key, "ref_name": row.ref_name},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def validate_credential_reference(
        self, reference_id: uuid.UUID, *, actor: AuthenticatedPrincipal
    ) -> CredentialReference:
        row = self.db.get(CredentialReference, reference_id)
        if row is None:
            raise LiveActivationError("reference_not_found", str(reference_id))

        status = self._secrets.get_reference_status(row.ref_name)
        row.is_present_cached = status.present
        row.last_validated_at = status.checked_at

        # Redacted-by-construction: only ref_name + boolean presence, never
        # the underlying value (the SecretsProvider never returns it either).
        self.audit.append(
            action="micro_live.credential_reference.validate",
            resource_type="credential_reference",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"ref_name": row.ref_name, "present": status.present},
        )
        self.db.commit()
        self.db.refresh(row)
        return row
