# ARGUS Project Status — Engineering Execution Plan

| Field | Value |
| --- | --- |
| **Role** | Principal Software Architect / Technical Program Manager |
| **As of** | 2026-07-21 |
| **Commit inspected** | `8d0fd715a05dead9b1e36b573630d7a285c2b384` |
| **Branch** | `phase-14-treasury-executive-analytics` |
| **Source of truth** | Implementation (code, migrations, tests) — docs cross-checked and flagged where stale |
| **Scope of this document** | Assessment and plan only — **no implementation in this run** |
| **Release target for critical path** | Production-ready **controlled paper trading** (live trading explicitly out of scope) |

---

## 1. Executive summary

Argus Phases **0–14 are implemented on a stacked feature branch**, with phase certifications claiming **180 API tests passed** at Phase 14 tip. The product is a coherent institutional **control plane + paper trading institution** with Strategy Lab, Market Intelligence (observation), Micro-Live architecture (**deny-by-default / not active**), and simulated Treasury analytics.

**It is not yet a finished v1.0 paper release candidate** because:

1. Phases 8–14 are **not merged to `main`**
2. **Phase 15 (Hardening & CI) is absent** — no `.github/` workflows
3. **v1.0 RC validation report was never completed** (`ARGUS_V1_RELEASE_CANDIDATE_VALIDATION.md` missing; only untracked `rc_*` evidence fragments exist)
4. **EOC has no automated tests**; root `README.md` is stale vs implementation
5. **No backup/restore automation**; recovery is documentation-only
6. Paper provider simulation remains **process-local memory synced to Postgres** (known Medium residual)

**Overall completion (paper-trading product, not live):** **~83%**

**Estimated remaining to controlled paper release:** **32–48 engineering hours** (~**4–7 calendar days** with focused Founder-authorized batches)

**Largest blockers:** unmerged stack, missing CI/RC certification evidence, incomplete operational hardening (backup), stale operator docs.

**Do not start live trading, brokerage adapters beyond current stubs, or Phase 15 feature expansion until paper RC gates pass.**

---

## 2. Repository assessment (implementation truth)

### 2.1 Completed (Done in code)

| Area | Evidence |
| --- | --- |
| Governance / ADRs | ADRs 001–030; Constitution + Phase/Review/Certification frameworks |
| Infra | Compose Postgres 16 + Redis 7; operator `.ps1`/`.sh` scripts |
| API control plane | FastAPI routers: auth, audit, config/policy, operating-mode, health supervisor, workers, incidents, market, strategies, paper, micro-live, treasury |
| Schema | 11 Alembic revisions; HEAD `a3b4c5d6e7f8` |
| Auth / RBAC / CSRF / sessions | Implemented + tests |
| Health supervisor worker | Real ARQ worker under `workers/health_supervisor/` |
| EOC | 22 routes; 14 SideNav entries including paper, micro-live, treasury |
| Strategy Laboratory | Engine + registry + APIs + EOC |
| Paper Trading | Gateway + `internal_paper` default + APIs + EOC |
| Micro-Live architecture | Activation SM, secrets refs, kill switches, adapters scaffolds — **live path structurally blocked** |
| Treasury / analytics | Simulated ledgers; external transfer execute forbidden at DB/API |
| Phase release evidence | Phase 11–14 IER + certification docs under `docs/releases/` |

### 2.2 Partially completed

| Area | Gap |
| --- | --- |
| Market Intelligence | Observation-only; limited providers; no rich pipeline maturity |
| Risk engine | Portfolio risk limits + paper kill switch + Phase 13 scoped switches exist; **not all RC checklist controls proven end-to-end** across every scope |
| Paper order lifecycle | Happy path + reject short + idempotency + risk block tested; **replace/expire/stale-data/provider-unavailable matrix incomplete** |
| Reconciliation | Fixture/injected discrepancy paths; not multi-process provider drift |
| Operating mode `PAPER` | Paper **APIs work** without entering global `OperatingMode.PAPER` (still prerequisite-blocked with other risk-increasing modes) — intentional dual-track, but operator-confusing |
| Feature registry honesty | Doc still marks `feat.api.fastapi` as `scaffolded` / “health/ready only” — **stale vs full API surface** |
| RC validation | Harness script + `rc_*.txt` untracked; no durable certified report |

### 2.3 Placeholders / scaffolds (honest, not bugs)

| Item | State |
| --- | --- |
| Coinbase / Kraken / IBKR adapters | Disabled scaffolds; contract/mock only; **not live-certified** |
| `packages/` | Empty by design |
| Live activation `MICRO_LIVE_ACTIVE` | Enum exists; **no reachable activation path** |
| External treasury transfer execute | Always forbidden |
| Root `tests/` | README only; real tests live in `apps/api/tests` |

