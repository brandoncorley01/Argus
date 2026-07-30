"use client";

import { useEffect, useState } from "react";

import { ClearPaperSymbolButton } from "@/components/founder/ClearPaperSymbolButton";
import { usePaperLiveOptional } from "@/components/founder/PaperLiveProvider";
import { EmptyState } from "@/components/ui";
import { money, moneyPnl, pnlClass } from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";

export type PositionSummary = {
  id: string;
  symbol: string;
  quantity: string;
  side: string;
  average_cost: string;
  committed_capital: string;
  market_value?: string | null;
  realized_pnl: string;
  unrealized_pnl: string | null;
  mark_price: string | null;
  pnl_percent: string | null;
  price_status?: string;
  opened_at: string | null;
  strategy_version_id: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  state: string;
};

/** Matches API TAKE_PROFIT_MIN_HOLD_SECONDS — take-profit waits this long after entry. */
const TAKE_PROFIT_MIN_HOLD_SEC = 120;
/** Scan + price-refresh workers evaluate exits at least every minute. */
const EXIT_PASS_CADENCE_MS = 60_000;

function timeInTrade(openedAt: string | null, nowMs: number): string {
  if (!openedAt) return "Unknown";
  const ms = nowMs - DateParseSafe(openedAt);
  if (!Number.isFinite(ms) || ms < 0) return "Unknown";
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return `${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours} hr`;
  return `${Math.floor(hours / 24)} days`;
}

function DateParseSafe(value: string): number {
  const t = Date.parse(value);
  return Number.isFinite(t) ? t : NaN;
}

