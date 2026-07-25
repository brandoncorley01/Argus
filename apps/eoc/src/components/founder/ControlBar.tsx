"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  startArgusAction,
  stopArgusAction,
  type ActionResult,
} from "@/lib/actions/control";

function Feedback({ result }: { result: ActionResult | null }) {
  if (!result) return null;
  return (
    <p className={`control-feedback ${result.ok ? "ok" : "err"}`} role="status">
      {result.message}
    </p>
  );
}

function ControlButton({
  label,
  busyLabel,
  className,
  run,
  onDone,
}: {
  label: string;
  busyLabel: string;
  className: string;
  run: () => Promise<ActionResult>;
  onDone?: (result: ActionResult) => void;
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
            onDone?.(res);
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
  buildId,
}: {
  status: "Running" | "Stopped" | "Attention";
  buildId: string;
}) {
  const statusLabel =
    status === "Running" ? "Running" : status === "Stopped" ? "Stopped" : "Paused";
  const statusHint =
    status === "Running"
      ? "Argus is up. Use Stop when you are done."
      : status === "Stopped"
        ? "Press Start Argus."
        : "Paper trading is paused.";

  return (
    <section className="control-bar panel home-controls" aria-label="Start and stop Argus">
      <div className="control-status-row">
        <div>
          <div className="metric-label">Status</div>
          <div className={`control-status control-status-${status.toLowerCase()}`}>
            {statusLabel}
          </div>
          <p className="control-hint" style={{ marginTop: "0.35rem" }}>
            {statusHint}
          </p>
          <p className="muted-note" style={{ marginTop: "0.35rem", marginBottom: 0 }}>
            Build {buildId}
          </p>
        </div>
      </div>

      <div className="control-primary">
        <ControlButton
          label="Start Argus"
          busyLabel="Starting…"
          className="btn control-btn control-btn-start"
          run={startArgusAction}
          onDone={(res) => {
            if (!res.ok) return;
            // Pull + dashboard reload can take a few seconds; then hard reload Home.
            window.setTimeout(() => {
              window.location.assign("/today");
            }, 8000);
          }}
        />
        <ControlButton
          label="Stop Argus"
          busyLabel="Stopping…"
          className="btn control-btn control-btn-stop"
          run={stopArgusAction}
        />
      </div>
    </section>
  );
}
