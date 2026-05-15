# Optic Odds API — Reference for Research Tooling

Quick onboarding for an agent building research tools against Optic Odds.
This isn't a full vendor doc — it's our accumulated, verified, what-works
view of the API. Use it as the source of truth before reading their docs.

## Auth

- Base URL: `https://api.opticodds.com/api/v3`
- Auth: `x-api-key: <key>` header. Key lives in `ODDSJAM_API_KEY` env var
  (legacy name — was OddsJam before rebrand). Loaded from `.env` at repo root.
- No body auth required, no token refresh, no per-request signing.

## Endpoints we actually use

| Endpoint | Purpose |
|---|---|
| `GET /leagues` | List every league + sport mapping |
| `GET /fixtures` | List fixtures by league + date window |
| `GET /fixtures/active` | Fixtures currently `unplayed` (filters out finished games) |
| `GET /fixtures/odds` | Per-fixture odds across multiple sportsbooks/markets |
| `GET /stream/odds/{sport}` | SSE stream — pushed odds updates |

### `GET /fixtures`

```
GET /fixtures?league=MLB&limit=30
  &start_date_after=2026-05-13T00:00:00Z
  &start_date_before=2026-05-14T00:00:00Z
```

Returns a list of fixture objects. Important fields:

```jsonc
{
  "id": "20260513XXXXXXXX",          // fixture_id — use everywhere
  "start_date": "2026-05-13T22:05:00Z",
  "status": "unplayed",              // "unplayed" | "live" | "completed"
  "is_live": false,
  "has_odds": true,
  "league": {"id": "mlb", "name": "MLB"},
  "sport":  {"id": "baseball", "name": "Baseball"},
  "home_team_display": "Boston Red Sox",
  "away_team_display": "Minnesota Twins",
  "home_competitors": [...],
  "away_competitors": [...]
}
```

**Important**: `home_team_display` is the canonical name used in odds entries'
`selection` field. Don't rely on `home_competitors[].name` — display name is
the match key.

### `GET /fixtures/odds`

The workhorse. One fixture at a time, multi-book, multi-market.

```
GET /fixtures/odds
  ?fixture_id=20260513XXXXXXXX
  &sportsbook=Pinnacle
  &sportsbook=Circa Sports
  &sportsbook=BetOnline
  &sportsbook=Betcris
  &sportsbook=Kalshi
  &market=Moneyline
  &is_main=true
```

Response shape:

```jsonc
{
  "data": [
    {
      "id": "20260513...",
      "odds": [
        {
          "sportsbook": "Pinnacle",
          "market": "Moneyline",
          "market_id": "moneyline",
          "selection": "Boston Red Sox",
          "selection_line": null,        // "over"/"under" for totals
          "name": "Boston Red Sox",
          "price": -135,                 // American odds (int)
          "points": null,                // line value for spreads/totals
          "is_main": true,
          "is_live": false,
          "limits": {"max": 1000},       // Pinnacle limits (USD) — KEY FIELD
          "source_ids": {
            "market_id": "KXMLBGAME-..."  // Kalshi ticker if sportsbook=Kalshi
          }
        }
      ]
    }
  ]
}
```

### `GET /leagues`

Use once to discover IDs. Each entry has `id`, `name`, `sport.id`. We've
verified the following are supported:

| Sport | League IDs |
|---|---|
| `baseball` | `mlb` |
| `hockey` | `nhl` |
| `basketball` | `nba`, `ncaab` |
| `football` | `nfl` |
| `soccer` | `epl`, `ucl`, `mls`, etc. |
| `mma` | `ufc`, `pfl` |
| `tennis` | `atp`, `wta` |

**Not supported**: horse racing. There is no `horse_racing` sport and no
league entries for the Derby / TVG / etc. (verified across 1300+ leagues).

### SSE stream

Used for real-time pricing (see `seeder/pricing.py`). Subscribe pattern:

```
GET /stream/odds/{sport}
  ?key=<ODDSJAM_API_KEY>
  &sportsbook=Pinnacle
  &sportsbook=Kalshi
  &market=Moneyline
  &league=MLB
  &is_main=true
  &last_entry_id=<resume_cursor>
```