function fmtClock(totalSec: number): string {
  const s = Math.max(0, Math.floor(totalSec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

function priceMoney(value: string | number | null | undefined): string {
  if (value == null || value === "") return "Unavailable";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "Unavailable";
  const digits = Math.abs(n) < 1 ? 6 : Math.abs(n) < 100 ? 4 : 2;
  const abs = Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: Math.min(2, digits),
    maximumFractionDigits: digits,
  });
  return n < 0 ? `-${abs}` : abs;
}

function nextExitPassAt(nowMs: number): number {
  // Align to the next whole minute — market scan evaluates exits every minute.
  return Math.ceil((nowMs + 1) / EXIT_PASS_CADENCE_MS) * EXIT_PASS_CADENCE_MS;
}

function TimeInTradeLabel({ openedAt }: { openedAt: string | null }) {
  const [label, setLabel] = useState("—");
  useEffect(() => {
    const tick = () => setLabel(timeInTrade(openedAt, Date.now()));
    tick();
    const id = window.setInterval(tick, 30_000);
    return () => window.clearInterval(id);
  }, [openedAt]);
  return <>{label}</>;
}

function ExitCountdownDial({
  kind,
  openedAt,
}: {
  kind: "stop_loss" | "take_profit";
  openedAt: string | null;
}) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  if (now == null) {
    return (
      <div className="exit-countdown" role="status">
        <p className="attention-box">Calculating exit countdown…</p>
      </div>
    );
  }

  const openedMs = openedAt ? DateParseSafe(openedAt) : NaN;
  const holdEndsAt =
    kind === "take_profit" && Number.isFinite(openedMs)
      ? openedMs + TAKE_PROFIT_MIN_HOLD_SEC * 1000
      : now;
  const holdRemaining = Math.max(0, Math.ceil((holdEndsAt - now) / 1000));
  const passAt = nextExitPassAt(Math.max(now, holdEndsAt));
  const passRemaining = Math.max(0, Math.ceil((passAt - now) / 1000));
  const phase: "hold" | "pass" | "overdue" =
    kind === "take_profit" && holdRemaining > 0
      ? "hold"
      : passRemaining <= 1
        ? "overdue"
        : "pass";
  const remaining =
    phase === "hold" ? holdRemaining : phase === "overdue" ? 0 : passRemaining;
  const total =
    phase === "hold" ? TAKE_PROFIT_MIN_HOLD_SEC : EXIT_PASS_CADENCE_MS / 1000;
  const pct =
    phase === "overdue"
      ? 100
      : Math.max(0, Math.min(100, ((total - remaining) / total) * 100));
  const tone = kind === "stop_loss" || phase === "overdue" ? "bad" : "warn";
  const r = 36;
  const c = 2 * Math.PI * r;
  const dash = (pct / 100) * c;

  const headline =
    kind === "stop_loss"
      ? phase === "overdue"
        ? "Stop-loss hit — exit overdue"
        : "Stop-loss hit — closing soon"
      : phase === "hold"
        ? "Profit target hit — hold timer"
        : phase === "overdue"
          ? "Profit target hit — exit overdue"
          : "Profit target hit — closing soon";
  const detail =
    phase === "hold"
      ? `Take-profit needs ${TAKE_PROFIT_MIN_HOLD_SEC / 60} minutes in the trade before Argus may close. Hold ends in ${fmtClock(remaining)}.`
      : phase === "overdue"
        ? "Countdown reached zero. Argus is retrying the paper close on each worker pass (about every minute). Capital updates when the sell fill lands."
        : `Next exit pass in ${fmtClock(remaining)}. Argus closes this paper trade on that worker pass (about every minute).`;

  return (
    <div className={`exit-countdown tone-${tone}`} role="status">
      <div className="exit-countdown-row">
        <div
          className={`argus-dial tone-${tone} is-beating exit-dial`}
          role="img"
          aria-label={`Exit countdown ${fmtClock(remaining)}`}
        >
          <svg viewBox="0 0 96 96" className="argus-dial-svg" aria-hidden>
            <circle className="argus-dial-track" cx="48" cy="48" r={r} />
            <circle
              className="argus-dial-fill"
              cx="48"
              cy="48"
              r={r}
              strokeDasharray={`${dash} ${c - dash}`}
              transform="rotate(-90 48 48)"
            />
          </svg>
          <div className="argus-dial-center">
            <strong>{phase === "overdue" ? "Now" : fmtClock(remaining)}</strong>
            <span>
              {phase === "hold" ? "Hold" : phase === "overdue" ? "Retry" : "Exit"}
            </span>
          </div>
        </div>
        <div className="exit-countdown-copy">
          <p className="attention-box" style={{ margin: 0 }}>
            {headline}
          </p>
          <p className="muted-note" style={{ margin: "0.45rem 0 0" }}>
            {detail}
          </p>
          <p className="muted-note" style={{ margin: "0.35rem 0 0" }}>
            Exit rule: {kind === "stop_loss" ? "stop-loss" : "take-profit"}
            {phase === "pass"
              ? ` · next pass ~${new Date(passAt).toLocaleTimeString("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                  second: "2-digit",
                })}`
              : phase === "overdue"
                ? " · worker retrying each minute"
                : ""}
          </p>
        </div>
      </div>
    </div>
  );
}

