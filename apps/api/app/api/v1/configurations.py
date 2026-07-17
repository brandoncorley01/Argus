from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    RequireAnyAuthenticatedRead,
    RequireFounder,
    RequireOperatorRead,
    require_csrf,
)
from app.db.session import get_db
from app.models import ConfigurationDocument, ConfigurationVersion, VersionLifecycleStatus
from app.schemas.governance import (
    ConfigurationDocumentCreate,
    ConfigurationDocumentResponse,
    ConfigurationVersionCreate,
    ConfigurationVersionResponse,
    ConfigurationVersionUpdateDraft,
    TransitionRequest,
    VersionCompareResponse,
)
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.governance_service import GovernanceError, GovernanceService

router = APIRouter(prefix="/api/v1/configurations", tags=["configurations"])


def get_governance_service(db: Session = Depends(get_db)) -> GovernanceService:
    return GovernanceService(db)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, GovernanceError):
        detail = str(exc)
        code = status.HTTP_400_BAD_REQUEST
        if "not found" in detail.lower():
            code = status.HTTP_404_NOT_FOUND
        return HTTPException(status_code=code, detail=detail)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error"
    )


@router.post(
    "/documents",
    response_model=ConfigurationDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    body: ConfigurationDocumentCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ConfigurationDocument:
    try:
        return service.create_configuration_document(
            actor=principal,
            document_key=body.document_key,
            name=body.name,
            description=body.description,
            schema_identifier=body.schema_identifier,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.get("/documents", response_model=list[ConfigurationDocumentResponse])
def list_documents(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> list[ConfigurationDocument]:
    return list(
        db.scalars(select(ConfigurationDocument).order_by(ConfigurationDocument.document_key))
    )


@router.get("/documents/{document_id}", response_model=ConfigurationDocumentResponse)
def get_document(
    document_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> ConfigurationDocument:
    row = db.get(ConfigurationDocument, document_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Configuration document not found"
        )
    return row


@router.post(
    "/documents/{document_id}/versions",
    response_model=ConfigurationVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    document_id: uuid.UUID,
    body: ConfigurationVersionCreate,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ConfigurationVersion:
    try:
        return service.create_configuration_version(
            actor=principal,
            document_id=document_id,
            payload=body.payload,
            change_summary=body.change_summary,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[ConfigurationVersionResponse],
)
def list_versions(
    document_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> list[ConfigurationVersion]:
    return list(
        db.scalars(
            select(ConfigurationVersion)
            .where(ConfigurationVersion.document_id == document_id)
            .order_by(ConfigurationVersion.version_number.asc())
        )
    )


@router.get(
    "/documents/{document_id}/active",
    response_model=ConfigurationVersionResponse,
)
def get_active(
    document_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: GovernanceService = Depends(get_governance_service),
) -> ConfigurationVersion:
    row = service.get_active_configuration(document_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No active configuration version"
        )
    return row


@router.get("/versions/compare", response_model=VersionCompareResponse)
def compare_versions(
    left_id: uuid.UUID,
    right_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireOperatorRead),
    service: GovernanceService = Depends(get_governance_service),
) -> VersionCompareResponse:
    try:
        return VersionCompareResponse(**service.compare_configuration_versions(left_id, right_id))
    except GovernanceError as exc:
        raise _http_error(exc) from exc


@router.patch(
    "/versions/{version_id}",
    response_model=ConfigurationVersionResponse,
)
def update_draft(
    version_id: uuid.UUID,
    body: ConfigurationVersionUpdateDraft,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ConfigurationVersion:
    try:
        return service.update_configuration_draft(
            actor=principal,
            version_id=version_id,
            payload=body.payload,
            change_summary=body.change_summary,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.get("/versions/{version_id}", response_model=ConfigurationVersionResponse)
def get_version(
    version_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> ConfigurationVersion:
    row = db.get(ConfigurationVersion, version_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Configuration version not found"
        )
    return row


@router.post("/versions/{version_id}/submit", response_model=ConfigurationVersionResponse)
def submit_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ConfigurationVersion:
    try:
        return service.transition_configuration_version(
            actor=principal,
            version_id=version_id,
            new_status=VersionLifecycleStatus.UNDER_REVIEW,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.post("/versions/{version_id}/approve", response_model=ConfigurationVersionResponse)
def approve_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ConfigurationVersion:
    try:
        return service.transition_configuration_version(
            actor=principal,
            version_id=version_id,
            new_status=VersionLifecycleStatus.APPROVED,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.post("/versions/{version_id}/reject", response_model=ConfigurationVersionResponse)
def reject_version(
    version_id: uuid.UUID,
    body: TransitionRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ConfigurationVersion:
    try:
        return service.transition_configuration_version(
            actor=principal,
            version_id=version_id,
            new_status=VersionLifecycleStatus.REJECTED,
            rejection_reason=body.rejection_reason,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.post("/versions/{version_id}/activate", response_model=ConfigurationVersionResponse)
def activate_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ConfigurationVersion:
    try:
        return service.activate_configuration_version(
            actor=principal,
            version_id=version_id,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.post("/versions/{version_id}/retire", response_model=ConfigurationVersionResponse)
def retire_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ConfigurationVersion:
    try:
        return service.transition_configuration_version(
            actor=principal,
            version_id=version_id,
            new_status=VersionLifecycleStatus.RETIRED,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc
