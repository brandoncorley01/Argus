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
