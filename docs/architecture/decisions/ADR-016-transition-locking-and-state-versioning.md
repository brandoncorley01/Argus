# ADR-016: Transition locking and state versioning

- Status: Accepted
- Date: 2026-07-17
- Deciders: Founder (Phase 7)

## Context

Concurrent mode transitions must not produce contradictory institutional state.

## Decision

1. Acquire `SELECT … FOR UPDATE` on the singleton `system_states` row.
2. Reload with `populate_existing` before evaluating matrix/prerequisites.
3. Increment monotonic `state_version` on each committed transition.
4. Optional client `expected_state_version` rejects stale writers (`stale_state`).

### Upgrade backfill (Phase 7 remediation)

When adding `previous_state_version` / `new_state_version`, existing history is renumbered by stable order `(changed_at ASC, id ASC)`:

- row N receives `previous_state_version = N-1`, `new_state_version = N` (1-based)
- `system_states.state_version` is set to `MAX(new_state_version)` (or `0` if empty)
- `current_mode` is never rewritten
- migration fails closed if history tip `to_mode` disagrees with `current_mode`

## Consequences

- Competing transitions serialize on the singleton lock.
- History records previous/new state versions for forensic reconstruction.
- Locking details are not exposed in API responses.
- Pre-Phase-7 history retains distinct monotonic version identity after upgrade.
