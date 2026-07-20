import type { Metadata } from "next";
import Link from "next/link";

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
import { isFounder, isOperator, primaryRole, roleLabel } from "@/lib/rbac";
import {
  getIncidents,
  getInstitutionalHealth,
  getOperatingMode,
  getProcessReady,
  getProtectiveActions,
  getServices,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Executive Overview" };

export default async function OverviewPage() {
  const user = await requireUser();
  const role = primaryRole(user);

  const [mode, health, ready, services, incidents, protective] =
    await Promise.all([
      soft(getOperatingMode),
      soft(getInstitutionalHealth),
      soft(getProcessReady),
      soft(getServices),
      soft(getIncidents),
      soft(getProtectiveActions),
    ]);

  const openIncidents =
    incidents?.filter((i) => i.status === "open" || i.status === "investigating")
      .length ?? null;

  const dashboardTitle =
    role === "FOUNDER"
      ? "Founder dashboard"
      : role === "OPERATOR"
        ? "Operator dashboard"
        : "Viewer dashboard";

  return (
    <>
      <PageHeader
        title={dashboardTitle}
        description={`Signed in as ${user.username} (${roleLabel(role)}). All values below are live control-plane reads. Empty or unavailable means the API returned no data—not a fabricated zero.`}
      />

      <div className="grid grid-4" style={{ marginBottom: "1rem" }}>
        <Panel className="rise-delay-1">
          <Metric
            label="Operating mode"
            value={mode?.current_mode ?? "Unavailable"}
            hint={
              mode
                ? `v${mode.state_version} · ${formatTimestamp(mode.updated_at)}`
                : "Control plane did not return mode state"
            }
          />
        </Panel>
        <Panel className="rise-delay-1">
          <Metric
            label="Institutional health"
            value={
              health ? (
                <StatusBadge status={health.status} />
              ) : (
                <StatusBadge status={null} label="unavailable" />
              )
            }
            hint={
              health
                ? `eval v${health.evaluation_version}`
                : "Health supervisor projection missing"
            }
          />
        </Panel>
        <Panel className="rise-delay-2">
          <Metric
            label="API readiness"
            value={
              ready ? (
                <StatusBadge
                  status={
                    typeof ready.status === "string" ? ready.status : "ready"
                  }
                />
              ) : (
                <StatusBadge status={null} label="unavailable" />
              )
            }
            hint="/ready probe"
          />
        </Panel>
        <Panel className="rise-delay-2">
          <Metric
            label="Open incidents"
            value={openIncidents === null ? "—" : openIncidents}
            hint={
              openIncidents === null
                ? "Incident API unavailable"
                : "open + investigating"
            }
          />
        </Panel>
      </div>

      <div className="grid grid-2">
        <Panel title="Executive summary" className="rise-delay-3">
          <ul style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--ink-soft)" }}>
            <li>
              Role surface: {roleLabel(role)}. Mutations require matching backend
              authority; this UI never elevates privileges.
            </li>
            <li>
              Emergency stop:{" "}
              {mode
                ? mode.emergency_stop_active
                  ? "ACTIVE"
                  : "inactive"
                : "unknown"}
            </li>
            <li>
              Recovery required:{" "}
              {mode ? (mode.recovery_required ? "yes" : "no") : "unknown"}
            </li>
            <li>
              Registered services reported:{" "}
              {services ? services.length : "unavailable"}
            </li>
            <li>
              Protective recommendations:{" "}
              {protective ? protective.length : "unavailable"}
            </li>
          </ul>
          <div className="form-actions" style={{ marginTop: "1rem" }}>
            {isOperator(user) ? (
              <Link className="btn" href="/operations">
                Manage operating mode
              </Link>
            ) : null}
            <Link className="btn secondary" href="/incidents">
              Review incidents
            </Link>
            {isFounder(user) ? (
              <Link className="btn secondary" href="/administration">
                Administration
              </Link>
            ) : null}
          </div>
        </Panel>

        <Panel title="Institutional health detail">
          {!health ? (
            <ErrorState>
              Institutional health could not be loaded. Confirm Phase 8 APIs and
              authentication.
            </ErrorState>
          ) : (
            <>
              <p style={{ marginTop: 0 }}>
                Evaluated {formatTimestamp(health.evaluated_at)}
              </p>
              <pre
                style={{
                  margin: 0,
                  whiteSpace: "pre-wrap",
                  fontSize: "0.82rem",
                  color: "var(--ink-soft)",
                }}
              >
                {JSON.stringify(health.summary, null, 2)}
              </pre>
            </>
          )}
        </Panel>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <Panel title="Service snapshot">
          {!services ? (
            <ErrorState>Service health list unavailable.</ErrorState>
          ) : services.length === 0 ? (
            <EmptyState>No registered services returned.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Kind</th>
                    <th>Status</th>
                    <th>Last observed</th>
                  </tr>
                </thead>
                <tbody>
                  {services.slice(0, 8).map((row) => (
                    <tr key={row.service.id}>
                      <td>{row.service.display_name}</td>
                      <td>{row.service.service_kind}</td>
                      <td>
                        <StatusBadge
                          status={row.projection?.status}
                          label={row.projection?.status ?? "no projection"}
                        />
                      </td>
                      <td>
                        {formatTimestamp(row.projection?.last_observed_at)}
                      </td>
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
