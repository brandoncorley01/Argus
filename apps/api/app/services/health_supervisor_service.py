"""Institutional health supervisor orchestration (Phase 8).

Coordinates a single durable lease holder that probes core infrastructure
(Postgres, Redis), records heartbeats, evaluates per-service and
institutional health, manages system-opened incidents, and recommends (and,
when eligible, applies) protective operating-mode degradation into
SAFE_MODE when a critical service is persistently unhealthy.

This service also owns the worker identity/instance directory used to
coordinate multiple ARQ worker processes against the singleton
`health_supervisor_leases` row (lease-based leader election).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import redis
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.models import (
    HealthStatus,
    HealthSupervisorLease,
    IncidentSeverity,
    IncidentStatus,
    ProtectiveActionType,
    ServiceCriticality,
    ServiceHealthProjection,
    WorkerIdentity,
    WorkerInstance,
    WorkerInstanceStatus,
)
from app.services.audit_service import AuditError, AuditService
from app.services.health_evaluation_service import (
    HealthEvaluationError,
    HealthEvaluationService,
    ServiceEvaluation,
)
from app.services.heartbeat_service import HealthError, HeartbeatService
from app.services.incident_service import IncidentService
from app.services.mode_transitions import DEGRADE_ELIGIBLE_MODES
from app.services.operating_mode_service import OperatingModeError, OperatingModeService
from app.services.protective_action_service import ProtectiveActionService
from app.services.service_registry_service import ServiceRegistryService


class HealthSupervisorError(RuntimeError):
    """Domain error for health supervisor cycle orchestration."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(UTC)


