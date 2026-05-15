# Kalshi API — Reference for Research Tooling

Onboarding doc for an agent working against Kalshi's API. Reflects our
hands-on experience — what actually works, what's flaky, what fields to
trust. Cross-reference with [API_ARCHITECTURE.md](API_ARCHITECTURE.md) for
trading-side details. This doc focuses on **read paths** used by research.

## Environments

| Env | Base URL |
|---|---|
| `prod` | `https://api.elections.kalshi.com/trade-api/v2` |
| `demo` | `https://demo-api.kalshi.co/trade-api/v2` |

Pick via `ENVIRONMENT=prod|dev` env var (see `seeder/config.py`).

## Auth

RSA-signed requests. For each request:

```
KALSHI-ACCESS-KEY:        <key_id>
KALSHI-ACCESS-TIMESTAMP:  <unix_ms as string>
KALSHI-ACCESS-SIGNATURE:  <base64(sign(timestamp + method + path, private_key))>
```

Implementation: `KalshiClient._sign_request()` in `seeder/execution.py`.

Credentials:
- `KALSHI_API_KEY` (or `KALSHI_API_KEY_PROD` / `_DEV`) — the key ID
- `KALSHI_PRIVATE_KEY` — PEM string with literal `\n` newlines preserved

**Research tools that only need market data + orderbook can run unauthed
where possible** — but most useful endpoints require auth.

## Ticker conventions

Tickers encode the league, date, teams, and outcome. Pattern:

```
KX{LEAGUE}{TYPE}-{YYMMMDDHHMM}{TEAMS}-{SIDE_OR_LINE}
```

Verified series prefixes (`LEAGUE_SERIES_PREFIX` in `seeder/scheduler.py`):

| Sport | Market | Prefix | Example |
|---|---|---|---|
| MLB | Moneyline | `KXMLBGAME` | `KXMLBGAME-26MAY131905BOSMIN-BOS` |
| MLB | Run line | `KXMLBSPREAD` | `KXMLBSPREAD-26MAY131905BOSMIN-BOS2` |
| MLB | Game total | `KXMLBTOTAL` | `KXMLBTOTAL-26MAY131905BOSMIN-9` |
| MLB | F5 total | `KXMLBF5TOTAL` | `KXMLBF5TOTAL-26MAY131905BOSMIN-5` |
| NHL | Moneyline | `KXNHLGAME` | — |
| NBA | Moneyline | `KXNBAGAME` | — |
| NFL | Moneyline | `KXNFLGAME` | — |
| NCAAB | Moneyline | `KXNCAAMBGAME` | — |
| Tennis (ATP/WTA) | Match | `KXATPMATCH` / `KXWTAMATCH` | — |
| EPL | Moneyline (3-way) | `KXEPLGAME` | — |
| UCL | Moneyline (3-way) | `KXUCLGAME` | — |
| UFC | Fight | `KXUFCFIGHT` | `KXUFCFIGHT-26MAY09CHISTR-STR` |

**Last segment** = the YES outcome:
- ML: team abbreviation (BOS = Boston wins)
- Spread: team abbreviation + line number (BOS2 = BOS wins by 2+)
- Total: integer threshold (9 = 9+ runs)
- Soccer 3-way: `HOME`, `DRAW`, `AWAY` or team-abbrev / `DRAW`

The middle segment groups markets by event:
`26MAY131905BOSMIN` = May 13 2026, 19:05 ET, BOS @ MIN. All KXMLB*** tickers
for the same game share this segment.

## Endpoints we use

### `GET /markets/{ticker}`

Returns single market detail.

