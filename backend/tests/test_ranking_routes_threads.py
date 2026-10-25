"""E1 (gthread readiness) — ranking routes keep mutate -> persist -> publish atomic.

Plan: docs/plans/e1-concurrency/scope.md; finding F1c/F1d in
docs/plans/org-bringup/e1-concurrency-audit.md. The tier-save route holds the
session RankingService's RLock from apply_tiers through save_tier_overrides and
the member_rankings publish, so a publish can never mix two board states and
the stored override blob always equals the in-memory one.

T3 test_tier_saves_swipes_and_reads_stay_consistent — per round, one Flask
test client per thread, released by one Barrier: /api/tiers/save for QB and
for RB, 4x /api/trades/swipe, and a /api/rankings loop. A wrapper around
_publish_member_rankings_for_trade_refresh snapshots the service's swipe logs
and overrides AT CALL TIME. Asserts: every response 200; stored overrides equal
in-memory; each publish payload equals a recompute from its own snapshot; the
last publish holds both tier saves; 4 swipe_decisions rows; _version moved by 6.
Swipes never publish, so the final member_rankings is NOT compared with the
final in-memory board (that would fail on a correct build).

T3b test_tier_publish_cannot_straddle_a_swipe — deterministic: the tier save
is parked (bounded Event wait) between its board read and its publish while a
swipe is fired into that window. Proves the ROUTE span, not just method locks.

Sabotage record (run 2026-10-22, red observed, reverted, green):
  S1  RankingService lock -> contextlib.nullcontext() in __init__ (disables
      method locks AND route spans): T3b RED 5/5 runs; T3 RED 3/5 runs at
      20 rounds (non-200 /api/rankings: get_rankings raised mid-tier-save).
      A free race is red in only ~5% of rounds here (4 of ~120 measured), so
      T3 is the integration check and T3b is the reliable red.
  S2  tiers-save route `with service._lock:` -> nullcontext (method locks
      kept): T3b RED 3/3 runs; T3 green (readers stay safe on method locks).

DB: a per-test SQLite FILE under tmp_path (as test_trade_job_admission.py does):
`sqlite:///:memory:` uses SingletonThreadPool, so each thread would get its own
empty database. Network is blocked at socket.connect.
"""
import random
import socket
import sys
import threading
import weakref
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, func, select

import backend.database as db
import backend.feature_flags as ff
import backend.server as server
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeCard, TradeService

FMT = "1qb_ppr"
LEAGUE = "e1-routes-league"
OPP = "e1-routes-opponent"
ROUNDS = 20
JOIN_S = 60

MINE, THEIRS = ["q3", "q4", "r3", "r4"], ["q5", "q6", "r5", "r6"]
NAMED = [f"q{i}" for i in range(1, 7)] + [f"r{i}" for i in range(1, 7)]
SEED = {pid: 1420.0 + 17.0 * i for i, pid in enumerate(NAMED)}
POS = {pid: "QB" if pid[0] == "q" else "RB" for pid in NAMED}
# A realistic board (300 more players, 3,000 replayed rank swipes among them)
# so a full-board compute takes long enough for requests to overlap inside it.
_rng = random.Random(20261022)
FILLERS = [f"f{i:03d}" for i in range(300)]
SEED.update({pid: _rng.uniform(1160.0, 1960.0) for pid in FILLERS})
POS.update({pid: ("QB", "RB")[i % 2] for i, pid in enumerate(FILLERS)})
HISTORY = [{"winner_player_id": w, "loser_player_id": l, "decision_type": "rank",
            "k_factor": 32.0, "created_at": "2026-10-01T00:00:00+00:00"}
           for w, l in (_rng.sample(FILLERS, 2) for _ in range(3000))]
# One player per tier, so each pin lands at that band's max (apply_tiers n=1).
SAVES = {"QB": ({"firsts_2": ["q1"], "third": ["q2"]}, {"q1": 1864.0, "q2": 1365.0}),
         "RB": ({"firsts_3": ["r1"], "fourth": ["r2"]}, {"r1": 1922.0, "r2": 1275.0})}
# Pinned players never appear on a card, so their published Elo is the pin.
CARDS = [("t1", "q3", "q5", "like"), ("t2", "r3", "r5", "pass"),
         ("t3", "q4", "q6", "like"), ("t4", "r4", "r6", "pass")]


@pytest.fixture
def fast_switch():
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        yield
    finally:
        sys.setswitchinterval(old)


def _pool():
    return [Player(id=pid, name=pid.upper(), position=POS[pid], team="AAA", age=25)
            for pid in SEED]


def _fresh_service():
    svc = RankingService(players=_pool(), seed_ratings=dict(SEED))
    svc._scoring_format = FMT
    return svc


