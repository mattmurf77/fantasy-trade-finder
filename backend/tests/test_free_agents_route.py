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


# ═══════════════════════════════════════════════════════════════════════════
# #178 — regression: "free agents still shows rostered players / all players"
#
# Root cause: every pre-#178 exclusion source (in-session rosters AND the
# league_members snapshot) descends from the CLIENT-built session payload,
# and the clients drop rosters whose owner_id is null (a manager left the
# league). The orphaned team's whole roster — the operator's real league has
# one holding Ja'Marr Chase / Bijan Robinson / Jayden Daniels — surfaced at
# the TOP of the FA list. Fix: Sleeper leagues union a LIVE Sleeper rosters
# read (roster-shaped, owner or not); an all-sources-empty exclusion is a
# hard 503, never a full-pool listing.
# ═══════════════════════════════════════════════════════════════════════════

SLEEPER_LEAGUE_ID = "1312140920132497408"   # numeric ⇒ live-read path


def _sleeper_session(league_members, user_roster=("wr1",),
                     league_id=SLEEPER_LEAGUE_ID):
    """An initialized session whose league mirrors what session_init builds
    from the client payload (ownerless rosters already dropped client-side)."""
    return {
        "user_id":       UID,
        "league":        League(league_id=league_id, name="Real League",
                                platform="sleeper", members=list(league_members)),
        "players":       list(SF_POOL),
        "user_roster":   list(user_roster),
        "service":       _FakeService(),
        "trade_svc":     object(),
        "active_format": "sf_tep",
        "last_active":   0.0,
    }


