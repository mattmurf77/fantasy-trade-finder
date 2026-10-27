"""Evidence cleanup before the packed-evidence flip.

- (A) F5 (_drop_stale_deck_evidence) drops an undelivered pre-built deck's
  evidence and notes the drop as this process's eviction (_deck_evicted_at,
  which also leaves _deck_held), so a later miss on it (its stored pages
  served, then its row gone) reads evicted_split, never other (models-lead's
  ruling via head-eng; release-lead's #451 QA P2 was restart_split).
- (B) A deploy overlap's second writer logs the cause the CAS merge kept,
  with its own as local_cause, at WARNING (#439/#445 QA P3-1).
- (C) The ledger guard warning per ledger; its rate-limit state reset per
  test (conftest.py); the store's double fault; the flip day's read-time
  normalizer and the series_break constant; the day span's league join.
- (D) Pins for #445 QA P3-3 and #454 QA P3-3.

Harness: test_packed_evidence's (the `deferred` fixture, real routes and
evidence writes inline).
"""
import collections
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import backend.database as db_module
import backend.receipts_service as rs
import backend.server as server
from backend.eval import contract
from backend.tests.test_i1_serve_filter import LEAGUE, live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import (  # noqa: F401  (fixture)
    HEADERS, SCOPE, _row, p1, status, stored)
from backend.tests.test_deferred_evidence import UID, deferred  # noqa: F401  (fixture)
from backend.tests.test_packed_evidence import (
    deck_ids, delivered_before_completion, fail_after, pack_of, packed_deck, restart, unpack,
    view)
from backend.tests.test_replaced_page_rows import _Owned, miss_lines, row_gone, the_row_goes

BACKEND = Path(__file__).resolve().parents[1]


def run_of(engine, job_id):
    return unpack(pack_of(engine, job_id))[0]


def delivered(client, job_id, *cursors):
    for cursor in cursors or (0, 30):
        assert deck_ids(status(client, job_id, cursor).get_json())


def errors(caplog):
    return [r.getMessage() for r in caplog.records
            if r.levelname == "ERROR" and "upgrade miss" in r.getMessage()]


def counting_reads(monkeypatch):
    calls = []
    real = db_module.load_trade_page_deck_job_id

    def read(*args):
        calls.append(args)
        return real(*args)
    monkeypatch.setattr(db_module, "load_trade_page_deck_job_id", read)
    return calls


# ── (A) F5's drop is this process's eviction ────────────────────────────────

@pytest.mark.parametrize("how", ["replaced", "evicted"])
@pytest.mark.parametrize("path", ["f5_only", "f5_then_job_evicted", "control_restart"])
def test_a_deck_f5_dropped_reads_evicted_split_once_its_row_goes(
        deferred, monkeypatch, caplog, how, path):
    """release-lead's #451 QA repro: a pre-built 90-card deck nobody opened in
    the fresh window. F5 drops its evidence and revokes its job, noting the
    drop in _deck_evicted_at (then, 4 h on, the loop evicts the job, which
    adds nothing: no evidence). Its stored pages are served from the page
    store, its row goes (replaced or evicted), and card 40, delivered, is
    viewed in the same process: evicted_split, never other, no ERROR line.
    The control is a real restart: restart_split."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(90)
    assert pack_of(engine, job_id) is None and job_id in server._deck_held
    if path == "control_restart":
        restart()
    else:
        with server._trade_jobs_lock:
            server._trade_jobs[job_id]["finished_at"] = (
                time.monotonic() - server._PREGEN_TTL_SECONDS - 60)
        assert server._drop_stale_deck_evidence() == 1
        assert "evidence" not in server._trade_jobs[job_id]
        assert job_id not in server._deck_held and job_id in server._deck_evicted_at
        if path == "f5_then_job_evicted":
            with server._trade_jobs_lock:                  # the cleanup loop's eviction lines
                job = server._trade_jobs.pop(job_id)       # (its tick would also expire sessions)
                server._note_deck_evicted(job_id, job)
                if server._trade_jobs_by_key.get(job.get("key")) == job_id:
                    server._trade_jobs_by_key.pop(job["key"], None)
            assert job_id in server._deck_evicted_at              # F5's note; the eviction adds none
    for cursor in (0, 30):
        page = client.get(f"/api/trades/status?deck={job_id}&cursor={cursor}", headers=HEADERS)
        assert page.status_code == 200 and deck_ids(page.get_json())
    assert run_of(engine, job_id)["stored_count"] == 90
    the_row_goes(job_id, how)
    with caplog.at_level("WARNING"):
        view(job_id, 40)
    run = run_of(engine, job_id)
    cause = "restart_split" if path == "control_restart" else "evicted_split"
    assert (run["upgrade_miss_cards"], row_gone(run)) == ({"40": cause}, {"40": 90})
    assert errors(caplog) == []


def test_f5_leaves_a_delivered_deck_held(deferred):
    """F5 drops only undelivered decks: a delivered one keeps its evidence and
    its held entry (a miss on it here is still other)."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    with server._trade_jobs_lock:
        server._trade_jobs[job_id]["finished_at"] = time.monotonic() - server._PREGEN_TTL_SECONDS - 60
    assert server._drop_stale_deck_evidence() == 0
    assert job_id in server._deck_held


