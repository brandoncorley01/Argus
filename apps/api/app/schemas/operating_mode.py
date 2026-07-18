"""Pydantic schemas for the operating-mode state machine API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import OperatingMode


class OperatingModeStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current_mode: OperatingMode
    state_version: int
    reason: str | None
    emergency_stop_active: bool
    recovery_required: bool
    last_history_id: uuid.UUID | None
    active_policy_version_id: uuid.UUID | None
    updated_by_user_id: uuid.UUID | None
    updated_at: datetime


class OperatingModeHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_mode: OperatingMode | None
    to_mode: OperatingMode
    previous_state_version: int
    new_state_version: int
    changed_at: datetime
    changed_by_user_id: uuid.UUID | None
    reason: str | None
    request_id: str | None
    policy_version_id: uuid.UUID | None
    incident_id: uuid.UUID | None
    prerequisite_summary: dict[str, Any] | None


class TransitionRequest(BaseModel):
    target_mode: OperatingMode
    reason: str = Field(min_length=1, max_length=2000)
    incident_id: uuid.UUID | None = None
    expected_state_version: int | None = None


class EmergencyStopRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    incident_id: uuid.UUID | None = None
    expected_state_version: int | None = None


class EmergencyRecoverRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    expected_state_version: int | None = None


class TransitionResponse(BaseModel):
    current_mode: str
    previous_mode: str
    state_version: int
    previous_state_version: int
    history_id: str
    emergency_stop_active: bool
    recovery_required: bool
    reason: str
    policy_version_id: str | None = None
    idempotent_replay: bool = False


class ModeAvailabilityItem(BaseModel):
    mode: str
    enterable: bool
    required_authority: str
    blocking_codes: list[str]
    required_policy: str | None
    definitive: bool
    notes: str | None = None


class TransitionTargetItem(BaseModel):
    mode: str
    structurally_allowed: bool
    enterable: bool
    blocking_codes: list[str]


class AllowedTransitionsResponse(BaseModel):
    current_mode: str
    state_version: int
    targets: list[TransitionTargetItem]
    structural_targets: list[str]
    enterable_targets: list[str]
