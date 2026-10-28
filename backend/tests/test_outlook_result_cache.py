"""GET /api/league/outlook result cache (`backend/outlook_result_cache.py`).

The engine is pure and seeded, so a stored result must be exactly what an
uncached `run_outlook` returns for the same inputs. These tests pin that, the
key's coverage of every input, per-caller `is_you`, single-flight, the bounds,
and that errors are never stored. Unit tests drive the real `run_outlook` on
small crafted leagues; the route tests reuse `test_outlook_route_cache.py`'s
fake Sleeper.
"""

from __future__ import annotations

import json
import threading
import time
from unittest.mock import patch

import pytest

import backend.server as server
from backend import outlook_result_cache as orc
from backend.outlook.league_state import LeagueState, TeamState
from backend.outlook.pipeline import run_outlook
from backend.tests.test_outlook_route_cache import LEAGUE_ID, _fake_sleeper

CFG = {"outlook_sim_count": 400.0, "outlook_seed": 0.0}
_N, _WEEKS = 8, 10


def _league(completed: int = 0) -> LeagueState:
    """A fresh 8-team league, identical on every call (one per "request")."""
    rids = list(range(1, _N + 1))
    arr, rounds = rids[:], []
    for _ in range(_N - 1):
        rounds.append([(arr[i], arr[_N - 1 - i]) for i in range(_N // 2)])
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    teams = [TeamState(
        roster_id=r, user_id=f"u{r}", username=f"user{r}",
        display_name=f"Team {r}", wins=(r * 5) % (completed + 1),
        losses=completed - (r * 5) % (completed + 1),
        points_for=100.0 * completed + r,
        player_ids=[f"p{r}_{i}" for i in range(6)],
        starters=[f"p{r}_{i}" for i in range(4)],
    ) for r in rids]
    return LeagueState(
        league_id="LG-RC", platform="sleeper", season="2026",
        regular_season_weeks=_WEEKS, playoff_slots=4, num_byes=0,
        roster_slots=["QB", "RB", "WR", "FLEX"], teams=teams,
        schedule={w: list(rounds[(w - 1) % len(rounds)])
                  for w in range(1, _WEEKS + 1)},
        completed_weeks=completed,
        weekly_scores={r: [90.0 + r * 4 + w for w in range(completed)]
                       for r in rids},
        status="in_season")


def _inputs(completed: int = 2, **over) -> dict:
    state = _league(completed)
    pos = ("QB", "RB", "WR", "WR", "RB", "TE")
    pv, pp = {}, {}
    for t in state.teams:
        for i, pid in enumerate(t.player_ids):
            pv[pid] = float(100 + (t.roster_id * 7 + i * 13) % 60)
            pp[pid] = pos[i]
    inp = dict(league_id=state.league_id, basis="consensus",
               scoring_format="1qb_ppr", user_id="u1", state=state,
               player_value=pv, player_pos=pp, model_cfg=dict(CFG),
               playoff_seed_type=1, strength_source="auto")
    inp.update(over)
    return inp


def _run(inp: dict, you: str) -> dict:
    """An uncached run — what the route returned before the cache."""
    return run_outlook(
        inp["state"], player_value=inp["player_value"],
        player_pos=inp["player_pos"], model_cfg=inp["model_cfg"],
        basis=inp["basis"], scoring_format=inp["scoring_format"],
        you_user_id=you, playoff_seed_type=inp["playoff_seed_type"])


def _counting(inp: dict, calls: list):
    def compute():
        calls.append(inp["user_id"])
        return _run(inp, you="")       # the route computes caller-independent
    return compute


def _you(payload: dict) -> list[str]:
    return [t["user_id"] for t in payload["teams"] if t["is_you"]]


# ---------------------------------------------------------------------------
# 1 — a hit is byte-identical to an uncached run
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("completed", [0, 2, 5],
                         ids=["roster_value", "blended", "trailing_scores"])
def test_hit_is_byte_identical_to_an_uncached_run(completed):
    cache, calls = orc.OutlookResultCache(), []
    first = _inputs(completed)
    cache.get_or_compute(orc.make_key(**first), _counting(first, calls))
    again = _inputs(completed)          # a fresh request, same league facts
    shared = cache.get_or_compute(orc.make_key(**again), _counting(again, calls))
    assert len(calls) == 1 and cache.stats["hits"] == 1
    for you in ("u3", "u1", "", "not-in-league"):
        got = json.dumps(orc.for_caller(shared, you))
        want = json.dumps(_run(_inputs(completed), you=you))
        assert got == want, f"hit differs from an uncached run for {you!r}"


# ---------------------------------------------------------------------------
# 2 — any change to an input misses and recomputes
# ---------------------------------------------------------------------------

def _swap_players(i):
    a, b = i["state"].teams[0], i["state"].teams[1]
    a.player_ids[0], b.player_ids[0] = b.player_ids[0], a.player_ids[0]


def _record(i):
    t = i["state"].teams[2]
    t.wins, t.losses = t.wins + 1, t.losses - 1


def _schedule(i):
    week = i["state"].completed_weeks + 1
    (a, b), (c, d), *rest = i["state"].schedule[week]
    i["state"].schedule[week] = [(a, c), (b, d), *rest]


MUTATIONS = {
    "roster": _swap_players,
    "record": _record,
    "schedule": _schedule,
    "points_for": lambda i: setattr(i["state"].teams[0], "points_for", 1.5),
    "weekly_scores": lambda i: i["state"].weekly_scores[1].__setitem__(0, 1.0),
    "median_match": lambda i: setattr(i["state"], "median_match", True),
    "playoff_slots": lambda i: setattr(i["state"], "playoff_slots", 6),
    "player_value": lambda i: i["player_value"].__setitem__("p1_0", 1.0),
    "player_pos": lambda i: i["player_pos"].__setitem__("p1_0", "TE"),
    "model_cfg": lambda i: i["model_cfg"].__setitem__("outlook_seed", 7.0),
    "playoff_seed_type": lambda i: i.__setitem__("playoff_seed_type", 0),
    "strength_source": lambda i: i.__setitem__("strength_source", "blended"),
}


@pytest.mark.parametrize("name", list(MUTATIONS))
def test_any_input_change_misses_and_recomputes(name):
    cache, calls = orc.OutlookResultCache(), []
    base = _inputs()
    cache.get_or_compute(orc.make_key(**base), _counting(base, calls))
    changed = _inputs()
    MUTATIONS[name](changed)
    assert orc.make_key(**changed) != orc.make_key(**_inputs())
    cache.get_or_compute(orc.make_key(**changed), _counting(changed, calls))
    assert len(calls) == 2, f"a {name} change was served the old result"


def test_digest_ignores_dict_order_and_handles_sets():
    pv = {"a": 1.0, "b": 2.0}
    assert (orc.input_digest(m=pv, s={"x", "y", "z"})
            == orc.input_digest(m=dict(reversed(pv.items())), s={"z", "y", "x"}))


# ---------------------------------------------------------------------------
# 3 — `is_you` never leaks between callers
# ---------------------------------------------------------------------------

def test_personal_basis_keys_per_caller():
    cache, calls = orc.OutlookResultCache(), []
    out = {}
    for you in ("u1", "u2"):
        inp = _inputs(basis="personal", user_id=you)
        shared = cache.get_or_compute(orc.make_key(**inp), _counting(inp, calls))
        out[you] = orc.for_caller(shared, you)
    assert calls == ["u1", "u2"], "B must never be served A's personal entry"
    assert _you(out["u1"]) == ["u1"] and _you(out["u2"]) == ["u2"]


def test_shared_basis_entry_is_restamped_for_each_caller():
    cache, calls = orc.OutlookResultCache(), []
    out = []
    for you in ("u1", "u2", "u1"):
        inp = _inputs(user_id=you)
        shared = cache.get_or_compute(orc.make_key(**inp), _counting(inp, calls))
        out.append(orc.for_caller(shared, you))
        out[-1]["teams"][0]["odds"]["playoff_pct"] = -1.0   # caller scribbles
    assert calls == ["u1"]
    assert [_you(p) for p in out] == [["u1"], ["u2"], ["u1"]]
    assert not any(t["is_you"] for t in shared["teams"])
    assert shared["teams"][0]["odds"]["playoff_pct"] >= 0.0


# ---------------------------------------------------------------------------
# 4 — single-flight
# ---------------------------------------------------------------------------

def _pile_up(cache, n, compute):
    """n threads cold-miss one key at once; returns (results, errors)."""
    barrier = threading.Barrier(n)
    results, errors = [None] * n, [None] * n

    def worker(i):
        barrier.wait()
        try:
            results[i] = cache.get_or_compute(("k",), compute)
        except Exception as e:   # noqa: BLE001 — collected for the asserts
            errors[i] = e

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    return threads, results, errors


def _wait_coalesced(cache, n, release):
    deadline = time.monotonic() + 2.0
    while cache.stats["coalesced"] < n and time.monotonic() < deadline:
        time.sleep(0.005)
    release.set()


def test_concurrent_cold_misses_compute_once():
    cache, calls, release, n = orc.OutlookResultCache(), [], threading.Event(), 8

    def compute():
        calls.append(1)
        release.wait(5)
        return {"teams": []}

    threads, results, errors = _pile_up(cache, n, compute)
    _wait_coalesced(cache, n - 1, release)
    for t in threads:
        t.join(5)
    assert errors == [None] * n
    assert len(calls) == 1
    assert cache.stats == {"hits": 0, "misses": 1, "coalesced": n - 1, "errors": 0}
    assert all(r is results[0] for r in results)


def test_waiters_on_a_failed_computation_share_the_error_and_nothing_is_cached():
    cache, calls, release, n = orc.OutlookResultCache(), [], threading.Event(), 6

    def compute():
        calls.append(1)
        release.wait(5)
        raise RuntimeError("sim blew up")

    threads, results, errors = _pile_up(cache, n, compute)
    _wait_coalesced(cache, n - 1, release)
    for t in threads:
        t.join(5)
    assert len(calls) == 1
    assert all(isinstance(e, RuntimeError) for e in errors)
    assert cache.get_or_compute(("k",), lambda: {"teams": [], "ok": True})["ok"]
    assert cache.stats["misses"] == 2


# ---------------------------------------------------------------------------
# 5 — bounds: TTL and the entry cap
# ---------------------------------------------------------------------------

def test_module_bounds_are_6h_and_256():
    assert orc.TTL_SECONDS == 6 * 3600 and orc.MAX_ENTRIES == 256
    assert orc.OUTLOOK_RESULTS._ttl == orc.TTL_SECONDS
    assert orc.OUTLOOK_RESULTS._max == orc.MAX_ENTRIES


def test_ttl_expiry_recomputes():
    now = [1000.0]
    cache = orc.OutlookResultCache(ttl_seconds=60, clock=lambda: now[0])
    calls = []

    def compute():
        calls.append(1)
        return {"teams": [], "v": len(calls)}

    cache.get_or_compute(("k",), compute)
    now[0] += 59.9
    assert cache.get_or_compute(("k",), compute)["v"] == 1
    now[0] += 0.2
    assert cache.get_or_compute(("k",), compute)["v"] == 2


def test_cap_evicts_least_recently_used():
    cache, calls = orc.OutlookResultCache(max_entries=3), []

    def get(k):
        return cache.get_or_compute((k,), lambda: calls.append(k) or {"k": k})

    for k in "abc":
        get(k)
    get("a")                  # touch: b is now least recently used
    get("d")                  # over the cap → evicts b
    calls.clear()
    for k in "acd":
        get(k)
    assert calls == []
    get("b")
    assert calls == ["b"]


# ---------------------------------------------------------------------------
# 6 — errors are never cached
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exc", [ValueError("boom"),
                                 NotImplementedError("no espn provider")])
def test_an_error_is_not_cached_and_the_next_call_recomputes(exc):
    cache, calls = orc.OutlookResultCache(), []

    def bad():
        raise exc

    with pytest.raises(type(exc)):
        cache.get_or_compute(("k",), bad)
    assert cache.get_or_compute(("k",), lambda: calls.append(1) or {"ok": 1}) == {"ok": 1}
    assert calls == [1] and cache.stats["errors"] == 1


# ---------------------------------------------------------------------------
# Route level — through the Flask test client
# ---------------------------------------------------------------------------

TOKENS = {"u1": "outlook-result-tok-u1", "u2": "outlook-result-tok-u2"}


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    with server._sessions_lock:
        for uid, tok in TOKENS.items():
            server._sessions[tok] = {
                "user_id": uid, "active_format": "1qb_ppr", "last_active": 0.0,
                "league": None, "players": [], "trade_svc": object()}
    server._outlook_cache_clear()
    try:
        yield server.app.test_client()
    finally:
        with server._sessions_lock:
            for tok in TOKENS.values():
                server._sessions.pop(tok, None)
        server._outlook_cache_clear()


def _requests(client, users):
    import backend.outlook as outlook_pkg
    fake, _log = _fake_sleeper()
    runs = []
    real = outlook_pkg.run_outlook

    def spy(*a, **k):
        runs.append(k.get("you_user_id"))
        return real(*a, **k)

    with patch.object(server, "is_enabled", lambda k: k == "outlook.odds"), \
         patch.object(server, "_sleeper_get", fake), \
         patch.object(server, "_get_universal_pool", lambda fmt: ([], {})), \
         patch.object(outlook_pkg, "run_outlook", spy):
        out = [client.get(f"/api/league/outlook?league_id={LEAGUE_ID}",
                          headers={"X-Session-Token": TOKENS[u]})
               for u in users]
    for r in out:
        assert r.status_code == 200, r.get_data(as_text=True)
    return out, runs


def test_route_runs_the_sim_once_for_two_identical_requests(client):
    (r1, r2), runs = _requests(client, ["u1", "u1"])
    assert runs == [""], "second request must be a hit, computed caller-free"
    assert r1.get_data() == r2.get_data()
    assert _you(r1.get_json()) == ["u1"]


def test_route_restamps_is_you_for_a_second_caller_on_a_hit(client):
    (ra, rb), runs = _requests(client, ["u1", "u2"])
    assert len(runs) == 1
    a, b = ra.get_json(), rb.get_json()
    assert _you(a) == ["u1"] and _you(b) == ["u2"]
    for t in a["teams"] + b["teams"]:
        t.pop("is_you")
    assert a == b
