"""POST /api/session/init — per-token single-flight (E1 F5, audit T6).

Two inits for one token used to run side by side: each rebuilt ranking
services and the last swap won, so a swipe landing on the first service
between the swaps was in the DB but missing from the second (it replayed
earlier). session_init now single-flights per X-Session-Token:

  • T6a  identical requests coalesce — one build per format, one swap, and the
         follower replays the leader's response bytes
  • T6b  a different league for the same token waits, then runs its own init —
         no interleaving, and the last init to finish owns the session
  • T6c  a leader that raises never strands its follower
  • T6d  a lone caller is byte-identical to calling the undecorated body
         (`session_init.__wrapped__`) directly

The single-flight is a decorator (`_single_flight_session_init`) closing over
the unchanged body, so the fixture registers the production decorator around
the real body with an enter/exit recorder between them; T6d drives the real
registered `server.session_init`.

Overlap is forced, not hoped for: the first request to enter the init body
blocks in `resolve_session_input` until every other request is provably parked
in the decorator's own wait (its thread's stack shows the single-flight view
calling `wait`), or — with single-flight removed — has entered the body too.

Harness: test_session_init_sleeper_calls.py's tiny universal pool, with two
imported MFL leagues so no Sleeper call is ever needed; StaticPool in-memory
SQLite so every request thread sees the same tables; sockets blocked. The
after-response bg-writes daemon is not started — it is untouched by F5 and
would only add unrelated concurrent DB writes.
"""

import collections
import inspect
import socket
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import request
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import backend.database as db
import backend.server as server
import backend.session_input as session_input
from backend.database import SCORING_FORMATS
from backend.ranking_service import Player

TOKEN = "f5-single-flight-token-do-not-log-me-in-full"
USER_ID = "460238423161040896"
OPP_ID = "733459678624915456"
LEAGUE_A = "mfl:synthetic:a"
LEAGUE_B = "mfl:synthetic:b"
JOIN_S = 30


