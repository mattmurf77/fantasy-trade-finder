"""The one batch-writer for the relevance engine (HLD §2.2, LLD §2.1).

SQLite is single-writer and the request path shares the file, so every derive
pass in this package writes through `batch_write` and nothing else: short
transactions, one commit per chunk, a pacing sleep between chunks, and the
product engine's 5000 ms busy timeout doing the waiting.

No Flask imports (D12).
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Sequence

__all__ = ["batch_write"]

MODES = ("insert", "insert_ignore", "upsert")


def _product_engine():
    """The PRODUCT engine — WAL, busy_timeout=5000 (`database.py:60-96`).

    Resolved through the module object on every call (never bound at import)
    so tests can patch `backend.database.engine` the way the rest of the suite
    already does.

    Deliberately NOT `ingest_engine`: that one runs busy_timeout=150 +
    `BEGIN IMMEDIATE`, which is the analytics fail-fast shed path (KD-12 /
    RC-8). A batch pass that adopted it would drop writes on the floor under
    exactly the contention this helper exists to survive.
    """
    from .. import database as db
    return db.engine


def _dialect_insert(conn):
    """`insert()` construct carrying ON CONFLICT for the live dialect.

    Matches the idiom already used in `database.py:4428` and
    `analytics_ingest.py:291` — sqlite and postgres both speak
    `ON CONFLICT ... DO NOTHING / DO UPDATE`, so callers stay portable.
    """
    if conn.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    return dialect_insert


def _statement(conn, table, chunk_rows: Sequence[dict], mode: str,
               upsert_keys: tuple[str, ...] | None):
    if mode == "insert":
        from sqlalchemy import insert as core_insert
        return core_insert(table)

    dialect_insert = _dialect_insert(conn)
    stmt = dialect_insert(table)

    if mode == "insert_ignore":
        if upsert_keys:
            return stmt.on_conflict_do_nothing(index_elements=list(upsert_keys))
        # Bare DO NOTHING (no conflict target) is legal on both dialects and
        # covers every constraint on the table, not just one index.
        return stmt.on_conflict_do_nothing()

    # mode == "upsert"
    key_set = set(upsert_keys or ())
    # Update every non-key column the caller actually supplied. Columns absent
    # from the payload keep their stored value rather than being nulled.
    payload_cols = [c for c in chunk_rows[0].keys() if c not in key_set]
    if not payload_cols:
        # Nothing to update ⇒ semantically identical to insert_ignore.
        return stmt.on_conflict_do_nothing(index_elements=list(upsert_keys))
    return stmt.on_conflict_do_update(
        index_elements=list(upsert_keys),
        set_={c: getattr(stmt.excluded, c) for c in payload_cols},
    )


def batch_write(table, rows: list[dict], *, mode: str = "insert_ignore",
                chunk: int = 200, pace_s: float = 0.05,
                upsert_keys: tuple[str, ...] | None = None) -> int:
    """Write `rows` into `table` in paced, short transactions. Returns the count.

    One `engine.begin()` per chunk of at most `chunk` rows on the **product
    engine** (5000 ms busy timeout); NEVER the ingest engine (150 ms +
    `BEGIN IMMEDIATE` is the analytics fail-fast path — wrong tool). A
    `time.sleep(pace_s)` between chunks hands the writer lock back to the
    request path.

    **Caller contract: no open network socket while calling.** Fetch a page,
    close the socket, *then* call this. No transaction may ever be held across
    a network call (HLD §2.2) — a stalled upstream must not become a held
    SQLite write lock. This helper cannot enforce that; the caller owns it.

    Args:
        table: SQLAlchemy `Table` to write into.
        rows: list of column→value dicts. All rows in a chunk should share a
            key shape; `upsert` derives its SET list from the first row.
        mode: ``insert`` (raises on conflict) | ``insert_ignore`` (default,
            ON CONFLICT DO NOTHING) | ``upsert`` (ON CONFLICT DO UPDATE).
        chunk: max rows per transaction (HLD §2.2 caps this at 200).
        pace_s: sleep between chunks; not slept after the final chunk.
        upsert_keys: conflict-target columns. Required for ``upsert``;
            optional for ``insert_ignore`` (narrows the target to one index).

    Returns:
        Rows written. Taken from the driver's rowcount when it reports one
        (SQLite does, so `insert_ignore` genuinely excludes the duplicates it
        skipped); falls back to the submitted chunk size when the driver
        reports -1, which some Postgres executemany paths do.
    """
    if mode not in MODES:
        raise ValueError(f"batch_write: unknown mode {mode!r} (expected one of {MODES})")
    if mode == "upsert" and not upsert_keys:
        raise ValueError("batch_write: mode='upsert' requires upsert_keys")
    if chunk < 1:
        raise ValueError(f"batch_write: chunk must be >= 1, got {chunk!r}")
    if not rows:
        return 0
    if chunk > 200:
        # HLD §2.2 is a ceiling, not a suggestion: a long transaction is the
        # failure mode this whole helper exists to prevent.
        raise ValueError(f"batch_write: chunk must be <= 200 (HLD §2.2), got {chunk}")

    engine = _product_engine()
    written = 0
    chunks: Iterable[Sequence[dict]] = [rows[i:i + chunk] for i in range(0, len(rows), chunk)]
    last = len(chunks) - 1

    for idx, chunk_rows in enumerate(chunks):
        with engine.begin() as conn:
            stmt = _statement(conn, table, chunk_rows, mode, upsert_keys)
            result: Any = conn.execute(stmt, list(chunk_rows))
            # Read rowcount inside the block: it is a cursor attribute and is
            # not guaranteed once the connection is returned to the pool.
            rc = getattr(result, "rowcount", -1)
        written += rc if isinstance(rc, int) and rc >= 0 else len(chunk_rows)
        if idx != last and pace_s > 0:
            time.sleep(pace_s)

    return written
