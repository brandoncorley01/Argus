from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status

from app.core.redis_check import check_redis
from app.core.settings import get_settings
from app.db.session import check_postgres

router = APIRouter(tags=["health"])


def _probe_dependencies() -> dict[str, Any]:
    settings = get_settings()
    postgres = check_postgres(settings)
    redis_result = check_redis(settings)
    overall = (
        "ok"
        if postgres.get("status") == "ok" and redis_result.get("status") == "ok"
        else "degraded"
    )
    return {
        "service": settings.app_name,
        "status": overall,
        "dependencies": {
            "postgres": postgres,
            "redis": redis_result,
        },
    }


@router.get("/health")
def health() -> dict[str, Any]:
    """Liveness-oriented summary; always returns HTTP 200 if the process is up."""
    return _probe_dependencies()


@router.get("/ready")
def ready(response: Response) -> dict[str, Any]:
    """Readiness: fail closed with 503 when Postgres or Redis is unavailable."""
    payload = _probe_dependencies()
    if payload["status"] != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        payload["status"] = "not_ready"
    else:
        payload["status"] = "ready"
    return payload