@pytest.fixture
def world(tmp_path, monkeypatch, fast_switch):
    def blocked(*args, **kwargs):
        raise AssertionError("network forbidden in E1 route test")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    engine = create_engine("sqlite:///" + str(tmp_path / "e1-routes.sqlite3"),
                           connect_args={"check_same_thread": False, "timeout": 30})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(ff, "_flags_cache", {k: False for k in ff.DEFAULT_FLAGS})
    monkeypatch.setattr(server, "is_enabled", lambda key: False)
    monkeypatch.setattr(server, "_trade_jobs", {})
    monkeypatch.setattr(server, "_trade_jobs_by_key", {})
    monkeypatch.setattr(server, "_trade_input_epochs", weakref.WeakValueDictionary())
    for name in ("record_event", "touch_user_activity", "create_notification",
                 "_send_typed_push"):
        monkeypatch.setattr(server, name, Mock())
    # /api/rankings enrichments read the universal pool; not under test here.
    monkeypatch.setattr(server, "_consensus_pos_ranks", lambda fmt: ({}, {}))
    monkeypatch.setattr(server, "load_community_elo_for_league", Mock(return_value={}))
    publishes: list = []
    current: dict = {}
    original_publish = server._publish_member_rankings_for_trade_refresh

    def recording_publish(*, user_id, **kwargs):
        svc = current["svc"]
        publishes.append({
            "version": svc._version,
            "rankings": [dict(r) for r in kwargs["rankings"]],
            "comparison_counts": dict(kwargs.get("comparison_counts") or {}),
            "swipes": list(svc._swipes),
            "trade_swipes": list(svc._trade_swipes),
            "overrides": dict(svc._elo_overrides),
            "override_at": dict(svc._elo_override_at),
        })
        return original_publish(user_id=user_id, **kwargs)

    monkeypatch.setattr(server, "_publish_member_rankings_for_trade_refresh",
                        recording_publish)
    server.app.config["TESTING"] = True
    tokens: list = []
    yield {"engine": engine, "publishes": publishes, "current": current, "tokens": tokens}
    with server._sessions_lock:
        for token in tokens:
            server._sessions.pop(token, None)
    engine.dispose()


def _install_round(world, round_no):
    user, token = f"e1-routes-user-{round_no}", f"e1-routes-token-{round_no}"
    with world["engine"].begin() as conn:
        conn.execute(db.users_table.insert().values(
            sleeper_user_id=user, created_at="2026-10-22T00:00:00+00:00"))
    pool = _pool()
    svc = _fresh_service()
    svc.replay_from_db(HISTORY)
    trades = TradeService({p.id: p for p in pool})
    league = League(LEAGUE, "E1 League", "sleeper", [
        LeagueMember(user, "Me", list(MINE), {}),
        LeagueMember(OPP, "Opp", list(THEIRS), {})])
    trades.add_league(league)
    for trade_id, give, receive, _ in CARDS:
        trades._trade_cards[trade_id] = TradeCard(
            trade_id=trade_id, league_id=LEAGUE, proposing_user_id=user,
            target_user_id=OPP, target_username="opp", give_player_ids=[give],
            receive_player_ids=[receive], mismatch_score=0.0, fairness_score=0.0,
            composite_score=0.0)
    sess = dict(user_id=user, league_user_id=user, verified=True, league=league,
                user_roster=list(MINE), players=pool, services={FMT: svc},
                trade_svcs={FMT: trades}, service=svc, trade_svc=trades,
                active_format=FMT, last_active=0)
    with server._sessions_lock:
        server._sessions[token] = sess
    world["tokens"].append(token)
    world["current"]["svc"] = svc
    world["publishes"].clear()
    return user, token, svc


def _recompute(snapshot):
    svc = _fresh_service()
    svc._swipes = list(snapshot["swipes"])
    svc._trade_swipes = list(snapshot["trade_swipes"])
    svc._elo_overrides = dict(snapshot["overrides"])
    svc._elo_override_at = dict(snapshot["override_at"])
    board = {rp.player.id: rp.elo for rp in svc.get_rankings(position=None).rankings}
    return board, svc.comparison_counts()


