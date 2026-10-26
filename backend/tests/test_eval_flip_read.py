"""backend.eval.flip_read, the model-side 24 h read after the one-step 200 ms
flip (models-lead-launch.md §Gate-11-03 §3, addenda A3 and B3 (f3)): each
barred G passing and failing, G10's report, the two weekly ceilings (U4-R4,
B4) at, under and over, the read-only guard, and that the module never
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
from backend.tests.test_eval_pack_reader import SERVED, _deck_cards, pack_table, write_deck
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
        assert "| G1 | pack_integrity decks / decks with a pack row | 1 / 3 | 0 | FAIL |" in text
        assert "models-lead recommends the kill" in text


# ---------------------------------------------------------------------------
# G2: incomplete decks among final decks only, and the 10-deck minimum
# ---------------------------------------------------------------------------

def test_g2_reads_only_final_decks():
    """2 h after serving, only the retired packs are final: an unretired pack
    is in flight, and a pack-less deck with a gap (incomplete_deck to the
    loader) is not final yet. 30 h after, every deck is."""
    db = make_db()
    _packed(db, "retired_gap", cards=9, retired=True, retired_at=_after(1))   # lost card 9
    _packed(db, "retired_ok", retired=True, retired_at=_after(1))
    _packed(db, "live", deliveries=[[4, SERVED]], retired=False)
    put_deck(db, "rows_gap", 10, rows={*range(10)} - {4})
    put_deck(db, "refresh", 6, source="grading_refresh")              # not a Trades deck

    early = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert early.exclusions[IN_FLIGHT] == 1 and early.exclusions[INCOMPLETE_DECK] == 2
    assert early.g2["final_decks"] == 2 and early.g2["incomplete"] == 1
    assert early.g2["ids"] == [["retired_gap", SERVED]] and early.g2["status"] == FAIL
    assert early.g2["insufficient"] and early.overall == FAIL
    text = render(early)
    assert "G2 INSUFFICIENT (<10 final decks): extend to 48 h" in text
    assert f"retired_gap (served {SERVED})" in text

    late = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert late.exclusions[CALIBRATION_REFRESH] == 1
    assert late.g2["final_decks"] == 4 and late.g2["incomplete"] == 2
    assert late.g2["ids"] == [["retired_gap", SERVED], ["rows_gap", SERVED]]


@pytest.mark.parametrize("n", [9, 10])
def test_g2_says_insufficient_below_ten_final_decks(n):
    """A retired pack is final at once; a pack-less deck 25 h after serving."""
    db = make_db()
    for k in range(n):
        _packed(db, f"r{k}", retired=True, retired_at=_after(1))
        put_deck(db, f"d{k}", 4)
    early = flip_read(db.eng, since=SINCE, as_of=EARLY)
    assert early.g2["final_decks"] == n and early.g2["insufficient"] == (n < 10)
    assert early.g2["status"] == PASS and early.overall == (INSUFFICIENT if n < 10 else PASS)
    assert ("INSUFFICIENT (<10 final decks): extend to 48 h" in render(early)) == (n < 10)
    late = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert late.g2["final_decks"] == 2 * n and not late.g2["insufficient"]


# ---------------------------------------------------------------------------
# G3: every outcome in the window joins a card, row or packed
# ---------------------------------------------------------------------------

def _joins_db() -> DB:
    """j: rows 0-4 and a pack of 5-9, viewed at 2 (a row) and 7 (left
    packed); old: served before the window, viewed in it at 1 (a row) and 8
    (packed); a ghost row's outcome."""
    db = make_db()
    write_deck(db.eng, db.packs, _deck_cards("j", 10), full=range(5), packed=range(5, 10),
               viewed=[2, 7])
    write_deck(db.eng, db.packs, _deck_cards("old", 10, served_at=BEFORE), full=range(5),
               packed=range(5, 10), served_at=BEFORE)
    act(db, "old", 1, "viewed")
    act(db, "old", 8, "viewed")
    _post(db, "j:3:ghost")
    return db