class _SwapSpy(dict):
    """The token's session dict; records each init's swap (thread, services)."""

    def __init__(self, swaps, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._swaps = swaps

    def update(self, *args, **kwargs):
        payload = dict(*args, **kwargs)
        if "services" in payload:
            self._swaps.append((threading.current_thread().name, payload["services"]))
        super().update(*args, **kwargs)


@pytest.fixture()
def world(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)

    def denied(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(server, "_sleeper_get", denied)

    pool = [Player(f"p{i}", f"P{i}", "RB", "AAA", 25, 1) for i in (1, 2)]
    seed = {p.id: 1500.0 for p in pool}
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format",
                        {fmt: {"players": pool, "seed": seed} for fmt in SCORING_FORMATS})
    monkeypatch.setattr(server, "g_universal_players", pool)
    monkeypatch.setattr(server, "_kickoff_trade_job", MagicMock())
    monkeypatch.setattr(server, "_session_init_inflight", {})
    monkeypatch.setitem(server.app.config, "TESTING", True)

    real_thread = server.threading.Thread

    class _NoBgWrites(real_thread):
        def start(self):
            if self.name != "session-init-bg-writes":
                super().start()

    monkeypatch.setattr(server.threading, "Thread", _NoBgWrites)

    built = []

    class _CountingRankingService(server.RankingService):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            built.append(self)

    monkeypatch.setattr(server, "RankingService", _CountingRankingService)

    order = []          # ("enter" | "exit", league_id) per init-body run
    real_body = inspect.unwrap(server.session_init)

    def recording_body():
        body = request.get_json(silent=True)
        league = body.get("league_id") if isinstance(body, dict) else None
        order.append(("enter", league))
        try:
            return real_body()
        finally:
            order.append(("exit", league))

    view = _install_view(monkeypatch, recording_body)

    for league in (LEAGUE_A, LEAGUE_B):
        with engine.begin() as conn:
            conn.execute(db.leagues_table.insert().values(
                sleeper_league_id=league, user_id=USER_ID,
                name=f"Imported {league}", platform="mfl"))
        db.upsert_league_members(league, [
            {"user_id": USER_ID, "username": "Me", "player_ids": ["p1"]},
            {"user_id": OPP_ID, "username": "Opp", "player_ids": ["p2"]},
        ])

    swaps = []
    # last_active=now throttles the before_request activity write, so the
    # racing requests touch no DB before the init body.
    sess = _SwapSpy(swaps, user_id=USER_ID, verified=True, last_active=time.time())
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        yield SimpleNamespace(built=built, order=order, swaps=swaps,
                              view_name=view.__code__.co_name)
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
        engine.dispose()


def _install_view(monkeypatch, body_fn):
    """Register the production single-flight decorator around body_fn."""
    view = server._single_flight_session_init(body_fn)
    monkeypatch.setitem(server.app.view_functions, "session_init", view)
    return view


def _body(league_id):
    return {"user_id": USER_ID, "league_id": league_id}


def _post(body, token=TOKEN):
    headers = {"X-Session-Token": token} if token else {}
    return server.app.test_client().post("/api/session/init", headers=headers, json=body)


def _parked_in_single_flight(thread, view_name):
    """True when `thread` is blocked in the wait the single-flight view calls."""
    frame = sys._current_frames().get(thread.ident)
    names = []
    while frame is not None:
        names.append(frame.f_code.co_name)
        frame = frame.f_back
    if view_name not in names:
        return False
    at = names.index(view_name)
    return at > 0 and names[at - 1] == "wait"


def _race(world, monkeypatch, bodies, fail_first=False):
    """POST bodies (name → body) concurrently on TOKEN with the overlap forced.

    Returns (responses by thread name, thread names in init-body entry order).
    """
    lock, entered, release = threading.Lock(), [], threading.Event()
    real_resolve = session_input.resolve_session_input

    def gated_resolve(*args, **kwargs):
        with lock:
            first = not entered
            entered.append(threading.current_thread().name)
        assert release.wait(10), "gate never released"
        if first and fail_first:
            raise RuntimeError("synthetic leader failure")
        return real_resolve(*args, **kwargs)

    monkeypatch.setattr(session_input, "resolve_session_input", gated_resolve)

    barrier = threading.Barrier(len(bodies))
    responses = {}

    def worker(body):
        barrier.wait(5)
        try:
            responses[threading.current_thread().name] = _post(body)
        except BaseException as exc:  # surfaced by the asserts below
            responses[threading.current_thread().name] = exc

    threads = [threading.Thread(target=worker, args=(body,), name=name, daemon=True)
               for name, body in bodies.items()]
    for t in threads:
        t.start()
    deadline = time.monotonic() + 10
    while not release.is_set():
        with lock:
            snapshot = list(entered)
        if snapshot:
            others = [t for t in threads if t.name not in snapshot]
            if all(_parked_in_single_flight(t, world.view_name) for t in others):
                release.set()
                break
        assert time.monotonic() < deadline, f"overlap never reached; entered={snapshot}"
        time.sleep(0.002)
    for t in threads:
        t.join(JOIN_S)
    assert [t.name for t in threads if t.is_alive()] == [], "a request hung"
    assert [r for r in responses.values() if isinstance(r, BaseException)] == []
    return responses, entered


# ---------------------------------------------------------------------------
# T6a — identical requests coalesce onto one init
# ---------------------------------------------------------------------------

def test_t6a_identical_inits_coalesce(world, monkeypatch, caplog):
    caplog.set_level("INFO", logger="trade_finder")
    responses, entered = _race(world, monkeypatch, {"A": _body(LEAGUE_A), "B": _body(LEAGUE_A)})

    assert [r.status_code for r in responses.values()] == [200, 200]
    builds = collections.Counter(s._scoring_format for s in world.built)
    installed = [svcs for _, svcs in world.swaps]
    assert {"builds_per_format": dict(builds),
            "distinct_services_installed": len({id(s) for s in installed})} == {
        "builds_per_format": {fmt: 1 for fmt in SCORING_FORMATS},
        "distinct_services_installed": 1}
    # Only the leader swapped; the follower's response is the leader's replay,
    # so both responses observed the services the session finally holds.
    final = server._sessions[TOKEN]["services"]
    assert [name for name, _ in world.swaps] == [entered[0]]
    assert installed[0] is final
    assert responses["A"].get_data() == responses["B"].get_data()
    assert responses["A"].get_json()["token"] == TOKEN
    assert world.order == [("enter", LEAGUE_A), ("exit", LEAGUE_A)]
    assert server._session_init_inflight == {}

    coalesced = [r.getMessage() for r in caplog.records if "coalesced" in r.getMessage()]
    assert len(coalesced) == 1
    assert TOKEN not in coalesced[0] and TOKEN[:6] in coalesced[0]


# ---------------------------------------------------------------------------
# T6b — a different league for the same token runs after, never alongside
# ---------------------------------------------------------------------------

def test_t6b_different_league_runs_after_the_leader(world, monkeypatch):
    responses, entered = _race(world, monkeypatch, {"A": _body(LEAGUE_A), "B": _body(LEAGUE_B)})

    assert {name: (r.status_code, r.get_json().get("league_id"))
            for name, r in responses.items()} == {
        "A": (200, LEAGUE_A), "B": (200, LEAGUE_B)}
    first = LEAGUE_A if entered[0] == "A" else LEAGUE_B
    second = LEAGUE_B if first == LEAGUE_A else LEAGUE_A
    assert world.order == [("enter", first), ("exit", first),
                           ("enter", second), ("exit", second)]
    assert server._sessions[TOKEN]["league"].league_id == second
    assert server._session_init_inflight == {}


# ---------------------------------------------------------------------------
# T6c — a leader that raises never strands its follower
# ---------------------------------------------------------------------------

def test_t6c_leader_error_releases_follower(world, monkeypatch):
    responses, entered = _race(world, monkeypatch, {"A": _body(LEAGUE_A), "B": _body(LEAGUE_A)},
                               fail_first=True)

    leader, follower = entered[0], ("B" if entered[0] == "A" else "A")
    assert responses[leader].status_code == 500
    assert responses[follower].status_code == 200
    assert responses[follower].get_json()["ok"] is True
    assert responses[follower].get_json()["league_id"] == LEAGUE_A
    # The follower ran its own init after the leader's failed one.
    assert world.order == [("enter", LEAGUE_A), ("exit", LEAGUE_A)] * 2
    assert [name for name, _ in world.swaps] == [follower]
    assert server._session_init_inflight == {}


def test_t6c_stuck_leader_times_out_to_own_init(world, monkeypatch):
    """Past the wait bound the follower takes over; the stuck leader's cleanup
    must not evict the follower's in-flight entry."""
    monkeypatch.setattr(server, "_SESSION_INIT_WAIT_S", 0.05)
    gates = {name: (threading.Event(), threading.Event()) for name in ("leader", "follower")}

    def fake_impl():
        name = threading.current_thread().name
        entered, go = gates[name]
        entered.set()
        assert go.wait(10)
        return server.jsonify({"ran": name})

    _install_view(monkeypatch, fake_impl)
    results = {}

    def run():
        results[threading.current_thread().name] = _post(_body(LEAGUE_A)).get_json()

    threads = {name: threading.Thread(target=run, name=name, daemon=True) for name in gates}
    threads["leader"].start()
    assert gates["leader"][0].wait(5)
    threads["follower"].start()
    assert gates["follower"][0].wait(5)          # timed out, now running its own init

    gates["leader"][1].set()
    threads["leader"].join(JOIN_S)
    assert results["leader"] == {"ran": "leader"}
    [entry] = server._session_init_inflight.values()   # the follower's, still in flight
    assert not entry["done"].is_set()

    gates["follower"][1].set()
    threads["follower"].join(JOIN_S)
    assert results["follower"] == {"ran": "follower"}
    assert server._session_init_inflight == {}


# ---------------------------------------------------------------------------
# T6d — a lone caller is unchanged
# ---------------------------------------------------------------------------

def test_t6d_single_caller_matches_the_body_byte_for_byte(world, monkeypatch):
    # The real registered view, not the fixture's recording rebuild.
    monkeypatch.setitem(server.app.view_functions, "session_init", server.session_init)
    [rule] = [r for r in server.app.url_map.iter_rules() if r.rule == "/api/session/init"]
    assert rule.endpoint == "session_init"

    resp = _post(_body(LEAGUE_A))
    assert resp.status_code == 200
    assert server._session_init_inflight == {}

    with server.app.test_request_context("/api/session/init", method="POST",
                                         json=_body(LEAGUE_A),
                                         headers={"X-Session-Token": TOKEN}):
        direct = server.app.make_response(server.session_init.__wrapped__())

    assert (direct.status_code, direct.headers.get("Content-Type"), direct.get_data()) == (
        resp.status_code, resp.headers.get("Content-Type"), resp.get_data())
    builds = collections.Counter(s._scoring_format for s in world.built)
    assert builds == {fmt: 1 for fmt in SCORING_FORMATS}


@pytest.mark.parametrize("token, body, status, error", [
    ("", _body(LEAGUE_A), 401, "session_expired"),   # no token → no single-flight
    (TOKEN, [1], 400, "invalid_body"),               # non-object body → no single-flight
], ids=["no-token", "non-object-body"])
def test_t6d_bypass_paths_are_unchanged(world, token, body, status, error):
    resp = _post(body, token=token)
    assert (resp.status_code, resp.get_json()["error"]) == (status, error)
    assert server._session_init_inflight == {}
