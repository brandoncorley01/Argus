"""Operational Validation HTTP API (Phase 15).

Read-only System Health dashboard, an append-only operational event log,
on-demand host metrics capture, and immutable daily paper-ops reports. This
router does not add any new external service integration, trading logic, or
live-trading capability — it observes and reports on existing subsystems.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequireAnyAuthenticatedRead, RequireFounderOrOperator
from app.db.session import get_db
from app.middleware.correlation import get_correlation_id
from app.models.operations import OperationalComponent, OperationalSeverity
from app.schemas.operations import (
    DailyTradingReportGenerateRequest,
    DailyTradingReportRead,
    HostResourceSnapshotRead,
    OperationalEventCreateRequest,
    OperationalEventRead,
    SystemHealthRead,
)
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.daily_trading_report_service import (
    DailyTradingReportError,
    DailyTradingReportService,
)
from app.services.host_metrics_service import HostMetricsService
from app.services.operational_log_service import OperationalLogError, OperationalLogService
from app.services.system_health_service import SystemHealthService

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])

_ERROR_STATUS: dict[str, int] = {
    "invalid_component": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "invalid_severity": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "invalid_description": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "invalid_correlation_id": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "secret_detected": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "report_immutable": status.HTTP_409_CONFLICT,
}


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, (OperationalLogError, DailyTradingReportError)):
        return HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": "internal_error", "message": "Unexpected error"},
    )


def get_system_health_service(db: Session = Depends(get_db)) -> SystemHealthService:
    return SystemHealthService(db)


def get_operational_log_service(db: Session = Depends(get_db)) -> OperationalLogService:
    return OperationalLogService(db)


def get_host_metrics_service(db: Session = Depends(get_db)) -> HostMetricsService:
    return HostMetricsService(db)


def get_daily_report_service(db: Session = Depends(get_db)) -> DailyTradingReportService:
    return DailyTradingReportService(db)


# --- system health ------------------------------------------------------------


@router.get("/system-health", response_model=SystemHealthRead)
def get_system_health(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: SystemHealthService = Depends(get_system_health_service),
) -> SystemHealthRead:
    return SystemHealthRead(**service.build())


# --- operational events --------------------------------------------------------


@router.get("/events", response_model=list[OperationalEventRead])
def list_events(
    severity: OperationalSeverity | None = Query(default=None),
    component: OperationalComponent | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: OperationalLogService = Depends(get_operational_log_service),
) -> list[OperationalEventRead]:
    rows = service.list_events(severity=severity, component=component, limit=limit, offset=offset)
    return [OperationalEventRead.model_validate(row) for row in rows]


@router.post("/events", response_model=OperationalEventRead, status_code=201)
def create_event(
    body: OperationalEventCreateRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: OperationalLogService = Depends(get_operational_log_service),
    correlation_header: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> OperationalEventRead:
    correlation_id = body.correlation_id or correlation_header or get_correlation_id()
    try:
        row = service.append(
            component=body.component,
            severity=body.severity,
            description=body.description,
            correlation_id=correlation_id,
            details=body.details,
            actor_user_id=principal.user.id,
        )
    except OperationalLogError as exc:
        raise _http_error(exc) from exc
    return OperationalEventRead.model_validate(row)


# --- host metrics --------------------------------------------------------------


@router.post("/host-metrics/capture", response_model=HostResourceSnapshotRead, status_code=201)
def capture_host_metrics(
    _: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: HostMetricsService = Depends(get_host_metrics_service),
) -> HostResourceSnapshotRead:
    snapshot = service.capture()
    return HostResourceSnapshotRead.model_validate(snapshot)


@router.get("/host-metrics/latest", response_model=HostResourceSnapshotRead | None)
def get_latest_host_metrics(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: HostMetricsService = Depends(get_host_metrics_service),
) -> HostResourceSnapshotRead | None:
    snapshot = service.latest()
    if snapshot is None:
        return None
    return HostResourceSnapshotRead.model_validate(snapshot)


# --- daily trading reports ------------------------------------------------------


@router.get("/daily-reports", response_model=list[DailyTradingReportRead])
def list_daily_reports(
    limit: int = Query(default=60, ge=1, le=365),
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: DailyTradingReportService = Depends(get_daily_report_service),
) -> list[DailyTradingReportRead]:
    rows = service.list_reports(limit=limit)
    return [DailyTradingReportRead.model_validate(row) for row in rows]


@router.get("/daily-reports/{report_date}", response_model=DailyTradingReportRead)
def get_daily_report(
    report_date: date,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: DailyTradingReportService = Depends(get_daily_report_service),
) -> DailyTradingReportRead:
    row = service.get_report(report_date)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "report_not_found",
                "message": f"No daily trading report exists for {report_date.isoformat()}",
            },
        )
    return DailyTradingReportRead.model_validate(row)


@router.post("/daily-reports/generate", response_model=DailyTradingReportRead, status_code=201)
def generate_daily_report(
    body: DailyTradingReportGenerateRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: DailyTradingReportService = Depends(get_daily_report_service),
) -> DailyTradingReportRead:
    target_date = body.report_date or (datetime.now(UTC) - timedelta(days=1)).date()
    try:
        row = service.generate(report_date=target_date, actor=principal)
    except DailyTradingReportError as exc:
        raise _http_error(exc) from exc
    return DailyTradingReportRead.model_validate(row)


# --- trading intelligence (observational; never enables live) -------------------


@router.get("/trading-intelligence/briefing")
def trading_intelligence_briefing(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.trading_intelligence_service import TradingIntelligenceService

    try:
        return TradingIntelligenceService(db).founder_briefing()
    except Exception as exc:  # noqa: BLE001 — never blank Home
        return {
            "bullets": [
                "Average confidence: —",
                "Best strategy today: —",
                "Largest risk: —",
                "Largest missed opportunity: —",
                "Recommendation: Start Argus so intelligence tables migrate",
            ],
            "error": str(exc)[:160],
            "generated_at": datetime.now(UTC).isoformat(),
        }


@router.get("/trading-intelligence/certification")
def trading_intelligence_certification(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.trading_intelligence_service import TradingIntelligenceService

    return TradingIntelligenceService(db).certification_progress()


@router.get("/trading-intelligence/learning")
def trading_intelligence_learning(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.trading_intelligence_service import TradingIntelligenceService

    return TradingIntelligenceService(db).learning_summary()


@router.get("/trading-intelligence/watchlist")
def trading_intelligence_watchlist(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.trading_intelligence_service import TradingIntelligenceService

    return TradingIntelligenceService(db).watchlist_intelligence()


@router.get("/trading-intelligence/mission")
def trading_intelligence_mission(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.trading_intelligence_service import TradingIntelligenceService

    return TradingIntelligenceService(db).morning_mission()


@router.get("/trading-intelligence/debrief")
def trading_intelligence_debrief(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.trading_intelligence_service import TradingIntelligenceService

    return TradingIntelligenceService(db).mission_debrief()


@router.get("/trading-intelligence/case-files/{candidate_id}")
def trading_intelligence_case_file(
    candidate_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.trading_intelligence_service import TradingIntelligenceService

    row = TradingIntelligenceService(db).case_file(candidate_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case file not found")
    return row


@router.get("/trading-intelligence/advanced-learning")
def trading_intelligence_advanced_learning(
    portfolio_id: uuid.UUID | None = None,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> dict:
    """Advanced 20-day PAPER learning pane. Never enables live trading."""
    from app.models.paper_trading import PaperPortfolio
    from app.services.advanced_learning_service import AdvancedLearningService

    pid = portfolio_id
    if pid is None:
        row = db.scalar(select(PaperPortfolio).limit(1))
        if row is None:
            return {
                "error": "no_paper_portfolio",
                "live_trading_enabled": False,
                "disclaimer": "Create a paper portfolio to begin advanced learning.",
            }
        pid = row.id
    try:
        return AdvancedLearningService(db).pane(pid)
    except Exception as exc:  # noqa: BLE001 — never blank Training
        return {
            "error": str(exc)[:200],
            "live_trading_enabled": False,
            "learning_day": 1,
            "required_days": 20,
            "disclaimer": "Advanced learning unavailable until migrations and worker are healthy.",
        }


@router.get("/trading-intelligence/advanced-learning/readiness-report")
def trading_intelligence_readiness_report(
    portfolio_id: uuid.UUID | None = None,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> dict:
    from app.models.paper_trading import PaperPortfolio
    from app.services.advanced_learning_service import AdvancedLearningService

    pid = portfolio_id
    if pid is None:
        row = db.scalar(select(PaperPortfolio).limit(1))
        if row is None:
            raise HTTPException(status_code=404, detail="No paper portfolio")
        pid = row.id
    report = AdvancedLearningService(db).readiness_report(pid)
    if report is None:
        return {
            "ready": False,
            "live_trading_enabled": False,
            "message": "Readiness report generates after Learning Day 20 with stored evidence.",
        }
    return report


@router.post("/trading-intelligence/advanced-learning/evaluate")
def trading_intelligence_evaluate_learning(
    portfolio_id: uuid.UUID | None = None,
    _: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    db: Session = Depends(get_db),
) -> dict:
    from app.models.paper_trading import PaperPortfolio
    from app.services.advanced_learning_service import AdvancedLearningService

    pid = portfolio_id
    if pid is None:
        row = db.scalar(select(PaperPortfolio).limit(1))
        if row is None:
            raise HTTPException(status_code=404, detail="No paper portfolio")
        pid = row.id
    return AdvancedLearningService(db).evaluate_cycle(pid)