import type { HealthStatus } from "@/lib/types";

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  // Deterministic UTC string — avoids SSR/client locale hydration mismatches.
  const iso = d.toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 19)} UTC`;
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
