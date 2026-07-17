from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.settings import Settings, SettingsError, clear_settings_cache, get_settings
from app.db.session import reset_engine


@pytest.fixture(autouse=True)
def _clear_runtime_caches() -> Iterator[None]:
    clear_settings_cache()
    reset_engine()
    yield
    clear_settings_cache()
    reset_engine()


def test_blank_database_url_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="   ", redis_url="redis://127.0.0.1:6379/0")


def test_settings_fail_closed_when_urls_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.settings._ENV_FILE", Path("/nonexistent-argus-env"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    clear_settings_cache()
    with pytest.raises(SettingsError):
        get_settings()


def test_health_and_ready_against_local_infra() -> None:
    """Integration probe against Phase 1 Compose services when configured."""
    clear_settings_cache()
    try:
        get_settings()
    except SettingsError:
        pytest.skip("DATABASE_URL/REDIS_URL not configured")

    # Import create_app only after settings are known-good.
    from app.main import create_app

    application = create_app()
    with TestClient(application) as client:
        health = client.get("/health")
        assert health.status_code == 200
        body = health.json()
        assert body["dependencies"]["postgres"]["status"] == "ok"
        assert body["dependencies"]["redis"]["status"] == "ok"

        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"


def test_ready_returns_503_when_dependency_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://argus:bad@127.0.0.1:5432/argus")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setattr("app.core.settings._ENV_FILE", Path("/nonexistent-argus-env"))
    clear_settings_cache()
    reset_engine()

    from app.main import create_app

    application = create_app()
    with TestClient(application) as client:
        ready = client.get("/ready")
        assert ready.status_code == 503
        assert ready.json()["status"] == "not_ready"
