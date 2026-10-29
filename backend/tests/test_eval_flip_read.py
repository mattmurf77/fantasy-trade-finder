"""backend.eval.flip_read, the model-side 24 h read after the one-step 200 ms
flip (models-lead-launch.md §Gate-11-03 §3, addenda A3 and B3 (f3)): each
barred G passing and failing (a failing G fails the read), G2 over final
packed decks and every pack-less deck, G3's ghost-row bucket (a loaded
ghost row, and one of a deck served before the window), G10 at
trade_i1_mode 0, 1 and 2, the two weekly ceilings (U4-R4, B4) at, under and
over, the CLI's as_of settle (STAMP_SETTLE) on a pinned clock, each exit
status, the read-only guard and engine options, and that the module never
imports backend.server.

The DBs are in-memory SQLite built with the v5 tests' helpers (the pack and
withdrawals tables are test-local there); the CLI tests write the same tables
to a temporary file and read it through the read-only engine.
"""

import json
import sqlite3
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import MetaData, create_engine, event, insert, text

import backend.eval.flip_read as fr
from backend.database import deck_outcomes_table
from backend.eval.data import (
    CALIBRATION_REFRESH, IN_FLIGHT, INCOMPLETE_DECK, NO_DELIVERY_EVIDENCE, WITHDRAWAL_CONFLICT,
)
from backend.eval.flip_read import (
    FAIL, INSUFFICIENT, PASS, REPORT, ReadOnlyViolation, flip_read, main, read_only_engine,
    render, weekly_read,
)
from backend.tests.test_eval_pack_reader import SERVED, _deck_cards, _row, pack_table, write_deck
from backend.tests.test_eval_refresh_and_live_columns import _bare_impressions
from backend.tests.test_eval_withdrawals_and_paging import (
    DB, PAGING_COLUMNS, _after, act, make_db, put_deck, put_pack, withdraw, withdrawals_table,
)

REPO = Path(__file__).resolve().parents[2]
SINCE = "2026-10-23T00:00:00+00:00"
EARLY = _after(2)             # 2 h after SERVED: inside the 25 h window
LATE = _after(30)             # 30 h after: a deck served at SERVED is final
BEFORE = "2026-10-22T12:00:00+00:00"   # served before the window


def _post(db: DB, impression_id, action="viewed", at=SERVED):
    with db.eng.begin() as conn:
        conn.execute(insert(deck_outcomes_table).values(
            impression_id=impression_id, action=action, acted_at=at))


def _packed(db: DB, job, n=10, *, rows=5, cards=None, served_at=SERVED, **run):
    """Rows 0..rows-1 and a pack of the rest (through `cards`, default n),
    delivered whole unless `deliveries` is given; `run` is the run metadata."""
    built = _deck_cards(job, n, served_at=served_at)
    put_deck(db, job, n, rows=range(rows), served_at=served_at)
    last = (cards or n) - 1
    put_pack(db, job, built[rows:cards], card_count=n, served_at=served_at,
             **{"deliveries": [[last, served_at]], **run})


# ---------------------------------------------------------------------------
# G1: pack integrity, over every pack retired or not
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tamper", [False, True], ids=["clean", "tampered"])
def test_g1_counts_unreadable_packs_among_every_pack(tamper):
    db = make_db()
    write_deck(db.eng, db.packs, _deck_cards("ok", 10), full=range(5), packed=range(5, 10))
    _packed(db, "live", deliveries=[[4, SERVED]], retired=False)      # in flight: still counted
    write_deck(db.eng, db.packs, _deck_cards("bad", 10), full=range(5), packed=range(5, 10),
               edit=(lambda p: replace(p, checksum="0" * 64)) if tamper else None)
    put_deck(db, "rows", 6)                                           # no pack row
    r = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert r.g1["pack_decks"] == 3
    assert r.g1["pack_integrity"] == int(tamper)
    assert r.g1["status"] == (FAIL if tamper else PASS)
    text = render(r)
    if tamper:
        assert r.g1["ids"] == ["bad"] and r.overall == FAIL
        assert "| G1 | pack_integrity decks (+ malformed display moves) / decks with a pack row | 1 (+ 0) / 3 | 0 | FAIL |" in text
        assert "models-lead recommends the kill" in text


@pytest.mark.parametrize("run", [5, None, "x", [1]], ids=["int", "null", "str", "list"])
def test_g1_a_pack_whose_run_is_not_an_object_fails_g1_not_the_read(run):
    """A parseable header whose run is not an object is G1's FAIL and the B3
    (f4) kill, on the 24 h read and the weekly one, never a crash."""
    db = make_db()
    write_deck(db.eng, db.packs, _deck_cards("ok", 10), full=range(5), packed=range(5, 10))
    write_deck(db.eng, db.packs, _deck_cards("bad", 10), full=range(5), packed=range(5, 10),
               edit=lambda p: replace(p, header_json=json.dumps(
                   {**json.loads(p.header_json), "run": run})))
    r = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert r.g1["ids"] == ["bad"] and r.g1["status"] == FAIL and r.overall == FAIL
    assert r.g7["row_gone"] == 0
    assert "models-lead recommends the kill" in render(r)
    assert weekly_read(db.eng, as_of=LATE)["u4_r4"]["row_gone"] == 0
    # The guard holds on its own, not only through the integrity skip.
    assert fr._row_gone({"bad": (SERVED, json.dumps({"run": run}))})["total"] == 0


# ---------------------------------------------------------------------------
# G2: incomplete decks among final packed decks and every pack-less deck, and
# the 10-final-packed-deck minimum
# ---------------------------------------------------------------------------

def test_g2_reads_final_packed_decks_and_every_pack_less_deck():
    """2 h after serving, only the retired packs are final: an unretired pack
    is in flight. A pack-less deck has no in-flight state, so its gap
    (incomplete_deck to the loader) is barred at once. 30 h after, every
    pack is final."""
    db = make_db()
    _packed(db, "retired_gap", cards=9, retired=True, retired_at=_after(1))   # lost card 9
    _packed(db, "retired_ok", retired=True, retired_at=_after(1))
    _packed(db, "live", deliveries=[[4, SERVED]], retired=False)
    put_deck(db, "rows_gap", 10, rows={*range(10)} - {4})
    put_deck(db, "refresh", 6, source="grading_refresh")              # not a Trades deck

    early = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert early.exclusions[IN_FLIGHT] == 1 and early.exclusions[INCOMPLETE_DECK] == 2
    assert (early.g2["final_packed_decks"], early.g2["packless_decks"]) == (2, 1)
    assert early.g2["incomplete"] == 2 and early.g2["status"] == FAIL
    assert early.g2["ids"] == [["retired_gap", SERVED], ["rows_gap", SERVED]]
    assert early.g2["insufficient"] and early.overall == FAIL
    text = render(early)
    assert ("| G2 | incomplete_deck / Trades decks read (final packed + every pack-less) "
            "| 2 / 3 (2 final packed + 1 pack-less) | 0; INSUFFICIENT below 10 final packed "
            "| FAIL |") in text
    assert "G2 INSUFFICIENT (<10 final packed decks): extend to 48 h (2 final packed)" in text
    assert f"retired_gap (served {SERVED}), rows_gap (served {SERVED})" in text

    late = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert late.exclusions[CALIBRATION_REFRESH] == 1
    assert (late.g2["final_packed_decks"], late.g2["packless_decks"]) == (3, 1)
    assert late.g2["incomplete"] == 2
    assert late.g2["ids"] == [["retired_gap", SERVED], ["rows_gap", SERVED]]


