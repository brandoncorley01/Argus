"""Unit tests for DB engine pool hardening."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.settings import SettingsError, clear_settings_cache, get_settings
from app.db import session as session_mod
from app.db.session import get_engine, reset_engine


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    clear_settings_cache()
    reset_engine()
    yield
    clear_settings_cache()
    reset_engine()


def test_pool_dims_by_role() -> None:
    assert session_mod._pool_dims("api") == (10, 10)
    assert session_mod._pool_dims("worker") == (6, 6)
    assert session_mod._pool_dims("app") == (5, 5)


def test_connect_args_include_idle_txn_timeout() -> None:
    opts = str(session_mod._connect_args("api")["options"])
    assert "idle_in_transaction_session_timeout=60000" in opts
    assert "application_name=argus-api" in opts


def test_engine_uses_small_pool_and_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        get_settings()
    except SettingsError:
        pytest.skip("DATABASE_URL not configured")

    monkeypatch.setenv("ARGUS_PROCESS_ROLE", "api")
    reset_engine()
    engine = get_engine()
    assert engine.pool.size() == 10
    assert engine.pool._max_overflow == 10  # noqa: SLF001
    assert engine.pool._timeout == 15  # noqa: SLF001
