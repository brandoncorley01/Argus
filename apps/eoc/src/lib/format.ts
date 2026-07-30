import type { HealthStatus } from "@/lib/types";

/** Founder-facing clock — US Eastern (EST/EDT). Fixed zone keeps SSR/client HTML aligned. */
export const ARGUS_DISPLAY_TIMEZONE = "America/New_York";

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-US", {
    timeZone: ARGUS_DISPLAY_TIMEZONE,
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
    timeZoneName: "short",
  });
}

/** Compact live clock for the Home header / status bar (ticks every second). */
export function formatLiveClock(ms: number | Date): string {
  const d = typeof ms === "number" ? new Date(ms) : ms;
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    timeZone: ARGUS_DISPLAY_TIMEZONE,
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
    timeZoneName: "short",
  });
}

/** Relative age that updates every second — “12s ago”, “3m ago”. */
export function formatAgeLabel(
  iso: string | null | undefined,
  nowMs: number | null,
): string {
  if (!iso || nowMs == null) return "—";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "—";
  const age = Math.max(0, Math.floor((nowMs - t) / 1000));
  if (age < 60) return `${age}s ago`;
  if (age < 3600) return `${Math.floor(age / 60)}m ${age % 60}s ago`;
  const h = Math.floor(age / 3600);
  const m = Math.floor((age % 3600) / 60);
  return `${h}h ${m}m ago`;
}

export function healthTone(
  status: HealthStatus | string | null | undefined,
): "ok" | "warn" | "bad" | "muted" {
  const s = (status ?? "").toLowerCase();
  if (s === "healthy" || s === "ok") return "ok";
  if (s === "degraded") return "warn";
  if (s === "unhealthy") return "bad";
  return "muted";
}

export function emptyMessage(noun: string): string {
  return `No ${noun} returned by the control plane.`;
}
