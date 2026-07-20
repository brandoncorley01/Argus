import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { IncidentTransitionForm } from "@/components/IncidentForms";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
} from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import { isOperator } from "@/lib/rbac";
import {
  getIncident,
  getIncidentEvents,
  soft,
} from "@/lib/server/control-plane";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return { title: `Incident ${id.slice(0, 8)}` };
}

export default async function IncidentDetailPage({ params }: Props) {
  const user = await requireUser();
  const { id } = await params;
  const [incident, events] = await Promise.all([
    soft(() => getIncident(id)),
    soft(() => getIncidentEvents(id)),
  ]);

  if (!incident) {
    notFound();
  }

  return (
    <>
      <PageHeader
        title={incident.title}
        description={incident.description ?? "No description provided."}
        actions={
          <Link className="btn secondary" href="/incidents">
            Back to incidents
          </Link>
        }
      />

      <div className="grid grid-2">
        <Panel title="Incident state">
          <dl style={{ margin: 0, display: "grid", gap: "0.45rem" }}>
            <div>
              <dt className="metric-label">Status</dt>
              <dd style={{ margin: 0 }}>{incident.status}</dd>
            </div>
            <div>
              <dt className="metric-label">Severity</dt>
              <dd style={{ margin: 0 }}>{incident.severity}</dd>
            </div>
            <div>
              <dt className="metric-label">Related mode</dt>
              <dd style={{ margin: 0 }}>{incident.related_mode ?? "—"}</dd>
            </div>
            <div>
              <dt className="metric-label">Opened</dt>
              <dd style={{ margin: 0 }}>{formatTimestamp(incident.opened_at)}</dd>
            </div>
            <div>
              <dt className="metric-label">Closed</dt>
              <dd style={{ margin: 0 }}>{formatTimestamp(incident.closed_at)}</dd>
            </div>
          </dl>
        </Panel>

        <Panel title="Lifecycle transition">
          {isOperator(user) ? (
            <IncidentTransitionForm incidentId={incident.id} />
          ) : (
            <EmptyState>Viewer cannot mutate incident lifecycle.</EmptyState>
          )}
        </Panel>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <Panel title="Lifecycle events">
          {!events ? (
            <ErrorState>Lifecycle events unavailable.</ErrorState>
          ) : events.length === 0 ? (
            <EmptyState>No lifecycle events.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Type</th>
                    <th>From → To</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => (
                    <tr key={ev.id}>
                      <td>{formatTimestamp(ev.occurred_at)}</td>
                      <td>{ev.event_type}</td>
                      <td>
                        {ev.from_status ?? "—"} → {ev.to_status ?? "—"}
                      </td>
                      <td>{ev.note ?? "—"}</td>
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
