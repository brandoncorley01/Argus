from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.configurations import router as configurations_router
from app.api.v1.policies import router as policies_router
from app.core.settings import SettingsError, get_settings
from app.db.session import get_engine, reset_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Fail closed at startup if settings are invalid.
    settings = get_settings()
    get_engine(settings)
    yield
    reset_engine()


def create_app() -> FastAPI:
    try:
        settings = get_settings()
    except SettingsError:
        # Re-raise so process managers see a hard failure instead of a half-live app.
        raise

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(audit_router)
    app.include_router(configurations_router)
    app.include_router(policies_router)
    return app


app = create_app()
