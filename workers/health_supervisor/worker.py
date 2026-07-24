"""ARQ worker entry for the Argus health supervisor (Phase 8) + operational
validation crons (Phase 15).

Phase 15 additions reuse the existing health-supervisor worker process
rather than introducing a new worker/service:

- every 5 minutes: capture a host resource snapshot (`HostMetricsService`)
- once daily at 00:15 UTC: generate yesterday's daily trading report
  (`DailyTradingReportService`), idempotently — a report that already
  exists for that date is left untouched (immutable)

Any cron failure (health cycle, host metrics capture, or daily report
generation) is recorded as an `OperationalEvent` with a correlation id
before the original exception is re-raised, so ARQ's own failure/retry
visibility is preserved while the operational log still captures the event.
"""

from __future__ import annotations

import os
import socket
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from arq import cron
from arq.connections import RedisSettings

_API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.core.settings import clear_settings_cache, get_settings  # noqa: E402
from app.db.session import get_session_factory, reset_engine  # noqa: E402
from app.models.operations import OperationalComponent, OperationalSeverity  # noqa: E402
from app.services.daily_trading_report_service import (  # noqa: E402
    DailyTradingReportError,
    DailyTradingReportService,
)
from app.services.health_supervisor_service import HealthSupervisorService  # noqa: E402
from app.services.host_metrics_service import HostMetricsService  # noqa: E402
from app.services.operational_log_service import OperationalLogService  # noqa: E402

T = TypeVar("T")


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings.from_dsn(settings.redis_url)


def _log_cycle_failure(
    ctx: dict[str, Any],
    *,
    component: OperationalComponent,
    description: str,
    correlation_id: str,
    severity: OperationalSeverity = OperationalSeverity.HIGH,
) -> None:
    """Best-effort operational-event write. Never raises — a logging
    failure must not mask (or replace) the original cycle failure."""
    try:
        factory = get_session_factory(ctx["settings"])
        log_session = factory()
        try:
            OperationalLogService(log_session).append(
                component=component,
                severity=severity,
                description=description,
                correlation_id=correlation_id,
                details={},
            )
        finally:
            log_session.close()
    except Exception:  # noqa: BLE001 — logging must never crash the worker
        pass


def _run_logged(
    ctx: dict[str, Any],
    *,
    component: OperationalComponent,
    label: str,
    fn: Callable[[], T],
) -> T:
    correlation_id = str(uuid.uuid4())
    try:
        return fn()
    except Exception as exc:
        _log_cycle_failure(
            ctx,
            component=component,
            description=f"{label} failed: {exc}",
            correlation_id=correlation_id,
        )
        raise


async def startup(ctx: dict[str, Any]) -> None:
    clear_settings_cache()
    reset_engine()
    settings = get_settings()
    ctx["settings"] = settings
    instance_key = os.environ.get(
        "ARGUS_WORKER_INSTANCE_KEY", f"{socket.gethostname()}:{os.getpid()}"
    )
    factory = get_session_factory(settings)
    session = factory()
    try:
        service = HealthSupervisorService(session, settings)
        instance = service.register_instance(
            worker_key="health_supervisor_worker",
            instance_key=instance_key,
            hostname=socket.gethostname(),
            metadata={"role": "arq_health_supervisor"},
        )
        ctx["instance_id"] = instance.id
        ctx["instance_key"] = instance_key
    finally:
        session.close()


async def shutdown(ctx: dict[str, Any]) -> None:
    instance_id = ctx.get("instance_id")
    if instance_id is not None:
        factory = get_session_factory(ctx["settings"])
        session = factory()
        try:
            HealthSupervisorService(session, ctx["settings"]).mark_instance_stopped(instance_id)
        finally:
            session.close()
    reset_engine()
    clear_settings_cache()


async def run_health_supervisor_cycle(ctx: dict[str, Any]) -> dict[str, Any]:
    def _cycle() -> dict[str, Any]:
        factory = get_session_factory(ctx["settings"])
        session = factory()
        try:
            service = HealthSupervisorService(session, ctx["settings"])
            return service.run_cycle(
                instance_id=ctx["instance_id"],
                request_id=str(uuid.uuid4()),
            )
        finally:
            session.close()

    return _run_logged(
        ctx, component=OperationalComponent.WORKER, label="health supervisor cycle", fn=_cycle
    )


async def capture_host_metrics_cycle(ctx: dict[str, Any]) -> dict[str, Any]:
    def _cycle() -> dict[str, Any]:
        factory = get_session_factory(ctx["settings"])
        session = factory()
        try:
            snapshot = HostMetricsService(session).capture()
            return {
                "captured": True,
                "snapshot_id": str(snapshot.id),
                "captured_at": snapshot.captured_at.isoformat(),
            }
        finally:
            session.close()

    return _run_logged(
        ctx, component=OperationalComponent.HOST, label="host metrics capture", fn=_cycle
    )


async def generate_daily_report_cycle(ctx: dict[str, Any]) -> dict[str, Any]:
    def _cycle() -> dict[str, Any]:
        factory = get_session_factory(ctx["settings"])
        session = factory()
        try:
            target_date = (datetime.now(UTC) - timedelta(days=1)).date()
            service = DailyTradingReportService(session)
            try:
                report = service.generate(report_date=target_date, actor=None)
                return {
                    "generated": True,
                    "report_date": target_date.isoformat(),
                    "report_id": str(report.id),
                }
            except DailyTradingReportError as exc:
                if exc.code == "report_immutable":
                    # Idempotent: already generated for this date, nothing to do.
                    return {
                        "generated": False,
                        "reason": "already_exists",
                        "report_date": target_date.isoformat(),
                    }
                raise
        finally:
            session.close()

    return _run_logged(
        ctx,
        component=OperationalComponent.SCHEDULER,
        label="daily trading report generation",
        fn=_cycle,
    )


class WorkerSettings:
    """ARQ worker settings for `arq workers.health_supervisor.worker.WorkerSettings`."""

    functions = [
        run_health_supervisor_cycle,
        capture_host_metrics_cycle,
        generate_daily_report_cycle,
    ]
    cron_jobs = [
        cron(run_health_supervisor_cycle, second={0, 30}),
        cron(capture_host_metrics_cycle, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(generate_daily_report_cycle, hour={0}, minute={15}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 1
