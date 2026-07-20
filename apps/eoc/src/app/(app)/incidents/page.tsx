import type { Metadata } from "next";
import Link from "next/link";

import { IncidentCreateForm } from "@/components/IncidentForms";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import { isOperator } from "@/lib/rbac";
import { getIncidents, soft } from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Incidents" };

export default async function IncidentsPage() {
  const user = await requireUser();
  const incidents = await soft(getIncidents);

  return (
    <>
      <PageHeader
        title="Incidents"
        description="Institutional incident lifecycle from the Phase 8 incident service. Opening or transitioning incidents is denied by the API for Viewer."
      />

      {isOperator(user) ? (
        <div style={{ marginBottom: "1rem" }}>
          <Panel title="Open incident">
            <IncidentCreateForm />
          </Panel>
        </div>
      ) : null}

      <Panel title="Incident list">
        {!incidents ? (
          <ErrorState>Incidents API unavailable.</ErrorState>
        ) : incidents.length === 0 ? (
          <EmptyState>No incidents returned.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Opened</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((inc) => (
                  <tr key={inc.id}>
                    <td>
                      <Link href={`/incidents/${inc.id}`}>{inc.title}</Link>
                      {inc.opened_by_system ? (
                        <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
                          system-opened
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <StatusBadge status={inc.severity} label={inc.severity} />
                    </td>
                    <td>{inc.status}</td>
                    <td>{formatTimestamp(inc.opened_at)}</td>
                    <td>{inc.source_service_id ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
