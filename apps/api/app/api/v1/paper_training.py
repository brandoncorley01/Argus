"""Paper Training Lab HTTP API — paper practice only; never unlocks live."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import RequireAnyAuthenticatedRead, RequireFounder, RequireFounderOrOperator
from app.db.session import get_db
from app.schemas.paper import PortfolioRead
from app.schemas.paper_training import (
    CandleReadinessRow,
    CoachingActionRequest,
    CoachingActionResponse,
    FeedbackRead,
    FeedbackRequest,
    FounderCandidateRead,
    ScorecardRead,
    TrainingSettingsRead,
    TrainingSettingsUpdate,
)
from app.services.auth_service import AuthenticatedPrincipal, AuthError
from app.services.market_scan_service import MarketScanService
from app.services.paper_training_service import PaperTrainingError, PaperTrainingService

router = APIRouter(prefix="/api/v1/paper/training", tags=["paper-training"])


def get_service(db: Session = Depends(get_db)) -> PaperTrainingService:
    return PaperTrainingService(db)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, PaperTrainingError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(status_code=500, detail="Unexpected error")


@router.get("/readiness", response_model=list[CandleReadinessRow])
def candle_readiness(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTrainingService = Depends(get_service),
) -> list[CandleReadinessRow]:
    return [CandleReadinessRow.model_validate(r) for r in service.candle_readiness()]


@router.get("/candidates", response_model=list[FounderCandidateRead])
def founder_candidates(
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
    limit: int = 10,
) -> list[FounderCandidateRead]:
    scan = MarketScanService(db)
    training = PaperTrainingService(db)
    rows = []
    for cand in scan.list_candidates(limit=limit):
        payload = training.founder_candidate(cand)
        payload["lesson"] = training.trade_lesson_for_candidate(cand)
        rows.append(FounderCandidateRead.model_validate(payload))
    return rows


@router.get("/learning-desk", response_model=PortfolioRead)
def learning_desk(
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: PaperTrainingService = Depends(get_service),
) -> PortfolioRead:
    """Ensure the canonical $300 Founder Learning Desk exists and return it."""
    try:
        desk = service.ensure_learning_desk(actor=principal)
        return PortfolioRead.model_validate(desk)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/{portfolio_id}/settings", response_model=TrainingSettingsRead)
def get_settings(
    portfolio_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTrainingService = Depends(get_service),
) -> TrainingSettingsRead:
    return TrainingSettingsRead.model_validate(service.get_or_create_settings(portfolio_id))


@router.put("/{portfolio_id}/settings", response_model=TrainingSettingsRead)
def update_settings(
    portfolio_id: uuid.UUID,
    body: TrainingSettingsUpdate,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: PaperTrainingService = Depends(get_service),
) -> TrainingSettingsRead:
    try:
        row = service.set_mode(
            portfolio_id,
            mode=body.mode,
            actor=principal,
            default_notional=body.default_notional,
        )
    except PaperTrainingError as exc:
        raise _http(exc) from exc
    return TrainingSettingsRead.model_validate(row)


@router.get("/{portfolio_id}/scorecard", response_model=ScorecardRead)
def scorecard(
    portfolio_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    service: PaperTrainingService = Depends(get_service),
) -> ScorecardRead:
    return ScorecardRead.model_validate(service.scorecard(portfolio_id))


@router.post("/{portfolio_id}/coaching/take", response_model=CoachingActionResponse)
def coaching_take(
    portfolio_id: uuid.UUID,
    body: CoachingActionRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: PaperTrainingService = Depends(get_service),
) -> CoachingActionResponse:
    try:
        result = service.coaching_take(
            portfolio_id=portfolio_id,
            candidate_id=body.candidate_id,
            actor=principal,
            note=body.note,
        )
    except PaperTrainingError as exc:
        raise _http(exc) from exc
    return CoachingActionResponse(
        ok=True,
        message=f"Opened a simulated {result['symbol']} paper trade.",
        order_id=result["order_id"],
        decision_id=result["decision_id"],
        symbol=result["symbol"],
    )


@router.post("/{portfolio_id}/coaching/skip", response_model=CoachingActionResponse)
def coaching_skip(
    portfolio_id: uuid.UUID,
    body: CoachingActionRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: PaperTrainingService = Depends(get_service),
) -> CoachingActionResponse:
    try:
        result = service.coaching_skip(
            portfolio_id=portfolio_id,
            candidate_id=body.candidate_id,
            actor=principal,
            note=body.note,
        )
    except PaperTrainingError as exc:
        raise _http(exc) from exc
    return CoachingActionResponse(
        ok=True,
        message=f"Skipped {result['symbol']} for this practice round.",
        decision_id=result["decision_id"],
        symbol=result["symbol"],
    )


@router.post("/{portfolio_id}/feedback", response_model=FeedbackRead, status_code=201)
def record_feedback(
    portfolio_id: uuid.UUID,
    body: FeedbackRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: PaperTrainingService = Depends(get_service),
) -> FeedbackRead:
    try:
        row = service.record_feedback(
            portfolio_id=portfolio_id,
            actor=principal,
            feedback_code=body.feedback_code,
            symbol=body.symbol,
            fill_id=body.fill_id,
            candidate_id=body.candidate_id,
            note=body.note,
            strategy_key=body.strategy_key,
        )
    except PaperTrainingError as exc:
        raise _http(exc) from exc
    return FeedbackRead.model_validate(row)


@router.post("/{portfolio_id}/auto-enter")
def auto_enter(
    portfolio_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounderOrOperator),
    service: PaperTrainingService = Depends(get_service),
) -> dict[str, object]:
    """Run automatic practice entries if mode=automatic (paper only)."""
    opened = service.maybe_auto_enter_from_scan(
        portfolio_id=portfolio_id, actor=principal
    )
    return {
        "ok": True,
        "opened": opened,
        "message": (
            f"Opened {len(opened)} simulated trade(s)."
            if opened
            else "No automatic paper entries were taken."
        ),
    }


@router.post("/{portfolio_id}/reseed-learning")
def reseed_learning(
    portfolio_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    service: PaperTrainingService = Depends(get_service),
) -> dict[str, object]:
    """Flatten paper risk and reset the learning desk to $300 starting cash.

    Live trading stays locked. Default practice size becomes $30 (~10% of book).
    """
    try:
        result = service.reseed_learning_desk(portfolio_id, actor=principal)
    except PaperTrainingError as exc:
        raise _http(exc) from exc
    return {
        "ok": True,
        "message": (
            f"Learning desk reset to ${result['cash_balance']} with "
            f"${result['default_notional']} per practice entry."
        ),
        **result,
    }


@router.get("/{portfolio_id}/advanced-learning")
def advanced_learning_pane(
    portfolio_id: uuid.UUID,
    _: AuthenticatedPrincipal = Depends(RequireAnyAuthenticatedRead),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Advanced Learning pane for Paper Training — PAPER only."""
    from app.services.advanced_learning_service import AdvancedLearningService

    try:
        return AdvancedLearningService(db).pane(portfolio_id)
    except Exception as exc:  # noqa: BLE001
        return {
            "error": str(exc)[:200],
            "live_trading_enabled": False,
            "learning_day": 1,
            "required_days": 20,
            "disclaimer": "Advanced learning unavailable until migrations and worker are healthy.",
        }
