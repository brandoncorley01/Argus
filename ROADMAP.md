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
| 9 — Executive Operations Center | Done | Next.js EOC: auth bridge, role dashboards, ops/health/incidents/audit/config/policy |
| 10 — Market Intelligence Platform | Done | Observation-only multi-provider intelligence (no trading/signals) |
| 11 — Strategy Laboratory | Done | Versioned strategies, deterministic research engines, validation — no live trading |
| 12 — Paper Trading Institution | Done | Internal paper execution provider + gateway (no brokerage account required) |
| 13 — Micro-Live Institution | Done | Deny-by-default live-execution architecture; live trading disabled; no credentials required |
| 14 — Treasury and Executive Analytics | Planned | Not yet implemented |
| 15 — Hardening & CI | Planned | GitHub Actions, acceptance pack |

## Explicitly out of scope (v0.1)

- Live trading / exchange credentials
- Leverage, margin, futures, options, short selling
- Withdrawals
- Fabricated financial performance data
- Decorative or misleading dashboard metrics

## Near-term sequence

1. Merge Phase 8–13 when Founder authorizes (stacked branches; keep phases identifiable)
2. Treasury and Executive Analytics (Phase 14) — do not start until Founder authorizes
3. Hardening & CI (Phase 15) — do not start until Founder authorizes

## Longer horizon (post-foundation)

- Observation / research pipelines (maturity Level 2+)
- Paper-trading execution under controls (Level 3)
- Micro-live execution architecture exists (Phase 13) but remains deny-by-default; actual live activation requires a dedicated future phase, ADR, and independent review
- Any live capability only after explicit Founder approval and unlocked feature registry entries
