"""Phase 12 paper trading tests — internal provider only, no external accounts."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.models import InstitutionalRole
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


def _bootstrap(db: Session, username: str, password: str) -> None:
    AuthService(db).bootstrap_founder(
        username=username, password=password, email=f"{username}@example.com"
    )


def _login(client: TestClient, identifier: str, password: str) -> tuple[dict, str]:
    res = client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": password}
    )
    assert res.status_code == 200, res.text
    return dict(res.cookies), res.json()["csrf_token"]


def test_default_provider_is_internal_paper(client: TestClient, db_session: Session) -> None:
    u, p = _unique("pf"), "paper-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, _ = _login(client, u, p)
    res = client.get("/api/v1/paper/providers", cookies=cookies)
    assert res.status_code == 200, res.text
    rows = res.json()
    keys = {r["provider"]["provider_key"] for r in rows}
    assert "internal_paper" in keys
    default = next(r for r in rows if r["provider"]["is_default"])
    assert default["provider"]["provider_key"] == "internal_paper"
    assert default["provider"]["environment"] == "paper"


def test_full_paper_lifecycle(client: TestClient, db_session: Session) -> None:
    u, p = _unique("pl"), "paper-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}

    port = client.post(
        "/api/v1/paper/portfolios",
        cookies=cookies,
        headers=headers,
        json={"name": "Lab Book", "initial_cash": "100000"},
    )
    assert port.status_code == 201, port.text
    pid = port.json()["id"]
    assert Decimal(port.json()["cash_balance"]) == Decimal("100000")

    sess = client.post(
        f"/api/v1/paper/portfolios/{pid}/sessions",
        cookies=cookies,
        headers=headers,
        json={"seed": 7},
    )
    assert sess.status_code == 201, sess.text
    sid = sess.json()["id"]

    order = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=cookies,
        headers={**headers, "Idempotency-Key": _unique("idem")},
        json={
            "symbol": "BTC-USD",
            "side": "buy",
            "order_type": "market",
            "quantity": "1",
            "session_id": sid,
        },
    )
    assert order.status_code == 200, order.text
    assert order.json()["status"] in {"filled", "partially_filled"}
    assert order.json()["environment"] == "paper"
    assert order.json()["provider_id"]

    positions = client.get(f"/api/v1/paper/portfolios/{pid}/positions", cookies=cookies)
    assert positions.status_code == 200
    assert len(positions.json()) >= 1
    assert positions.json()[0]["symbol"] == "BTC-USD"

    updated = client.get(f"/api/v1/paper/portfolios/{pid}", cookies=cookies)
    assert Decimal(updated.json()["cash_balance"]) < Decimal("100000")


def test_idempotent_order_submit(client: TestClient, db_session: Session) -> None:
    u, p = _unique("pi"), "paper-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": _unique("dup")}
    port = client.post(
        "/api/v1/paper/portfolios",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"name": "Idem", "initial_cash": "50000"},
    )
    pid = port.json()["id"]
    body = {"symbol": "ETH-USD", "side": "buy", "order_type": "market", "quantity": "1"}
    a = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=cookies,
        headers=headers,
        json=body,
    )
    b = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=cookies,
        headers=headers,
        json=body,
    )
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["id"] == b.json()["id"]


def test_risk_limit_and_kill_switch(client: TestClient, db_session: Session) -> None:
    u, p = _unique("pr"), "paper-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}
    port = client.post(
        "/api/v1/paper/portfolios",
        cookies=cookies,
        headers=headers,
        json={"name": "Risk", "initial_cash": "100000"},
    )
    pid = port.json()["id"]
    lim = client.post(
        f"/api/v1/paper/portfolios/{pid}/risk-limits",
        cookies=cookies,
        headers=headers,
        json={"name": "tiny notional", "limit_type": "notional", "threshold": "10"},
    )
    assert lim.status_code == 201, lim.text
    blocked = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=cookies,
        headers={**headers, "Idempotency-Key": _unique("risk")},
        json={"symbol": "BTC-USD", "side": "buy", "order_type": "market", "quantity": "1"},
    )
    assert blocked.status_code == 400

    ks = client.post(
        f"/api/v1/paper/portfolios/{pid}/kill-switch",
        cookies=cookies,
        headers=headers,
        json={"active": True},
    )
    assert ks.status_code == 200
    assert ks.json()["kill_switch_active"] is True


def test_cannot_short(client: TestClient, db_session: Session) -> None:
    u, p = _unique("ps"), "paper-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}
    port = client.post(
        "/api/v1/paper/portfolios",
        cookies=cookies,
        headers=headers,
        json={"name": "Short", "initial_cash": "100000"},
    )
    pid = port.json()["id"]
    sell = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=cookies,
        headers={**headers, "Idempotency-Key": _unique("short")},
        json={"symbol": "BTC-USD", "side": "sell", "order_type": "market", "quantity": "1"},
    )
    # Rejected by provider (short) — may be 200 with rejected status or 400
    assert sell.status_code == 200
    assert sell.json()["status"] == "rejected"
    assert sell.json()["reject_reason"] == "short_selling_forbidden"


def test_viewer_cannot_submit(client: TestClient, db_session: Session) -> None:
    founder = _unique("pvf")
    password = "paper-pass-1234"
    auth = AuthService(db_session)
    auth.bootstrap_founder(
        username=founder, password=password, email=f"{founder}@example.com"
    )
    cookies, csrf = _login(client, founder, password)
    viewer = _unique("pvv")
    created = client.post(
        "/api/v1/auth/users",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={
            "username": viewer,
            "password": "viewer-pass-1234",
            "roles": [InstitutionalRole.VIEWER.value],
        },
    )
    assert created.status_code == 201, created.text
    port = client.post(
        "/api/v1/paper/portfolios",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"name": "V", "initial_cash": "1000"},
    )
    pid = port.json()["id"]
    v_cookies, v_csrf = _login(client, viewer, "viewer-pass-1234")
    denied = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=v_cookies,
        headers={"X-CSRF-Token": v_csrf},
        json={"symbol": "BTC-USD", "side": "buy", "order_type": "market", "quantity": "1"},
    )
    assert denied.status_code == 403


def test_checkpoint_and_report(client: TestClient, db_session: Session) -> None:
    u, p = _unique("pc"), "paper-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}
    port = client.post(
        "/api/v1/paper/portfolios",
        cookies=cookies,
        headers=headers,
        json={"name": "Replay", "initial_cash": "10000"},
    )
    pid = port.json()["id"]
    sess = client.post(
        f"/api/v1/paper/portfolios/{pid}/sessions",
        cookies=cookies,
        headers=headers,
        json={"seed": 1},
    )
    sid = sess.json()["id"]
    cp = client.post(
        f"/api/v1/paper/sessions/{sid}/checkpoints",
        cookies=cookies,
        headers=headers,
    )
    assert cp.status_code == 201, cp.text
    assert cp.json()["sequence_number"] == 1
    rep = client.post(
        f"/api/v1/paper/portfolios/{pid}/reports",
        cookies=cookies,
        headers=headers,
        json={"report_type": "account_statement"},
    )
    assert rep.status_code == 201, rep.text
    assert rep.json()["is_immutable"] is True
    assert "disclaimer" in rep.json()["content"]
