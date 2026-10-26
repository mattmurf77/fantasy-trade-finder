"""A deck whose page row is gone: option A, run["upgrade_miss_row_gone"], and
#438 QA's stored-count fixes.

The page store holds one row per (user, league, format, scope): a newer deck's
store replaces it, and evict_trade_pages deletes it. Once the deck's job has
left the process, a card it stored has no snapshot left then.

- server._STORED_COUNT_FROM_ROW_NOW (option A; head-eng recommends it,
  models-lead rules on it; off until then). Off, today: the deck's stored
  count is the one its pack recorded, so a delivered card under it reads
  other. On: the count is what the page store holds now, 0 with no row, so the
  card reads restart_split after a restart (evicted_split after an eviction).
- head-eng's condition 1: either way the writer records the card in
  run["upgrade_miss_row_gone"] = {"<card_index>": the recorded count}, in the
  miss-map entry's commit and only when that entry is new. A raising commit
  takes both back; the CAS merge unions it (the stored entry wins). Every key
  in it is a miss-map key (models-eng's flip_read joins them).
- head-eng's condition 2: a deck still held here upgrades from its job's
  snapshot whatever its row did.
- #438 QA: a pack first written on the stored path records the row's count
  (P2-1); the miss line names its count's source and the fallback warns
  (P3-1); a refused store never lets a delivery pack its count (P3-2);
  _deck_store_missed's lock, failure handling and kill-knob path (P3-3).

Harness: test_packed_evidence's (the `deferred` fixture, real routes and
evidence writes inline).
"""
import json
import time
from datetime import datetime, timezone

import pytest

import backend.database as db_module
import backend.server as server
from backend.eval import contract
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import (  # noqa: F401  (fixture)
    HEADERS, PAGES, _row, p1, set_row, status, stored)
from backend.tests.test_deferred_evidence import UID, deferred, rows  # noqa: F401  (fixture)
from backend.tests.test_packed_evidence import (
    NO_MISSES, deck_ids, delivered_before_completion, evict, fail_after, pack_of, packed_deck,
    restart, unpack, view)


def run_of(engine, job_id):
    return unpack(pack_of(engine, job_id))[0]


def row_gone(run):
    return run.get("upgrade_miss_row_gone", {})


def assert_joined(run):
    """models-eng's join: every row-gone key is a miss-map key."""
    assert set(row_gone(run)) <= set(run["upgrade_miss_cards"])


def row_of(engine, job_id, index):
    [got] = [r for r in rows(engine)
             if r["deck_job_id"] == job_id and r["card_index"] == index and not r["is_ghost"]]
    return got


def delivered(client, job_id, *cursors):
    for cursor in cursors or (0, 30):
        assert deck_ids(status(client, job_id, cursor).get_json())


def a_newer_deck_replaces(job_id):
    """Deck B, a newer deck for A's scope, built and stored: its row replaces A's."""
    other = next(f"deck-{i:04d}" for i in range(100000) if f"deck-{i:04d}" != job_id
                 and not contract.is_archive_deck(f"deck-{i:04d}"))
    packed_deck(120, job_id=other, force_fresh=True)
    assert stored()["deck_job_id"] == other


def the_row_goes(job_id, how):
    if how == "replaced":
        a_newer_deck_replaces(job_id)
    else:
        assert db_module.evict_trade_pages(evict_days=30, max_bytes=0) == (0, 1)
    assert db_module.load_trade_page_for_job(UID, job_id) is None


def miss_lines(caplog):
    return [r.getMessage() for r in caplog.records if "upgrade miss cause=" in r.getMessage()]


# ── Option A, and the row-gone record ───────────────────────────────────────

