# Argus Engineering Constitution

| Field | Value |
| --- | --- |
| **Title** | Argus Engineering Constitution |
| **Version** | `1.0.0` |
| **Status** | Binding |
| **Authority** | Founder |
| **Last updated** | `2026-07-19` |
| **Applies to** | All Argus engineering work from Phase 9 onward (and remaining Phase 8 remediation) |

## Purpose

This Constitution is the supreme engineering authority for the Argus codebase. It defines how Argus is designed, built, reviewed, merged, and released.

Future implementation prompts should begin with:

> Read and obey `docs/governance/ARGUS_ENGINEERING_CONSTITUTION.md` before making any changes.

Agents and engineers inherit the standards herein without requiring those standards to be restated in every prompt.

## Authority

1. This Constitution binds all contributors, agents, and automation working on Argus.
2. Where this Constitution conflicts with informal practice, this Constitution prevails.
3. Where this Constitution conflicts with an Accepted ADR on a specific technical decision, the ADR prevails for that decision until superseded.
4. Where this Constitution conflicts with `AGENTS.md` permanent rules, `AGENTS.md` permanent rules prevail (capital preservation, no live trading until approved, no leverage/margin/futures/shorts/withdrawals, no fabricated financial data).
5. Amendments require Founder approval and a version bump of this document.

## Scope

Covers architecture, database, APIs, security, audit, testing, documentation, review, merge, and release practice for control-plane and worker code. It does not authorize trading, market-data, exchange, treasury-transfer, or leverage capabilities forbidden by `AGENTS.md`.

## Relationship to other documents

| Document class | Role relative to this Constitution |
| --- | --- |
| [`AGENTS.md`](../../AGENTS.md) | Permanent product/safety rules; not superseded |
| [ADRs](../architecture/decisions/README.md) | Normative decisions for specific technical choices |
| [Feature Governance](FEATURE_GOVERNANCE.md) | Honest capability registry and locks |
| [Institutional Maturity Model](INSTITUTIONAL_MATURITY_MODEL.md) | Capability-level claims and advancement rules |
| [Institutional Identity](../foundation/INSTITUTIONAL_IDENTITY.md) | Durable identity and mode/role names |
| Phase / architecture docs | Phase-scoped design detail; must obey this Constitution |
| [Phase Execution Framework](ARGUS_PHASE_EXECUTION_FRAMEWORK.md) | How phases are planned, built, reviewed, and closed |
| [Independent Engineering Review Framework](ARGUS_INDEPENDENT_ENGINEERING_REVIEW_FRAMEWORK.md) | How independent / Red Team review is conducted and certified |
| [Release Certification Framework](ARGUS_RELEASE_CERTIFICATION_FRAMEWORK.md) | When a milestone is institutionally releasable |
| [`ROADMAP.md`](../../ROADMAP.md) / [`CHANGELOG.md`](../../CHANGELOG.md) | Sequence and release history |
| Recovery / operations docs | Operational procedures under constitutional standards |

**Do not duplicate ADR content here.** Cite ADRs. Propose a new or superseding ADR when changing a major technical decision.

## Table of contents

