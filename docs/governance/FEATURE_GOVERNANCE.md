# Feature Governance

Argus uses a Feature Registry to record capabilities honestly. Prefer typed registry entries and locks over placeholder UI or fake metrics.

## Registry fields

Every feature record must include:

| Field | Description |
| --- | --- |
| Feature identifier | Stable machine id (e.g. `feat.operating_mode.micro_live`) |
| Feature name | Human-readable name |
| Status | `planned` \| `scaffolded` \| `implemented` \| `validated` \| `deprecated` |
| Capability level | Maturity level 0–6 this feature supports |
| Version | Feature version string |
| Activation state | `inactive` \| `active` \| `locked` |
| Lock reason | Required when `locked` |
| Dependencies | Feature ids or infrastructure dependencies |
| Last review timestamp | ISO-8601 UTC |

Runtime persistence of the registry is deferred to a later application phase. This document is the Phase 0 source of truth.

## Initial registry (v0.1 Foundation)

| Feature ID | Name | Status | Level | Version | Activation | Lock reason | Dependencies | Last review |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `feat.infra.postgres` | PostgreSQL system of record | `implemented` | 1 | `0.1.0` | `active` | — | Docker Compose | `2026-07-16` |
| `feat.infra.redis` | Redis coordination/broker | `implemented` | 1 | `0.1.0` | `active` | — | Docker Compose | `2026-07-16` |
| `feat.worker.arq` | ARQ background worker | `planned` | 1 | `0.1.0` | `locked` | Not implemented before Phase 2+ | `feat.infra.redis` | `2026-07-15` |
| `feat.api.fastapi` | FastAPI control plane | `scaffolded` | 1 | `0.1.0` | `active` (health/ready only) | — | `feat.infra.postgres`, `feat.infra.redis` | `2026-07-16` |
| `feat.ui.eoc` | Executive Operations Center | `planned` | 1 | `0.1.0` | `locked` | Frontend phase not started | `feat.api.fastapi` | `2026-07-15` |
| `feat.auth.sessions` | Server-side sessions | `implemented` | 1 | `0.1.0` | `active` | — | `feat.api.fastapi`, `feat.audit.fail_closed` | `2026-07-16` |
| `feat.audit.fail_closed` | Fail-closed audit | `implemented` | 1 | `0.1.0` | `active` | — | `feat.api.fastapi` | `2026-07-16` |
| `feat.config.policy_versioning` | Config & policy versioning engine | `implemented` | 1 | `0.1.0` | `active` | — | `feat.audit.fail_closed`, `feat.auth.sessions` | `2026-07-16` |
| `feat.mode.state_machine` | Operating mode state machine | `implemented` | 1 | `0.1.0` | `active` | — | `feat.audit.fail_closed`, `feat.config.policy_versioning` | `2026-07-17` |
| `feat.mode.micro_live` | MICRO_LIVE mode | `planned` | 4 | `0.1.0` | `locked` | Permanently locked in v0.1 | `feat.mode.state_machine` | `2026-07-15` |
| `feat.mode.normal_live` | NORMAL_LIVE mode | `planned` | 5 | `0.1.0` | `locked` | Permanently locked in v0.1 | `feat.mode.state_machine` | `2026-07-15` |
| `feat.trading.live` | Live trading execution | `planned` | 4 | `0.0.0` | `locked` | Forbidden in v0.1 | — | `2026-07-15` |
| `feat.trading.leverage` | Leverage / margin | `planned` | 0 | `0.0.0` | `locked` | Permanently out of scope per AGENTS.md | — | `2026-07-15` |
| `feat.trading.withdrawals` | Withdrawals | `planned` | 0 | `0.0.0` | `locked` | Out of scope per AGENTS.md | — | `2026-07-15` |

## Governance rules

1. Locked features must not be activated by UI affordances or hidden flags.
2. Do not create decorative dashboards that imply an active capability.
3. Activation of a feature requires Founder approval, tests, and an audit trail (once audit exists).
4. Registry updates that change activation or locks are important configuration and must be versioned when runtime-backed.
