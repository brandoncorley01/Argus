"""Institutional reporting service (Phase 14).

Generates versioned, hashed, immutable reports that explicitly separate
PAPER/SIMULATED results from LIVE results. Live trading has no reachable
activation path in this system (ADR-029), so every report's "live" section
is empty and carries an explicit unavailability note rather than a
fabricated or zero-as-if-real figure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.treasury import (
    CapitalAllocation,
    EnvironmentClass,
    ExecutiveKpiSnapshot,
    ExternalTransferInstruction,
    InstitutionalReport,
    InstitutionalReportType,
    PerformanceAttributionSnapshot,
    TreasuryAccount,
)
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal
from app.services.payload_integrity import hash_payload

ENVIRONMENT_DISCLAIMER = (
    "This report strictly separates PAPER/SIMULATED results from LIVE results. "
    "Live trading is disabled in this system and has no reachable activation "
    "path (see ADR-029); the 'live' section below is always empty and marked "
    "unavailable rather than fabricated. No figure in this report represents "
    "real financial performance. Simulated treasury balances are internal "
    "paper capital only, never real money (see ADR-030)."
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class TreasuryReportingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class TreasuryReportingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def list_reports(self, *, report_type: str | None = None) -> list[InstitutionalReport]:
        stmt = select(InstitutionalReport).order_by(InstitutionalReport.created_at.desc())
        if report_type is not None:
            stmt = stmt.where(InstitutionalReport.report_type == report_type)
        return list(self.db.scalars(stmt))

    def get_report(self, report_id: uuid.UUID) -> InstitutionalReport:
        row = self.db.get(InstitutionalReport, report_id)
        if row is None:
            raise TreasuryReportingError("not_found", f"Report {report_id} not found")
        return row

    def generate_report(
        self, *, report_type: str, actor: AuthenticatedPrincipal, as_of: datetime | None = None
    ) -> InstitutionalReport:
        try:
            type_enum = InstitutionalReportType(report_type)
        except ValueError as exc:
            raise TreasuryReportingError(
                "invalid_report_type", f"Unknown report_type: {report_type}"
            ) from exc

        effective_as_of = as_of or _utcnow()
        content = self._build_content(type_enum, effective_as_of)
        content_hash = hash_payload(content)

        existing_max = self.db.scalar(
            select(InstitutionalReport.version)
            .where(InstitutionalReport.report_type == type_enum.value)
            .order_by(InstitutionalReport.version.desc())
            .limit(1)
        )
        next_version = (existing_max or 0) + 1

        row = InstitutionalReport(
            report_type=type_enum.value,
            version=next_version,
            as_of=effective_as_of,
            content=content,
            content_hash=content_hash,
            provenance={
                "generated_by": str(actor.user.id),
                "generator": "treasury_reporting_service",
            },
            is_immutable=True,
            environment_disclaimer=ENVIRONMENT_DISCLAIMER,
            generated_by_user_id=actor.user.id,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="treasury.report.generate",
            resource_type="institutional_report",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={
                "report_type": type_enum.value,
                "version": next_version,
                "content_hash": content_hash,
            },
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def _build_content(
        self, report_type: InstitutionalReportType, as_of: datetime
    ) -> dict[str, Any]:
        accounts = list(self.db.scalars(select(TreasuryAccount)))
        allocations = list(self.db.scalars(select(CapitalAllocation)))
        transfers = list(self.db.scalars(select(ExternalTransferInstruction)))
        latest_attribution = list(
            self.db.scalars(
                select(PerformanceAttributionSnapshot)
                .order_by(PerformanceAttributionSnapshot.as_of.desc())
                .limit(20)
            )
        )
        latest_kpis = list(
            self.db.scalars(
                select(ExecutiveKpiSnapshot).order_by(ExecutiveKpiSnapshot.as_of.desc()).limit(20)
            )
        )

        treasury_summary = {
            "account_count": len(accounts),
            "total_simulated_balance": str(sum((a.balance for a in accounts), Decimal("0"))),
            "accounts": [
                {
                    "id": str(a.id),
                    "name": a.name,
                    "classification": a.classification,
                    "balance": str(a.balance),
                }
                for a in accounts
            ],
            "allocation_status_counts": self._count_by(allocations, "status"),
            "external_transfer_status_counts": self._count_by(transfers, "status"),
            "external_transfer_executed_count": 0,
        }

        paper_section = {
            "environment_class": EnvironmentClass.PAPER.value,
            "attribution_snapshots": [
                {
                    "scope": s.scope,
                    "scope_ref": s.scope_ref,
                    "amounts": s.amounts,
                    "is_available": s.is_available,
                    "as_of": _jsonable(s.as_of),
                }
                for s in latest_attribution
                if s.environment_class == EnvironmentClass.PAPER.value
            ],
        }
        live_section = {
            "environment_class": EnvironmentClass.LIVE.value,
            "attribution_snapshots": [],
            "available": False,
            "unavailable_reason": (
                "Live trading has no reachable activation path in this system "
                "(see ADR-029). This section is intentionally empty."
            ),
        }

        return {
            "report_type": report_type.value,
            "as_of": _jsonable(as_of),
            "treasury": treasury_summary,
            "kpis": [
                {
                    "kpi_key": k.kpi_key,
                    "value": str(k.value) if k.value is not None else None,
                    "unit": k.unit,
                    "environment_class": k.environment_class,
                    "is_estimated": k.is_estimated,
                }
                for k in latest_kpis
            ],
            "paper": paper_section,
            "live": live_section,
            "disclaimer": ENVIRONMENT_DISCLAIMER,
        }

    @staticmethod
    def _count_by(rows: list[Any], attr: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            key = str(getattr(row, attr))
            counts[key] = counts.get(key, 0) + 1
        return counts
