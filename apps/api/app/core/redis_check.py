from __future__ import annotations

import redis

from app.core.settings import Settings, get_settings


def check_redis(settings: Settings | None = None) -> dict[str, str]:
    """Return redis probe result without raising on connection failure."""
    cfg = settings or get_settings()
    client: redis.Redis | None = None
    try:
        client = redis.Redis.from_url(cfg.redis_url, socket_connect_timeout=2)
        pong = client.ping()
        if pong is True:
            return {"status": "ok"}
        return {"status": "error", "detail": "unexpected ping response"}
    except Exception as exc:  # noqa: BLE001 — probe must never crash the process
        return {"status": "error", "detail": str(exc)}
    finally:
        if client is not None:
            client.close()
