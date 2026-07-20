# Market Intelligence recovery

## Symptoms

- `/api/v1/market/*` returns 5xx or empty unexpectedly
- Provider health stuck `unhealthy`
- Duplicate ingest rejected unexpectedly

## Checks

1. Confirm migration head includes `c9d0e1f2a3b4`.
2. Confirm seeded providers `manual` and `null_probe` exist.
3. Probe: `POST /api/v1/market/providers/null_probe/probe` with session + CSRF.
4. Review `market_quality_findings` for stale/duplicate/provider_error.
5. Confirm ingest uses `Idempotency-Key` for replay-safe retries.

## Boundaries

Do not “fix” empty dashboards by inventing prices. Empty means no observations were ingested.

Trading, signals, and execution remain out of scope.
