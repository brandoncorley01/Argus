import type { Metadata } from "next";
import Link from "next/link";

import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
} from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import { getAuditEvents, soft } from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Audit Explorer" };

type Props = {
  searchParams: Promise<{ action?: string; resource_type?: string; offset?: string }>;
};

export default async function AuditPage({ searchParams }: Props) {
  await requireUser();
  const sp = await searchParams;
  const offset = Number(sp.offset ?? 0) || 0;
  const audit = await soft(() =>
    getAuditEvents({
      limit: 50,
      offset,
      action: sp.action,
      resource_type: sp.resource_type,
    }),
  );

  return (
    <>
      <PageHeader
        title="Audit Explorer"
        description="Append-only institutional audit trail. Filters are passed to the API; results are never invented."
      />

      <Panel title="Filters">
        <form method="get" className="grid grid-3">
          <div className="field">
            <label htmlFor="action">Action contains / equals</label>
            <input id="action" name="action" defaultValue={sp.action ?? ""} />
          </div>
          <div className="field">
            <label htmlFor="resource_type">Resource type</label>
            <input
              id="resource_type"
              name="resource_type"
              defaultValue={sp.resource_type ?? ""}
            />
          </div>
          <div className="form-actions" style={{ alignItems: "end" }}>
            <button className="btn secondary" type="submit">
              Apply filters
            </button>
          </div>
        </form>
      </Panel>

      <div style={{ marginTop: "1rem" }}>
        <Panel title="Events">
          {!audit ? (
            <ErrorState>Audit API unavailable.</ErrorState>
          ) : audit.items.length === 0 ? (
            <EmptyState>No audit events for this query.</EmptyState>
          ) : (
            <>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Action</th>
                      <th>Resource</th>
                      <th>Actor</th>
                      <th>Request</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.items.map((ev) => (
                      <tr key={ev.id}>
                        <td>{formatTimestamp(ev.occurred_at)}</td>
                        <td>
                          <Link href={`/audit/${ev.id}`}>{ev.action}</Link>
                        </td>
                        <td>
                          {ev.resource_type}
                          {ev.resource_id ? `:${ev.resource_id}` : ""}
                        </td>
                        <td>{ev.actor_user_id ?? "—"}</td>
                        <td>{ev.request_id ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="form-actions" style={{ marginTop: "1rem" }}>
                {offset > 0 ? (
                  <Link
                    className="btn secondary"
                    href={`/audit?offset=${Math.max(0, offset - 50)}&action=${sp.action ?? ""}&resource_type=${sp.resource_type ?? ""}`}
                  >
                    Previous
                  </Link>
                ) : null}
                {audit.items.length >= audit.limit ? (
                  <Link
                    className="btn secondary"
                    href={`/audit?offset=${offset + audit.limit}&action=${sp.action ?? ""}&resource_type=${sp.resource_type ?? ""}`}
                  >
                    Next
                  </Link>
                ) : null}
              </div>
            </>
          )}
        </Panel>
      </div>
    </>
  );
}
