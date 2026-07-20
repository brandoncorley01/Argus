"""Phase 14 Treasury and Executive Analytics tests — simulated ledgers only.

These tests prove: only simulated/paper capital ever exists, external
transfer execution is always refused (never merely "not yet implemented"
by accident — structurally forbidden), attribution/KPI/report data is
always evidence-backed and environment-labeled, and paper results are
never silently combined with (nonexistent) live results.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.models import InstitutionalRole
from app.models.paper_trading import ExecutionProvider, PaperFill, PaperOrder, PaperPortfolio
from app.services.auth_service import AuthService
from app.services.payload_integrity import hash_payload


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


def _make_viewer(client: TestClient, founder_cookies: dict, founder_csrf: str) -> tuple[str, str]:
    viewer = _unique("treasviewer")
    password = "viewer-pass-1234"
    created = client.post(
        "/api/v1/auth/users",
        cookies=founder_cookies,
        headers={"X-CSRF-Token": founder_csrf},
        json={
            "username": viewer,
            "password": password,
            "roles": [InstitutionalRole.VIEWER.value],
        },
    )
    assert created.status_code == 201, created.text
    return viewer, password


def _seed_paper_fill(db: Session, *, quantity: str, price: str, fee: str) -> tuple[str, str]:
    """Direct DB insertion of a minimal paper portfolio/order/fill for
    attribution tests — no HTTP order-placement flow is required here."""
    provider = db.scalar(
        select(ExecutionProvider).where(ExecutionProvider.provider_key == "internal_paper")
    )
    assert provider is not None, "internal_paper provider must be seeded"

    username = _unique("treaspaper")
    auth = AuthService(db)
    auth.bootstrap_founder(
        username=username, password="paper-pass-1234", email=f"{username}@example.com"
    )
    db.commit()
    from app.models import User

    user = db.scalar(select(User).where(User.username == username))
    assert user is not None

    portfolio = PaperPortfolio(
        name=_unique("treas-portfolio"),
        currency="USD",
        cash_balance=Decimal("10000"),
        status="active",
        default_provider_id=provider.id,
        owner_user_id=user.id,
    )
    db.add(portfolio)
    db.flush()

    order = PaperOrder(
        portfolio_id=portfolio.id,
        provider_id=provider.id,
        client_order_id=_unique("client-order"),
        idempotency_key=_unique("idem"),
        symbol="BTC-USD",
        side="buy",
        order_type="market",
        quantity=Decimal(quantity),
        status="filled",
        environment="paper",
        created_by_user_id=user.id,
    )
    db.add(order)
    db.flush()

    fill = PaperFill(
        order_id=order.id,
        portfolio_id=portfolio.id,
        provider_id=provider.id,
        provider_fill_id=_unique("fill"),
        symbol="BTC-USD",
        side="buy",
        quantity=Decimal(quantity),
        price=Decimal(price),
        fee=Decimal(fee),
        filled_at=datetime.now(UTC),
    )
    db.add(fill)
    db.commit()
    return str(portfolio.id), str(order.id)


# --- accounts ------------------------------------------------------------


def test_simulated_account_seeded(client: TestClient, db_session: Session) -> None:
    u, p = _unique("treas"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, _ = _login(client, u, p)

    res = client.get("/api/v1/treasury/accounts", cookies=cookies)
    assert res.status_code == 200, res.text
    accounts = res.json()
    seeded = next((a for a in accounts if a["name"] == "Paper Institutional Capital"), None)
    assert seeded is not None
    assert seeded["classification"] == "simulated"
    assert seeded["is_simulated"] is True


def test_account_creatable_by_founder_and_always_simulated(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("treasf"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)

    name = _unique("Test Treasury Account")
    res = client.post(
        "/api/v1/treasury/accounts",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"name": name, "currency": "USD", "classification": "available"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["is_simulated"] is True
    assert body["balance"] == "0.00000000" or float(body["balance"]) == 0.0


def test_viewer_cannot_create_account(client: TestClient, db_session: Session) -> None:
    u, p = _unique("treasfv"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    f_cookies, f_csrf = _login(client, u, p)
    viewer, viewer_password = _make_viewer(client, f_cookies, f_csrf)
    v_cookies, v_csrf = _login(client, viewer, viewer_password)

    res = client.post(
        "/api/v1/treasury/accounts",
        cookies=v_cookies,
        headers={"X-CSRF-Token": v_csrf},
        json={"name": _unique("viewer-account"), "currency": "USD", "classification": "available"},
    )
    assert res.status_code == 403


# --- allocations / reservations ------------------------------------------


def _setup_pool_with_funds(
    client: TestClient, cookies: dict, csrf: str, *, amount: str = "1000"
) -> tuple[str, str]:
    headers = {"X-CSRF-Token": csrf}
    account_name = _unique("Alloc Account")
    account = client.post(
        "/api/v1/treasury/accounts",
        cookies=cookies,
        headers=headers,
        json={"name": account_name, "currency": "USD", "classification": "available"},
    )
    assert account.status_code == 201, account.text
    account_id = account.json()["id"]

    funded = client.post(
        f"/api/v1/treasury/accounts/{account_id}/fund-simulated",
        cookies=cookies,
        headers=headers,
        json={"amount": amount, "note": "test funding"},
    )
    assert funded.status_code == 200, funded.text

    pool = client.post(
        "/api/v1/treasury/pools",
        cookies=cookies,
        headers=headers,
        json={"account_id": account_id, "name": _unique("Pool"), "pool_type": "strategy_reserve"},
    )
    assert pool.status_code == 201, pool.text
    return account_id, pool.json()["id"]


def test_allocation_request_and_founder_approve(client: TestClient, db_session: Session) -> None:
    u, p = _unique("treasa"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}
    account_id, pool_id = _setup_pool_with_funds(client, cookies, csrf, amount="1000")

    requested = client.post(
        "/api/v1/treasury/allocations",
        cookies=cookies,
        headers=headers,
        json={
            "pool_id": pool_id,
            "target_type": "strategy",
            "target_id": str(_uuid.uuid4()),
            "amount": "250",
        },
    )
    assert requested.status_code == 201, requested.text
    allocation_id = requested.json()["id"]
    assert requested.json()["status"] == "requested"

    approved = client.post(
        f"/api/v1/treasury/allocations/{allocation_id}/approve", cookies=cookies, headers=headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    reserved = client.post(
        f"/api/v1/treasury/allocations/{allocation_id}/reserve", cookies=cookies, headers=headers
    )
    assert reserved.status_code == 200, reserved.text
    assert reserved.json()["status"] == "active"

    ledger = client.get(
        f"/api/v1/treasury/ledger?account_id={account_id}", cookies=cookies
    )
    assert ledger.status_code == 200, ledger.text
    entry_types = {e["entry_type"] for e in ledger.json()}
    assert "allocation_reserved" in entry_types
    assert "deposit_simulated" in entry_types

    released = client.post(
        f"/api/v1/treasury/allocations/{allocation_id}/release", cookies=cookies, headers=headers
    )
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "released"

    account_after = client.get(f"/api/v1/treasury/accounts/{account_id}", cookies=cookies)
    assert Decimal(account_after.json()["balance"]) == Decimal("1000")


def test_viewer_cannot_approve_allocation(client: TestClient, db_session: Session) -> None:
    u, p = _unique("treasva"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    f_cookies, f_csrf = _login(client, u, p)
    _account_id, pool_id = _setup_pool_with_funds(client, f_cookies, f_csrf, amount="500")

    requested = client.post(
        "/api/v1/treasury/allocations",
        cookies=f_cookies,
        headers={"X-CSRF-Token": f_csrf},
        json={
            "pool_id": pool_id,
            "target_type": "portfolio",
            "target_id": str(_uuid.uuid4()),
            "amount": "100",
        },
    )
    assert requested.status_code == 201, requested.text
    allocation_id = requested.json()["id"]

    viewer, viewer_password = _make_viewer(client, f_cookies, f_csrf)
    v_cookies, v_csrf = _login(client, viewer, viewer_password)
    denied = client.post(
        f"/api/v1/treasury/allocations/{allocation_id}/approve",
        cookies=v_cookies,
        headers={"X-CSRF-Token": v_csrf},
    )
    assert denied.status_code == 403


# --- external transfers (never executed) ---------------------------------


def test_external_transfer_execute_is_always_forbidden(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("treast"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}
    account_id, _pool_id = _setup_pool_with_funds(client, cookies, csrf, amount="200")

    created = client.post(
        "/api/v1/treasury/external-transfers",
        cookies=cookies,
        headers=headers,
        json={
            "account_id": account_id,
            "direction": "outbound",
            "amount": "50",
            "currency": "USD",
            "destination_reference": "external-bank-ref-placeholder",
        },
    )
    assert created.status_code == 201, created.text
    instruction_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    proposed = client.post(
        f"/api/v1/treasury/external-transfers/{instruction_id}/propose",
        cookies=cookies,
        headers=headers,
    )
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["status"] == "proposed"

    blocked = client.post(
        f"/api/v1/treasury/external-transfers/{instruction_id}/execute",
        cookies=cookies,
        headers=headers,
    )
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["detail"]["code"] == "external_transfer_execution_forbidden"

    current = client.get(
        f"/api/v1/treasury/external-transfers/{instruction_id}", cookies=cookies
    )
    assert current.status_code == 200, current.text
    body = current.json()
    assert body["status"] in ("draft", "proposed", "cancelled")
    assert body["status"] != "executed"
    assert body["execution_attempt_count"] >= 1
    assert body["blocked_reason"] is not None


def test_external_transfer_status_enum_has_no_executed_state(
    client: TestClient, db_session: Session
) -> None:
    from app.models.treasury import ExternalTransferStatus

    values = {member.value for member in ExternalTransferStatus}
    assert values == {"draft", "proposed", "cancelled"}
    assert "executed" not in values
    assert "completed" not in values


# --- attribution -----------------------------------------------------------


def test_attribution_from_paper_data_labeled_paper(client: TestClient, db_session: Session) -> None:
    portfolio_id, _order_id = _seed_paper_fill(db_session, quantity="1.5", price="20000", fee="5")

    u, p = _unique("treasat"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)

    res = client.post(
        "/api/v1/treasury/attribution/generate",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"scope": "portfolio", "scope_ref": portfolio_id, "environment_class": "paper"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["environment_class"] == "paper"
    assert body["is_available"] is True
    assert Decimal(body["amounts"]["gross_notional"]) == Decimal("1.5") * Decimal("20000")
    assert len(body["evidence_refs"]) > 0


def test_attribution_live_environment_is_explicitly_unavailable(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("treasal"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)

    res = client.post(
        "/api/v1/treasury/attribution/generate",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"scope": "portfolio", "scope_ref": None, "environment_class": "live"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["environment_class"] == "live"
    assert body["is_available"] is False
    assert body["amounts"] == {}
    assert body["unavailable_reason"] is not None
    assert "live" in body["unavailable_reason"].lower()


# --- KPIs --------------------------------------------------------------------


def test_kpi_snapshot_is_evidence_backed(client: TestClient, db_session: Session) -> None:
    u, p = _unique("treask"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)

    res = client.post(
        "/api/v1/treasury/kpis/generate", cookies=cookies, headers={"X-CSRF-Token": csrf}
    )
    assert res.status_code == 201, res.text
    rows = res.json()
    assert len(rows) > 0
    for row in rows:
        assert isinstance(row["evidence_refs"], list)
        assert len(row["evidence_refs"]) > 0
        assert row["environment_class"] in ("paper", "sandbox", "testnet", "live", "simulated")

    listing = client.get("/api/v1/treasury/kpis", cookies=cookies)
    assert listing.status_code == 200, listing.text
    assert len(listing.json()) >= len(rows)


def test_viewer_cannot_generate_kpis(client: TestClient, db_session: Session) -> None:
    u, p = _unique("treaskv"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    f_cookies, f_csrf = _login(client, u, p)
    viewer, viewer_password = _make_viewer(client, f_cookies, f_csrf)
    v_cookies, v_csrf = _login(client, viewer, viewer_password)

    denied = client.post(
        "/api/v1/treasury/kpis/generate", cookies=v_cookies, headers={"X-CSRF-Token": v_csrf}
    )
    assert denied.status_code == 403


# --- forecasts ---------------------------------------------------------------


def test_forecast_scenario_is_deterministic(client: TestClient, db_session: Session) -> None:
    u, p = _unique("treasfc"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)

    res = client.post(
        "/api/v1/treasury/forecasts",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "test cash flow",
            "scenario_type": "cash_flow",
            "inputs": {"starting_balance": "1000", "periods": 3, "net_flow_per_period": "10"},
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["outputs"]["ending_balance"] == "1030"
    assert body["outputs"]["projected_balances"] == ["1010", "1020", "1030"]
    assert "assumption_note" in body["outputs"]


# --- reports -----------------------------------------------------------------


def test_report_is_immutable_and_hashed(client: TestClient, db_session: Session) -> None:
    u, p = _unique("treasr"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)

    res = client.post(
        "/api/v1/treasury/reports/generate",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"report_type": "daily_brief"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["is_immutable"] is True
    assert body["content_hash"] == hash_payload(body["content"])
    assert "paper" in body["environment_disclaimer"].lower()
    assert "live" in body["environment_disclaimer"].lower()
    assert body["content"]["live"]["available"] is False

    res2 = client.post(
        "/api/v1/treasury/reports/generate",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
        json={"report_type": "daily_brief"},
    )
    assert res2.status_code == 201, res2.text
    assert res2.json()["version"] == body["version"] + 1


# --- summary: paper vs live separation ----------------------------------------


def test_summary_separates_paper_and_live(client: TestClient, db_session: Session) -> None:
    u, p = _unique("treassum"), "treasury-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, _ = _login(client, u, p)

    res = client.get("/api/v1/treasury/summary", cookies=cookies)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["live_available"] is False
    assert "live" in body["live_unavailable_reason"].lower()
    assert body["external_transfer_executed_count"] == 0
    assert "simulated" in body["disclaimer"].lower()
    for kpi in body["latest_kpis"]:
        assert kpi["environment_class"] in ("paper", "sandbox", "testnet", "live", "simulated")
    for snap in body["latest_paper_attribution"]:
        assert snap["environment_class"] == "paper"
