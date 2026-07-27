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
  statusExplanation,
  tradingMode,
  connectionLabel,
  connectionOk,
  lastHeartbeat,
  scannerState,
  marketDataLabel,
  lastScanLabel,
  lastDecisionLabel,
  portfolioId,
  pauseNewEntries,
  buildId,
}: {
  argusStatus: "Running" | "Paused" | "Stopped" | "Warning";
  statusExplanation: string;
  tradingMode: "Paper" | "Live";
  connectionLabel: string;
  connectionOk: boolean;
  lastHeartbeat: string;
  scannerState: string;
  marketDataLabel: string;
  lastScanLabel: string;
  lastDecisionLabel: string;
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

  const feedOutdated = marketDataLabel.toLowerCase().includes("outdated");

  return (
    <section className="panel command-status-bar" aria-label="Argus command status">
      <div className="status-chip-row" aria-label="System status">
        <span
          className={`status-chip tone-${
            argusStatus === "Running"
              ? "ok"
              : argusStatus === "Warning"
                ? "warn"
                : argusStatus === "Paused"
                  ? "warn"
                  : "bad"
          }`}
          title={statusExplanation}
        >
          <i aria-hidden />
          {argusStatus}
        </span>
        <span
          className={`status-chip tone-${tradingMode === "Paper" ? "neutral" : "warn"}`}
        >
          {tradingMode}
        </span>
        <span className={`status-chip tone-${connectionOk ? "ok" : "bad"}`}>
          {connectionLabel}
        </span>
        <span className={`status-chip tone-${feedOutdated ? "bad" : "ok"}`}>
          Feed {marketDataLabel}
        </span>
        <span className="status-chip tone-neutral">Scan {scannerState}</span>
        <span className="status-chip tone-neutral">Last scan {lastScanLabel}</span>
        <span className="status-chip tone-neutral" title={lastDecisionLabel}>
          Beat {lastHeartbeat}
        </span>
        <span className="status-chip tone-neutral">Build {buildId}</span>
      </div>

      <div className="command-actions">
        {argusStatus === "Stopped" ? (
          <button
            type="button"
            className="btn control-btn control-btn-start"
            disabled={busy === "start"}
            onClick={() => run("start", () => startArgusAction(), true)}
          >
            {busy === "start" ? "Starting…" : "Start Argus"}
          </button>
        ) : (
          <span className="muted-note" role="status" style={{ alignSelf: "center" }}>
            Argus stays Running until you press Stop.
          </span>
        )}
        <button
          type="button"
          className="btn secondary control-btn"
          disabled={busy !== null || !portfolioId || argusStatus === "Stopped"}
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
              ? "Resume entries"
              : "Pause entries"}
        </button>
        <button
          type="button"
          className="btn control-btn control-btn-stop"
          disabled={busy === "stop" || argusStatus === "Stopped"}
          title="Stops API and worker. Paper data is kept. Use only when you want Argus off."
          onClick={() => run("stop", () => stopArgusAction())}
        >
          {busy === "stop" ? "Stopping…" : "Stop Argus"}
        </button>
      </div>
      {busy === "start" ? (
        <p className="muted-note" role="status">
          Starting… Argus will stay up until you press Stop.
        </p>
      ) : null}
      <Feedback result={result} />
    </section>
  );
}
