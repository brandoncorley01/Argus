"""ARQ worker for market scan + price refresh (paper automation hooks).

Separated from the health supervisor so health cycles are not coupled to
market-data jobs. Never enables live trading.
"""

from __future__ import annotations

import os
import socket
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from arq import cron
from arq.connections import RedisSettings

_API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.core.settings import clear_settings_cache, get_settings  # noqa: E402
from app.db.session import get_session_factory, reset_engine  # noqa: E402
from app.models import IncidentSeverity  # noqa: E402
from app.models.operations import OperationalComponent, OperationalSeverity  # noqa: E402
from app.services.health_supervisor_service import HealthSupervisorService  # noqa: E402
from app.services.incident_service import IncidentService  # noqa: E402
from app.services.market_scan_service import MarketScanService  # noqa: E402
from app.services.operational_log_service import OperationalLogService  # noqa: E402

T = TypeVar("T")


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings.from_dsn(settings.redis_url)


def _deterministic_correlation(label: str) -> str:
    bucket = datetime.now(UTC).strftime("%Y%m%dT%H%M")
    return f"market-ops:{label}:{bucket}"


def _open_failure_incident(ctx: dict[str, Any], *, title: str, description: str, key: str) -> None:
    try:
        factory = get_session_factory(ctx["settings"])
        session = factory()
        try:
            IncidentService(session).open_system_incident(
                title=title,
                description=description[:2000],
                severity=IncidentSeverity.HIGH,
                correlation_key=key,
                commit=True,
            )
        finally:
            session.close()
    except Exception:  # noqa: BLE001
        pass


def _log_cycle_failure(
    ctx: dict[str, Any],
    *,
    component: OperationalComponent,
    description: str,
    correlation_id: str,
    severity: OperationalSeverity = OperationalSeverity.HIGH,
) -> None:
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
    except Exception:  # noqa: BLE001
        pass


def _run_logged(
    ctx: dict[str, Any],
    *,
    component: OperationalComponent,
    label: str,
    fn: Callable[[], T],
) -> T:
    correlation_id = _deterministic_correlation(label.replace(" ", "_"))
    try:
        return fn()
    except Exception as exc:
        _log_cycle_failure(
            ctx,
            component=component,
            description=f"{label} failed: {exc}",
            correlation_id=correlation_id,
        )
        _open_failure_incident(
            ctx,
            title=f"Market ops failure: {label}",
            description=str(exc),
            key=f"market-ops-fail:{label.replace(' ', '_')}",
        )
        raise


async def startup(ctx: dict[str, Any]) -> None:
    clear_settings_cache()
    reset_engine()
    settings = get_settings()
    ctx["settings"] = settings
    instance_key = os.environ.get(
        "ARGUS_WORKER_INSTANCE_KEY", f"{socket.gethostname()}:market-ops:{os.getpid()}"
    )
    ctx["instance_key"] = instance_key
    ctx["instance_id"] = None
    factory = get_session_factory(settings)
    session = factory()
    try:
        service = HealthSupervisorService(session, settings)
        try:
            instance = service.register_instance(
                worker_key="market_ops_worker",
                instance_key=instance_key,
                hostname=socket.gethostname(),
                metadata={"role": "arq_market_ops"},
            )
            ctx["instance_id"] = instance.id
        except Exception as exc:  # noqa: BLE001 — scans must still run if registry lags
            # Missing worker identity must not freeze Live Monitor scan cycles.
            print(
                f"market_ops: health registration skipped ({exc}); "
                "continuing scan/price crons",
                flush=True,
            )
    finally:
        session.close()


async def shutdown(ctx: dict[str, Any]) -> None:
    instance_id = ctx.get("instance_id")
    if instance_id is not None:
        factory = get_session_factory(ctx["settings"])
        session = factory()
        try:
            HealthSupervisorService(session, ctx["settings"]).mark_instance_stopped(
                instance_id
            )
        finally:
            session.close()
    reset_engine()
    clear_settings_cache()


