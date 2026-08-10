"""Market Intelligence HTTP API (Phase 10) — observation only."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RequireAnyAuthenticatedRead, RequireFounder, RequireFounderOrOperator
from app.db.session import get_db
from app.schemas.market import (
    EconomicEventRead,
    IngestBatchRequest,
    IngestBatchResponse,
    IngestionRunRead,
    MarketInstrumentCreate,
    MarketInstrumentRead,
    MarketProviderHealthRead,
    MarketProviderRead,
    NewsItemRead,
    ObservationRead,
    OhlcvBarRead,
    ProviderProbeResponse,
    ProviderWithHealthRead,
    QualityFindingRead,
    ResearchItemRead,
)
from app.schemas.market_scan import (
    CockpitSnapshotRead,
    ScanBarsResponse,
    ScanCandidateRead,
    ScanCycleRead,
    ScanEventRead,
    ScanRunResponse,
    ScanStatusRead,
    TeachSignalRequest,
    TeachSignalResponse,
)
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.market_intelligence_service import (
    MarketIntelligenceError,
    MarketIntelligenceService,
)
from app.services.market_scan_service import MarketScanError, MarketScanService

router = APIRouter(prefix="/api/v1/market", tags=["market-intelligence"])

_ERROR_STATUS: dict[str, int] = {
    "provider_not_found": status.HTTP_404_NOT_FOUND,
    "provider_disabled": status.HTTP_400_BAD_REQUEST,
    "provider_misconfigured": status.HTTP_400_BAD_REQUEST,
    "provider_unreachable": status.HTTP_502_BAD_GATEWAY,
    "schema_invalid": status.HTTP_400_BAD_REQUEST,
    "idempotency_conflict": status.HTTP_409_CONFLICT,
}


def get_market_service(db: Session = Depends(get_db)) -> MarketIntelligenceService:
    return MarketIntelligenceService(db)


def get_scan_service(db: Session = Depends(get_db)) -> MarketScanService:
    return MarketScanService(db)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, MarketIntelligenceError):
        return HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": "internal_error", "message": "Unexpected error"},
    )


@router.get("/providers", response_model=list[ProviderWithHealthRead])
def list_providers(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketIntelligenceService = Depends(get_market_service),
) -> list[ProviderWithHealthRead]:
    rows = service.list_providers()
    return [
        ProviderWithHealthRead(
            provider=MarketProviderRead.model_validate(p),
            health=MarketProviderHealthRead.model_validate(h) if h else None,
        )
        for p, h in rows
    ]


@router.post("/providers/{provider_key}/probe", response_model=ProviderProbeResponse)
def probe_provider(
    provider_key: str,
    _: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: MarketIntelligenceService = Depends(get_market_service),
) -> ProviderProbeResponse:
    try:
        result = service.probe_provider(provider_key)
    except MarketIntelligenceError as exc:
        raise _http_error(exc) from exc
    return ProviderProbeResponse(**result)


@router.get("/instruments", response_model=list[MarketInstrumentRead])
def list_instruments(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketIntelligenceService = Depends(get_market_service),
) -> list[MarketInstrumentRead]:
    return [
        MarketInstrumentRead.model_validate(row) for row in service.list_instruments()
    ]


@router.post(
    "/instruments",
    response_model=MarketInstrumentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_instrument(
    body: MarketInstrumentCreate,
    _: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: MarketIntelligenceService = Depends(get_market_service),
) -> MarketInstrumentRead:
    row = service.create_instrument(
        symbol=body.symbol,
        display_name=body.display_name,
        asset_class=body.asset_class,
        base_asset=body.base_asset,
        quote_asset=body.quote_asset,
    )
    return MarketInstrumentRead.model_validate(row)


@router.get("/bars", response_model=list[OhlcvBarRead])
def list_bars(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketIntelligenceService = Depends(get_market_service),
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[OhlcvBarRead]:
    return [
        OhlcvBarRead.model_validate(row)
        for row in service.list_bars(
            symbol=symbol, timeframe=timeframe, limit=limit, offset=offset
        )
    ]


@router.get("/observations", response_model=list[ObservationRead])
def list_observations(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketIntelligenceService = Depends(get_market_service),
    channel: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ObservationRead]:
    return [
        ObservationRead.model_validate(row)
        for row in service.list_observations(channel=channel, limit=limit, offset=offset)
    ]


@router.get("/news", response_model=list[NewsItemRead])
def list_news(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketIntelligenceService = Depends(get_market_service),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[NewsItemRead]:
    return [
        NewsItemRead.model_validate(row)
        for row in service.list_news(limit=limit, offset=offset)
    ]


@router.get("/calendar", response_model=list[EconomicEventRead])
def list_calendar(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketIntelligenceService = Depends(get_market_service),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[EconomicEventRead]:
    return [
        EconomicEventRead.model_validate(row)
        for row in service.list_economic(limit=limit, offset=offset)
    ]


@router.get("/research", response_model=list[ResearchItemRead])
def list_research(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketIntelligenceService = Depends(get_market_service),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ResearchItemRead]:
    return [
        ResearchItemRead.model_validate(row)
        for row in service.list_research(limit=limit, offset=offset)
    ]


@router.get("/ingestion-runs", response_model=list[IngestionRunRead])
def list_runs(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketIntelligenceService = Depends(get_market_service),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[IngestionRunRead]:
    return [
        IngestionRunRead.model_validate(row)
        for row in service.list_runs(limit=limit, offset=offset)
    ]


@router.get("/quality", response_model=list[QualityFindingRead])
def list_quality(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketIntelligenceService = Depends(get_market_service),
    open_only: bool = True,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[QualityFindingRead]:
    return [
        QualityFindingRead.model_validate(row)
        for row in service.list_quality(open_only=open_only, limit=limit)
    ]


@router.post("/ingest", response_model=IngestBatchResponse)
def ingest_batch(
    body: IngestBatchRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: MarketIntelligenceService = Depends(get_market_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestBatchResponse:
    try:
        result = service.ingest_batch(
            body=body,
            actor=principal,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
    except (AuthError, MarketIntelligenceError) as exc:
        raise _http_error(exc) from exc
    return IngestBatchResponse(**result)


@router.post("/prices/refresh")
def refresh_recent_prices(
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Download recent public market candles into Recent Price History (paper practice)."""
    from app.schemas.paper_training import PriceRefreshResponse
    from app.services.market_price_refresh_service import (
        MarketPriceRefreshError,
        MarketPriceRefreshService,
    )

    try:
        result = MarketPriceRefreshService(db).refresh_recent_prices(actor=principal)
    except MarketPriceRefreshError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return PriceRefreshResponse(**result).model_dump(mode="json")


