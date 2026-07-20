# Provider outage response

Applies to Phase 13 optional adapters (`coinbase_adapter`, `kraken_adapter`, `ibkr_adapter`) and the Phase 12 internal paper/deterministic-test providers.

## Micro-live adapters (Coinbase / Kraken / IBKR)

These adapters never make network calls in default mode and never submit live orders in any mode. "Outage" for these adapters means `connect()`/`health()` correctly continue to report `disabled` / `credentials_unavailable` — this is the expected steady state, not a fault.

1. `GET /api/v1/micro-live/adapters` — confirm the affected adapter shows `is_enabled: false`, `supports_live: false`.
2. No customer/strategy impact is possible: nothing routes through these adapters for real execution.
3. If health reporting itself is misbehaving (e.g. raising instead of returning a disabled health record), treat as a code defect, not a provider outage — file against `app/execution/adapters/`.

## Paper / deterministic-test provider (Phase 12) outage

1. Check `GET /api/v1/paper/providers` for provider health.
2. If `internal_paper` is unhealthy, this affects paper trading (Phase 12 scope) and should follow `docs/operations/PAPER_TRADING_RECOVERY.md`.
3. Do not enable a live provider to "work around" a paper outage — paper remains authoritative for development.

## Verification

- `GET /api/v1/micro-live/status` — `paper_provider_default: true` regardless of adapter health.
- Audit log shows no order-submission attempts against disabled adapters (they would raise `live_execution_forbidden` before any transport call).