def test_g2_fails_on_pack_less_live_decks_with_a_gap_or_a_missed_stamp_inside_25_h():
    """release-lead's #425 QA probe: 10 retired packs (sufficient), and two
    live-mode value-core decks (marked rows at build, delivered_at stamps,
    no pack) 2 h after serving, one with a gap and one with an outcome on a
    row never stamped delivered. Both are incomplete_deck to the loader;
    final-only G2 read 0 / 10 PASS and OVERALL PASS."""
    db = make_db(live=PAGING_COLUMNS)
    for k in range(10):
        _packed(db, f"r{k}", retired=True, retired_at=_after(1))
    put_deck(db, "vc_gap", 10, rows=[i for i in range(10) if i != 4],
             delivered=[i for i in range(10) if i != 4], extra={"page_store": 1})
    put_deck(db, "vc_stamp", 10, delivered=range(5), extra={"page_store": 1})
    act(db, "vc_stamp", 7, "viewed")                  # viewed, never stamped delivered
    put_deck(db, "vc_ok", 10, delivered=range(10), viewed=[3], extra={"page_store": 1})

    r = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert r.exclusions[INCOMPLETE_DECK] == 2
    assert (r.g2["final_packed_decks"], r.g2["packless_decks"]) == (10, 3)
    assert r.g2["incomplete"] == 2 and not r.g2["insufficient"]
    assert r.g2["ids"] == [["vc_gap", SERVED], ["vc_stamp", SERVED]]
    assert r.g2["status"] == FAIL and r.overall == FAIL
    text = render(r)
    assert ("| G2 | incomplete_deck / Trades decks read (final packed + every pack-less) "
            "| 2 / 13 (10 final packed + 3 pack-less) | 0; INSUFFICIENT below 10 final "
            "packed | FAIL |") in text
    assert "OVERALL: FAIL" in text and "INSUFFICIENT (<10" not in text


def test_g2_does_not_count_a_deferred_deck_waiting_on_its_pack(monkeypatch):
    """A tiered (deferred-evidence) deck served at/after PACK_REQUIRED_SINCE
    with no pack yet is the loader's in_flight inside 25 h, not
    incomplete_deck, so it never fails G2; past 25 h it is a lost pack."""
    import backend.eval.data as data_mod
    monkeypatch.setattr(data_mod, "PACK_REQUIRED_SINCE", SINCE)
    db = make_db(live=PAGING_COLUMNS)
    put_deck(db, "tiered", 10, rows=range(5), tier="first30", delivered=range(5))
    early = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert early.exclusions[IN_FLIGHT] == 1 and early.g2["packless_decks"] == 1
    assert early.g2["incomplete"] == 0 and early.g2["status"] == PASS
    late = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert late.g2["ids"] == [["tiered", SERVED]] and late.g2["status"] == FAIL


@pytest.mark.parametrize("n", [9, 10])
def test_g2_says_insufficient_below_ten_final_packed_decks(n):
    """A retired pack is final at once; pack-less decks never count toward
    the minimum, however old."""
    db = make_db()
    for k in range(n):
        _packed(db, f"r{k}", retired=True, retired_at=_after(1))
        put_deck(db, f"d{k}", 4)
    early = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert early.g2["final_packed_decks"] == n and early.g2["packless_decks"] == n
    assert early.g2["insufficient"] == (n < 10)
    assert early.g2["status"] == PASS and early.overall == (INSUFFICIENT if n < 10 else PASS)
    assert ("INSUFFICIENT (<10 final packed decks): extend to 48 h" in render(early)) == (n < 10)
    late = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert late.g2["final_packed_decks"] == n and late.g2["insufficient"] == (n < 10)


# ---------------------------------------------------------------------------
# G3: every outcome in the window joins a card, row or packed
# ---------------------------------------------------------------------------

GHOST_ID = "5f0c2a9e-3b7d-4e61-9a24-c1d8e7f60b13"   # ghosts keep uuid4 ids


def _joins_db() -> DB:
    """j: rows 0-4 and a pack of 5-9, viewed at 2 (a row) and 7 (left
    packed), and a ghost row copying card 3 under a uuid4 id, as the
    writer gives ghosts; old: served before the window, viewed in it at 1
    (a row) and 8 (packed)."""
    db = make_db()
    cards = _deck_cards("j", 10)
    write_deck(db.eng, db.packs, cards, full=range(5), packed=range(5, 10), viewed=[2, 7])
    with db.eng.begin() as conn:
        conn.execute(insert(db.imp).values({**_row(cards[3], ghost=True),
                                            "impression_id": GHOST_ID}))
    write_deck(db.eng, db.packs, _deck_cards("old", 10, served_at=BEFORE), full=range(5),
               packed=range(5, 10), served_at=BEFORE)
    act(db, "old", 1, "viewed")
    act(db, "old", 8, "viewed")
    return db


def test_g3_passes_when_every_outcome_joins():
    r = flip_read(_joins_db().eng, since=SINCE, as_of=LATE)
    assert r.g3 == {"outcomes": 4, "joined": 2, "joined_outside_window": 2, "on_ghost": 0,
                    "ghost_ids": [], "orphans": 0, "ids": [], "status": PASS}


@pytest.mark.parametrize("impression_id", [
    "j:12",                 # its deck is in the window; the card is not
    "old:15",               # past the older deck's card_count
    "nowhere:0",            # no row, no pack
    "legacy-uuid-1",        # not a contract id, and no row
    "j:3:ghost",            # the old ghost suffix, joining no ghost row
])
def test_g3_fails_on_an_outcome_joining_no_card(impression_id):
    db = _joins_db()
    _post(db, impression_id, action="like")
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert r.g3["orphans"] == 1 and r.g3["ids"] == [impression_id] and r.g3["on_ghost"] == 0
    assert r.g3["status"] == FAIL and r.overall == FAIL
    assert f"G3 outcomes joining no card: {impression_id}" in render(r)


