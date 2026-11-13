"""Is the forecast's weekly score spread (score_sd 25) right? Player, lineup and game level.

Measures how far actual fantasy points land from the provider's weekly projection,
for players and for whole starting lineups, in every league of the research store
plus the cached study leagues; fits the spread that best explains realised
head-to-head results; then re-runs the operator's three saved forecasts with the
spreads the data support.

    python3.12 docs/plans/league-projections/score-spread-study/study.py \
        /path/outside/repo/scratch /path/to/universe.sqlite [--workers 8] [--iterations 250000]

The scratch folder holds `cache/` (raw Sleeper responses), `league_ids.txt`,
`operator_leagues.txt` and `snapshots/league1..3.json`; intermediate files that
carry ids are written to `<scratch>/study/`, never the repo. The store is opened
read-only. Network access is disabled. Output: `result.json` next to this file,
aggregates only (no league, roster, manager or player identity).
Standard library and the repo's own modules only; Python 3.12.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import pickle
import random
import socket
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def _no_network(*_args, **_kwargs):
    raise RuntimeError("network access is disabled in this study")


# Every process, before anything else is imported: no connection can be opened.
socket.socket.connect = socket.socket.connect_ex = _no_network
socket.create_connection = socket.getaddrinfo = _no_network

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import spread_stats as ss  # noqa: E402
from backend.league_projections import simulation  # noqa: E402
from backend.league_projections.core import SLOTS, decimal, median_outcomes, optimize  # noqa: E402
from backend.league_projections.provider import LINEAR_PROJECTED_EVENTS  # noqa: E402
from backend.season_forecasts import normalize_scoring_for_slots  # noqa: E402

SEASONS = {2024: 18, 2025: 18, 2026: 9}   # last completed week cached / played (2026: week 10 is in progress)
HORIZONS = (1, 2, 3, 4, 5)
GROUP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "K": "K", "DEF": "DEF",
         "DL": "DL", "DE": "DL", "DT": "DL", "NT": "DL", "LB": "LB", "ILB": "LB", "OLB": "LB",
         "DB": "DB", "CB": "DB", "S": "DB", "SS": "DB", "FS": "DB"}
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB")
SIZE_GROUPS = (("8-9", 8, 9), ("10", 10, 10), ("11-12", 11, 12), ("13+", 13, 99))


def size_group(n):
    return next(label for label, lo, hi in SIZE_GROUPS if lo <= n <= hi)


def url_path(cache, url):
    return cache / (url.replace("https://", "").replace("/", "_").replace("?", "_") + ".json")


def load_url(cache, url):
    path = url_path(cache, url)
    if not path.exists():
        raise FileNotFoundError("cache miss: " + url)
    return json.loads(path.read_text())


def _load_backtest():
    """The universal-SD backtest's `projected_points`: the product's best-available scoring path."""
    spec = importlib.util.spec_from_file_location("sd_backtest", HERE.parent / "universal-sd" / "backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.projected_points


# ------------------------------------------------------------------ stage 0: slim inputs
def prepare(scratch):
    """Slim projection payloads and the player map into pickles under <scratch>/study (ids stay there)."""
    out = scratch / "study"
    (out / "proj").mkdir(parents=True, exist_ok=True)
    meta_path = out / "meta.pkl"
    if not meta_path.exists():
        players = load_url(scratch / "cache", "https://api.sleeper.app/v1/players/nfl")
        meta = {pid: {"fantasy_positions": m.get("fantasy_positions") or [], "position": m.get("position")}
                for pid, m in players.items() if m.get("fantasy_positions")}
        meta_path.write_bytes(pickle.dumps(meta))
    for season, last in SEASONS.items():
        teams_seen = set()
        weekly = {}
        for week in range(1, last + 1):
            payload = load_url(scratch / "cache", f"https://api.sleeper.app/projections/nfl/{season}/{week}?season_type=regular")
            rows = {str(r["player_id"]): {"stats": r.get("stats") or {}, "company": r.get("company"),
                                         "category": r.get("category"), "team": r.get("team")}
                    for r in payload if isinstance(r, dict) and r.get("stats")}
            present = {k for r in rows.values() for k in r["stats"]} & LINEAR_PROJECTED_EVENTS
            playing = {r["team"] for r in rows.values() if r["stats"].get("gp") and r["team"]}
            teams_seen |= playing
            weekly[week] = (rows, present, playing)
        for week, (rows, present, playing) in weekly.items():
            path = out / "proj" / f"{season}_{week}.pkl"
            if not path.exists():
                path.write_bytes(pickle.dumps({"rows": rows, "present": present, "bye_teams": teams_seen - playing}))


# ------------------------------------------------------------------ stage 1: per-league extraction
_G = {}


def _proj(scratch, season, week):
    key = (season, week)
    if key not in _G:
        _G[key] = pickle.loads((scratch / "study" / "proj" / f"{season}_{week}.pkl").read_bytes())
    return _G[key]


def _meta(scratch):
    if "meta" not in _G:
        _G["meta"] = pickle.loads((scratch / "study" / "meta.pkl").read_bytes())
        _G["projected_points"] = _load_backtest()
    return _G["meta"]


def _universe_weeks(db, league_id, last):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("select week, roster_id, matchup_id, players_json, starters_json, players_points_json, points "
                           "from roster_weeks where league_id=? and played=1 and has_points=1 and week<=? "
                           "order by week, roster_id", (league_id, last)).fetchall()
    finally:
        con.close()
    weeks = defaultdict(list)
    for week, roster, matchup, players, starters, pp, points in rows:
        weeks[week].append({"roster": roster, "matchup": matchup, "players": json.loads(players or "[]"),
                            "starters": json.loads(starters or "[]"), "pp": json.loads(pp or "{}"), "points": points})
    return weeks


def _cache_weeks(cache, league_id, last):
    weeks = {}
    for week in range(1, last + 1):
        path = url_path(cache, f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}")
        if not path.exists():
            break
        teams = []
        for t in json.loads(path.read_text()):
            if t.get("points") is None or t.get("custom_points") is not None:
                continue
            teams.append({"roster": t["roster_id"], "matchup": t.get("matchup_id"), "players": t.get("players") or [],
                          "starters": t.get("starters") or [], "pp": t.get("players_points") or {}, "points": t["points"]})
        weeks[week] = teams
    return weeks


def process_league(task):
    scratch = Path(task["scratch"])
    meta = _meta(scratch)
    projected_points = _G["projected_points"]
    season, slots, scoring = task["season"], task["slots"], task["scoring"]
    supported = task["supported"]
    weeks = _universe_weeks(task["db"], task["league_id"], task["last"]) if task["source"] == "universe" \
        else _cache_weeks(scratch / "cache", task["league_id"], task["last"])
    memo = {}

    def proj(week, pid):
        key = (week, pid)
        if key not in memo:
            m = meta.get(pid)
            data = _proj(scratch, season, week)
            raw = data["rows"].get(pid)
            value = projected_points(raw, scoring, data["present"], m) if m and raw else None
            memo[key] = None if value is None else float(value)
        return memo[key]

    def stale(week, h, pid, strict):
        """A player's projection as known h weeks before `week`.

        lenient: the latest priced projection at or before week - h (up to 3 more weeks
        back), so a player who was out at the origin counts as healthy (his old projection).
        strict: the origin week's own projection; an earlier one only if his NFL team was
        on bye at the origin; a player out at the origin stays out.
        """
        origin = week - h
        for k in range(origin, max(0, origin - 4), -1):
            value = proj(k, pid)
            if value is not None:
                team = _proj(scratch, season, k)["rows"][pid].get("team")
                if strict and k != origin and team not in _proj(scratch, season, origin)["bye_teams"]:
                    return None, None
                return value, team
        return None, None

    player_acc = defaultdict(lambda: [0, 0., 0.])     # (kind, pos, bucket) -> n, sum, sumsq
    player_groups = defaultdict(lambda: [0, 0., 0.])  # (kind, pos, pid) -> n, sum, sumsq
    team_rows, unpriced_started, started_total = [], 0, 0
    for week in sorted(weeks):
        for team in weeks[week]:
            players = [str(p) for p in team["players"] if p]
            starters = [str(p) for p in team["starters"] if p and str(p) != "0"]
            pp = {str(k): float(v) for k, v in (team["pp"] or {}).items() if v is not None}
            priced = {pid: proj(week, pid) for pid in players}
            pool = [{"player_id": pid, "positions": meta[pid]["fantasy_positions"], "points": repr(v)}
                    for pid, v in priced.items() if v is not None]
            best_ids, lineup = set(), None
            if supported and pool:
                lineup = optimize(slots, pool, empty_policy="fill_available")
                best_ids = {row["player"]["player_id"] for row in lineup["lineup"] if row["player"]}
            for pid in starters:
                started_total += 1
                unpriced_started += priced.get(pid) is None
            for pid, value in priced.items():
                if value is None or pid not in pp:
                    continue
                pos = GROUP.get(meta[pid].get("position"), "other")
                r = pp[pid] - value
                b = ss.bucket(value)
                for kind, flag in (("started", pid in starters), ("projected_start", pid in best_ids)):
                    if flag:
                        acc = player_acc[(kind, pos, b)]
                        acc[0] += 1; acc[1] += r; acc[2] += r * r
                        grp = player_groups[(kind, pos, pid)]
                        grp[0] += 1; grp[1] += r; grp[2] += r * r
            if lineup is None:
                continue
            lineup_players = []
            for row in lineup["lineup"]:
                if row["player"]:
                    pid = row["player"]["player_id"]
                    value = priced[pid]
                    lineup_players.append((GROUP.get(meta[pid].get("position"), "other"), ss.bucket(value), value, pp.get(pid, 0.)))
            stale_totals = {"lenient": {}, "strict": {}}
            byes = _proj(scratch, season, week)["bye_teams"]
            for h in HORIZONS:
                if week - h < 1:
                    continue
                for variant in stale_totals:
                    spool = []
                    for pid in players:
                        value, nfl_team = stale(week, h, pid, variant == "strict")
                        if value is not None and nfl_team not in byes:
                            spool.append({"player_id": pid, "positions": meta[pid]["fantasy_positions"], "points": repr(value)})
                    if spool:
                        stale_totals[variant][h] = float(decimal(optimize(slots, spool, empty_policy="fill_available")["points"]))
            team_rows.append({"week": week, "roster": team["roster"], "matchup": team["matchup"],
                              "proj_best": float(decimal(lineup["points"])), "actual": float(team["points"]),
                              "proj_set": sum(priced.get(pid) or 0. for pid in starters),
                              "unpriced_set": sum(priced.get(pid) is None for pid in starters),
                              "best_actual": sum(p[3] for p in lineup_players), "lineup": lineup_players,
                              "gaps": len(lineup["gaps"]), "stale": stale_totals})
    return {"key": task["key"], "season": season, "n_starters": len(slots), "supported": supported,
            "idp": task["idp"], "median": task["median"], "source": task["source"],
            "operator": task["operator"], "player_acc": dict(player_acc),
            "player_groups": {k: v for k, v in player_groups.items()},
            "team_rows": team_rows, "unpriced_started": unpriced_started, "started_total": started_total}


def league_tasks(scratch, db):
    cache = scratch / "cache"
    operator = {line.split(",")[1].strip() for line in (scratch / "operator_leagues.txt").read_text().split() if "," in line}
    tasks, seen = [], set()

    def add(source, league_id, season, positions, scoring, playoff_start, median, idp):
        slots = [s for s in positions if s not in {"BN", "IR", "TAXI"}]
        last = (playoff_start - 1) if playoff_start else 14
        last = min(last, SEASONS[season])
        tasks.append({"source": source, "league_id": league_id, "season": season, "slots": slots,
                      "scoring": normalize_scoring_for_slots(scoring, slots), "last": last,
                      "supported": all(s in SLOTS for s in slots), "median": bool(median), "idp": bool(idp),
                      "operator": league_id in operator, "scratch": str(scratch), "db": str(db)})
        seen.add(league_id)

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for league_id, season, positions, scoring, playoff_start, median, idp, settings in con.execute(
            "select league_id, season, roster_positions_json, scoring_settings_json, playoff_week_start, median_game, idp, "
            "settings_json from leagues where coalesce(best_ball, 0) = 0 order by league_id"):
        if season in SEASONS:
            add("universe", league_id, season, json.loads(positions), json.loads(scoring), playoff_start, median, idp)
    con.close()
    for league_id in sorted(set((scratch / "league_ids.txt").read_text().split()) - seen):
        league = load_url(cache, f"https://api.sleeper.app/v1/league/{league_id}")
        if not isinstance(league, dict) or league.get("sport") != "nfl" or (league.get("settings") or {}).get("best_ball"):
            continue
        season = int(league["season"])
        if season not in SEASONS:
            continue
        positions = league.get("roster_positions") or []
        add("cache", league_id, season, positions, league["scoring_settings"],
            (league.get("settings") or {}).get("playoff_week_start"), (league.get("settings") or {}).get("league_average_match"),
            any(p in {"DL", "LB", "DB", "IDP_FLEX"} for p in positions))
    for i, task in enumerate(sorted(tasks, key=lambda t: (t["season"], t["league_id"]))):
        task["key"] = i
    return sorted(tasks, key=lambda t: t["key"])


# ------------------------------------------------------------------ stage 2: analysis
def player_tables(leagues):
    acc = defaultdict(lambda: [0, 0., 0.])
    groups = defaultdict(list)
    for lg in leagues:
        for (kind, pos, b), (n, s, s2) in lg["player_acc"].items():
            for season in (lg["season"], "all"):
                for bb in (b, "all"):
                    a = acc[(season, kind, pos, bb)]
                    a[0] += n; a[1] += s; a[2] += s2
        for (kind, pos, _pid), g in lg["player_groups"].items():
            groups[(lg["season"], kind, pos)].append(tuple(g))
            groups[("all", kind, pos)].append(tuple(g))
    by_position = {}
    for (season, kind, pos, b), (n, s, s2) in sorted(acc.items(), key=lambda kv: str(kv[0])):
        if b != "all" or n < 30:
            continue
        m = ss.moments(n, s, s2)
        comp = ss.variance_components(groups[(season, kind, pos)])
        m["bias_share_of_mse"] = m["mean"] ** 2 / m["rmse"] ** 2 if m["rmse"] else None
        m["persistent_player_bias"] = comp
        by_position.setdefault(str(season), {}).setdefault(kind, {})[pos] = m
    by_bucket = {}
    for (season, kind, pos, b), (n, s, s2) in acc.items():
        if b == "all" or n < 30:
            continue
        by_bucket.setdefault(str(season), {}).setdefault(kind, {}).setdefault(pos, {})[ss.BUCKET_LABELS[b]] = ss.moments(n, s, s2)
    return by_position, by_bucket, acc


def variance_table(acc):
    """(pos, bucket) -> (mean, variance) of projected starters' residuals, all seasons pooled; position fallback."""
    table = {}
    for pos in POSITIONS + ("other",):
        whole = acc.get(("all", "projected_start", pos, "all"))
        for b in range(len(ss.BUCKET_LABELS)):
            cell = acc.get(("all", "projected_start", pos, b))
            use = cell if cell and cell[0] >= 50 else whole
            if use and use[0] >= 2:
                m = ss.moments(*use)
                table[(pos, b)] = (m["mean"], m["sd"] ** 2)
    return table


