"""batch_write — the one batch-writer discipline (HLD §2.2, LLD §2.1).

Every test names the sabotage it catches. The four properties that make this
helper worth having at all:

  1. It chunks (≤200 rows) and paces, so the request path can get the writer
     lock back between chunks.
  2. It writes on the PRODUCT engine, never the 150 ms fail-fast ingest engine.
  3. insert_ignore actually tolerates conflicts (a nightly re-run is a no-op,
     not a crash).
  4. It reports how many rows it wrote.

Transactions are counted with SQLAlchemy's engine-level "begin" event — the
same hook database.py uses for the ingest engine — so "one txn per chunk" is
observed, not inferred.
"""

import pytest
from sqlalchemy import (Column, Integer, MetaData, String, Table, create_engine,
                        event as sa_event, func, select)
from sqlalchemy.exc import IntegrityError

import backend.database as db_module
import backend.relevance.batch as batch
from backend.relevance.batch import batch_write

_md = MetaData()
rows_table = Table("relevance_batch_probe", _md,
                   Column("k", String, primary_key=True),
                   Column("v", Integer))


def _mk(path):
    e = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    _md.create_all(e)
    return e


@pytest.fixture
def eng(tmp_path, monkeypatch):
    """Patched product engine + a DISTINCT ingest engine on its own DB file.

    Two files, not two engines on one file: if batch_write ever reaches for the
    ingest engine, the rows land in the wrong database and the test says so.
    """
    product = _mk(tmp_path / "product.db")
    ingest = _mk(tmp_path / "ingest.db")
    monkeypatch.setattr(db_module, "engine", product)
    monkeypatch.setattr(db_module, "ingest_engine", ingest)
    return product


def _txn_counter(engine):
    box = {"n": 0}

    @sa_event.listens_for(engine, "begin")
    def _count(_conn):
        box["n"] += 1

    return box


def _count_rows(engine):
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(rows_table)).scalar()


def _rows(n, start=0, v=1):
    return [{"k": f"k{i:04d}", "v": v} for i in range(start, start + n)]


# ---------------------------------------------------------------------------
# Chunking + pacing
# ---------------------------------------------------------------------------

def test_201_rows_is_two_transactions(eng):
    # SABOTAGE: drop the chunk loop (one big executemany) ⇒ 1 txn, fails. This
    # is the whole point of the helper: SQLite is single-writer and a 201-row
    # transaction holds the lock against the request path.
    txns = _txn_counter(eng)
    written = batch_write(rows_table, _rows(201), chunk=200, pace_s=0)
    assert txns["n"] == 2
    assert written == 201
    assert _count_rows(eng) == 201


def test_exact_multiple_does_not_open_an_empty_transaction(eng):
    # SABOTAGE: an off-by-one in the slice range (e.g. range(0, len+chunk, chunk))
    # ⇒ 3 txns for 400 rows, the last one empty.
    txns = _txn_counter(eng)
    batch_write(rows_table, _rows(400), chunk=200, pace_s=0)
    assert txns["n"] == 2


def test_no_rows_opens_no_transaction(eng):
    # SABOTAGE: remove the empty-rows guard ⇒ an executemany with [] raises or
    # opens a pointless txn.
    txns = _txn_counter(eng)
    assert batch_write(rows_table, [], chunk=200, pace_s=0) == 0
    assert txns["n"] == 0


def test_paces_between_chunks_but_not_after_the_last(eng, monkeypatch):
    # SABOTAGE: delete the sleep ⇒ [] (no yielding to the request path between
    # chunks). Sleep after the final chunk ⇒ 3 sleeps, pure latency for nothing.
    slept = []
    monkeypatch.setattr(batch.time, "sleep", lambda s: slept.append(s))
    batch_write(rows_table, _rows(15), chunk=5, pace_s=0.05)
    assert slept == [0.05, 0.05]      # 3 chunks ⇒ 2 gaps


def test_chunk_ceiling_is_enforced(eng):
    # SABOTAGE: accept chunk=5000 ⇒ a caller can reintroduce the long
    # transaction HLD §2.2 exists to forbid, one keyword argument at a time.
    with pytest.raises(ValueError):
        batch_write(rows_table, _rows(10), chunk=5000)


