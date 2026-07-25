/** Map real audit/ops/paper events into plain-language Founder activity. */

export type FounderActivityItem = {
  id: string;
  at: string;
  title: string;
  detail: string;
  tone: "info" | "ok" | "warn" | "bad";
};

type AuditLike = {
  id: string;
  occurred_at: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  payload?: Record<string, unknown> | null;
};

type OpsLike = {
  id: string;
  occurred_at: string;
  component: string;
  severity: string;
  description: string;
};

type FillLike = {
  id?: string;
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  filled_at: string;
};

function auditTitle(action: string): { title: string; tone: FounderActivityItem["tone"] } {
  switch (action) {
    case "paper.order.submit":
      return { title: "Paper order submitted", tone: "info" };
    case "paper.order.cancel":
      return { title: "Paper order cancelled", tone: "warn" };
    case "paper.kill_switch":
      return { title: "Paper kill switch changed", tone: "warn" };
    case "paper.pause_new_entries":
      return { title: "Pause new entries changed", tone: "warn" };
    case "paper.session.open":
      return { title: "Paper session opened", tone: "info" };
    case "paper.risk_limit.create":
      return { title: "Risk limit added", tone: "info" };
    case "paper.report.create":
      return { title: "Paper report created", tone: "ok" };
    case "operations.daily_report.generate":
      return { title: "Daily report generated", tone: "ok" };
    case "market.ingest.batch":
      return { title: "Market scan / ingest completed", tone: "info" };
    case "health.status_changed":
      return { title: "Service health changed", tone: "warn" };
    case "health.heartbeat_accepted":
      return { title: "Heartbeat accepted", tone: "ok" };
    default:
      return { title: action.replaceAll(".", " · "), tone: "info" };
  }
}

export function buildFounderActivity(opts: {
  audits?: AuditLike[] | null;
  ops?: OpsLike[] | null;
  fills?: FillLike[] | null;
  limit?: number;
}): FounderActivityItem[] {
  const items: FounderActivityItem[] = [];

  for (const a of opts.audits ?? []) {
    const { title, tone } = auditTitle(a.action);
    const active = a.payload && typeof a.payload.active === "boolean" ? a.payload.active : null;
    const detailParts = [
      a.resource_type,
      a.resource_id ? `id ${a.resource_id.slice(0, 8)}…` : null,
      active === true ? "enabled" : active === false ? "cleared" : null,
    ].filter(Boolean);
    items.push({
      id: `audit-${a.id}`,
      at: a.occurred_at,
      title,
      detail: detailParts.join(" · ") || "Institutional audit event",
      tone,
    });
  }

  for (const e of opts.ops ?? []) {
    const sev = e.severity.toLowerCase();
    items.push({
      id: `ops-${e.id}`,
      at: e.occurred_at,
      title: `${e.component}: ${e.description}`,
      detail: `Severity ${e.severity}`,
      tone: sev === "critical" || sev === "high" ? "bad" : sev === "medium" ? "warn" : "info",
    });
  }

  for (const f of opts.fills ?? []) {
    items.push({
      id: `fill-${f.id ?? `${f.symbol}-${f.filled_at}`}`,
      at: f.filled_at,
      title:
        f.side === "buy"
          ? `Position opened / increased · ${f.symbol}`
          : `Position reduced / closed · ${f.symbol}`,
      detail: `${f.side === "buy" ? "Buy" : "Sell"} ${f.quantity} @ ${f.price}`,
      tone: "ok",
    });
  }

  items.sort((a, b) => +new Date(b.at) - +new Date(a.at));
  return items.slice(0, opts.limit ?? 20);
}
