"use client";

import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui";
import type { DecisionItem } from "@/lib/founder/decisionStream";
import { formatAgeLabel, formatTimestamp } from "@/lib/format";

export function DecisionStream({
  initialItems,
  pollMs = 3_000,
}: {
  initialItems: DecisionItem[];
  pollMs?: number;
}) {
  const [items, setItems] = useState(initialItems);
  const [showTechnical, setShowTechnical] = useState(false);
  const [now, setNow] = useState<number | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  useEffect(() => {
    setItems(initialItems);
  }, [initialItems]);

  useEffect(() => {
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;
    async function tick() {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await fetch("/api/founder/decisions", {
          cache: "no-store",
          signal: AbortSignal.timeout(12_000),
        });
        if (!res.ok) return;
        const data = (await res.json()) as { items?: DecisionItem[] };
        if (!cancelled && Array.isArray(data.items)) {
          setItems(data.items);
          setUpdatedAt(new Date().toISOString());
        }
      } catch {
        /* keep last good snapshot */
      } finally {
        inFlight = false;
      }
    }
    void tick();
    const id = window.setInterval(tick, pollMs);

    const onVisible = () => {
      if (document.visibilityState === "visible") void tick();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [pollMs]);

  if (items.length === 0) {
    return (
      <EmptyState>
        No market or trading decisions yet. Technical supervisor noise is hidden
        here by default.
      </EmptyState>
    );
  }

  return (
    <div className="decision-live-pane">
      <div className="decision-live-meta" aria-live="polite">
        <span className="status-chip tone-ok">
          <i aria-hidden />
          Live decisions
        </span>
        <span className="muted-note countdown">
          Pane {formatAgeLabel(updatedAt, now)}
        </span>
      </div>
      <ul className="activity-feed">
        {items.map((item) => (
          <li key={item.id} className={`activity-item activity-${item.tone}`}>
            <div className="activity-when">
              <span className="countdown decision-age" title={formatTimestamp(item.at)}>
                {formatAgeLabel(item.at, now)}
              </span>
              <span className="decision-when-abs">{formatTimestamp(item.at)}</span>
            </div>
            <div className="activity-title">
              {item.symbol ? `${item.symbol} · ` : ""}
              {item.event}
            </div>
            <div className="activity-detail">
              Outcome: {item.outcome}
              {item.reason ? ` — ${item.reason}` : ""}
              {item.strategy ? ` · ${item.strategy}` : ""}
            </div>
            {showTechnical && item.correlationId ? (
              <div className="activity-detail">Trace {item.correlationId}</div>
            ) : null}
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="btn secondary"
        style={{ marginTop: "0.75rem" }}
        onClick={() => setShowTechnical((v) => !v)}
      >
        {showTechnical ? "Hide technical IDs" : "Show technical IDs"}
      </button>
    </div>
  );
}
