# Argus Phase Execution Framework

| Field | Value |
| --- | --- |
| **Title** | Argus Phase Execution Framework |
| **Version** | `1.0.0` |
| **Status** | Binding |
| **Authority** | Founder |
| **Last updated** | `2026-07-19` |
| **Applies to** | Every implementation phase from Phase 9 onward |

## Purpose

This Framework defines **how** every Argus phase is executed.

It does **not** define **what** is built. Scope, deliverables, and acceptance criteria live in the phase prompt (and supporting architecture/ADR work).

**Standards** (safety, audit, testing, merge, ethics) live in:

[`ARGUS_ENGINEERING_CONSTITUTION.md`](ARGUS_ENGINEERING_CONSTITUTION.md)

Beginning with Phase 9, implementation prompts should define only:

- Objective  
- Deliverables  
- Acceptance Criteria  
- Out-of-Scope  
- Dependencies  
- Special Constraints (if any)  

Everything else is inherited from the Constitution and this Framework.

## Authority

1. This Framework binds contributors, agents, and automation executing Argus phases.
2. The Constitution prevails on engineering standards (§ merge, Red Team, audit, ethics).
3. `AGENTS.md` permanent product/safety rules prevail on forbidden capabilities.
4. Accepted ADRs prevail on specific technical decisions they cover.
5. Amendments require Founder approval and a version bump of this document.

## Relationship to other documents

| Document | Role |
| --- | --- |
| [Engineering Constitution](ARGUS_ENGINEERING_CONSTITUTION.md) | *What* quality/safety/audit/test/merge standards apply |
| This Framework | *How* a phase is planned, built, reviewed, and closed |
| [Independent Engineering Review Framework](ARGUS_INDEPENDENT_ENGINEERING_REVIEW_FRAMEWORK.md) | *How* independent / Red Team review is conducted |
| [Release Certification Framework](ARGUS_RELEASE_CERTIFICATION_FRAMEWORK.md) | *When* a milestone may be certified / released |
| [`AGENTS.md`](../../AGENTS.md) | Permanent product constraints |
| [`ROADMAP.md`](../../ROADMAP.md) | Phase sequence and status |
| [`CHANGELOG.md`](../../CHANGELOG.md) | Release history |
| [Feature Governance](FEATURE_GOVERNANCE.md) | Capability honesty and locks |
| [Institutional Maturity Model](INSTITUTIONAL_MATURITY_MODEL.md) | Maturity claims |
| [ADRs](../architecture/decisions/README.md) | Technical decisions |
| Architecture / recovery docs | Phase-specific design and operations |

**Do not restate the Constitution here.** Cite it.

## Table of contents