# ---------------------------------------------------------------------------
# Engine choice
# ---------------------------------------------------------------------------

def test_writes_on_the_product_engine_not_the_ingest_engine(eng, tmp_path):
    # SABOTAGE: swap _product_engine() to db.ingest_engine ⇒ the rows land in
    # ingest.db and both asserts fail. The ingest engine runs busy_timeout=150
    # + BEGIN IMMEDIATE (the analytics fail-fast shed path) — batch passes
    # using it would drop writes under exactly the contention they must survive.
    assert batch._product_engine() is db_module.engine
    assert batch._product_engine() is not db_module.ingest_engine

    batch_write(rows_table, _rows(10), chunk=5, pace_s=0)
    assert _count_rows(eng) == 10
    assert _count_rows(db_module.ingest_engine) == 0


def test_engine_is_resolved_per_call_not_bound_at_import(tmp_path, monkeypatch):
    # SABOTAGE: `from ..database import engine` at module top ⇒ batch_write
    # keeps writing to whatever engine existed at import time, and every test
    # (and every DATABASE_URL swap) silently hits the wrong DB.
    late = _mk(tmp_path / "late.db")
    monkeypatch.setattr(db_module, "engine", late)
    batch_write(rows_table, _rows(3), chunk=2, pace_s=0)
    assert _count_rows(late) == 3


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def test_insert_ignore_tolerates_duplicates(eng):
    # SABOTAGE: emit a plain INSERT for insert_ignore ⇒ IntegrityError on the
    # second call, i.e. every nightly re-run of a derive pass crashes.
    assert batch_write(rows_table, _rows(5), mode="insert_ignore", chunk=2, pace_s=0) == 5
    again = batch_write(rows_table, _rows(5), mode="insert_ignore", chunk=2, pace_s=0)
    assert again == 0                 # nothing new written
    assert _count_rows(eng) == 5      # and nothing duplicated


def test_insert_ignore_partial_overlap_counts_only_new_rows(eng):
    # SABOTAGE: return len(rows) unconditionally ⇒ 5 instead of 3, and every
    # pass counter over-reports its work. (k0000-k0004 exist; k0003-k0007
    # submitted ⇒ 3 genuinely new.)
    batch_write(rows_table, _rows(5), mode="insert_ignore", chunk=2, pace_s=0)
    n = batch_write(rows_table, _rows(5, start=3), mode="insert_ignore",
                    chunk=2, pace_s=0)
    assert n == 3
    assert _count_rows(eng) == 8


def test_plain_insert_still_raises_on_conflict(eng):
    # SABOTAGE: make every mode insert_ignore ⇒ mode='insert' silently swallows
    # a duplicate-key bug instead of surfacing it.
    batch_write(rows_table, _rows(2), mode="insert", chunk=2, pace_s=0)
    with pytest.raises(IntegrityError):
        batch_write(rows_table, _rows(2), mode="insert", chunk=2, pace_s=0)


def test_upsert_updates_the_existing_row(eng):
    # SABOTAGE: route upsert to on_conflict_do_nothing ⇒ v stays 1 and every
    # refreshed profile/aggregate row silently freezes at its first value.
    batch_write(rows_table, _rows(3, v=1), mode="insert_ignore", chunk=2, pace_s=0)
    batch_write(rows_table, _rows(3, v=9), mode="upsert",
                upsert_keys=("k",), chunk=2, pace_s=0)
    with eng.connect() as conn:
        vals = [r.v for r in conn.execute(select(rows_table.c.v))]
    assert vals == [9, 9, 9]
    assert _count_rows(eng) == 3


def test_upsert_without_keys_is_rejected(eng):
    # SABOTAGE: default upsert_keys to the PK ⇒ a caller gets a conflict target
    # it never chose. Better to refuse.
    with pytest.raises(ValueError):
        batch_write(rows_table, _rows(1), mode="upsert")


def test_unknown_mode_is_rejected(eng):
    # SABOTAGE: fall through to insert on an unknown mode ⇒ a typo'd
    # mode="upser" writes with the wrong conflict semantics.
    with pytest.raises(ValueError):
        batch_write(rows_table, _rows(1), mode="replace")
