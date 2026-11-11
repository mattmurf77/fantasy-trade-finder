"""Universal weekly score SD: pooled projection error, later-week holdout.

For every team-week in the supplied Sleeper leagues, compares the projected
best lineup of that week's roster (the simulator's future mean: provider weekly
projections scored with the league's own settings, best legal assignment) with
the score the team actually recorded. Errors are pooled across teams and
leagues; one SD is selected on the early weeks and checked on later weeks that
played no part in selecting it.

Reads the public Sleeper API only. League ids come from a file that is never
committed; output is aggregate (no league, team, manager or player identity).

    python docs/plans/league-projections/universal-sd/backtest.py \
        --leagues /path/outside/repo/league_ids.txt --season 2026 \
        --select-weeks 1-6 --holdout-weeks 7-9 --cache /path/outside/repo/cache \
        --out docs/plans/league-projections/universal-sd/backtest-result.json
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from backend.league_projections.core import SLOTS, Unavailable, decimal, optimize, score  # noqa: E402
from backend.league_projections.provider import LINEAR_PROJECTED_EVENTS  # noqa: E402
from backend.league_projections.scoring import best_available  # noqa: E402
from backend.season_forecasts import normalize_scoring_for_slots  # noqa: E402

API = "https://api.sleeper.app"
CANDIDATES = (15, 20, 22.5, 25, 27.5, 30, 35, 40)


def fetch(url, cache):
    path = cache / (url.replace("https://", "").replace("/", "_").replace("?", "_") + ".json")
    if path.exists():
        return json.loads(path.read_text())
    request = urllib.request.Request(url, headers={"User-Agent": "projection-backtest"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read())
    path.write_text(json.dumps(payload))
    time.sleep(.15)
    return payload


def span(text):
    low, _, high = text.partition("-")
    return list(range(int(low), int(high or low) + 1))


def phi(z):
    return .5 * math.erfc(-z / math.sqrt(2))


def projected_points(raw, scoring, present, meta):
    """The provider's best-available player score, or None when unpriced."""
    stats = (raw or {}).get("stats") or {}
    if not raw or not stats:
        return None
    try:
        row = best_available(raw, scoring, present, positions=meta.get("fantasy_positions") or [],
                             primary_position=meta.get("position"))
    except Unavailable:
        return None
    if row.get("projection_status") == "unpriced":
        return None
    covered = {k: v for k, v in scoring.items() if k in row.get("stats", {}) and k in row.get("supported_keys", [])}
    if not covered:
        return None
    return score(row.get("stats", {}), covered, row.get("supported_keys", []))


def league_rows(league_id, season, weeks, cache, metadata):
    league = fetch(f"{API}/v1/league/{league_id}", cache)
    if not isinstance(league, dict) or str(league.get("season")) != str(season) or league.get("sport") != "nfl":
        return None, "other_season_or_sport"
    slots = [s for s in league.get("roster_positions") or [] if s not in {"BN", "IR", "TAXI"}]
    if not slots or any(s not in SLOTS for s in slots):
        return None, "unsupported_lineup"
    if (league.get("settings") or {}).get("best_ball"):
        return None, "best_ball"
    scoring = normalize_scoring_for_slots(league["scoring_settings"], slots)
    last = int((league.get("settings") or {}).get("playoff_week_start") or 15) - 1
    rows = []
    for week in weeks:
        if week > last:
            continue
        matchups = fetch(f"{API}/v1/league/{league_id}/matchups/{week}", cache)
        payload = fetch(f"{API}/projections/nfl/{season}/{week}?season_type=regular", cache)
        if not isinstance(matchups, list) or not isinstance(payload, list):
            continue
        present = {key for raw in payload for key in ((raw.get("stats") or {}) if isinstance(raw, dict) else {})} & LINEAR_PROJECTED_EVENTS
        by_id = {str(raw.get("player_id")): raw for raw in payload if isinstance(raw, dict)}
        teams = {}
        for team in matchups:
            if team.get("points") is None or team.get("custom_points") is not None or team.get("matchup_id") is None:
                continue
            pool = []
            for pid in map(str, team.get("players") or []):
                meta = metadata.get(pid) or {}
                if not meta.get("fantasy_positions"):
                    continue
                points = projected_points(by_id.get(pid), scoring, present, meta)
                if points is not None:
                    pool.append({"player_id": pid, "positions": meta["fantasy_positions"], "points": str(points)})
            if not pool:
                continue
            lineup = optimize(slots, pool, empty_policy="fill_available")
            teams[team["roster_id"]] = {"matchup": team["matchup_id"], "projected": float(decimal(lineup["points"])),
                                        "actual": float(decimal(team["points"])), "gaps": len(lineup["gaps"])}
        for roster_id, item in teams.items():
            rows.append({"week": week, "roster": roster_id, "slots": len(slots), **item})
    return rows, None


