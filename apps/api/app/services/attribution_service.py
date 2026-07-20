"""Performance attribution service (Phase 14).

Builds attribution snapshots from Phase 12 paper-trading tables only
(``paper_orders`` / ``paper_fills`` / ``paper_positions`` /
``paper_portfolios``). Every generated row is explicitly labeled
``environment_class``. There is no live data source anywhere in this
system (see ADR-029) — requesting a non-paper environment class always
yields an empty, explicitly-unavailable snapshot rather than a fabricated
figure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.paper_trading import PaperFill, PaperOrder, PaperPortfolio, PaperPosition
from app.models.treasury import AttributionScope, EnvironmentClass, PerformanceAttributionSnapshot
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal


class AttributionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


_MAX_EVIDENCE_SAMPLE = 20


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _d(value: Decimal | None) -> str:
    return str(value if value is not None else Decimal("0"))


class AttributionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def list_snapshots(
        self, *, scope: str | None = None, environment_class: str | None = None, limit: int = 100
    ) -> list[PerformanceAttributionSnapshot]:
        safe_limit = min(max(limit, 1), 500)
        stmt = select(PerformanceAttributionSnapshot).order_by(
            PerformanceAttributionSnapshot.as_of.desc()
        )
        if scope is not None:
            stmt = stmt.where(PerformanceAttributionSnapshot.scope == scope)
        if environment_class is not None:
            stmt = stmt.where(PerformanceAttributionSnapshot.environment_class == environment_class)
        stmt = stmt.limit(safe_limit)
        return list(self.db.scalars(stmt))

    def generate_snapshot(
        self,
        *,
        scope: str,
        scope_ref: str | None,
        environment_class: str,
        actor: AuthenticatedPrincipal,
        as_of: datetime | None = None,
    ) -> PerformanceAttributionSnapshot:
        try:
            scope_enum = AttributionScope(scope)
        except ValueError as exc:
            raise AttributionError("invalid_scope", f"Unknown scope: {scope}") from exc
        try:
            env_enum = EnvironmentClass(environment_class)
        except ValueError as exc:
            raise AttributionError(
                "invalid_environment_class", f"Unknown environment_class: {environment_class}"
            ) from exc

        effective_as_of = as_of or _utcnow()

        if env_enum is not EnvironmentClass.PAPER:
            amounts: dict[str, Any] = {}
            evidence_refs: list[Any] = []
            is_available = False
            unavailable_reason = (
                f"No '{environment_class}' trading capability is active in this system. "
                "Only paper/simulated execution exists; live trading remains disabled "
                "(see ADR-029). This snapshot is intentionally empty."
            )
        elif scope_enum is AttributionScope.SLIPPAGE:
            amounts = {}
            evidence_refs = []
            is_available = False
            unavailable_reason = (
                "Slippage attribution requires a market reference price at order-submit "
                "time, which Phase 12 paper fills do not persist. Not fabricated."
            )
        else:
            amounts, evidence_refs = self._compute_paper_amounts(scope_enum, scope_ref)
            is_available = True
            unavailable_reason = None

        row = PerformanceAttributionSnapshot(
            as_of=effective_as_of,
            scope=scope_enum.value,
            scope_ref=scope_ref,
            environment_class=env_enum.value,
            amounts=amounts,
            evidence_refs=evidence_refs,
            is_available=is_available,
            unavailable_reason=unavailable_reason,
            generated_by_user_id=actor.user.id,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="treasury.attribution.generate",
            resource_type="performance_attribution_snapshot",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={
                "scope": scope_enum.value,
                "environment_class": env_enum.value,
                "is_available": is_available,
            },
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def _compute_paper_amounts(
        self, scope: AttributionScope, scope_ref: str | None
    ) -> tuple[dict[str, Any], list[Any]]:
        fills_stmt = select(PaperFill)
        if scope is AttributionScope.PORTFOLIO and scope_ref:
            fills_stmt = fills_stmt.where(PaperFill.portfolio_id == scope_ref)
        elif scope is AttributionScope.PROVIDER and scope_ref:
            fills_stmt = fills_stmt.where(PaperFill.provider_id == scope_ref)
        elif scope is AttributionScope.INSTRUMENT and scope_ref:
            fills_stmt = fills_stmt.where(PaperFill.symbol == scope_ref)
        elif scope is AttributionScope.STRATEGY and scope_ref:
            fills_stmt = fills_stmt.join(PaperOrder, PaperFill.order_id == PaperOrder.id).where(
                PaperOrder.strategy_version_id == scope_ref
            )

        fills = list(self.db.scalars(fills_stmt))
        gross_notional = sum((f.quantity * f.price for f in fills), Decimal("0"))
        total_fees = sum((f.fee for f in fills), Decimal("0"))
        fill_count = len(fills)

        realized_pnl = Decimal("0")
        unrealized_pnl = Decimal("0")
        if scope is AttributionScope.FEE:
            amounts = {"total_fees": _d(total_fees), "fill_count": fill_count}
        else:
            positions_stmt = select(PaperPosition)
            if scope is AttributionScope.PORTFOLIO and scope_ref:
                positions_stmt = positions_stmt.where(PaperPosition.portfolio_id == scope_ref)
            elif scope is AttributionScope.INSTRUMENT and scope_ref:
                positions_stmt = positions_stmt.where(PaperPosition.symbol == scope_ref)
            positions = list(self.db.scalars(positions_stmt))
            realized_pnl = sum((p.realized_pnl for p in positions), Decimal("0"))
            unrealized_pnl = sum((p.unrealized_pnl for p in positions), Decimal("0"))
            amounts = {
                "gross_notional": _d(gross_notional),
                "total_fees": _d(total_fees),
                "realized_pnl": _d(realized_pnl),
                "unrealized_pnl": _d(unrealized_pnl),
                "net_pnl": _d(realized_pnl + unrealized_pnl - total_fees),
                "fill_count": fill_count,
                "position_count": len(positions),
            }

        evidence_refs: list[Any] = [
            {"table": "paper_fills", "id": str(f.id)} for f in fills[:_MAX_EVIDENCE_SAMPLE]
        ]
        evidence_refs.append({"table": "paper_fills", "matched_count": fill_count})
        return amounts, evidence_refs

    def portfolio_evidence_summary(self, portfolio_id: str) -> dict[str, Any]:
        """Small honesty check used by KPI/report builders — never fabricated."""
        portfolio = self.db.scalar(select(PaperPortfolio).where(PaperPortfolio.id == portfolio_id))
        fill_count = self.db.scalar(
            select(func.count())
            .select_from(PaperFill)
            .where(PaperFill.portfolio_id == portfolio_id)
        )
        return {
            "portfolio_found": portfolio is not None,
            "fill_count": int(fill_count or 0),
        }
