"""U4 as models-lead ruled it (addendum C, 2026-10-26): evicted_split and
option A, with their conditions.

- (c1) Both named causes need the card at or past the deck's effective stored
  count (option A: its current page row's count, else 0). A miss below it is
  other, whatever the provenance.
- (c2) "This process evicted (or built) deck J" is kept at least the 24 h
  display cap: the ledgers trim by age, and their count cap is a memory guard
  that warns when it trims a younger entry.
- (d3) The pack's recorded stored_count is never rewritten: the store-miss
  writer and the CAS merge only fill it when absent.

Harness: test_packed_evidence's (the `deferred` fixture, real routes and
evidence writes inline) and the ledgers with a replaced clock.
"""
import collections
import pytest

import backend.server as server
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import p1, set_row, status  # noqa: F401  (fixture)
from backend.tests.test_deferred_evidence import deferred  # noqa: F401  (fixture)
from backend.tests.test_packed_evidence import (
    deck_ids, delivered_before_completion, evict, pack_of, packed_deck, restart, unpack, view)

DAY = 24 * 3600


def run_of(engine, job_id):
    return unpack(pack_of(engine, job_id))[0]


def delivered_to_119(client, job_id):
    for cursor in (0, 30, 60, 90):
        assert deck_ids(status(client, job_id, cursor).get_json())


class Clock:
    """The ledgers' clock, moved by hand."""

    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture()
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(server, "_ledger_now", c)
    monkeypatch.setattr(server, "_ledger_guard_young", 0)          # the warning's rate limit
    monkeypatch.setattr(server, "_ledger_guard_warned_at", float("-inf"))
    return c


def test_both_rulings_are_on_by_default():
    """Addendum C: evicted_split named (C1) and option A (C4), both on before
    the flip. The off paths stay covered by tests that set them off."""
    assert server._EVICTED_SPLIT_NAMED is True
    assert server._STORED_COUNT_FROM_ROW_NOW is True


# ── (c1) the index test comes first ─────────────────────────────────────────

@pytest.mark.parametrize("cause", ["restart_split", "evicted_split"])
@pytest.mark.parametrize("row_count, named", [(96, False), (95, True), (90, True)])
def test_c1_a_named_cause_needs_the_card_at_or_past_the_effective_count(
        deferred, monkeypatch, cause, row_count, named):
    """Option A on, evicted_split named. Card 95, delivered, has no snapshot
    left (its deck stored 90). The deck's current row says `row_count` cards:
    below that count the miss is other, whatever the provenance (a restart, or
    this process's eviction); at or past it, the named cause."""
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_STORED_COUNT_FROM_ROW_NOW", True)
    monkeypatch.setattr(server, "_EVICTED_SPLIT_NAMED", True)
    job_id, *_ = packed_deck(120)
    delivered_to_119(client, job_id)
    set_row(engine, card_count=row_count)
    if cause == "restart_split":
        restart()
    else:
        evict(monkeypatch, job_id)
    view(job_id, 95)
    assert run_of(engine, job_id)["upgrade_miss_cards"] == {"95": cause if named else "other"}


# ── (c2) the ledgers keep 24 h ──────────────────────────────────────────────

def test_c2_a_mass_age_trim_is_linear(clock):
    """#451 QA P2-1: a ledger idle for 24 h, then one add, trims every entry at
    once. The ledgers are OrderedDicts, so each trim is O(1): a full guard of
    aged entries goes in well under a second (a plain dict rescans its deleted
    front slots: O(n²), ~12 s at the guard, under the locks)."""
    import time as _time
    assert isinstance(server._deck_held, collections.OrderedDict)
    assert isinstance(server._deck_evicted_at, collections.OrderedDict)
    ledger = type(server._deck_evicted_at)()
    for i in range(server._DECK_LEDGER_GUARD - 1):
        ledger[f"old-{i}"] = clock.t
    clock.t += DAY
    started = _time.perf_counter()
    server._ledger_add(ledger, "new")
    assert _time.perf_counter() - started < 2.0
    assert list(ledger) == ["new"]


def test_c2_an_evicted_deck_leaves_the_held_ledger(clock, monkeypatch):
    """#451 QA P3-1: eviction drops the deck's held entry, so once its eviction
    record ages out a late view reads restart_split (C (c2)), never other."""
    from types import SimpleNamespace
    monkeypatch.setattr(server, "_deck_held", collections.OrderedDict())
    monkeypatch.setattr(server, "_deck_evicted_at", collections.OrderedDict())
    job = {"evidence": SimpleNamespace(packed=True, pack=object())}
    server._note_deck_held("deck-a")
    server._note_deck_evicted("deck-a", job)
    assert "deck-a" not in server._deck_held and "deck-a" in server._deck_evicted_at
    assert server._upgrade_miss_cause("deck-a", 95, 90, True) == "evicted_split"
    clock.t += DAY + 1
    server._note_deck_evicted("deck-b", job)               # ages deck-a's record out
    assert "deck-a" not in server._deck_evicted_at
    assert server._upgrade_miss_cause("deck-a", 95, 90, True) == "restart_split"