@router.get("/scan/status", response_model=ScanStatusRead)
def scan_status(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketScanService = Depends(get_scan_service),
) -> ScanStatusRead:
    try:
        snap = service.plain_status_summary()
        return ScanStatusRead(
            scanner_state=snap["scanner_state"],
            cycle=ScanCycleRead.model_validate(snap["cycle"]) if snap["cycle"] else None,
            symbols_monitored=snap["symbols_monitored"],
            market_data_at=snap["market_data_at"],
            market_data_age_seconds=snap["market_data_age_seconds"],
            market_data_stale=snap["market_data_stale"],
            pause_new_entries_active=snap["pause_new_entries_active"],
            kill_switch_active=snap["kill_switch_active"],
            trading_allowed=snap["trading_allowed"],
            last_decision=(
                ScanEventRead.model_validate(snap["last_decision"])
                if snap["last_decision"]
                else None
            ),
            pipeline_counts=snap["pipeline_counts"] or {},
            rejection_counts=snap["rejection_counts"] or {},
            next_scheduled_at=snap["next_scheduled_at"],
            worker_note=snap.get("headline") or snap["worker_note"],
            headline=snap.get("headline"),
            watching_count=snap.get("watching_count"),
            rejected_count=snap.get("rejected_count"),
            current_market=snap.get("current_market"),
            scan_progress=snap.get("scan_progress"),
            possible_trades_found=snap.get("possible_trades_found"),
            next_step=snap.get("next_step"),
            top_watching=snap.get("top_watching"),
            market_discovery=snap.get("market_discovery"),
        )
    except Exception as exc:  # noqa: BLE001 — never blank Home on status shape issues
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "scan_status_error", "message": str(exc)[:240]},
        ) from exc


@router.get("/scan/candidates", response_model=list[ScanCandidateRead])
def scan_candidates(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketScanService = Depends(get_scan_service),
    limit: int = Query(default=5, ge=1, le=50),
) -> list[ScanCandidateRead]:
    return [
        ScanCandidateRead.model_validate(row) for row in service.list_candidates(limit=limit)
    ]


