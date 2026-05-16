from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.models import Market, MarketFeatureBucket
from app.services.feature_buckets import backfill_feature_buckets


def normalize_database_url(url: str) -> str:
    return Settings.model_validate({"DATABASE_URL": url}).database_url


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill 1-minute market feature buckets from stored snapshots.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--market", help="Optional ticker to backfill one market")
    parser.add_argument("--start", help="Optional ISO start timestamp")
    parser.add_argument("--end", help="Optional ISO end timestamp")
    parser.add_argument("--truncate", action="store_true", help="Delete matching feature buckets before rebuilding")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("Missing --database-url or DATABASE_URL")

    engine = create_engine(normalize_database_url(args.database_url), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        stmt = select(Market).order_by(Market.event_start_time, Market.ticker)
        if args.market:
            stmt = stmt.where(Market.ticker == args.market)
        markets = list(db.scalars(stmt))
        if args.truncate:
            delete_stmt = delete(MarketFeatureBucket)
            if args.market:
                market_ids = [market.id for market in markets]
                delete_stmt = delete_stmt.where(MarketFeatureBucket.market_id.in_(market_ids))
            db.execute(delete_stmt)
            db.commit()
        rows = backfill_feature_buckets(db, markets, start=parse_dt(args.start), end=parse_dt(args.end))
        print(f"feature_buckets: {rows}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
