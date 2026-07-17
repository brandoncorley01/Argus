from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.models import AuditEvent, AuthSession, User
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


def _bootstrap_founder(db_session: Session, username: str, password: str) -> User:
    auth = AuthService(db_session)
    return auth.bootstrap_founder(
        username=username,
        password=password,
        email=f"{username}@example.com",
    )


def _login(
    client: TestClient, identifier: str, password: str
) -> tuple[dict[str, str], str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    return dict(response.cookies), csrf


def test_successful_login_and_me(client: TestClient, db_session: Session) -> None:
    username = _unique("founder")
    password = "founder-pass-1234"
    _bootstrap_founder(db_session, username, password)

    cookies, csrf = _login(client, username, password)
    me = client.get("/api/v1/auth/me", cookies=cookies)
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == username
    assert "FOUNDER" in body["roles"]
    assert csrf


def test_invalid_password_and_unknown_user_same_message(
    client: TestClient, db_session: Session
) -> None:
    username = _unique("founder")
    password = "founder-pass-1234"
    _bootstrap_founder(db_session, username, password)

    bad = client.post(
        "/api/v1/auth/login", json={"identifier": username, "password": "wrong-password-123"}
    )
    unknown = client.post(
        "/api/v1/auth/login",
        json={"identifier": "missing-user", "password": "wrong-password-123"},
    )
    assert bad.status_code == 401
    assert unknown.status_code == 401
    assert bad.json()["detail"] == unknown.json()["detail"] == "Invalid credentials"


def test_logout_invalidates_session(client: TestClient, db_session: Session) -> None:
    username = _unique("founder")
    password = "founder-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, csrf = _login(client, username, password)

    logout = client.post(
        "/api/v1/auth/logout",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
    )
    assert logout.status_code == 204
    me = client.get("/api/v1/auth/me", cookies=cookies)
    assert me.status_code == 401


def test_csrf_rejection_on_logout(client: TestClient, db_session: Session) -> None:
    username = _unique("founder")
    password = "founder-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, _csrf = _login(client, username, password)

    rejected = client.post("/api/v1/auth/logout", cookies=cookies)
    assert rejected.status_code == 403


def test_expired_session(client: TestClient, db_session: Session) -> None:
    username = _unique("founder")
    password = "founder-pass-1234"
    user = _bootstrap_founder(db_session, username, password)
    cookies, _csrf = _login(client, username, password)

    token = cookies.get("argus_session")
    assert token
    row = db_session.scalars(
        select(AuthSession).where(AuthSession.token_hash == hash_token(token))
    ).one()
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    me = client.get("/api/v1/auth/me", cookies=cookies)
    assert me.status_code == 401

    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "auth.session.expired")
    ).all()
    assert any(event.actor_user_id == user.id for event in events)


def test_founder_create_user_and_viewer_write_denial(
    client: TestClient, db_session: Session
) -> None:
    founder_name = _unique("founder")
    founder_pass = "founder-pass-1234"
    _bootstrap_founder(db_session, founder_name, founder_pass)
    founder_cookies, founder_csrf = _login(client, founder_name, founder_pass)

    viewer_name = _unique("viewer")
    created = client.post(
        "/api/v1/auth/users",
        cookies=founder_cookies,
        headers={"X-CSRF-Token": founder_csrf},
        json={
            "username": viewer_name,
            "password": "viewer-pass-1234",
            "email": f"{viewer_name}@example.com",
            "roles": ["VIEWER"],
        },
    )
    assert created.status_code == 201, created.text

    viewer_cookies, viewer_csrf = _login(client, viewer_name, "viewer-pass-1234")
    denied = client.post(
        "/api/v1/auth/users",
        cookies=viewer_cookies,
        headers={"X-CSRF-Token": viewer_csrf},
        json={
            "username": _unique("other"),
            "password": "other-pass-1234",
            "roles": ["VIEWER"],
        },
    )
    assert denied.status_code == 403


def test_operator_governance_denial(client: TestClient, db_session: Session) -> None:
    founder_name = _unique("founder")
    founder_pass = "founder-pass-1234"
    _bootstrap_founder(db_session, founder_name, founder_pass)
    founder_cookies, founder_csrf = _login(client, founder_name, founder_pass)

    operator_name = _unique("operator")
    created = client.post(
        "/api/v1/auth/users",
        cookies=founder_cookies,
        headers={"X-CSRF-Token": founder_csrf},
        json={
            "username": operator_name,
            "password": "operator-pass-12",
            "roles": ["OPERATOR"],
        },
    )
    assert created.status_code == 201, created.text
    operator_cookies, operator_csrf = _login(client, operator_name, "operator-pass-12")

    denied = client.post(
        "/api/v1/auth/users",
        cookies=operator_cookies,
        headers={"X-CSRF-Token": operator_csrf},
        json={
            "username": _unique("nope"),
            "password": "nope-pass-12345",
            "roles": ["VIEWER"],
        },
    )
    assert denied.status_code == 403

    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "authz.denied")
    ).all()
    assert len(events) >= 1


def test_role_assignment_founder_only(client: TestClient, db_session: Session) -> None:
    founder_name = _unique("founder")
    founder_pass = "founder-pass-1234"
    _bootstrap_founder(db_session, founder_name, founder_pass)
    founder_cookies, founder_csrf = _login(client, founder_name, founder_pass)

    user_name = _unique("member")
    created = client.post(
        "/api/v1/auth/users",
        cookies=founder_cookies,
        headers={"X-CSRF-Token": founder_csrf},
        json={
            "username": user_name,
            "password": "member-pass-1234",
            "roles": ["VIEWER"],
        },
    )
    user_id = created.json()["id"]
    assigned = client.post(
        f"/api/v1/auth/users/{user_id}/roles",
        cookies=founder_cookies,
        headers={"X-CSRF-Token": founder_csrf},
        json={"role": "OPERATOR"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["role"] == "OPERATOR"


def test_audit_login_and_redaction(db_session: Session) -> None:
    username = _unique("founder")
    password = "founder-pass-1234"
    auth = AuthService(db_session)
    user = auth.bootstrap_founder(username=username, password=password)
    auth.login(identifier=username, password=password, ip_address="127.0.0.1")

    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.actor_user_id == user.id)
    ).all()
    assert any(event.action == "auth.login.success" for event in events)
    for event in events:
        if event.payload:
            assert "password" not in event.payload
            assert "session_token" not in event.payload


def test_lockout_after_repeated_failures(client: TestClient, db_session: Session) -> None:
    username = _unique("founder")
    password = "founder-pass-1234"
    _bootstrap_founder(db_session, username, password)
    settings = get_settings()

    for _ in range(settings.login_max_failures):
        response = client.post(
            "/api/v1/auth/login",
            json={"identifier": username, "password": "bad-password-xxxx"},
        )
        assert response.status_code == 401

    locked = client.post(
        "/api/v1/auth/login",
        json={"identifier": username, "password": password},
    )
    assert locked.status_code == 401

    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "auth.login.lockout")
    ).all()
    assert len(events) >= 1


def test_audit_api_requires_auth(client: TestClient, db_session: Session) -> None:
    unauth = client.get("/api/v1/audit/events")
    assert unauth.status_code == 401

    username = _unique("founder")
    password = "founder-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, _csrf = _login(client, username, password)
    ok = client.get("/api/v1/audit/events", cookies=cookies)
    assert ok.status_code == 200