def test_g3_fails_on_an_outcome_on_a_ghost_row():
    """Ghosts are never shown: an outcome joining a loaded ghost row means a
    ghost reached a client. Counted apart from the orphans, barred at 0."""
    db = _joins_db()
    _post(db, GHOST_ID)
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert (r.g3["on_ghost"], r.g3["ghost_ids"], r.g3["orphans"]) == (1, [GHOST_ID], 0)
    assert r.g3["joined"] == 2 and r.g3["status"] == FAIL and r.overall == FAIL
    text = render(r)
    assert ("| G3 | outcomes joining no card / on a ghost row | 0 / 1 of 5 (joined 2, "
            "outside the window 2) | 0 / 0 | FAIL |") in text
    assert ("G3 outcomes on a ghost row (ghosts are never shown: a ghost reached a "
            f"client): {GHOST_ID}") in text
    # A serve bug, not lost data: back to models-lead, never the kill (B3 (f4)).
    assert "recommends the kill" not in text
    assert "Back to models-lead" in text


OLD_GHOST_ID = "9a1e7c44-0d2b-4f8e-b3a6-5c7d2e1f0a98"


def test_g3_an_outcome_on_a_ghost_row_of_a_deck_served_before_the_window():
    """#431 QA P3: the ghost row of a deck served before the window is not
    loaded, and its uuid4 id names no run, so the out-of-window lookup finds
    it by id (is_ghost = 1). The outcome is on a ghost row (barred, back to
    models-lead), not an orphan that prints the kill."""
    db = _joins_db()
    old = _deck_cards("old", 10, served_at=BEFORE)
    with db.eng.begin() as conn:
        conn.execute(insert(db.imp).values({**_row(old[3], ghost=True),
                                            "impression_id": OLD_GHOST_ID}))
    _post(db, OLD_GHOST_ID)
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert (r.g3["on_ghost"], r.g3["ghost_ids"], r.g3["orphans"]) == (1, [OLD_GHOST_ID], 0)
    assert r.g3["joined_outside_window"] == 2
    assert r.g3["status"] == FAIL and r.overall == FAIL
    text = render(r)
    assert "recommends the kill" not in text and "Back to models-lead" in text


def test_an_orphan_outcome_recommends_the_kill():
    """B3 (f4): an outcome that joins no card is lost data, so the read
    recommends the kill at once."""
    db = _joins_db()
    _post(db, "nowhere:9")
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert r.g3["orphans"] == 1 and r.g3["status"] == FAIL
    assert ("G1 failed or G3 has orphans: models-lead recommends the kill "
            "(first_page_store_enabled 0) at once") in render(r)       # the exact condition


def test_g3_reads_only_outcomes_in_the_window_and_by_as_of():
    db = _joins_db()
    _post(db, "nowhere:0", at=BEFORE)          # before the window
    _post(db, "nowhere:1", at=_after(31))      # after as_of
    _post(db, GHOST_ID, at=_after(31))         # after as_of
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert r.g3["outcomes"] == 4 and r.g3["status"] == PASS


# ---------------------------------------------------------------------------
# G7: upgrade misses by cause; `other` is the one that must be 0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("misses, total, status", [
    ({"restart_split": 2, "evicted_split": 1, "other": 0},
     {"evicted_split": 1, "other": 0, "restart_split": 3}, PASS),
    ({"other": 1}, {"other": 1, "restart_split": 1}, FAIL),
    (2, {"other": 2, "restart_split": 1}, FAIL),       # a legacy int: cause unknown
    (0, {"other": 0, "restart_split": 1}, PASS),
    (None, {"restart_split": 1}, PASS),
], ids=["named_causes", "other", "legacy_int", "legacy_zero", "missing"])
def test_g7_bars_other_and_prints_every_cause(misses, total, status):
    db = make_db()
    _packed(db, "p", **({} if misses is None else {"upgrade_misses": misses}))
    _packed(db, "q", upgrade_misses={"restart_split": 1}, retired=False)   # in flight: counted
    r = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert r.g7["upgrade_misses"] == total and list(r.g7["upgrade_misses"]) == sorted(total)
    assert r.g7["status"] == status
    assert r.overall == (FAIL if status == FAIL else INSUFFICIENT)    # 1 final packed deck
    causes = ", ".join(f"{k}={v}" for k, v in sorted(total.items()))
    assert f"| G7 | upgrade misses by cause | {causes} | other 0 | {status} |" in render(r)


def test_g7_reports_misses_whose_page_row_was_gone_without_barring_them():
    """U4 option A's guard (head-eng's condition 1): misses whose pack recorded
    a stored count above the card while the page row was gone, and how many of
    them carry a named cause. Reported, never barred: G7 stays bar-on-other."""
    db = make_db()
    _packed(db, "p", upgrade_misses={"restart_split": 1, "other": 0},
            upgrade_miss_cards={"12": "restart_split", "40": "evicted_split", "41": "other"},
            upgrade_miss_row_gone={"12": 90, "40": 90, "41": 90},
            upgrade_miss_row_gone_why={"12": "replaced", "40": "no_row"})   # 41: unsplit
    _packed(db, "q", upgrade_misses={"restart_split": 1},
            upgrade_miss_row_gone={"7": 90})                     # no cause map: other
    _packed(db, "r", upgrade_misses={"restart_split": 1})        # no row-gone key: 0
    r = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert (r.g7["row_gone"], r.g7["row_gone_named"]) == (4, 2)
    assert r.g7["row_gone_split"] == {"replaced": 1, "no_row": 1, "unsplit": 2}   # C4 (d1)
    assert r.g7["status"] == PASS                                # never barred
    assert ("G7 (not barred) row gone: 4 misses whose pack recorded a stored count above "
            "the card while its page row was gone; 2 of them with a named cause (U4 option "
            "A's guard); replaced=1, no_row=1, unsplit=2.") in render(r)


def test_row_gone_never_reads_a_pack_failing_integrity():
    """A pack failing integrity is G1's: its run metadata is not trusted, so
    its row-gone entries are not counted (its misses are not either)."""
    db = make_db()
    _packed(db, "bad", upgrade_misses={"restart_split": 1},
            upgrade_miss_cards={"7": "restart_split"}, upgrade_miss_row_gone={"7": 90})
    with db.eng.begin() as conn:
        conn.execute(db.packs.update().where(db.packs.c.run_id == "bad")
                     .values(checksum="0" * 64))
    r = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert r.g1["ids"] == ["bad"]
    assert (r.g7["upgrade_misses"], r.g7["row_gone"], r.g7["row_gone_named"]) == ({}, 0, 0)
    assert weekly_read(db.eng, as_of=LATE)["u4_r4"]["row_gone"] == 0


