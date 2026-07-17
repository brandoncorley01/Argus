# Operating Mode State Machine

Phase 7 control plane for Argus institutional operating modes.

## Purpose

The state machine is the authoritative control mechanism for the institution’s permitted level of operational activity. It does **not** implement trading, market data, paper simulation, credentials, workers, or the Executive Operations Center.

## Authoritative state

- One singleton `system_states` row (`singleton_key='current'`) is the source of truth.
- `operating_mode_history` is append-only evidence (DB trigger blocks UPDATE/DELETE).
- `operating_mode_idempotency` stores durable idempotency results.
- See ADR-015 through ADR-019.

## Modes

| Mode | Phase 7 enterable? | Notes |
| --- | --- | --- |
| `OFF` | Yes | Intentional inactive / shutdown |
| `OBSERVE` | Yes | Read-only observation posture; no execution |
| `PAPER` | No | Defined; blocked (`mode_unavailable`) |
| `MICRO_LIVE` | No | Defined; locked / unavailable |
| `NORMAL_LIVE` | No | Defined; locked / unavailable |
| `SAFE_MODE` | Yes | Protective degraded state |
| `EMERGENCY_STOP` | Yes | Highest-priority protective override |

## Transition matrix

Edges are defined in `apps/api/app/services/mode_transitions.py`.

Notable rules:

- `EMERGENCY_STOP` → `OFF` only (Founder recovery).
- No direct emergency exit into `PAPER` / `MICRO_LIVE` / `NORMAL_LIVE`.
- Risk-increasing modes remain on the matrix for future phases but fail prerequisites in Phase 7.

## Transition discovery

`GET /api/v1/operating-mode/transitions` returns:

- `structural_targets` — matrix edges from the current mode (may include future PAPER/live edges)
- `enterable_targets` — subset that currently passes prerequisites (never includes PAPER / MICRO_LIVE / NORMAL_LIVE in Phase 7)
- `targets[]` — per-mode `structurally_allowed`, `enterable`, and `blocking_codes`

Clients must not treat structural edges as permission to enter unavailable modes.

## Authorization

| Role | Capabilities |
| --- | --- |
| FOUNDER | Initialize; all allowed matrix edges that pass prerequisites; emergency enter; emergency recover to OFF; enter OBSERVE |
| OPERATOR | HTTP `/transition` allowed only for targets service permits (`OFF` / `SAFE_MODE`); no emergency enter/exit; no OBSERVE/PAPER/live |
| VIEWER | Read-only |

Route layer: `/transition` requires Founder or Operator (CSRF); emergency/recover/initialize require Founder. Service `_require` remains authoritative for target-specific rules.

Defaults D1–D5 (Founder-approved for Phase 7):

1. OPERATOR may **not** enter `EMERGENCY_STOP`.
2. Protective / OBSERVE / OFF allowed without active operating policy; risk-increasing modes still blocked.
3. `SAFE_MODE` → `OBSERVE` is minimal recovery (Founder + reason); deeper health checks deferred to Phase 8.
4. Extend existing `SystemState` singleton.
5. Append-only history immutability trigger.

## Prerequisites and availability

`ModePrerequisiteEvaluator` centralizes readiness. Phase 7 implements only foundations that already exist:

- Transition matrix membership
- Hard-blocked risk-increasing modes (`PAPER` / `MICRO_LIVE` / `NORMAL_LIVE`) with stable `mode_unavailable`
- Feature registry locks for `feat.mode.micro_live`, `feat.mode.normal_live`, and `feat.trading.live` when rows exist (reinforcement; absence is treated as unavailable, not ready)
- Active operating policy integrity checks for risk-increasing modes (additional blocker when a tampered ACTIVE operating policy exists)

`GET /api/v1/operating-mode/availability` reports honest enterability and blocking codes. It does not fabricate future readiness.

## Policy integration