@pytest.mark.parametrize("row_now", [False, True])
@pytest.mark.parametrize("how", ["replaced", "evicted"])
def test_a_delivered_card_whose_row_is_gone_after_a_restart(deferred, monkeypatch, how, row_now):
    """Card 40 (delivered on page 2, under the recorded 90) is viewed after a
    restart, its deck's row replaced by a newer deck's or evicted. Off: other
    (the pack's 90). On: restart_split (no row now, 0). Recorded in row_gone
    either way, with the recorded count."""
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_STORED_COUNT_FROM_ROW_NOW", row_now)
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    assert run_of(engine, job_id)["stored_count"] == PAGES == 90
    the_row_goes(job_id, how)
    restart()
    view(job_id, 40)
    run = run_of(engine, job_id)
    assert run["upgrade_miss_cards"] == {"40": "restart_split" if row_now else "other"}
    assert run["upgrade_misses"] == {**NO_MISSES, run["upgrade_miss_cards"]["40"]: 1}
    assert row_gone(run) == {"40": 90}
    assert_joined(run)
    got = row_of(engine, job_id, 40)
    assert got["evidence_tier"] == "viewed" and got["assets_json"] is None


def test_with_a_on_a_card_whose_row_is_gone_after_its_jobs_eviction_is_evicted_split(
        deferred, monkeypatch):
    """The same in process, after the cleanup loop evicted the deck's job (the
    cause named): evicted_split, recorded in row_gone."""
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_STORED_COUNT_FROM_ROW_NOW", True)
    monkeypatch.setattr(server, "_EVICTED_SPLIT_NAMED", True)
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    the_row_goes(job_id, "replaced")
    evict(monkeypatch, job_id)
    view(job_id, 40)
    run = run_of(engine, job_id)
    assert (run["upgrade_miss_cards"], row_gone(run)) == ({"40": "evicted_split"}, {"40": 90})


@pytest.mark.parametrize("row_now", [False, True])
def test_a_card_at_or_past_the_recorded_count_is_never_row_gone(deferred, monkeypatch, row_now):
    """Cards 90 (the boundary) and 95, past the recorded 90, had no stored
    snapshot to lose: restart_split both ways, and not in row_gone."""
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_STORED_COUNT_FROM_ROW_NOW", row_now)
    job_id, *_ = packed_deck(120)
    delivered(client, job_id, 0, 30, 60, 90)
    the_row_goes(job_id, "replaced")
    restart()
    view(job_id, 90)
    view(job_id, 95)
    run = run_of(engine, job_id)
    assert run["upgrade_miss_cards"] == {"90": "restart_split", "95": "restart_split"}
    assert row_gone(run) == {}


@pytest.mark.parametrize("row_now", [False, True])
@pytest.mark.parametrize("row_count, pack_count, cause", [
    (100, 90, "other"), (90, 100, "restart_split")])
def test_a_row_still_present_counts_by_its_card_count(deferred, monkeypatch, caplog, row_now,
                                                      row_count, pack_count, cause):
    """The deck's row is still there, its card_count and the pack's recorded
    count set apart here: either way the count is the row's, so card 95 reads
    other under a row of 100 and restart_split under a row of 90 (whatever the
    pack says), and nothing is row_gone (the row isn't gone)."""
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_STORED_COUNT_FROM_ROW_NOW", row_now)
    job_id, *_ = packed_deck(120)
    delivered(client, job_id, 0, 30, 60, 90)
    set_row(engine, card_count=row_count)
    ev = server._trade_jobs[job_id]["evidence"]
    with server._deck_evidence_write_lock:
        ev.pack.run["stored_count"] = pack_count
        assert server._deck_pack_commit(job_id, ev.pack)
    restart()
    with caplog.at_level("WARNING"):
        view(job_id, 95)
    run = run_of(engine, job_id)
    assert (run["upgrade_miss_cards"], row_gone(run)) == ({"95": cause}, {})
    [line] = miss_lines(caplog)
    assert f"index=95 stored={row_count} stored_from=row " in line


