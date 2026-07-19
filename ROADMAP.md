# Argus roadmap

Private institutional crypto research and paper-trading system.
Capital preservation comes before profit. Live trading stays disabled until explicitly implemented and approved.

## Current release target

**v0.1 Foundation** — smallest complete institutional control plane.

| Phase | Status | Scope |
| --- | --- | --- |
| 0 — Repository & governance | Done | `AGENTS.md`, docs structure, ADRs, identity/feature/maturity docs |
| 1 — Compose infra | Done | PostgreSQL 16, Redis 7, scripts, healthchecks |
| 2 — API skeleton | Done | FastAPI, settings fail-closed, `/health`, `/ready` |
| 3 — Schema & Alembic | Done | Foundational institutional domain models + migration |
| 4 — Audit framework | Done | Fail-closed audit service + read API |
| 5 — Authentication & RBAC | Done | Server-side sessions, Argon2id, CSRF, lockout, Founder bootstrap |
| 6 — Config & policy versioning APIs | Done | Lifecycle versions, hash integrity, atomic activate, APIs + audit |
| 7 — Operating-mode state machine | Done | Governed modes; PAPER/MICRO_LIVE/NORMAL_LIVE unavailable; emergency fail-closed |
| 8 — Health supervisor (ARQ) | Done | Governed registry, heartbeats, supervisor lease, incidents, SYSTEM SAFE_MODE |
| 9 — Executive Operations Center | Planned | Next.js operator UI (status, audit, mode) — no fake dashboards |
| 10 — Hardening & CI | Planned | GitHub Actions, acceptance pack |

## Explicitly out of scope (v0.1)

- Live trading / exchange credentials
- Leverage, margin, futures, options, short selling
- Withdrawals
- Fabricated financial performance data
- Decorative or misleading dashboard metrics

## Near-term sequence

1. Review/merge Phase 8 on `phase-8-health-supervisor-worker-foundation` when Founder authorizes
2. Phase 9 Executive Operations Center once control-plane APIs are trustworthy
3. Hardening & CI

## Longer horizon (post-foundation)

- Observation / research pipelines (maturity Level 2+)
- Paper-trading execution under controls (Level 3)
- Any live capability only after explicit Founder approval and unlocked feature registry entries
