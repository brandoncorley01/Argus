"""Micro-capital policy management and pretrade validation (Phase 13).

The active policy is enforced in dry-run today (no live path exists to
enforce it against a real order). It remains fully testable so the
institutional controls are proven before any future certification work.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.micro_live import MicroCapitalPolicy
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal


class MicroCapitalError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class OrderValidationResult:
    allowed: bool
    blocking_codes: list[str]
    notional: Decimal
    policy_version: int


class MicroCapitalService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def get_active_policy(self) -> MicroCapitalPolicy:
        row = self.db.scalar(
            select(MicroCapitalPolicy).where(MicroCapitalPolicy.is_active.is_(True))
        )
        if row is None:
            raise MicroCapitalError("policy_missing", "No active micro-capital policy")
        return row

    def list_policies(self) -> list[MicroCapitalPolicy]:
        return list(
            self.db.scalars(
                select(MicroCapitalPolicy).order_by(MicroCapitalPolicy.version.desc())
            )
        )

    def set_policy(
        self,
        *,
        max_deployable_capital: Decimal,
        max_order_notional: Decimal,
        max_daily_loss: Decimal,
        max_concurrent_exposure: Decimal,
        max_provider_exposure: Decimal,
        max_strategy_exposure: Decimal,
        actor: AuthenticatedPrincipal,
    ) -> MicroCapitalPolicy:
        for label, value in (
            ("max_deployable_capital", max_deployable_capital),
            ("max_order_notional", max_order_notional),
            ("max_daily_loss", max_daily_loss),
            ("max_concurrent_exposure", max_concurrent_exposure),
            ("max_provider_exposure", max_provider_exposure),
            ("max_strategy_exposure", max_strategy_exposure),
        ):
            if value <= 0:
                raise MicroCapitalError("invalid_policy", f"{label} must be positive")

        current = self.db.scalar(
            select(MicroCapitalPolicy).where(MicroCapitalPolicy.is_active.is_(True))
        )
        next_version = (current.version + 1) if current else 1
        if current is not None:
            current.is_active = False

        row = MicroCapitalPolicy(
            version=next_version,
            max_deployable_capital=max_deployable_capital,
            max_order_notional=max_order_notional,
            max_daily_loss=max_daily_loss,
            max_concurrent_exposure=max_concurrent_exposure,
            max_provider_exposure=max_provider_exposure,
            max_strategy_exposure=max_strategy_exposure,
            is_active=True,
            created_by_user_id=actor.user.id,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="micro_live.capital_policy.update",
            resource_type="micro_capital_policy",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"version": next_version, "max_order_notional": str(max_order_notional)},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def validate_order(
        self, *, quantity: Decimal, reference_price: Decimal
    ) -> OrderValidationResult:
        policy = self.get_active_policy()
        notional = quantity * reference_price
        codes: list[str] = []
        if notional > policy.max_order_notional:
            codes.append("max_order_notional_exceeded")
        if notional > policy.max_deployable_capital:
            codes.append("max_deployable_capital_exceeded")
        return OrderValidationResult(
            allowed=len(codes) == 0,
            blocking_codes=codes,
            notional=notional,
            policy_version=policy.version,
        )
