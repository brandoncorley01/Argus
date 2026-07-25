import type { Metadata } from "next";
import { isRedirectError } from "next/dist/client/components/redirect-error";
import Link from "next/link";

import { ActiveTrades, type PositionSummary } from "@/components/founder/ActiveTrades";
import { CommandStatusBar } from "@/components/founder/CommandStatusBar";
import { EndDayButton } from "@/components/founder/EndDayButton";
import { TradingCockpit } from "@/components/founder/TradingCockpit";
import { requireUser } from "@/lib/actions/auth";
import { ARGUS_UI_BUILD } from "@/lib/build";
import type { CockpitSnapshot } from "@/lib/founder/cockpitTypes";
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
  try {
    return await renderTodayPage();
  } catch (err) {
    // Must not swallow Next.js navigation (login redirect, etc.)
    if (isRedirectError(err)) throw err;
    const digest =
      typeof err === "object" &&
      err !== null &&
      "digest" in err &&
      typeof (err as { digest?: unknown }).digest === "string"
        ? String((err as { digest: string }).digest)
        : "";
    if (digest.startsWith("NEXT_")) throw err;

    const message = err instanceof Error ? err.message : "Unknown page error";
    return (
      <div className="panel rise">
        <h1 style={{ marginTop: 0 }}>Home could not load</h1>
        <p>
          Argus hit an unexpected page error. Start Argus again so the latest
          build and database updates apply, then reload this page.
        </p>
        <p className="muted-note">Detail: {message}</p>
        <p className="muted-note">Build expected: {ARGUS_UI_BUILD}</p>
        <Link className="btn" href="/today">
          Reload Home
        </Link>
      </div>
    );
  }
}

async function renderTodayPage() {
  await requireUser();

  const [ready, microLive, portfolios, providers, health, scanStatusInitial] =
    await Promise.all([
      soft(getProcessReady),
      soft(getMicroLiveStatus),
      soft(() => apiFetch<Portfolio[]>("/api/v1/paper/portfolios")),
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

  const totalPnl = closedTrades.reduce(
    (sum, t) => sum + (Number(t.realized_pnl) || 0),
    0,
  );

  return (
    <div className="founder-home training-lab-home cockpit-home">
      <header className="page-header rise">
        <div>
          <h1>Argus</h1>
          <p>
            Live paper cockpit — Eastern time, verified market data only.{" "}
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
