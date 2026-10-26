"""scripts/report_trade_page_store_size.py: the P1 page-store size report.

Scope: docs/plans/trade-time-to-suggestion/scope-eng-200ms.md §7 (the
size query ships with P1). Pinned here: the report's numbers against an
in-memory DB with a few rows, the CLI on a file DB, and that it never writes
(the SQLite connection is read-only).
"""
import io
import json
import os
import sqlite3
import sys
import time
from contextlib import redirect_stdout

import pytest
from sqlalchemy import create_engine, text

import backend.database as db_module
from backend.database import metadata

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import report_trade_page_store_size as size_report  # noqa: E402


def _seed(engine, monkeypatch):
    monkeypatch.setattr(db_module, "engine", engine)
    now = time.time()
    for n, (cards, served) in enumerate(((30, True), (90, False), (60, True))):
        blob = db_module.CompressedJSON.encode({"v": 1, "opponents_total": 3,
                                                "cards": [{"trade_id": f"t{n}-{i}"} for i in range(cards)]})
        db_module.save_trade_page(dict(
            user_id=f"u{n % 2}", league_id=f"l{n}", scoring_format="1qb_ppr",
            request_scope="organic:f=0.50", roster_fp="rfp1:x", values_snapshot_id="vsn1:x",
            engine_version="v3+x", config_signature="c", experiment_digest="e", deck_job_id=f"j{n}",
            built_at=db_module.page_store_iso(now - n * 86400),
            expires_at=db_module.page_store_iso(now + 86400), card_count=cards,
            pages_blob=blob, evidence_blob=None, stored_bytes=len(blob), state="ready",
            last_served_at=db_module.page_store_iso(now) if served else None))
    with engine.connect() as conn:
        return sorted(conn.execute(text("SELECT stored_bytes FROM trade_page_store")).scalars())


def test_report_counts_an_in_memory_store(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    sizes = _seed(engine, monkeypatch)
    out = size_report.report(engine)
    assert (out["rows"], out["users"], out["leagues"]) == (3, 2, 3)
    assert out["stored_bytes"]["total"] == sum(sizes) == out["pages_blob_bytes"]
    assert out["stored_bytes"]["max"] == sizes[-1] and out["stored_bytes"]["p50"] == sizes[1]
    assert out["evidence_blob_bytes"] == 0
    assert out["cards"] == {"total": 180, "mean_per_row": 60}
    assert out["never_served_rows"] == 1
    assert out["budget"]["rows_over_per_pair"] == 0 and out["budget"]["total_over_max"] is False
    assert out["budget"]["max_bytes"] == 262_144_000
    assert out["relation_bytes"] is None          # Postgres only


def test_report_on_a_db_without_the_table():
    engine = create_engine("sqlite:///:memory:")
    assert size_report.report(engine) == {"table": "missing", "rows": 0}


def test_cli_reads_a_file_db_and_never_writes(tmp_path, monkeypatch):
    path = tmp_path / "pages.db"
    engine = create_engine(f"sqlite:///{path}")
    metadata.create_all(engine)
    _seed(engine, monkeypatch)
    engine.dispose()
    before = path.read_bytes()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert size_report.main(["--database-url", f"sqlite:///{path}"]) == 0
    assert json.loads(buffer.getvalue())["rows"] == 3
    assert path.read_bytes() == before
    read_only = size_report.read_only_engine(f"sqlite:///{path}")
    with pytest.raises(Exception) as err:
        with read_only.begin() as conn:
            conn.execute(text("DELETE FROM trade_page_store"))
    assert isinstance(err.value.orig, sqlite3.OperationalError)
    assert "readonly" in str(err.value.orig)
    read_only.dispose()
