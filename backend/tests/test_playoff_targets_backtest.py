"""The Playoff targets backtest (docs/plans/league-projections/playoff-targets/backtest/).

A tiny synthetic league written as a Sleeper cache in a temp folder (four
teams, two playoff spots, four regular-season weeks, a full 272-game NFL
schedule so the product's timing contract accepts it), with every number
chosen so the answer is known by hand:

- the product's own `provider.capture` accepts the rebuilt Tuesday snapshot,
  its records reconcile, and the forecast's lineups re-solve to the stored ones;
- the replay table scores players exactly as the snapshot does;
- replaying recorded scores through `simulation.simulate` reproduces the real
  bracket, ties on wins going to points for;
- moving the seller's star to the viewer flips the viewer into the playoffs,
  and `playoff_targets.compute` lists him first with a positive gain;
- pure pieces: team-by-week fallback, pregame score rows, Sleeper's split
  points, stats scoring, the exhaustive lineup check, the statistics.
No network, no database, no real cache.
"""
from __future__ import annotations

import importlib.util
import json
import socket
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parents[2] / "docs/plans/league-projections/playoff-targets/backtest"
sys.path.insert(0, str(_DIR))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bs = _load("backtest_stats")
bt = _load("backtest")

from backend.league_projections import playoff_targets, simulation  # noqa: E402
from backend.league_projections.core import optimize, split_points  # noqa: E402
from backend.league_projections.maxpf_moves import parity  # noqa: E402
from backend.league_projections import season_points  # noqa: E402

LEAGUE = "900000000000000001"
SEASON = 2025
NFL = [f"T{i:02d}" for i in range(32)]
# Fantasy roster -> {player: (position, weekly points)}. Projection = actual.
ROSTERS = {
    1: {"q1": ("QB", 5), "s1": ("RB", 30), "b1": ("RB", 4)},   # the seller, with the star
    2: {"q2": ("QB", 20), "r2": ("RB", 15), "b2": ("RB", 11)},
    3: {"q3": ("QB", 18), "r3": ("RB", 14), "b3": ("RB", 9)},
    4: {"q4": ("QB", 19), "r4": ("RB", 13), "b4": ("RB", 8)},  # the viewer
}
GAMES = {1: [(1, 2), (3, 4)], 2: [(1, 3), (2, 4)], 3: [(1, 4), (2, 3)], 4: [(1, 2), (3, 4)]}
SLOTS = ["QB", "RB", "FLEX"]


def _nfl_schedule():
    """18 weeks, 272 games: teams 2k-2 and 2k-1 rest in week k (k <= 16)."""
    rows = []
    for week in range(1, 19):
        resting = {2 * week - 2, 2 * week - 1} if week <= 16 else set()
        playing = [t for t in range(32) if t not in resting]
        shift = week % len(playing)
        playing = playing[shift:] + playing[:shift]
        for i in range(0, len(playing), 2):
            home, away = NFL[playing[i]], NFL[playing[i + 1]]
            rows.append({"game_id": f"{SEASON}{week:02d}{i // 2:02d}", "week": week, "home": home, "away": away,
                         "status": "complete", "date": "2025-09-07"})
    return rows


def _kickoff(week):
    return datetime(2025, 9, 7, 17, tzinfo=timezone.utc) + timedelta(days=7 * (week - 1))


