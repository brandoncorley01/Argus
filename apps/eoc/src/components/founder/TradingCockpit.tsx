"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import {
  coachingSkipAction,
  coachingTakeAction,
  refreshRecentPricesAction,
  runMarketScanAction,
  setTrainingModeAction,
} from "@/lib/actions/paper";
import type {
  CockpitSnapshot,
  CockpitWallTile,
  CockpitWatch,
} from "@/lib/founder/cockpitTypes";
import { money, moneyPnl } from "@/lib/founder/simple";
import { formatAgeLabel, formatLiveClock, formatTimestamp } from "@/lib/format";
import { usePaperLiveOptional } from "@/components/founder/PaperLiveProvider";

const COCKPIT_POLL_MS = 4_000;
const COCKPIT_POLL_SCANNING_MS = 1_500;
const PULSE_POLL_MS = 5_000;
const KEEP_ALIVE_MS = 30_000;
/** Interval fire delayed this much ⇒ host likely slept; force catch-up poll. */
const WAKE_GAP_MS = 10_000;

type DeskLogItem = {
  id: string;
  at: number;
  text: string;
  tone: "ok" | "warn" | "info" | "bad";
  symbol?: string;
};

function fmtCountdown(totalSec: number | null | undefined): string {
  if (totalSec == null || !Number.isFinite(totalSec)) return "—";
  const s = Math.max(0, Math.floor(totalSec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

function ageSeconds(
  iso: string | null | undefined,
  nowMs: number | null,
): number | null {
  if (!iso || nowMs == null) return null;
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return null;
  return Math.max(0, Math.floor((nowMs - t) / 1000));
}

/** Circular dial — fill is a real 0–100% from verified ages/counts, not decoration. */
function Dial({
  label,
  valueLabel,
  pct,
  tone = "neutral",
  beating = false,
}: {
  label: string;
  valueLabel: string;
  pct: number;
  tone?: "ok" | "warn" | "bad" | "neutral";
  beating?: boolean;
}) {
  const clamped = Math.max(0, Math.min(100, pct));
  const r = 36;
  const c = 2 * Math.PI * r;
  const dash = (clamped / 100) * c;
  return (
    <div
      className={`argus-dial tone-${tone}${beating ? " is-beating" : ""}`}
      role="img"
      aria-label={`${label}: ${valueLabel}`}
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
        <strong>{valueLabel}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

type PaperPulse = {
  fetched_at: string;
  summary: {
    cash_balance: string;
    buying_power: string;
    committed_capital: string;
    total_account_value: string;
    open_position_count: number;
    kill_switch_active: boolean;
    pause_new_entries_active: boolean;
  };
  closed_trade_count: number;
  total_realized_pnl: string;
  open_unrealized_pnl?: string;
  open_positions?: Array<{
    symbol: string;
    unrealized_pnl: string | null;
    mark_price: string | null;
    stop_loss: string | null;
    take_profit: string | null;
  }>;
  mode: "automatic" | "coaching";
  default_notional: string;
};

const DESK_ROTATE_MS = 8_000;

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
  const [mode, setMode] = useState<"automatic" | "coaching">(trainingMode);
  const [liveAccount, setLiveAccount] = useState(account);
  const [openSymbols, setOpenSymbols] = useState<string[]>([]);
  const [closedCount, setClosedCount] = useState(0);
  const [liveTotalPnl, setLiveTotalPnl] = useState<number | null>(totalPnl);
  const [openUnrealized, setOpenUnrealized] = useState<number | null>(null);
  const sharedLive = usePaperLiveOptional();
  const hasSharedLive = sharedLive != null;
  const displayAccount = sharedLive?.account ?? liveAccount;
  const displayOpenSymbols =
    sharedLive?.positions.map((p) => p.symbol).filter(Boolean) ?? openSymbols;
  const displayClosedCount = sharedLive?.closedTradeCount ?? closedCount;
  const displayTotalPnl = sharedLive?.totalRealizedPnl ?? liveTotalPnl;
  const displayOpenUnrealized = sharedLive?.openUnrealizedPnl ?? openUnrealized;
  const displayMode = sharedLive?.mode ?? mode;
  const [lastBeatAt, setLastBeatAt] = useState<string | null>(
    initial?.generated_at ?? null,
  );
  const [beatCount, setBeatCount] = useState(0);
  const [keepAliveNote, setKeepAliveNote] = useState<string | null>(null);
  // null until mount — Date.now() in useState breaks hydration vs SSR HTML
  const [now, setNow] = useState<number | null>(null);
  const [userPinnedUntil, setUserPinnedUntil] = useState(0);
  const [deskLog, setDeskLog] = useState<DeskLogItem[]>([]);
  const [popSymbols, setPopSymbols] = useState<Set<string>>(new Set());
  const knownWallRef = useRef<Set<string> | null>(null);
  const knownDiscoveryRef = useRef<Set<string>>(new Set());
  const scanningRef = useRef(false);

  useEffect(() => {
    setNow(Date.now());
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;
    let lastTick = Date.now();
    let timer: number | null = null;

    const pushLog = (item: Omit<DeskLogItem, "id" | "at"> & { id?: string }) => {
      const id =
        item.id ?? `${item.symbol ?? "log"}-${Date.now()}-${Math.random()}`;
      setDeskLog((prev) => {
        if (prev.some((p) => p.id === id)) return prev;
        return [
          {
            id,
            at: Date.now(),
            text: item.text,
            tone: item.tone,
            symbol: item.symbol,
          },
          ...prev,
        ].slice(0, 40);
      });
    };

    const markPop = (symbol: string) => {
      setPopSymbols((prev) => new Set(prev).add(symbol));
      window.setTimeout(() => {
        setPopSymbols((prev) => {
          const next = new Set(prev);
          next.delete(symbol);
          return next;
        });
      }, 4200);
    };

    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const q = portfolioId
          ? `?portfolioId=${encodeURIComponent(portfolioId)}`
          : "";
        const res = await fetch(`/api/founder/cockpit${q}`, {
          cache: "no-store",
          signal: AbortSignal.timeout(50_000),
        });
        if (!res.ok) return;
        const data = (await res.json()) as CockpitSnapshot;
        if (cancelled) return;
        scanningRef.current = data.scanner_state === "Scanning";
        setLastBeatAt(data.generated_at);
        setBeatCount((n) => n + 1);

        const wallSyms = new Set(data.wall.map((t) => t.symbol));
        if (knownWallRef.current == null) {
          knownWallRef.current = wallSyms;
        } else {
          for (const tile of data.wall) {
            if (!knownWallRef.current.has(tile.symbol)) {
              knownWallRef.current.add(tile.symbol);
              if (tile.discovered || tile.newly_discovered) {
                markPop(tile.symbol);
                setFlash(tile.symbol);
                window.setTimeout(() => setFlash(null), 1600);
                const cls = tile.opportunity_class?.replaceAll("_", " ");
                pushLog({
                  tone: "ok",
                  symbol: tile.symbol,
                  text: cls
                    ? `Discovered ${tile.symbol} · ${cls} → Radar`
                    : `Discovered ${tile.symbol} → Radar`,
                });
              }
            }
          }
        }

        for (const raw of data.market_discovery?.newly_discovered ?? []) {
          const sym = typeof raw === "string" ? raw : raw.symbol;
          if (!sym || knownDiscoveryRef.current.has(sym)) continue;
          knownDiscoveryRef.current.add(sym);
          markPop(sym);
          const cls =
            typeof raw === "object" && raw.opportunity_class
              ? raw.opportunity_class.replaceAll("_", " ")
              : null;
          pushLog({
            tone: "ok",
            symbol: sym,
            text: cls
              ? `New opportunity ${sym} · ${cls}`
              : `New opportunity ${sym}`,
          });
        }

        if (
          data.scanner_state === "Scanning" &&
          data.current_market
        ) {
          pushLog({
            id: `scan-${data.current_market}-${data.scan_progress.scanned}`,
            tone: "info",
            symbol: data.current_market,
            text: `Scanning ${data.current_market} (${data.scan_progress.scanned}/${data.scan_progress.total})`,
          });
        }

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
      } finally {
        inFlight = false;
        lastTick = Date.now();
        if (!cancelled) {
          const delay = scanningRef.current
            ? COCKPIT_POLL_SCANNING_MS
            : COCKPIT_POLL_MS;
          timer = window.setTimeout(() => {
            const gap = Date.now() - lastTick;
            void poll();
            if (gap > WAKE_GAP_MS + COCKPIT_POLL_MS) void poll();
          }, delay);
        }
      }
    };
    void poll();

    const onVisible = () => {
      if (document.visibilityState === "visible") void poll();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      if (timer != null) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [portfolioId]);

  useEffect(() => {
    // Shared PaperLiveProvider already polls — avoid a second competing pulse.
    if (hasSharedLive || !portfolioId) return;
    let cancelled = false;
    let inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await fetch(
          `/api/founder/paper-pulse?portfolioId=${encodeURIComponent(portfolioId)}`,
          { cache: "no-store", signal: AbortSignal.timeout(12_000) },
        );
        if (!res.ok) return;
        const data = (await res.json()) as PaperPulse;
        if (cancelled) return;
        setMode(data.mode);
        setClosedCount(data.closed_trade_count);
        setLiveTotalPnl(Number(data.total_realized_pnl));
        setOpenUnrealized(
          data.open_unrealized_pnl != null
            ? Number(data.open_unrealized_pnl)
            : null,
        );
        setLiveAccount({
          balance: data.summary.total_account_value,
          cash: data.summary.cash_balance,
          inTrades: data.summary.committed_capital,
          openCount: data.summary.open_position_count,
        });
        setOpenSymbols(
          (data.open_positions ?? []).map((p) => p.symbol).filter(Boolean),
        );
      } catch {
        /* keep last good pulse */
      } finally {
        inFlight = false;
      }
    };
    void poll();
    const id = window.setInterval(poll, PULSE_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [portfolioId, hasSharedLive]);

  // Keepalive may refresh market data only — never scans or trading logic.
  // Also fires on tab/host wake so the desk recovers without Founder attention.
  useEffect(() => {
    let cancelled = false;
    let busy = false;
    const keepAlive = async (reason: "interval" | "wake" = "interval") => {
      if (cancelled || busy || pending) return;
      const age = ageSeconds(cockpit?.market_data_at, Date.now());
      if (reason === "interval" && age != null && age < 90) return;
      if (reason === "wake" && age != null && age < 45) return;
      busy = true;
      try {
        const r = await refreshRecentPricesAction();
        if (!cancelled && r.ok) {
          setKeepAliveNote(
            reason === "wake" ? "Caught up after pause" : "Prices updated",
          );
          setLastBeatAt(new Date().toISOString());
        }
      } finally {
        busy = false;
        if (!cancelled) {
          window.setTimeout(() => setKeepAliveNote(null), 4000);
        }
      }
    };
    const boot = window.setTimeout(() => void keepAlive(), 2500);
    const id = window.setInterval(() => void keepAlive("interval"), KEEP_ALIVE_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void keepAlive("wake");
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      window.clearTimeout(boot);
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [cockpit?.market_data_at, pending]);

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

  // Rotate Live Desk focus across open positions + active watches (skip Expired).
  // While scanning, stick to the symbol Argus is evaluating right now.
  useEffect(() => {
    const rotate = () => {
      if (Date.now() < userPinnedUntil) return;
      if (
        cockpit?.scanner_state === "Scanning" &&
        cockpit.current_market
      ) {
        setSelected(cockpit.current_market);
        return;
      }
      const fromCockpit = cockpit?.focus_symbols?.length
        ? cockpit.focus_symbols
        : [
            ...(cockpit?.open_position_symbols ?? []),
            ...(cockpit?.watches ?? [])
              .filter((w) =>
                ["Watching", "Risk Review", "Evaluating"].includes(w.stage_raw),
              )
              .map((w) => w.symbol),
            ...(cockpit?.current_market ? [cockpit.current_market] : []),
          ];
      const roster = Array.from(
        new Set([...displayOpenSymbols, ...fromCockpit].filter(Boolean)),
      );
      if (roster.length === 0) return;
      setSelected((prev) => {
        if (!prev || !roster.includes(prev)) return roster[0] ?? null;
        const idx = roster.indexOf(prev);
        return roster[(idx + 1) % roster.length] ?? roster[0] ?? null;
      });
    };
    const id = window.setInterval(rotate, DESK_ROTATE_MS);
    return () => window.clearInterval(id);
  }, [
    cockpit?.focus_symbols,
    cockpit?.open_position_symbols,
    cockpit?.watches,
    cockpit?.current_market,
    cockpit?.scanner_state,
    displayOpenSymbols,
    userPinnedUntil,
  ]);

  // Follow the live scan spotlight as soon as current_market advances.
  useEffect(() => {
    if (Date.now() < userPinnedUntil) return;
    if (cockpit?.scanner_state !== "Scanning" || !cockpit.current_market) return;
    setSelected(cockpit.current_market);
  }, [
    cockpit?.scanner_state,
    cockpit?.current_market,
    userPinnedUntil,
  ]);

  const nextScanSec = useMemo(() => {
    if (!cockpit?.next_scan_at) return null;
    if (now == null) {
      // SSR / first paint: use snapshot age, not live clock
      const generated = Date.parse(cockpit.generated_at);
      if (!Number.isFinite(generated)) return null;
      return Math.max(0, (Date.parse(cockpit.next_scan_at) - generated) / 1000);
    }
    return Math.max(0, (Date.parse(cockpit.next_scan_at) - now) / 1000);
  }, [cockpit?.next_scan_at, cockpit?.generated_at, now]);

  const watch: CockpitWatch | null =
    cockpit?.watches.find(
      (w) =>
        w.symbol === selected &&
        w.stage_raw !== "Expired",
    ) ??
    cockpit?.watches.find((w) =>
      ["Watching", "Risk Review", "Evaluating"].includes(w.stage_raw),
    ) ??
    cockpit?.watches.find((w) => w.symbol === selected) ??
    null;
  const tile: CockpitWallTile | null =
    cockpit?.wall.find((w) => w.symbol === selected) ?? null;

  const wallSorted = useMemo(() => {
    const wall = cockpit?.wall ?? [];
    const cur = cockpit?.current_market;
    return [...wall].sort((a, b) => {
      const rank = (t: CockpitWallTile) => {
        if (cur && t.symbol === cur) return 0;
        if (popSymbols.has(t.symbol) || t.newly_discovered) return 1;
        if (t.status === "Open" || displayOpenSymbols.includes(t.symbol)) return 2;
        if (t.status.includes("Watch") || t.status.includes("Setup")) return 3;
        if (t.discovered) return 4;
        return 5;
      };
      return rank(a) - rank(b) || a.symbol.localeCompare(b.symbol);
    });
  }, [cockpit?.wall, cockpit?.current_market, popSymbols, displayOpenSymbols]);

  const activityLog = useMemo(() => {
    const fromApi = (cockpit?.decided ?? []).slice(0, 12).map((d) => ({
      id: d.id,
      at: Date.parse(d.at) || 0,
      text: d.text,
      tone: (d.tone === "ok" || d.tone === "warn" || d.tone === "bad"
        ? d.tone
        : "info") as DeskLogItem["tone"],
    }));
    return [...deskLog, ...fromApi]
      .sort((a, b) => b.at - a.at)
      .slice(0, 18);
  }, [deskLog, cockpit?.decided]);

  if (!cockpit) {
    return (
      <section className="panel rise" aria-label="Trading Cockpit">
        <h2 style={{ marginTop: 0 }}>Live Trading Cockpit</h2>
        <p className="muted-note">
          Loading live markets… If this stays blank, press Start Argus so the API
          and worker are healthy, then hard-refresh Home.
        </p>
      </section>
    );
  }

  const beatAge = ageSeconds(lastBeatAt, now);
  const feedAge =
    now == null
      ? cockpit.market_data_age_seconds
      : ageSeconds(cockpit.market_data_at, now);
  const scanInterval = Math.max(1, cockpit.scan_interval_seconds);
  const scanFill =
    nextScanSec == null
      ? 0
      : Math.min(100, Math.round(((scanInterval - nextScanSec) / scanInterval) * 100));
  const beatFresh = beatAge != null && beatAge <= 12;
  // 1m/5m charts: fresh ≤3m, warn ≤10m
  const feedOk = feedAge != null && feedAge <= 180;
  const feedWarn = feedAge != null && feedAge > 180 && feedAge <= 600;
  const openCount =
    displayAccount.openCount ||
    positionsOpen ||
    (cockpit.open_position_symbols?.length ?? 0) ||
    cockpit.open_trades ||
    0;
  const watchingN = cockpit.watching_count;
  const statusChips: Array<{ label: string; tone: "ok" | "warn" | "bad" | "neutral" }> =
    [];
  statusChips.push({
    label: displayMode === "automatic" ? "Auto enter" : "Coaching",
    tone: displayMode === "automatic" ? "ok" : "warn",
  });
  statusChips.push({
    label: feedOk ? "Feed live" : feedWarn ? "Feed aging" : "Feed stale",
    tone: feedOk ? "ok" : feedWarn ? "warn" : "bad",
  });
  statusChips.push({
    label:
      cockpit.scanner_state === "Scanning"
        ? "Scanning"
        : cockpit.scanner_state === "Delayed"
          ? "Scan delayed"
          : cockpit.scanner_state === "Paused"
            ? "Paused"
            : "Running",
    tone:
      cockpit.scanner_state === "Scanning"
        ? "ok"
        : cockpit.scanner_state === "Delayed" ||
            cockpit.scanner_state === "Paused"
          ? "warn"
          : "ok",
  });
  if (watchingN > 0) {
    statusChips.push({ label: `${watchingN} watching`, tone: "warn" });
  }
  if (openCount > 0) {
    statusChips.push({ label: `${openCount} open`, tone: "ok" });
  }
  if (cockpit.pause_new_entries_active) {
    statusChips.push({ label: "Entries paused", tone: "warn" });
  }
  if (cockpit.kill_switch_active) {
    statusChips.push({ label: "Stopped", tone: "bad" });
  }

  const entryN = watch?.entry_zone != null ? Number(watch.entry_zone) : null;
  const stopN = watch?.stop_loss != null ? Number(watch.stop_loss) : null;
  const targetN = watch?.take_profit != null ? Number(watch.take_profit) : null;
  const curN =
    watch?.current_price != null
      ? Number(watch.current_price)
      : tile?.current_price ?? null;

  const scanning = cockpit.scanner_state === "Scanning";
  const scanProgressPct =
    cockpit.scan_progress.total > 0
      ? Math.min(
          100,
          Math.round(
            (cockpit.scan_progress.scanned / cockpit.scan_progress.total) * 100,
          ),
        )
      : scanning
        ? 8
        : scanFill;
  const md = cockpit.market_discovery;
  const watchingList = (cockpit.watches ?? []).filter((w) =>
    ["Watching", "Risk Review", "Evaluating"].includes(w.stage_raw),
  );

  const expireLeft =
    watch == null
      ? null
      : now == null
        ? watch.expire_in_seconds
        : Math.max(0, (Date.parse(watch.expires_at) - now) / 1000);
  const nextEvalLeft =
    watch == null
      ? null
      : now == null
        ? (watch.next_eval_in_seconds ?? null)
        : watch.next_eval_at != null
          ? Math.max(0, (Date.parse(watch.next_eval_at) - now) / 1000)
          : (watch.next_eval_in_seconds ?? null);
  const watchedSec =
    watch == null
      ? null
      : now == null
        ? watch.watched_seconds
        : Math.max(0, Math.floor((now - Date.parse(watch.watching_since)) / 1000));

  return (
    <div className="trading-cockpit desk-simplified">
      <section className="panel rise heartbeat-panel" aria-label="Argus live desk">
        <div className="cockpit-head">
          <div>
            <h2 style={{ marginTop: 0 }}>Live desk</h2>
            <time
              className="argus-live-clock cockpit-clock"
              dateTime={now == null ? undefined : new Date(now).toISOString()}
              aria-live="polite"
            >
              {now == null ? "—" : formatLiveClock(now)}
            </time>
          </div>
          <span className={`status-light ${beatFresh && feedOk ? "ok" : "warn"}`}>
            {beatFresh && feedOk
              ? `Live · ${beatCount || 1}`
              : feedOk
                ? "Updating…"
                : "Catching up"}
          </span>
        </div>

        <div className="status-chip-row" aria-label="Status">
          {statusChips.map((c) => (
            <span key={c.label} className={`status-chip tone-${c.tone}`}>
              <i aria-hidden />
              {c.label}
            </span>
          ))}
        </div>

        <div
          className={`scan-stage${scanning ? " is-scanning" : ""}`}
          aria-live="polite"
          aria-label="Scan progress"
        >
          <div className="scan-stage-main">
            <span className="scan-stage-kicker">
              {scanning ? "Scanning now" : "Next scan"}
            </span>
            <strong className="scan-stage-symbol">
              {scanning
                ? (cockpit.current_market ?? "…")
                : nextScanSec != null
                  ? fmtCountdown(nextScanSec)
                  : "—"}
            </strong>
            <span className="scan-stage-meta">
              {cockpit.scan_progress.scanned}/{cockpit.scan_progress.total} markets
              {md
                ? ` · discovered ${md.promoted_to_radar?.length ?? 0}`
                : ""}
            </span>
          </div>
          <div className="scan-stage-bar" aria-hidden>
            <i style={{ width: `${scanProgressPct}%` }} />
          </div>
          {scanning && cockpit.current_market ? (
            <p className="scan-stage-beam">
              Sweeping <em>{cockpit.current_market}</em>
              {" — "}
              tile highlighted on the wall
            </p>
          ) : md && (md.newly_discovered?.length ?? 0) > 0 ? (
            <p className="scan-stage-beam">
              New on Radar:{" "}
              {(md.newly_discovered ?? [])
                .map((n) => (typeof n === "string" ? n : n.symbol))
                .filter(Boolean)
                .slice(0, 4)
                .join(", ")}
            </p>
          ) : null}
        </div>

        <div className="argus-dial-row dial-row-compact">
          <Dial
            label="Watching"
            valueLabel={String(watchingN)}
            pct={Math.min(100, watchingN * 25)}
            tone={watchingN ? "warn" : "neutral"}
            beating={watchingN > 0}
          />
          <Dial
            label="Open"
            valueLabel={String(openCount)}
            pct={Math.min(100, openCount * 34)}
            tone={openCount ? "ok" : "neutral"}
            beating={openCount > 0}
          />
          <Dial
            label="Open P&L"
            valueLabel={
              openCount === 0 || displayOpenUnrealized == null
                ? "—"
                : moneyPnl(String(displayOpenUnrealized))
            }
            pct={
              openCount === 0 || displayOpenUnrealized == null
                ? 5
                : Math.min(100, 50 + Math.abs(displayOpenUnrealized))
            }
            tone={
              openCount === 0 || displayOpenUnrealized == null
                ? "neutral"
                : displayOpenUnrealized >= 0
                  ? "ok"
                  : "bad"
            }
            beating={openCount > 0}
          />
          <Dial
            label="Closed P&L"
            valueLabel={
              displayClosedCount === 0
                ? "—"
                : displayTotalPnl != null && Number.isFinite(displayTotalPnl)
                  ? moneyPnl(String(displayTotalPnl))
                  : "—"
            }
            pct={
              displayClosedCount === 0
                ? 5
                : Math.min(100, 40 + displayClosedCount * 10)
            }
            tone={
              displayClosedCount === 0
                ? "neutral"
                : (displayTotalPnl ?? 0) >= 0
                  ? "ok"
                  : "bad"
            }
            beating={displayClosedCount > 0}
          />
        </div>

        <div className="action-card-row action-row-compact" aria-label="Manual controls">
          <button
            type="button"
            className="action-card"
            disabled={pending}
            onClick={() =>
              startTransition(async () => {
                const r = await refreshRecentPricesAction();
                setMessage(r.ok ? "Prices updated from exchange" : r.message);
              })
            }
          >
            <strong>Update prices</strong>
          </button>
          <button
            type="button"
            className="action-card"
            disabled={pending}
            onClick={() =>
              startTransition(async () => {
                const r = await runMarketScanAction(true);
                setMessage(r.ok ? "Markets re-scored" : r.message);
              })
            }
          >
            <strong>Re-score now</strong>
          </button>
          {portfolioId ? (
            <div className="action-card mode-card">
              <div className="mode-seg">
                <button
                  type="button"
                  className={mode === "coaching" ? "is-on" : ""}
                  disabled={pending || mode === "coaching"}
                  onClick={() =>
                    startTransition(async () => {
                      const r = await setTrainingModeAction({
                        portfolioId,
                        mode: "coaching",
                      });
                      if (r.ok) setMode("coaching");
                      setMessage(r.ok ? "Coaching on" : r.message);
                    })
                  }
                >
                  You approve
                </button>
                <button
                  type="button"
                  className={mode === "automatic" ? "is-on" : ""}
                  disabled={pending || mode === "automatic"}
                  onClick={() =>
                    startTransition(async () => {
                      const r = await setTrainingModeAction({
                        portfolioId,
                        mode: "automatic",
                      });
                      if (r.ok) setMode("automatic");
                      setMessage(r.ok ? "Auto enter on" : r.message);
                    })
                  }
                >
                  Auto enter
                </button>
              </div>
            </div>
          ) : null}
        </div>

        {(message || keepAliveNote) && (
          <p className="live-flash" role="status">
            {message || keepAliveNote}
          </p>
        )}
      </section>

      <section className="panel rise" aria-label="Market wall">
        <div className="cockpit-head">
          <h2 style={{ marginTop: 0 }}>Markets</h2>
          <span className="muted-note">
            {scanning
              ? `Live sweep · ${cockpit.current_market ?? "…"}`
              : `${cockpit.wall.length} on desk · tap a tile`}
          </span>
        </div>
        <div className="market-wall">
          {wallSorted.length === 0 ? (
            <button
              type="button"
              className="action-card"
              disabled={pending}
              onClick={() =>
                startTransition(async () => {
                  const r = await refreshRecentPricesAction();
                  setMessage(r.message);
                })
              }
            >
              <strong>Load markets</strong>
              <span className="action-card-hint">Update prices first</span>
            </button>
          ) : (
            wallSorted.map((t) => {
              const isScanFocus =
                scanning && cockpit.current_market === t.symbol;
              const isNew =
                popSymbols.has(t.symbol) || Boolean(t.newly_discovered);
              return (
                <button
                  type="button"
                  key={t.symbol}
                  className={[
                    "wall-tile",
                    selected === t.symbol ? "is-selected" : "",
                    flash === t.symbol ? "flash" : "",
                    t.stale ? "is-stale" : "",
                    isScanFocus ? "is-scanning" : "",
                    isNew ? "is-new-discovery" : "",
                    t.discovered ? "is-discovered" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onClick={() => {
                    setUserPinnedUntil(Date.now() + 45_000);
                    setSelected(t.symbol);
                  }}
                >
                  <header>
                    <strong>{t.symbol}</strong>
                    <span
                      className={`fresh-dot ${t.stale ? "is-stale" : "is-fresh"}`}
                      title={t.stale ? "Stale" : "Fresh"}
                    />
                    <span
                      className={`wall-status status-${t.status.replace(/\s+/g, "-").toLowerCase()}`}
                    >
                      {isScanFocus
                        ? "Scanning"
                        : isNew
                          ? "New"
                          : t.status}
                    </span>
                  </header>
                  <div className="wall-price">
                    {t.current_price != null
                      ? money(String(t.current_price))
                      : "—"}
                    {t.pct_change != null ? (
                      <span
                        className={t.pct_change >= 0 ? "pnl-pos" : "pnl-neg"}
                      >
                        {t.pct_change >= 0 ? "+" : ""}
                        {t.pct_change.toFixed(2)}%
                      </span>
                    ) : null}
                  </div>
                  <Sparkline
                    values={t.sparkline}
                    highlight={flash === t.symbol || isScanFocus}
                  />
                  <div className="wall-meta">
                    <span>
                      {t.opportunity_class
                        ? t.opportunity_class.replaceAll("_", " ")
                        : t.outlook}
                    </span>
                    <span>{Math.round(t.signal_strength)}</span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </section>

      <section className="panel rise focus-grid" aria-label="Selected market">
        <div>
          <div className="cockpit-head">
            <h2 style={{ marginTop: 0 }}>{selected ?? "Pick a market"}</h2>
            {watch ? (
              <span className={`status-chip chip-${watch.confidence.toLowerCase()}`}>
                {watch.confidence}
              </span>
            ) : null}
          </div>
          {watch ? (
            <p className="watch-narrative">{watch.narrative}</p>
          ) : (
            <p className="muted-note">
              {tile?.stale ? "Stale — Update prices" : "No active watch on this tile"}
            </p>
          )}
          <CandleChart
            bars={bars}
            entry={entryN}
            stop={stopN}
            target={targetN}
            current={curN}
          />
          <div className="status-chip-row" style={{ marginTop: "0.55rem" }}>
            <span className="status-chip">
              Bars {formatTimestamp(barsAt) || "—"}
            </span>
            {watch?.timeframe ? (
              <span className="status-chip">{watch.timeframe}</span>
            ) : null}
          </div>
          <label className="tech-toggle">
            <input
              type="checkbox"
              checked={showTechInd}
              onChange={(e) => setShowTechInd(e.target.checked)}
            />
            Tech detail
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
          <h3 style={{ marginTop: 0 }}>Checks</h3>
          {watch?.checklist?.length ? (
            <ul className="confirm-list">
              {watch.checklist.map((c) => (
                <li key={c.key} className={`confirm-${c.status}`}>
                  <span>{c.label}</span>
                  <strong aria-label={c.status}>
                    {c.status === "passed" ? "●" : c.status === "failed" ? "✕" : "○"}
                  </strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted-note">No checklist yet</p>
          )}

          <h3>Plan</h3>
          {watch ? (
            <>
              <div className="plan-meters" aria-label="Timers">
                <div>
                  <span>Next look</span>
                  <strong className="countdown">{fmtCountdown(nextEvalLeft)}</strong>
                </div>
                <div>
                  <span>Expires</span>
                  <strong className="countdown">{fmtCountdown(expireLeft)}</strong>
                </div>
                <div>
                  <span>Watched</span>
                  <strong>{fmtCountdown(watchedSec)}</strong>
                </div>
              </div>
              <dl className="considering-dl plan-compact">
                <div>
                  <dt>Entry</dt>
                  <dd>{watch.entry_zone ? money(watch.entry_zone) : "—"}</dd>
                </div>
                <div>
                  <dt>Stop</dt>
                  <dd>{watch.stop_loss ? money(watch.stop_loss) : "—"}</dd>
                </div>
                <div>
                  <dt>Target</dt>
                  <dd>{watch.take_profit ? money(watch.take_profit) : "—"}</dd>
                </div>
                <div>
                  <dt>Size</dt>
                  <dd>{money(String(watch.paper_capital_planned))}</dd>
                </div>
                <div>
                  <dt>Max loss</dt>
                  <dd>
                    {watch.max_dollar_loss != null
                      ? money(String(watch.max_dollar_loss))
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Upside</dt>
                  <dd>
                    {watch.potential_dollar_profit != null
                      ? money(String(watch.potential_dollar_profit))
                      : "—"}
                  </dd>
                </div>
              </dl>
              <RiskRewardBar
                stop={stopN}
                entry={entryN}
                current={curN}
                target={targetN}
              />

              {portfolioId &&
              mode === "coaching" &&
              ["Watching", "Risk Review"].includes(watch.stage_raw) ? (
                <div className="coach-actions">
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
                    Take (paper)
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
                </div>
              ) : null}
            </>
          ) : (
            <p className="muted-note">Tap a Watching / Setup Ready tile</p>
          )}
        </div>
      </section>

      <section className="panel rise desk-activity" aria-label="Activity">
        <div className="live-activity-boards desk-activity-boards">
          <div className="live-activity-col">
            <h3 className="live-activity-title">Watching</h3>
            {watchingList.length === 0 ? (
              <p className="muted-note">Nothing on watch.</p>
            ) : (
              <ul className="live-activity-list">
                {watchingList.slice(0, 6).map((w) => (
                  <li key={w.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setUserPinnedUntil(Date.now() + 45_000);
                        setSelected(w.symbol);
                      }}
                    >
                      <strong>{w.symbol}</strong>
                      <span>{w.stage_raw}</span>
                      <em>{w.why || w.waiting_for}</em>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="live-activity-col">
            <h3 className="live-activity-title">Scan &amp; discovery log</h3>
            {activityLog.length === 0 ? (
              <p className="muted-note">Log fills as Argus scans and discovers.</p>
            ) : (
              <ul className="live-activity-list desk-log-list">
                {activityLog.map((d) => (
                  <li key={d.id} className={`tone-${d.tone}`}>
                    <button
                      type="button"
                      disabled={!d.symbol}
                      onClick={() => {
                        if (!d.symbol) return;
                        setUserPinnedUntil(Date.now() + 45_000);
                        setSelected(d.symbol);
                      }}
                    >
                      <strong>
                        {d.at
                          ? formatAgeLabel(new Date(d.at).toISOString(), now)
                          : "—"}
                      </strong>
                      <em>{d.text}</em>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="live-activity-col">
            <h3 className="live-activity-title">Filtered</h3>
            {(cockpit.rejection_summary?.length ?? 0) === 0 &&
            (md?.rejected_sample?.length ?? 0) === 0 ? (
              <p className="muted-note">No filters this pass.</p>
            ) : (
              <ul className="live-activity-list rejects-tally">
                {(cockpit.rejection_summary ?? []).slice(0, 5).map((r) => (
                  <li key={r.code}>
                    <strong>{r.count}×</strong>
                    <em>{r.why}</em>
                  </li>
                ))}
                {(md?.rejected_sample ?? []).slice(0, 4).map((r, i) => (
                  <li key={`d-${r.symbol ?? i}`}>
                    <strong>{r.symbol ?? "—"}</strong>
                    <em>{r.primary_reason || r.reason || "filtered"}</em>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      <details className="panel rise tech-panel">
        <summary>System detail</summary>
        <div className="status-chip-row" style={{ marginTop: "0.75rem" }}>
          <span className={`status-chip tone-${cockpit.market_data_stale ? "bad" : "ok"}`}>
            Feed {formatTimestamp(cockpit.market_data_at) || "—"}
          </span>
          <span className="status-chip tone-neutral">
            Scan every {Math.max(1, Math.round(cockpit.scan_interval_seconds / 60))}m
          </span>
          <span className="status-chip tone-neutral">
            Watch window {Math.round(cockpit.watch_ttl_seconds / 60)}m
          </span>
          <span className={`status-chip tone-${cockpit.trading_allowed ? "ok" : "warn"}`}>
            {cockpit.trading_allowed ? "Entries open" : "Entries blocked"}
          </span>
          <span className="status-chip tone-neutral">
            At risk {displayAccount.inTrades != null ? money(displayAccount.inTrades) : "—"}
          </span>
          {md ? (
            <span className="status-chip tone-neutral">
              Discovery {md.markets_scanned ?? 0} scanned · {md.rejected_count ?? 0} rejected
            </span>
          ) : null}
        </div>
        <details className="developer-info">
          <summary>Developer</summary>
          <pre className="tech-details">
            {JSON.stringify(
              {
                generated_at: cockpit.generated_at,
                scanner_state: cockpit.scanner_state,
                scan_progress: cockpit.scan_progress,
                next_scan_at: cockpit.next_scan_at,
                market_data_at: cockpit.market_data_at,
                market_discovery: md,
              },
              null,
              2,
            )}
          </pre>
        </details>
      </details>
    </div>
  );
}
