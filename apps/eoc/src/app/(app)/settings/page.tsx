import type { Metadata } from "next";
import Link from "next/link";

import { ControlBar } from "@/components/founder/ControlBar";
import { PageHeader, Panel } from "@/components/ui";
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
        description="Start, Stop, and desktop shortcuts. Live trading stays locked."
      />

      <ControlBar status={status} />

      <Panel title="What the installer adds">
        <ul className="plain-list">
          <li>Start Argus</li>
          <li>Stop Argus</li>
          <li>Open Argus</li>
          <li>End Trading Day</li>
        </ul>
        <div className="form-actions" style={{ marginTop: "0.75rem" }}>
          <a className="btn" href="/api/founder/desktop-installer" download>
            Download desktop installer
          </a>
        </div>
      </Panel>

      <div className="form-actions" style={{ marginTop: "1rem" }}>
        <Link className="btn secondary" href="/today">
          Back to Today
        </Link>
        <Link className="btn secondary" href="/get-desktop">
          Open download page
        </Link>
      </div>
    </>
  );
}
