import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ErrorState, PageHeader, Panel } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import { getAuditEvent, soft } from "@/lib/server/control-plane";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return { title: `Audit ${id.slice(0, 8)}` };
}

export default async function AuditDetailPage({ params }: Props) {
  await requireUser();
  const { id } = await params;
  const event = await soft(() => getAuditEvent(id));
  if (!event) notFound();

  return (
    <>
      <PageHeader
        title={event.action}
        description={`Occurred ${formatTimestamp(event.occurred_at)}`}
        actions={
          <Link className="btn secondary" href="/audit">
            Back to explorer
          </Link>
        }
      />
      <Panel title="Event payload">
        {!event.payload ? (
          <ErrorState>No payload on this event.</ErrorState>
        ) : (
          <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
            {JSON.stringify(event.payload, null, 2)}
          </pre>
        )}
      </Panel>
      <div style={{ marginTop: "1rem" }}>
        <Panel title="Metadata">
          <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
            {JSON.stringify(
              {
                id: event.id,
                actor_user_id: event.actor_user_id,
                resource_type: event.resource_type,
                resource_id: event.resource_id,
                request_id: event.request_id,
                mode_at_time: event.mode_at_time,
                created_at: event.created_at,
              },
              null,
              2,
            )}
          </pre>
        </Panel>
      </div>
    </>
  );
}
