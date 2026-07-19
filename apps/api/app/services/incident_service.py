"""System and human incident lifecycle management (Phase 8).

Incidents may be opened by the health supervisor (system, `actor=None`,
`opened_by_system=True`) or by a human Founder/Operator. System-opened
incidents are keyed by a `correlation_key` and deduplicated via the
`ix_incidents_open_correlation` partial-unique index (one open incident per
correlation key at a time). Every transition is recorded as an append-only
`IncidentLifecycleEvent` (DB trigger enforces immutability) and audited
fail-closed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Incident,
    IncidentLifecycleEvent,
    IncidentLifecycleEventType,
    IncidentSeverity,
    IncidentStatus,
    InstitutionalRole,
    OperatingMode,
    RegisteredService,
)
from app.services.audit_service import AuditError, AuditService
from app.services.auth_service import AuthenticatedPrincipal, AuthError

# Allowed incident-status transitions. CLOSED is terminal: reopening requires
# opening a fresh incident (system incidents dedupe via correlation_key,
# which is only enforced while an incident is open/investigating/mitigated).
INCIDENT_TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    IncidentStatus.OPEN: frozenset(
        {IncidentStatus.INVESTIGATING, IncidentStatus.MITIGATED, IncidentStatus.CLOSED}
    ),
    IncidentStatus.INVESTIGATING: frozenset(
        {IncidentStatus.MITIGATED, IncidentStatus.CLOSED, IncidentStatus.OPEN}
    ),
    IncidentStatus.MITIGATED: frozenset({IncidentStatus.CLOSED, IncidentStatus.INVESTIGATING}),
    IncidentStatus.CLOSED: frozenset(),
}

_EVENT_TYPE_BY_STATUS: dict[IncidentStatus, IncidentLifecycleEventType] = {
    IncidentStatus.OPEN: IncidentLifecycleEventType.OPENED,
    IncidentStatus.INVESTIGATING: IncidentLifecycleEventType.INVESTIGATING,
    IncidentStatus.MITIGATED: IncidentLifecycleEventType.MITIGATED,
    IncidentStatus.CLOSED: IncidentLifecycleEventType.CLOSED,
}


class IncidentError(RuntimeError):
    """Domain error for incident lifecycle operations."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def can_transition_incident(current: IncidentStatus, target: IncidentStatus) -> bool:
    if current == target:
        return False
    return target in INCIDENT_TRANSITIONS.get(current, frozenset())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class IncidentService:
    def __init__(self, session: Session) -> None:
        self._db = session
        self._audit = AuditService(session)

    def _require_human_mutation(
        self, actor: AuthenticatedPrincipal | None, *, action: str, request_id: str | None
    ) -> None:
        """System (actor=None) callers bypass RBAC; human callers require
        Founder or Operator."""
        if actor is None:
            return
        allowed = {InstitutionalRole.FOUNDER, InstitutionalRole.OPERATOR}
        if actor.roles.isdisjoint(allowed):
            try:
                self._audit.append(
                    action="authz.denied",
                    resource_type="incident",
                    actor_user_id=actor.user.id,
                    request_id=request_id,
                    payload={"action": action, "roles": [r.value for r in actor.roles]},
                )
                self._db.commit()
            except AuditError:
                self._db.rollback()
            raise AuthError("Forbidden")

    def get(self, incident_id: uuid.UUID) -> Incident | None:
        return self._db.get(Incident, incident_id)

    def list_incidents(
        self,
        *,
        status: IncidentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        safe_limit = min(max(limit, 1), 200)
        safe_offset = max(offset, 0)
        stmt = select(Incident).order_by(Incident.opened_at.desc())
        if status is not None:
            stmt = stmt.where(Incident.status == status)
        return list(self._db.scalars(stmt.offset(safe_offset).limit(safe_limit)))

    def list_lifecycle_events(self, incident_id: uuid.UUID) -> list[IncidentLifecycleEvent]:
        return list(
            self._db.scalars(
                select(IncidentLifecycleEvent)
                .where(IncidentLifecycleEvent.incident_id == incident_id)
                .order_by(IncidentLifecycleEvent.occurred_at.asc())
            )
        )

    def find_open_by_correlation_key(self, correlation_key: str) -> Incident | None:
        return self._db.scalars(
            select(Incident)
            .where(
                Incident.correlation_key == correlation_key,
                Incident.status.in_(
                    [IncidentStatus.OPEN, IncidentStatus.INVESTIGATING, IncidentStatus.MITIGATED]
                ),
            )
            .with_for_update()
        ).first()

    def open_incident(
        self,
        *,
        title: str,
        description: str | None,
        severity: IncidentSeverity,
        actor: AuthenticatedPrincipal | None = None,
        correlation_key: str | None = None,
        source_service: RegisteredService | None = None,
        related_mode: OperatingMode | None = None,
        request_id: str | None = None,
        commit: bool = True,
    ) -> tuple[Incident, bool]:
        """Open an incident. Returns (incident, created).

        When `correlation_key` is provided, opening is idempotent: an
        existing open/investigating/mitigated incident with the same key is
        returned instead of creating a duplicate (created=False). System
        (health-supervisor) callers should always pass a correlation_key;
        human-created incidents typically omit it.
        """
        self._require_human_mutation(actor, action="incident.open", request_id=request_id)

        if correlation_key is not None:
            existing = self.find_open_by_correlation_key(correlation_key)
            if existing is not None:
                return existing, False

        incident = Incident(
            title=title.strip(),
            description=description,
            severity=severity,
            status=IncidentStatus.OPEN,
            related_mode=related_mode,
            source_service_id=source_service.id if source_service is not None else None,
            correlation_key=correlation_key,
            opened_by_system=actor is None,
            created_by_user_id=actor.user.id if actor is not None else None,
        )
        self._db.add(incident)
        try:
            self._db.flush()
        except IntegrityError:
            self._db.rollback()
            if correlation_key is not None:
                recovered = self.find_open_by_correlation_key(correlation_key)
                if recovered is not None:
                    return recovered, False
            raise IncidentError(
                "incident_conflict", "Concurrent incident creation conflicted"
            ) from None

        event = IncidentLifecycleEvent(
            incident_id=incident.id,
            event_type=IncidentLifecycleEventType.OPENED,
            from_status=None,
            to_status=IncidentStatus.OPEN,
            from_severity=None,
            to_severity=severity,
            actor_user_id=actor.user.id if actor is not None else None,
            opened_by_system=actor is None,
            note="opened by system" if actor is None else "opened",
            payload={"correlation_key": correlation_key} if correlation_key else {},
        )
        self._db.add(event)
        try:
            self._db.flush()
            self._audit.append(
                action="incident.opened",
                resource_type="incident",
                resource_id=str(incident.id),
                actor_user_id=actor.user.id if actor is not None else None,
                request_id=request_id,
                payload={
                    "actor": "SYSTEM" if actor is None else None,
                    "correlation_key": correlation_key,
                    "severity": severity.value,
                    "opened_by_system": actor is None,
                },
            )
            if commit:
                self._db.commit()
            else:
                self._db.flush()
        except AuditError:
            self._db.rollback()
            raise IncidentError(
                "audit_unavailable",
                "Audit persistence failed; incident open aborted (fail-closed)",
            ) from None
        return incident, True

    def open_system_incident(
        self,
        *,
        title: str,
        description: str | None,
        severity: IncidentSeverity,
        correlation_key: str,
        source_service_id: uuid.UUID | None = None,
        related_mode: OperatingMode | None = None,
        request_id: str | None = None,
        commit: bool = True,
    ) -> Incident:
        source: RegisteredService | None = None
        if source_service_id is not None:
            source = self._db.get(RegisteredService, source_service_id)
        incident, _created = self.open_incident(
            title=title,
            description=description,
            severity=severity,
            actor=None,
            correlation_key=correlation_key,
            source_service=source,
            related_mode=related_mode,
            request_id=request_id,
            commit=commit,
        )
        return incident

    def transition(
        self,
        *,
        incident_id: uuid.UUID,
        target_status: IncidentStatus,
        actor: AuthenticatedPrincipal | None = None,
        note: str | None = None,
        request_id: str | None = None,
    ) -> Incident:
        self._require_human_mutation(
            actor, action=f"incident.transition.{target_status.value}", request_id=request_id
        )

        incident = self._db.scalars(
            select(Incident).where(Incident.id == incident_id).with_for_update()
        ).first()
        if incident is None:
            raise IncidentError("incident_not_found", "Incident not found")

        if not can_transition_incident(incident.status, target_status):
            raise IncidentError(
                "invalid_transition",
                f"invalid incident transition {incident.status.value} -> {target_status.value}",
            )

        previous_status = incident.status
        now = _utcnow()
        incident.status = target_status
        if target_status == IncidentStatus.CLOSED:
            incident.closed_at = now
        self._db.add(incident)

        event = IncidentLifecycleEvent(
            incident_id=incident.id,
            event_type=_EVENT_TYPE_BY_STATUS.get(target_status, IncidentLifecycleEventType.NOTE),
            from_status=previous_status,
            to_status=target_status,
            actor_user_id=actor.user.id if actor is not None else None,
            opened_by_system=actor is None,
            note=note,
            payload={"request_id": request_id} if request_id else {},
        )
        self._db.add(event)
        try:
            self._db.flush()
            self._audit.append(
                action=f"incident.{target_status.value}",
                resource_type="incident",
                resource_id=str(incident.id),
                actor_user_id=actor.user.id if actor is not None else None,
                request_id=request_id,
                payload={
                    "previous_status": previous_status.value,
                    "new_status": target_status.value,
                    "opened_by_system": actor is None,
                },
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise IncidentError(
                "audit_unavailable",
                "Audit persistence failed; incident transition aborted (fail-closed)",
            ) from None
        return incident

    def change_severity(
        self,
        *,
        incident_id: uuid.UUID,
        new_severity: IncidentSeverity,
        actor: AuthenticatedPrincipal | None = None,
        note: str | None = None,
        request_id: str | None = None,
    ) -> Incident:
        self._require_human_mutation(
            actor, action="incident.severity_changed", request_id=request_id
        )
        incident = self._db.scalars(
            select(Incident).where(Incident.id == incident_id).with_for_update()
        ).first()
        if incident is None:
            raise IncidentError("incident_not_found", "Incident not found")
        if incident.status == IncidentStatus.CLOSED:
            raise IncidentError("invalid_transition", "Cannot change severity of a closed incident")

        previous_severity = incident.severity
        incident.severity = new_severity
        self._db.add(incident)

        event = IncidentLifecycleEvent(
            incident_id=incident.id,
            event_type=IncidentLifecycleEventType.SEVERITY_CHANGED,
            from_status=incident.status,
            to_status=incident.status,
            from_severity=previous_severity,
            to_severity=new_severity,
            actor_user_id=actor.user.id if actor is not None else None,
            opened_by_system=actor is None,
            note=note,
            payload={},
        )
        self._db.add(event)
        try:
            self._db.flush()
            self._audit.append(
                action="incident.severity_changed",
                resource_type="incident",
                resource_id=str(incident.id),
                actor_user_id=actor.user.id if actor is not None else None,
                request_id=request_id,
                payload={
                    "previous_severity": previous_severity.value,
                    "new_severity": new_severity.value,
                },
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise IncidentError(
                "audit_unavailable",
                "Audit persistence failed; severity change aborted (fail-closed)",
            ) from None
        return incident

    def add_note(
        self,
        *,
        incident_id: uuid.UUID,
        note: str,
        actor: AuthenticatedPrincipal | None = None,
        request_id: str | None = None,
    ) -> IncidentLifecycleEvent:
        self._require_human_mutation(actor, action="incident.note", request_id=request_id)
        incident = self._db.scalars(
            select(Incident).where(Incident.id == incident_id).with_for_update()
        ).first()
        if incident is None:
            raise IncidentError("incident_not_found", "Incident not found")
        event = IncidentLifecycleEvent(
            incident_id=incident.id,
            event_type=IncidentLifecycleEventType.NOTE,
            from_status=incident.status,
            to_status=incident.status,
            actor_user_id=actor.user.id if actor is not None else None,
            opened_by_system=actor is None,
            note=note,
            payload={},
        )
        self._db.add(event)
        try:
            self._db.flush()
            self._audit.append(
                action="incident.note_added",
                resource_type="incident",
                resource_id=str(incident.id),
                actor_user_id=actor.user.id if actor is not None else None,
                request_id=request_id,
                payload={"note_present": bool(note)},
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise IncidentError(
                "audit_unavailable", "Audit persistence failed; note aborted (fail-closed)"
            ) from None
        return event
