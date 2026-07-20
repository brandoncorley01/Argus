# Argus Release Certification Framework

| Field | Value |
| --- | --- |
| **Title** | Argus Release Certification Framework |
| **Version** | `1.0.0` |
| **Status** | Binding |
| **Authority** | Founder |
| **Last updated** | `2026-07-19` |
| **Applies to** | Phase completions, minor/major releases, RCs, production, hotfixes, emergency patches, future SaaS releases |

## Purpose

This Framework defines **when** Argus software is considered ready for release.

It does **not** define how software is built ([Phase Execution Framework](ARGUS_PHASE_EXECUTION_FRAMEWORK.md)) or how it is independently reviewed ([Independent Engineering Review Framework](ARGUS_INDEPENDENT_ENGINEERING_REVIEW_FRAMEWORK.md)). Engineering standards remain in the [Engineering Constitution](ARGUS_ENGINEERING_CONSTITUTION.md).

**A release is an institutional decision—not a Git operation.**

Mission:

> Ensure Argus is released only when **institutional confidence exceeds implementation enthusiasm**.

Future prompts may simply state:

> Prepare the release according to `docs/governance/ARGUS_RELEASE_CERTIFICATION_FRAMEWORK.md`.

## Authority

1. This Framework binds Founder, operators, and agents preparing Argus releases.  
2. Constitution merge policy and Development Covenant still apply ([Constitution §13, §17](ARGUS_ENGINEERING_CONSTITUTION.md)).  
3. Independent review must be **PASS** or **PASS WITH MEDIUM** before certification ([Review Framework §9](ARGUS_INDEPENDENT_ENGINEERING_REVIEW_FRAMEWORK.md)).  
4. `AGENTS.md`, Feature Registry locks, and Accepted ADRs are not waived by tagging a version.  
5. Amendments require Founder approval and a version bump of this document.

## Relationship to other documents

| Document | Role |
| --- | --- |
| [Engineering Constitution](ARGUS_ENGINEERING_CONSTITUTION.md) | Standards that a certified release must satisfy |
| [Phase Execution Framework](ARGUS_PHASE_EXECUTION_FRAMEWORK.md) | Lifecycle ending in certification / merge / release notes |
| [Independent Engineering Review Framework](ARGUS_INDEPENDENT_ENGINEERING_REVIEW_FRAMEWORK.md) | Independent QA gate before certification |
| [`ROADMAP.md`](../../ROADMAP.md) | Phase / milestone status |
| [`CHANGELOG.md`](../../CHANGELOG.md) | Release history |
| [Feature Governance](FEATURE_GOVERNANCE.md) | Capability honesty at release |
| [Institutional Maturity Model](INSTITUTIONAL_MATURITY_MODEL.md) | Maturity claims must not outrun evidence |
| [`docs/releases/`](../releases/) | Durable release / migration notes |

**Do not duplicate those documents.** Cite them.

## Table of contents

