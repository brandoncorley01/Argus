"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  refreshRecentPricesAction,
  runMarketScanAction,
} from "@/lib/actions/paper";

/** One prominent live statement: what Argus is doing right now. */
export function WhatArgusIsDoing({
  headline,
  currentMarket,
  scanned,
  total,
  possibleTrades,
  lastScanLabel,
  nextScanLabel,
  latestPriceLabel,
  nextStep,
  openPositions,
}: {
  headline: string;
  currentMarket: string | null;
  scanned: number;
  total: number;
  possibleTrades: number;
  lastScanLabel: string;
  nextScanLabel: string;
  latestPriceLabel: string;
  nextStep: string | null;
  openPositions: number;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const progress =
    total > 0 ? Math.min(100, Math.round((scanned / total) * 100)) : 0;

  return (
    <section className="panel what-argus-doing rise" aria-label="What Argus is doing">
      <div className="metric-label">What is Argus doing now?</div>
      <p className="what-argus-headline">{headline}</p>

      <div className="argus-now-meta">
        <div>
          <span className="metric-label">Current market</span>
          <strong>{currentMarket ?? "None yet"}</strong>
        </div>
        <div>
          <span className="metric-label">Markets scanned</span>
          <strong>
            {scanned}
            {total ? ` of ${total}` : ""}
          </strong>
        </div>
        <div>
          <span className="metric-label">Possible trades found</span>
          <strong>{possibleTrades}</strong>
        </div>
        <div>
          <span className="metric-label">Open paper trades</span>
          <strong>{openPositions}</strong>
        </div>
        <div>
          <span className="metric-label">Last completed scan</span>
          <strong>{lastScanLabel}</strong>
        </div>
        <div>
          <span className="metric-label">Next scan</span>
          <strong>{nextScanLabel}</strong>
        </div>
        <div>
          <span className="metric-label">Latest market-price update</span>
          <strong>{latestPriceLabel}</strong>
        </div>
      </div>

      {total > 0 ? (
        <div className="scan-progress" aria-label="Scan progress">
          <div className="scan-progress-bar" style={{ width: `${progress}%` }} />
          <span className="muted-note">
            Scan progress: {progress}% ({scanned} of {total} markets)
          </span>
        </div>
      ) : null}

      {nextStep ? (
        <p className="attention-box" role="status">
          {nextStep}
        </p>
      ) : null}

      <div className="what-argus-actions">
        <button
          type="button"
          className="btn control-btn control-btn-start"
          disabled={pending}
          onClick={() => {
            setMessage(null);
            startTransition(async () => {
              const res = await refreshRecentPricesAction();
              setMessage(res.message);
              router.refresh();
            });
          }}
        >
          {pending ? "Working…" : "Refresh recent prices"}
        </button>
        <button
          type="button"
          className="btn secondary"
          disabled={pending}
          onClick={() => {
            setMessage(null);
            startTransition(async () => {
              const res = await runMarketScanAction(true);
              setMessage(res.message);
              router.refresh();
            });
          }}
        >
          Scan markets now
        </button>
      </div>
      <p className="muted-note" style={{ margin: "0.5rem 0 0" }}>
        Paper practice only — these actions never spend real money.
      </p>
      {message ? (
        <p className="control-feedback ok" role="status">
          {message}
        </p>
      ) : null}
    </section>
  );
}
