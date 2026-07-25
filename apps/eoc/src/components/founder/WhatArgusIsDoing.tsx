"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { runMarketScanAction } from "@/lib/actions/paper";

/** One sentence: what Argus is doing right now. */
export function WhatArgusIsDoing({
  headline,
  scannerState,
  scanned,
  watching,
  openPositions,
  tradingAllowed,
}: {
  headline: string;
  scannerState: string;
  scanned: number;
  watching: number;
  openPositions: number;
  tradingAllowed: boolean;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);

  return (
    <section className="panel what-argus-doing rise" aria-label="What Argus is doing">
      <div className="what-argus-grid">
        <div>
          <div className="metric-label">What Argus is doing now</div>
          <p className="what-argus-headline">{headline}</p>
          <p className="muted-note" style={{ marginBottom: 0 }}>
            Scanner: <strong>{scannerState}</strong>
            {" · "}
            Last scan checked <strong>{scanned}</strong> market{scanned === 1 ? "" : "s"}
            {" · "}
            Watching <strong>{watching}</strong>
            {" · "}
            Open paper positions <strong>{openPositions}</strong>
            {" · "}
            New entries {tradingAllowed ? "allowed" : "blocked / paused"}
          </p>
        </div>
        <div className="what-argus-actions">
          <button
            type="button"
            className="btn control-btn control-btn-start"
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
            {pending ? "Scanning…" : "Scan markets now"}
          </button>
          <p className="muted-note" style={{ margin: "0.35rem 0 0" }}>
            Paper practice only — scans do not spend real money.
          </p>
        </div>
      </div>
      {message ? (
        <p className="control-feedback ok" role="status">
          {message}
        </p>
      ) : null}
    </section>
  );
}
