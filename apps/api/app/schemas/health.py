"""Pydantic schemas for health supervisor, worker, and incident APIs (Phase 8)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    HealthStatus,
    IncidentLifecycleEventType,
    IncidentSeverity,
    IncidentStatus,
    OperatingMode,
    ProtectiveActionStatus,
    ProtectiveActionType,
    ServiceCriticality,
    ServiceKind,
    WorkerInstanceStatus,
)

# --- Registered services / heartbeats / projections ---


class RegisteredServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_key: str
    display_name: str
    service_kind: ServiceKind
    criticality: ServiceCriticality
    heartbeat_interval_seconds: int
    heartbeat_timeout_seconds: int
    expected_instance_count: int
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class ServiceHealthProjectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_id: uuid.UUID
    status: HealthStatus
    last_heartbeat_id: uuid.UUID | None
    last_sequence_number: int | None
    last_observed_at: datetime | None
    consecutive_failures: int
    evaluation_version: int
    detail: str | None
    updated_at: datetime


class ServiceWithProjectionRead(BaseModel):
    service: RegisteredServiceRead
    projection: ServiceHealthProjectionRead | None


class HeartbeatIngestRequest(BaseModel):
    service_key: str = Field(min_length=1, max_length=64)
    status: HealthStatus
    observed_at: datetime
    sequence_number: int = Field(ge=0)
    detail: str | None = Field(default=None, max_length=2000)
    payload: dict[str, Any] | None = None
    worker_instance_id: uuid.UUID | None = None


class HeartbeatIngestResponse(BaseModel):
    heartbeat_id: str | None = None
    service_id: str
    service_key: str
    status: str
    sequence_number: int
    observed_at: str
    idempotent_replay: bool = False


# --- Institutional health + lease ---


class InstitutionalHealthStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    singleton_key: str
    status: HealthStatus
    evaluation_version: int
    summary: dict[str, Any]
    evaluated_at: datetime
    updated_at: datetime


class HealthSupervisorLeaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    singleton_key: str
    holder_instance_id: uuid.UUID | None
    lease_epoch: int
    lease_until: datetime | None
    last_cycle_at: datetime | None
    last_cycle_result: str | None
    updated_at: datetime


class SupervisorRunCycleRequest(BaseModel):
    instance_id: uuid.UUID | None = None


class SupervisorRunCycleResponse(BaseModel):
    lease_acquired: bool
    cycle_id: str | None = None
    institutional_status: str | None = None
    heartbeats: dict[str, Any] | None = None
    incidents: dict[str, Any] | None = None
    protective_action: dict[str, Any] | None = None
    reason: str | None = None
    holder_instance_id: str | None = None
    lease_until: str | None = None


# --- Worker identities / instances ---


class WorkerIdentityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    worker_key: str
    service_id: uuid.UUID
    display_name: str
    description: str | None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class WorkerInstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    worker_identity_id: uuid.UUID
    instance_key: str
    hostname: str | None
    status: WorkerInstanceStatus
    started_at: datetime
    last_seen_at: datetime
    stopped_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkerInstanceRegisterRequest(BaseModel):
    worker_key: str = Field(min_length=1, max_length=64)
    instance_key: str = Field(min_length=1, max_length=128)
    hostname: str | None = Field(default=None, max_length=256)
    metadata: dict[str, Any] | None = None


# --- Incidents ---


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    severity: IncidentSeverity
    status: IncidentStatus
    related_mode: OperatingMode | None
    source_service_id: uuid.UUID | None
    correlation_key: str | None
    opened_by_system: bool
    opened_at: datetime
    closed_at: datetime | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class IncidentLifecycleEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    event_type: IncidentLifecycleEventType
    from_status: IncidentStatus | None
    to_status: IncidentStatus | None
    from_severity: IncidentSeverity | None
    to_severity: IncidentSeverity | None
    actor_user_id: uuid.UUID | None
    opened_by_system: bool
    note: str | None
    payload: dict[str, Any]
    occurred_at: datetime


class IncidentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=4000)
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    related_mode: OperatingMode | None = None


class IncidentTransitionRequest(BaseModel):
    target_status: IncidentStatus
    note: str | None = Field(default=None, max_length=2000)


class IncidentSeverityChangeRequest(BaseModel):
    severity: IncidentSeverity
    note: str | None = Field(default=None, max_length=2000)


class IncidentNoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


# --- Protective actions ---


class ProtectiveActionRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action_type: ProtectiveActionType
    status: ProtectiveActionStatus
    incident_id: uuid.UUID | None
    source_service_id: uuid.UUID | None
    rationale: str
    payload: dict[str, Any]
    applied_at: datetime | None
    dismissed_at: datetime | None
    created_at: datetime
    updated_at: datetime
