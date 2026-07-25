import type { Metadata } from "next";
import Link from "next/link";

import { ActiveTrades, type PositionSummary } from "@/components/founder/ActiveTrades";
import { CommandStatusBar } from "@/components/founder/CommandStatusBar";
import { DecisionPipeline } from "@/components/founder/DecisionPipeline";
import { DecisionStream } from "@/components/founder/DecisionStream";
import { EndDayButton } from "@/components/founder/EndDayButton";
import { MarketScannerPanel } from "@/components/founder/MarketScannerPanel";
import { OpportunityWorkspace } from "@/components/founder/OpportunityWorkspace";
import type { ScanCandidate } from "@/components/founder/OpportunityRadar";
import { EmptyState, Panel } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { ARGUS_UI_BUILD } from "@/lib/build";
import { buildDecisionStream } from "@/lib/founder/decisionStream";
import {
  formatWinRate,
  holdingLabel,
  money,
  moneyPnl,
  pnlClass,
} from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";
import { apiFetch } from "@/lib/server/api";
import {
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
  total_account_value_basis?: string;
  marks_complete?: boolean;
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
    order_count?: number;
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

type ClosedTrade = {
  fill_id: string;
  symbol: string;
  quantity: string;
  entry_price: string;
  exit_price: string;
  realized_pnl: string;
  filled_at: string;
  holding_seconds: number | null;
  exit_reason: string | null;
};

type ScanStatus = {
  scanner_state: string;
  cycle: {
    id: string;
    status: string;
    timeframe: string;
    strategy_key: string;
    symbols_total: number;
    symbols_scanned: number;
    candidates_found: number;
    current_symbol: string | null;
    started_at: string;
    completed_at: string | null;
    next_scheduled_at: string | null;
  } | null;
  symbols_monitored: number;
  market_data_at: string | null;
  market_data_age_seconds: number | null;
  market_data_stale: boolean;
  pause_new_entries_active: boolean;
  kill_switch_active: boolean;
  trading_allowed: boolean;
  last_decision: {
    occurred_at: string;
    title: string;
    symbol: string | null;
  } | null;
  pipeline_counts: Record<string, number>;
  rejection_counts: Record<string, number>;
  next_scheduled_at: string | null;
};

type ScanEvent = {
  id: string;
  occurred_at: string;
  symbol: string | null;
  title: string;
  detail: string;
  outcome: string;
  reason_code: string | null;
  strategy_key: string | null;
  correlation_id: string;
  component: string;
};

function Tip({ text }: { text: string }) {
  return (
    <span className="info-tip" title={text} aria-label={text}>
      ?
    </span>
  );
}

function deriveOperationalPicture(opts: {
  apiReady: boolean;
  pauseNewEntries: boolean;
  killSwitch: boolean;
  healthWarning: boolean;
  marketDataStale: boolean;
  marksIncomplete: boolean;
  scannerFailed: boolean;
}): { status: "Running" | "Paused" | "Stopped" | "Warning"; explanation: string } {
  if (!opts.apiReady) {
    return {
      status: "Stopped",
      explanation: "Argus API is not ready. Web UI may still load; trading services are down.",
    };
  }
  if (opts.killSwitch) {
    return {
      status: "Warning",
      explanation: "Paper kill switch is active — all new paper submits are blocked.",
    };
  }
  if (opts.pauseNewEntries) {
    return {
      status: "Paused",
      explanation:
        "New entries are paused. Argus can still monitor open positions and run market scans.",
    };
  }
  if (opts.scannerFailed) {
    return {
      status: "Warning",
      explanation:
        "Market scanner failed (often: no instruments registered). Heartbeat alone is not full operation.",
    };
  }
  if (opts.marketDataStale) {
    return {
      status: "Warning",
      explanation:
        "Market data is missing or stale. Positions may lack current prices; Argus is not fully market-ready.",
    };
  }
  if (opts.marksIncomplete) {
    return {
      status: "Warning",
      explanation:
        "Open positions lack verified market marks. Unrealized P&L is incomplete — not treated as zero.",
    };
  }
  if (opts.healthWarning) {
    return {
      status: "Warning",
      explanation: "System health reports degraded or unhealthy services.",
    };
  }
  return {
    status: "Running",
    explanation:
      "API is up, trading is not paused, and no active data/scanner warnings were detected.",
  };
}

export default async function TodayPage() {
  await requireUser();

  const [ready, microLive, portfolios, reports, providers, health, scanStatusInitial] =
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
      soft(() => apiFetch<ScanStatus>("/api/v1/market/scan/status")),
    ]);

  // Kick an observation-only scan when none exists yet (does not place trades).
  let scanStatus = scanStatusInitial;
  if (ready && (!scanStatus?.cycle || scanStatus.scanner_state === "Between Cycles")) {
    const ageMin =
      scanStatus?.cycle?.completed_at != null
        ? (Date.now() - Date.parse(scanStatus.cycle.completed_at)) / 60000
        : null;
    if (!scanStatus?.cycle || (ageMin != null && ageMin >= 2)) {
      await soft(() =>
        apiFetch("/api/v1/market/scan/run", {
          method: "POST",
          searchParams: { force: scanStatus?.cycle ? "false" : "true" },
          requireCsrf: true,
        }),
      );
      scanStatus =
        (await soft(() => apiFetch<ScanStatus>("/api/v1/market/scan/status"))) ??
        scanStatus;
    }
  }

  const [candidates, scanEvents] = await Promise.all([
    soft(() =>
      apiFetch<ScanCandidate[]>("/api/v1/market/scan/candidates", {
        searchParams: { limit: 5 },
      }),
    ),
    soft(() =>
      apiFetch<ScanEvent[]>("/api/v1/market/scan/events", {
        searchParams: { limit: 40 },
      }),
    ),
  ]);

  const portfolio = portfolios?.[0] ?? null;
  let summary: PortfolioSummary | null = null;
  let positions: PositionSummary[] = [];
  let fills: Fill[] = [];
  let closedTrades: ClosedTrade[] = [];
  if (portfolio) {
    const [s, p, f, c] = await Promise.all([
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
      soft(() =>
        apiFetch<ClosedTrade[]>(
          `/api/v1/paper/portfolios/${portfolio.id}/closed-trades`,
          { searchParams: { limit: 5 } },
        ),
      ),
    ]);
    summary = s;
    positions = p ?? [];
    fills = f ?? [];
    closedTrades = c ?? [];
  }

  const defaultProvider =
    providers?.find((row) => row.provider.is_default) ?? providers?.[0] ?? null;
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
  const marksIncomplete = positions.some(
    (pos) => pos.price_status === "unavailable" || pos.mark_price == null,
  );
  const marketDataStale = Boolean(scanStatus?.market_data_stale);
  const scannerFailed = scanStatus?.scanner_state === "Failed";

  const picture = deriveOperationalPicture({
    apiReady: ready != null,
    pauseNewEntries,
    killSwitch,
    healthWarning,
    marketDataStale: marketDataStale && positions.length > 0,
    marksIncomplete: marksIncomplete && positions.length > 0,
    scannerFailed: Boolean(scannerFailed && (scanStatus?.symbols_monitored ?? 0) === 0),
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

  const report = reports?.[0];
  const reportContent = report?.content;
  const realizedToday = reportContent?.daily_pnl ?? null;
  const unrealizedValues = positions
    .map((pos) => (pos.unrealized_pnl == null ? null : Number(pos.unrealized_pnl)))
    .filter((n): n is number => n != null && Number.isFinite(n));
  const unrealizedComplete =
    positions.length > 0 && unrealizedValues.length === positions.length;
  const unrealizedToday = unrealizedComplete
    ? unrealizedValues.reduce((a, b) => a + b, 0)
    : null;

  const decisions = buildDecisionStream({
    scanEvents: scanEvents ?? [],
    fills: fills.slice(0, 12),
    limit: 25,
  });
  const scannerFeed = buildDecisionStream({
    scanEvents: (scanEvents ?? []).filter((e) =>
      ["market_scanner", "strategy_evaluator"].includes(e.component),
    ),
    limit: 12,
  });

  const liveExposure = summary?.committed_capital ?? null;
  const reportExposure = reportContent?.exposure ?? null;
  const closedTodayCount = closedTrades.filter((t) => {
    const day = t.filled_at.slice(0, 10);
    const today = new Date().toISOString().slice(0, 10);
    return day === today;
  }).length;

  return (
    <div className="founder-home command-center market-command-center">
      <header className="page-header rise">
        <div>
          <h1>Market Command Center</h1>
          <p>
            Operating picture for paper trading and observation-only market scanning.
            Live unlock remains on the existing authorization path.
          </p>
        </div>
      </header>

      <CommandStatusBar
        argusStatus={picture.status}
        statusExplanation={picture.explanation}
        tradingMode={tradingMode}
        connectionLabel={connectionLabel}
        connectionOk={Boolean(connectionOk && ready)}
        lastHeartbeat={lastHeartbeat}
        scannerState={scanStatus?.scanner_state ?? "Unavailable"}
        marketDataLabel={
          scanStatus?.market_data_at
            ? `${formatTimestamp(scanStatus.market_data_at)}${
                scanStatus.market_data_stale ? " (stale)" : ""
              }`
            : "Unavailable"
        }
        lastScanLabel={
          formatTimestamp(scanStatus?.cycle?.completed_at) || "No completed scan yet"
        }
        lastDecisionLabel={
          scanStatus?.last_decision
            ? `${scanStatus.last_decision.symbol ? `${scanStatus.last_decision.symbol} · ` : ""}${scanStatus.last_decision.title}`
            : "None yet"
        }
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
          <>
            <div className="summary-grid summary-grid-primary">
              <div className="summary-card">
                <span className="metric-label">
                  Total account value{" "}
                  <Tip
                    text={
                      summary.total_account_value_basis === "mark"
                        ? "Cash plus marked market value of open positions."
                        : "Cash plus capital committed at cost basis (marks incomplete)."
                    }
                  />
                </span>
                <strong>{money(summary.total_account_value)}</strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">Available cash</span>
                <strong>{money(summary.cash_balance)}</strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">
                  Capital in open trades{" "}
                  <Tip text="Live Σ |qty| × average entry price (cost basis)." />
                </span>
                <strong>{money(summary.committed_capital)}</strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">
                  Today&apos;s realized P&amp;L{" "}
                  <Tip text="From the latest daily report (UTC calendar day of that report)." />
                </span>
                <strong className={pnlClass(realizedToday)}>
                  {moneyPnl(realizedToday)}
                </strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">
                  Today&apos;s unrealized P&amp;L{" "}
                  <Tip text="Sum of marked unrealized P&L. Unavailable unless every open position has a mark." />
                </span>
                <strong className={pnlClass(unrealizedToday)}>
                  {unrealizedToday == null ? "Unavailable" : moneyPnl(unrealizedToday)}
                </strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">Open positions</span>
                <strong>{summary.open_position_count}</strong>
              </div>
            </div>
            <details className="secondary-metrics">
              <summary>Secondary account metrics</summary>
              <div className="summary-grid summary-grid-compact">
                <div className="summary-card">
                  <span className="metric-label">
                    Buying power <Tip text="Cash balance minus reserved cash." />
                  </span>
                  <strong>{money(summary.buying_power)}</strong>
                </div>
                <div className="summary-card">
                  <span className="metric-label">Reserved cash</span>
                  <strong>{money(summary.reserved_cash)}</strong>
                </div>
              </div>
            </details>
          </>
        )}
      </section>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Active Market Scanner">
          <MarketScannerPanel status={scanStatus} feed={scannerFeed} />
        </Panel>
        <Panel title="Decision Pipeline">
          <DecisionPipeline
            counts={scanStatus?.pipeline_counts ?? {}}
            rejections={scanStatus?.rejection_counts ?? {}}
          />
        </Panel>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <OpportunityWorkspace
          candidates={candidates ?? []}
          scannedCount={scanStatus?.cycle?.symbols_scanned ?? 0}
        />
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Active trades">
          <ActiveTrades positions={positions} />
        </Panel>
        <Panel title="Argus Decision Stream">
          <DecisionStream initialItems={decisions} />
        </Panel>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Performance & risk">
          <div className="summary-grid summary-grid-compact">
            <div className="summary-card">
              <span className="metric-label">
                Closed trades (recent list){" "}
                <Tip text="Replayed sell fills with entry/exit. Not the same as daily-report fill_count." />
              </span>
              <strong>{closedTrades.length}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                Closed trades dated today{" "}
                <Tip text="Subset of closed-trade replay whose exit timestamp is UTC today." />
              </span>
              <strong>{closedTodayCount}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                Report fill count{" "}
                <Tip text="Daily report trade_count = buy+sell fills that UTC day — not round trips." />
              </span>
              <strong>{reportContent?.trade_count ?? "Unavailable"}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                Win rate{" "}
                <Tip text="From daily report: winning sell fills / sell fills that day." />
              </span>
              <strong>{formatWinRate(reportContent?.win_rate)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Largest winner</span>
              <strong className={pnlClass(reportContent?.largest_winner)}>
                {reportContent?.largest_winner == null
                  ? "Unavailable"
                  : moneyPnl(reportContent.largest_winner)}
              </strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Largest loser</span>
              <strong className={pnlClass(reportContent?.largest_loser)}>
                {reportContent?.largest_loser == null
                  ? "Unavailable"
                  : moneyPnl(reportContent.largest_loser)}
              </strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                Portfolio exposure (live){" "}
                <Tip text="Always live capital in open trades (cost basis)." />
              </span>
              <strong>{liveExposure == null ? "Unavailable" : money(liveExposure)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                Report exposure snapshot{" "}
                <Tip text="Exposure stored when the daily report was generated — may differ from live." />
              </span>
              <strong>
                {reportExposure == null ? "Unavailable" : money(reportExposure)}
              </strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Risk events (report day)</span>
              <strong>{reportContent?.risk_events_count ?? "Unavailable"}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                Daily risk remaining{" "}
                <Tip text="No remaining-allowance field is persisted yet." />
              </span>
              <strong>Unavailable</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">
                Consecutive losses / drawdown{" "}
                <Tip text="Not computed from stored history yet." />
              </span>
              <strong>Unavailable</strong>
            </div>
          </div>
          {report ? (
            <p className="muted-note" style={{ marginBottom: 0 }}>
              Latest report date: {report.report_date} (UTC). Cron generates yesterday
              by default; End of Day generates for the selected day.
            </p>
          ) : null}
        </Panel>

        <Panel title="Recent completed trades">
          {closedTrades.length === 0 ? (
            <EmptyState>
              No closed trades from fill replay yet. Report fill counts are not shown
              here as completed round trips.
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>P&amp;L</th>
                    <th>Held</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {closedTrades.map((t) => (
                    <tr key={t.fill_id}>
                      <td>{t.symbol}</td>
                      <td>{money(t.entry_price)}</td>
                      <td>{money(t.exit_price)}</td>
                      <td className={pnlClass(t.realized_pnl)}>
                        {moneyPnl(t.realized_pnl)}
                      </td>
                      <td>{holdingLabel(t.holding_seconds)}</td>
                      <td>{t.exit_reason ?? "Unavailable"}</td>
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
