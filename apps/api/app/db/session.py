from __future__ import annotations

import os
import sys
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings, get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _process_role() -> str:
    """Label connections so pg_stat_activity shows api vs worker vs other."""
    explicit = (os.environ.get("ARGUS_PROCESS_ROLE") or "").strip().lower()
    if explicit:
        return explicit
    joined = " ".join(sys.argv).lower()
    if "uvicorn" in joined:
        return "api"
    if "arq" in joined or "workers." in joined:
        return "worker"
    return "app"


def _pool_dims(role: str) -> tuple[int, int]:
    """Keep per-process pools small so API + worker cannot exhaust Postgres.

    Prior 20+20 pools × duplicate processes hit QueuePool timeouts and made
    every Founder request look like an API malfunction.
    """
    if role == "worker":
        return 6, 6
    if role == "api":
        return 10, 10
    return 5, 5


def _connect_args(role: str) -> dict[str, object]:
    # idle_in_transaction_session_timeout: kill clients that hold a txn open
    # while doing Coinbase HTTP / Python work (the root of pool starvation).
    # statement_timeout / lock_timeout: fail closed instead of wedging forever.
    return {
        "connect_timeout": 5,
        "options": (
            f"-c application_name=argus-{role} "
            "-c idle_in_transaction_session_timeout=60000 "
            "-c statement_timeout=180000 "
            "-c lock_timeout=30000"
        ),
    }


def get_engine(settings: Settings | None = None) -> Engine:
    global _engine, _SessionLocal
    cfg = settings or get_settings()
    if _engine is None:
        role = _process_role()
        pool_size, max_overflow = _pool_dims(role)
        _engine = create_engine(
            cfg.database_url,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            # Fail fast under pressure — 60s waits made the UI look "dead".
            pool_timeout=15,
            pool_recycle=900,
            pool_reset_on_return="rollback",
            connect_args=_connect_args(role),
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    get_engine(settings)
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        try:
            session.rollback()
        except Exception:  # noqa: BLE001 — close must still run
            pass
        raise
    finally:
        session.close()


def check_postgres(settings: Settings | None = None) -> dict[str, str]:
    """Return postgres probe result without raising on connection failure."""
    try:
        engine = get_engine(settings)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 — probe must never crash the process
        return {"status": "error", "detail": str(exc)}


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
