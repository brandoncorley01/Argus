import type { Metadata } from "next";
import Link from "next/link";

import { ControlBar } from "@/components/founder/ControlBar";
import { EndDayButton } from "@/components/founder/EndDayButton";
import { EmptyState, Panel, StatusBadge } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { deriveActivity, isSameUtcDay } from "@/lib/founder/activity";
import {
  deriveStatus,
  direction,
  firstName,
  greeting,
  money,
  pnlClass,
} from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";
import { apiFetch } from "@/lib/server/api";
import { ARGUS_UI_BUILD } from "@/lib/build";
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
  kill_switch_active: boolean;
};

type Position = {
  symbol: string;
  quantity: string;
  unrealized_pnl?: string | null;
  realized_pnl?: string | null;
  average_cost?: string;
};

type Order = {
  id: string;
  symbol: string;
  side: string;
  status: string;
  quantity: string;
  created_at: string;
};

type Fill = {
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  filled_at: string;
};

type DailyReport = {
  report_date: string;
  content?: { daily_pnl?: string | null; trade_count?: number };
};

function activityTone(
  kind: ReturnType<typeof deriveActivity>["kind"],
): "healthy" | "degraded" | "unhealthy" | null {
  if (kind === "trading_today" || kind === "holding") return "healthy";
  if (kind === "waiting") return "degraded";
  if (kind === "paused") return "degraded";
  return "unhealthy";
}

