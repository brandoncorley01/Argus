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
