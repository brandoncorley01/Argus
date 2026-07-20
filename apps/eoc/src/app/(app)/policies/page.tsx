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
import { getPolicyDocuments, soft } from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Policies" };

export default async function PoliciesPage() {
  await requireUser();
  const docs = await soft(getPolicyDocuments);

  return (
    <>
      <PageHeader
        title="Policies"
        description="Versioned policy documents. Lifecycle mutations stay on the API; this view provides institutional visibility without inventing policy content."
      />
      <Panel title="Documents">
        {!docs ? (
          <ErrorState>Policy documents unavailable.</ErrorState>
        ) : docs.length === 0 ? (
          <EmptyState>No policy documents.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Key</th>
                  <th>Name</th>
                  <th>Kind</th>
                  <th>Retired</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link href={`/policies/${d.id}`}>{d.document_key}</Link>
                    </td>
                    <td>{d.name}</td>
                    <td>{d.policy_kind}</td>
                    <td>{d.is_retired ? "yes" : "no"}</td>
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
