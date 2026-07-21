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
| `feat.worker.arq` | ARQ background worker | `implemented` | 1 | `0.1.0` | `active` | — | `feat.infra.redis` | `2026-07-19` |
| `feat.health.supervisor` | Institutional health supervisor | `implemented` | 1 | `0.1.0` | `active` | — | `feat.worker.arq`, `feat.mode.state_machine`, `feat.audit.fail_closed` | `2026-07-19` |
| `feat.api.fastapi` | FastAPI control plane | `implemented` | 1 | `0.1.0` | `active` | — | `feat.infra.postgres`, `feat.infra.redis` | `2026-07-21` |
| `feat.ui.eoc` | Executive Operations Center | `implemented` | 1 | `0.1.0` | `active` | — | `feat.api.fastapi`, `feat.auth.sessions` | `2026-07-19` |
| `feat.market.intelligence` | Market Intelligence Platform | `implemented` | 2 | `0.1.0` | `active` | Observation only — no signals/trading | `feat.api.fastapi`, `feat.audit.fail_closed` | `2026-07-19` |
| `feat.strategy.laboratory` | Strategy Laboratory | `implemented` | 2 | `0.1.0` | `active` | Research only — no live execution | `feat.api.fastapi`, `feat.audit.fail_closed` | `2026-07-19` |
| `feat.paper.trading` | Paper Trading Institution | `implemented` | 2 | `0.1.0` | `active` | Internal paper provider only — no live brokers | `feat.api.fastapi`, `feat.audit.fail_closed`, `feat.strategy.laboratory` | `2026-07-19` |
| `feat.micro_live.institution` | Micro-Live Institution (deny-by-default architecture) | `implemented` | 3 | `0.1.0` | `locked` | `live_execution_disabled` — architecture implemented, no reachable path to `MICRO_LIVE_ACTIVE`, no credentials configured | `feat.api.fastapi`, `feat.audit.fail_closed`, `feat.paper.trading` | `2026-07-20` |
| `feat.treasury.analytics` | Treasury and Executive Analytics (simulated-ledger architecture) | `implemented` | 3 | `0.1.0` | `active` | Simulated/internal-paper capital only — external transfer execution has no reachable code path (`external_transfer_execution_forbidden`); real-transfer execution remains permanently locked pending a dedicated future phase, ADR, and independent review | `feat.api.fastapi`, `feat.audit.fail_closed`, `feat.paper.trading` | `2026-07-20` |
| `feat.auth.sessions` | Server-side sessions | `implemented` | 1 | `0.1.0` | `active` | — | `feat.api.fastapi`, `feat.audit.fail_closed` | `2026-07-16` |
| `feat.audit.fail_closed` | Fail-closed audit | `implemented` | 1 | `0.1.0` | `active` | — | `feat.api.fastapi` | `2026-07-16` |
| `feat.config.policy_versioning` | Config & policy versioning engine | `implemented` | 1 | `0.1.0` | `active` | — | `feat.audit.fail_closed`, `feat.auth.sessions` | `2026-07-16` |
| `feat.mode.state_machine` | Operating mode state machine | `implemented` | 1 | `0.1.0` | `active` | — | `feat.audit.fail_closed`, `feat.config.policy_versioning` | `2026-07-17` |
| `feat.mode.micro_live` | MICRO_LIVE mode | `planned` | 4 | `0.1.0` | `locked` | Architecture ready (Phase 13 `live_activation_state`), but global `OperatingMode` entry stays locked; activation additionally requires credentials and `live_activation_state == MICRO_LIVE_ACTIVE`, which has no reachable code path in v0.1 | `feat.mode.state_machine`, `feat.micro_live.institution` | `2026-07-20` |
| `feat.mode.normal_live` | NORMAL_LIVE mode | `planned` | 5 | `0.1.0` | `locked` | Permanently locked in v0.1 | `feat.mode.state_machine` | `2026-07-15` |
| `feat.trading.live` | Live trading execution | `planned` | 4 | `0.0.0` | `locked` | Forbidden in v0.1 | — | `2026-07-15` |
| `feat.trading.leverage` | Leverage / margin | `planned` | 0 | `0.0.0` | `locked` | Permanently out of scope per AGENTS.md | — | `2026-07-15` |
| `feat.trading.withdrawals` | Withdrawals | `planned` | 0 | `0.0.0` | `locked` | Out of scope per AGENTS.md | — | `2026-07-15` |

## Governance rules

1. Locked features must not be activated by UI affordances or hidden flags.
2. Do not create decorative dashboards that imply an active capability.
3. Activation of a feature requires Founder approval, tests, and an audit trail (once audit exists).
4. Registry updates that change activation or locks are important configuration and must be versioned when runtime-backed.
