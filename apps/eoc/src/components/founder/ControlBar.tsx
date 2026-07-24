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

type Kind = "start" | "stop" | "restart" | "backup" | "refresh";

const ACTIONS: Record<
  Kind,
  { label: string; busy: string; run: () => Promise<ActionResult>; className: string }
> = {
  start: {
    label: "Start Argus",
    busy: "Starting…",
    run: startArgusAction,
    className: "btn control-btn control-btn-start",
  },
  stop: {
    label: "Stop Argus",
    busy: "Stopping…",
    run: stopArgusAction,
    className: "btn secondary control-btn",
  },
  restart: {
    label: "Restart",
    busy: "Restarting…",
    run: restartArgusAction,
    className: "btn secondary control-btn",
  },
  backup: {
    label: "Backup",
    busy: "Backing up…",
    run: backupArgusAction,
    className: "btn secondary control-btn",
  },
  refresh: {
    label: "Refresh status",
    busy: "Refreshing…",
    run: refreshStatusAction,
    className: "btn secondary control-btn",
  },
};

export function ControlButton({ kind }: { kind: Kind }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionResult | null>(null);
  const cfg = ACTIONS[kind];

  return (
    <div className="control-btn-wrap">
      <button
        type="button"
        className={cfg.className}
        disabled={pending}
        onClick={() => {
          setResult(null);
          startTransition(async () => {
            const res = await cfg.run();
            setResult(res);
            router.refresh();
          });
        }}
      >
        {pending ? cfg.busy : cfg.label}
      </button>
      {result ? (
        <p className={`control-feedback ${result.ok ? "ok" : "err"}`} role="status">
          {result.message}
        </p>
      ) : null}
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
      <div className="control-status-row">
        <div>
          <div className="metric-label">Argus</div>
          <div className={`control-status control-status-${status.toLowerCase()}`}>
            {status === "Running"
              ? "Running"
              : status === "Stopped"
                ? "Stopped"
                : "Needs attention"}
          </div>
        </div>
        <p className="control-hint">
          {status === "Stopped"
            ? "Press Start Argus to begin."
            : status === "Attention"
              ? "Something needs a look — then continue as usual."
              : "Paper trading only. Live trading stays locked."}
        </p>
      </div>

      <div className="control-actions">
        {status === "Stopped" ? (
          <ControlButton kind="start" />
        ) : (
          <>
            <ControlButton kind="refresh" />
            <ControlButton kind="stop" />
          </>
        )}
        <ControlButton kind="restart" />
        <ControlButton kind="backup" />
      </div>

      <p className="control-desktop-note">
        Prefer desktop? Use <strong>Start Argus</strong> / <strong>Stop Argus</strong>{" "}
        shortcuts — same scripts as these buttons.
      </p>
    </section>
  );
}
