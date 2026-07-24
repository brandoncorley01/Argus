# Treasury

Phase 14 treasury and executive-analytics documentation lives primarily in [`docs/architecture/TREASURY.md`](../architecture/TREASURY.md) (full data model, lifecycle, and API surface) and [ADR-030](../architecture/decisions/ADR-030-treasury-simulated-ledger-boundary.md) (the simulated-ledger boundary decision).

## The one-sentence version

Every balance, allocation, KPI, and report produced by this subsystem represents **simulated / internal paper capital only**. No real deposit, withdrawal, or external transfer can ever be executed — the terminal "executed" state does not exist in the `external_transfer_instructions` status enum, and `TreasuryService.attempt_execute_transfer(...)` always raises.

## Where to look

| Need | Document |
| --- | --- |
| Data model, capital lifecycle stages, API surface, EOC | [`docs/architecture/TREASURY.md`](../architecture/TREASURY.md) |
| Why external execution is structurally forbidden | [ADR-030](../architecture/decisions/ADR-030-treasury-simulated-ledger-boundary.md) |
| Operational recovery / troubleshooting | [`docs/operations/TREASURY_RECOVERY.md`](../operations/TREASURY_RECOVERY.md) |
| Phase 14 review / certification | [`docs/releases/PHASE_14_INDEPENDENT_ENGINEERING_REVIEW.md`](../releases/PHASE_14_INDEPENDENT_ENGINEERING_REVIEW.md), [`docs/releases/PHASE_14_RELEASE_CERTIFICATION.md`](../releases/PHASE_14_RELEASE_CERTIFICATION.md) |
