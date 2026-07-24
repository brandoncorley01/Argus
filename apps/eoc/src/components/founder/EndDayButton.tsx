"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { endTradingDayAction } from "@/lib/actions/control";
import { money, pnlClass } from "@/lib/founder/simple";

export function EndDayButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [done, setDone] = useState<Awaited<ReturnType<typeof endTradingDayAction>> | null>(
    null,
  );

  if (done) {
    return (
      <div className="panel end-day-done">
        <h2>Trading day closed</h2>
        <ul className="plain-list">
          <li>
            P&amp;L:{" "}
            <span className={pnlClass(done.dailyPnl)}>{money(done.dailyPnl)}</span>
          </li>
          <li>Trades: {done.tradeCount ?? "Unavailable"}</li>
          <li>{done.reportMessage}</li>
          <li>{done.backupMessage}</li>
        </ul>
        {!done.ok ? (
          <p className="alert error" role="alert">
            Something failed — check Backup / Reports. Do not assume success.
          </p>
        ) : null}
        <div className="form-actions">
          <Link className="btn" href="/reports">
            View reports
          </Link>
          <Link className="btn secondary" href="/today">
            Home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      className="btn control-btn"
      disabled={pending}
      onClick={() => {
        startTransition(async () => {
          const res = await endTradingDayAction();
          setDone(res);
          router.refresh();
        });
      }}
    >
      {pending ? "Ending day…" : "End Trading Day"}
    </button>
  );
}
