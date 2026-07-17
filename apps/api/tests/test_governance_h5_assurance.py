"""H5: audit fail-closed, integrity, RBAC, secrets, version-number concurrency."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.models import (
    AuditEvent,
    AuthSession,
    ConfigurationVersion,
    DraftAuthority,
    InstitutionalIdentity,
    InstitutionalRole,
    User,
    VersionLifecycleStatus,
)
from app.services.audit_service import AuditError, AuditService
from app.services.auth_service import AuthenticatedPrincipal, AuthService
from app.services.governance_service import GovernanceError, GovernanceService
from app.services.payload_integrity import (
    PayloadValidationError,
    assert_no_secrets,
    find_secret_violations,
)


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@pytest.fixture(autouse=True)
def _allow_additional_founders(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALLOW_ADDITIONAL_FOUNDERS", "true")
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def db() -> Session:
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
def client() -> TestClient:
    clear_settings_cache()
    reset_engine()
    get_settings()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    reset_engine()
    clear_settings_cache()


def _founder_principal(session: Session) -> AuthenticatedPrincipal:
    auth = AuthService(session)
    user = auth.bootstrap_founder(
        username=_unique("h5f"),
        password="founder-pass-1234",
        email=None,
    )
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        expires_at=datetime.now(UTC),
    )
    session.add(auth_session)
    session.commit()
    return AuthenticatedPrincipal(
        user=user,
        roles=frozenset({InstitutionalRole.FOUNDER}),
        session=auth_session,
    )


def _login(client: TestClient, identifier: str, password: str) -> tuple[dict, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert response.status_code == 200, response.text
    return dict(response.cookies), response.json()["csrf_token"]


# --- Secrets ---


def test_recursive_secret_detection_nested_structures() -> None:
    nested = {
        "meta": {
            "items": [
                {"name": "ok"},
                {"nested": {"API_KEY": "should-fail"}},
            ]
        }
    }
    violations = find_secret_violations(nested)
    assert violations
    with pytest.raises(PayloadValidationError):
        assert_no_secrets(nested)

    pem = {
        "files": [
            {"body": "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."},
        ]
    }
    assert find_secret_violations(pem)

    conn = {"db": {"url": "postgresql://user:secretpass@localhost/db"}}
    assert find_secret_violations(conn)

    bearer = {"headers": {"raw": "Bearer abcdefghijklmnop1234"}}
    assert find_secret_violations(bearer)

    # Reasonable non-secrets should pass (avoid substrings of forbidden keys).
    assert_no_secrets(
        {
            "mode_default": "OFF",
            "word_splitter": "whitespace",
            "metadata": {"owner": "governance"},
        }
    )


# --- Audit fail-closed ---


def test_activation_rolls_back_when_audit_fails(db: Session) -> None:
    principal = _founder_principal(db)
    gov = GovernanceService(db)
    doc = gov.create_configuration_document(
        actor=principal,
        document_key=_unique("cfg.h5.audit"),
        name="Audit Fail",
        description=None,
        schema_identifier="config.generic.v1",
        draft_authority=DraftAuthority.FOUNDER_ONLY,
    )
    version = gov.create_configuration_version(
        actor=principal, document_id=doc.id, payload={"a": 1, "n": uuid.uuid4().hex}
    )
    for status in (
        VersionLifecycleStatus.UNDER_REVIEW,
        VersionLifecycleStatus.APPROVED,
    ):
        gov.transition_configuration_version(
            actor=principal, version_id=version.id, new_status=status
        )

    with patch.object(AuditService, "append", side_effect=AuditError("forced")):
        with pytest.raises(GovernanceError, match="Audit persistence failed"):
            gov.activate_configuration_version(actor=principal, version_id=version.id)

    db.expire_all()
    row = db.get(ConfigurationVersion, version.id)
    assert row is not None
    assert row.status == VersionLifecycleStatus.APPROVED
    active = gov.get_active_configuration(doc.id)
    assert active is None


def test_version_create_rolls_back_when_audit_fails(db: Session) -> None:
    principal = _founder_principal(db)
    gov = GovernanceService(db)
    doc = gov.create_configuration_document(
        actor=principal,
        document_key=_unique("cfg.h5.create"),
        name="Create Fail",
        description=None,
        schema_identifier="config.generic.v1",
    )
    before = db.scalar(
        select(func.count()).select_from(ConfigurationVersion).where(
            ConfigurationVersion.document_id == doc.id
        )
    )
    with patch.object(AuditService, "append", side_effect=AuditError("forced")):
        with pytest.raises(GovernanceError, match="Audit persistence failed"):
            gov.create_configuration_version(
                actor=principal,
                document_id=doc.id,
                payload={"x": 1, "n": uuid.uuid4().hex},
            )
    after = db.scalar(
        select(func.count()).select_from(ConfigurationVersion).where(
            ConfigurationVersion.document_id == doc.id
        )
    )
    assert int(before or 0) == int(after or 0)


# --- Integrity ---


def test_tampered_hash_blocks_activation_and_preserves_prior_active(db: Session) -> None:
    principal = _founder_principal(db)
    identity = InstitutionalIdentity(
        institution_name="Argus",
        institution_id=_unique("argus"),
        product_version="0.1.0",
        founding_date=date(2026, 7, 15),
        active_constitution_version="unset",
        active_operating_policy_version="unset",
        active_governance_version="unset",
        active_treasury_policy_version="unset",
        active_research_framework_version="unset",
    )
    db.add(identity)
    db.commit()

    gov = GovernanceService(db)
    doc = gov.create_configuration_document(
        actor=principal,
        document_key=_unique("cfg.h5.integrity"),
        name="Integrity",
        description=None,
        schema_identifier="config.generic.v1",
    )
    v1 = gov.create_configuration_version(
        actor=principal, document_id=doc.id, payload={"v": 1, "n": uuid.uuid4().hex}
    )
    for status in (VersionLifecycleStatus.UNDER_REVIEW, VersionLifecycleStatus.APPROVED):
        gov.transition_configuration_version(
            actor=principal, version_id=v1.id, new_status=status
        )
    gov.activate_configuration_version(actor=principal, version_id=v1.id)

    v2 = gov.create_configuration_version(
        actor=principal, document_id=doc.id, payload={"v": 2, "n": uuid.uuid4().hex}
    )
    for status in (VersionLifecycleStatus.UNDER_REVIEW, VersionLifecycleStatus.APPROVED):
        gov.transition_configuration_version(
            actor=principal, version_id=v2.id, new_status=status
        )

    # Tamper hash via SQL bypassing ORM trigger path: temporarily disable trigger,
    # or update only while DRAFT then transition. Simpler: use raw SQL with
    # session_replication_role / disable trigger for the tamper only.
    db.execute(text("ALTER TABLE configuration_versions DISABLE TRIGGER USER"))
    db.execute(
        text(
            "UPDATE configuration_versions SET payload_hash = :ph WHERE id = :id"
        ),
        {"ph": "0" * 64, "id": v2.id},
    )
    db.execute(text("ALTER TABLE configuration_versions ENABLE TRIGGER USER"))
    db.commit()

    prior_identity = identity.active_operating_policy_version
    with pytest.raises(GovernanceError, match="Payload hash mismatch"):
        gov.activate_configuration_version(actor=principal, version_id=v2.id)

    db.expire_all()
    assert gov.get_active_configuration(doc.id).id == v1.id
    v2_row = db.get(ConfigurationVersion, v2.id)
    assert v2_row is not None
    assert v2_row.status == VersionLifecycleStatus.APPROVED
    db.refresh(identity)
    assert identity.active_operating_policy_version == prior_identity

    integrity_events = list(
        db.scalars(
            select(AuditEvent).where(AuditEvent.action == "configuration_integrity.failed")
        )
    )
    assert any(e.resource_id == str(v2.id) for e in integrity_events)


# --- RBAC ---


def test_rbac_matrix_operator_and_viewer(client: TestClient, db: Session) -> None:
    founder_name = _unique("founder")
    founder_pass = "founder-pass-1234"
    AuthService(db).bootstrap_founder(
        username=founder_name, password=founder_pass, email=None
    )
    f_cookies, f_csrf = _login(client, founder_name, founder_pass)

    op = client.post(
        "/api/v1/auth/users",
        headers={"X-CSRF-Token": f_csrf},
        cookies=f_cookies,
        json={
            "username": _unique("operator"),
            "password": "operator-pass-1234",
            "roles": ["OPERATOR"],
        },
    )
    assert op.status_code == 201, op.text
    viewer = client.post(
        "/api/v1/auth/users",
        headers={"X-CSRF-Token": f_csrf},
        cookies=f_cookies,
        json={
            "username": _unique("viewer"),
            "password": "viewer-pass-1234",
            "roles": ["VIEWER"],
        },
    )
    assert viewer.status_code == 201, viewer.text

    # Founder creates operator-draftable config document
    doc = client.post(
        "/api/v1/configurations/documents",
        headers={"X-CSRF-Token": f_csrf},
        cookies=f_cookies,
        json={
            "document_key": _unique("cfg.rbac"),
            "name": "RBAC",
            "schema_identifier": "config.generic.v1",
            "draft_authority": "FOUNDER_OR_OPERATOR",
        },
    )
    assert doc.status_code == 201, doc.text
    document_id = doc.json()["id"]

    o_cookies, o_csrf = _login(client, op.json()["username"], "operator-pass-1234")
    v_cookies, v_csrf = _login(client, viewer.json()["username"], "viewer-pass-1234")

    # Operator may create draft on FOUNDER_OR_OPERATOR doc
    draft = client.post(
        f"/api/v1/configurations/documents/{document_id}/versions",
        headers={"X-CSRF-Token": o_csrf},
        cookies=o_cookies,
        json={"payload": {"ok": True, "n": uuid.uuid4().hex}},
    )
    assert draft.status_code == 201, draft.text
    version_id = draft.json()["id"]

    submit = client.post(
        f"/api/v1/configurations/versions/{version_id}/submit",
        headers={"X-CSRF-Token": o_csrf},
        cookies=o_cookies,
    )
    assert submit.status_code == 200, submit.text

    # Operator cannot approve/activate
    assert (
        client.post(
            f"/api/v1/configurations/versions/{version_id}/approve",
            headers={"X-CSRF-Token": o_csrf},
            cookies=o_cookies,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/configurations/versions/{version_id}/activate",
            headers={"X-CSRF-Token": o_csrf},
            cookies=o_cookies,
        ).status_code
        == 403
    )

    # Viewer cannot mutate
    assert (
        client.post(
            f"/api/v1/configurations/documents/{document_id}/versions",
            headers={"X-CSRF-Token": v_csrf},
            cookies=v_cookies,
            json={"payload": {"no": True}},
        ).status_code
        == 403
    )

    # Founder-only document: operator cannot draft
    locked = client.post(
        "/api/v1/configurations/documents",
        headers={"X-CSRF-Token": f_csrf},
        cookies=f_cookies,
        json={
            "document_key": _unique("cfg.locked"),
            "name": "Locked",
            "schema_identifier": "config.generic.v1",
            "draft_authority": "FOUNDER_ONLY",
        },
    )
    assert locked.status_code == 201
    denied = client.post(
        f"/api/v1/configurations/documents/{locked.json()['id']}/versions",
        headers={"X-CSRF-Token": o_csrf},
        cookies=o_cookies,
        json={"payload": {"x": 1}},
    )
    assert denied.status_code == 403


# --- Version number concurrency ---


def test_concurrent_version_create_unique_numbers() -> None:
    clear_settings_cache()
    reset_engine()
    engine = create_engine(get_settings().database_url, pool_size=8)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup = SessionLocal()
    try:
        principal = _founder_principal(setup)
        gov = GovernanceService(setup)
        doc = gov.create_configuration_document(
            actor=principal,
            document_key=_unique("cfg.h5.vn"),
            name="VN",
            description=None,
            schema_identifier="config.generic.v1",
            draft_authority=DraftAuthority.FOUNDER_ONLY,
        )
        document_id = doc.id
        user_id = principal.user.id
        session_id = principal.session.id
    finally:
        setup.close()

    barrier = threading.Barrier(4)
    results: list[dict[str, Any]] = []

    def worker(i: int) -> dict[str, Any]:
        eng = create_engine(get_settings().database_url, pool_pre_ping=True)
        SessionT = sessionmaker(bind=eng, autoflush=False, autocommit=False)
        db = SessionT()
        try:
            user = db.get(User, user_id)
            auth_session = db.get(AuthSession, session_id)
            assert user and auth_session
            p = AuthenticatedPrincipal(
                user=user,
                roles=frozenset({InstitutionalRole.FOUNDER}),
                session=auth_session,
            )
            gov = GovernanceService(db)
            barrier.wait(timeout=30)
            try:
                row = gov.create_configuration_version(
                    actor=p,
                    document_id=document_id,
                    payload={"i": i, "n": uuid.uuid4().hex},
                )
                return {"ok": True, "version_number": row.version_number, "error": None}
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                return {"ok": False, "version_number": None, "error": str(exc)}
        finally:
            db.close()
            eng.dispose()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(worker, i) for i in range(4)]
        for fut in as_completed(futures):
            results.append(fut.result())

    successes = [r for r in results if r["ok"]]
    assert len(successes) == 4, results
    numbers = sorted(r["version_number"] for r in successes)
    assert numbers == sorted(set(numbers))
    assert len(numbers) == 4

    verify = SessionLocal()
    try:
        rows = list(
            verify.scalars(
                select(ConfigurationVersion)
                .where(ConfigurationVersion.document_id == document_id)
                .order_by(ConfigurationVersion.version_number)
            )
        )
        assert [r.version_number for r in rows] == list(range(1, 5))
    finally:
        verify.close()
        engine.dispose()
        reset_engine()
        clear_settings_cache()
