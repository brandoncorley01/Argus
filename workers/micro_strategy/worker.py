"""Dedicated ARQ lane for Micro paper strategies.

This worker consumes only fresh ``range_micro`` and ``trend_pullback_micro``
candidates produced by the market scanner. It never refreshes prices, runs the
full scanner, bypasses portfolio liquidity rules, or enables live trading.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arq import cron
from arq.connections import RedisSettings

_API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.core.settings import clear_settings_cache, get_settings  # noqa: E402
from app.db.session import get_session_factory, reset_engine  # noqa: E402
from app.models import HealthStatus  # noqa: E402
from app.services.health_supervisor_service import HealthSupervisorService  # noqa: E402


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def startup(ctx: dict[str, Any]) -> None:
    clear_settings_cache()
    reset_engine()
    settings = get_settings()
    ctx["settings"] = settings
    instance_key = os.environ.get(
        "ARGUS_WORKER_INSTANCE_KEY",
        f"{socket.gethostname()}:micro-strategy:{os.getpid()}",
    )
    session = get_session_factory(settings)()
    try:
        instance = HealthSupervisorService(session, settings).register_instance(
            worker_key="micro_strategy_worker",
            instance_key=instance_key,
            hostname=socket.gethostname(),
            metadata={
                "role": "arq_micro_strategy",
                "paper_only": True,
                "live_trading_enabled": False,
            },
        )
        ctx["instance_id"] = instance.id
    finally:
        session.close()


async def shutdown(ctx: dict[str, Any]) -> None:
    instance_id = ctx.get("instance_id")
    if instance_id is not None:
        session = get_session_factory(ctx["settings"])()
        try:
            HealthSupervisorService(
                session, ctx["settings"]
            ).mark_instance_stopped(instance_id)
        finally:
            session.close()
    reset_engine()
    clear_settings_cache()


async def run_micro_strategy_cycle(ctx: dict[str, Any]) -> dict[str, Any]:
    """Evaluate Micro entry candidates on an independent one-job lane."""

    def _cycle() -> dict[str, Any]:
        from app.services.paper_opportunity_detectors import MICRO_STRATEGY_KEYS
        from app.services.market_price_refresh_service import (
            REFRESH_TIMEFRAMES_FAST,
            MarketPriceRefreshService,
        )
        from app.services.paper_training_service import PaperTrainingService

        session = get_session_factory(ctx["settings"])()
        try:
            instance_id = ctx.get("instance_id")
            if instance_id is None:
                raise RuntimeError("Micro worker instance was not registered")
            HealthSupervisorService(
                session, ctx["settings"]
            ).touch_instance(instance_id)
            training = PaperTrainingService(session)
            opened: list[dict[str, Any]] = []
            closed: list[dict[str, Any]] = []
            portfolio_ids = training.iter_automation_portfolio_ids()
            open_symbols: list[str] = []
            for portfolio_id in portfolio_ids:
                open_symbols.extend(
                    training.open_position_symbols_for_strategies(
                        portfolio_id=portfolio_id,
                        strategy_keys=set(MICRO_STRATEGY_KEYS),
                    )
                )
            refresh_result: dict[str, Any] | None = None
            if open_symbols:
                refresh_result = MarketPriceRefreshService(session).refresh_recent_prices(
                    actor=None,
                    symbols=sorted(set(open_symbols)),
                    timeframes=REFRESH_TIMEFRAMES_FAST,
                )
            for portfolio_id in portfolio_ids:
                closed.extend(
                    training.evaluate_paper_exits(
                        portfolio_id=portfolio_id,
                        actor=None,
                        allowed_strategy_keys=set(MICRO_STRATEGY_KEYS),
                    )
                )
                opened.extend(
                    training.maybe_auto_enter_from_scan(
                        portfolio_id=portfolio_id,
                        actor=None,
                        allowed_strategy_keys=set(MICRO_STRATEGY_KEYS),
                    )
                )
            observed_at = datetime.now(UTC)
            supervisor = HealthSupervisorService(session, ctx["settings"])
            supervisor.record_worker_heartbeat(
                service_key="micro_strategy",
                instance_id=instance_id,
                status=HealthStatus.HEALTHY,
                observed_at=observed_at,
                idempotency_key=(
                    f"micro_strategy:{instance_id}:"
                    f"{observed_at.strftime('%Y%m%dT%H%M')}"
                ),
                detail="Dedicated Micro strategy cycle completed",
                payload={
                    "entries": len(opened),
                    "exits": len(closed),
                    "open_symbols_refreshed": sorted(set(open_symbols)),
                    "strategies": sorted(MICRO_STRATEGY_KEYS),
                    "paper_only": True,
                },
            )
            return {
                "ok": True,
                "lane": "micro_strategy",
                "strategies": sorted(MICRO_STRATEGY_KEYS),
                "entries": len(opened),
                "exits": len(closed),
                "opened": opened,
                "closed": closed,
                "price_refresh_ok": (
                    bool(refresh_result.get("ok")) if refresh_result is not None else None
                ),
                "evaluated_at": datetime.now(UTC).isoformat(),
                "paper_only": True,
                "live_trading_enabled": False,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return await asyncio.to_thread(_cycle)


class WorkerSettings:
    """Exactly one dedicated, serialized Micro strategy worker."""

    functions = [run_micro_strategy_cycle]
    cron_jobs = [cron(run_micro_strategy_cycle, second={30})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    queue_name = "arq:queue:micro_strategy"
    max_jobs = 1
    job_timeout = 120
    expires_extra_ms = 90_000
    keep_result = 60
