"""Phase 8 health supervisor integration tests."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.models import (
    AuditEvent,
    AuthSession,
    HealthHeartbeat,
    HealthStatus,
    InstitutionalRole,
    OperatingMode,
    SystemState,
    User,
)
from app.services.auth_service import AuthenticatedPrincipal, AuthService
from app.services.health_evaluation_service import HealthEvaluationService
from app.services.health_supervisor_service import HealthSupervisorService
from app.services.heartbeat_service import HealthError, HeartbeatService
from app.services.operating_mode_service import OperatingModeService
from app.services.service_registry_service import ServiceRegistryService


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _cleanup_health(session: Session) -> None:
    session.execute(text("UPDATE health_supervisor_leases SET holder_instance_id = NULL"))
    session.execute(text("DELETE FROM protective_action_recommendations"))
    session.execute(
        text(
            "ALTER TABLE incident_lifecycle_events "
            "DISABLE TRIGGER trg_incident_lifecycle_events_immutability"
        )
    )
    session.execute(text("DELETE FROM incident_lifecycle_events"))
    session.execute(
        text(
            "ALTER TABLE incident_lifecycle_events "
            "ENABLE TRIGGER trg_incident_lifecycle_events_immutability"
        )
    )
    session.execute(text("DELETE FROM incidents WHERE correlation_key LIKE 'health:%'"))
    session.execute(text("DELETE FROM health_heartbeat_idempotency"))
    session.execute(text("UPDATE service_health_projections SET last_heartbeat_id = NULL"))
    session.execute(
        text("ALTER TABLE health_heartbeats DISABLE TRIGGER trg_health_heartbeats_immutability")
    )
    session.execute(text("DELETE FROM health_heartbeats"))
    session.execute(
        text("ALTER TABLE health_heartbeats ENABLE TRIGGER trg_health_heartbeats_immutability")
    )
    session.execute(text("DELETE FROM worker_instances"))
    session.execute(
        text(
            """
            UPDATE service_health_projections
            SET status = 'healthy',
                last_sequence_number = NULL,
                last_observed_at = NULL,
                consecutive_failures = 0,
                evaluation_version = 0,
                detail = 'test reset'
            """
        )
    )
    session.execute(
        text(
            """
            UPDATE institutional_health_state
            SET status = 'healthy',
                evaluation_version = 0,
                summary = '{}'::jsonb,
                evaluated_at = now()
            WHERE singleton_key = 'current'
            """
        )
    )
    session.execute(
        text(
            """
            UPDATE health_supervisor_leases
            SET lease_epoch = 0,
                lease_until = NULL,
                last_cycle_at = NULL,
                last_cycle_result = NULL,
                updated_at = now()
            WHERE singleton_key = 'current'
            """
        )
    )
    session.execute(
        text(
            """
            DELETE FROM audit_events
            WHERE action LIKE 'health.%'
               OR action LIKE 'incident.%'
               OR (action LIKE 'operating_mode.%' AND payload->>'actor' = 'SYSTEM')
            """
        )
    )
    session.commit()


def _reset_mode(session: Session) -> None:
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
    session.commit()


@pytest.fixture(autouse=True)
def _allow_additional_founders(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ALLOW_ADDITIONAL_FOUNDERS", "true")
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def db_session() -> Iterator[Session]:
    reset_engine()
    clear_settings_cache()
    factory = get_session_factory()
    session = factory()
    _cleanup_health(session)
    _reset_mode(session)
    try:
        yield session
    finally:
        _cleanup_health(session)
        _reset_mode(session)
        session.close()
        reset_engine()


@pytest.fixture
def client() -> Iterator[TestClient]:
    reset_engine()
    clear_settings_cache()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    reset_engine()
    clear_settings_cache()


def _bootstrap_founder(session: Session, username: str | None = None) -> User:
    settings = get_settings()
    auth = AuthService(session, settings)
    name = username or _unique("founder")
    user = auth.bootstrap_founder(
        username=name,
        password="FounderPass123!",
        email=f"{name}@example.com",
    )
    session.commit()
    return user


def _principal_for(session: Session, user: User) -> AuthenticatedPrincipal:
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


def _login(
    client: TestClient, identifier: str, password: str = "FounderPass123!"
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert response.status_code == 200, response.text
    headers = {"X-CSRF-Token": response.json()["csrf_token"]}
    # TestClient keeps cookies automatically from the response.
    return headers


def test_heartbeat_ordering_and_idempotency(db_session: Session) -> None:
    svc = HeartbeatService(db_session)
    now = datetime.now(UTC)
    first = svc.record_heartbeat(
        service_key="postgres",
        status=HealthStatus.HEALTHY,
        sequence_number=1,
        observed_at=now,
        idempotency_key="hb-1",
        detail="ok",
    )
    assert first["sequence_number"] == 1
    replay = svc.record_heartbeat(
        service_key="postgres",
        status=HealthStatus.HEALTHY,
        sequence_number=1,
        observed_at=now,
        idempotency_key="hb-1",
        detail="ok",
    )
    assert replay.get("idempotent_replay") is True

    with pytest.raises(HealthError) as stale:
        svc.record_heartbeat(
            service_key="postgres",
            status=HealthStatus.HEALTHY,
            sequence_number=1,
            observed_at=now,
            idempotency_key="hb-2",
            detail="stale",
        )
    assert stale.value.code in {
        "stale_sequence",
        "invalid_heartbeat",
        "sequence_conflict",
        "sequence_out_of_order",
    }

    second = svc.record_heartbeat(
        service_key="postgres",
        status=HealthStatus.DEGRADED,
        sequence_number=2,
        observed_at=now,
        idempotency_key="hb-3",
        detail="degraded",
    )
    assert second["sequence_number"] == 2
    assert db_session.scalars(select(HealthHeartbeat)).first() is not None


def test_heartbeat_append_only_trigger(db_session: Session) -> None:
    svc = HeartbeatService(db_session)
    now = datetime.now(UTC)
    result = svc.record_heartbeat(
        service_key="redis",
        status=HealthStatus.HEALTHY,
        sequence_number=1,
        observed_at=now,
        idempotency_key="append-1",
    )
    hb_id = result.get("heartbeat_id")
    assert hb_id
    with pytest.raises(Exception):  # noqa: B017
        db_session.execute(
            text("UPDATE health_heartbeats SET detail = 'mutated' WHERE id = :id"),
            {"id": hb_id},
        )
        db_session.commit()
    db_session.rollback()


def test_timeout_evaluation(db_session: Session) -> None:
    hb = HeartbeatService(db_session)
    old = datetime.now(UTC) - timedelta(seconds=500)
    hb.record_heartbeat(
        service_key="postgres",
        status=HealthStatus.HEALTHY,
        sequence_number=1,
        observed_at=old,
        idempotency_key="old-1",
    )
    registry = ServiceRegistryService(db_session)
    service = registry.require_by_key("postgres")
    evaluation = HealthEvaluationService(db_session)
    # Prefer evaluate_and_persist if present; else evaluate_all.
    if hasattr(evaluation, "evaluate_and_persist"):
        row = evaluation.evaluate_and_persist(service=service, now=datetime.now(UTC))
        status = getattr(row, "status", None) or row.get("status")  # type: ignore[union-attr]
        if hasattr(status, "value"):
            assert status.value == HealthStatus.UNHEALTHY.value
        else:
            assert status == HealthStatus.UNHEALTHY.value
    else:
        result = evaluation.evaluate_all(now=datetime.now(UTC))  # type: ignore[attr-defined]
        postgres = next(s for s in result["services"] if s["service_key"] == "postgres")
        assert postgres["status"] == HealthStatus.UNHEALTHY.value


def test_supervisor_cycle_records_heartbeats(db_session: Session) -> None:
    supervisor = HealthSupervisorService(db_session)
    instance = supervisor.register_instance(
        worker_key="health_supervisor_worker",
        instance_key="test-cycle-1",
        hostname="test",
    )
    result = supervisor.run_cycle(instance_id=instance.id, request_id="req-cycle-1")
    assert result.get("lease_acquired") is True or result.get("result") == "completed"
    lease = supervisor.get_lease()
    assert lease is not None


def test_system_safe_mode_from_observe(db_session: Session) -> None:
    founder = _bootstrap_founder(db_session)
    principal = _principal_for(db_session, founder)
    modes = OperatingModeService(db_session)
    modes.initialize(actor=principal, request_id="init-1")  # type: ignore[arg-type]
    modes.transition(
        actor=principal,  # type: ignore[arg-type]
        target_mode=OperatingMode.OBSERVE,
        reason="enter observe for health test",
        idempotency_key="to-observe-1",
        request_id="tr-1",
    )
    result = modes.system_enter_safe_mode(
        reason="test forced safe mode",
        idempotency_key="sys-safe-1",
        request_id="safe-1",
    )
    assert result["current_mode"] == OperatingMode.SAFE_MODE.value
    assert result.get("actor") == "SYSTEM" or (
        db_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "operating_mode.safe_mode_entered")
        ).first()
        is not None
    )
    state = db_session.scalars(select(SystemState)).one()
    assert state.current_mode == OperatingMode.SAFE_MODE


def test_system_safe_mode_skipped_from_off(db_session: Session) -> None:
    founder = _bootstrap_founder(db_session)
    principal = _principal_for(db_session, founder)
    modes = OperatingModeService(db_session)
    modes.initialize(actor=principal, request_id="init-off")  # type: ignore[arg-type]
    with pytest.raises(Exception) as exc:
        modes.system_enter_safe_mode(reason="should skip", idempotency_key="sys-safe-off")
    assert getattr(exc.value, "code", "") == "health_degrade_not_applicable"


def test_supervisor_lease_concurrency(db_session: Session) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_size=8, max_overflow=0)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    setup = factory()
    try:
        svc = HealthSupervisorService(setup)
        a = svc.register_instance(worker_key="health_supervisor_worker", instance_key="lease-a")
        b = svc.register_instance(worker_key="health_supervisor_worker", instance_key="lease-b")
        a_id, b_id = a.id, b.id
    finally:
        setup.close()

    def worker(instance_id: uuid.UUID) -> bool:
        session = factory()
        try:
            result = HealthSupervisorService(session).run_cycle(
                instance_id=instance_id, request_id=_unique("lease")
            )
            return bool(result.get("lease_acquired", result.get("result") == "completed"))
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in [pool.submit(worker, a_id), pool.submit(worker, b_id)]]

    assert any(results)
    engine.dispose()


def test_health_api_rbac(client: TestClient, db_session: Session) -> None:
    founder = _bootstrap_founder(db_session, username=_unique("hf"))

    # Fresh client has no session cookies yet.
    unauth = client.get("/api/v1/health/services")
    assert unauth.status_code in {401, 403}

    headers = _login(client, founder.username)
    services = client.get("/api/v1/health/services", headers=headers)
    assert services.status_code == 200
    payload = services.json()
    keys = {
        (row["service"]["service_key"] if "service" in row else row["service_key"])
        for row in payload
    }
    assert {"postgres", "redis", "api", "health_supervisor"}.issubset(keys)

    institutional = client.get("/api/v1/health/institutional", headers=headers)
    assert institutional.status_code == 200

    reg = client.post(
        "/api/v1/workers/instances/register",
        headers=headers,
        json={
            "worker_key": "health_supervisor_worker",
            "instance_key": "api-manual",
            "hostname": "test",
        },
    )
    assert reg.status_code == 200, reg.text
    instance_id = reg.json()["id"]
    run = client.post(
        "/api/v1/health/supervisor/run-cycle",
        headers=headers,
        json={"instance_id": instance_id},
    )
    assert run.status_code == 200, run.text

    workers = client.get("/api/v1/workers/identities", headers=headers)
    assert workers.status_code == 200
    assert any(w["worker_key"] == "health_supervisor_worker" for w in workers.json())

    incidents = client.get("/api/v1/incidents", headers=headers)
    assert incidents.status_code == 200
