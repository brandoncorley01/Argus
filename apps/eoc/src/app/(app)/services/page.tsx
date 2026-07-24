import type { Metadata } from "next";

import { SupervisorCycleButton } from "@/components/SupervisorCycleButton";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import { isFounder } from "@/lib/rbac";
import {
  getLease,
  getProcessHealth,
  getProcessReady,
  getProtectiveActions,
  getServices,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Services" };

export default async function ServicesPage() {
  const user = await requireUser();
  const [services, lease, health, ready, protective] = await Promise.all([
    soft(getServices),
    soft(getLease),
    soft(getProcessHealth),
    soft(getProcessReady),
    soft(getProtectiveActions),
  ]);

  return (
    <>
      <PageHeader
        title="Services"
        description="Registered service health projections, process probes, supervisor lease, and protective recommendations. Dependency visualization uses real registry criticality and projection status."
        actions={isFounder(user) ? <SupervisorCycleButton /> : undefined}
      />

      <div className="grid grid-3" style={{ marginBottom: "1rem" }}>
        <Panel title="Process /health">
          {!health ? (
            <ErrorState>Unavailable</ErrorState>
          ) : (
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: "0.82rem" }}>
              {JSON.stringify(health, null, 2)}
            </pre>
          )}
        </Panel>
        <Panel title="Process /ready">
          {!ready ? (
            <ErrorState>Unavailable or not ready</ErrorState>
          ) : (
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: "0.82rem" }}>
              {JSON.stringify(ready, null, 2)}
            </pre>
          )}
        </Panel>
        <Panel title="Supervisor lease">
          {!lease ? (
            <ErrorState>Lease unavailable</ErrorState>
          ) : (
            <dl style={{ margin: 0, display: "grid", gap: "0.4rem" }}>
              <div>
                <dt className="metric-label">Holder</dt>
                <dd style={{ margin: 0 }}>{lease.holder_instance_id ?? "—"}</dd>
              </div>
              <div>
                <dt className="metric-label">Epoch</dt>
                <dd style={{ margin: 0 }}>{lease.lease_epoch}</dd>
              </div>
              <div>
                <dt className="metric-label">Until</dt>
                <dd style={{ margin: 0 }}>{formatTimestamp(lease.lease_until)}</dd>
              </div>
              <div>
                <dt className="metric-label">Last cycle</dt>
                <dd style={{ margin: 0 }}>
                  {formatTimestamp(lease.last_cycle_at)} ·{" "}
                  {lease.last_cycle_result ?? "—"}
                </dd>
              </div>
            </dl>
          )}
        </Panel>
      </div>

      <Panel title="Service registry & projections">
        {!services ? (
          <ErrorState>Service list unavailable.</ErrorState>
        ) : services.length === 0 ? (
          <EmptyState>No services registered.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Kind</th>
                  <th>Criticality</th>
                  <th>Enabled</th>
                  <th>Status</th>
                  <th>Failures</th>
                  <th>Last observed</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {services.map((row) => (
                  <tr key={row.service.id}>
                    <td>
                      <strong>{row.service.display_name}</strong>
                      <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
                        {row.service.service_key}
                      </div>
                    </td>
                    <td>{row.service.service_kind}</td>
                    <td>{row.service.criticality}</td>
                    <td>{row.service.is_enabled ? "yes" : "no"}</td>
                    <td>
                      <StatusBadge
                        status={row.projection?.status}
                        label={row.projection?.status ?? "no projection"}
                      />
                    </td>
                    <td>{row.projection?.consecutive_failures ?? "—"}</td>
                    <td>{formatTimestamp(row.projection?.last_observed_at)}</td>
                    <td>{row.projection?.detail ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div style={{ marginTop: "1rem" }}>
        <Panel title="Dependency / protective posture">
          {!protective ? (
            <ErrorState>Protective actions unavailable.</ErrorState>
          ) : protective.length === 0 ? (
            <EmptyState>No protective recommendations currently open.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Rationale</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {protective.map((p) => (
                    <tr key={p.id}>
                      <td>{p.action_type}</td>
                      <td>{p.status}</td>
                      <td>{p.rationale}</td>
                      <td>{formatTimestamp(p.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