# ── (B) the miss line logs the merged cause ─────────────────────────────────

def test_a_second_writer_logs_the_kept_cause_never_an_error(deferred, caplog):
    """A deploy overlap: the first writer misses card 95 as restart_split; the
    second (it built the deck: other, locally) misses the CAS, and the merge
    keeps restart_split. Its line logs restart_split with local_cause=other,
    at WARNING: no ERROR line for an alert to fire on."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    for cursor in (0, 30, 60, 90):
        status(client, job_id, cursor)
    restart()
    first = server._load_pack_state(job_id, UID)
    second = server._load_pack_state(job_id, UID)
    iid = contract.card_impression_id(job_id, 95)
    now = datetime.now(timezone.utc).isoformat()
    with caplog.at_level("WARNING"):
        with server._deck_evidence_write_lock:
            assert server._deck_upgrade_from_pack(first, job_id, iid, 95, now)
    [line] = miss_lines(caplog)
    assert "cause=restart_split" in line and "local_cause" not in line
    caplog.clear()
    server._note_deck_held(job_id)                         # the second process built it
    with caplog.at_level("WARNING"):
        with server._deck_evidence_write_lock:
            assert server._deck_upgrade_from_pack(second, job_id, iid, 95, now)
    [line] = miss_lines(caplog)
    assert "cause=restart_split" in line and line.endswith(" local_cause=other")
    assert errors(caplog) == []
    assert run_of(engine, job_id)["upgrade_miss_cards"] == {"95": "restart_split"}


# ── (C1) the guard warning per ledger ───────────────────────────────────────

class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_the_guard_warning_counts_each_ledgers_trims(monkeypatch, caplog):
    clock = Clock()
    monkeypatch.setattr(server, "_ledger_now", clock)
    monkeypatch.setattr(server, "_deck_held", collections.OrderedDict())
    monkeypatch.setattr(server, "_deck_evicted_at", collections.OrderedDict())
    monkeypatch.setattr(server, "_DECK_LEDGER_GUARD", 2)
    with caplog.at_level("WARNING"):
        for i in range(3):
            server._ledger_add(server._deck_held, f"h{i}")       # h2 trims h0: warned now
        for i in range(3):
            server._ledger_add(server._deck_evicted_at, f"e{i}")  # e2 trims e0
        server._ledger_add(server._deck_held, "h3")              # trims h1
        clock.t += 60
        server._ledger_add(server._deck_evicted_at, "e3")        # trims e1: warned again
    lines = [r.getMessage() for r in caplog.records if "ledger guard" in r.getMessage()]
    assert len(lines) == 2
    assert "trimmed 1 entry younger than 24 h since its last warning (held=1, evicted=0)" in lines[0]
    assert "trimmed 3 entries younger than 24 h since its last warning (held=1, evicted=2)" in lines[1]


# ── (C2) the guard's rate-limit state is reset per test (conftest.py) ───────

def test_the_guard_state_a_test_leaves_dirty():
    """As the ledger thread-safety test does: thousands of young trims."""
    server._ledger_guard_young = {"held": 7, "evicted": 3}
    server._ledger_guard_warned_at = 1e12


def test_the_next_test_starts_with_the_guard_state_clean():
    assert server._ledger_guard_young == {"held": 0, "evicted": 0}
    assert server._ledger_guard_warned_at == float("-inf")


# ── (C3) the store's double fault ───────────────────────────────────────────

def raising_save(monkeypatch, commits: bool):
    real = db_module.save_trade_page

    def save(row):
        if commits:
            real(row)
        raise RuntimeError("injected: the save raised" + (" after its commit" if commits else ""))
    monkeypatch.setattr(db_module, "save_trade_page", save)


def test_a_save_that_commits_then_raises_counts_as_written(deferred, monkeypatch):
    """#445 QA P3-4: the row holds 90, so the deck's stored count is 90 (in
    the job and, filled late, in the pack), never 0."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, complete=False, store=False)
    delivered_before_completion(client, job_id)            # the pack, no stored_count yet
    raising_save(monkeypatch, commits=True)
    assert server._store_trade_page(job_id) is True
    assert db_module.load_trade_page_for_job(UID, job_id)["card_count"] == 90
    assert server._trade_jobs[job_id]["evidence"].stored_count == 90
    assert run_of(engine, job_id)["stored_count"] == 90


