"""#151 — GET /api/league/free-agents exclusion-set construction (route layer).

The pure ranking rules live in test_free_agents.py; this file pins the ROUTE's
roster-exclusion wiring, which is where #151 lived: session-init filters every
in-session roster against the DEFAULT (1qb_ppr) pool (`if str(x) in
players_dict`), so a rostered player who exists only in the ACTIVE format's
pool (e.g. a low-end QB with an SF value but a zero 1QB value) was missing
from the exclusion set and surfaced as a "free agent". The fix unions the RAW
league_members snapshot (client-sent ids, unfiltered) into the exclusion set
and stores the caller's own row raw at session init.

Harness: Flask test client + injected initialized session (pattern from
test_verified_reads.py), `_get_universal_pool` and `load_league_members`
patched at the server module — no network, no real DB.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import backend.server as server
from backend.ranking_service import Player
from backend.trade_service import League, LeagueMember

UID = "u_fa_route"
TOKEN = "sess-fa-route-tok"
LEAGUE_ID = "L_fa_route"


def _p(pid, position):
    return Player(id=pid, name=pid, position=position, team="FA", age=25)


# Active-format (sf_tep) pool: includes qb_sf_only, which the default
# 1qb_ppr pool does NOT contain — the #151 trigger shape.
SF_POOL = [_p("qb_sf_only", "QB"), _p("qb1", "QB"), _p("rb1", "RB"),
           _p("wr1", "WR"), _p("te1", "TE")]
SF_SEED = {p.id: 1500.0 for p in SF_POOL}


class _FakeRankSet(SimpleNamespace):
    pass


class _FakeService:
    def get_rankings(self, position=None):
        return _FakeRankSet(rankings=[])


@pytest.fixture()
def client():
    # In-session league: the opponent ROSTERS qb_sf_only in real life, but
    # session init filtered it out (not in the 1qb pool) — the member object
    # only carries rb1. The RAW DB snapshot below still has it.
    league = League(
        league_id=LEAGUE_ID, name="FA Route League", platform="sleeper",
        members=[LeagueMember(user_id="opp1", username="opp1",
                              roster=["rb1"], elo_ratings={})],
    )
    sess = {
        "user_id":       UID,
        "league":        league,
        "players":       list(SF_POOL),
        "user_roster":   ["wr1"],          # also 1qb-filtered at init
        "service":       _FakeService(),
        "trade_svc":     object(),
        "active_format": "sf_tep",
        "last_active":   0.0,
    }
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        yield c
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


def _get(c, raw_rows, **params):
    """GET the route with the universal pool + DB snapshot patched."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    with patch.object(server, "_get_universal_pool",
                      lambda fmt: (SF_POOL, dict(SF_SEED))), \
         patch.object(server, "load_league_members",
                      MagicMock(return_value=raw_rows)), \
         patch.object(server, "_verified_read_denial", lambda s: None), \
         patch.object(server, "touch_user_activity", MagicMock()):
        return c.get(f"/api/league/free-agents{('?' + q) if q else ''}",
                     headers={"X-Session-Token": TOKEN})


RAW_ROWS = [
    # Caller's own row — stored RAW since the #151 fix (was 1qb-filtered).
    {"user_id": UID,    "username": "me",   "player_ids": ["wr1"]},
    # Opponent's raw roster carries qb_sf_only even though the in-session
    # member object lost it to the default-pool filter.
    {"user_id": "opp1", "username": "opp1", "player_ids": ["rb1", "qb_sf_only"]},
]


def test_rostered_player_outside_default_pool_is_excluded(client):
    """#151 regression: qb_sf_only is rostered (raw snapshot) but absent
    from the in-session member roster — it must NOT appear as a free agent."""
    r = _get(client, RAW_ROWS)
    assert r.status_code == 200, r.get_json()
    ids = {row["player_id"] for row in r.get_json()["free_agents"]}
    assert "qb_sf_only" not in ids
    # Sanity: session-roster exclusions still hold, true FAs still surface.
    assert "rb1" not in ids and "wr1" not in ids
    assert ids == {"qb1", "te1"}


def test_missing_snapshot_falls_back_to_session_rosters(client):
    """No league_members rows yet (fresh/demo league) → the session-derived
    exclusion set still applies and the route still answers."""
    r = _get(client, [])
    assert r.status_code == 200, r.get_json()
    ids = {row["player_id"] for row in r.get_json()["free_agents"]}
    assert "rb1" not in ids and "wr1" not in ids       # session rosters
    assert "qb_sf_only" in ids                          # nothing raw to add


def test_snapshot_failure_never_errors_the_route(client):
    """A DB error reading the snapshot is best-effort: pre-#151 behavior,
    not a 500."""
    boom = MagicMock(side_effect=RuntimeError("db down"))
    with patch.object(server, "_get_universal_pool",
                      lambda fmt: (SF_POOL, dict(SF_SEED))), \
         patch.object(server, "load_league_members", boom), \
         patch.object(server, "_verified_read_denial", lambda s: None), \
         patch.object(server, "touch_user_activity", MagicMock()):
        r = client.get("/api/league/free-agents",
                       headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200, r.get_json()
