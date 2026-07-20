# Architecture documentation

This directory holds Argus system design notes and Architecture Decision Records (ADRs).

## Contents

| Path | Purpose |
| --- | --- |
| [`decisions/`](decisions/) | Normative ADRs for major technical decisions |
| [`AUTHENTICATION.md`](AUTHENTICATION.md) | Phase 5 authentication, sessions, RBAC, bootstrap |
| [`CONFIG_POLICY_VERSIONING.md`](CONFIG_POLICY_VERSIONING.md) | Phase 6 configuration and policy versioning |
| [`OPERATING_MODE_STATE_MACHINE.md`](OPERATING_MODE_STATE_MACHINE.md) | Phase 7 operating-mode state machine |
| [`HEALTH_SUPERVISOR.md`](HEALTH_SUPERVISOR.md) | Phase 8 health supervisor and worker foundation |
| [`STRATEGY_LABORATORY.md`](STRATEGY_LABORATORY.md) | Phase 11 Strategy Laboratory (research only) |
| [`PAPER_TRADING.md`](PAPER_TRADING.md) | Phase 12 Paper Trading Institution / Execution Gateway |
| [`MICRO_LIVE.md`](MICRO_LIVE.md) | Phase 13 Micro-Live Institution (deny-by-default; live execution disabled) |
| [`TREASURY.md`](TREASURY.md) | Phase 14 Treasury and Executive Analytics (simulated-ledger only; external transfer execution forbidden) |

## Conventions

- Prefer ADRs for decisions that affect boundaries, security, audit, data stores, or operating modes.
- ADRs are durable; update status rather than silently rewriting history.
- Application scaffolding lives under `apps/`, `workers/`, and `packages/` — not under `docs/`.
- Do not document fictional capabilities as implemented.
