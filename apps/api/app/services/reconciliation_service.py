"""Reconciliation runs (Phase 13) — compares paper state against a provider fixture.

No live provider is ever contacted. Reconciliation compares the Internal
Paper Provider's authoritative state against a supplied comparison fixture
(e.g. a test-provided snapshot standing in for "what a provider reported"),
which is how discrepancy detection is proven without a real account.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.micro_live import (
    ReconciliationDiscrepancy,
    ReconciliationRun,
    ReconciliationRunStatus,
)
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal


class ReconciliationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ReconciliationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def run(
        self,
        *,
        provider_key: str,
        authoritative_state: dict[str, Any],
        comparison_state: dict[str, Any],
        actor: AuthenticatedPrincipal,
    ) -> ReconciliationRun:
        from app.models.operations import OperationalComponent, OperationalSeverity
        from app.services.operational_log_service import OperationalLogError, OperationalLogService

        run = ReconciliationRun(
            provider_key=provider_key,
            status=ReconciliationRunStatus.RUNNING.value,
            initiated_by_user_id=actor.user.id,
        )
        self.db.add(run)
        self.db.flush()

        try:
            discrepancies = self._diff(authoritative_state, comparison_state)
            for disc in discrepancies:
                self.db.add(
                    ReconciliationDiscrepancy(
                        run_id=run.id,
                        kind=disc["kind"],
                        detail=disc["detail"],
                        resolved=False,
                    )
                )
            run.discrepancies = discrepancies
            run.status = ReconciliationRunStatus.COMPLETED.value
            run.completed_at = _utcnow()

            self.audit.append(
                action="micro_live.reconciliation.run",
                resource_type="reconciliation_run",
                resource_id=str(run.id),
                actor_user_id=actor.user.id,
                payload={"provider_key": provider_key, "discrepancy_count": len(discrepancies)},
            )
            if discrepancies:
                try:
                    OperationalLogService(self.db).append(
                        component=OperationalComponent.PAPER_PROVIDER,
                        severity=OperationalSeverity.HIGH,
                        description=(
                            f"Reconciliation completed with {len(discrepancies)} discrepancy(ies)"
                        ),
                        correlation_id=str(run.id),
                        details={
                            "provider_key": provider_key,
                            "discrepancy_count": len(discrepancies),
                        },
                        actor_user_id=actor.user.id,
                        commit=False,
                    )
                except OperationalLogError:
                    pass
            self.db.commit()
            self.db.refresh(run)
            return run
        except Exception as exc:
            run.status = ReconciliationRunStatus.FAILED.value
            run.completed_at = _utcnow()
            try:
                OperationalLogService(self.db).append(
                    component=OperationalComponent.PAPER_PROVIDER,
                    severity=OperationalSeverity.CRITICAL,
                    description=f"Reconciliation failure: {exc}",
                    correlation_id=str(run.id),
                    details={"provider_key": provider_key},
                    actor_user_id=actor.user.id,
                    commit=False,
                )
            except OperationalLogError:
                pass
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
            raise

    def _diff(
        self, authoritative: dict[str, Any], comparison: dict[str, Any]
    ) -> list[dict[str, Any]]:
        discrepancies: list[dict[str, Any]] = []

        auth_cash = Decimal(str(authoritative.get("cash_balance", "0")))
        comp_cash = Decimal(str(comparison.get("cash_balance", "0")))
        if auth_cash != comp_cash:
            discrepancies.append(
                {
                    "kind": "cash_balance_mismatch",
                    "detail": {
                        "authoritative": str(auth_cash),
                        "comparison": str(comp_cash),
                        "delta": str(auth_cash - comp_cash),
                    },
                }
            )

        auth_positions = {
            p["symbol"]: str(p["quantity"]) for p in authoritative.get("positions", [])
        }
        comp_positions = {
            p["symbol"]: str(p["quantity"]) for p in comparison.get("positions", [])
        }
        for symbol, qty in auth_positions.items():
            if comp_positions.get(symbol) != qty:
                discrepancies.append(
                    {
                        "kind": "position_mismatch",
                        "detail": {
                            "symbol": symbol,
                            "authoritative_quantity": qty,
                            "comparison_quantity": comp_positions.get(symbol, "0"),
                        },
                    }
                )
        for symbol in comp_positions:
            if symbol not in auth_positions:
                discrepancies.append(
                    {
                        "kind": "unexpected_position",
                        "detail": {
                            "symbol": symbol,
                            "comparison_quantity": comp_positions[symbol],
                        },
                    }
                )
        return discrepancies

    def list_runs(self) -> list[ReconciliationRun]:
        return list(
            self.db.scalars(
                select(ReconciliationRun).order_by(ReconciliationRun.started_at.desc())
            )
        )

    def get_run(self, run_id: uuid.UUID) -> ReconciliationRun:
        row = self.db.get(ReconciliationRun, run_id)
        if row is None:
            raise ReconciliationError("run_not_found", str(run_id))
        return row

    def list_discrepancies(self, run_id: uuid.UUID) -> list[ReconciliationDiscrepancy]:
        return list(
            self.db.scalars(
                select(ReconciliationDiscrepancy).where(
                    ReconciliationDiscrepancy.run_id == run_id
                )
            )
        )
