import { useEffect, useMemo, useState } from "react";
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
  Cell,
  ComposedChart,
  Line,
  LineChart as ReLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  api,
  DerivedMetric,
  Market,
  MarketFeatureBucket,
  MarketVolumeSummary,
  Opportunity,
  OrderbookSnapshot,
  SharpBookLimit,
  SharpBookOdds
} from "./api";

type OpportunityKind = "all" | "stale" | "market-making" | "queue-positioning";
type SideMode = "yes" | "no";
type MarketScope = "upcoming" | "live" | "past" | "all";
type TimeWindow = "15m" | "30m" | "1h" | "3h" | "all";
type MarketSort = "start" | "volume_total" | "volume_30m" | "volume_1h" | "volume_3h";
type DashboardMode = "all" | "itf";
type DepthLadderDatum = {
  price: string;
  priceCents: number;
  depth: number;
};

const opportunityTabs: { id: OpportunityKind; label: string }[] = [
  { id: "all", label: "All" },
  { id: "stale", label: "Stale" },
  { id: "market-making", label: "Market making" },
  { id: "queue-positioning", label: "Queue" }
];

const marketScopes: { id: MarketScope; label: string }[] = [
  { id: "upcoming", label: "Upcoming" },
  { id: "live", label: "Live" },
  { id: "past", label: "Past" },
  { id: "all", label: "All" }
];

const timeWindows: { id: TimeWindow; label: string; minutes: number | null }[] = [
  { id: "15m", label: "15m", minutes: 15 },
  { id: "30m", label: "30m", minutes: 30 },
  { id: "1h", label: "1h", minutes: 60 },
  { id: "3h", label: "3h", minutes: 180 },
  { id: "all", label: "All", minutes: null }
];

const marketSorts: { id: MarketSort; label: string }[] = [
  { id: "start", label: "Start time" },
  { id: "volume_30m", label: "Vol 30m" },
  { id: "volume_1h", label: "Vol 1h" },
  { id: "volume_3h", label: "Vol 3h" },
  { id: "volume_total", label: "Total vol" }
];

function detectDashboardMode(): DashboardMode {
  if (typeof window === "undefined") return "all";
  const params = new URLSearchParams(window.location.search);
  const league = params.get("league")?.toLowerCase();
  const path = window.location.pathname.toLowerCase();
  return league === "itf" || path.includes("/itf") ? "itf" : "all";
}

