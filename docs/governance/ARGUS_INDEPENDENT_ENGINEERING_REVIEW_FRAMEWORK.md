# Argus Independent Engineering Review Framework

| Field | Value |
| --- | --- |
| **Title** | Argus Independent Engineering Review Framework |
| **Version** | `1.0.0` |
| **Status** | Binding |
| **Authority** | Founder |
| **Last updated** | `2026-07-19` |
| **Applies to** | Every implementation phase, material PR, and production-bound release from Phase 9 onward |

## Purpose

This Framework institutionalizes **independent software quality assurance** for Argus.

The reviewer must behave as if they:

- did **not** author the implementation  
- are responsible for **approving or rejecting** the merge  
- have authority to **block production**  

The review exists to **discover defects**—not to justify the implementation.

Every future phase should conclude with:

> Perform an Independent Engineering Review according to `docs/governance/ARGUS_INDEPENDENT_ENGINEERING_REVIEW_FRAMEWORK.md`.

## Authority

1. This Framework binds reviewers, agents, and automation performing Argus reviews.  
2. Engineering standards come from the [Engineering Constitution](ARGUS_ENGINEERING_CONSTITUTION.md) (especially §10–§17).  
3. Phase process comes from the [Phase Execution Framework](ARGUS_PHASE_EXECUTION_FRAMEWORK.md) (especially Gates 4–8).  
4. `AGENTS.md` permanent product/safety rules and Accepted ADRs are not waived by a passing narrative review.  
5. Amendments require Founder approval and a version bump of this document.

## Relationship to other documents

| Document | Role |
| --- | --- |
| [Engineering Constitution](ARGUS_ENGINEERING_CONSTITUTION.md) | Standards the review enforces |
| [Phase Execution Framework](ARGUS_PHASE_EXECUTION_FRAMEWORK.md) | When review occurs in the lifecycle |
| [Release Certification Framework](ARGUS_RELEASE_CERTIFICATION_FRAMEWORK.md) | When certified review evidence feeds a releasable milestone |
| This Framework | *How* independent review is conducted and certified |
| [ADRs](../architecture/decisions/README.md) | Decision correctness vs. implementation |
| Architecture / recovery docs | Operational and design truth to verify against |
| [Feature Governance](FEATURE_GOVERNANCE.md) | Capability honesty |

**Do not restate the Constitution or Phase Framework.** Cite them.

## Table of contents

