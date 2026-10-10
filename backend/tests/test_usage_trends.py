"""Usage Trends — backend/usage_trends.py (pure math) + GET /api/usage-trends.

Spec: docs/plans/usage-trends/scope.md. Covers:
  * the window: last four completed regular-season weeks, nothing out of season;
  * team share: team snaps from tm_off_snp, carries/targets summed over every
    QB/RB/WR/TE row of the team (QB carries in the denominator);
  * averages over PLAYED weeks only — byes and missed games both left out
    (operator ruling 2026-10-10), with the week marked bye / out;
  * spikes are share-driven: a role can grow while counts fall (Braelon Allen)
    and a count gain on a busier team is not a spike;
  * return / new / out / rising signals and the server rank order;
  * low-usage players dropped;
  * real-data regression on a trimmed 2026 Weeks 1-4 capture (NYJ + PHI);
  * the route: flag gate, roster join (mine / rostered / orphan / FA), other
    leagues, non-member leagues withheld, 503 without a partial window, the
    out-of-season shape, and the stats cache.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import backend.server as server
from backend import usage_trends as ut
from backend.trade_service import League, LeagueMember

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "backend/tests/fixtures/usage_trends/sleeper_stats_2026_w1-4_nyj_phi.json"


def _row(pid, pos, team, snp=None, *, tm=60, car=0, tgt=0, gp=True):
    stats = {}
    if gp:
        stats["gp"] = 1
    if snp is not None:
        stats["off_snp"] = snp
    if tm:
        stats["tm_off_snp"] = tm
    if car:
        stats["rush_att"] = car
    if tgt:
        stats["rec_tgt"] = tgt
    return {"player_id": pid, "team": team, "stats": stats,
            "player": {"position": pos, "first_name": "P", "last_name": pid}}


def _team(team, tm=60, qb_car=0, others_tgt=0):
    """A QB row carrying the team's snap total, QB carries, and filler targets."""
    return [_row(f"qb_{team}", "QB", team, tm, tm=tm, car=qb_car),
            _row(f"filler_{team}", "WR", team, tm, tm=tm, tgt=others_tgt)]


def _by_id(players):
    return {p["player_id"]: p for p in players}


# ── window ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("state, expected", [
    ({"season": "2026", "week": 5, "season_type": "regular"}, (2026, [1, 2, 3, 4])),
    ({"season": "2026", "week": 9, "season_type": "regular"}, (2026, [5, 6, 7, 8])),
    ({"season": "2026", "week": 2, "season_type": "regular"}, (2026, [1])),
    ({"season": "2026", "week": 1, "season_type": "regular"}, (2026, [])),
    ({"season": "2026", "week": 1, "season_type": "pre"}, (2026, [])),
    ({"season": "2026", "week": 19, "season_type": "post"}, (2026, [])),
    ({}, (None, [])),
])
def test_window_is_last_four_completed_regular_season_weeks(state, expected):
    assert ut.window_weeks(state) == expected


# ── shares, byes, missed games ───────────────────────────────────────────────

def test_team_share_counts_qb_carries_in_the_denominator():
    week = _team("NYJ", tm=50, qb_car=10) + [_row("rb", "RB", "NYJ", 40, tm=50, car=10)]
    p = _by_id(ut.compute({1: week}, [1]))["rb"]
    assert p["snaps"]["shares"] == [80.0]
    assert p["carries"]["shares"] == [50.0]          # 10 of the team's 20


def test_bye_and_missed_games_are_left_out_of_the_average():
    weeks = {
        1: _team("A") + [_row("wr", "WR", "A", 30)],
        2: [],                                                  # A on bye
        3: _team("A") + [_row("wr", "WR", "A", None, gp=False)],  # inactive
        4: _team("A") + [_row("wr", "WR", "A", 45)],
    }
    p = _by_id(ut.compute(weeks, [1, 2, 3, 4]))["wr"]
    assert p["status"] == ["played", "bye", "out", "played"]
    assert p["snaps"]["counts"] == [30, None, None, 45]
    assert p["snaps"]["avg"] == 37.5                  # (30 + 45) / 2, not / 4
    assert p["snaps"]["avg_share"] == 62.5            # 75 of 120 team snaps


