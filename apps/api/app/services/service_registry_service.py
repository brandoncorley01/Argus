"""Registered service directory lookups (Phase 8)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RegisteredService


class ServiceRegistryError(RuntimeError):
    """Domain error for registered-service directory lookups."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ServiceRegistryService:
    def __init__(self, session: Session) -> None:
        self._db = session

    def list_all(self) -> list[RegisteredService]:
        return list(
            self._db.scalars(select(RegisteredService).order_by(RegisteredService.service_key.asc()))
        )

    def list_enabled(self) -> list[RegisteredService]:
        return list(
            self._db.scalars(
                select(RegisteredService)
                .where(RegisteredService.is_enabled.is_(True))
                .order_by(RegisteredService.service_key.asc())
            )
        )

    def get_by_key(self, service_key: str) -> RegisteredService | None:
        return self._db.scalars(
            select(RegisteredService).where(RegisteredService.service_key == service_key)
        ).first()

    def get_by_id(self, service_id: uuid.UUID) -> RegisteredService | None:
        return self._db.get(RegisteredService, service_id)

    def require_by_key(self, service_key: str) -> RegisteredService:
        service = self.get_by_key(service_key)
        if service is None:
            raise ServiceRegistryError(
                "service_not_found", f"registered service '{service_key}' not found"
            )
        return service

    def lock_by_key(self, service_key: str) -> RegisteredService:
        """Lock the registered_services row FOR UPDATE.

        Callers (e.g. HeartbeatService) use this to serialize concurrent
        heartbeat ingestion / projection updates for the same service.
        """
        service = self._db.scalars(
            select(RegisteredService)
            .where(RegisteredService.service_key == service_key)
            .with_for_update()
        ).first()
        if service is None:
            raise ServiceRegistryError(
                "service_not_found", f"registered service '{service_key}' not found"
            )
        return service
