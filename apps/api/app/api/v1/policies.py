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
from app.models import PolicyDocument, PolicyVersion, VersionLifecycleStatus
from app.schemas.governance import (
    PolicyDocumentCreate,
    PolicyDocumentResponse,
    PolicyVersionCreate,
    PolicyVersionResponse,
    PolicyVersionUpdateDraft,
    TransitionRequest,
    VersionCompareResponse,
)
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.governance_service import GovernanceError, GovernanceService

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])


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
    response_model=PolicyDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    body: PolicyDocumentCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PolicyDocument:
    try:
        return service.create_policy_document(
            actor=principal,
            document_key=body.document_key,
            name=body.name,
            policy_kind=body.policy_kind,
            description=body.description,
            schema_identifier=body.schema_identifier,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.get("/documents", response_model=list[PolicyDocumentResponse])
def list_documents(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> list[PolicyDocument]:
    return list(db.scalars(select(PolicyDocument).order_by(PolicyDocument.document_key)))


@router.get("/documents/{document_id}", response_model=PolicyDocumentResponse)
def get_document(
    document_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> PolicyDocument:
    row = db.get(PolicyDocument, document_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy document not found"
        )
    return row


@router.post(
    "/documents/{document_id}/versions",
    response_model=PolicyVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    document_id: uuid.UUID,
    body: PolicyVersionCreate,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PolicyVersion:
    try:
        return service.create_policy_version(
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
    response_model=list[PolicyVersionResponse],
)
def list_versions(
    document_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> list[PolicyVersion]:
    return list(
        db.scalars(
            select(PolicyVersion)
            .where(PolicyVersion.document_id == document_id)
            .order_by(PolicyVersion.version_number.asc())
        )
    )


@router.get(
    "/documents/{document_id}/active",
    response_model=PolicyVersionResponse,
)
def get_active(
    document_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: GovernanceService = Depends(get_governance_service),
) -> PolicyVersion:
    row = service.get_active_policy(document_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No active policy version"
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
        return VersionCompareResponse(**service.compare_policy_versions(left_id, right_id))
    except GovernanceError as exc:
        raise _http_error(exc) from exc


@router.patch("/versions/{version_id}", response_model=PolicyVersionResponse)
def update_draft(
    version_id: uuid.UUID,
    body: PolicyVersionUpdateDraft,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PolicyVersion:
    try:
        return service.update_policy_draft(
            actor=principal,
            version_id=version_id,
            payload=body.payload,
            change_summary=body.change_summary,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.get("/versions/{version_id}", response_model=PolicyVersionResponse)
def get_version(
    version_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> PolicyVersion:
    row = db.get(PolicyVersion, version_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy version not found"
        )
    return row


@router.post("/versions/{version_id}/submit", response_model=PolicyVersionResponse)
def submit_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PolicyVersion:
    try:
        return service.transition_policy_version(
            actor=principal,
            version_id=version_id,
            new_status=VersionLifecycleStatus.UNDER_REVIEW,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.post("/versions/{version_id}/approve", response_model=PolicyVersionResponse)
def approve_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PolicyVersion:
    try:
        return service.transition_policy_version(
            actor=principal,
            version_id=version_id,
            new_status=VersionLifecycleStatus.APPROVED,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.post("/versions/{version_id}/reject", response_model=PolicyVersionResponse)
def reject_version(
    version_id: uuid.UUID,
    body: TransitionRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PolicyVersion:
    try:
        return service.transition_policy_version(
            actor=principal,
            version_id=version_id,
            new_status=VersionLifecycleStatus.REJECTED,
            rejection_reason=body.rejection_reason,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.post("/versions/{version_id}/activate", response_model=PolicyVersionResponse)
def activate_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PolicyVersion:
    try:
        return service.activate_policy_version(
            actor=principal,
            version_id=version_id,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc


@router.post("/versions/{version_id}/retire", response_model=PolicyVersionResponse)
def retire_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: GovernanceService = Depends(get_governance_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PolicyVersion:
    try:
        return service.transition_policy_version(
            actor=principal,
            version_id=version_id,
            new_status=VersionLifecycleStatus.RETIRED,
            request_id=request_id,
        )
    except (AuthError, GovernanceError) as exc:
        raise _http_error(exc) from exc