export function ActiveTrades({
  positions: seedPositions,
  portfolioId = null,
}: {
  positions: PositionSummary[];
  portfolioId?: string | null;
}) {
  const live = usePaperLiveOptional();
  const positions = live?.positions ?? seedPositions;
  const livePortfolioId = live?.portfolioId ?? portfolioId;

  if (positions.length === 0) {
    return (
      <EmptyState>
        No open paper trades. When Argus enters a simulated trade, it will show
        here with entry, stop, target, and profit or loss.
      </EmptyState>
    );
  }

  return (
    <div className="open-trade-cards">
      {positions.map((p) => {
        const entry = Number(p.average_cost);
        const mark = p.mark_price != null ? Number(p.mark_price) : null;
        const absurdEntry =
          (p.symbol.toUpperCase().startsWith("BTC") && entry > 0 && entry < 1000) ||
          (p.symbol.toUpperCase().startsWith("ETH") && entry > 0 && entry < 50);
        const stale =
          p.price_status === "unavailable" ||
          p.mark_price == null ||
          p.unrealized_pnl == null ||
          absurdEntry;
        const stop = p.stop_loss != null ? Number(p.stop_loss) : null;
        const target = p.take_profit != null ? Number(p.take_profit) : null;
        const isLong = p.side === "long" || Number(p.quantity) > 0;
        const stopBreached =
          !stale &&
          mark != null &&
          stop != null &&
          Number.isFinite(mark) &&
          Number.isFinite(stop) &&
          (isLong ? mark <= stop : mark >= stop);
        const targetHit =
          !stale &&
          !stopBreached &&
          mark != null &&
          target != null &&
          Number.isFinite(mark) &&
          Number.isFinite(target) &&
          (isLong ? mark >= target : mark <= target);
        const boughtOrSold = isLong ? "Bought" : "Sold";
        return (
          <article key={p.id} className="open-trade-card">
            <header className="open-trade-head">
              <h3>{p.symbol}</h3>
              <span className="muted-note">{boughtOrSold}</span>
            </header>
            {absurdEntry ? (
              <p className="attention-box" role="status">
                This paper entry looks inaccurate (test/stale price{" "}
                {money(p.average_cost)}
                {mark != null ? `, mark ${money(String(mark))}` : ""}). Remove it
                and refresh recent prices so Argus can restart with real market
                data.
              </p>
            ) : null}
            <dl className="considering-dl">
              <div>
                <dt>Entry price</dt>
                <dd>{priceMoney(p.average_cost)}</dd>
              </div>
              <div>
                <dt>Current price</dt>
                <dd>
                  {stale
                    ? "Outdated"
                    : p.mark_price
                      ? priceMoney(p.mark_price)
                      : "Unavailable"}
                </dd>
              </div>
              <div>
                <dt>Paper money invested</dt>
                <dd>{money(p.committed_capital)}</dd>
              </div>
              <div>
                <dt>Current profit or loss</dt>
                <dd>
                  {stale ? (
                    <span className="warn-text">Cannot calculate safely</span>
                  ) : (
                    <span className={pnlClass(p.unrealized_pnl)}>
                      {moneyPnl(p.unrealized_pnl)}
                      {p.pnl_percent != null
                        ? ` (${Number(p.pnl_percent).toFixed(2)}%)`
                        : ""}
                    </span>
                  )}
                </dd>
              </div>
              <div>
                <dt>Stop-loss</dt>
                <dd>{p.stop_loss ? priceMoney(p.stop_loss) : "Not set"}</dd>
              </div>
              <div>
                <dt>Profit target</dt>
                <dd>{p.take_profit ? priceMoney(p.take_profit) : "Not set"}</dd>
              </div>
              <div>
                <dt>Time in trade</dt>
                <dd>
                  <TimeInTradeLabel openedAt={p.opened_at} />
                </dd>
              </div>
              <div>
                <dt>Opened</dt>
                <dd>{formatTimestamp(p.opened_at) || "—"}</dd>
              </div>
            </dl>
            {stale ? (
              <p className="attention-box" role="status">
                Current market price is outdated. Profit/loss cannot be
                calculated safely. Refresh recent prices, then return here.
              </p>
            ) : stopBreached ? (
              <ExitCountdownDial kind="stop_loss" openedAt={p.opened_at} />
            ) : targetHit ? (
              <ExitCountdownDial kind="take_profit" openedAt={p.opened_at} />
            ) : (
              <p>
                <strong>What Argus is doing now:</strong> Monitoring this open
                paper position against its stop and target.
              </p>
            )}
            {!stale && !stopBreached && !targetHit ? (
              <p className="muted-note">
                Why Argus is continuing to hold: the exit rules have not been
                met yet
                {p.state ? ` (state: ${p.state})` : ""}.
              </p>
            ) : null}
            {livePortfolioId ? (
              <ClearPaperSymbolButton
                portfolioId={livePortfolioId}
                symbol={p.symbol}
              />
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
