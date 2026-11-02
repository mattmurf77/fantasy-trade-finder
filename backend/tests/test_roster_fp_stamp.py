"""S0 PR-B — the roster fingerprint stamp after a background refresh, and the hook.

Pins (scope-eng-s0-fetch.md §B.3 step 7; fingerprint contract v0.4 §4, A3):
  • a 'fresh' outcome stamps `league_roster_state.roster_fp` with trades-eng's
    `rfp1`, computed as the serve computes it (same function, same pick source)
  • the first stamp calls `on_roster_change(league, None, new)`; a changed
    roster calls it with (old, new); an unchanged roster writes nothing and
    makes no call
  • compare-and-set: a refresh that loses the CAS (another stamped first)
    makes no call and leaves the winner's value
  • a handler exception, or the hook itself raising, never escapes or changes
    the recorded outcome
  • a failed refresh never stamps; a fingerprint error leaves roster_fp as
    stored, makes no call, and the outcome stays 'fresh'
  • A3: the hook runs with no open DB transaction and no refresh-module or
    snapshot-module lock held, on the refresh's own background thread (the
    P41 kick and the session-init daemon), never the request thread

File-backed SQLite (QueuePool), so `pool.checkedout()` and a second
connection's write see a connection or transaction the stamp still holds.
Sleeper calls are stubbed; no network.
"""

import threading
import time

import pytest
from sqlalchemy import create_engine, insert, update

import backend.database as db_module
import backend.roster_refresh as rr
import backend.roster_snapshot as rs
import backend.server as server
import backend.sleeper_http as sh
from backend.database import metadata
from backend.tests import test_roster_refresh_state as refresh

LID = "1338231586314780672"
RIVAL = "rfp1:" + "c" * 32
T = db_module.league_roster_state_table


@pytest.fixture()
def env(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 's0-pr-b.db'}",
                           connect_args={"check_same_thread": False, "timeout": 0.5})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(rs, "_roster_change_handlers", [])   # only this test's handlers
    rr._inflight.clear()
    sh.reset()
    server._FA_LEAGUE_META_CACHE.pop(LID, None)

    sleeper = {"rosters": [{"roster_id": 1, "owner_id": "u1", "players": ["p1"]},
                           {"roster_id": 2, "owner_id": "u2", "players": ["p2"]}],
               "fail": False}

    def fake_get(url, timeout=15):
        if sleeper["fail"]:
            raise TimeoutError("read timed out")
        if url.endswith("/rosters"):
            return [dict(r) for r in sleeper["rosters"]]
        if url.endswith("/users"):
            return [{"user_id": "u1", "username": "a"}, {"user_id": "u2", "username": "b"}]
        raise AssertionError(f"unexpected Sleeper GET {url}")

    monkeypatch.setattr(server, "_sleeper_get", fake_get)
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta",
                        lambda lid: {"league_id": lid, "season": "2026", "settings": {}})
    monkeypatch.setattr(server, "_sync_sleeper_owned_picks", lambda *a, **k: [])
    monkeypatch.setattr(server, "_invalidate_league_members_cache", lambda lid: None)
    errors = []
    monkeypatch.setattr(threading, "excepthook", lambda args: errors.append(args.exc_value))
    yield sleeper, errors
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


def _refresh(players=("p1",)):
    """One session-init-shaped success: members committed, then the outcome."""
    assert db_module.replace_league_members_snapshot(LID, [
        {"user_id": "u1", "username": "a", "player_ids": list(players)},
        {"user_id": "u2", "username": "b", "player_ids": ["p2"]}])
    return rr.record_outcome(LID, rr.fetch_started_at(), members_ok=True, picks_ok=True)


def _fp():
    return (db_module.get_league_roster_state(LID) or {}).get("roster_fp")


def _recorder():
    calls = []
    rs.register_roster_change_handler(lambda lid, old, new: calls.append((lid, old, new)))
    return calls