1. [Mission](#1-mission)
2. [Core principles](#2-core-principles)
3. [The $10 million test](#3-the-10-million-test)
4. [The 90/10 rule](#4-the-9010-rule)
5. [Architecture rules](#5-architecture-rules)
6. [Database rules](#6-database-rules)
7. [API standards](#7-api-standards)
8. [Security](#8-security)
9. [Audit](#9-audit)
10. [Testing](#10-testing)
11. [Documentation](#11-documentation)
12. [Red Team review](#12-red-team-review)
13. [Merge policy](#13-merge-policy)
14. [Release policy](#14-release-policy)
15. [Engineering ethics](#15-engineering-ethics)
16. [Cursor operating directive](#16-cursor-operating-directive)
17. [Argus Development Covenant](#17-argus-development-covenant)

---

## 1. Mission

Argus exists to become an **autonomous software institution**: a private institutional crypto research and paper-trading control plane that earns trust through discipline, not spectacle.

Mission pillars:

- **Capital preservation** before profit
- **Disciplined decision-making** under explicit modes and policies
- **Transparency** of state, capability, and limitation
- **Auditability** of important actions
- **Deterministic behavior** under concurrency and failure
- **Operational excellence** (safe failure, recoverability, honest health)
- **Long-term institutional growth** via maturity levels and governed features

Profit is a consequence of discipline. It is never the primary engineering objective.

See also: [`AGENTS.md`](../../AGENTS.md), [`INSTITUTIONAL_IDENTITY.md`](../foundation/INSTITUTIONAL_IDENTITY.md).

---

## 2. Core principles

| Principle | Meaning |
| --- | --- |
| Safety before speed | Prefer correct, fail-closed behavior over premature delivery |
| Evidence over assumptions | Do not claim profitability, health, or capability without evidence |
| Configuration over hardcoding | Important policy and config must be versioned (see ADR-009–014) |
| Audit before automation | Automate only where audit and authority already exist |
| Fail closed | Uncertain or unauditable state must stop the mutation |
| Least privilege | Roles, workers, and APIs get minimum authority |
| Institution before feature | Institutional integrity outranks feature novelty |
| Simple beats clever | Prefer clarity and reversibility over cleverness |
| Deterministic behavior | Same inputs and locks → same institutional outcomes |
| Recoverability | Every critical path has a documented recovery posture |
| Operational transparency | Do not fake dashboards, health, or maturity |
| Security by default | Sessions, CSRF, RBAC, secrets—no “open for convenience” |
| Documentation is engineering | Undocumented institutional behavior is incomplete |
| Small reversible changes | Prefer reviewable, mergeable increments |
| Institutional thinking | Design as if Argus outlives any single implementer |

---

## 3. The $10 million test

Every material design decision must answer:

> Would we build it this way if Argus managed **$10 million**?

If the answer is no—**redesign it** before implementation.

This test covers data integrity, concurrency, audit, authz, recovery, and honesty of capability claims. It does not authorize live trading or leverage.

---

## 4. The 90/10 rule

| Share | Work |
| --- | --- |
| **90%** | Thinking, architecture, review, validation |
| **10%** | Coding |

Never reverse this ratio. Code without design, review, and validation is not institutional engineering.

---

## 5. Architecture rules

Normative layout and boundaries: [ADR-001](../architecture/decisions/ADR-001-monorepo-architecture.md), [ADR-004](../architecture/decisions/ADR-004-nextjs-fastapi-boundary.md).

1. **Bounded contexts** — Keep API, workers, docs, and infra responsibilities separated.
2. **Service boundaries** — Business logic lives in services; routers stay thin.
3. **Layering** — HTTP → services → persistence; no upward coupling from DB helpers into HTTP.
4. **Dependency direction** — Shared rules used by API and workers must not create privilege side doors ([ADR-003](../architecture/decisions/ADR-003-redis-arq-worker-architecture.md), [ADR-024](../architecture/decisions/ADR-024-arq-health-worker-foundation.md)).
5. **Domain ownership** — One authoritative owner per institutional concept (e.g. operating mode singleton: [ADR-015](../architecture/decisions/ADR-015-authoritative-operating-state-singleton.md)).
6. **Immutability** — Evidence and version payloads are append-only / immutable once committed ([ADR-013](../architecture/decisions/ADR-013-database-immutability-triggers.md)).
7. **Idempotency** — Mutating institutional operations require durable idempotency where concurrency exists ([ADR-017](../architecture/decisions/ADR-017-durable-operating-mode-idempotency.md), [ADR-021](../architecture/decisions/ADR-021-append-only-heartbeats.md)).
8. **Append-only history** — Mode history, heartbeats, audit, and lifecycle events are evidence—not editable scratchpads.
9. **Configuration management** — Versioned documents, canonical hashes, atomic activation ([ADR-009](../architecture/decisions/ADR-009-config-policy-version-lifecycle.md)–[ADR-014](../architecture/decisions/ADR-014-institutional-identity-projection-and-retirement.md)).
10. **Institutional identity** — Runtime projections follow [INSTITUTIONAL_IDENTITY.md](../foundation/INSTITUTIONAL_IDENTITY.md) and ADR-014.
11. **State management** — Authoritative state uses locking and explicit versions ([ADR-016](../architecture/decisions/ADR-016-transition-locking-and-state-versioning.md)).
12. **Single responsibility** — One module, one institutional job.
13. **No circular dependencies** — Break cycles via packages or explicit interfaces—not import tricks.

PostgreSQL is the system of record ([ADR-002](../architecture/decisions/ADR-002-postgresql-system-of-record.md)). Redis is coordination/broker—not institutional truth for modes, health leases, or auth sessions ([ADR-008](../architecture/decisions/ADR-008-postgresql-server-side-sessions.md), [ADR-022](../architecture/decisions/ADR-022-durable-supervisor-lease.md)).

---

## 6. Database rules

Baseline modeling: [ADR-007](../architecture/decisions/ADR-007-foundational-institutional-database-modeling.md).

1. **Alembic** — All schema change via migrations; no silent production DDL.
2. **SQLAlchemy 2.x** — Typed mapped models; keep ORM out of HTTP response types.
3. **UUIDs** — Prefer UUID primary keys for institutional entities.
4. **Timestamps** — Timezone-aware timestamps; record `created_at` / `updated_at` where mutable.
5. **Constraints** — Encode invariants in CHECK/UNIQUE/FK; do not rely on application hope alone.
6. **Indexes** — Index access paths used by institutional queries; document partial unique indexes carefully (predicates must be index-safe).
7. **Transactions** — Mutations that require audit commit in one fail-closed transaction where required by ADR-006 / phase doctrine.
8. **Locking** — Use `FOR UPDATE` / advisory locks for singletons and races ([ADR-016](../architecture/decisions/ADR-016-transition-locking-and-state-versioning.md), [ADR-022](../architecture/decisions/ADR-022-durable-supervisor-lease.md)).
9. **Projection tables** — Derived current state (e.g. health projections) is recomputable from evidence.
10. **History tables** — Append-only; enforce with triggers where institutional.
11. **Append-only evidence** — Heartbeats, audit, mode history, incident lifecycle ([ADR-021](../architecture/decisions/ADR-021-append-only-heartbeats.md)).
12. **Migrations** — Ordered, reversible where practical; validate base→head on PostgreSQL.
13. **Rollback** — Downgrade paths must not silently destroy irreplaceable production evidence without Founder-approved procedure.
14. **Concurrency** — Design for concurrent writers; prove with tests.

---

## 7. API standards

1. **Thin routers** — AuthZ gate + parse + call service + map errors.
2. **Typed schemas** — Pydantic request/response models; stable field names.
3. **Service layer** — Authoritative business rules and RBAC checks live in services.
4. **Stable error codes** — Structured `{code, message}` (or equivalent) for institutional mutations; no raw IntegrityError leakage to clients.
5. **Pagination** — Bounded `limit`/`offset` (or cursor) on list endpoints.
6. **Authentication** — Server-side sessions ([ADR-005](../architecture/decisions/ADR-005-server-side-session-authentication.md), [AUTHENTICATION.md](../architecture/AUTHENTICATION.md)).
7. **RBAC** — `FOUNDER` / `OPERATOR` / `VIEWER`; Founder-critical paths stay Founder-only.
8. **No ORM leakage** — Do not return SQLAlchemy models from routers.
9. **Versioning** — Prefer `/api/v1/...` for institutional HTTP APIs.
10. **OpenAPI quality** — Accurate response models and status codes; no decorative fake endpoints.

---

## 8. Security

1. **Least privilege** — Default deny; grant by role and action.
2. **CSRF** — Required on cookie-authenticated mutating routes.
3. **Session management** — Opaque tokens; hashed at rest; TTL and revocation ([ADR-008](../architecture/decisions/ADR-008-postgresql-server-side-sessions.md)).
4. **RBAC** — Enforce at service layer; route deps are the first gate, not the only gate.
5. **Secret handling** — Never commit secrets; `.env` stays local; redact audit payloads ([ADR-012](../architecture/decisions/ADR-012-secret-detection-version-payloads.md)).
6. **Credential storage** — Argon2id (or current approved hasher) for passwords.
7. **Logging** — No secrets in logs; prefer structured operational detail.
8. **Rate limiting / lockout** — Login abuse controls remain enabled.
9. **Worker authentication** — Workers reuse institutional services; no alternate auth bypass ([ADR-024](../architecture/decisions/ADR-024-arq-health-worker-foundation.md)).
10. **Dependency review** — New dependencies require justification; keep lockfiles honest.

Live trading credentials and exchange integrations remain forbidden until explicitly unlocked by Founder and Feature Registry.

---

## 9. Audit

Doctrine: [ADR-006](../architecture/decisions/ADR-006-fail-closed-audit-policy.md), emergency doctrine [ADR-018](../architecture/decisions/ADR-018-emergency-stop-audit-doctrine.md).

1. **Fail closed** — If required audit cannot persist, abort the mutation.
2. **Audit boundaries** — Important mutations (mode, config/policy activation, authz denial on protected paths, health protective actions, incidents) must be auditable.
3. **Transactional audit** — Critical paths audit in the same transaction as the mutation where doctrine requires.
4. **Event naming** — Dotted namespaces (`operating_mode.*`, `health.*`, `incident.*`, `authz.denied`).
5. **Immutability** — Audit events are append-oriented evidence.
6. **History preservation** — Do not delete or rewrite institutional history to “fix” demos.

SYSTEM actors (e.g. health supervisor SAFE_MODE) use `actor_user_id=null` with explicit payload `actor: "SYSTEM"` ([ADR-023](../architecture/decisions/ADR-023-system-actor-safe-mode.md)).

---

## 10. Testing

Mandatory coverage for institutional changes:

| Class | Expectation |
| --- | --- |
| Unit | Domain rules and pure helpers |
| Integration | Services against real PostgreSQL |
| PostgreSQL | Constraints, triggers, projections |
| Concurrency | Races on locks/idempotency/activation |
| Migration | `base` → `head` (and relevant backfills) |
| API | AuthN/AuthZ, CSRF, stable error codes |
| Security | RBAC denial, secret redaction paths |
| Fault injection | Audit unavailable → fail closed |
| Regression | Prior High/Critical remediations stay green |

**No skipped, hidden, weakened, or reclassified failing tests** merely to obtain a green result—without explicit Founder approval.

Run relevant tests after changes (`AGENTS.md`).

---

## 11. Documentation

Required artifacts for material work:

- **ADRs** for major technical decisions
- **CHANGELOG** under `[Unreleased]` / release sections
- **ROADMAP** phase status honesty
- **Feature Registry** status/activation/locks
- **Recovery docs** for new operational subsystems
- **API / architecture docs** matching implementation
- **Release notes** when certifying a release

Documentation that claims unimplemented capability is a governance defect.

---

## 12. Red Team review

Every phase (or material PR set) receives an **independent** review. The reviewer assumes they did not author the code.

Review surfaces:

Architecture · Database · Concurrency · Security · RBAC · API · Operations · Audit · Recovery · Documentation · Testing

Severity:

| Severity | Merge rule |
| --- | --- |
| **Critical** | Must resolve before merge |
| **High** | Must resolve before merge |
| **Medium** | Track; Founder may accept with explicit note |
| **Low** | Track; fix opportunistically |

Do not weaken guarantees to satisfy tests or reviews.

---

## 13. Merge policy

No feature merge unless all are true:

1. Relevant tests pass (including PostgreSQL integration and concurrency where applicable)
2. Documentation matches implementation
3. Audit coverage verified where required
4. Security reviewed
5. Working tree clean
6. Descriptive commit message
7. Red Team review completed
8. **Zero unresolved Critical or High findings**

Missing GitHub CLI does not waive local quality gates; it only changes how PRs are opened.

---

## 14. Release policy

| Stage | Meaning |
| --- | --- |
| **Development** | Feature branch; isolated test state; do not silently initialize shared SystemState for convenience |
| **Review** | Diff review + Red Team + migration validation |
| **Merge** | Into `main` only under §13 |
| **Certification** | Release notes, registry/maturity honesty, recovery procedures checked |
| **Production** | Founder-approved promotion; live trading remains locked until explicitly unlocked |

Do not invent “production ready” claims beyond Feature Registry and maturity evidence.

---

## 15. Engineering ethics

Engineers and agents must **never**:

- fabricate financial or operational results
- hide failures
- disable or skip tests to force green CI
- fake health, maturity, or dashboards
- fake audit trails
- bypass governance or locked features
- modify append-only institutional history
- ignore required documentation
- commit secrets or credentials
- implement leverage, margin, futures, short selling, or withdrawals

---

## 16. Cursor operating directive

Future prompts may simply state:

> Read and obey `docs/governance/ARGUS_ENGINEERING_CONSTITUTION.md` before making any changes.

Cursor (and any coding agent) must then inherit:

- engineering and architecture standards (§2, §5)
- security standards (§8)
- database standards (§6)
- testing standards (§10)
- documentation standards (§11)
- review standards (§12)
- merge standards (§13)
- the Development Covenant (§17)

Phase prompts add **scope and deliverables** only—not a restatement of this Constitution—unless amending it.

---

## 17. Argus Development Covenant

**No feature is complete unless:**

1. Relevant tests pass  
2. Documentation is updated and honest  
3. Required audit coverage exists  
4. Security review is completed  
5. Working tree is clean  
6. The final commit is descriptive  
7. Red Team review is completed  
8. There are **no unresolved Critical or High** findings  

This Covenant applies to every phase from Phase 9 onward and to any remediation of prior phases.

---

## Amendment

Propose amendments as a PR that:

1. Bumps **Version** and **Last updated**
2. States what changed and why
3. Notes impact on ADRs / Feature Registry if any
4. Receives Founder approval before merge

---

*Argus Engineering Constitution v1.0.0 — binding institutional engineering law.*
