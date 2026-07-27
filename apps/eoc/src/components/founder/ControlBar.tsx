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
  disabled = false,
}: {
  label: string;
  busyLabel: string;
  className: string;
  run: () => Promise<ActionResult>;
  onDone?: (result: ActionResult) => void;
  disabled?: boolean;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionResult | null>(null);
  const blocked = disabled || pending;

  return (
    <div className="control-btn-wrap">
      <button
        type="button"
        className={className}
        disabled={blocked}
        title={disabled ? "Argus is already Running." : undefined}
        onClick={() => {
          if (blocked) return;
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
      ? "Start is greyed out while Running. Use Stop only when you want Argus off."
      : status === "Stopped"
        ? "Press Start Argus. It stays up until you press Stop."
        : "Paper trading is paused. Argus is still up.";
  const startLabel = status === "Stopped" ? "Start Argus" : "Running";

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
          label={startLabel}
          busyLabel="Starting…"
          className="btn control-btn control-btn-start"
          disabled={status !== "Stopped"}
          run={startArgusAction}
          onDone={(res) => {
            if (!res.ok) return;
            window.setTimeout(() => {
              window.location.assign("/today");
            }, 3000);
          }}
        />
        <ControlButton
          label="Stop Argus"
          busyLabel="Stopping…"
          className="btn control-btn control-btn-stop"
          disabled={status === "Stopped"}
          run={stopArgusAction}
        />
      </div>
    </section>
  );
}
