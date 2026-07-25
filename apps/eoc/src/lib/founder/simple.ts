/** Tiny Founder-facing helpers — display only. */

export function firstName(username: string): string {
  const raw = username.trim() || "Founder";
  const local = raw.includes("@") ? raw.split("@")[0]! : raw;
  const token = local.split(/[._-]/)[0] || local;
  return token.charAt(0).toUpperCase() + token.slice(1);
}

export function greeting(name: string, now = new Date()): string {
  const h = now.getHours();
  const part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  return `${part}, ${name}`;
}

export function money(value: string | number | null | undefined): string {
  if (value == null || value === "") return "Unavailable";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "Unavailable";
  const abs = Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (n > 0) return `+${abs}`;
  if (n < 0) return `-${abs}`;
  return abs;
}

export function pnlClass(value: string | number | null | undefined): string {
  if (value == null || value === "") return "pnl-flat";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n === 0) return "pnl-flat";
  return n > 0 ? "pnl-up" : "pnl-down";
}

export function direction(qty: string | number): string {
  const n = typeof qty === "number" ? qty : Number(qty);
  if (!Number.isFinite(n) || n === 0) return "Flat";
  return n > 0 ? "Long" : "Short";
}

export type SimpleStatus = "Running" | "Stopped" | "Attention";

/**
 * Founder Home status must match Start/Stop + Paper.
 * Running = Argus is up. Stopped = not up. Attention = paper paused only.
 * Never use stale alerts/incidents/worker noise for this label.
 */
export function deriveStatus(opts: {
  apiReady: boolean | null;
  paperPaused: boolean;
  criticalAlerts?: number;
  workerFailed?: boolean;
}): SimpleStatus {
  if (opts.apiReady === false || opts.apiReady == null) return "Stopped";
  if (opts.paperPaused) return "Attention";
  return "Running";
}
