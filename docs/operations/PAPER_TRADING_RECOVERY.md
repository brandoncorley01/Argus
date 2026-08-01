# Paper Trading recovery

## Checks

1. Migration head includes `e1f2a3b4c5d6`.
2. Providers `internal_paper` (default) and `deterministic_test` exist.
3. Portfolio kill switch clears via Founder API when safe.
4. Reconcile cash/positions via reports and order events — do not invent balances.
5. Before every paper order the API hydrates the in-memory book from DB cash +
   open positions. If capital looks wiped after an API restart, Start Argus
   (reload API) and confirm Home equity = cash + open marks; do not manually
   invent a balance. Reseed learning desk only when intentionally resetting to $300.

## Boundaries

Never enable live providers to “fix” paper issues. Paper remains authoritative for development.