def _spy_hook(monkeypatch):
    """Replace the hook entry point itself: catches a call even when old == new
    (`on_roster_change` would drop that before any handler)."""
    calls = []
    monkeypatch.setattr(rs, "on_roster_change", lambda *a: calls.append(a))
    return calls


# ---------------------------------------------------------------------------
# Stamp and hook
# ---------------------------------------------------------------------------

def test_first_stamp_writes_rfp1_and_calls_the_hook_with_old_none(env, monkeypatch):
    calls = _recorder()
    sources = []
    real = rs.roster_snapshot

    def spy(conn, lid, **kw):
        sources.append(kw.get("pick_source"))
        return real(conn, lid, **kw)

    monkeypatch.setattr(rs, "roster_snapshot", spy)
    assert _refresh() == "fresh"
    fp = _fp()
    assert fp.startswith("rfp1:") and len(fp) == len("rfp1:") + 32
    assert calls == [(LID, None, fp)]
    assert sources == [server._pick_read_source()]           # the engine's pick row set
    monkeypatch.setattr(rs, "roster_snapshot", real)
    assert server._trade_roster_snapshot(LID).fp == fp       # what the serve computes


def test_stamp_follows_the_platform_pick_source_when_assign_tradeable_is_off(env, monkeypatch, request):
    """#470 QA P3: CI runs with `picks.assign_tradeable` on (`'any'`), so the pin
    above can't tell a hard-coded `'any'` from the engine's source. Off, the
    engine reads platform rows only; a member-asserted row makes the two
    sources hash differently, and the stamp must match the serve's."""
    import backend.feature_flags as ff
    ff.flags_dict()                                          # populate the cache
    monkeypatch.setitem(ff._flags_cache, "picks.assign_tradeable", False)
    assert server._pick_read_source() == db_module.PICK_SOURCE_PLATFORM
    db_module._invalidate_contested(LID)
    request.addfinalizer(lambda: db_module._invalidate_contested(LID))
    platform_row = {"pick_id": f"{LID}_2027_1_1", "league_id": LID, "season": 2027, "round": 1,
                    "owner_user_id": "u1", "original_roster_id": "1", "platform": "sleeper"}
    asserted_row = {"pick_id": f"{LID}_2027_2_2", "league_id": LID, "season": 2027, "round": 2,
                    "owner_user_id": "u2", "original_roster_id": "2", "platform": "sleeper",
                    "source": db_module.PICK_SOURCE_USER, "assigned_by": "u1",
                    "assigned_at": "2026-10-27T00:00:00.000000+00:00"}
    with db_module.engine.begin() as conn:                   # one row per insert: same keys
        conn.execute(insert(db_module.draft_picks_table).values(platform_row))
        conn.execute(insert(db_module.draft_picks_table).values(asserted_row))
    assert _refresh() == "fresh"
    with db_module.engine.connect() as conn:
        any_fp = rs.roster_snapshot(conn, LID, pick_source=db_module.PICK_SOURCE_ANY).fp
    assert any_fp != _fp()                                   # the fixture tells the sources apart
    assert server._trade_roster_snapshot(LID).fp == _fp()    # the serve, flag off


def test_changed_roster_calls_the_hook_with_old_and_new(env):
    calls = _recorder()
    assert _refresh(("p1",)) == "fresh"
    first = _fp()
    assert _refresh(("p3",)) == "fresh"                      # u1 dropped p1, added p3
    second = _fp()
    assert second.startswith("rfp1:") and second != first
    assert calls == [(LID, None, first), (LID, first, second)]


def test_unchanged_roster_stamps_nothing_and_makes_no_call(env, monkeypatch):
    assert _refresh() == "fresh"
    first = _fp()
    hook = _spy_hook(monkeypatch)
    cas = []
    real_cas = db_module.cas_league_roster_fp
    monkeypatch.setattr(db_module, "cas_league_roster_fp",
                        lambda *a: cas.append(a) or real_cas(*a))
    assert _refresh() == "fresh"                             # same rows again
    assert _fp() == first
    assert hook == [] and cas == []