def team_tables(leagues, vtable):
    """Team-week residuals with spread bases attached; games; per-league summaries."""
    teams = []
    for lg in leagues:
        if not lg["supported"]:
            continue
        rows = lg["team_rows"]
        for r in rows:
            fallback = (0., 50.)
            cells = [vtable.get((pos, b), fallback) for pos, b, _, _ in r["lineup"]]
            r["comp_var"] = sum(v for _, v in cells)
            r["player_vars"] = [v for _, v in cells]
            r["centered_pure"] = (r["best_actual"] - r["proj_best"]) - sum(m for m, _ in cells)
        league_comp = sum(r["comp_var"] for r in rows) / len(rows) if rows else None
        weekly = defaultdict(list)
        for r in rows:
            weekly[r["week"]].append(r["actual"] - r["proj_best"])
        for r in rows:
            r.update(league=lg["key"], season=lg["season"], n_starters=lg["n_starters"], idp=lg["idp"],
                     operator=lg["operator"], league_comp=league_comp,
                     rel_best=(r["actual"] - r["proj_best"]) - sum(weekly[r["week"]]) / len(weekly[r["week"]]))
            teams.append(r)
    return teams


def sd_summary(values):
    n = len(values)
    if n < 2:
        return {"n": n}
    return ss.moments(n, sum(values), sum(v * v for v in values))


