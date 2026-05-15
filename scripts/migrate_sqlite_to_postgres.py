from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, delete, insert, select, text
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.models import Base

TABLE_ORDER = [
    "markets",
    "job_runs",
    "kalshi_orderbook_snapshots",
    "sharp_book_odds_snapshots",
    "sharp_book_limits_snapshots",
    "derived_market_metrics",
    "opportunity_scores",
]


def normalize_database_url(url: str) -> str:
    return Settings.model_validate({"DATABASE_URL": url}).database_url


def reflected_tables(engine: Engine) -> dict[str, Table]:
    metadata = MetaData()
    metadata.reflect(bind=engine)
    return {name: metadata.tables[name] for name in TABLE_ORDER if name in metadata.tables}


def rows_for_table(source: Engine, table: Table, batch_size: int) -> Iterable[list[dict[str, object]]]:
    with source.connect() as connection:
        result = connection.execute(select(table))
        batch: list[dict[str, object]] = []
        for row in result.mappings():
            batch.append(dict(row))
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch


def reset_postgres_sequence(target: Engine, table_name: str) -> None:
    with target.begin() as connection:
        connection.execute(
            text(
                """
                SELECT setval(
                    pg_get_serial_sequence(:table_name, 'id'),
                    COALESCE((SELECT MAX(id) FROM """ + table_name + """), 1),
                    true
                )
                """
            ),
            {"table_name": table_name},
        )


def migrate(source_url: str, target_url: str, truncate: bool, batch_size: int) -> None:
    source = create_engine(source_url)
    target = create_engine(normalize_database_url(target_url), pool_pre_ping=True)

    Base.metadata.create_all(target)
    source_tables = reflected_tables(source)
    target_tables = reflected_tables(target)

    if truncate:
        with target.begin() as connection:
            for table_name in reversed(TABLE_ORDER):
                if table_name in target_tables:
                    connection.execute(delete(target_tables[table_name]))

    for table_name in TABLE_ORDER:
        if table_name not in source_tables or table_name not in target_tables:
            continue
        target_table = target_tables[table_name]
        copied = 0
        for batch in rows_for_table(source, source_tables[table_name], batch_size):
            with target.begin() as connection:
                connection.execute(insert(target_table), batch)
            copied += len(batch)
        if copied:
            reset_postgres_sequence(target, table_name)
        print(f"{table_name}: {copied}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy local SQLite research data into Postgres.")
    parser.add_argument("--source", default=os.getenv("SQLITE_DATABASE_URL"), help="SQLite URL, e.g. sqlite:///./local.db")
    parser.add_argument("--target", default=os.getenv("DATABASE_URL"), help="Postgres URL from Render")
    parser.add_argument("--truncate", action="store_true", help="Delete target table contents before copying")
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    if not args.source:
        raise SystemExit("Missing --source or SQLITE_DATABASE_URL")
    if not args.target:
        raise SystemExit("Missing --target or DATABASE_URL")
    migrate(args.source, args.target, truncate=args.truncate, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
