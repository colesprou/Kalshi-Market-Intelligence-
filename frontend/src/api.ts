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
  metrics: (ticker: string) => request<DerivedMetric[]>(`/markets/${ticker}/metrics?limit=200`),
  orderbooks: (ticker: string) => request<OrderbookSnapshot[]>(`/markets/${ticker}/orderbooks?limit=200`),
  sharpOdds: (ticker: string, side: "yes" | "no") =>
    request<SharpBookOdds[]>(`/markets/${ticker}/sharp-odds?side=${side}&limit=500`),
  limits: (ticker: string) => request<SharpBookLimit[]>(`/markets/${ticker}/limits?sportsbook=Pinnacle&limit=500`),
  scores: (ticker: string) => request<OpportunityScore>(`/scores/${ticker}`)
};
