/** Founder-facing trading activity labels — display only. */

export type ActivityKind =
  | "stopped"
  | "paused"
  | "waiting"
  | "holding"
  | "trading_today";

export function deriveActivity(opts: {
  running: boolean;
  paperPaused: boolean;
  openPositions: number;
  fillsToday: number;
  openOrders: number;
}): { kind: ActivityKind; title: string; detail: string } {
  if (!opts.running) {
    return {
      kind: "stopped",
      title: "Not running",
      detail: "Press Start Argus. Paper trading is offline until then.",
    };
  }
  if (opts.paperPaused) {
    return {
      kind: "paused",
      title: "Paper trading paused",
      detail: "Argus is up, but it will not place or manage paper trades while paused.",
    };
  }
  if (opts.fillsToday > 0 || opts.openOrders > 0) {
    return {
      kind: "trading_today",
      title: "Trading today",
      detail:
        opts.openOrders > 0
          ? `Paper book is active with ${opts.openOrders} open order(s) and ${opts.fillsToday} fill(s) today.`
          : `Paper book is active. ${opts.fillsToday} fill(s) recorded today.`,
    };
  }
  if (opts.openPositions > 0) {
    return {
      kind: "holding",
      title: "Holding positions",
      detail:
        "Paper trading is active. Argus is holding open positions; no new fills yet today.",
    };
  }
  return {
    kind: "waiting",
    title: "Waiting for trades",
    detail:
      "Paper trading is active. No open positions and no fills yet today — Argus is ready when signals fire.",
  };
}

export function isSameUtcDay(iso: string | null | undefined, now = new Date()): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return false;
  return (
    d.getUTCFullYear() === now.getUTCFullYear() &&
    d.getUTCMonth() === now.getUTCMonth() &&
    d.getUTCDate() === now.getUTCDate()
  );
}
