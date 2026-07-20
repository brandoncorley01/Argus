/**
 * Typed Argus control-plane API models (Phase 5–8).
 * Mirror backend schemas; frontend never invents institutional state.
 */

export type InstitutionalRole = "FOUNDER" | "OPERATOR" | "VIEWER";

export type OperatingMode =
  | "OFF"
  | "OBSERVE"
  | "PAPER"
  | "MICRO_LIVE"
  | "NORMAL_LIVE"
  | "SAFE_MODE"
  | "EMERGENCY_STOP";

export type HealthStatus = "healthy" | "degraded" | "unhealthy";

export type IncidentSeverity = "low" | "medium" | "high" | "critical";
export type IncidentStatus =
  | "open"
  | "investigating"
  | "mitigated"
  | "closed";

export interface LoginResponse {
  user_id: string;
  username: string;
  roles: InstitutionalRole[];
  csrf_token: string;
  expires_at: string;
}

export interface CurrentUser {
  id: string;
  username: string;
  email: string | null;
  is_active: boolean;
  roles: InstitutionalRole[];
  session_expires_at: string;
}

export interface OperatingModeState {
  current_mode: OperatingMode;
  state_version: number;
  reason: string | null;
  emergency_stop_active: boolean;
  recovery_required: boolean;
  last_history_id: string | null;
  active_policy_version_id: string | null;
  updated_by_user_id: string | null;
  updated_at: string;
}

export interface ModeAvailabilityItem {
  mode: string;
  enterable: boolean;
  required_authority: string;
  blocking_codes: string[];
  required_policy: string | null;
  definitive: boolean;
  notes: string | null;
}

export interface AllowedTransitions {
  current_mode: string;
  state_version: number;
  targets: Array<{
    mode: string;
    structurally_allowed: boolean;
    enterable: boolean;
    blocking_codes: string[];
  }>;
  structural_targets: string[];
  enterable_targets: string[];
}

export interface InstitutionalHealth {
  singleton_key: string;
  status: HealthStatus;
  evaluation_version: number;
  summary: Record<string, unknown>;
  evaluated_at: string;
  updated_at: string;
}

export interface ServiceProjection {
  service_id: string;
  status: HealthStatus;
  last_heartbeat_id: string | null;
  last_sequence_number: number | null;
  last_observed_at: string | null;
  consecutive_failures: number;
  evaluation_version: number;
  detail: string | null;
  updated_at: string;
}

