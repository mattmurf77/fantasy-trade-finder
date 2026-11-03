"""Size report for the P1 first-page store (`trade_page_store`). Read only.

Scope: docs/plans/trade-time-to-suggestion/scope-eng-200ms.md §7 (AC-L8):
about 0.2 MB compressed per active (user, league) pair and a total ceiling of
about 250 MB (`trade_page_store_max_bytes`). The flag stays off until the
measured numbers are in; this is how they are read.

Usage, from the repo root:
    python3 scripts/report_trade_page_store_size.py                    # local data/trade_finder.db
    python3 scripts/report_trade_page_store_size.py --database-url URL # e.g. DATABASE_URL_PROD
    DATABASE_URL=URL python3 scripts/report_trade_page_store_size.py

Prints one JSON object. It never writes: SQLite opens with mode=ro, and a
Postgres session runs with default_transaction_read_only. Load credentials
from secrets.local.env without printing them.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

REPO = Path(__file__).resolve().parents[1]
LOCAL_DB = REPO / "data" / "trade_finder.db"
PER_PAIR_BUDGET = 200_000          # §7: "≤ about 0.2 MB compressed per active pair"
DEFAULT_MAX_BYTES = 262_144_000    # trade_page_store_max_bytes seed


def read_only_engine(url: str):
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        return create_engine(f"sqlite:///file:{path}?mode=ro&uri=true")
    return create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    return values[min(len(values) - 1, int(q * len(values)))]


def report(engine) -> dict:
    with engine.connect() as conn:
        if not inspect(conn).has_table("trade_page_store"):
            return {"table": "missing", "rows": 0}
        totals = conn.execute(text(
            "SELECT COUNT(*), COUNT(DISTINCT user_id), COUNT(DISTINCT league_id), "
            "COALESCE(SUM(stored_bytes), 0), COALESCE(SUM(LENGTH(pages_blob)), 0), "
            "COALESCE(SUM(LENGTH(evidence_blob)), 0), COALESCE(SUM(card_count), 0), "
            "SUM(CASE WHEN last_served_at IS NULL THEN 1 ELSE 0 END), "
            "MIN(COALESCE(last_served_at, built_at)), MAX(COALESCE(last_served_at, built_at)) "
            "FROM trade_page_store")).one()
        sizes = sorted(row[0] for row in conn.execute(text("SELECT stored_bytes FROM trade_page_store")))
        relation_bytes = None
        if conn.dialect.name == "postgresql":
            relation_bytes = conn.execute(text(
                "SELECT pg_total_relation_size('trade_page_store')")).scalar()
        max_bytes = DEFAULT_MAX_BYTES
        if inspect(conn).has_table("model_config"):
            seeded = conn.execute(text(
                "SELECT value FROM model_config WHERE key = 'trade_page_store_max_bytes'")).scalar()
            max_bytes = int(seeded) if seeded is not None else max_bytes
    rows, users, leagues, stored, pages, evidence, cards, never_served, oldest, newest = totals
    return {
        "table": "trade_page_store",
        "dialect": engine.dialect.name,
        "rows": rows,
        "users": users,
        "leagues": leagues,
        "stored_bytes": {"total": int(stored), "mean": int(stored) // rows if rows else 0,
                         "p50": _percentile(sizes, 0.50), "p95": _percentile(sizes, 0.95),
                         "max": sizes[-1] if sizes else 0},
        "pages_blob_bytes": int(pages),
        "evidence_blob_bytes": int(evidence),
        "cards": {"total": int(cards), "mean_per_row": int(cards) // rows if rows else 0},
        "never_served_rows": int(never_served or 0),
        "last_use": {"oldest": oldest, "newest": newest},
        "relation_bytes": relation_bytes,
        "budget": {"per_pair_bytes": PER_PAIR_BUDGET,
                   "rows_over_per_pair": sum(1 for size in sizes if size > PER_PAIR_BUDGET),
                   "max_bytes": max_bytes,
                   "total_over_max": int(stored) > max_bytes},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"),
                        help="defaults to $DATABASE_URL, else the local SQLite DB")
    args = parser.parse_args(argv)
    url = args.database_url or f"sqlite:///{LOCAL_DB}"
    engine = read_only_engine(url)
    try:
        print(json.dumps(report(engine), indent=2, sort_keys=True))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