@pytest.mark.parametrize("fault", ["no_row", "reread_fails"])
def test_a_save_that_raises_without_its_row_stays_unwritten(deferred, monkeypatch, fault):
    """Today's behaviour stands when the row isn't there, or can't be read."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, complete=False, store=False)
    delivered_before_completion(client, job_id)
    raising_save(monkeypatch, commits=fault == "reread_fails")
    if fault == "reread_fails":
        def boom(*_a, **_k):
            raise RuntimeError("injected: the re-read fails")
        monkeypatch.setattr(db_module, "load_trade_page_for_job", boom)
    assert server._store_trade_page(job_id) is False
    assert server._trade_jobs[job_id]["evidence"].stored_count == 0
    assert run_of(engine, job_id)["stored_count"] == 0


# ── (C4) the flip day, read through one normalizer ──────────────────────────

SPAN = [{"served_at": "2026-10-01T00:00:00+00:00"}, {"served_at": "2026-12-01T00:00:00+00:00"}]


@pytest.mark.parametrize("value", ["2026-11-4", "20261104", "2026-11-04T00:00:00", "",
                                   20261104, date(2026, 11, 4)])
def test_a_malformed_flip_day_is_no_caveat_and_one_warning(monkeypatch, caplog, value):
    """#448 QA: both caveats read the day through database.packed_evidence_flip_day:
    a malformed value is no caveat on either series (never a 500, a TypeError
    on a non-str before), with one WARNING per process, not per read."""
    monkeypatch.setattr(db_module, "PACKED_EVIDENCE_FLIP_DAY", value)
    monkeypatch.setattr(db_module, "_flip_day_warned", False)
    with caplog.at_level("WARNING"):
        for _ in range(2):
            assert rs._receipts_series_break_caveats(SPAN) == []
            assert server._ratio_series_break_caveats("2026-10-01", "2026-12-01") == []
    assert caplog.text.count("is not a YYYY-MM-DD day") == 1


def test_a_well_formed_flip_day_still_flags_both_series(monkeypatch, caplog):
    monkeypatch.setattr(db_module, "PACKED_EVIDENCE_FLIP_DAY", "2026-11-04")
    monkeypatch.setattr(db_module, "_flip_day_warned", False)
    with caplog.at_level("WARNING"):
        assert [c["day"] for c in rs._receipts_series_break_caveats(SPAN)] == ["2026-11-04"]
        assert [c["day"] for c in server._ratio_series_break_caveats(
            "2026-10-01", "2026-12-01")] == ["2026-11-04"]
    assert "YYYY-MM-DD" not in caplog.text


def test_the_emitters_use_the_series_break_constant():
    """#448 QA: the three emitters (the event series, receipts, the ratio) carry
    database.SERIES_BREAK_CAVEAT; the literal appears only at its definition."""
    for name in ("analytics_queries.py", "receipts_service.py", "server.py"):
        source = (BACKEND / name).read_text()
        assert '"series_break"' not in source and "'series_break'" not in source, name
        assert "SERIES_BREAK_CAVEAT" in source, name
    assert (BACKEND / "database.py").read_text().count('"series_break"') == 1


# ── (C5) the day span joins on the league ───────────────────────────────────

def test_the_day_span_joins_the_trades_on_the_league(p1):
    """#448 QA: the ON clause matches the league too (Postgres plans the join
    on it: 23 ms → 1.3 ms); the span is the same."""
    from sqlalchemy import event, insert
    _, engine, _ = p1
    with engine.begin() as conn:
        conn.execute(insert(db_module.sleeper_trades_table).values(
            transaction_id="tx-1", league_id=LEAGUE, synced_at="2026-11-02T00:00:00+00:00",
            raw="{}"))
        conn.execute(insert(db_module.suggestion_trade_links_table).values(
            transaction_id="tx-1", league_id=LEAGUE, was_recommended=0,
            computed_at="2026-11-09T00:00:00+00:00"))
    seen = []
    listen = lambda conn, cursor, statement, *a: seen.append(" ".join(statement.split()))
    event.listen(engine, "before_cursor_execute", listen)
    try:
        assert db_module.suggestion_link_day_span(LEAGUE) == ("2026-11-02", "2026-11-02")
    finally:
        event.remove(engine, "before_cursor_execute", listen)
    [sql] = [s for s in seen if "suggestion_trade_links" in s]
    assert ("sleeper_trades.transaction_id = suggestion_trade_links.transaction_id AND "
            "sleeper_trades.league_id = suggestion_trade_links.league_id") in sql


# ── (D) #445 QA P3-3 pins ───────────────────────────────────────────────────

def test_the_stored_blob_carries_only_the_stored_cards_trade_impressions(deferred, monkeypatch):
    """With 2 of 4 cards stored (one page of 2), the evidence blob's
    trade_impressions holds 2 cards: blob(stored_count=…) truncates before the
    deck's own count is set."""
    client, engine, _ = deferred
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_page_size", 2.0)
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_pages_stored", 1.0)
    job_id, served, *_ = packed_deck(4, store=False)
    server._trade_jobs[job_id]["evidence"].defer_trade_impressions(LEAGUE, served)
    assert server._store_trade_page(job_id)
    row = stored()
    assert row["card_count"] == 2
    assert len(row["evidence_blob"]["trade_impressions"]["cards"]) == 2


