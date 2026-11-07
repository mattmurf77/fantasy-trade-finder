"""Read-only research probe. Emits aggregates only; never persists raw league data.

The explicitly authorized reference league is the sole league requested. No users,
names, rosters, rankings or preferences are fetched. /matchups stays memory-only.
From repository root: PYTHONPATH=. python3 docs/plans/league-projections/provider-coverage-probe.py --league-id "$PROJECTION_REFERENCE_LEAGUE_ID" > /private/tmp/projection-aggregate-coverage.json
"""
import argparse
import concurrent.futures
from collections import Counter
from datetime import datetime, timezone
import json
import urllib.request
from backend.league_projections.timing import validate_season_schedule, normalize_week_games, classify_player_game, CoverageError

BASE = "https://api.sleeper.app/"
SEASON = 2026


def fetch(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league-id", required=True, help="Authorized reference league; never written into output")
    league_id = parser.parse_args().league_id
    if not league_id.isdigit():
        parser.error("league ID must be numeric")
    captured_at = datetime.now(timezone.utc).isoformat()
    paths = ["schedule/nfl/regular/2026", f"v1/league/{league_id}"]
    paths += [f"projections/nfl/{SEASON}/{w}?season_type=regular" for w in range(9, 15)]
    paths += [f"scores/nfl/regular/{SEASON}/{w}" for w in range(8, 15)]
    paths += [p for w in range(1, 9) for p in (f"stats/nfl/{SEASON}/{w}?season_type=regular", f"v1/league/{league_id}/matchups/{w}")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        fetched = dict(zip(paths, pool.map(fetch, paths)))
    schedule = fetched[paths[0]]
    schedule_index = validate_season_schedule(schedule)
    scoring = {k: v for k, v in fetched[paths[1]]["scoring_settings"].items() if v}
    report = {"captured_at": captured_at, "evidence_type": "observed_undocumented_provider_responses_not_API_guarantee",
              "raw_league_data_persisted": False, "season": SEASON,
              "schedule": {"games": len(schedule), "unique_game_ids": len(schedule_index),
                           "teams": len({x[k] for x in schedule for k in ("home", "away")})},
              "weekly": {}, "actual_scoring": {"weeks": {}}}
    projection_keys = set()
    for week in range(8, 15):
        scores = fetched[f"scores/nfl/regular/{SEASON}/{week}"]
        games = normalize_week_games(schedule_index, scores, SEASON, week, captured_at)
        item = {"scores_url": BASE + f"scores/nfl/regular/{SEASON}/{week}",
                "games": len(games), "phases": dict(Counter(x["phase"] for x in games.values()))}
        report["weekly"][str(week)] = item
        if week == 8:
            continue
        projections = fetched[f"projections/nfl/{SEASON}/{week}?season_type=regular"]
        keys = set().union(*(set(x.get("stats") or {}) for x in projections))
        projection_keys.update(keys)
        classes, errors, injury_gp1 = Counter(), Counter(), Counter()
        for row in projections:
            team = row.get("team") or (row.get("player") or {}).get("team")
            try:
                classes[classify_player_game(row, team, schedule_index, games, SEASON, week)["phase"]] += 1
            except CoverageError as error:
                errors[str(error)] += 1
            if (row.get("stats") or {}).get("gp") == 1:
                injury_gp1[str((row.get("player") or {}).get("injury_status"))] += 1
        kicker_rows = [x["stats"] for x in projections if (x.get("player") or {}).get("position") == "K"
                       and "fga" in x.get("stats", {}) and "fgm" in x.get("stats", {})]
        item.update({"projection_url": BASE + f"projections/nfl/{SEASON}/{week}?season_type=regular",
                     "projection_rows": len(projections), "projection_stat_keys": sorted(keys),
                     "normalization_classes": dict(classes), "normalization_errors": dict(errors),
                     "nonzero_reference_rules_absent_from_full_forecast": sorted(set(scoring) - keys),
                     "gp1_current_injury_labels": dict(injury_gp1),
                     "kicker_attempt_minus_made": {"rows_with_both_operands": len(kicker_rows),
                         "negative_derived_misses": sum(x["fga"] < x["fgm"] for x in kicker_rows),
                         "max_abs_difference_from_sum_present_miss_bands": max((abs(x["fga"] - x["fgm"] - sum(v for k, v in x.items() if k.startswith("fgmiss_"))) for x in kicker_rows), default=None)}})
    counts, actual_keys = Counter(), set()
    for week in range(1, 9):
        stats = fetched[f"stats/nfl/{SEASON}/{week}?season_type=regular"]
        matchups = fetched[f"v1/league/{league_id}/matchups/{week}"]
        by_id = {str(x["player_id"]): x["stats"] for x in stats}
        actual_keys.update(set().union(*(set(x) for x in by_id.values())))
        weekly, max_diff = Counter(), 0
        for row in matchups:
            for player_id, official in (row.get("players_points") or {}).items():
                weekly["official_player_week_entries"] += 1
                if player_id not in by_id:
                    weekly["missing_actual_stat_row"] += 1
                    weekly["missing_row_with_nonzero_official_points"] += bool(official)
                    continue
                reconstructed = sum(float(c) * float(by_id[player_id].get(k, 0)) for k, c in scoring.items())
                difference = abs(round(reconstructed - float(official), 6))
                weekly["compared"] += 1
                weekly["mismatch_over_one_cent"] += difference > .010001
                max_diff = max(max_diff, difference)
        counts.update(weekly)
        report["actual_scoring"]["weeks"][str(week)] = {**weekly, "max_abs_difference": max_diff}
    report["actual_scoring"].update({"totals": dict(counts), "nonzero_reference_rules_absent_all_actuals": sorted(set(scoring) - actual_keys),
                                    "actual_stat_keys": sorted(actual_keys)})
    report["nonzero_reference_rules_absent_all_future_forecasts"] = sorted(set(scoring) - projection_keys)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