### 2.4 Unfinished for paper release (not product features)

- Merge / release branch discipline vs `main`
- CI (lint, typecheck, pytest, EOC build)
- Completed `ARGUS_V1_RELEASE_CANDIDATE_VALIDATION.md`
- Backup/restore procedure that is executable (scripted `pg_dump`/`restore`)
- README / CONTRIBUTING / FEATURE_GOVERNANCE honesty sync
- Commit or discard untracked `rc_*` artifacts
- Optional: thin EOC smoke tests; paper provider DB-authoritative store for multi-process

### 2.5 Duplication / technical debt

| Debt | Impact |
| --- | --- |
| Large `models/__init__.py` + domain modules | Import surface sprawl; maintenance cost |
| Dual mode systems (global `OperatingMode` vs `live_activation_state`) | Cognitive load; docs must be crystal clear |
| Process-local paper account store | Incorrect under multi-worker API replicas |
| Repeated TestClient bootstrap patterns across 21 test modules | Slow tests (~2 min full suite historically); harder to extend |
| Stacked unmerged phases 8–14 | Integration risk vs `main`; review burden |
| Untracked RC debris | Noise; risk of lost evidence |

### 2.6 Architectural bottlenecks

1. **Monolithic agent prompts** for multi-phase work — context overflow / long wall-clock
2. **Full pytest ~2 minutes** locally without parallelization/sharding
3. **EOC ↔ API BFF** requires both processes for UI validation — no contract test layer
4. **No CI gate** — regressions only caught manually
5. **Paper sim in-process** — limits horizontal scale and restart fidelity

### 2.7 Tests / build

| Surface | Status |
| --- | --- |
| API pytest | ~158 `test_*` functions / 21 modules; Phase 14 cert: **180 passed** |
| API ruff/mypy | Historically clean at phase tips (re-verify in Batch 1) |
| EOC typecheck/build/lint | Scripts exist; historically green; **no unit tests** |
| Worker tests | Covered via API health-supervisor tests; no separate worker suite |
| CI | **Unavailable** (Phase 15) |
| Failing tests at HEAD | **Not re-executed in this assessment run** — treat last cert as evidence with **re-verify required** before certification |
| Skipped tests | No systematic skip inventory claimed; report honestly after next full run |

### 2.8 Documentation gaps

| Doc | Issue |
| --- | --- |
| Root `README.md` | Claims workers/tests “not scaffolded”; product scope “baseline only” — **false vs Phases 8–14** |
| `FEATURE_GOVERNANCE.md` | `feat.api.fastapi` still `scaffolded` |
| Backup | Framework expects posture; **no scripts** |
| v1 RC report | **Missing** |
| Phase 8–10 formal IER/cert files | Not present in `docs/releases/` (work predated framework formalization) |

### 2.9 Migration / dependencies

- Alembic HEAD: **`a3b4c5d6e7f8`** (linear chain intact)
- Runtime deps: managed via `apps/api` uv lock + `apps/eoc` pnpm
- No live/broker credentials in `.env.example` (correct)
- Dependency vulnerability scan: **not automated** (Phase 15)

### 2.10 Security posture (paper release relevant)

- Sessions, CSRF, RBAC, audit redaction, secret-in-config rejection: implemented
- Live execution deny-by-default: implemented
- Credential values not stored for paper path: correct
- Rate limiting / formal dependency CVE gate: **incomplete**

---

## 3. Completion estimates

Weighted toward **controlled paper trading readiness** (not live).

| Domain | % | Notes |
| --- | --- | --- |
| Core Architecture | **92%** | Gateway, modes, audit, health — solid |
| Backend | **88%** | Broad surface; some lifecycle/risk matrix gaps |
| Frontend (EOC) | **78%** | Screens exist; no automated UI tests; polish unknown |
| Paper Trading | **85%** | Default path works; multi-process & full lifecycle residual |
| Strategy Lab | **87%** | Research-complete for v0.1; not live-coupled |
| Market Intelligence | **72%** | Observation sufficient for paper; not deep intel platform |
| Risk Engine | **70%** | Core controls present; RC checklist not fully proven |
| Treasury | **82%** | Simulated by design; enough for paper exec analytics |
| Analytics / Reporting | **78%** | Evidence-backed snapshots; depth limited |
| Documentation | **68%** | Volume high; operator entry docs stale; RC incomplete |
| Testing | **74%** | Strong API; zero EOC; no CI |
| **Overall (paper product)** | **~83%** | |
| Live trading | **~15%** | Architecture only; correctly locked — **exclude from paper critical path** |

### Effort remaining (paper release)

| Estimate | Value |
| --- | --- |
| Engineering hours | **32–48 h** (P50 ~40 h) |
| Calendar days (1 focused stream) | **4–7 days** |
| Calendar days (part-time / large prompts) | **2–3 weeks** (context thrash) |

