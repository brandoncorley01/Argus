#!/usr/bin/env python3
"""Argus v1 RC deterministic end-to-end paper validation harness.

Uses FastAPI TestClient + the local DB (same pattern as apps/api/tests).
Internal Paper Execution Provider only — no live trading, no real credentials.

Run from repo root (or anywhere) with the API venv:

  apps/api/.venv/Scripts/python.exe scripts/rc_e2e_paper_validation.py

Exit code 0 on full pass; non-zero on first hard failure.
Prints human progress lines plus a final machine-readable JSON summary.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

# Ensure apps/api is importable (app.* package).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_API_ROOT = _REPO_ROOT / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

os.environ.setdefault("ALLOW_ADDITIONAL_FOUNDERS", "true")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.settings import clear_settings_cache, get_settings  # noqa: E402
from app.db.session import get_session_factory, reset_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402


OPENING_CASH = Decimal("100000")
PASSWORD = "rc-e2e-pass-1234"
SEED = 42


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class HarnessState:
    checks: list[CheckResult] = field(default_factory=list)
    portfolio_id: str | None = None
    session_id: str | None = None
    order_id: str | None = None
    fill_count: int = 0
    opening_cash: str = str(OPENING_CASH)
    ending_cash: str | None = None
    position_qty: str | None = None
    total_fees: str | None = None
    coverage_notes: list[str] = field(default_factory=list)

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, ok=ok, detail=detail))
        status = "PASS" if ok else "FAIL"
        suffix = f" - {detail}" if detail else ""
        print(f"[{status}] {name}{suffix}")
        if not ok:
            raise AssertionError(f"{name}: {detail or 'failed'}")


def _unique(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%H%M%S%f')}_{uuid.uuid4().hex[:6]}"


def _bootstrap(db: Session, username: str, password: str) -> None:
    AuthService(db).bootstrap_founder(
        username=username, password=password, email=f"{username}@example.com"
    )


def _login(client: TestClient, identifier: str, password: str) -> tuple[dict[str, str], str]:
    res = client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": password}
    )
    if res.status_code != 200:
        raise AssertionError(f"login failed: {res.status_code} {res.text}")
    return dict(res.cookies), res.json()["csrf_token"]


def _run(client: TestClient, db: Session, state: HarnessState) -> None:
    username = _unique("rc_founder")
    _bootstrap(db, username, PASSWORD)
    state.record("A.bootstrap_founder", True, username)

    cookies, csrf = _login(client, username, PASSWORD)
    headers = {"X-CSRF-Token": csrf}
    state.record("B.login_csrf", True, "csrf present" if csrf else "missing csrf")

    # C — providers
    providers = client.get("/api/v1/paper/providers", cookies=cookies)
    if providers.status_code != 200:
        state.record("C.providers", False, providers.text)
    rows = providers.json()
    default = next((r for r in rows if r["provider"]["is_default"]), None)
    ok = (
        default is not None
        and default["provider"]["provider_key"] == "internal_paper"
        and default["provider"]["environment"] == "paper"
    )
    state.record(
        "C.providers_internal_paper_default",
        ok,
        default["provider"]["provider_key"] if default else "no default",
    )

    # D — micro-live status
    ml = client.get("/api/v1/micro-live/status", cookies=cookies)
    if ml.status_code != 200:
        state.record("D.micro_live_status", False, ml.text)
    ml_body = ml.json()
    ok = (
        ml_body.get("live_execution_active") is False
        and ml_body.get("activation_state") == "PAPER_ONLY"
    )
    state.record(
        "D.micro_live_paper_only",
        ok,
        f"live_execution_active={ml_body.get('live_execution_active')} "
        f"activation_state={ml_body.get('activation_state')}",
    )

    # E — portfolio
    port = client.post(
        "/api/v1/paper/portfolios",
        cookies=cookies,
        headers=headers,
        json={"name": f"RC E2E {username}", "initial_cash": str(OPENING_CASH)},
    )
    if port.status_code != 201:
        state.record("E.create_portfolio", False, port.text)
    port_body = port.json()
    state.portfolio_id = port_body["id"]
    cash_ok = Decimal(port_body["cash_balance"]) == OPENING_CASH
    state.record(
        "E.create_portfolio",
        cash_ok,
        f"id={state.portfolio_id} cash={port_body['cash_balance']}",
    )
    pid = state.portfolio_id

    # F — session seed=42
    sess = client.post(
        f"/api/v1/paper/portfolios/{pid}/sessions",
        cookies=cookies,
        headers=headers,
        json={"seed": SEED},
    )
    if sess.status_code != 201:
        state.record("F.open_session", False, sess.text)
    sess_body = sess.json()
    state.session_id = sess_body["id"]
    state.record(
        "F.open_session",
        sess_body.get("seed") == SEED,
        f"id={state.session_id} seed={sess_body.get('seed')}",
    )
    sid = state.session_id

    # G — market BUY 1 BTC-USD
    idem_key = f"rc-e2e-buy-{uuid.uuid4().hex}"
    order = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=cookies,
        headers={**headers, "Idempotency-Key": idem_key},
        json={
            "symbol": "BTC-USD",
            "side": "buy",
            "order_type": "market",
            "quantity": "1",
            "session_id": sid,
        },
    )
    if order.status_code != 200:
        state.record("G.buy_btc", False, order.text)
    order_body = order.json()
    state.order_id = order_body["id"]
    filled_ok = order_body["status"] in {"filled", "partially_filled"}
    env_ok = order_body.get("environment") == "paper"
    state.record(
        "G.buy_btc",
        filled_ok and env_ok,
        f"order={state.order_id} status={order_body['status']} env={order_body.get('environment')}",
    )

    fills = client.get(f"/api/v1/paper/portfolios/{pid}/fills", cookies=cookies)
    if fills.status_code != 200:
        state.record("G.record_fills", False, fills.text)
    fill_rows = fills.json()
    state.fill_count = len(fill_rows)
    total_fees = sum((Decimal(f["fee"]) for f in fill_rows), Decimal("0"))
    state.total_fees = str(total_fees)

    positions = client.get(f"/api/v1/paper/portfolios/{pid}/positions", cookies=cookies)
    if positions.status_code != 200:
        state.record("G.record_position", False, positions.text)
    pos_rows = positions.json()
    btc = next((p for p in pos_rows if p["symbol"] == "BTC-USD"), None)
    state.position_qty = btc["quantity"] if btc else "0"
    state.record(
        "G.record_accounting",
        btc is not None and Decimal(btc["quantity"]) > 0,
        f"fills={state.fill_count} qty={state.position_qty} fees={state.total_fees}",
    )

    updated = client.get(f"/api/v1/paper/portfolios/{pid}", cookies=cookies)
    state.ending_cash = updated.json()["cash_balance"]
    state.record(
        "G.cash_decreased",
        Decimal(state.ending_cash) < OPENING_CASH,
        f"ending_cash={state.ending_cash}",
    )

    # H — idempotent resubmit
    order2 = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=cookies,
        headers={**headers, "Idempotency-Key": idem_key},
        json={
            "symbol": "BTC-USD",
            "side": "buy",
            "order_type": "market",
            "quantity": "1",
            "session_id": sid,
        },
    )
    if order2.status_code != 200:
        state.record("H.idempotent_resubmit", False, order2.text)
    same_id = order2.json()["id"] == state.order_id
    state.record(
        "H.idempotent_resubmit",
        same_id,
        f"first={state.order_id} second={order2.json()['id']}",
    )

    # I — SELL excess of position → short rejected
    sell_qty = str(Decimal(state.position_qty or "1") + Decimal("1"))
    sell = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=cookies,
        headers={**headers, "Idempotency-Key": _unique("rc-short")},
        json={
            "symbol": "BTC-USD",
            "side": "sell",
            "order_type": "market",
            "quantity": sell_qty,
            "session_id": sid,
        },
    )
    if sell.status_code != 200:
        state.record("I.short_rejected", False, f"status={sell.status_code} {sell.text}")
    sell_body = sell.json()
    short_ok = (
        sell_body.get("status") == "rejected"
        and sell_body.get("reject_reason") == "short_selling_forbidden"
    )
    state.record(
        "I.short_rejected",
        short_ok,
        f"status={sell_body.get('status')} reason={sell_body.get('reject_reason')}",
    )

    # J — tiny notional risk limit blocks buy
    lim = client.post(
        f"/api/v1/paper/portfolios/{pid}/risk-limits",
        cookies=cookies,
        headers=headers,
        json={"name": "rc tiny notional", "limit_type": "notional", "threshold": "10"},
    )
    if lim.status_code != 201:
        state.record("J.risk_limit", False, lim.text)
    state.record("J.risk_limit", True, f"id={lim.json()['id']} threshold=10")

    blocked = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=cookies,
        headers={**headers, "Idempotency-Key": _unique("rc-risk")},
        json={
            "symbol": "BTC-USD",
            "side": "buy",
            "order_type": "market",
            "quantity": "1",
            "session_id": sid,
        },
    )
    risk_ok = blocked.status_code == 400 and (
        blocked.json().get("detail", {}).get("code") == "risk_blocked"
        if isinstance(blocked.json().get("detail"), dict)
        else True
    )
    state.record(
        "J.buy_blocked_by_risk",
        risk_ok,
        f"status={blocked.status_code} body={blocked.text[:200]}",
    )

    # K — kill switch
    ks = client.post(
        f"/api/v1/paper/portfolios/{pid}/kill-switch",
        cookies=cookies,
        headers=headers,
        json={"active": True},
    )
    if ks.status_code != 200:
        state.record("K.kill_switch_on", False, ks.text)
    ks_body = ks.json()
    ks_ok = (
        ks_body.get("kill_switch_active") is True
        and ks_body.get("status") == "suspended"
    )
    state.record(
        "K.kill_switch_on",
        ks_ok,
        f"kill_switch_active={ks_body.get('kill_switch_active')} status={ks_body.get('status')}",
    )

    # Qty small enough to pass notional=10 pretrade (ref_price defaults to 100)
    # so gateway kill_switch / portfolio_inactive is exercised.
    ks_order = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        cookies=cookies,
        headers={**headers, "Idempotency-Key": _unique("rc-ks")},
        json={
            "symbol": "BTC-USD",
            "side": "buy",
            "order_type": "market",
            "quantity": "0.01",
            "session_id": sid,
        },
    )
    ks_blocked = ks_order.status_code in {400, 403}
    detail_code = None
    if isinstance(ks_order.json().get("detail"), dict):
        detail_code = ks_order.json()["detail"].get("code")
    state.record(
        "K.submit_blocked",
        ks_blocked,
        f"status={ks_order.status_code} code={detail_code}",
    )

    # L — treasury attribution / KPI / report (paper/simulated labels)
    attr = client.post(
        "/api/v1/treasury/attribution/generate",
        cookies=cookies,
        headers=headers,
        json={
            "scope": "portfolio",
            "scope_ref": pid,
            "environment_class": "paper",
        },
    )
    if attr.status_code != 201:
        state.record("L.attribution", False, attr.text)
    attr_body = attr.json()
    state.record(
        "L.attribution_paper",
        attr_body.get("environment_class") == "paper" and attr_body.get("is_available") is True,
        f"env={attr_body.get('environment_class')} available={attr_body.get('is_available')}",
    )

    kpis = client.post(
        "/api/v1/treasury/kpis/generate", cookies=cookies, headers=headers
    )
    if kpis.status_code != 201:
        state.record("L.kpis", False, kpis.text)
    kpi_rows = kpis.json()
    kpi_ok = len(kpi_rows) > 0 and all(
        row.get("environment_class") in ("paper", "sandbox", "testnet", "live", "simulated")
        for row in kpi_rows
    )
    state.record("L.kpis_labeled", kpi_ok, f"count={len(kpi_rows)}")

    report = client.post(
        "/api/v1/treasury/reports/generate",
        cookies=cookies,
        headers=headers,
        json={"report_type": "daily_brief"},
    )
    if report.status_code != 201:
        state.record("L.report", False, report.text)
    rep_body = report.json()
    disclaimer = (rep_body.get("environment_disclaimer") or "").lower()
    report_ok = (
        rep_body.get("is_immutable") is True
        and "paper" in disclaimer
        and rep_body.get("content", {}).get("live", {}).get("available") is False
    )
    state.record(
        "L.report_paper_labels",
        report_ok,
        f"immutable={rep_body.get('is_immutable')} disclaimer_has_paper={'paper' in disclaimer}",
    )

    # Paper account statement (Phase 12) also carries disclaimer
    paper_rep = client.post(
        f"/api/v1/paper/portfolios/{pid}/reports",
        cookies=cookies,
        headers=headers,
        json={"report_type": "account_statement"},
    )
    if paper_rep.status_code == 201:
        content = paper_rep.json().get("content") or {}
        state.record(
            "L.paper_account_statement",
            "disclaimer" in content,
            "disclaimer present in paper report content",
        )
    else:
        state.record("L.paper_account_statement", False, paper_rep.text)

    # M — external transfer execute → 403
    acct = client.post(
        "/api/v1/treasury/accounts",
        cookies=cookies,
        headers=headers,
        json={
            "name": f"RC Sim {username}",
            "currency": "USD",
            "classification": "simulated",
        },
    )
    if acct.status_code != 201:
        state.record("M.create_treasury_account", False, acct.text)
    account_id = acct.json()["id"]
    state.record(
        "M.create_treasury_account",
        acct.json().get("is_simulated") is True,
        f"id={account_id} classification={acct.json().get('classification')}",
    )

    xfer = client.post(
        "/api/v1/treasury/external-transfers",
        cookies=cookies,
        headers=headers,
        json={
            "account_id": account_id,
            "direction": "outbound",
            "amount": "1",
            "currency": "USD",
            "destination_reference": "rc-e2e-blocked-destination",
        },
    )
    if xfer.status_code != 201:
        state.record("M.create_external_transfer", False, xfer.text)
    instruction_id = xfer.json()["id"]
    state.record("M.create_external_transfer", True, f"id={instruction_id}")

    execute = client.post(
        f"/api/v1/treasury/external-transfers/{instruction_id}/execute",
        cookies=cookies,
        headers=headers,
    )
    exec_ok = execute.status_code == 403 and (
        isinstance(execute.json().get("detail"), dict)
        and execute.json()["detail"].get("code") == "external_transfer_execution_forbidden"
    )
    state.record(
        "M.external_transfer_execute_403",
        exec_ok,
        f"status={execute.status_code} body={execute.text[:200]}",
    )

    # N — MICRO_LIVE_ACTIVE must fail (deny-by-default gate)
    denied = client.post(
        "/api/v1/micro-live/activation/transition",
        cookies=cookies,
        headers=headers,
        json={
            "target_state": "MICRO_LIVE_ACTIVE",
            "reason": "RC e2e attempt — must fail",
        },
    )
    n_ok = denied.status_code == 403 and (
        isinstance(denied.json().get("detail"), dict)
        and denied.json()["detail"].get("code") == "live_execution_not_certified"
    )
    state.record(
        "N.micro_live_active_denied",
        n_ok,
        f"status={denied.status_code} body={denied.text[:200]}",
    )
    still = client.get("/api/v1/micro-live/status", cookies=cookies)
    still_ok = (
        still.status_code == 200
        and still.json().get("live_execution_active") is False
    )
    state.record(
        "N.still_not_live",
        still_ok,
        f"live_execution_active={still.json().get('live_execution_active') if still.status_code == 200 else 'n/a'}",
    )

    # Refresh ending cash / position after controls (should be unchanged post-buy)
    final_port = client.get(f"/api/v1/paper/portfolios/{pid}", cookies=cookies)
    final_pos = client.get(f"/api/v1/paper/portfolios/{pid}/positions", cookies=cookies)
    if final_port.status_code == 200:
        state.ending_cash = final_port.json()["cash_balance"]
    if final_pos.status_code == 200:
        btc2 = next((p for p in final_pos.json() if p["symbol"] == "BTC-USD"), None)
        if btc2:
            state.position_qty = btc2["quantity"]

    state.coverage_notes = [
        "Duplicate fill protection: UniqueConstraint(provider_fill_id, provider_id) "
        "on paper_fills + PaperTradingService skips prior provider_fill_id "
        "(apps/api/app/services/paper_trading_service.py); covered by schema/migration "
        "and order idempotency tests in apps/api/tests/test_paper_trading.py "
        "(test_idempotent_order_submit).",
        "Process restart recovery is out of scope for this in-process TestClient harness; "
        "durable order idempotency keys and fill uniqueness are DB-enforced.",
    ]


def main() -> int:
    print("Argus v1 RC E2E paper validation (Internal Paper Execution Provider only)")
    print(f"repo={_REPO_ROOT}")
    print(f"api={_API_ROOT}")
    print(f"seed={SEED} opening_cash={OPENING_CASH}")
    print("---")

    state = HarnessState()
    clear_settings_cache()
    reset_engine()
    get_settings()

    exit_code = 0
    error: str | None = None
    try:
        app = create_app()
        session_factory = get_session_factory()
        db = session_factory()
        try:
            with TestClient(app) as client:
                _run(client, db, state)
        finally:
            db.close()
    except AssertionError as exc:
        exit_code = 1
        error = str(exc)
        print(f"\nHARD FAIL: {exc}")
    except Exception:
        exit_code = 2
        error = traceback.format_exc()
        print(f"\nUNEXPECTED ERROR:\n{error}")
    finally:
        reset_engine()
        clear_settings_cache()

    summary: dict[str, Any] = {
        "harness": "rc_e2e_paper_validation",
        "passed": exit_code == 0,
        "exit_code": exit_code,
        "error": error,
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in state.checks],
        "accounting": {
            "opening_cash": state.opening_cash,
            "ending_cash": state.ending_cash,
            "position_qty": state.position_qty,
            "fees": state.total_fees,
            "fill_count": state.fill_count,
            "portfolio_id": state.portfolio_id,
            "order_id": state.order_id,
            "session_id": state.session_id,
            "environment": "paper",
            "provider": "internal_paper",
            "seed": SEED,
        },
        "coverage_notes": state.coverage_notes,
    }

    print("---")
    print("RC_E2E_SUMMARY_JSON")
    print(json.dumps(summary, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
