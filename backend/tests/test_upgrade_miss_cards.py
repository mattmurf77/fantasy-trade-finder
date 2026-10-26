"""U4-R2's per-card miss map (models-eng): run["upgrade_miss_cards"].

The pack's run metadata carries {"<card_index>": cause} for every card whose
upgrade missed, beside upgrade_misses, which is always that map's tally. A card
is counted once by the persisted map, so a header reloaded after a deploy or an
eviction never recounts it (#434 QA P3-1); the CAS merge unions the maps (the
stored cause wins) and re-tallies, so two writers that missed the same card
count it once; and #424's reader takes each acted-on, no-full-row card's cause
from its run's map.

Harness: test_packed_evidence's (the `deferred` fixture, real routes and
evidence writes inline).
"""
import pytest

import backend.database as db_module
import backend.server as server
from backend.eval import contract
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import p1, status  # noqa: F401  (fixture)
from backend.tests.test_deferred_evidence import UID, deferred, rows  # noqa: F401  (fixture)
from backend.tests.test_packed_evidence import (
    NO_MISSES, evict, fail_after, pack_of, packed_deck, restart, unpack, view)


def run_of(engine, job_id):
    return unpack(pack_of(engine, job_id))[0]


def delivered_to_119(client, job_id):
    for cursor in (0, 30, 60, 90):
        status(client, job_id, cursor)


def test_the_counts_are_the_maps_tally_after_mixed_misses(deferred, monkeypatch):
    """The invariant: one deck's misses of all three causes (other: a deck held
    here whose snapshot is gone; evicted_split: after its eviction, with the
    cause named; restart_split: after a restart). The map holds each card's
    cause, and upgrade_misses equals its tally, other included."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered_to_119(client, job_id)
    assert (run_of(engine, job_id)["upgrade_miss_cards"],
            run_of(engine, job_id)["upgrade_misses"]) == ({}, NO_MISSES)
    ev = server._trade_jobs[job_id]["evidence"]
    with ev.lock:
        ev.rows.pop(contract.card_impression_id(job_id, 100))
    view(job_id, 100)                                      # held here: other
    monkeypatch.setattr(server, "_EVICTED_SPLIT_NAMED", True)
    evict(monkeypatch, job_id)
    view(job_id, 95)                                       # evicted here: evicted_split
    restart()
    view(job_id, 110)                                      # another process built it
    run = run_of(engine, job_id)
    assert run["upgrade_miss_cards"] == {"100": "other", "95": "evicted_split",
                                         "110": "restart_split"}
    assert run["upgrade_misses"] == server._upgrade_miss_tally(run["upgrade_miss_cards"]) == {
        "restart_split": 1, "evicted_split": 1, "other": 1}


def test_a_failed_row_save_then_a_restart_counts_the_card_once(deferred):
    """#434 QA P3-1: the miss's count commits, its row save fails, and the
    process restarts. The reloaded header's map already has the card, so the
    retry writes the row without counting it again (an in-memory set lost
    with the process counted it twice)."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered_to_119(client, job_id)
    restart()
    with fail_after(engine, "INSERT INTO DECK_IMPRESSIONS"):
        view(job_id, 95)
    assert run_of(engine, job_id)["upgrade_miss_cards"] == {"95": "restart_split"}
    restart()                                              # the deploy: the header is reloaded
    view(job_id, 95)
    assert len([r for r in rows(engine) if r["card_index"] == 95]) == 1
    run = run_of(engine, job_id)
    assert run["upgrade_miss_cards"] == {"95": "restart_split"}
    assert run["upgrade_misses"] == {**NO_MISSES, "restart_split": 1}


def test_a_cards_first_recorded_cause_stands_across_a_restart(deferred):
    """The map is checked before the cause is written: a card first missed
    here as other (a deck this process built), whose row save then failed,
    keeps other when it's retried after a restart (where it would classify as
    restart_split); the retry only writes the row."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered_to_119(client, job_id)
    ev = server._trade_jobs[job_id]["evidence"]
    with ev.lock:
        ev.rows.pop(contract.card_impression_id(job_id, 95))
    with fail_after(engine, "INSERT INTO DECK_IMPRESSIONS"):
        view(job_id, 95)
    assert run_of(engine, job_id)["upgrade_miss_cards"] == {"95": "other"}
    restart()
    view(job_id, 95)
    assert len([r for r in rows(engine) if r["card_index"] == 95]) == 1
    run = run_of(engine, job_id)
    assert (run["upgrade_miss_cards"], run["upgrade_misses"]) == (
        {"95": "other"}, {**NO_MISSES, "other": 1})


def test_the_merge_unions_the_maps_and_tallies_them():
    """The CAS merge: the union, a card in both keeping the stored cause (it
    landed first), and upgrade_misses the merged map's tally, whatever either
    side's counts said."""
    stored = {"upgrade_miss_cards": {"91": "restart_split", "95": "restart_split"},
              "upgrade_misses": {"restart_split": 2, "evicted_split": 0, "other": 0}}
    ours = {"upgrade_miss_cards": {"95": "other", "97": "evicted_split"},
            "upgrade_misses": {"restart_split": 0, "evicted_split": 1, "other": 1}}
    merged = server._merge_pack_runs(stored, ours, {"upgrade_miss_cards": {}})
    assert merged["upgrade_miss_cards"] == {"91": "restart_split", "95": "restart_split",
                                            "97": "evicted_split"}
    assert merged["upgrade_misses"] == {"restart_split": 2, "evicted_split": 1, "other": 0}


def test_two_writers_that_missed_the_same_card_count_it_once(deferred):
    """A deploy overlap: two processes, each holding the stored header, miss
    card 95 (the second classifies it other: it built the deck). The second's
    commit misses the CAS, merges (the stored restart_split wins) and lands:
    one entry, one count, one row."""
    from datetime import datetime, timezone
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered_to_119(client, job_id)
    restart()
    first = server._load_pack_state(job_id, UID)
    second = server._load_pack_state(job_id, UID)
    iid = contract.card_impression_id(job_id, 95)
    now = datetime.now(timezone.utc).isoformat()
    with server._deck_evidence_write_lock:
        assert server._deck_upgrade_from_pack(first, job_id, iid, 95, now)
    server._note_deck_held(job_id)                         # the second process built it
    with server._deck_evidence_write_lock:
        assert server._deck_upgrade_from_pack(second, job_id, iid, 95, now)
    run = run_of(engine, job_id)
    assert run["upgrade_miss_cards"] == {"95": "restart_split"}
    assert run["upgrade_misses"] == {**NO_MISSES, "restart_split": 1}
    assert len([r for r in rows(engine) if r["card_index"] == 95]) == 1