def test_g7_row_gone_reads_any_other_why_as_unsplit():
    db = make_db()
    _packed(db, "p", upgrade_misses={"restart_split": 3},
            upgrade_miss_cards={"6": "restart_split", "7": "restart_split", "8": "restart_split"},
            upgrade_miss_row_gone={"6": 90, "7": 90, "8": 90},
            upgrade_miss_row_gone_why={"6": "mystery", "7": ["replaced"], "8": {"no_row": 1}})
    r = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert r.g7["row_gone_split"] == {"replaced": 0, "no_row": 0, "unsplit": 3}


def test_g7_reports_the_u4_r4_sum_over_the_window_as_indicative_only():
    """Addendum C4: over the 24 h window the U4-R4 sum (named causes / viewed
    cards) is indicative; it never changes G7's status, which bars other only."""
    db = _joins_db()                                   # 2 viewed cards in the window
    _packed(db, "p", upgrade_misses={"restart_split": 1, "evicted_split": 1, "other": 0})
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    ind = r.g7["indicative"]
    assert (ind["numerator"], ind["status"]) == (2, "OVER") and ind["denominator"] >= 2
    assert r.g7["status"] == PASS
    assert "indicative only, the 7-day ceiling is read with --weekly" in render(r)


# ---------------------------------------------------------------------------
# G8, G9, G10
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("conflict", [False, True], ids=["removed", "conflict"])
def test_g8_bars_withdrawal_conflicts(conflict):
    db = make_db(live=PAGING_COLUMNS)
    put_deck(db, "c", 8, rows=range(8), delivered=[3] if conflict else [], w0=[3])
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert r.exclusions[WITHDRAWAL_CONFLICT] == int(conflict)
    assert r.g8["withdrawal_conflict"] == int(conflict)
    assert r.g8["status"] == (FAIL if conflict else PASS)
    assert r.g8["ids"] == (["c"] if conflict else [])
    assert r.overall == (FAIL if conflict else INSUFFICIENT)


@pytest.mark.parametrize("actions", [(), ("viewed",), ("pass",)], ids=["none", "viewed", "pass"])
def test_g9_a_deck_without_delivery_evidence_must_have_no_outcome(actions):
    """B3: a built-but-undelivered deck lands in no_delivery_evidence
    legitimately; an outcome there means a missed delivered_at stamp."""
    db = make_db(live=PAGING_COLUMNS)
    put_deck(db, "quiet", 6, tier="first30")
    put_deck(db, "acted", 6, tier="first30")
    for action in actions:
        act(db, "acted", 0, action)
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert r.exclusions[NO_DELIVERY_EVIDENCE] == r.g9["no_delivery_evidence"] == 2
    assert r.g9["with_outcomes"] == (1 if actions else 0)
    assert r.g9["status"] == (FAIL if actions else PASS)
    assert r.g9["ids"] == (["acted"] if actions else [])
    assert r.overall == (FAIL if actions else INSUFFICIENT)            # G9 is barred


def _withdrawals_db(i1_dropped: bool) -> DB:
    db = make_db()
    withdraw(db, "a", 1, 0, reason="disposition_cut")
    withdraw(db, "a", 2, 1, reason="disposition_cut")
    if i1_dropped:
        withdraw(db, "b", 0, 0, reason="i1_dropped")
    withdraw(db, "c", 0, 0, reason="disposition_cut", at=BEFORE)        # before the window
    withdraw(db, "d", 0, 0, reason="i1_dropped", at=_after(31))         # after as_of
    return db


@pytest.mark.parametrize("i1_dropped", [False, True], ids=["cuts_only", "i1_dropped"])
def test_g10_at_mode_1_bars_i1_dropped_and_reports_cuts(i1_dropped):
    """trade_i1_mode 1 (the default, the launch value) withdraws nothing for
    I-1: any i1_dropped in the window fails G10 and the read. Cuts are
    expected and only reported."""
    db = _withdrawals_db(i1_dropped)
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert r.g10["by_reason"] == ({"disposition_cut": 2, "i1_dropped": 1} if i1_dropped
                                  else {"disposition_cut": 2})
    assert r.g10["i1_mode"] == 1 and r.g10["status"] == (FAIL if i1_dropped else PASS)
    assert r.overall == (FAIL if i1_dropped else INSUFFICIENT)       # no final decks here
    text = render(r)
    assert ("| G10 | withdrawals by reason (window), trade_i1_mode 1 | disposition_cut=2"
            + (", i1_dropped=1" if i1_dropped else "")
            + f" | i1_dropped 0 | {FAIL if i1_dropped else PASS} |") in text
    assert ("G10 note: disposition_cut > 0 expected; any i1_dropped at trade_i1_mode 1 is "
            "a bug (barred at 0).") in text
    assert flip_read(db.eng, since=SINCE, as_of=LATE, until=SERVED).g10["by_reason"] == {}


def test_g10_at_mode_2_only_reports_i1_dropped():
    db = _withdrawals_db(i1_dropped=True)
    r = flip_read(db.eng, since=SINCE, as_of=LATE, i1_mode=2)
    assert r.g10["by_reason"] == {"disposition_cut": 2, "i1_dropped": 1}
    assert r.g10["i1_mode"] == 2 and r.g10["status"] == REPORT
    assert r.overall == INSUFFICIENT                 # not barred at mode 2; no final decks
    text = render(r)
    assert ("| G10 | withdrawals by reason (window), trade_i1_mode 2 | disposition_cut=2, "
            "i1_dropped=1 | reported | REPORT |") in text
    assert "disposition_cut > 0 expected; i1_dropped reported at trade_i1_mode 2" in text


def test_the_v5_exclusion_counts_cover_every_reason_and_the_removals_by_reason():
    db = make_db(live=PAGING_COLUMNS)
    put_deck(db, "kept", 10, rows=[i for i in range(10) if i not in (2, 6)], viewed=[0])
    withdraw(db, "kept", 2, 0, reason="disposition_cut")
    withdraw(db, "kept", 6, 0, reason="i1_dropped")
    put_deck(db, "partial", 6, tier=lambda i: "partial_run", delivered=range(6))
    put_deck(db, "nde", 6, tier="first30")
    put_deck(db, "refresh", 6, source="grading_refresh")
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert r.decks == 4
    assert r.exclusions == {"calibration_refresh": 1, "pack_integrity": 0,
                            "withdrawal_conflict": 0, "in_flight": 0, "incomplete_deck": 0,
                            "no_delivery_evidence": 1, "none": 2}
    assert r.partial_run_decks == 1
    assert r.withdrawn_removed_by_reason == {"disposition_cut": 1, "i1_dropped": 1}
    assert ("v5 exclusions (decks): calibration_refresh=1, pack_integrity=0, "
            "withdrawal_conflict=0, in_flight=0, incomplete_deck=0, no_delivery_evidence=1, "
            "none=2; partial_run decks (replay): 1; withdrawn_removed_by_reason "
            "(every loaded deck): disposition_cut=1, i1_dropped=1") in render(r)