def test_condition_2_a_held_decks_replaced_row_upgrades_from_its_jobs_snapshot(deferred):
    """head-eng's condition 2: deck A is stored, then a newer deck B for the
    same scope replaces A's row while A's job is still held here. A's
    delivered card 40 is viewed: a full row from the job's snapshot (assets
    present), no miss, nothing counted, nothing row_gone."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    the_row_goes(job_id, "replaced")
    assert server._trade_jobs[job_id]["evidence"] is not None     # A's job, still held
    view(job_id, 40)
    got = row_of(engine, job_id, 40)
    assert got["evidence_tier"] == "viewed" and got["assets_json"]
    assert "give_value_band" in json.loads(got["features_json"])     # the wide row
    run = run_of(engine, job_id)
    assert (run["upgrade_miss_cards"], run["upgrade_misses"], row_gone(run)) == ({}, NO_MISSES, {})


# ── The record: once, with its map entry, and joined to it ──────────────────

def test_row_gone_is_written_only_with_a_new_map_entry(deferred):
    """Card 40 first missed in process (a deck held here whose snapshot is
    gone: other, no row-gone), and its row save failed. After its row is
    replaced and a restart, the retry finds the card in the map: it writes the
    row only, so nothing is added to row_gone."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    ev = server._trade_jobs[job_id]["evidence"]
    with ev.lock:
        ev.rows.pop(contract.card_impression_id(job_id, 40))
    with fail_after(engine, "INSERT INTO DECK_IMPRESSIONS"):
        view(job_id, 40)
    assert run_of(engine, job_id)["upgrade_miss_cards"] == {"40": "other"}
    the_row_goes(job_id, "replaced")
    restart()
    view(job_id, 40)
    run = run_of(engine, job_id)
    assert (run["upgrade_miss_cards"], row_gone(run)) == ({"40": "other"}, {})
    assert row_of(engine, job_id, 40)["assets_json"] is None


def test_a_raising_commit_takes_the_row_gone_entry_back_with_its_map_entry(deferred):
    """The miss's header commit raises: the map entry and its row-gone entry go
    back together (ours only), in memory and in the store; the next miss
    commits its own pair, and no row-gone key is ever left without its card."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    the_row_goes(job_id, "replaced")
    restart()
    with fail_after(engine, "UPDATE DECK_EVIDENCE_PACKS"):
        view(job_id, 40)
    state = server._deck_pack_states[job_id]
    assert (state.run["upgrade_miss_cards"], row_gone(state.run)) == ({}, {})
    assert (run_of(engine, job_id)["upgrade_miss_cards"], row_gone(run_of(engine, job_id))) == ({}, {})
    view(job_id, 41)
    run = run_of(engine, job_id)
    assert (run["upgrade_miss_cards"], row_gone(run)) == ({"41": "other"}, {"41": 90})
    assert_joined(run)


def test_two_writers_row_gone_entries_are_unioned_with_their_cards(deferred):
    """A deploy overlap: two processes, each holding the stored header, miss
    cards 40 and 41 with the row gone. The second commit misses the CAS and
    merges: both cards, both row-gone entries."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    the_row_goes(job_id, "replaced")
    restart()
    first = server._load_pack_state(job_id, UID)
    second = server._load_pack_state(job_id, UID)
    now = datetime.now(timezone.utc).isoformat()
    for state, index in ((first, 40), (second, 41)):
        with server._deck_evidence_write_lock:
            assert server._deck_upgrade_stored_locked(
                state, job_id, contract.card_impression_id(job_id, index), index, UID, now)
    run = run_of(engine, job_id)
    assert run["upgrade_miss_cards"] == {"40": "other", "41": "other"}
    assert run["upgrade_misses"] == {**NO_MISSES, "other": 2}
    assert row_gone(run) == {"40": 90, "41": 90}
    assert_joined(run)


