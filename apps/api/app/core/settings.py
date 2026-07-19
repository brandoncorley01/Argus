from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/app/core/settings.py -> repo root is parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime settings. Missing required values fail closed at load time."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Argus API")
    app_env: str = Field(default="development")
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)

    database_url: str
    redis_url: str

    session_cookie_name: str = Field(default="argus_session")
    csrf_header_name: str = Field(default="X-CSRF-Token")
    session_ttl_hours: int = Field(default=8, ge=1, le=168)
    session_cookie_secure: bool = Field(default=False)
    session_cookie_samesite: str = Field(default="lax")
    session_cookie_path: str = Field(default="/")

    login_max_failures: int = Field(default=5, ge=1, le=50)
    login_failure_window_minutes: int = Field(default=15, ge=1, le=1440)
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)

    allow_additional_founders: bool = Field(default=False)

    health_supervisor_lease_seconds: int = Field(default=45, ge=5, le=600)
    health_supervisor_failure_threshold: int = Field(default=3, ge=1, le=100)

    @field_validator("database_url", "redis_url")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("session_cookie_samesite")
    @classmethod
    def samesite_must_be_valid(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("session_cookie_samesite must be lax, strict, or none")
        return normalized


class SettingsError(RuntimeError):
    """Raised when institutional settings cannot be loaded safely."""


@lru_cache
def get_settings() -> Settings:
    try:
        # pydantic-settings accepts runtime `_env_file`; typed constructors omit it.
        settings_cls: Any = Settings
        return cast(
            Settings,
            settings_cls(_env_file=_ENV_FILE if _ENV_FILE.exists() else None),
        )
    except ValidationError as exc:
        raise SettingsError(
            "Argus API settings failed closed: required configuration is missing or invalid. "
            "Ensure DATABASE_URL and REDIS_URL are set in the environment or repo-root .env."
        ) from exc


def clear_settings_cache() -> None:
    get_settings.cache_clear()
