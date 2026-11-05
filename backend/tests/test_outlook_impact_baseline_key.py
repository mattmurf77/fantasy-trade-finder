"""`_outlook_impact_baseline`'s cache key (#357, found in QA review 2026-11-03).

`_OUTLOOK_IMPACT_CACHE` holds one baseline bundle per league for 15 minutes,
and SHARING it is the performance design: the 30-card deck pays one baseline
sim instead of 30 (see the comment block above the cache in `server.py`). But
the bundle is built from inputs read off the CALLING session, so any of them
that can differ between two callers in one league has to be in the key, or
caller B is served a bundle built from caller A's session:

  * the board, on `basis=personal` — `sess["service"].get_rankings()`;
  * the scoring format — `_active_format(sess)`, which is per session
    (`active_format`, flipped by `/api/scoring/switch`) and per request
    (`X-Scoring-Format`), never per league;
  * the pool the session's services and players were built from. A session
    initialised before a players-refresh keeps the old pool's seed and player
    list until its next `/api/session/init`, and the baseline reads both
    (`svc_seed`, `sess["players"]`), so a player the refresh dropped is still
    priced for that caller and priced at 0 for a fresh one.

Each repro test computes caller B's bundle ALONE first (the ground truth), then
lets caller A warm the cache and asks again as B. Sleeper, the universal pool,
the league-context lookup and `get_config` are all faked; the simulator runs
for real, at `DELTA_SIM_COUNT`, exactly as the two consumers call it.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

import backend.outlook.trade_delta as trade_delta
import backend.server as server

LEAGUE_ID = "880011223344"
_PLAYED_WEEKS = (1, 2)
_REGULAR_WEEKS = 4
GONE = "p_gone"      # rostered on team 1; dropped from the pool by a refresh

_POSITIONS = {**{f"q{r}": "QB" for r in range(1, 5)},
              **{f"r{r}": "RB" for r in range(1, 5)}}


def _seed(fmt: str) -> dict[str, float]:
    """Format-dependent consensus: SF prices every QB far higher."""
    qb_base = 1800.0 if fmt == "sf_tep" else 1400.0
    out: dict[str, float] = {}
    for r in range(1, 5):
        out[f"q{r}"] = qb_base + 40.0 * r
        out[f"r{r}"] = 1500.0 + 60.0 * (5 - r)
    return out


def _players() -> list:
    return [SimpleNamespace(id=pid, position=pos) for pid, pos in _POSITIONS.items()]


def _fake_sleeper(url: str, timeout: int = 15):
    path = url.split("/v1/", 1)[1]
    if path == f"league/{LEAGUE_ID}":
        return {"season": "2026",
                "settings": {"playoff_week_start": _REGULAR_WEEKS + 1,
                             "playoff_teams": 2},
                "roster_positions": ["QB", "RB", "BN"]}
    if path == f"league/{LEAGUE_ID}/rosters":
        return [{"roster_id": r, "owner_id": f"u{r}",
                 "players": [f"q{r}", f"r{r}"] + ([GONE] if r == 1 else []),
                 "starters": [f"q{r}", f"r{r}"],
                 "settings": {"wins": 1, "losses": 1, "ties": 0, "fpts": 200}}
                for r in range(1, 5)]
    if path == f"league/{LEAGUE_ID}/users":
        return [{"user_id": f"u{r}", "display_name": f"user{r}",
                 "metadata": {"team_name": f"Team {r}"}} for r in range(1, 5)]
    m = re.match(rf"league/{LEAGUE_ID}/matchups/(\d+)$", path)
    if m:
        pts = 100.0 if int(m.group(1)) in _PLAYED_WEEKS else 0.0
        return [{"roster_id": r, "matchup_id": (r + 1) // 2, "points": pts}
                for r in range(1, 5)]
    raise AssertionError(f"unexpected Sleeper URL in test: {url}")


class _Service:
    """The two things the baseline reads off a RankingService."""

    def __init__(self, seed: dict, board: dict | None = None):
        self._seed = seed
        self._board = board or {}

    def get_rankings(self, position=None):
        return SimpleNamespace(rankings=[
            SimpleNamespace(player=SimpleNamespace(id=pid), elo=elo)
            for pid, elo in self._board.items()])


def _sess(user_id: str, *, fmt: str = "1qb_ppr", board: dict | None = None,
          seed: dict | None = None, players: list | None = None,
          generation: int = 2, league_user_id: str | None = None):
    """A request-local view, built the way `_require_session` builds one."""
    src = {
        "user_id": user_id,
        "league_user_id": league_user_id or user_id,
        "active_format": fmt,
        "services": {fmt: _Service(seed if seed is not None else _seed(fmt), board)},
        "players": players if players is not None else _players(),
        "pool_generation": generation,
    }
    return server._RequestSession(src, fmt)


def _clear() -> None:
    with server._OUTLOOK_IMPACT_LOCK:
        server._OUTLOOK_IMPACT_CACHE.clear()


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setattr(server, "_sleeper_get", _fake_sleeper)
    monkeypatch.setattr(server, "_get_universal_pool",
                        lambda fmt: (_players(), _seed(fmt)))
    monkeypatch.setattr(server, "get_league_draft_context",
                        lambda lid: {"platform": "sleeper"})
    monkeypatch.setattr(server, "get_config", lambda: {})
    server._outlook_cache_clear()
    _clear()
    yield
    _clear()
    server._outlook_cache_clear()


def _baseline(sess, basis: str = "consensus"):
    return server._outlook_impact_baseline(LEAGUE_ID, basis, sess)


def _alone(sess, basis: str = "consensus"):
    """This caller's bundle with nobody else in the cache: the ground truth."""
    _clear()
    bundle = _baseline(sess, basis)
    _clear()
    return bundle


