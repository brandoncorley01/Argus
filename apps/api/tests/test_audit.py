from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.models import DepartmentCapability, OperatingMode
from app.services.audit_service import AuditError, AuditService, redact_payload
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


def test_redact_payload_masks_secrets() -> None:
    cleaned = redact_payload(
        {"username": "founder", "password": "secret", "nested": {"token": "abc", "ok": 1}}
    )
    assert cleaned is not None
    assert cleaned["username"] == "founder"
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["nested"]["token"] == "[REDACTED]"
    assert cleaned["nested"]["ok"] == 1


def test_append_and_read_audit_event(db_session: Session) -> None:
    service = AuditService(db_session)
    event = service.append(
        action="system.test",
        resource_type="test",
        resource_id="1",
        mode_at_time=OperatingMode.OFF,
        payload={"note": "phase4", "password": "should-not-store"},
    )
    db_session.commit()

    loaded = service.get(event.id)
    assert loaded is not None
    assert loaded.action == "system.test"
    assert loaded.payload is not None
    assert loaded.payload["password"] == "[REDACTED]"
    assert loaded.payload["note"] == "phase4"

    listed = service.list_events(action="system.test", limit=10)
    assert any(item.id == event.id for item in listed)


def test_run_critical_commits_mutation_with_audit(db_session: Session) -> None:
    service = AuditService(db_session)

    def mutation(session: Session) -> DepartmentCapability:
        row = DepartmentCapability(
            department_key=f"audit_phase4_ok_{datetime.now(UTC).timestamp()}",
            department_name="Audit Phase4",
            capability_level=1,
            last_reviewed_at=datetime.now(UTC),
        )
        session.add(row)
        session.flush()
        return row

    row, event = service.run_critical(
        action="department_capability.create",
        resource_type="department_capability",
        mutation=mutation,
        payload={"department_key": "audit_phase4_ok"},
    )
    assert event.id is not None
    assert db_session.get(DepartmentCapability, row.id) is not None


def test_run_critical_fail_closed_rolls_back_mutation(db_session: Session) -> None:
    service = AuditService(db_session)
    key = f"audit_phase4_fail_{datetime.now(UTC).timestamp()}"

    def mutation(session: Session) -> DepartmentCapability:
        row = DepartmentCapability(
            department_key=key,
            department_name="Audit Phase4 Fail",
            capability_level=1,
            last_reviewed_at=datetime.now(UTC),
        )
        session.add(row)
        session.flush()
        return row

    with patch.object(AuditService, "append", side_effect=AuditError("forced audit failure")):
        with pytest.raises(AuditError):
            service.run_critical(
                action="department_capability.create",
                resource_type="department_capability",
                mutation=mutation,
            )

    remaining = db_session.scalars(
        select(DepartmentCapability).where(DepartmentCapability.department_key == key)
    ).first()
    assert remaining is None


def test_audit_read_api() -> None:
    clear_settings_cache()
    reset_engine()
    get_settings()
    session = get_session_factory()()
    try:
        auth = AuthService(session)
        username = f"audit_reader_{datetime.now(UTC).strftime('%H%M%S%f')}"
        password = "audit-reader-12"
        auth.bootstrap_founder(username=username, password=password)
        service = AuditService(session)
        event = service.append(
            action="api.read_test",
            resource_type="audit_event",
            payload={"source": "test"},
        )
        session.commit()
        event_id = event.id
    finally:
        session.close()

    app = create_app()
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"identifier": username, "password": password},
        )
        assert login.status_code == 200
        cookies = dict(login.cookies)

        listed = client.get(
            "/api/v1/audit/events",
            params={"action": "api.read_test"},
            cookies=cookies,
        )
        assert listed.status_code == 200
        body = listed.json()
        assert any(item["id"] == str(event_id) for item in body["items"])

        detail = client.get(f"/api/v1/audit/events/{event_id}", cookies=cookies)
        assert detail.status_code == 200
        assert detail.json()["action"] == "api.read_test"

        missing = client.get(
            "/api/v1/audit/events/00000000-0000-0000-0000-000000000000",
            cookies=cookies,
        )
        assert missing.status_code == 404