export interface RegisteredService {
  id: string;
  service_key: string;
  display_name: string;
  service_kind: string;
  criticality: string;
  heartbeat_interval_seconds: number;
  heartbeat_timeout_seconds: number;
  expected_instance_count: number;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ServiceWithProjection {
  service: RegisteredService;
  projection: ServiceProjection | null;
}

export interface SupervisorLease {
  singleton_key: string;
  holder_instance_id: string | null;
  lease_epoch: number;
  lease_until: string | null;
  last_cycle_at: string | null;
  last_cycle_result: string | null;
  updated_at: string;
}

export interface WorkerIdentity {
  id: string;
  worker_key: string;
  service_id: string;
  display_name: string;
  description: string | null;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkerInstance {
  id: string;
  worker_identity_id: string;
  instance_key: string;
  hostname: string | null;
  status: string;
  started_at: string;
  last_seen_at: string;
  stopped_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Incident {
  id: string;
  title: string;
  description: string | null;
  severity: IncidentSeverity;
  status: IncidentStatus;
  related_mode: OperatingMode | null;
  source_service_id: string | null;
  correlation_key: string | null;
  opened_by_system: boolean;
  opened_at: string;
  closed_at: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface IncidentLifecycleEvent {
  id: string;
  incident_id: string;
  event_type: string;
  from_status: IncidentStatus | null;
  to_status: IncidentStatus | null;
  from_severity: IncidentSeverity | null;
  to_severity: IncidentSeverity | null;
  actor_user_id: string | null;
  opened_by_system: boolean;
  note: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface ProtectiveAction {
  id: string;
  action_type: string;
  status: string;
  incident_id: string | null;
  source_service_id: string | null;
  rationale: string;
  payload: Record<string, unknown>;
  applied_at: string | null;
  dismissed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditEvent {
  id: string;
  occurred_at: string;
  actor_user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  request_id: string | null;
  mode_at_time: string | null;
  config_version_id: string | null;
  policy_version_id: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditEventList {
  items: AuditEvent[];
  limit: number;
  offset: number;
}

export interface ConfigurationDocument {
  id: string;
  document_key: string;
  name: string;
  description: string | null;
  schema_identifier: string;
  is_retired: boolean;
  draft_authority: string;
  created_at: string;
}

export interface ConfigurationVersion {
  id: string;
  document_id: string;
  version_number: number;
  version_label: string;
  status: string;
  content: Record<string, unknown>;
  payload_hash: string;
  change_summary: string | null;
  previous_version_id: string | null;
  created_at: string;
  submitted_at: string | null;
  approved_at: string | null;
  activated_at: string | null;
  superseded_at: string | null;
  rejected_at: string | null;
  retired_at: string | null;
  rejection_reason: string | null;
}

export interface PolicyDocument {
  id: string;
  document_key: string;
  name: string;
  description: string | null;
  policy_kind: string;
  schema_identifier: string;
  is_retired: boolean;
  draft_authority: string;
  created_at: string;
}

export interface PolicyVersion {
  id: string;
  document_id: string;
  version_number: number;
  version_label: string;
  status: string;
  content: Record<string, unknown>;
  payload_hash: string;
  change_summary: string | null;
  previous_version_id: string | null;
  created_at: string;
  submitted_at: string | null;
  approved_at: string | null;
  activated_at: string | null;
  superseded_at: string | null;
  rejected_at: string | null;
  retired_at: string | null;
  rejection_reason: string | null;
}

export interface ProcessHealth {
  status: string;
  service?: string;
  checks?: Record<string, unknown>;
  [key: string]: unknown;
}

/**
 * Phase 13 — Micro-Live Institution.
 * Deny-by-default: live execution architecture only, no credentials
 * required, no real orders possible. These types never carry secret
 * values — only presence/reference metadata.
 */
export interface MicroLiveStatus {
  live_capable_architecture: boolean;
  credentials_configured: boolean;
  live_execution_active: boolean;
  paper_provider_default: boolean;
  activation_state: string;
  state_version: number;
  global_kill_switch_active: boolean;
  active_capital_policy_version: number | null;
  adapter_count: number;
  enabled_adapter_count: number;
  disclaimer: string;
}

export interface ActivationState {
  activation_state: string;
  state_version: number;
  credentials_configured: boolean;
  live_execution_active: boolean;
  live_capable_architecture: boolean;
  paper_provider_default: boolean;
  updated_at: string;
  evidence: Record<string, unknown>;
}

export interface ActivationTransition {
  id: string;
  from_state: string | null;
  to_state: string;
  previous_state_version: number;
  new_state_version: number;
  reason: string | null;
  evidence: Record<string, unknown>;
  changed_at: string;
}

export interface CredentialReference {
  id: string;
  provider_key: string;
  ref_name: string;
  purpose: string;
  is_present_cached: boolean;
  last_validated_at: string | null;
  created_at: string;
}

export interface KillSwitch {
  id: string;
  scope_type: string;
  scope_id: string | null;
  active: boolean;
  reason: string | null;
  activated_at: string | null;
  cleared_at: string | null;
  created_at: string;
}

export interface MicroCapitalPolicy {
  id: string;
  version: number;
  max_deployable_capital: string;
  max_order_notional: string;
  max_daily_loss: string;
  max_concurrent_exposure: string;
  max_provider_exposure: string;
  max_strategy_exposure: string;
  is_active: boolean;
  created_at: string;
}

export interface ReconciliationRun {
  id: string;
  provider_key: string;
  status: string;
  discrepancies: unknown[];
  started_at: string;
  completed_at: string | null;
}

export interface ReconciliationDiscrepancy {
  id: string;
  run_id: string;
  kind: string;
  detail: Record<string, unknown>;
  resolved: boolean;
  created_at: string;
}

export interface MicroLiveAdapter {
  id: string;
  provider_key: string;
  display_name: string;
  provider_kind: string;
  environment: string;
  is_default: boolean;
  is_enabled: boolean;
  verification_status: string;
  supports_live: boolean;
  description: string | null;
}

export interface DryRunOrderResult {
  would_be_allowed: boolean;
  blocking_codes: string[];
  notional: string;
  policy_version: number;
  activation_state: string;
  note: string;
}

/**
 * Phase 14 — Treasury and Executive Analytics.
 * Every balance and KPI here is SIMULATED / INTERNAL PAPER capital only.
 * There is no code path that represents a real external transfer as
 * executed — `ExternalTransferInstruction.status` is always one of
 * draft/proposed/cancelled.
 */
export interface TreasuryAccount {
  id: string;
  name: string;
  currency: string;
  classification: string;
  balance: string;
  is_simulated: boolean;
  status: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface CapitalPool {
  id: string;
  account_id: string;
  name: string;
  pool_type: string;
  balance: string;
  created_at: string;
  updated_at: string;
}

export interface CapitalAllocation {
  id: string;
  pool_id: string;
  target_type: string;
  target_id: string | null;
  amount: string;
  max_amount: string | null;
  status: string;
  notes: string | null;
  requested_at: string;
  approved_at: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
  released_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CapitalReservation {
  id: string;
  allocation_id: string;
  amount: string;
  status: string;
  reserved_at: string;
  released_at: string | null;
  created_at: string;
}

export interface TreasuryLedgerEntry {
  id: string;
  account_id: string;
  pool_id: string | null;
  allocation_id: string | null;
  entry_type: string;
  amount: string;
  balance_after: string;
  reference_type: string | null;
  reference_id: string | null;
  note: string | null;
  created_at: string;
}

export interface ExternalTransferInstruction {
  id: string;
  account_id: string;
  direction: string;
  amount: string;
  currency: string;
  destination_reference: string;
  status: string;
  environment_label: string;
  blocked_reason: string | null;
  execution_attempted_at: string | null;
  execution_attempt_count: number;
  proposed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface AttributionSnapshot {
  id: string;
  as_of: string;
  scope: string;
  scope_ref: string | null;
  environment_class: string;
  amounts: Record<string, unknown>;
  evidence_refs: unknown[];
  is_available: boolean;
  unavailable_reason: string | null;
  created_at: string;
}

export interface ExecutiveKpiSnapshot {
  id: string;
  as_of: string;
  kpi_key: string;
  value: string | null;
  unit: string;
  environment_class: string;
  evidence_refs: unknown[];
  is_estimated: boolean;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface ForecastScenario {
  id: string;
  name: string;
  scenario_type: string;
  as_of: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  is_deterministic: boolean;
  created_at: string;
}

export interface InstitutionalReport {
  id: string;
  report_type: string;
  version: number;
  as_of: string;
  content: Record<string, unknown>;
  content_hash: string;
  provenance: Record<string, unknown>;
  is_immutable: boolean;
  environment_disclaimer: string;
  created_at: string;
}

export interface TreasurySummary {
  disclaimer: string;
  total_simulated_balance: string;
  account_count: number;
  allocation_status_counts: Record<string, number>;
  external_transfer_status_counts: Record<string, number>;
  external_transfer_executed_count: number;
  latest_kpis: ExecutiveKpiSnapshot[];
  latest_paper_attribution: AttributionSnapshot[];
  live_available: boolean;
  live_unavailable_reason: string;
  latest_report: InstitutionalReport | null;
}

export interface ApiErrorBody {
  detail?: string | { msg?: string; type?: string }[] | Record<string, unknown>;
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.body = body;
  }
}
