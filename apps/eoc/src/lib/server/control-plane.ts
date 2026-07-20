import { apiFetch } from "@/lib/server/api";
import type {
  ActivationState,
  ActivationTransition,
  AllowedTransitions,
  AuditEvent,
  AuditEventList,
  ConfigurationDocument,
  ConfigurationVersion,
  CredentialReference,
  CurrentUser,
  Incident,
  IncidentLifecycleEvent,
  InstitutionalHealth,
  KillSwitch,
  MicroCapitalPolicy,
  MicroLiveAdapter,
  MicroLiveStatus,
  ModeAvailabilityItem,
  OperatingModeState,
  PolicyDocument,
  PolicyVersion,
  ProcessHealth,
  ProtectiveAction,
  ReconciliationDiscrepancy,
  ReconciliationRun,
  ServiceWithProjection,
  SupervisorLease,
  WorkerIdentity,
  WorkerInstance,
} from "@/lib/types";

export async function getMe(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/v1/auth/me");
}

export async function getOperatingMode(): Promise<OperatingModeState> {
  return apiFetch<OperatingModeState>("/api/v1/operating-mode");
}

export async function getModeAvailability(): Promise<ModeAvailabilityItem[]> {
  return apiFetch<ModeAvailabilityItem[]>("/api/v1/operating-mode/availability");
}

export async function getAllowedTransitions(): Promise<AllowedTransitions> {
  return apiFetch<AllowedTransitions>("/api/v1/operating-mode/transitions");
}

export async function getInstitutionalHealth(): Promise<InstitutionalHealth> {
  return apiFetch<InstitutionalHealth>("/api/v1/health/institutional");
}

export async function getServices(): Promise<ServiceWithProjection[]> {
  return apiFetch<ServiceWithProjection[]>("/api/v1/health/services");
}

export async function getLease(): Promise<SupervisorLease> {
  return apiFetch<SupervisorLease>("/api/v1/health/lease");
}

export async function getProtectiveActions(): Promise<ProtectiveAction[]> {
  return apiFetch<ProtectiveAction[]>("/api/v1/health/protective-actions");
}

export async function getWorkerIdentities(): Promise<WorkerIdentity[]> {
  return apiFetch<WorkerIdentity[]>("/api/v1/workers/identities");
}

export async function getWorkerInstances(): Promise<WorkerInstance[]> {
  return apiFetch<WorkerInstance[]>("/api/v1/workers/instances");
}

export async function getIncidents(): Promise<Incident[]> {
  return apiFetch<Incident[]>("/api/v1/incidents");
}

export async function getIncident(id: string): Promise<Incident> {
  return apiFetch<Incident>(`/api/v1/incidents/${id}`);
}

export async function getIncidentEvents(
  id: string,
): Promise<IncidentLifecycleEvent[]> {
  return apiFetch<IncidentLifecycleEvent[]>(`/api/v1/incidents/${id}/events`);
}

export async function getAuditEvents(params?: {
  limit?: number;
  offset?: number;
  action?: string;
  resource_type?: string;
}): Promise<AuditEventList> {
  return apiFetch<AuditEventList>("/api/v1/audit/events", {
    searchParams: params,
  });
}

export async function getAuditEvent(id: string): Promise<AuditEvent> {
  return apiFetch<AuditEvent>(`/api/v1/audit/events/${id}`);
}

export async function getConfigurationDocuments(): Promise<
  ConfigurationDocument[]
> {
  return apiFetch<ConfigurationDocument[]>("/api/v1/configurations/documents");
}

export async function getConfigurationVersions(
  documentId: string,
): Promise<ConfigurationVersion[]> {
  return apiFetch<ConfigurationVersion[]>(
    `/api/v1/configurations/documents/${documentId}/versions`,
  );
}

export async function getPolicyDocuments(): Promise<PolicyDocument[]> {
  return apiFetch<PolicyDocument[]>("/api/v1/policies/documents");
}

export async function getPolicyVersions(
  documentId: string,
): Promise<PolicyVersion[]> {
  return apiFetch<PolicyVersion[]>(
    `/api/v1/policies/documents/${documentId}/versions`,
  );
}

/**
 * Phase 13 — Micro-Live Institution reads. All read-only; no endpoint here
 * can return a credential value or an activated live-trading state.
 */
export async function getMicroLiveStatus(): Promise<MicroLiveStatus> {
  return apiFetch<MicroLiveStatus>("/api/v1/micro-live/status");
}

export async function getMicroLiveActivation(): Promise<ActivationState> {
  return apiFetch<ActivationState>("/api/v1/micro-live/activation");
}

export async function getMicroLiveActivationTransitions(): Promise<
  ActivationTransition[]
> {
  return apiFetch<ActivationTransition[]>(
    "/api/v1/micro-live/activation/transitions",
  );
}

export async function getMicroLiveCredentialReferences(): Promise<
  CredentialReference[]
> {
  return apiFetch<CredentialReference[]>(
    "/api/v1/micro-live/credential-references",
  );
}

export async function getMicroLiveKillSwitches(): Promise<KillSwitch[]> {
  return apiFetch<KillSwitch[]>("/api/v1/micro-live/kill-switches");
}

export async function getMicroLiveCapitalPolicy(): Promise<MicroCapitalPolicy> {
  return apiFetch<MicroCapitalPolicy>("/api/v1/micro-live/capital-policy");
}

export async function getMicroLiveReconciliationRuns(): Promise<
  ReconciliationRun[]
> {
  return apiFetch<ReconciliationRun[]>("/api/v1/micro-live/reconciliation/runs");
}

export async function getMicroLiveReconciliationDiscrepancies(
  runId: string,
): Promise<ReconciliationDiscrepancy[]> {
  return apiFetch<ReconciliationDiscrepancy[]>(
    `/api/v1/micro-live/reconciliation/runs/${runId}/discrepancies`,
  );
}

export async function getMicroLiveAdapters(): Promise<MicroLiveAdapter[]> {
  return apiFetch<MicroLiveAdapter[]>("/api/v1/micro-live/adapters");
}

export async function getProcessHealth(): Promise<ProcessHealth> {
  return apiFetch<ProcessHealth>("/health");
}

export async function getProcessReady(): Promise<ProcessHealth> {
  return apiFetch<ProcessHealth>("/ready");
}

/** Soft read — returns null on 401/403/network so pages can show unavailable. */
export async function soft<T>(fn: () => Promise<T>): Promise<T | null> {
  try {
    return await fn();
  } catch {
    return null;
  }
}
