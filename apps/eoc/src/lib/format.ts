import type { HealthStatus } from "@/lib/types";

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
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
