/** Turn system-health payloads into Founder-facing status copy. */

export type HealthServiceRow = {
  service_key: string;
  display_name?: string;
  status: string;
  detail?: string | null;
  criticality?: string;
};

export type SystemHealthLite = {
  overall_status?: string;
  services?: HealthServiceRow[];
  institutional_health?: {
    status?: string;
    summary?: {
      services?: Array<{
        service_key?: string;
        status?: string;
        detail?: string | null;
        criticality?: string;
      }>;
    };
  } | null;
  runtime_monitor?: Record<string, { status?: string; detail?: string }>;
  active_alerts?: Array<{
    severity?: string;
    component?: string;
    description?: string;
  }>;
  readiness?: { postgres?: boolean; redis?: boolean };
};

const SERVICE_LABEL: Record<string, string> = {
  api: "Argus API",
  postgres: "PostgreSQL database",
  redis: "Redis queue",
  health_supervisor: "Health Supervisor",
  market_ops: "Market Ops worker (scans + paper exits)",
};

const SERVICE_FIX: Record<string, string> = {
  market_ops:
    "Fix: press Stop Argus, wait a few seconds, then press Start Argus once. That restarts Market Ops so paper scans and stop-losses run again.",
  health_supervisor:
    "Fix: press Stop Argus, then Start Argus once so the Health Supervisor comes back.",
  api: "Fix: press Start Argus. If it stays down, check that nothing else is using port 8000.",
  postgres:
    "Fix: start Docker Desktop, then press Start Argus so Postgres comes back.",
  redis:
    "Fix: start Docker Desktop, then press Start Argus so Redis comes back.",
};

function labelFor(key: string, displayName?: string | null): string {
  return displayName?.trim() || SERVICE_LABEL[key] || key;
}

function collectBadServices(health: SystemHealthLite | null | undefined): Array<{
  key: string;
  label: string;
  status: string;
  detail: string;
}> {
  if (!health) return [];
  const out: Array<{ key: string; label: string; status: string; detail: string }> =
    [];
  const seen = new Set<string>();

  const push = (
    key: string,
    status: string,
    detail: string | null | undefined,
    displayName?: string | null,
  ) => {
    const s = (status || "").toLowerCase();
    if (s !== "unhealthy" && s !== "degraded" && s !== "failed" && s !== "unknown") {
      return;
    }
    if (!key || seen.has(key)) return;
    seen.add(key);
    out.push({
      key,
      label: labelFor(key, displayName),
      status: s,
      detail: (detail && detail.trim()) || "no detail reported",
    });
  };

  for (const row of health.services ?? []) {
    push(row.service_key, row.status, row.detail, row.display_name);
  }

  for (const row of health.institutional_health?.summary?.services ?? []) {
    if (row.service_key) {
      push(row.service_key, row.status ?? "", row.detail, null);
    }
  }

  for (const [key, probe] of Object.entries(health.runtime_monitor ?? {})) {
    push(key, probe.status ?? "", probe.detail, null);
  }

  if (health.readiness?.postgres === false) {
    push("postgres", "unhealthy", "not ready", null);
  }
  if (health.readiness?.redis === false) {
    push("redis", "unhealthy", "not ready", null);
  }

  return out;
}

/**
 * Specific, actionable explanation when overall health is degraded/unhealthy.
 */
export function explainHealthWarning(
  health: SystemHealthLite | null | undefined,
): { explanation: string; fix: string | null } {
  const bad = collectBadServices(health);
  if (bad.length === 0) {
    const alert = health?.active_alerts?.[0];
    if (alert?.description) {
      return {
        explanation: `System health is ${health?.overall_status ?? "degraded"}: ${alert.description}. Trading rules still apply.`,
        fix: "Open Advanced → System health for the full list, or press Stop then Start Argus once.",
      };
    }
    return {
      explanation:
        "System health reports a warning, but no single service was named. Trading rules still apply.",
      fix: "Open Advanced → System health, or press Stop then Start Argus once.",
    };
  }

  const top = bad[0]!;
  const extras =
    bad.length > 1
      ? ` Also: ${bad
          .slice(1, 3)
          .map((b) => `${b.label} (${b.status})`)
          .join("; ")}.`
      : "";

  const explanation = `${top.label} is ${top.status} — ${top.detail}.${extras} Paper trading rules still apply.`;
  const fix =
    SERVICE_FIX[top.key] ??
    "Fix: press Stop Argus, then Start Argus once. If it returns, open Advanced → System health.";

  return { explanation, fix };
}
