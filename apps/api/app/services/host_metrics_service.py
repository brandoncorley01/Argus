"""Host resource metrics capture (Phase 15) — single-host observability via `psutil`.

This observes the host the API/worker process is running on. It never
contacts an external monitoring service and never fabricates a metric —
`psutil` failures propagate rather than silently defaulting to a healthy
value.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import psutil
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.operations import HostResourceSnapshot


def _utcnow() -> datetime:
    return datetime.now(UTC)


class HostMetricsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def capture(self) -> HostResourceSnapshot:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.abspath(os.sep))

        snapshot = HostResourceSnapshot(
            captured_at=_utcnow(),
            cpu_percent=float(cpu_percent),
            memory_percent=float(memory.percent),
            memory_used_bytes=int(memory.used),
            disk_percent=float(disk.percent),
            disk_used_bytes=int(disk.used),
            details={
                "memory_total_bytes": int(memory.total),
                "disk_total_bytes": int(disk.total),
                "cpu_count": psutil.cpu_count() or 0,
            },
        )
        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def latest(self) -> HostResourceSnapshot | None:
        return self.db.scalar(
            select(HostResourceSnapshot).order_by(HostResourceSnapshot.captured_at.desc()).limit(1)
        )

    def list_recent(self, *, limit: int = 100) -> list[HostResourceSnapshot]:
        safe_limit = min(max(limit, 1), 1000)
        return list(
            self.db.scalars(
                select(HostResourceSnapshot)
                .order_by(HostResourceSnapshot.captured_at.desc())
                .limit(safe_limit)
            )
        )