export default async function TodayPage() {
  const user = await requireUser();
  const name = firstName(user.username);

  const [ready, microLive, portfolios, reports] = await Promise.all([
    soft(getProcessReady),
    soft(getMicroLiveStatus),
    soft(() => apiFetch<Portfolio[]>("/api/v1/paper/portfolios")),
    soft(() =>
      apiFetch<DailyReport[]>("/api/v1/operations/daily-reports", {
        searchParams: { limit: 1 },
      }),
    ),
  ]);

  const portfolio = portfolios?.[0] ?? null;
  let positions: Position[] = [];
  let orders: Order[] = [];
  let fills: Fill[] = [];
  if (portfolio) {
    const [p, o, f] = await Promise.all([
      soft(() =>
        apiFetch<Position[]>(`/api/v1/paper/portfolios/${portfolio.id}/positions`),
      ),
      soft(() =>
        apiFetch<Order[]>(`/api/v1/paper/portfolios/${portfolio.id}/orders`),
      ),
      soft(() =>
        apiFetch<Fill[]>(`/api/v1/paper/portfolios/${portfolio.id}/fills`),
      ),
    ]);
    positions = p ?? [];
    orders = o ?? [];
    fills = f ?? [];
  }

  const open = positions.filter((p) => Number(p.quantity) !== 0);
  const openOrders = orders.filter((o) => {
    const s = o.status.toLowerCase();
    return s === "open" || s === "submitted" || s === "partially_filled" || s === "new";
  });
  const fillsToday = fills.filter((f) => isSameUtcDay(f.filled_at));
  const lastFill = fills[0] ?? null;
  const unrealized = open.reduce((s, p) => s + (Number(p.unrealized_pnl) || 0), 0);

  const status = deriveStatus({
    apiReady: ready != null,
    paperPaused: Boolean(portfolio?.kill_switch_active),
  });
  const running = status === "Running";
  const activity = deriveActivity({
    running,
    paperPaused: Boolean(portfolio?.kill_switch_active),
    openPositions: open.length,
    fillsToday: fillsToday.length,
    openOrders: openOrders.length,
  });

  const liveLocked =
    microLive?.live_execution_active === false ||
    microLive?.activation_state === "PAPER_ONLY" ||
    microLive == null;

  const pnl = reports?.[0]?.content?.daily_pnl ?? null;
  const reportTrades = reports?.[0]?.content?.trade_count ?? null;

  return (
    <div className="founder-home">
      <header className="page-header rise">
        <div>
          <h1>{greeting(name)}</h1>
          <p>Start, stop, and see whether Argus is actually trading.</p>
        </div>
      </header>

      <ControlBar status={status} buildId={ARGUS_UI_BUILD} />

      <section className="panel rise" aria-label="Is Argus working">
        <h2 style={{ marginTop: 0 }}>Is Argus working?</h2>
        <div className="simple-row">
          <div className="simple-chip">
            <span className="metric-label">System</span>
            <StatusBadge
              status={
                status === "Running"
                  ? "healthy"
                  : status === "Stopped"
                    ? "unhealthy"
                    : "degraded"
              }
              label={
                status === "Running"
                  ? "Running"
                  : status === "Stopped"
                    ? "Stopped"
                    : "Paused"
              }
            />
          </div>
          <div className="simple-chip">
            <span className="metric-label">Paper trading</span>
            <StatusBadge
              status={
                portfolio?.kill_switch_active
                  ? "degraded"
                  : ready
                    ? "healthy"
                    : "unhealthy"
              }
              label={
                portfolio?.kill_switch_active
                  ? "Paused"
                  : ready
                    ? "Active"
                    : "Offline"
              }
            />
          </div>
          <div className="simple-chip">
            <span className="metric-label">Live trading</span>
            <StatusBadge status={null} label={liveLocked ? "Locked" : "Check Advanced"} />
          </div>
          <div className="simple-chip">
            <span className="metric-label">Right now</span>
            <StatusBadge
              status={activityTone(activity.kind)}
              label={activity.title}
            />
          </div>
        </div>
        <p style={{ marginBottom: 0, color: "var(--ink-soft)" }}>{activity.detail}</p>
      </section>

      <div className="simple-row" style={{ marginTop: "1rem" }}>
        <div className="simple-chip">
          <span className="metric-label">Today&apos;s P&amp;L</span>
          <strong className={pnlClass(pnl)}>{money(pnl)}</strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Open P&amp;L</span>
          <strong className={pnlClass(unrealized)}>{money(unrealized)}</strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Fills today</span>
          <strong>{fillsToday.length}</strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Last fill</span>
          <strong>
            {lastFill
              ? `${lastFill.side === "buy" ? "Buy" : "Sell"} ${lastFill.symbol}`
              : "None yet"}
          </strong>
          <div className="muted-note" style={{ marginTop: "0.25rem" }}>
            {lastFill ? formatTimestamp(lastFill.filled_at) : "No paper fills on file"}
          </div>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Open positions">
          {open.length === 0 ? (
            <EmptyState>
              {running
                ? "No open positions. Argus is waiting for the next paper trade."
                : "No open positions. Start Argus to resume paper trading."}
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>P&amp;L</th>
                  </tr>
                </thead>
                <tbody>
                  {open.slice(0, 5).map((p) => (
                    <tr key={p.symbol}>
                      <td>{p.symbol}</td>
                      <td>{direction(p.quantity)}</td>
                      <td className={pnlClass(p.unrealized_pnl ?? p.realized_pnl)}>
                        {money(p.unrealized_pnl ?? p.realized_pnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="form-actions" style={{ marginTop: "0.75rem" }}>
            <Link className="btn secondary" href="/trading">
              Trading detail
            </Link>
            <Link className="btn secondary" href="/portfolio">
              Portfolio
            </Link>
          </div>
        </Panel>

        <Panel title="Recent paper fills">
          {fills.length === 0 ? (
            <EmptyState>
              No fills yet. If Right now says Waiting or Holding, Argus is up but has
              not executed a new paper trade.
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Price</th>
                  </tr>
                </thead>
                <tbody>
                  {fills.slice(0, 6).map((f, i) => (
                    <tr key={`${f.symbol}-${f.filled_at}-${i}`}>
                      <td>{formatTimestamp(f.filled_at)}</td>
                      <td>{f.symbol}</td>
                      <td>{f.side === "buy" ? "Buy" : "Sell"}</td>
                      <td>{money(f.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted-note" style={{ marginBottom: 0 }}>
            Report trades today: {reportTrades ?? "Unavailable"}
            {openOrders.length > 0 ? ` · Open orders: ${openOrders.length}` : ""}
          </p>
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

      <p className="muted-note" style={{ marginTop: "1.5rem" }}>
        UI build: {ARGUS_UI_BUILD}
      </p>
    </div>
  );
}
