import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  Clock,
  Database,
  Gauge,
  LineChart,
  ListFilter,
  RefreshCw,
  Search,
  Target,
  Waves
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart as ReLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { api, DerivedMetric, Market, Opportunity, OrderbookSnapshot, SharpBookLimit, SharpBookOdds } from "./api";

type OpportunityKind = "all" | "stale" | "market-making" | "queue-positioning";
type SideMode = "yes" | "no";

const opportunityTabs: { id: OpportunityKind; label: string }[] = [
  { id: "all", label: "All" },
  { id: "stale", label: "Stale" },
  { id: "market-making", label: "Market making" },
  { id: "queue-positioning", label: "Queue" }
];

export function App() {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [kind, setKind] = useState<OpportunityKind>("all");
  const [sideMode, setSideMode] = useState<SideMode>("no");

  const marketsQuery = useQuery({ queryKey: ["markets"], queryFn: api.markets });
  const opportunitiesQuery = useQuery({
    queryKey: ["opportunities", kind],
    queryFn: () => api.opportunities(kind === "all" ? undefined : kind)
  });

  const pregameMarkets = useMemo(() => {
    return (marketsQuery.data ?? [])
      .filter((market) => isPregameMarket(market))
      .sort((left, right) => compareMarketStartTime(left, right));
  }, [marketsQuery.data]);

  const pregameOpportunities = useMemo(() => {
    return (opportunitiesQuery.data ?? []).filter((opportunity) => isPregameMarket(opportunity.market));
  }, [opportunitiesQuery.data]);

  const selectedMarket = useMemo(() => {
    if (!pregameMarkets.length) return null;
    if (selectedTicker) {
      return pregameMarkets.find((market) => market.ticker === selectedTicker) ?? pregameMarkets[0];
    }
    return pregameMarkets[0];
  }, [pregameMarkets, selectedTicker]);

  const metricsQuery = useQuery({
    queryKey: ["metrics", selectedMarket?.ticker],
    queryFn: () => api.metrics(selectedMarket!.ticker),
    enabled: Boolean(selectedMarket)
  });
  const orderbooksQuery = useQuery({
    queryKey: ["orderbooks", selectedMarket?.ticker],
    queryFn: () => api.orderbooks(selectedMarket!.ticker),
    enabled: Boolean(selectedMarket)
  });
  const sharpOddsQuery = useQuery({
    queryKey: ["sharp-odds", selectedMarket?.ticker, sideMode],
    queryFn: () => api.sharpOdds(selectedMarket!.ticker, sideMode),
    enabled: Boolean(selectedMarket)
  });
  const limitsQuery = useQuery({
    queryKey: ["limits", selectedMarket?.ticker],
    queryFn: () => api.limits(selectedMarket!.ticker),
    enabled: Boolean(selectedMarket)
  });

  const latestByMarketId = useMemo(() => {
    const map = new Map<number, Opportunity>();
    for (const opportunity of pregameOpportunities) {
      if (!map.has(opportunity.market.id)) map.set(opportunity.market.id, opportunity);
    }
    return map;
  }, [pregameOpportunities]);

  const filteredMarkets = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return pregameMarkets.filter((market) => {
      const matchesStatus = status === "all" || market.status === status;
      const text = `${market.ticker} ${market.league ?? ""} ${market.market_type ?? ""} ${
        market.event_title ?? ""
      }`.toLowerCase();
      return matchesStatus && (!normalized || text.includes(normalized));
    });
  }, [pregameMarkets, query, status]);

  const statuses = useMemo(() => {
    return Array.from(new Set(pregameMarkets.map((market) => market.status).filter(Boolean))).sort();
  }, [pregameMarkets]);

  const latestMetric = metricsQuery.data?.[0] ?? latestByMarketId.get(selectedMarket?.id ?? -1)?.metric ?? null;
  const latestOrderbook = orderbooksQuery.data?.[0] ?? null;

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Kalshi Research</p>
          <h1>Market Microstructure Console</h1>
        </div>
        <div className="top-actions">
          <HealthPill />
          <button
            className="icon-button"
            title="Refresh data"
            onClick={() => {
              void marketsQuery.refetch();
              void opportunitiesQuery.refetch();
              void metricsQuery.refetch();
              void orderbooksQuery.refetch();
              void sharpOddsQuery.refetch();
              void limitsQuery.refetch();
            }}
          >
            <RefreshCw size={18} />
          </button>
        </div>
      </header>

      <section className="kpi-strip">
        <Kpi label="Pregame markets" value={pregameMarkets.length} icon={<Database size={18} />} />
        <Kpi label="Opportunities" value={pregameOpportunities.length} icon={<Target size={18} />} />
        <Kpi label="Avg spread" value={formatCents(avgMetric(pregameOpportunities, "spread"))} icon={<Waves size={18} />} />
        <Kpi label="Avg liquidity" value={formatScore(avgMetric(pregameOpportunities, "liquidity_score"))} icon={<Gauge size={18} />} />
      </section>

      <section className="workspace">
        <aside className="market-panel">
          <div className="panel-heading">
            <div>
              <h2>Markets</h2>
              <p>{filteredMarkets.length} visible</p>
            </div>
          </div>
          <div className="filters">
            <label className="search-box">
              <Search size={16} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search ticker, league, event" />
            </label>
            <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter status">
              <option value="all">All statuses</option>
              {statuses.map((item) => (
                <option key={item ?? ""} value={item ?? ""}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <SideToggle value={sideMode} onChange={setSideMode} />
          <MarketTable
            markets={filteredMarkets}
            latestByMarketId={latestByMarketId}
            selectedTicker={selectedMarket?.ticker ?? null}
            onSelect={setSelectedTicker}
            sideMode={sideMode}
            loading={marketsQuery.isLoading}
          />
        </aside>

        <section className="detail-panel">
          <OpportunityTabs kind={kind} onChange={setKind} />
          <OpportunityList
            opportunities={pregameOpportunities}
            loading={opportunitiesQuery.isLoading}
            selectedTicker={selectedMarket?.ticker ?? null}
            onSelect={setSelectedTicker}
          />
          <MarketDetail
            market={selectedMarket}
            metric={latestMetric}
            orderbook={latestOrderbook}
            metrics={metricsQuery.data ?? []}
            orderbooks={orderbooksQuery.data ?? []}
            sharpOdds={sharpOddsQuery.data ?? []}
            limits={limitsQuery.data ?? []}
            sideMode={sideMode}
            loading={metricsQuery.isLoading || orderbooksQuery.isLoading || sharpOddsQuery.isLoading || limitsQuery.isLoading}
          />
        </section>
      </section>
    </main>
  );
}

function HealthPill() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}/health`);
      return response.ok;
    },
    refetchInterval: 15_000
  });
  return <span className={healthQuery.data ? "health ok" : "health"}>{healthQuery.data ? "API online" : "API offline"}</span>;
}

function Kpi({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return (
    <div className="kpi">
      <div className="kpi-icon">{icon}</div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function SideToggle({ value, onChange }: { value: SideMode; onChange: (value: SideMode) => void }) {
  return (
    <div className="side-toggle" aria-label="Displayed contract side">
      <button className={value === "no" ? "active" : ""} onClick={() => onChange("no")}>
        NO side
      </button>
      <button className={value === "yes" ? "active" : ""} onClick={() => onChange("yes")}>
        YES side
      </button>
    </div>
  );
}

function MarketTable({
  markets,
  latestByMarketId,
  selectedTicker,
  onSelect,
  sideMode,
  loading
}: {
  markets: Market[];
  latestByMarketId: Map<number, Opportunity>;
  selectedTicker: string | null;
  onSelect: (ticker: string) => void;
  sideMode: SideMode;
  loading: boolean;
}) {
  if (loading) return <EmptyState title="Loading markets" detail="Waiting for the API response." />;
  if (!markets.length) return <EmptyState title="No markets yet" detail="Run the worker discovery and ingestion jobs to populate this table." />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Game</th>
            <th>Start</th>
            <th>Spread</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {markets.map((market) => {
            const opportunity = latestByMarketId.get(market.id);
            return (
              <tr
                key={market.id}
                className={selectedTicker === market.ticker ? "selected" : ""}
                onClick={() => onSelect(market.ticker)}
              >
                <td>
                  <strong>{gameTitle(market)}</strong>
                  <span>{marketSideLabel(market, sideMode)} · {market.league ?? "mlb"}</span>
                </td>
                <td>{formatStartTime(market)}</td>
                <td>{formatCents(opportunity?.metric?.spread)}</td>
                <td>{formatCents(sideEdge(opportunity?.metric, sideMode))}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function OpportunityTabs({ kind, onChange }: { kind: OpportunityKind; onChange: (kind: OpportunityKind) => void }) {
  return (
    <div className="tabs">
      {opportunityTabs.map((tab) => (
        <button key={tab.id} className={kind === tab.id ? "active" : ""} onClick={() => onChange(tab.id)}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function OpportunityList({
  opportunities,
  loading,
  selectedTicker,
  onSelect
}: {
  opportunities: Opportunity[];
  loading: boolean;
  selectedTicker: string | null;
  onSelect: (ticker: string) => void;
}) {
  if (loading) return <EmptyState title="Loading opportunities" detail="Scores refresh every 30 seconds." />;
  if (!opportunities.length) return <EmptyState title="No scored opportunities" detail="Metrics and scores will appear after snapshots are ingested." />;
  return (
    <div className="opportunity-grid">
      {opportunities.slice(0, 12).map((opportunity) => (
        <button
          key={`${opportunity.market.id}-${opportunity.score.id}`}
          className={selectedTicker === opportunity.market.ticker ? "opportunity active" : "opportunity"}
          onClick={() => onSelect(opportunity.market.ticker)}
        >
          <span>{opportunity.market.ticker}</span>
          <strong>{formatScore(bestOpportunityScore(opportunity))}</strong>
          <small>
            stale {formatScore(opportunity.score.stale_opportunity_score)} · mm{" "}
            {formatScore(opportunity.score.market_making_score)}
          </small>
        </button>
      ))}
    </div>
  );
}

function MarketDetail({
  market,
  metric,
  orderbook,
  metrics,
  orderbooks,
  sharpOdds,
  limits,
  sideMode,
  loading
}: {
  market: Market | null;
  metric: DerivedMetric | null;
  orderbook: OrderbookSnapshot | null;
  metrics: DerivedMetric[];
  orderbooks: OrderbookSnapshot[];
  sharpOdds: SharpBookOdds[];
  limits: SharpBookLimit[];
  sideMode: SideMode;
  loading: boolean;
}) {
  if (!market) return <EmptyState title="Select a market" detail="Market details will appear once discovery finds active tickers." />;
  const priceChartData = buildPriceChartData(metrics, orderbooks, sideMode);
  const sharpChartData = buildSharpOddsChartData(sharpOdds);
  const limitChartData = buildLimitChartData(limits);
  const fairPrice = sideFairPrice(metric, sideMode);
  const edge = sideEdge(metric, sideMode);
  return (
    <section className="market-detail">
      <div className="detail-header">
        <div>
          <p className="eyebrow">{market.league ?? "league"} · {market.market_type ?? "market"} · {formatStartTime(market)}</p>
          <h2>{gameTitle(market)}</h2>
          <p>{marketSideLabel(market, sideMode)} · {market.ticker}</p>
        </div>
        <span className="status">{market.status ?? "unknown"}</span>
      </div>

      <div className="metric-grid">
        <Kpi label={`${sideMode.toUpperCase()} fair`} value={formatCents(fairPrice)} icon={<Target size={18} />} />
        <Kpi label={`Edge ${sideMode}`} value={formatCents(edge)} icon={<Activity size={18} />} />
        <Kpi label="Spread" value={formatCents(metric?.spread)} icon={<Waves size={18} />} />
        <Kpi label="Depth" value={orderbook?.total_depth ?? "-"} icon={<BarChart3 size={18} />} />
        <Kpi label="Volatility" value={formatScore(metric?.volatility_score)} icon={<LineChart size={18} />} />
        <Kpi label="Sharp rows" value={sharpOdds.length} icon={<ListFilter size={18} />} />
      </div>

      <NoQueuePanel orderbook={orderbook} />

      <div className="chart-panel">
        <div className="panel-heading">
          <div>
            <h2>{sideMode.toUpperCase()} Depth Ladder</h2>
            <p>{sideMode === "no" ? "Queue depth at and below our maker side" : "YES-side bid depth by price"}</p>
          </div>
        </div>
        {orderbook ? (
          <DepthLadderChart orderbook={orderbook} sideMode={sideMode} />
        ) : (
          <EmptyState title="No depth snapshot" detail="Depth bars will appear after the next orderbook poll." />
        )}
      </div>

      <div className="chart-panel">
        <div className="panel-heading">
          <div>
            <h2>Kalshi Price, Fair, Depth</h2>
            <p>{loading ? "Loading series" : `${priceChartData.length} points`}</p>
          </div>
        </div>
        {priceChartData.length ? (
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={priceChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#d9e2df" />
              <XAxis dataKey="time" minTickGap={24} />
              <YAxis yAxisId="price" domain={[0, 100]} />
              <YAxis yAxisId="depth" orientation="right" tickFormatter={(value) => compactNumber(Number(value))} />
              <Tooltip />
              <Bar yAxisId="depth" dataKey="depth" fill="#c9ddd6" radius={[3, 3, 0, 0]} />
              <Line yAxisId="price" type="monotone" dataKey="bestYesBid" stroke="#1f7a5b" dot={false} strokeWidth={2} />
              <Line yAxisId="price" type="monotone" dataKey="fair" stroke="#854d0e" dot={false} strokeWidth={2} />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState title="No time series yet" detail="Orderbook and metric snapshots will chart here after ingestion starts." />
        )}
      </div>

      <div className="chart-row">
        <div className="chart-panel">
          <div className="panel-heading">
            <div>
              <h2>Sharp YES Fair</h2>
              <p>{sharpChartData.length ? `${sharpChartData.length} points` : "No sharp odds yet"}</p>
            </div>
          </div>
          {sharpChartData.length ? <SharpOddsChart data={sharpChartData} /> : <EmptyState title="No sharp odds" detail="Check the ODDSJAM key and worker logs." />}
        </div>
        <div className="chart-panel">
          <div className="panel-heading">
            <div>
              <h2>Pinnacle Limits</h2>
              <p>{limitChartData.length ? `${limitChartData.length} points` : "No limit snapshots yet"}</p>
            </div>
          </div>
          {limitChartData.length ? <LimitChart data={limitChartData} /> : <EmptyState title="No Pinnacle limits" detail="Limits appear when Optic returns limits.max." />}
        </div>
      </div>
    </section>
  );
}

function SharpOddsChart({ data }: { data: Record<string, string | number | null>[] }) {
  const books = ["Pinnacle", "Circa Sports", "BetOnline", "Betcris"];
  const colors = ["#1f7a5b", "#315f85", "#854d0e", "#7a4e9f"];
  return (
    <ResponsiveContainer width="100%" height={220}>
      <ReLineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#d9e2df" />
        <XAxis dataKey="time" minTickGap={22} />
        <YAxis domain={[0, 100]} />
        <Tooltip />
        {books.map((book, index) => (
          <Line key={book} type="monotone" dataKey={book} stroke={colors[index]} dot={false} strokeWidth={2} connectNulls />
        ))}
      </ReLineChart>
    </ResponsiveContainer>
  );
}

function LimitChart({ data }: { data: Record<string, string | number | null>[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <ReLineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#d9e2df" />
        <XAxis dataKey="time" minTickGap={22} />
        <YAxis />
        <Tooltip />
        <Line type="monotone" dataKey="Pinnacle" stroke="#1f7a5b" dot={false} strokeWidth={2} connectNulls />
      </ReLineChart>
    </ResponsiveContainer>
  );
}

function DepthLadderChart({ orderbook, sideMode }: { orderbook: OrderbookSnapshot; sideMode: SideMode }) {
  const data = buildDepthLadderData(orderbook, sideMode);
  if (!data.length) {
    return <EmptyState title="No displayed depth" detail="This side has no visible bid ladder in the latest snapshot." />;
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 28, bottom: 8, left: 28 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#d9e2df" horizontal={false} />
        <XAxis type="number" tickFormatter={(value) => compactNumber(Number(value))} />
        <YAxis type="category" dataKey="price" width={58} />
        <Tooltip formatter={(value) => formatInteger(Number(value))} labelFormatter={(label) => `${sideMode.toUpperCase()} ${label}`} />
        <Bar dataKey="depth" fill="#1f7a5b" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function NoQueuePanel({ orderbook }: { orderbook: OrderbookSnapshot | null }) {
  const bestNoBid = orderbook?.best_no_bid ?? null;
  const noBook = orderbook?.no_book ?? {};
  const depthAtBest = bestNoBid === null ? null : noBook[String(bestNoBid)] ?? 0;
  const depthMinusOne = bestNoBid === null ? null : noBook[String(bestNoBid - 1)] ?? 0;
  const depthMinusTwo = bestNoBid === null ? null : noBook[String(bestNoBid - 2)] ?? 0;

  return (
    <div className="queue-panel">
      <div>
        <span>Best NO bid</span>
        <strong>{formatCents(bestNoBid)}</strong>
      </div>
      <div>
        <span>NO ask</span>
        <strong>{formatCents(orderbook?.best_no_ask)}</strong>
      </div>
      <div>
        <span>Depth at bid</span>
        <strong>{formatInteger(depthAtBest)}</strong>
      </div>
      <div>
        <span>Depth -1c</span>
        <strong>{formatInteger(depthMinusOne)}</strong>
      </div>
      <div>
        <span>Depth -2c</span>
        <strong>{formatInteger(depthMinusTwo)}</strong>
      </div>
    </div>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

function buildPriceChartData(metrics: DerivedMetric[], orderbooks: OrderbookSnapshot[], sideMode: SideMode) {
  const metricByMinute = new Map<string, DerivedMetric>();
  for (const metric of metrics) {
    metricByMinute.set(metric.timestamp.slice(0, 16), metric);
  }
  return [...orderbooks]
    .reverse()
    .map((orderbook) => {
      const metric = metricByMinute.get(orderbook.timestamp.slice(0, 16));
      const fair = sideFairPrice(metric ?? null, sideMode);
      return {
        time: new Date(orderbook.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        bestYesBid: sideMode === "no" ? orderbook.best_no_bid : orderbook.best_yes_bid,
        fair,
        depth: orderbook.total_depth
      };
    })
    .slice(-80);
}

function buildSharpOddsChartData(odds: SharpBookOdds[]) {
  const byMinute = new Map<string, Record<string, string | number | null>>();
  for (const row of [...odds].reverse()) {
    const key = row.timestamp.slice(0, 16);
    const item =
      byMinute.get(key) ??
      ({
        time: new Date(row.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      } as Record<string, string | number | null>);
    item[row.sportsbook] = Math.round(((row.devigged_probability ?? row.implied_probability) || 0) * 1000) / 10;
    byMinute.set(key, item);
  }
  return Array.from(byMinute.values()).slice(-120);
}

function buildLimitChartData(limits: SharpBookLimit[]) {
  const byMinute = new Map<string, Record<string, string | number | null>>();
  for (const row of [...limits].reverse()) {
    const key = row.timestamp.slice(0, 16);
    const item =
      byMinute.get(key) ??
      ({
        time: new Date(row.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      } as Record<string, string | number | null>);
    item[row.sportsbook] = row.limit_amount;
    byMinute.set(key, item);
  }
  return Array.from(byMinute.values()).slice(-120);
}

function buildDepthLadderData(orderbook: OrderbookSnapshot, sideMode: SideMode) {
  const book = sideMode === "no" ? orderbook.no_book : orderbook.yes_book;
  const bestBid = sideMode === "no" ? orderbook.best_no_bid : orderbook.best_yes_bid;
  if (!book || bestBid === null || bestBid === undefined) return [];

  return Object.entries(book)
    .map(([price, depth]) => ({ priceCents: Number(price), depth }))
    .filter((row) => Number.isFinite(row.priceCents) && row.depth > 0 && row.priceCents <= bestBid)
    .sort((left, right) => right.priceCents - left.priceCents)
    .slice(0, 12)
    .map((row) => ({
      price: row.priceCents === bestBid ? `${row.priceCents}c best` : `${row.priceCents}c`,
      depth: row.depth
    }));
}

function bestOpportunityScore(opportunity?: Opportunity) {
  if (!opportunity) return null;
  return Math.max(
    opportunity.score.queue_positioning_score,
    opportunity.score.stale_opportunity_score,
    opportunity.score.market_making_score,
    opportunity.score.maker_stress_score
  );
}

function avgMetric(opportunities: Opportunity[] | undefined, key: keyof DerivedMetric) {
  const values = (opportunities ?? [])
    .map((opportunity) => opportunity.metric?.[key])
    .filter((value): value is number => typeof value === "number");
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function formatCents(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value)}c`;
}