class HealthSupervisorService:
    SINGLETON_KEY = "current"
    DEGRADE_FAILURE_THRESHOLD = 3
    LEASE_SECONDS = 45
    DEGRADE_ELIGIBLE_MODES = DEGRADE_ELIGIBLE_MODES

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._db = session
        self._settings = settings or get_settings()
        self._audit = AuditService(session)
        self._registry = ServiceRegistryService(session)
        self._heartbeats = HeartbeatService(session)
        self._evaluation = HealthEvaluationService(session)
        self._incidents = IncidentService(session)
        self._protective_actions = ProtectiveActionService(session)
        self._operating_mode = OperatingModeService(session)

        self.lease_seconds = self._settings.health_supervisor_lease_seconds
        self.degrade_failure_threshold = self._settings.health_supervisor_failure_threshold

    # --- Worker identity / instance directory ---

    def get_worker_identity(self, worker_key: str) -> WorkerIdentity | None:
        return self._db.scalars(
            select(WorkerIdentity).where(WorkerIdentity.worker_key == worker_key)
        ).first()

    def list_worker_identities(self) -> list[WorkerIdentity]:
        return list(
            self._db.scalars(select(WorkerIdentity).order_by(WorkerIdentity.worker_key.asc()))
        )

    def list_worker_instances(
        self, *, worker_identity_id: uuid.UUID | None = None
    ) -> list[WorkerInstance]:
        stmt = select(WorkerInstance).order_by(WorkerInstance.last_seen_at.desc())
        if worker_identity_id is not None:
            stmt = stmt.where(WorkerInstance.worker_identity_id == worker_identity_id)
        return list(self._db.scalars(stmt))

    def get_lease(self) -> HealthSupervisorLease | None:
        return self._db.scalars(
            select(HealthSupervisorLease).where(
                HealthSupervisorLease.singleton_key == self.SINGLETON_KEY
            )
        ).first()

    def register_instance(
        self,
        *,
        worker_key: str,
        instance_key: str,
        hostname: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkerInstance:
        identity = self.get_worker_identity(worker_key)
        if identity is None or not identity.is_enabled:
            raise HealthSupervisorError(
                "worker_identity_not_found",
                f"worker identity '{worker_key}' not found or disabled",
            )
        now = _utcnow()
        existing = self._db.scalars(
            select(WorkerInstance)
            .where(
                WorkerInstance.worker_identity_id == identity.id,
                WorkerInstance.instance_key == instance_key,
            )
            .with_for_update()
        ).first()
        if existing is not None:
            existing.status = WorkerInstanceStatus.RUNNING
            existing.hostname = hostname
            existing.last_seen_at = now
            existing.stopped_at = None
            existing.metadata_ = metadata or {}
            self._db.add(existing)
            instance = existing
        else:
            instance = WorkerInstance(
                worker_identity_id=identity.id,
                instance_key=instance_key,
                hostname=hostname,
                status=WorkerInstanceStatus.STARTING,
                started_at=now,
                last_seen_at=now,
                metadata_=metadata or {},
            )
            self._db.add(instance)
        try:
            self._db.flush()
            self._audit.append(
                action="health.worker_instance_registered",
                resource_type="worker_instance",
                resource_id=str(instance.id),
                payload={"worker_key": worker_key, "instance_key": instance_key},
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise HealthSupervisorError(
                "audit_unavailable",
                "Audit persistence failed; worker instance registration aborted (fail-closed)",
            ) from None
        return instance

    def touch_instance(
        self, instance_id: uuid.UUID, *, status: WorkerInstanceStatus = WorkerInstanceStatus.RUNNING
    ) -> None:
        instance = self._db.get(WorkerInstance, instance_id)
        if instance is None:
            return
        instance.last_seen_at = _utcnow()
        instance.status = status
        self._db.add(instance)
        self._db.commit()

    def mark_instance_stopped(self, instance_id: uuid.UUID) -> None:
        instance = self._db.get(WorkerInstance, instance_id)
        if instance is None:
            return
        instance.status = WorkerInstanceStatus.STOPPED
        instance.stopped_at = _utcnow()
        self._db.add(instance)
        self._db.commit()

    # --- Lease coordination ---

    def _lock_lease_row(self) -> HealthSupervisorLease | None:
        return self._db.scalars(
            select(HealthSupervisorLease)
            .where(HealthSupervisorLease.singleton_key == self.SINGLETON_KEY)
            .with_for_update()
        ).first()

    def acquire_or_renew_lease(
        self, worker_instance_id: uuid.UUID, *, request_id: str | None = None
    ) -> dict[str, Any]:
        lease = self._lock_lease_row()
        if lease is None:
            raise HealthSupervisorError(
                "lease_missing", "Authoritative health_supervisor_leases row is missing"
            )
        now = _utcnow()
        expired = lease.lease_until is None or lease.lease_until <= now
        held_by_self = lease.holder_instance_id == worker_instance_id
        if not expired and not held_by_self:
            return {
                "acquired": False,
                "reason": "lease_held_by_other_instance",
                "holder_instance_id": (
                    str(lease.holder_instance_id) if lease.holder_instance_id else None
                ),
                "lease_until": lease.lease_until.isoformat() if lease.lease_until else None,
            }

        renewed = held_by_self and not expired
        new_epoch = (lease.lease_epoch or 0) + (0 if renewed else 1)
        lease.holder_instance_id = worker_instance_id
        lease.lease_epoch = new_epoch
        lease.lease_until = now + timedelta(seconds=self.lease_seconds)
        self._db.add(lease)
        try:
            self._audit.append(
                action="health.supervisor_lease_acquired",
                resource_type="health_supervisor_lease",
                resource_id=self.SINGLETON_KEY,
                request_id=request_id,
                payload={
                    "worker_instance_id": str(worker_instance_id),
                    "lease_epoch": new_epoch,
                    "renewed": renewed,
                },
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise HealthSupervisorError(
                "audit_unavailable",
                "Audit persistence failed; lease acquisition aborted (fail-closed)",
            ) from None
        return {
            "acquired": True,
            "lease_epoch": new_epoch,
            "lease_until": lease.lease_until.isoformat(),
            "renewed": renewed,
        }

    def release_lease(
        self, worker_instance_id: uuid.UUID, *, request_id: str | None = None
    ) -> None:
        lease = self._lock_lease_row()
        if lease is None or lease.holder_instance_id != worker_instance_id:
            return
        lease.holder_instance_id = None
        lease.lease_until = None
        self._db.add(lease)
        try:
            self._audit.append(
                action="health.supervisor_lease_released",
                resource_type="health_supervisor_lease",
                resource_id=self.SINGLETON_KEY,
                request_id=request_id,
                payload={"worker_instance_id": str(worker_instance_id)},
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()

    # --- Probes ---

    def _probe_postgres(self) -> tuple[HealthStatus, str]:
        try:
            self._db.execute(text("SELECT 1"))
            return HealthStatus.HEALTHY, "select_1 succeeded"
        except Exception as exc:  # noqa: BLE001 — probe must never crash the cycle
            return HealthStatus.UNHEALTHY, f"select_1 failed: {exc}"

    def _probe_redis(self) -> tuple[HealthStatus, str]:
        client: redis.Redis[Any] | None = None
        try:
            client = redis.Redis.from_url(self._settings.redis_url, socket_connect_timeout=2)
            if client.ping() is True:
                return HealthStatus.HEALTHY, "ping succeeded"
            return HealthStatus.UNHEALTHY, "unexpected ping response"
        except Exception as exc:  # noqa: BLE001 — probe must never crash the cycle
            return HealthStatus.UNHEALTHY, f"ping failed: {exc}"
        finally:
            if client is not None:
                client.close()

    def _next_sequence_number(self, service_key: str) -> int:
        service = self._registry.get_by_key(service_key)
        if service is None:
            return 1
        projection = self._db.get(ServiceHealthProjection, service.id)
        last = projection.last_sequence_number if projection is not None else None
        return int(last or 0) + 1

    # --- Incident + protective action orchestration ---

    def _manage_incidents(
        self, *, evaluations: list[ServiceEvaluation], request_id: str | None
    ) -> dict[str, Any]:
        opened: list[str] = []
        closed: list[str] = []
        for evaluation in evaluations:
            correlation_key = f"health:{evaluation.service.service_key}"
            if (
                evaluation.status == HealthStatus.UNHEALTHY
                and evaluation.service.criticality == ServiceCriticality.CRITICAL
            ):
                _, created = self._incidents.open_incident(
                    title=f"{evaluation.service.display_name} unhealthy",
                    description=evaluation.detail,
                    severity=IncidentSeverity.CRITICAL,
                    actor=None,
                    correlation_key=correlation_key,
                    source_service=evaluation.service,
                    request_id=request_id,
                )
                if created:
                    opened.append(correlation_key)
            elif evaluation.status == HealthStatus.HEALTHY:
                existing = self._incidents.find_open_by_correlation_key(correlation_key)
                if existing is not None:
                    self._incidents.transition(
                        incident_id=existing.id,
                        target_status=IncidentStatus.CLOSED,
                        actor=None,
                        note="auto-resolved by health supervisor",
                        request_id=request_id,
                    )
                    closed.append(correlation_key)
        return {"opened": opened, "closed": closed}

    def _maybe_apply_protective_action(
        self,
        *,
        evaluations: list[ServiceEvaluation],
        cycle_id: str,
        request_id: str | None,
    ) -> dict[str, Any]:
        candidates = [
            e
            for e in evaluations
            if e.status == HealthStatus.UNHEALTHY
            and e.service.criticality == ServiceCriticality.CRITICAL
            and e.consecutive_failures >= self.degrade_failure_threshold
        ]
        if not candidates:
            return {"triggered": False}

        try:
            current_mode = self._operating_mode.get_state().current_mode
        except OperatingModeError as exc:
            if exc.code == "institutional_state_missing":
                return {
                    "triggered": False,
                    "skipped": True,
                    "code": "institutional_state_missing",
                    "note": "SystemState uninitialized; protective degrade deferred",
                }
            raise HealthSupervisorError(exc.code, exc.message) from exc

        rationale = "; ".join(
            (
                f"{c.service.service_key} unhealthy for "
                f"{c.consecutive_failures} consecutive evaluations"
            )
            for c in candidates
        )
        idempotency_key = f"health_supervisor:degrade:{cycle_id}"
        incident_id: uuid.UUID | None = None
        for candidate in candidates:
            existing_incident = self._incidents.find_open_by_correlation_key(
                f"health:{candidate.service.service_key}"
            )
            if existing_incident is not None:
                incident_id = existing_incident.id
                break

        action, _created = self._protective_actions.create_recommendation(
            action_type=ProtectiveActionType.RECOMMEND_SAFE_MODE,
            rationale=rationale,
            idempotency_key=idempotency_key,
            incident_id=incident_id,
            source_service_id=candidates[0].service.id,
            payload={
                "candidates": [c.service.service_key for c in candidates],
                "current_mode": current_mode.value,
            },
            request_id=request_id,
        )

        try:
            self._audit.append(
                action="health.safe_mode_recommended",
                resource_type="protective_action_recommendation",
                resource_id=str(action.id),
                request_id=request_id,
                payload={"rationale": rationale, "current_mode": current_mode.value},
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()

        if current_mode not in DEGRADE_ELIGIBLE_MODES:
            return {
                "triggered": True,
                "recommendation_id": str(action.id),
                "applied": False,
                "reason": "mode_not_degrade_eligible",
            }

        try:
            result = self._operating_mode.system_enter_safe_mode(
                reason=f"health_supervisor: {rationale}",
                idempotency_key=f"health_supervisor:degrade:apply:{cycle_id}",
                request_id=request_id,
                incident_id=incident_id,
            )
        except OperatingModeError as exc:
            try:
                self._audit.append(
                    action="health.safe_mode_apply_skipped",
                    resource_type="protective_action_recommendation",
                    resource_id=str(action.id),
                    request_id=request_id,
                    payload={"code": exc.code, "message": exc.message},
                )
                self._db.commit()
            except AuditError:
                self._db.rollback()
            return {
                "triggered": True,
                "recommendation_id": str(action.id),
                "applied": False,
                "reason": exc.code,
            }

        applied = self._protective_actions.mark_applied(action_id=action.id, request_id=request_id)
        try:
            self._audit.append(
                action="health.safe_mode_applied",
                resource_type="protective_action_recommendation",
                resource_id=str(applied.id),
                request_id=request_id,
                payload={"operating_mode_result": result},
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise HealthSupervisorError(
                "audit_unavailable",
                "Audit persistence failed after applying SAFE_MODE degrade (fail-closed)",
            ) from None
        return {
            "triggered": True,
            "recommendation_id": str(applied.id),
            "applied": True,
            "operating_mode_result": result,
        }

    # --- Cycle orchestration ---

    def run_cycle(self, *, instance_id: uuid.UUID, request_id: str | None = None) -> dict[str, Any]:
        lease_result = self.acquire_or_renew_lease(instance_id, request_id=request_id)
        if not lease_result.get("acquired"):
            return {"lease_acquired": False, **lease_result}

        cycle_id = str(uuid.uuid4())
        now = _utcnow()

        postgres_status, postgres_detail = self._probe_postgres()
        redis_status, redis_detail = self._probe_redis()
        probes: dict[str, tuple[HealthStatus, str]] = {
            "postgres": (postgres_status, postgres_detail),
            "redis": (redis_status, redis_detail),
            "health_supervisor": (HealthStatus.HEALTHY, "supervisor cycle executing"),
        }

        heartbeat_results: dict[str, Any] = {}
        for service_key, (status_value, detail) in probes.items():
            try:
                heartbeat_results[service_key] = self._heartbeats.record_heartbeat(
                    service_key=service_key,
                    status=status_value,
                    observed_at=now,
                    idempotency_key=f"health_supervisor:{cycle_id}:{service_key}",
                    sequence_number=self._next_sequence_number(service_key),
                    detail=detail,
                    worker_instance_id=instance_id,
                    request_id=request_id,
                )
            except HealthError as exc:
                heartbeat_results[service_key] = {"error": exc.code, "message": exc.message}

        services = self._registry.list_enabled()
        evaluations: list[ServiceEvaluation] = []
        for service in services:
            try:
                evaluation = self._evaluation.evaluate_and_persist(
                    service=service, now=now, request_id=request_id
                )
            except HealthEvaluationError as exc:
                raise HealthSupervisorError(exc.code, exc.message) from exc
            evaluations.append(evaluation)

        institutional_status, summary = self._evaluation.aggregate_institutional(evaluations)
        try:
            self._evaluation.update_institutional_state(
                status=institutional_status, summary=summary, request_id=request_id
            )
        except HealthEvaluationError as exc:
            raise HealthSupervisorError(exc.code, exc.message) from exc

        incident_result = self._manage_incidents(evaluations=evaluations, request_id=request_id)
        protective_result = self._maybe_apply_protective_action(
            evaluations=evaluations, cycle_id=cycle_id, request_id=request_id
        )

        lease_row = self._lock_lease_row()
        if lease_row is not None:
            lease_row.last_cycle_at = now
            lease_row.last_cycle_result = institutional_status.value
            self._db.add(lease_row)

        try:
            self._audit.append(
                action="health.supervisor_cycle_completed",
                resource_type="health_supervisor_lease",
                resource_id=self.SINGLETON_KEY,
                request_id=request_id,
                payload={
                    "cycle_id": cycle_id,
                    "institutional_status": institutional_status.value,
                    "incidents": incident_result,
                    "protective_action": protective_result,
                },
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise HealthSupervisorError(
                "audit_unavailable",
                "Audit persistence failed; supervisor cycle aborted (fail-closed)",
            ) from None

        return {
            "lease_acquired": True,
            "cycle_id": cycle_id,
            "institutional_status": institutional_status.value,
            "heartbeats": heartbeat_results,
            "incidents": incident_result,
            "protective_action": protective_result,
        }
