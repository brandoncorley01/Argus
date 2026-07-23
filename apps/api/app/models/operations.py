"""Phase 15 Operational Validation domain models.

This phase adds no new external services. It observes and reports on
existing subsystems only:

- `OperationalEvent` — an append-only operational log (never edited or
  deleted; secrets are rejected at write time by `operational_log_service`).
- `HostResourceSnapshot` — periodic host CPU/memory/disk metrics captured
  via `psutil`, used to populate the Founder-facing System Health dashboard.
- `DailyTradingReport` — an immutable, content-hashed daily summary of
  Internal Paper Provider operations (never real trading; never a
  fabricated P&L figure).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OperationalComponent(enum.StrEnum):
    API = "api"
    WORKER = "worker"
    DATABASE = "database"
    QUEUE = "queue"
    MARKET_DATA = "market_data"
    PAPER_PROVIDER = "paper_provider"
    SCHEDULER = "scheduler"
    HOST = "host"


class OperationalSeverity(enum.StrEnum):
    """Founder-facing operational alert severity.

    This intentionally mirrors the levels a Founder sees in an operational
    alert rather than reusing `IncidentSeverity` directly, because
    `IncidentSeverity` has `low` (no Founder-alert equivalent) instead of
    `info` (routine/informational operational events, e.g. a successful
    scheduled job). See `system_health_service.map_incident_severity` for
    the `IncidentSeverity.LOW -> OperationalSeverity.INFO` display mapping.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    INFO = "info"


_OPERATIONAL_COMPONENTS_SQL = (
    "component IN ('api','worker','database','queue','market_data',"
    "'paper_provider','scheduler','host')"
)
_OPERATIONAL_SEVERITIES_SQL = "severity IN ('critical','high','medium','info')"


class OperationalEvent(Base):
    """Append-only operational log. Never logs secret values (see
    `operational_log_service.OperationalLogService.append`)."""

    __tablename__ = "operational_events"
    __table_args__ = (
        CheckConstraint(_OPERATIONAL_COMPONENTS_SQL, name="ck_operational_events_component"),
        CheckConstraint(_OPERATIONAL_SEVERITIES_SQL, name="ck_operational_events_severity"),
        Index("ix_operational_events_occurred_at", "occurred_at"),
        Index("ix_operational_events_correlation_id", "correlation_id"),
        Index("ix_operational_events_component", "component"),
        Index("ix_operational_events_severity", "severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    component: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class HostResourceSnapshot(Base):
    """Periodic host resource metrics (CPU/memory/disk), captured via `psutil`."""

    __tablename__ = "host_resource_snapshots"
    __table_args__ = (Index("ix_host_resource_snapshots_captured_at", "captured_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disk_percent: Mapped[float] = mapped_column(Float, nullable=False)
    disk_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class DailyTradingReport(Base):
    """Immutable, content-hashed daily summary of Internal Paper Provider
    operations. `daily_trading_report_service` refuses to regenerate a
    report for a `report_date` that already has an immutable row."""

    __tablename__ = "daily_trading_reports"
    __table_args__ = (
        UniqueConstraint("report_date", name="uq_daily_trading_reports_report_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_immutable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


__all__ = [
    "OperationalComponent",
    "OperationalSeverity",
    "OperationalEvent",
    "HostResourceSnapshot",
    "DailyTradingReport",
]
