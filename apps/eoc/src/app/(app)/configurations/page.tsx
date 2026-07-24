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
import {
  getConfigurationDocuments,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Configurations" };

export default async function ConfigurationsPage() {
  await requireUser();
  const docs = await soft(getConfigurationDocuments);

  return (
    <>
      <PageHeader
        title="Configurations"
        description="Versioned configuration documents from the Phase 6 governance engine. Draft/activate mutations remain API-authoritative; this screen is the institutional inventory."
      />
      <Panel title="Documents">
        {!docs ? (
          <ErrorState>Configuration documents unavailable.</ErrorState>
        ) : docs.length === 0 ? (
          <EmptyState>No configuration documents.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Key</th>
                  <th>Name</th>
                  <th>Schema</th>
                  <th>Retired</th>
                  <th>Authority</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link href={`/configurations/${d.id}`}>{d.document_key}</Link>
                    </td>
                    <td>{d.name}</td>
                    <td>{d.schema_identifier}</td>
                    <td>{d.is_retired ? "yes" : "no"}</td>
                    <td>{d.draft_authority}</td>
                    <td>{formatTimestamp(d.created_at)}</td>
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
