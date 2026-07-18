# ADR-019: Mode availability and prerequisite honesty

- Status: Accepted
- Date: 2026-07-17
- Deciders: Founder (Phase 7 defaults D2–D3)

## Context

All seven modes exist in the enum, but paper/live execution is not implemented. Availability must not be implied by enum membership.

## Decision

1. Centralize readiness in `ModePrerequisiteEvaluator`.
2. Mark `PAPER` / `MICRO_LIVE` / `NORMAL_LIVE` unavailable with stable codes (`mode_unavailable`, `execution_capability_not_implemented`).
3. Allow OFF / OBSERVE / SAFE_MODE / EMERGENCY_STOP without requiring an active operating policy.
4. Keep SAFE_MODE → OBSERVE as minimal Founder+reason recovery in Phase 7; deeper health checks belong to Phase 8.
5. Transition discovery must separate structural matrix edges from currently enterable targets.

## Consequences

- Availability APIs report definitive Phase 7 limits honestly.
- `/operating-mode/transitions` may list structural PAPER/live edges as defined-but-not-enterable.
- Future phases can relax prerequisites without inventing readiness today.
- Feature registry locks reinforce unavailable live modes when rows exist.
