"""S0 / P41 — `roster_refresh.maybe_refresh_async`: the non-blocking floor kick.

Pins (scope-eng-s0-fetch.md §B.1, §B.5):
  • concurrent callers start exactly ONE refresh per league (single-flight)
  • no-ops without a thread: fresh-enough league, linked platform league,
    open 429 circuit, refresh already in flight, a failed attempt younger than
    `retry_after_s` (the cooldown); NULL / no row is past the bound
  • the refresh records 'fresh' (refreshed_at advances), 'stale' /
    'picks_unavailable' on a pick failure, 'stale' on a read exception — and
    the thread never raises
  • the league always leaves the in-flight set (success and failure)
  • no Sleeper read runs while the module lock is held
  • ≤ 4 Sleeper reads per kick (5 on a meta-cache miss)

`server` functions are stubbed with monkeypatch; in-memory DB; no network.
"""

import threading
import time
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.pool import StaticPool

import backend.database as db_module
import backend.roster_refresh as rr
import backend.server as server
import backend.sleeper_http as sh
from backend.database import metadata

LID = "1338231586314780672"
ROSTERS = [{"roster_id": 1, "owner_id": "u1", "players": ["p1", None, ""]},
           {"roster_id": 2, "owner_id": "u2", "players": ["p2"]}]
USERS = [{"user_id": "u1", "display_name": "Alpha"}, {"user_id": "u2", "username": "beta"}]
META = {"league_id": LID, "season": "2026", "total_rosters": 2, "settings": {"draft_rounds": 1}}
OLD = "2026-01-01T00:00:00.000000+00:00"


class _OwnerLock:
    """threading.Lock that remembers which thread holds it."""

    def __init__(self):
        self._lock = threading.Lock()
        self.owner = None

    def __enter__(self):
        self._lock.acquire()
        self.owner = threading.get_ident()
        return self

    def __exit__(self, *exc):
        self.owner = None
        self._lock.release()

    def held_by_me(self):
        return self.owner == threading.get_ident()


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    lock = _OwnerLock()
    monkeypatch.setattr(rr, "_inflight_lock", lock)
    rr._inflight.clear()
    sh.reset()
    server._FA_LEAGUE_META_CACHE.pop(LID, None)

    calls = {"rosters": 0, "users": 0, "meta": 0, "picks": 0, "under_lock": 0}
    behaviour = {"picks_result": [], "raise": None, "gate": None}

    def fake_get(url, timeout=15):
        if lock.held_by_me():
            calls["under_lock"] += 1
        if behaviour["gate"] is not None:
            behaviour["gate"].wait(5)
        if behaviour["raise"] is not None:
            raise behaviour["raise"]
        if url.endswith("/rosters"):
            calls["rosters"] += 1
            return [dict(r) for r in ROSTERS]
        if url.endswith("/users"):
            calls["users"] += 1
            return [dict(u) for u in USERS]
        raise AssertionError(f"unexpected Sleeper GET {url}")

    def fake_meta(league_id):
        if lock.held_by_me():
            calls["under_lock"] += 1
        calls["meta"] += 1
        return dict(META)

    def fake_picks(league_id, uid_to_name, scoring, *, rosters=None, meta=None):
        if lock.held_by_me():
            calls["under_lock"] += 1
        calls["picks"] += 1
        assert uid_to_name == {"u1": "Alpha", "u2": "beta"}
        assert scoring in db_module.SCORING_FORMATS and rosters and meta
        return behaviour["picks_result"]

    monkeypatch.setattr(server, "_sleeper_get", fake_get)
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta", fake_meta)
    monkeypatch.setattr(server, "_sync_sleeper_owned_picks", fake_picks)
    monkeypatch.setattr(server, "_invalidate_league_members_cache", lambda lid: None)

    errors = []
    monkeypatch.setattr(threading, "excepthook", lambda args: errors.append(args.exc_value))
    yield calls, behaviour, errors
    if behaviour["gate"] is not None:
        behaviour["gate"].set()
    _wait_idle()
    rr._inflight.clear()
    sh.reset()
    server._FA_LEAGUE_META_CACHE.pop(LID, None)
    engine.dispose()


