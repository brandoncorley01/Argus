"""Operating Mode State Machine HTTP API (Phase 7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    RequireAnyAuthenticatedRead,
    RequireFounder,
    RequireFounderOrOperator,
)
from app.db.session import get_db
from app.schemas.operating_mode import (
    AllowedTransitionsResponse,
    EmergencyRecoverRequest,
    EmergencyStopRequest,
    ModeAvailabilityItem,
    OperatingModeHistoryItem,
    OperatingModeStateResponse,
    TransitionRequest,
    TransitionResponse,
)
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.operating_mode_service import OperatingModeError, OperatingModeService

router = APIRouter(prefix="/api/v1/operating-mode", tags=["operating-mode"])


def get_operating_mode_service(db: Session = Depends(get_db)) -> OperatingModeService:
    return OperatingModeService(db)


_ERROR_STATUS: dict[str, int] = {
    "invalid_transition": status.HTTP_400_BAD_REQUEST,
    "prerequisite_failed": status.HTTP_400_BAD_REQUEST,
    "mode_unavailable": status.HTTP_400_BAD_REQUEST,
    "recovery_requirements_not_met": status.HTTP_400_BAD_REQUEST,
    "policy_missing": status.HTTP_400_BAD_REQUEST,
    "policy_integrity_failed": status.HTTP_400_BAD_REQUEST,
    "invalid_reference": status.HTTP_400_BAD_REQUEST,
    "stale_state": status.HTTP_409_CONFLICT,
    "idempotency_conflict": status.HTTP_409_CONFLICT,
    "institutional_state_conflict": status.HTTP_409_CONFLICT,
    "institutional_state_missing": status.HTTP_404_NOT_FOUND,
    "audit_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, OperatingModeError):
        return HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": "internal_error", "message": "Unexpected error"},
    )


@router.get("", response_model=OperatingModeStateResponse)
def get_operating_mode(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: OperatingModeService = Depends(get_operating_mode_service),
) -> OperatingModeStateResponse:
    try:
        state = service.get_state()
    except OperatingModeError as exc:
        raise _http_error(exc) from exc
    return OperatingModeStateResponse.model_validate(state)


@router.post(
    "/initialize",
    response_model=OperatingModeStateResponse,
    status_code=status.HTTP_200_OK,
)
def initialize_operating_mode(
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: OperatingModeService = Depends(get_operating_mode_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> OperatingModeStateResponse:
    try:
        state = service.initialize(actor=principal, request_id=request_id)
    except (AuthError, OperatingModeError) as exc:
        raise _http_error(exc) from exc
    return OperatingModeStateResponse.model_validate(state)


@router.get("/history", response_model=list[OperatingModeHistoryItem])
def list_operating_mode_history(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: OperatingModeService = Depends(get_operating_mode_service),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[OperatingModeHistoryItem]:
    rows = service.list_history(limit=limit, offset=offset)
    return [OperatingModeHistoryItem.model_validate(row) for row in rows]


@router.get("/availability", response_model=list[ModeAvailabilityItem])
def get_mode_availability(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: OperatingModeService = Depends(get_operating_mode_service),
) -> list[ModeAvailabilityItem]:
    return [ModeAvailabilityItem.model_validate(row) for row in service.availability()]


@router.get("/transitions", response_model=AllowedTransitionsResponse)
def get_allowed_transitions(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: OperatingModeService = Depends(get_operating_mode_service),
) -> AllowedTransitionsResponse:
    try:
        return AllowedTransitionsResponse.model_validate(service.allowed_transitions())
    except OperatingModeError as exc:
        raise _http_error(exc) from exc


@router.post("/transition", response_model=TransitionResponse)
def transition_operating_mode(
    body: TransitionRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: OperatingModeService = Depends(get_operating_mode_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TransitionResponse:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_transition", "message": "Idempotency-Key header is required"},
        )
    try:
        result = service.transition(
            actor=principal,
            target_mode=body.target_mode,
            reason=body.reason,
            idempotency_key=idempotency_key,
            request_id=request_id,
            incident_id=body.incident_id,
            expected_state_version=body.expected_state_version,
        )
    except (AuthError, OperatingModeError) as exc:
        raise _http_error(exc) from exc
    return TransitionResponse.model_validate(result)


@router.post("/emergency-stop", response_model=TransitionResponse)
def enter_emergency_stop(
    body: EmergencyStopRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: OperatingModeService = Depends(get_operating_mode_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TransitionResponse:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_transition", "message": "Idempotency-Key header is required"},
        )
    try:
        result = service.emergency_stop(
            actor=principal,
            reason=body.reason,
            idempotency_key=idempotency_key,
            request_id=request_id,
            incident_id=body.incident_id,
            expected_state_version=body.expected_state_version,
        )
    except (AuthError, OperatingModeError) as exc:
        raise _http_error(exc) from exc
    return TransitionResponse.model_validate(result)


@router.post("/emergency-stop/recover", response_model=TransitionResponse)
def recover_emergency_stop(
    body: EmergencyRecoverRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: OperatingModeService = Depends(get_operating_mode_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TransitionResponse:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_transition", "message": "Idempotency-Key header is required"},
        )
    try:
        result = service.recover_from_emergency(
            actor=principal,
            reason=body.reason,
            idempotency_key=idempotency_key,
            request_id=request_id,
            expected_state_version=body.expected_state_version,
        )
    except (AuthError, OperatingModeError) as exc:
        raise _http_error(exc) from exc
    return TransitionResponse.model_validate(result)