def test_g3_passes_when_every_outcome_joins():
    r = flip_read(_joins_db().eng, since=SINCE, as_of=LATE)
    assert r.g3 == {"outcomes": 5, "joined": 2, "joined_outside_window": 2, "ghost": 1,
                    "orphans": 0, "ids": [], "status": PASS}


@pytest.mark.parametrize("impression_id", [
    "j:12",                 # its deck is in the window; the card is not
    "old:15",               # past the older deck's card_count
    "nowhere:0",            # no row, no pack
    "legacy-uuid-1",        # not a contract id, and no row
])
def test_g3_fails_on_an_outcome_joining_no_card(impression_id):
    db = _joins_db()
    _post(db, impression_id, action="like")
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert r.g3["orphans"] == 1 and r.g3["ids"] == [impression_id]
    assert r.g3["status"] == FAIL and r.overall == FAIL
    assert f"G3 outcomes joining no card: {impression_id}" in render(r)


def test_g3_reads_only_outcomes_in_the_window_and_by_as_of():
    db = _joins_db()
    _post(db, "nowhere:0", at=BEFORE)          # before the window
    _post(db, "nowhere:1", at=_after(31))      # after as_of
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert r.g3["outcomes"] == 5 and r.g3["status"] == PASS


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
    causes = ", ".join(f"{k}={v}" for k, v in sorted(total.items()))
    assert f"| G7 | upgrade misses by cause | {causes} | other 0 | {status} |" in render(r)


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


def test_g10_reports_withdrawals_by_reason_in_the_window():
    db = make_db()
    withdraw(db, "a", 1, 0, reason="disposition_cut")
    withdraw(db, "a", 2, 1, reason="disposition_cut")
    withdraw(db, "b", 0, 0, reason="i1_dropped")
    withdraw(db, "c", 0, 0, reason="disposition_cut", at=BEFORE)        # before the window
    withdraw(db, "d", 0, 0, reason="i1_dropped", at=_after(31))         # after as_of
    r = flip_read(db.eng, since=SINCE, as_of=LATE)
    assert r.g10["by_reason"] == {"disposition_cut": 2, "i1_dropped": 1}
    assert r.g10["status"] == REPORT
    assert r.overall == INSUFFICIENT                 # G10 is never barred; no final decks here
    text = render(r)
    assert ("| G10 | withdrawals by reason (window) | disposition_cut=2, i1_dropped=1 "
            "| reported | REPORT |") in text
    assert "disposition_cut > 0 expected; any i1_dropped at mode 1 is a bug" in text
    assert flip_read(db.eng, since=SINCE, as_of=LATE, until=SERVED).g10["by_reason"] == {}


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
    _packed(db, "p", upgrade_misses={**named, "other": 3})
    _packed(db, "old", served_at="2026-10-16T12:00:00+00:00",
            upgrade_misses={"restart_split": 9})
    w = weekly_read(db.eng, as_of=LATE)
    u = w["u4_r4"]
    assert (u["numerator"], u["denominator"]) == (sum(named.values()), 100)
    assert u["causes"] == dict(sorted(named.items())) and u["status"] == status
    assert u["ceiling"] == fr.U4_R4_CEILING == 0.01 and fr.U4_R4_CAUSES is None


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
    assert main(args) == 0                                         # INSUFFICIENT is not a FAIL
    out = capsys.readouterr().out
    assert "| G1 | pack_integrity decks / decks with a pack row | 0 / 2 | 0 | PASS |" in out
    assert "| G2 | incomplete_deck / final Trades decks | 0 / 1 | 0 | PASS |" in out
    assert "| G3 | outcomes joining no card | 0 of 7" in out
    assert "OVERALL: INSUFFICIENT" in out and "U4-R4" not in out

    # 1 restart split over 7 viewed cards is over 1%: OVER exits 1.
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
