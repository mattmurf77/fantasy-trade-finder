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
    out-of-season shape, the stats cache, and the user's week selection
    (default last four, `available_weeks`, any subset, 400 on a bad one);
  * the "Last 3 weeks" reading (`?period=3`, scope-period-toggle.md): the
    period and baseline weeks, the three-week average over played weeks, the
    jump against up to three earlier weeks (outside the selection), its two-
    game and volume floors, fewer than two games ranked last, no earlier
    weeks = no jumps, back-or-new, and — without the parameter — output and
    route bytes identical to the code before the reading existed.
"""
import hashlib
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


def test_return_needs_the_weekly_volume_floor():
    # Back from a missed game with 2 snaps (under the floor of 20): not news.
    # With 30 snaps the same comeback is a return.
    weeks = {1: _team("A") + [_row("lo", "WR", "A", 30), _row("hi", "WR", "A", 30)],
             2: _team("A"),
             3: _team("A") + [_row("lo", "WR", "A", 2), _row("hi", "WR", "A", 30)]}
    ps = _by_id(ut.compute(weeks, [1, 2, 3]))
    assert ps["lo"]["snaps"]["signal"] is None
    assert ps["hi"]["snaps"]["signal"]["kind"] == "return"


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
    assert body["available_weeks"] == []
    assert not any("/stats/nfl/" in u for u in fake.calls)


def test_route_default_selection_and_available_weeks(client):
    body = _get(client, FakeSleeper(state={"season": "2026", "week": 7, "season_type": "regular"})).get_json()
    assert body["weeks"] == [3, 4, 5, 6] and body["available_weeks"] == [1, 2, 3, 4, 5, 6]


def test_route_honours_a_user_week_selection(client):
    fake = FakeSleeper(state={"season": "2026", "week": 7, "season_type": "regular"})
    body = _get(client, fake, "?weeks=6,2,2").get_json()
    assert body["weeks"] == [2, 6]
    rb = next(p for p in body["players"] if p["player_id"] == "rb1")
    assert len(rb["status"]) == 2 and len(rb["snaps"]["counts"]) == 2
    assert sorted({u.split("/stats/nfl/2026/")[1].split("?")[0] for u in fake.calls if "/stats/" in u}) == ["2", "6"]


@pytest.mark.parametrize("bad", ["7", "0", "abc", ",", ",".join(str(w) for w in range(1, 21))])
def test_route_rejects_a_bad_week_selection(client, bad):
    r = _get(client, FakeSleeper(state={"season": "2026", "week": 7, "season_type": "regular"}), f"?weeks={bad}")
    assert r.status_code == 400 and r.get_json()["error"] == "invalid_weeks"


def test_route_caches_the_stats_window(client):
    fake = FakeSleeper()
    assert _get(client, fake).status_code == 200
    assert _get(client, fake).status_code == 200
    assert sum("/stats/nfl/" in u for u in fake.calls) == 4    # one per week, once


# ── the "Last 3 weeks" reading (?period=3, scope-period-toggle.md) ──────────


def _weeks_of(shapes, n, tm=60):
    """{week: rows} for team A over weeks 1..n; shapes = {pid: (snaps per
    week or None for a missed game or 'bye')}. A 'bye' in any shape makes
    the whole team bye that week."""
    out = {}
    for w in range(1, n + 1):
        if any(s[w - 1] == "bye" for s in shapes.values()):
            out[w] = []
            continue
        out[w] = _team("A", tm=tm)
        for pid, s in shapes.items():
            if s[w - 1] is not None:
                out[w].append(_row(pid, "WR", "A", s[w - 1], tm=tm))
    return out


def _with_period(weeks_rows, weeks, available):
    parsed = {w: ut.normalize_week(rows) for w, rows in weeks_rows.items()}
    return _by_id(ut.compute_normalized(parsed, weeks, period=ut.period_weeks(weeks, available)))


def test_period_param_and_weeks():
    assert ut.parse_period_param(None) is None and ut.parse_period_param(" ") is None
    assert ut.parse_period_param("3") == 3
    for bad in ("1", "4", "x", "3,3"):
        with pytest.raises(ValueError):
            ut.parse_period_param(bad)
    nine = list(range(1, 10))
    assert ut.period_weeks([6, 7, 8, 9], nine) == ([7, 8, 9], [4, 5, 6])      # default window
    assert ut.period_weeks([1, 2, 3], nine) == ([1, 2, 3], [])                # no earlier weeks
    assert ut.period_weeks([2, 6, 9], nine) == ([2, 6, 9], [1])               # sparse pick
    assert ut.period_weeks([3, 4], nine) == ([3, 4], [1, 2])                  # under three picked
    assert ut.period_weeks([], nine) == ([], [])


def test_three_week_average_leaves_out_byes_and_missed_games():
    # Weeks 7-9: 30, bye, 40 → 2 games, avg 35, share 70/120.
    rows = _weeks_of({"wr": (30, 30, 30, 30, 30, 30, 30, "bye", 40)}, 9)
    b = _with_period(rows, [6, 7, 8, 9], list(range(1, 10)))["wr"]["snaps"]["period"]
    assert (b["games"], b["avg"], b["avg_share"]) == (2, 35.0, 58.3)
    rows = _weeks_of({"wr": (30, 30, 30, 30, 30, 30, 30, None, 40)}, 9)      # missed game
    b = _with_period(rows, [6, 7, 8, 9], list(range(1, 10)))["wr"]["snaps"]["period"]
    assert (b["games"], b["avg"], b["avg_share"]) == (2, 35.0, 58.3)
    assert b["base_games"] == 3 and b["base_avg"] == 30.0 and b["base_avg_share"] == 50.0


def test_three_week_jump_is_measured_against_the_three_weeks_before():
    # Baseline weeks 4-6 (outside the default selection 6-9), one of them missed.
    shapes = {"riser": (50, 50, 50, 10, None, 14, 30, 33, 36),   # base (10+14)/2=12 → 20%; period 55%
              "steady": (30,) * 9,
              "small": (50, 50, 50, 30, 30, 30, 40, 40, 40)}      # +16.7 share: a jump, smaller
    ps = _with_period(_weeks_of(shapes, 9), [6, 7, 8, 9], list(range(1, 10)))
    r = ps["riser"]["snaps"]["period"]
    assert r["kind"] == "jump" and r["base_games"] == 2 and r["base_avg"] == 12.0
    assert r["base_avg_share"] == 20.0 and r["avg_share"] == 55.0
    assert r["delta_share"] == 35.0 and r["delta"] == 21.0
    assert ps["steady"]["snaps"]["period"]["kind"] is None
    assert ps["small"]["snaps"]["period"]["kind"] == "jump"
    order = sorted(shapes, key=lambda pid: ps[pid]["snaps"]["period"]["rank_jump"])
    assert order == ["riser", "small", "steady"]                 # biggest jump first
    # Weekly reading by the period average, not the jump.
    assert sorted(shapes, key=lambda pid: ps[pid]["snaps"]["period"]["rank_share"]) == ["small", "riser", "steady"]
    # The one-week reading is untouched by the period.
    plain = _by_id(ut.compute({w: r for w, r in _weeks_of(shapes, 9).items()}, [6, 7, 8, 9]))
    for pid in shapes:
        block = dict(ps[pid]["snaps"])
        block.pop("period")
        assert block == plain[pid]["snaps"]


def test_three_week_jump_needs_two_games_and_the_volume_floor():
    shapes = {"one_game": (10, 10, 10, 10, 10, 10, None, None, 50),   # +big, but 1 game
              "thin": (2, 2, 2, 2, 2, 2, 15, 15, 15)}                  # +20 pp, 15 snaps < 20
    ps = _with_period(_weeks_of(shapes, 9), [6, 7, 8, 9], list(range(1, 10)))
    one = ps["one_game"]["snaps"]["period"]
    assert one["games"] == 1 and one["kind"] is None and one["avg_share"] == 83.3
    assert ps["thin"]["snaps"]["period"]["kind"] is None


def test_fewer_than_two_games_rank_after_everyone_who_played_two():
    shapes = {"one_game": (40, 40, 40, 40, 40, 40, None, None, 58),   # 97% in his only game
              "two_games": (40, 40, 40, 40, 40, 40, None, 30, 30),
              "three": (40,) * 9}
    ps = _with_period(_weeks_of(shapes, 9), [6, 7, 8, 9], list(range(1, 10)))
    by = lambda key: sorted(shapes, key=lambda pid: ps[pid]["snaps"]["period"][key])
    assert by("rank_share") == ["three", "two_games", "one_game"]
    assert by("rank_count") == ["three", "two_games", "one_game"]
    assert by("rank_jump")[-1] == "one_game"


def test_no_earlier_weeks_means_no_jumps_and_no_new():
    shapes = {"a": (10, 40, 50), "b": (None, 40, 40)}
    ps = _with_period(_weeks_of(shapes, 3), [1, 2, 3], [1, 2, 3])
    for pid in shapes:
        b = ps[pid]["snaps"]["period"]
        assert b["kind"] is None and b["base_games"] == 0 and b["base_avg_share"] is None


def test_back_or_new_over_three_weeks():
    # No game in the baseline weeks (4-6), a real role in 7-9: "new". With the
    # volume under the floor, nothing.
    shapes = {"new": (None,) * 6 + (40, 42, 44),
              "faint": (None,) * 6 + (5, 6, 7),
              "anchor": (50,) * 9}
    ps = _with_period(_weeks_of(shapes, 9), [6, 7, 8, 9], list(range(1, 10)))
    assert ps["new"]["snaps"]["period"]["kind"] == "new"
    assert ps["new"]["snaps"]["period"]["delta_share"] is None
    assert ps["faint"]["snaps"]["period"]["kind"] is None
    order = sorted(shapes, key=lambda pid: ps[pid]["snaps"]["period"]["rank_jump"])
    assert order[0] == "new"                                   # no jumps; "new" leads


# Captured from the code BEFORE the period reading existed (2026-11-12, 12ac0f1d).
_REAL_W1_4 = "d9d4efef857f2bcdad23565dd55fb72cda7fee426c1324106bf45c77e22d5cfc"
_REAL_W2_4 = "606fd3e44b67f723691b280d6b3880665d3e712939bb29ec707620e8d9a6d774"


def test_without_a_period_the_output_is_byte_identical_to_before():
    doc = json.loads(FIXTURE.read_text())
    rows = {int(w): r for w, r in doc["weeks"].items()}
    digest = lambda ps: hashlib.sha256(json.dumps(ps, sort_keys=True).encode()).hexdigest()
    assert digest(ut.compute(rows, [1, 2, 3, 4])) == _REAL_W1_4
    assert digest(ut.compute(rows, [2, 3, 4])) == _REAL_W2_4


def test_real_2026_three_week_reading():
    doc = json.loads(FIXTURE.read_text())
    parsed = {int(w): ut.normalize_week(r) for w, r in doc["weeks"].items()}
    ps = ut.compute_normalized(parsed, [2, 3, 4], period=ut.period_weeks([2, 3, 4], [1, 2, 3, 4]))
    by_name = {p["name"]: p for p in ps}
    cooper = by_name["Darius Cooper"]["snaps"]["period"]
    assert (cooper["base_avg_share"], cooper["avg_share"], cooper["kind"]) == (14.5, 48.7, "jump")
    assert cooper["rank_jump"] == 1
    assert by_name["Sterling Shepard"]["snaps"]["period"]["kind"] == "new"


# Raw response bytes captured from the route BEFORE `period` existed.
_ROUTE_BYTES = {
    "": "a5bfab256bfc9d1435c5f268ddd0a161def03691835ce4df866d717ab9487e72",
    f"?league_ids={OTHER},{ESPN}": "11102c1b51f3952790973fb002f9b99bf193081090030a70c8e4f579b1e7e484",
    "?weeks=2,6": "58f54b93aa728262b013bdaf5b33b5aa1d39af76d145ac18369221bae121cdba",
}


def test_route_without_period_is_byte_identical_to_before(client):
    for qs, want in _ROUTE_BYTES.items():
        fake = FakeSleeper(state={"season": "2026", "week": 7, "season_type": "regular"})
        r = _get(client, fake, qs)
        assert hashlib.sha256(r.get_data()).hexdigest() == want, qs


def test_route_period_adds_the_reading_and_reads_the_baseline_weeks(client):
    fake = FakeSleeper(state={"season": "2026", "week": 10, "season_type": "regular"})
    body = _get(client, fake, "?period=3").get_json()
    assert body["weeks"] == [6, 7, 8, 9]
    assert body["period"] == {"weeks": [7, 8, 9], "base_weeks": [4, 5, 6]}
    fetched = sorted(int(u.split("/stats/nfl/2026/")[1].split("?")[0]) for u in fake.calls if "/stats/" in u)
    assert fetched == [4, 5, 6, 7, 8, 9]
    rb = next(p for p in body["players"] if p["player_id"] == "rb1")
    assert set(rb["snaps"]["period"]) >= {"games", "avg", "avg_share", "base_avg_share", "kind",
                                          "rank_jump", "rank_share", "rank_count"}
    plain = _get(client, fake, "").get_json()
    assert "period" not in plain and "period" not in plain["players"][0]["snaps"]


@pytest.mark.parametrize("bad", ["1", "4", "abc"])
def test_route_rejects_a_bad_period(client, bad):
    r = _get(client, FakeSleeper(), f"?period={bad}")
    assert r.status_code == 400 and r.get_json()["error"] == "invalid_period"
