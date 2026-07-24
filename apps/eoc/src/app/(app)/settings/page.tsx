import type { Metadata } from "next";
import Link from "next/link";

import { ControlBar } from "@/components/founder/ControlBar";
import { PageHeader } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { deriveStatus } from "@/lib/founder/simple";
import { getProcessReady, soft } from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Settings" };

export default async function SettingsPage() {
  await requireUser();
  const ready = await soft(getProcessReady);
  const status = deriveStatus({
    apiReady: ready == null ? false : true,
    paperPaused: false,
    criticalAlerts: 0,
    workerFailed: false,
  });

  return (
    <>
      <PageHeader
        title="Settings"
        description="Start and stop Argus. Live trading stays locked."
      />

      <ControlBar status={status} />

      <div className="form-actions" style={{ marginTop: "1rem" }}>
        <Link className="btn secondary" href="/today">
          Back to Today
        </Link>
      </div>
    </>
  );
}