def _get_live(c, raw_rows, live_rosters, *, linked_platform=False,
              league_meta=None, **params):
    """GET the route with pool, snapshot, platform lookup and the live
    Sleeper reads all patched. `live_rosters` may be an Exception instance
    (the live read fails) or a list of Sleeper roster dicts."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    sleeper_get = (MagicMock(side_effect=live_rosters)
                   if isinstance(live_rosters, Exception)
                   else MagicMock(return_value=live_rosters))
    server._FA_LEAGUE_META_CACHE.clear()
    with patch.object(server, "_get_universal_pool",
                      lambda fmt: (SF_POOL, dict(SF_SEED))), \
         patch.object(server, "load_league_members",
                      MagicMock(return_value=raw_rows)), \
         patch.object(server, "is_linked_platform_league",
                      MagicMock(return_value=linked_platform)), \
         patch.object(server, "_sleeper_get", sleeper_get), \
         patch.object(server, "_fetch_sleeper_league_meta",
                      MagicMock(return_value=league_meta)), \
         patch.object(server, "_verified_read_denial", lambda s: None), \
         patch.object(server, "touch_user_activity", MagicMock()):
        resp = c.get(f"/api/league/free-agents{('?' + q) if q else ''}",
                     headers={"X-Session-Token": TOKEN})
    return resp, sleeper_get


@pytest.fixture()
def sleeper_client():
    """Session on a numeric (real-Sleeper) league id. The client payload —
    and therefore BOTH the session league and the snapshot — never saw the
    ownerless roster that holds qb1."""
    sess = _sleeper_session(
        [LeagueMember(user_id="opp1", username="opp1",
                      roster=["rb1"], elo_ratings={})],
    )
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        yield c
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


# Live Sleeper truth: opp1's roster PLUS an ownerless roster holding qb1.
LIVE_ROSTERS = [
    {"roster_id": 1, "owner_id": UID,    "players": ["wr1"]},
    {"roster_id": 2, "owner_id": "opp1", "players": ["rb1"]},
    {"roster_id": 3, "owner_id": None,   "players": ["qb1"]},   # orphaned team
]

SNAPSHOT_ROWS = [
    {"user_id": UID,    "username": "me",   "player_ids": ["wr1"]},
    {"user_id": "opp1", "username": "opp1", "player_ids": ["rb1"]},
]


def test_ownerless_roster_players_are_excluded_for_sleeper_league(sleeper_client):
    """#178 regression: qb1 sits on a roster with owner_id=None — absent
    from the session league AND the snapshot (clients drop ownerless
    rosters) — and must still be excluded via the live Sleeper read."""
    r, _ = _get_live(sleeper_client, SNAPSHOT_ROWS, LIVE_ROSTERS)
    assert r.status_code == 200, r.get_json()
    ids = {row["player_id"] for row in r.get_json()["free_agents"]}
    assert "qb1" not in ids                       # the orphaned-roster leak
    assert "rb1" not in ids and "wr1" not in ids  # normal exclusions hold
    assert ids == {"qb_sf_only", "te1"}


def test_empty_exclusion_fails_loud_for_sleeper_league():
    """#178: session on a DIFFERENT league + empty snapshot + live Sleeper
    read down ⇒ every source empty. Must 503, never list the whole pool."""
    sess = _sleeper_session([], user_roster=[], league_id="999888777")
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        r, _ = _get_live(c, [], RuntimeError("sleeper down"),
                         league_id=SLEEPER_LEAGUE_ID)
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
    body = r.get_json()
    assert r.status_code == 503, body
    assert body["error"] == "rosters_unavailable"
    assert "free_agents" not in body


def test_empty_exclusion_fails_loud_for_platform_league():
    """#178 (ESPN/MFL shape): numeric platform-native league id whose
    league_members snapshot was never synced ⇒ empty exclusion ⇒ 503 with a
    clear error, never the full universal pool."""
    sess = _sleeper_session([], user_roster=[], league_id="acct_no_league")
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        r, sleeper_get = _get_live(c, [], [], linked_platform=True,
                                   league_id="424242")
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
    body = r.get_json()
    assert r.status_code == 503, body
    assert body["error"] == "rosters_unavailable"
    sleeper_get.assert_not_called()   # platform leagues never hit Sleeper


def test_platform_league_serves_from_snapshot_without_live_read():
    """ESPN-imported league: the server-written snapshot is authoritative
    (every team, no owner filter) — route serves from it and never calls
    the live Sleeper API."""
    sess = _sleeper_session([], user_roster=[], league_id="acct_no_league")
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    espn_rows = [
        {"user_id": UID,          "username": "me",  "player_ids": ["wr1"]},
        {"user_id": "espn:x.t2",  "username": "t2",  "player_ids": ["rb1", "qb1"]},
    ]
    try:
        r, sleeper_get = _get_live(c, espn_rows, [], linked_platform=True,
                                   league_id="424242")
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
    assert r.status_code == 200, r.get_json()
    ids = {row["player_id"] for row in r.get_json()["free_agents"]}
    assert ids == {"qb_sf_only", "te1"}
    sleeper_get.assert_not_called()


def test_live_read_failure_falls_back_to_snapshot(sleeper_client):
    """A Sleeper flake with a NON-empty snapshot union stays best-effort:
    200 from the snapshot-derived exclusion (degraded, but mostly right)."""
    r, _ = _get_live(sleeper_client, SNAPSHOT_ROWS,
                     RuntimeError("sleeper down"))
    assert r.status_code == 200, r.get_json()
    ids = {row["player_id"] for row in r.get_json()["free_agents"]}
    assert "rb1" not in ids and "wr1" not in ids
    assert "qb1" in ids   # honest degradation: live-only knowledge is gone


# ── #179 — roster_capacity context for the client's add pre-check ─────────

def test_roster_capacity_for_sleeper_league(sleeper_client):
    meta = {"roster_positions": ["QB", "RB", "WR", "TE", "BN", "BN"],
            "settings": {"reserve_slots": 2, "taxi_slots": 3}}
    r, _ = _get_live(sleeper_client, SNAPSHOT_ROWS, LIVE_ROSTERS,
                     league_meta=meta)
    assert r.status_code == 200, r.get_json()
    cap = r.get_json()["roster_capacity"]
    assert cap == {"my_count": 1, "limit": 11}   # 6 slots + 2 IR + 3 taxi


def test_roster_capacity_null_for_non_sleeper_league(client):
    """Non-numeric (demo/local) league ids get no capacity block."""
    r = _get(client, RAW_ROWS)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["roster_capacity"] is None
