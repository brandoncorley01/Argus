import type { Metadata } from "next";

import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import { soft } from "@/lib/server/control-plane";
import { apiFetch } from "@/lib/server/api";

export const metadata: Metadata = { title: "Market Intelligence" };

type ProviderRow = {
  provider: {
    provider_key: string;
    display_name: string;
    provider_kind: string;
    is_enabled: boolean;
    priority: number;
  };
  health: {
    status: string;
    consecutive_failures: number;
    last_success_at: string | null;
    last_error: string | null;
  } | null;
};

type Observation = {
  id: string;
  channel: string;
  title: string;
  observed_at: string;
  source_attribution: string;
};

type Quality = {
  id: string;
  kind: string;
  message: string;
  detected_at: string;
  channel: string | null;
};

async function getProviders() {
  return apiFetch<ProviderRow[]>("/api/v1/market/providers");
}
async function getObservations() {
  return apiFetch<Observation[]>("/api/v1/market/observations", {
    searchParams: { limit: 25 },
  });
}
async function getNews() {
  return apiFetch<Array<{ id: string; headline: string; published_at: string; source_attribution: string }>>(
    "/api/v1/market/news",
    { searchParams: { limit: 20 } },
  );
}
async function getCalendar() {
  return apiFetch<Array<{ id: string; title: string; scheduled_at: string; country: string | null; source_attribution: string }>>(
    "/api/v1/market/calendar",
    { searchParams: { limit: 20 } },
  );
}
async function getResearch() {
  return apiFetch<Array<{ id: string; title: string; published_at: string; source_attribution: string }>>(
    "/api/v1/market/research",
    { searchParams: { limit: 20 } },
  );
}
async function getQuality() {
  return apiFetch<Quality[]>("/api/v1/market/quality", {
    searchParams: { open_only: "true", limit: 50 },
  });
}
async function getBars() {
  return apiFetch<Array<{ id: string; timeframe: string; open_time: string; close: string; source_attribution: string; instrument_id: string }>>(
    "/api/v1/market/bars",
    { searchParams: { limit: 20 } },
  );
}

export default async function MarketPage() {
  await requireUser();
  const [providers, observations, news, calendar, research, quality, bars] =
    await Promise.all([
      soft(getProviders),
      soft(getObservations),
      soft(getNews),
      soft(getCalendar),
      soft(getResearch),
      soft(getQuality),
      soft(getBars),
    ]);

  return (
    <>
      <PageHeader
        title="Market Intelligence"
        description="Observation-only institutional intelligence. No signals, recommendations, orders, or positions. Empty lists mean no ingested data—not fabricated market prices."
      />

      <div className="grid grid-2" style={{ marginBottom: "1rem" }}>
        <Panel title="Provider registry & health">
          {!providers ? (
            <ErrorState>Providers unavailable.</ErrorState>
          ) : providers.length === 0 ? (
            <EmptyState>No providers registered.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Kind</th>
                    <th>Enabled</th>
                    <th>Health</th>
                    <th>Last success</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.map((row) => (
                    <tr key={row.provider.provider_key}>
                      <td>
                        <strong>{row.provider.display_name}</strong>
                        <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
                          {row.provider.provider_key}
                        </div>
                      </td>
                      <td>{row.provider.provider_kind}</td>
                      <td>{row.provider.is_enabled ? "yes" : "no"}</td>
                      <td>
                        <StatusBadge
                          status={row.health?.status}
                          label={row.health?.status ?? "unknown"}
                        />
                      </td>
                      <td>{formatTimestamp(row.health?.last_success_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Data quality findings">
          {!quality ? (
            <ErrorState>Quality API unavailable.</ErrorState>
          ) : quality.length === 0 ? (
            <EmptyState>No open quality findings.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Kind</th>
                    <th>Message</th>
                    <th>Detected</th>
                  </tr>
                </thead>
                <tbody>
                  {quality.map((q) => (
                    <tr key={q.id}>
                      <td>{q.kind}</td>
                      <td>{q.message}</td>
                      <td>{formatTimestamp(q.detected_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-2" style={{ marginBottom: "1rem" }}>
        <Panel title="Historical bars (ingested only)">
          {!bars ? (
            <ErrorState>Bars unavailable.</ErrorState>
          ) : bars.length === 0 ? (
            <EmptyState>
              No OHLCV bars stored. Use authenticated ingest — Argus does not invent prices.
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Open time</th>
                    <th>TF</th>
                    <th>Close</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {bars.map((b) => (
                    <tr key={b.id}>
                      <td>{formatTimestamp(b.open_time)}</td>
                      <td>{b.timeframe}</td>
                      <td>{b.close}</td>
                      <td>{b.source_attribution}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Normalized observations">
          {!observations ? (
            <ErrorState>Observations unavailable.</ErrorState>
          ) : observations.length === 0 ? (
            <EmptyState>No observations yet.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Channel</th>
                    <th>Title</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {observations.map((o) => (
                    <tr key={o.id}>
                      <td>{formatTimestamp(o.observed_at)}</td>
                      <td>{o.channel}</td>
                      <td>{o.title}</td>
                      <td>{o.source_attribution}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-3">
        <Panel title="News">
          {!news ? (
            <ErrorState>Unavailable</ErrorState>
          ) : news.length === 0 ? (
            <EmptyState>No news items.</EmptyState>
          ) : (
            <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
              {news.map((n) => (
                <li key={n.id}>
                  {n.headline}
                  <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
                    {formatTimestamp(n.published_at)} · {n.source_attribution}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Economic calendar">
          {!calendar ? (
            <ErrorState>Unavailable</ErrorState>
          ) : calendar.length === 0 ? (
            <EmptyState>No calendar events.</EmptyState>
          ) : (
            <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
              {calendar.map((e) => (
                <li key={e.id}>
                  {e.title}
                  <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
                    {formatTimestamp(e.scheduled_at)} · {e.country ?? "—"}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Research feeds">
          {!research ? (
            <ErrorState>Unavailable</ErrorState>
          ) : research.length === 0 ? (
            <EmptyState>No research items.</EmptyState>
          ) : (
            <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
              {research.map((r) => (
                <li key={r.id}>
                  {r.title}
                  <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
                    {formatTimestamp(r.published_at)} · {r.source_attribution}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