def lineup_level(teams):
    out = {}

    def block(rows):
        if len(rows) < 2:
            return {"team_weeks": len(rows)}
        best = [r["actual"] - r["proj_best"] for r in rows]
        set_ = [r["actual"] - r["proj_set"] for r in rows]
        pure = [r["best_actual"] - r["proj_best"] for r in rows]
        centered = [r["centered_pure"] for r in rows]
        mean_indep = sum(r["comp_var"] for r in rows) / len(rows)
        team_var = sd_summary(centered)["sd"] ** 2
        rho = sum(ss.implied_correlation(team_var, r["player_vars"]) or 0. for r in rows) / len(rows)
        return {"team_weeks": len(rows), "leagues": len({r["league"] for r in rows}),
                "mean_projected_best": sum(r["proj_best"] for r in rows) / len(rows),
                "actual_minus_projected_best_lineup": sd_summary(best),
                "actual_minus_projected_starters_as_set": sd_summary(set_),
                "projected_lineup_actual_minus_projection": sd_summary(pure),
                "relative_to_league_week_mean": sd_summary([r["rel_best"] for r in rows]),
                "independent_players_sd": math.sqrt(mean_indep),
                "observed_sd_projected_lineup_bias_removed": math.sqrt(team_var),
                "implied_average_teammate_correlation": rho,
                "team_weeks_with_unpriced_starter_as_set": sum(r["unpriced_set"] > 0 for r in rows)}
    out["all"] = block(teams)
    out["by_season"] = {str(s): block([r for r in teams if r["season"] == s]) for s in sorted({r["season"] for r in teams})}
    out["by_starting_slots"] = {label: block([r for r in teams if size_group(r["n_starters"]) == label]) for label, _, _ in SIZE_GROUPS}
    out["by_exact_starting_slots"] = {str(n): block([r for r in teams if r["n_starters"] == n]) for n in sorted({r["n_starters"] for r in teams})}
    out["idp_leagues"] = block([r for r in teams if r["idp"]])
    per_league = defaultdict(list)
    for r in teams:
        per_league[r["league"]].append(r["actual"] - r["proj_best"])
    sds = sorted(sd_summary(v)["sd"] for v in per_league.values() if len(v) >= 20)
    out["per_league_sd_distribution"] = {"league_seasons": len(sds), "p10": sds[int(.1 * (len(sds) - 1))],
                                         "median": sds[len(sds) // 2], "p90": sds[int(.9 * (len(sds) - 1))],
                                         "min": sds[0], "max": sds[-1]}
    return out


def build_games(teams):
    by = defaultdict(list)
    for r in teams:
        if r["matchup"] is not None:
            by[(r["league"], r["week"], r["matchup"])].append(r)
    games = []
    for (league, week, _), pair in sorted(by.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        if len(pair) != 2 or pair[0]["actual"] == pair[1]["actual"]:
            continue
        a, b = sorted(pair, key=lambda r: r["roster"])
        games.append({"league": league, "week": week, "season": a["season"], "n_starters": a["n_starters"],
                      "operator": a["operator"], "a": a, "b": b, "y": 1 if a["actual"] > b["actual"] else 0})
    return games


BASES = {
    "flat": lambda r: 1.,
    "lineup_size": lambda r: r["n_starters"] / 10.,
    "scoring_level": lambda r: max(r["proj_best"], 1.) / 120.,
    "per_team_composition": lambda r: r["comp_var"],
    "per_league_composition": lambda r: r["league_comp"],
}
SCALE_RANGE = {"flat": (5, 80), "lineup_size": (5, 80), "scoring_level": (5, 80),
               "per_team_composition": (.2, 5), "per_league_composition": (.2, 5)}


def as_tuples(games, model):
    f = BASES[model]
    return [(g["a"]["proj_best"] - g["b"]["proj_best"], f(g["a"]), f(g["b"]), g["y"]) for g in games]


def opponents(games):
    ra = [g["a"]["actual"] - g["a"]["proj_best"] for g in games]
    rb = [g["b"]["actual"] - g["b"]["proj_best"] for g in games]
    rel_a = [g["a"]["rel_best"] for g in games]
    rel_b = [g["b"]["rel_best"] for g in games]
    diff = [x - y for x, y in zip(ra, rb)]
    gap = [g["a"]["proj_best"] - g["b"]["proj_best"] for g in games]
    margin = [g["a"]["actual"] - g["b"]["actual"] for g in games]
    mg, mm = sum(gap) / len(gap), sum(margin) / len(margin)
    slope = sum((x - mg) * (y - mm) for x, y in zip(gap, margin)) / sum((x - mg) ** 2 for x in gap)
    md, sd = sum(diff) / len(diff), sd_summary(diff)["sd"]
    kurt = sum(((v - md) / sd) ** 4 for v in diff) / len(diff) - 3
    return {"games": len(games), "correlation_raw": ss.correlation(ra, rb),
            "slope_actual_margin_on_projected_gap": slope, "excess_kurtosis_of_residual_difference": kurt,
            "correlation_relative_to_league_week": ss.correlation(rel_a, rel_b),
            "sd_of_residual_difference": sd_summary(diff)["sd"],
            "effective_single_team_sd": sd_summary(diff)["sd"] / math.sqrt(2),
            "single_team_sd_a_side": sd_summary(ra)["sd"]}


def fit_models(games, reps, seed):
    leagues = sorted({g["league"] for g in games})
    by_league = defaultdict(list)
    for g in games:
        by_league[g["league"]].append(g)
    fitted = {m: ss.fit_scale(as_tuples(games, m), *SCALE_RANGE[m]) for m in BASES}
    in_sample = {m: -ss.log_likelihood(as_tuples(games, m), fitted[m]) / len(games) for m in BASES}
    # leave-leagues-out cross-validation, 10 folds
    rng = random.Random(seed)
    order = leagues[:]
    rng.shuffle(order)
    fold = {lg: i % 10 for i, lg in enumerate(order)}
    test_ll = {m: defaultdict(float) for m in BASES}
    for k in range(10):
        train = [g for g in games if fold[g["league"]] != k]
        for m in BASES:
            scale = ss.fit_scale(as_tuples(train, m), *SCALE_RANGE[m])
            for lg in (lg for lg in leagues if fold[lg] == k):
                test_ll[m][lg] = ss.log_likelihood(as_tuples(by_league[lg], m), scale)
    n_games = {lg: len(by_league[lg]) for lg in leagues}
    cv = {m: -sum(test_ll[m].values()) / len(games) for m in BASES}
    boot = defaultdict(list)
    for _ in range(reps):
        sample = [leagues[rng.randrange(len(leagues))] for _ in leagues]
        total = sum(n_games[lg] for lg in sample)
        for m in BASES:
            if m != "flat":
                boot[m].append(sum(test_ll["flat"][lg] - test_ll[m][lg] for lg in sample) / total)
    cv_diff = {m: {"log_loss_minus_flat": cv[m] - cv["flat"], "interval_95_league_resampled": ss.interval(boot[m])}
               for m in BASES if m != "flat"}
    return fitted, in_sample, cv, cv_diff


def flat_interval(by_league, samples, low=5, high=80):
    values = []
    for sample in samples:
        tuples = [t for lg in sample for t in as_tuples(by_league[lg], "flat")]
        values.append(ss.fit_scale(tuples, low, high, tol=5e-3))
    return ss.interval(values)


def horizon(teams, window=5, reps=200):
    """How lineup error behaves when the projection is made h weeks before the game.

    Per horizon: the residual SD and the head-to-head fitted SD on the same team-weeks
    (weeks 6+, so every h exists). Per forecast origin: a team's relative errors over
    the next `window` weeks (step 0 = that week's own projection, step h = the
    projection as known at the origin), and the same weeks scored with each week's
    own projection as a control. Their covariance says whether misses persist.
    """
    out = {}
    for variant in ("lenient", "strict"):
        def forecast(r, h):
            return r["proj_best"] if h == 0 else r["stale"][variant].get(h)
        rows = [r for r in teams if all(h in r["stale"][variant] for h in HORIZONS)]
        block = {"team_weeks": len(rows)}
        weekly = defaultdict(list)
        for r in rows:
            weekly[(r["league"], r["week"])].append(r)
        by = defaultdict(list)
        for r in rows:
            if r["matchup"] is not None:
                by[(r["league"], r["week"], r["matchup"])].append(r)
        for h in (0,) + HORIZONS:
            resid = [r["actual"] - forecast(r, h) for r in rows]
            rel = []
            for group in weekly.values():
                mean = sum(r["actual"] - forecast(r, h) for r in group) / len(group)
                rel.extend(r["actual"] - forecast(r, h) - mean for r in group)
            games = []
            for pair in by.values():
                if len(pair) == 2 and pair[0]["actual"] != pair[1]["actual"]:
                    a, b = sorted(pair, key=lambda r: r["roster"])
                    games.append((forecast(a, h) - forecast(b, h), 1., 1., 1 if a["actual"] > b["actual"] else 0))
            block[str(h)] = {"residual": sd_summary(resid), "relative_sd": sd_summary(rel)["sd"],
                             "games": len(games), "fitted_game_sd": ss.fit_scale(games, 5, 120)}
        # relative error of every team-week under every horizon, then forward windows by origin
        rel_err = {}
        all_weekly = defaultdict(list)
        for r in teams:
            all_weekly[(r["league"], r["week"])].append(r)
        for group in all_weekly.values():
            for h in (0,) + HORIZONS:
                vals = [(r, forecast(r, h)) for r in group]
                if any(v is None for _, v in vals):
                    continue
                mean = sum(r["actual"] - v for r, v in vals) / len(vals)
                for r, v in vals:
                    rel_err[(r["league"], r["roster"], r["week"], h)] = r["actual"] - v - mean
        forward, control = defaultdict(list), defaultdict(list)
        for r in teams:
            f = [rel_err.get((r["league"], r["roster"], r["week"] + h, h)) for h in range(window)]
            c = [rel_err.get((r["league"], r["roster"], r["week"] + h, 0)) for h in range(window)]
            if None not in f and None not in c:
                forward[(r["league"], r["season"])].append(f)
                control[(r["league"], r["season"])].append(c)
        block["windows"] = {}
        rng = random.Random(17)
        keys = sorted(forward)
        samples = [[keys[rng.randrange(len(keys))] for _ in keys] for _ in range(reps)]
        for name, data in (("forward_from_origin", forward), ("each_week_own_projection", control)):
            moments = {k: ss.window_moments(v) for k, v in data.items()}
            stats = ss.window_stats_from_moments(*ss.add_moments(moments.values()))
            boot = [ss.window_stats_from_moments(*ss.add_moments(moments[k] for k in sample)) for sample in samples]
            stats["interval_95_league_resampled"] = {
                "mean_offdiagonal_covariance": ss.interval([b["mean_offdiagonal_covariance"] for b in boot]),
                "sum_variance_ratio": ss.interval([b["sum_variance_ratio"] for b in boot]),
                "persistent_sd": ss.interval([math.sqrt(max(0., b["mean_offdiagonal_covariance"])) for b in boot])}
            stats["by_season"] = {str(season): {key: value for key, value in ss.window_stats_from_moments(*ss.add_moments(
                m for (lg, se), m in moments.items() if se == season)).items() if key not in ("covariance",)}
                for season in sorted({se for _, se in moments})}
            block["windows"][name] = stats
        out[variant] = block
    return out


def horizon_parameters(windows, base_sd=25., covariance=None):
    """Simulation inputs from forward-window covariances, scaled so step 0 keeps the calibrated base SD.

    A team gets one persistent draw (SD tau) shared by every remaining week, plus an
    independent weekly draw (SD sigma_h) at step h.
    """
    v0 = windows["variance_by_step"][0]
    c = max(0., windows["mean_offdiagonal_covariance"] if covariance is None else covariance)
    tau = base_sd * math.sqrt(c / v0)
    sigmas = [base_sd * math.sqrt(max(0., v - c) / v0) for v in windows["variance_by_step"]]
    return {"tau": tau, "sigma_by_step": sigmas}


# ------------------------------------------------------------------ stage 3: the operator's forecasts
def _primary(positions):
    for p in positions or []:
        if p in GROUP:
            return GROUP[p]
    return "other"


def snapshot_bases(snapshot, vtable):
    """{week: {roster_id: (full lineup variance, unplayed-only variance)}} from the stored projected lineups."""
    out = {}
    for week in snapshot["weeks"]:
        per = {}
        for rid, detail in week["teams"].items():
            full = unplayed = 0.
            for row in detail["actual"]["lineup"]:
                player = row.get("player")
                if not player:
                    continue
                v = vtable.get((_primary(player.get("positions")), ss.bucket(float(decimal(player["points"])))), (0., 50.))[1]
                full += v
                if not player.get("locked_actual"):
                    unplayed += v
            per[str(rid)] = (full, unplayed)
        out[int(week["week"])] = per
    return out


def own_simulate(snapshot, sd_of, iterations, seed, tau=0.):
    """Independent re-implementation of the product's regular-season playoff draw, per-team spreads allowed.

    sd_of(week, roster_id) -> weekly SD for that team-week; tau > 0 adds one persistent
    draw per team per simulated season, shared by all its remaining weeks. Records, PF/PA tie-breaks,
    median game, observed-score handling and rounding follow `simulation.simulate`.
    """
    teams = sorted(snapshot["teams"], key=lambda t: t["roster_id"])
    ids = [t["roster_id"] for t in teams]
    n, index = len(ids), {rid: i for i, rid in enumerate(ids)}
    median = bool((snapshot.get("league_format") or {}).get("median_game"))
    weeks = sorted(snapshot["weeks"], key=lambda w: w["week"])
    plan = []
    for week in weeks:
        games = [(index[a], index[b]) for a, b in week["games"]]
        rows = []
        for t in teams:
            d = week["teams"][str(t["roster_id"])]
            mean = float(decimal(d.get("modeled_actual_projection", d["actual"]["points"])))
            fixed = bool(d.get("actual_score_observed"))
            rows.append((mean, 0. if fixed else sd_of(int(week["week"]), t["roster_id"]), fixed))
        plan.append((games, rows))
    base_rec = [[int(t[k]) for k in ("wins", "losses", "ties")] for t in teams]
    base_pf = [float(decimal(t["points_for"])) for t in teams]
    base_pa = [float(decimal(t["points_against"])) for t in teams]
    playoff = int(snapshot["playoff_spots"])
    counts = [0] * n
    rng = random.Random(seed)
    gauss, rand = rng.gauss, rng.random
    for _ in range(iterations):
        rec = [r[:] for r in base_rec]
        pf, pa = base_pf[:], base_pa[:]
        shift = [tau * gauss(0, 1) for _ in range(n)] if tau else [0.] * n
        for games, rows in plan:
            scores = [m if fixed else round(m + shift[i] + s * gauss(0, 1), 2) for i, (m, s, fixed) in enumerate(rows)]
            for i in range(n):
                pf[i] += scores[i]
            for a, b in games:
                pa[a] += scores[b]
                pa[b] += scores[a]
                o = 0 if scores[a] > scores[b] else 1 if scores[a] < scores[b] else 2
                rec[a][o] += 1
                rec[b][1 - o if o < 2 else 2] += 1
            if median:
                for i, o in enumerate(median_outcomes(scores)):
                    rec[i][o] += 1
        lottery = [rand() for _ in range(n)]
        order = sorted(range(n), key=lambda i: (2 * rec[i][0] + rec[i][2], round(pf[i], 2), round(pa[i], 2), lottery[i]), reverse=True)
        for i in order[:playoff]:
            counts[i] += 1
    return {rid: counts[i] / iterations for i, rid in enumerate(ids)}


def _sim_job(job):
    kind, path, payload, iterations, seed = job
    snapshot = json.loads(Path(path).read_text())
    if kind == "product":
        raw = dict(json.loads((ROOT / "config" / "league_projections.json").read_text())["model"],
                   score_sd=payload, iterations=iterations)
        out = simulation.simulate(snapshot, raw)
        return {t["roster_id"]: t["playoff_probability"] for t in out["teams"]}
    table, tau = payload
    return own_simulate(snapshot, lambda w, rid: table[str(w)][str(rid)], iterations, seed, tau)


def forecasts(scratch, vtable, scales, flat_value, horizon_params, workers, iterations):
    snaps = sorted((scratch / "snapshots").glob("league*.json"))
    jobs, meta = [], []
    for path in snaps:
        snap = json.loads(path.read_text())
        bases = snapshot_bases(snap, vtable)
        league_basis = sum(f for per in bases.values() for f, _ in per.values()) / sum(len(per) for per in bases.values())
        league_sd = scales["per_league_composition"] * math.sqrt(league_basis)
        flat_table = {str(w): {rid: 25. for rid in per} for w, per in bases.items()}
        team_table = {str(w): {rid: scales["per_team_composition"] * math.sqrt(u) for rid, (_, u) in per.items()} for w, per in bases.items()}
        meta.append({"path": path, "snap": snap, "league_sd": league_sd, "team_table": team_table})
        jobs += [("product", str(path), 25., iterations, 0), ("product", str(path), flat_value, iterations, 0),
                 ("product", str(path), round(league_sd * 2) / 2, iterations, 0),
                 ("own", str(path), (flat_table, 0.), iterations, 7), ("own", str(path), (team_table, 0.), iterations, 7)]
        weeks = sorted(bases)
        for variant in ("point", "upper"):
            hp = horizon_params[variant]
            table = {str(w): {rid: hp["sigma_by_step"][min(i, len(hp["sigma_by_step"]) - 1)] for rid in bases[w]} for i, w in enumerate(weeks)}
            jobs.append(("own", str(path), (table, hp["tau"]), iterations, 7))
        # Stress tests, NOT supported by the data: weekly SD 35, and a persistent team SD of 20 (twice the measured)
        jobs.append(("own", str(path), ({w: {rid: 35. for rid in per} for w, per in flat_table.items()}, 0.), iterations, 7))
        jobs.append(("own", str(path), (flat_table, 20.), iterations, 7))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_sim_job, jobs))
    out = {}
    labels = {1: "League A (9 starters)", 2: "League B (15 starters, with defensive players)", 3: "League C (10 starters)"}
    for k, m in enumerate(meta):
        r25, rflat, rleague, own25, ownteam, hpoint, hupper, s35, s20 = results[9 * k: 9 * k + 9]
        snap = m["snap"]
        n_iter = iterations
        z = [abs(r25[rid] - own25[rid]) / math.sqrt(max(1e-12, r25[rid] * (1 - r25[rid]) / n_iter + own25[rid] * (1 - own25[rid]) / n_iter))
             for rid in r25]
        diff = [abs(r25[rid] - own25[rid]) for rid in r25]
        order = sorted(r25, key=lambda rid: (-r25[rid], rid))
        record = {t["roster_id"]: "%d-%d%s" % (t["wins"], t["losses"], "-%d" % t["ties"] if t["ties"] else "") for t in snap["teams"]}
        team_sds = sorted(v for per in m["team_table"].values() for v in per.values())
        scenarios = {"shipped_25": r25, "best_flat_%.1f" % flat_value: rflat,
                     "per_league_%.1f" % (round(m["league_sd"] * 2) / 2): rleague, "per_team_composition": ownteam,
                     "horizon_persistent_point": hpoint, "horizon_persistent_upper": hupper,
                     "stress_weekly_sd_35_unsupported": s35, "stress_persistent_20_unsupported": s20}
        number = int(m["path"].stem.replace("league", ""))
        out[labels.get(number, m["path"].stem)] = {
            "starting_slots": len(snap["slots"]), "median_game": bool((snap.get("league_format") or {}).get("median_game")),
            "completed_weeks": snap["completed_weeks"], "weeks_left": len(snap["weeks"]), "playoff_spots": snap["playoff_spots"],
            "per_league_sd_exact": m["league_sd"],
            "per_team_sd_range": [team_sds[0], team_sds[len(team_sds) // 2], team_sds[-1]],
            "own_engine_check_at_25": {"max_abs_difference": max(diff), "max_abs_z": max(z),
                                       "iterations_each": n_iter},
            "teams": [{"label": "Team %d" % (i + 1), "record": record[rid],
                       **{name: res[rid] for name, res in scenarios.items()}} for i, rid in enumerate(order)],
            "counts": {name: {"at_least_95": sum(v >= .95 for v in res.values()), "at_least_99_9": sum(v >= .999 for v in res.values()),
                              "largest_change_vs_25": max(abs(res[rid] - r25[rid]) for rid in r25)} for name, res in scenarios.items()},
        }
    return out


# ------------------------------------------------------------------ main
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scratch")
    parser.add_argument("store")
    parser.add_argument("--out", default=str(HERE / "result.json"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=250000)
    parser.add_argument("--reps", type=int, default=200)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="first N leagues only (smoke test)")
    args = parser.parse_args()
    scratch, store = Path(args.scratch).resolve(), Path(args.store).resolve()
    started = time.time()
    prepare(scratch)
    rows_path = scratch / "study" / ("rows.pkl" if not args.limit else "rows_smoke.pkl")
    if args.rebuild or not rows_path.exists():
        tasks = league_tasks(scratch, store)
        if args.limit:
            tasks = tasks[:args.limit]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            leagues = list(pool.map(process_league, tasks, chunksize=1))
        rows_path.write_bytes(pickle.dumps(leagues))
        print("extracted", len(leagues), "league-seasons in %.0fs" % (time.time() - started), flush=True)
    leagues = pickle.loads(rows_path.read_bytes())

    by_position, by_bucket, acc = player_tables(leagues)
    vtable = variance_table(acc)
    teams = team_tables(leagues, vtable)
    lineup = lineup_level(teams)
    games = build_games(teams)
    seasons_games = {"all": games, **{str(s): [g for g in games if g["season"] == s] for s in sorted({g["season"] for g in games})},
                     **{"slots " + label: [g for g in games if size_group(g["n_starters"]) == label] for label, _, _ in SIZE_GROUPS},
                     "operator leagues": [g for g in games if g["operator"]]}
    fitted, in_sample, cv, cv_diff = fit_models(games, args.reps, 5)
    flat = {}
    for name, subset in seasons_games.items():
        if len(subset) < 30:
            flat[name] = {"games": len(subset)}
            continue
        sub_leagues = defaultdict(list)
        for g in subset:
            sub_leagues[g["league"]].append(g)
        keys = sorted(sub_leagues)
        rng = random.Random(9)
        sample_sets = [[keys[rng.randrange(len(keys))] for _ in keys] for _ in range(args.reps)]
        flat[name] = {"games": len(subset), "leagues": len(keys),
                      "fitted_sd": ss.fit_scale(as_tuples(subset, "flat"), 5, 80),
                      "interval_95_league_resampled": flat_interval(sub_leagues, sample_sets),
                      "log_loss_at_25": -ss.log_likelihood(as_tuples(subset, "flat"), 25.) / len(subset),
                      "opponents": opponents(subset)}
        flat[name]["log_loss_at_fitted"] = -ss.log_likelihood(as_tuples(subset, "flat"), flat[name]["fitted_sd"]) / len(subset)
    best_flat = round(fitted["flat"] * 2) / 2
    rel = {name: {"at_25": ss.reliability(as_tuples(subset, "flat"), 25.),
                  "at_fitted_%.1f" % best_flat: ss.reliability(as_tuples(subset, "flat"), best_flat)}
           for name, subset in (("all", games), ("2025", seasons_games.get("2025", [])), ("2026", seasons_games.get("2026", [])))}
    rel["all"]["per_team_composition"] = ss.reliability(as_tuples(games, "per_team_composition"), fitted["per_team_composition"])
    hz = horizon(teams, reps=args.reps)
    strict = hz["strict"]["windows"]["forward_from_origin"]
    hparams = {"point": horizon_parameters(strict),
               "upper": horizon_parameters(strict, covariance=strict["interval_95_league_resampled"]["mean_offdiagonal_covariance"][1])}
    hz["simulation_parameters"] = hparams
    print("analysis done in %.0fs; simulating" % (time.time() - started), flush=True)
    fc = forecasts(scratch, vtable, fitted, best_flat, hparams, args.workers, args.iterations)

    covered = [lg for lg in leagues if lg["started_total"]]   # league-seasons with at least one scored week
    result = {
        "question": "Is one flat weekly score SD of 25 right for every team? Player, lineup and game level.",
        "data": {"league_seasons": len(covered), "by_season": dict(Counter(str(lg["season"]) for lg in covered)),
                 "lineup_level_league_seasons": len({r["league"] for r in teams}),
                 "unsupported_lineups_player_level_only": sum(not lg["supported"] for lg in covered),
                 "team_weeks": len(teams), "games": len(games),
                 "weeks": {"2024": "1-14 (or the league's regular season)", "2025": "1-14 (or the league's regular season)",
                           "2026": "1-9 (all completed weeks; week 10 in progress)"},
                 "started_player_weeks": sum(lg["started_total"] for lg in covered),
                 "started_player_weeks_unpriced": sum(lg["unpriced_started"] for lg in covered)},
        "player_level": {"by_position": by_position, "by_projected_points_bucket": by_bucket,
                         "variance_table_used_for_lineups": {"%s %s" % (p, ss.BUCKET_LABELS[b]): {"mean": m, "sd": math.sqrt(v)}
                                                             for (p, b), (m, v) in sorted(vtable.items())}},
        "lineup_level": lineup,
        "game_level": {"flat_sd_fits": flat, "model_scales_fitted": fitted, "log_loss_in_sample": in_sample,
                       "log_loss_cross_validated": cv, "cross_validated_vs_flat": cv_diff,
                       "reliability": rel, "best_flat_rounded": best_flat},
        "horizon_proxy": hz,
        "operator_forecasts": fc,
        "seconds": time.time() - started,
    }
    Path(args.out).write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(json.dumps({k: result[k] for k in ("data",)}, indent=1))
    print(json.dumps(result["game_level"]["flat_sd_fits"]["all"], indent=1))


if __name__ == "__main__":
    main()
