export type Market = {
  id: number;
  ticker: string;
  sport: string | null;
  league: string | null;
  market_type: string | null;
  event_title: string | null;
  event_start_time: string | null;
  status: string | null;
  created_at: string;
  updated_at: string;
};

export type DerivedMetric = {
  id: number;
  market_id: number;
  timestamp: string;
  consensus_fair_probability: number | null;
  consensus_fair_price: number | null;
  edge_yes: number | null;
  edge_no: number | null;
  spread: number | null;
  volatility_score: number | null;
  sharp_move_score: number | null;
  liquidity_score: number | null;
  contracts_per_minute: number | null;
  time_to_event_minutes: number | null;
  orderbook_imbalance: number | null;
  liquidity_stability: number | null;
  kalshi_lag_seconds: number | null;
};

export type OrderbookSnapshot = {
  id: number;
  market_id: number;
  timestamp: string;
  best_yes_bid: number | null;
  best_yes_ask: number | null;
  best_no_bid: number | null;
  best_no_ask: number | null;
  yes_bid_depth: number;
  yes_ask_depth: number;
  no_bid_depth: number;
  no_ask_depth: number;
  total_depth: number;
  spread: number | null;
  contracts_per_minute: number | null;
  volume: number | null;
  yes_book: Record<string, number> | null;
  no_book: Record<string, number> | null;
};

export type OpportunityScore = {
  id: number;
  market_id: number;
  timestamp: string;
  queue_positioning_score: number;
  stale_opportunity_score: number;
  market_making_score: number;
  maker_stress_score: number;
  notes_json: Record<string, unknown> | null;
};

export type Opportunity = {
  market: Market;
  score: OpportunityScore;
  metric: DerivedMetric | null;
};

export type SharpBookOdds = {
  id: number;
  market_id: number;
  timestamp: string;
  sportsbook: string;
  side: string;
  american_odds: number;
  decimal_odds: number;
  implied_probability: number;
  devigged_probability: number | null;
};

export type SharpBookLimit = {
  id: number;
  market_id: number;
  timestamp: string;
  sportsbook: string;
  side: string;
  limit_amount: number | null;
};

export type MarketFeatureBucket = {
  id: number;
  market_id: number;
  bucket_start: string;
  bucket_seconds: number;
  sport: string | null;
  league: string | null;
  market_type: string | null;
  time_to_event_minutes: number | null;
  day_of_week: number | null;
  hour_of_day: number | null;
  best_yes_bid: number | null;
  best_no_bid: number | null;
  consensus_fair_yes: number | null;
  consensus_fair_no: number | null;
  edge_yes_at_bid: number | null;
  edge_no_at_bid: number | null;
  volume_delta: number | null;
  contracts_per_minute: number | null;
  taker_yes_contracts: number | null;
  taker_no_contracts: number | null;
  one_sided_flow_ratio: number | null;
  volume_acceleration: number | null;
  spread: number | null;
  total_depth: number | null;
  depth_at_best_yes: number | null;
  depth_at_best_no: number | null;
  orderbook_imbalance: number | null;
  ev_at_best_yes_bid: number | null;
  ev_at_best_no_bid: number | null;
  actual_fill_count: number;
  avg_ev_at_fill: number | null;
  source_quality_flags: Record<string, boolean> | null;
};

export type MarketEventDetection = {
  id: number;
  market_id: number;
  event_type: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  side: string | null;
  magnitude: number | null;
  metadata_json: Record<string, unknown> | null;
};

export type LiveMarketSignal = {
  id: number;
  market_id: number;
  timestamp: string;
  signal_type: string;
  contracts_last_5s: number | null;
  contracts_last_10s: number | null;
  contracts_last_30s: number | null;
  contracts_last_60s: number | null;
  trailing_cpm_5m: number | null;
  expected_contracts_10s: number | null;
  flow_spike_ratio: number | null;
  taker_side: string | null;
  taker_side_imbalance: number | null;
  taker_yes_last_10s: number | null;
  taker_no_last_10s: number | null;
  best_yes_bid: number | null;
  best_yes_ask: number | null;
  best_no_bid: number | null;
  best_no_ask: number | null;
  spread: number | null;
  total_depth: number | null;
  depth_change_after_spike: number | null;
  spread_change_after_spike: number | null;
  kalshi_price_change_after_spike: number | null;
  signal_score: number | null;
  metadata_json: Record<string, unknown> | null;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  markets: () => request<Market[]>("/markets?limit=2000"),
  opportunities: (kind?: "stale" | "market-making" | "queue-positioning") =>
    request<Opportunity[]>(kind ? `/opportunities/${kind}` : "/opportunities"),
  metrics: (ticker: string) => request<DerivedMetric[]>(`/markets/${ticker}/metrics?limit=1000`),
  orderbooks: (ticker: string) => request<OrderbookSnapshot[]>(`/markets/${ticker}/orderbooks?limit=1000`),
  features: (ticker: string) => request<MarketFeatureBucket[]>(`/markets/${ticker}/features?bucket_seconds=60&limit=2000`),
  events: (ticker: string) => request<MarketEventDetection[]>(`/markets/${ticker}/events?limit=500`),
  liveSignals: (ticker: string) => request<LiveMarketSignal[]>(`/markets/${ticker}/live-signals?limit=500`),
  sharpOdds: (ticker: string, side: "yes" | "no") =>
    request<SharpBookOdds[]>(`/markets/${ticker}/sharp-odds?side=${side}&limit=2000`),
  limits: (ticker: string) => request<SharpBookLimit[]>(`/markets/${ticker}/limits?sportsbook=Pinnacle&limit=2000`),
  scores: (ticker: string) => request<OpportunityScore>(`/scores/${ticker}`)
};
