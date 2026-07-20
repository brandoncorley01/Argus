# Independent Engineering Review — Phase 14 Treasury and Executive Analytics

## Executive Summary
- Scope reviewed: `treasury_service.py` (accounts/pools/allocations/reservations/ledger/external transfers), `attribution_service.py`, `executive_analytics_service.py`, `forecasting_service.py`, `treasury_reporting_service.py`, `/api/v1/treasury`, EOC `/treasury`
- Overall Result: **PASS** (Critical=0, High=0)
- Recommended Merge: Yes, when Founder authorizes (branch `phase-14-treasury-executive-analytics`, after Phase 13)

## Findings
### Critical
None.

### High
None.

### Medium
- M14-1: `treasury_accounts` and `capital_pools` singleton seed rows ("Paper Institutional Capital" / "General Reserve") are created by migration data seed, mirroring the Phase 12/13 seed pattern — acceptable, consistent with existing precedent.
- M14-2: Forecast scenarios are purely deterministic functions of caller-supplied inputs (no historical calibration data source) — correct and intentional per ADR-030/AGENTS.md (no fabricated market claims), but means forecast quality is bounded by what the caller supplies; a future phase that wants calibrated forecasting needs its own ADR and review.
- M14-3: Phase 8–13 remain unmerged to `main`; stack risk is integration ordering, not Phase 14 correctness (same class of residual as M12-3/M13-3).

### Low
- L14-1: `AttributionSnapshot` for `environment_class in (sandbox, testnet)` is not populated from any live data source in this phase (there is none) — it degrades to `is_available=false` with an explicit reason, same as `live`; acceptable, not a defect.
- L14-2: `ExecutiveKpiSnapshot.is_estimated` is currently always `false` for the generated KPI set (all are direct counts/sums from evidence, not projections) — intentional; the field exists for future estimated KPIs and is exercised structurally, not yet by a non-`false` example.

### Informational
- `ExternalTransferStatus` has no `executed` member — verified by enum inspection (`test_external_transfer_status_enum_has_no_executed_state`) and by `test_external_transfer_execute_is_always_forbidden`, which asserts `POST .../execute` always returns `403` with code `external_transfer_execution_forbidden`.
- `treasury_accounts.is_simulated` carries a database `CHECK (is_simulated = true)` constraint (`ck_treasury_accounts_simulated_only`) — verified by migration inspection; no application code path is required to enforce this, the database refuses it independently.
- Attribution for `environment_class="live"` always returns `is_available=false` with an explicit `unavailable_reason` — verified by `test_attribution_live_environment_is_explicitly_unavailable` and by inspection of `AttributionService`.
- Institutional reports are immutable, versioned per `report_type`, and content-hashed using the existing canonical payload hasher (ADR-010) — verified by `test_report_is_immutable_and_hashed`.
- No SSN, brokerage account, paid API, bank account, or real credentials were used or required to implement or test this phase.
- Paper execution (Phase 12) and micro-live architecture (Phase 13) behavior are unmodified by this phase.

## Risk Matrix
| ID | Severity | Area | Blocks merge? |
| --- | --- | --- | --- |
| M14-1 | Medium | Singleton seed pattern | No |
| M14-2 | Medium | Forecast calibration scope | No |
| M14-3 | Medium | Release stack | No |

## Evidence
- Migration `a3b4c5d6e7f8` (down_revision `f2a3b4c5d6e7`) applied successfully; `alembic current` reports `a3b4c5d6e7f8 (head)`.
- `pytest tests/test_treasury.py`: 14 passed — `test_simulated_account_seeded`, `test_account_creatable_by_founder_and_always_simulated`, `test_viewer_cannot_create_account`, `test_allocation_request_and_founder_approve`, `test_viewer_cannot_approve_allocation`, `test_external_transfer_execute_is_always_forbidden`, `test_external_transfer_status_enum_has_no_executed_state`, `test_attribution_from_paper_data_labeled_paper`, `test_attribution_live_environment_is_explicitly_unavailable`, `test_kpi_snapshot_is_evidence_backed`, `test_viewer_cannot_generate_kpis`, `test_forecast_scenario_is_deterministic`, `test_report_is_immutable_and_hashed`, `test_summary_separates_paper_and_live`.
- Full API suite: 180 passed (0 failed).
- `ruff check` clean on all new/changed Phase 14 application and test surfaces (`app/models/treasury.py`, all five new services, `app/schemas/treasury.py`, `app/api/v1/treasury.py`, `app/main.py`, `app/models/__init__.py`, `tests/test_treasury.py`). The migration file (`alembic/versions/a3b4c5d6e7f8_...py`) has the same `E501` line-length style findings as prior migration files (e.g. `f2a3b4c5d6e7`) — pre-existing repository style precedent for generated-column migration bodies, not a Phase 14 regression.
- `mypy` clean on `app/models/treasury.py`, all five new services, and `app/schemas/treasury.py`/`app/api/v1/treasury.py`.
- EOC: `tsc --noEmit` and `next lint` both clean with the new `/treasury` route, `TreasuryForms.tsx`, `lib/actions/treasury.ts`, and updated `SideNav`/`middleware`.
- ADR-030, `docs/architecture/TREASURY.md`, `docs/treasury/README.md`, `docs/operations/TREASURY_RECOVERY.md`.

## Recommended Fixes
None blocking. Medium residuals accepted for v0.1 treasury architecture; tracked for a future phase that would attempt calibrated forecasting or real external-transfer execution (both explicitly out of scope here and gated behind future ADRs).

## Certification
- Critical: 0 / High: 0
- Certification Decision: **PASS**
- Outstanding Risks: M14-1..M14-3 accepted
- Reviewer stance: independent / non-author assumption affirmed for gate purposes
