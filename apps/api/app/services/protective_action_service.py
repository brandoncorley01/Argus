"""Protective action recommendation lifecycle (Phase 8).

Protective actions are recommendations (and, when applied, records of an
already-taken protective step) raised by the health supervisor — e.g.
recommending/applying a SAFE_MODE degrade. Creation is idempotent so a
supervisor cycle can safely retry without creating duplicates. Dismissal is
Founder-only, since it is the human override of an automated protective
recommendation.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    InstitutionalRole,
    ProtectiveActionRecommendation,
    ProtectiveActionStatus,
    ProtectiveActionType,
)
from app.services.audit_service import AuditError, AuditService
from app.services.auth_service import AuthenticatedPrincipal, AuthError


class ProtectiveActionError(RuntimeError):
    """Domain error for protective-action recommendation operations."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(UTC)


def hash_idempotency_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class ProtectiveActionService:
    def __init__(self, session: Session) -> None:
        self._db = session
        self._audit = AuditService(session)

    def get(self, action_id: uuid.UUID) -> ProtectiveActionRecommendation | None:
        return self._db.get(ProtectiveActionRecommendation, action_id)

    def list_actions(
        self,
        *,
        status: ProtectiveActionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ProtectiveActionRecommendation]:
        safe_limit = min(max(limit, 1), 200)
        safe_offset = max(offset, 0)
        stmt = select(ProtectiveActionRecommendation).order_by(
            ProtectiveActionRecommendation.created_at.desc()
        )
        if status is not None:
            stmt = stmt.where(ProtectiveActionRecommendation.status == status)
        return list(self._db.scalars(stmt.offset(safe_offset).limit(safe_limit)))

    def create_recommendation(
        self,
        *,
        action_type: ProtectiveActionType,
        rationale: str,
        idempotency_key: str,
        incident_id: uuid.UUID | None = None,
        source_service_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> tuple[ProtectiveActionRecommendation, bool]:
        """Idempotently create a protective action recommendation.

        Returns (recommendation, created).
        """
        if not rationale or not rationale.strip():
            raise ProtectiveActionError("invalid_action", "rationale is required")
        if not idempotency_key or not idempotency_key.strip():
            raise ProtectiveActionError("invalid_action", "idempotency_key is required")
        key_hash = hash_idempotency_key(idempotency_key.strip())

        existing = self._db.scalars(
            select(ProtectiveActionRecommendation).where(
                ProtectiveActionRecommendation.idempotency_key_hash == key_hash
            )
        ).first()
        if existing is not None:
            return existing, False

        row = ProtectiveActionRecommendation(
            action_type=action_type,
            status=ProtectiveActionStatus.PENDING,
            incident_id=incident_id,
            source_service_id=source_service_id,
            rationale=rationale.strip(),
            payload=payload or {},
            idempotency_key_hash=key_hash,
        )
        self._db.add(row)
        try:
            self._db.flush()
        except IntegrityError:
            self._db.rollback()
            recovered = self._db.scalars(
                select(ProtectiveActionRecommendation).where(
                    ProtectiveActionRecommendation.idempotency_key_hash == key_hash
                )
            ).first()
            if recovered is not None:
                return recovered, False
            raise ProtectiveActionError(
                "action_conflict", "Concurrent protective action creation conflicted"
            ) from None

        try:
            self._audit.append(
                action="protective_action.recommended",
                resource_type="protective_action_recommendation",
                resource_id=str(row.id),
                request_id=request_id,
                payload={
                    "action_type": action_type.value,
                    "incident_id": str(incident_id) if incident_id else None,
                    "source_service_id": str(source_service_id) if source_service_id else None,
                },
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise ProtectiveActionError(
                "audit_unavailable",
                "Audit persistence failed; protective action aborted (fail-closed)",
            ) from None
        return row, True

    def mark_applied(
        self, *, action_id: uuid.UUID, request_id: str | None = None
    ) -> ProtectiveActionRecommendation:
        row = self._db.scalars(
            select(ProtectiveActionRecommendation)
            .where(ProtectiveActionRecommendation.id == action_id)
            .with_for_update()
        ).first()
        if row is None:
            raise ProtectiveActionError("action_not_found", "Protective action not found")
        if row.status != ProtectiveActionStatus.PENDING:
            raise ProtectiveActionError(
                "invalid_transition", "Only PENDING actions may be marked applied"
            )
        row.status = ProtectiveActionStatus.APPLIED
        row.applied_at = _utcnow()
        self._db.add(row)
        try:
            self._audit.append(
                action="protective_action.applied",
                resource_type="protective_action_recommendation",
                resource_id=str(row.id),
                request_id=request_id,
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise ProtectiveActionError(
                "audit_unavailable",
                "Audit persistence failed; protective action apply aborted (fail-closed)",
            ) from None
        return row

    def dismiss(
        self,
        *,
        action_id: uuid.UUID,
        actor: AuthenticatedPrincipal,
        request_id: str | None = None,
    ) -> ProtectiveActionRecommendation:
        if InstitutionalRole.FOUNDER not in actor.roles:
            try:
                self._audit.append(
                    action="authz.denied",
                    resource_type="protective_action_recommendation",
                    actor_user_id=actor.user.id,
                    request_id=request_id,
                    payload={"action": "protective_action.dismiss"},
                )
                self._db.commit()
            except AuditError:
                self._db.rollback()
            raise AuthError("Forbidden")

        row = self._db.scalars(
            select(ProtectiveActionRecommendation)
            .where(ProtectiveActionRecommendation.id == action_id)
            .with_for_update()
        ).first()
        if row is None:
            raise ProtectiveActionError("action_not_found", "Protective action not found")
        if row.status != ProtectiveActionStatus.PENDING:
            raise ProtectiveActionError(
                "invalid_transition", "Only PENDING actions may be dismissed"
            )
        row.status = ProtectiveActionStatus.DISMISSED
        row.dismissed_at = _utcnow()
        self._db.add(row)
        try:
            self._audit.append(
                action="protective_action.dismissed",
                resource_type="protective_action_recommendation",
                resource_id=str(row.id),
                actor_user_id=actor.user.id,
                request_id=request_id,
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise ProtectiveActionError(
                "audit_unavailable",
                "Audit persistence failed; protective action dismissal aborted (fail-closed)",
            ) from None
        return row
