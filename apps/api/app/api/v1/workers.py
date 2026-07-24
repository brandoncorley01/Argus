"""Worker identity / instance directory HTTP API (Phase 8)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RequireAnyAuthenticatedRead, RequireFounderOrOperator
from app.db.session import get_db
from app.schemas.health import WorkerIdentityRead, WorkerInstanceRead, WorkerInstanceRegisterRequest
from app.services.auth_service import AuthenticatedPrincipal
from app.services.health_supervisor_service import HealthSupervisorError, HealthSupervisorService

router = APIRouter(prefix="/api/v1/workers", tags=["workers"])

_ERROR_STATUS: dict[str, int] = {
    "worker_identity_not_found": status.HTTP_404_NOT_FOUND,
    "audit_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _http_error(exc: HealthSupervisorError) -> HTTPException:
    return HTTPException(
        status_code=_ERROR_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": exc.code, "message": exc.message},
    )


def get_supervisor_service(db: Session = Depends(get_db)) -> HealthSupervisorService:
    return HealthSupervisorService(db)


@router.get("/identities", response_model=list[WorkerIdentityRead])
def list_worker_identities(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: HealthSupervisorService = Depends(get_supervisor_service),
) -> list[WorkerIdentityRead]:
    return [WorkerIdentityRead.model_validate(row) for row in service.list_worker_identities()]


@router.get("/instances", response_model=list[WorkerInstanceRead])
def list_worker_instances(
    worker_identity_id: uuid.UUID | None = Query(default=None),
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: HealthSupervisorService = Depends(get_supervisor_service),
) -> list[WorkerInstanceRead]:
    rows = service.list_worker_instances(worker_identity_id=worker_identity_id)
    return [WorkerInstanceRead.model_validate(row) for row in rows]


@router.post("/instances/register", response_model=WorkerInstanceRead)
def register_worker_instance(
    body: WorkerInstanceRegisterRequest,
    _: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: HealthSupervisorService = Depends(get_supervisor_service),
) -> WorkerInstanceRead:
    try:
        instance = service.register_instance(
            worker_key=body.worker_key,
            instance_key=body.instance_key,
            hostname=body.hostname,
            metadata=body.metadata,
        )
    except HealthSupervisorError as exc:
        raise _http_error(exc) from exc
    return WorkerInstanceRead.model_validate(instance)
