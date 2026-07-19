"""ARQ worker entry for the Argus health supervisor (Phase 8)."""

from __future__ import annotations

import os
import socket
import sys
import uuid
from pathlib import Path
from typing import Any

from arq import cron
from arq.connections import RedisSettings

_API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.core.settings import clear_settings_cache, get_settings  # noqa: E402
from app.db.session import get_session_factory, reset_engine  # noqa: E402
from app.services.health_supervisor_service import HealthSupervisorService  # noqa: E402


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings.from_dsn(settings.redis_url)


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


class WorkerSettings:
    """ARQ worker settings for `arq workers.health_supervisor.worker.WorkerSettings`."""

    functions = [run_health_supervisor_cycle]
    cron_jobs = [cron(run_health_supervisor_cycle, second={0, 30})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 1
