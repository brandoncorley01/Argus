"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, useTransition } from "react";

import {
  coachingSkipAction,
  coachingTakeAction,
  recordTrainingFeedbackAction,
  refreshRecentPricesAction,
  runMarketScanAction,
} from "@/lib/actions/paper";
import type {
  CockpitSnapshot,
  CockpitWallTile,
  CockpitWatch,
} from "@/lib/founder/cockpitTypes";
import { money, moneyPnl, pnlClass } from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";

function fmtCountdown(totalSec: number | null | undefined): string {
  if (totalSec == null || !Number.isFinite(totalSec)) return "—";
  const s = Math.max(0, Math.floor(totalSec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

function Gauge({
  label,
  value,
  max,
  tone = "neutral",
}: {
  label: string;
  value: number;
  max: number;
  tone?: "ok" | "warn" | "bad" | "neutral";
}) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className={`cockpit-gauge tone-${tone}`}>
      <div className="metric-label">{label}</div>
      <div className="cockpit-gauge-track" aria-hidden>
        <div className="cockpit-gauge-fill" style={{ width: `${pct}%` }} />
      </div>
      <strong>
        {value}
        {max ? ` / ${max}` : ""}
      </strong>
    </div>
  );
}

function Sparkline({
  values,
  highlight,
}: {
  values: number[];
  highlight?: boolean;
}) {
  if (values.length < 2) {
    return <div className="mini-spark empty">No chart yet</div>;
  }
  const w = 120;
  const h = 36;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * (w - 4) + 2;
      const y = h - 3 - ((v - min) / span) * (h - 6);
      return `${x},${y}`;
    })
    .join(" ");
  const up = values[values.length - 1] >= values[0];
  return (
    <svg
      className={`mini-spark ${highlight ? "flash" : ""}`}
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-label="Recent verified closes"
    >
      <polyline
        fill="none"
        stroke={up ? "var(--ok)" : "var(--bad)"}
        strokeWidth="2"
        points={pts}
      />
    </svg>
  );
}

function CandleChart({
  bars,
  entry,
  stop,
  target,
  current,
}: {
  bars: Array<{
    open: number;
    high: number;
    low: number;
    close: number;
  }>;
  entry: number | null;
  stop: number | null;
  target: number | null;
  current: number | null;
}) {
  if (bars.length < 2) {
    return (
      <p className="muted-note">
        Not enough recent price candles to draw this chart yet.
      </p>
    );
  }
  const w = 640;
  const h = 220;
  const pad = 28;
  const highs = bars.map((b) => b.high);
  const lows = bars.map((b) => b.low);
  const levels = [entry, stop, target, current].filter(
    (n): n is number => n != null && Number.isFinite(n),
  );
  const min = Math.min(...lows, ...levels);
  const max = Math.max(...highs, ...levels);
  const span = max - min || 1;
  const y = (v: number) => pad + ((max - v) / span) * (h - pad * 2);
  const cw = Math.max(3, (w - pad * 2) / bars.length - 1);

  const levelLine = (v: number | null, color: string, label: string) => {
    if (v == null) return null;
    const yy = y(v);
    return (
      <g key={label}>
        <line
          x1={pad}
          x2={w - pad}
          y1={yy}
          y2={yy}
          stroke={color}
          strokeWidth="1.5"
          strokeDasharray="4 3"
        />
        <text x={w - pad - 4} y={yy - 4} textAnchor="end" fill={color} fontSize="10">
          {label} {v.toFixed(2)}
        </text>
      </g>
    );
  };

  return (
    <svg
      className="plan-chart"
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-label="Candidate price chart with entry, stop, and target"
    >
      {bars.map((b, i) => {
        const x = pad + i * ((w - pad * 2) / bars.length);
        const up = b.close >= b.open;
        return (
          <g key={i}>
            <line
              x1={x + cw / 2}
              x2={x + cw / 2}
              y1={y(b.high)}
              y2={y(b.low)}
              stroke={up ? "var(--ok)" : "var(--bad)"}
              strokeWidth="1"
            />
            <rect
              x={x}
              y={y(Math.max(b.open, b.close))}
              width={cw}
              height={Math.max(1, Math.abs(y(b.open) - y(b.close)))}
              fill={up ? "var(--ok)" : "var(--bad)"}
            />
          </g>
        );
      })}
      {levelLine(entry, "var(--accent)", "Entry")}
      {levelLine(stop, "var(--bad)", "Stop")}
      {levelLine(target, "var(--ok)", "Target")}
      {levelLine(current, "var(--ink)", "Now")}
    </svg>
  );
}

