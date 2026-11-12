"""Are the playoff odds overconfident? Week-to-week persistence of projection error.

Rebuilds the universal-SD backtest's team-week table (projected best lineup vs
recorded score) from the cached Sleeper responses, then measures whether a
team's weekly errors are independent, tests the independence assumption at
season scale, and simulates the rest of the regular season with and without a
persistent team draw. Offline only: a cache miss raises and is listed, never
fetched. Output is aggregate (no league, team, manager or player identity).

    python docs/plans/league-projections/calibration-check/calibration_check.py \
        --cache /path/outside/repo/cache --leagues /path/outside/repo/league_ids.txt \
        --out docs/plans/league-projections/calibration-check/result.json

Needs numpy (the season simulation) besides the repo's own modules.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import statistics
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import calibration_stats as cs  # noqa: E402

API = "https://api.sleeper.app"
SEASON = 2026
WEEKS = list(range(1, 10))
WINDOWS = (3, 5, 7, 9)


class CacheMiss(RuntimeError):
    pass


def _no_network(*_args, **_kwargs):
    raise CacheMiss("network access is disabled in this script")


def load_backtest(cache):
    spec = importlib.util.spec_from_file_location("sd_backtest", HERE.parent / "universal-sd" / "backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def cache_only(url, _cache=None):
        path = cache / (url.replace("https://", "").replace("/", "_").replace("?", "_") + ".json")
        if not path.exists():
            raise CacheMiss(url)
        return json.loads(path.read_text())

    module.fetch = cache_only
    urllib.request.urlopen = _no_network
    return module, cache_only


# ---------------------------------------------------------------- step 1: table
def build_table(cache, leagues_file):
    bt, fetch = load_backtest(cache)
    metadata = fetch(f"{API}/v1/players/nfl")
    ids = sorted({line.strip() for line in Path(leagues_file).read_text().splitlines() if line.strip().isdigit()})
    rows, leagues = [], {}
    for number, league_id in enumerate(ids):
        found, _reason = bt.league_rows(league_id, SEASON, WEEKS, cache, metadata)
        if found is None:
            continue
        league = fetch(f"{API}/v1/league/{league_id}")
        settings = league.get("settings") or {}
        leagues[number] = {"id": league_id, "median": bool(settings.get("league_average_match")),
                           "playoff_teams": int(settings.get("playoff_teams") or 6),
                           "playoff_week_start": int(settings.get("playoff_week_start") or 15)}
        rows.extend({**row, "league": number} for row in found)
    return rows, leagues


def headline(rows):
    def stats(errors):
        return {"team_weeks": len(errors), "mean_error": statistics.mean(errors),
                "rmse": math.sqrt(sum(e * e for e in errors) / len(errors))}
    errors = lambda ws: [r["actual"] - r["projected"] for r in rows if r["week"] in ws]  # noqa: E731
    return {"all": stats(errors(WEEKS)), "weeks_1_6": stats(errors(range(1, 7))), "weeks_7_9": stats(errors(range(7, 10)))}


# ---------------------------------------------------------------- panels
def panel_from(rows):
    """League -> team -> errors by week, plus the matching keys."""
    by = defaultdict(dict)
    for r in rows:
        by[r["league"]].setdefault(r["roster"], {})[r["week"]] = r
    panel, keys = [], []
    for league in sorted(by):
        teams = sorted(t for t, weeks in by[league].items() if all(w in weeks for w in WEEKS))
        panel.append([[by[league][t][w]["actual"] - by[league][t][w]["projected"] for w in WEEKS] for t in teams])
        keys.append((league, teams))
    return panel, keys, by


def projection_panel(by, keys):
    return [[[by[league][t][w]["projected"] for w in WEEKS] for t in teams] for league, teams in keys]


def actual_panel(by, keys):
    return [[[by[league][t][w]["actual"] for w in WEEKS] for t in teams] for league, teams in keys]


def spread_slopes(pair):
    """Slope of relative actual on relative projected: below 1 means projections
    overstate the gaps between teams (the other road to overconfident odds)."""
    proj, act = (cs.relative(p) for p in pair)
    x = [v for league in proj for team in league for v in team]
    y = [v for league in act for team in league for v in team]
    X = [sum(team) for league in proj for team in league]
    Y = [sum(team) for league in act for team in league]
    return {"weekly": sum(a * b for a, b in zip(x, y)) / sum(a * a for a in x),
            "nine_week_total": sum(a * b for a, b in zip(X, Y)) / sum(a * a for a in X)}


def drift_stats(proj):
    gamma = cs.semivariogram(proj, 5)
    early = cs.semivariogram(proj, 3, weeks=range(0, 4))
    return {"step_variance": cs.drift_step_variance(gamma), "step_variance_weeks_1_4": cs.drift_step_variance(early),
            **{f"gamma_lag_{h}": v for h, v in gamma.items()}, **{f"gamma_weeks_1_4_lag_{h}": v for h, v in early.items()}}


def cross_team_correlation(rows):
    """Correlation of two different teams' errors in the same league-week (each
    week's all-league mean removed), for opponents and for the other pairs."""
    week_mean = {w: statistics.mean(r["actual"] - r["projected"] for r in rows if r["week"] == w) for w in WEEKS}
    groups = defaultdict(list)
    for r in rows:
        groups[(r["league"], r["week"])].append(r)
    pairs = {"opponents": [], "other_pairs": []}
    for members in groups.values():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                ea, eb = (x["actual"] - x["projected"] - week_mean[x["week"]] for x in (a, b))
                kind = "opponents" if a["matchup"] == b["matchup"] else "other_pairs"
                pairs[kind] += [(ea, eb), (eb, ea)]
    return {k: {"pairs": len(v) // 2, "correlation": statistics.correlation(*zip(*v))} for k, v in pairs.items()}


def games_from(by, keys, sd):
    """Per team, per week: [(result, pregame win probability)] for its head-to-head game."""
    out = []
    for league, teams in keys:
        for t in teams:
            weeks = []
            for w in WEEKS:
                me = by[league][t][w]
                opp = [by[league][o][w] for o in by[league] if o != t and w in by[league][o] and by[league][o][w]["matchup"] == me["matchup"]]
                if len(opp) != 1:
                    weeks.append([])
                    continue
                other = opp[0]
                result = 1. if me["actual"] > other["actual"] else 0. if me["actual"] < other["actual"] else .5
                weeks.append([(result, cs.win_probability(me["projected"], other["projected"], sd))])
            out.append(weeks)
    return out


def regroup_games(games, keys):
    """Flat team list -> league -> team, for team resampling inside leagues."""
    out, i = [], 0
    for _league, teams in keys:
        out.append(games[i:i + len(teams)])
        i += len(teams)
    return out


# ---------------------------------------------------------------- step 2/3
def persistence(panel):
    parts = cs.variance_components(panel)
    return {**parts, "lag1": cs.lag_correlation(panel, 1), "lag2": cs.lag_correlation(panel, 2),
            "lag3": cs.lag_correlation(panel, 3),
            **{f"sum_ratio_{k}": cs.sum_variance_ratio(panel, k)["ratio"] for k in WINDOWS}}


def drift(panel):
    means = [statistics.mean(team[w] for league in panel for team in league) for w in range(len(WEEKS))]
    x = [w + 1 for w in range(len(WEEKS))]
    mx, my = statistics.mean(x), statistics.mean(means)
    slope = sum((a - mx) * (b - my) for a, b in zip(x, means)) / sum((a - mx) ** 2 for a in x)
    return {"by_week": means, "slope_per_week": slope}


def overdispersion(grouped_games):
    flat = [team for league in grouped_games for team in league]
    return {f"win_ratio_{k}": cs.win_overdispersion(flat, k)["ratio"] for k in WINDOWS}


def bootstrap(stat, data, reps, seed, resample=cs.resample_teams):
    rng = random.Random(seed)
    draws = [stat(resample(data, rng)) for _ in range(reps)]
    return {key: cs.interval([d[key] for d in draws]) for key in draws[0]
            if not isinstance(draws[0][key], list)}, draws


def _paired_resample(pair, rng):
    proj, act = pair
    picks = [[rng.randrange(len(league)) for _ in league] for league in proj]
    return [[[league[i] for i in idx] for league, idx in zip(proj, picks)],
            [[league[i] for i in idx] for league, idx in zip(act, picks)]]


def resample_leagues(panel, rng):
    return [panel[rng.randrange(len(panel))] for _ in panel]


def reliability(rows, sd):
    games = defaultdict(list)
    for r in rows:
        games[(r["league"], r["week"], r["matchup"])].append(r)
    pairs = [g for g in games.values() if len(g) == 2 and g[0]["actual"] != g[1]["actual"]]
    bins = defaultdict(lambda: [0, 0, 0.])
    predicted = observed = 0.
    for a, b in pairs:
        p = cs.win_probability(a["projected"], b["projected"], sd)
        fav, other = (a, b) if p >= .5 else (b, a)
        q = max(p, 1 - p)
        won = fav["actual"] > other["actual"]
        k = min(4, int((q - .5) * 10))
        bins[k][0] += 1
        bins[k][1] += won
        bins[k][2] += q
        predicted += q
        observed += won
    table = []
    for k in sorted(bins):
        n, w, q = bins[k]
        table.append({"model_says": [round(.5 + k / 10, 1), round(.6 + k / 10, 1)], "games": n,
                      "mean_model_probability": q / n, "favourite_won": w / n, "wilson_95": wilson(w, n)})
    return {"games": len(pairs), "mean_model_favourite_probability": predicted / len(pairs),
            "favourite_win_rate": observed / len(pairs), "favourite_win_rate_95": wilson(observed, len(pairs)),
            "bins": table}, pairs


def wilson(wins, n, z=1.959964):
    if not n:
        return [None, None]
    p = wins / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [centre - half, centre + half]


def best_game_sd(pairs):
    """The single-game SD that maximizes head-to-head log likelihood."""
    def loglik(sd):
        total = 0.
        for a, b in pairs:
            p = min(1 - 1e-12, max(1e-12, cs.win_probability(a["projected"], b["projected"], sd)))
            total += math.log(p) if a["actual"] > b["actual"] else math.log(1 - p)
        return total
    grid = [x / 2 for x in range(20, 81)]
    return max(grid, key=loglik)


# ---------------------------------------------------------------- step 4: season simulation
def league_state(by, leagues, league):
    teams = sorted(by[league])
    index = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    wins, losses, ties, pf, pa = (np.zeros(n) for _ in range(5))
    from backend.league_projections.core import median_outcomes
    for w in WEEKS:
        rows = [by[league][t][w] for t in teams]
        scores = [r["actual"] for r in rows]
        for i, r in enumerate(rows):
            pf[i] += r["actual"]
            j = next(index[t] for t in teams if t != teams[i] and by[league][t][w]["matchup"] == r["matchup"])
            pa[i] += scores[j]
            if scores[i] > scores[j]:
                wins[i] += 1
            elif scores[i] < scores[j]:
                losses[i] += 1
            else:
                ties[i] += 1
        if leagues[league]["median"]:
            for i, outcome in enumerate(median_outcomes(scores)):
                (wins, losses, ties)[outcome][i] += 1
    means = np.array([statistics.mean(by[league][t][w]["projected"] for w in WEEKS[-3:]) for t in teams])
    return {"teams": teams, "wins": wins, "losses": losses, "ties": ties, "pf": pf, "pa": pa, "means": means,
            "median": leagues[league]["median"], "playoff": leagues[league]["playoff_teams"],
            "remaining": leagues[league]["playoff_week_start"] - 1 - WEEKS[-1]}


def random_opponents(rng, iterations, n):
    order = np.argsort(rng.random((iterations, n)), axis=1)
    opp = np.empty_like(order)
    rows = np.arange(iterations)[:, None]
    opp[rows, order[:, 0::2]] = order[:, 1::2]
    opp[rows, order[:, 1::2]] = order[:, 0::2]
    return opp


def simulate(state, tau, weekly_sd, iterations, seed, schedule=None, drift_sd=0.):
    """Playoff probability per team. schedule: list of opponent index arrays per
    remaining week (fixed), or None for a fresh random pairing every week of
    every simulated season. Common random numbers: the same seed gives the same
    standard-normal draws, so scenarios differ only by tau / weekly_sd / drift.
    drift_sd: a team's mean takes a random-walk step of this SD each future
    week (horizon-growing uncertainty), shared by all its later weeks."""
    rng = np.random.default_rng(seed)
    n, weeks = len(state["teams"]), state["remaining"]
    points = np.tile(2 * state["wins"] + state["ties"], (iterations, 1))
    pf = np.tile(state["pf"], (iterations, 1))
    pa = np.tile(state["pa"], (iterations, 1))
    persistent = rng.standard_normal((iterations, n)) * tau
    rows = np.arange(iterations)[:, None]
    walk = np.zeros((iterations, n))
    for w in range(weeks):
        walk += drift_sd * rng.standard_normal((iterations, n))
        z = rng.standard_normal((iterations, n))
        opp = random_opponents(rng, iterations, n) if schedule is None else np.tile(schedule[w], (iterations, 1))
        scores = state["means"] + persistent + walk + weekly_sd * z
        theirs = scores[rows, opp]
        points += 2 * (scores > theirs) + (scores == theirs)
        pf += scores
        pa += theirs
        if state["median"]:
            ranks = np.argsort(np.argsort(scores, axis=1), axis=1)
            points += 2 * (ranks >= n // 2)
    lottery = rng.random((iterations, n))
    order = np.lexsort((lottery, pa, pf, points), axis=1)
    made = np.zeros((iterations, n), dtype=bool)
    np.put_along_axis(made, order[:, -state["playoff"]:], True, axis=1)
    return made.mean(axis=0)


def validate_engine(state, iterations, seed):
    """Run the production simulator and this engine on the same fixed schedule."""
    from backend.league_projections import simulation
    n = len(state["teams"])
    rng = np.random.default_rng(seed)
    schedule = [random_opponents(rng, 1, n)[0] for _ in range(state["remaining"])]
    ids = list(range(1, n + 1))
    completed = len(WEEKS)
    per_week_pf = state["pf"] / completed
    teams = []
    for i in range(n):
        history = [round(float(per_week_pf[i]), 6)] * completed
        teams.append({"roster_id": ids[i], "name": f"T{i}", "wins": int(state["wins"][i]), "losses": int(state["losses"][i]),
                      "ties": int(state["ties"][i]), "points_for": sum(history), "points_against": float(state["pa"][i]),
                      "maxpf": sum(history), "actual_history": history, "maxpf_history": []})
    weeks = []
    for w, opp in enumerate(schedule):
        games = sorted({tuple(sorted((ids[i], ids[int(opp[i])]))) for i in range(n)})
        weeks.append({"week": WEEKS[-1] + 1 + w, "games": [list(g) for g in games],
                      "teams": {str(ids[i]): {"actual": {"points": str(round(float(state["means"][i]), 4))},
                                              "maxpf": {"points": str(round(float(state["means"][i]), 4))}} for i in range(n)}})
    snapshot = {"teams": teams, "playoff_spots": state["playoff"], "playoff_byes": 0, "weeks": weeks,
                "completed_weeks": completed, "league_format": {"median_game": state["median"]},
                "source": "calibration-check", "captured_at": "offline"}
    cfg = {"iterations": iterations, "seed": 7, "score_sd": 25.0, "residual_correlation": 0,
           "seeding": "record_pf_higher_pa_random", "draft_tie": "random_exact_ties", "ir_maxpf": "exclude",
           "reserve_activation": "exclude_current_reserve", "empty_slots": "fill_available",
           "availability_scenario": "conditional_provider_forecast", "scoring_contract": "sleeper_best_available_v1",
           "maxpf_joint_policy": "mean_preserving_positive_gap_v1", "score_decimals": 2}
    production = simulation.simulate(snapshot, cfg)
    prod = np.array([t["playoff_probability"] for t in sorted(production["teams"], key=lambda t: t["roster_id"])])
    # The production run uses PF = completed history; mirror that state exactly.
    mirror = {**state, "pf": np.array([sum(t["actual_history"]) for t in teams])}
    ours = simulate(mirror, 0., 25., iterations, seed + 1, schedule=schedule)
    se = np.sqrt(prod * (1 - prod) / iterations + ours * (1 - ours) / iterations)
    return {"teams": n, "median_league": state["median"], "iterations_each": iterations,
            "max_abs_difference": float(np.max(np.abs(prod - ours))),
            "max_z": float(np.max(np.abs(prod - ours) / np.maximum(se, 1e-9)))}


def compare(a, b, label):
    a, b = np.concatenate(a), np.concatenate(b)
    change = b - a
    band = (a >= .85) & (a <= .99)
    return {"scenario": label, "teams": int(a.size),
            "at_or_above_95": {"a": int((a >= .95).sum()), "b": int((b >= .95).sum())},
            "at_or_below_5": {"a": int((a <= .05).sum()), "b": int((b <= .05).sum())},
            "mean_abs_change_pts": float(np.mean(np.abs(change)) * 100),
            "largest_abs_change_pts": float(np.max(np.abs(change)) * 100),
            "teams_85_to_99_under_a": int(band.sum()),
            "those_teams_mean_a": float(np.mean(a[band])) if band.any() else None,
            "those_teams_mean_b": float(np.mean(b[band])) if band.any() else None,
            "those_teams_change_range_pts": [float(np.min(change[band]) * 100), float(np.max(change[band]) * 100)] if band.any() else None}


def missing_future(cache, leagues):
    urls = []
    for info in leagues.values():
        for week in range(WEEKS[-1] + 1, info["playoff_week_start"]):
            urls.append(f"{API}/v1/league/{info['id']}/matchups/{week}")
    for week in range(WEEKS[-1] + 1, max(i["playoff_week_start"] for i in leagues.values())):
        urls.append(f"{API}/projections/nfl/{SEASON}/{week}?season_type=regular")
    path = lambda u: cache / (u.replace("https://", "").replace("/", "_").replace("?", "_") + ".json")  # noqa: E731
    return [u for u in urls if not path(u).exists()]


def cached_schedule(cache, info, state):
    """Opponent arrays for the remaining weeks from cached future matchups, or None."""
    index = {t: i for i, t in enumerate(state["teams"])}
    out = []
    for week in range(WEEKS[-1] + 1, info["playoff_week_start"]):
        p = cache / f"api.sleeper.app_v1_league_{info['id']}_matchups_{week}.json"
        if not p.exists():
            return None
        groups = defaultdict(list)
        for team in json.loads(p.read_text()):
            groups[team.get("matchup_id")].append(index[team["roster_id"]])
        opp = np.empty(len(index), dtype=int)
        for members in groups.values():
            if len(members) != 2:
                return None
            opp[members[0]], opp[members[1]] = members[1], members[0]
        out.append(opp)
    return out


# ---------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", required=True)
    parser.add_argument("--leagues", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--missing-out", help="write the uncached URLs needed for an exact run here (outside the repo)")
    parser.add_argument("--boot", type=int, default=1000)
    parser.add_argument("--shuffles", type=int, default=200)
    parser.add_argument("--iterations", type=int, default=40000)
    parser.add_argument("--validate-iterations", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=20261112)
    parser.add_argument("--sd", type=float, default=25.)
    args = parser.parse_args()
    cache = Path(args.cache)

    rows, leagues = build_table(cache, args.leagues)
    head = headline(rows)
    panel, keys, by = panel_from(rows)
    team_count = sum(len(t) for _, t in keys)

    # step 2
    point = persistence(panel)
    intervals, draws = bootstrap(persistence, panel, args.boot, args.seed)
    league_intervals, _ = bootstrap(lambda p: {k: v for k, v in cs.variance_components(p).items()},
                                    panel, args.boot, args.seed + 1, resample=resample_leagues)
    raw_drift = drift(panel)
    mean_drift_ci, _ = bootstrap(lambda p: {"slope_per_week": drift(p)["slope_per_week"],
                                       **{f"week_{w}": drift(p)["by_week"][w - 1] for w in WEEKS}},
                            panel, args.boot, args.seed + 2)

    # global week drift (common to all leagues), and the projection-spread check
    week_means = raw_drift["by_week"]
    within_var = statistics.mean(e * e for league in panel for team in league for e in team) - statistics.mean(week_means) ** 2
    global_week_var = statistics.variance(week_means) - within_var / team_count
    pair = [projection_panel(by, keys), actual_panel(by, keys)]
    slopes = spread_slopes(pair)
    slope_ci, _ = bootstrap(lambda p: spread_slopes(p), pair, args.boot, args.seed + 7,
                            resample=lambda pr, rng: _paired_resample(pr, rng))
    proj = pair[0]
    drift_point = drift_stats(proj)
    drift_ci, _ = bootstrap(drift_stats, proj, args.boot, args.seed + 8)

    # step 3: wins
    games = regroup_games(games_from(by, keys, args.sd), keys)
    wins = overdispersion(games)
    win_ci, _ = bootstrap(overdispersion, games, args.boot, args.seed + 3)
    rel, pairs = reliability(rows, args.sd)
    game_sd = best_game_sd(pairs)
    rng = random.Random(args.seed + 4)
    sd_draws = []
    for _ in range(min(args.boot, 300)):
        sd_draws.append(best_game_sd([pairs[rng.randrange(len(pairs))] for _ in pairs]))
    games_fit = regroup_games(games_from(by, keys, game_sd), keys)
    wins_fit = overdispersion(games_fit)
    win_fit_ci, _ = bootstrap(overdispersion, games_fit, args.boot, args.seed + 5)

    # placebos
    rng = random.Random(args.seed + 6)
    placebo_keys = ("team_share_of_relative", "tau", "lag1", "lag2", "sum_ratio_5", "sum_ratio_9")
    within = [persistence(cs.shuffle_within_team(panel, rng)) for _ in range(args.shuffles)]
    across = [persistence(cs.shuffle_across_teams(panel, rng)) for _ in range(args.shuffles)]

    def shuffle_games(grouped, rng):
        out = []
        for league in grouped:
            new = [[None] * len(WEEKS) for _ in league]
            for w in range(len(WEEKS)):
                column = [team[w] for team in league]
                rng.shuffle(column)
                for t, item in enumerate(column):
                    new[t][w] = item
            out.append(new)
        return out
    across_wins = [overdispersion(shuffle_games(games, rng)) for _ in range(args.shuffles)]

    # Upper bound for tau by inversion: plant a team effect of SD t on a
    # shuffled (team-free) copy of the data; the bound is the smallest t at which
    # fewer than 5% of planted copies show a team share as low as observed.
    tau_curve = {}
    for t in (0., 1., 2., 3., 4., 5., 6., 8.):
        shares = []
        for _ in range(args.shuffles):
            null = cs.shuffle_across_teams(panel, rng)
            planted = [[[e + effect for e in team] for team, effect in zip(league, [rng.gauss(0, t) for _ in league])] for league in null]
            shares.append(cs.variance_components(planted)["team_share_of_relative"])
        tau_curve[t] = sum(v <= point["team_share_of_relative"] for v in shares) / len(shares)
    tau_rejected_1pct = next((t for t, frac in sorted(tau_curve.items()) if frac <= .01), None)

    def p_low(results, key, observed):
        return (1 + sum(r[key] <= observed for r in results)) / (1 + len(results))

    def p_high(results, key, observed):
        return (1 + sum(r[key] >= observed for r in results)) / (1 + len(results))

    def summarize_placebo(results, keys_):
        return {k: {"mean": statistics.mean(r[k] for r in results), "95": cs.interval([r[k] for r in results])} for k in keys_}

    # step 4
    tau = point["tau"]
    tau_lo, tau_hi = intervals["tau"]
    resid_sd = math.sqrt(point["residual"])
    missing = missing_future(cache, leagues)
    if args.missing_out:
        Path(args.missing_out).write_text("\n".join(missing) + ("\n" if missing else ""))
    states = {league: league_state(by, leagues, league) for league in sorted(leagues)}
    schedules = {league: cached_schedule(cache, leagues[league], states[league]) for league in states}
    exact = all(s is not None for s in schedules.values())
    scenarios = {"a_independent_25": (0., args.sd)}
    for name, t in (("b_tau_point", tau), ("b_tau_low", tau_lo), ("b_tau_high", tau_hi), ("b_v4_persistent_5", 5.)):
        t = max(0., min(t, args.sd))
        scenarios[name] = (t, math.sqrt(args.sd ** 2 - t ** 2))
    scenarios["b_tau_3_largest_plausible"] = (3., math.sqrt(args.sd ** 2 - 9.))
    scenarios["b_hypothetical_tau_10"] = (10., math.sqrt(args.sd ** 2 - 100.))
    scenarios["c_data_matched"] = (tau, resid_sd)
    drift_sd = math.sqrt(max(drift_point["step_variance"], 0.))
    drift_lo, drift_hi = (math.sqrt(max(v, 0.)) for v in drift_ci["step_variance"])
    drift_early = math.sqrt(max(drift_point["step_variance_weeks_1_4"], 0.))
    drifts = {"d_drift_point": drift_sd, "d_drift_low": drift_lo, "d_drift_high": drift_hi, "d_drift_weeks_1_4": drift_early}
    probabilities = {name: [] for name in list(scenarios) + list(drifts)}
    for league, state in states.items():
        for name, (t, s) in scenarios.items():
            probabilities[name].append(simulate(state, t, s, args.iterations, args.seed + 100 + league,
                                                schedule=schedules[league] if exact else None))
        for name, d in drifts.items():
            probabilities[name].append(simulate(state, 0., args.sd, args.iterations, args.seed + 100 + league,
                                                schedule=schedules[league] if exact else None, drift_sd=d))
    comparisons = [compare(probabilities["a_independent_25"], probabilities[name], name)
                   for name in probabilities if name != "a_independent_25"]
    # Monte Carlo noise floor: two seeds of (a)
    noise = [simulate(state, 0., args.sd, args.iterations, args.seed + 900 + league, schedule=schedules[league] if exact else None)
             for league, state in states.items()]
    noise_cmp = compare(probabilities["a_independent_25"], noise, "a_vs_a_other_seed")

    # step 5: one game over .500
    one_over = {"head_to_head_5_4": {}, "median_10_8": {}}
    for name in probabilities:
        h2h, med = [], []
        for k, (league, state) in enumerate(states.items()):
            diff = state["wins"] - state["losses"]
            for i in range(len(state["teams"])):
                if not state["median"] and diff[i] == 1 and state["ties"][i] == 0:
                    h2h.append(float(probabilities[name][k][i]))
                if state["median"] and diff[i] == 2 and state["ties"][i] == 0:
                    med.append(float(probabilities[name][k][i]))
        for key, values in (("head_to_head_5_4", h2h), ("median_10_8", med)):
            values.sort()
            one_over[key][name] = {"teams": len(values), "min": values[0] if values else None,
                                   "median": statistics.median(values) if values else None,
                                   "max": values[-1] if values else None,
                                   "at_or_above_95": sum(v >= .95 for v in values)}

    validation = [validate_engine(states[league], args.validate_iterations, args.seed + 500 + league)
                  for league in (next(l for l in states if states[l]["median"]), next(l for l in states if not states[l]["median"]))]

    result = {
        "question": "are weekly projection errors independent within a team, and what does persistence do to playoff odds",
        "data": {"season": SEASON, "weeks": WEEKS, "leagues": len(leagues), "teams": team_count,
                 "team_weeks": len(rows), "median_leagues": sum(i["median"] for i in leagues.values()),
                 "head_to_head_games": rel["games"]},
        "step1_reproduction": head,
        "step2_persistence": {
            "units": "points squared for variances, points for tau; relative = league-week mean removed",
            "point": point, "team_bootstrap_95": intervals, "league_bootstrap_95": league_intervals,
            "bootstrap_reps": args.boot,
            "mean_error_drift": {"point": raw_drift, "team_bootstrap_95": mean_drift_ci},
            "global_week_shock_sd": math.sqrt(max(global_week_var, 0.)),
            "same_league_week_cross_team_correlation": cross_team_correlation(rows),
            "note": "league_week from the team bootstrap is biased upward (duplicated teams inflate league-week means); use the league bootstrap"},
        "projection_spread_slope": {"point": slopes, "team_bootstrap_95": slope_ci,
                                    "sd_across_teams_of_9_week_mean_projection": statistics.pstdev(
                                        [sum(team) / len(team) for league in cs.relative(proj) for team in league]),
                                    "sd_across_teams_of_last_3_week_mean_projection": statistics.pstdev(
                                        [v for st_ in states.values() for v in (st_["means"] - st_["means"].mean()).tolist()])},
        "projection_drift": {"point": drift_point, "team_bootstrap_95": drift_ci,
                             "drift_sd_per_week": math.sqrt(max(drift_point["step_variance"], 0.)),
                             "drift_sd_per_week_95": [math.sqrt(max(v, 0.)) for v in drift_ci["step_variance"]],
                             "drift_sd_per_week_weeks_1_4": math.sqrt(max(drift_point["step_variance_weeks_1_4"], 0.))},
        "step3_independence": {
            "points_sum_ratio": {f"window_{k}": {**cs.sum_variance_ratio(panel, k), "team_bootstrap_95": intervals[f"sum_ratio_{k}"]} for k in WINDOWS},
            "wins_overdispersion_sd25": {k: {"ratio": v, "team_bootstrap_95": win_ci[k]} for k, v in wins.items()},
            "single_game_reliability_sd25": rel,
            "best_fit_single_game_sd": {"point": game_sd, "game_bootstrap_95": cs.interval(sd_draws)},
            "wins_overdispersion_best_fit_sd": {k: {"ratio": v, "team_bootstrap_95": win_fit_ci[k]} for k, v in wins_fit.items()},
            "placebo_within_team_week_shuffle": summarize_placebo(within, placebo_keys),
            "placebo_across_teams_within_league_week": {**summarize_placebo(across, placebo_keys),
                                                         **summarize_placebo(across_wins, [f"win_ratio_{k}" for k in (5, 9)])},
            "tau_upper_bound_by_inversion": {"share_of_planted_copies_as_low_as_observed": {str(k): v for k, v in tau_curve.items()},
                                             "smallest_tau_rejected_at_1pct": tau_rejected_1pct,
                                             "reading": "a fraction under .05 means a persistent team SD that large is inconsistent with the data; even 0 sits near .05 because the observed errors lean mean-reverting"},
            "permutation_p_values": {
                "team_share_at_or_below_observed": p_low(across, "team_share_of_relative", point["team_share_of_relative"]),
                "team_share_at_or_above_observed": p_high(across, "team_share_of_relative", point["team_share_of_relative"]),
                "sum_ratio_9_at_or_below_observed": p_low(across, "sum_ratio_9", point["sum_ratio_9"]),
                "sum_ratio_5_at_or_below_observed": p_low(across, "sum_ratio_5", point["sum_ratio_5"]),
                "win_ratio_9_at_or_above_observed": p_high(across_wins, "win_ratio_9", wins["win_ratio_9"]),
                "win_ratio_5_at_or_above_observed": p_high(across_wins, "win_ratio_5", wins["win_ratio_5"])},
            "shuffles": args.shuffles},
        "step4_season_simulation": {
            "schedule": "cached remaining schedule" if exact else "NOT CACHED: a fresh random pairing each remaining week of each simulated season (illustration, not the leagues' odds)",
            "future_means": "each team's average projected best-lineup total over weeks 7-9 (future-week projections not cached)",
            "state": "records, PF and PA after week 9 from the cached matchups; median game included where the league has one",
            "tiebreak": "record, then PF, then PA, then random (the app's seeding)",
            "remaining_weeks": sorted({s["remaining"] for s in states.values()}),
            "iterations_per_league_per_scenario": args.iterations,
            "scenarios": {**{name: {"tau": t, "weekly_sd": s, "total_weekly_sd": math.hypot(t, s)} for name, (t, s) in scenarios.items()},
                          **{name: {"tau": 0., "weekly_sd": args.sd, "drift_sd_per_week": d} for name, d in drifts.items()}},
            "comparisons_vs_a": comparisons, "monte_carlo_noise_floor": noise_cmp,
            "engine_validation_vs_production_simulator": validation,
            "missing_for_exact_run": {"count": len(missing),
                                      "templates": sorted({u.replace(next((i["id"] for i in leagues.values() if i["id"] in u), "~"), "{league_id}") for u in missing})}},
        "step5_one_game_over_500": one_over,
        "limits": ["One season, weeks 1-9, 9 leagues: wide intervals.",
                   "Projection rows are the provider's stored rows, stamped after the games; they may carry post-game information.",
                   "Each week's final projection only: error growth with forecast horizon cannot be measured here.",
                   "Rosters are each week's recorded roster."],
    }
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"reproduction": head, "tau": [tau, tau_lo, tau_hi], "drift_sd": [drift_sd, drift_lo, drift_hi, drift_early], "exact_schedule": exact,
                      "missing_urls": len(missing)}, indent=1))


if __name__ == "__main__":
    main()
