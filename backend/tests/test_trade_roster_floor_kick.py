"""S0 / P41 at serve: a past-bound Sleeper roster kicks ONE background refresh.

`_trade_job_public_view` calls `roster_refresh.maybe_refresh_async(league,
max_age_s=trade_roster_bound_s)` after the response is built, with no lock
held, whenever the Sleeper roster is past the bound. Pinned here through
`GET /api/trades/status`, with the real hook and stubbed Sleeper reads:
  (a) a past-bound tap gets its cards, and no platform call runs on the
      request thread (AC-L3);
  (b) N concurrent past-bound taps start exactly one refresh (the hook's
      single-flight), while the refresh is held in flight.
Harness: a file-backed SQLite engine (one connection per thread) and Sleeper stubs.
"""
import json
import threading
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.roster_refresh as rr
import backend.server as server
import backend.sleeper_http as sh
from backend.database import league_members_table, league_roster_state_table, metadata

LID = "1338231586314780999"
UID, OPP = "u1", "u2"
TOKEN = "floor-kick-tok"
KEY = (UID, LID, "1qb_ppr")
OLD = "2026-01-01T00:00:00.000000+00:00"
ROSTERS = [{"roster_id": 1, "owner_id": UID, "players": ["p1"]},
           {"roster_id": 2, "owner_id": OPP, "players": ["p2"]}]
USERS = [{"user_id": UID, "display_name": "Me"}, {"user_id": OPP, "display_name": "Opp"}]
CARD = {"trade_id": "t-floor", "league_id": LID, "target_user_id": OPP,
        "give": [{"id": "p1"}], "receive": [{"id": "p2"}], "decision": None}


@pytest.fixture()
def env(monkeypatch, tmp_path):
    # A file-backed DB, so each thread gets its own connection. The barrier
    # test runs 6 concurrent taps, and one shared StaticPool connection across
    # threads raised sqlite3.InterfaceError on CI (prod runs on a pooled Postgres).
    engine = create_engine(f"sqlite:///{tmp_path / 'floor-kick.db'}",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    rr._inflight.clear()
    sh.reset()
    server._FA_LEAGUE_META_CACHE.pop(LID, None)
    with engine.begin() as conn:
        for uid, roster in ((UID, ["p1"]), (OPP, ["p2"])):
            conn.execute(insert(league_members_table).values(
                league_id=LID, user_id=uid, roster_data=json.dumps(roster), updated_at=OLD))
        # Past the bound, last refresh fine, no failure cooldown.
        conn.execute(insert(league_roster_state_table).values(
            league_id=LID, status="fresh", refreshed_at=OLD, updated_at=OLD))

    calls, gate = [], {"event": None}

    def fake_get(url, timeout=15):
        calls.append((url.rsplit("/", 1)[-1], threading.current_thread().name))
        if gate["event"] is not None:
            gate["event"].wait(5)
        if url.endswith("/rosters"):
            return [dict(r) for r in ROSTERS]
        if url.endswith("/users"):
            return [dict(u) for u in USERS]
        raise AssertionError(f"unexpected Sleeper GET {url}")

    monkeypatch.setattr(server, "_sleeper_get", fake_get)
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta", lambda lid: {"league_id": lid})
    monkeypatch.setattr(server, "_sync_sleeper_owned_picks", MagicMock(return_value=[]))
    job = {"job_id": "job-floor", "key": KEY, "status": "complete", "opponents_done": 1,
           "opponents_total": 1, "cards": [dict(CARD)], "error": None, "league_user_id": UID}
    with server._trade_jobs_lock:
        server._trade_jobs[job["job_id"]] = job
    with server._sessions_lock:
        server._sessions[TOKEN] = {"user_id": UID, "verified": True, "last_active": 0.0}
    try:
        yield calls, gate
    finally:
        _join_refreshes()
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
        with server._trade_jobs_lock:
            server._trade_jobs.pop(job["job_id"], None)
        rr._inflight.clear()


def _join_refreshes():
    for thread in threading.enumerate():
        if thread.name == f"roster-refresh-{LID}":
            thread.join(5)


def _tap():
    resp = server.app.test_client().get("/api/trades/status?job_id=job-floor",
                                        headers={"X-Session-Token": TOKEN})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_a_past_bound_tap_serves_cards_with_no_platform_call_on_the_request_thread(env):
    calls, _ = env
    body = _tap()
    request_thread = threading.current_thread().name
    assert body["cards"] == [CARD] and body["status"] == "complete"
    _join_refreshes()
    assert calls, "the floor refresh never ran"
    assert {thread for _, thread in calls} == {f"roster-refresh-{LID}"}
    assert request_thread not in {thread for _, thread in calls}


def test_a_fresh_roster_within_the_bound_kicks_nothing(env):
    calls, _ = env
    with db_module.engine.begin() as conn:
        conn.execute(league_roster_state_table.update().values(
            refreshed_at=rr.fetch_started_at()))
    assert _tap()["cards"] == [CARD]
    _join_refreshes()
    assert calls == []


def test_concurrent_past_bound_taps_start_exactly_one_refresh(env):
    calls, gate = env
    gate["event"] = threading.Event()            # hold the refresh in flight
    taps, start, bodies, errors = 6, threading.Barrier(6), [], []

    def tap():
        try:
            start.wait(5)
            bodies.append(_tap())
        except Exception as exc:     # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=tap) for _ in range(taps)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    gate["event"].set()
    _join_refreshes()
    assert not errors and len(bodies) == taps
    assert all(body["cards"] == [CARD] for body in bodies)
    assert [name for name, _ in calls].count("rosters") == 1
