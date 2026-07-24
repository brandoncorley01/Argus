# Treasury and Executive Analytics (Phase 14)

## Purpose

Institutional capital-governance and executive-reporting architecture, implemented entirely on internal, simulated ledgers. **No real money is held, allocated, transferred, or transferable.** No brokerage account, bank account, payment rail, SSN, paid API, or real credentials are required to implement, test, or certify Phase 14.

See ADR-030 for the full rationale, including why external transfer execution is structurally unreachable (not just permission-gated).

## Capital lifecycle stages

Every capital movement passes through explicit, separately-authorized stages. No stage is skippable in code:

1. **Analysis** — `AttributionService`, `ExecutiveAnalyticsService` (read-only, evidence-backed, never invented).
2. **Recommendation** — `ForecastingService` deterministic scenario projections from caller-supplied inputs only.
3. **Approval** — `CapitalAllocation.status`: `requested → approved | rejected` (Founder only).
4. **Reservation** — `CapitalReservation`, created only from an `approved` allocation; allocation moves to `active`.
5. **Internal ledger** — `TreasuryLedgerEntry` (append-only) records every balance-affecting operation (fund, reserve, release).
6. **External transfer instruction** — `ExternalTransferInstruction`: `draft → proposed | cancelled`.
7. **Execution** — always forbidden. `TreasuryService.attempt_execute_transfer(...)` always raises; the API always returns `403` with code `external_transfer_execution_forbidden`.
8. **Reconciliation** — nothing is ever executed externally, so external reconciliation is out of scope; internal ledger entries remain reconcilable against account/pool balances at all times.

## Data model

| Table | Purpose |
| --- | --- |
| `treasury_accounts` | Simulated capital accounts. `is_simulated=true` is DB-enforced (`CHECK` constraint) — no row can represent real capital. |
| `capital_pools` | Named sub-ledgers within an account. |
| `capital_allocations` | Requests to allocate pool capital to a strategy/portfolio/provider target; Founder approve/reject workflow. |
| `capital_reservations` | Reservation of an approved allocation's capital; released independently. |
| `treasury_ledger_entries` | Append-only internal movements. Never represents an external transfer. |
| `external_transfer_instructions` | Draft/proposed/cancelled only — the `executed` state does not exist in the enum. Every execution attempt is recorded (`blocked_reason`, `execution_attempted_at`, `execution_attempt_count`). |
| `performance_attribution_snapshots` | Attribution by scope (`strategy\|portfolio\|instrument\|provider\|fee\|slippage`), labeled by `environment_class`. |
| `executive_kpi_snapshots` | Evidence-backed KPIs (`evidence_refs` cites source rows); `is_estimated` flag when a KPI is a deterministic projection rather than an observed count. |
| `institutional_reports` | Immutable, versioned, content-hashed reports with a fixed `environment_disclaimer`. |
| `forecast_scenarios` | Deterministic scenario projections (`cash_flow\|capital_requirement\|drawdown\|provider_outage\|strategy_suspension`) — never a market prediction. |

Seed data: one simulated treasury account ("Paper Institutional Capital", classification `simulated`) with one linked capital pool ("General Reserve"). No real-capital row is ever seeded.

## Environment labeling and paper/live separation

- `PerformanceAttributionSnapshot.environment_class` and `ExecutiveKpiSnapshot.environment_class` are mandatory (`paper | sandbox | testnet | live | simulated`).
- `AttributionService` builds real attribution from Phase 12 paper-trading tables (`paper_portfolios`, `paper_orders`, `paper_fills`) labeled `paper`. A request for `live` scope always returns `is_available=false` with an explicit `unavailable_reason` (there is no live trading per ADR-029) — it never fabricates a number or silently defaults to zero disguised as a real observation.
- `ExecutiveAnalyticsService` KPIs are derived from real rows (paper portfolios, incidents, strategy documents, treasury accounts, institutional health) with `evidence_refs` citing the source table and matched ids. No P&L figure is invented.
- `TreasuryReportingService` embeds a fixed disclaimer in every report stating that all balances are simulated/paper and are never combined with live performance, and separately reports `external_transfer_executed_count: 0` and full allocation/transfer status breakdowns.
- The executive summary endpoint (`GET /api/v1/treasury/summary`) always sets `live_available=false` with `live_unavailable_reason` explaining why, alongside the latest paper attribution and KPIs.

## Services

| Service | Responsibility |
| --- | --- |
| `treasury_service.py` | Accounts, pools, allocations (request/approve/reject Founder), reservations/release, internal ledger, external transfer create/propose/cancel, and the always-forbidden `attempt_execute_transfer`. |
| `attribution_service.py` | Builds attribution snapshots from paper data; labels environment; returns explicit unavailability for live. |
| `executive_analytics_service.py` | Generates/lists evidence-backed executive KPI snapshots. |
| `forecasting_service.py` | Deterministic scenario projections from caller-supplied inputs; no market predictions. |
| `treasury_reporting_service.py` | Generates versioned, immutable, hashed institutional reports with environment disclaimer. |

## API surface

`/api/v1/treasury/*` (`app/api/v1/treasury.py`):

- `accounts`, `pools` — CRUD/list (Founder for mutations, any authenticated role for reads).
- `allocations` — request/approve/reject/reserve/release (Founder).
- `reservations`, `ledger` — read-only.
- `external-transfers` — create/propose/cancel (Founder); `POST .../execute` always `403 external_transfer_execution_forbidden`.
- `attribution/generate`, `attribution` (list) — Founder or Operator to generate, any authenticated role to read.
- `kpis/generate`, `kpis` (list) — Founder or Operator to generate, any authenticated role to read.
- `forecasts` (create/list) — Founder or Operator to create, any authenticated role to read.
- `reports/generate`, `reports` (list/get) — Founder or Operator to generate, any authenticated role to read.
- `GET /summary` — executive dashboard payload (any authenticated role).

## EOC

`apps/eoc/src/app/(app)/treasury/page.tsx` — accounts, pools, allocations (with Founder approve/reject/reserve/release controls), external transfer instructions (with an "attempt execute" control that demonstrates the always-forbidden boundary), attribution snapshots, executive KPIs, forecast scenarios, and institutional reports. A SIMULATED/PAPER disclaimer banner is always rendered from the backend `summary.disclaimer`, and every table renders an explicit empty state rather than inventing rows.

## Non-goals (explicitly out of scope for Phase 14)

- No real deposit, withdrawal, or external transfer is ever executed.
- No leverage, margin, futures, short selling.
- No brokerage/bank integration, payment rail, SSN, or paid API.
- No claim that live trading performance exists or is combined with paper performance.