def _write_cache(cache):
    def put(url, data):
        bt.cache_path(cache, url).write_text(json.dumps(data))

    schedule = _nfl_schedule()
    put(f"{bt.API}/schedule/nfl/regular/{SEASON}", schedule)
    players, nfl_team = {}, {}
    for n, (rid, roster) in enumerate(sorted(ROSTERS.items())):
        for k, (pid, (pos, _pts)) in enumerate(sorted(roster.items())):
            nfl_team[pid] = NFL[16 + 3 * n + k]  # teams 16+ never rest in weeks 1-4
            players[pid] = {"fantasy_positions": [pos], "position": pos, "full_name": f"Player {pid}", "team": "T00"}
    put(f"{bt.API}/v1/players/nfl", players)
    put(f"{bt.API}/v1/league/{LEAGUE}", {
        "league_id": LEAGUE, "season": str(SEASON), "sport": "nfl", "season_type": "regular", "status": "complete",
        "total_rosters": 4, "roster_positions": SLOTS + ["BN"], "scoring_settings": {"rush_yd": 0.1},
        "previous_league_id": None,
        "settings": {"playoff_week_start": 5, "playoff_teams": 2, "trade_deadline": 99, "league_average_match": 0,
                     "divisions": 0, "best_ball": 0, "start_week": 1, "playoff_type": 0, "playoff_round_type": 0,
                     "playoff_seed_type": 0}})
    put(f"{bt.API}/v1/league/{LEAGUE}/rosters", [{"roster_id": r, "owner_id": f"u{r}", "players": sorted(ROSTERS[r])}
                                               for r in ROSTERS])
    put(f"{bt.API}/v1/league/{LEAGUE}/winners_bracket", [{"r": 1, "m": 1, "t1": 2, "t2": 3}])
    for week in range(1, 5):
        games = [g for g in schedule if g["week"] == week]
        put(f"{bt.API}/scores/nfl/regular/{SEASON}/{week}", [{
            "game_id": g["game_id"], "season": str(SEASON), "week": week, "season_type": "regular", "sport": "nfl",
            "status": "complete", "start_time": int(_kickoff(week).timestamp() * 1000),
            "metadata": {"home_team": g["home"], "away_team": g["away"], "date_time": _kickoff(week).isoformat(),
                         "canceled": False, "is_over": True, "has_started": True, "is_in_progress": False,
                         "status": "complete"}} for g in games])
        by_team = {}
        for g in games:
            by_team[g["home"]] = (g["game_id"], g["away"])
            by_team[g["away"]] = (g["game_id"], g["home"])
        proj, stats = [], []
        for roster in ROSTERS.values():
            for pid, (_pos, pts) in roster.items():
                gid, opp = by_team[nfl_team[pid]]
                proj.append({"player_id": pid, "team": nfl_team[pid], "game_id": gid, "opponent": opp, "category": "proj",
                             "season": str(SEASON), "week": week, "season_type": "regular", "company": "rotowire",
                             "stats": {"rush_yd": pts * 10, "gp": 1}})
                stats.append({"player_id": pid, "team": nfl_team[pid], "stats": {"rush_yd": pts * 10}})
        put(f"{bt.API}/projections/nfl/{SEASON}/{week}?season_type=regular", proj)
        put(f"{bt.API}/stats/nfl/{SEASON}/{week}?season_type=regular", stats)
        rows = []
        for m, (a, b) in enumerate(GAMES[week], start=1):
            for rid in (a, b):
                roster = ROSTERS[rid]
                pool = [{"player_id": p, "positions": [pos], "points": str(v)} for p, (pos, v) in roster.items()]
                starters = [r["player"]["player_id"] for r in optimize(SLOTS, pool, empty_policy="fill_available")["lineup"]]
                rows.append({"roster_id": rid, "matchup_id": m, "players": sorted(roster), "starters": starters,
                             "starters_points": [roster[p][1] for p in starters],
                             "players_points": {p: v for p, (_pos, v) in roster.items()},
                             "points": sum(roster[p][1] for p in starters), "custom_points": None})
        put(f"{bt.API}/v1/league/{LEAGUE}/matchups/{week}", rows)


@pytest.fixture(scope="module")
def season(tmp_path_factory):
    cache = tmp_path_factory.mktemp("cache")
    _write_cache(cache)
    s = bt.Season(cache, LEAGUE, bt.load(cache, f"{bt.API}/v1/players/nfl"))
    s._memo = {}
    s.build_tables(3)
    return s


@pytest.fixture(scope="module")
def cfg():
    model = json.loads(bt.CONFIG_PATH.read_text())["model"]
    return simulation.config({**model, "draft_season": SEASON + 1, "iterations": 4000})