```jsonc
{
  "market": {
    "ticker": "KXMLBGAME-...",
    "status": "active",
    "yes_bid_dollars": "0.42",     // string! parse with float()
    "yes_ask_dollars": "0.44",
    "no_bid_dollars":  "0.56",
    "no_ask_dollars":  "0.58",
    "yes_bid_quantity": 120,
    "no_bid_quantity": 80,
    "yes_ask_quantity": 200,
    "no_ask_quantity": 150,
    "last_price_dollars": "0.43",
    "volume": 1200,
    "open_interest": 4500,
    "expected_expiration_time": "2026-05-14T02:05:00Z",  // game end-ish, NOT start
    "expiration_time": "2026-05-14T04:00:00Z",
    "title": "Will the Boston Red Sox beat...",
    "subtitle": "Boston Red Sox @ Minnesota Twins",
    "event_ticker": "KXMLBGAME-26MAY131905BOSMIN"
  }
}
```

**Cents conversion**: every `*_dollars` field is a string. Convert with
`int(round(float(v) * 100))` to get cents. Quantities are already integers.

**Time fields**: `expected_expiration_time` is approximately the game's
**END** time for team sports, not start. To get start, subtract ~3h for
MLB/NBA/NHL or use Optic's `start_date`. See `market_validator.py`.

### `GET /markets/{ticker}/orderbook`

Full depth. **Two response formats** — code must handle both:

```jsonc
// New format (preferred): "orderbook_fp" with dollar floats
{
  "orderbook_fp": {
    "yes_dollars": [[0.42, 120], [0.41, 300], [0.40, 500]],
    "no_dollars":  [[0.56, 80],  [0.55, 200]]
  }
}

// Old format: "orderbook" with integer cents
{
  "orderbook": {
    "yes": {"bids": [[42, 120], [41, 300]]},
    "no":  {"bids": [[56, 80],  [55, 200]]}
  }
}
```

Implementation: `KalshiClient.get_full_orderbook()` returns:

```python
{
  "yes": {price_cents: qty, ...},
  "no":  {price_cents: qty, ...},
  "best_yes_bid": int|None,
  "best_no_bid":  int|None,
  "best_yes_ask": int|None,   # = 100 - best_no_bid
  "best_no_ask":  int|None,   # = 100 - best_yes_bid
}
```

**Critical**: Kalshi's YES and NO sides are **separate books**. The "ask"
for YES is mathematically the complement of the best NO bid (someone bidding
56 on NO is effectively offering YES at 44¢). The `best_yes_ask` / `best_no_ask`
in our helper are derived this way — there's no explicit ask side stored.

### `GET /markets?series_ticker={prefix}&status=open&limit=200`

List all markets in a series. Used for ticker discovery when Optic doesn't
map Kalshi (e.g. F5 totals — Optic doesn't link them, so we fetch
`KXMLBF5TOTAL` series ourselves and match by team abbreviations).

```jsonc
{
  "markets": [
    {"ticker": "KXMLBF5TOTAL-...-5", "subtitle": "...", "event_ticker": "..."},
    ...
  ],
  "cursor": "..."
}
```

### `GET /markets/trades?ticker=X&limit=N`

Trade tape — every executed trade with price + side + count. Useful for
contracts-per-minute research.

### `GET /portfolio/orders`, `GET /portfolio/fills`, `GET /portfolio/settlements`

Authenticated. Returns your own positions / executed trades / settled markets.
Not needed for pure market-microstructure research.

## Fee model

Kalshi charges a **maker fee** that depends on price (most expensive at 50¢,
near-zero at 1¢ or 99¢):

```
fee_per_contract = ceil(0.0175 * C * P * (1-P))   # USD
```

Where `C` is contracts, `P` is price in dollars (0..1).

As a % of cost:
```
fee_pct_of_cost ≈ 1.75 * (1 - P) * 100   # P in dollars
```

So a 40¢ fill: fee% ≈ 1.05% of cost. A 70¢ fill: fee% ≈ 0.525%. A 5¢ fill:
fee% ≈ 1.66%. Reference impl: `kalshi_maker_fee_pct()` in `seeder/models.py`.

**Takers** pay double maker fees in some markets — verify per-market. We've
exclusively run maker strategies so haven't documented taker.

## Market microstructure facts

