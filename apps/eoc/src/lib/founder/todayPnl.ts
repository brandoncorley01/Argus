import { ARGUS_DISPLAY_TIMEZONE } from "@/lib/format";

/** YYYY-MM-DD in America/New_York — Founder learning day key. */
export function easternDateKey(value: Date | string): string {
  const d = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-CA", { timeZone: ARGUS_DISPLAY_TIMEZONE });
}

/**
 * Realized paper P&L for the current Eastern calendar day (12:00 AM → 12:00 AM).
 * Aligns with the $300 learning desk clock on Home.
 */
export function sumTodayRealizedPnl(
  trades: Array<{ realized_pnl: string | number; filled_at: string }>,
  now = new Date(),
): { pnl: number; count: number; dayKey: string } {
  const dayKey = easternDateKey(now);
  let pnl = 0;
  let count = 0;
  for (const t of trades) {
    if (!t.filled_at || easternDateKey(t.filled_at) !== dayKey) continue;
    const n = Number(t.realized_pnl);
    if (!Number.isFinite(n)) continue;
    pnl += n;
    count += 1;
  }
  return { pnl, count, dayKey };
}

export function todayPnlWindowLabel(): string {
  return "12:00 AM–12:00 AM ET";
}
