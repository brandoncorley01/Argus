from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.models import (
    AuditEvent,
    InstitutionalIdentity,
    InstitutionalRole,
    PolicyDocument,
    PolicyKind,
    User,
    VersionLifecycleStatus,
)
from app.services.auth_service import AuthenticatedPrincipal, AuthService
from app.services.governance_service import GovernanceError, GovernanceService, identity_pointer
from app.services.payload_integrity import (
    PayloadValidationError,
    assert_no_secrets,
    hash_payload,
)
from app.services.version_lifecycle import assert_transition, can_transition


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


def _login(client: TestClient, identifier: str, password: str) -> tuple[dict[str, str], str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert response.status_code == 200, response.text
    return dict(response.cookies), response.json()["csrf_token"]


def _auth_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


def _fake_session_hashes() -> tuple[str, str]:
    token_hash = hashlib.sha256(_unique("session").encode()).hexdigest()
    csrf_hash = hashlib.sha256(_unique("csrf").encode()).hexdigest()
    return token_hash, csrf_hash


def test_payload_hash_is_canonical_and_stable() -> None:
    a = hash_payload({"b": 2, "a": 1})
    b = hash_payload({"a": 1, "b": 2})
    assert a == b
    assert len(a) == 64


def test_secret_detection_rejects_forbidden_keys() -> None:
    with pytest.raises(PayloadValidationError):
        assert_no_secrets({"api_key": "should-not-store"})


def test_lifecycle_transitions() -> None:
    assert can_transition(VersionLifecycleStatus.DRAFT, VersionLifecycleStatus.UNDER_REVIEW)
    assert not can_transition(VersionLifecycleStatus.DRAFT, VersionLifecycleStatus.ACTIVE)
    with pytest.raises(ValueError):
        assert_transition(VersionLifecycleStatus.REJECTED, VersionLifecycleStatus.APPROVED)


def test_configuration_lifecycle_activate_and_supersede(
    client: TestClient, db_session: Session
) -> None:
    username = _unique("founder")
    password = "founder-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, csrf = _login(client, username, password)
    headers = _auth_headers(csrf)

    doc = client.post(
        "/api/v1/configurations/documents",
        headers=headers,
        cookies=cookies,
        json={
            "document_key": _unique("cfg"),
            "name": "Runtime Config",
            "schema_identifier": "config.system_runtime.v1",
        },
    )
    assert doc.status_code == 201, doc.text
    document_id = doc.json()["id"]

    v1 = client.post(
        f"/api/v1/configurations/documents/{document_id}/versions",
        headers=headers,
        cookies=cookies,
        json={"payload": {"mode_default": "OFF"}, "change_summary": "initial"},
    )
    assert v1.status_code == 201, v1.text
    v1_id = v1.json()["id"]
    assert v1.json()["status"] == "DRAFT"
    assert v1.json()["payload_hash"] == hash_payload({"mode_default": "OFF"})

    assert (
        client.post(
            f"/api/v1/configurations/versions/{v1_id}/submit",
            headers=headers,
            cookies=cookies,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/configurations/versions/{v1_id}/approve",
            headers=headers,
            cookies=cookies,
        ).status_code
        == 200
    )
    activated = client.post(
        f"/api/v1/configurations/versions/{v1_id}/activate",
        headers=headers,
        cookies=cookies,
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE"

    active = client.get(
        f"/api/v1/configurations/documents/{document_id}/active",
        cookies=cookies,
    )
    assert active.status_code == 200
    assert active.json()["id"] == v1_id

    v2 = client.post(
        f"/api/v1/configurations/documents/{document_id}/versions",
        headers=headers,
        cookies=cookies,
        json={"payload": {"mode_default": "OBSERVE"}},
    )
    assert v2.status_code == 201, v2.text
    v2_id = v2.json()["id"]
    for path in ("submit", "approve", "activate"):
        resp = client.post(
            f"/api/v1/configurations/versions/{v2_id}/{path}",
            headers=headers,
            cookies=cookies,
        )
        assert resp.status_code == 200, resp.text

    superseded = client.get(f"/api/v1/configurations/versions/{v1_id}", cookies=cookies)
    assert superseded.json()["status"] == "SUPERSEDED"
    assert (
        client.get(
            f"/api/v1/configurations/documents/{document_id}/active",
            cookies=cookies,
        ).json()["id"]
        == v2_id
    )

    compare = client.get(
        "/api/v1/configurations/versions/compare",
        cookies=cookies,
        params={"left_id": v1_id, "right_id": v2_id},
    )
    assert compare.status_code == 200, compare.text
    assert compare.json()["identical"] is False
    assert "mode_default" in compare.json()["changed_keys"]

    actions = {
        row.action
        for row in db_session.scalars(
            select(AuditEvent).where(AuditEvent.action.like("configuration_%"))
        )
    }
    assert "configuration_version.activated" in actions
    assert "configuration_version.superseded" in actions


def test_reject_identical_payload_and_secret_payload(
    client: TestClient, db_session: Session
) -> None:
    username = _unique("founder")
    password = "founder-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, csrf = _login(client, username, password)
    headers = _auth_headers(csrf)

    doc = client.post(
        "/api/v1/configurations/documents",
        headers=headers,
        cookies=cookies,
        json={
            "document_key": _unique("cfg"),
            "name": "Cfg",
            "schema_identifier": "config.generic.v1",
        },
    )
    document_id = doc.json()["id"]
    payload = {"flag": True}
    first = client.post(
        f"/api/v1/configurations/documents/{document_id}/versions",
        headers=headers,
        cookies=cookies,
        json={"payload": payload},
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/configurations/documents/{document_id}/versions",
        headers=headers,
        cookies=cookies,
        json={"payload": payload},
    )
    assert second.status_code == 400

    secret = client.post(
        f"/api/v1/configurations/documents/{document_id}/versions",
        headers=headers,
        cookies=cookies,
        json={"payload": {"token": "secret-value"}},
    )
    assert secret.status_code == 400


def test_invalid_transition_blocked(client: TestClient, db_session: Session) -> None:
    username = _unique("founder")
    password = "founder-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, csrf = _login(client, username, password)
    headers = _auth_headers(csrf)

    doc = client.post(
        "/api/v1/configurations/documents",
        headers=headers,
        cookies=cookies,
        json={
            "document_key": _unique("cfg"),
            "name": "Cfg",
            "schema_identifier": "config.generic.v1",
        },
    )
    version = client.post(
        f"/api/v1/configurations/documents/{doc.json()['id']}/versions",
        headers=headers,
        cookies=cookies,
        json={"payload": {"ok": True}},
    )
    bad = client.post(
        f"/api/v1/configurations/versions/{version.json()['id']}/activate",
        headers=headers,
        cookies=cookies,
    )
    assert bad.status_code == 400


def test_viewer_cannot_mutate_configuration(client: TestClient, db_session: Session) -> None:
    founder_name = _unique("founder")
    founder_pass = "founder-pass-1234"
    _bootstrap_founder(db_session, founder_name, founder_pass)
    f_cookies, f_csrf = _login(client, founder_name, founder_pass)

    viewer_pass = "viewer-pass-1234"
    created = client.post(
        "/api/v1/auth/users",
        headers=_auth_headers(f_csrf),
        cookies=f_cookies,
        json={
            "username": _unique("viewer"),
            "password": viewer_pass,
            "roles": ["VIEWER"],
        },
    )
    assert created.status_code == 201, created.text
    viewer_username = created.json()["username"]

    doc = client.post(
        "/api/v1/configurations/documents",
        headers=_auth_headers(f_csrf),
        cookies=f_cookies,
        json={
            "document_key": _unique("cfg"),
            "name": "Cfg",
            "schema_identifier": "config.generic.v1",
        },
    )
    assert doc.status_code == 201
    document_id = doc.json()["id"]

    v_cookies, v_csrf = _login(client, viewer_username, viewer_pass)
    denied = client.post(
        f"/api/v1/configurations/documents/{document_id}/versions",
        headers=_auth_headers(v_csrf),
        cookies=v_cookies,
        json={"payload": {"x": 1}},
    )
    assert denied.status_code == 403


def test_policy_activation_updates_institutional_identity(
    db_session: Session,
) -> None:
    auth = AuthService(db_session)
    username = _unique("founder")
    founder = auth.bootstrap_founder(
        username=username,
        password="founder-pass-1234",
        email=f"{username}@example.com",
    )
    identity = db_session.scalars(
        select(InstitutionalIdentity).order_by(InstitutionalIdentity.created_at.asc()).limit(1)
    ).first()
    if identity is None:
        identity = InstitutionalIdentity(
            institution_name="Argus",
            institution_id=_unique("argus"),
            product_version="0.1.0",
            founding_date=datetime.now(UTC).date(),
            active_constitution_version="unset",
            active_operating_policy_version="unset",
            active_governance_version="unset",
            active_treasury_policy_version="unset",
            active_research_framework_version="unset",
        )
        db_session.add(identity)
    else:
        identity.active_operating_policy_version = "unset"
    db_session.commit()

    from app.models import AuthSession

    token_hash, csrf_hash = _fake_session_hashes()
    fake_session = AuthSession(
        user_id=founder.id,
        token_hash=token_hash,
        csrf_token_hash=csrf_hash,
        expires_at=datetime.now(UTC),
    )
    db_session.add(fake_session)
    db_session.flush()
    principal = AuthenticatedPrincipal(
        user=founder,
        roles=frozenset({InstitutionalRole.FOUNDER}),
        session=fake_session,
    )

    gov = GovernanceService(db_session)
    existing = db_session.scalars(
        select(PolicyDocument).where(
            PolicyDocument.policy_kind == PolicyKind.OPERATING,
            PolicyDocument.is_retired.is_(False),
        )
    ).first()
    if existing is None:
        doc = gov.create_policy_document(
            actor=principal,
            document_key=_unique("pol.operating"),
            name="Operating Policy",
            policy_kind=PolicyKind.OPERATING,
            description=None,
            schema_identifier="policy.operating.v1",
        )
        doc_id = doc.id
        document_key = doc.document_key
    else:
        doc_id = existing.id
        document_key = existing.document_key
    version = gov.create_policy_version(
        actor=principal,
        document_id=doc_id,
        payload={"summary": "operating baseline", "n": _unique("n")},
    )
    gov.transition_policy_version(
        actor=principal,
        version_id=version.id,
        new_status=VersionLifecycleStatus.UNDER_REVIEW,
    )
    gov.transition_policy_version(
        actor=principal,
        version_id=version.id,
        new_status=VersionLifecycleStatus.APPROVED,
    )
    activated = gov.activate_policy_version(actor=principal, version_id=version.id)
    db_session.refresh(identity)
    assert identity.active_operating_policy_version == identity_pointer(
        document_key, activated.version_number
    )


def test_draft_only_mutation(db_session: Session) -> None:
    auth = AuthService(db_session)
    username = _unique("founder")
    founder = auth.bootstrap_founder(
        username=username,
        password="founder-pass-1234",
        email=f"{username}@example.com",
    )
    from app.models import AuthSession

    token_hash, csrf_hash = _fake_session_hashes()
    fake_session = AuthSession(
        user_id=founder.id,
        token_hash=token_hash,
        csrf_token_hash=csrf_hash,
        expires_at=datetime.now(UTC),
    )
    db_session.add(fake_session)
    db_session.flush()
    principal = AuthenticatedPrincipal(
        user=founder,
        roles=frozenset({InstitutionalRole.FOUNDER}),
        session=fake_session,
    )
    gov = GovernanceService(db_session)
    doc = gov.create_configuration_document(
        actor=principal,
        document_key=_unique("cfg"),
        name="Cfg",
        description=None,
        schema_identifier="config.generic.v1",
    )
    version = gov.create_configuration_version(
        actor=principal,
        document_id=doc.id,
        payload={"a": 1},
    )
    gov.transition_configuration_version(
        actor=principal,
        version_id=version.id,
        new_status=VersionLifecycleStatus.UNDER_REVIEW,
    )
    with pytest.raises(GovernanceError, match="Only DRAFT"):
        gov.update_configuration_draft(
            actor=principal,
            version_id=version.id,
            payload={"a": 2},
        )
