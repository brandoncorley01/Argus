"""Treasury and Executive Analytics HTTP API (Phase 14).

No endpoint in this router can execute a real external transfer or
represent simulated capital as real capital. ``POST .../execute`` always
returns 403 with code ``external_transfer_execution_forbidden``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import RequireAnyAuthenticatedRead, RequireFounder, RequireFounderOrOperator
from app.db.session import get_db
from app.schemas.treasury import (
    AttributionSnapshotGenerate,
    AttributionSnapshotRead,
    CapitalAllocationRead,
    CapitalAllocationReject,
    CapitalAllocationRequest,
    CapitalPoolCreate,
    CapitalPoolRead,
    CapitalReservationRead,
    ExecutiveKpiSnapshotRead,
    ExternalTransferCancel,
    ExternalTransferCreate,
    ExternalTransferInstructionRead,
    ForecastScenarioCreate,
    ForecastScenarioRead,
    InstitutionalReportGenerate,
    InstitutionalReportRead,
    TreasuryAccountCreate,
    TreasuryAccountFundRequest,
    TreasuryAccountRead,
    TreasuryLedgerEntryRead,
    TreasurySummaryRead,
)
from app.services.attribution_service import AttributionError, AttributionService
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.executive_analytics_service import ExecutiveAnalyticsService
from app.services.forecasting_service import ForecastingError, ForecastingService
from app.services.treasury_reporting_service import TreasuryReportingError, TreasuryReportingService
from app.services.treasury_service import TreasuryError, TreasuryService

router = APIRouter(prefix="/api/v1/treasury", tags=["treasury"])

_ERROR_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "duplicate_name": status.HTTP_400_BAD_REQUEST,
    "invalid_classification": status.HTTP_400_BAD_REQUEST,
    "invalid_amount": status.HTTP_400_BAD_REQUEST,
    "invalid_target_type": status.HTTP_400_BAD_REQUEST,
    "invalid_limit": status.HTTP_400_BAD_REQUEST,
    "invalid_state": status.HTTP_400_BAD_REQUEST,
    "insufficient_balance": status.HTTP_400_BAD_REQUEST,
    "corrupt_state": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "invalid_direction": status.HTTP_400_BAD_REQUEST,
    "external_transfer_execution_forbidden": status.HTTP_403_FORBIDDEN,
    "invalid_scope": status.HTTP_400_BAD_REQUEST,
    "invalid_environment_class": status.HTTP_400_BAD_REQUEST,
    "invalid_scenario_type": status.HTTP_400_BAD_REQUEST,
    "missing_input": status.HTTP_400_BAD_REQUEST,
    "invalid_input": status.HTTP_400_BAD_REQUEST,
    "invalid_report_type": status.HTTP_400_BAD_REQUEST,
}


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(
        exc, (TreasuryError, AttributionError, ForecastingError, TreasuryReportingError)
    ):
        return HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, 400),
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(status_code=500, detail="Unexpected error")


def get_treasury_service(db: Session = Depends(get_db)) -> TreasuryService:
    return TreasuryService(db)


def get_attribution_service(db: Session = Depends(get_db)) -> AttributionService:
    return AttributionService(db)


def get_analytics_service(db: Session = Depends(get_db)) -> ExecutiveAnalyticsService:
    return ExecutiveAnalyticsService(db)


def get_forecasting_service(db: Session = Depends(get_db)) -> ForecastingService:
    return ForecastingService(db)


def get_reporting_service(db: Session = Depends(get_db)) -> TreasuryReportingService:
    return TreasuryReportingService(db)


# --- accounts ----------------------------------------------------------------


@router.get("/accounts", response_model=list[TreasuryAccountRead])
def list_accounts(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: TreasuryService = Depends(get_treasury_service),
) -> list[TreasuryAccountRead]:
    return [TreasuryAccountRead.model_validate(a) for a in service.list_accounts()]


@router.post("/accounts", response_model=TreasuryAccountRead, status_code=201)
def create_account(
    body: TreasuryAccountCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> TreasuryAccountRead:
    try:
        row = service.create_account(
            name=body.name,
            currency=body.currency,
            classification=body.classification,
            description=body.description,
            actor=principal,
        )
        return TreasuryAccountRead.model_validate(row)
    except TreasuryError as exc:
        raise _http(exc) from exc


@router.get("/accounts/{account_id}", response_model=TreasuryAccountRead)
def get_account(
    account_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: TreasuryService = Depends(get_treasury_service),
) -> TreasuryAccountRead:
    try:
        return TreasuryAccountRead.model_validate(service.get_account(account_id))
    except TreasuryError as exc:
        raise _http(exc) from exc


@router.post("/accounts/{account_id}/fund-simulated", response_model=TreasuryAccountRead)
def fund_account_simulated(
    account_id: uuid.UUID,
    body: TreasuryAccountFundRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> TreasuryAccountRead:
    try:
        row = service.fund_account_simulated(
            account_id, amount=body.amount, note=body.note, actor=principal
        )
        return TreasuryAccountRead.model_validate(row)
    except TreasuryError as exc:
        raise _http(exc) from exc


# --- pools ---------------------------------------------------------------------


@router.get("/pools", response_model=list[CapitalPoolRead])
def list_pools(
    account_id: uuid.UUID | None = None,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: TreasuryService = Depends(get_treasury_service),
) -> list[CapitalPoolRead]:
    return [CapitalPoolRead.model_validate(p) for p in service.list_pools(account_id)]


@router.post("/pools", response_model=CapitalPoolRead, status_code=201)
def create_pool(
    body: CapitalPoolCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> CapitalPoolRead:
    try:
        row = service.create_pool(
            account_id=body.account_id, name=body.name, pool_type=body.pool_type, actor=principal
        )
        return CapitalPoolRead.model_validate(row)
    except TreasuryError as exc:
        raise _http(exc) from exc


# --- allocations -----------------------------------------------------------------


@router.get("/allocations", response_model=list[CapitalAllocationRead])
def list_allocations(
    pool_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: TreasuryService = Depends(get_treasury_service),
) -> list[CapitalAllocationRead]:
    return [
        CapitalAllocationRead.model_validate(a)
        for a in service.list_allocations(pool_id=pool_id, status=status_filter)
    ]


@router.post("/allocations", response_model=CapitalAllocationRead, status_code=201)
def request_allocation(
    body: CapitalAllocationRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> CapitalAllocationRead:
    try:
        row = service.request_allocation(
            pool_id=body.pool_id,
            target_type=body.target_type,
            target_id=body.target_id,
            amount=body.amount,
            max_amount=body.max_amount,
            notes=body.notes,
            actor=principal,
        )
        return CapitalAllocationRead.model_validate(row)
    except TreasuryError as exc:
        raise _http(exc) from exc


@router.get("/allocations/{allocation_id}", response_model=CapitalAllocationRead)
def get_allocation(
    allocation_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: TreasuryService = Depends(get_treasury_service),
) -> CapitalAllocationRead:
    try:
        return CapitalAllocationRead.model_validate(service.get_allocation(allocation_id))
    except TreasuryError as exc:
        raise _http(exc) from exc


@router.post("/allocations/{allocation_id}/approve", response_model=CapitalAllocationRead)
def approve_allocation(
    allocation_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> CapitalAllocationRead:
    try:
        return CapitalAllocationRead.model_validate(
            service.approve_allocation(allocation_id, actor=principal)
        )
    except TreasuryError as exc:
        raise _http(exc) from exc


@router.post("/allocations/{allocation_id}/reject", response_model=CapitalAllocationRead)
def reject_allocation(
    allocation_id: uuid.UUID,
    body: CapitalAllocationReject,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> CapitalAllocationRead:
    try:
        return CapitalAllocationRead.model_validate(
            service.reject_allocation(allocation_id, reason=body.reason, actor=principal)
        )
    except TreasuryError as exc:
        raise _http(exc) from exc


@router.post("/allocations/{allocation_id}/reserve", response_model=CapitalAllocationRead)
def reserve_allocation(
    allocation_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> CapitalAllocationRead:
    try:
        return CapitalAllocationRead.model_validate(
            service.reserve_allocation(allocation_id, actor=principal)
        )
    except TreasuryError as exc:
        raise _http(exc) from exc


@router.post("/allocations/{allocation_id}/release", response_model=CapitalAllocationRead)
def release_allocation(
    allocation_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> CapitalAllocationRead:
    try:
        return CapitalAllocationRead.model_validate(
            service.release_allocation(allocation_id, actor=principal)
        )
    except TreasuryError as exc:
        raise _http(exc) from exc


# --- reservations (read) ----------------------------------------------------------


@router.get("/reservations", response_model=list[CapitalReservationRead])
def list_reservations(
    allocation_id: uuid.UUID | None = None,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: TreasuryService = Depends(get_treasury_service),
) -> list[CapitalReservationRead]:
    return [
        CapitalReservationRead.model_validate(r)
        for r in service.list_reservations(allocation_id)
    ]


# --- ledger (read) -----------------------------------------------------------------


@router.get("/ledger", response_model=list[TreasuryLedgerEntryRead])
def list_ledger_entries(
    account_id: uuid.UUID | None = None,
    limit: int = 100,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: TreasuryService = Depends(get_treasury_service),
) -> list[TreasuryLedgerEntryRead]:
    return [
        TreasuryLedgerEntryRead.model_validate(e)
        for e in service.list_ledger_entries(account_id=account_id, limit=limit)
    ]


# --- external transfers (never executed) --------------------------------------------


@router.get("/external-transfers", response_model=list[ExternalTransferInstructionRead])
def list_external_transfers(
    account_id: uuid.UUID | None = None,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: TreasuryService = Depends(get_treasury_service),
) -> list[ExternalTransferInstructionRead]:
    return [
        ExternalTransferInstructionRead.model_validate(t)
        for t in service.list_external_transfers(account_id=account_id)
    ]


@router.post("/external-transfers", response_model=ExternalTransferInstructionRead, status_code=201)
def create_external_transfer(
    body: ExternalTransferCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> ExternalTransferInstructionRead:
    try:
        row = service.create_external_transfer(
            account_id=body.account_id,
            direction=body.direction,
            amount=body.amount,
            currency=body.currency,
            destination_reference=body.destination_reference,
            actor=principal,
        )
        return ExternalTransferInstructionRead.model_validate(row)
    except TreasuryError as exc:
        raise _http(exc) from exc


@router.get("/external-transfers/{instruction_id}", response_model=ExternalTransferInstructionRead)
def get_external_transfer(
    instruction_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: TreasuryService = Depends(get_treasury_service),
) -> ExternalTransferInstructionRead:
    try:
        return ExternalTransferInstructionRead.model_validate(
            service.get_external_transfer(instruction_id)
        )
    except TreasuryError as exc:
        raise _http(exc) from exc


@router.post(
    "/external-transfers/{instruction_id}/propose", response_model=ExternalTransferInstructionRead
)
def propose_external_transfer(
    instruction_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> ExternalTransferInstructionRead:
    try:
        return ExternalTransferInstructionRead.model_validate(
            service.propose_external_transfer(instruction_id, actor=principal)
        )
    except TreasuryError as exc:
        raise _http(exc) from exc


@router.post(
    "/external-transfers/{instruction_id}/cancel", response_model=ExternalTransferInstructionRead
)
def cancel_external_transfer(
    instruction_id: uuid.UUID,
    body: ExternalTransferCancel,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> ExternalTransferInstructionRead:
    try:
        return ExternalTransferInstructionRead.model_validate(
            service.cancel_external_transfer(instruction_id, reason=body.reason, actor=principal)
        )
    except TreasuryError as exc:
        raise _http(exc) from exc


@router.post("/external-transfers/{instruction_id}/execute")
def execute_external_transfer(
    instruction_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: TreasuryService = Depends(get_treasury_service),
) -> None:
    """Always forbidden. There is no code path that returns success here."""
    try:
        service.attempt_execute_transfer(instruction_id, actor=principal)
    except TreasuryError as exc:
        raise _http(exc) from exc
    raise HTTPException(status_code=500, detail="Unreachable — execution must always be forbidden")


# --- attribution -------------------------------------------------------------------


@router.get("/attribution", response_model=list[AttributionSnapshotRead])
def list_attribution_snapshots(
    scope: str | None = None,
    environment_class: str | None = None,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: AttributionService = Depends(get_attribution_service),
) -> list[AttributionSnapshotRead]:
    return [
        AttributionSnapshotRead.model_validate(s)
        for s in service.list_snapshots(scope=scope, environment_class=environment_class)
    ]


@router.post("/attribution/generate", response_model=AttributionSnapshotRead, status_code=201)
def generate_attribution_snapshot(
    body: AttributionSnapshotGenerate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: AttributionService = Depends(get_attribution_service),
) -> AttributionSnapshotRead:
    try:
        row = service.generate_snapshot(
            scope=body.scope,
            scope_ref=body.scope_ref,
            environment_class=body.environment_class,
            actor=principal,
        )
        return AttributionSnapshotRead.model_validate(row)
    except AttributionError as exc:
        raise _http(exc) from exc


# --- KPIs ------------------------------------------------------------------------------


@router.get("/kpis", response_model=list[ExecutiveKpiSnapshotRead])
def list_kpis(
    kpi_key: str | None = None,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: ExecutiveAnalyticsService = Depends(get_analytics_service),
) -> list[ExecutiveKpiSnapshotRead]:
    return [ExecutiveKpiSnapshotRead.model_validate(k) for k in service.list_kpis(kpi_key=kpi_key)]


@router.post("/kpis/generate", response_model=list[ExecutiveKpiSnapshotRead], status_code=201)
def generate_kpis(
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: ExecutiveAnalyticsService = Depends(get_analytics_service),
) -> list[ExecutiveKpiSnapshotRead]:
    rows = service.generate_snapshots(actor=principal)
    return [ExecutiveKpiSnapshotRead.model_validate(r) for r in rows]


# --- forecasts ---------------------------------------------------------------------------


@router.get("/forecasts", response_model=list[ForecastScenarioRead])
def list_forecasts(
    scenario_type: str | None = None,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: ForecastingService = Depends(get_forecasting_service),
) -> list[ForecastScenarioRead]:
    return [
        ForecastScenarioRead.model_validate(s)
        for s in service.list_scenarios(scenario_type=scenario_type)
    ]


@router.post("/forecasts", response_model=ForecastScenarioRead, status_code=201)
def create_forecast(
    body: ForecastScenarioCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: ForecastingService = Depends(get_forecasting_service),
) -> ForecastScenarioRead:
    try:
        row = service.create_scenario(
            name=body.name, scenario_type=body.scenario_type, inputs=body.inputs, actor=principal
        )
        return ForecastScenarioRead.model_validate(row)
    except ForecastingError as exc:
        raise _http(exc) from exc


# --- reports -----------------------------------------------------------------------------


@router.get("/reports", response_model=list[InstitutionalReportRead])
def list_reports(
    report_type: str | None = None,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: TreasuryReportingService = Depends(get_reporting_service),
) -> list[InstitutionalReportRead]:
    rows = service.list_reports(report_type=report_type)
    return [InstitutionalReportRead.model_validate(r) for r in rows]


@router.post("/reports/generate", response_model=InstitutionalReportRead, status_code=201)
def generate_report(
    body: InstitutionalReportGenerate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: TreasuryReportingService = Depends(get_reporting_service),
) -> InstitutionalReportRead:
    try:
        row = service.generate_report(report_type=body.report_type, actor=principal)
        return InstitutionalReportRead.model_validate(row)
    except TreasuryReportingError as exc:
        raise _http(exc) from exc


@router.get("/reports/{report_id}", response_model=InstitutionalReportRead)
def get_report(
    report_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: TreasuryReportingService = Depends(get_reporting_service),
) -> InstitutionalReportRead:
    try:
        return InstitutionalReportRead.model_validate(service.get_report(report_id))
    except TreasuryReportingError as exc:
        raise _http(exc) from exc


# --- executive summary -----------------------------------------------------------------


@router.get("/summary", response_model=TreasurySummaryRead)
def get_summary(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    treasury: TreasuryService = Depends(get_treasury_service),
    analytics: ExecutiveAnalyticsService = Depends(get_analytics_service),
    attribution: AttributionService = Depends(get_attribution_service),
    reporting: TreasuryReportingService = Depends(get_reporting_service),
) -> TreasurySummaryRead:
    accounts = treasury.list_accounts()
    allocations = treasury.list_allocations()
    transfers = treasury.list_external_transfers()
    total_balance = sum((a.balance for a in accounts), Decimal("0"))

    allocation_counts: dict[str, int] = {}
    for a in allocations:
        allocation_counts[a.status] = allocation_counts.get(a.status, 0) + 1
    transfer_counts: dict[str, int] = {}
    for t in transfers:
        transfer_counts[t.status] = transfer_counts.get(t.status, 0) + 1

    latest_kpis = analytics.latest_kpis()
    latest_paper_attribution = attribution.list_snapshots(environment_class="paper", limit=10)
    reports = reporting.list_reports()
    latest_report = reports[0] if reports else None

    return TreasurySummaryRead(
        disclaimer=(
            "All balances and KPIs below represent SIMULATED / INTERNAL PAPER "
            "capital only. No real money is held, allocated, or transferable. "
            "Live performance is never combined with paper performance."
        ),
        total_simulated_balance=str(total_balance),
        account_count=len(accounts),
        allocation_status_counts=allocation_counts,
        external_transfer_status_counts=transfer_counts,
        external_transfer_executed_count=0,
        latest_kpis=[ExecutiveKpiSnapshotRead.model_validate(k) for k in latest_kpis],
        latest_paper_attribution=[
            AttributionSnapshotRead.model_validate(s) for s in latest_paper_attribution
        ],
        live_available=False,
        live_unavailable_reason=(
            "Live trading has no reachable activation path in this system "
            "(see ADR-029). No live performance data exists to summarize."
        ),
        latest_report=(
            InstitutionalReportRead.model_validate(latest_report) if latest_report else None
        ),
    )
