# Architecture documentation

This directory holds Argus system design notes and Architecture Decision Records (ADRs).

## Contents

| Path | Purpose |
| --- | --- |
| [`decisions/`](decisions/) | Normative ADRs for major technical decisions |

## Conventions

- Prefer ADRs for decisions that affect boundaries, security, audit, data stores, or operating modes.
- ADRs are durable; update status rather than silently rewriting history.
- Application scaffolding lives under `apps/`, `workers/`, and `packages/` — not under `docs/`.
- Do not document fictional capabilities as implemented.
