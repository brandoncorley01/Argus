"""Daily trading (paper-ops) report generation (Phase 15).

Builds an immutable, content-hashed daily summary of Internal Paper
Provider activity from real `PaperOrder`/`PaperFill`/`PaperPosition`/
`PaperRiskBreach`/`Incident` rows for a single UTC calendar date. Every
figure is derived from persisted data — nothing is invented, and metrics
that cannot be honestly computed from available data (e.g. win rate with no
sell fills that day) are reported as `null` rather than `0`.

Realized P&L is not tracked per-fill; `PaperPosition.realized_pnl` is a
cumulative, current-state figure. To attribute realized P&L to a specific
calendar day, this service replays every fill for each (portfolio, symbol)
pair in chronological order (oldest first, across all history) and records
the realized P&L computed at the moment each sell fill lands within the
target day. This is a deterministic re-derivation from real fills, not an
estimate or simulation of a hypothetical trade.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incident
from app.models.operations import DailyTradingReport
from app.models.paper_trading import PaperFill, PaperOrder, PaperPosition, PaperRiskBreach
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal
from app.services.payload_integrity import hash_payload

DAILY_REPORT_DISCLAIMER = (
    "This report summarizes Internal Paper Execution Provider ('internal_paper') "
    "activity only. No real money, brokerage account, or live trading is "
    "involved. Open positions and exposure reflect the current state at "
    "report-generation time, not a historical end-of-day snapshot. Metrics "
    "that cannot be honestly computed from recorded data (e.g. win rate with "
    "no closing trades that day) are reported as null, never as zero."
)


class DailyTradingReportError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _day_bounds(report_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(report_date, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class DailyTradingReportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def get_report(self, report_date: date) -> DailyTradingReport | None:
        return self.db.scalar(
            select(DailyTradingReport).where(DailyTradingReport.report_date == report_date)
        )

    def list_reports(self, *, limit: int = 60) -> list[DailyTradingReport]:
        safe_limit = min(max(limit, 1), 365)
        return list(
            self.db.scalars(
                select(DailyTradingReport)
                .order_by(DailyTradingReport.report_date.desc())
                .limit(safe_limit)
            )
        )

    def generate(
        self, *, report_date: date, actor: AuthenticatedPrincipal | None = None
    ) -> DailyTradingReport:
        existing = self.get_report(report_date)
        if existing is not None:
            raise DailyTradingReportError(
                "report_immutable",
                f"Daily trading report for {report_date.isoformat()} already exists "
                "and is immutable; it cannot be regenerated or overwritten.",
            )

        content = self._build_content(report_date)
        content_hash = hash_payload(content)

        row = DailyTradingReport(
            report_date=report_date,
            content=content,
            content_hash=content_hash,
            is_immutable=True,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="operations.daily_report.generate",
            resource_type="daily_trading_report",
            resource_id=str(row.id),
            actor_user_id=actor.user.id if actor is not None else None,
            payload={"report_date": report_date.isoformat(), "content_hash": content_hash},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def _realized_pnl_for_day(
        self, report_date: date
    ) -> tuple[Decimal, list[Decimal], int]:
        """Replay every fill chronologically per (portfolio, symbol) and
        return (total realized P&L on `report_date`, list of individual
        sell realized-P&L values on `report_date`, sell-fill count)."""
        day_start, day_end = _day_bounds(report_date)
        all_fills = list(self.db.scalars(select(PaperFill).order_by(PaperFill.filled_at.asc())))

        grouped: dict[tuple[Any, str], list[PaperFill]] = defaultdict(list)
        for fill in all_fills:
            grouped[(fill.portfolio_id, fill.symbol)].append(fill)

        day_total = Decimal("0")
        day_sell_pnls: list[Decimal] = []
        day_sell_count = 0

        for fills in grouped.values():
            quantity = Decimal("0")
            average_cost = Decimal("0")
            for fill in fills:
                if fill.side == "buy":
                    notional = fill.quantity * fill.price
                    new_quantity = quantity + fill.quantity
                    if new_quantity > 0:
                        average_cost = ((quantity * average_cost) + notional) / new_quantity
                    quantity = new_quantity
                else:
                    realized = (fill.price - average_cost) * fill.quantity
                    quantity = quantity - fill.quantity
                    if day_start <= fill.filled_at < day_end:
                        day_total += realized
                        day_sell_pnls.append(realized)
                        day_sell_count += 1

        return day_total, day_sell_pnls, day_sell_count

    def _build_content(self, report_date: date) -> dict[str, Any]:
        day_start, day_end = _day_bounds(report_date)

        fills_today = list(
            self.db.scalars(
                select(PaperFill).where(
                    PaperFill.filled_at >= day_start, PaperFill.filled_at < day_end
                )
            )
        )
        orders_today = list(
            self.db.scalars(
                select(PaperOrder).where(
                    PaperOrder.created_at >= day_start, PaperOrder.created_at < day_end
                )
            )
        )
        risk_breaches_today = list(
            self.db.scalars(
                select(PaperRiskBreach).where(
                    PaperRiskBreach.detected_at >= day_start, PaperRiskBreach.detected_at < day_end
                )
            )
        )
        incidents_today = list(
            self.db.scalars(
                select(Incident).where(
                    Incident.opened_at >= day_start, Incident.opened_at < day_end
                )
            )
        )
        open_positions = list(
            self.db.scalars(select(PaperPosition).where(PaperPosition.quantity != 0))
        )

        daily_pnl, day_sell_pnls, sell_count = self._realized_pnl_for_day(report_date)

        win_rate: str | None = None
        largest_winner: str | None = None
        largest_loser: str | None = None
        if sell_count > 0:
            wins = [p for p in day_sell_pnls if p > 0]
            win_rate = str(Decimal(len(wins)) / Decimal(sell_count))
            largest_winner = str(max(day_sell_pnls))
            largest_loser = str(min(day_sell_pnls))

        exposure = sum(
            (abs(p.quantity) * p.average_cost for p in open_positions), Decimal("0")
        )

        return {
            "report_date": report_date.isoformat(),
            "provider": "internal_paper",
            "daily_pnl": str(daily_pnl),
            "trade_count": len(fills_today),
            "order_count": len(orders_today),
            "win_rate": win_rate,
            "largest_winner": largest_winner,
            "largest_loser": largest_loser,
            "open_positions": [
                {
                    "portfolio_id": str(p.portfolio_id),
                    "symbol": p.symbol,
                    "quantity": _jsonable(p.quantity),
                    "average_cost": _jsonable(p.average_cost),
                    "realized_pnl": _jsonable(p.realized_pnl),
                    "unrealized_pnl": _jsonable(p.unrealized_pnl),
                }
                for p in open_positions
            ],
            "exposure": str(exposure),
            "risk_events_count": len(risk_breaches_today),
            "incidents_count": len(incidents_today),
            "disclaimer": DAILY_REPORT_DISCLAIMER,
        }