def test_c2_the_guard_warning_is_rate_limited(clock, monkeypatch, caplog):
    """#451 QA P3-2: at the guard every add trims a young entry; the warning
    fires at most once a minute, with the count since the last one."""
    monkeypatch.setattr(server, "_DECK_LEDGER_GUARD", 2)
    ledger = collections.OrderedDict()
    with caplog.at_level("WARNING"):
        for i in range(50):                                # 48 young trims over 5 s
            server._ledger_add(ledger, f"d{i}")
            clock.t += 0.1
    assert caplog.text.count("ledger guard") == 1
    caplog.clear()
    clock.t += 60
    with caplog.at_level("WARNING"):
        server._ledger_add(ledger, "late")
    assert caplog.text.count("ledger guard") == 1 and "trimmed 48 entries younger" in caplog.text


def test_c2_an_entry_younger_than_24h_survives_adds_past_the_old_cap(clock):
    """20,000 adds over 5.5 h, past the old FIFO's 16,384: the first entry
    stays (it is younger than 24 h), and nothing is trimmed."""
    ledger = collections.OrderedDict()
    server._ledger_add(ledger, "evicted-first")
    for i in range(20000):
        clock.t += 1
        server._ledger_add(ledger, f"evicted-{i}")
    assert "evicted-first" in ledger and len(ledger) == 20001


def test_c2_an_entry_24h_old_is_trimmed_and_a_younger_one_kept(clock):
    ledger = collections.OrderedDict()
    server._ledger_add(ledger, "old")
    clock.t += DAY - 1
    server._ledger_add(ledger, "young")
    assert list(ledger) == ["old", "young"]                # 1 s short of 24 h: kept
    clock.t += 1
    server._ledger_add(ledger, "next")
    assert list(ledger) == ["young", "next"]               # 24 h old: trimmed


def test_c2_a_re_add_moves_the_entry_to_now(clock):
    ledger = collections.OrderedDict()
    server._ledger_add(ledger, "a")
    clock.t += DAY - 10
    server._ledger_add(ledger, "b")
    server._ledger_add(ledger, "a")                        # noted again: its age restarts
    clock.t += 20
    server._ledger_add(ledger, "c")
    assert list(ledger) == ["b", "a", "c"]


def test_c2_the_memory_guard_trims_the_oldest_and_warns_for_a_young_entry(
        clock, monkeypatch, caplog):
    monkeypatch.setattr(server, "_DECK_LEDGER_GUARD", 4)
    ledger = collections.OrderedDict()
    for i in range(4):
        server._ledger_add(ledger, f"d{i}")
        clock.t += 1
    with caplog.at_level("WARNING"):
        server._ledger_add(ledger, "d4")
    assert list(ledger) == ["d1", "d2", "d3", "d4"]
    assert "U4 ledger guard (4 entries) trimmed 1 entry younger than 24 h" in caplog.text
    caplog.clear()
    clock.t += DAY                                         # all of them 24 h old now
    with caplog.at_level("WARNING"):
        server._ledger_add(ledger, "d5")
    assert list(ledger) == ["d5"] and "ledger guard" not in caplog.text   # the age trim: silent


def test_c2_the_held_ledger_keeps_24h_too(clock, monkeypatch):
    """_deck_held has the same policy: a deck built here 20 h ago, with
    20,000 builds since, is still held (a live miss on it stays other, never a
    restart_split)."""
    monkeypatch.setattr(server, "_deck_held", collections.OrderedDict())
    server._note_deck_held("built-early")
    for i in range(20000):
        clock.t += 3.6                                     # 20 h in all
        server._note_deck_held(f"built-{i}")
    assert "built-early" in server._deck_held
    assert server._upgrade_miss_cause("built-early", 95, 90, True) == "other"


def test_c2_a_late_view_20h_after_the_eviction_is_still_evicted_split(
        deferred, monkeypatch, clock):
    """The deck's job is evicted here; 20,000 more evictions follow over 20 h
    (past the old 16,384 cap); then card 95 is viewed. The eviction is still on
    record: evicted_split, not restart_split."""
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_EVICTED_SPLIT_NAMED", True)
    job_id, *_ = packed_deck(120)
    delivered_to_119(client, job_id)
    evict(monkeypatch, job_id)
    for i in range(20000):
        clock.t += 3.6
        server._ledger_add(server._deck_evicted_at, f"another-deck-{i}")
    view(job_id, 95)
    assert run_of(engine, job_id)["upgrade_miss_cards"] == {"95": "evicted_split"}


# ── (d3) the recorded count is never rewritten ──────────────────────────────

def test_d3_a_store_miss_never_rewrites_a_recorded_count(deferred):
    """The pack's header already records 77; the store then writes no row.
    _deck_store_missed fills 0 only where the header has no count, so 77
    stays, in memory and in the store."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, complete=False, store=False)
    delivered_before_completion(client, job_id)
    ev = server._trade_jobs[job_id]["evidence"]
    with server._deck_evidence_write_lock:
        ev.pack.run["stored_count"] = 77
        assert server._deck_pack_commit(job_id, ev.pack)
    server._deck_store_missed(job_id)
    assert (ev.pack.run["stored_count"], run_of(engine, job_id)["stored_count"]) == (77, 77)


def test_d3_a_store_miss_fills_an_absent_count():
    """The other half: with no count in the header, the miss records 0."""
    # (pinned end to end by test_packed_evidence's test_store_count_zero_* and
    # test_replaced_page_rows' P3-3 tests; here the CAS merge's half)
    merged = server._merge_pack_runs({"stored_count": 90}, {"stored_count": 0}, {})
    assert merged["stored_count"] == 90                    # the stored header's count stands
    assert server._merge_pack_runs({}, {"stored_count": 0}, {})["stored_count"] == 0
