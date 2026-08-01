"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { LiveClock } from "@/components/founder/LiveClock";
import {
  startArgusAction,
  stopArgusAction,
  type ActionResult,
} from "@/lib/actions/control";
import { pauseNewEntriesAction } from "@/lib/actions/paper";
import { formatDurationLabel } from "@/lib/format";

/** Home is server-rendered, so only a refresh can move these timestamps. */
const REFRESH_MS = 30_000;
/** Two missed refreshes: never present frozen readings as if they were live. */
const STALE_AFTER_MS = 90_000;
/** Home SSR takes several seconds; let a returning tab catch up before warning. */
const CATCH_UP_MS = 15_000;

function Feedback({ result }: { result: ActionResult | null }) {
  if (!result) return null;
  return (
    <p className={`control-feedback ${result.ok ? "ok" : "err"}`} role="status">
      {result.message}
    </p>
  );
}

type Busy = "start" | "stop" | "pause" | null;

async function fetchLiveBuildId(): Promise<string | null> {
  try {
    const res = await fetch(`/argus-build.txt?t=${Date.now()}`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const text = (await res.text()).trim();
    // File may be "live-monitor-v2.17" or "live-monitor-v2.17 abc1234"
    const token = text.split(/\s+/)[0]?.trim();
    return token || null;
  } catch {
    return null;
  }
}

export function CommandStatusBar({
  argusStatus,
  statusExplanation,
  statusFix,
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
  renderedAt,
}: {
  argusStatus: "Running" | "Paused" | "Stopped" | "Warning";
  statusExplanation: string;
  statusFix?: string | null;
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
  renderedAt: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<Busy>(null);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [staleMs, setStaleMs] = useState(0);
  const [stale, setStale] = useState(false);
  const [liveBuildId, setLiveBuildId] = useState(buildId);
  const lastRenderRef = useRef(0);
  const visibleSinceRef = useRef(0);
  const busyRef = useRef<Busy>(null);

  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  // Prefer public/argus-build.txt (written on Start) over the compile-time
  // constant so a synced tree can prove the stamp without a stale .next bundle.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const live = await fetchLiveBuildId();
      if (!cancelled && live) setLiveBuildId(live);
    };
    void load();
    const id = window.setInterval(() => {
      void load();
    }, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [renderedAt]);

  // Only a completed server render advances renderedAt, so timing it locally
  // measures real staleness without trusting the browser and API clocks to agree.
  useEffect(() => {
    lastRenderRef.current = Date.now();
    setStaleMs(0);
  }, [renderedAt]);

  useEffect(() => {
    const refresh = () => {
      if (busyRef.current) return;
      if (document.visibilityState !== "visible") return;
      router.refresh();
      void fetchLiveBuildId().then((live) => {
        if (live) setLiveBuildId(live);
      });
    };
    const id = window.setInterval(refresh, REFRESH_MS);
    // A tab left open through host sleep wakes up hours behind.
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      visibleSinceRef.current = Date.now();
      refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [router]);

  useEffect(() => {
    const id = window.setInterval(() => {
      if (!lastRenderRef.current) return;
      const age = Date.now() - lastRenderRef.current;
      setStaleMs(age);
      // Refreshes pause while hidden, so a returning tab is expected to be
      // behind until its catch-up render lands. Warning then would cry wolf.
      const catchingUp =
        visibleSinceRef.current > 0 &&
        Date.now() - visibleSinceRef.current < CATCH_UP_MS;
      setStale(age >= STALE_AFTER_MS && !catchingUp);
    }, 1_000);
    return () => window.clearInterval(id);
  }, []);

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
      <div className="command-status-top">
        <LiveClock className="argus-live-clock" />
        {argusStatus === "Running" ? (
          <span className="muted-note command-unattended">
            Stays awake until Stop — automatic sleep blocked
          </span>
        ) : null}
      </div>
      <div className="status-chip-row" aria-label="System status">
        {stale ? (
          <span
            className="status-chip tone-bad"
            title="These readings are a snapshot from the last successful page update, not live values."
          >
            <i aria-hidden />
            Not updating {formatDurationLabel(staleMs)}
          </span>
        ) : null}
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
        <span
          className="status-chip tone-neutral"
          title={`Compile-time ${buildId}; live file ${liveBuildId}`}
        >
          Build {liveBuildId}
        </span>
      </div>

      {stale ? (
        <p className="command-status-fix" role="alert">
          This page stopped updating {formatDurationLabel(staleMs)} ago. Every
          reading above is from that moment and may no longer be true. Reload
          the page, and if it stays stale check that Argus is still running.
        </p>
      ) : null}

      <p className="command-status-why" role="status">
        {statusExplanation}
      </p>
      {statusFix ? (
        <p className="command-status-fix" role="status">
          {statusFix}
        </p>
      ) : null}

      <div className="command-actions">
        <button
          type="button"
          className="btn control-btn control-btn-start"
          disabled={busy === "start" || argusStatus !== "Stopped"}
          title={
            argusStatus === "Stopped"
              ? "Start Argus"
              : "Argus is already Running. Press Stop only when you want it off."
          }
          onClick={() => run("start", () => startArgusAction(), true)}
        >
          {busy === "start"
            ? "Starting…"
            : argusStatus === "Stopped"
              ? "Start Argus"
              : "Running"}
        </button>
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
          Starting… button will show Running when Argus is up.
        </p>
      ) : null}
      <Feedback result={result} />
    </section>
  );
}
