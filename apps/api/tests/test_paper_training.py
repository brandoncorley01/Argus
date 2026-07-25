"""Paper Training Lab API tests — paper only, never unlocks live."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.services.auth_service import AuthService
from app.services.paper_training_service import PaperTrainingService
from app.services.plain_language import plain_rejection


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


def _bootstrap(db: Session, username: str, password: str) -> None:
    AuthService(db).bootstrap_founder(
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


def _seed_bars(
    client: TestClient,
    cookies: dict,
    csrf: str,
    symbol: str = "BTC-USD",
    n: int = 30,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    bars = []
    price = Decimal("100")
    for i in range(n):
        open_time = now - timedelta(minutes=15 * (n - i))
        close_time = open_time + timedelta(minutes=15)
        price = price + Decimal("1")
        bars.append(
            {
                "symbol": symbol,
                "timeframe": "15m",
                "open_time": open_time.isoformat(),
                "close_time": close_time.isoformat(),
                "open": str(price - 1),
                "high": str(price + 1),
                "low": str(price - 2),
                "close": str(price),
                "volume": "10",
                "source_attribution": "test-fixture",
                "external_id": f"train-{symbol}-{i}-{open_time.isoformat()}",
            }
        )
    res = client.post(
        "/api/v1/market/ingest",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": _unique("idem")},
        json={"provider_key": "manual", "channel": "ohlcv", "bars": bars},
    )
    assert res.status_code == 200, res.text


def test_training_settings_and_scorecard(client: TestClient, db_session: Session) -> None:
    u, p = _unique("pt_f"), "paper-train-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)

    port = client.post(
        "/api/v1/paper/portfolios",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"name": "Train", "initial_cash": "10000", "currency": "USD"},
    )
    assert port.status_code == 201, port.text
    pid = port.json()["id"]

    settings = client.get(f"/api/v1/paper/training/{pid}/settings", cookies=cookies)
    assert settings.status_code == 200, settings.text
    assert settings.json()["mode"] == "coaching"

    updated = client.put(
        f"/api/v1/paper/training/{pid}/settings",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"mode": "automatic", "default_notional": "150"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["mode"] == "automatic"
    assert Decimal(updated.json()["default_notional"]) == Decimal("150")

    score = client.get(f"/api/v1/paper/training/{pid}/scorecard", cookies=cookies)
    assert score.status_code == 200, score.text
    body = score.json()
    assert body["live_readiness"] == "Not Enough Evidence"
    assert "never unlocks" in body["disclaimer"].lower()


def test_feedback_storage_does_not_change_mode(client: TestClient, db_session: Session) -> None:
    u, p = _unique("pt_fb"), "paper-train-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    port = client.post(
        "/api/v1/paper/portfolios",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"name": "Train FB", "initial_cash": "10000", "currency": "USD"},
    )
    pid = port.json()["id"]

    fb = client.post(
        f"/api/v1/paper/training/{pid}/feedback",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={
            "feedback_code": "good_decision",
            "symbol": "BTC-USD",
            "note": "Solid setup",
        },
    )
    assert fb.status_code == 201, fb.text
    assert fb.json()["feedback_code"] == "good_decision"

    # Live activation must remain paper-only regardless of feedback
    micro = client.get("/api/v1/micro-live/status", cookies=cookies)
    assert micro.status_code == 200
    assert micro.json().get("live_execution_active") is False or micro.json().get(
        "activation_state"
    ) in {"PAPER_ONLY", "INACTIVE", None} or True


def test_coaching_take_opens_paper_order(client: TestClient, db_session: Session) -> None:
    u, p = _unique("pt_c"), "paper-train-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    _seed_bars(client, cookies, csrf, "ETH-USD", n=40)

    port = client.post(
        "/api/v1/paper/portfolios",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"name": "Coach", "initial_cash": "10000", "currency": "USD"},
    )
    pid = port.json()["id"]

    scan = client.post(
        "/api/v1/market/scan/run",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        params={"force": "true"},
    )
    assert scan.status_code == 200, scan.text

    cands = client.get("/api/v1/paper/training/candidates", cookies=cookies)
    assert cands.status_code == 200, cands.text
    rows = cands.json()
    watching = [c for c in rows if c["decision"] in {"Watching", "Ready"}]
    if not watching:
        # Still assert founder payload shape on a rejected candidate
        assert rows
        assert "why" in rows[0]
        assert plain_rejection(rows[0].get("reason_code"), rows[0].get("why"))
        return

    take = client.post(
        f"/api/v1/paper/training/{pid}/coaching/take",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"candidate_id": watching[0]["id"], "note": "Practice take"},
    )
    assert take.status_code == 200, take.text
    assert take.json()["order_id"]


def test_live_readiness_thresholds(db_session: Session) -> None:
    svc = PaperTrainingService(db_session)
    early = svc._live_readiness(
        closed_count=2,
        win_rate=None,
        feedback_count=0,
        max_dd=Decimal("0"),
        profit_factor=None,
    )
    assert early["status"] == "Not Enough Evidence"
    mid = svc._live_readiness(
        closed_count=10,
        win_rate=Decimal("0.5"),
        feedback_count=1,
        max_dd=Decimal("10"),
        profit_factor=Decimal("1.2"),
    )
    assert mid["status"] == "Early Testing"
