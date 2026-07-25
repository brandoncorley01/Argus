"use client";

import { useEffect, useState } from "react";

import type { FounderActivityItem } from "@/lib/founder/activityFeed";
import { formatTimestamp } from "@/lib/format";

export function ActivityFeed({
  initialItems,
  pollMs = 15_000,
}: {
  initialItems: FounderActivityItem[];
  pollMs?: number;
}) {
  const [items, setItems] = useState(initialItems);

  useEffect(() => {
    setItems(initialItems);
  }, [initialItems]);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const res = await fetch("/api/founder/activity", { cache: "no-store" });
        if (!res.ok) return;
        const data = (await res.json()) as { items?: FounderActivityItem[] };
        if (!cancelled && Array.isArray(data.items)) {
          setItems(data.items);
        }
      } catch {
        /* keep last good snapshot */
      }
    }
    const id = window.setInterval(tick, pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollMs]);

  if (items.length === 0) {
    return (
      <p className="muted-note" style={{ margin: 0 }}>
        No recent institutional activity yet. Heartbeats, paper fills, and risk
        events will appear here.
      </p>
    );
  }

  return (
    <ul className="activity-feed">
      {items.map((item) => (
        <li key={item.id} className={`activity-item activity-${item.tone}`}>
          <div className="activity-when">{formatTimestamp(item.at)}</div>
          <div className="activity-title">{item.title}</div>
          <div className="activity-detail">{item.detail}</div>
        </li>
      ))}
    </ul>
  );
}
