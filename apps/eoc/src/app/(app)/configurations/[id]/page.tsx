import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

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
  getConfigurationVersions,
  soft,
} from "@/lib/server/control-plane";

type Props = { params: Promise<{ id: string }> };

export const metadata: Metadata = { title: "Configuration" };

export default async function ConfigurationDetailPage({ params }: Props) {
  await requireUser();
  const { id } = await params;
  const docs = await soft(getConfigurationDocuments);
  const doc = docs?.find((d) => d.id === id);
  if (!doc) notFound();
  const versions = await soft(() => getConfigurationVersions(id));

  return (
    <>
      <PageHeader
        title={doc.name}
        description={doc.description ?? doc.document_key}
        actions={
          <Link className="btn secondary" href="/configurations">
            Back
          </Link>
        }
      />
      <Panel title="Versions">
        {!versions ? (
          <ErrorState>Versions unavailable.</ErrorState>
        ) : versions.length === 0 ? (
          <EmptyState>No versions.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Status</th>
                  <th>Hash</th>
                  <th>Created</th>
                  <th>Activated</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((v) => (
                  <tr key={v.id}>
                    <td>
                      {v.version_label} (#{v.version_number})
                    </td>
                    <td>{v.status}</td>
                    <td style={{ fontSize: "0.8rem" }}>{v.payload_hash}</td>
                    <td>{formatTimestamp(v.created_at)}</td>
                    <td>{formatTimestamp(v.activated_at)}</td>
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
