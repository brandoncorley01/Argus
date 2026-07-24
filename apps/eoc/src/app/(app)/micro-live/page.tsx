import type { Metadata } from "next";

import {
  ActivationTransitionForm,
  CapitalPolicyForm,
  CredentialReferenceCreateForm,
  CredentialReferenceValidateButton,
  DryRunOrderForm,
  KillSwitchForm,
  ReconciliationRunForm,
} from "@/components/MicroLiveForms";
import {
  EmptyState,
  ErrorState,
  Metric,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import { isFounder, isOperator } from "@/lib/rbac";
import {
  getMicroLiveActivation,
  getMicroLiveAdapters,
  getMicroLiveCapitalPolicy,
  getMicroLiveCredentialReferences,
  getMicroLiveKillSwitches,
  getMicroLiveReconciliationRuns,
  getMicroLiveStatus,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Micro-Live Institution" };

export default async function MicroLivePage() {
  const user = await requireUser();
  const [status, activation, credentials, killSwitches, policy, adapters, reconRuns] =
    await Promise.all([
      soft(getMicroLiveStatus),
      soft(getMicroLiveActivation),
      soft(getMicroLiveCredentialReferences),
      soft(getMicroLiveKillSwitches),
      soft(getMicroLiveCapitalPolicy),
      soft(getMicroLiveAdapters),
      soft(getMicroLiveReconciliationRuns),
    ]);

  return (
    <>
      <PageHeader
        title="Micro-Live Institution"
        description="Deny-by-default live-execution architecture. No credentials are configured, no live order can be submitted, and there is no reachable path to an active live-trading state. Internal paper execution remains the default and only operational provider."
      />

      {!status ? (
        <ErrorState>Micro-live status unavailable.</ErrorState>
      ) : (
        <div className="grid grid-4" style={{ marginBottom: "1rem" }}>
          <Metric
            label="Activation state"
            value={status.activation_state}
            hint={`state version ${status.state_version}`}
          />
          <Metric
            label="Credentials configured"
            value={status.credentials_configured ? "yes" : "no"}
            hint="Presence-only; values never stored"
          />
          <Metric
            label="Live execution active"
            value={status.live_execution_active ? "YES" : "no"}
            hint="Always no in this system"
          />
          <Metric
            label="Paper provider default"
            value={status.paper_provider_default ? "yes" : "no"}
          />
        </div>
      )}

      {status ? (
        <div className="grid grid-3" style={{ marginBottom: "1rem" }}>
          <Metric
            label="Global kill switch"
            value={status.global_kill_switch_active ? "ACTIVE" : "off"}
          />
          <Metric
            label="Active capital policy version"
            value={status.active_capital_policy_version ?? "—"}
          />
          <Metric
            label="Adapters (enabled / total)"
            value={`${status.enabled_adapter_count} / ${status.adapter_count}`}
          />
        </div>
      ) : null}

      {status ? (
        <div className="state-block" style={{ marginBottom: "1.5rem" }}>
          {status.disclaimer}
        </div>
      ) : null}

      <div className="grid grid-2">
        <Panel title="Live activation state machine">
          {!activation ? (
            <ErrorState>Activation state unavailable.</ErrorState>
          ) : (
            <dl style={{ margin: 0, display: "grid", gap: "0.5rem" }}>
              <div>
                <dt className="metric-label">Current state</dt>
                <dd style={{ margin: 0, fontFamily: "var(--font-display)", fontSize: "1.2rem" }}>
                  {activation.activation_state}
                </dd>
              </div>
              <div>
                <dt className="metric-label">Updated</dt>
                <dd style={{ margin: 0 }}>{formatTimestamp(activation.updated_at)}</dd>
              </div>
            </dl>
          )}
          {!isFounder(user) ? (
            <EmptyState>
              Founder role required to submit activation transitions. Viewer
              and Operator roles cannot arm or activate live execution — the
              backend enforces this independent of this UI.
            </EmptyState>
          ) : activation ? (
            <div style={{ marginTop: "1rem" }}>
              <ActivationTransitionForm currentState={activation.activation_state} />
            </div>
          ) : null}
        </Panel>

        <Panel title="Global kill switches">
          {!killSwitches ? (
            <ErrorState>Kill switches unavailable.</ErrorState>
          ) : killSwitches.length === 0 ? (
            <EmptyState>No kill switches configured.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Scope</th>
                    <th>Scope id</th>
                    <th>Status</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {killSwitches.map((k) => (
                    <tr key={k.id}>
                      <td>{k.scope_type}</td>
                      <td>{k.scope_id ?? "—"}</td>
                      <td>
                        <StatusBadge
                          status={k.active ? "unhealthy" : "healthy"}
                          label={k.active ? "ACTIVE" : "off"}
                        />
                      </td>
                      <td>{k.reason ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {isFounder(user) ? (
            <div style={{ marginTop: "1rem" }}>
              <KillSwitchForm />
            </div>
          ) : (
            <EmptyState>Founder role required to change kill switches.</EmptyState>
          )}
        </Panel>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Credential references (names only — never values)">
          {!credentials ? (
            <ErrorState>Credential references unavailable.</ErrorState>
          ) : credentials.length === 0 ? (
            <EmptyState>
              No credential references configured. System remains PAPER_ONLY.
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Env var reference</th>
                    <th>Purpose</th>
                    <th>Present</th>
                    <th>Last checked</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {credentials.map((c) => (
                    <tr key={c.id}>
                      <td>{c.provider_key}</td>
                      <td>{c.ref_name}</td>
                      <td>{c.purpose}</td>
                      <td>{c.is_present_cached ? "yes" : "no"}</td>
                      <td>{formatTimestamp(c.last_validated_at)}</td>
                      <td>
                        {isFounder(user) ? (
                          <CredentialReferenceValidateButton referenceId={c.id} />
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {isFounder(user) ? (
            <div style={{ marginTop: "1rem" }}>
              <CredentialReferenceCreateForm />
            </div>
          ) : null}
        </Panel>

        <Panel title="Optional live adapters (disabled by default)">
          {!adapters ? (
            <ErrorState>Adapters unavailable.</ErrorState>
          ) : adapters.length === 0 ? (
            <EmptyState>No optional adapters registered.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Adapter</th>
                    <th>Environment</th>
                    <th>Verification</th>
                    <th>Enabled</th>
                    <th>Supports live</th>
                  </tr>
                </thead>
                <tbody>
                  {adapters.map((a) => (
                    <tr key={a.id}>
                      <td>{a.display_name}</td>
                      <td>{a.environment}</td>
                      <td>{a.verification_status}</td>
                      <td>{a.is_enabled ? "yes" : "no"}</td>
                      <td>{a.supports_live ? "yes" : "no"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Micro-capital policy (active)">
          {!policy ? (
            <ErrorState>Micro-capital policy unavailable.</ErrorState>
          ) : (
            <dl style={{ margin: "0 0 1rem 0", display: "grid", gap: "0.4rem" }}>
              <div>
                <dt className="metric-label">Version</dt>
                <dd style={{ margin: 0 }}>{policy.version}</dd>
              </div>
              <div>
                <dt className="metric-label">Max deployable capital</dt>
                <dd style={{ margin: 0 }}>{policy.max_deployable_capital}</dd>
              </div>
              <div>
                <dt className="metric-label">Max order notional</dt>
                <dd style={{ margin: 0 }}>{policy.max_order_notional}</dd>
              </div>
              <div>
                <dt className="metric-label">Max daily loss</dt>
                <dd style={{ margin: 0 }}>{policy.max_daily_loss}</dd>
              </div>
            </dl>
          )}
          {isFounder(user) ? (
            <CapitalPolicyForm policy={policy} />
          ) : (
            <EmptyState>Founder role required to change capital policy.</EmptyState>
          )}
        </Panel>

        <Panel title="Dry-run order validation">
          <p style={{ color: "var(--muted)" }}>
            Runs pretrade/micro-capital checks only. Never submits a real or
            paper order.
          </p>
          <DryRunOrderForm />
        </Panel>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <Panel title="Reconciliation runs (fixture-based)">
          {!reconRuns ? (
            <ErrorState>Reconciliation runs unavailable.</ErrorState>
          ) : reconRuns.length === 0 ? (
            <EmptyState>No reconciliation runs yet.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Status</th>
                    <th>Discrepancies</th>
                    <th>Started</th>
                    <th>Completed</th>
                  </tr>
                </thead>
                <tbody>
                  {reconRuns.map((r) => (
                    <tr key={r.id}>
                      <td>{r.provider_key}</td>
                      <td>
                        <StatusBadge
                          status={r.status === "clean" ? "healthy" : "degraded"}
                          label={r.status}
                        />
                      </td>
                      <td>{r.discrepancies.length}</td>
                      <td>{formatTimestamp(r.started_at)}</td>
                      <td>{formatTimestamp(r.completed_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {isOperator(user) ? (
            <div style={{ marginTop: "1rem" }}>
              <ReconciliationRunForm />
            </div>
          ) : (
            <EmptyState>
              Operator or Founder role required to run reconciliation.
            </EmptyState>
          )}
        </Panel>
      </div>
    </>
  );
}
