# Changelog

All notable changes to Argus are recorded here.
Format follows a simple keep-a-changelog style adapted for institutional releases.

## [Unreleased]

### Added

- Phase 5 authentication: Argon2id passwords, PostgreSQL server-side sessions, CSRF, login lockout, Founder bootstrap CLI
- RBAC enforcement for Founder-only user/role management; audit reads require authentication
- Phase 6 configuration/policy versioning: lifecycle statuses, canonical payload hashing, secret detection, atomic activation with Institutional Identity updates, HTTP APIs under `/api/v1/configurations` and `/api/v1/policies`
- Phase 7 operating-mode state machine: singleton authoritative state, transition matrix, durable idempotency, emergency fail-closed doctrine, APIs under `/api/v1/operating-mode`
- Phase 8 institutional health supervisor and worker foundation: governed service registry, append-only heartbeats, projections, durable supervisor lease, incidents/lifecycle, protective actions, ARQ worker, SYSTEM `SAFE_MODE` integration
- Phase 9 Executive Operations Center (`apps/eoc`): Next.js App Router BFF session bridge, role-aware dashboards, operations/services/workers/incidents/audit/configurations/policies/administration — real API state only
- Phase 10 Market Intelligence Platform: multi-provider registry, historical OHLCV/news/calendar/research storage, replay-safe ingest, quality monitoring, `/api/v1/market` APIs, EOC `/market` — observation only
- Phase 11 Strategy Laboratory: governed strategy versions, deterministic backtest/walk-forward/optimization/Monte Carlo, validation reports, `/api/v1/strategies`, EOC `/strategies` — research only
- Phase 12 Paper Trading Institution: Execution Gateway, Internal Paper Provider (default), portfolios/orders/fills/P&L/risk/replay, `/api/v1/paper`, EOC `/paper` — no brokerage account required
- Governance frameworks: Engineering Constitution, Phase Execution, Independent Review, Release Certification

### Planned

- Phase 13 Hardening & CI

## [0.1.0-foundation] — 2026-07-16

### Added

- Project governance baseline (`AGENTS.md`, ADRs 001–007, institutional identity/maturity/feature docs)
- Docker Compose foundation for PostgreSQL 16 and Redis 7 with operator scripts
- FastAPI control-plane skeleton with fail-closed settings and `/health` / `/ready`
- Alembic-managed institutional domain schema (identity, users/roles, audit, config/policy versions, feature registry, maturity, system state, incidents, health events)
- Fail-closed audit service and read API (`GET /api/v1/audit/events`)

### Security

- Live trading modes (`MICRO_LIVE`, `NORMAL_LIVE`) remain permanently locked in v0.1
- Secrets excluded via `.gitignore`; `.env.example` documents required variables only
- Audit payloads redact sensitive keys before persistence

### Notes

- No exchange integrations, market data, strategies, execution, leverage, margin, futures, options, short selling, or withdrawals
- No public remote configured in early local development; commits remain local unless explicitly pushed