### Largest blockers

1. Unmerged Phase 8–14 stack vs `main`
2. Missing CI + durable RC certification evidence
3. Stale operator documentation (onboarding risk)
4. No backup/restore executable path
5. Paper provider process-local state (ops risk if scaled)

### Easiest wins

1. Sync README + FEATURE_GOVERNANCE honesty (2–4 h)
2. Commit RC E2E harness; run once; write `ARGUS_V1_RELEASE_CANDIDATE_VALIDATION.md` (6–10 h)
3. Add minimal GitHub Actions: pytest + EOC typecheck/build (4–8 h)
4. Scripted `pg_dump` / restore runbook (3–5 h)
5. Founder merge PR for stacked phases (process, not coding)

### Highest-risk components

1. Paper cash/position consistency under restart / multi-process
2. Dual activation/mode mental models (operator error)
3. Merge conflicts / forgotten migration order when landing on `main`
4. Incomplete order-lifecycle edge cases in production ops
5. Treating Micro-Live UI as “live ready” (must stay labeled disabled)

---

## 4. Critical path — smallest sequence to paper-ready release

Ignore: live brokers, paid data, KYC, withdrawals, SaaS, Phase 13 activation unlocks, nice-to-have analytics.

```text
1. Re-verify green build at HEAD (pytest, ruff, mypy, EOC typecheck/build)
2. Fix only regressions found (in-scope)
3. Stabilize paper path evidence (E2E harness + accounting spot checks)
4. Add CI gate (minimal)
5. Add backup/restore script + one dry-run evidence
6. Sync operator docs (README, env, startup, kill switch, recovery pointers)
7. Produce ARGUS_V1_RELEASE_CANDIDATE_VALIDATION.md
8. Independent Engineering Review (paper channel) → Release Certification
9. Founder merge to main + tag v1.0.0-rc.1 (paper-only)
```

**Exit criteria for paper release:**

- Clean boot: infra + migrate + API `/health` `/ready` + EOC build
- Full API suite green; EOC typecheck/build green
- Deterministic paper E2E: order → fill → position → cash → treasury/attribution labels → audit
- Kill switch blocks paper submit; live path remains forbidden
- Backup/restore preserves institutional tables
- Docs match commands
- Recommendation: **CERTIFIED FOR CONTROLLED PAPER OPERATION** (or conditional with accepted Mediums)

---

## 5. Fast-track plan (batches)

### Batch 1 — Verification gate
| | |
| --- | --- |
| **Time** | 3–5 h |
| **Difficulty** | Low |
| **Dependencies** | Local Docker Postgres/Redis |
| **Work** | `infra-up` → `migrate-up` → full pytest → ruff → mypy → EOC typecheck/build; record results; fix only failures |
| **Output** | Pass/fail evidence file committed under `docs/releases/evidence/` or appendix |

### Batch 2 — Paper E2E + risk spot checks
| | |
| --- | --- |
| **Time** | 6–10 h |
| **Difficulty** | Medium |
| **Dependencies** | Batch 1 green |
| **Work** | Land `scripts/rc_e2e_paper_validation.py`; extend only if gaps block certification (idempotency, short reject, kill switch, notional limit); manual accounting case |
| **Output** | Stable E2E script + captured run log |

### Batch 3 — CI minimal (Phase 15 slice A)
| | |
| --- | --- |
| **Time** | 4–8 h |
| **Difficulty** | Medium |
| **Dependencies** | Batch 1 |
| **Work** | `.github/workflows/ci.yml`: API pytest + ruff; EOC typecheck/build; no live secrets |
| **Output** | PR checks on push |

### Batch 4 — Backup / restore
| | |
| --- | --- |
| **Time** | 3–5 h |
| **Difficulty** | Low–Medium |
| **Dependencies** | None |
| **Work** | `scripts/backup-db.ps1` / `.sh` + restore counterpart; one documented dry-run; link from ops docs |
| **Output** | Executable recovery path |

### Batch 5 — Doc honesty + RC report
| | |
| --- | --- |
| **Time** | 4–6 h |
| **Difficulty** | Low |
| **Dependencies** | Batches 1–4 evidence |
| **Work** | Fix README/FEATURE_GOVERNANCE; write `docs/releases/ARGUS_V1_RELEASE_CANDIDATE_VALIDATION.md`; clean or commit `rc_*` intentionally |
| **Output** | Founder-readable RC package |

### Batch 6 — Merge & tag
| | |
| --- | --- |
| **Time** | 2–4 h (+ Founder review time) |
| **Difficulty** | Process |
| **Dependencies** | Batches 1–5 + IER PASS |
| **Work** | Stacked PR(s) or single integration PR to `main`; tag `v1.0.0-rc.1`; CHANGELOG entry |
| **Output** | Releasable paper RC on `main` |