1. [The Argus phase lifecycle](#1-the-argus-phase-lifecycle)
2. [Standard phase structure](#2-standard-phase-structure)
3. [Implementation workflow](#3-implementation-workflow)
4. [Implementation rules](#4-implementation-rules)
5. [Phase completion checklist](#5-phase-completion-checklist)
6. [Database change process](#6-database-change-process)
7. [API change process](#7-api-change-process)
8. [Documentation workflow](#8-documentation-workflow)
9. [Quality gates](#9-quality-gates)
10. [Release preparation](#10-release-preparation)
11. [Automated work](#11-automated-work)
12. [Manual approvals](#12-manual-approvals)
13. [Future prompt format](#13-future-prompt-format)
14. [Example (Phase 12–scale prompt)](#14-example-phase-12scale-prompt)

---

## 1. The Argus phase lifecycle

```text
1.  Founder Objective
2.  Repository Inspection
3.  Architecture Review
4.  Implementation Plan
5.  Coding
6.  Testing
7.  Documentation
8.  Security Review
9.  Red Team Review
10. Commit
11. Push
12. Pull Request
13. Certification
14. Merge
15. Release Notes
16. Prepare Next Phase
```

| Step | Intent |
| --- | --- |
| **1. Founder Objective** | Founder states phase name, objective, deliverables, acceptance, out-of-scope, dependencies |
| **2. Repository Inspection** | Confirm branch, clean tree (or known dirty state), `main` sync, migration head, infra health as needed |
| **3. Architecture Review** | Read Constitution, ADRs, related architecture/recovery docs; note deviations before coding |
| **4. Implementation Plan** | Concise plan only; apply 90/10 rule (Constitution §4) |
| **5. Coding** | Implement deliverables; no scope expansion |
| **6. Testing** | Constitution §10 — unit, Postgres integration, concurrency, migrations, API, security as applicable |
| **7. Documentation** | Architecture, ADRs, registry, roadmap, changelog, recovery as applicable |
| **8. Security Review** | AuthN/AuthZ, secrets, CSRF, worker privilege, fail-closed paths |
| **9. Red Team Review** | Independent review; Critical/High must be zero unresolved (Constitution §12) |
| **10. Commit** | Descriptive commit(s); clean tree after |
| **11. Push** | Push feature branch to origin |
| **12. Pull Request** | Open PR (via `gh` or comparison URL); do not fabricate merge |
| **13. Certification** | Confirm gates (§9); Founder approval to merge |
| **14. Merge** | Into `main` under Constitution §13 |
| **15. Release Notes** | Changelog / release notes for the phase outcome |
| **16. Prepare Next Phase** | Update ROADMAP; do **not** start the next phase branch until merge is real |

---

## 2. Standard phase structure

Every phase prompt (or phase charter) must define **only**:

| Field | Content |
| --- | --- |
| **Purpose** | Why this phase exists institutionally |
| **Objectives** | Outcomes, not file lists |
| **Deliverables** | Concrete artifacts (APIs, migrations, UI surfaces, docs) |
| **Acceptance Criteria** | Testable completion conditions |
| **Dependencies** | Prior phases, infra, unlocked features |
| **Out of Scope** | Explicit exclusions (and default: no fabricated capabilities) |
| **Expected Risks** | Technical/operational risks and mitigations |

Everything else—fail-closed audit, RBAC, testing doctrine, merge policy, ethics—comes from the Constitution.

---

## 3. Implementation workflow

Execute in order unless Founder authorizes a documented exception:

1. **Repository inspection** — branch, status, remotes, migration head, whether prior phase merged  
2. **Architecture understanding** — read ADRs and architecture docs for touched domains  
3. **Dependency analysis** — Feature Registry locks, maturity claims, infra prerequisites  
4. **Migration planning** — if schema changes, plan revision chain, backfill, downgrade posture  
5. **Implementation planning** — short plan; surface Founder decisions before coding when required  
6. **Code implementation** — deliverables only; modular boundaries (Constitution §5)  
7. **Testing** — Constitution §10; run relevant suites after changes  
8. **Documentation** — §8 of this Framework  
9. **Review** — security + Red Team (Constitution §8, §12)  
10. **Merge** — after gates and Founder certification  

---

## 4. Implementation rules

1. **Small commits** — Prefer reviewable increments; one descriptive final commit is acceptable when Founder requests a single phase commit.  
2. **Incremental implementation** — Ship vertical slices that can be tested; avoid big-bang untestable dumps.  
3. **No hidden work** — Do not silently start the next phase or unrelated subsystems.  
4. **No unrelated refactors** — No drive-by cleanups outside deliverables.  
5. **No fabricated capabilities** — No fake dashboards, fake PnL, fake health, unlocked live trading.  
6. **No skipped validation** — Do not skip, hide, weaken, or reclassify failing tests without Founder approval (Constitution §10, §15).  

Apply the **$10 million test** (Constitution §3) to material design choices.

---

## 5. Phase completion checklist

Before declaring a phase complete:

- [ ] Requirements / deliverables implemented  
- [ ] Relevant tests passing (including Postgres integration and concurrency when applicable)  
- [ ] Docs updated and honest  
- [ ] ADRs added or updated when major decisions changed  
- [ ] Feature Registry updated  
- [ ] ROADMAP updated  
- [ ] CHANGELOG updated  
- [ ] Recovery / operations docs updated when new operational surfaces exist  
- [ ] Migrations validated (`base` → `head` when schema changed)  
- [ ] Working tree clean  
- [ ] Descriptive commit present  
- [ ] Security review done  
- [ ] Red Team done with **no unresolved Critical/High**  
- [ ] Development Covenant satisfied (Constitution §17)  

---

## 6. Database change process

When a phase changes schema (Constitution §6):

1. **Model** — SQLAlchemy models aligned with institutional invariants  
2. **Migration** — Alembic revision with clear `down_revision`  
3. **Upgrade** — Apply and verify on real PostgreSQL  
4. **Downgrade** — Support when practical; document irreversible steps  
5. **Validation** — Migration tests; constraint/trigger checks  
6. **Concurrency review** — Locks, unique constraints, idempotency tables  
7. **Documentation** — Architecture note + ADR if the decision is major  

Do not initialize shared `SystemState` or overwrite Founder accounts as “prep” unless the phase explicitly requires an approved demonstration.

---

## 7. API change process

When a phase changes HTTP APIs (Constitution §7):

1. **Schemas** — Typed request/response models  
2. **Documentation** — Architecture/API docs match behavior  
3. **OpenAPI** — Accurate models and status codes  
4. **Authentication** — Session rules unchanged unless ADR supersedes  
5. **RBAC** — Route gate + service enforcement  
6. **Versioning** — Prefer `/api/v1/...`  
7. **Testing** — AuthZ, CSRF on mutations, stable error codes  

---

## 8. Documentation workflow

Material phases update, as applicable:

| Artifact | When |
| --- | --- |
| Architecture docs | New subsystems or behavior |
| Recovery / operations | New failure modes or runbooks |
| ADRs | Major technical decisions |
| Feature Registry | Status, activation, locks |
| ROADMAP | Phase status |
| CHANGELOG | User/operator-visible outcomes |
| Developer docs / README | Run/build changes |
| Release notes | At certification / merge |

Honesty rule: documentation must not claim locked or unimplemented capabilities as active.

---

## 9. Quality gates

| Gate | Name | Exit criteria |
| --- | --- | --- |
| **1** | Architecture complete | Plan + ADR/architecture understanding; Founder decisions resolved |
| **2** | Implementation complete | Deliverables present; out-of-scope respected |
| **3** | Tests passing | Constitution §10 satisfied for the change set |
| **4** | Security reviewed | AuthN/AuthZ/secrets/fail-closed checked |
| **5** | Documentation complete | §8 checklist done |
| **6** | Red Team complete | No unresolved Critical/High |
| **7** | Founder approval | Explicit approval to merge / certify |
| **8** | Merge | Merged to `main` under Constitution §13 |

Do not skip gates. Do not invent “merge complete” without an authenticated merge mechanism.

---

## 10. Release preparation

Every completed phase produces (as applicable):

- **Release notes** (CHANGELOG and/or `docs/releases/`)  
- **Migration notes** (revision id, backfill/downgrade caveats)  
- **Known limitations**  
- **Future work** (honest, non-binding)  
- **Breaking changes**  
- **Operational notes** (compose profiles, worker commands, recovery links)  

---

## 11. Automated work

Agents (including Cursor) should perform **without** asking the Founder to run routine steps:

- Repository inspection and `git status`  
- Branch creation/cleanup when authorized by the phase prompt  
- Migration validation  
- Relevant test suites  
- Documentation / CHANGELOG / Feature Registry / ROADMAP updates required by the phase  
- Commit preparation when the Founder authorizes commit  
- Push when the Founder authorizes push  
- PR body + comparison URL when `gh` is unavailable  

Never ask the Founder to manually execute routine engineering work unless §12 applies.

---

## 12. Manual approvals

Interrupt the Founder **only** for:

- GitHub authentication / PR merge when no safe automated path exists  
- External credentials or secrets  
- Production deployment  
- Explicit Founder approval (Gate 7)  
- Architectural conflicts with Accepted ADRs or the Constitution  
- Institutional policy conflicts with `AGENTS.md` or Feature Registry locks  

Do not interrupt for “please run pytest” or “please open Docker” when the agent can do so.

---

## 13. Future prompt format

Standard Phase 9+ implementation prompt:

```text
Read and obey:
- docs/governance/ARGUS_ENGINEERING_CONSTITUTION.md
- docs/governance/ARGUS_PHASE_EXECUTION_FRAMEWORK.md

Phase: <N — Name>

Objective:
<one short paragraph>

Deliverables:
- ...

Acceptance Criteria:
- ...

Out of Scope:
- ...

Dependencies:
- ...

Special Constraints:   # optional
- ...
```

Do **not** paste fail-closed, RBAC, Red Team, or covenant text into every prompt—those are inherited.

---

## 14. Example (Phase 12–scale prompt)

*Illustrative only. Not an authorization to begin Phase 12.*

```text
Read and obey:
- docs/governance/ARGUS_ENGINEERING_CONSTITUTION.md
- docs/governance/ARGUS_PHASE_EXECUTION_FRAMEWORK.md

Phase: 12 — Observation Research Pipeline Foundation

Objective:
Introduce a governed, auditable observation pipeline that records research
artifacts without execution capability. Remain OBSERVE-compatible; no paper
or live trading.

Deliverables:
- Domain models + Alembic migration for research observation runs
- Service APIs under /api/v1/research/observations (read + Founder/Operator create)
- Fail-closed audit on create; append-only observation evidence
- ADR(s) + recovery notes + Feature Registry / ROADMAP / CHANGELOG updates
- PostgreSQL integration + concurrency tests

Acceptance Criteria:
- Migrations validate base→head
- Full relevant pytest green; ruff/mypy clean
- VIEWER read-only; OPERATOR cannot unlock live features
- Red Team: zero unresolved Critical/High
- No SystemState initialization of shared environments unless approved demo

Out of Scope:
- Strategy signals, orders, positions, paper/live trading, exchanges, EOC UI polish

Dependencies:
- Phase 7 operating mode; Phase 8 health supervisor; feat.mode.state_machine active
- Feature Registry: observation feature unlocked to implemented/active at merge

Special Constraints:
- Do not fabricate market data; provenance required for any ingested series
```

This fits on one page because lifecycle, quality gates, merge policy, and ethics are inherited.

---

## Amendment

Propose amendments as a PR that bumps **Version** and **Last updated**, states rationale, and receives Founder approval.

---

*Argus Phase Execution Framework v1.0.0 — binding phase operating procedure.*
