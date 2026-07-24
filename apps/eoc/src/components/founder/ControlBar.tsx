"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  backupArgusAction,
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

export function ControlBar({
  status,
}: {
  status: "Running" | "Stopped" | "Attention";
}) {
  return (
    <section className="control-bar panel" aria-label="Argus controls">
      <h2 className="control-bar-title">Start / Stop</h2>
      <div className="control-status-row">
        <div>
          <div className="metric-label">Status</div>
          <div className={`control-status control-status-${status.toLowerCase()}`}>
            {status === "Running"
              ? "Running"
              : status === "Stopped"
                ? "Stopped"
                : "Needs attention"}
          </div>
        </div>
        <p className="control-hint">
          If this page will not load, double-click <strong>Start-Argus.cmd</strong>{" "}
          in your Argus folder.
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
          label="Refresh"
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
  );
}