def test_missing_row_while_team_played_is_out_and_latest_out_is_the_signal():
    weeks = {1: _team("A") + [_row("rb", "RB", "A", 40)],
             2: _team("A") + [_row("rb", "RB", "A", 42)],
             3: _team("A")}                            # no row at all
    p = _by_id(ut.compute(weeks, [1, 2, 3]))["rb"]
    assert p["status"] == ["played", "played", "out"]
    assert p["snaps"]["signal"] == {"kind": "out", "week": 3}
    assert p["snaps"]["avg"] == 41.0


# ── spikes are share-driven ──────────────────────────────────────────────────

def test_role_growth_with_fewer_snaps_is_a_spike():
    # Braelon Allen's shape: team snaps collapse, his count dips, share soars.
    weeks = {w: _team("NYJ", tm=66) + [_row("rb", "RB", "NYJ", 27, tm=66)] for w in (1, 2, 3)}
    weeks[4] = _team("NYJ", tm=32) + [_row("rb", "RB", "NYJ", 25, tm=32)]
    sig = _by_id(ut.compute(weeks, [1, 2, 3, 4]))["rb"]["snaps"]["signal"]
    assert sig["kind"] == "spike" and sig["week"] == 4
    assert sig["delta"] == -2.0 and sig["delta_share"] > 15


def test_count_gain_on_a_busier_team_is_not_a_spike():
    # Tee Higgins' shape: more snaps, smaller share of a bigger pie.
    weeks = {w: _team("CIN", tm=57) + [_row("wr", "WR", "CIN", 53, tm=57)] for w in (1, 2, 3)}
    weeks[4] = _team("CIN", tm=76) + [_row("wr", "WR", "CIN", 60, tm=76)]
    sig = _by_id(ut.compute(weeks, [1, 2, 3, 4]))["wr"]["snaps"]["signal"]
    assert sig is None or sig["kind"] != "spike"


def test_spike_needs_the_weekly_volume_floor():
    # +40 pp of targets, but 2 targets is under the floor of 4.
    weeks = {1: _team("A", others_tgt=5) + [_row("te", "TE", "A", 30, tgt=0)],
             2: _team("A", others_tgt=3) + [_row("te", "TE", "A", 30, tgt=2)]}
    assert _by_id(ut.compute(weeks, [1, 2]))["te"]["targets"]["signal"] is None


# ── return / new / rising ────────────────────────────────────────────────────

def test_return_after_missed_games_and_new_role_on_first_game():
    weeks = {1: _team("A") + [_row("wr1", "WR", "A", 50)],
             2: _team("A"), 3: _team("A"),
             4: _team("A") + [_row("wr1", "WR", "A", 52), _row("wr2", "WR", "A", 40)]}
    ps = _by_id(ut.compute(weeks, [1, 2, 3, 4]))
    back = ps["wr1"]["snaps"]["signal"]
    assert back["kind"] == "return" and back["missed"] == 2 and back["week"] == 4
    new = ps["wr2"]["snaps"]["signal"]
    assert new["kind"] == "new" and new["missed"] == 3 and new["share"] == 66.7


def test_steadily_growing_share_reads_as_rising():
    weeks = {w: _team("A") + [_row("te", "TE", "A", s)] for w, s in
             zip((1, 2, 3, 4), (18, 24, 30, 36))}            # +10 pp a week, no spike
    sig = _by_id(ut.compute(weeks, [1, 2, 3, 4]))["te"]["snaps"]["signal"]
    assert sig["kind"] == "rising" and sig["from_share"] == 30.0 and sig["to_share"] == 60.0


# ── rank order ───────────────────────────────────────────────────────────────

