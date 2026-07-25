"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

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

type Busy = "start" | "stop" | "pause" | null;

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
  const [busy, setBusy] = useState<Busy>(null);
  const [result, setResult] = useState<ActionResult | null>(null);

  async function run(
    kind: Busy,
    action: () => Promise<ActionResult>,
    reloadHome = false,
  ) {
    if (busy) return;
    setBusy(kind);
    setResult(null);
    try {
      const res = await action();
      setResult(res);
      router.refresh();
      if (reloadHome && res.ok) {
        window.setTimeout(() => window.location.assign("/today"), 3000);
      }
    } catch (err) {
      setResult({
        ok: false,
        message:
          err instanceof Error
            ? err.message
            : "Start did not finish. Refresh this page, then try again.",
      });
    } finally {
      setBusy(null);
    }
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
          disabled={busy === "start"}
          onClick={() => run("start", () => startArgusAction(), true)}
        >
          {busy === "start" ? "Starting…" : "Start Argus"}
        </button>
        <button
          type="button"
          className="btn secondary control-btn"
          disabled={busy !== null || !portfolioId}
          title="Blocks new paper entries. Open positions can still be monitored and exited."
          onClick={() => {
            if (!portfolioId) return;
            void run("pause", () =>
              pauseNewEntriesAction(portfolioId, !pauseNewEntries),
            );
          }}
        >
          {busy === "pause"
            ? "Updating…"
            : pauseNewEntries
              ? "Resume New Trades"
              : "Pause New Trades"}
        </button>
        <button
          type="button"
          className="btn control-btn control-btn-stop"
          disabled={busy === "stop"}
          title="Stop stays available even while Start is running."
          onClick={() => run("stop", () => stopArgusAction())}
        >
          {busy === "stop" ? "Stopping…" : "Stop Argus"}
        </button>
      </div>
      {busy === "start" ? (
        <p className="muted-note" role="status">
          Starting can take a few minutes. If this page never updates, press F5
          then try Start again — Stop remains available.
        </p>
      ) : null}
      <Feedback result={result} />
    </section>
  );
}
