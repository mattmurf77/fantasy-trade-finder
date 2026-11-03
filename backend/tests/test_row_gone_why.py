"""models-lead (d1): a row-gone miss split by why.

A deck's run metadata records its page-store key (scoring_format and
page_scope; its league is on every packed card), so a stored-path miss whose
page row is gone (upgrade_miss_row_gone) reads the key's current row once:
"replaced" when it now holds another deck, "no_row" when the key has none. The
answer goes into run["upgrade_miss_row_gone_why"] in the same commit, only
with its row-gone entry, once per card; a raising commit takes it back with
that entry; the CAS merge unions it (stored wins), kept to row-gone keys. A
pack without the key writes no why (unsplit). Invariant: why keys ⊆ row-gone
keys ⊆ miss-map keys.

Harness: test_packed_evidence's (the `deferred` fixture, real routes and
evidence writes inline).
"""
from datetime import datetime, timezone

import backend.database as db_module
import backend.server as server
from backend.eval import contract
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import HEADERS, SCOPE, p1, status  # noqa: F401  (fixture)
from backend.tests.test_deferred_evidence import UID, deferred  # noqa: F401  (fixture)
from backend.tests.test_packed_evidence import (
    deck_ids, delivered_before_completion, fail_after, pack_of, packed_deck, restart, unpack, view)
from backend.tests.test_replaced_page_rows import the_row_goes


def run_of(engine, job_id):
    return unpack(pack_of(engine, job_id))[0]


def gone_why(run):
    return run.get("upgrade_miss_row_gone", {}), run.get("upgrade_miss_row_gone_why", {})


def assert_nested(run):
    """why keys ⊆ row-gone keys ⊆ miss-map keys."""
    gone, why = gone_why(run)
    assert set(why) <= set(gone) <= set(run["upgrade_miss_cards"])


def delivered(client, job_id, *cursors):
    for cursor in cursors or (0, 30):
        assert deck_ids(status(client, job_id, cursor).get_json())


def counting_reads(monkeypatch):
    calls = []
    real = db_module.load_trade_page_deck_job_id

    def read(*args):
        calls.append(args)
        return real(*args)
    monkeypatch.setattr(db_module, "load_trade_page_deck_job_id", read)
    return calls


# ── The key in the run ──────────────────────────────────────────────────────

def test_a_page_scoped_decks_run_records_its_page_store_key(deferred):
    """Written at the first write, on the live path and (from the stored blob's
    run metadata) on the stored path."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    run = run_of(engine, job_id)
    assert (run["scoring_format"], run["page_scope"]) == ("1qb_ppr", SCOPE)
    stored_first, *_ = packed_deck(90, job_id="deck-why-stored-first", force_fresh=True)
    restart()
    page = client.get(f"/api/trades/status?deck={stored_first}&cursor=0", headers=HEADERS)
    assert deck_ids(page.get_json())
    run = run_of(engine, stored_first)
    assert (run["scoring_format"], run["page_scope"]) == ("1qb_ppr", SCOPE)


def test_a_deck_without_a_page_scope_omits_the_key(deferred):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, complete=False, store=False)
    with server._trade_jobs_lock:
        server._trade_jobs[job_id]["page_scope"] = None
    delivered_before_completion(client, job_id)            # job_done writes the pack
    run = run_of(engine, job_id)
    assert "scoring_format" not in run and "page_scope" not in run


# ── The split ───────────────────────────────────────────────────────────────

def test_a_row_replaced_by_a_newer_deck_for_the_key_is_replaced(deferred):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    the_row_goes(job_id, "replaced")
    restart()
    view(job_id, 40)
    run = run_of(engine, job_id)
    assert gone_why(run) == ({"40": 90}, {"40": "replaced"})
    assert_nested(run)


def test_a_row_evicted_with_no_newer_row_is_no_row(deferred):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    the_row_goes(job_id, "evicted")
    restart()
    view(job_id, 40)
    run = run_of(engine, job_id)
    assert gone_why(run) == ({"40": 90}, {"40": "no_row"})
    assert_nested(run)


def test_a_pack_without_the_key_writes_row_gone_unsplit(deferred, monkeypatch):
    """A pack written before the key was recorded: its row-gone miss is
    recorded, with no why entry, and the key's row is never read."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    ev = server._trade_jobs[job_id]["evidence"]
    with server._deck_evidence_write_lock:
        for key in ("scoring_format", "page_scope"):
            ev.pack.run.pop(key)
        assert server._deck_pack_commit(job_id, ev.pack)
    the_row_goes(job_id, "replaced")
    restart()
    calls = counting_reads(monkeypatch)
    view(job_id, 40)
    run = run_of(engine, job_id)
    assert gone_why(run) == ({"40": 90}, {}) and calls == []
    assert run["upgrade_miss_cards"] == {"40": "restart_split"}


