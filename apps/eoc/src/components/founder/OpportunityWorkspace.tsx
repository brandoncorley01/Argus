"use client";

import { useEffect, useState } from "react";

import {
  OpportunityRadar,
  type ScanCandidate,
} from "@/components/founder/OpportunityRadar";
import {
  WatchedCandidateChart,
  type ScanBar,
} from "@/components/founder/WatchedCandidateChart";

export function OpportunityWorkspace({
  candidates,
  scannedCount,
}: {
  candidates: ScanCandidate[];
  scannedCount: number;
}) {
  const initial =
    candidates.find((c) => c.stage !== "Rejected")?.id ?? candidates[0]?.id ?? null;
  const [selectedId, setSelectedId] = useState<string | null>(initial);
  const selected = candidates.find((c) => c.id === selectedId) ?? null;
  const [bars, setBars] = useState<ScanBar[]>([]);
  const [timeframe, setTimeframe] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!selected) {
        setBars([]);
        setTimeframe(null);
        return;
      }
      try {
        const res = await fetch(
          `/api/founder/scan-bars?symbol=${encodeURIComponent(selected.symbol)}`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as {
          bars?: ScanBar[];
          timeframe?: string | null;
        };
        if (!cancelled) {
          setBars(Array.isArray(data.bars) ? data.bars : []);
          setTimeframe(data.timeframe ?? null);
        }
      } catch {
        if (!cancelled) {
          setBars([]);
          setTimeframe(null);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [selected]);

  return (
    <div className="grid grid-2 opportunity-workspace">
      <section className="panel" aria-label="Opportunity radar">
        <h2 style={{ marginTop: 0 }}>Opportunity Radar</h2>
        <OpportunityRadar
          candidates={candidates}
          scannedCount={scannedCount}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </section>
      <section className="panel" aria-label="Watched candidate">
        <h2 style={{ marginTop: 0 }}>Watched candidate</h2>
        <WatchedCandidateChart
          candidate={selected}
          bars={bars}
          timeframe={timeframe}
        />
      </section>
    </div>
  );
}
