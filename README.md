# Kalshi Market Intelligence

Research and BI tooling for Kalshi sports-market microstructure. The platform collects
Kalshi orderbook snapshots, sharp sportsbook odds, sportsbook limits, and derived
market metrics so researchers can study queue positioning, stale prices, liquidity
behavior, spread dynamics, and market-maker stress.

This is research infrastructure, not trading advice or an automated trading system.

## Features

- Kalshi market discovery and orderbook snapshot ingestion
- Sharp sportsbook odds ingestion through Optic Odds
- Pinnacle limit tracking when available
- Multiplicative devigging and consensus fair probability estimates
- Derived metrics for spread, depth, edge, volatility, liquidity, and time to event
- Interpretable 0-100 opportunity scores for stale, queue, market-making, and maker-stress signals
- APScheduler background worker for recurring ingestion and scoring jobs
- FastAPI endpoints for exploratory analysis
- Vite React dashboard for market inspection
- Render-ready API, worker, UI, and Postgres deployment configuration

## Stack

- Python, FastAPI
- SQLAlchemy, Alembic
- Postgres on Render
- APScheduler for scheduled jobs
- Pandas for analytics-oriented calculations
- React, Vite, Recharts

## Project Layout

- `app/main.py` - FastAPI application entrypoint
- `app/models.py` - SQLAlchemy tables for markets, snapshots, metrics, scores, and job runs
- `app/api/` - HTTP routes and response schemas
- `app/clients/` - Kalshi and Optic Odds API clients
- `app/services/` - devigging, metric, and scoring logic
- `app/repositories.py` - database access helpers
- `app/worker/` - APScheduler configuration and recurring jobs
- `alembic/` - database migrations
- `frontend/` - Vite React dashboard
- `scripts/migrate_sqlite_to_postgres.py` - local SQLite to Postgres migration helper
- `render.yaml` - Render Blueprint configuration

## Environment

Copy the example environment file and fill in local or Render-specific values:

```bash
cp .env.example .env
```

Common variables:

```bash
DATABASE_URL=sqlite:///./local.db
KALSHI_API_KEY=
KALSHI_PRIVATE_KEY=
ODDSJAM_API_KEY=
KALSHI_SERIES_PREFIXES=KXMLBGAME,KXMLBSPREAD,KXMLBTOTAL,KXMLBF5TOTAL,KXITFMATCH
POLLING_LEAGUES=mlb,itf
POLLING_MARKETS=Moneyline,Run Line,Total Runs,1st Half Total Runs
SHARP_BOOKS=Pinnacle,Circa,BetOnline
CORS_ORIGINS=http://localhost:5173
OPTIC_DISCOVERY_CONCURRENCY=8
KALSHI_PRIVATE_DATA_ENABLED=false
FAST_POLL_ENABLED=false
FAST_POLL_INTERVAL_SECONDS=5
FAST_POLL_MARKET_LIMIT=20
FAST_POLL_WINDOW_MINUTES=15
FEATURE_BUCKET_LOOKBACK_MINUTES=3
```

Polling intervals and feature flags are also environment-driven. See
`.env.example` for the full set of supported settings.

## Local Development

Install backend dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
```

Run the API:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run the worker:

```bash
python -m app.worker run
```

Run the UI:

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## Render Deployment

The included `render.yaml` defines:

- `kalshi-research-api` - FastAPI web service
- `kalshi-research-worker` - APScheduler background worker
- `kalshi-research-ui` - static Vite dashboard
- `kalshi-research-db` - Render Postgres database

Expected service commands:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
python -m app.worker run
```

Recommended deployment flow:

1. Push this repository to GitHub.
2. Create a Render Blueprint from the repository.
3. Add secret environment variables for Kalshi, Optic Odds, and CORS.
4. Let Render create the Postgres database and inject `DATABASE_URL`.
5. Confirm the API health check and worker logs after deploy.

## Data Migration

To move local SQLite data into Render Postgres:

```bash
SQLITE_DATABASE_URL=sqlite:///./local.db \
DATABASE_URL='postgresql+psycopg://user:password@host:5432/database' \
python scripts/migrate_sqlite_to_postgres.py --truncate
```

Use `--truncate` only when the target database can be replaced with the local
dataset.

Backfill 1-minute BI feature buckets from existing snapshots:

```bash
python scripts/backfill_market_feature_buckets.py --truncate
```

## API

- `GET /health`
- `GET /markets`
- `GET /markets/{ticker}`
- `GET /markets/{ticker}/metrics`
- `GET /markets/{ticker}/orderbooks`
- `GET /markets/{ticker}/trades`
- `GET /markets/{ticker}/features`
- `GET /markets/{ticker}/events`
- `GET /markets/{ticker}/live-signals`
- `GET /markets/{ticker}/sharp-odds`
- `GET /markets/{ticker}/limits`
- `GET /opportunities`
- `GET /opportunities/stale`
- `GET /opportunities/market-making`
- `GET /opportunities/queue-positioning`
- `GET /scores/{ticker}`

## Current Scope And Assumptions

- The default research configuration focuses on main MLB moneyline, run line,
  game total, first-five total markets, and ITF tennis match winners.
- MLB Kalshi series defaults are `KXMLBGAME`, `KXMLBSPREAD`, `KXMLBTOTAL`,
  and `KXMLBF5TOTAL`.
- MLB Optic Odds market defaults are `Moneyline`, `Run Line`, `Total Runs`,
  and `1st Half Total Runs` with `is_main=true`.
- ITF Kalshi match winners use the `KXITFMATCH` series. Each ticker is a
  single YES/NO match market, so research views show both side labels and
  side trade flow when Kalshi trade tape exposes `taker_side`.
- Kalshi YES and NO markets are separate binary markets with separate orderbooks.
- Kalshi exposes bids on each side; asks are derived from the opposite side bid
  where applicable.
- Moneyline and run-line ticker suffixes are used to map the YES team where
  available. Total markets are treated as YES=over threshold and NO=under
  threshold in research views.
- Multiplicative devigging is implemented first; Shin, probit, logit, and
  weighted consensus models can be added later.
- Opportunity scores are heuristic research triage signals, not automated
  execution instructions.
- API behavior that is ambiguous should be documented with TODOs instead of
  invented.

## Security

Do not commit `.env`, private keys, API keys, exported database credentials, or
other secrets. The repository ignore rules exclude common local secret files,
including private key material.