function RiskRewardBar({
  stop,
  entry,
  current,
  target,
}: {
  stop: number | null;
  entry: number | null;
  current: number | null;
  target: number | null;
}) {
  if (stop == null || target == null || entry == null) {
    return (
      <p className="muted-note">
        Stop and target are not set yet for a visual risk band.
      </p>
    );
  }
  const min = Math.min(stop, target, entry, current ?? entry);
  const max = Math.max(stop, target, entry, current ?? entry);
  const span = max - min || 1;
  const pct = (v: number) => `${((v - min) / span) * 100}%`;
  return (
    <div className="rr-bar" aria-label="Price between stop and target">
      <div className="rr-track">
        <span className="rr-mark stop" style={{ left: pct(stop) }} title="Stop" />
        <span className="rr-mark entry" style={{ left: pct(entry) }} title="Entry" />
        {current != null ? (
          <span
            className="rr-mark now"
            style={{ left: pct(current) }}
            title="Current"
          />
        ) : null}
        <span className="rr-mark target" style={{ left: pct(target) }} title="Target" />
      </div>
      <div className="rr-labels">
        <span>Stop {stop.toFixed(2)}</span>
        <span>Entry {entry.toFixed(2)}</span>
        <span>Target {target.toFixed(2)}</span>
      </div>
    </div>
  );
}

