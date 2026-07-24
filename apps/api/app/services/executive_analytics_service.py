"""Executive analytics / KPI service (Phase 14).

Every KPI value in this module is derived directly from an existing
institutional data source (paper trading, health, incidents, strategy
lab, governance/maturity, treasury ledgers) and carries ``evidence_refs``
pointing at that source. This module never invents or estimates a P&L
figure; ``is_estimated`` is only set true for genuinely derived/roll-up
values that are still evidence-backed (e.g. governance maturity averages),
never for financial performance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DepartmentCapability, Incident, IncidentStatus
from app.models.paper_trading import PaperOrder, PaperPortfolio
from app.models.strategy_laboratory import StrategyDocument, StrategyLifecycleStatus
from app.models.treasury import EnvironmentClass, ExecutiveKpiSnapshot, TreasuryAccount
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal

try:
    from app.models import InstitutionalHealthState
except ImportError:  # pragma: no cover - defensive; model always present
    InstitutionalHealthState = None  # type: ignore[assignment,misc]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ExecutiveAnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def list_kpis(
        self, *, kpi_key: str | None = None, limit: int = 200
    ) -> list[ExecutiveKpiSnapshot]:
        safe_limit = min(max(limit, 1), 1000)
        stmt = select(ExecutiveKpiSnapshot).order_by(ExecutiveKpiSnapshot.as_of.desc())
        if kpi_key is not None:
            stmt = stmt.where(ExecutiveKpiSnapshot.kpi_key == kpi_key)
        stmt = stmt.limit(safe_limit)
        return list(self.db.scalars(stmt))

    def latest_kpis(self) -> list[ExecutiveKpiSnapshot]:
        """Latest row per kpi_key, evidence-backed, no invented figures."""
        stmt = select(ExecutiveKpiSnapshot).order_by(ExecutiveKpiSnapshot.as_of.desc())
        rows = list(self.db.scalars(stmt))
        latest: dict[str, ExecutiveKpiSnapshot] = {}
        for row in rows:
            if row.kpi_key not in latest:
                latest[row.kpi_key] = row
        return list(latest.values())

    def generate_snapshots(self, *, actor: AuthenticatedPrincipal) -> list[ExecutiveKpiSnapshot]:
        as_of = _utcnow()
        rows: list[ExecutiveKpiSnapshot] = []

        rows.append(self._paper_active_portfolios(as_of))
        rows.append(self._paper_cash_total(as_of))
        rows.append(self._paper_order_count(as_of))
        rows.append(self._incidents_open_count(as_of))
        rows.append(self._strategies_approved_count(as_of))
        rows.append(self._governance_maturity_level(as_of))
        rows.append(self._treasury_simulated_capital_total(as_of))
        health_row = self._health_status(as_of)
        if health_row is not None:
            rows.append(health_row)

        for row in rows:
            self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="treasury.kpi.generate",
            resource_type="executive_kpi_snapshot",
            resource_id=None,
            actor_user_id=actor.user.id,
            payload={"kpi_count": len(rows), "as_of": as_of.isoformat()},
        )
        self.db.commit()
        for row in rows:
            self.db.refresh(row)
        return rows

    def _paper_active_portfolios(self, as_of: datetime) -> ExecutiveKpiSnapshot:
        stmt = select(PaperPortfolio.id).where(PaperPortfolio.status == "active")
        ids = list(self.db.scalars(stmt))
        return ExecutiveKpiSnapshot(
            as_of=as_of,
            kpi_key="paper.portfolios.active_count",
            value=Decimal(len(ids)),
            unit="count",
            environment_class=EnvironmentClass.PAPER.value,
            evidence_refs=[
                {"table": "paper_portfolios", "matched_ids": [str(i) for i in ids[:20]]}
            ],
            is_estimated=False,
        )

    def _paper_cash_total(self, as_of: datetime) -> ExecutiveKpiSnapshot:
        total = self.db.scalar(select(func.coalesce(func.sum(PaperPortfolio.cash_balance), 0)))
        count = self.db.scalar(select(func.count()).select_from(PaperPortfolio))
        return ExecutiveKpiSnapshot(
            as_of=as_of,
            kpi_key="paper.cash.total",
            value=Decimal(str(total or 0)),
            unit="USD",
            environment_class=EnvironmentClass.PAPER.value,
            evidence_refs=[{"table": "paper_portfolios", "aggregated_rows": int(count or 0)}],
            is_estimated=False,
        )

    def _paper_order_count(self, as_of: datetime) -> ExecutiveKpiSnapshot:
        count = self.db.scalar(select(func.count()).select_from(PaperOrder))
        return ExecutiveKpiSnapshot(
            as_of=as_of,
            kpi_key="paper.orders.total_count",
            value=Decimal(int(count or 0)),
            unit="count",
            environment_class=EnvironmentClass.PAPER.value,
            evidence_refs=[{"table": "paper_orders", "aggregated_rows": int(count or 0)}],
            is_estimated=False,
        )

    def _incidents_open_count(self, as_of: datetime) -> ExecutiveKpiSnapshot:
        open_statuses = (
            IncidentStatus.OPEN.value,
            IncidentStatus.INVESTIGATING.value,
            IncidentStatus.MITIGATED.value,
        )
        ids = list(self.db.scalars(select(Incident.id).where(Incident.status.in_(open_statuses))))
        return ExecutiveKpiSnapshot(
            as_of=as_of,
            kpi_key="incidents.open_count",
            value=Decimal(len(ids)),
            unit="count",
            environment_class=EnvironmentClass.SIMULATED.value,
            evidence_refs=[{"table": "incidents", "matched_ids": [str(i) for i in ids[:20]]}],
            is_estimated=False,
        )

    def _strategies_approved_count(self, as_of: datetime) -> ExecutiveKpiSnapshot:
        ids = list(
            self.db.scalars(
                select(StrategyDocument.id).where(
                    StrategyDocument.status == StrategyLifecycleStatus.APPROVED.value
                )
            )
        )
        return ExecutiveKpiSnapshot(
            as_of=as_of,
            kpi_key="strategies.approved_count",
            value=Decimal(len(ids)),
            unit="count",
            environment_class=EnvironmentClass.SIMULATED.value,
            evidence_refs=[
                {"table": "strategy_documents", "matched_ids": [str(i) for i in ids[:20]]}
            ],
            is_estimated=False,
        )

    def _governance_maturity_level(self, as_of: datetime) -> ExecutiveKpiSnapshot:
        rows = list(self.db.scalars(select(DepartmentCapability)))
        if not rows:
            return ExecutiveKpiSnapshot(
                as_of=as_of,
                kpi_key="governance.maturity_level_avg",
                value=None,
                unit="level_0_6",
                environment_class=EnvironmentClass.SIMULATED.value,
                evidence_refs=[{"table": "department_capabilities", "matched_count": 0}],
                is_estimated=True,
                detail={"note": "No department capability rows recorded yet"},
            )
        avg = sum(r.capability_level for r in rows) / len(rows)
        return ExecutiveKpiSnapshot(
            as_of=as_of,
            kpi_key="governance.maturity_level_avg",
            value=Decimal(str(round(avg, 4))),
            unit="level_0_6",
            environment_class=EnvironmentClass.SIMULATED.value,
            evidence_refs=[
                {"table": "department_capabilities", "ids": [str(r.id) for r in rows[:20]]}
            ],
            is_estimated=True,
            detail={"department_count": len(rows)},
        )

    def _treasury_simulated_capital_total(self, as_of: datetime) -> ExecutiveKpiSnapshot:
        total = self.db.scalar(select(func.coalesce(func.sum(TreasuryAccount.balance), 0)))
        count = self.db.scalar(select(func.count()).select_from(TreasuryAccount))
        return ExecutiveKpiSnapshot(
            as_of=as_of,
            kpi_key="treasury.simulated_capital.total",
            value=Decimal(str(total or 0)),
            unit="USD",
            environment_class=EnvironmentClass.SIMULATED.value,
            evidence_refs=[{"table": "treasury_accounts", "aggregated_rows": int(count or 0)}],
            is_estimated=False,
            detail={"note": "Simulated/paper capital only — never real money"},
        )

    def _health_status(self, as_of: datetime) -> ExecutiveKpiSnapshot | None:
        if InstitutionalHealthState is None:
            return None
        state = self.db.get(InstitutionalHealthState, "current")
        if state is None:
            return None
        return ExecutiveKpiSnapshot(
            as_of=as_of,
            kpi_key="health.institutional_status",
            value=None,
            unit="status",
            environment_class=EnvironmentClass.SIMULATED.value,
            evidence_refs=[{"table": "institutional_health_state", "singleton_key": "current"}],
            is_estimated=False,
            detail={"status": str(state.status), "evaluation_version": state.evaluation_version},
        )

    def build_maturity_summary(self) -> dict[str, Any]:
        rows = list(self.db.scalars(select(DepartmentCapability)))
        return {
            "department_count": len(rows),
            "departments": [
                {
                    "department_key": r.department_key,
                    "capability_level": r.capability_level,
                }
                for r in rows
            ],
        }