1. [Mission](#1-mission)
2. [Review principles](#2-review-principles)
3. [Review types](#3-review-types)
4. [Mandatory review checklist](#4-mandatory-review-checklist)
5. [Risk classification](#5-risk-classification)
6. [Merge authority](#6-merge-authority)
7. [Required evidence](#7-required-evidence)
8. [Red Team process](#8-red-team-process)
9. [Certification](#9-certification)
10. [Report format](#10-report-format)
11. [Future prompts](#11-future-prompts)

---

## 1. Mission

Protect Argus from:

- architectural debt  
- security defects  
- operational failures  
- governance violations  
- hidden technical risk  

Capital preservation and institutional honesty outrank schedule pressure.

---

## 2. Review principles

| Principle | Meaning |
| --- | --- |
| **Evidence over opinion** | Cite tests, diffs, migrations, logs, ADRs—not vibes |
| **Assume failure exists** | Start from “what is broken?” not “how do we approve?” |
| **Verify, never trust** | Re-run or inspect evidence; do not accept author claims alone |
| **Review behavior, not intent** | Judge what the system does under failure and concurrency |
| **Reject hidden complexity** | Unexplained cleverness is a finding until proven necessary |
| **Institution first** | Prefer safe, auditable, reversible designs over feature completeness |

Aligns with Constitution §2, §3 ($10M test), §15 (ethics).

---

## 3. Review types

Each material change set is assessed across these lenses (depth scales with risk):

| Type | Focus |
| --- | --- |
| **Architecture** | Boundaries, dependency direction, domain ownership, ADR fidelity |
| **Security** | AuthN/AuthZ, CSRF, secrets, worker privilege, injection, session abuse |
| **Database** | Constraints, indexes, triggers, migrations, immutability |
| **API** | Thin routers, schemas, error codes, versioning, OpenAPI honesty |
| **Concurrency** | Locks, races, idempotency, singleton correctness |
| **Audit** | Fail-closed paths, event naming, transactional integrity |
| **RBAC** | Role gates vs. service enforcement; Founder-only paths |
| **Operations** | Compose/worker startup, health, config, observability |
| **Documentation** | Matches implementation; no fabricated capabilities |
| **Testing** | Coverage of critical paths; no weakened/skipped failures |
| **Recovery** | Runbooks exist and match real failure modes |
| **Performance** | Obvious hotspots, unbounded queries, N+1 institutional reads |
| **Scalability** | Lease/singleton designs, queue backpressure, projection growth |

Not every type needs a novel essay each phase—but each must be **considered**, and silence on a risky area is itself a finding.

---

## 4. Mandatory review checklist

For every phase / production-bound PR, verify:

| Area | Questions |
| --- | --- |
| Architecture | Bounded contexts respected? ADR deviations explained? |
| Service boundaries | Logic in services? No privilege side doors in workers? |
| Dependencies | New deps justified? Locks/registry honest? |
| Database | Models/migrations consistent? |
| Indexes | Correct and safe (including partial unique predicates)? |
| Constraints | Invariants enforced in DB where institutional? |
| Transactions | Critical mutations + audit correctly scoped? |
| Locking | Singletons / activations use durable locks? |
| Concurrency | Tests prove the race story? |
| Migrations | `base`→`head` validated? Backfill safe? |
| Audit | Fail-closed where required? SYSTEM actor explicit? |
| RBAC | VIEWER cannot mutate? Founder paths protected? |
| Authentication | Sessions/CSRF intact? |
| Authorization | Service-layer checks present? |
| Error handling | Stable codes; no raw DB leakage? |
| Recovery | Docs exist for new operational surfaces? |
| Configuration | Versioned where required; no secrets in git? |
| Secrets | Redaction; `.env` discipline? |
| Logging | No credentials in logs? |
| Documentation | ROADMAP / CHANGELOG / registry / architecture updated? |
| Tests | Relevant suite green; Constitution §10? |
| Developer experience | Clear run paths; no tribal-only steps? |
| Future maintainability | Complexity justified by $10M test? |

---

## 5. Risk classification

| Severity | Definition | Examples |
| --- | --- | --- |
| **Critical** | Immediate integrity, security, or capital-risk defect | Auth bypass; audit skipped on emergency path; data loss migration; live trading unlocked without approval |
| **High** | Likely production failure or governance breach under normal ops | Race corrupting singleton state; RBAC hole on mutate; fail-open on audit error; history mutability |
| **Medium** | Real defect or debt; not an immediate merge-stopper if documented | Missing index on hot path; incomplete recovery note; Medium ADR drift with mitigation |
| **Low** | Quality / clarity issue | Naming inconsistency; minor doc gap; non-blocking DX friction |
| **Informational** | Observation, suggestion, or context | Alternate design noted; future scalability remark |

Severity must reflect **institutional impact**, not author embarrassment.

---

## 6. Merge authority

| Severity | Merge impact |
| --- | --- |
| **Critical** | **Merge blocked** until resolved |
| **High** | **Merge blocked** until resolved |
| **Medium** | Merge allowed **only with** explicit documentation of acceptance / follow-up |
| **Low** | Improvement backlog; does not block by default |
| **Informational** | Observation only |

This matches Constitution §12–§13 and Phase Framework Gate 6–8.  
**Do not weaken guarantees to clear a finding.**

---

## 7. Required evidence

The reviewer must verify (or obtain equivalent proof) for the change set:

| Evidence | Expectation |
| --- | --- |
| **Tests** | Relevant pytest (or successor) green |
| **Coverage** | Critical new paths exercised (concurrency/migration/API as applicable)—not vanity % alone |
| **Migration validation** | Clean DB path to current head when schema changed |
| **Docker / infra validation** | Required services healthy when the phase depends on them |
| **Ruff** | Lint clean for touched Python |
| **Mypy** | Strict package check clean for API app code |
| **API startup** | App loads with fail-closed settings when API touched |
| **Recovery procedures** | Present and consistent when new ops surfaces exist |
| **Audit integrity** | Fail-closed and event evidence spot-checked |

Missing evidence ⇒ finding (typically High if the area is institutional).

---

## 8. Red Team process

After checklist review, the reviewer **attempts to break** the change set intentionally:

| Attack surface | Examples |
| --- | --- |
| Security | Session theft patterns, CSRF omission, secret leakage |
| Concurrency | Double-submit, lease steal, activation races |
| RBAC | Privilege escalation via alternate routes/workers |
| Audit | Force audit failure; confirm mutation aborts |
| Database integrity | Illegal updates to append-only tables; constraint bypass |
| Recovery | Simulate dependency death; verify safe failure |
| Operating modes | Illegal transitions; SYSTEM degrade from wrong modes |
| Configuration / policies | Secret-in-payload; activation races |
| Health supervision | Stale sequences; lease contests; fake healthy claims |
| Institutional identity | Unauthorized identity mutation / dishonest registry |

Red Team is adversarial. A “clean” author narrative is not evidence of safety.

---

## 9. Certification

Every review concludes with:

| Field | Content |
| --- | --- |
| **Overall Result** | `PASS` \| `PASS WITH MEDIUM` \| `FAIL` |
| **Critical Count** | integer |
| **High Count** | integer |
| **Medium Count** | integer |
| **Low Count** | integer |
| **Informational Count** | integer (optional) |
| **Certification Decision** | Certify / Do not certify for merge |
| **Recommended Merge** | `yes` \| `no` \| `yes after Medium acceptance notes` |
| **Outstanding Risks** | Residual Medium/Low and accepted risks |

**PASS** requires Critical = 0 and High = 0.  
**PASS WITH MEDIUM** requires Critical = 0, High = 0, and documented Medium acceptance.  
**FAIL** if any Critical or High remains unresolved.

---

## 10. Report format

Standard Independent Engineering Review report:

```text
# Independent Engineering Review — <phase or PR>

## Executive Summary
- Scope reviewed
- Overall Result
- Recommended Merge

## Findings
### Critical
### High
### Medium
### Low
### Informational

(For each finding: ID, area, evidence, impact, recommended fix)

## Risk Matrix
| ID | Severity | Area | Blocks merge? |

## Evidence
- Tests / ruff / mypy / migrations / startup / recovery checks performed

## Recommended Fixes
- Ordered remediation list (Critical/High first)

## Certification
- Counts
- Certification Decision
- Outstanding Risks
- Reviewer stance: independent / non-author assumption affirmed
```

Store durable review outcomes in PR description, release notes, or `docs/releases/` as the Founder prefers—do not invent a green certificate without evidence.

---

## 11. Future prompts

Implementation prompts need not redefine review doctrine. They should simply state:

> Perform an Independent Engineering Review according to `docs/governance/ARGUS_INDEPENDENT_ENGINEERING_REVIEW_FRAMEWORK.md`.

Combined inheritance:

```text
Read and obey:
- docs/governance/ARGUS_ENGINEERING_CONSTITUTION.md
- docs/governance/ARGUS_PHASE_EXECUTION_FRAMEWORK.md

…phase objective / deliverables / acceptance / out-of-scope / dependencies…

At completion:
Perform an Independent Engineering Review according to
docs/governance/ARGUS_INDEPENDENT_ENGINEERING_REVIEW_FRAMEWORK.md.
```

---

## Amendment

Propose amendments as a PR that bumps **Version** and **Last updated**, states rationale, and receives Founder approval.

---

*Argus Independent Engineering Review Framework v1.0.0 — binding independent QA law.*
