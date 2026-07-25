import type { Metadata } from "next";
import Link from "next/link";

import { ActiveTrades, type PositionSummary } from "@/components/founder/ActiveTrades";
import { CommandStatusBar } from "@/components/founder/CommandStatusBar";
import { EndDayButton } from "@/components/founder/EndDayButton";
import { TradingCockpit } from "@/components/founder/TradingCockpit";
import { WhatArgusIsDoing } from "@/components/founder/WhatArgusIsDoing";
import { EmptyState } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { ARGUS_UI_BUILD } from "@/lib/build";
import type { CockpitSnapshot } from "@/lib/founder/cockpitTypes";
import { money, moneyPnl, pnlClass } from "@/lib/founder/simple";
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
};

type DailyReport = {
  report_date: string;
  content?: {
    daily_pnl?: string | null;
    trade_count?: number;
    order_count?: number;
    win_rate?: string | null;
    exposure?: string | null;
  };
};

type ClosedTrade = {
  fill_id: string;
  symbol: string;
  realized_pnl: string;
  filled_at: string;
};

type ScanStatus = {
  scanner_state: string;
  cycle: {
    id: string;
    status: string;
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
  next_scheduled_at: string | null;
  worker_note?: string;
  headline?: string | null;
  watching_count?: number | null;
  current_market?: string | null;
  scan_progress?: { scanned: number; total: number } | null;
  possible_trades_found?: number | null;
  next_step?: string | null;
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
      explanation:
        "Argus is not ready. Start Argus, then refresh this page.",
    };
  }
  if (opts.killSwitch) {
    return {
      status: "Warning",
      explanation: "Emergency stop is on — Argus will not open new paper trades.",
    };
  }
  if (opts.pauseNewEntries) {
    return {
      status: "Paused",
      explanation:
        "Argus is paused and will not open new trades. Open trades can still be monitored.",
    };
  }
  if (opts.scannerFailed) {
    return {
      status: "Warning",
      explanation:
        "No markets are registered yet. Press Refresh recent prices to restore scanning.",
    };
  }
  if (opts.marketDataStale) {
    return {
      status: "Warning",
      explanation:
        "Market prices are outdated. Profit/loss may be unsafe to trust until prices refresh.",
    };
  }
  if (opts.marksIncomplete) {
    return {
      status: "Warning",
      explanation:
        "Open trades are missing current prices. Profit/loss is not shown as zero.",
    };
  }
  if (opts.healthWarning) {
    return {
      status: "Warning",
      explanation: "A system service needs attention. Trading rules still apply.",
    };
  }
  return {
    status: "Running",
    explanation: "Argus is running correctly for paper practice.",
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

  let scanStatus = scanStatusInitial;
  if (ready && (!scanStatus?.cycle || scanStatus.scanner_state === "Between Cycles")) {
    const ageMin =
      scanStatus?.cycle?.completed_at != null
        ? (Date.now() - Date.parse(scanStatus.cycle.completed_at)) / 60000
        : null;
    if (!scanStatus?.cycle || (ageMin != null && ageMin >= 1)) {
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

  const cockpitInitial = await soft(() =>
    apiFetch<CockpitSnapshot>("/api/v1/market/scan/cockpit"),
  );

  const portfolio = portfolios?.[0] ?? null;
  let summary: PortfolioSummary | null = null;
  let positions: PositionSummary[] = [];
  let closedTrades: ClosedTrade[] = [];
  let trainingMode: "automatic" | "coaching" = "coaching";
  if (portfolio) {
    const [s, p, c, settings] = await Promise.all([
      soft(() =>
        apiFetch<PortfolioSummary>(`/api/v1/paper/portfolios/${portfolio.id}/summary`),
      ),
      soft(() =>
        apiFetch<PositionSummary[]>(
          `/api/v1/paper/portfolios/${portfolio.id}/position-summaries`,
        ),
      ),
      soft(() =>
        apiFetch<ClosedTrade[]>(
          `/api/v1/paper/portfolios/${portfolio.id}/closed-trades`,
          { searchParams: { limit: 5 } },
        ),
      ),
      soft(() =>
        apiFetch<{ default_notional: string; mode: "automatic" | "coaching" }>(
          `/api/v1/paper/training/${portfolio.id}/settings`,
        ),
      ),
    ]);
    summary = s;
    positions = p ?? [];
    closedTrades = c ?? [];
    if (settings?.mode) trainingMode = settings.mode;
  }

  const defaultProvider =
    providers?.find((row) => row.provider.is_default) ?? providers?.[0] ?? null;
  const connectionOk =
    (defaultProvider?.health?.status ?? "").toLowerCase() === "healthy" ||
    (defaultProvider?.provider.provider_key ?? "").includes("paper");
  const connectionLabel = defaultProvider
    ? `${defaultProvider.provider.display_name}: ${defaultProvider.health?.status ?? "unknown"}`
    : ready
      ? "Paper ready"
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
    marketDataStale: marketDataStale && (positions.length > 0 || (scanStatus?.symbols_monitored ?? 0) > 0),
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
      defaultProvider?.health?.last_success_at ?? health?.generated_at ?? null,
    ) || "Unavailable";

  const report = reports?.[0];
  const realizedToday = report?.content?.daily_pnl ?? null;
  const totalPnl = closedTrades.reduce(
    (sum, t) => sum + (Number(t.realized_pnl) || 0),
    0,
  );

  const scanned =
    cockpitInitial?.scan_progress.scanned ??
    scanStatus?.scan_progress?.scanned ??
    scanStatus?.cycle?.symbols_scanned ??
    0;
  const total =
    cockpitInitial?.scan_progress.total ??
    scanStatus?.scan_progress?.total ??
    scanStatus?.cycle?.symbols_total ??
    0;
  const possible =
    cockpitInitial?.possible_trades_found ??
    scanStatus?.possible_trades_found ??
    0;

  return (
    <div className="founder-home training-lab-home cockpit-home">
      <header className="page-header rise">
        <div>
          <h1>Home</h1>
          <p>
            Live Trading Cockpit — Argus watches markets continuously with
            verified data only. Simulated paper money.{" "}
            <Link href="/paper-training">Paper Training</Link>
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
        scannerState={
          cockpitInitial?.scanner_state ?? scanStatus?.scanner_state ?? "Unavailable"
        }
        marketDataLabel={
          (cockpitInitial?.market_data_at ?? scanStatus?.market_data_at)
            ? `${formatTimestamp(
                cockpitInitial?.market_data_at ?? scanStatus?.market_data_at ?? null,
              )}${
                (cockpitInitial?.market_data_stale ?? scanStatus?.market_data_stale)
                  ? " (outdated)"
                  : ""
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

      {/* 1. Argus is… */}
      <WhatArgusIsDoing
        headline={
          cockpitInitial?.headline ||
          scanStatus?.headline ||
          scanStatus?.worker_note ||
          (ready
            ? "Waiting for scanner status…"
            : "Start Argus to begin scanning and paper trading.")
        }
        currentMarket={
          cockpitInitial?.current_market ??
          scanStatus?.current_market ??
          scanStatus?.cycle?.current_symbol ??
          null
        }
        scanned={scanned}
        total={total}
        possibleTrades={possible}
        lastScanLabel={
          formatTimestamp(scanStatus?.cycle?.completed_at) || "Not yet"
        }
        nextScanLabel={
          formatTimestamp(
            cockpitInitial?.next_scan_at ??
              scanStatus?.next_scheduled_at ??
              scanStatus?.cycle?.next_scheduled_at,
          ) || "Scheduled market scan"
        }
        latestPriceLabel={
          (cockpitInitial?.market_data_at ?? scanStatus?.market_data_at)
            ? `${formatTimestamp(
                cockpitInitial?.market_data_at ?? scanStatus?.market_data_at ?? null,
              )}${
                (cockpitInitial?.market_data_stale ?? scanStatus?.market_data_stale)
                  ? " — outdated"
                  : ""
              }`
            : "No recent price history yet"
        }
        nextStep={cockpitInitial?.next_step ?? scanStatus?.next_step ?? null}
        openPositions={summary?.open_position_count ?? 0}
      />

      {/* 2. Paper account + risk */}
      <section className="panel rise" aria-label="Your paper account">
        <h2 style={{ marginTop: 0 }}>
          Your paper account{" "}
          <span className="mode-tag mode-tag-paper">SIMULATED</span>
        </h2>
        {!summary ? (
          <EmptyState>
            {ready
              ? "No paper portfolio available yet."
              : "Argus is stopped. Start Argus to load paper account figures."}
          </EmptyState>
        ) : (
          <div className="summary-grid summary-grid-primary">
            <div className="summary-card">
              <span className="metric-label">
                Paper Account Balance{" "}
                <Tip text="Total simulated account value. Not real money." />
              </span>
              <strong>{money(summary.total_account_value)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Available Paper Cash</span>
              <strong>{money(summary.buying_power)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Money Currently in Trades</span>
              <strong>{money(summary.committed_capital)}</strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Profit or Loss Today</span>
              <strong className={pnlClass(realizedToday)}>
                {realizedToday != null ? moneyPnl(realizedToday) : "Not reported yet"}
              </strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Total Paper Profit or Loss</span>
              <strong className={pnlClass(String(totalPnl))}>
                {closedTrades.length ? moneyPnl(String(totalPnl)) : "No closed trades yet"}
              </strong>
            </div>
            <div className="summary-card">
              <span className="metric-label">Open Trades</span>
              <strong>{summary.open_position_count}</strong>
            </div>
          </div>
        )}
      </section>

      {/* 3–10 Cockpit, wall, chart, checklist, plan, activity, tech */}
      <TradingCockpit
        initial={cockpitInitial}
        portfolioId={portfolio?.id ?? null}
        trainingMode={trainingMode}
        account={{
          balance: summary?.total_account_value ?? null,
          cash: summary?.buying_power ?? null,
          inTrades: summary?.committed_capital ?? null,
          openCount: summary?.open_position_count ?? 0,
        }}
        positionsOpen={summary?.open_position_count ?? 0}
        realizedToday={realizedToday}
        totalPnl={closedTrades.length ? totalPnl : null}
      />

      {/* Open paper trades */}
      <section className="panel rise" aria-label="Open paper trades">
        <h2 style={{ marginTop: 0 }}>Open paper trades</h2>
        <ActiveTrades positions={positions} />
      </section>

      <section className="panel rise" aria-label="End of day">
        <h2 style={{ marginTop: 0 }}>End of day</h2>
        <p className="muted-note">
          Save today&apos;s paper session summary. This does not unlock live trading.
        </p>
        {portfolio ? <EndDayButton /> : null}
      </section>
    </div>
  );
}