function formatScore(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return Math.round(value).toString();
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value >= 10 ? Math.round(value).toString() : value.toFixed(1);
}

function formatInteger(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return Math.round(value).toLocaleString();
}

function compactNumber(value: number) {
  if (value >= 1_000_000) return `${Math.round(value / 100_000) / 10}M`;
  if (value >= 1_000) return `${Math.round(value / 100) / 10}K`;
  return `${Math.round(value)}`;
}

function gameTitle(market: Market) {
  return (market.event_title ?? market.ticker).replace(/\s+Winner\?$/i, "");
}

function marketSelection(market: Market) {
  const parts = market.ticker.split("-");
  return parts[parts.length - 1] ?? market.ticker;
}

function marketSideLabel(market: Market, sideMode: SideMode) {
  return `${sideMode.toUpperCase()} ${marketSelection(market)}`;
}

function sideFairPrice(metric: DerivedMetric | null | undefined, sideMode: SideMode) {
  const fairYes = metric?.consensus_fair_price;
  if (fairYes === null || fairYes === undefined) return null;
  return sideMode === "no" ? 100 - fairYes : fairYes;
}

function sideEdge(metric: DerivedMetric | null | undefined, sideMode: SideMode) {
  return sideMode === "no" ? metric?.edge_no : metric?.edge_yes;
}

