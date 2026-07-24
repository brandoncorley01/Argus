"""Append-only health heartbeat ingestion (Phase 8).

Heartbeats are append-only evidence (enforced by a DB trigger). Ingestion is
ordered (monotonic per-service `sequence_number`) and idempotent (unique
`(service_id, idempotency_key_hash)` with a fingerprint check on replay).
Accepting a heartbeat also updates the current `service_health_projections`
row for the service under a row lock; consecutive-failure bookkeeping is
owned by `health_evaluation_service`, not here.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    HealthHeartbeat,
    HealthHeartbeatIdempotency,
    HealthStatus,
    ServiceHealthProjection,
)
from app.services.audit_service import AuditError, AuditService
from app.services.service_registry_service import ServiceRegistryError, ServiceRegistryService


class HealthError(RuntimeError):
    """Domain error for heartbeat ingestion / health operations."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(UTC)


def hash_idempotency_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def heartbeat_fingerprint(
    *,
    service_key: str,
    status: str,
    sequence_number: int,
    observed_at: datetime,
    detail: str | None,
    payload: dict[str, Any] | None,
) -> str:
    encoded = json.dumps(
        {
            "service_key": service_key,
            "status": status,
            "sequence_number": sequence_number,
            "observed_at": observed_at.isoformat(),
            "detail": detail or "",
            "payload": payload or {},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class HeartbeatService:
    def __init__(self, session: Session) -> None:
        self._db = session
        self._audit = AuditService(session)
        self._registry = ServiceRegistryService(session)

    def _map_integrity_error(self, exc: IntegrityError) -> HealthError:
        orig = getattr(exc, "orig", None)
        diag = getattr(orig, "diag", None)
        constraint = getattr(diag, "constraint_name", None) if diag is not None else None
        message = str(orig or exc).lower()
        if constraint == "uq_health_heartbeats_service_sequence" or (
            "uq_health_heartbeats_service_sequence" in message
        ):
            return HealthError(
                "sequence_out_of_order",
                "sequence_number already recorded for this service",
            )
        if constraint == "uq_health_heartbeat_idempotency_service_key" or (
            "uq_health_heartbeat_idempotency_service_key" in message
        ):
            return HealthError(
                "idempotency_conflict",
                "Idempotency key conflicted with a concurrent commit",
            )
        return HealthError(
            "health_state_conflict",
            "Database integrity constraint rejected the heartbeat",
        )

    def _lookup_idempotency(
        self, *, service_id: uuid.UUID, key_hash: str, fingerprint: str
    ) -> dict[str, Any] | None:
        row = self._db.scalars(
            select(HealthHeartbeatIdempotency).where(
                HealthHeartbeatIdempotency.service_id == service_id,
                HealthHeartbeatIdempotency.idempotency_key_hash == key_hash,
            )
        ).first()
        if row is None:
            return None
        if row.request_fingerprint != fingerprint:
            raise HealthError(
                "idempotency_conflict",
                "Idempotency key reused with a different heartbeat payload",
            )
        if row.response_payload is not None:
            return dict(row.response_payload)
        raise HealthError(
            "idempotency_conflict",
            "Idempotency record exists without a committed response payload",
        )

    def record_heartbeat(
        self,
        *,
        service_key: str,
        status: HealthStatus,
        observed_at: datetime,
        idempotency_key: str,
        sequence_number: int,
        detail: str | None = None,
        payload: dict[str, Any] | None = None,
        worker_instance_id: uuid.UUID | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if not idempotency_key or not idempotency_key.strip():
            raise HealthError("invalid_heartbeat", "idempotency_key is required")
        if sequence_number < 0:
            raise HealthError("invalid_heartbeat", "sequence_number must be non-negative")

        try:
            service = self._registry.lock_by_key(service_key)
        except ServiceRegistryError as exc:
            raise HealthError(exc.code, exc.message) from exc
        if not service.is_enabled:
            raise HealthError(
                "service_disabled", f"registered service '{service_key}' is disabled"
            )

        key_hash = hash_idempotency_key(idempotency_key.strip())
        fingerprint = heartbeat_fingerprint(
            service_key=service_key,
            status=status.value,
            sequence_number=sequence_number,
            observed_at=observed_at,
            detail=detail,
            payload=payload,
        )

        replay = self._lookup_idempotency(
            service_id=service.id, key_hash=key_hash, fingerprint=fingerprint
        )
        if replay is not None:
            return {**replay, "idempotent_replay": True}

        projection = self._db.scalars(
            select(ServiceHealthProjection)
            .where(ServiceHealthProjection.service_id == service.id)
            .with_for_update()
        ).first()

        last_sequence = projection.last_sequence_number if projection is not None else None
        if last_sequence is not None and sequence_number <= last_sequence:
            raise HealthError(
                "sequence_out_of_order",
                f"sequence_number {sequence_number} <= last accepted {last_sequence}",
            )

        heartbeat = HealthHeartbeat(
            service_id=service.id,
            worker_instance_id=worker_instance_id,
            sequence_number=sequence_number,
            status=status,
            detail=detail,
            payload=payload or {},
            observed_at=observed_at,
        )
        self._db.add(heartbeat)
        try:
            self._db.flush()
        except IntegrityError as exc:
            self._db.rollback()
            raise self._map_integrity_error(exc) from None

        previous_status = projection.status if projection is not None else None
        now = _utcnow()
        if projection is None:
            projection = ServiceHealthProjection(
                service_id=service.id,
                status=status,
                last_heartbeat_id=heartbeat.id,
                last_sequence_number=sequence_number,
                last_observed_at=observed_at,
                consecutive_failures=0,
                evaluation_version=1,
                detail=detail,
                updated_at=now,
            )
            self._db.add(projection)
        else:
            projection.status = status
            projection.last_heartbeat_id = heartbeat.id
            projection.last_sequence_number = sequence_number
            projection.last_observed_at = observed_at
            projection.detail = detail
            projection.evaluation_version = (projection.evaluation_version or 0) + 1
            self._db.add(projection)
        self._db.flush()

        result = {
            "heartbeat_id": str(heartbeat.id),
            "service_id": str(service.id),
            "service_key": service.service_key,
            "status": status.value,
            "sequence_number": sequence_number,
            "observed_at": observed_at.isoformat(),
        }

        idem = HealthHeartbeatIdempotency(
            service_id=service.id,
            idempotency_key_hash=key_hash,
            request_fingerprint=fingerprint,
            heartbeat_id=heartbeat.id,
            response_payload=result,
        )
        self._db.add(idem)

        events: list[dict[str, Any]] = [
            {
                "action": "health.heartbeat_accepted",
                "resource_type": "registered_service",
                "resource_id": str(service.id),
                "request_id": request_id,
                "payload": {
                    "service_key": service.service_key,
                    "status": status.value,
                    "sequence_number": sequence_number,
                    "worker_instance_id": str(worker_instance_id) if worker_instance_id else None,
                },
            }
        ]
        if previous_status != status:
            events.append(
                {
                    "action": "health.status_changed",
                    "resource_type": "registered_service",
                    "resource_id": str(service.id),
                    "request_id": request_id,
                    "payload": {
                        "service_key": service.service_key,
                        "previous_status": previous_status.value if previous_status else None,
                        "new_status": status.value,
                        "reason": "heartbeat",
                    },
                }
            )

        try:
            for event in events:
                self._audit.append(**event)
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise HealthError(
                "audit_unavailable",
                "Audit persistence failed; heartbeat aborted (fail-closed)",
            ) from None
        except IntegrityError as exc:
            self._db.rollback()
            mapped = self._map_integrity_error(exc)
            if mapped.code == "idempotency_conflict":
                replay = self._lookup_idempotency(
                    service_id=service.id, key_hash=key_hash, fingerprint=fingerprint
                )
                if replay is not None:
                    return {**replay, "idempotent_replay": True}
            raise mapped from None

        return {**result, "idempotent_replay": False}