export function TradingCockpit({
  initial,
  portfolioId,
  trainingMode,
  account,
  positionsOpen,
  realizedToday,
  totalPnl,
}: {
  initial: CockpitSnapshot | null;
  portfolioId: string | null;
  trainingMode: "automatic" | "coaching";
  account: {
    balance: string | null;
    cash: string | null;
    inTrades: string | null;
    openCount: number;
  };
  positionsOpen: number;
  realizedToday: string | null;
  totalPnl: number | null;
}) {
  const [cockpit, setCockpit] = useState<CockpitSnapshot | null>(initial);
  const [selected, setSelected] = useState<string | null>(
    initial?.watches[0]?.symbol ?? initial?.wall[0]?.symbol ?? null,
  );
  const [bars, setBars] = useState<
    Array<{ open: number; high: number; low: number; close: number }>
  >([]);
  const [barsAt, setBarsAt] = useState<string | null>(null);
  const [showTechInd, setShowTechInd] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [pending, startTransition] = useTransition();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch("/api/founder/cockpit", { cache: "no-store" });
        if (!res.ok) return;
        const data = (await res.json()) as CockpitSnapshot;
        if (cancelled) return;
        setCockpit((prev) => {
          if (prev) {
            for (const tile of data.wall) {
              const old = prev.wall.find((w) => w.symbol === tile.symbol);
              if (
                old &&
                (old.current_price !== tile.current_price ||
                  old.status !== tile.status ||
                  old.signal_strength !== tile.signal_strength)
              ) {
                setFlash(tile.symbol);
                window.setTimeout(() => setFlash(null), 1200);
                break;
              }
            }
          }
          return data;
        });
      } catch {
        /* keep last good snapshot */
      }
    };
    const id = window.setInterval(poll, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!selected) {
      setBars([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `/api/founder/scan-bars?symbol=${encodeURIComponent(selected)}&limit=60`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as {
          available: boolean;
          bars: Array<{
            open: string;
            high: string;
            low: string;
            close: string;
            close_time: string;
          }>;
        };
        if (cancelled) return;
        setBars(
          (data.bars ?? []).map((b) => ({
            open: Number(b.open),
            high: Number(b.high),
            low: Number(b.low),
            close: Number(b.close),
          })),
        );
        const last = data.bars?.[data.bars.length - 1];
        setBarsAt(last?.close_time ?? null);
      } catch {
        if (!cancelled) setBars([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected, cockpit?.generated_at]);

  const nextScanSec = useMemo(() => {
    if (!cockpit?.next_scan_at) return null;
    return Math.max(0, (Date.parse(cockpit.next_scan_at) - now) / 1000);
  }, [cockpit?.next_scan_at, now]);

  const watch: CockpitWatch | null =
    cockpit?.watches.find((w) => w.symbol === selected) ??
    cockpit?.watches[0] ??
    null;
  const tile: CockpitWallTile | null =
    cockpit?.wall.find((w) => w.symbol === selected) ?? null;

  const scanPct =
    cockpit && cockpit.scan_progress.total > 0
      ? Math.round(
          (cockpit.scan_progress.scanned / cockpit.scan_progress.total) * 100,
        )
      : 0;

  const riskUsed =
    account.inTrades != null && account.balance != null
      ? Math.min(
          100,
          Math.round(
            (Number(account.inTrades) / Math.max(Number(account.balance), 1)) *
              100,
          ),
        )
      : 0;

  if (!cockpit) {
    return (
      <section className="panel rise" aria-label="Trading Cockpit">
        <h2 style={{ marginTop: 0 }}>Live Trading Cockpit</h2>
        <p className="attention-box">
          Cockpit data is unavailable. Start Argus, press Refresh recent prices,
          then Scan markets now. Argus will not invent movement.
        </p>
      </section>
    );
  }

  const entryN = watch?.entry_zone != null ? Number(watch.entry_zone) : null;
  const stopN = watch?.stop_loss != null ? Number(watch.stop_loss) : null;
  const targetN = watch?.take_profit != null ? Number(watch.take_profit) : null;
  const curN =
    watch?.current_price != null
      ? Number(watch.current_price)
      : tile?.current_price ?? null;

  const expireLeft =
    watch != null
      ? Math.max(
          0,
          (Date.parse(watch.expires_at) - now) / 1000,
        )
      : null;
  const nextEvalLeft =
    watch?.next_eval_at != null
      ? Math.max(0, (Date.parse(watch.next_eval_at) - now) / 1000)
      : watch?.next_eval_in_seconds ?? null;

  return (
    <div className="trading-cockpit">
      {/* 3. Cockpit gauges */}
      <section className="panel rise cockpit-panel" aria-label="Live Trading Cockpit">
        <div className="cockpit-head">
          <h2 style={{ marginTop: 0 }}>Live Trading Cockpit</h2>
          <span className={`status-light ${cockpit.market_data_stale ? "warn" : "ok"}`}>
            {cockpit.market_data_stale ? "Prices need refresh" : "Market data current"}
          </span>
        </div>
        <div className="cockpit-gauges">
          <Gauge
            label="Markets monitored"
            value={cockpit.markets_monitored}
            max={Math.max(cockpit.markets_monitored, 1)}
            tone="neutral"
          />
          <div className="cockpit-gauge">
            <div className="metric-label">Current market</div>
            <strong>{cockpit.current_market ?? "Between markets"}</strong>
          </div>
          <div className="cockpit-gauge">
            <div className="metric-label">Scan progress</div>
            <div className="cockpit-gauge-track">
              <div
                className="cockpit-gauge-fill"
                style={{ width: `${scanPct}%` }}
              />
            </div>
            <strong>
              {cockpit.scan_progress.scanned} of {cockpit.scan_progress.total} (
              {scanPct}%)
            </strong>
          </div>
          <div className="cockpit-gauge">
            <div className="metric-label">Next scan</div>
            <strong className="countdown">{fmtCountdown(nextScanSec)}</strong>
          </div>
          <Gauge
            label="Possible trades"
            value={cockpit.possible_trades_found}
            max={Math.max(cockpit.possible_trades_found, 1)}
            tone={cockpit.possible_trades_found ? "ok" : "neutral"}
          />
          <Gauge
            label="Watching"
            value={cockpit.watching_count}
            max={Math.max(cockpit.watching_count, 1)}
            tone={cockpit.watching_count ? "warn" : "neutral"}
          />
          <Gauge
            label="Awaiting confirmation"
            value={cockpit.awaiting_confirmation}
            max={Math.max(cockpit.awaiting_confirmation, 1)}
            tone="warn"
          />
          <Gauge
            label="Open trades"
            value={cockpit.open_trades || positionsOpen}
            max={Math.max(cockpit.open_trades || positionsOpen, 1)}
            tone="ok"
          />
          <div className="cockpit-gauge">
            <div className="metric-label">Risk used (paper)</div>
            <div className="cockpit-gauge-track">
              <div
                className="cockpit-gauge-fill"
                style={{ width: `${riskUsed}%` }}
              />
            </div>
            <strong>{riskUsed}% of account in trades</strong>
          </div>
          <div className="cockpit-gauge">
            <div className="metric-label">Paper performance</div>
            <strong className={pnlClass(realizedToday)}>
              Today{" "}
              {realizedToday != null ? moneyPnl(realizedToday) : "not reported"}
            </strong>
            <span className={`muted-note ${pnlClass(String(totalPnl ?? 0))}`}>
              Total{" "}
              {totalPnl != null && Number.isFinite(totalPnl)
                ? moneyPnl(String(totalPnl))
                : "—"}
            </span>
          </div>
        </div>
        <div className="what-argus-actions">
          <button
            type="button"
            className="btn control-btn control-btn-start"
            disabled={pending}
            onClick={() =>
              startTransition(async () => {
                const r = await refreshRecentPricesAction();
                setMessage(r.message);
              })
            }
          >
            Refresh recent prices
          </button>
          <button
            type="button"
            className="btn secondary"
            disabled={pending}
            onClick={() =>
              startTransition(async () => {
                const r = await runMarketScanAction(true);
                setMessage(r.message);
              })
            }
          >
            Scan markets now
          </button>
        </div>
        {cockpit.next_step ? (
          <p className="attention-box">{cockpit.next_step}</p>
        ) : null}
      </section>

      {/* 4. Market wall */}
      <section className="panel rise" aria-label="Market wall">
        <h2 style={{ marginTop: 0 }}>Market wall</h2>
        <p className="muted-note">
          Verified prices and scan status only. Tiles highlight when a real
          price, score, or stage change arrives.
        </p>
        <div className="market-wall">
          {cockpit.wall.length === 0 ? (
            <p className="muted-note">
              No markets registered yet. Refresh recent prices to load the
              practice universe.
            </p>
          ) : (
            cockpit.wall.map((t) => (
              <button
                type="button"
                key={t.symbol}
                className={`wall-tile ${selected === t.symbol ? "is-selected" : ""} ${
                  flash === t.symbol ? "flash" : ""
                } ${t.stale ? "is-stale" : ""}`}
                onClick={() => setSelected(t.symbol)}
              >
                <header>
                  <strong>{t.symbol}</strong>
                  <span className={`wall-status status-${t.status.replace(/\s+/g, "-").toLowerCase()}`}>
                    {t.status}
                  </span>
                </header>
                <div className="wall-price">
                  {t.current_price != null ? money(String(t.current_price)) : "—"}
                  {t.pct_change != null ? (
                    <span className={t.pct_change >= 0 ? "pnl-pos" : "pnl-neg"}>
                      {t.pct_change >= 0 ? "+" : ""}
                      {t.pct_change.toFixed(2)}%
                    </span>
                  ) : null}
                </div>
                <Sparkline
                  values={t.sparkline}
                  highlight={flash === t.symbol}
                />
                <div className="wall-meta">
                  <span>{t.outlook}</span>
                  <span>Strength {Math.round(t.signal_strength)}</span>
                </div>
                <div className="muted-note">
                  Analyzed {formatTimestamp(t.last_analyzed_at) || "not yet"}
                </div>
              </button>
            ))
          )}
        </div>
      </section>

      {/* 5–7 Selected focus */}
      <section className="panel rise focus-grid" aria-label="Selected market analysis">
        <div>
          <h2 style={{ marginTop: 0 }}>
            {selected ? `${selected} analysis` : "Select a market"}
          </h2>
          {watch ? (
            <p className="watch-narrative">{watch.narrative}</p>
          ) : (
            <p className="muted-note">
              {tile?.stale
                ? "Current market price is outdated. Refresh recent prices."
                : "No active watch plan for this market. Argus may still be scanning or waiting for data."}
            </p>
          )}
          <CandleChart
            bars={bars}
            entry={entryN}
            stop={stopN}
            target={targetN}
            current={curN}
          />
          <p className="muted-note">
            Chart data freshness: {formatTimestamp(barsAt) || "Unavailable"}.
            Lines show planned entry, stop, and target from Argus — not decoration.
          </p>
          <label className="tech-toggle">
            <input
              type="checkbox"
              checked={showTechInd}
              onChange={(e) => setShowTechInd(e.target.checked)}
            />
            Show optional technical details (strategy key / score)
          </label>
          {showTechInd && watch ? (
            <pre className="tech-details">
              {JSON.stringify(
                {
                  strategy: watch.strategy_key,
                  score: watch.score,
                  risk_status: watch.risk_status,
                  reason_code: watch.reason_code,
                  timeframe: watch.timeframe,
                },
                null,
                2,
              )}
            </pre>
          ) : null}
        </div>

        <div>
          <h3>What Argus is waiting for</h3>
          {watch?.checklist?.length ? (
            <>
              <ul className="confirm-list">
                {watch.checklist.map((c) => (
                  <li key={c.key} className={`confirm-${c.status}`}>
                    <span>{c.label}</span>
                    <strong>
                      {c.status === "passed"
                        ? "Passed"
                        : c.status === "failed"
                          ? "Failed"
                          : "Waiting"}
                    </strong>
                  </li>
                ))}
              </ul>
              <p className="checklist-summary">{watch.checklist_summary}</p>
            </>
          ) : (
            <p className="muted-note">No confirmation checklist for this market.</p>
          )}

          <h3>Entry and exit plan</h3>
          {watch ? (
            <>
              <dl className="considering-dl">
                <div>
                  <dt>Watching since</dt>
                  <dd>{formatTimestamp(watch.watching_since)}</dd>
                </div>
                <div>
                  <dt>Time watched</dt>
                  <dd>{fmtCountdown(watch.watched_seconds)}</dd>
                </div>
                <div>
                  <dt>Next evaluation</dt>
                  <dd className="countdown">{fmtCountdown(nextEvalLeft)}</dd>
                </div>
                <div>
                  <dt>Opportunity expires</dt>
                  <dd className="countdown">{fmtCountdown(expireLeft)}</dd>
                </div>
                <div>
                  <dt>Planned entry</dt>
                  <dd>
                    {watch.entry_zone ? money(watch.entry_zone) : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Stop-loss</dt>
                  <dd>{watch.stop_loss ? money(watch.stop_loss) : "—"}</dd>
                </div>
                <div>
                  <dt>Profit target</dt>
                  <dd>{watch.take_profit ? money(watch.take_profit) : "—"}</dd>
                </div>
                <div>
                  <dt>Paper capital planned</dt>
                  <dd>{money(String(watch.paper_capital_planned))}</dd>
                </div>
                <div>
                  <dt>Max dollar loss</dt>
                  <dd>
                    {watch.max_dollar_loss != null
                      ? money(String(watch.max_dollar_loss))
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Potential dollar profit</dt>
                  <dd>
                    {watch.potential_dollar_profit != null
                      ? money(String(watch.potential_dollar_profit))
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Risk / reward</dt>
                  <dd>
                    {watch.risk_reward != null
                      ? Number(watch.risk_reward).toFixed(2)
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Confidence</dt>
                  <dd>{watch.confidence}</dd>
                </div>
              </dl>
              <RiskRewardBar
                stop={stopN}
                entry={entryN}
                current={curN}
                target={targetN}
              />
              <p>
                <strong>Why Argus is watching:</strong> {watch.why}
              </p>
              <p>
                <strong>Waiting to see:</strong> {watch.waiting_for}
              </p>

              {portfolioId &&
              trainingMode === "coaching" &&
              ["Watching", "Risk Review"].includes(watch.stage_raw) ? (
                <div className="coach-actions">
                  <p className="muted-note">
                    Coaching Mode — feedback is recorded for later review and
                    does not change Live rules.
                  </p>
                  <label>
                    Note
                    <input
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                    />
                  </label>
                  <button
                    type="button"
                    className="btn control-btn control-btn-start"
                    disabled={pending}
                    onClick={() =>
                      startTransition(async () => {
                        const r = await coachingTakeAction({
                          portfolioId,
                          candidateId: watch.id,
                          note: note || undefined,
                        });
                        setMessage(r.message);
                      })
                    }
                  >
                    Let Argus take this simulated trade
                  </button>
                  <button
                    type="button"
                    className="btn secondary"
                    disabled={pending}
                    onClick={() =>
                      startTransition(async () => {
                        const r = await coachingSkipAction({
                          portfolioId,
                          candidateId: watch.id,
                          note: note || undefined,
                        });
                        setMessage(r.message);
                      })
                    }
                  >
                    Skip
                  </button>
                  <div className="idea-marks">
                    {(["good_decision", "personal_note", "bad_decision"] as const).map(
                      (code, i) => (
                        <button
                          key={code}
                          type="button"
                          className="btn secondary"
                          disabled={pending}
                          onClick={() =>
                            startTransition(async () => {
                              const r = await recordTrainingFeedbackAction({
                                portfolioId,
                                feedbackCode: code,
                                symbol: watch.symbol,
                                candidateId: watch.id,
                                note:
                                  note ||
                                  ["Good", "Questionable", "Bad"][i],
                              });
                              setMessage(r.message);
                            })
                          }
                        >
                          {["Good", "Questionable", "Bad"][i]}
                        </button>
                      ),
                    )}
                  </div>
                  <Link className="btn secondary" href="/paper-training">
                    Open Paper Training
                  </Link>
                </div>
              ) : (
                <p className="muted-note">
                  {trainingMode === "automatic"
                    ? "Automatic Practice may enter if risk checks clear."
                    : null}{" "}
                  <Link href="/paper-training">Paper Training</Link>
                </p>
              )}
            </>
          ) : (
            <p className="muted-note">Select a watched market to see the plan.</p>
          )}
        </div>
      </section>

      {/* 8–9 Activity */}
      <div className="grid grid-2 activity-dual">
        <section className="panel rise" aria-label="What Argus is doing">
          <h2 style={{ marginTop: 0 }}>What Argus is doing</h2>
          <ul className="doing-list">
            {cockpit.doing.map((d, i) => (
              <li key={`${d.text}-${i}`} className={`tone-${d.tone}`}>
                {d.text}
              </li>
            ))}
          </ul>
        </section>
        <section className="panel rise" aria-label="Why Argus decided">
          <h2 style={{ marginTop: 0 }}>Why Argus decided</h2>
          <ul className="decided-list">
            {cockpit.decided.length === 0 ? (
              <li className="muted-note">No decisions yet this session.</li>
            ) : (
              cockpit.decided.map((d) => (
                <li key={d.id} className={`tone-${d.tone}`}>
                  <time dateTime={d.at}>{formatTimestamp(d.at)}</time>
                  <span>{d.text}</span>
                </li>
              ))
            )}
          </ul>
        </section>
      </div>

      {/* 10 Technical details */}
      <details className="panel rise tech-panel">
        <summary>Technical details (plain language)</summary>
        <div className="tech-sections">
          <section>
            <h3>Market Data</h3>
            <p>
              Recent price candles: latest update{" "}
              {formatTimestamp(cockpit.market_data_at) || "none"}.
              {cockpit.market_data_stale
                ? " Needs attention — prices are outdated."
                : " Healthy."}
            </p>
          </section>
          <section>
            <h3>Strategy</h3>
            <p>
              Moving-average trend strategy (short-term). Scan interval{" "}
              {cockpit.scan_interval_seconds / 60} minute(s). Opportunity time
              remaining window: {cockpit.watch_ttl_seconds / 60} minutes.
            </p>
          </section>
          <section>
            <h3>Risk</h3>
            <p>
              Money currently at risk:{" "}
              {account.inTrades != null ? money(account.inTrades) : "—"}. New
              entries{" "}
              {cockpit.trading_allowed ? "allowed" : "blocked or paused"}.
            </p>
          </section>
          <section>
            <h3>Trade Execution</h3>
            <p>
              Paper practice only. Open simulated trades:{" "}
              {cockpit.open_trades || positionsOpen}. Live trading stays locked.
            </p>
          </section>
          <section>
            <h3>System Health</h3>
            <p>
              Scanner: {cockpit.scanner_state}.
              {cockpit.kill_switch_active
                ? " Emergency stop is on."
                : cockpit.pause_new_entries_active
                  ? " Pause new trades is on."
                  : " Operating normally for paper."}
            </p>
          </section>
        </div>
        <details className="developer-info">
          <summary>Developer information</summary>
          <pre className="tech-details">
            {JSON.stringify(
              {
                generated_at: cockpit.generated_at,
                scanner_state: cockpit.scanner_state,
                scan_progress: cockpit.scan_progress,
                next_scan_at: cockpit.next_scan_at,
              },
              null,
              2,
            )}
          </pre>
        </details>
      </details>

      {message ? (
        <p className="control-feedback ok" role="status">
          {message}
        </p>
      ) : null}
    </div>
  );
}
