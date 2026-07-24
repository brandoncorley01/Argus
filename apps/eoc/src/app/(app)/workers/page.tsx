import type { Metadata } from "next";

import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import {
  getWorkerIdentities,
  getWorkerInstances,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Workers" };

export default async function WorkersPage() {
  await requireUser();
  const [identities, instances] = await Promise.all([
    soft(getWorkerIdentities),
    soft(getWorkerInstances),
  ]);

  return (
    <>
      <PageHeader
        title="Workers"
        description="Worker identities and runtime instances from the Phase 8 worker registry. Status reflects control-plane records only."
      />

      <div className="grid grid-2">
        <Panel title="Identities">
          {!identities ? (
            <ErrorState>Worker identities unavailable.</ErrorState>
          ) : identities.length === 0 ? (
            <EmptyState>No worker identities registered.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Name</th>
                    <th>Enabled</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {identities.map((w) => (
                    <tr key={w.id}>
                      <td>{w.worker_key}</td>
                      <td>{w.display_name}</td>
                      <td>{w.is_enabled ? "yes" : "no"}</td>
                      <td>{formatTimestamp(w.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Instances">
          {!instances ? (
            <ErrorState>Worker instances unavailable.</ErrorState>
          ) : instances.length === 0 ? (
            <EmptyState>No worker instances reported.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Instance</th>
                    <th>Host</th>
                    <th>Status</th>
                    <th>Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  {instances.map((i) => (
                    <tr key={i.id}>
                      <td>{i.instance_key}</td>
                      <td>{i.hostname ?? "—"}</td>
                      <td>
                        <StatusBadge status={i.status} label={i.status} />
                      </td>
                      <td>{formatTimestamp(i.last_seen_at)}</td>
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