function isPregameMarket(market: Market) {
  const status = (market.status ?? "").toLowerCase();
  if (["live", "completed", "closed", "settled", "expired", "finalized", "resolved", "inactive"].includes(status)) {
    return false;
  }
  const startTime = marketStartTime(market);
  if (!startTime) return false;
  return startTime.getTime() > Date.now();
}

function compareMarketStartTime(left: Market, right: Market) {
  const leftStart = marketStartTime(left)?.getTime() ?? Number.MAX_SAFE_INTEGER;
  const rightStart = marketStartTime(right)?.getTime() ?? Number.MAX_SAFE_INTEGER;
  if (leftStart !== rightStart) return leftStart - rightStart;
  return left.ticker.localeCompare(right.ticker);
}

function marketStartTime(market: Market) {
  if (market.event_start_time) return parseApiDate(market.event_start_time);
  return parseKalshiTickerStart(market.ticker);
}

function parseApiDate(value: string) {
  const hasTimezone = /(?:z|[+-]\d\d:\d\d)$/i.test(value);
  const date = new Date(hasTimezone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function parseKalshiTickerStart(ticker: string) {
  const match = ticker.match(/-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})/);
  if (!match) return null;
  const [, yearText, monthText, dayText, hourText, minuteText] = match;
  const month = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"].indexOf(monthText);
  if (month < 0) return null;
  const year = 2000 + Number(yearText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const date = new Date(Date.UTC(year, month, day, hour + 4, minute));
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatStartTime(market: Market) {
  const startTime = marketStartTime(market);
  if (!startTime) return "-";
  return startTime.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}
