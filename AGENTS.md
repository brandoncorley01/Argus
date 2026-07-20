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
