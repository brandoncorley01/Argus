# Erroneous order response

Applies to orders submitted through the Execution Gateway. In Phase 13, **no live order can exist** — `assert_live_allowed` refuses every `LIVE`-environment order before any transport call, and no adapter's `submit_order` can succeed for a real venue. This runbook therefore applies to paper-environment erroneous orders (Phase 12 scope) and to confirming a suspected "erroneous live order" is impossible.

## If a "live order" is suspected

1. `GET /api/v1/micro-live/status` — confirm `live_execution_active: false` and `activation_state` is not `MICRO_LIVE_ACTIVE` (it cannot be, by construction in this phase).
2. Search the audit log for `live_execution_forbidden` events correlated with the suspected order's `idempotency_key` — a refusal record, not a fill, is the expected artifact.
3. If any adapter shows evidence of a network call having occurred, treat as a Critical defect (violates ADR-029) — escalate immediately, do not attempt local mitigation first.

## If a paper order is erroneous

1. Identify the order via `GET /api/v1/paper/portfolios/{id}/orders`.
2. Apply the portfolio kill switch if the erroneous order could recur: `POST /api/v1/paper/portfolios/{id}` kill-switch controls (Phase 12 API).
3. Reconcile the affected portfolio's cash/positions against fills and order events — do not manually edit balances.
4. Open an incident (`POST /api/v1/incidents`) documenting the order id, root cause, and corrective action.

## Dry-run misfires

`POST /api/v1/micro-live/dry-run/validate-order` never submits an order under any input. If a dry-run result is unexpected, treat it as a policy/validation logic question (`micro_capital_service.py`), not an execution incident.