def test_the_merge_unions_row_gone_the_stored_entry_winning():
    """The CAS merge: the union, a card in both keeping the stored entry; a
    run without the key reads as {}; a key without its card is dropped."""
    stored = {"upgrade_miss_cards": {"40": "other", "41": "other"},
              "upgrade_miss_row_gone": {"40": 90, "41": 90}}
    ours = {"upgrade_miss_cards": {"41": "restart_split", "50": "restart_split"},
            "upgrade_miss_row_gone": {"41": 88, "50": 90}}
    merged = server._merge_pack_runs(stored, ours, {})
    assert merged["upgrade_miss_row_gone"] == {"40": 90, "41": 90, "50": 90}
    assert_joined(merged)
    assert server._merge_pack_runs({"upgrade_miss_cards": {}}, {"upgrade_miss_cards": {}},
                                   {})["upgrade_miss_row_gone"] == {}
    assert server._upgrade_miss_row_gone({}) == {}
    orphan = server._merge_pack_runs({"upgrade_miss_cards": {}, "upgrade_miss_row_gone": {"40": 90}},
                                     {"upgrade_miss_cards": {"41": "other"},
                                      "upgrade_miss_row_gone": {"41": 90}}, {})
    assert orphan["upgrade_miss_row_gone"] == {"41": 90}


# ── #438 QA ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("row_now", [False, True])
@pytest.mark.parametrize("how", ["replaced", "evicted"])
def test_p2_1_a_pack_first_written_on_the_stored_path_records_the_rows_count(
        deferred, monkeypatch, how, row_now):
    """#438 QA P2-1: a pre-built deck of 90 cards (none truncated) is stored; a
    deploy restarts; its first pages are served from the stored row, so its
    pack is first written on the stored path, with the row's count. Then its
    row goes and card 40, still on the device, is viewed: off, other (never a
    restart_split from the fallback 0); on, restart_split. Recorded in
    row_gone either way."""
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_STORED_COUNT_FROM_ROW_NOW", row_now)
    job_id, *_ = packed_deck(90)
    assert pack_of(engine, job_id) is None                 # nothing delivered while its job ran
    restart()
    for cursor in (0, 30):
        page = client.get(f"/api/trades/status?deck={job_id}&cursor={cursor}", headers=HEADERS)
        assert deck_ids(page.get_json())
    assert run_of(engine, job_id)["stored_count"] == 90
    the_row_goes(job_id, how)
    restart()
    view(job_id, 40)
    run = run_of(engine, job_id)
    assert run["upgrade_miss_cards"] == {"40": "restart_split" if row_now else "other"}
    assert row_gone(run) == {"40": 90}


def test_p3_1_the_miss_line_names_its_stored_counts_source(deferred, monkeypatch, caplog):
    """#438 QA P3-1: stored_from= on the miss line: the job, the row, the pack,
    option A's no_row, or the fallback; the fallback on a page-scoped deck
    also warns (it stays a restart_split: the process dying between job_done
    and its store is the legitimate case)."""
    client, engine, _ = deferred
    seen = {}
    # job: held here, snapshot gone
    job_id, *_ = packed_deck(120)
    delivered(client, job_id, 0, 30, 60, 90)
    ev = server._trade_jobs[job_id]["evidence"]
    with ev.lock:
        ev.rows.pop(contract.card_impression_id(job_id, 95))
    with caplog.at_level("WARNING"):
        view(job_id, 95)                                   # job
        restart()
        view(job_id, 96)                                   # row (still present)
        the_row_goes(job_id, "evicted")
        restart()
        view(job_id, 40)                                   # pack (A off)
        monkeypatch.setattr(server, "_STORED_COUNT_FROM_ROW_NOW", True)
        view(job_id, 41)                                   # no_row (A on)
    for line in miss_lines(caplog):
        seen[line.split(" index=")[1].split()[0]] = line.split("stored_from=")[1].split()[0]
    assert seen == {"95": "job", "96": "row", "40": "pack", "41": "no_row"}
    assert "stored count fallback" not in caplog.text
    caplog.clear()
    monkeypatch.setattr(server, "_STORED_COUNT_FROM_ROW_NOW", False)   # on, it reads no_row
    other, *_ = packed_deck(120, complete=False, job_id="deck-p31-fallback")
    delivered_before_completion(client, other)             # the pack, no stored_count
    restart()                                              # died before its store
    with caplog.at_level("WARNING"):
        view(other, 40)
    [line] = miss_lines(caplog)
    assert "cause=restart_split" in line and "stored=0 stored_from=fallback " in line
    assert f"stored count fallback job={other} index=40" in caplog.text


