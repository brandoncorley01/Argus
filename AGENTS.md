# Argus

Argus is a private institutional crypto research and paper-trading system.

## Engineering authority

Before implementing features (Phase 9+), read and obey:

- [`docs/governance/ARGUS_ENGINEERING_CONSTITUTION.md`](docs/governance/ARGUS_ENGINEERING_CONSTITUTION.md) — engineering standards  
- [`docs/governance/ARGUS_PHASE_EXECUTION_FRAMEWORK.md`](docs/governance/ARGUS_PHASE_EXECUTION_FRAMEWORK.md) — how phases are executed  
- [`docs/governance/ARGUS_INDEPENDENT_ENGINEERING_REVIEW_FRAMEWORK.md`](docs/governance/ARGUS_INDEPENDENT_ENGINEERING_REVIEW_FRAMEWORK.md) — independent review / Red Team certification  
- [`docs/governance/ARGUS_RELEASE_CERTIFICATION_FRAMEWORK.md`](docs/governance/ARGUS_RELEASE_CERTIFICATION_FRAMEWORK.md) — when a release is institutionally ready  

## Permanent rules

- Capital preservation comes before profit.
- Live trading must remain disabled until explicitly implemented and approved.
- Do not add leverage, margin, futures, short selling, or withdrawal functionality.
- Every important action must be auditable.
- Risk controls may never be bypassed.
- Important configuration must be versioned.
- Use modular architecture and strict separation of responsibilities.
- Do not fabricate financial data.
- Do not claim that a strategy is profitable without validation evidence.
- Prefer safe failure over continuing with uncertain system state.
- Never expose secrets or commit credentials.
- Run relevant tests after making changes.
- Explain significant architectural deviations before implementing them.
- **Bump Build live monitor on every product-behavior delivery** (see Cloud agent delivery proof below).

## Cloud agent delivery proof (mandatory)

Every completed cloud-agent job that changes Argus product behavior **must** bump the **Build live monitor** stamp so the Founder can verify the work landed.

**Required on each such job (before claiming done):**

1. Increment `live-monitor-vX.Y` (patch +1 unless a larger bump is justified).
2. Update **both**:
   - `apps/eoc/public/argus-build.txt`
   - `apps/eoc/src/lib/build.ts` (`ARGUS_UI_BUILD`)
3. Record the same stamp in `CHANGELOG.md` for the change.
4. Commit + push; merge (or leave a ready PR) only when that stamp is on the delivered branch.
5. In the final summary, state the new Build live monitor version explicitly.

**Failure to bump the stamp = job incomplete.** Docs-only or pure chore commits that do not change runtime behavior may skip the stamp; product, trading, worker, API, or UI behavior changes may not.
