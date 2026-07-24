"""Per-service and institutional health evaluation (Phase 8).

Heartbeat ingestion (`heartbeat_service`) records the latest observed status
per service. This module is the sole owner of:

- Heartbeat-timeout detection (no heartbeat within `heartbeat_timeout_seconds`
  degrades the projection to UNHEALTHY even without a new heartbeat).
- `consecutive_failures` bookkeeping (increment for critical services
  evaluated degraded/unhealthy; reset to 0 on healthy).
- Institutional aggregation across all enabled registered services, and the
  singleton `institutional_health_state` row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    HealthStatus,
    InstitutionalHealthState,
    RegisteredService,
    ServiceCriticality,
    ServiceHealthProjection,
)
from app.services.audit_service import AuditError, AuditService


class HealthEvaluationError(RuntimeError):
    """Domain error for health evaluation / institutional aggregation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ServiceEvaluation:
    service: RegisteredService
    status: HealthStatus
    is_timed_out: bool
    detail: str
    consecutive_failures: int = 0


class HealthEvaluationService:
    SINGLETON_KEY = "current"

    def __init__(self, session: Session) -> None:
        self._db = session
        self._audit = AuditService(session)

    def evaluate_service(
        self,
        *,
        service: RegisteredService,
        projection: ServiceHealthProjection | None,
        now: datetime | None = None,
    ) -> ServiceEvaluation:
        """Pure (no persistence) evaluation of a service's current health.

        Applies heartbeat-timeout detection: if no heartbeat has ever been
        observed, or the last observed heartbeat is older than the service's
        `heartbeat_timeout_seconds`, the service is considered UNHEALTHY
        regardless of the last recorded projection status.
        """
        moment = now or _utcnow()
        if projection is None or projection.last_observed_at is None:
            return ServiceEvaluation(
                service=service,
                status=HealthStatus.UNHEALTHY,
                is_timed_out=True,
                detail="no heartbeat received",
                consecutive_failures=projection.consecutive_failures if projection else 0,
            )
        elapsed = (moment - projection.last_observed_at).total_seconds()
        if elapsed > service.heartbeat_timeout_seconds:
            return ServiceEvaluation(
                service=service,
                status=HealthStatus.UNHEALTHY,
                is_timed_out=True,
                detail=(
                    f"no heartbeat within {service.heartbeat_timeout_seconds}s "
                    f"(elapsed {int(elapsed)}s)"
                ),
                consecutive_failures=projection.consecutive_failures,
            )
        return ServiceEvaluation(
            service=service,
            status=projection.status,
            is_timed_out=False,
            detail=projection.detail or "",
            consecutive_failures=projection.consecutive_failures,
        )

    def evaluate_and_persist(
        self,
        *,
        service: RegisteredService,
        now: datetime | None = None,
        request_id: str | None = None,
    ) -> ServiceEvaluation:
        """Lock the service's projection, evaluate, persist, and commit.

        This is the authoritative path used by the health supervisor cycle.
        It is the sole writer of `consecutive_failures`: incremented for
        CRITICAL services evaluated degraded/unhealthy, reset to 0 on
        healthy. Timeout-driven status changes are written back to the
        projection; heartbeat-driven status is left as-is (heartbeat_service
        already wrote it).
        """
        moment = now or _utcnow()
        projection = self._db.scalars(
            select(ServiceHealthProjection)
            .where(ServiceHealthProjection.service_id == service.id)
            .with_for_update()
        ).first()

        if projection is None:
            projection = ServiceHealthProjection(
                service_id=service.id,
                status=HealthStatus.UNHEALTHY,
                consecutive_failures=0,
                evaluation_version=0,
                detail="no heartbeat received",
                updated_at=moment,
            )
            self._db.add(projection)
            self._db.flush()

        evaluation = self.evaluate_service(service=service, projection=projection, now=moment)
        previous_status = projection.status

        if evaluation.is_timed_out:
            projection.status = evaluation.status
            projection.detail = evaluation.detail

        if evaluation.status == HealthStatus.HEALTHY:
            projection.consecutive_failures = 0
        elif service.criticality == ServiceCriticality.CRITICAL:
            projection.consecutive_failures = (projection.consecutive_failures or 0) + 1

        projection.evaluation_version = (projection.evaluation_version or 0) + 1
        self._db.add(projection)

        try:
            self._db.flush()
            if evaluation.is_timed_out and previous_status != evaluation.status:
                self._audit.append(
                    action="health.status_changed",
                    resource_type="registered_service",
                    resource_id=str(service.id),
                    request_id=request_id,
                    payload={
                        "service_key": service.service_key,
                        "previous_status": previous_status.value,
                        "new_status": evaluation.status.value,
                        "reason": "heartbeat_timeout",
                    },
                )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise HealthEvaluationError(
                "audit_unavailable",
                "Audit persistence failed; health evaluation aborted (fail-closed)",
            ) from None

        return ServiceEvaluation(
            service=service,
            status=evaluation.status,
            is_timed_out=evaluation.is_timed_out,
            detail=evaluation.detail,
            consecutive_failures=projection.consecutive_failures,
        )

    def aggregate_institutional(
        self, evaluations: list[ServiceEvaluation]
    ) -> tuple[HealthStatus, dict[str, Any]]:
        """Healthy if all healthy; degraded if any degraded/unhealthy but no
        critical-unhealthy service; unhealthy if any critical service is
        unhealthy."""
        unhealthy_critical = [
            e
            for e in evaluations
            if e.status == HealthStatus.UNHEALTHY
            and e.service.criticality == ServiceCriticality.CRITICAL
        ]
        any_unhealthy = [e for e in evaluations if e.status == HealthStatus.UNHEALTHY]
        any_degraded = [e for e in evaluations if e.status == HealthStatus.DEGRADED]

        if unhealthy_critical:
            status = HealthStatus.UNHEALTHY
        elif any_degraded or any_unhealthy:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        summary: dict[str, Any] = {
            "services": [
                {
                    "service_key": e.service.service_key,
                    "criticality": e.service.criticality.value,
                    "status": e.status.value,
                    "detail": e.detail,
                    "consecutive_failures": e.consecutive_failures,
                }
                for e in evaluations
            ],
            "unhealthy_critical_count": len(unhealthy_critical),
            "unhealthy_count": len(any_unhealthy),
            "degraded_count": len(any_degraded),
        }
        return status, summary

    def get_institutional_state(self) -> InstitutionalHealthState | None:
        return self._db.scalars(
            select(InstitutionalHealthState).where(
                InstitutionalHealthState.singleton_key == self.SINGLETON_KEY
            )
        ).first()

    def _lock_institutional_state(self) -> InstitutionalHealthState | None:
        return self._db.scalars(
            select(InstitutionalHealthState)
            .where(InstitutionalHealthState.singleton_key == self.SINGLETON_KEY)
            .with_for_update()
        ).first()

    def update_institutional_state(
        self,
        *,
        status: HealthStatus,
        summary: dict[str, Any],
        request_id: str | None = None,
    ) -> InstitutionalHealthState:
        state = self._lock_institutional_state()
        if state is None:
            raise HealthEvaluationError(
                "institutional_health_state_missing",
                "Authoritative institutional_health_state row is missing",
            )
        previous_status = state.status
        now = _utcnow()
        state.status = status
        state.evaluation_version = (state.evaluation_version or 0) + 1
        state.summary = summary
        state.evaluated_at = now
        self._db.add(state)

        try:
            if previous_status != status:
                self._audit.append(
                    action="health.institutional_status_changed",
                    resource_type="institutional_health_state",
                    resource_id=self.SINGLETON_KEY,
                    request_id=request_id,
                    payload={
                        "previous_status": previous_status.value,
                        "new_status": status.value,
                    },
                )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise HealthEvaluationError(
                "audit_unavailable",
                "Audit persistence failed; institutional health update aborted (fail-closed)",
            ) from None
        return state
