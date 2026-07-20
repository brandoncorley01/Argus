"""Phase 10 Market Intelligence tests — observation only, no fabricated live prices."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.services.auth_service import AuthService


@pytest.fixture(autouse=True)
def _allow_additional_founders(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ALLOW_ADDITIONAL_FOUNDERS", "true")
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def db_session() -> Iterator[Session]:
    clear_settings_cache()
    reset_engine()
    get_settings()
    session = get_session_factory()()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
        reset_engine()
        clear_settings_cache()


@pytest.fixture
def client() -> Iterator[TestClient]:
    clear_settings_cache()
    reset_engine()
    get_settings()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    reset_engine()
    clear_settings_cache()


def _unique(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%H%M%S%f')}"


def _bootstrap_founder(db_session: Session, username: str, password: str) -> None:
    AuthService(db_session).bootstrap_founder(
        username=username,
        password=password,
        email=f"{username}@example.com",
    )


def _login(client: TestClient, identifier: str, password: str) -> tuple[dict[str, str], str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert response.status_code == 200, response.text
    return dict(response.cookies), response.json()["csrf_token"]


def test_list_seeded_providers(client: TestClient, db_session: Session) -> None:
    username = _unique("mkt_f")
    password = "market-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, _ = _login(client, username, password)

    res = client.get("/api/v1/market/providers", cookies=cookies)
    assert res.status_code == 200, res.text
    keys = {row["provider"]["provider_key"] for row in res.json()}
    assert "manual" in keys
    assert "null_probe" in keys


def test_manual_ingest_replay_safe(client: TestClient, db_session: Session) -> None:
    username = _unique("mkt_i")
    password = "market-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, csrf = _login(client, username, password)

    open_time = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    payload = {
        "provider_key": "manual",
        "channel": "ohlcv",
        "bars": [
            {
                "symbol": "BTC-USD",
                "timeframe": "1h",
                "open_time": open_time.isoformat(),
                "close_time": (open_time + timedelta(hours=1)).isoformat(),
                "open": "100",
                "high": "110",
                "low": "90",
                "close": "105",
                "volume": "1.5",
                "source_attribution": "manual-operator-entry",
                "external_id": f"bar-{open_time.isoformat()}",
            }
        ],
        "news": [
            {
                "external_id": f"news-{_unique('n')}",
                "headline": "Observation note only",
                "published_at": datetime.now(UTC).isoformat(),
                "source_attribution": "manual-desk",
            }
        ],
    }

    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": _unique("idem")}
    first = client.post(
        "/api/v1/market/ingest", json=payload, cookies=cookies, headers=headers
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["records_accepted"] >= 2
    assert body["idempotent_replay"] is False

    second = client.post(
        "/api/v1/market/ingest", json=payload, cookies=cookies, headers=headers
    )
    assert second.status_code == 200, second.text
    assert second.json()["idempotent_replay"] is True

    bars = client.get("/api/v1/market/bars?symbol=BTC-USD", cookies=cookies)
    assert bars.status_code == 200
    assert len(bars.json()) >= 1
    # Honesty: values match what was ingested, not invented by a feed
    assert bars.json()[0]["source_attribution"] == "manual-operator-entry"


def test_null_probe_does_not_emit_prices(client: TestClient, db_session: Session) -> None:
    username = _unique("mkt_p")
    password = "market-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, csrf = _login(client, username, password)

    res = client.post(
        "/api/v1/market/providers/null_probe/probe",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "healthy"
    assert res.json()["detail"].get("emits_data") is False


def test_viewer_cannot_ingest(client: TestClient, db_session: Session) -> None:
    from app.models import InstitutionalRole

    founder = _unique("mkt_fv")
    password = "market-pass-1234"
    auth = AuthService(db_session)
    founder_user = auth.bootstrap_founder(
        username=founder, password=password, email=f"{founder}@example.com"
    )
    viewer_name = _unique("mkt_v")
    # create viewer via founder session
    cookies, csrf = _login(client, founder, password)
    create = client.post(
        "/api/v1/auth/users",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={
            "username": viewer_name,
            "password": "viewer-pass-1234",
            "roles": [InstitutionalRole.VIEWER.value],
        },
    )
    assert create.status_code == 201, create.text

    v_cookies, v_csrf = _login(client, viewer_name, "viewer-pass-1234")
    denied = client.post(
        "/api/v1/market/ingest",
        cookies=v_cookies,
        headers={"X-CSRF-Token": v_csrf},
        json={"provider_key": "manual", "channel": "news", "news": []},
    )
    assert denied.status_code == 403
    _ = founder_user
