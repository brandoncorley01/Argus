"use client";

import { useState, useTransition } from "react";

import {
  generateDailyReportAction,
  type ActionResult,
} from "@/lib/actions/operations";

/** Founder/Operator control to generate yesterday's (or chosen) paper daily report. */
export function GenerateDailyReportForm() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await generateDailyReportAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
      style={{ display: "grid", gap: "0.65rem", maxWidth: "28rem" }}
    >
      <p style={{ margin: 0, color: "var(--ink-soft)", fontSize: "0.92rem" }}>
        Generates an immutable Internal Paper daily report. Defaults to yesterday
        UTC when the date is left blank. Does not enable live trading.
      </p>
      {result ? (
        <div
          className={`alert ${result.ok ? "ok" : "error"}`}
          role="status"
        >
          {result.message}
        </div>
      ) : null}
      <div className="field">
        <label htmlFor="report_date">Report date (optional)</label>
        <input id="report_date" name="report_date" type="date" disabled={pending} />
      </div>
      <button className="btn" type="submit" disabled={pending}>
        {pending ? "Generating…" : "Generate daily report"}
      </button>
    </form>
  );
}
