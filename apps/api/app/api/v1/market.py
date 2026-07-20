"""Market Intelligence HTTP API (Phase 10) — observation only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RequireAnyAuthenticatedRead, RequireFounderOrOperator
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
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.market_intelligence_service import (
    MarketIntelligenceError,
    MarketIntelligenceService,
)

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