def _wait_idle(timeout=5.0):
    deadline = time.monotonic() + timeout
    while rr._inflight and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not rr._inflight, "refresh thread did not finish"


def _state():
    return db_module.get_league_roster_state(LID)


# ---------------------------------------------------------------------------
# Single-flight
# ---------------------------------------------------------------------------

def test_concurrent_callers_start_exactly_one_refresh(env, monkeypatch):
    calls, behaviour, errors = env
    behaviour["gate"] = threading.Event()              # the refresh blocks inside its first read
    # Counting only: keep the (single, shared) in-memory SQLite connection out of
    # this test, so a broken single-flight fails as an assertion, not a crash.
    monkeypatch.setattr(db_module, "replace_league_members_snapshot", lambda lid, m: True)
    monkeypatch.setattr(rr, "record_outcome", lambda *a, **k: "fresh")
    n = 8
    barrier = threading.Barrier(n)
    results = []

    def caller():
        barrier.wait()
        results.append(rr.maybe_refresh_async(LID, 300))

    threads = [threading.Thread(target=caller) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert sum(results) == 1 and len(results) == n
    assert rr._inflight == {LID}                         # still in flight, gated
    behaviour["gate"].set()
    _wait_idle()
    assert calls["rosters"] == 1                         # exactly one refresh ran
    assert errors == []


# ---------------------------------------------------------------------------
# No-ops
# ---------------------------------------------------------------------------

def test_fresh_enough_league_starts_none(env):
    calls, _b, _e = env
    recent = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat(timespec="microseconds")
    db_module.mark_league_roster_fresh(LID, recent)
    assert rr.maybe_refresh_async(LID, 300) is False
    assert rr._inflight == set() and calls["rosters"] == 0


def test_no_row_starts_one(env):
    calls, _b, _e = env
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()
    assert calls["rosters"] == 1


def test_null_refreshed_at_starts_one(env):
    calls, _b, _e = env
    db_module.mark_league_roster_failed(LID, "timeout")      # row with refreshed_at NULL
    _set_updated_at(seconds_ago=120)                          # past the retry cooldown
    assert _state()["refreshed_at"] is None
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()
    assert calls["rosters"] == 1


def test_stale_past_the_bound_starts_one(env):
    calls, _b, _e = env
    db_module.mark_league_roster_fresh(LID, OLD)
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()


def _set_updated_at(seconds_ago):
    from sqlalchemy import update
    stamp = (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()
    t = db_module.league_roster_state_table
    with db_module.engine.begin() as conn:
        conn.execute(update(t).where(t.c.league_id == LID).values(updated_at=stamp))


def test_stale_league_inside_retry_cooldown_starts_none(env):
    calls, _b, _e = env
    db_module.mark_league_roster_failed(LID, "http_5xx")
    _set_updated_at(seconds_ago=10)
    assert rr.maybe_refresh_async(LID, 300) is False              # default retry_after_s = 60
    assert rr._inflight == set() and calls["rosters"] == 0


def test_stale_league_past_retry_cooldown_starts_one(env):
    calls, _b, _e = env
    db_module.mark_league_roster_failed(LID, "http_5xx")
    _set_updated_at(seconds_ago=61)
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()
    assert calls["rosters"] == 1


def test_fresh_but_past_bound_league_ignores_the_cooldown(env):
    calls, _b, _e = env
    db_module.mark_league_roster_fresh(LID, OLD)                  # status fresh, updated_at = now
    assert _state()["status"] == "fresh"
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()
    assert calls["rosters"] == 1


def test_unparseable_updated_at_never_blocks(env):
    from sqlalchemy import update
    calls, _b, _e = env
    db_module.mark_league_roster_failed(LID, "timeout")
    t = db_module.league_roster_state_table
    with db_module.engine.begin() as conn:
        conn.execute(update(t).where(t.c.league_id == LID).values(updated_at="not-a-date"))
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()


def test_linked_platform_league_starts_none(env):
    calls, _b, _e = env
    mfl = "62846"
    with db_module.engine.begin() as conn:
        conn.execute(insert(db_module.leagues_table).values(
            sleeper_league_id=mfl, user_id="u1", name="Imported", platform="mfl"))
    assert rr.maybe_refresh_async(mfl, 300) is False
    assert rr.maybe_refresh_async("league_demo", 300) is False      # not a Sleeper id
    assert rr._inflight == set() and calls["rosters"] == 0


def test_open_circuit_starts_none(env):
    calls, _b, _e = env
    sh.record_429("60")
    assert rr.maybe_refresh_async(LID, 300) is False
    assert rr._inflight == set() and calls["rosters"] == 0


# ---------------------------------------------------------------------------
# What the refresh records
# ---------------------------------------------------------------------------

def test_success_writes_fresh_and_advances_refreshed_at(env):
    calls, _b, errors = env
    db_module.mark_league_roster_fresh(LID, OLD)
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()
    state = _state()
    assert (state["status"], state["last_error_code"]) == ("fresh", None)
    assert state["refreshed_at"] > OLD
    rows = {m["user_id"]: m["player_ids"] for m in db_module.load_league_members(LID)}
    assert rows == {"u1": ["p1"], "u2": ["p2"]}                      # G-004 filtered
    assert errors == []


def test_picks_failure_writes_stale_picks_unavailable(env):
    _calls, behaviour, errors = env
    behaviour["picks_result"] = None                                 # R10: picks failed
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()
    state = _state()
    assert (state["status"], state["last_error_code"]) == ("stale", "picks_unavailable")
    assert state["refreshed_at"] is None
    assert errors == []


def test_read_exception_writes_stale_and_thread_does_not_raise(env):
    _calls, behaviour, errors = env
    behaviour["raise"] = urllib.error.HTTPError("u", 503, "x", None, None)
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()
    state = _state()
    assert (state["status"], state["last_error_code"]) == ("stale", "http_5xx")
    assert errors == []
    assert db_module.load_league_members(LID) == []                 # rows untouched


def test_unexpected_crash_never_escapes_and_clears_inflight(env, monkeypatch):
    _calls, _b, errors = env
    monkeypatch.setattr(rr, "_refresh_league", lambda lid, started: 1 / 0)
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()
    assert errors == []


# ---------------------------------------------------------------------------
# The in-flight set always empties
# ---------------------------------------------------------------------------

def test_league_leaves_inflight_after_success_and_failure(env):
    calls, behaviour, _e = env
    assert rr.maybe_refresh_async(LID, 300) is True                  # success
    _wait_idle()
    assert rr._inflight == set()
    assert rr.maybe_refresh_async(LID, 0) is True                    # past a 0 s bound: starts again
    _wait_idle()
    behaviour["raise"] = TimeoutError("slow")                        # failure
    assert rr.maybe_refresh_async(LID, 0) is True
    _wait_idle()
    assert rr._inflight == set()
    behaviour["raise"] = None
    assert rr.maybe_refresh_async(LID, 0, retry_after_s=0) is True   # and again after a failure
    _wait_idle()
    assert calls["rosters"] == 3


# ---------------------------------------------------------------------------
# Lock discipline and budget
# ---------------------------------------------------------------------------

def test_no_sleeper_read_or_write_under_the_module_lock(env):
    calls, _b, _e = env
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()
    assert calls["rosters"] == 1 and calls["picks"] == 1
    assert calls["under_lock"] == 0


def test_reads_per_kick_meta_cached_vs_miss(env):
    calls, _b, _e = env
    server._FA_LEAGUE_META_CACHE[LID] = (time.time(), dict(META))
    assert rr.maybe_refresh_async(LID, 0) is True
    _wait_idle()
    assert (calls["rosters"], calls["users"], calls["meta"]) == (1, 1, 0)   # + traded_picks, drafts
    server._FA_LEAGUE_META_CACHE.pop(LID, None)
    assert rr.maybe_refresh_async(LID, 0) is True
    _wait_idle()
    assert (calls["rosters"], calls["users"], calls["meta"]) == (2, 2, 1)   # one meta read on a miss
    assert LID in server._FA_LEAGUE_META_CACHE                              # and the cache is warm again