def test_a_failed_read_leaves_the_miss_unsplit(deferred, monkeypatch, caplog):
    """The why is a report field: its read failing never stops the miss."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    the_row_goes(job_id, "replaced")
    restart()

    def boom(*_args):
        raise RuntimeError("injected: the page-store read fails")
    monkeypatch.setattr(db_module, "load_trade_page_deck_job_id", boom)
    with caplog.at_level("WARNING"):
        view(job_id, 40)
    run = run_of(engine, job_id)
    assert (run["upgrade_miss_cards"], gone_why(run)) == ({"40": "restart_split"}, ({"40": 90}, {}))
    assert "row-gone why job=" in caplog.text


def test_a_miss_that_isnt_row_gone_writes_no_why(deferred):
    """Card 95 (past the recorded 90) with the row gone, and card 96 with the
    row present: misses, neither row-gone, so no why."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id, 0, 30, 60, 90)
    restart()
    view(job_id, 96)                                       # the row present
    the_row_goes(job_id, "evicted")
    restart()
    view(job_id, 95)                                       # the row gone, 95 >= 90
    run = run_of(engine, job_id)
    assert set(run["upgrade_miss_cards"]) == {"95", "96"}
    assert gone_why(run) == ({}, {})


def test_the_keys_row_is_read_only_on_the_row_gone_path(deferred, monkeypatch):
    """No read on a normal upgrade (live, or from the stored blob), on a miss
    with the row present, or on a miss past the recorded count; one read for
    the row-gone miss."""
    client, engine, _ = deferred
    calls = counting_reads(monkeypatch)
    job_id, *_ = packed_deck(120)
    delivered(client, job_id, 0, 30, 60, 90)
    view(job_id, 45)                                       # live: the job's snapshot
    restart()
    view(job_id, 50)                                       # stored: the blob's snapshot
    view(job_id, 96)                                       # a miss, the row present
    assert calls == []
    the_row_goes(job_id, "replaced")
    restart()
    view(job_id, 95)                                       # a miss past the recorded 90
    assert calls == []
    view(job_id, 40)                                       # the row-gone miss
    assert len(calls) == 1 and calls[0][2:] == ("1qb_ppr", SCOPE)
    assert gone_why(run_of(engine, job_id)) == ({"40": 90}, {"40": "replaced"})


# ── Rollback, merge, invariant ──────────────────────────────────────────────

def test_a_raising_commit_takes_the_why_back_with_its_row_gone_entry(deferred):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    the_row_goes(job_id, "replaced")
    restart()
    with fail_after(engine, "UPDATE DECK_EVIDENCE_PACKS"):
        view(job_id, 40)
    state = server._deck_pack_states[job_id]
    assert gone_why(state.run) == ({}, {}) and state.run["upgrade_miss_cards"] == {}
    assert gone_why(run_of(engine, job_id)) == ({}, {})
    view(job_id, 41)
    run = run_of(engine, job_id)
    assert gone_why(run) == ({"41": 90}, {"41": "replaced"})
    assert_nested(run)


def test_two_writers_whys_are_unioned_with_their_row_gone_entries(deferred):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    the_row_goes(job_id, "evicted")
    restart()
    first = server._load_pack_state(job_id, UID)
    second = server._load_pack_state(job_id, UID)
    now = datetime.now(timezone.utc).isoformat()
    for state, index in ((first, 40), (second, 41)):
        with server._deck_evidence_write_lock:
            assert server._deck_upgrade_stored_locked(
                state, job_id, contract.card_impression_id(job_id, index), index, UID, now)
    run = run_of(engine, job_id)
    assert gone_why(run) == ({"40": 90, "41": 90}, {"40": "no_row", "41": "no_row"})
    assert_nested(run)


def test_the_merge_unions_the_whys_kept_to_row_gone_keys():
    stored = {"upgrade_miss_cards": {"40": "restart_split", "41": "restart_split"},
              "upgrade_miss_row_gone": {"40": 90, "41": 90},
              "upgrade_miss_row_gone_why": {"40": "replaced", "41": "replaced"}}
    ours = {"upgrade_miss_cards": {"41": "restart_split", "50": "restart_split", "60": "other"},
            "upgrade_miss_row_gone": {"41": 90, "50": 90},
            "upgrade_miss_row_gone_why": {"41": "no_row", "50": "no_row", "60": "no_row"}}
    merged = server._merge_pack_runs(stored, ours, {})
    assert merged["upgrade_miss_row_gone_why"] == {"40": "replaced", "41": "replaced",
                                                   "50": "no_row"}     # stored wins; 60 dropped
    assert_nested(merged)
    assert server._merge_pack_runs({"upgrade_miss_cards": {}}, {"upgrade_miss_cards": {}},
                                   {})["upgrade_miss_row_gone_why"] == {}
    assert server._upgrade_miss_row_gone_why({}) == {}
