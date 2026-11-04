#!/usr/bin/env python3
"""create_outcome_owner_index.py — build ix_deck_outcomes_user off the boot path.

G3-e (legal R28.22): account deletion and export also match deck_outcomes by
its user_id. A plain CREATE INDEX on an existing deck_outcomes holds a SHARE
lock that blocks every outcome write (likes, passes, views) for its whole scan,
so it is never built in init_db; a fresh DB gets it from the declaration in
backend/database.py. Run this once after the deploy that adds the column. Until
the index exists, deletion and export still find the rows, by a scan.

Postgres: CREATE INDEX CONCURRENTLY with a lock_timeout, in autocommit. An
INVALID leftover (a concurrent build that failed earlier) is dropped
concurrently and rebuilt. SQLite (local): a plain CREATE INDEX IF NOT EXISTS.
Idempotent: a valid index is left alone.

Usage (from the repo root; writes the DB `backend.database` points at,
DATABASE_URL, default data/trade_finder.db):
    python3 scripts/create_outcome_owner_index.py            # build it
    python3 scripts/create_outcome_owner_index.py --check    # report only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

INDEX = "ix_deck_outcomes_user"
LOCK_TIMEOUT = "5s"


def state(engine) -> str:
    """'valid', 'invalid' (Postgres only: a failed concurrent build) or 'missing'."""
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            row = conn.execute(text(
                "SELECT i.indisvalid FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid "
                "WHERE c.relname = :name"), {"name": INDEX}).first()
            return "missing" if row is None else ("valid" if row[0] else "invalid")
        names = [r[1] for r in conn.execute(text("PRAGMA index_list('deck_outcomes')"))]
        return "valid" if INDEX in names else "missing"


def build(engine) -> str:
    """Build the index unless a valid one exists; returns the final state."""
    current = state(engine)
    if current == "valid":
        return current
    if engine.dialect.name == "postgresql":
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
            if current == "invalid":
                conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}"))
            conn.execute(text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX} "
                              "ON deck_outcomes (user_id)"))
    else:
        with engine.begin() as conn:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {INDEX} "
                              "ON deck_outcomes (user_id)"))
    return state(engine)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report the index's state only")
    args = parser.parse_args(argv)
    from backend import database
    result = state(database.engine) if args.check else build(database.engine)
    print(f"{INDEX}: {result}")
    return 0 if result == "valid" or args.check else 1


if __name__ == "__main__":
    sys.exit(main())
