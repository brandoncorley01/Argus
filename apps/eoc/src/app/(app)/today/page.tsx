import type { Metadata } from "next";
import { isRedirectError } from "next/dist/client/components/redirect-error";
import Link from "next/link";

import { ActiveTrades, type PositionSummary } from "@/components/founder/ActiveTrades";
import { CapitalStrip } from "@/components/founder/CapitalStrip";
import { CommandStatusBar } from "@/components/founder/CommandStatusBar";
import { EndDayButton } from "@/components/founder/EndDayButton";
import { ExecutiveBriefing } from "@/components/founder/ExecutiveBriefing";
import { PaperLiveProvider } from "@/components/founder/PaperLiveProvider";
import { TradingCockpit } from "@/components/founder/TradingCockpit";
import { requireUser } from "@/lib/actions/auth";
import { ARGUS_UI_BUILD } from "@/lib/build";
import { explainHealthWarning } from "@/lib/founder/institutionStatus";
import { sumTodayRealizedPnl } from "@/lib/founder/todayPnl";
import { formatTimestamp } from "@/lib/format";
import { apiFetch } from "@/lib/server/api";
import {
  getMicroLiveStatus,
  getProcessReady,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Home" };

/** Keep Home SSR under the soft-nav starvation threshold. */
const FAST_MS = 8_000;

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
  services?: Array<{
    service_key: string;
    display_name?: string;
    status: string;
    detail?: string | null;
    criticality?: string;
  }>;
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
  healthDetail: { explanation: string; fix: string | null } | null;
  marketDataStale: boolean;
  marksIncomplete: boolean;
  scannerFailed: boolean;
}): {
  status: "Running" | "Paused" | "Stopped" | "Warning";
  explanation: string;
  fix: string | null;
} {
  if (!opts.apiReady) {
    return {
      status: "Stopped",
      explanation:
        "Argus is stopped. Press Start Argus once — it stays Running until you press Stop.",
      fix: "Press Start Argus.",
    };
  }
  if (opts.killSwitch) {
    return {
      status: "Warning",
      explanation: "Emergency stop is on — Argus will not open new paper trades.",
      fix: "Turn off the emergency stop on Paper Training or Home controls if you want new entries.",
    };
  }
  if (opts.pauseNewEntries) {
    return {
      status: "Paused",
      explanation:
        "Argus is paused and will not open new trades. Open trades can still be monitored.",
      fix: "Press Resume / unpause new entries when you want scanning to open trades again.",
    };
  }
  if (opts.scannerFailed) {
    return {
      status: "Warning",
      explanation:
        "No markets are registered yet. Press Refresh recent prices to restore scanning.",
      fix: "On Home Live Desk, press Refresh recent prices.",
    };
  }
  if (opts.marketDataStale) {
    return {
      status: "Warning",
      explanation:
        "Market prices are outdated. Profit/loss may be unsafe to trust until prices refresh.",
      fix: "On Home Live Desk, press Refresh recent prices. If that fails, Stop then Start Argus.",
    };
  }
  if (opts.marksIncomplete) {
    return {
      status: "Warning",
      explanation:
        "Open trades are missing current prices. Profit/loss is not shown as zero.",
      fix: "Press Refresh recent prices, or Stop then Start Argus so Market Ops can mark positions.",
    };
  }
  if (opts.healthWarning) {
    const detail = opts.healthDetail;
    return {
      status: "Warning",
      explanation:
        detail?.explanation ??
        "A system service needs attention. Trading rules still apply.",
      fix:
        detail?.fix ??
        "Press Stop Argus, then Start Argus once. Or open Advanced → System health.",
    };
  }
  return {
    status: "Running",
    explanation: "Argus is running correctly for paper practice.",
    fix: null,
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

  // Fast path only — heavy cockpit / intelligence load client-side.
  const [ready, microLive, portfolios, providers, health, scanStatus] =
    await Promise.all([
      soft(getProcessReady),
      soft(getMicroLiveStatus),
      soft(() =>
        apiFetch<Portfolio[]>("/api/v1/paper/portfolios", { timeoutMs: FAST_MS }),
      ),
      soft(() =>
        apiFetch<ProviderRow[]>("/api/v1/paper/providers", { timeoutMs: FAST_MS }),
      ),
      soft(() =>
        apiFetch<SystemHealth>("/api/v1/operations/system-health", {
          timeoutMs: FAST_MS,
        }),
      ),
      soft(() =>
        apiFetch<ScanStatus>("/api/v1/market/scan/status", { timeoutMs: FAST_MS }),
      ),
    ]);

  // Backend orders by open risk; first book is the active Founder desk.
  const portfolio = portfolios?.[0] ?? null;
  let summary: PortfolioSummary | null = null;
  let positions: PositionSummary[] = [];
  let closedTrades: ClosedTrade[] = [];
  let trainingMode: "automatic" | "coaching" = "coaching";
  if (portfolio) {
    const [s, p, c, settings] = await Promise.all([
      soft(() =>
        apiFetch<PortfolioSummary>(
          `/api/v1/paper/portfolios/${portfolio.id}/summary`,
          { timeoutMs: FAST_MS },
        ),
      ),
      soft(() =>
        apiFetch<PositionSummary[]>(
          `/api/v1/paper/portfolios/${portfolio.id}/position-summaries`,
          { timeoutMs: FAST_MS },
        ),
      ),
      soft(() =>
        apiFetch<ClosedTrade[]>(
          `/api/v1/paper/portfolios/${portfolio.id}/closed-trades`,
          { searchParams: { limit: 200 }, timeoutMs: FAST_MS },
        ),
      ),
      soft(() =>
        apiFetch<{ default_notional: string; mode: "automatic" | "coaching" }>(
          `/api/v1/paper/training/${portfolio.id}/settings`,
          { timeoutMs: FAST_MS },
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
  const healthDetail = healthWarning ? explainHealthWarning(health) : null;
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
    healthDetail,
    marketDataStale:
      marketDataStale &&
      (positions.length > 0 || (scanStatus?.symbols_monitored ?? 0) > 0),
    marksIncomplete: marksIncomplete && positions.length > 0,
    scannerFailed: Boolean(
      scannerFailed && (scanStatus?.symbols_monitored ?? 0) === 0,
    ),
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

  const todayClosed = sumTodayRealizedPnl(
    (closedTrades ?? []).map((t) => ({
      realized_pnl: t.realized_pnl,
      filled_at: t.filled_at,
    })),
  );
  const totalPnl = todayClosed.pnl;

  return (
    <div className="founder-home training-lab-home cockpit-home">
      <header className="page-header rise">
        <div>
          <h1>Argus</h1>
          <p className="muted-note">
            Paper desk · EST ·{" "}
            <Link href="/paper-training">Training</Link>
          </p>
        </div>
      </header>

      <CommandStatusBar
        argusStatus={picture.status}
        statusExplanation={picture.explanation}
        statusFix={picture.fix}
        tradingMode={tradingMode}
        connectionLabel={connectionLabel}
        connectionOk={Boolean(connectionOk && ready)}
        lastHeartbeat={lastHeartbeat}
        scannerState={scanStatus?.scanner_state ?? "Unavailable"}
        marketDataLabel={
          scanStatus?.market_data_at
            ? `${formatTimestamp(scanStatus.market_data_at)}${
                scanStatus.market_data_stale ? " (outdated)" : ""
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

      <PaperLiveProvider
        portfolioId={portfolio?.id ?? null}
        seedAccount={{
          balance: summary?.total_account_value ?? null,
          cash: summary?.buying_power ?? null,
          inTrades: summary?.committed_capital ?? null,
          openCount: summary?.open_position_count ?? positions.length,
        }}
        seedPositions={positions}
        seedTotalPnl={totalPnl}
        seedMode={trainingMode}
      >
        <CapitalStrip />

        <ExecutiveBriefing
          briefing={null}
          todayPnl={totalPnl}
          openPositions={summary?.open_position_count ?? positions.length}
          institutionStatus={picture.status}
          institutionExplanation={picture.explanation}
          institutionFix={picture.fix}
        />

        {/* Open positions above Live Desk so they are never buried under the cockpit. */}
        <section className="panel rise" aria-label="Open paper trades">
          <h2 style={{ marginTop: 0 }}>Open positions</h2>
          <ActiveTrades
            positions={positions}
            portfolioId={portfolio?.id ?? null}
          />
        </section>

        <TradingCockpit
          initial={null}
          portfolioId={portfolio?.id ?? null}
          trainingMode={trainingMode}
          account={{
            balance: summary?.total_account_value ?? null,
            cash: summary?.buying_power ?? null,
            inTrades: summary?.committed_capital ?? null,
            openCount: summary?.open_position_count ?? positions.length,
          }}
          positionsOpen={summary?.open_position_count ?? positions.length}
          totalPnl={totalPnl}
        />
      </PaperLiveProvider>
      <section className="panel rise" aria-label="End of day">
        <h2 style={{ marginTop: 0 }}>End of day</h2>
        <p className="muted-note">
          Save today&apos;s paper mission debrief. This does not unlock live trading.
        </p>
        {portfolio ? <EndDayButton /> : null}
      </section>
    </div>
  );
}
