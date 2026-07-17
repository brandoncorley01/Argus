from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import DraftAuthority, PolicyKind, VersionLifecycleStatus


class ConfigurationDocumentCreate(BaseModel):
    document_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    description: str | None = None
    schema_identifier: str = Field(default="config.generic.v1", min_length=1, max_length=128)
    draft_authority: DraftAuthority = DraftAuthority.FOUNDER_ONLY


class ConfigurationDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_key: str
    name: str
    description: str | None
    schema_identifier: str
    is_retired: bool
    draft_authority: DraftAuthority
    created_at: datetime


class ConfigurationVersionCreate(BaseModel):
    payload: dict[str, Any]
    change_summary: str | None = None


class ConfigurationVersionUpdateDraft(BaseModel):
    payload: dict[str, Any]
    change_summary: str | None = None


class TransitionRequest(BaseModel):
    rejection_reason: str | None = None


class ConfigurationVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    version_label: str
    status: VersionLifecycleStatus
    content: dict[str, Any]
    payload_hash: str
    change_summary: str | None
    previous_version_id: uuid.UUID | None
    created_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    activated_at: datetime | None
    superseded_at: datetime | None
    rejected_at: datetime | None
    retired_at: datetime | None
    rejection_reason: str | None


class PolicyDocumentCreate(BaseModel):
    document_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    policy_kind: PolicyKind
    description: str | None = None
    schema_identifier: str = Field(default="policy.generic.v1", min_length=1, max_length=128)
    draft_authority: DraftAuthority = DraftAuthority.FOUNDER_ONLY


class PolicyDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_key: str
    name: str
    policy_kind: PolicyKind
    description: str | None
    schema_identifier: str
    is_retired: bool
    draft_authority: DraftAuthority
    created_at: datetime


class PolicyVersionCreate(BaseModel):
    payload: dict[str, Any]
    change_summary: str | None = None


class PolicyVersionUpdateDraft(BaseModel):
    payload: dict[str, Any]
    change_summary: str | None = None


class PolicyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    version_label: str
    status: VersionLifecycleStatus
    content: dict[str, Any]
    payload_hash: str
    change_summary: str | None
    previous_version_id: uuid.UUID | None
    created_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    activated_at: datetime | None
    superseded_at: datetime | None
    rejected_at: datetime | None
    retired_at: datetime | None
    rejection_reason: str | None


class VersionCompareResponse(BaseModel):
    left_id: str
    right_id: str
    left_hash: str
    right_hash: str
    added_keys: list[str]
    removed_keys: list[str]
    changed_keys: list[str]
    identical: bool