Returns Server-Sent-Events stream with `data:` lines containing JSON odds
events. Each event has the same shape as a `/fixtures/odds` entry. The
`id` of each event is the resume cursor — track and pass back via
`last_entry_id` on reconnect.

**Gotcha**: Circa under-pushes. Some books (esp. Circa) emit events sparsely
on the stream. For research-grade data, **always do a periodic REST refresh**
(every 30-60s) to fill gaps — see `PricingEngine.run_rest_refresh_loop()`.

## Sportsbook names

Exact strings (case + spacing matters):

- `Pinnacle` — primary sharp source, also publishes `limits.max`
- `Circa Sports` — sharp, **lower coverage**, often missing on individual polls
- `BetOnline` — sharp, reliable
- `Betcris` — sharp, reliable
- `DraftKings`, `FanDuel`, `BetMGM`, `Caesars` — recreational books (not used for fair calc)
- `Kalshi` — present here; their entries carry `source_ids.market_id` = the Kalshi ticker

Other useful for some props:

- `Blue Book`, `Props Builder` (MLB strikeouts)

## Market name strings

The `market` query param is **case- and word-sensitive**. We've verified:

| Sport | Market type | Optic string |
|---|---|---|
| MLB | Moneyline | `Moneyline` |
| MLB | Run line | `Run Line` |
| MLB | Game totals | `Total Runs` |
| MLB | F5 totals | `1st Half Total Runs` |
| Soccer | Moneyline (3-way) | `Moneyline` |
| Soccer | Spreads (alt lines) | `Asian Handicap` |
| Soccer | Totals (alt lines) | `Total Goals` |
| MMA | Fight winner | `Moneyline` |
| NHL | Moneyline | `Moneyline` |
| NHL | Puck line | `Puck Line` |
| Tennis | Match winner | `Moneyline` |

Wrong strings return empty `data[].odds[]` silently (no 4xx).

## `is_main` flag

- `is_main=true` — only the book's "main" line (one spread/total per book)
- omitted — all alternate lines (used for soccer because every line is "alt")

For run lines / totals where books disagree on which line is "main"
(e.g. Pinnacle at -1, BetOnline at -1.5), `is_main=true` keeps each book's
choice. You handle disagreement on the consumer side.

## Devigging

We use multiplicative devig:

```
prob_book = american_to_probability(price)
total = home_prob + away_prob  (+ draw_prob if 3-way)
home_fair_per_book = home_prob / total
combined_fair = weighted_avg(home_fair_per_book across books)
```

Reference impls live in `seeder/pricing.py`:
- `american_to_probability(american)` — handles +/- sign
- `devig_two_way(odds_dict, books, weights, min_books)` — returns `(home, away)`
- `devig_three_way(odds_dict, books, weights, min_books)` — returns `(home, draw, away)`

Weights are 1.0 across all sharp books by default (in `config.book_weights`).

## Three-way detection (soccer)

Soccer moneyline has three outcomes. Detect by:

1. Any selection matches `"draw"`, `"tie"`, `"x"`, `"the draw"` (case-insensitive)
2. Or the Optic Kalshi entry includes a `draw` ticker for the same fixture

See `_classify_selection()` in `seeder/pricing.py` for the canonical mapping.

## Rate limits / quota

- No hard rate limit observed, but **bursty REST polls during peak game
  windows can starve quota** on lower-tier plans.
- Stream is the cheapest way to stay current; REST is the recovery path.
- For research tooling, throttle REST polling to once every 30-60s per
  fixture per market.

## What's reliably available vs flaky

**Reliable on REST every poll**:
- BetOnline (price + line)
- Betcris (price + line)
- Kalshi mapping (when the Kalshi market exists)

**Often missing on REST**:
- Pinnacle (returns intermittently — usually present on the stream)
- Circa Sports (sparse — sometimes hours between data points)

**Never empty**:
- The `data` array — empty `odds` means no books matched your filter, not
  that the fixture has no odds.

## How this maps to the research goals

- **Track sharp limits over time** → poll `/fixtures/odds` every N min,
  read `limits.max` on every Pinnacle entry. Plot vs minutes-to-game.
- **Sharp book correlation** → store per-book devigged probability per
  fixture/market over time, compute pairwise correlation in pandas.
- **Sudden sharp moves** → compute Δprobability per book per snapshot;
  flag |Δ| > N cents in <60s as a move event.
