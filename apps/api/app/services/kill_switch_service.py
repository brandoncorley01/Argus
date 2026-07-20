"""Kill switch management (Phase 13) — global/provider/account/portfolio/strategy/instrument."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.micro_live import KillSwitch, KillSwitchScope
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal


class KillSwitchError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class KillSwitchService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def list_switches(self) -> list[KillSwitch]:
        return list(
            self.db.scalars(select(KillSwitch).order_by(KillSwitch.created_at.desc()))
        )

    def get_global(self) -> KillSwitch:
        row = self.db.scalar(
            select(KillSwitch).where(
                KillSwitch.scope_type == KillSwitchScope.GLOBAL.value,
                KillSwitch.scope_id.is_(None),
            )
        )
        if row is None:
            row = KillSwitch(
                scope_type=KillSwitchScope.GLOBAL.value,
                scope_id=None,
                active=False,
                reason="auto_initialized",
            )
            self.db.add(row)
            self.db.flush()
        return row

    def is_global_active(self) -> bool:
        return bool(self.get_global().active)

    def is_any_blocking(
        self, *, provider_key: str | None = None, portfolio_id: str | None = None
    ) -> bool:
        if self.is_global_active():
            return True
        scoped: list[tuple[str, str | None]] = [(KillSwitchScope.PROVIDER.value, provider_key)]
        if portfolio_id is not None:
            scoped.append((KillSwitchScope.PORTFOLIO.value, portfolio_id))
        for scope_type, scope_id in scoped:
            if scope_id is None:
                continue
            row = self.db.scalar(
                select(KillSwitch).where(
                    KillSwitch.scope_type == scope_type,
                    KillSwitch.scope_id == scope_id,
                    KillSwitch.active.is_(True),
                )
            )
            if row is not None:
                return True
        return False

    def set_switch(
        self,
        *,
        scope_type: str,
        scope_id: str | None,
        active: bool,
        reason: str | None,
        actor: AuthenticatedPrincipal,
    ) -> KillSwitch:
        try:
            KillSwitchScope(scope_type)
        except ValueError as exc:
            raise KillSwitchError("invalid_scope", f"Unknown scope_type: {scope_type}") from exc
        if scope_type == KillSwitchScope.GLOBAL.value and scope_id is not None:
            raise KillSwitchError("invalid_scope", "Global scope must not have a scope_id")
        if scope_type != KillSwitchScope.GLOBAL.value and not scope_id:
            raise KillSwitchError("invalid_scope", "Non-global scope requires a scope_id")

        row = self.db.scalar(
            select(KillSwitch).where(
                KillSwitch.scope_type == scope_type,
                KillSwitch.scope_id == scope_id,
            )
        )
        if row is None:
            row = KillSwitch(scope_type=scope_type, scope_id=scope_id, active=False)
            self.db.add(row)
            self.db.flush()

        row.active = active
        row.reason = reason
        if active:
            row.activated_by_user_id = actor.user.id
            row.activated_at = _utcnow()
        else:
            row.cleared_by_user_id = actor.user.id
            row.cleared_at = _utcnow()

        self.audit.append(
            action="micro_live.kill_switch.set",
            resource_type="kill_switch",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"scope_type": scope_type, "scope_id": scope_id, "active": active},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def get(self, switch_id: uuid.UUID) -> KillSwitch:
        row = self.db.get(KillSwitch, switch_id)
        if row is None:
            raise KillSwitchError("not_found", str(switch_id))
        return row