- **Tick size**: 1¢ universally.
- **Price range**: 1¢ to 99¢. 0 and 100 are not valid limit prices (markets
  that resolve always settle at one of those — they're terminal states).
- **Volume / OI**: refresh on `get_market`. Not in orderbook response.
- **Hidden liquidity**: none — Kalshi shows full L2 in orderbook.
- **Iceberg orders**: not supported.
- **Self-trading**: prevented (you can't fill your own bid).
- **Order types**: limit (`buy_max_cost`, GTC, GTD), no market orders for
  binary contracts.
- **Series vs Event vs Market**:
  - **Series**: family of recurring events (e.g. KXMLBGAME)
  - **Event**: one specific game (e.g. KXMLBGAME-26MAY131905BOSMIN). For
    spreads/totals, the event groups all line variations.
  - **Market**: one binary outcome (e.g. KXMLBGAME-...-BOS). What you trade.

## Volume + Open Interest semantics

- `volume` is **per-market** (each YES/NO side counts as 1 contract per
  trade). A trade of 100 contracts adds 100 to `volume`.
- `open_interest` is unique open positions. Equals total filled contracts
  not yet settled / closed.
- **Both can be 0** even on liquid books — only resting bids/asks indicate
  market quality, not volume.

## Quirks we've hit

### 1. Orderbook can have placeholder bids at 1¢

When a market has no real liquidity, Kalshi sometimes shows a 1¢ bid as a
floor. Naïvely "joining the bid" puts your order at 1¢ — usually a bug.
We guard via `max_seed_distance_cents` (skip seeding if best_bid is >5¢
below fair). For research purposes, treat 1¢ bids as "no real book".

### 2. Time fields disagree with Optic

Optic's `start_date` and Kalshi's `expected_expiration_time` minus game
length can differ by several minutes for the same game (especially MLB
doubleheaders, weather postponements). For research timestamps, trust Kalshi
for time-to-game on resting orders, Optic for forward-looking discovery.

### 3. New tickers appear without Optic mapping

Kalshi sometimes lists markets before Optic's Kalshi-sportsbook feed picks
them up. For totals/F5 and some props, we fetch the series via
`get_markets_by_series()` and match to Optic fixtures by team-abbreviation
parsing of the ticker. See `f5_totals_pricing.match_kalshi_ticker()`.

### 4. Kalshi-listed favorite ≠ sharp favorite

For run-line markets near pick'em, Kalshi will sometimes list the moneyline
**underdog** as the named favorite (e.g. `KXMLBSPREAD-...-SD2` meaning
"SD wins by 2+" even though sharps trade AZ as the -1.5 favorite). The
ticker convention always points to a specific team; the **YES side answers
"does that named team win by N+"**. Detect via `selection` field — if Kalshi's
selection on the negative-points side doesn't match the sharp favorite,
either skip or invert your fair mapping. See `runline_pricing.py` flip log.

### 5. `expiration_ts` on orders

When placing orders, set `expiration_ts` (unix seconds) to the game's start
time (or game end for sports where post-start trading matters). Kalshi will
auto-cancel at that point. For research-only tools you never place — ignore.

## Useful for the research goals

| Research goal | Kalshi data needed |
|---|---|
| Queue positioning timing | Snapshot `get_full_orderbook` every N min, track depth at top + within-N-cents |
| Make-spots (wide spread + high vol) | Track `spread_cents = best_yes_ask - best_yes_bid`, plot with `volume` deltas |
| Contracts/min | `GET /markets/trades` polled; sum `count` per minute |
| Sharp-move reaction | `get_full_orderbook` polled @ ≤2s during known Optic Δ events |
| One-sided volume opps | Trade tape side imbalance: count YES-buy vs NO-buy contracts in rolling window |

## How `seeder/execution.py` shields you

Every endpoint above is wrapped in `KalshiClient` methods that handle
auth + retry + dollar↔cent conversion + dual-format orderbook parsing.
**Always go through that client** — never call Kalshi directly. The
helpers you'll use most:

```python
await kalshi.get_market(ticker)              # market detail
await kalshi.get_full_orderbook(ticker)      # parsed L2
await kalshi.get_markets_by_series(prefix)   # series discovery
```
