"""Institutional health supervisor HTTP API (Phase 8)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RequireAnyAuthenticatedRead, RequireFounder, RequireFounderOrOperator
from app.db.session import get_db
from app.models import ProtectiveActionStatus, RegisteredService, ServiceHealthProjection
from app.schemas.health import (
    HealthSupervisorLeaseRead,
    HeartbeatIngestRequest,
    HeartbeatIngestResponse,
    InstitutionalHealthStateRead,
    ProtectiveActionRecommendationRead,
    RegisteredServiceRead,
    ServiceHealthProjectionRead,
    ServiceWithProjectionRead,
    SupervisorRunCycleRequest,
    SupervisorRunCycleResponse,
)
from app.services.audit_service import AuditError
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.health_evaluation_service import HealthEvaluationError, HealthEvaluationService
from app.services.health_supervisor_service import HealthSupervisorError, HealthSupervisorService
from app.services.heartbeat_service import HealthError, HeartbeatService
from app.services.protective_action_service import ProtectiveActionError, ProtectiveActionService
from app.services.service_registry_service import ServiceRegistryError, ServiceRegistryService

router = APIRouter(prefix="/api/v1/health", tags=["health-supervisor"])

MANUAL_TRIGGER_WORKER_KEY = "health_supervisor_worker"
MANUAL_TRIGGER_INSTANCE_KEY = "manual-api-trigger"

_ERROR_STATUS: dict[str, int] = {
    "invalid_heartbeat": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "sequence_out_of_order": status.HTTP_409_CONFLICT,
    "idempotency_conflict": status.HTTP_409_CONFLICT,
    "service_not_found": status.HTTP_404_NOT_FOUND,
    "service_disabled": status.HTTP_400_BAD_REQUEST,
    "health_state_conflict": status.HTTP_409_CONFLICT,
    "institutional_health_state_missing": status.HTTP_404_NOT_FOUND,
    "lease_missing": status.HTTP_404_NOT_FOUND,
    "worker_identity_not_found": status.HTTP_404_NOT_FOUND,
    "action_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_transition": status.HTTP_400_BAD_REQUEST,
    "invalid_action": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "action_conflict": status.HTTP_409_CONFLICT,
    "audit_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(
        exc,
        HealthError
        | HealthEvaluationError
        | HealthSupervisorError
        | ProtectiveActionError
        | ServiceRegistryError,
    ):
        return HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail={"code": exc.code, "message": exc.message},
        )
    if isinstance(exc, AuditError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "audit_unavailable", "message": str(exc)},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": "internal_error", "message": "Unexpected error"},
    )


def get_registry_service(db: Session = Depends(get_db)) -> ServiceRegistryService:
    return ServiceRegistryService(db)


def get_heartbeat_service(db: Session = Depends(get_db)) -> HeartbeatService:
    return HeartbeatService(db)


def get_supervisor_service(db: Session = Depends(get_db)) -> HealthSupervisorService:
    return HealthSupervisorService(db)


def get_evaluation_service(db: Session = Depends(get_db)) -> HealthEvaluationService:
    return HealthEvaluationService(db)


def get_protective_action_service(db: Session = Depends(get_db)) -> ProtectiveActionService:
    return ProtectiveActionService(db)


def _service_with_projection(db: Session, service: RegisteredService) -> ServiceWithProjectionRead:
    projection = db.get(ServiceHealthProjection, service.id)
    return ServiceWithProjectionRead(
        service=RegisteredServiceRead.model_validate(service),
        projection=(
            ServiceHealthProjectionRead.model_validate(projection)
            if projection is not None
            else None
        ),
    )


@router.get("/services", response_model=list[ServiceWithProjectionRead])
def list_services(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    registry: ServiceRegistryService = Depends(get_registry_service),
    db: Session = Depends(get_db),
) -> list[ServiceWithProjectionRead]:
    return [_service_with_projection(db, service) for service in registry.list_all()]


@router.get("/services/{service_key}", response_model=ServiceWithProjectionRead)
def get_service(
    service_key: str,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    registry: ServiceRegistryService = Depends(get_registry_service),
    db: Session = Depends(get_db),
) -> ServiceWithProjectionRead:
    service = registry.get_by_key(service_key)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "service_not_found", "message": "service not found"},
        )
    return _service_with_projection(db, service)


@router.post("/heartbeats", response_model=HeartbeatIngestResponse)
def ingest_heartbeat(
    body: HeartbeatIngestRequest,
    _: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: HeartbeatService = Depends(get_heartbeat_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> HeartbeatIngestResponse:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_heartbeat",
                "message": "Idempotency-Key header is required",
            },
        )
    try:
        result = service.record_heartbeat(
            service_key=body.service_key,
            status=body.status,
            observed_at=body.observed_at,
            idempotency_key=idempotency_key,
            sequence_number=body.sequence_number,
            detail=body.detail,
            payload=body.payload,
            worker_instance_id=body.worker_instance_id,
            request_id=request_id,
        )
    except HealthError as exc:
        raise _http_error(exc) from exc
    return HeartbeatIngestResponse.model_validate(result)


@router.get("/institutional", response_model=InstitutionalHealthStateRead)
def get_institutional_health(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    evaluation: HealthEvaluationService = Depends(get_evaluation_service),
) -> InstitutionalHealthStateRead:
    state = evaluation.get_institutional_state()
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "institutional_health_state_missing",
                "message": "institutional_health_state row is missing",
            },
        )
    return InstitutionalHealthStateRead.model_validate(state)


@router.get("/lease", response_model=HealthSupervisorLeaseRead)
def get_lease(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    supervisor: HealthSupervisorService = Depends(get_supervisor_service),
) -> HealthSupervisorLeaseRead:
    lease = supervisor.get_lease()
    if lease is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "lease_missing",
                "message": "health_supervisor_leases row is missing",
            },
        )
    return HealthSupervisorLeaseRead.model_validate(lease)


@router.post("/supervisor/run-cycle", response_model=SupervisorRunCycleResponse)
def run_supervisor_cycle(
    body: SupervisorRunCycleRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    supervisor: HealthSupervisorService = Depends(get_supervisor_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> SupervisorRunCycleResponse:
    try:
        instance_id = body.instance_id
        if instance_id is None:
            instance = supervisor.register_instance(
                worker_key=MANUAL_TRIGGER_WORKER_KEY,
                instance_key=MANUAL_TRIGGER_INSTANCE_KEY,
                hostname="api",
                metadata={
                    "trigger": "manual_api",
                    "actor_user_id": str(principal.user.id),
                },
            )
            instance_id = instance.id
        result = supervisor.run_cycle(instance_id=instance_id, request_id=request_id)
    except HealthSupervisorError as exc:
        raise _http_error(exc) from exc
    return SupervisorRunCycleResponse.model_validate(result)


@router.get("/protective-actions", response_model=list[ProtectiveActionRecommendationRead])
def list_protective_actions(
    action_status: ProtectiveActionStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: ProtectiveActionService = Depends(get_protective_action_service),
) -> list[ProtectiveActionRecommendationRead]:
    items = service.list_actions(status=action_status, limit=limit, offset=offset)
    return [ProtectiveActionRecommendationRead.model_validate(item) for item in items]


@router.post(
    "/protective-actions/{action_id}/dismiss",
    response_model=ProtectiveActionRecommendationRead,
)
def dismiss_protective_action(
    action_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: ProtectiveActionService = Depends(get_protective_action_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ProtectiveActionRecommendationRead:
    try:
        result = service.dismiss(
            action_id=action_id, actor=principal, request_id=request_id
        )
    except (AuthError, ProtectiveActionError) as exc:
        raise _http_error(exc) from exc
    return ProtectiveActionRecommendationRead.model_validate(result)
