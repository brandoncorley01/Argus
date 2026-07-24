# Treasury recovery

## Checks

1. Migration head includes `a3b4c5d6e7f8`.
2. Seeded simulated account "Paper Institutional Capital" (`classification=simulated`, `is_simulated=true`) and its linked "General Reserve" capital pool exist (`GET /api/v1/treasury/accounts`, `GET /api/v1/treasury/pools`).
3. No `treasury_accounts` row ever has `is_simulated = false` — this is a database `CHECK` constraint (`ck_treasury_accounts_simulated_only`); if a migration or manual write attempted otherwise it would fail at the database, not silently succeed.
4. No `external_transfer_instructions` row ever reaches an `executed` status — the enum has no such member. If any external system depends on a "transfer completed" signal, it will never receive one from this subsystem; that is intentional (ADR-030).
5. Reconcile internal balances via `GET /api/v1/treasury/ledger` (append-only) against account/pool balances — do not invent or manually edit a balance outside of `TreasuryService`.
6. Institutional reports are immutable and content-hashed (`content_hash`); if a report's hash cannot be recomputed from its stored `content`, treat the report row as corrupted and regenerate rather than editing it in place.
7. Confirm `GET /api/v1/treasury/summary` always reports `external_transfer_executed_count: 0` and `live_available: false`.

## Boundaries

- Never add a code path, migration, or manual database write that sets an account's `is_simulated` to `false` or represents simulated capital as real.
- Never attempt to "fix" a stuck external transfer instruction by executing it — cancel and recreate the instruction instead. Execution is permanently forbidden by design (ADR-030), not a bug to route around.
- Never combine paper/simulated attribution or KPI figures with live figures in a report or dashboard — live is always `unavailable`, not zero.
- If `attempt_execute_transfer` ever returns anything other than a `TreasuryError("external_transfer_execution_forbidden")`, treat this as a critical regression and halt release — file an incident and do not proceed with certification until fixed and re-reviewed under a new ADR.
