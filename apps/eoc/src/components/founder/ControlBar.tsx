"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  backupArgusAction,
  installDesktopShortcutsAction,
  refreshStatusAction,
  restartArgusAction,
  startArgusAction,
  stopArgusAction,
  type ActionResult,
} from "@/lib/actions/control";

function Feedback({ result }: { result: ActionResult | null }) {
  if (!result) return null;
  return (
    <p className={`control-feedback ${result.ok ? "ok" : "err"}`} role="status">
      {result.message}
      {result.detail ? (
        <span className="control-feedback-detail"> {result.detail.slice(0, 240)}</span>
      ) : null}
    </p>
  );
}

function BigButton({
  label,
  busyLabel,
  className,
  run,
}: {
  label: string;
  busyLabel: string;
  className: string;
  run: () => Promise<ActionResult>;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionResult | null>(null);

  return (
    <div className="control-btn-wrap">
      <button
        type="button"
        className={className}
        disabled={pending}
        onClick={() => {
          setResult(null);
          startTransition(async () => {
            const res = await run();
            setResult(res);
            router.refresh();
          });
        }}
      >
        {pending ? busyLabel : label}
      </button>
      <Feedback result={result} />
    </div>
  );
}

export function DesktopDownloadBanner() {
  return (
    <section className="panel desktop-banner rise" aria-label="Desktop shortcuts">
      <h2 style={{ marginTop: 0 }}>Put Start &amp; Stop on this PC</h2>
      <p className="muted-note" style={{ marginTop: 0 }}>
        One download. Double-click it. Shortcuts appear on your Desktop.
      </p>
      <div className="control-primary">
        <a
          className="btn control-btn control-btn-desktop desktop-download-cta"
          href="/api/founder/desktop-installer"
          download="Install-Argus-Desktop.cmd"
        >
          Download desktop installer
        </a>
        <BigButton
          label="Install now (this PC)"
          busyLabel="Installing…"
          className="btn secondary control-btn"
          run={installDesktopShortcutsAction}
        />
      </div>
      <p className="control-desktop-note">
        Creates: <strong>Start Argus</strong>, <strong>Stop Argus</strong>,{" "}
        <strong>Open Argus</strong>, <strong>End Trading Day</strong>
      </p>
    </section>
  );
}

export function ControlBar({
  status,
}: {
  status: "Running" | "Stopped" | "Attention";
}) {
  return (
    <>
      <DesktopDownloadBanner />

      <section className="control-bar panel" aria-label="Argus controls">
        <h2 className="control-bar-title">Start / Stop Argus</h2>
        <div className="control-status-row">
          <div>
            <div className="metric-label">Status right now</div>
            <div className={`control-status control-status-${status.toLowerCase()}`}>
              {status === "Running"
                ? "Running"
                : status === "Stopped"
                  ? "Stopped"
                  : "Needs attention"}
            </div>
          </div>
          <p className="control-hint">
            Use these buttons here, or the Desktop shortcuts after you download
            them above.
          </p>
        </div>

        <div className="control-primary">
          <BigButton
            label="Start Argus"
            busyLabel="Starting…"
            className="btn control-btn control-btn-start"
            run={startArgusAction}
          />
          <BigButton
            label="Stop Argus"
            busyLabel="Stopping…"
            className="btn control-btn control-btn-stop"
            run={stopArgusAction}
          />
        </div>

        <div className="control-actions">
          <BigButton
            label="Refresh status"
            busyLabel="Refreshing…"
            className="btn secondary control-btn"
            run={refreshStatusAction}
          />
          <BigButton
            label="Restart"
            busyLabel="Restarting…"
            className="btn secondary control-btn"
            run={restartArgusAction}
          />
          <BigButton
            label="Backup"
            busyLabel="Backing up…"
            className="btn secondary control-btn"
            run={backupArgusAction}
          />
        </div>
      </section>
    </>
  );
}