### Optional Batch 7 — Paper hardening (only if Batch 2 finds Mediums that block confidence)
| | |
| --- | --- |
| **Time** | 8–16 h |
| **Difficulty** | Medium–High |
| **Work** | DB-authoritative paper balances; expand order lifecycle tests; thin EOC smoke |
| **Defer if** | Single-process local paper ops accepted with documented residual |

**Total critical path:** Batches 1–6 ≈ **32–48 h**

---

## 6. Performance improvements (reduce future build time)

1. **Stop mega-prompts** — one batch = one PR = one cert note  
2. **Shared pytest fixtures package** — cut bootstrap duplication; faster authoring  
3. **pytest-xdist** (optional) once tests are isolation-safe  
4. **Do not expand Micro-Live/Treasury** until paper RC lands  
5. **Keep adapters mocked** — no network in CI  
6. **Shrink agent scope** — “fix failing tests” beats “validate entire RC matrix”  
7. **Single SoT docs** — README points to one Startup guide; stop duplicating commands  
8. **Defer packages/** until a second consumer exists  
9. **Parallelize only independent batches** (CI vs backup vs docs) after Batch 1  
10. **Discard untracked RC noise** or promote to `docs/releases/evidence/` deliberately

---

## 7. Autonomous execution recommendation

| Option | Description | Fit |
| --- | --- | --- |
| **A — Small focused prompts** | One defect/doc/CI file per chat | Safest; slower calendar |
| **B — One autonomous batch at a time** | Execute Batch N end-to-end, stop, report, Founder ack optional | **Best speed/confidence** |
| **C — Large autonomous implementation** | Multi-batch / multi-phase in one prompt | **Fails on this repo size** — already demonstrated by slow RC validation |

### Final recommendation: **Option B**

Complete Argus **fastest** by authorizing **Batch 1 → Batch 6 sequentially**, each:

- scoped to the batch table above  
- producing git-identifiable commit(s)  
- refusing live trading and new product features  
- stopping for Founder only on merge/tag (Batch 6) or blocking Critical/High defects  

Avoid Option C until after paper RC is tagged.

---

## 8. Remaining task backlog (paper release)

| ID | Task | Priority |
| --- | --- | --- |
| T1 | Re-run full verification suite at HEAD | P0 |
| T2 | Fix any regressions from T1 | P0 |
| T3 | Commit E2E paper harness + evidence | P0 |
| T4 | Minimal CI workflow | P0 |
| T5 | Backup/restore scripts + dry-run | P1 |
| T6 | README / feature registry honesty | P1 |
| T7 | Write `ARGUS_V1_RELEASE_CANDIDATE_VALIDATION.md` | P0 |
| T8 | Independent review + release cert (paper channel) | P0 |
| T9 | Merge stack to `main` + tag RC | P0 |
| T10 | Optional: paper multi-process store | P2 |
| T11 | Optional: EOC smoke tests | P2 |
| — | Live trading unlock | **Out of scope** |
| — | Broker account / KYC / paid APIs | **Out of scope** |

---

## 9. Recommendations

1. **Freeze product scope** at paper trading + existing research/treasury surfaces until RC tag.  
2. **Treat Micro-Live UI as architecture status**, not capability.  
3. **Authorize Batch 1 immediately** — without a fresh green suite, estimates are provisional.  
4. **Prefer merge of Phases 8–14 as one integration train** with identifiable commits retained.  
5. **Do not reopen Phases 11–14 feature lists** unless Batch 1–2 finds Critical/High defects.  
6. **Calendar estimate assumes** Founder can approve merge within 24–48 h of Batch 6 readiness.

---

## 10. Final recommendation

| Question | Answer |
| --- | --- |
| Is Argus feature-complete for Phases 0–14? | **Yes, on the phase-14 branch tip** (with known Medium residuals) |
| Is Argus ready to declare v1.0 paper RC today? | **No — missing CI, durable RC validation report, merge, backup automation, doc sync** |
| Overall completion | **~83%** toward controlled paper release |
| Hours remaining | **32–48** |
| Calendar days | **4–7** focused |
| Fastest execution mode | **Option B — one autonomous batch at a time** |
| Next action | **Founder authorizes Batch 1 (Verification gate) only** |

**Certification stance (preview, not a formal cert):**  
Not yet certifiable. After Batches 1–6 with Critical=0 / High=0, target recommendation:

> **CERTIFIED FOR CONTROLLED PAPER OPERATION**  
> Live trading: **NOT CERTIFIED** (and not requested)

---

*Generated from repository inspection at `8d0fd71`. No code was implemented in this run.*
