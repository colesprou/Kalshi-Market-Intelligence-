# Kalshi Research BI Tool

MVP backend for researching Kalshi sports-market microstructure, sharp book reactions,
liquidity behavior, queue value, stale quotes, and maker/taker opportunity signals.

## Architecture

- `app/main.py` exposes the FastAPI service.
- `app/models.py` defines SQLAlchemy tables for markets, snapshots, metrics, scores, and job runs.
- `app/clients/` contains thin Kalshi and Optic Odds API clients with documented parsing quirks.
- `app/services/` contains pure metric, devigging, and scoring functions.
- `app/repositories.py` keeps common database access out of routes and jobs.
- `app/worker/` runs APScheduler jobs in a dedicated Render background worker.
- `frontend/` contains the Vite React research console.
- `alembic/versions/0001_initial_schema.py` creates the initial Postgres schema.

The worker is intentionally simple: APScheduler runs inside one Render worker process, each job has
`max_instances=1`, and every job records a `job_runs` row.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
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

Copy local SQLite data into Postgres:

```bash
SQLITE_DATABASE_URL=sqlite:////private/tmp/kalshi_research_alembic2.db \
DATABASE_URL='postgresql+psycopg://user:password@host:5432/kalshi_research' \
python scripts/migrate_sqlite_to_postgres.py --truncate
```

Run the UI:

```bash
cd frontend
npm install
npm run dev
```

The UI defaults to `http://localhost:8000` for API calls. Override it with:

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

Render Blueprint services:

- `kalshi-research-api`: FastAPI web service.
- `kalshi-research-worker`: APScheduler background worker.
- `kalshi-research-ui`: static Vite dashboard.
- `kalshi-research-db`: Render Postgres database.

## API

- `GET /health`
- `GET /markets`
- `GET /markets/{ticker}`
- `GET /markets/{ticker}/metrics`
- `GET /markets/{ticker}/orderbooks`
- `GET /opportunities`
- `GET /opportunities/stale`
- `GET /opportunities/market-making`
- `GET /opportunities/queue-positioning`
- `GET /scores/{ticker}`

## Current Assumptions

- Kalshi YES asks are derived from the best NO bid, and NO asks are derived from the best YES bid.
- Local discovery defaults to MLB moneylines via `KALSHI_SERIES_PREFIXES=KXMLBGAME`.
- Kalshi dollar fields are converted to integer cents.
- Optic Odds exact sportsbook and market strings come from `OPTIC_ODDS_API.md`.
- Multiplicative devigging is the only implemented devig method.
- Sharp-side-to-Kalshi-YES mapping is left as a TODO where market semantics are ambiguous.
- Scores are 0-100 interpretable heuristics for research triage, not trading recommendations.
