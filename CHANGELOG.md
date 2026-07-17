# Changelog

All notable changes to Argus are recorded here.
Format follows a simple keep-a-changelog style adapted for institutional releases.

## [Unreleased]

### Added

- Phase 5 authentication: Argon2id passwords, PostgreSQL server-side sessions, CSRF, login lockout, Founder bootstrap CLI
- RBAC enforcement for Founder-only user/role management; audit reads require authentication

### Planned

- Phase 6: configuration and policy activation APIs
- Operating-mode state machine services
- Health supervisor worker (ARQ)
- Executive Operations Center (Next.js)

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