@router.get("/scan/cockpit", response_model=CockpitSnapshotRead)
def scan_cockpit(
    portfolio_id: uuid.UUID | None = None,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketScanService = Depends(get_scan_service),
    db: Session = Depends(get_db),
) -> CockpitSnapshotRead:
    """Trading Cockpit snapshot for Home — real markets, watches, and activity.

    Never hard-fails the dashboard: missing training tables or snapshot errors
    return a degraded empty cockpit (HTTP 200) so Home can still render.
    """
    from datetime import UTC, datetime
    from decimal import Decimal

    from sqlalchemy import select

    from app.models.paper_trading import PaperPortfolio
    from app.models.paper_training import PaperTrainingSettings
    from app.services.market_scan_service import (
        CANDIDATE_WATCH_TTL,
        SCAN_INTERVAL,
    )
    from app.services.paper_training_service import PaperTrainingService

    notional = Decimal("100")
    resolved_portfolio_id = portfolio_id
    try:
        if resolved_portfolio_id is None:
            auto = db.scalars(
                select(PaperTrainingSettings.portfolio_id).where(
                    PaperTrainingSettings.mode == "automatic"
                )
            ).first()
            if auto is not None:
                resolved_portfolio_id = auto
            else:
                # Prefer newest portfolio (Founder book) over oldest fixture books.
                newest = db.scalars(
                    select(PaperPortfolio).order_by(PaperPortfolio.created_at.desc())
                ).first()
                if newest is not None:
                    resolved_portfolio_id = newest.id
        if resolved_portfolio_id is not None:
            try:
                settings = PaperTrainingService(db).get_or_create_settings(
                    resolved_portfolio_id
                )
                notional = settings.default_notional
            except Exception:  # noqa: BLE001 — cockpit works without training tables
                db.rollback()
                notional = Decimal("100")
        snap = service.cockpit_snapshot(
            default_notional=notional, portfolio_id=resolved_portfolio_id
        )
        return CockpitSnapshotRead.model_validate(snap)
    except Exception as exc:  # noqa: BLE001 — degraded cockpit, never blank Home
        db.rollback()
        now = datetime.now(UTC)
        return CockpitSnapshotRead.model_validate(
            {
                "generated_at": now,
                "headline": (
                    "Cockpit temporarily unavailable. Start Argus so database "
                    "updates apply, then Refresh recent prices."
                ),
                "scanner_state": "Failed",
                "current_market": None,
                "markets_monitored": 0,
                "scan_progress": {"scanned": 0, "total": 0},
                "next_scan_at": None,
                "possible_trades_found": 0,
                "watching_count": 0,
                "awaiting_confirmation": 0,
                "risk_check_count": 0,
                "open_trades": 0,
                "open_position_symbols": [],
                "focus_symbols": [],
                "market_data_at": None,
                "market_data_stale": True,
                "market_data_age_seconds": None,
                "trading_allowed": False,
                "pause_new_entries_active": False,
                "kill_switch_active": False,
                "next_step": (
                    "Run Start Argus (migrations must succeed), then "
                    "Refresh recent prices on Home."
                ),
                "wall": [],
                "watches": [],
                "monitor": [],
                "doing": [
                    {
                        "text": f"Cockpit could not load: {str(exc)[:160]}",
                        "tone": "warn",
                    }
                ],
                "decided": [],
                "scan_interval_seconds": int(SCAN_INTERVAL.total_seconds()),
                "watch_ttl_seconds": int(CANDIDATE_WATCH_TTL.total_seconds()),
            }
        )


@router.get("/scan/events", response_model=list[ScanEventRead])
def scan_events(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketScanService = Depends(get_scan_service),
    limit: int = Query(default=40, ge=1, le=200),
) -> list[ScanEventRead]:
    return [ScanEventRead.model_validate(row) for row in service.list_events(limit=limit)]


@router.get("/scan/bars/{symbol}", response_model=ScanBarsResponse)
def scan_bars(
    symbol: str,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: MarketScanService = Depends(get_scan_service),
    limit: int = Query(default=60, ge=1, le=200),
) -> ScanBarsResponse:
    return ScanBarsResponse.model_validate(service.bars_for_symbol(symbol, limit=limit))


@router.post("/scan/run", response_model=ScanRunResponse)
def run_scan(
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: MarketScanService = Depends(get_scan_service),
    db: Session = Depends(get_db),
    force: bool = Query(default=False),
) -> ScanRunResponse:
    try:
        cycle = service.run_scan_cycle(force=force)
    except MarketScanError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    # Automatic Practice may open paper trades after a successful scan (paper only).
    # Failures are audited; scan response still returns.
    try:
        from app.services.paper_training_service import PaperTrainingService
        from app.services.trading_intelligence_service import TradingIntelligenceService

        training = PaperTrainingService(db)
        for portfolio_id in training.iter_automation_portfolio_ids():
            training.evaluate_paper_exits(
                portfolio_id=portfolio_id, actor=principal
            )
            training.maybe_auto_enter_from_scan(
                portfolio_id=portfolio_id, actor=principal
            )
        try:
            TradingIntelligenceService(db).resolve_pending_misses()
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001 — never fail the scan response on auto-enter
        try:
            AuditService(db).append(
                action="paper.training.post_scan_automation_failed",
                resource_type="market_scan_cycle",
                resource_id=str(cycle.id),
                actor_user_id=principal.user.id,
                payload={"error": str(exc)[:240]},
            )
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    return ScanRunResponse(cycle=ScanCycleRead.model_validate(service._cycle_dict(cycle)))


@router.post("/scan/teach", response_model=TeachSignalResponse)
def teach_scan(
    body: TeachSignalRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: MarketScanService = Depends(get_scan_service),
    db: Session = Depends(get_db),
) -> TeachSignalResponse:
    """Paper teaching signal — records Founder preference; never places orders."""
    try:
        event = service.record_teaching_signal(
            symbol=body.symbol,
            signal=body.signal,
            actor_user_id=principal.user.id,
            candidate_id=body.candidate_id,
            note=body.note,
        )
        AuditService(db).append(
            action="market.scan.teach",
            resource_type="market_scan_event",
            resource_id=str(event.id),
            actor_user_id=principal.user.id,
            payload={
                "signal": body.signal,
                "symbol": body.symbol.upper(),
                "candidate_id": str(body.candidate_id) if body.candidate_id else None,
            },
        )
        db.commit()
    except MarketScanError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return TeachSignalResponse(
        ok=True,
        message="Teaching note saved. Argus did not place a trade.",
        event_id=event.id,
    )
