from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import InstitutionalRole


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    roles: list[InstitutionalRole]
    csrf_token: str
    expires_at: datetime


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str | None
    is_active: bool
    roles: list[InstitutionalRole]
    session_expires_at: datetime


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=1024)
    email: str | None = Field(default=None, max_length=320)
    roles: list[InstitutionalRole] = Field(min_length=1)

    @field_validator("username")
    @classmethod
    def username_stripped(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("username must not be blank")
        return cleaned


class CreateUserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str | None
    roles: list[InstitutionalRole]


class AssignRoleRequest(BaseModel):
    role: InstitutionalRole


class AssignRoleResponse(BaseModel):
    user_id: uuid.UUID
    role: InstitutionalRole