def summarize(errors):
    if len(errors) < 2:
        return {"team_weeks": len(errors)}
    ordered = sorted(errors)
    return {"team_weeks": len(errors), "mean_error": statistics.mean(errors),
            "sd_about_mean": statistics.stdev(errors),
            "rmse_about_projection": math.sqrt(sum(e * e for e in errors) / len(errors)),
            "median_error": statistics.median(errors),
            "p10": ordered[int(.1 * (len(ordered) - 1))], "p90": ordered[int(.9 * (len(ordered) - 1))]}


def evaluate(rows, sd):
    errors = [r["actual"] - r["projected"] for r in rows]
    coverage = {str(level): sum(abs(e) <= z * sd for e in errors) / len(errors)
                for level, z in ((.5, .6744897501960817), (.8, 1.2815515655446004), (.9, 1.6448536269514722))}
    games = defaultdict(list)
    for r in rows:
        games[(r["league"], r["week"], r["matchup"])].append(r)
    brier, logloss, bins, count = 0., 0., defaultdict(lambda: [0, 0.]), 0
    for pair in games.values():
        if len(pair) != 2 or pair[0]["actual"] == pair[1]["actual"]:
            continue
        a, b = sorted(pair, key=lambda r: r["roster"])
        p = min(1 - 1e-9, max(1e-9, phi((a["projected"] - b["projected"]) / (sd * math.sqrt(2)))))
        won = 1. if a["actual"] > b["actual"] else 0.
        favourite, favourite_won = (p, won) if p >= .5 else (1 - p, 1 - won)
        brier += (p - won) ** 2
        logloss += -(won * math.log(p) + (1 - won) * math.log(1 - p))
        bucket = min(4, int((favourite - .5) * 10))
        bins[bucket][0] += 1
        bins[bucket][1] += favourite_won
        count += 1
    return {"sd": sd, "interval_coverage": coverage, "games": count,
            "brier": brier / count if count else None, "log_loss": logloss / count if count else None,
            "favourite_calibration": [{"predicted_range": [.5 + k / 10, .6 + k / 10], "games": n, "favourite_won": w / n}
                                      for k, (n, w) in sorted(bins.items())]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--leagues", required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--select-weeks", required=True)
    parser.add_argument("--holdout-weeks", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    select, holdout = span(args.select_weeks), span(args.holdout_weeks)
    metadata = fetch(f"{API}/v1/players/nfl", cache)
    rows, skipped = [], Counter()
    ids = sorted({line.strip() for line in Path(args.leagues).read_text().splitlines() if line.strip().isdigit()})
    for number, league_id in enumerate(ids):
        found, reason = league_rows(league_id, args.season, select + holdout, cache, metadata)
        if found is None:
            skipped[reason] += 1
            continue
        rows.extend({**row, "league": number} for row in found)
    chosen = [r for r in rows if r["week"] in select]
    later = [r for r in rows if r["week"] in holdout]
    selection = summarize([r["actual"] - r["projected"] for r in chosen])
    selected_sd = round(selection["rmse_about_projection"] * 2) / 2
    by_slots = defaultdict(list)
    for r in rows:
        by_slots[r["slots"]].append(r["actual"] - r["projected"])
    update_days = Counter()
    for week in select + holdout:
        payload = fetch(f"{API}/projections/nfl/{args.season}/{week}?season_type=regular", cache)
        stamps = sorted(raw.get("updated_at") or 0 for raw in payload if isinstance(raw, dict) and (raw.get("stats") or {}).get("gp"))
        if stamps:
            update_days[week] = time.strftime("%Y-%m-%d", time.gmtime(stamps[len(stamps) // 2] / 1000))
    result = {
        "question": "one app-wide SD for weekly team scores about the projected best lineup",
        "units": "fantasy points per team per week, in each league's own scoring",
        "distribution": "normal, centred on the projected best-lineup total, independent by team and week",
        "season": args.season, "select_weeks": select, "holdout_weeks": holdout,
        "leagues_used": len({r["league"] for r in rows}), "leagues_skipped": dict(skipped),
        "selection": selection, "selected_sd": selected_sd,
        "selection_rule": "root-mean-square error about the projection on the selection weeks, rounded to 0.5",
        "holdout": summarize([r["actual"] - r["projected"] for r in later]),
        "holdout_candidates": [evaluate(later, sd) for sd in sorted(set(CANDIDATES) | {selected_sd})],
        "by_starting_slots": {str(k): summarize(v) for k, v in sorted(by_slots.items())},
        "team_weeks_with_unfilled_slot": sum(bool(r["gaps"]) for r in rows),
        "projection_rows_median_update_date_by_week": dict(update_days),
        "limits": ["Projection rows are the provider's stored rows for past weeks. Their last-update stamps fall after the games, so they are not proven pregame snapshots.",
                   "Rosters are each week's recorded roster; the simulator projects the current roster forward.",
                   "IDP bye replacements are not modelled here."],
    }
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("leagues_used", "leagues_skipped", "selection", "selected_sd", "holdout", "by_starting_slots", "projection_rows_median_update_date_by_week")}, indent=1))
    for item in result["holdout_candidates"]:
        print(item["sd"], item["interval_coverage"], "brier %.4f logloss %.4f games %d" % (item["brier"], item["log_loss"], item["games"]))


if __name__ == "__main__":
    main()
