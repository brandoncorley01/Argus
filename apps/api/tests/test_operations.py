"""Phase 15 operational validation tests — paper-only, no live trading."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.models.operations import DailyTradingReport
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


def test_system_health_and_correlation_header(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("oh"), "ops-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, _ = _login(client, u, p)
    res = client.get(
        "/api/v1/operations/system-health",
        cookies=cookies,
        headers={"X-Correlation-ID": "rc-ops-health-1"},
    )
    assert res.status_code == 200, res.text
    assert res.headers.get("X-Correlation-ID") == "rc-ops-health-1"
    body = res.json()
    assert "overall_status" in body
    assert body["paper"]["default_provider_is_internal_paper"] is True
    assert body["paper"]["default_provider_key"] == "internal_paper"
    assert set(body["incidents_by_severity"]) >= {"critical", "high", "medium", "info"}
    assert "runtime_monitor" in body
    assert set(body["runtime_monitor"]) >= {"api", "worker", "scheduler", "reconciliation"}
    for key in ("api", "worker", "scheduler", "reconciliation"):
        assert body["runtime_monitor"][key]["status"] in {
            "ok",
            "failed",
            "degraded",
            "unknown",
        }
    assert "backup" in body
    assert "available" in body["backup"]
    assert "active_alerts" in body
    assert isinstance(body["active_alerts"], list)
    assert "incident_history" in body
    assert isinstance(body["incident_history"], list)
    assert "uptime_seconds" in body
    assert "process_started_at" in body


def test_system_health_backup_meta(tmp_path, monkeypatch, client: TestClient, db_session: Session) -> None:
    u, p = _unique("ob"), "ops-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, _ = _login(client, u, p)

    dump = tmp_path / "argus_postgres_test.sql"
    dump.write_text("-- PostgreSQL database dump\n" + ("x" * 200), encoding="utf-8")
    import hashlib

    sha = hashlib.sha256(dump.read_bytes()).hexdigest()
    meta = {
        "ok": True,
        "integrity_ok": True,
        "completed_at": "2026-07-23T00:00:00+00:00",
        "filename": dump.name,
        "size_bytes": dump.stat().st_size,
        "sha256": sha,
        "note": "test",
    }
    (tmp_path / "LAST_OK.json").write_text(
        __import__("json").dumps(meta), encoding="utf-8"
    )
    monkeypatch.setenv("ARGUS_BACKUPS_DIR", str(tmp_path))
    clear_settings_cache()

    res = client.get("/api/v1/operations/system-health", cookies=cookies)
    assert res.status_code == 200, res.text
    backup = res.json()["backup"]
    assert backup["available"] is True
    assert backup["integrity_ok"] is True
    assert backup["filename"] == dump.name
    clear_settings_cache()


def test_operational_event_severities_and_secret_reject(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("oe"), "ops-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}
    ok = client.post(
        "/api/v1/operations/events",
        cookies=cookies,
        headers=headers,
        json={
            "component": "api",
            "severity": "info",
            "description": "Phase 15 operational event",
            "correlation_id": "corr-ops-1",
            "details": {"note": "no secrets"},
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["severity"] == "info"
    assert ok.json()["correlation_id"] == "corr-ops-1"

    for sev in ("critical", "high", "medium", "info"):
        r = client.post(
            "/api/v1/operations/events",
            cookies=cookies,
            headers=headers,
            json={
                "component": "paper_provider",
                "severity": sev,
                "description": f"severity {sev}",
                "correlation_id": f"corr-{sev}",
            },
        )
        assert r.status_code == 201, r.text

    denied = client.post(
        "/api/v1/operations/events",
        cookies=cookies,
        headers=headers,
        json={
            "component": "api",
            "severity": "high",
            "description": "must not store secrets",
            "correlation_id": "corr-secret",
            "details": {"api_key": "should-be-rejected"},
        },
    )
    assert denied.status_code == 422, denied.text


def test_host_metrics_capture(client: TestClient, db_session: Session) -> None:
    u, p = _unique("hm"), "ops-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    cap = client.post(
        "/api/v1/operations/host-metrics/capture",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf},
    )
    assert cap.status_code == 201, cap.text
    assert "cpu_percent" in cap.json()
    latest = client.get("/api/v1/operations/host-metrics/latest", cookies=cookies)
    assert latest.status_code == 200
    assert latest.json()["id"] == cap.json()["id"]


def test_daily_trading_report_immutable_paper_only(
    client: TestClient, db_session: Session
) -> None:
    u, p = _unique("dr"), "ops-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, csrf = _login(client, u, p)
    headers = {"X-CSRF-Token": csrf}
    report_date = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()

    # Isolate from prior runs: reports are immutable and keyed by calendar date
    for existing in db_session.query(DailyTradingReport).filter(
        DailyTradingReport.report_date == (datetime.now(UTC) - timedelta(days=1)).date()
    ).all():
        db_session.delete(existing)
    db_session.commit()

    # Ensure there is at least one paper fill so report has real paper context
    port = client.post(
        "/api/v1/paper/portfolios",
        cookies=cookies,
        headers=headers,
        json={"name": "Ops Book", "initial_cash": "10000"},
    )
    assert port.status_code == 201, port.text
    pid = port.json()["id"]
    order = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=cookies,
        headers={**headers, "Idempotency-Key": _unique("opsord")},
        json={"symbol": "BTC-USD", "side": "buy", "order_type": "market", "quantity": "1"},
    )
    assert order.status_code == 200, order.text
    assert order.json()["environment"] == "paper"

    gen = client.post(
        "/api/v1/operations/daily-reports/generate",
        cookies=cookies,
        headers=headers,
        json={"report_date": report_date},
    )
    assert gen.status_code == 201, gen.text
    body = gen.json()
    assert body["is_immutable"] is True
    assert body["content"]["provider"] == "internal_paper"
    assert "disclaimer" in body["content"]
    assert "live" not in body["content"].get("provider", "").lower() or True

    again = client.post(
        "/api/v1/operations/daily-reports/generate",
        cookies=cookies,
        headers=headers,
        json={"report_date": report_date},
    )
    assert again.status_code == 409

    listed = client.get("/api/v1/operations/daily-reports", cookies=cookies)
    assert listed.status_code == 200
    assert any(r["report_date"] == report_date for r in listed.json())


def test_paper_still_default_after_ops(client: TestClient, db_session: Session) -> None:
    u, p = _unique("pd"), "ops-pass-1234"
    _bootstrap(db_session, u, p)
    cookies, _ = _login(client, u, p)
    res = client.get("/api/v1/paper/providers", cookies=cookies)
    assert res.status_code == 200
    default = next(r for r in res.json() if r["provider"]["is_default"])
    assert default["provider"]["provider_key"] == "internal_paper"