When an ACTIVE `PolicyKind.OPERATING` version exists and its payload hash verifies, its id is recorded on history and (when present) on `SystemState.active_policy_version_id`. Missing or hash-invalid policy does **not** block OFF / OBSERVE / SAFE_MODE / EMERGENCY_STOP. Invalid policy contributes `policy_integrity_failed` for risk-increasing attempts (which are already unavailable).

## Idempotency

Mutating endpoints require header `Idempotency-Key`.

- Same key + same fingerprint → original result (`idempotent_replay`)
- Same key + different payload → `409` `idempotency_conflict`
- Fingerprint covers operation, target mode, reason, incident id, expected state version
- Keys are stored as SHA-256 hashes only

## Concurrency and versioning

Transitions:

1. Authorize
2. `SELECT … FOR UPDATE` on the singleton row
3. Reload with `populate_existing`
4. Re-check idempotency / matrix / prerequisites
5. Append history, bump `state_version`, write audit, persist idempotency, commit

Optional `expected_state_version` rejects stale writers with `stale_state`.

Initialization uses `pg_advisory_xact_lock(hashtext('argus.operating_mode.singleton'))` so concurrent Founder initialize calls serialize to exactly one history row and one `operating_mode.initialized` audit.

## Emergency doctrine

- Founder may enter `EMERGENCY_STOP` from any non-emergency mode without ordinary capability prerequisites.
- Entry remains authenticated, authorized, transactional, and fail-closed on audit failure.
- **Tradeoff:** if audit persistence is unavailable, emergency entry is refused. Availability is sacrificed to preserve institutional evidence integrity (ADR-018). There is no silent bypass and no unauthenticated kill switch.
- Recovery: Founder-only `POST …/emergency-stop/recover` → `OFF`, clearing `emergency_stop_active` and `recovery_required`.

## API

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/v1/operating-mode` | Current state |
| POST | `/api/v1/operating-mode/initialize` | Founder; idempotent OFF bootstrap |
| GET | `/api/v1/operating-mode/history` | Paginated history |
| GET | `/api/v1/operating-mode/availability` | Mode enterability matrix |
| GET | `/api/v1/operating-mode/transitions` | Allowed targets from current mode |
| POST | `/api/v1/operating-mode/transition` | CSRF + Idempotency-Key |
| POST | `/api/v1/operating-mode/emergency-stop` | Founder |
| POST | `/api/v1/operating-mode/emergency-stop/recover` | Founder |

Stable error codes include: `invalid_transition`, `prerequisite_failed`, `stale_state`, `idempotency_conflict`, `institutional_state_missing`, `audit_unavailable`, `recovery_requirements_not_met`.

## Audit events

Critical mutations fail closed if audit write fails:

- `operating_mode.initialized`
- `operating_mode.transition_succeeded`
- `operating_mode.safe_mode_entered`
- `operating_mode.emergency_stop_entered`
- `operating_mode.emergency_stop_cleared`

Additional observational events (best-effort where noted in service):

- `operating_mode.idempotent_replay`
- `operating_mode.idempotency_conflict`
- `operating_mode.prerequisite_failed`
- `authz.denied`

## Recovery procedures (manual)

Do **not** implement unaudited repair endpoints.

| Condition | Guidance |
| --- | --- |
| Missing `SystemState` | Founder calls `/initialize` after confirming no silent corruption; if corruption suspected, snapshot DB first |
| Audit outage | Transitions refuse to commit; restore audit path, then retry |
| Stuck `SAFE_MODE` | Founder transitions to `OFF` or `OBSERVE` with documented reason |
| `EMERGENCY_STOP` | Founder recover → `OFF`; investigate incident; do not jump to live modes |
| Idempotency conflict | Use a new key for a genuinely new request |
| History/state mismatch | Snapshot, Founder-authorized SQL repair under change control, verify counts/versions, write incident + audit after restoration |

## Phase 7 limitations

- No paper/live execution capability
- No health-supervisor automatic degrade (Phase 8)
- No EOC UI
- Minimal SAFE→OBSERVE recovery checks only
