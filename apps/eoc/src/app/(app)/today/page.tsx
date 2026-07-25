import type { Metadata } from "next";
import Link from "next/link";

import { ActiveTrades, type PositionSummary } from "@/components/founder/ActiveTrades";
import { ActivityFeed } from "@/components/founder/ActivityFeed";
import { CommandStatusBar } from "@/components/founder/CommandStatusBar";
import { EndDayButton } from "@/components/founder/EndDayButton";
import { EmptyState, Panel } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { ARGUS_UI_BUILD } from "@/lib/build";
import { buildFounderActivity } from "@/lib/founder/activityFeed";
import { money, pnlClass } from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";
import { apiFetch } from "@/lib/server/api";
import {
  getAuditEvents,
  getMicroLiveStatus,
  getProcessReady,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Home" };

type Portfolio = {
  id: string;
  name: string;
  cash_balance: string;
  reserved_cash?: string;
  kill_switch_active: boolean;
  pause_new_entries_active?: boolean;
  status: string;
};

type PortfolioSummary = {
  portfolio_id: string;
  currency: string;
  cash_balance: string;
  reserved_cash: string;
  buying_power: string;
  committed_capital: string;
  total_account_value: string;
  open_position_count: number;
  kill_switch_active: boolean;
  pause_new_entries_active: boolean;
  status: string;
};

type ProviderRow = {
  provider: { provider_key: string; display_name: string; is_default: boolean };
  health: {
    status: string;
    last_success_at: string | null;
    last_error: string | null;
  } | null;
};

type SystemHealth = {
  overall_status: string;
  generated_at?: string;
  paper?: { last_paper_order_at?: string | null };
  runtime_monitor?: Record<string, { status: string; detail: string }>;
};

type DailyReport = {
  report_date: string;
  content?: {
    daily_pnl?: string | null;
    trade_count?: number;
    win_rate?: string | null;
    largest_winner?: string | null;
    largest_loser?: string | null;
    exposure?: string | null;
    risk_events_count?: number;
  };
};

type Fill = {
  id: string;
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  filled_at: string;
};

type OpsEvent = {
  id: string;
  occurred_at: string;
  component: string;
  severity: string;
  description: string;
};

function Tip({ text }: { text: string }) {
  return (
    <span className="info-tip" title={text} aria-label={text}>
      ?
    </span>
  );
}

function deriveArgusStatus(opts: {
  apiReady: boolean;
  pauseNewEntries: boolean;
  killSwitch: boolean;
  healthWarning: boolean;
}): "Running" | "Paused" | "Stopped" | "Warning" {
  if (!opts.apiReady) return "Stopped";
  if (opts.killSwitch) return "Warning";
  if (opts.pauseNewEntries) return "Paused";
  if (opts.healthWarning) return "Warning";
  return "Running";
}

export default async function TodayPage() {
  await requireUser();

  const [ready, microLive, portfolios, reports, providers, health, audits, ops] =
    await Promise.all([
      soft(getProcessReady),
      soft(getMicroLiveStatus),
      soft(() => apiFetch<Portfolio[]>("/api/v1/paper/portfolios")),
      soft(() =>
        apiFetch<DailyReport[]>("/api/v1/operations/daily-reports", {
          searchParams: { limit: 1 },
        }),
      ),
      soft(() => apiFetch<ProviderRow[]>("/api/v1/paper/providers")),
      soft(() => apiFetch<SystemHealth>("/api/v1/operations/system-health")),
      soft(() => getAuditEvents({ limit: 30 })),
      soft(() =>
        apiFetch<OpsEvent[]>("/api/v1/operations/events", {
          searchParams: { limit: 30 },
        }),
      ),
    ]);

  const portfolio = portfolios?.[0] ?? null;
  let summary: PortfolioSummary | null = null;
  let positions: PositionSummary[] = [];
  let fills: Fill[] = [];
  if (portfolio) {
    const [s, p, f] = await Promise.all([
      soft(() =>
        apiFetch<PortfolioSummary>(`/api/v1/paper/portfolios/${portfolio.id}/summary`),
      ),
      soft(() =>
        apiFetch<PositionSummary[]>(
          `/api/v1/paper/portfolios/${portfolio.id}/position-summaries`,
        ),
      ),
      soft(() =>
        apiFetch<Fill[]>(`/api/v1/paper/portfolios/${portfolio.id}/fills`),
      ),
    ]);
    summary = s;
    positions = p ?? [];
    fills = f ?? [];
  }

  const defaultProvider =
    providers?.find((p) => p.provider.is_default) ?? providers?.[0] ?? null;
  const connectionOk =
    (defaultProvider?.health?.status ?? "").toLowerCase() === "healthy" ||
    (defaultProvider?.provider.provider_key ?? "").includes("paper");
  const connectionLabel = defaultProvider
    ? `${defaultProvider.provider.display_name}: ${defaultProvider.health?.status ?? "unknown"}`
    : ready
      ? "Internal paper ready"
      : "Disconnected";

  const pauseNewEntries = Boolean(
    summary?.pause_new_entries_active ?? portfolio?.pause_new_entries_active,
  );
  const killSwitch = Boolean(
    summary?.kill_switch_active ?? portfolio?.kill_switch_active,
  );
  const healthWarning =
    (health?.overall_status ?? "").toLowerCase() === "degraded" ||
    (health?.overall_status ?? "").toLowerCase() === "unhealthy";

  const argusStatus = deriveArgusStatus({
    apiReady: ready != null,
    pauseNewEntries,
    killSwitch,
    healthWarning,
  });

  const liveLocked =
    microLive?.live_execution_active === false ||
    microLive?.activation_state === "PAPER_ONLY" ||
    microLive == null;
  const tradingMode: "Paper" | "Live" = liveLocked ? "Paper" : "Live";

  const lastHeartbeat =
    formatTimestamp(
      defaultProvider?.health?.last_success_at ??
        health?.generated_at ??
        health?.paper?.last_paper_order_at ??
        null,
    ) || "Unavailable";

  const report = reports?.[0]?.content;
  const realizedToday = report?.daily_pnl ?? null;
  const unrealizedToday = positions.reduce(
    (s, p) => s + (Number(p.unrealized_pnl) || 0),
    0,
  );

  const activity = buildFounderActivity({
    audits: audits?.items ?? [],
    ops: ops ?? [],
    fills: fills.slice(0, 12),
    limit: 20,
  });

  const closedSells = fills.filter((f) => f.side === "sell").slice(0, 5);

  const exposure = report?.exposure ?? summary?.committed_capital ?? null;
  const riskEvents = report?.risk_events_count;

  return (
    <div className="founder-home command-center">
      <header className="page-header rise">
        <div>
          <h1>Command Center</h1>
          <p>
            Operating picture for paper trading. Live unlock still requires the
            existing authorization path — not from this page.
          </p>
        </div>
      </header>

      <CommandStatusBar
        argusStatus={argusStatus}
        tradingMode={tradingMode}
        connectionLabel={connectionLabel}
        connectionOk={Boolean(connectionOk && ready)}
        lastHeartbeat={lastHeartbeat}
        portfolioId={portfolio?.id ?? null}
        pauseNewEntries={pauseNewEntries}
        buildId={ARGUS_UI_BUILD}
      />

      <section className="panel rise" aria-label="Account summary">
        <h2 style={{ marginTop: 0 }}>
          Account summary{" "}
          <span className="mode-tag mode-tag-paper">PAPER</span>
        </h2>
        {!summary ? (
          <EmptyState>
            {ready
              ? "No paper portfolio available yet."
              : "Argus is stopped. Start Argus to load paper account figures."}
          </EmptyState>
        ) : (
          <div className="summary-grid">
            <div className="summary-card">
              <span className="metric-label">
                Total account value <Tip text="Paper cash plus capital committed to open positions (cost basis)." />
              </span>
              <strong>{money(summary.total_account_value)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Available cash</span>
              <strong>{money(summary.cash_balance)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                In open trades <Tip text="Sum of |qty| × average cost for open paper positions." />
              </span>
              <strong>{money(summary.committed_capital)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                Buying power <Tip text="Cash balance minus reserved cash." />
              </span>
              <strong>{money(summary.buying_power)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Today realized P&amp;L</span>
              <strong className={pnlClass(realizedToday)}>{money(realizedToday)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                Open unrealized P&amp;L{" "}
                <Tip text="From paper position books. Stays near zero until marks are maintained." />
              </span>
              <strong className={pnlClass(unrealizedToday)}>{money(unrealizedToday)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Open positions</span>
              <strong>{summary.open_position_count}</strong>
            </div>
          </div>
        )}
      </section>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Active trades">
          <ActiveTrades positions={positions} />
        </Panel>
        <Panel title="Live Argus activity">
          <ActivityFeed initialItems={activity} />
        </Panel>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Performance & risk">
          <div className="summary-grid summary-grid-compact">
            <div className="summary-card">
              <span className="metric-label">Trades completed today</span>
              <strong>{report?.trade_count ?? "Unavailable"}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Win rate</span>
              <strong>
                {report?.win_rate == null ? "Unavailable" : `${report.win_rate}`}
              </strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                Largest winner{" "}
                <Tip text="Average win is not stored yet; showing largest winner from today’s report when present." />
              </span>
              <strong className={pnlClass(report?.largest_winner)}>
                {report?.largest_winner == null
                  ? "Unavailable"
                  : money(report.largest_winner)}
              </strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                Largest loser{" "}
                <Tip text="Average loss is not stored yet; showing largest loser from today’s report when present." />
              </span>
              <strong className={pnlClass(report?.largest_loser)}>
                {report?.largest_loser == null
                  ? "Unavailable"
                  : money(report.largest_loser)}
              </strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Portfolio exposure</span>
              <strong>{exposure == null ? "Unavailable" : money(exposure)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Risk events today</span>
              <strong>{riskEvents ?? "Unavailable"}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Daily risk allowance remaining</span>
              <strong>Unavailable</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Consecutive losses / drawdown</span>
              <strong>Unavailable</strong>
            </div>
          </div>
          <p className="muted-note" style={{ marginBottom: 0 }}>
            Charting is omitted until a verified equity series exists. Metrics stay
            Unavailable instead of inventing values.
          </p>
        </Panel>

        <Panel title="Recent completed trades">
          {closedSells.length === 0 ? (
            <EmptyState>
              No recent sell fills. Closed-trade entry/exit pairing is limited to
              real fill history.
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Exit price</th>
                    <th>Qty</th>
                    <th>When</th>
                    <th>Entry / P&amp;L / reason</th>
                  </tr>
                </thead>
                <tbody>
                  {closedSells.map((f) => (
                    <tr key={f.id}>
                      <td>{f.symbol}</td>
                      <td>{money(f.price)}</td>
                      <td>{f.quantity}</td>
                      <td>{formatTimestamp(f.filled_at)}</td>
                      <td>Unavailable</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="form-actions" style={{ marginTop: "0.75rem" }}>
            <Link className="btn secondary" href="/trading">
              Trading history
            </Link>
            <Link className="btn secondary" href="/reports">
              Full reports
            </Link>
          </div>
        </Panel>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <Panel title="End of day">
          <p style={{ color: "var(--ink-soft)", marginTop: 0 }}>
            Saves today&apos;s report and backup. Does not stop Argus.
          </p>
          <EndDayButton />
        </Panel>
      </div>
    </div>
  );
}
