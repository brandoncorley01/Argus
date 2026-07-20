"""Paper trading HTTP API (Phase 12)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import RequireAnyAuthenticatedRead, RequireFounder, RequireFounderOrOperator
from app.db.session import get_db
from app.schemas.paper import (
    CheckpointRead,
    FillRead,
    KillSwitchRequest,
    OrderRead,
    OrderSubmit,
    PortfolioCreate,
    PortfolioRead,
    PositionRead,
    ProviderHealthRead,
    ProviderRead,
    ProviderWithHealth,
    ReportCreate,
    ReportRead,
    RiskBreachRead,
    RiskLimitCreate,
    RiskLimitRead,
    SessionCreate,
    SessionRead,
)
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.paper_trading_service import PaperTradingError, PaperTradingService

router = APIRouter(prefix="/api/v1/paper", tags=["paper-trading"])

_ERROR_STATUS = {
    "provider_missing": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "provider_not_found": status.HTTP_404_NOT_FOUND,
    "portfolio_not_found": status.HTTP_404_NOT_FOUND,
    "session_not_found": status.HTTP_404_NOT_FOUND,
    "session_invalid": status.HTTP_400_BAD_REQUEST,
    "order_not_found": status.HTTP_404_NOT_FOUND,
    "risk_blocked": status.HTTP_400_BAD_REQUEST,
    "kill_switch": status.HTTP_403_FORBIDDEN,
    "live_execution_forbidden": status.HTTP_403_FORBIDDEN,
    "short_forbidden": status.HTTP_400_BAD_REQUEST,
    "insufficient_buying_power": status.HTTP_400_BAD_REQUEST,
    "portfolio_inactive": status.HTTP_400_BAD_REQUEST,
}


def get_service(db: Session = Depends(get_db)) -> PaperTradingService:
    return PaperTradingService(db)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, PaperTradingError):
        return HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, 400),
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(status_code=500, detail="Unexpected error")


@router.get("/providers", response_model=list[ProviderWithHealth])
def list_providers(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTradingService = Depends(get_service),
) -> list[ProviderWithHealth]:
    return [
        ProviderWithHealth(
            provider=ProviderRead.model_validate(p),
            health=ProviderHealthRead.model_validate(h) if h else None,
        )
        for p, h in service.list_providers()
    ]


@router.post("/portfolios", response_model=PortfolioRead, status_code=201)
def create_portfolio(
    body: PortfolioCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: PaperTradingService = Depends(get_service),
) -> PortfolioRead:
    try:
        row = service.create_portfolio(
            name=body.name,
            initial_cash=body.initial_cash,
            currency=body.currency,
            actor=principal,
        )
    except PaperTradingError as exc:
        raise _http(exc) from exc
    return PortfolioRead.model_validate(row)


@router.get("/portfolios", response_model=list[PortfolioRead])
def list_portfolios(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTradingService = Depends(get_service),
) -> list[PortfolioRead]:
    return [PortfolioRead.model_validate(p) for p in service.list_portfolios()]


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioRead)
def get_portfolio(
    portfolio_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTradingService = Depends(get_service),
) -> PortfolioRead:
    try:
        return PortfolioRead.model_validate(service.get_portfolio(portfolio_id))
    except PaperTradingError as exc:
        raise _http(exc) from exc


@router.post("/portfolios/{portfolio_id}/kill-switch", response_model=PortfolioRead)
def kill_switch(
    portfolio_id: uuid.UUID,
    body: KillSwitchRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: PaperTradingService = Depends(get_service),
) -> PortfolioRead:
    try:
        return PortfolioRead.model_validate(
            service.set_kill_switch(portfolio_id, active=body.active, actor=principal)
        )
    except PaperTradingError as exc:
        raise _http(exc) from exc


@router.post(
    "/portfolios/{portfolio_id}/sessions",
    response_model=SessionRead,
    status_code=201,
)
def open_session(
    portfolio_id: uuid.UUID,
    body: SessionCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: PaperTradingService = Depends(get_service),
) -> SessionRead:
    try:
        return SessionRead.model_validate(
            service.open_session(
                portfolio_id=portfolio_id,
                actor=principal,
                strategy_version_id=body.strategy_version_id,
                seed=body.seed,
                assumptions=body.assumptions,
            )
        )
    except PaperTradingError as exc:
        raise _http(exc) from exc


@router.get("/portfolios/{portfolio_id}/sessions", response_model=list[SessionRead])
def list_sessions(
    portfolio_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTradingService = Depends(get_service),
) -> list[SessionRead]:
    return [SessionRead.model_validate(s) for s in service.list_sessions(portfolio_id)]


@router.post("/portfolios/{portfolio_id}/orders", response_model=OrderRead)
def submit_order(
    portfolio_id: uuid.UUID,
    body: OrderSubmit,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: PaperTradingService = Depends(get_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> OrderRead:
    try:
        return OrderRead.model_validate(
            service.submit_order(
                portfolio_id=portfolio_id,
                symbol=body.symbol,
                side=body.side,
                order_type=body.order_type,
                quantity=body.quantity,
                limit_price=body.limit_price,
                session_id=body.session_id,
                strategy_version_id=body.strategy_version_id,
                idempotency_key=idempotency_key,
                client_order_id=body.client_order_id,
                actor=principal,
            )
        )
    except PaperTradingError as exc:
        raise _http(exc) from exc


@router.post("/orders/{order_id}/cancel", response_model=OrderRead)
def cancel_order(
    order_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: PaperTradingService = Depends(get_service),
) -> OrderRead:
    try:
        return OrderRead.model_validate(service.cancel_order(order_id, actor=principal))
    except PaperTradingError as exc:
        raise _http(exc) from exc


@router.get("/portfolios/{portfolio_id}/orders", response_model=list[OrderRead])
def list_orders(
    portfolio_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTradingService = Depends(get_service),
) -> list[OrderRead]:
    return [OrderRead.model_validate(o) for o in service.list_orders(portfolio_id)]


@router.get("/portfolios/{portfolio_id}/fills", response_model=list[FillRead])
def list_fills(
    portfolio_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTradingService = Depends(get_service),
) -> list[FillRead]:
    return [FillRead.model_validate(f) for f in service.list_fills(portfolio_id)]


@router.get("/portfolios/{portfolio_id}/positions", response_model=list[PositionRead])
def list_positions(
    portfolio_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTradingService = Depends(get_service),
) -> list[PositionRead]:
    return [PositionRead.model_validate(p) for p in service.list_positions(portfolio_id)]


@router.post(
    "/portfolios/{portfolio_id}/risk-limits",
    response_model=RiskLimitRead,
    status_code=201,
)
def add_risk_limit(
    portfolio_id: uuid.UUID,
    body: RiskLimitCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: PaperTradingService = Depends(get_service),
) -> RiskLimitRead:
    try:
        return RiskLimitRead.model_validate(
            service.add_risk_limit(
                portfolio_id=portfolio_id,
                name=body.name,
                limit_type=body.limit_type,
                threshold=body.threshold,
                symbol=body.symbol,
                actor=principal,
            )
        )
    except PaperTradingError as exc:
        raise _http(exc) from exc


@router.get(
    "/portfolios/{portfolio_id}/risk-limits", response_model=list[RiskLimitRead]
)
def list_risk_limits(
    portfolio_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTradingService = Depends(get_service),
) -> list[RiskLimitRead]:
    return [RiskLimitRead.model_validate(r) for r in service.list_risk_limits(portfolio_id)]


@router.get(
    "/portfolios/{portfolio_id}/risk-breaches", response_model=list[RiskBreachRead]
)
def list_breaches(
    portfolio_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTradingService = Depends(get_service),
) -> list[RiskBreachRead]:
    return [RiskBreachRead.model_validate(b) for b in service.list_breaches(portfolio_id)]


@router.post(
    "/sessions/{session_id}/checkpoints",
    response_model=CheckpointRead,
    status_code=201,
)
def checkpoint(
    session_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: PaperTradingService = Depends(get_service),
) -> CheckpointRead:
    try:
        return CheckpointRead.model_validate(
            service.checkpoint_session(session_id, actor=principal)
        )
    except PaperTradingError as exc:
        raise _http(exc) from exc


@router.post(
    "/portfolios/{portfolio_id}/reports",
    response_model=ReportRead,
    status_code=201,
)
def create_report(
    portfolio_id: uuid.UUID,
    body: ReportCreate,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: PaperTradingService = Depends(get_service),
) -> ReportRead:
    try:
        return ReportRead.model_validate(
            service.generate_report(
                portfolio_id=portfolio_id,
                report_type=body.report_type,
                actor=principal,
            )
        )
    except PaperTradingError as exc:
        raise _http(exc) from exc


@router.get("/portfolios/{portfolio_id}/reports", response_model=list[ReportRead])
def list_reports(
    portfolio_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTradingService = Depends(get_service),
) -> list[ReportRead]:
    return [ReportRead.model_validate(r) for r in service.list_reports(portfolio_id)]
