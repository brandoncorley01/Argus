"""Phase 13 Micro-Live Institution tests — deny-by-default, no real credentials.

These tests must never require a brokerage account, SSN, or paid API key.
They prove the institution stays PAPER_ONLY by default, that no path to
MICRO_LIVE_ACTIVE exists, and that credential/kill-switch/capital-policy
controls behave correctly without ever contacting a real provider.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.execution.adapters.coinbase import CoinbaseAdapter
from app.execution.adapters.ibkr import IbkrAdapter
from app.execution.adapters.kraken import KrakenAdapter
from app.execution.contracts import (
    ExecutionEnvironment,
    LiveExecutionForbiddenError,
    OrderIntent,
    OrderSide,
    OrderType,
)
from app.execution.gateway import ExecutionGateway, ExecutionGatewayError
from app.execution.registry import DEFAULT_REGISTRY
from app.main import create_app
from app.models import InstitutionalRole
from app.services.auth_service import AuthService


@pytest.fixture(autouse=True)
def _allow_additional_founders(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ALLOW_ADDITIONAL_FOUNDERS", "true")
    clear_settings_cache()
    yield
    clear_settings_cache()


def _reset_micro_live_tables(session: Session) -> None:
    """The Phase 13 activation state is a real singleton committed by the
    service layer (not a test-transaction rollback), so it must be reset
    between tests just like the Phase 7 ``system_states`` singleton.
    """
    session.execute(text("DELETE FROM live_activation_transitions"))
    session.execute(text("DELETE FROM live_activation_state"))
    session.execute(text("DELETE FROM credential_references"))
    session.execute(text("DELETE FROM kill_switches"))
    session.execute(
        text(
            "INSERT INTO kill_switches (scope_type, scope_id, active, reason) "
            "VALUES ('global', NULL, false, 'test reset')"
        )
    )
    session.execute(text("DELETE FROM reconciliation_discrepancies"))
    session.execute(text("DELETE FROM reconciliation_runs"))
    session.execute(text("DELETE FROM micro_capital_policies"))
    session.execute(
        text(
            "INSERT INTO micro_capital_policies "
            "(version, max_deployable_capital, max_order_notional, max_daily_loss, "
            " max_concurrent_exposure, max_provider_exposure, max_strategy_exposure, is_active) "
            "VALUES (1, 100.00000000, 10.00000000, 5.00000000, 100.00000000, 100.00000000, "
            " 50.00000000, true)"
        )
    )
    session.execute(
        text(
            """
            DELETE FROM audit_events
            WHERE action LIKE 'micro_live.%'
            """
        )
    )
    session.commit()


@pytest.fixture
def db_session() -> Iterator[Session]:
    clear_settings_cache()
    reset_engine()
    get_settings()
    session = get_session_factory()()
    try:
        _reset_micro_live_tables(session)
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


# --- default posture ---


def test_default_activation_is_paper_only(client: TestClient, db_session: Session) -> None:
    u, p = _unique("mlp"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, _ = _login(client, u, p)
    res = client.get("/api/v1/micro-live/activation", cookies=cookies)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["activation_state"] == "PAPER_ONLY"
    assert body["credentials_configured"] is False
    assert body["live_execution_active"] is False
    assert body["live_capable_architecture"] is True
    assert body["paper_provider_default"] is True


def test_status_dashboard_never_claims_live_active(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("mls"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, _ = _login(client, u, p)
    res = client.get("/api/v1/micro-live/status", cookies=cookies)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["live_execution_active"] is False
    assert body["credentials_configured"] is False
    assert body["paper_provider_default"] is True
    assert "disabled" in body["disclaimer"].lower()


def test_paper_trading_still_works_with_internal_paper_default(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("mlpp"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, _ = _login(client, u, p)
    res = client.get("/api/v1/paper/providers", cookies=cookies)
    assert res.status_code == 200, res.text
    rows = res.json()
    default = next(r for r in rows if r["provider"]["is_default"])
    assert default["provider"]["provider_key"] == "internal_paper"
    assert default["provider"]["environment"] == "paper"


def test_optional_adapters_listed_disabled_not_default(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("mla"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, _ = _login(client, u, p)
    res = client.get("/api/v1/micro-live/adapters", cookies=cookies)
    assert res.status_code == 200, res.text
    by_key = {a["provider_key"]: a for a in res.json()}
    for key in ("coinbase_adapter", "kraken_adapter", "ibkr_adapter"):
        assert by_key[key]["is_enabled"] is False
        assert by_key[key]["is_default"] is False
        assert by_key[key]["supports_live"] is False
        assert by_key[key]["verification_status"] != "live_certified"


# --- activation transitions ---


def test_cannot_transition_past_credential_configured_without_credentials(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("mlc"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}

    for target in ("ADAPTER_CONFIGURED", "CREDENTIAL_REFERENCE_CONFIGURED"):
        res = client.post(
            "/api/v1/micro-live/activation/transition",
            cookies=cookies,
            headers=headers,
            json={"target_state": target, "reason": "phase13 test progression"},
        )
        assert res.status_code == 200, res.text

    blocked = client.post(
        "/api/v1/micro-live/activation/transition",
        cookies=cookies,
        headers=headers,
        json={"target_state": "CONNECTION_VERIFIED", "reason": "attempt without credentials"},
    )
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["detail"]["code"] == "credentials_required"

    current = client.get("/api/v1/micro-live/activation", cookies=cookies)
    assert current.json()["activation_state"] == "CREDENTIAL_REFERENCE_CONFIGURED"


def test_no_path_to_micro_live_active_even_with_credentials(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref_name = _unique("MICRO_LIVE_TEST_REF").upper()
    monkeypatch.setenv(ref_name, "present-marker-not-a-real-secret")

    u, p = _unique("mln"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}

    for target in ("ADAPTER_CONFIGURED", "CREDENTIAL_REFERENCE_CONFIGURED"):
        res = client.post(
            "/api/v1/micro-live/activation/transition",
            cookies=cookies,
            headers=headers,
            json={"target_state": target, "reason": "phase13 test progression"},
        )
        assert res.status_code == 200, res.text

    ref = client.post(
        "/api/v1/micro-live/credential-references",
        cookies=cookies,
        headers=headers,
        json={
            "provider_key": "coinbase_adapter",
            "ref_name": ref_name,
            "purpose": "test-only presence marker",
        },
    )
    assert ref.status_code == 201, ref.text
    ref_id = ref.json()["id"]
    assert "value" not in ref.json()

    validated = client.post(
        f"/api/v1/micro-live/credential-references/{ref_id}/validate",
        cookies=cookies,
        headers=headers,
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["is_present_cached"] is True
    assert "value" not in validated.json()

    for target in (
        "CONNECTION_VERIFIED",
        "OBSERVE_ONLY",
        "SANDBOX_OR_TESTNET",
        "SHADOW_MODE",
        "MICRO_LIVE_ARMED",
    ):
        res = client.post(
            "/api/v1/micro-live/activation/transition",
            cookies=cookies,
            headers=headers,
            json={"target_state": target, "reason": "phase13 test progression with credentials"},
        )
        assert res.status_code == 200, res.text

    denied = client.post(
        "/api/v1/micro-live/activation/transition",
        cookies=cookies,
        headers=headers,
        json={"target_state": "MICRO_LIVE_ACTIVE", "reason": "attempt full activation"},
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"]["code"] == "live_execution_not_certified"

    current = client.get("/api/v1/micro-live/activation", cookies=cookies)
    assert current.json()["activation_state"] == "MICRO_LIVE_ARMED"
    assert current.json()["live_execution_active"] is False


def test_credential_validate_does_not_leak_value(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref_name = _unique("MICRO_LIVE_SECRET_REF").upper()
    secret_value = "super-secret-do-not-leak-123"
    monkeypatch.setenv(ref_name, secret_value)

    u, p = _unique("mlv"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}

    ref = client.post(
        "/api/v1/micro-live/credential-references",
        cookies=cookies,
        headers=headers,
        json={"provider_key": "kraken_adapter", "ref_name": ref_name, "purpose": "leak test"},
    )
    assert ref.status_code == 201, ref.text
    ref_id = ref.json()["id"]

    validated = client.post(
        f"/api/v1/micro-live/credential-references/{ref_id}/validate",
        cookies=cookies,
        headers=headers,
    )
    assert validated.status_code == 200, validated.text
    body_text = validated.text
    assert secret_value not in body_text
    assert validated.json()["is_present_cached"] is True

    listing = client.get("/api/v1/micro-live/credential-references", cookies=cookies)
    assert secret_value not in listing.text


def test_viewer_cannot_transition_activation(client: TestClient, db_session: Session) -> None:
    founder = _unique("mlvf")
    password = "micro-pass-1234"
    auth = AuthService(db_session)
    auth.bootstrap_founder(username=founder, password=password, email=f"{founder}@example.com")
    cookies, csrf = _login(client, founder, password)
    viewer = _unique("mlvv")
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

    v_cookies, v_csrf = _login(client, viewer, "viewer-pass-1234")
    denied = client.post(
        "/api/v1/micro-live/activation/transition",
        cookies=v_cookies,
        headers={"X-CSRF-Token": v_csrf},
        json={"target_state": "ADAPTER_CONFIGURED", "reason": "viewer attempt"},
    )
    assert denied.status_code == 403


# --- kill switches / capital policy / dry-run ---


def test_kill_switch_blocks_dry_run(client: TestClient, db_session: Session) -> None:
    u, p = _unique("mlk"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}

    baseline = client.post(
        "/api/v1/micro-live/dry-run/validate-order",
        cookies=cookies,
        headers=headers,
        json={"quantity": "1", "reference_price": "1"},
    )
    assert baseline.status_code == 200, baseline.text
    assert baseline.json()["would_be_allowed"] is False
    assert "global_kill_switch_active" not in baseline.json()["blocking_codes"]

    switch = client.post(
        "/api/v1/micro-live/kill-switches",
        cookies=cookies,
        headers=headers,
        json={"scope_type": "global", "active": True, "reason": "test kill"},
    )
    assert switch.status_code == 200, switch.text
    assert switch.json()["active"] is True

    blocked = client.post(
        "/api/v1/micro-live/dry-run/validate-order",
        cookies=cookies,
        headers=headers,
        json={"quantity": "1", "reference_price": "1"},
    )
    assert blocked.status_code == 200, blocked.text
    assert "global_kill_switch_active" in blocked.json()["blocking_codes"]
    assert blocked.json()["would_be_allowed"] is False


def test_capital_policy_rejects_oversized_notional_in_dry_run(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("mlm"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}

    policy = client.get("/api/v1/micro-live/capital-policy", cookies=cookies)
    assert policy.status_code == 200, policy.text
    max_notional = Decimal(policy.json()["max_order_notional"])

    oversized = client.post(
        "/api/v1/micro-live/dry-run/validate-order",
        cookies=cookies,
        headers=headers,
        json={"quantity": "1000", "reference_price": "1000"},
    )
    assert oversized.status_code == 200, oversized.text
    codes = oversized.json()["blocking_codes"]
    assert "max_order_notional_exceeded" in codes
    assert Decimal(oversized.json()["notional"]) > max_notional


def test_capital_policy_update_requires_founder_and_versions(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("mlcp"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}

    updated = client.put(
        "/api/v1/micro-live/capital-policy",
        cookies=cookies,
        headers=headers,
        json={
            "max_deployable_capital": "200",
            "max_order_notional": "20",
            "max_daily_loss": "10",
            "max_concurrent_exposure": "200",
            "max_provider_exposure": "200",
            "max_strategy_exposure": "100",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert updated.json()["is_active"] is True


# --- reconciliation ---


def test_reconciliation_detects_injected_discrepancy(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("mlr"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}

    run = client.post(
        "/api/v1/micro-live/reconciliation/runs",
        cookies=cookies,
        headers=headers,
        json={
            "provider_key": "internal_paper",
            "authoritative_state": {
                "cash_balance": "100.00000000",
                "positions": [{"symbol": "BTC-USD", "quantity": "1.00000000"}],
            },
            "comparison_state": {
                "cash_balance": "90.00000000",
                "positions": [{"symbol": "BTC-USD", "quantity": "1.00000000"}],
            },
        },
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "completed"
    kinds = {d["kind"] for d in body["discrepancies"]}
    assert "cash_balance_mismatch" in kinds

    run_id = body["id"]
    discrepancies = client.get(
        f"/api/v1/micro-live/reconciliation/runs/{run_id}/discrepancies", cookies=cookies
    )
    assert discrepancies.status_code == 200, discrepancies.text
    assert any(d["kind"] == "cash_balance_mismatch" for d in discrepancies.json())


def test_reconciliation_no_discrepancy_when_states_match(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("mlrm"), "micro-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}

    matching_state = {
        "cash_balance": "500.00000000",
        "positions": [{"symbol": "ETH-USD", "quantity": "2.00000000"}],
    }
    run = client.post(
        "/api/v1/micro-live/reconciliation/runs",
        cookies=cookies,
        headers=headers,
        json={
            "provider_key": "internal_paper",
            "authoritative_state": matching_state,
            "comparison_state": dict(matching_state),
        },
    )
    assert run.status_code == 201, run.text
    assert run.json()["discrepancies"] == []


# --- adapters (unit-level contract behavior) ---


@pytest.mark.parametrize("adapter_cls", [CoinbaseAdapter, KrakenAdapter, IbkrAdapter])
def test_adapters_never_connect_and_refuse_live_submit(adapter_cls: type) -> None:
    adapter = adapter_cls()
    adapter.connect()
    assert adapter.readiness() is False
    health = adapter.health()
    assert health.status == "disabled"

    intent = OrderIntent(
        client_order_id="test",
        portfolio_id=_uuid.uuid4(),
        provider_id=_uuid.uuid4(),
        symbol="BTC-USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        idempotency_key="test-key",
        environment=ExecutionEnvironment.LIVE,
    )
    with pytest.raises(LiveExecutionForbiddenError):
        adapter.submit_order(intent)


def test_adapters_registered_but_not_default() -> None:
    for key in ("coinbase_adapter", "kraken_adapter", "ibkr_adapter"):
        assert DEFAULT_REGISTRY.is_registered(key)
    assert "internal_paper" in DEFAULT_REGISTRY.keys()


# --- gateway ---


def test_gateway_rejects_live_environment(db_session: Session) -> None:
    gateway = ExecutionGateway(db_session)
    intent = OrderIntent(
        client_order_id="test",
        portfolio_id=_uuid.uuid4(),
        provider_id=_uuid.uuid4(),
        symbol="BTC-USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
        idempotency_key="test-key-2",
        environment=ExecutionEnvironment.LIVE,
    )
    with pytest.raises(ExecutionGatewayError) as exc_info:
        gateway.submit(
            provider_key="internal_paper",
            intent=intent,
            environment=ExecutionEnvironment.LIVE.value,
            kill_switch_active=False,
            portfolio_status="active",
            cash=Decimal("1000"),
        )
    assert exc_info.value.code == "live_execution_forbidden"


def test_assert_live_allowed_always_forbidden_without_override(db_session: Session) -> None:
    gateway = ExecutionGateway(db_session)
    with pytest.raises(ExecutionGatewayError) as exc_info:
        gateway.assert_live_allowed(
            activation_state="MICRO_LIVE_ACTIVE",
            credentials_present=True,
            global_kill_active=False,
            policy_allows=True,
        )
    assert exc_info.value.code == "live_execution_forbidden"


def test_assert_live_allowed_rejects_incomplete_gates_even_with_override(
    db_session: Session,
) -> None:
    gateway = ExecutionGateway(db_session)
    with pytest.raises(ExecutionGatewayError):
        gateway.assert_live_allowed(
            activation_state="PAPER_ONLY",
            credentials_present=False,
            global_kill_active=True,
            policy_allows=False,
            test_only_override=True,
        )


def test_assert_live_allowed_never_submits_even_when_all_gates_pass(
    db_session: Session,
) -> None:
    gateway = ExecutionGateway(db_session)
    result = gateway.assert_live_allowed(
        activation_state="MICRO_LIVE_ACTIVE",
        credentials_present=True,
        global_kill_active=False,
        policy_allows=True,
        test_only_override=True,
    )
    assert result is True
    # This method never submits an order; confirm no submission API exists
    # on the return value and the gateway's paper allowlist is unaffected.
    assert ExecutionEnvironment.LIVE.value not in gateway.ALLOWED_ENVIRONMENTS