# ---------------------------------------------------------------------------
# The weekly ceilings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("named, status", [
    ({}, "OK"),                                            # under: 0 / 100
    ({"restart_split": 1}, "OK"),                          # at: 1 / 100
    ({"restart_split": 1, "evicted_split": 1}, "OVER"),    # over: every named cause counts
], ids=["under", "at", "over"])
def test_weekly_u4_r4_named_misses_over_viewed_cards(named, status):
    """The denominator is viewed cards only (a like without a view is not
    one, nor a ghost's view); `other` is not a named cause; a deck served
    before the 7 days is not read."""
    db = make_db()
    put_deck(db, "viewed", 100, viewed=range(100), ghosts=[0])
    _post(db, "viewed:0:ghost")
    put_deck(db, "liked", 10)
    for i in range(10):
        act(db, "liked", i, "like")
    _packed(db, "p", upgrade_misses={**named, "other": 3},
            upgrade_miss_row_gone={"40": 90}, upgrade_miss_row_gone_why={"40": "replaced"})
    _packed(db, "old", served_at="2026-10-16T12:00:00+00:00",
            upgrade_misses={"restart_split": 9}, upgrade_miss_row_gone={"50": 90})
    w = weekly_read(db.eng, as_of=LATE)
    u = w["u4_r4"]
    assert (u["numerator"], u["denominator"]) == (sum(named.values()), 100)
    # C4 (d1): the weekly line reports row_gone too, the old deck's not read
    assert u["row_gone"] == 1 and u["row_gone_split"] == {"replaced": 1, "no_row": 0,
                                                           "unsplit": 0}
    assert u["causes"] == dict(sorted(named.items())) and u["status"] == status
    assert u["ceiling"] == fr.U4_R4_CEILING == 0.01
    assert fr.U4_R4_CAUSES == ("restart_split", "evicted_split")


def test_u4_r4_sums_the_two_named_causes_once():
    """Addendum C2: restart_split + evicted_split, by name. `other` and a
    cause added later stay out, and a row-gone miss, already counted under
    its cause, is not counted again: in the weekly sum or the indicative one."""
    db = make_db()
    put_deck(db, "viewed", 100, viewed=range(100))
    _packed(db, "p", upgrade_misses={"restart_split": 1, "evicted_split": 1,
                                     "cross_worker": 2, "other": 3},
            upgrade_miss_cards={"5": "restart_split", "6": "evicted_split"},
            upgrade_miss_row_gone={"5": 90, "6": 90})
    u = weekly_read(db.eng, as_of=LATE)["u4_r4"]
    assert (u["numerator"], u["denominator"]) == (2, 100)
    assert u["causes"] == {"evicted_split": 1, "restart_split": 1}
    assert (u["row_gone"], u["row_gone_named"]) == (2, 2)
    ind = flip_read(db.eng, since=SINCE, as_of=LATE).g7["indicative"]
    assert (ind["numerator"], ind["denominator"]) == (2, 100)


@pytest.mark.parametrize("cuts, status", [(4, "OK"), (5, "OK"), (6, "OVER")],
                         ids=["under", "at", "over"])
def test_weekly_b4_disposition_cuts_over_delivered_range_positions(cuts, status):
    """A paged deck (rows with delivered_at): 90 - cuts delivered, the cuts,
    an i1_dropped removal (not a cut) and 3 undelivered rows; a packed deck
    delivered through 9. A legacy deck (no delivery evidence) and a conflict
    deck (excluded) don't count. delivered + cuts = 100."""
    db = make_db(live=PAGING_COLUMNS)
    cut, tail = set(range(10, 10 + cuts)), {91, 92, 93}
    rows = [i for i in range(94) if i not in cut and i != 50]
    put_deck(db, "paged", 94, rows=rows, tier="first30",
             delivered=[i for i in rows if i not in tail])
    for i in cut:
        withdraw(db, "paged", i, 0, reason="disposition_cut")
    withdraw(db, "paged", 50, 0, reason="i1_dropped")
    _packed(db, "packed", 20, deliveries=[[9, SERVED]])
    put_deck(db, "legacy", 50)
    put_deck(db, "bad", 8, rows=range(8), delivered=[3])
    withdraw(db, "bad", 3, 0, reason="disposition_cut")
    w = weekly_read(db.eng, as_of=LATE)
    b = w["b4"]
    assert (b["numerator"], b["denominator"], b["evidenced_decks"]) == (cuts, 100, 2)
    assert b["status"] == status and b["ceiling"] == fr.B4_CEILING == 0.05
    assert b["ratio"] == cuts / 100


# ---------------------------------------------------------------------------
# The CLI, read-only
# ---------------------------------------------------------------------------

def _file_db(path) -> DB:
    md = MetaData()
    imp = _bare_impressions(md, PAGING_COLUMNS)
    deck_outcomes_table.to_metadata(md)
    packs, wd = pack_table(md), withdrawals_table(md)
    eng = create_engine(f"sqlite:///{path}")
    md.create_all(eng)
    return DB(eng, packs, wd, imp)


def _example(db: DB):
    """A small read: a retired packed deck, a paged row deck with a cut, an
    unretired pack, a legacy deck, a refresh deck, an outcome on a deck
    served before the window, and withdrawals."""
    _packed(db, "packed", 30, rows=5, deliveries=[[19, SERVED]], retired=True,
            retired_at=_after(1), upgrade_misses={"restart_split": 1, "other": 0})
    act(db, "packed", 0, "viewed")
    act(db, "packed", 12, "viewed")
    put_deck(db, "paged", 12, rows=[i for i in range(12) if i != 9], tier="first30",
             delivered=range(8), viewed=[0, 2])
    withdraw(db, "paged", 9, 0, reason="disposition_cut")
    _packed(db, "live", deliveries=[[4, SERVED]], retired=False)
    put_deck(db, "legacy", 8, viewed=[0, 1])
    put_deck(db, "refresh", 6, source="grading_refresh")
    put_deck(db, "old", 6, served_at=BEFORE)
    act(db, "old", 1, "viewed")