async def run_market_scan_cycle(ctx: dict[str, Any]) -> dict[str, Any]:
    force = bool(ctx.pop("force_scan", False))

    def _cycle() -> dict[str, Any]:
        factory = get_session_factory(ctx["settings"])
        # Separate sessions: a poisoned automation transaction must never
        # mark a successful scan as failed (PendingRollbackError on cycle attrs).
        scan_session = factory()
        summary: dict[str, Any]
        try:
            service = MarketScanService(scan_session)
            try:
                cycle = service.run_scan_cycle(force=force)
                summary = {
                    "ok": True,
                    "cycle_id": str(cycle.id),
                    "status": cycle.status,
                    "symbols_scanned": cycle.symbols_scanned,
                    "candidates_found": cycle.candidates_found,
                    "auto_paper_entries": 0,
                    "auto_paper_exits": 0,
                }
            except Exception as exc:  # noqa: BLE001
                try:
                    scan_session.rollback()
                except Exception:  # noqa: BLE001
                    pass
                _open_failure_incident(
                    ctx,
                    title="Market scan cycle failed",
                    description=str(exc),
                    key="market-scan:cycle",
                )
                return {"ok": False, "error": str(exc)[:240]}
        finally:
            scan_session.close()

        auto_session = factory()
        try:
            try:
                from app.services.paper_training_service import PaperTrainingService
                from app.services.trading_intelligence_service import (
                    TradingIntelligenceService,
                )

                training = PaperTrainingService(auto_session)
                auto_opened = 0
                auto_exits = 0
                for portfolio_id in training.iter_automation_portfolio_ids():
                    try:
                        exits = training.evaluate_paper_exits(
                            portfolio_id=portfolio_id, actor=None
                        )
                        auto_exits += len(exits)
                        opened = training.maybe_auto_enter_from_scan(
                            portfolio_id=portfolio_id, actor=None
                        )
                        auto_opened += len(opened)
                    except Exception as exc:  # noqa: BLE001
                        try:
                            auto_session.rollback()
                        except Exception:  # noqa: BLE001
                            pass
                        _open_failure_incident(
                            ctx,
                            title="Paper automation after scan failed",
                            description=str(exc),
                            key="paper-automation:scan",
                        )
                try:
                    TradingIntelligenceService(auto_session).resolve_pending_misses()
                except Exception as exc:  # noqa: BLE001
                    try:
                        auto_session.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                    _open_failure_incident(
                        ctx,
                        title="Trading intelligence resolve failed",
                        description=str(exc),
                        key="trading-intelligence:resolve",
                    )
                try:
                    from app.services.advanced_learning_service import (
                        AdvancedLearningService,
                    )

                    learning = AdvancedLearningService(auto_session)
                    for portfolio_id in training.iter_automation_portfolio_ids():
                        try:
                            learning.evaluate_cycle(portfolio_id)
                        except Exception as exc:  # noqa: BLE001
                            try:
                                auto_session.rollback()
                            except Exception:  # noqa: BLE001
                                pass
                            _open_failure_incident(
                                ctx,
                                title="Advanced learning evaluate failed",
                                description=str(exc),
                                key="advanced-learning:evaluate",
                            )
                except Exception as exc:  # noqa: BLE001
                    _open_failure_incident(
                        ctx,
                        title="Advanced learning evaluate failed",
                        description=str(exc),
                        key="advanced-learning:evaluate",
                    )
                summary["auto_paper_entries"] = auto_opened
                summary["auto_paper_exits"] = auto_exits
            except Exception as exc:  # noqa: BLE001
                try:
                    auto_session.rollback()
                except Exception:  # noqa: BLE001
                    pass
                _open_failure_incident(
                    ctx,
                    title="Paper automation after scan failed",
                    description=str(exc),
                    key="paper-automation:scan",
                )
        finally:
            auto_session.close()

        return summary

    return _run_logged(
        ctx,
        component=OperationalComponent.MARKET_DATA,
        label="market scan cycle",
        fn=_cycle,
    )


async def run_market_price_refresh(ctx: dict[str, Any]) -> dict[str, Any]:
    def _cycle() -> dict[str, Any]:
        factory = get_session_factory(ctx["settings"])
        session = factory()
        try:
            from app.services.market_price_refresh_service import (
                MarketPriceRefreshError,
                MarketPriceRefreshService,
            )

            try:
                result = MarketPriceRefreshService(session).refresh_recent_prices(
                    actor=None
                )
                auto_exits = 0
                try:
                    from app.services.paper_training_service import PaperTrainingService

                    training = PaperTrainingService(session)
                    for portfolio_id in training.iter_automation_portfolio_ids():
                        auto_exits += len(
                            training.evaluate_paper_exits(
                                portfolio_id=portfolio_id, actor=None
                            )
                        )
                except Exception as exc:  # noqa: BLE001
                    _open_failure_incident(
                        ctx,
                        title="Paper auto-exit during price refresh failed",
                        description=str(exc),
                        key="paper-automation:price-refresh",
                    )
                return {
                    "ok": result.get("ok"),
                    "records_accepted": result.get("records_accepted"),
                    "failed_count": len(result.get("failed") or []),
                    "auto_paper_exits": auto_exits,
                }
            except MarketPriceRefreshError as exc:
                _open_failure_incident(
                    ctx,
                    title="Market price refresh failed",
                    description=exc.message,
                    key=f"market-price-refresh:{exc.code}",
                )
                return {"ok": False, "code": exc.code, "error": exc.message[:240]}
            except Exception as exc:  # noqa: BLE001
                _open_failure_incident(
                    ctx,
                    title="Market price refresh failed",
                    description=str(exc),
                    key="market-price-refresh:unexpected",
                )
                return {"ok": False, "error": str(exc)[:240]}
        finally:
            session.close()

    return _run_logged(
        ctx,
        component=OperationalComponent.MARKET_DATA,
        label="market price refresh",
        fn=_cycle,
    )


async def run_runtime_catch_up(ctx: dict[str, Any]) -> dict[str, Any]:
    """After host sleep/startup: refresh prices, then force a scan + exits/entries."""
    reason = str(ctx.pop("catch_up_reason", "downtime"))
    gap_seconds = ctx.pop("catch_up_gap_seconds", None)
    prices = await run_market_price_refresh(ctx)
    ctx["force_scan"] = True
    scan = await run_market_scan_cycle(ctx)
    return {
        "ok": True,
        "reason": reason,
        "gap_seconds": gap_seconds,
        "prices": prices,
        "scan": scan,
    }


class WorkerSettings:
    """ARQ worker settings for market ops."""

    functions = [run_market_scan_cycle, run_market_price_refresh, run_runtime_catch_up]
    cron_jobs = [
        cron(run_market_price_refresh, minute=set(range(0, 60, 2))),
        cron(run_market_scan_cycle, minute=set(range(60))),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 3