def _run_round(world, round_no):
    user, token, svc = _install_round(world, round_no)
    v0 = svc._version
    headers = {"X-Session-Token": token}
    jobs = [("POST", "/api/tiers/save", {"position": pos, "tiers": SAVES[pos][0]})
            for pos in ("QB", "RB")]
    jobs += [("POST", "/api/trades/swipe", {"trade_id": t, "decision": d})
             for t, _, _, d in CARDS]
    start = threading.Barrier(len(jobs) + 1)
    writers_done = threading.Event()
    results: list = []

    def send(method, path, body):
        client = server.app.test_client()
        try:
            start.wait(timeout=10)
            resp = client.open(path, method=method, json=body, headers=headers)
            results.append((path, resp.status_code, resp.get_data(as_text=True)[:200]))
        except BaseException as exc:          # noqa: BLE001 — surfaced below
            results.append((path, "exception", repr(exc)))

    def read_loop():
        client = server.app.test_client()
        try:
            start.wait(timeout=10)
            while not writers_done.is_set():
                resp = client.get("/api/rankings", headers=headers)
                results.append(("/api/rankings", resp.status_code, ""))
        except BaseException as exc:          # noqa: BLE001
            results.append(("/api/rankings", "exception", repr(exc)))

    writers = [threading.Thread(target=send, args=job) for job in jobs]
    reader = threading.Thread(target=read_loop)
    for t in writers + [reader]:
        t.start()
    for t in writers:
        t.join(timeout=JOIN_S)
    writers_done.set()
    reader.join(timeout=JOIN_S)
    assert not any(t.is_alive() for t in writers + [reader]), "request thread hung"

    bad = [r for r in results if r[1] != 200]
    assert bad == [], f"round {round_no}: non-200 responses {bad}"
    assert db.load_tier_overrides(user, scoring_format=FMT) == svc._elo_overrides

    publishes = world["publishes"]
    assert len(publishes) == 2                          # one per tier save
    for snap in publishes:
        board, counts = _recompute(snap)
        assert {r["player_id"]: r["elo"] for r in snap["rankings"]} == board, \
            f"round {round_no}: torn publish at version {snap['version']}"
        assert snap["comparison_counts"] == counts
    last = {r["player_id"]: r["elo"] for r in publishes[-1]["rankings"]}
    for pos in ("QB", "RB"):
        for pid, pinned in SAVES[pos][1].items():
            assert last[pid] == pinned, f"round {round_no}: last publish lacks {pos} save"

    with world["engine"].connect() as conn:
        rows = conn.execute(select(func.count()).select_from(db.swipe_decisions_table)
                            .where(db.swipe_decisions_table.c.user_id == user)).scalar()
    assert rows == len(CARDS)
    assert svc._version == v0 + len(jobs)


def test_tier_saves_swipes_and_reads_stay_consistent(world):
    for round_no in range(ROUNDS):
        _run_round(world, round_no)


def test_tier_publish_cannot_straddle_a_swipe(world, monkeypatch):
    """T3b, deterministic: open the tier save's window between its board read
    and its publish, and fire a swipe into it. Under the route lock the swipe
    waits, so the publish matches its own snapshot; without it the swipe lands
    and the payload no longer matches the service it was published from."""
    user, token, svc = _install_round(world, 99)
    v0 = svc._version
    headers = {"X-Session-Token": token}
    window_open, swipe_landed = threading.Event(), threading.Event()
    tier_thread: dict = {}
    original_conf = server._ranking_confidence
    original_signal = svc.record_trade_signal

    def conf_with_window(*args, **kwargs):
        # Called after get_rankings(None) and before the publish.
        if threading.get_ident() == tier_thread.get("id") and not window_open.is_set():
            window_open.set()
            swipe_landed.wait(timeout=0.25)     # times out when the lock holds
        return original_conf(*args, **kwargs)

    def signal_then_flag(*args, **kwargs):
        result = original_signal(*args, **kwargs)
        swipe_landed.set()
        return result

    monkeypatch.setattr(server, "_ranking_confidence", conf_with_window)
    svc.record_trade_signal = signal_then_flag
    results: list = []

    def tier_save():
        tier_thread["id"] = threading.get_ident()
        resp = server.app.test_client().post(
            "/api/tiers/save", json={"position": "QB", "tiers": SAVES["QB"][0]},
            headers=headers)
        results.append(("tiers", resp.status_code))

    def swipe():
        if window_open.wait(timeout=10):
            resp = server.app.test_client().post(
                "/api/trades/swipe", json={"trade_id": "t1", "decision": "like"},
                headers=headers)
            results.append(("swipe", resp.status_code))

    threads = [threading.Thread(target=tier_save), threading.Thread(target=swipe)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=JOIN_S)
    assert not any(t.is_alive() for t in threads), "request thread hung"
    assert sorted(results) == [("swipe", 200), ("tiers", 200)]
    assert svc._version == v0 + 2

    [snap] = world["publishes"]
    board, counts = _recompute(snap)
    assert {r["player_id"]: r["elo"] for r in snap["rankings"]} == board, \
        "publish straddled a swipe"
    assert snap["comparison_counts"] == counts