1. [Certification levels](#1-certification-levels)
2. [Release readiness](#2-release-readiness)
3. [Required evidence](#3-required-evidence)
4. [Quality gates](#4-quality-gates)
5. [Release checklist](#5-release-checklist)
6. [Versioning](#6-versioning)
7. [Production requirements](#7-production-requirements)
8. [Rollback](#8-rollback)
9. [Post-release](#9-post-release)
10. [Certification report](#10-certification-report)
11. [Future prompts](#11-future-prompts)

---

## 1. Certification levels

| Level | Meaning |
| --- | --- |
| **Development** | Work in progress on a feature branch; not releasable |
| **Internal Review** | Implementation claimed complete; independent review in progress or pending |
| **Release Candidate** | Tagged/candidate build under certification; may still fail gates |
| **Certified** | Founder-approved institutional release for the stated channel (internal or production-bound) |
| **Production** | Running in the production environment under Founder authority |
| **Hotfix** | Expedited patch to a Certified/Production line; still requires review proportional to risk |
| **Emergency Patch** | Immediate integrity/safety fix; Founder-authorized; post-facto full certification within a defined window |
| **Retired** | Superseded; must not be redeployed except for forensic recovery |

Promotion is **one-way by default**. Downgrades (e.g. Certified → Internal Review) require Founder note when defects are found after tagging.

---

## 2. Release readiness

Before certification, verify readiness across:

| Domain | Verify |
| --- | --- |
| Architecture | ADRs and architecture docs match shipped behavior |
| Database | Schema at intended Alembic head; constraints/triggers intact |
| Migrations | Validated path; notes for operators |
| API | Versioned surfaces stable; OpenAPI honest |
| Authentication | Sessions / CSRF / lockout posture intact |
| RBAC | Roles enforced; locked features remain locked |
| Audit | Fail-closed paths present where required |
| Security | No unresolved Critical/High from independent review |
| Recovery | Runbooks exist for new operational surfaces |
| Documentation | ROADMAP, CHANGELOG, registry, maturity honesty |
| Operational readiness | Compose/infra/worker run paths documented |
| Testing | Constitution §10 suites applicable to the release |
| Performance | No known unbounded failure modes left undocumented |
| Observability | Health/ready/supervisor (as applicable) meaningful—not decorative |

---

## 3. Required evidence

Certification packages must include (or link) evidence for:

| Evidence | Notes |
| --- | --- |
| **pytest** | Full relevant suite green for the release tip |
| **Integration tests** | PostgreSQL-backed tests when persistence changed |
| **Migration validation** | `base`→`head` (or documented partial path) when schema changed |
| **Ruff** | Clean for released Python packages |
| **Mypy** | Clean for released typed packages (API `app`) |
| **Docker / infra validation** | Required services healthy when release depends on them |
| **Startup validation** | API (and workers if in scope) start fail-closed with valid settings |
| **API documentation** | Matches shipped routes and auth |
| **Health verification** | `/health`, `/ready`, and Phase 8 health APIs as applicable—honest status only |

Missing mandatory evidence ⇒ certification **denied**.

---

## 4. Quality gates

| Gate | Name | Exit criteria |
| --- | --- | --- |
| **1** | Implementation complete | Deliverables for the milestone present; out-of-scope respected |
| **2** | Documentation complete | Checklist §5 docs items satisfied |
| **3** | Independent review passed | Review Framework: Critical=0, High=0 (`PASS` or `PASS WITH MEDIUM`) |
| **4** | Certification evidence complete | §3 evidence attached or reproducibly cited |
| **5** | Founder approval | Explicit institutional approval to certify / promote |
| **6** | Release | Tag / channel promotion / deploy under Founder authority |

Gates are sequential. Do not declare “released” after Gate 1–2 alone.

---

## 5. Release checklist

Confirm before Founder approval (Gate 5):

- [ ] Working tree clean on the release tip  
- [ ] Commits descriptive; no secret material  
- [ ] Migration head matches intended revision  
- [ ] Configuration integrity (no committed secrets; `.env.example` current)  
- [ ] Policy / versioning integrity where touched  
- [ ] Feature Registry accurate for shipped capabilities  
- [ ] CHANGELOG updated  
- [ ] ROADMAP status honest  
- [ ] Release notes prepared (`CHANGELOG` and/or `docs/releases/`)  
- [ ] ADRs current for major decisions in the release  
- [ ] Recovery procedures updated when ops surface changed  
- [ ] Independent Engineering Review certification recorded  
- [ ] Maturity claims do not exceed evidence  

---

## 6. Versioning

Argus uses **Semantic Versioning** adapted for institutional releases:

| Component | When to bump |
| --- | --- |
| **MAJOR** | Breaking institutional API/schema/contract changes, or maturity/capability class change that operators must treat as incompatible |
| **MINOR** | Backward-compatible institutional capability (new phase features, additive APIs) |
| **PATCH** | Backward-compatible fixes, hardening, docs-only operator-critical fixes when tagged |
| **Release Candidate** | `X.Y.Z-rc.N` — candidate under certification; not Production |
| **Hotfix** | Patch on a Certified line; may use `X.Y.Z+hotfix.N` or next PATCH with release notes stating hotfix |

**Tagging conventions**

- Annotated tags preferred: `v0.1.0`, `v0.1.0-rc.1`, `v0.1.1`  
- Tag only Certified (or Founder-authorized Emergency Patch) tips  
- Tag message cites certification report / PR  
- Do not retag rewritten history on published tags  

Pre-1.0 (`0.y.z`) may still use MINOR for additive foundation phases; honesty in CHANGELOG matters more than marketing version theater.

---

## 7. Production requirements

Minimum before **Production** level:

1. Gates 1–6 complete for the exact commit deployed  
2. Independent review Critical/High = 0  
3. Feature Registry: no live trading / leverage / withdrawals activated without Founder unlock  
4. Secrets managed outside git; production session cookie security appropriate  
5. PostgreSQL migrations applied to intended head; backup/restore posture understood  
6. Recovery docs reachable for health, auth, mode, and any new subsystems  
7. Monitoring/health checks meaningful; no decorative “green”  
8. Rollback plan known (§8)  
9. Founder explicit production approval  

Local/dev demonstration environments are **not** Production merely because migrations applied.

---

## 8. Rollback

**Doctrine:** Prefer safe failure and reversible promotion over forward-fix panic.

1. **Application rollback** — Redeploy prior Certified tag when code is the fault.  
2. **Schema rollback** — Prefer expand/contract migrations; irreversible migrations require Founder-approved forward fix, not silent history rewrite.  
3. **Config/policy rollback** — Use versioned activation (supersede), not DB surgery on immutable payloads.  
4. **Mode/safety** — Protective modes (`SAFE_MODE`, `EMERGENCY_STOP`) are operational controls, not substitutes for bad releases—but may be used while rolling back.  
5. **Evidence** — Do not delete audit/history to “undo” a release.  
6. **Communication** — Record rollback in CHANGELOG / release notes with cause and prior version.

Emergency Patches still require post-facto certification evidence within the Founder-defined window.

---

## 9. Post-release

After Production (or Certified channel) promotion:

| Activity | Action |
| --- | --- |
| **Verification** | Confirm health/ready, auth, critical reads/mutates, migration version |
| **Monitoring** | Watch error rates, supervisor/lease (if applicable), DB/Redis health |
| **Known issues** | Publish Medium/Low residuals and accepted risks |
| **Future roadmap** | Update ROADMAP; do not start next phase branch until merge/certification is real |
| **Registry / maturity** | Reaffirm locks; advance maturity only with evidence |

---

## 10. Certification report

Standard report:

```text
# Release Certification — <version or milestone>

## Executive Summary
- Artifact / commit / tag
- Channel (RC / Certified / Production / Hotfix / Emergency Patch)
- Overall decision

## Evidence
- Tests, ruff, mypy, migrations, Docker/startup, health, review link

## Remaining Risks
- Medium/Low / accepted residuals

## Certification Decision
- CERTIFIED | NOT CERTIFIED | CERTIFIED WITH ACCEPTED MEDIUM

## Version
- SemVer + tag name

## Release Recommendation
- Promote / Hold / Rollback prior

## Approvals
- Independent review result
- Founder approval
```

Retain reports in PR, `docs/releases/`, or both.

---

## 11. Future prompts

Release preparation prompts need not redefine gates. Use:

```text
Read and obey:
- docs/governance/ARGUS_ENGINEERING_CONSTITUTION.md
- docs/governance/ARGUS_PHASE_EXECUTION_FRAMEWORK.md
- docs/governance/ARGUS_INDEPENDENT_ENGINEERING_REVIEW_FRAMEWORK.md
- docs/governance/ARGUS_RELEASE_CERTIFICATION_FRAMEWORK.md

Prepare the release according to ARGUS_RELEASE_CERTIFICATION_FRAMEWORK.md.

Milestone / version: <...>
Channel: <RC | Certified | Production | Hotfix | Emergency Patch>
Commit / branch: <...>
```

---

## Amendment

Propose amendments as a PR that bumps **Version** and **Last updated**, states rationale, and receives Founder approval.

---

*Argus Release Certification Framework v1.0.0 — binding institutional release gate.*