def test_the_cli_reads_a_sqlite_file_read_only_and_never_writes(tmp_path, capsys):
    path = tmp_path / "flip.db"
    db = _file_db(path)
    _example(db)
    db.eng.dispose()
    before = path.read_bytes()

    args = ["--db", str(path), "--since", "2026-10-23T00:00:00Z", "--as-of", _after(20)]
    assert main(args) == 3                                         # INSUFFICIENT: not a pass
    out = capsys.readouterr().out
    assert "| G1 | pack_integrity decks (+ malformed display moves) / decks with a pack row | 0 (+ 0) / 2 | 0 | PASS |" in out
    assert ("| G2 | incomplete_deck / Trades decks read (final packed + every pack-less) "
            "| 0 / 3 (1 final packed + 2 pack-less) | 0; INSUFFICIENT below 10 final packed "
            "| PASS |") in out
    assert "| G3 | outcomes joining no card / on a ghost row | 0 / 0 of 7" in out
    assert "OVERALL: INSUFFICIENT" in out and "Weekly ceilings" not in out

    # 1 restart split over 7 viewed cards is over 1%: OVER exits 1, over INSUFFICIENT's 3.
    assert main(args + ["--weekly"]) == 1
    out = capsys.readouterr().out
    assert ("U4-R4 named upgrade misses / viewed cards: 14.29% (1 / 7), ceiling 1%: OVER "
            "[restart_split=1]") in out
    assert ("B4 disposition_cut removals / delivered-range positions: 3.45% (1 / 29), "
            "ceiling 5%: OK") in out

    assert main(args + ["--json", "--weekly"]) == 1
    got = json.loads(capsys.readouterr().out)
    assert got["overall"] == INSUFFICIENT and got["g7"]["upgrade_misses"] == {
        "other": 0, "restart_split": 1}
    assert got["since"] == "2026-10-23T00:00:00+00:00"           # normalized to UTC
    assert got["weekly"]["u4_r4"]["status"] == "OVER" and got["weekly"]["b4"]["status"] == "OK"
    assert path.read_bytes() == before

    eng = read_only_engine(str(path))
    try:
        with pytest.raises(ReadOnlyViolation):
            with eng.begin() as conn:
                conn.execute(text("DELETE FROM deck_outcomes"))
        raw = eng.raw_connection()              # below the statement guard: mode=ro holds
        try:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                raw.cursor().execute("DELETE FROM deck_outcomes")
        finally:
            raw.close()
    finally:
        eng.dispose()
    assert path.read_bytes() == before


def test_a_fail_exits_1(tmp_path, capsys):
    path = tmp_path / "flip.db"
    db = _file_db(path)
    _example(db)
    _post(db, "packed:99")                       # joins no card: G3 fails
    db.eng.dispose()
    assert main(["--db", f"sqlite:///{path}", "--since", SINCE, "--as-of", _after(20)]) == 1
    out = capsys.readouterr().out
    assert "OVERALL: FAIL" in out and "recommends the kill (first_page_store_enabled 0)" in out


def test_a_pass_exits_0(tmp_path, capsys):
    path = tmp_path / "flip.db"
    db = _file_db(path)
    for k in range(10):
        _packed(db, f"r{k}", retired=True, retired_at=_after(1))
    db.eng.dispose()
    assert main(["--db", str(path), "--since", SINCE, "--as-of", EARLY]) == 0
    assert "OVERALL: PASS" in capsys.readouterr().out


def test_the_cli_i1_mode_defaults_to_1(tmp_path, capsys):
    """An i1_dropped withdrawal fails the read at the default (1); with
    --i1-mode 2 it is reported and the read is INSUFFICIENT (exit 3)."""
    path = tmp_path / "flip.db"
    db = _file_db(path)
    _example(db)
    withdraw(db, "packed", 29, 0, reason="i1_dropped")
    db.eng.dispose()
    args = ["--db", str(path), "--since", SINCE, "--as-of", _after(20)]
    assert main(args) == 1
    assert "trade_i1_mode 1 | disposition_cut=1, i1_dropped=1 | i1_dropped 0 | FAIL |" in (
        capsys.readouterr().out)
    assert main(args + ["--i1-mode", "2"]) == 3
    out = capsys.readouterr().out
    assert "trade_i1_mode 2 | disposition_cut=1, i1_dropped=1 | reported | REPORT |" in out
    assert "OVERALL: INSUFFICIENT" in out
    with pytest.raises(SystemExit) as usage:
        main(args + ["--i1-mode", "3"])
    assert usage.value.code == 2


def test_the_cli_at_i1_mode_0_bars_i1_dropped_too(tmp_path, capsys):
    """#431 QA P3: trade_i1_mode 0 never withdraws for I-1 either, so an
    i1_dropped withdrawal fails G10 and the read at --i1-mode 0, as at 1."""
    path = tmp_path / "flip.db"
    db = _file_db(path)
    _example(db)
    withdraw(db, "packed", 29, 0, reason="i1_dropped")
    db.eng.dispose()
    assert main(["--db", str(path), "--since", SINCE, "--as-of", _after(20),
                 "--i1-mode", "0"]) == 1
    out = capsys.readouterr().out
    assert "trade_i1_mode 0 | disposition_cut=1, i1_dropped=1 | i1_dropped 0 | FAIL |" in out
    assert "any i1_dropped at trade_i1_mode 0 is a bug (barred at 0)" in out
    assert "OVERALL: FAIL" in out


def test_the_cli_settles_as_of_behind_the_clock(tmp_path, capsys, monkeypatch):
    """#431 QA P3: delivered_at is stamped off the request thread, so near
    now an outcome can commit before its card's stamp, and a live deck reads
    incomplete_deck (a transient G2 FAIL). The CLI's as_of is at most the
    clock minus STAMP_SETTLE: that by default, and a later --as-of is clamped
    to it with a note giving both values. flip_read() takes as_of as given."""
    clock = datetime.fromisoformat(_after(3))
    settled = (clock - timedelta(minutes=5)).isoformat()
    assert fr.STAMP_SETTLE == timedelta(minutes=5)
    monkeypatch.setattr(fr, "_now", lambda: clock)
    path = tmp_path / "flip.db"
    db = _file_db(path)
    put_deck(db, "vc", 10, delivered=range(5), extra={"page_store": 1})
    act(db, "vc", 7, "viewed", at=(clock - timedelta(minutes=2)).isoformat())   # stamp not landed
    raw = flip_read(db.eng, since=SINCE, as_of=clock.isoformat())                # un-clamped
    assert raw.as_of == clock.isoformat() and raw.g2["ids"] == [["vc", SERVED]]
    db.eng.dispose()
    args = ["--db", str(path), "--since", SINCE, "--json"]

    assert main(args) == 3                               # default: the clock minus 5 min
    out, err = capsys.readouterr()
    got = json.loads(out)
    assert got["as_of"] == settled and got["g2"]["status"] == PASS and err == ""

    assert main(args + ["--as-of", clock.isoformat()]) == 3      # later: clamped, noted
    out, err = capsys.readouterr()
    assert json.loads(out)["as_of"] == settled
    assert err == (f"flip_read: note: --as-of {clock.isoformat()} is later than now minus "
                   f"STAMP_SETTLE (5 min); clamped to {settled}\n")

    assert main(args + ["--as-of", _after(2)]) == 3              # earlier: as given
    out, err = capsys.readouterr()
    assert json.loads(out)["as_of"] == _after(2) and err == ""

    main(args + ["--as-of", clock.isoformat(), "--weekly"])     # #432 QA P3: the weekly
    assert json.loads(capsys.readouterr().out)["weekly"]["as_of"] == settled   # window too


