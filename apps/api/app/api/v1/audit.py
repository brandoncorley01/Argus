from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.audit import AuditEventListResponse, AuditEventRead
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def get_audit_service(db: Session = Depends(get_db)) -> AuditService:
    return AuditService(db)


@router.get("/events", response_model=AuditEventListResponse)
def list_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    service: AuditService = Depends(get_audit_service),
) -> AuditEventListResponse:
    """
    Read audit events.

    Authentication is deferred to Phase 5. Until then this endpoint is available
    only on the local private control-plane and must not be exposed publicly.
    """
    items = service.list_events(
        limit=limit, offset=offset, action=action, resource_type=resource_type
    )
    return AuditEventListResponse(
        items=[AuditEventRead.model_validate(item) for item in items],
        limit=limit,
        offset=offset,
    )


@router.get("/events/{event_id}", response_model=AuditEventRead)
def get_audit_event(
    event_id: uuid.UUID,
    service: AuditService = Depends(get_audit_service),
) -> AuditEventRead:
    event = service.get(event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audit event not found")
    return AuditEventRead.model_validate(event)
