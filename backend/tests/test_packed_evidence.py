"""ADR-025 stage 2: packed deck evidence (S8), flag trade.packed_evidence.

Spec: docs/plans/trade-time-to-suggestion/eng-evidence-contract.md §6-§9;
models-lead R2.4 addendum §2-§3 and R4.2 (U1-U8).

Harness: test_deferred_evidence's `deferred` (p1's real worker and routes,
flag on, evidence writes inline).
"""
import json
from pathlib import Path

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
from backend.feature_flags import DEFAULT_FLAGS, FLAG_KEYS
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import p1, run_job, status  # noqa: F401  (fixture)
from backend.tests.test_deferred_evidence import (  # noqa: F401  (fixture)
    deferred, deferred_deck, rows)

REPO = Path(__file__).resolve().parents[2]


# ── Item 6: the flag ────────────────────────────────────────────────────────

def test_the_packed_evidence_flag_is_registered_and_off():
    """The 3-touch mirror (FLAG_KEYS, config/features.json, the release
    fixture). It ships off; it goes on before trade.first_page_store (R2.4 §3)."""
    features = json.loads((REPO / "config/features.json").read_text())
    release = json.loads((REPO / "backend/tests/fixtures/flags/release.json").read_text())
    assert "trade.packed_evidence" in FLAG_KEYS and DEFAULT_FLAGS["trade.packed_evidence"] is False
    assert features["trade.packed_evidence"] is False
    assert release["trade.packed_evidence"] == features["trade.packed_evidence"]


# ── Item 4: the page_store marker ───────────────────────────────────────────

def marker(row):
    return json.loads(row["features_json"]).get("page_store")


def test_every_row_of_a_page_scoped_deck_carries_the_page_store_marker(deferred):
    """R2.4 addendum §3: full rows and narrow ghosts alike, so a paged deck is
    never read as a legacy one."""
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(60, ghost_every=9)
    assert server._trade_jobs[job_id]["page_scope"]
    status(client, job_id, 0)
    written = rows(engine)
    assert {r["is_ghost"] for r in written} == {0, 1}
    assert {marker(r) for r in written} == {1}


def test_a_real_page_scoped_job_marks_its_rows_and_a_flag_off_job_does_not(deferred, monkeypatch):
    client, engine, _ = deferred
    job_id = run_job()
    status(client, job_id, 0)
    assert rows(engine) and {marker(r) for r in rows(engine)} == {1}
    with engine.begin() as conn:
        conn.execute(db_module.deck_impressions_table.delete())
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.first_page_store": False})
    off = run_job(force_fresh=True)                        # flag off: rows at build, no page_scope
    assert "page_scope" not in server._trade_jobs[off]
    assert rows(engine)
    assert all("page_store" not in json.loads(r["features_json"]) for r in rows(engine))
