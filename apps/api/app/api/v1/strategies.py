"""Strategy Laboratory HTTP API (Phase 11) — research only, no live trading."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    RequireAnyAuthenticatedRead,
    RequireFounder,
    RequireFounderOrOperator,
)
from app.db.session import get_db
from app.schemas.strategy import (
    ReasonBody,
    ResearchDatasetCreate,
    ResearchDatasetRead,
    ResearchRunCreate,
    ResearchRunRead,
    ResearchRunResultRead,
    StrategyComparisonCreate,
    StrategyComparisonRead,
    StrategyDocumentCreate,
    StrategyDocumentRead,
    StrategyVersionCreate,
    StrategyVersionParametersUpdate,
    StrategyVersionRead,
    ValidationReportCreate,
    ValidationReportRead,
)
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.strategy_laboratory_service import (
    StrategyLabError,
    StrategyLaboratoryService,
)

router = APIRouter(prefix="/api/v1/strategies", tags=["strategy-laboratory"])

_ERROR_STATUS: dict[str, int] = {
    "document_not_found": status.HTTP_404_NOT_FOUND,
    "version_not_found": status.HTTP_404_NOT_FOUND,
    "dataset_not_found": status.HTTP_404_NOT_FOUND,
    "run_not_found": status.HTTP_404_NOT_FOUND,
    "result_not_found": status.HTTP_404_NOT_FOUND,
    "duplicate_strategy_key": status.HTTP_409_CONFLICT,
    "duplicate_dataset_key": status.HTTP_409_CONFLICT,
    "version_immutable": status.HTTP_409_CONFLICT,
    "invalid_transition": status.HTTP_409_CONFLICT,
    "run_not_cancellable": status.HTTP_409_CONFLICT,
    "reason_required": status.HTTP_400_BAD_REQUEST,
    "unknown_strategy_class": status.HTTP_400_BAD_REQUEST,
    "unbounded_budget": status.HTTP_400_BAD_REQUEST,
    "invalid_run_kind": status.HTTP_400_BAD_REQUEST,
    "provenance_required": status.HTTP_400_BAD_REQUEST,
}


def get_lab_service(db: Session = Depends(get_db)) -> StrategyLaboratoryService:
    return StrategyLaboratoryService(db)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, StrategyLabError):
        return HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": "internal_error", "message": "Unexpected error"},
    )


# Static paths MUST be registered before /{document_id} to avoid capture.


@router.get("", response_model=list[StrategyDocumentRead])
def list_documents(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> list[StrategyDocumentRead]:
    return [
        StrategyDocumentRead.model_validate(row) for row in service.list_documents()
    ]


@router.post(
    "",
    response_model=StrategyDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    body: StrategyDocumentCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyDocumentRead:
    try:
        row = service.create_document(
            strategy_key=body.strategy_key,
            name=body.name,
            description=body.description,
            tags=body.tags,
            owner_user_id=principal.user.id,
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyDocumentRead.model_validate(row)


@router.get("/datasets", response_model=list[ResearchDatasetRead])
def list_datasets(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> list[ResearchDatasetRead]:
    return [
        ResearchDatasetRead.model_validate(row) for row in service.list_datasets()
    ]


@router.post(
    "/datasets",
    response_model=ResearchDatasetRead,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset(
    body: ResearchDatasetCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> ResearchDatasetRead:
    try:
        row = service.register_dataset(
            dataset_key=body.dataset_key,
            name=body.name,
            provenance=body.provenance,
            source_kind=body.source_kind,
            bars=body.bars,
            metadata_json=body.metadata_json,
            actor_user_id=principal.user.id,
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return ResearchDatasetRead.model_validate(row)


@router.get("/runs", response_model=list[ResearchRunRead])
def list_runs(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: StrategyLaboratoryService = Depends(get_lab_service),
    strategy_version_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ResearchRunRead]:
    return [
        ResearchRunRead.model_validate(row)
        for row in service.list_runs(
            strategy_version_id=strategy_version_id, limit=limit, offset=offset
        )
    ]


@router.post(
    "/runs",
    response_model=ResearchRunRead,
    status_code=status.HTTP_201_CREATED,
)
def create_run(
    body: ResearchRunCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> ResearchRunRead:
    try:
        row = service.create_run(
            kind=body.kind,
            strategy_version_id=body.strategy_version_id,
            dataset_id=body.dataset_id,
            created_by_user_id=principal.user.id,
            execution_assumptions=body.execution_assumptions.model_dump(),
            parameters=body.parameters,
            budget=body.budget,
            random_seed=body.random_seed,
            execute=body.execute,
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return ResearchRunRead.model_validate(row)


@router.get("/runs/{run_id}", response_model=ResearchRunRead)
def get_run(
    run_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> ResearchRunRead:
    try:
        row = service.get_run(run_id)
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return ResearchRunRead.model_validate(row)


@router.post("/runs/{run_id}/cancel", response_model=ResearchRunRead)
def cancel_run(
    run_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> ResearchRunRead:
    try:
        row = service.cancel_run(run_id=run_id, actor_user_id=principal.user.id)
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return ResearchRunRead.model_validate(row)


@router.get("/runs/{run_id}/results", response_model=ResearchRunResultRead)
def get_run_result(
    run_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> ResearchRunResultRead:
    try:
        row = service.get_result(run_id)
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return ResearchRunResultRead.model_validate(row)


@router.get("/validation-reports", response_model=list[ValidationReportRead])
def list_validation_reports(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: StrategyLaboratoryService = Depends(get_lab_service),
    strategy_version_id: uuid.UUID | None = None,
) -> list[ValidationReportRead]:
    return [
        ValidationReportRead.model_validate(row)
        for row in service.list_validation_reports(
            strategy_version_id=strategy_version_id
        )
    ]


@router.post(
    "/validation-reports",
    response_model=ValidationReportRead,
    status_code=status.HTTP_201_CREATED,
)
def create_validation_report(
    body: ValidationReportCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> ValidationReportRead:
    try:
        row = service.create_validation_report(
            strategy_version_id=body.strategy_version_id,
            title=body.title,
            verdict=body.verdict,
            summary=body.summary,
            run_id=body.run_id,
            evidence=body.evidence,
            created_by_user_id=principal.user.id,
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return ValidationReportRead.model_validate(row)


@router.get("/comparisons", response_model=list[StrategyComparisonRead])
def list_comparisons(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> list[StrategyComparisonRead]:
    return [
        StrategyComparisonRead.model_validate(row)
        for row in service.list_comparisons()
    ]


@router.post(
    "/comparisons",
    response_model=StrategyComparisonRead,
    status_code=status.HTTP_201_CREATED,
)
def create_comparison(
    body: StrategyComparisonCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyComparisonRead:
    try:
        row = service.create_comparison(
            dataset_id=body.dataset_id,
            version_ids=body.version_ids,
            execution_assumptions=body.execution_assumptions.model_dump(),
            created_by_user_id=principal.user.id,
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyComparisonRead.model_validate(row)


@router.get("/versions/{version_id}", response_model=StrategyVersionRead)
def get_version(
    version_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyVersionRead:
    try:
        row = service.get_version(version_id)
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyVersionRead.model_validate(row)


@router.patch("/versions/{version_id}/parameters", response_model=StrategyVersionRead)
def update_version_parameters(
    version_id: uuid.UUID,
    body: StrategyVersionParametersUpdate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyVersionRead:
    try:
        row = service.update_version_parameters(
            version_id=version_id,
            parameters=body.parameters,
            actor_user_id=principal.user.id,
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyVersionRead.model_validate(row)


@router.post("/versions/{version_id}/submit", response_model=StrategyVersionRead)
def submit_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyVersionRead:
    try:
        row = service.submit_version(
            version_id=version_id, actor_user_id=principal.user.id
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyVersionRead.model_validate(row)


@router.post("/versions/{version_id}/approve", response_model=StrategyVersionRead)
def approve_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyVersionRead:
    try:
        row = service.approve_version(
            version_id=version_id, actor_user_id=principal.user.id
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyVersionRead.model_validate(row)


@router.post("/versions/{version_id}/reject", response_model=StrategyVersionRead)
def reject_version(
    version_id: uuid.UUID,
    body: ReasonBody,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyVersionRead:
    try:
        row = service.reject_version(
            version_id=version_id,
            actor_user_id=principal.user.id,
            reason=body.reason,
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyVersionRead.model_validate(row)


@router.post("/versions/{version_id}/suspend", response_model=StrategyVersionRead)
def suspend_version(
    version_id: uuid.UUID,
    body: ReasonBody,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyVersionRead:
    try:
        row = service.suspend_version(
            version_id=version_id,
            actor_user_id=principal.user.id,
            reason=body.reason,
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyVersionRead.model_validate(row)


@router.post("/versions/{version_id}/retire", response_model=StrategyVersionRead)
def retire_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyVersionRead:
    try:
        row = service.retire_version(
            version_id=version_id, actor_user_id=principal.user.id
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyVersionRead.model_validate(row)


@router.post("/versions/{version_id}/archive", response_model=StrategyVersionRead)
def archive_version(
    version_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyVersionRead:
    try:
        row = service.archive_version(
            version_id=version_id, actor_user_id=principal.user.id
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyVersionRead.model_validate(row)


@router.get("/{document_id}", response_model=StrategyDocumentRead)
def get_document(
    document_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyDocumentRead:
    try:
        row = service.get_document(document_id)
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyDocumentRead.model_validate(row)


@router.get("/{document_id}/versions", response_model=list[StrategyVersionRead])
def list_versions(
    document_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> list[StrategyVersionRead]:
    try:
        rows = service.list_versions(document_id)
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return [StrategyVersionRead.model_validate(row) for row in rows]


@router.post(
    "/{document_id}/versions",
    response_model=StrategyVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    document_id: uuid.UUID,
    body: StrategyVersionCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: StrategyLaboratoryService = Depends(get_lab_service),
) -> StrategyVersionRead:
    try:
        row = service.create_version(
            document_id=document_id,
            version_label=body.version_label,
            strategy_class=body.strategy_class,
            parameters=body.parameters,
            parameter_schema=body.parameter_schema,
            code_ref=body.code_ref,
            change_summary=body.change_summary,
            created_by_user_id=principal.user.id,
        )
    except StrategyLabError as exc:
        raise _http_error(exc) from exc
    return StrategyVersionRead.model_validate(row)
