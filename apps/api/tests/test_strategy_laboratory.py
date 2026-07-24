"""Phase 11 Strategy Laboratory tests — research only, synthetic fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
from app.main import create_app
from app.services.auth_service import AuthService
from app.services.strategy_engine import (
    STRATEGY_REGISTRY,
    ExecutionAssumptions,
    StrategyEngineError,
    bars_from_dicts,
    hash_result,
    run_bar_backtest,
    run_monte_carlo,
    run_optimization,
    run_walk_forward,
)
from app.services.strategy_laboratory_service import (
    StrategyLabError,
    StrategyLaboratoryService,
)


@pytest.fixture(autouse=True)
def _allow_additional_founders(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ALLOW_ADDITIONAL_FOUNDERS", "true")
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def db_session() -> Iterator[Session]:
    clear_settings_cache()
    reset_engine()
    get_settings()
    session = get_session_factory()()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
        reset_engine()
        clear_settings_cache()


@pytest.fixture
def client() -> Iterator[TestClient]:
    clear_settings_cache()
    reset_engine()
    get_settings()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    reset_engine()
    clear_settings_cache()


def _unique(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%H%M%S%f')}"


def _bootstrap_founder(db_session: Session, username: str, password: str):
    return AuthService(db_session).bootstrap_founder(
        username=username,
        password=password,
        email=f"{username}@example.com",
    )


def _login(client: TestClient, identifier: str, password: str) -> tuple[dict[str, str], str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert response.status_code == 200, response.text
    return dict(response.cookies), response.json()["csrf_token"]


def _synthetic_research_bars(n: int = 120) -> list[dict]:
    """Deterministic synthetic research fixture — not real market prices."""
    bars: list[dict] = []
    start = datetime(2024, 1, 1, tzinfo=UTC)
    price = 100.0
    for i in range(n):
        # Gentle deterministic drift + oscillation (research fixture only)
        price = price * (1.0 + 0.001 * ((i % 17) - 8) / 10.0)
        open_p = price
        high_p = price * 1.005
        low_p = price * 0.995
        close_p = price * (1.0 + 0.0005 * ((i % 5) - 2))
        bars.append(
            {
                "open_time": (start + timedelta(hours=i)).isoformat(),
                "open": round(open_p, 6),
                "high": round(high_p, 6),
                "low": round(low_p, 6),
                "close": round(close_p, 6),
                "volume": 1000.0 + i,
            }
        )
        price = close_p
    return bars


def test_create_strategy_version_lifecycle_approve(
    client: TestClient, db_session: Session
) -> None:
    username = _unique("lab_f")
    password = "lab-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, csrf = _login(client, username, password)
    headers = {"X-CSRF-Token": csrf}

    doc = client.post(
        "/api/v1/strategies",
        cookies=cookies,
        headers=headers,
        json={
            "strategy_key": _unique("sma_key"),
            "name": "SMA Research Strategy",
            "description": "Phase 11 research document",
            "tags": ["research", "synthetic"],
        },
    )
    assert doc.status_code == 201, doc.text
    document_id = doc.json()["id"]

    ver = client.post(
        f"/api/v1/strategies/{document_id}/versions",
        cookies=cookies,
        headers=headers,
        json={
            "version_label": "v1",
            "strategy_class": "sma_crossover",
            "parameters": {"fast": 5, "slow": 20},
            "change_summary": "Initial draft",
        },
    )
    assert ver.status_code == 201, ver.text
    version_id = ver.json()["id"]
    assert ver.json()["status"] == "draft"
    assert ver.json()["is_immutable"] is False

    submitted = client.post(
        f"/api/v1/strategies/versions/{version_id}/submit",
        cookies=cookies,
        headers=headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "under_review"
    assert submitted.json()["is_immutable"] is True

    approved = client.post(
        f"/api/v1/strategies/versions/{version_id}/approve",
        cookies=cookies,
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_at"] is not None


def test_immutable_version_cannot_change_params(
    client: TestClient, db_session: Session
) -> None:
    username = _unique("lab_im")
    password = "lab-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, csrf = _login(client, username, password)
    headers = {"X-CSRF-Token": csrf}

    doc = client.post(
        "/api/v1/strategies",
        cookies=cookies,
        headers=headers,
        json={"strategy_key": _unique("bh_key"), "name": "Buy Hold"},
    )
    document_id = doc.json()["id"]
    ver = client.post(
        f"/api/v1/strategies/{document_id}/versions",
        cookies=cookies,
        headers=headers,
        json={
            "version_label": "v1",
            "strategy_class": "buy_and_hold",
            "parameters": {},
        },
    )
    version_id = ver.json()["id"]
    client.post(
        f"/api/v1/strategies/versions/{version_id}/submit",
        cookies=cookies,
        headers=headers,
    )

    denied = client.patch(
        f"/api/v1/strategies/versions/{version_id}/parameters",
        cookies=cookies,
        headers=headers,
        json={"parameters": {"fast": 3}},
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["detail"]["code"] == "version_immutable"


def test_deterministic_backtest_same_seed_hash() -> None:
    bars = bars_from_dicts(_synthetic_research_bars(120))
    assumptions = ExecutionAssumptions(commission_bps=1.0, fee_bps=1.0)
    a = run_bar_backtest(bars, "sma_crossover", {"fast": 5, "slow": 20}, assumptions, 42)
    b = run_bar_backtest(bars, "sma_crossover", {"fast": 5, "slow": 20}, assumptions, 42)
    assert a.metrics == b.metrics
    assert a.equity_curve == b.equity_curve
    assert a.trades == b.trades
    ha = hash_result(
        {"metrics": a.metrics, "equity_curve": a.equity_curve, "trades": a.trades}
    )
    hb = hash_result(
        {"metrics": b.metrics, "equity_curve": b.equity_curve, "trades": b.trades}
    )
    assert ha == hb


def test_walk_forward_separates_is_oos() -> None:
    bars = bars_from_dicts(_synthetic_research_bars(120))
    assumptions = ExecutionAssumptions()
    result = run_walk_forward(
        bars,
        "buy_and_hold",
        {},
        assumptions,
        seed=7,
        train_frac=0.6,
        val_frac=0.2,
        test_frac=0.2,
    )
    assert "in_sample_metrics" in result
    assert "out_of_sample_metrics" in result
    assert result["diagnostics"]["in_sample_reported_as_oos"] is False
    # Primary metrics must equal OOS, not IS
    assert result["metrics"] == result["out_of_sample_metrics"]
    split = result["diagnostics"]["split"]
    assert split["is_bar_count"] + split["oos_bar_count"] == 120
    assert split["oos_bar_count"] > 0


def test_optimization_rejects_unbounded_budget() -> None:
    bars = bars_from_dicts(_synthetic_research_bars(60))
    assumptions = ExecutionAssumptions()
    with pytest.raises(StrategyEngineError) as exc:
        run_optimization(
            bars,
            "sma_crossover",
            assumptions,
            param_grid={"fast": [3, 5, 8], "slow": [20, 30, 40, 50]},
            max_trials=5,
        )
    assert exc.value.code == "unbounded_budget"

    with pytest.raises(StrategyEngineError) as exc2:
        run_optimization(
            bars,
            "sma_crossover",
            assumptions,
            param_grid={"fast": [5], "slow": [20]},
            max_trials=0,
        )
    assert exc2.value.code == "unbounded_budget"


def test_monte_carlo_reproducible() -> None:
    equity = [100.0]
    for i in range(1, 50):
        equity.append(equity[-1] * (1.0 + 0.01 * ((i % 7) - 3) / 10.0))
    a = run_monte_carlo(equity, n_sims=50, seed=123)
    b = run_monte_carlo(equity, n_sims=50, seed=123)
    assert a["metrics"] == b["metrics"]
    assert (
        a["diagnostics"]["confidence_intervals"]
        == b["diagnostics"]["confidence_intervals"]
    )
    c = run_monte_carlo(equity, n_sims=50, seed=999)
    assert (
        a["metrics"]["ci_50"] != c["metrics"]["ci_50"]
        or a["metrics"]["ci_5"] != c["metrics"]["ci_5"]
    )


def test_no_path_to_live_execution() -> None:
    assert set(STRATEGY_REGISTRY.keys()) == {"buy_and_hold", "sma_crossover"}
    with pytest.raises(StrategyEngineError) as exc:
        run_bar_backtest(
            bars_from_dicts(_synthetic_research_bars(10)),
            "live_broker_execution",
            {},
            ExecutionAssumptions(),
            1,
        )
    assert exc.value.code == "unknown_strategy_class"
    # Registry must not expose broker / live hooks
    for name in STRATEGY_REGISTRY:
        assert "live" not in name
        assert "broker" not in name
        assert "order" not in name


def test_research_run_via_api(client: TestClient, db_session: Session) -> None:
    username = _unique("lab_run")
    password = "lab-pass-1234"
    _bootstrap_founder(db_session, username, password)
    cookies, csrf = _login(client, username, password)
    headers = {"X-CSRF-Token": csrf}

    doc = client.post(
        "/api/v1/strategies",
        cookies=cookies,
        headers=headers,
        json={"strategy_key": _unique("run_key"), "name": "Run Fixture"},
    )
    document_id = doc.json()["id"]
    ver = client.post(
        f"/api/v1/strategies/{document_id}/versions",
        cookies=cookies,
        headers=headers,
        json={
            "version_label": "v1",
            "strategy_class": "buy_and_hold",
            "parameters": {},
        },
    )
    version_id = ver.json()["id"]

    bars = _synthetic_research_bars(120)
    ds = client.post(
        "/api/v1/strategies/datasets",
        cookies=cookies,
        headers=headers,
        json={
            "dataset_key": _unique("ds"),
            "name": "Synthetic research fixture",
            "provenance": "Generated in-test synthetic OHLCV for Strategy Laboratory research only",
            "source_kind": "synthetic",
            "bars": bars,
            "metadata_json": {"label": "synthetic research fixture"},
        },
    )
    assert ds.status_code == 201, ds.text
    dataset_id = ds.json()["id"]
    assert ds.json()["bar_count"] == 120
    assert ds.json()["content_hash"]

    run = client.post(
        "/api/v1/strategies/runs",
        cookies=cookies,
        headers=headers,
        json={
            "kind": "backtest",
            "strategy_version_id": version_id,
            "dataset_id": dataset_id,
            "random_seed": 42,
            "execute": True,
        },
    )
    assert run.status_code == 201, run.text
    assert run.json()["status"] == "succeeded"
    run_id = run.json()["id"]

    result = client.get(
        f"/api/v1/strategies/runs/{run_id}/results",
        cookies=cookies,
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["is_immutable"] is True
    assert "total_return" in body["metrics"]
    assert body["result_hash"]


def test_service_rejects_unknown_strategy_class(db_session: Session) -> None:
    user = _bootstrap_founder(db_session, _unique("lab_svc"), "lab-pass-1234")
    svc = StrategyLaboratoryService(db_session)
    doc = svc.create_document(
        strategy_key=_unique("bad"),
        name="Bad",
        owner_user_id=user.id,
    )
    with pytest.raises(StrategyLabError) as exc:
        svc.create_version(
            document_id=doc.id,
            version_label="v1",
            strategy_class="margin_futures_live",
            parameters={},
            created_by_user_id=user.id,
        )
    assert exc.value.code == "unknown_strategy_class"
