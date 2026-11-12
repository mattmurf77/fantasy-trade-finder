"""Win-now season signal WI-1: per-player points derived from a saved projection snapshot.

Spec: docs/plans/win-now-season-signal/lld.md §1.1, invariant I10 (§10).

The snapshot is produced by the real `provider.capture` over a synthetic Sleeper
world: the committed 12-team league (`fixtures/season-signal/league-12.json`, public
players), the committed Sleeper weekly projections (`outlook-calibration/
sleeper-projections-2026.json`), the real 2026 NFL schedule (byes included) and a
PPR scoring table that carries kicker and team-defense coefficients the lineup has
no slot for. No network, no database.

Covered:
- test_derived_points_reproduce_stored_lineup_totals (I10), under the production
  best-available contract and the strict sparse-offense contract. Sabotage: score
  with the raw scoring settings instead of the slot-normalised ones.
- test_points_match_the_projection_fixture: every priced row equals Sleeper's
  pts_ppr; a week the player's NFL team does not play is BYE; a player with no
  row is unknown, never zero.
- test_unknown_rows_are_none: unpriced, unavailable and completed rows are None.
- test_free_agent_rows_are_kept_apart: a model v6 free-agent row never becomes a
  rostered player's points, and unknown extra keys are ignored.
- test_malformed_snapshot_raises_unavailable.
"""
from __future__ import annotations

import csv
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend.league_projections import provider, season_points
from backend.league_projections.core import Unavailable
from backend.league_projections.scoring import BEST_AVAILABLE, CONTRACT as SPARSE

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "backend" / "tests" / "fixtures"
API = provider.API
LEAGUE_ID = "900001"
CAPTURED_AT = "2026-09-01T12:00:00+00:00"
# Kicker and team-defense keys stay in Sleeper's scoring settings of an
# offense-only league; capture strips them (normalize_scoring_for_slots).
SCORING = {"pass_yd": .04, "pass_td": 4, "pass_int": -2, "rush_yd": .1, "rush_td": 6,
           "rec": 1, "rec_yd": .1, "rec_td": 6, "fum_lost": -2, "fgm": 3, "pts_allow_0": 10}


def load_league():
    return json.loads((FIXTURES / "season-signal" / "league-12.json").read_text())


def load_pool():
    return json.loads((FIXTURES / "player_pool_2026.json").read_text())["players"]


def load_projections():
    return json.loads((FIXTURES / "outlook-calibration" / "sleeper-projections-2026.json").read_text())["weeks"]


def _schedule():
    """The real 2026 regular season, Sleeper team codes, kickoff in UTC."""
    games = []
    with open(FIXTURES / "nflverse_games_2022_2026.csv") as handle:
        for row in csv.DictReader(handle):
            if row["season"] != "2026" or row["game_type"] != "REG":
                continue
            fix = lambda team: "LAR" if team == "LA" else team
            kickoff = datetime.fromisoformat(f"{row['gameday']}T{row['gametime']}").replace(tzinfo=ZoneInfo("America/New_York"))
            games.append({"game_id": row["game_id"], "week": int(row["week"]), "home": fix(row["home_team"]),
                          "away": fix(row["away_team"]), "kickoff": kickoff})
    return games


def _stats(position, pts):
    """A reconciling stat line whose PPR total is exactly Sleeper's pts_ppr."""
    pts = Decimal(str(pts))
    if position == "QB":
        line = {"pass_yd": pts * 25}
        std = half = pts
    else:
        rec = (pts / 4).quantize(Decimal("0.1"))
        line = {"rec": rec, "rec_yd": (pts - rec) * 10}
        std, half = pts - rec, pts - rec / 2
    return {"gp": 1, **{k: float(v) for k, v in line.items()},
            "pts_std": float(std), "pts_half_ppr": float(half), "pts_ppr": float(pts)}