@pytest.mark.parametrize("prior", ["first_stamp", "restamp"])
def test_lost_cas_makes_no_hook_call(env, monkeypatch, prior):
    if prior == "restamp":
        assert _refresh(("p1",)) == "fresh"
    old = _fp()
    hook = _spy_hook(monkeypatch)
    real = rs.roster_snapshot

    def racing(conn, lid, **kw):
        snap = real(conn, lid, **kw)
        with db_module.engine.begin() as other:              # another refresh stamps first
            other.execute(update(T).where(T.c.league_id == lid).values(roster_fp=RIVAL))
        return snap

    monkeypatch.setattr(rs, "roster_snapshot", racing)
    assert _refresh(("p9",)) == "fresh"
    assert _fp() == RIVAL                                    # the winner's value stands
    assert hook == []
    assert old != RIVAL


def test_stamp_without_a_state_row_writes_nothing(env, monkeypatch):
    hook = _spy_hook(monkeypatch)
    assert db_module.replace_league_members_snapshot(LID, [
        {"user_id": "u1", "username": "a", "player_ids": ["p1"]}])
    assert rr.stamp(LID) is False
    assert db_module.get_league_roster_state(LID) is None and hook == []


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------

def test_handler_exception_is_swallowed_and_logged(env, caplog):
    def boom(lid, old, new):
        raise RuntimeError("handler bug")

    rs.register_roster_change_handler(boom)
    calls = _recorder()
    with caplog.at_level("ERROR"):
        assert _refresh() == "fresh"
    assert calls == [(LID, None, _fp())]                     # the next handler still ran
    assert "on_roster_change handler" in caplog.text and "handler bug" in caplog.text


def test_hook_raising_never_escapes_the_refresh(env, monkeypatch, caplog):
    def broken(*a):
        raise RuntimeError("registry bug")

    monkeypatch.setattr(rs, "on_roster_change", broken)
    with caplog.at_level("ERROR"):
        assert _refresh() == "fresh"
    assert _fp().startswith("rfp1:")
    assert "on_roster_change failed" in caplog.text


@pytest.mark.parametrize("outcome", [
    {"members_ok": False, "picks_ok": True},
    {"members_ok": True, "picks_ok": False},
])
def test_failed_refresh_does_not_stamp(env, monkeypatch, outcome):
    hook = _spy_hook(monkeypatch)
    assert db_module.replace_league_members_snapshot(LID, [
        {"user_id": "u1", "username": "a", "player_ids": ["p1"]}])
    assert rr.record_outcome(LID, rr.fetch_started_at(), **outcome) == "stale"
    assert _fp() is None and hook == []


def test_failed_read_and_failed_state_write_do_not_stamp(env, monkeypatch):
    hook = _spy_hook(monkeypatch)
    assert rr.record_failure(LID, "timeout") == "stale"
    assert _fp() is None

    def db_down(*a):
        raise RuntimeError("db down")

    monkeypatch.setattr(db_module, "mark_league_roster_fresh", db_down)
    assert _refresh() is None
    assert _fp() is None and hook == []


def test_failed_kick_read_does_not_stamp(env, monkeypatch):
    hook = _spy_hook(monkeypatch)
    sleeper, errors = env
    sleeper["fail"] = True
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()
    state = db_module.get_league_roster_state(LID)
    assert (state["status"], state["roster_fp"]) == ("stale", None)
    assert hook == [] and errors == []


