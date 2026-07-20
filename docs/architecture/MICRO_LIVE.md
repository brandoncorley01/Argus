# Micro-Live Institution (Phase 13)

## Purpose

Architecture for eventual micro-scale live execution, implemented deny-by-default. **Live trading is not active in this phase.** No brokerage account, exchange account, SSN, paid API, or real credentials are required to implement, test, or certify Phase 13.

The **Internal Paper Execution Provider** (Phase 12) remains the default and only operational provider. Nothing in Phase 13 changes paper trading behavior.

## Two independent gates

Live execution requires **both** of the following to hold, and neither has a reachable path to "allow" in this phase:

1. **Global `OperatingMode`** (Phase 7) — `RISK_INCREASING_MODES` (`MICRO_LIVE`, `NORMAL_LIVE`) remain blocked for entry. Unchanged by Phase 13.
2. **`live_activation_state`** (Phase 13, this document) — an independent, narrower state machine scoped to the micro-live execution subsystem. Default: `PAPER_ONLY`. **No code path reaches `MICRO_LIVE_ACTIVE`.**

See ADR-029 for the full rationale.

## `live_activation_state` machine

States: `DISABLED`, `PAPER_ONLY` (default), `ADAPTER_CONFIGURED`, `CREDENTIAL_REFERENCE_CONFIGURED`, `CONNECTION_VERIFIED`, `OBSERVE_ONLY`, `SANDBOX_OR_TESTNET`, `SHADOW_MODE`, `MICRO_LIVE_ARMED`, `MICRO_LIVE_ACTIVE` (unreachable), `SUSPENDED`, `EMERGENCY_STOP`, `RECOVERY`.

- Singleton row (`live_activation_state`) with `state_version` for optimistic concurrency, plus append-only `live_activation_transitions` history.
- Transitions at/after `CREDENTIAL_REFERENCE_CONFIGURED` require at least one present credential reference. Transitions at/after `MICRO_LIVE_ARMED` require Founder role.
- Absence of credentials keeps the system in `PAPER_ONLY`, which is fully operational for paper trading.

## Credential referencing (never values)

- `credential_references`: `(provider_key, ref_name, purpose, is_present_cached, last_validated_at)`. The `ref_name` is an **environment variable name** — e.g. `COINBASE_API_KEY_REF` — not a secret.
- `SecretsProvider.get_reference_status(ref_name)` (`app/secrets/`) checks `os.environ` for a non-empty value and returns a boolean only. No API endpoint, schema, log line, or audit payload in this system can carry a credential value.
- Audit entries for credential checks record the reference name only (redacted payload).

## Kill switches

`kill_switches` support scopes `global | provider | account | portfolio | strategy | instrument`. Any active switch blocks the relevant execution path and is checked independent of activation state. A global switch row is seeded inactive.

## Micro-capital policy

`micro_capital_policies` is versioned (immutable history, one active version): `max_deployable_capital`, `max_order_notional`, `max_daily_loss`, `max_concurrent_exposure`, `max_provider_exposure`, `max_strategy_exposure`. A conservative default policy is seeded. Used today only by dry-run validation (`POST /api/v1/micro-live/dry-run/validate-order`); no real or paper order is submitted by this endpoint.

## Reconciliation

`reconciliation_runs` / `reconciliation_discrepancies` compare a fixture "authoritative" (paper) state against a fixture "comparison" state and record discrepancies (cash, position quantity mismatches). Fully fixture-driven — no provider network call.

## Execution Gateway

`ExecutionGateway.assert_live_allowed(...)` (`app/execution/gateway.py`) always raises `live_execution_forbidden` for `LIVE` environment orders. The paper path (Phase 12) is unchanged and remains default. No live provider adapter can be routed to for a real submit.

## Adapter framework

`app/execution/adapters/`:
- `base.py` — `LiveAdapterBase`, `AdapterDescriptor`. All adapters extend this; every live-facing method is stubbed to report disabled or raise `LiveExecutionForbiddenError`.
- `mock_transport.py` — deterministic fixtures for contract tests, no network.
- `coinbase.py`, `kraken.py`, `ibkr.py` — scaffolds. `connect()` reports `disabled`/`credentials_unavailable`. `submit_order()` always raises. Registered in `ExecutionProviderRegistry` as optional, non-default, `verification_status=contract_tested`, `supports_live=false`.

`VerificationStatus` progression: `implemented_unverified → contract_tested → sandbox_verified → testnet_verified → live_certified`. **No adapter is ever marked `live_certified` in this phase**, by design — that would require a future, separately reviewed phase with real sandbox/testnet evidence.

## API surface

`/api/v1/micro-live/*` (see `app/api/v1/micro_live.py`): status, activation (read/transition/history), credential references (create/list/validate-presence), kill switches (list/set), capital policy (get/put), reconciliation (create/list/discrepancies), adapters (list), dry-run order validation. RBAC: mutations that arm/activate/change kill switches/credentials/policy require Founder; reconciliation runs require Founder or Operator; reads require any authenticated role.

## EOC

`apps/eoc/src/app/(app)/micro-live/page.tsx` — status dashboard, activation controls (Founder-only), kill switches, credential references (names only), adapters, capital policy, dry-run validator, reconciliation runs. No secret value is ever rendered.

## Status dashboard contract

`GET /api/v1/micro-live/status` always reflects, by default and in tests: `live_capable_architecture=true`, `credentials_configured=false`, `live_execution_active=false`, `paper_provider_default=true`, `activation_state=PAPER_ONLY`.

## Non-goals (explicitly out of scope for Phase 13)

- No live order is ever submitted.
- No short selling, leverage, margin, futures, or withdrawal functionality.
- No claim that live trading is active or operational.
- No live-certified adapter.
