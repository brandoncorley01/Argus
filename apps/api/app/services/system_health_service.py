"""System Health aggregation (Phase 15) — read-only Founder-facing dashboard DTO.

Aggregates, from existing subsystems only (no new external service is ever
contacted here):

- institutional health (`institutional_health_state`)
- per-service health projections (`registered_services` / `/ready`-style probes)
- the latest host resource snapshot
- the default execution provider + active kill-switch count
- the last paper order timestamp
- the last micro-live reconciliation run, if one has ever executed
- open incidents grouped by Founder-facing severity
- the worker instance directory
- process uptime (`APP_STARTED_AT`)
- the most recent operational events

Every section that has no data is explicitly marked unavailable/empty; this
service never fabricates a healthy status or a zero P&L to fill a gap.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.redis_check import check_redis
from app.core.settings import get_settings
from app.db.session import check_postgres
from app.models import (
    HealthStatus,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    ServiceHealthProjection,
    WorkerInstanceStatus,
)
from app.models.micro_live import ReconciliationRun
from app.models.operations import OperationalSeverity
from app.models.paper_trading import ExecutionProvider, PaperOrder
from app.services.health_evaluation_service import HealthEvaluationService
from app.services.health_supervisor_service import HealthSupervisorService
from app.services.host_metrics_service import HostMetricsService
from app.services.kill_switch_service import KillSwitchService
from app.services.operational_log_service import OperationalLogService
from app.services.service_registry_service import ServiceRegistryService

# Process start time — the best available proxy for "uptime" in a
# single-process deployment; reset whenever the API/worker process restarts.
APP_STARTED_AT: datetime = datetime.now(UTC)

DEFAULT_PAPER_PROVIDER_KEY = "internal_paper"
WORKER_STALE_SECONDS = 120
SCHEDULER_FAILURE_LOOKBACK = timedelta(hours=1)
# apps/api/app/services -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]


def map_incident_severity(severity: IncidentSeverity) -> str:
    """Map `IncidentSeverity` onto the Founder-facing operational severity set.

    `IncidentSeverity.LOW` has no direct Founder-alert equivalent and is
    displayed as `info`; every other member shares its name.
    """
    if severity == IncidentSeverity.LOW:
        return "info"
    return severity.value


class SystemHealthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._evaluation = HealthEvaluationService(db)
        self._registry = ServiceRegistryService(db)
        self._supervisor = HealthSupervisorService(db)
        self._host_metrics = HostMetricsService(db)
        self._kill_switches = KillSwitchService(db)
        self._log = OperationalLogService(db)

    def _service_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for service in self._registry.list_all():
            projection = self.db.get(ServiceHealthProjection, service.id)
            rows.append(
                {
                    "service_key": service.service_key,
                    "display_name": service.display_name,
                    "criticality": service.criticality.value,
                    "is_enabled": service.is_enabled,
                    "status": projection.status.value if projection else "unknown",
                    "last_observed_at": (
                        projection.last_observed_at.isoformat()
                        if projection is not None and projection.last_observed_at is not None
                        else None
                    ),
                    "consecutive_failures": (
                        projection.consecutive_failures if projection is not None else 0
                    ),
                    "detail": projection.detail if projection is not None else None,
                }
            )
        return rows

    def _paper_section(self) -> dict[str, Any]:
        default_provider = self.db.scalar(
            select(ExecutionProvider).where(ExecutionProvider.is_default.is_(True))
        )
        active_kill_switch_count = sum(
            1 for switch in self._kill_switches.list_switches() if switch.active
        )
        last_order = self.db.scalar(
            select(PaperOrder).order_by(PaperOrder.created_at.desc()).limit(1)
        )
        return {
            "default_provider_key": default_provider.provider_key if default_provider else None,
            "default_provider_is_internal_paper": (
                default_provider is not None
                and default_provider.provider_key == DEFAULT_PAPER_PROVIDER_KEY
            ),
            "active_kill_switch_count": active_kill_switch_count,
            "last_paper_order_at": last_order.created_at.isoformat() if last_order else None,
        }

    def _reconciliation_section(self) -> dict[str, Any]:
        run = self.db.scalar(
            select(ReconciliationRun).order_by(ReconciliationRun.started_at.desc()).limit(1)
        )
        if run is None:
            return {
                "available": False,
                "note": "No micro-live reconciliation run has ever been executed.",
            }
        return {
            "available": True,
            "run_id": str(run.id),
            "provider_key": run.provider_key,
            "status": run.status,
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "discrepancy_count": len(run.discrepancies or []),
        }

    def _incidents_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "info": 0}
        open_incidents = self.db.scalars(
            select(Incident).where(
                Incident.status.in_(
                    [IncidentStatus.OPEN, IncidentStatus.INVESTIGATING, IncidentStatus.MITIGATED]
                )
            )
        )
        for incident in open_incidents:
            key = map_incident_severity(incident.severity)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _backups_dir(self) -> Path:
        settings = get_settings()
        if settings.argus_backups_dir:
            return Path(settings.argus_backups_dir)
        return _REPO_ROOT / "backups"

    def _backup_section(self) -> dict[str, Any]:
        """Read last successful backup metadata written by Control Center scripts.

        Never invents a successful backup. Verifies sha256 when the dump exists.
        """
        backups = self._backups_dir()
        last_ok = backups / "LAST_OK.json"
        meta_path: Path | None = last_ok if last_ok.is_file() else None
        if meta_path is None:
            candidates = sorted(
                backups.glob("argus_postgres_*.meta.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            meta_path = candidates[0] if candidates else None
        if meta_path is None or not meta_path.is_file():
            return {
                "available": False,
                "integrity_ok": None,
                "note": "No verified backup metadata found under backups/.",
            }
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "available": False,
                "integrity_ok": False,
                "note": f"Backup metadata unreadable: {meta_path.name}",
            }

        dump_name = data.get("filename") or data.get("path")
        dump_path = Path(dump_name) if dump_name else None
        if dump_path is not None and not dump_path.is_absolute():
            dump_path = backups / dump_path.name
        expected_sha = data.get("sha256")
        integrity_ok: bool | None = data.get("integrity_ok")
        if dump_path is not None and dump_path.is_file() and expected_sha:
            digest = hashlib.sha256(dump_path.read_bytes()).hexdigest()
            integrity_ok = digest == expected_sha
        elif integrity_ok is None and data.get("ok") is True:
            integrity_ok = True

        return {
            "available": bool(data.get("ok", True)),
            "completed_at": data.get("completed_at"),
            "filename": dump_path.name if dump_path else data.get("filename"),
            "size_bytes": data.get("size_bytes"),
            "sha256": expected_sha,
            "integrity_ok": integrity_ok,
            "note": data.get("note"),
        }

    def _incident_history(self, *, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(Incident).order_by(Incident.opened_at.desc()).limit(limit)
        )
        return [
            {
                "id": str(row.id),
                "title": row.title,
                "severity": map_incident_severity(row.severity),
                "status": row.status.value,
                "opened_at": row.opened_at.isoformat() if row.opened_at else None,
            }
            for row in rows
        ]

    def _active_alerts(
        self,
        *,
        recent_events: list[dict[str, Any]],
        incidents_by_severity: dict[str, int],
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for event in recent_events:
            if event["severity"] in {
                OperationalSeverity.CRITICAL.value,
                OperationalSeverity.HIGH.value,
            }:
                alerts.append(
                    {
                        "kind": "operational_event",
                        "severity": event["severity"],
                        "component": event["component"],
                        "description": event["description"],
                        "occurred_at": event["occurred_at"],
                        "correlation_id": event["correlation_id"],
                    }
                )
        open_critical = incidents_by_severity.get("critical", 0) + incidents_by_severity.get(
            "high", 0
        )
        if open_critical:
            alerts.append(
                {
                    "kind": "incident_summary",
                    "severity": "critical" if incidents_by_severity.get("critical") else "high",
                    "component": "api",
                    "description": (
                        f"{open_critical} open/investigating incident(s) at critical/high severity"
                    ),
                    "occurred_at": None,
                    "correlation_id": None,
                }
            )
        return alerts[:15]

    def _runtime_monitor(
        self,
        *,
        now: datetime,
        readiness: dict[str, Any],
        worker_instances: list[dict[str, Any]],
        reconciliation: dict[str, Any],
        recent_events: list[dict[str, Any]],
        critical_service_count: int,
    ) -> dict[str, Any]:
        api_ok = bool(readiness.get("postgres")) and bool(readiness.get("redis"))
        api_status = "ok" if api_ok and critical_service_count == 0 else (
            "failed" if not api_ok else "degraded"
        )

        running = [
            w
            for w in worker_instances
            if w["status"] == WorkerInstanceStatus.RUNNING.value
        ]
        fresh = []
        for w in running:
            try:
                seen = datetime.fromisoformat(w["last_seen_at"])
            except (TypeError, ValueError):
                continue
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=UTC)
            if (now - seen).total_seconds() <= WORKER_STALE_SECONDS:
                fresh.append(w)
        if fresh:
            worker_status = "ok"
            worker_detail = f"{len(fresh)} fresh running instance(s)"
        elif running:
            worker_status = "failed"
            worker_detail = "Worker registered but heartbeat is stale"
        elif worker_instances:
            worker_status = "failed"
            worker_detail = "Worker instances present but none running"
        else:
            worker_status = "failed"
            worker_detail = "No worker instances registered"

        lookback = now - SCHEDULER_FAILURE_LOOKBACK
        scheduler_failures = []
        for event in recent_events:
            if event["component"] != "scheduler":
                continue
            if event["severity"] not in {
                OperationalSeverity.CRITICAL.value,
                OperationalSeverity.HIGH.value,
            }:
                continue
            try:
                occurred = datetime.fromisoformat(event["occurred_at"])
            except (TypeError, ValueError):
                continue
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=UTC)
            if occurred >= lookback:
                scheduler_failures.append(event)
        if scheduler_failures:
            scheduler_status = "failed"
            scheduler_detail = scheduler_failures[0]["description"]
        elif worker_status == "ok":
            scheduler_status = "ok"
            scheduler_detail = "Scheduler crons hosted by running health supervisor worker"
        else:
            scheduler_status = "failed"
            scheduler_detail = "Scheduler unavailable while worker is not healthy"

        if not reconciliation.get("available"):
            recon_status = "unknown"
            recon_detail = reconciliation.get("note") or "No reconciliation run yet"
        elif reconciliation.get("status") == "failed":
            recon_status = "failed"
            recon_detail = "Last reconciliation run failed"
        elif int(reconciliation.get("discrepancy_count") or 0) > 0:
            recon_status = "degraded"
            recon_detail = (
                f"Last run completed with {reconciliation['discrepancy_count']} discrepancy(ies)"
            )
        else:
            recon_status = "ok"
            recon_detail = "Last reconciliation completed without discrepancies"

        return {
            "api": {"status": api_status, "detail": "Postgres/Redis readiness + critical services"},
            "worker": {"status": worker_status, "detail": worker_detail},
            "scheduler": {"status": scheduler_status, "detail": scheduler_detail},
            "reconciliation": {"status": recon_status, "detail": recon_detail},
        }

    def build(self) -> dict[str, Any]:
        settings = get_settings()
        now = datetime.now(UTC)

        institutional = self._evaluation.get_institutional_state()
        services = self._service_rows()
        healthy_count = sum(1 for s in services if s["status"] == HealthStatus.HEALTHY.value)
        warning_count = sum(1 for s in services if s["status"] == HealthStatus.DEGRADED.value)
        critical_count = sum(1 for s in services if s["status"] == HealthStatus.UNHEALTHY.value)

        host_snapshot = self._host_metrics.latest()
        host = (
            {
                "captured_at": host_snapshot.captured_at.isoformat(),
                "cpu_percent": host_snapshot.cpu_percent,
                "memory_percent": host_snapshot.memory_percent,
                "memory_used_bytes": host_snapshot.memory_used_bytes,
                "disk_percent": host_snapshot.disk_percent,
                "disk_used_bytes": host_snapshot.disk_used_bytes,
            }
            if host_snapshot is not None
            else None
        )

        worker_instances = [
            {
                "instance_key": instance.instance_key,
                "status": instance.status.value,
                "hostname": instance.hostname,
                "last_seen_at": instance.last_seen_at.isoformat(),
            }
            for instance in self._supervisor.list_worker_instances()
        ]

        recent_events = [
            {
                "id": str(event.id),
                "occurred_at": event.occurred_at.isoformat(),
                "component": event.component,
                "severity": event.severity,
                "description": event.description,
                "correlation_id": event.correlation_id,
            }
            for event in self._log.list_events(limit=20)
        ]

        overall_status = institutional.status.value if institutional is not None else "unknown"
        readiness = {
            "postgres": check_postgres(settings),
            "redis": check_redis(settings),
        }
        reconciliation = self._reconciliation_section()
        incidents_by_severity = self._incidents_by_severity()
        backup = self._backup_section()
        runtime_monitor = self._runtime_monitor(
            now=now,
            readiness=readiness,
            worker_instances=worker_instances,
            reconciliation=reconciliation,
            recent_events=recent_events,
            critical_service_count=critical_count,
        )
        active_alerts = self._active_alerts(
            recent_events=recent_events,
            incidents_by_severity=incidents_by_severity,
        )
        if backup.get("available") and backup.get("integrity_ok") is False:
            active_alerts.insert(
                0,
                {
                    "kind": "backup",
                    "severity": "critical",
                    "component": "database",
                    "description": "Last backup failed integrity verification",
                    "occurred_at": backup.get("completed_at"),
                    "correlation_id": None,
                },
            )
        for key, probe in runtime_monitor.items():
            if probe["status"] == "failed":
                active_alerts.append(
                    {
                        "kind": "runtime_monitor",
                        "severity": "critical" if key in {"api", "worker"} else "high",
                        "component": key if key != "reconciliation" else "paper_provider",
                        "description": f"{key} monitor: {probe['detail']}",
                        "occurred_at": now.isoformat(),
                        "correlation_id": None,
                    }
                )

        return {
            "overall_status": overall_status,
            "app_name": settings.app_name,
            "institutional_health": (
                {
                    "status": institutional.status.value,
                    "evaluation_version": institutional.evaluation_version,
                    "evaluated_at": institutional.evaluated_at.isoformat(),
                    "summary": institutional.summary,
                }
                if institutional is not None
                else None
            ),
            "services": services,
            "healthy_service_count": healthy_count,
            "warning_service_count": warning_count,
            "critical_service_count": critical_count,
            "readiness": readiness,
            "host": host,
            "paper": self._paper_section(),
            "reconciliation": reconciliation,
            "incidents_by_severity": incidents_by_severity,
            "worker_instances": worker_instances,
            "uptime_seconds": (now - APP_STARTED_AT).total_seconds(),
            "process_started_at": APP_STARTED_AT.isoformat(),
            "recent_events": recent_events,
            "generated_at": now.isoformat(),
            "runtime_monitor": runtime_monitor,
            "backup": backup,
            "active_alerts": active_alerts[:15],
            "incident_history": self._incident_history(),
        }