def test_rank_puts_latest_week_news_first_then_older_spikes_then_the_rest():
    weeks = {1: _team("A"), 2: _team("A"), 3: _team("A"), 4: _team("A")}
    shapes = {
        "latest_spike": (20, 20, 20, 50),
        "old_spike":    (20, 50, 50, 50),
        "steady_big":   (55, 55, 55, 55),
        "returned":     (40, None, None, 40),
    }
    for pid, counts in shapes.items():
        for w, c in zip((1, 2, 3, 4), counts):
            if c is not None:
                weeks[w].append(_row(pid, "WR", "A", c))
    ps = _by_id(ut.compute(weeks, [1, 2, 3, 4]))
    order = sorted(shapes, key=lambda pid: ps[pid]["snaps"]["rank"])
    assert order == ["latest_spike", "returned", "old_spike", "steady_big"]
    assert "_tier" not in ps["steady_big"]["snaps"]


def test_low_usage_player_without_news_is_dropped():
    weeks = {w: _team("A") + [_row("depth", "WR", "A", 3)] for w in (1, 2, 3, 4)}
    assert "depth" not in _by_id(ut.compute(weeks, [1, 2, 3, 4]))


def test_fetch_weeks_refuses_a_partial_window():
    with pytest.raises(ValueError):
        ut.fetch_weeks(2026, [1, 2], lambda url: [] if url.endswith("/1?") else {"err": 1})


# ── real data ────────────────────────────────────────────────────────────────

def test_real_2026_weeks_1_to_4_regression():
    doc = json.loads(FIXTURE.read_text())
    ps = ut.compute({int(w): rows for w, rows in doc["weeks"].items()}, [1, 2, 3, 4])
    by_name = {p["name"]: p for p in ps}
    allen = by_name["Braelon Allen"]["snaps"]
    assert allen["counts"] == [27, 23, 34, 30]
    assert allen["shares"][2:] == [51.5, 93.8]
    assert allen["signal"]["kind"] == "spike" and allen["signal"]["week"] == 4
    cooper = by_name["Darius Cooper"]
    assert cooper["snaps"]["counts"] == [8, 31, 5, 55]
    assert cooper["targets"]["counts"] == [0, 3, 0, 7]
    assert cooper["targets"]["shares"][3] == 28.0             # 7 of PHI's 25
    assert cooper["snaps"]["signal"]["kind"] == "spike"


# ── route ────────────────────────────────────────────────────────────────────

UID = "u_usage"
TOKEN = "sess-usage-trends"
LEAGUE = "111"          # Sleeper (numeric)
OTHER = "222"           # Sleeper, caller has no roster there
ESPN = "333"            # platform-linked


def _stats_week():
    return _team("A") + [_row("rb1", "RB", "A", 40), _row("wr1", "WR", "A", 45),
                         _row("te1", "TE", "A", 30), _row("wr9", "WR", "A", 20)]


class FakeSleeper:
    def __init__(self, state=None, stats_ok=True):
        self.state = state or {"season": "2026", "week": 5, "season_type": "regular"}
        self.stats_ok = stats_ok
        self.calls = []

    def __call__(self, url, timeout=15):
        self.calls.append(url)
        if url.endswith("/state/nfl"):
            return self.state
        if "/stats/nfl/" in url:
            if not self.stats_ok:
                raise OSError("sleeper down")
            return _stats_week()
        if url.endswith(f"/league/{LEAGUE}/rosters"):
            return [{"roster_id": 1, "owner_id": UID, "players": ["rb1", "bench_guy"]},
                    {"roster_id": 2, "owner_id": "opp", "players": ["wr1"]},
                    {"roster_id": 3, "owner_id": None, "players": ["te1"]}]
        if url.endswith(f"/league/{LEAGUE}/users"):
            return [{"user_id": "opp", "display_name": "gdubs10"}]
        if url.endswith(f"/league/{OTHER}/rosters"):
            return [{"roster_id": 1, "owner_id": "someone", "players": ["rb1"]}]
        raise AssertionError(f"unexpected Sleeper URL in test: {url}")


