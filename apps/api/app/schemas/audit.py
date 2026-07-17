from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import OperatingMode


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    request_id: str | None
    mode_at_time: OperatingMode | None
    config_version_id: uuid.UUID | None
    policy_version_id: uuid.UUID | None
    payload: dict[str, Any] | None
    created_at: datetime


class AuditEventListResponse(BaseModel):
    items: list[AuditEventRead]
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