def test_capture_accepts_the_rebuilt_tuesday_snapshot(season, cfg):
    snapshot, sidecar = season.capture(3, cfg)
    assert snapshot["completed_weeks"] == 2 and [w["week"] for w in snapshot["weeks"]] == [3, 4]
    records = {t["roster_id"]: (t["wins"], t["losses"]) for t in snapshot["teams"]}
    assert records == {1: (0, 2), 2: (2, 0), 3: (2, 0), 4: (0, 2)}
    assert parity(snapshot, cfg, sidecar["free_agents"])["mismatches"] == []
    assert sidecar["trade_deadline"] is None  # 99 means no deadline
    # The replay table scores every player exactly as the snapshot does.
    for week, table in season_points.player_points(snapshot).items():
        assert table == {p: season.proj[week][p] for p in table}
    assert season.proj[3]["s1"] == Decimal(30)


def test_recorded_replay_reproduces_the_bracket(season, cfg):
    made = season.made(cfg, [season.recorded[w] for w in season.weeks])
    assert {r for r, p in made.items() if p == 1} == season.real_playoff == {2, 3}
    assert season.stats_check["mismatch"] == 0


def test_moving_the_star_flips_the_viewer(season, cfg):
    base = season.made(cfg, season.season_scores(3))
    moved_scores = season.season_scores(3, ("s1", 4))
    moved = season.made(cfg, moved_scores)
    assert base[4] == 0 and moved[4] == 1  # 2-2 with team 3, ahead on points for (204 to 164)
    assert moved_scores[2][4] == 62 and moved_scores[2][1] == 9  # week 3: 19+30+13; the seller's flex is empty
    assert moved_scores[1] == season.recorded[2]  # weeks before the trade are facts


def test_compute_lists_the_star_first(season, cfg):
    snapshot, sidecar = season.capture(3, cfg)
    result = simulation.simulate(snapshot, cfg)
    block = playoff_targets.compute(snapshot, result, sidecar["free_agents"], playoff_targets.settings(),
                                    roster_id=4, seller_outlooks={}, owners=sidecar["owners"])
    assert block["computed"] and not block["skipped"]
    first = block["rows"][0]
    assert first["player_id"] == "s1" and first["lineup_gain"] == 44  # (62 - 40) x 2 weeks
    assert first["playoff_probability"]["after"] > first["playoff_probability"]["now"]


def test_row_records_predicted_and_realised(season, cfg):
    snapshot, sidecar = season.capture(3, cfg)
    result = simulation.simulate(snapshot, cfg)
    team = next(t for t in result["teams"] if t["roster_id"] == 4)
    block = playoff_targets.compute(snapshot, result, sidecar["free_agents"], playoff_targets.settings(),
                                    roster_id=4, seller_outlooks={}, owners=sidecar["owners"])
    base_made = season.made(cfg, season.season_scores(3))
    row = bt._row(season, cfg, 3, 4, "s1", 1, Decimal(44), 1, block["rows"][0], team, base_made, snapshot, None)
    assert row["realised_gain"] == 1 and row["seller_made_cf"] == 0
    assert row["realised_lineup_gain"] == 44 == row["realised_lineup_gain_fixed_roster"]
    assert row["realised_hindsight_gain"] == 44 and row["lineup_gain"] == 44
    assert row["predicted_gain"] == pytest.approx(row["after"] - row["now"])


def test_network_is_refused():
    saved = socket.socket
    try:
        socket.socket = bt._no_network
        with pytest.raises(RuntimeError):
            socket.socket()
    finally:
        socket.socket = saved


def test_cache_miss_raises(tmp_path):
    with pytest.raises(bt.CacheMiss):
        bt.load(tmp_path, f"{bt.API}/v1/league/1")


# ---------------------------------------------------------------- pure pieces
def test_week_teams_prefers_the_nearest_earlier_week():
    teams = bt.week_teams({1: {"a": "X"}, 3: {"a": "Y", "b": "Z"}}, [1, 2, 3, 4])
    assert teams[2]["a"] == "X" and teams[4]["a"] == "Y" and teams[1]["b"] == "Z" and teams[2]["b"] == "Z"


