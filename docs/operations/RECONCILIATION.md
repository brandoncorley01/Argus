# Reconciliation runbook

Applies to Phase 13 `reconciliation_runs` — fixture-based comparison between an authoritative state and a comparison state. No provider network call is made; both states are supplied by the caller (Founder or Operator).

## Running a reconciliation

1. `POST /api/v1/micro-live/reconciliation/runs` with:
   ```json
   {
     "provider_key": "internal_paper",
     "authoritative_state": {"cash": "1000.00", "positions": [{"symbol": "BTC-USD", "quantity": "0.01"}]},
     "comparison_state": {"cash": "1000.00", "positions": [{"symbol": "BTC-USD", "quantity": "0.01"}]}
   }
   ```
2. Response includes `status` (`clean` or `discrepancies_found`) and the run id.
3. If discrepancies exist: `GET /api/v1/micro-live/reconciliation/runs/{run_id}/discrepancies` lists each `kind` (`cash_mismatch`, `position_mismatch`, etc.) with `detail`.

## Investigating discrepancies

1. For `cash_mismatch`: compare against the authoritative ledger (Phase 12 `PaperCashLedger` for paper) — determine whether the "comparison" input was stale or wrong, not the authoritative side.
2. For `position_mismatch`: compare quantities per symbol; check for missed fills or duplicate/void orders in the authoritative source.
3. Mark discrepancies resolved only after root cause is documented (future enhancement: `resolved` flag update endpoint; currently tracked via audit/incident).
4. For anything beyond a fixture exercise (i.e., involving a real venue in a future phase), open an incident before taking any corrective action on real capital.

## Scope note

Phase 13 reconciliation is intentionally fixture-driven so the discrepancy-detection logic can be exercised and audited without any live account or provider credentials. A future phase that wires this to a real provider must add its own explicit ADR and review.