@pytest.mark.parametrize("page_store", [0, 1])
def test_the_fallback_warning_fires_only_for_a_page_scoped_deck(
        deferred, monkeypatch, caplog, page_store):
    """Option A off (the stored path's only fallback): a deck that died before
    its store, so no count anywhere, reads 0 either way, and only a
    page-scoped deck (page_store 1) warns."""
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_STORED_COUNT_FROM_ROW_NOW", False)
    job_id, *_ = packed_deck(120, complete=False, store=False)
    server._trade_jobs[job_id]["evidence"].page_store = bool(page_store)
    delivered_before_completion(client, job_id)
    run = run_of(engine, job_id)
    assert run["page_store"] == page_store and "stored_count" not in run
    restart()
    with caplog.at_level("WARNING"):
        view(job_id, 40)
    [line] = miss_lines(caplog)
    assert "stored=0 stored_from=fallback " in line
    assert ("stored count fallback" in caplog.text) is bool(page_store)


class _Recorder:
    """ev.lock, recording the write lock's depth at each acquisition."""

    def __init__(self, lock, note):
        self.lock, self.note = lock, note

    def __enter__(self):
        self.note()
        return self.lock.__enter__()

    def __exit__(self, *exc):
        return self.lock.__exit__(*exc)


def test_the_save_and_its_finally_run_under_the_write_lock(deferred, monkeypatch):
    """The page save and every ev.lock section around it (the snapshot, the
    finally that sets the deck's count, the late header fill) run inside one
    hold of _deck_evidence_write_lock, so a delivery never interleaves."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120, complete=False, store=False)
    delivered_before_completion(client, job_id)
    lock = _Owned(server._deck_evidence_write_lock)
    monkeypatch.setattr(server, "_deck_evidence_write_lock", lock)
    depths = {"save": [], "ev": []}
    real_save = db_module.save_trade_page

    def save(row):
        depths["save"].append(lock.depth)
        return real_save(row)
    monkeypatch.setattr(db_module, "save_trade_page", save)
    ev = server._trade_jobs[job_id]["evidence"]
    ev.lock = _Recorder(ev.lock, lambda: depths["ev"].append(lock.depth))
    assert server._store_trade_page(job_id)
    assert depths["save"] == [1]
    assert len(depths["ev"]) >= 3 and set(depths["ev"]) == {1}


# ── (D) #454 QA P3-3 pins ───────────────────────────────────────────────────

def test_the_why_read_happens_only_for_a_card_new_to_the_map(deferred, monkeypatch):
    """Card 40 first missed here (other: a held deck whose snapshot is gone)
    and its row save failed. After its row is replaced and a restart, the
    retry is row-gone but the card is already in the map: no why, no read."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    ev = server._trade_jobs[job_id]["evidence"]
    with ev.lock:
        ev.rows.pop(contract.card_impression_id(job_id, 40))
    with fail_after(engine, "INSERT INTO DECK_IMPRESSIONS"):
        view(job_id, 40)
    the_row_goes(job_id, "replaced")
    restart()
    calls = counting_reads(monkeypatch)
    view(job_id, 40)
    run = run_of(engine, job_id)
    assert calls == [] and run.get("upgrade_miss_row_gone_why", {}) == {}
    assert run["upgrade_miss_cards"] == {"40": "other"}


@pytest.mark.parametrize("column, value", [("scoring_format", "2qb_ppr"),
                                           ("request_scope", "organic:f=0.75")])
def test_a_row_for_another_format_or_scope_is_not_a_replacement(deferred, column, value):
    """The deck's row is evicted; a row exists for the same user and league
    under another scoring format (or scope). That isn't the deck's key: no_row."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    the_row_goes(job_id, "evicted")
    assert db_module.save_trade_page(_row(time.time(), "a-deck-for-another-key", **{column: value}))
    restart()
    view(job_id, 40)
    run = run_of(engine, job_id)
    assert run["upgrade_miss_row_gone_why"] == {"40": "no_row"}


def test_the_decks_own_row_back_leaves_the_entry_unsplit(deferred, monkeypatch):
    """The key's row holds this deck again (a race with its own row's read):
    row-gone recorded, no why."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    delivered(client, job_id)
    the_row_goes(job_id, "evicted")
    restart()
    monkeypatch.setattr(db_module, "load_trade_page_deck_job_id", lambda *a: job_id)
    view(job_id, 40)
    run = run_of(engine, job_id)
    assert (row_gone(run), run.get("upgrade_miss_row_gone_why", {})) == ({"40": 90}, {})