def test_pregame_scores_read_as_scheduled():
    row = bt.pregame_scores([{"status": "complete", "metadata": {"is_over": True, "has_started": True, "home_team": "A"}}])[0]
    assert row["status"] == "pre_game" and row["metadata"]["status"] == "scheduled"
    assert row["metadata"]["home_team"] == "A" and not row["metadata"]["is_over"] and not row["metadata"]["has_started"]


@pytest.mark.parametrize("value", ["123.45", "0.07", "-2.35", "-0.40", "88"])
def test_split_round_trips_through_the_product_reader(value):
    out = bt._split("fpts", Decimal(value))
    assert split_points(out["fpts"], out["fpts_decimal"]) == Decimal(value)


def test_record_settings_count_the_median_game():
    history = {1: [Decimal(10)], 2: [Decimal(20)], 3: [Decimal(30)], 4: [Decimal(40)]}
    head = bt.record_settings(history, [[(1, 2), (3, 4)]], median=False)
    median = bt.record_settings(history, [[(1, 2), (3, 4)]], median=True)
    assert (head[4]["wins"], head[4]["losses"]) == (1, 0) and (head[3]["wins"], head[3]["losses"]) == (0, 1)
    assert (median[4]["wins"], median[3]["wins"], median[2]["wins"], median[1]["wins"]) == (2, 1, 1, 0)
    assert head[1]["fpts_against"] == 20


def test_actual_points_uses_league_scoring():
    assert bt.actual_points({"stats": {"rush_yd": 123, "rec": 4, "x": 9}}, {"rush_yd": .1, "rec": 1}) == Decimal("16.3")
    assert bt.actual_points(None, {"rush_yd": .1}) == 0


def test_chosen_starters_by_projection_then_free_agent():
    positions = {"q": ["QB"], "r": ["RB"], "fa": ["RB"]}
    proj = {"q": Decimal(20), "r": Decimal(10), "fa": Decimal(7)}
    fa = [{"player_id": "fa", "positions": ["RB"], "points": "7"}]
    assert sorted(bt.chosen_starters(SLOTS, ["q", "r"], proj, positions, fa)) == ["fa", "q", "r"]
    assert sorted(bt.chosen_starters(SLOTS, ["q", "r"], proj, positions, [])) == ["q", "r"]


def test_exhaustive_best_agrees_with_optimize():
    players = [(["QB"], Decimal(20)), (["RB"], Decimal(12)), (["RB"], Decimal(9)), (["WR"], Decimal(30))]
    pool = [{"player_id": str(i), "positions": p, "points": str(v)} for i, (p, v) in enumerate(players)]
    assert bt.exhaustive_best(SLOTS, players) == Decimal(optimize(SLOTS, pool, empty_policy="fill_available")["points"]) == 62


def test_bracket_teams():
    assert bt.bracket_teams([{"t1": 1, "t2": 4}, {"t1": 2, "t2": {"w": 1}}, {"t1": None}]) == {1, 2, 4}


def test_stats_bins_and_brier():
    rows = [{"g": .005}, {"g": .01}, {"g": .03}, {"g": .2}]
    assert [(label, len(part)) for label, part in bs.binned(rows, "g", (.01, .05))] == [("<0.01", 1), ("0.01-0.05", 2), (">=0.05", 1)]
    assert bs.brier([(1, 1), (0, 1)]) == .5
    assert bs.brier_climatology([1, 0, 1, 0]) == .25
    out = bs.summary([(10, 4), (2, 6)])
    assert out["bias"] == 1 and out["mae"] == 5 and out["realised_over_predicted"] == pytest.approx(10 / 12)


def test_bootstrap_resamples_whole_groups():
    groups = [[{"x": 1}], [{"x": 3}]]
    out = bs.bootstrap(groups, lambda rs: {"m": bs.mean(r["x"] for r in rs)}, reps=200, seed=1)
    assert out["m"]["value"] == 2 and out["m"]["ci95"][0] >= 1 and out["m"]["ci95"][1] <= 3