def sleeper_world(*, strict=False):
    """URL -> payload for `provider.capture`. `strict` keeps only fully projected players
    (the sparse contract refuses missing rows instead of leaving them unpriced)."""
    league, pool, proj, games = load_league(), load_pool(), load_projections(), _schedule()
    weeks = range(1, 15)
    plays = {(g["week"], team): g for g in games for team in (g["home"], g["away"])}

    def complete(pid):
        team = pool[pid].get("team")
        return bool(team) and all((str(w) in proj and pid in proj[str(w)]) or (w, team) not in plays for w in weeks)

    rosters = []
    for team in league["teams"]:
        players = [p for p in team["players"] if not strict or complete(p)]
        rosters.append({"roster_id": team["roster_id"], "owner_id": team["owner_id"], "players": players,
                        "reserve": [], "taxi": [],
                        "settings": {"wins": 0, "losses": 0, "ties": 0, "fpts": 0, "fpts_against": 0, "ppts": 0}})
    source = {
        f"{API}/state/nfl": {"season": "2026", "season_type": "regular", "week": 1},
        f"{API}/league/{LEAGUE_ID}": {
            "league_id": LEAGUE_ID, "name": "Fixture", "season": "2026", "sport": "nfl", "season_type": "regular",
            "status": "in_season", "total_rosters": len(rosters), "scoring_settings": dict(SCORING),
            "roster_positions": league["slots"] + ["BN"] * 15,
            "settings": {"playoff_week_start": 15, "playoff_teams": 6, "start_week": 1}},
        f"{API}/league/{LEAGUE_ID}/rosters": rosters,
        f"{API}/league/{LEAGUE_ID}/users": [],
        f"{API}/league/{LEAGUE_ID}/traded_picks": [],
        f"{API}/players/nfl": {pid: {"fantasy_positions": [r["position"]], "position": r["position"],
                                     "team": r.get("team"), "full_name": r["full_name"]} for pid, r in pool.items()},
        f"https://api.sleeper.app/schedule/nfl/regular/2026": [
            {k: g[k] for k in ("game_id", "week", "home", "away")} for g in games],
    }
    for w in weeks:
        source[f"{API}/league/{LEAGUE_ID}/matchups/{w}"] = [
            {"roster_id": r["roster_id"], "matchup_id": (r["roster_id"] + 1) // 2} for r in rosters]
        source[f"https://api.sleeper.app/scores/nfl/regular/2026/{w}"] = [
            {"game_id": g["game_id"], "season": "2026", "week": w, "season_type": "regular", "sport": "nfl",
             "status": "pre_game", "start_time": int(g["kickoff"].timestamp() * 1000),
             "metadata": {"home_team": g["home"], "away_team": g["away"], "status": "scheduled",
                          "has_started": False, "is_in_progress": False, "is_over": False, "canceled": False}}
            for g in games if g["week"] == w]
        rows = []
        for pid, item in sorted(proj.get(str(w), {}).items()):
            team = (pool.get(pid) or {}).get("team")
            game = plays.get((w, team))
            if game is None:
                continue  # no team, or a bye: Sleeper has no game row to join
            rows.append({"player_id": pid, "season": "2026", "week": w, "season_type": "regular",
                         "category": "proj", "company": "rotowire", "game_id": game["game_id"], "team": team,
                         "opponent": game["away"] if game["home"] == team else game["home"],
                         "stats": _stats(item["pos"], item["pts_ppr"])})
        source[f"https://api.sleeper.app/projections/nfl/2026/{w}?season_type=regular"] = rows
    return source


def capture_cfg(contract):
    return {"ir_maxpf": "exclude", "empty_slots": "fill_available", "scoring_contract": contract,
            "availability_scenario": "conditional_provider_forecast", "reserve_activation": "exclude_current_reserve"}


@lru_cache(maxsize=None)
def _captured(contract):
    source = sleeper_world(strict=contract != BEST_AVAILABLE)
    return provider.capture(LEAGUE_ID, "me", capture_cfg(contract), lambda url: deepcopy(source[url]),
                            captured_at=CAPTURED_AT, clock=lambda: CAPTURED_AT)


def captured_snapshot(contract=BEST_AVAILABLE):
    """A fresh copy of the real capture over the fixture world (cached per contract)."""
    return deepcopy(_captured(contract))


@pytest.mark.parametrize("contract", [BEST_AVAILABLE, SPARSE])
def test_derived_points_reproduce_stored_lineup_totals(contract):
    snapshot = captured_snapshot(contract)
    assert set(snapshot["coverage"]["inactive_slot_coefficients"]) == {"fgm", "pts_allow_0"}
    result = season_points.lineup_parity(snapshot)
    assert result["mismatches"] == []
    # Model v6 fills an open slot from free agents; those team-weeks are skipped.
    assert result["checked"] + result["skipped"] == 12 * 14 and result["checked"] >= 150


def test_points_match_the_projection_fixture():
    snapshot, proj, pool = captured_snapshot(), load_projections(), load_pool()
    plays = {(g["week"], team) for g in _schedule() for team in (g["home"], g["away"])}
    points = season_points.player_points(snapshot)
    assert sorted(points) == list(range(1, 15))
    rostered = {p for t in load_league()["teams"] for p in t["players"]}
    priced = byes = 0
    for week, rows in points.items():
        for pid, value in rows.items():
            assert pid in rostered
            if value == season_points.BYE:
                byes += 1
                assert (week, pool[pid]["team"]) not in plays
            elif value is not None:
                priced += 1
                assert value == Decimal(str(proj[str(week)][pid]["pts_ppr"]))
            else:
                assert pid not in proj[str(week)] or not pool[pid].get("team")
    assert priced > 3000 and byes > 200
    # A rostered player with no team has no row at all: absent, never zero.
    no_team = next(p for p in sorted(rostered) if not pool[p].get("team"))
    assert all(points[w].get(no_team) is None for w in points)


@pytest.mark.parametrize("change", [
    {"projection_status": "unpriced"},
    {"availability": 0},
    {"availability": None},
    {"phase": "completed", "projection_status": "completed_actual", "actual_points": "30"},
    {"stats": {}},
])
def test_unknown_rows_are_none(change):
    snapshot = captured_snapshot()
    entry = next(e for e in snapshot["player_week_inputs"] if not e["input"].get("bye"))
    entry["input"].update(change)
    assert season_points.player_points(snapshot)[entry["week"]][entry["player_id"]] is None


def test_free_agent_rows_are_kept_apart():
    snapshot = captured_snapshot()
    baseline = season_points.free_agent_points(snapshot)  # {} under v5; v6 records the fills it used
    assert not any(pid in rows for rows in baseline.values() for pid in
                   {p for rows in season_points.player_points(snapshot).values() for p in rows})
    template = next(e for e in snapshot["player_week_inputs"] if not e["input"].get("bye") and not e.get("free_agent"))
    free_agent = deepcopy(template)
    free_agent.update(player_id="fa1", free_agent=True, some_v7_field={"x": 1})
    free_agent["input"]["free_agent"] = True
    snapshot["player_week_inputs"].append(free_agent)
    snapshot["coverage"]["fa_filled_slots"] = 0  # a v6 coverage field: ignored
    assert "fa1" not in season_points.player_points(snapshot)[template["week"]]
    fa = season_points.free_agent_points(snapshot)
    week = template["week"]
    assert fa == {**baseline, week: {**baseline.get(week, {}), "fa1": season_points.player_points(snapshot)[week][template["player_id"]]}}


@pytest.mark.parametrize("snapshot", [None, [], {}, {"player_week_inputs": [], "scoring": {}},
                                      {"player_week_inputs": [{"week": 1}], "scoring": {}, "slots": ["QB"]}])
def test_malformed_snapshot_raises_unavailable(snapshot):
    with pytest.raises(Unavailable):
        season_points.player_points(snapshot)
