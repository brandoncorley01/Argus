"""Service, API, RBAC, audit, and policy tests for Phase 7 operating mode."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.models import (
    AuditEvent,
    AuthSession,
    InstitutionalRole,
    OperatingMode,
    OperatingModeHistory,
    PolicyDocument,
    PolicyKind,
    PolicyVersion,
    SystemState,
    User,
    UserRole,
    VersionLifecycleStatus,
)
from app.services.audit_service import AuditError, AuditService
from app.services.auth_service import AuthenticatedPrincipal, AuthError, AuthService
from app.services.operating_mode_service import (
    OperatingModeError,
    OperatingModeService,
    hash_idempotency_key,
    request_fingerprint,
)
from app.services.payload_integrity import hash_payload


def _reset_operating_mode_tables(session: Session) -> None:
    session.execute(text("UPDATE system_states SET last_history_id = NULL"))
    session.execute(text("DELETE FROM operating_mode_idempotency"))
    session.execute(
        text(
            "ALTER TABLE operating_mode_history "
            "DISABLE TRIGGER trg_operating_mode_history_immutability"
        )
    )
    session.execute(text("DELETE FROM operating_mode_history"))
    session.execute(
        text(
            "ALTER TABLE operating_mode_history "
            "ENABLE TRIGGER trg_operating_mode_history_immutability"
        )
    )
    session.execute(text("DELETE FROM system_states"))
    session.execute(
        text(
            """
            DELETE FROM audit_events
            WHERE action LIKE 'operating_mode.%'
               OR resource_type IN ('operating_mode', 'system_state')
            """
        )
    )
    session.commit()


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
        _reset_operating_mode_tables(session)
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
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _bootstrap_founder(db_session: Session, username: str | None = None) -> User:
    auth = AuthService(db_session)
    name = username or _unique("founder")
    return auth.bootstrap_founder(
        username=name,
        password="founder-pass-1234",
        email=f"{name}@example.com",
    )


def _principal_for(
    db_session: Session, user: User, *roles: InstitutionalRole
) -> AuthenticatedPrincipal:
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        expires_at=datetime.now(UTC),
    )
    db_session.add(auth_session)
    db_session.commit()
    return AuthenticatedPrincipal(
        user=user,
        roles=frozenset(roles),
        session=auth_session,
    )


def _login(client: TestClient, identifier: str, password: str) -> tuple[dict[str, str], str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert response.status_code == 200, response.text
    return dict(response.cookies), response.json()["csrf_token"]


def test_request_fingerprint_stable() -> None:
    a = request_fingerprint(
        operation="transition",
        target_mode="OBSERVE",
        reason="r",
        incident_id=None,
        expected_state_version=1,
    )
    b = request_fingerprint(
        operation="transition",
        target_mode="OBSERVE",
        reason="r",
        incident_id=None,
        expected_state_version=1,
    )
    c = request_fingerprint(
        operation="transition",
        target_mode="SAFE_MODE",
        reason="r",
        incident_id=None,
        expected_state_version=1,
    )
    assert a == b
    assert a != c
    assert len(hash_idempotency_key("k")) == 64


def test_initialize_idempotent_off(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    first = svc.initialize(actor=actor, request_id="init-1")
    second = svc.initialize(actor=actor, request_id="init-2")
    assert first.id == second.id
    assert first.current_mode == OperatingMode.OFF
    assert first.state_version == 1
    audits = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "operating_mode.initialized",
                AuditEvent.resource_id == str(first.id),
            )
        )
    )
    assert len(audits) == 1


def test_off_to_observe_and_back(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    to_observe = svc.transition(
        actor=actor,
        target_mode=OperatingMode.OBSERVE,
        reason="begin observation",
        idempotency_key=_unique("k"),
    )
    assert to_observe["current_mode"] == "OBSERVE"
    assert to_observe["state_version"] == 2
    back = svc.transition(
        actor=actor,
        target_mode=OperatingMode.OFF,
        reason="shutdown",
        idempotency_key=_unique("k"),
    )
    assert back["current_mode"] == "OFF"
    assert back["state_version"] == 3


def test_safe_mode_and_emergency_from_off(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    safe = svc.transition(
        actor=actor,
        target_mode=OperatingMode.SAFE_MODE,
        reason="anomaly",
        idempotency_key=_unique("k"),
    )
    assert safe["current_mode"] == "SAFE_MODE"
    emergency = svc.emergency_stop(
        actor=actor,
        reason="critical",
        idempotency_key=_unique("k"),
    )
    assert emergency["current_mode"] == "EMERGENCY_STOP"
    assert emergency["emergency_stop_active"] is True
    assert emergency["recovery_required"] is True
    state = svc.get_state()
    assert state.current_mode == OperatingMode.EMERGENCY_STOP


def test_founder_recovery_and_block_live_exit(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    svc.emergency_stop(actor=actor, reason="halt", idempotency_key=_unique("k"))
    with pytest.raises(OperatingModeError) as exc:
        svc.transition(
            actor=actor,
            target_mode=OperatingMode.OBSERVE,
            reason="illegal",
            idempotency_key=_unique("k"),
        )
    assert exc.value.code == "recovery_requirements_not_met"
    recovered = svc.recover_from_emergency(
        actor=actor, reason="cleared", idempotency_key=_unique("k")
    )
    assert recovered["current_mode"] == "OFF"
    assert recovered["emergency_stop_active"] is False
    assert recovered["recovery_required"] is False


def test_paper_micro_normal_blocked(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    svc.transition(
        actor=actor,
        target_mode=OperatingMode.OBSERVE,
        reason="observe",
        idempotency_key=_unique("k"),
    )
    with pytest.raises(OperatingModeError) as exc:
        svc.transition(
            actor=actor,
            target_mode=OperatingMode.PAPER,
            reason="paper",
            idempotency_key=_unique("k"),
        )
    assert exc.value.code == "prerequisite_failed"
    assert "mode_unavailable" in exc.value.message


def test_missing_system_state(db_session: Session) -> None:
    svc = OperatingModeService(db_session)
    with pytest.raises(OperatingModeError) as exc:
        svc.get_state()
    assert exc.value.code == "institutional_state_missing"


def test_idempotent_replay_and_conflict(db_session: Session) -> None:
    from sqlalchemy import func

    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    key = _unique("idem")
    first = svc.transition(
        actor=actor,
        target_mode=OperatingMode.OBSERVE,
        reason="observe",
        idempotency_key=key,
    )
    replay = svc.transition(
        actor=actor,
        target_mode=OperatingMode.OBSERVE,
        reason="observe",
        idempotency_key=key,
    )
    assert replay["idempotent_replay"] is True
    assert replay["history_id"] == first["history_id"]
    history_count = db_session.scalar(select(func.count()).select_from(OperatingModeHistory))
    assert history_count == 2  # initialize + one transition
    with pytest.raises(OperatingModeError) as exc:
        svc.transition(
            actor=actor,
            target_mode=OperatingMode.SAFE_MODE,
            reason="different",
            idempotency_key=key,
        )
    assert exc.value.code == "idempotency_conflict"


def test_stale_state_version(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    with pytest.raises(OperatingModeError) as exc:
        svc.transition(
            actor=actor,
            target_mode=OperatingMode.OBSERVE,
            reason="observe",
            idempotency_key=_unique("k"),
            expected_state_version=99,
        )
    assert exc.value.code == "stale_state"


def test_history_immutability_trigger(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    row = db_session.scalars(select(OperatingModeHistory)).first()
    assert row is not None
    with pytest.raises(DBAPIError):
        db_session.execute(
            text("UPDATE operating_mode_history SET reason = 'tamper' WHERE id = :id"),
            {"id": str(row.id)},
        )
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    "action",
    ["initialize", "transition", "safe_mode", "emergency", "recover"],
)
def test_audit_fail_closed(db_session: Session, action: str) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)

    if action == "initialize":
        with patch.object(AuditService, "append", side_effect=AuditError("forced")):
            with pytest.raises(OperatingModeError) as exc:
                svc.initialize(actor=actor)
            assert exc.value.code == "audit_unavailable"
        assert db_session.scalars(select(SystemState)).first() is None
        return

    svc.initialize(actor=actor)
    if action == "recover":
        svc.emergency_stop(actor=actor, reason="halt", idempotency_key=_unique("k"))

    with patch.object(AuditService, "append", side_effect=AuditError("forced")):
        with pytest.raises(OperatingModeError) as exc:
            if action == "transition":
                svc.transition(
                    actor=actor,
                    target_mode=OperatingMode.OBSERVE,
                    reason="observe",
                    idempotency_key=_unique("k"),
                )
            elif action == "safe_mode":
                svc.transition(
                    actor=actor,
                    target_mode=OperatingMode.SAFE_MODE,
                    reason="safe",
                    idempotency_key=_unique("k"),
                )
            elif action == "emergency":
                svc.emergency_stop(
                    actor=actor, reason="halt", idempotency_key=_unique("k")
                )
            else:
                svc.recover_from_emergency(
                    actor=actor, reason="clear", idempotency_key=_unique("k")
                )
        assert exc.value.code == "audit_unavailable"

    state = db_session.scalars(select(SystemState)).first()
    assert state is not None
    if action == "recover":
        assert state.current_mode == OperatingMode.EMERGENCY_STOP
    else:
        assert state.current_mode == OperatingMode.OFF


def test_operator_rbac_matrix(db_session: Session) -> None:
    founder = _bootstrap_founder(db_session)
    founder_actor = _principal_for(db_session, founder, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=founder_actor)

    op_user = User(
        username=_unique("op"),
        email=None,
        password_hash="unused",
        is_active=True,
    )
    db_session.add(op_user)
    db_session.flush()
    db_session.add(UserRole(user_id=op_user.id, role=InstitutionalRole.OPERATOR))
    db_session.commit()
    operator = _principal_for(db_session, op_user, InstitutionalRole.OPERATOR)

    ok = svc.transition(
        actor=operator,
        target_mode=OperatingMode.SAFE_MODE,
        reason="degrade",
        idempotency_key=_unique("k"),
    )
    assert ok["current_mode"] == "SAFE_MODE"

    with pytest.raises(AuthError):
        svc.transition(
            actor=operator,
            target_mode=OperatingMode.OBSERVE,
            reason="observe",
            idempotency_key=_unique("k"),
        )

    with pytest.raises(AuthError):
        svc.emergency_stop(actor=operator, reason="nope", idempotency_key=_unique("k"))

    # Founder enters emergency; operator cannot recover.
    svc.emergency_stop(actor=founder_actor, reason="halt", idempotency_key=_unique("k"))
    with pytest.raises(AuthError):
        svc.recover_from_emergency(
            actor=operator, reason="nope", idempotency_key=_unique("k")
        )


def test_availability_endpoint_honesty(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    rows = {row["mode"]: row for row in svc.availability()}
    assert rows["OFF"]["enterable"] is True
    assert rows["OBSERVE"]["enterable"] is True
    assert rows["PAPER"]["enterable"] is False
    assert rows["MICRO_LIVE"]["enterable"] is False
    assert rows["NORMAL_LIVE"]["enterable"] is False
    assert "mode_unavailable" in rows["PAPER"]["blocking_codes"]


def test_api_founder_flow(client: TestClient, db_session: Session) -> None:
    username = _unique("api_f")
    _bootstrap_founder(db_session, username)
    cookies, csrf = _login(client, username, "founder-pass-1234")
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": _unique("k")}

    init = client.post("/api/v1/operating-mode/initialize", cookies=cookies, headers=headers)
    assert init.status_code == 200, init.text
    assert init.json()["current_mode"] == "OFF"

    observe = client.post(
        "/api/v1/operating-mode/transition",
        cookies=cookies,
        headers=headers,
        json={"target_mode": "OBSERVE", "reason": "start"},
    )
    assert observe.status_code == 200, observe.text
    assert observe.json()["current_mode"] == "OBSERVE"

    current = client.get("/api/v1/operating-mode", cookies=cookies)
    assert current.status_code == 200
    assert current.json()["current_mode"] == "OBSERVE"

    availability = client.get("/api/v1/operating-mode/availability", cookies=cookies)
    assert availability.status_code == 200
    assert any(row["mode"] == "PAPER" and not row["enterable"] for row in availability.json())

    history = client.get("/api/v1/operating-mode/history", cookies=cookies)
    assert history.status_code == 200
    assert len(history.json()) >= 2


def test_api_viewer_denied_mutation(client: TestClient, db_session: Session) -> None:
    founder_name = _unique("vf")
    founder = _bootstrap_founder(db_session, founder_name)
    cookies_f, csrf_f = _login(client, founder_name, "founder-pass-1234")
    create = client.post(
        "/api/v1/auth/users",
        cookies=cookies_f,
        headers={"X-CSRF-Token": csrf_f},
        json={
            "username": _unique("viewer"),
            "password": "viewer-pass-1234",
            "roles": ["VIEWER"],
        },
    )
    assert create.status_code == 201, create.text
    viewer_name = create.json()["username"]
    # Ensure system state exists
    founder_actor = _principal_for(db_session, founder, InstitutionalRole.FOUNDER)
    OperatingModeService(db_session).initialize(actor=founder_actor)

    cookies_v, csrf_v = _login(client, viewer_name, "viewer-pass-1234")
    denied = client.post(
        "/api/v1/operating-mode/transition",
        cookies=cookies_v,
        headers={"X-CSRF-Token": csrf_v, "Idempotency-Key": _unique("k")},
        json={"target_mode": "SAFE_MODE", "reason": "nope"},
    )
    assert denied.status_code == 403

    allowed_read = client.get("/api/v1/operating-mode", cookies=cookies_v)
    assert allowed_read.status_code == 200


def test_policy_reference_attached_when_present(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    doc = db_session.scalars(
        select(PolicyDocument).where(
            PolicyDocument.policy_kind == PolicyKind.OPERATING,
            PolicyDocument.is_retired.is_(False),
        )
    ).first()
    if doc is None:
        doc = PolicyDocument(
            document_key=_unique("pol.op"),
            name="Operating",
            policy_kind=PolicyKind.OPERATING,
        )
        db_session.add(doc)
        db_session.flush()
    for row in list(
        db_session.scalars(
            select(PolicyVersion).where(
                PolicyVersion.document_id == doc.id,
                PolicyVersion.status == VersionLifecycleStatus.ACTIVE,
            )
        )
    ):
        row.status = VersionLifecycleStatus.SUPERSEDED
        row.superseded_at = datetime.now(UTC)
    payload = {"mode_default": "OFF", "nonce": _unique("n")}
    next_num = (
        db_session.scalar(
            select(func.max(PolicyVersion.version_number)).where(
                PolicyVersion.document_id == doc.id
            )
        )
        or 0
    ) + 1
    version = PolicyVersion(
        document_id=doc.id,
        version_number=next_num,
        version_label=f"op-v{next_num}",
        content=payload,
        payload_hash=hash_payload(payload),
        status=VersionLifecycleStatus.ACTIVE,
        activated_at=datetime.now(UTC),
    )
    db_session.add(version)
    db_session.commit()


    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    result = svc.transition(
        actor=actor,
        target_mode=OperatingMode.OBSERVE,
        reason="observe",
        idempotency_key=_unique("k"),
    )
    assert result["policy_version_id"] == str(version.id)
    history = db_session.scalars(
        select(OperatingModeHistory).where(
            OperatingModeHistory.to_mode == OperatingMode.OBSERVE
        )
    ).first()
    assert history is not None
    assert history.policy_version_id == version.id

def test_transitions_distinguish_structural_vs_enterable(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    svc.transition(
        actor=actor,
        target_mode=OperatingMode.OBSERVE,
        reason="observe",
        idempotency_key=_unique("k"),
    )
    body = svc.allowed_transitions()
    assert "PAPER" in body["structural_targets"]
    assert "PAPER" not in body["enterable_targets"]
    paper = next(t for t in body["targets"] if t["mode"] == "PAPER")
    assert paper["structurally_allowed"] is True
    assert paper["enterable"] is False
    assert "mode_unavailable" in paper["blocking_codes"]
    assert "OFF" in body["enterable_targets"]


def test_micro_live_and_normal_live_blocked(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    state = svc.get_state()
    state.current_mode = OperatingMode.PAPER
    db_session.add(state)
    db_session.commit()

    with pytest.raises(OperatingModeError) as micro:
        svc.transition(
            actor=actor,
            target_mode=OperatingMode.MICRO_LIVE,
            reason="micro",
            idempotency_key=_unique("k"),
        )
    assert micro.value.code == "prerequisite_failed"
    assert "mode_unavailable" in micro.value.message

    state = svc.get_state()
    state.current_mode = OperatingMode.MICRO_LIVE
    db_session.add(state)
    db_session.commit()
    with pytest.raises(OperatingModeError) as normal:
        svc.transition(
            actor=actor,
            target_mode=OperatingMode.NORMAL_LIVE,
            reason="normal",
            idempotency_key=_unique("k"),
        )
    assert normal.value.code == "prerequisite_failed"
    assert "mode_unavailable" in normal.value.message


def test_history_delete_blocked_by_trigger(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    OperatingModeService(db_session).initialize(actor=actor)
    row = db_session.scalars(select(OperatingModeHistory)).first()
    assert row is not None
    with pytest.raises(DBAPIError):
        db_session.execute(
            text("DELETE FROM operating_mode_history WHERE id = :id"),
            {"id": str(row.id)},
        )
        db_session.commit()
    db_session.rollback()


def test_tampered_policy_blocks_risk_increasing(db_session: Session) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    doc = db_session.scalars(
        select(PolicyDocument).where(
            PolicyDocument.policy_kind == PolicyKind.OPERATING,
            PolicyDocument.is_retired.is_(False),
        )
    ).first()
    if doc is None:
        doc = PolicyDocument(
            document_key=_unique("pol.op"),
            name="Operating",
            policy_kind=PolicyKind.OPERATING,
        )
        db_session.add(doc)
        db_session.flush()
    for row in list(
        db_session.scalars(
            select(PolicyVersion).where(
                PolicyVersion.document_id == doc.id,
                PolicyVersion.status == VersionLifecycleStatus.ACTIVE,
            )
        )
    ):
        row.status = VersionLifecycleStatus.SUPERSEDED
        row.superseded_at = datetime.now(UTC)
    payload = {"mode_default": "OFF", "nonce": _unique("n")}
    version = PolicyVersion(
        document_id=doc.id,
        version_number=(
            db_session.scalar(
                select(func.max(PolicyVersion.version_number)).where(
                    PolicyVersion.document_id == doc.id
                )
            )
            or 0
        )
        + 1,
        version_label=_unique("tamper"),
        content=payload,
        payload_hash=hash_payload(payload),
        status=VersionLifecycleStatus.ACTIVE,
        activated_at=datetime.now(UTC),
    )
    db_session.add(version)
    db_session.commit()

    db_session.execute(text("ALTER TABLE policy_versions DISABLE TRIGGER USER"))
    db_session.execute(
        text("UPDATE policy_versions SET payload_hash = :bad WHERE id = :id"),
        {"bad": "0" * 64, "id": str(version.id)},
    )
    db_session.execute(text("ALTER TABLE policy_versions ENABLE TRIGGER USER"))
    db_session.commit()

    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    svc.transition(
        actor=actor,
        target_mode=OperatingMode.OBSERVE,
        reason="observe",
        idempotency_key=_unique("k"),
    )
    with pytest.raises(OperatingModeError) as exc:
        svc.transition(
            actor=actor,
            target_mode=OperatingMode.PAPER,
            reason="paper",
            idempotency_key=_unique("k"),
        )
    assert exc.value.code == "prerequisite_failed"
    assert "mode_unavailable" in exc.value.message
    assert "policy_integrity_failed" in exc.value.message


def test_committed_transition_has_matching_state_history_audit(
    db_session: Session,
) -> None:
    user = _bootstrap_founder(db_session)
    actor = _principal_for(db_session, user, InstitutionalRole.FOUNDER)
    svc = OperatingModeService(db_session)
    svc.initialize(actor=actor)
    result = svc.transition(
        actor=actor,
        target_mode=OperatingMode.SAFE_MODE,
        reason="degrade",
        idempotency_key=_unique("k"),
    )
    state = svc.get_state()
    assert state.current_mode == OperatingMode.SAFE_MODE
    assert state.state_version == result["state_version"]
    history = db_session.get(OperatingModeHistory, uuid.UUID(result["history_id"]))
    assert history is not None
    assert history.to_mode == OperatingMode.SAFE_MODE
    assert history.new_state_version == state.state_version
    assert state.last_history_id == history.id
    audit = db_session.scalars(
        select(AuditEvent)
        .where(AuditEvent.action == "operating_mode.safe_mode_entered")
        .order_by(AuditEvent.occurred_at.desc())
    ).first()
    assert audit is not None
    assert audit.payload is not None
    assert audit.payload.get("history_id") == result["history_id"]
    assert audit.payload.get("new_state_version") == state.state_version
    assert audit.resource_id == str(state.id)


def test_api_operator_emergency_denied(client: TestClient, db_session: Session) -> None:
    founder_name = _unique("ef")
    founder = _bootstrap_founder(db_session, founder_name)
    cookies_f, csrf_f = _login(client, founder_name, "founder-pass-1234")
    create = client.post(
        "/api/v1/auth/users",
        cookies=cookies_f,
        headers={"X-CSRF-Token": csrf_f},
        json={
            "username": _unique("op"),
            "password": "operator-pass-1234",
            "roles": ["OPERATOR"],
        },
    )
    assert create.status_code == 201, create.text
    op_name = create.json()["username"]
    OperatingModeService(db_session).initialize(
        actor=_principal_for(db_session, founder, InstitutionalRole.FOUNDER)
    )

    cookies_o, csrf_o = _login(client, op_name, "operator-pass-1234")
    denied = client.post(
        "/api/v1/operating-mode/emergency-stop",
        cookies=cookies_o,
        headers={"X-CSRF-Token": csrf_o, "Idempotency-Key": _unique("k")},
        json={"reason": "nope"},
    )
    assert denied.status_code == 403

    recover = client.post(
        "/api/v1/operating-mode/emergency-stop/recover",
        cookies=cookies_o,
        headers={"X-CSRF-Token": csrf_o, "Idempotency-Key": _unique("k")},
        json={"reason": "nope"},
    )
    assert recover.status_code == 403
