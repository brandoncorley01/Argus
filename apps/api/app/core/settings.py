from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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

    @field_validator("database_url", "redis_url")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class SettingsError(RuntimeError):
    """Raised when institutional settings cannot be loaded safely."""


@lru_cache
def get_settings() -> Settings:
    try:
        if _ENV_FILE.exists():
            return Settings(_env_file=_ENV_FILE)
        return Settings(_env_file=None)
    except ValidationError as exc:
        raise SettingsError(
            "Argus API settings failed closed: required configuration is missing or invalid. "
            "Ensure DATABASE_URL and REDIS_URL are set in the environment or repo-root .env."
        ) from exc


def clear_settings_cache() -> None:
    get_settings.cache_clear()
