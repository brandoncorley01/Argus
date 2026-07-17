from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar, cast

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, OperatingMode

T = TypeVar("T")

# Keys that must never be persisted in audit payloads.
_REDACT_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "private_key",
        "access_key",
        "credential",
        "credentials",
        "session_token",
        "csrf_token",
        "cookie",
        "cookies",
    }
)


class AuditError(RuntimeError):
    """Raised when an audit write fails and the operation must fail closed."""


def redact_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a copy of payload with sensitive keys redacted."""
    if payload is None:
        return None

    def _walk(value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for key, item in value.items():
                if str(key).lower() in _REDACT_KEYS:
                    cleaned[key] = "[REDACTED]"
                else:
                    cleaned[key] = _walk(item)
            return cleaned
        if isinstance(value, list):
            return [_walk(item) for item in value]
        return value

    return cast(dict[str, Any], _walk(payload))


class AuditService:
    """Append-oriented audit recorder. Critical paths must fail closed on write failure."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        actor_user_id: uuid.UUID | None = None,
        request_id: str | None = None,
        mode_at_time: OperatingMode | None = None,
        config_version_id: uuid.UUID | None = None,
        policy_version_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditEvent:
        if not action or not action.strip():
            raise AuditError("audit action must not be blank")
        if not resource_type or not resource_type.strip():
            raise AuditError("audit resource_type must not be blank")

        event = AuditEvent(
            action=action.strip(),
            resource_type=resource_type.strip(),
            resource_id=resource_id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            mode_at_time=mode_at_time,
            config_version_id=config_version_id,
            policy_version_id=policy_version_id,
            payload=redact_payload(payload),
        )
        if occurred_at is not None:
            event.occurred_at = occurred_at

        try:
            self._session.add(event)
            self._session.flush()
        except Exception as exc:  # noqa: BLE001 — convert to fail-closed institutional error
            self._session.rollback()
            raise AuditError("audit recording failed; operation aborted (fail-closed)") from exc

        return event

    def get(self, event_id: uuid.UUID) -> AuditEvent | None:
        return self._session.get(AuditEvent, event_id)

    def list_events(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        action: str | None = None,
        resource_type: str | None = None,
    ) -> list[AuditEvent]:
        safe_limit = min(max(limit, 1), 200)
        safe_offset = max(offset, 0)
        stmt: Select[tuple[AuditEvent]] = select(AuditEvent).order_by(
            AuditEvent.occurred_at.desc()
        )
        if action:
            stmt = stmt.where(AuditEvent.action == action)
        if resource_type:
            stmt = stmt.where(AuditEvent.resource_type == resource_type)
        stmt = stmt.offset(safe_offset).limit(safe_limit)
        return list(self._session.scalars(stmt))

    def run_critical(
        self,
        *,
        action: str,
        resource_type: str,
        mutation: Callable[[Session], T],
        resource_id: str | None = None,
        actor_user_id: uuid.UUID | None = None,
        request_id: str | None = None,
        mode_at_time: OperatingMode | None = None,
        config_version_id: uuid.UUID | None = None,
        policy_version_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> tuple[T, AuditEvent]:
        """
        Execute a critical mutation and persist an audit event in one transaction.

        If audit recording fails, the session is rolled back and AuditError is raised.
        """
        try:
            result = mutation(self._session)
            event = self.append(
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                actor_user_id=actor_user_id,
                request_id=request_id,
                mode_at_time=mode_at_time,
                config_version_id=config_version_id,
                policy_version_id=policy_version_id,
                payload=payload,
            )
            self._session.commit()
            return result, event
        except AuditError:
            self._session.rollback()
            raise
        except Exception:
            self._session.rollback()
            raise