def test_a_read_only_violation_inside_the_read_exits_2(tmp_path, capsys, monkeypatch):
    """The statement guard firing mid-read is exit 2, as a refused database
    is, and nothing goes to stdout."""
    path = tmp_path / "flip.db"
    _file_db(path).eng.dispose()
    before = path.read_bytes()

    def writes(engine, **_kw):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM deck_outcomes"))

    monkeypatch.setattr(fr, "load_decks", writes)
    assert main(["--db", str(path), "--since", SINCE, "--as-of", EARLY]) == 2
    out, err = capsys.readouterr()
    assert out == "" and "blocked a non-read statement" in err
    assert path.read_bytes() == before


def test_an_unexpected_error_inside_the_read_exits_4(tmp_path, capsys, monkeypatch):
    """#431 QA P3: a crash is exit 4 with its traceback on stderr, never 0
    and never FAIL's 1."""
    path = tmp_path / "flip.db"
    _file_db(path).eng.dispose()

    def boom(engine, **_kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(fr, "load_decks", boom)
    assert main(["--db", str(path), "--since", SINCE, "--as-of", EARLY]) == 4
    out, err = capsys.readouterr()
    assert out == "" and "Traceback (most recent call last)" in err
    assert "RuntimeError: boom" in err


def test_a_crash_never_echoes_the_database_credentials(capsys, monkeypatch):
    """#432 QA P3: a password with an unencoded '@' comes back from libpq as
    part of a "host" (could not translate host name "RET123@…"). The exit-4
    traceback redacts every credential and host piece of --db."""
    db = "postgresql://ftf:SEC@RET123@192.0.2.1:5432/ftf"

    def refused(url, **_kw):
        raise RuntimeError('could not translate host name "RET123@192.0.2.1" to address')

    monkeypatch.setattr(fr, "read_only_engine", refused)
    assert main(["--db", db, "--allow-postgres-readonly", "--since", SINCE,
                 "--as-of", EARLY]) == 4
    out, err = capsys.readouterr()
    assert out == "" and "Traceback (most recent call last)" in err
    assert "***" in err
    for secret in ("SEC", "RET123", "192.0.2.1"):
        assert secret not in err


def _crash_err(monkeypatch, capsys, db, message, *, exc=RuntimeError):
    """Run the CLI with --db `db` whose engine creation raises `exc(message)`;
    returns (exit status, stderr)."""
    def boom(url, **_kw):
        raise exc(message)

    monkeypatch.setattr(fr, "read_only_engine", boom)
    status = main(["--db", db, "--allow-postgres-readonly", "--since", SINCE,
                   "--as-of", EARLY])
    out, err = capsys.readouterr()
    assert out == ""
    return status, err


@pytest.mark.parametrize("db, message, exc, status, secrets", [
    # exit 2: SQLAlchemy reads an unencoded password's tail as the port
    ("postgresql://u:Tr0ub4dor@x:9k2LmQ@dpg-host.invalid/ftf",
     "invalid literal for int() with base 10: '9k2LmQ@dpg-host.invalid'", ValueError, 2,
     ("Tr0ub4dor", "9k2LmQ", "dpg-host.invalid")),
    # a query-string password with an unencoded '&'
    ("postgresql://u@dpg-host.invalid/ftf?password=S3cr&et=x",
     'invalid connection option "et" (S3cr)', RuntimeError, 4, ("S3cr", "dpg-host.invalid")),
    # a '?' in an unencoded password must not cut the host off the redaction
    ("postgresql://u:ab?cdefg@host.invalid/ftf",
     'could not translate host name "host.invalid" (cdefg)', RuntimeError, 4,
     ("host.invalid", "cdefg")),
    # a percent-encoded username comes back decoded
    ("postgresql://ops%40team:pw12345@h.invalid/main",
     'FATAL: password authentication failed for user "ops@team"', RuntimeError, 4,
     ("ops@team", "pw12345")),
    # a 3-character piece is redacted (the minimum)
    ("postgresql://u:abc@h.invalid/ftf", "auth failed: abc", RuntimeError, 4, ("abc",)),
    # longest first: a username inside the password leaves no tail behind
    ("postgresql://sec:secret99@h.invalid/ftf", "bad password secret99", RuntimeError, 4,
     ("secret99", "ret99")),
    # libpq splits a host list on ',': each host is redacted
    ("postgresql://u:x9k@hostA.invalid,hostB.invalid/main",
     'could not translate host name "hostB.invalid" to address', RuntimeError, 4,
     ("hostB.invalid", "hostA.invalid")),
    # a '#' in an unencoded password
    ("postgresql://u:pa#ss123@h.invalid/main",
     'could not translate host name "ss123@h.invalid"', RuntimeError, 4, ("ss123",)),
    # a '+' in a query value comes back as a space
    ("postgresql://u@h.invalid/main?password=a+b+c1234",
     "authentication failed: a b c1234", RuntimeError, 4, ("a b c1234", "c1234")),
], ids=["exit2_port", "query", "question_mark", "decoded_user", "three_chars",
        "longest_first", "host_list", "hash", "plus"])
def test_no_exit_path_echoes_database_credentials(monkeypatch, capsys, db, message, exc,
                                                   status, secrets):
    """#435 QA P3: every exit path (2 and 4) redacts every 3+ character piece of
    --db, split on ':@/?&=#' and percent-decoded, longest first."""
    got, err = _crash_err(monkeypatch, capsys, db, message, exc=exc)
    assert got == status and "***" in err
    for secret in secrets:
        assert secret not in err


def test_two_character_pieces_are_left(monkeypatch, capsys):
    """The lower bound: pieces under 3 characters are not redacted (they would
    redact noise), and everything longer is."""
    got, err = _crash_err(monkeypatch, capsys, "postgresql://ab:pw9k3@h.invalid/main",
                          "auth for ab failed: pw9k3")
    assert got == 4 and "auth for ab failed: ***" in err


def test_a_read_only_violation_message_is_redacted(monkeypatch, capsys):
    """Exit 2 from a ReadOnlyViolation mid-read is redacted like a crash."""
    class _Engine:
        def dispose(self):
            pass

    def blocked(engine, **_kw):
        raise fr.ReadOnlyViolation("blocked a non-read statement: 'SET pw = PWsecret9'")

    monkeypatch.setattr(fr, "read_only_engine", lambda url, **_kw: _Engine())
    monkeypatch.setattr(fr, "flip_read", blocked)
    assert main(["--db", "postgresql://u:PWsecret9@h.invalid/main",
                 "--allow-postgres-readonly", "--since", SINCE, "--as-of", EARLY]) == 2
    out, err = capsys.readouterr()
    assert out == "" and "PWsecret9" not in err and "***" in err


def test_a_usage_error_never_prints_a_database_url(capsys):
    """argparse's usage errors are exit 2 too: a URL passed by mistake (here a
    stray positional) is redacted."""
    with pytest.raises(SystemExit) as usage:
        main(["--db", "unused.db", "--since", SINCE,
              "postgresql://u:PW12345@h.invalid/main"])
    assert usage.value.code == 2
    err = capsys.readouterr().err
    assert "unrecognized arguments" in err and "PW12345" not in err and "***" in err


def test_a_sqlite_url_is_not_redacted(monkeypatch, capsys):
    """A SQLite URL carries no credentials: crash output keeps its paths."""
    got, err = _crash_err(monkeypatch, capsys, "sqlite:///backend/eval/flip.db",
                          "unable to open backend/eval/flip.db")
    assert got == 4 and "***" not in err and "backend/eval/flip.db" in err


@pytest.mark.parametrize("flag, value, why", [
    ("--since", "2026-10-23T25:00:00Z", "not an ISO 8601 time"),
    ("--until", "tomorrow", "not an ISO 8601 time"),
    ("--as-of", "2026-13-01", "not an ISO 8601 time"),
    ("--as-of", "0001-01-01T00:00:00+01:00",        # valid, but out of range in UTC
     "out of range for the read (it reaches back 9 days)"),
    ("--as-of", "0001-01-01T00:00:00Z",             # in range, but the window can't reach back
     "out of range for the read (it reaches back 9 days)"),
])
def test_a_malformed_time_is_a_usage_error(flag, value, why, capsys):
    """#431 QA P3: --since, --until and --as-of are parsed as ISO 8601 by
    argparse, so a malformed one is usage exit 2, not a traceback."""
    args = {"--db": "unused.db", "--since": SINCE, flag: value}
    with pytest.raises(SystemExit) as usage:
        main([part for pair in args.items() for part in pair])
    assert usage.value.code == 2
    err = capsys.readouterr().err
    assert f"argument {flag}: {why}: {value!r}" in err
    assert "Traceback" not in err


def test_help_documents_the_exit_codes(capsys):
    with pytest.raises(SystemExit) as done:
        main(["--help"])
    assert done.value.code == 0
    out = capsys.readouterr().out
    assert "--i1-mode" in out and "Exit status:" in out
    for line in ("0  PASS", "1  FAIL, or a weekly ceiling OVER", "2  a refused database or a "
                 "ReadOnlyViolation", "3  INSUFFICIENT", "4  an unexpected error"):
        assert line in out


def test_a_non_sqlite_database_is_refused_without_the_flag(capsys):
    url = "postgresql://reader:hunter2@db.invalid/ftf"
    assert main(["--db", url, "--since", SINCE]) == 2
    err = capsys.readouterr().err
    assert "--allow-postgres-readonly" in err and "hunter2" not in err
    with pytest.raises(ValueError, match="allow-postgres-readonly"):
        read_only_engine(url)
    with pytest.raises(ValueError, match="only a SQLite or a Postgres"):
        read_only_engine("mysql://reader@db.invalid/ftf", allow_postgres_readonly=True)


class _FakePG:
    """A DBAPI connection answering SHOW transaction_read_only."""

    def __init__(self, state):
        self.state, self.sql, self.commits = state, [], 0

    def cursor(self):
        conn = self

        class _Cursor:
            def execute(self, sql):
                conn.sql.append(sql)

            def fetchone(self):
                return (conn.state,)

            def close(self):
                pass
        return _Cursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def test_the_postgres_engine_opens_every_connection_read_only_with_a_timeout(monkeypatch):
    """#425 QA P3: pins the startup options every pooled connection opens
    with. Nothing at runtime notices a dropped statement_timeout, and the
    session SET masks a dropped read-only default."""
    seen = {}
    real = fr.create_engine

    def spy(url, **kw):
        seen.update(kw)
        return real(url, **kw)

    monkeypatch.setattr(fr, "create_engine", spy)
    read_only_engine("postgres://reader:pw@db.invalid/ftf", allow_postgres_readonly=True).dispose()
    options = seen["connect_args"]["options"]
    assert "-c statement_timeout=120s" in options
    assert "-c default_transaction_read_only=on" in options


def test_with_the_flag_every_postgres_session_must_prove_it_is_read_only():
    eng = read_only_engine("postgres://reader:pw@db.invalid/ftf", allow_postgres_readonly=True)
    try:
        assert eng.dialect.name == "postgresql"          # no connection is made here
        assert event.contains(eng, "connect", fr._read_only_session)
        assert event.contains(eng, "before_cursor_execute", fr._reads_only)
    finally:
        eng.dispose()
    ok = _FakePG("on")
    fr._read_only_session(ok, None)
    assert ok.sql == ["SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY",
                      "SHOW transaction_read_only"] and ok.commits == 1
    with pytest.raises(ReadOnlyViolation, match="transaction_read_only is not on"):
        fr._read_only_session(_FakePG("off"), None)


@pytest.mark.parametrize("statement, allowed", [
    ("SELECT 1", True), ("  (SELECT 1)", True), ("WITH x AS (SELECT 1) SELECT * FROM x", True),
    ("PRAGMA main.table_info('deck_outcomes')", True), ("SHOW transaction_read_only", True),
    ("DELETE FROM deck_outcomes", False), ("INSERT INTO x VALUES (1)", False),
    ("SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE", False), ("", False),
])
def test_the_statement_guard_lets_only_reads_through(statement, allowed):
    if allowed:
        fr._reads_only(None, None, statement, None, None, False)
    else:
        with pytest.raises(ReadOnlyViolation):
            fr._reads_only(None, None, statement, None, None, False)


def test_importing_flip_read_never_imports_the_server():
    code = "import sys, backend.eval.flip_read; print('backend.server' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True,
                         text=True, check=True)
    assert out.stdout.strip() == "False"
