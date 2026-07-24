"""Operational event logging (Phase 15) — append-only, secrets-free.

`OperationalEvent` rows are the raw feed behind the Founder-facing System
Health dashboard's "recent events" panel and the health-supervisor worker's
own cycle-failure log. Every write is scanned with the same secrets denylist
used for configuration/policy payloads (`payload_integrity.assert_no_secrets`)
before it is persisted — this log must never carry credential material.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.operations import OperationalComponent, OperationalEvent, OperationalSeverity
from app.services.payload_integrity import PayloadValidationError, assert_no_secrets


class OperationalLogError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OperationalLogService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def append(
        self,
        *,
        component: OperationalComponent | str,
        severity: OperationalSeverity | str,
        description: str,
        correlation_id: str,
        details: dict[str, Any] | None = None,
        actor_user_id: uuid.UUID | None = None,
        occurred_at: datetime | None = None,
        commit: bool = True,
    ) -> OperationalEvent:
        try:
            component_value = OperationalComponent(component).value
        except ValueError as exc:
            raise OperationalLogError(
                "invalid_component", f"Unknown operational component: {component}"
            ) from exc
        try:
            severity_value = OperationalSeverity(severity).value
        except ValueError as exc:
            raise OperationalLogError(
                "invalid_severity", f"Unknown operational severity: {severity}"
            ) from exc
        if not description or not description.strip():
            raise OperationalLogError("invalid_description", "description must not be blank")
        if not correlation_id or not correlation_id.strip():
            raise OperationalLogError("invalid_correlation_id", "correlation_id must not be blank")

        payload = details or {}
        try:
            assert_no_secrets(payload)
        except PayloadValidationError as exc:
            raise OperationalLogError("secret_detected", str(exc)) from None

        event = OperationalEvent(
            occurred_at=occurred_at or _utcnow(),
            component=component_value,
            severity=severity_value,
            description=description.strip(),
            correlation_id=correlation_id.strip(),
            details=payload,
            actor_user_id=actor_user_id,
        )
        self.db.add(event)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(event)
        return event

    def get(self, event_id: uuid.UUID) -> OperationalEvent | None:
        return self.db.get(OperationalEvent, event_id)

    def list_events(
        self,
        *,
        severity: OperationalSeverity | None = None,
        component: OperationalComponent | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OperationalEvent]:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)
        stmt = select(OperationalEvent).order_by(OperationalEvent.occurred_at.desc())
        if severity is not None:
            stmt = stmt.where(OperationalEvent.severity == OperationalSeverity(severity).value)
        if component is not None:
            stmt = stmt.where(OperationalEvent.component == OperationalComponent(component).value)
        return list(self.db.scalars(stmt.offset(safe_offset).limit(safe_limit)))