def test_p3_2_a_refused_store_never_lets_a_first_delivery_pack_its_count(deferred, monkeypatch):
    """#438 QA P3-2: the store is refused (a newer deck's row holds the key), and
    _deck_store_missed's correction never lands (its CAS failed, the process
    died). A first delivery in between packs stored_count 0, never the
    refused store's 90, so card 40 after a restart is a restart_split."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, store=False)
    monkeypatch.setattr(server, "_deck_store_missed", lambda job_id: None)
    assert db_module.save_trade_page(_row(time.time() + 3600, "a-newer-deck"))
    assert server._store_trade_page(job_id) is False
    assert server._trade_jobs[job_id]["evidence"].stored_count == 0
    delivered(client, job_id)
    assert run_of(engine, job_id)["stored_count"] == 0
    restart()
    view(job_id, 40)
    assert run_of(engine, job_id)["upgrade_miss_cards"] == {"40": "restart_split"}


class _Owned:
    """The write lock (an RLock), recording how deep this test's thread holds it."""

    def __init__(self, lock):
        self.lock, self.depth = lock, 0

    def __enter__(self):
        self.lock.acquire()
        self.depth += 1
        return self

    def __exit__(self, *_exc):
        self.depth -= 1
        self.lock.release()


def test_p3_3_the_store_miss_writes_the_header_under_the_write_lock(deferred, monkeypatch):
    """#438 QA P3-3: _deck_store_missed takes _deck_evidence_write_lock itself
    (a delivery holds it), so its header write never interleaves one."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, complete=False, store=False)
    delivered_before_completion(client, job_id)            # the pack, no stored_count
    lock = _Owned(server._deck_evidence_write_lock)
    monkeypatch.setattr(server, "_deck_evidence_write_lock", lock)
    depths = []
    real = server._deck_pack_flush_header

    def flush(ev, *args, **kwargs):
        depths.append(lock.depth)
        return real(ev, *args, **kwargs)
    monkeypatch.setattr(server, "_deck_pack_flush_header", flush)
    server._deck_store_missed(job_id)
    assert depths == [1] and run_of(engine, job_id)["stored_count"] == 0


def test_p3_3_a_store_miss_never_raises_when_its_header_write_fails(deferred, monkeypatch, caplog):
    """#438 QA P3-3: the header write raises; _store_trade_page still returns
    False, never raising (the synchronous replenish path calls it on the cron
    tick), with the deck's count 0 and the failure logged."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, complete=False, store=False)
    delivered_before_completion(client, job_id)

    def boom(*_a, **_k):
        raise RuntimeError("injected: the header write fails")
    monkeypatch.setattr(server, "_deck_pack_flush_header", boom)
    assert db_module.save_trade_page(_row(time.time() + 3600, "a-newer-deck"))
    with caplog.at_level("WARNING"):
        assert server._store_trade_page(job_id) is False
    assert server._trade_jobs[job_id]["evidence"].stored_count == 0
    assert f"deck-evidence {job_id}: stored count 0 not yet in the pack" in caplog.text


def test_p3_3_the_kill_knob_records_stored_count_0(deferred, monkeypatch):
    """#438 QA P3-3: first_page_store_enabled 0 turns the store off, so the
    deck's stored count is 0, recorded in its pack (not the read's fallback),
    and card 40 after a restart is a restart_split."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, store=False)
    monkeypatch.setitem(server._trade_service_mod._cfg, "first_page_store_enabled", 0.0)
    assert server._store_trade_page(job_id) is False
    assert db_module.load_trade_page_for_job(UID, job_id) is None
    delivered(client, job_id)
    run = run_of(engine, job_id)
    assert (run["page_store"], run["stored_count"]) == (1, 0)
    restart()
    view(job_id, 40)
    assert run_of(engine, job_id)["upgrade_miss_cards"] == {"40": "restart_split"}