@pytest.mark.parametrize("where", ["fingerprint", "pick_source"])
def test_fp_error_keeps_the_stored_fp_and_the_fresh_outcome(env, monkeypatch, caplog, where):
    assert _refresh(("p1",)) == "fresh"
    before = _fp()
    hook = _spy_hook(monkeypatch)

    def fail(*a, **k):
        raise RuntimeError("read failed")

    if where == "fingerprint":
        monkeypatch.setattr(rs, "roster_snapshot", fail)
    else:
        monkeypatch.setattr(server, "_pick_read_source", fail)
    with caplog.at_level("WARNING"):
        assert _refresh(("p3",)) == "fresh"                  # the outcome is unchanged
    state = db_module.get_league_roster_state(LID)
    assert (state["status"], state["roster_fp"]) == ("fresh", before)
    assert hook == []
    assert "roster fp stamp failed" in caplog.text


def test_linked_platform_league_is_never_refreshed_so_never_stamped(env, monkeypatch):
    hook = _spy_hook(monkeypatch)
    with db_module.engine.begin() as conn:
        conn.execute(db_module.leagues_table.insert().values(
            sleeper_league_id="62846", user_id="u1", name="Imported", platform="mfl"))
    db_module.upsert_league_members("62846", [
        {"user_id": "u1", "username": "a", "player_ids": ["p1"]}])
    assert rr.maybe_refresh_async("62846", 0) is False
    assert db_module.get_league_roster_state("62846") is None and hook == []


# ---------------------------------------------------------------------------
# A3: no transaction, no lock, a background thread
# ---------------------------------------------------------------------------

def _a3_probe(seen):
    def probe(lid, old, new):
        seen["thread"] = threading.current_thread().name
        seen["ident"] = threading.get_ident()
        seen["checked_out"] = db_module.engine.pool.checkedout()
        for name, lock in (("inflight_lock", rr._inflight_lock), ("snapshot_lock", rs._lock)):
            got = lock.acquire(blocking=False)
            if got:
                lock.release()
            seen[name] = got
        try:                                                 # a fresh connection can write
            with db_module.engine.begin() as conn:
                conn.execute(insert(T).values(league_id="a3-probe", status="fresh",
                                              updated_at="2026-10-27T00:00:00+00:00"))
            seen["write"] = True
        except Exception as exc:
            seen["write"] = type(exc).__name__
    return probe


def test_a3_hook_runs_unlocked_outside_any_transaction_on_the_kick_thread(env):
    _sleeper, errors = env
    seen = {}
    rs.register_roster_change_handler(_a3_probe(seen))
    assert rr.maybe_refresh_async(LID, 300) is True
    _wait_idle()
    assert seen.pop("ident") != threading.get_ident()
    assert seen == {"thread": f"roster-refresh-{LID}", "checked_out": 0,
                    "inflight_lock": True, "snapshot_lock": True, "write": True}
    assert db_module.get_league_roster_state("a3-probe") is not None
    assert _fp().startswith("rfp1:") and errors == []


@pytest.fixture()
def init_harness(monkeypatch, tmp_path):
    yield from refresh.harness.__wrapped__(monkeypatch, tmp_path)


def test_session_init_stamps_and_hooks_on_its_daemon_thread(init_harness, monkeypatch):
    client, _put = init_harness
    monkeypatch.setattr(rs, "_roster_change_handlers", [])
    calls = []
    rs.register_roster_change_handler(lambda lid, old, new: calls.append(
        (lid, old, new, threading.current_thread().name, threading.get_ident())))

    inline = server.threading.Thread                         # the harness's inline class

    class _JoinedBgThread(inline):
        """The daemon on a real thread; the request waits for it (deterministic)."""
        def start(self):
            super(inline, self).start()
            if self.name == "session-init-bg-writes":
                self.join(10)

    monkeypatch.setattr(server.threading, "Thread", _JoinedBgThread)
    assert refresh._init(client).status_code == 200
    fp = db_module.get_league_roster_state(refresh.LEAGUE_ID)["roster_fp"]
    assert fp.startswith("rfp1:")
    assert len(calls) == 1
    lid, old, new, name, ident = calls[0]
    assert (lid, old, new, name) == (refresh.LEAGUE_ID, None, fp, "session-init-bg-writes")
    assert ident != threading.get_ident()                    # never the request thread