export function App() {
  const dashboardMode = detectDashboardMode();
  const lockedLeague = dashboardMode === "itf" ? "itf" : null;
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [kind, setKind] = useState<OpportunityKind>("all");
  const [sideMode, setSideMode] = useState<SideMode>("no");
  const [marketScope, setMarketScope] = useState<MarketScope>(dashboardMode === "itf" ? "all" : "upcoming");
  const [leagueFilter, setLeagueFilter] = useState(lockedLeague ?? "all");
  const [marketTypeFilter, setMarketTypeFilter] = useState("all");
  const [marketSort, setMarketSort] = useState<MarketSort>(dashboardMode === "itf" ? "volume_30m" : "start");

  const marketsQuery = useQuery({ queryKey: ["markets"], queryFn: api.markets });
  const opportunitiesQuery = useQuery({
    queryKey: ["opportunities", kind],
    queryFn: () => api.opportunities(kind === "all" ? undefined : kind)
  });

  const scopedMarkets = useMemo(() => {
    return (marketsQuery.data ?? [])
      .filter((market) => !lockedLeague || (market.league ?? "").toLowerCase() === lockedLeague)
      .filter((market) => isMarketInScope(market, marketScope))
      .sort((left, right) => compareMarketStartTime(left, right, marketScope));
  }, [lockedLeague, marketsQuery.data, marketScope]);

  const scopedOpportunities = useMemo(() => {
    return (opportunitiesQuery.data ?? [])
      .filter((opportunity) => !lockedLeague || (opportunity.market.league ?? "").toLowerCase() === lockedLeague)
      .filter((opportunity) => isMarketInScope(opportunity.market, marketScope));
  }, [lockedLeague, opportunitiesQuery.data, marketScope]);

  const selectedMarket = useMemo(() => {
    if (!scopedMarkets.length) return null;
    if (selectedTicker) {
      return scopedMarkets.find((market) => market.ticker === selectedTicker) ?? scopedMarkets[0];
    }
    return scopedMarkets[0];
  }, [scopedMarkets, selectedTicker]);

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
  const volumeSummaryQuery = useQuery({
    queryKey: ["volume-summary", selectedMarket?.ticker],
    queryFn: () => api.volumeSummary(selectedMarket!.ticker),
    enabled: Boolean(selectedMarket)
  });
  const featuresQuery = useQuery({
    queryKey: ["features", selectedMarket?.ticker],
    queryFn: () => api.features(selectedMarket!.ticker),
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
    for (const opportunity of scopedOpportunities) {
      if (!map.has(opportunity.market.id)) map.set(opportunity.market.id, opportunity);
    }
    return map;
  }, [scopedOpportunities]);

  const filteredMarkets = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return scopedMarkets.filter((market) => {
      const matchesStatus = status === "all" || market.status === status;
      const matchesLeague = leagueFilter === "all" || (market.league ?? "").toLowerCase() === leagueFilter;
      const matchesMarketType = marketTypeFilter === "all" || normalizedMarketType(market.market_type) === marketTypeFilter;
      const text = `${market.ticker} ${market.league ?? ""} ${market.market_type ?? ""} ${
        market.event_title ?? ""
      }`.toLowerCase();
      return matchesStatus && matchesLeague && matchesMarketType && (!normalized || text.includes(normalized));
    }).sort((left, right) => compareMarketSort(left, right, marketSort, marketScope));
  }, [scopedMarkets, leagueFilter, marketTypeFilter, marketScope, marketSort, query, status]);

  const statuses = useMemo(() => {
    return Array.from(new Set(scopedMarkets.map((market) => market.status).filter(Boolean))).sort();
  }, [scopedMarkets]);

  const leagues = useMemo(() => {
    return Array.from(new Set(scopedMarkets.map((market) => market.league).filter(Boolean))).sort();
  }, [scopedMarkets]);

  const marketTypes = useMemo(() => {
    return Array.from(new Set(scopedMarkets.map((market) => normalizedMarketType(market.market_type)).filter(Boolean))).sort();
  }, [scopedMarkets]);

  const latestMetric = metricsQuery.data?.[0] ?? latestByMarketId.get(selectedMarket?.id ?? -1)?.metric ?? null;
  const latestOrderbook = orderbooksQuery.data?.[0] ?? null;

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">{dashboardMode === "itf" ? "Kalshi Research · ITF" : "Kalshi Research"}</p>
          <h1>{dashboardMode === "itf" ? "ITF Match Winner Console" : "Market Microstructure Console"}</h1>
        </div>
        <div className="top-actions">
          {dashboardMode === "itf" ? (
            <a className="mode-link" href="/">
              All markets
            </a>
          ) : (
            <a className="mode-link" href="/?league=itf">
              ITF dashboard
            </a>
          )}
          <HealthPill />
          <button
            className="icon-button"
            title="Refresh data"
            onClick={() => {
              void marketsQuery.refetch();
              void opportunitiesQuery.refetch();
              void metricsQuery.refetch();
              void orderbooksQuery.refetch();
              void volumeSummaryQuery.refetch();
              void featuresQuery.refetch();
              void sharpOddsQuery.refetch();
              void limitsQuery.refetch();
            }}
          >
            <RefreshCw size={18} />
          </button>
        </div>
      </header>

      <section className="kpi-strip">
        <Kpi label={`${marketScopeLabel(marketScope)} markets`} value={scopedMarkets.length} icon={<Database size={18} />} />
        <Kpi label="Opportunities" value={scopedOpportunities.length} icon={<Target size={18} />} />
        <Kpi label="Avg spread" value={formatCents(avgMetric(scopedOpportunities, "spread"))} icon={<Waves size={18} />} />
        <Kpi label="Avg liquidity" value={formatScore(avgMetric(scopedOpportunities, "liquidity_score"))} icon={<Gauge size={18} />} />
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
            <label className="search-box market-search">
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
            {lockedLeague ? (
              <div className="locked-filter">ITF</div>
            ) : (
              <select value={leagueFilter} onChange={(event) => setLeagueFilter(event.target.value)} aria-label="Filter league">
                <option value="all">All leagues</option>
                {leagues.map((item) => (
                  <option key={item ?? ""} value={(item ?? "").toLowerCase()}>
                    {(item ?? "").toUpperCase()}
                  </option>
                ))}
              </select>
            )}
            <select value={marketTypeFilter} onChange={(event) => setMarketTypeFilter(event.target.value)} aria-label="Filter market type">
              <option value="all">All markets</option>
              {marketTypes.map((item) => (
                <option key={item ?? ""} value={(item ?? "").toLowerCase()}>
                  {marketTypeLabel(item ?? "")}
                </option>
              ))}
            </select>
            <select value={marketSort} onChange={(event) => setMarketSort(event.target.value as MarketSort)} aria-label="Sort markets">
              {marketSorts.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <ScopeToggle value={marketScope} onChange={setMarketScope} />
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
            opportunities={scopedOpportunities}
            loading={opportunitiesQuery.isLoading}
            selectedTicker={selectedMarket?.ticker ?? null}
            onSelect={setSelectedTicker}
          />
          <MarketDetail
            market={selectedMarket}
            metric={latestMetric}
            orderbook={latestOrderbook}
            volumeSummary={volumeSummaryQuery.data ?? []}
            metrics={metricsQuery.data ?? []}
            orderbooks={orderbooksQuery.data ?? []}
            features={featuresQuery.data ?? []}
            sharpOdds={sharpOddsQuery.data ?? []}
            limits={limitsQuery.data ?? []}
            sideMode={sideMode}
            loading={
              metricsQuery.isLoading ||
              orderbooksQuery.isLoading ||
              volumeSummaryQuery.isLoading ||
              featuresQuery.isLoading ||
              sharpOddsQuery.isLoading ||
              limitsQuery.isLoading
            }
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

function ScopeToggle({ value, onChange }: { value: MarketScope; onChange: (value: MarketScope) => void }) {
  return (
    <div className="scope-toggle" aria-label="Market time scope">
      {marketScopes.map((scope) => (
        <button key={scope.id} className={value === scope.id ? "active" : ""} onClick={() => onChange(scope.id)}>
          {scope.label}
        </button>
      ))}
    </div>
  );
}

function TimeWindowToggle({ value, onChange }: { value: TimeWindow; onChange: (value: TimeWindow) => void }) {
  return (
    <div className="time-toggle" aria-label="Chart time window">
      {timeWindows.map((window) => (
        <button key={window.id} className={value === window.id ? "active" : ""} onClick={() => onChange(window.id)}>
          {window.label}
        </button>
      ))}
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
            <th>Vol</th>
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
                <td>{formatMarketVolume(market)}</td>
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
  volumeSummary,
  metrics,
  orderbooks,
  features,
  sharpOdds,
  limits,
  sideMode,
  loading
}: {
  market: Market | null;
  metric: DerivedMetric | null;
  orderbook: OrderbookSnapshot | null;
  volumeSummary: MarketVolumeSummary[];
  metrics: DerivedMetric[];
  orderbooks: OrderbookSnapshot[];
  features: MarketFeatureBucket[];
  sharpOdds: SharpBookOdds[];
  limits: SharpBookLimit[];
  sideMode: SideMode;
  loading: boolean;
}) {
  const [selectedDepthPrice, setSelectedDepthPrice] = useState<number | null>(null);
  const [timeWindow, setTimeWindow] = useState<TimeWindow>("1h");

  useEffect(() => {
    setSelectedDepthPrice(null);
    setTimeWindow("1h");
  }, [market?.ticker, sideMode]);

  if (!market) return <EmptyState title="Select a market" detail="Market details will appear once discovery finds active tickers." />;

  const trackedDepthLabel =
    selectedDepthPrice === null ? `${sideMode.toUpperCase()} best bid depth` : `${sideMode.toUpperCase()} ${selectedDepthPrice}c depth`;
  const timeWindowLabel = timeWindows.find((window) => window.id === timeWindow)?.label ?? "1h";
  const priceChartData = filterTimeWindow(buildPriceChartData(metrics, orderbooks, sideMode, selectedDepthPrice), timeWindow);
  const volumeChartData = filterTimeWindow(buildVolumeChartData(metrics, orderbooks, features, sideMode), timeWindow);
  const hasVolumeData = volumeChartData.some(
    (row) => Number(row.intervalVolume) > 0 || Number(row.contractsPerMinute) > 0
  );
  const sharpChartData = filterTimeWindow(buildSharpOddsChartData(sharpOdds), timeWindow);
  const limitChartData = filterTimeWindow(buildLimitChartData(limits), timeWindow);
  const fairPrice = sideFairPrice(metric, sideMode);
  const edge = sideEdge(metric, sideMode);
  const bestBid = orderbook ? sideBestBid(orderbook, sideMode) : null;
  const evAtBestBid = fairPrice !== null && bestBid !== null && bestBid !== undefined ? fairPrice - bestBid : null;
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

      <SharpPricingPanel
        sharpOdds={sharpOdds}
        sideMode={sideMode}
        fairPrice={fairPrice}
        bestBid={bestBid}
        evAtBestBid={evAtBestBid}
        spread={metric?.spread}
        totalDepth={orderbook?.total_depth}
      />

      <SideVolumePanel market={market} volumeSummary={volumeSummary} />

      <NoQueuePanel orderbook={orderbook} />

      <div className="chart-panel">
        <div className="panel-heading">
          <div>
            <h2>{sideMode.toUpperCase()} Depth Ladder</h2>
            <p>{sideMode === "no" ? "Queue depth at and below our maker side" : "YES-side bid depth by price"}</p>
          </div>
        </div>
        {orderbook ? (
          <DepthLadderChart
            orderbook={orderbook}
            sideMode={sideMode}
            selectedPrice={selectedDepthPrice}
            onSelectPrice={setSelectedDepthPrice}
          />
        ) : (
          <EmptyState title="No depth snapshot" detail="Depth bars will appear after the next orderbook poll." />
        )}
      </div>

      <div className="chart-panel">
        <div className="panel-heading">
          <div>
            <h2>Kalshi Price, Fair, Queue Liquidity</h2>
            <p>{loading ? "Loading series" : `${priceChartData.length} points · ${timeWindowLabel} · ${trackedDepthLabel}`}</p>
          </div>
          <div className="chart-actions">
            <TimeWindowToggle value={timeWindow} onChange={setTimeWindow} />
            {selectedDepthPrice !== null ? (
              <button className="text-button" onClick={() => setSelectedDepthPrice(null)}>
                Track best bid
              </button>
            ) : null}
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
              <Bar yAxisId="depth" dataKey="queueDepth" name={trackedDepthLabel} fill="#c9ddd6" radius={[3, 3, 0, 0]} />
              <Line
                yAxisId="price"
                type="monotone"
                dataKey="bestBid"
                name={`${sideMode.toUpperCase()} best bid`}
                stroke="#1f7a5b"
                dot={false}
                strokeWidth={2}
              />
              <Line yAxisId="price" type="monotone" dataKey="fair" name={`${sideMode.toUpperCase()} fair`} stroke="#854d0e" dot={false} strokeWidth={2} />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState title="No time series yet" detail="Orderbook and metric snapshots will chart here after ingestion starts." />
        )}
        {volumeChartData.length && hasVolumeData ? (
          <div className="volume-strip">
            <div className="volume-heading">
              <strong>Volume and Contracts/Min</strong>
              <span>{volumeChartData.length} points</span>
            </div>
            <ResponsiveContainer width="100%" height={150}>
              <ComposedChart data={volumeChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e4ece9" />
                <XAxis dataKey="time" minTickGap={24} />
                <YAxis yAxisId="volume" tickFormatter={(value) => compactNumber(Number(value))} />
                <YAxis yAxisId="cpm" orientation="right" tickFormatter={(value) => formatNumber(Number(value))} />
                <Tooltip formatter={(value, name) => [formatNumber(Number(value)), name]} />
                <Bar yAxisId="volume" dataKey="intervalVolume" name="Contracts traded" radius={[3, 3, 0, 0]}>
                  {volumeChartData.map((row) => (
                    <Cell
                      key={`${row.timestampMs}`}
                      fill={Number(row.evAtBestBid) > 0 ? "#1f7a5b" : "#c9ddd6"}
                    />
                  ))}
                </Bar>
                <Line
                  yAxisId="cpm"
                  type="monotone"
                  dataKey="contractsPerMinute"
                  name="Contracts/min"
                  stroke="#315f85"
                  dot={false}
                  strokeWidth={2}
                  connectNulls
                />
                <Line
                  yAxisId="cpm"
                  type="monotone"
                  dataKey="evAtBestBid"
                  name="EV at best bid"
                  stroke="#854d0e"
                  dot={false}
                  strokeWidth={2}
                  connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : volumeChartData.length ? (
          <EmptyState title="No volume in this window" detail="Trades are being tracked, but this market has no contracts in the selected time range." />
        ) : null}
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

function DepthLadderChart({
  orderbook,
  sideMode,
  selectedPrice,
  onSelectPrice
}: {
  orderbook: OrderbookSnapshot;
  sideMode: SideMode;
  selectedPrice: number | null;
  onSelectPrice: (price: number) => void;
}) {
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
        <Bar
          dataKey="depth"
          radius={[0, 4, 4, 0]}
          onClick={(entry: unknown) => {
            const row = entry as DepthLadderDatum;
            if (Number.isFinite(row.priceCents)) onSelectPrice(row.priceCents);
          }}
        >
          {data.map((row) => (
            <Cell key={row.priceCents} fill={selectedPrice === row.priceCents ? "#854d0e" : "#1f7a5b"} cursor="pointer" />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function SharpPricingPanel({
  sharpOdds,
  sideMode,
  fairPrice,
  bestBid,
  evAtBestBid,
  spread,
  totalDepth
}: {
  sharpOdds: SharpBookOdds[];
  sideMode: SideMode;
  fairPrice: number | null;
  bestBid: number | null | undefined;
  evAtBestBid: number | null;
  spread: number | null | undefined;
  totalDepth: number | null | undefined;
}) {
  const rows = latestSharpRows(sharpOdds);
  return (
    <div className="pricing-panel">
      <div className="pricing-summary">
        <div>
          <span>Consensus {sideMode.toUpperCase()}</span>
          <strong>{formatCents(fairPrice)}</strong>
        </div>
        <div>
          <span>Kalshi best bid</span>
          <strong>{formatCents(bestBid)}</strong>
        </div>
        <div className={Number(evAtBestBid) > 0 ? "positive" : ""}>
          <span>EV at best bid</span>
          <strong>{formatSignedCents(evAtBestBid)}</strong>
        </div>
        <div>
          <span>Spread</span>
          <strong>{formatCents(spread)}</strong>
        </div>
        <div>
          <span>Total depth</span>
          <strong>{formatInteger(totalDepth)}</strong>
        </div>
      </div>
      <div className="sharp-book-grid">
        {rows.length ? (
          rows.map((row) => (
            <div key={row.sportsbook} className="sharp-book-card">
              <span>{row.sportsbook}</span>
              <strong>{formatCents(probabilityToCents(row.devigged_probability ?? row.implied_probability))}</strong>
              <small>{formatAmerican(row.american_odds)}</small>
            </div>
          ))
        ) : (
          <div className="sharp-book-empty">No sharp book rows for {sideMode.toUpperCase()} yet</div>
        )}
      </div>
    </div>
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

function SideVolumePanel({ market, volumeSummary }: { market: Market; volumeSummary: MarketVolumeSummary[] }) {
  const rows = ["yes", "no"].map((side) => {
    const row = volumeSummary.find((item) => item.side === side);
    return {
      side,
      label: row?.label ?? sideLabelFromMarket(market, side as SideMode),
      total: row?.volume_total ?? market.volume_total,
      pregame: row?.contracts_pregame ?? 0,
      last30m: row?.contracts_30m ?? 0,
      last1h: row?.contracts_1h ?? 0,
      last3h: row?.contracts_3h ?? 0
    };
  });

  return (
    <div className="side-volume-panel">
      <div className="side-volume-heading">
        <strong>Pregame and Recent Flow</strong>
        <span>Ticker volume is total market volume; side rows use Kalshi trade tape when available.</span>
      </div>
      <div className="side-volume-grid">
        {rows.map((row) => (
          <div key={row.side} className="side-volume-card">
            <div>
              <span>{row.side.toUpperCase()}</span>
              <strong>{row.label}</strong>
            </div>
            <dl>
              <div>
                <dt>Pregame</dt>
                <dd>{formatInteger(row.pregame)}</dd>
              </div>
              <div>
                <dt>30m</dt>
                <dd>{formatInteger(row.last30m)}</dd>
              </div>
              <div>
                <dt>1h</dt>
                <dd>{formatInteger(row.last1h)}</dd>
              </div>
              <div>
                <dt>Total ticker</dt>
                <dd>{formatInteger(row.total)}</dd>
              </div>
            </dl>
          </div>
        ))}
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

function buildPriceChartData(
  metrics: DerivedMetric[],
  orderbooks: OrderbookSnapshot[],
  sideMode: SideMode,
  selectedDepthPrice: number | null
) {
  const metricByMinute = new Map<string, DerivedMetric>();
  for (const metric of metrics) {
    metricByMinute.set(metric.timestamp.slice(0, 16), metric);
  }
  return [...orderbooks]
    .reverse()
    .map((orderbook) => {
      const metric = metricByMinute.get(orderbook.timestamp.slice(0, 16));
      const fair = sideFairPrice(metric ?? null, sideMode);
      const bestBid = sideBestBid(orderbook, sideMode);
      const queuePrice = selectedDepthPrice ?? bestBid;
      const timestampMs = new Date(orderbook.timestamp).getTime();
      return {
        timestampMs,
        time: new Date(orderbook.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        bestBid,
        fair,
        queueDepth: depthAtPrice(orderbook, sideMode, queuePrice)
      };
    })
}

function buildVolumeChartData(
  metrics: DerivedMetric[],
  orderbooks: OrderbookSnapshot[],
  features: MarketFeatureBucket[],
  sideMode: SideMode
) {
  if (features.length) {
    return [...features]
      .reverse()
      .map((bucket) => ({
        timestampMs: new Date(bucket.bucket_start).getTime(),
        time: new Date(bucket.bucket_start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        intervalVolume: bucket.volume_delta ?? 0,
        cumulativeVolume: null,
        contractsPerMinute: bucket.contracts_per_minute,
        evAtBestBid: sideMode === "no" ? bucket.ev_at_best_no_bid : bucket.ev_at_best_yes_bid
      }));
  }

  const metricByMinute = new Map<string, DerivedMetric>();
  for (const metric of metrics) {
    metricByMinute.set(metric.timestamp.slice(0, 16), metric);
  }
  let previousVolume: number | null = null;
  return [...orderbooks].reverse().map((orderbook) => {
    const metric = metricByMinute.get(orderbook.timestamp.slice(0, 16));
    const fair = sideFairPrice(metric ?? null, sideMode);
    const bestBid = sideBestBid(orderbook, sideMode);
    const timestampMs = new Date(orderbook.timestamp).getTime();
    const volume = orderbook.volume ?? null;
    const intervalVolume =
      volume === null || previousVolume === null ? 0 : Math.max(0, volume - previousVolume);
    previousVolume = volume ?? previousVolume;
    return {
      timestampMs,
      time: new Date(orderbook.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      intervalVolume,
      cumulativeVolume: volume,
      contractsPerMinute: orderbook.contracts_per_minute,
      evAtBestBid: fair !== null && bestBid !== null && bestBid !== undefined ? fair - bestBid : null
    };
  });
}

function buildSharpOddsChartData(odds: SharpBookOdds[]) {
  const byMinute = new Map<string, Record<string, string | number | null>>();
  for (const row of [...odds].reverse()) {
    const key = row.timestamp.slice(0, 16);
    const item =
      byMinute.get(key) ??
      ({
        timestampMs: new Date(row.timestamp).getTime(),
        time: new Date(row.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      } as Record<string, string | number | null>);
    item[row.sportsbook] = Math.round(((row.devigged_probability ?? row.implied_probability) || 0) * 1000) / 10;
    byMinute.set(key, item);
  }
  return Array.from(byMinute.values());
}

function buildLimitChartData(limits: SharpBookLimit[]) {
  const byMinute = new Map<string, Record<string, string | number | null>>();
  for (const row of [...limits].reverse()) {
    const key = row.timestamp.slice(0, 16);
    const item =
      byMinute.get(key) ??
      ({
        timestampMs: new Date(row.timestamp).getTime(),
        time: new Date(row.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      } as Record<string, string | number | null>);
    item[row.sportsbook] = row.limit_amount;
    byMinute.set(key, item);
  }
  return Array.from(byMinute.values());
}

function filterTimeWindow<T extends { timestampMs?: number | string | null }>(rows: T[], window: TimeWindow) {
  const config = timeWindows.find((item) => item.id === window);
  if (!config || config.minutes === null || rows.length === 0) return rows;
  const latestTimestamp = rows.reduce((latest, row) => {
    const value = Number(row.timestampMs);
    return Number.isFinite(value) ? Math.max(latest, value) : latest;
  }, 0);
  if (!latestTimestamp) return rows;
  const cutoff = latestTimestamp - config.minutes * 60_000;
  return rows.filter((row) => Number(row.timestampMs) >= cutoff);
}

function buildDepthLadderData(orderbook: OrderbookSnapshot, sideMode: SideMode) {
  const book = sideMode === "no" ? orderbook.no_book : orderbook.yes_book;
  const bestBid = sideBestBid(orderbook, sideMode);
  if (!book || bestBid === null || bestBid === undefined) return [];

  return Object.entries(book)
    .map(([price, depth]) => ({ priceCents: Number(price), depth }))
    .filter((row) => Number.isFinite(row.priceCents) && row.depth > 0 && row.priceCents <= bestBid)
    .sort((left, right) => right.priceCents - left.priceCents)
    .slice(0, 12)
    .map((row) => ({
      price: row.priceCents === bestBid ? `${row.priceCents}c best` : `${row.priceCents}c`,
      priceCents: row.priceCents,
      depth: row.depth
    }));
}

function sideBestBid(orderbook: OrderbookSnapshot, sideMode: SideMode) {
  return sideMode === "no" ? orderbook.best_no_bid : orderbook.best_yes_bid;
}

function depthAtPrice(orderbook: OrderbookSnapshot, sideMode: SideMode, price: number | null | undefined) {
  if (price === null || price === undefined) return 0;
  const book = sideMode === "no" ? orderbook.no_book : orderbook.yes_book;
  return book?.[String(price)] ?? 0;
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

function latestSharpRows(odds: SharpBookOdds[]) {
  const latest = new Map<string, SharpBookOdds>();
  for (const row of odds) {
    const existing = latest.get(row.sportsbook);
    if (!existing || new Date(row.timestamp).getTime() > new Date(existing.timestamp).getTime()) {
      latest.set(row.sportsbook, row);
    }
  }
  return Array.from(latest.values()).sort((left, right) => left.sportsbook.localeCompare(right.sportsbook));
}

function probabilityToCents(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  return value * 100;
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

function formatSignedCents(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const rounded = Math.round(value);
  return `${rounded > 0 ? "+" : ""}${rounded}c`;
}

function formatAmerican(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value > 0 ? `+${value}` : `${value}`;
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

function formatMarketVolume(market: Market) {
  const value = market.volume_last_30m ?? market.volume_last_1h ?? market.volume_last_3h ?? market.volume_total;
  return value === null || value === undefined ? "-" : compactNumber(value);
}

function gameTitle(market: Market) {
  return (market.event_title ?? market.ticker).replace(/\s+Winner\?$/i, "");
}

function marketSelection(market: Market) {
  const parts = market.ticker.split("-");
  return parts[parts.length - 1] ?? market.ticker;
}

function marketSideLabel(market: Market, sideMode: SideMode) {
  const explicitLabel = sideLabelFromMarket(market, sideMode);
  const marketType = market.market_type ?? "";
  const selection = marketSelection(market);
  if (marketType.includes("TOTAL") || marketType === "Total Runs" || marketType === "1st Half Total Runs") {
    return sideMode === "yes" ? `YES over ${selection}` : `NO under ${selection}`;
  }
  if (marketType.includes("SPREAD") || marketType === "Run Line") {
    return `${sideMode.toUpperCase()} ${formatRunLineSelection(selection)}`;
  }
  if (isTennisMatchMarket(market)) {
    return explicitLabel ? `${sideMode.toUpperCase()} ${explicitLabel}` : `${sideMode.toUpperCase()} side`;
  }
  if (explicitLabel) return `${sideMode.toUpperCase()} ${explicitLabel}`;
  return `${sideMode.toUpperCase()} ${selection}`;
}

function sideLabelFromMarket(market: Market, sideMode: SideMode) {
  return sideMode === "yes" ? market.yes_label : market.no_label;
}

function isTennisMatchMarket(market: Market) {
  const value = market.market_type ?? "";
  const league = (market.league ?? "").toLowerCase();
  return (
    ["KXATPMATCH", "KXITFMATCH", "KXWTAMATCH"].includes(value) ||
    ["atp", "itf", "itf_men", "itf_women", "wta"].includes(league)
  );
}

function marketTypeLabel(value: string) {
  const labels: Record<string, string> = {
    moneyline: "Moneyline",
    run_line: "Run Line",
    total_runs: "Total Runs",
    f5_total_runs: "F5 Total Runs",
    KXMLBGAME: "Moneyline",
    KXMLBSPREAD: "Run Line",
    KXMLBTOTAL: "Total Runs",
    KXMLBF5TOTAL: "F5 Total Runs",
    KXATPMATCH: "Moneyline",
    KXITFMATCH: "Moneyline",
    KXWTAMATCH: "Moneyline",
    Moneyline: "Moneyline",
    "Run Line": "Run Line",
    "Total Runs": "Total Runs",
    "1st Half Total Runs": "F5 Total Runs"
  };
  return labels[value] ?? value;
}

function normalizedMarketType(value: string | null | undefined) {
  if (!value) return "";
  if (value === "KXMLBGAME" || value === "Moneyline") return "moneyline";
  if (value === "KXATPMATCH" || value === "KXITFMATCH" || value === "KXWTAMATCH") return "moneyline";
  if (value === "KXMLBSPREAD" || value === "Run Line") return "run_line";
  if (value === "KXMLBTOTAL" || value === "Total Runs") return "total_runs";
  if (value === "KXMLBF5TOTAL" || value === "1st Half Total Runs") return "f5_total_runs";
  return value.toLowerCase();
}

function formatRunLineSelection(selection: string) {
  const match = selection.match(/^([A-Z]+)(\d+)$/);
  if (!match) return selection;
  return `${match[1]} by ${match[2]}+`;
}

function sideFairPrice(metric: DerivedMetric | null | undefined, sideMode: SideMode) {
  const fairYes = metric?.consensus_fair_price;
  if (fairYes === null || fairYes === undefined) return null;
  return sideMode === "no" ? 100 - fairYes : fairYes;
}

function sideEdge(metric: DerivedMetric | null | undefined, sideMode: SideMode) {
  return sideMode === "no" ? metric?.edge_no : metric?.edge_yes;
}

function marketScopeLabel(scope: MarketScope) {
  return marketScopes.find((item) => item.id === scope)?.label ?? "Visible";
}

function isMarketInScope(market: Market, scope: MarketScope) {
  if (scope === "all") return true;
  if (scope === "upcoming") return isUpcomingMarket(market);
  if (scope === "live") return isLiveMarket(market);
  return isPastMarket(market);
}

function isUpcomingMarket(market: Market) {
  const status = (market.status ?? "").toLowerCase();
  if (["live", "completed", "closed", "settled", "expired", "finalized", "resolved", "inactive"].includes(status)) {
    return false;
  }
  const startTime = marketStartTime(market);
  if (!startTime) return false;
  return startTime.getTime() > Date.now();
}

function isLiveMarket(market: Market) {
  return (market.status ?? "").toLowerCase() === "live";
}

function isPastMarket(market: Market) {
  const status = (market.status ?? "").toLowerCase();
  if (["completed", "closed", "settled", "expired", "finalized", "resolved", "inactive"].includes(status)) return true;
  const startTime = marketStartTime(market);
  return Boolean(startTime && startTime.getTime() <= Date.now() && !isLiveMarket(market));
}

function compareMarketStartTime(left: Market, right: Market, scope: MarketScope = "upcoming") {
  const leftStart = marketStartTime(left)?.getTime() ?? Number.MAX_SAFE_INTEGER;
  const rightStart = marketStartTime(right)?.getTime() ?? Number.MAX_SAFE_INTEGER;
  if (leftStart !== rightStart) {
    return scope === "past" ? rightStart - leftStart : leftStart - rightStart;
  }
  return left.ticker.localeCompare(right.ticker);
}

function compareMarketSort(left: Market, right: Market, sort: MarketSort, scope: MarketScope) {
  if (sort === "start") return compareMarketStartTime(left, right, scope);
  const leftValue = marketSortValue(left, sort);
  const rightValue = marketSortValue(right, sort);
  if (leftValue !== rightValue) return rightValue - leftValue;
  return compareMarketStartTime(left, right, scope);
}

function marketSortValue(market: Market, sort: MarketSort) {
  if (sort === "volume_30m") return market.volume_last_30m ?? 0;
  if (sort === "volume_1h") return market.volume_last_1h ?? 0;
  if (sort === "volume_3h") return market.volume_last_3h ?? 0;
  if (sort === "volume_total") return market.volume_total ?? 0;
  return 0;
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
