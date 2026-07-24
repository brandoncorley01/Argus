"""Micro-Live Institution HTTP API (Phase 13) — deny-by-default.

No endpoint in this router can activate live trading, return a credential
value, or cause a real order to be submitted.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import RequireAnyAuthenticatedRead, RequireFounder, RequireFounderOrOperator
from app.db.session import get_db
from app.schemas.micro_live import (
    ActivationStateRead,
    ActivationTransitionRead,
    ActivationTransitionRequest,
    AdapterRead,
    CredentialReferenceCreate,
    CredentialReferenceRead,
    DryRunOrderResult,
    DryRunOrderValidate,
    KillSwitchRead,
    KillSwitchSet,
    MicroCapitalPolicyRead,
    MicroCapitalPolicyUpsert,
    MicroLiveStatusRead,
    ReconciliationDiscrepancyRead,
    ReconciliationRunCreate,
    ReconciliationRunRead,
)
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.kill_switch_service import KillSwitchError, KillSwitchService
from app.services.live_activation_service import LiveActivationError, LiveActivationService
from app.services.micro_capital_service import MicroCapitalError, MicroCapitalService
from app.services.micro_live_service import MicroLiveService
from app.services.reconciliation_service import ReconciliationError, ReconciliationService

router = APIRouter(prefix="/api/v1/micro-live", tags=["micro-live"])

_ERROR_STATUS = {
    "invalid_state": status.HTTP_400_BAD_REQUEST,
    "invalid_transition": status.HTTP_400_BAD_REQUEST,
    "founder_required": status.HTTP_403_FORBIDDEN,
    "credentials_required": status.HTTP_400_BAD_REQUEST,
    "reason_required": status.HTTP_400_BAD_REQUEST,
    "live_execution_not_certified": status.HTTP_403_FORBIDDEN,
    "corrupt_state": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "invalid_reference": status.HTTP_400_BAD_REQUEST,
    "reference_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_scope": status.HTTP_400_BAD_REQUEST,
    "not_found": status.HTTP_404_NOT_FOUND,
    "policy_missing": status.HTTP_400_BAD_REQUEST,
    "invalid_policy": status.HTTP_400_BAD_REQUEST,
    "run_not_found": status.HTTP_404_NOT_FOUND,
}


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(
        exc, (LiveActivationError, KillSwitchError, MicroCapitalError, ReconciliationError)
    ):
        return HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, 400),
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(status_code=500, detail="Unexpected error")


def get_activation_service(db: Session = Depends(get_db)) -> LiveActivationService:
    return LiveActivationService(db)


def get_kill_switch_service(db: Session = Depends(get_db)) -> KillSwitchService:
    return KillSwitchService(db)


def get_capital_service(db: Session = Depends(get_db)) -> MicroCapitalService:
    return MicroCapitalService(db)


def get_reconciliation_service(db: Session = Depends(get_db)) -> ReconciliationService:
    return ReconciliationService(db)


def get_micro_live_service(db: Session = Depends(get_db)) -> MicroLiveService:
    return MicroLiveService(db)


@router.get("/status", response_model=MicroLiveStatusRead)
def get_status(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MicroLiveService = Depends(get_micro_live_service),
) -> MicroLiveStatusRead:
    return MicroLiveStatusRead.model_validate(service.status().__dict__)


@router.get("/activation", response_model=ActivationStateRead)
def get_activation(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: LiveActivationService = Depends(get_activation_service),
) -> ActivationStateRead:
    return ActivationStateRead.model_validate(service.status().__dict__)


@router.get("/activation/transitions", response_model=list[ActivationTransitionRead])
def list_activation_transitions(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: LiveActivationService = Depends(get_activation_service),
) -> list[ActivationTransitionRead]:
    return [ActivationTransitionRead.model_validate(t) for t in service.list_transitions()]


@router.post("/activation/transition", response_model=ActivationStateRead)
def transition_activation(
    body: ActivationTransitionRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: LiveActivationService = Depends(get_activation_service),
) -> ActivationStateRead:
    try:
        service.transition(
            target=body.target_state,
            reason=body.reason,
            evidence=body.evidence,
            actor=principal,
        )
        return ActivationStateRead.model_validate(service.status().__dict__)
    except LiveActivationError as exc:
        raise _http(exc) from exc


@router.get("/credential-references", response_model=list[CredentialReferenceRead])
def list_credential_references(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: LiveActivationService = Depends(get_activation_service),
) -> list[CredentialReferenceRead]:
    return [
        CredentialReferenceRead.model_validate(r) for r in service.list_credential_references()
    ]


@router.post(
    "/credential-references", response_model=CredentialReferenceRead, status_code=201
)
def create_credential_reference(
    body: CredentialReferenceCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: LiveActivationService = Depends(get_activation_service),
) -> CredentialReferenceRead:
    try:
        row = service.create_credential_reference(
            provider_key=body.provider_key,
            ref_name=body.ref_name,
            purpose=body.purpose,
            actor=principal,
        )
        return CredentialReferenceRead.model_validate(row)
    except LiveActivationError as exc:
        raise _http(exc) from exc


@router.post(
    "/credential-references/{reference_id}/validate",
    response_model=CredentialReferenceRead,
)
def validate_credential_reference(
    reference_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: LiveActivationService = Depends(get_activation_service),
) -> CredentialReferenceRead:
    try:
        row = service.validate_credential_reference(reference_id, actor=principal)
        return CredentialReferenceRead.model_validate(row)
    except LiveActivationError as exc:
        raise _http(exc) from exc


@router.get("/kill-switches", response_model=list[KillSwitchRead])
def list_kill_switches(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: KillSwitchService = Depends(get_kill_switch_service),
) -> list[KillSwitchRead]:
    return [KillSwitchRead.model_validate(s) for s in service.list_switches()]


@router.post("/kill-switches", response_model=KillSwitchRead)
def set_kill_switch(
    body: KillSwitchSet,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: KillSwitchService = Depends(get_kill_switch_service),
) -> KillSwitchRead:
    try:
        row = service.set_switch(
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            active=body.active,
            reason=body.reason,
            actor=principal,
        )
        return KillSwitchRead.model_validate(row)
    except KillSwitchError as exc:
        raise _http(exc) from exc


@router.get("/capital-policy", response_model=MicroCapitalPolicyRead)
def get_capital_policy(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MicroCapitalService = Depends(get_capital_service),
) -> MicroCapitalPolicyRead:
    try:
        return MicroCapitalPolicyRead.model_validate(service.get_active_policy())
    except MicroCapitalError as exc:
        raise _http(exc) from exc


@router.put("/capital-policy", response_model=MicroCapitalPolicyRead)
def put_capital_policy(
    body: MicroCapitalPolicyUpsert,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: MicroCapitalService = Depends(get_capital_service),
) -> MicroCapitalPolicyRead:
    try:
        row = service.set_policy(
            max_deployable_capital=body.max_deployable_capital,
            max_order_notional=body.max_order_notional,
            max_daily_loss=body.max_daily_loss,
            max_concurrent_exposure=body.max_concurrent_exposure,
            max_provider_exposure=body.max_provider_exposure,
            max_strategy_exposure=body.max_strategy_exposure,
            actor=principal,
        )
        return MicroCapitalPolicyRead.model_validate(row)
    except MicroCapitalError as exc:
        raise _http(exc) from exc


@router.post("/reconciliation/runs", response_model=ReconciliationRunRead, status_code=201)
def create_reconciliation_run(
    body: ReconciliationRunCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> ReconciliationRunRead:
    try:
        row = service.run(
            provider_key=body.provider_key,
            authoritative_state=body.authoritative_state,
            comparison_state=body.comparison_state,
            actor=principal,
        )
        return ReconciliationRunRead.model_validate(row)
    except ReconciliationError as exc:
        raise _http(exc) from exc


@router.get("/reconciliation/runs", response_model=list[ReconciliationRunRead])
def list_reconciliation_runs(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> list[ReconciliationRunRead]:
    return [ReconciliationRunRead.model_validate(r) for r in service.list_runs()]


@router.get(
    "/reconciliation/runs/{run_id}/discrepancies",
    response_model=list[ReconciliationDiscrepancyRead],
)
def list_reconciliation_discrepancies(
    run_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> list[ReconciliationDiscrepancyRead]:
    try:
        service.get_run(run_id)
        return [
            ReconciliationDiscrepancyRead.model_validate(d)
            for d in service.list_discrepancies(run_id)
        ]
    except ReconciliationError as exc:
        raise _http(exc) from exc


@router.get("/adapters", response_model=list[AdapterRead])
def list_adapters(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MicroLiveService = Depends(get_micro_live_service),
) -> list[AdapterRead]:
    return [AdapterRead.model_validate(p) for p, _health in service.list_adapters()]


@router.post("/dry-run/validate-order", response_model=DryRunOrderResult)
def dry_run_validate_order(
    body: DryRunOrderValidate,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MicroLiveService = Depends(get_micro_live_service),
) -> DryRunOrderResult:
    result = service.dry_run_validate_order(
        quantity=body.quantity, reference_price=body.reference_price
    )
    return DryRunOrderResult.model_validate(result)
