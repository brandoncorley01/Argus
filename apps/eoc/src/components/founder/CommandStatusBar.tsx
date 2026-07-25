"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  startArgusAction,
  stopArgusAction,
  type ActionResult,
} from "@/lib/actions/control";
import { pauseNewEntriesAction } from "@/lib/actions/paper";

function Feedback({ result }: { result: ActionResult | null }) {
  if (!result) return null;
  return (
    <p className={`control-feedback ${result.ok ? "ok" : "err"}`} role="status">
      {result.message}
    </p>
  );
}

export function CommandStatusBar({
  argusStatus,
  tradingMode,
  connectionLabel,
  connectionOk,
  lastHeartbeat,
  portfolioId,
  pauseNewEntries,
  buildId,
}: {
  argusStatus: "Running" | "Paused" | "Stopped" | "Warning";
  tradingMode: "Paper" | "Live";
  connectionLabel: string;
  connectionOk: boolean;
  lastHeartbeat: string;
  portfolioId: string | null;
  pauseNewEntries: boolean;
  buildId: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionResult | null>(null);

  function run(action: () => Promise<ActionResult>, reloadHome = false) {
    setResult(null);
    startTransition(async () => {
      const res = await action();
      setResult(res);
      router.refresh();
      if (reloadHome && res.ok) {
        window.setTimeout(() => window.location.assign("/today"), 8000);
      }
    });
  }

  return (
    <section className="panel command-status-bar" aria-label="Argus command status">
      <div className="command-status-grid">
        <div>
          <div className="metric-label">Argus</div>
          <div className={`command-pill command-pill-${argusStatus.toLowerCase()}`}>
            {argusStatus}
          </div>
        </div>
        <div>
          <div className="metric-label">Trading mode</div>
          <div
            className={`command-pill ${tradingMode === "Paper" ? "command-pill-paper" : "command-pill-live"}`}
          >
            {tradingMode}
          </div>
          <p className="muted-note" style={{ margin: "0.25rem 0 0" }}>
            {tradingMode === "Paper"
              ? "Paper funds only — not real money."
              : "Live mode requires existing authorization."}
          </p>
        </div>
        <div>
          <div className="metric-label">Broker / data</div>
          <div
            className={`command-pill ${connectionOk ? "command-pill-running" : "command-pill-warning"}`}
          >
            {connectionLabel}
          </div>
        </div>
        <div>
          <div className="metric-label">Last heartbeat</div>
          <strong>{lastHeartbeat}</strong>
          <p className="muted-note" style={{ margin: "0.25rem 0 0" }}>
            Build {buildId}
          </p>
        </div>
      </div>

      <div className="command-actions">
        <button
          type="button"
          className="btn control-btn control-btn-start"
          disabled={pending}
          onClick={() => run(() => startArgusAction(), true)}
        >
          {pending ? "Working…" : "Start Argus"}
        </button>
        <button
          type="button"
          className="btn secondary control-btn"
          disabled={pending || !portfolioId}
          title="Blocks new paper entries. Open positions can still be monitored and exited."
          onClick={() => {
            if (!portfolioId) return;
            run(() => pauseNewEntriesAction(portfolioId, !pauseNewEntries));
          }}
        >
          {pauseNewEntries ? "Resume New Trades" : "Pause New Trades"}
        </button>
        <button
          type="button"
          className="btn control-btn control-btn-stop"
          disabled={pending}
          onClick={() => run(() => stopArgusAction())}
        >
          Stop Argus
        </button>
      </div>
      <Feedback result={result} />
    </section>
  );
}
