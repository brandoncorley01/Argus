# Argus Operations Model

Three environments. Only DEVELOPMENT and PAPER are operable today.

## DEVELOPMENT

| Attribute | Policy |
| --- | --- |
| Code changes | Permitted on feature branches |
| Data | Synthetic, fixture, or disposable local DB |
| Migrations | Experimental OK on disposable volumes |
| Cursor | Optional |
| Goal | Implement and verify changes |

## PAPER (controlled paper operation)

| Attribute | Policy |
| --- | --- |
| Execution provider | **`internal_paper` only** |
| Live execution | **Disabled** |
| Data | Persistent Postgres/Redis volumes |
| Migrations | Backup first; no casual resets |
| Strategies | Controlled / reviewed only |
| Daily review | Required (see Phase 15 ops guide when available) |
| Cursor | **Not required** — use scripts + EOC |
| Goal | Sustained paper operation |

## LIVE

| Attribute | Policy |
| --- | --- |
| Status | **Disabled — not certified** |
| Operating instructions | Denial only |
| Prerequisites (future) | Separate Founder authorization, credentials, review, certification |
| Current action | Do not configure live providers as default |

## Boundary: code vs paper operation

| Activity | Where |
| --- | --- |
| Edit source, run tests, open PRs | DEVELOPMENT |
| Submit paper orders, review health, generate reports | PAPER via EOC + scripts |
| Promote code into paper runtime | Merge/tag → pull on ops host → migrate → restart API/worker |

Paper operation must continue while Cursor is closed.

## Standard commands

See [scripts/README.md](../../scripts/README.md) and wrappers under `scripts/operations/` and `scripts/validation/`.

## Safety

- No real funds
- No broker/exchange accounts required
- External transfer execution remains forbidden
- Kill switches and risk limits remain authoritative