def _members(league_id):
    if league_id == ESPN:
        return [{"user_id": UID, "display_name": "me", "player_ids": ["wr1"]},
                {"user_id": f"espn:{ESPN}.t2", "display_name": "Team Two",
                 "player_ids": ["rb1"]}]
    return []


@pytest.fixture()
def client(monkeypatch):
    league = League(league_id=LEAGUE, name="Usage League", platform="sleeper",
                    members=[LeagueMember(user_id="opp", username="opp", roster=["wr1"],
                                          elo_ratings={})])
    sess = {"user_id": UID, "league": league, "user_roster": ["rb1"],
            "service": object(), "trade_svc": object(), "players": [],
            "active_format": "1qb_ppr", "last_active": 0.0}
    server.app.config["TESTING"] = True
    monkeypatch.setattr(server, "is_enabled", lambda k: k == "usage_trends.enabled")
    monkeypatch.setattr(server, "_verified_read_denial", lambda s: None)
    monkeypatch.setattr(server, "touch_user_activity", MagicMock(), raising=False)
    monkeypatch.setattr(server, "load_league_members", _members)
    monkeypatch.setattr(server, "is_linked_platform_league", lambda lid: lid == ESPN)
    server._usage_cache.clear()
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        yield server.app.test_client()
    finally:
        server._usage_cache.clear()
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


def _get(c, fake, qs=""):
    with patch.object(server, "_sleeper_get", fake):
        return c.get(f"/api/usage-trends{qs}", headers={"X-Session-Token": TOKEN})


def test_route_404s_with_the_flag_off(client, monkeypatch):
    monkeypatch.setattr(server, "is_enabled", lambda k: False)
    r = _get(client, FakeSleeper())
    assert r.status_code == 404 and r.get_json()["error"] == "feature_disabled"


def test_route_joins_rosters_for_focus_and_other_leagues(client):
    r = _get(client, FakeSleeper(), f"?league_ids={OTHER},{ESPN},{LEAGUE}")
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["weeks"] == [1, 2, 3, 4] and body["in_season"] is True
    assert {p["player_id"] for p in body["players"]} >= {"rb1", "wr1", "te1", "wr9"}
    focus, other, espn = body["leagues"]
    assert [lg["league_id"] for lg in body["leagues"]] == [LEAGUE, OTHER, ESPN]
    assert focus["ok"] and focus["me"] == UID
    assert focus["rosters"] == {"rb1": UID, "wr1": "opp", "te1": "roster:3"}  # wr9 = FA
    assert "bench_guy" not in focus["rosters"]                  # not a listed player
    assert focus["owners"] == {"opp": "gdubs10"}
    assert other == {"league_id": OTHER, "ok": False, "me": None,
                     "owners": {}, "rosters": {}}                # not the caller's league
    assert espn["ok"] and espn["me"] == UID
    assert espn["rosters"] == {"wr1": UID, "rb1": f"espn:{ESPN}.t2"}
    assert espn["owners"][f"espn:{ESPN}.t2"] == "Team Two"


def test_route_503s_rather_than_serving_a_partial_window(client):
    r = _get(client, FakeSleeper(stats_ok=False))
    assert r.status_code == 503 and r.get_json()["error"] == "stats_unavailable"
    assert _get(client, FakeSleeper()).status_code == 200    # failure was not cached


def test_route_out_of_season_shape(client):
    fake = FakeSleeper(state={"season": "2026", "week": 1, "season_type": "pre"})
    body = _get(client, fake).get_json()
    assert body["in_season"] is False and body["weeks"] == [] and body["players"] == []
    assert not any("/stats/nfl/" in u for u in fake.calls)


def test_route_caches_the_stats_window(client):
    fake = FakeSleeper()
    assert _get(client, fake).status_code == 200
    assert _get(client, fake).status_code == 200
    assert sum("/stats/nfl/" in u for u in fake.calls) == 4    # one per week, once
