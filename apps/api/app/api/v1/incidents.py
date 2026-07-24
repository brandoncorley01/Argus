"""Incident lifecycle HTTP API (Phase 8)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RequireAnyAuthenticatedRead, RequireFounderOrOperator
from app.db.session import get_db
from app.models import IncidentStatus
from app.schemas.health import (
    IncidentCreateRequest,
    IncidentLifecycleEventRead,
    IncidentNoteRequest,
    IncidentRead,
    IncidentSeverityChangeRequest,
    IncidentTransitionRequest,
)
from app.services.audit_service import AuditError
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.incident_service import IncidentError, IncidentService

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])

_ERROR_STATUS: dict[str, int] = {
    "incident_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_transition": status.HTTP_400_BAD_REQUEST,
    "incident_conflict": status.HTTP_409_CONFLICT,
    "audit_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, IncidentError):
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


def get_incident_service(db: Session = Depends(get_db)) -> IncidentService:
    return IncidentService(db)


@router.get("", response_model=list[IncidentRead])
def list_incidents(
    incident_status: IncidentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: IncidentService = Depends(get_incident_service),
) -> list[IncidentRead]:
    items = service.list_incidents(status=incident_status, limit=limit, offset=offset)
    return [IncidentRead.model_validate(item) for item in items]


@router.get("/{incident_id}", response_model=IncidentRead)
def get_incident(
    incident_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: IncidentService = Depends(get_incident_service),
) -> IncidentRead:
    incident = service.get(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "incident_not_found", "message": "Incident not found"},
        )
    return IncidentRead.model_validate(incident)


@router.get("/{incident_id}/events", response_model=list[IncidentLifecycleEventRead])
def list_incident_events(
    incident_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: IncidentService = Depends(get_incident_service),
) -> list[IncidentLifecycleEventRead]:
    if service.get(incident_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "incident_not_found", "message": "Incident not found"},
        )
    events = service.list_lifecycle_events(incident_id)
    return [IncidentLifecycleEventRead.model_validate(event) for event in events]


@router.post("", response_model=IncidentRead)
def create_incident(
    body: IncidentCreateRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: IncidentService = Depends(get_incident_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> IncidentRead:
    try:
        incident, _created = service.open_incident(
            title=body.title,
            description=body.description,
            severity=body.severity,
            actor=principal,
            related_mode=body.related_mode,
            request_id=request_id,
        )
    except (AuthError, IncidentError) as exc:
        raise _http_error(exc) from exc
    return IncidentRead.model_validate(incident)


@router.post("/{incident_id}/transition", response_model=IncidentRead)
def transition_incident(
    incident_id: uuid.UUID,
    body: IncidentTransitionRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: IncidentService = Depends(get_incident_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> IncidentRead:
    try:
        incident = service.transition(
            incident_id=incident_id,
            target_status=body.target_status,
            actor=principal,
            note=body.note,
            request_id=request_id,
        )
    except (AuthError, IncidentError) as exc:
        raise _http_error(exc) from exc
    return IncidentRead.model_validate(incident)


@router.post("/{incident_id}/severity", response_model=IncidentRead)
def change_incident_severity(
    incident_id: uuid.UUID,
    body: IncidentSeverityChangeRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: IncidentService = Depends(get_incident_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> IncidentRead:
    try:
        incident = service.change_severity(
            incident_id=incident_id,
            new_severity=body.severity,
            actor=principal,
            note=body.note,
            request_id=request_id,
        )
    except (AuthError, IncidentError) as exc:
        raise _http_error(exc) from exc
    return IncidentRead.model_validate(incident)


@router.post("/{incident_id}/notes", response_model=IncidentLifecycleEventRead)
def add_incident_note(
    incident_id: uuid.UUID,
    body: IncidentNoteRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: IncidentService = Depends(get_incident_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> IncidentLifecycleEventRead:
    try:
        event = service.add_note(
            incident_id=incident_id, note=body.note, actor=principal, request_id=request_id
        )
    except (AuthError, IncidentError) as exc:
        raise _http_error(exc) from exc
    return IncidentLifecycleEventRead.model_validate(event)