def _odds(bundle) -> list:
    return [(t["roster_id"], t["odds"]) for t in bundle[1]["teams"]]


# ---------------------------------------------------------------------------
# (a) personal basis — the board
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("co_owners", [False, True],
                         ids=["league_mates", "co_owners_of_one_roster"])
def test_personal_bundle_is_built_from_the_callers_own_board(co_owners):
    """Co-owners share a LEAGUE identity but each ranks their own board, so
    the board's owner is the ACCOUNT id (backend/CLAUDE.md § Identity)."""
    a = _sess("acctA", league_user_id="u1",
              board={"q1": 2100.0, "r1": 1100.0, "q2": 1100.0})
    b = _sess("acctB", league_user_id="u1" if co_owners else "u2",
              board={"q1": 1100.0, "r1": 2100.0, "q2": 2100.0})
    want_b = _alone(b, "personal")
    assert _alone(a, "personal")[2] != want_b[2], "precondition: boards differ"

    _baseline(a, "personal")
    got_b = _baseline(b, "personal")
    assert got_b[2] == want_b[2], "B was served A's board"
    assert _odds(got_b) == _odds(want_b)


# ---------------------------------------------------------------------------
# (b) scoring format
# ---------------------------------------------------------------------------

def test_bundle_is_built_in_the_callers_own_scoring_format():
    a = _sess("u1", fmt="1qb_ppr")
    b = _sess("u2", fmt="sf_tep")
    want_b = _alone(b)
    assert want_b[5] == "sf_tep"
    assert _alone(a)[2] != want_b[2], "precondition: formats price differently"

    _baseline(a)
    got_b = _baseline(b)
    assert got_b[5] == "sf_tep", "B was served A's format"
    assert got_b[2] == want_b[2]
    assert _odds(got_b) == _odds(want_b)


# ---------------------------------------------------------------------------
# (c) the pool generation behind the session's seed and players
# ---------------------------------------------------------------------------

def test_bundle_is_built_from_the_callers_own_pool_generation():
    """A was initialised at generation 1, when `GONE` was in the pool; a
    players-refresh then dropped it and bumped to generation 2, where B was
    initialised. Same league, same format, consensus basis."""
    a = _sess("u1", generation=1,
              seed={**_seed("1qb_ppr"), GONE: 1700.0},
              players=_players() + [SimpleNamespace(id=GONE, position="WR")])
    b = _sess("u2", generation=2)
    want_a, want_b = _alone(a), _alone(b)
    assert want_a[2][GONE] > 0.0 and want_b[2][GONE] == 0.0, (
        "precondition: the stale session still prices the dropped player")

    _baseline(a)
    got_b = _baseline(b)
    assert got_b[2] == want_b[2], "B was served A's stale pool"
    assert got_b[3] == want_b[3]
    assert _odds(got_b) == _odds(want_b)


# ---------------------------------------------------------------------------
# The sharing the cache exists for
# ---------------------------------------------------------------------------

def test_consensus_callers_in_one_league_and_format_share_one_baseline(monkeypatch):
    """Different people, different boards, consensus basis: one sim, one entry.
    Keying per caller here would cost the deck 30 baselines instead of one."""
    sims: list[int] = []
    real = trade_delta.resim_baseline

    def counting(*a, **k):
        sims.append(1)
        return real(*a, **k)

    monkeypatch.setattr(trade_delta, "resim_baseline", counting)
    a = _sess("u1", board={"q1": 2100.0})
    b = _sess("u2", board={"q1": 1100.0})
    first = _baseline(a)
    second = _baseline(b)
    assert len(sims) == 1, "the baseline must be computed once per league"
    assert second is first
    assert len(server._OUTLOOK_IMPACT_CACHE) == 1


def test_purge_drops_personal_baselines_only():
    a, b = _sess("acctA"), _sess("acctB")
    _baseline(a, "personal")
    kept = _baseline(b, "personal")
    shared = _baseline(a)
    assert server._purge_outlook_impact_callers({"acctA", ""}) == 1
    assert _baseline(b, "personal") is kept
    assert _baseline(b) is shared
    assert {key[3] for key in server._OUTLOOK_IMPACT_CACHE} == {"acctB", None}


@pytest.mark.parametrize("basis", ["personal", "consensus"])
def test_deletion_during_baseline_compute_cannot_refill_personal_cache(monkeypatch, basis):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    started, release = Event(), Event()
    real = trade_delta.resim_baseline

    def blocked(*a, **kw):
        started.set()
        assert release.wait(5), "test did not release simulation"
        return real(*a, **kw)

    monkeypatch.setattr(trade_delta, "resim_baseline", blocked)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_baseline, _sess("acctA"), basis)
        try:
            assert started.wait(5)
            server._purge_outlook_impact_callers({"acctA"})
        finally:
            release.set()
        assert future.result(timeout=5) is not None
    assert bool(server._OUTLOOK_IMPACT_CACHE) == (basis == "consensus")
    assert not server._OUTLOOK_IMPACT_PENDING


def test_failed_baseline_compute_releases_ticket(monkeypatch):
    def fail(*a, **kw):
        raise RuntimeError("synthetic simulation failure")

    monkeypatch.setattr(trade_delta, "resim_baseline", fail)
    with pytest.raises(RuntimeError):
        _baseline(_sess("acctA"), "personal")
    assert not server._OUTLOOK_IMPACT_PENDING
    assert not server._OUTLOOK_IMPACT_CACHE
