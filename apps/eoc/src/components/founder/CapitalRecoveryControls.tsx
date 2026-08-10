"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  digOutLearningDeskAction,
  reseedLearningDeskAction,
} from "@/lib/actions/paper";

/**
 * Founder controls: Dig out with remaining cash, or Reseed to $300.
 * Reseed count is a failure signal — prefer dig-out when cash remains.
 */
export function CapitalRecoveryControls({
  portfolioId,
  cashAvailable,
  reseedCount = 0,
  digOutCount = 0,
  recoveryLevel = "ok",
  recoveryNote = null,
  compact = false,
}: {
  portfolioId: string;
  cashAvailable?: number | null;
  reseedCount?: number;
  digOutCount?: number;
  recoveryLevel?: string;
  recoveryNote?: string | null;
  compact?: boolean;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const cash = cashAvailable;
  const canDigOut =
    cash == null ? true : Number.isFinite(cash) && cash >= 5;

  return (
    <div
      className={compact ? "capital-recovery compact" : "capital-recovery"}
      aria-label="Paper capital recovery"
    >
      {!compact ? (
        <>
          <h3 style={{ marginTop: 0 }}>Capital recovery</h3>
          <p className="muted-note">
            Dig out keeps the remaining paper cash and shrinks trade size so Argus
            can try to recover. Reseed resets to $300 — counted as a major recovery
            event. Frequent reseeds mean Argus is failing overall.
          </p>
        </>
      ) : null}

      <div className="summary-grid summary-grid-primary" style={{ marginBottom: "0.65rem" }}>
        <div className="summary-card">
          <span className="metric-label">Reseeds</span>
          <strong>{reseedCount}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Dig-outs</span>
          <strong>{digOutCount}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Recovery pressure</span>
          <strong>{recoveryLevel}</strong>
        </div>
      </div>

      {recoveryNote ? (
        <p
          className={
            recoveryLevel === "critical" || recoveryLevel === "elevated"
              ? "attention-box"
              : "muted-note"
          }
          role="status"
        >
          {recoveryNote}
        </p>
      ) : null}

      <div className="form-actions" style={{ marginTop: "0.65rem", gap: "0.5rem" }}>
        <button
          type="button"
          className="btn"
          disabled={pending || !canDigOut}
          title={
            canDigOut
              ? "Shrink entry size and keep practicing with remaining cash"
              : "Need at least $5 cash to dig out — reseed instead"
          }
          onClick={() => {
            startTransition(async () => {
              const res = await digOutLearningDeskAction(portfolioId);
              setMessage(res.message);
              router.refresh();
            });
          }}
        >
          Dig out with remaining cash
        </button>
        <button
          type="button"
          className="btn secondary"
          disabled={pending}
          title="Flatten open paper risk and reset to $300 practice cash"
          onClick={() => {
            if (
              !window.confirm(
                `Reseed the learning desk to $300?\n\nThis counts as reseed #${reseedCount + 1}. Frequent reseeds mean Argus is not recovering.`,
              )
            ) {
              return;
            }
            startTransition(async () => {
              const res = await reseedLearningDeskAction(portfolioId);
              setMessage(res.message);
              router.refresh();
            });
          }}
        >
          Reseed to $300
        </button>
      </div>
      {message ? (
        <p className="control-feedback ok" role="status" style={{ marginTop: "0.5rem" }}>
          {message}
        </p>
      ) : null}
    </div>
  );
}
