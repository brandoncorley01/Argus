import type { Metadata } from "next";
import Link from "next/link";

import { ControlBar } from "@/components/founder/ControlBar";
import { PageHeader, Panel } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { getProcessReady, soft } from "@/lib/server/control-plane";
import { deriveStatus } from "@/lib/founder/simple";

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
        description="Start, Stop, and desktop shortcuts. Live trading stays locked."
      />

      <ControlBar status={status} />

      <Panel title="Desktop shortcuts">
        <p className="muted-note" style={{ marginTop: 0 }}>
          Prefer icons on your Desktop? Use <strong>Install desktop shortcuts</strong>{" "}
          above, or download{" "}
          <a href="/api/founder/desktop-installer">Install-Argus-Desktop.cmd</a> and
          double-click it.
        </p>
        <ul className="plain-list">
          <li>Start Argus</li>
          <li>Stop Argus</li>
          <li>Open Argus</li>
          <li>End Trading Day</li>
        </ul>
      </Panel>

      <div className="form-actions" style={{ marginTop: "1rem" }}>
        <Link className="btn" href="/today">
          Back to Today
        </Link>
      </div>
    </>
  );
}
