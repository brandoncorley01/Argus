# Market Intelligence Platform (Phase 10)

## Purpose

Argus may **observe, normalize, classify, and store** market information. It must **not** generate trading signals, recommend trades, produce orders, manage positions, allocate capital, or execute trades.

## Architecture

| Component | Role |
| --- | --- |
| `market_providers` | Multi-provider registry with priority and failover flags |
| `market_provider_health` | Provider health projection |
| Adapters | `manual` (intake), `null_probe` (health only), `http_json` (optional configured URL) |
| Storage | OHLCV bars, news, economic calendar, research, normalized observations |
| Quality | Missing/stale/duplicate/provider_error findings |
| Ingestion | Replay-safe via `Idempotency-Key` + observation idempotency keys; retry/backoff on HTTP probes |

## APIs (`/api/v1/market`)

- Providers, probe, instruments
- Bars, observations, news, calendar, research
- Ingestion runs, quality findings
- `POST /ingest` (FOUNDER/OPERATOR + CSRF)

## Honesty rules

- Seeded providers do **not** invent live market prices.
- Dashboards show empty states when no data was ingested.
- Source attribution is mandatory on stored observations.

## EOC

`/market` in the Executive Operations Center surfaces provider health, quality, and ingested observations only.

See ADR-026.
