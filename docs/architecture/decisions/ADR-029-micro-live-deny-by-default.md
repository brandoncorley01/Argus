# ADR-029: Micro-Live Institution deny-by-default architecture

- Status: Accepted
- Date: 2026-07-20
- Deciders: Founder

## Context

Phase 13 introduces the *architecture* for eventual micro-scale live execution (small real orders against real venues) without ever enabling it. The Founder requires that the platform can demonstrate an institutionally complete live-execution control plane — activation state machine, credential referencing, kill switches, capital limits, reconciliation, adapter scaffolds — while guaranteeing that **no real order can be submitted** and **no credential value is ever stored, logged, or returned** during this phase.

Two independent authorization layers already exist or are needed:

1. The global `OperatingMode` state machine (Phase 7), which gates institutional posture (`OFF`, `OBSERVE`, `PAPER`, `MICRO_LIVE`, `NORMAL_LIVE`, `SAFE_MODE`, `EMERGENCY_STOP`). `RISK_INCREASING_MODES` (`MICRO_LIVE`, `NORMAL_LIVE`) already require Founder authority and remain **blocked at this global layer in Phase 13** — no code change relaxes this.
2. A new, independent `live_activation_state` machine (this ADR), scoped specifically to the micro-live execution subsystem, which tracks incremental readiness (adapter configured → credentials referenced → connection verified → observe-only → sandbox/testnet → shadow → armed → active) but has **no reachable code path to `MICRO_LIVE_ACTIVE`** in this phase.

Both layers must independently authorize live execution before any live order could ever be submitted; Phase 13 intentionally leaves the second layer's terminal state unreachable and the first layer's global entry blocked, so the composite system is deny-by-default at every layer.

## Decision

- Add `live_activation_state` (singleton) with 13 states: `DISABLED`, `PAPER_ONLY` (initial/default), `ADAPTER_CONFIGURED`, `CREDENTIAL_REFERENCE_CONFIGURED`, `CONNECTION_VERIFIED`, `OBSERVE_ONLY`, `SANDBOX_OR_TESTNET`, `SHADOW_MODE`, `MICRO_LIVE_ARMED`, `MICRO_LIVE_ACTIVE`, `SUSPENDED`, `EMERGENCY_STOP`, `RECOVERY`. Transitions are append-only audited (`live_activation_transitions`).
- The transition matrix in `LiveActivationService` structurally omits any edge into `MICRO_LIVE_ACTIVE`. This is not a runtime permission check that could be misconfigured — the state is unreachable in code. Reaching it requires a future, explicitly reviewed Phase.
- Transitions at or beyond `MICRO_LIVE_ARMED` (and any state past `CREDENTIAL_REFERENCE_CONFIGURED`) require Founder role and require at least one present credential reference; absent credentials, the system is refused past `CREDENTIAL_REFERENCE_CONFIGURED` and remains fully operational in `PAPER_ONLY`.
- Credentials are never stored as values. `credential_references` stores only `(provider_key, ref_name, purpose, is_present_cached, last_validated_at)`. `SecretsProvider.get_reference_status()` returns a boolean presence flag only, sourced from `os.environ` at validation time; the API layer, schemas, and audit log never carry a secret value.
- `kill_switches` provide a flexible, always-checkable circuit breaker (global/provider/account/portfolio/strategy/instrument scope) that can force-block execution paths independent of activation state.
- `micro_capital_policies` provide versioned, conservative pretrade limits (max deployable capital, max order notional, max daily loss, max concurrent/provider/strategy exposure) used by dry-run validation and, in a future phase, by real pretrade checks.
- `reconciliation_runs`/`reconciliation_discrepancies` support fixture-based comparison of authoritative (paper) state vs. a comparison state, to exercise discrepancy-detection logic without any live account.
- `ExecutionGateway.assert_live_allowed(...)` is a new deny-by-default gate: it raises `live_execution_forbidden` (`LiveExecutionForbiddenError`) unless the environment is not `LIVE`, and even the notional in-code path requires activation `MICRO_LIVE_ACTIVE` (unreachable), credentials present, no active kill switch, and policy allowance — all four of which cannot simultaneously hold, and no order-sending code exists on the live path regardless.
- Optional adapters (`coinbase.py`, `kraken.py`, `ibkr.py`) extend `LiveAdapterBase`: `connect()` always reports disabled/credentials-unavailable, `submit_order()` always raises `LiveExecutionForbiddenError`, and no network call is made in default mode. They are registered but never selected as default.
- The global `OperatingMode` machine is untouched: `RISK_INCREASING_MODES` (`MICRO_LIVE`, `NORMAL_LIVE`) remain blocked for entry regardless of `live_activation_state`. Reaching the global `MICRO_LIVE` operating mode would additionally require both a future feature unlock **and** `live_activation_state == MICRO_LIVE_ACTIVE` — the latter has no reachable path in this phase, so the two gates are independent and multiplicative, not redundant.

## Consequences

- The platform can demonstrate a complete, auditable live-execution control-plane architecture (status dashboard, activation history, credential reference lifecycle, kill switches, capital policy, reconciliation, adapter registry, dry-run validation) with zero real financial exposure.
- No SSN, brokerage account, paid API, or real credentials are required to exercise or certify Phase 13.
- A future phase that wishes to actually reach `MICRO_LIVE_ACTIVE` must add an explicit, reviewed code path (new ADR), not merely flip a flag — this is intentional friction.
- Operators/Founders can still fully exercise paper trading (Phase 12) independent of any Phase 13 state; `PAPER_ONLY` is the default and requires no action.
