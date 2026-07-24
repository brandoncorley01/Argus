"""Pydantic schemas for the Phase 15 Operational Validation HTTP API."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.operations import OperationalComponent, OperationalSeverity

# --- operational events -------------------------------------------------------


class OperationalEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    component: str
    severity: str
    description: str
    correlation_id: str
    details: dict[str, Any]
    actor_user_id: uuid.UUID | None


class OperationalEventCreateRequest(BaseModel):
    component: OperationalComponent
    severity: OperationalSeverity
    description: str = Field(min_length=1, max_length=4000)
    correlation_id: str | None = Field(default=None, max_length=64)
    details: dict[str, Any] | None = None


# --- host resource snapshots --------------------------------------------------


class HostResourceSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    captured_at: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_bytes: int
    disk_percent: float
    disk_used_bytes: int
    details: dict[str, Any]


# --- daily trading reports ----------------------------------------------------


class DailyTradingReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_date: date
    content: dict[str, Any]
    content_hash: str
    generated_at: datetime
    is_immutable: bool


class DailyTradingReportGenerateRequest(BaseModel):
    report_date: date | None = None


# --- system health -------------------------------------------------------------


class SystemHealthRead(BaseModel):
    overall_status: str
    app_name: str
    institutional_health: dict[str, Any] | None
    services: list[dict[str, Any]]
    healthy_service_count: int
    warning_service_count: int
    critical_service_count: int
    readiness: dict[str, Any]
    host: dict[str, Any] | None
    paper: dict[str, Any]
    reconciliation: dict[str, Any]
    incidents_by_severity: dict[str, int]
    worker_instances: list[dict[str, Any]]
    uptime_seconds: float
    process_started_at: datetime
    recent_events: list[dict[str, Any]]
    generated_at: datetime
    # Sprint 4 — operational stability (aggregated from existing subsystems + backup meta)
    runtime_monitor: dict[str, Any] = Field(default_factory=dict)
    backup: dict[str, Any] = Field(default_factory=dict)
    active_alerts: list[dict[str, Any]] = Field(default_factory=list)
    incident_history: list[dict[str, Any]] = Field(default_factory=list)
