# Argus documentation

Durable documentation for Argus. Application code stays under `apps/` and `workers/`.

## Start here

| Document | Purpose |
| --- | --- |
| [`ARGUS_HEADQUARTERS.md`](ARGUS_HEADQUARTERS.md) | GitHub as source of truth; responsibilities; how Argus runs without Cursor |
| [`development/DEVELOPMENT_WORKFLOW.md`](development/DEVELOPMENT_WORKFLOW.md) | Branch → PR → CI workflow |
| [`operations/ARGUS_OPERATIONS_MODEL.md`](operations/ARGUS_OPERATIONS_MODEL.md) | DEVELOPMENT / PAPER / LIVE environments |
| [`releases/RELEASE_MANAGEMENT.md`](releases/RELEASE_MANAGEMENT.md) | Tags, RC criteria, rollback |
| [`operations/PHASE15_HANDOFF_STATUS.md`](operations/PHASE15_HANDOFF_STATUS.md) | Phase 15 WIP classification |

## Directory guide

| Directory | Purpose |
| --- | --- |
| [`foundation/`](foundation/) | Institutional identity and constraints |
| [`architecture/`](architecture/) | Design and ADRs |
| [`governance/`](governance/) | Constitution, phase execution, review, certification |
| [`operations/`](operations/) | Runbooks and operating model |
| [`development/`](development/) | Developer workflow |
| [`security/`](security/) | Secrets boundary |
| [`releases/`](releases/) | Release evidence and management |
| [`treasury/`](treasury/) | Treasury docs |
| [`research/`](research/) | Research notes |
| [`risk/`](risk/) | Risk policy |

## Conventions

- Prefer versioned docs over chat transcripts for decisions that affect risk or architecture.
- Never document live trading as certified while it remains disabled.
- RC evidence must not be rewritten; append new releases.
