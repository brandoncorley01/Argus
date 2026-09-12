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

import asyncio
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
    bucket = datetime.now(UTC).strftime("%Y%m%dT%H%M")
    correlation_id = f"health:{label.replace(' ', '_')}:{bucket}"
    try:
        return fn()
    except Exception as exc:
        _log_cycle_failure(
            ctx,
            component=component,
            description=f"{label} failed: {exc}",
            correlation_id=correlation_id,
        )
        try:
            from app.models import IncidentSeverity
            from app.services.incident_service import IncidentService

            factory = get_session_factory(ctx["settings"])
            session = factory()
            try:
                IncidentService(session).open_system_incident(
                    title=f"Autonomous failure: {label}",
                    description=str(exc)[:2000],
                    severity=IncidentSeverity.HIGH,
                    correlation_key=f"autonomous-fail:{label.replace(' ', '_')}",
                    commit=True,
                )
            finally:
                session.close()
        except Exception:  # noqa: BLE001
            pass
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
    # First health cycle after (re)start always catch-up — covers cold start
    # and resume after a hard kill while the host was asleep.
    ctx["last_wall_clock"] = utcnow()
    ctx["catch_up_pending"] = True
    ctx["catch_up_reason"] = "worker_startup"


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
    now = utcnow()
    previous = ctx.get("last_wall_clock")
    gap = wall_clock_gap(previous, now)
    ctx["last_wall_clock"] = now
    sleep_gap = should_catch_up_after_gap(gap)
    pending = bool(ctx.pop("catch_up_pending", False))
    reason = str(ctx.pop("catch_up_reason", "host_sleep_or_suspend"))

    # Job backlog can delay health cron by a few minutes without host sleep.
    # A successful catch-up must cool down so we do not re-scan forever.
    last_cu = ctx.get("last_catch_up_at")
    if last_cu is not None:
        try:
            since_cu = (now - last_cu).total_seconds()
            if since_cu < 600:
                sleep_gap = False
                pending = False
        except Exception:  # noqa: BLE001
            pass

    # Startup catch-up is discovery+prices+force scan and blocks the ARQ event
    # loop (sync I/O). Skip when a scan already finished recently.
    if pending or sleep_gap:
        try:
            factory = get_session_factory(ctx["settings"])
            probe = factory()
            try:
                from sqlalchemy import text as _sql_text

                row = probe.execute(
                    _sql_text(
                        "select completed_at from market_scan_cycles "
                        "where status = 'succeeded' and completed_at is not null "
                        "order by completed_at desc limit 1"
                    )
                ).first()
                if row and row[0] is not None:
                    completed = row[0]
                    if completed.tzinfo is None:
                        completed = completed.replace(tzinfo=UTC)
                    age = (now - completed).total_seconds()
                    if age < 300:
                        print(
                            f"runtime_continuity: skip catch-up "
                            f"(last scan {int(age)}s ago)",
                            flush=True,
                        )
                        sleep_gap = False
                        pending = False
            finally:
                probe.close()
        except Exception as exc:  # noqa: BLE001
            print(f"runtime_continuity: catch-up probe failed: {exc}", flush=True)

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

    health_error: Exception | None = None
    try:
        result = _run_logged(
            ctx,
            component=OperationalComponent.WORKER,
            label="health supervisor cycle",
            fn=_cycle,
        )
    except Exception as exc:  # noqa: BLE001 — still attempt catch-up after downtime
        health_error = exc
        result = {"ok": False, "error": str(exc)[:240]}

    if pending or sleep_gap:
        catch_reason = "worker_startup" if pending and not sleep_gap else reason
        if sleep_gap:
            catch_reason = "host_sleep_or_suspend"
        try:
            ctx["catch_up_reason"] = catch_reason
            ctx["catch_up_gap_seconds"] = format_gap_seconds(gap)
            # Bound catch-up so a hung Coinbase/discovery call cannot freeze scans.
            catch_up = await asyncio.wait_for(run_runtime_catch_up(ctx), timeout=180)
            result = {**result, "catch_up": catch_up}
            ctx["last_catch_up_at"] = utcnow()
            ctx["last_wall_clock"] = utcnow()
            print(
                f"runtime_continuity: catch-up ok reason={catch_reason} "
                f"gap_seconds={format_gap_seconds(gap)}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 — health cycle must still surface
            ctx["last_catch_up_at"] = utcnow()
            ctx["last_wall_clock"] = utcnow()
            result = {
                **result,
                "catch_up": {"ok": False, "error": str(exc)[:240], "reason": catch_reason},
            }
            print(f"runtime_continuity: catch-up failed: {exc}", flush=True)

    if health_error is not None:
        raise health_error
    return result


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


# Market scan/price jobs live in workers.market_ops (separated code), but the
# Founder Start path runs one ARQ process. Register those jobs here so scans
# cannot freeze when a second process fails to start.
from app.services.runtime_continuity import (  # noqa: E402
    format_gap_seconds,
    should_catch_up_after_gap,
    utcnow,
    wall_clock_gap,
)
from workers.market_ops.worker import (  # noqa: E402
    run_market_discovery,
    run_market_price_refresh,
    run_market_scan_cycle,
    run_runtime_catch_up,
)


class WorkerSettings:
    """ARQ worker: health + metrics + reports + market ops (single Founder process)."""

    functions = [
        run_health_supervisor_cycle,
        capture_host_metrics_cycle,
        generate_daily_report_cycle,
        run_market_scan_cycle,
        run_market_price_refresh,
        run_market_discovery,
        run_runtime_catch_up,
    ]
    cron_jobs = [
        # Health stays frequent; market jobs are staggered so they never stampede.
        cron(run_health_supervisor_cycle, second={0}),
        cron(capture_host_metrics_cycle, minute={0, 15, 30, 45}),
        cron(generate_daily_report_cycle, hour={0}, minute={15}),
        # Every 3 minutes, offset from scans — keeps Feed fresh without API starvation.
        cron(run_market_price_refresh, minute={0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 57}),
        # A full scan can take 3–4 minutes across the discovered universe.
        # Six-minute cadence prevents overlapping scans from manufacturing an
        # hours-old queue while the independent Penny lane still runs minutely.
        cron(run_market_scan_cycle, minute={1, 7, 13, 19, 25, 31, 37, 43, 49, 55}),
        cron(run_market_discovery, minute={5, 20, 35, 50}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    # Two concurrent jobs max — more caused QueuePool + 45s Home timeouts.
    max_jobs = 2
    # Coinbase refresh/scan of ~50 symbols can exceed ARQ's default 300s.
    job_timeout = 600
    # Cron work that has waited over two minutes is stale market work. ARQ
    # discards it instead of replaying old scans and refreshes hours later.
    expires_extra_ms = 120_000
    keep_result = 60
