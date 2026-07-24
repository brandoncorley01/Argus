import type { Metadata } from "next";

import { ModeForms } from "@/components/ModeForms";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import { isFounder, isOperator } from "@/lib/rbac";
import {
  getAllowedTransitions,
  getModeAvailability,
  getOperatingMode,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Operations" };

export default async function OperationsPage() {
  const user = await requireUser();
  const [mode, availability, transitions] = await Promise.all([
    soft(getOperatingMode),
    soft(getModeAvailability),
    soft(getAllowedTransitions),
  ]);

  return (
    <>
      <PageHeader
        title="Operations"
        description="Operating mode management against the Phase 7 state machine. Confirmation workflows call the API; locked modes remain non-enterable when the backend says so."
      />

      <div className="grid grid-2">
        <Panel title="Current mode">
          {!mode ? (
            <ErrorState>
              Operating mode state unavailable. The system may be uninitialized
              or the API unreachable.
            </ErrorState>
          ) : (
            <dl style={{ margin: 0, display: "grid", gap: "0.55rem" }}>
              <div>
                <dt className="metric-label">Mode</dt>
                <dd style={{ margin: 0, fontSize: "1.4rem", fontFamily: "var(--font-display)" }}>
                  {mode.current_mode}
                </dd>
              </div>
              <div>
                <dt className="metric-label">State version</dt>
                <dd style={{ margin: 0 }}>{mode.state_version}</dd>
              </div>
              <div>
                <dt className="metric-label">Emergency stop</dt>
                <dd style={{ margin: 0 }}>
                  <StatusBadge
                    status={mode.emergency_stop_active ? "unhealthy" : "healthy"}
                    label={mode.emergency_stop_active ? "active" : "inactive"}
                  />
                </dd>
              </div>
              <div>
                <dt className="metric-label">Recovery required</dt>
                <dd style={{ margin: 0 }}>
                  {mode.recovery_required ? "yes" : "no"}
                </dd>
              </div>
              <div>
                <dt className="metric-label">Reason</dt>
                <dd style={{ margin: 0 }}>{mode.reason ?? "—"}</dd>
              </div>
              <div>
                <dt className="metric-label">Updated</dt>
                <dd style={{ margin: 0 }}>{formatTimestamp(mode.updated_at)}</dd>
              </div>
            </dl>
          )}
        </Panel>

        <Panel title="Governed actions">
          {!isOperator(user) ? (
            <EmptyState>
              Viewer role: mode mutations are hidden. Backend would deny them
              even if requested.
            </EmptyState>
          ) : !mode ? (
            isFounder(user) ? (
              <ModeForms kind="initialize" />
            ) : (
              <ErrorState>Mode state missing; Founder must initialize.</ErrorState>
            )
          ) : (
            <ModeForms
              kind="manage"
              mode={mode}
              enterable={transitions?.enterable_targets ?? []}
              canEmergency={isFounder(user)}
            />
          )}
        </Panel>
      </div>

      <div style={{ marginTop: "1rem" }} className="grid grid-2">
        <Panel title="Availability">
          {!availability ? (
            <ErrorState>Availability feed unavailable.</ErrorState>
          ) : availability.length === 0 ? (
            <EmptyState>No availability rows.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Mode</th>
                    <th>Enterable</th>
                    <th>Authority</th>
                    <th>Blocking</th>
                  </tr>
                </thead>
                <tbody>
                  {availability.map((row) => (
                    <tr key={row.mode}>
                      <td>{row.mode}</td>
                      <td>{row.enterable ? "yes" : "no"}</td>
                      <td>{row.required_authority}</td>
                      <td>
                        {row.blocking_codes.length
                          ? row.blocking_codes.join(", ")
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Allowed transitions">
          {!transitions ? (
            <ErrorState>Transitions feed unavailable.</ErrorState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Target</th>
                    <th>Structural</th>
                    <th>Enterable</th>
                    <th>Blocking</th>
                  </tr>
                </thead>
                <tbody>
                  {transitions.targets.map((t) => (
                    <tr key={t.mode}>
                      <td>{t.mode}</td>
                      <td>{t.structurally_allowed ? "yes" : "no"}</td>
                      <td>{t.enterable ? "yes" : "no"}</td>
                      <td>
                        {t.blocking_codes.length
                          ? t.blocking_codes.join(", ")
                          : "—"}
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
