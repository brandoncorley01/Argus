# ADR-030: Treasury simulated-ledger boundary

- Status: Accepted
- Date: 2026-07-20
- Deciders: Founder

## Context

Phase 14 introduces treasury management and executive analytics: capital accounts, pools, allocations, an internal ledger, external transfer *instructions*, performance attribution, executive KPIs, deterministic forecasting, and versioned institutional reports. The Founder requires that this phase demonstrate a complete, auditable capital-governance workflow — analysis, recommendation, approval, reservation, internal ledger movement, external transfer instruction, execution, reconciliation — as separate, explicit stages, while guaranteeing that **no real deposit, withdrawal, or external transfer can ever be executed**.

This mirrors the deny-by-default pattern established in ADR-029 (Micro-Live Institution): an institutionally complete architecture with a terminal state that is structurally unreachable in code, not merely gated by a runtime permission check.

## Decision

- `treasury_accounts.is_simulated` is a `NOT NULL BOOLEAN` with a database `CHECK (is_simulated = true)` constraint (`ck_treasury_accounts_simulated_only`). No row can ever represent real capital; this is enforced at the schema level, not only by application code.
- `TreasuryService` exposes `fund_account_simulated(...)` — the only funding path — which posts an internal ledger entry and updates account/pool balances. There is no code path that connects to a real payment rail, bank, or exchange.
- The capital lifecycle is modeled as explicit, separately-authorized stages:
  1. **Analysis** — `attribution_service.py` / `executive_analytics_service.py` (read-only, evidence-backed).
  2. **Recommendation** — `forecasting_service.py` deterministic scenario projections (no market predictions).
  3. **Approval** — `CapitalAllocation` status `requested → approved | rejected` (Founder only).
  4. **Reservation** — `CapitalReservation`, created only from an `approved` allocation (`reserve_allocation`), moving it to `active`.
  5. **Internal ledger** — `TreasuryLedgerEntry`, append-only, created by every balance-affecting operation (funding, reservation, release).
  6. **External transfer instruction** — `ExternalTransferInstruction`, created in `draft`, optionally `proposed`, or `cancelled`.
  7. **Execution** — `TreasuryService.attempt_execute_transfer(...)` **always raises** `TreasuryError("external_transfer_execution_forbidden")`. There is no branch, flag, or configuration that returns success. The API endpoint (`POST /api/v1/treasury/external-transfers/{id}/execute`) has no code path that can return anything other than `403 Forbidden`.
  8. **Reconciliation** — out of scope for external transfers (nothing is ever executed to reconcile); internal ledger entries remain reconcilable against account/pool balances at all times.
- `ExternalTransferStatus` the enum itself has no `executed` member — `draft`, `proposed`, `cancelled` only — plus a `blocked_reason`/`execution_attempted_at`/`execution_attempt_count` audit trail recorded on every forbidden attempt. This is a modeling choice, not just a status filter: the terminal "executed" state cannot be represented even if application logic were bypassed.
- `PerformanceAttributionSnapshot` and `ExecutiveKpiSnapshot` both carry a mandatory `environment_class` (`paper | sandbox | testnet | live | simulated`). `AttributionService` builds `paper`/`simulated` snapshots from real Phase 12 paper-trading data; any request for `live` attribution returns `is_available=false` with an explicit `unavailable_reason` — it never fabricates a value.
- `InstitutionalReport` is immutable (`is_immutable=true`, monotonically increasing `version` per `report_type`, content-hashed via the existing canonical payload hasher from ADR-010) and every generated report embeds a fixed `environment_disclaimer` stating that all balances are simulated/paper and are never combined with (non-existent) live performance.
- RBAC: allocation/reservation/account/pool mutations and all external-transfer actions require Founder; attribution/KPI/forecast/report generation require Founder or Operator; all reads require any authenticated role — consistent with existing Phase 12/13 precedent.

## Consequences

- The platform can demonstrate a complete, auditable treasury and executive-analytics workflow with zero real financial exposure and no external payment integration.
- No SSN, brokerage account, paid API, or real credentials are required to implement, test, or certify Phase 14.
- A future phase that wishes to actually execute an external transfer must add an explicit, reviewed code path (new ADR, new enum member, new service method) — this is intentional friction, identical in spirit to ADR-029's `MICRO_LIVE_ACTIVE` boundary.
- Executive KPIs, attribution, forecasts, and reports can never silently blend paper/simulated and live figures, because `environment_class` is mandatory and live data is structurally unavailable (there is no live trading, per ADR-029) rather than defaulted to zero or omitted.
- Phase 12 (paper trading) and Phase 13 (micro-live architecture) behavior is unmodified.
