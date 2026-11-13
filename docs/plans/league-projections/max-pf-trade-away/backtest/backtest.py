"""Max PF moves: leave-one-out accuracy backtest (exploration §11, operator decision 11).

For every cached league, week (1-9 of 2026) and roster, and every player on that
roster that week, compares:

  predicted drop  the best-lineup total from PROJECTED points with the player minus
                  without him, computed by the product's own `maxpf_moves.resolve`
                  (max PF lane), on a one-week snapshot rebuilt from the cached feed;
  realised drop   the same difference from ACTUAL points (`players_points`), i.e. the
                  hindsight-best lineup with and without him, by `core.optimize(hindsight=True)`.

Then sums both over weeks w..9 (each week's own roster) for every start week w,
and compares the operator's simple rule with the exact re-solve.

Offline only: socket creation is disabled before any file is read, and the
cache directory is the only input. Output (`result.json` next to this file by
default) is aggregate: no league, roster, manager or player identity.

    python docs/plans/league-projections/max-pf-trade-away/backtest/backtest.py /path/to/cache

Optional: --out PATH, --reps N (league bootstrap draws, default 1000),
--workers N, --rows PATH (per-row dump with ids, for checking; keep it OUT of the repo).
Standard library and the repo's own modules only. Python 3.12.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import socket
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import backtest_stats as bs  # noqa: E402
from backend.league_projections import maxpf_moves, season_points  # noqa: E402
from backend.league_projections.core import SLOTS, Unavailable, optimize  # noqa: E402
from backend.league_projections.provider import LINEAR_PROJECTED_EVENTS  # noqa: E402
from backend.league_projections.scoring import BEST_AVAILABLE, best_available  # noqa: E402
from backend.season_forecasts import normalize_scoring_for_slots  # noqa: E402

SEASON = 2026
WEEKS = list(range(1, 10))
# Every rostered player is in the max PF pool: past taxi/reserve status is not in
# the cache. "include" makes resolve keep cached players the product would drop.
CFG = {"empty_slots": "fill_available", "ir_maxpf": "include"}
WEEKLY_EDGES = (2, 5, 10, 20)
WINDOW_EDGES = (5, 10, 20, 40, 80)
IDP_POSITIONS = {"DL", "DE", "DT", "LB", "ILB", "OLB", "DB", "CB", "SS", "FS", "S"}


def _no_network(*_args, **_kwargs):
    raise RuntimeError("network access is disabled in this backtest")


# ---------------------------------------------------------------- pure lineup pieces
def position_group(positions):
    primary = (positions or ["?"])[0]
    return "IDP" if primary in IDP_POSITIONS else primary


def hindsight_drops(slots, players):
    """Realised (hindsight) drops. players: [{player_id, positions, points}] with
    ACTUAL points. Returns (best total, starters {pid: slot}, {pid: drop}, {pid: opens_gap})
    using the product's optimizer in hindsight mode."""
    pool = [{**p, "points": str(p["points"]), "actual_points": str(p["points"])} for p in players]
    base = optimize(slots, pool, empty_policy="fill_available", hindsight=True)
    total = Decimal(base["points"])
    starters = {str(r["player"]["player_id"]): r["slot"] for r in base["lineup"] if r["player"]}
    drops, gaps = {}, {}
    for p in pool:
        pid = str(p["player_id"])
        if pid not in starters:
            drops[pid], gaps[pid] = Decimal(0), False  # a bench player's removal leaves the optimum feasible
            continue
        without = optimize(slots, [q for q in pool if q is not p], empty_policy="fill_available", hindsight=True)
        drops[pid] = total - Decimal(without["points"])
        gaps[pid] = len(without["gaps"]) > len(base["gaps"])
    return total, starters, drops, gaps


def simple_rules(slots_by_starter, points, positions):
    """The operator's rule: a starter's projected points minus the best projected
    non-starter who could replace him; 0 for a non-starter.

    slots_by_starter {pid: slot} is the projected best lineup; points {pid: Decimal}
    the priced players; positions {pid: [..]}. Two readings (exploration §10):
    "same_position" (bench players sharing the starter's primary position) and
    "slot_eligible" (bench players who may fill the starter's slot). No
    replacement means the slot is lost: the rule is the starter's full points."""
    bench = [pid for pid in points if pid not in slots_by_starter]
    out = {}
    for pid in points:
        if pid not in slots_by_starter:
            out[pid] = (Decimal(0), Decimal(0))
            continue
        primary = (positions[pid] or ["?"])[0]
        same = [points[q] for q in bench if primary in positions[q]]
        slot = [points[q] for q in bench if SLOTS[slots_by_starter[pid]].intersection(positions[q])]
        out[pid] = (points[pid] - (max(same) if same else 0), points[pid] - (max(slot) if slot else 0))
    return out


def exhaustive_best(slots, players):
    """Independent exact check of the optimizer: dynamic programme over the
    remaining count of each slot type (no assignment algorithm). Same objective
    as `optimize(..., empty_policy="fill_available")`: fill as many slots as
    possible, then maximise points. players: [(positions, Decimal points)]."""
    types = sorted(set(slots))
    cap = tuple(slots.count(t) for t in types)
    big = Decimal(10) ** 5  # above any roster's total |points|; keeps 28-digit Decimal exact
    best = {cap: Decimal(0)}
    for positions, pts in players:
        eligible = [i for i, t in enumerate(types) if SLOTS[t].intersection(positions)]
        new = dict(best)
        for state, value in best.items():
            for i in eligible:
                if state[i]:
                    nxt = state[:i] + (state[i] - 1,) + state[i + 1:]
                    candidate = value + big + pts
                    if candidate > new.get(nxt, -big * 100):
                        new[nxt] = candidate
        best = new
    state, value = max(best.items(), key=lambda kv: kv[1])
    return value - big * (sum(cap) - sum(state))


# ---------------------------------------------------------------- feed -> product snapshot
def projected_input(raw, meta, active, present, playing):
    """One cached projection row -> the input row `provider.capture` stores for a
    pregame week under the best-available contract (provider.py weeks()).

    Bye: the player's NFL team has no projected player that week (the cache has
    no schedule). No team -> unpriced, as the provider's `no_known_team`."""
    team = (raw or {}).get("team") or meta.get("team")
    stats = (raw or {}).get("stats") or {}
    if not team:
        return {"phase": "pregame", "bye": False, "availability": None, "stats": {}, "supported_keys": [],
                "projection_status": "unpriced"}
    if team not in playing and not stats.get("gp"):
        return {"phase": "pregame", "bye": True, "availability": 0, "stats": {}, "supported_keys": []}
    try:
        normalized = best_available(raw or {}, active, present, positions=meta.get("fantasy_positions") or [],
                                    primary_position=meta.get("position"))
    except Unavailable:
        return {"phase": "pregame", "bye": False, "availability": None, "stats": {}, "supported_keys": [],
                "projection_status": "unpriced"}
    return {"phase": "pregame", "bye": False, **normalized, "inapplicable_keys": [], "availability": 1}


def league_week(league, matchups, payload, metadata, week, league_index, check_sample):
    """Rows for one league-week: per player, per team, plus solver checks."""
    slots = [s for s in league["roster_positions"] if s not in {"BN", "IR", "TAXI"}]
    active = normalize_scoring_for_slots(league["scoring_settings"], slots)
    present = {k for raw in payload for k in (raw.get("stats") or {})} & LINEAR_PROJECTED_EVENTS
    by_id = {str(r.get("player_id")): r for r in payload}
    playing = {r.get("team") for r in payload if (r.get("stats") or {}).get("gp")} - {None}
    teams, inputs, details, actual, info = [], [], {}, {}, {}
    no_positions = 0
    for team in matchups:
        if team.get("points") is None or team.get("custom_points") is not None:
            continue
        rid = int(team["roster_id"])
        ids = []
        for pid in map(str, team.get("players") or []):
            meta = metadata.get(pid) or {}
            if not meta.get("fantasy_positions"):
                no_positions += 1
                continue
            ids.append(pid)
            inputs.append({"week": week, "player_id": pid, "positions": list(meta["fantasy_positions"]),
                           "input": projected_input(by_id.get(pid), meta, active, present, playing)})
        teams.append({"roster_id": rid, "roster": {"players": ids, "taxi": [], "reserve": []}})
        details[str(rid)] = {"actual": {"lineup": []}, "maxpf": {"lineup": []}, "replacement_means": {}}
        points = team.get("players_points") or {}
        actual[rid] = {pid: Decimal(str(points.get(pid, 0))) for pid in ids}
        starters = [str(s) for s in team.get("starters") or [] if str(s) not in ("0", "None")]
        info[rid] = {"sleeper_points": Decimal(str(team["points"])),
                     "starters_sum": sum((Decimal(str(v)) for v in team.get("starters_points") or []), Decimal(0)),
                     "starters_filled": len(starters)}
    snapshot = {"slots": slots, "scoring": league["scoring_settings"], "coverage": {"scoring_contract": BEST_AVAILABLE},
                "teams": teams, "player_week_inputs": inputs, "weeks": [{"week": week, "teams": details}]}
    projected = season_points.player_points(snapshot).get(week, {})
    positions = season_points.positions(snapshot)
    rows, team_rows = [], []
    for team in teams:
        rid, ids = team["roster_id"], team["roster"]["players"]
        solved = maxpf_moves.resolve(snapshot, CFG, {}, rid)
        ctx = solved["context"]
        _lane, maximum = ctx.lineups(rid, week, details[str(rid)])
        proj_starters = {str(r["player"]["player_id"]): r["slot"] for r in maximum["lineup"] if r["player"]}
        priced = {pid: projected[pid] for pid in ids if isinstance(projected.get(pid), Decimal)}
        rules = simple_rules(proj_starters, priced, positions)
        real_total, real_starters, real_drop, real_gap = hindsight_drops(
            slots, [{"player_id": pid, "positions": positions[pid], "points": actual[rid][pid]} for pid in ids])
        depth = Counter(position_group(positions[pid]) for pid in ids)
        check = {"projected_ok": None, "realised_ok": None}
        if check_sample:
            check["projected_ok"] = exhaustive_best(slots, [(positions[p], v) for p, v in priced.items()]) == Decimal(maximum["points"])
            check["realised_ok"] = exhaustive_best(slots, [(positions[p], actual[rid][p]) for p in ids]) == real_total
        team_rows.append({"league": league_index, "roster": rid, "week": week,
                          "projected_best": float(Decimal(maximum["points"])), "realised_best": float(real_total),
                          "sleeper_points": float(info[rid]["sleeper_points"]),
                          "starters_sum": float(info[rid]["starters_sum"]),
                          "starters_filled": info[rid]["starters_filled"], "slots": len(slots), **check})
        for pid in ids:
            value = projected.get(pid)
            if pid in solved["unknown"] or pid not in solved["candidates"]:
                status, pred, gap_pred = "unknown", Decimal(0), False
            else:
                wk = solved["candidates"][pid]["weeks"][0]
                pred = wk["dM"]
                status = "bye" if value == season_points.BYE else "priced"
                gap_pred = any(r["player_id"] is None for r in wk["replaced_by"])
            rule_pos, rule_slot = rules.get(pid, (Decimal(0), Decimal(0)))
            group = position_group(positions[pid])
            rows.append({"league": league_index, "roster": rid, "week": week, "player": pid,
                         "group": group, "depth": depth[group], "status": status,
                         "projected_points": float(value) if isinstance(value, Decimal) else None,
                         "actual_points": float(actual[rid][pid]),
                         "projected_starter": pid in proj_starters, "realised_starter": pid in real_starters,
                         "pred": float(pred), "real": float(real_drop[pid]),
                         "rule_pos": float(rule_pos), "rule_slot": float(rule_slot),
                         "gap_pred": gap_pred, "gap_real": real_gap[pid]})
    return rows, team_rows, no_positions


# ---------------------------------------------------------------- cache
def cache_path(cache, url):
    return cache / (url.replace("https://", "").replace("/", "_").replace("?", "_") + ".json")


def load(cache, url):
    path = cache_path(cache, url)
    if not path.exists():
        raise FileNotFoundError(f"cache miss: {url}")
    return json.loads(path.read_text())


def league_ids(cache):
    return sorted({m.group(1) for f in cache.glob("*_matchups_*.json")
                   if (m := re.search(r"league_(\d+)_matchups_\d+\.json$", f.name))})


_METADATA = None


def _work(task):
    global _METADATA
    socket.socket = _no_network
    cache, league_id, index, week, sample = task
    cache = Path(cache)
    if _METADATA is None:
        _METADATA = load(cache, "https://api.sleeper.app/v1/players/nfl")
    league = load(cache, f"https://api.sleeper.app/v1/league/{league_id}")
    matchups = load(cache, f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}")
    payload = load(cache, f"https://api.sleeper.app/projections/nfl/{SEASON}/{week}?season_type=regular")
    return league_week(league, matchups, payload, _METADATA, week, index, sample)


# ---------------------------------------------------------------- windows
def windows(rows):
    """For each roster and start week w: per player on the roster at week w, the
    sum over weeks w..9 of his weekly drops in the weeks he is still on the
    roster (0 in weeks after he left). A week with no usable projection counts
    as predicted 0 (he is not in that week's projected pool); `unknown` marks
    such windows, which the product would leave out (strict sensitivity)."""
    by = defaultdict(dict)
    for r in rows:
        by[(r["league"], r["roster"], r["week"])][r["player"]] = r
    out = []
    for (league, roster, start), players in by.items():
        for pid, first in players.items():
            acc = {"pred": 0., "real": 0., "rule_pos": 0., "rule_slot": 0., "projected": 0., "weeks_on": 0}
            unknown = False
            for week in range(start, WEEKS[-1] + 1):
                r = by.get((league, roster, week), {}).get(pid)
                if r is None:
                    continue
                acc["weeks_on"] += 1
                unknown |= r["status"] == "unknown"
                for key in ("pred", "real", "rule_pos", "rule_slot"):
                    acc[key] += r[key]
                acc["projected"] += r["projected_points"] or 0.
            out.append({"league": league, "roster": roster, "start": start, "length": WEEKS[-1] - start + 1,
                        "player": pid, "group": first["group"], "unknown": unknown, **acc})
    return out


# ---------------------------------------------------------------- analysis
def by_league(rows, n_leagues):
    groups = [[] for _ in range(n_leagues)]
    for r in rows:
        groups[r["league"]].append(r)
    return groups


def calib(rows, n, reps, pred="pred", real="real", seed=11):
    stat = lambda rs: bs.summary((r[pred], r[real]) for r in rs)  # noqa: E731
    return bs.bootstrap(by_league(rows, n), stat, reps, seed)


def table_with_ci(rows, n, reps, edges, seed=13):
    """Calibration table by predicted bucket; mean realised per bucket with a league-bootstrap interval."""
    base = bs.calibration_table([(r["pred"], r["real"]) for r in rows], edges)
    groups = by_league(rows, n)
    rng = random.Random(seed)
    draws = [[] for _ in base]
    for _ in range(reps):
        sample = [r for _ in groups for r in groups[rng.randrange(len(groups))]]
        for i, cell in enumerate(bs.calibration_table([(r["pred"], r["real"]) for r in sample], edges)):
            draws[i].append(cell["mean_realised"])
    for cell, d in zip(base, draws):
        cell["mean_realised_ci95"] = bs.interval(d)
    return base


def risk2(rows, n, reps):
    zero = [r for r in rows if r["pred"] == 0]
    starters = [r for r in rows if r["projected_starter"]]

    def zero_stat(rs):
        positive = [r["real"] for r in rs if r["real"] > 0]
        return {"n": len(rs), "share_realised_above_0": bs.mean(r["real"] > 0 for r in rs),
                "mean_realised": bs.mean(r["real"] for r in rs),
                "mean_realised_when_above_0": bs.mean(positive)}

    def starter_stat(rs):
        p, q = sum(r["pred"] for r in rs), sum(r["real"] for r in rs)
        return {"n": len(rs), "realised_over_predicted": q / p if p else None,
                "mean_gap_realised_minus_predicted": bs.mean(r["real"] - r["pred"] for r in rs)}

    depth = []
    for d in sorted({min(r["depth"], 6) for r in rows}):
        part = [r for r in rows if min(r["depth"], 6) == d]
        depth.append({"depth_at_position": f"{d}+" if d == 6 else str(d), "n": len(part),
                      "predicted_zero_share_realised_above_0": bs.mean(r["real"] > 0 for r in part if r["pred"] == 0),
                      "predicted_zero_mean_realised": bs.mean(r["real"] for r in part if r["pred"] == 0),
                      "starters_realised_over_predicted": (sum(r["real"] for r in part if r["projected_starter"]) /
                                                           (sum(r["pred"] for r in part if r["projected_starter"]) or float("nan"))),
                      "mean_gap_realised_minus_predicted": bs.mean(r["real"] - r["pred"] for r in part)})
    depth_corr = bs.bootstrap(by_league(rows, n), lambda rs: {
        "spearman_depth_vs_gap": bs.spearman([r["depth"] for r in rs], [r["real"] - r["pred"] for r in rs]),
        "spearman_depth_vs_gap_predicted_zero": bs.spearman([r["depth"] for r in rs if r["pred"] == 0],
                                                            [r["real"] for r in rs if r["pred"] == 0])}, reps, 17)
    q = sorted(r["real"] for r in zero if r["real"] > 0)
    return {"predicted_zero": bs.bootstrap(by_league(zero, n), zero_stat, reps, 19),
            "predicted_zero_realised_quantiles_when_above_0": {
                "p50": q[len(q) // 2] if q else None, "p90": q[int(.9 * (len(q) - 1))] if q else None},
            "predicted_starters": bs.bootstrap(by_league(starters, n), starter_stat, reps, 23),
            "by_depth": depth, "depth_correlation": depth_corr}


def list_quality(wins, n, reps, k=5):
    """Per roster-window list agreement (priced players only)."""
    lists = defaultdict(dict)
    for w in wins:
        lists[(w["league"], w["roster"], w["start"])][w["player"]] = w
    items = []
    for (league, _roster, start), players in lists.items():
        if len(players) < k:
            continue
        pred = {p: w["pred"] for p, w in players.items()}
        real = {p: w["real"] for p, w in players.items()}
        naive = {p: w["projected"] for p, w in players.items()}
        a, b = bs.list_agreement(pred, real, k), bs.list_agreement(naive, real, k)
        items.append({"league": league, "start": start, "overlap": a["overlap"], "spearman": a["spearman"],
                      "first": a["first_in_real_top3"], "naive_overlap": b["overlap"], "naive_spearman": b["spearman"],
                      "naive_first": b["first_in_real_top3"], "pred_listed": sum(v >= 5 for v in pred.values())})

    def stat(xs):
        return {"lists": len(xs), "mean_top5_overlap": bs.mean(x["overlap"] for x in xs),
                "mean_spearman": bs.mean(x["spearman"] for x in xs if x["spearman"] is not None),
                "share_predicted_first_in_realised_top3": bs.mean(x["first"] for x in xs),
                "reference_by_projected_points_mean_top5_overlap": bs.mean(x["naive_overlap"] for x in xs),
                "reference_by_projected_points_mean_spearman": bs.mean(x["naive_spearman"] for x in xs if x["naive_spearman"] is not None),
                "reference_by_projected_points_share_first_in_realised_top3": bs.mean(x["naive_first"] for x in xs),
                "paired_overlap_exact_minus_reference": bs.mean(x["overlap"] - x["naive_overlap"] for x in xs),
                "paired_first_in_top3_exact_minus_reference": bs.mean(x["first"] - x["naive_first"] for x in xs)}
    return {"all_windows": bs.bootstrap(by_league(items, n), stat, reps, 29),
            "windows_5_weeks_or_more": bs.bootstrap(by_league([x for x in items if x["start"] <= 5], n), stat, reps, 31),
            "single_week": bs.bootstrap(by_league([x for x in items if x["start"] == 9], n), stat, reps, 37)}


def simple_rule(rows, wins, n, reps):
    starters = [r for r in rows if r["projected_starter"]]

    def diff_stat(key):
        def stat(rs):
            d = [r[key] - r["pred"] for r in rs]
            return {"n": len(d), "median_abs_diff_from_exact": sorted(map(abs, d))[len(d) // 2] if d else None,
                    "share_abs_diff_above_2": bs.mean(abs(x) > 2 for x in d),
                    "share_abs_diff_above_5": bs.mean(abs(x) > 5 for x in d),
                    "share_rule_above_exact_by_2": bs.mean(x > 2 for x in d),
                    "share_rule_below_exact_by_2": bs.mean(x < -2 for x in d),
                    "max_abs_diff": max(map(abs, d)) if d else None}
        return stat

    def err_stat(rs):
        return {"mae_exact_vs_realised": bs.mean(abs(r["pred"] - r["real"]) for r in rs),
                "mae_same_position_rule_vs_realised": bs.mean(abs(r["rule_pos"] - r["real"]) for r in rs),
                "mae_slot_eligible_rule_vs_realised": bs.mean(abs(r["rule_slot"] - r["real"]) for r in rs),
                "bias_exact": bs.mean(r["pred"] - r["real"] for r in rs),
                "bias_same_position_rule": bs.mean(r["rule_pos"] - r["real"] for r in rs),
                "bias_slot_eligible_rule": bs.mean(r["rule_slot"] - r["real"] for r in rs),
                "paired_mae_exact_minus_same_position_rule": bs.mean(abs(r["pred"] - r["real"]) - abs(r["rule_pos"] - r["real"]) for r in rs),
                "paired_mae_exact_minus_slot_eligible_rule": bs.mean(abs(r["pred"] - r["real"]) - abs(r["rule_slot"] - r["real"]) for r in rs)}
    long = [w for w in wins if w["length"] >= 5]
    long_starters = [w for w in long if w["pred"] > 0 or w["rule_slot"] > 0]
    return {"weekly_projected_starters_same_position_vs_exact": bs.bootstrap(by_league(starters, n), diff_stat("rule_pos"), reps, 41),
            "weekly_projected_starters_slot_eligible_vs_exact": bs.bootstrap(by_league(starters, n), diff_stat("rule_slot"), reps, 43),
            "weekly_closeness_to_realised_projected_starters": bs.bootstrap(by_league(starters, n), err_stat, reps, 47),
            "window_5plus_weeks_same_position_vs_exact": bs.bootstrap(by_league(long_starters, n), diff_stat("rule_pos"), reps, 53),
            "window_5plus_weeks_slot_eligible_vs_exact": bs.bootstrap(by_league(long_starters, n), diff_stat("rule_slot"), reps, 59),
            "window_5plus_weeks_closeness_to_realised": bs.bootstrap(by_league(long_starters, n), err_stat, reps, 61)}


def thresholds(wins, n, reps):
    priced = wins
    out = {}
    for label, part in (("all_windows", priced), ("windows_5_weeks_or_more", [w for w in priced if w["length"] >= 5])):
        cells = {}
        for t in (1, 5, 10, 15, 20, 30):
            listed = [w for w in part if w["pred"] >= t]
            cells[str(t)] = bs.bootstrap(by_league(listed, n), lambda rs, t=t: {
                "n": len(rs), "share_realised_zero_or_less": bs.mean(r["real"] <= 0 for r in rs),
                "share_realised_negative": bs.mean(r["real"] < 0 for r in rs),
                "share_realised_below_threshold": bs.mean(r["real"] < t for r in rs),
                "share_realised_below_half_predicted": bs.mean(r["real"] < r["pred"] / 2 for r in rs)}, reps, 67 + t)
        # Below the threshold: how many real drops of 5+ the rule hides.
        hidden = [w for w in part if 0 < w["pred"] < 5]
        cells["predicted_between_0_and_5"] = {"n": len(hidden), "share_realised_5_or_more": bs.mean(w["real"] >= 5 for w in hidden)}
        zero = [w for w in part if w["pred"] == 0]
        cells["predicted_0"] = {"n": len(zero), "share_realised_5_or_more": bs.mean(w["real"] >= 5 for w in zero)}
        # The product's candidate cut: the 8 largest predicted drops per list, then >= 5.
        lists = defaultdict(list)
        for w in part:
            lists[(w["league"], w["roster"], w["start"])].append(w)
        top8 = [w for ws in lists.values() for w in sorted(ws, key=lambda w: (-w["pred"], w["player"]))[:8] if w["pred"] >= 5]
        cells["top8_and_at_least_5"] = bs.bootstrap(by_league(top8, n), lambda rs: {
            "n": len(rs), "share_realised_zero_or_less": bs.mean(r["real"] <= 0 for r in rs),
            "share_realised_negative": bs.mean(r["real"] < 0 for r in rs),
            "share_realised_below_5": bs.mean(r["real"] < 5 for r in rs),
            "mean_predicted": bs.mean(r["pred"] for r in rs), "mean_realised": bs.mean(r["real"] for r in rs)}, reps, 97)
        out[label] = cells
    noise = {}
    for length in sorted({w["length"] for w in priced}):
        part = [w["real"] - w["pred"] for w in priced if w["length"] == length and w["pred"] > 0]
        noise[str(length)] = {"n": len(part), "sd_realised_minus_predicted_when_predicted_above_0":
                              (sum((x - bs.mean(part)) ** 2 for x in part) / (len(part) - 1)) ** .5 if len(part) > 1 else None}
    out["error_sd_by_window_length"] = noise
    return out


def corrections(wins, n):
    """Would a correction make the shown number closer to the realised one?
    Fitted on eight leagues, scored on the ninth (leave one league out), on
    windows of 5+ weeks. Candidates: realised = k * predicted (through the
    origin) and realised = b * predicted + c * weeks on the roster."""
    long = [w for w in wins if w["length"] >= 5]
    out = {"raw": [], "multiplicative": [], "additive_per_week": []}
    fitted = {"multiplicative_k": [], "additive_b": [], "additive_c_per_week": []}
    for held in range(n):
        train = [w for w in long if w["league"] != held]
        test = [w for w in long if w["league"] == held]
        if not test:
            continue
        k = sum(w["pred"] * w["real"] for w in train) / sum(w["pred"] ** 2 for w in train)
        # Two-variable least squares, no intercept: x1 = pred, x2 = weeks on roster.
        s11 = sum(w["pred"] ** 2 for w in train)
        s22 = sum(w["weeks_on"] ** 2 for w in train)
        s12 = sum(w["pred"] * w["weeks_on"] for w in train)
        t1 = sum(w["pred"] * w["real"] for w in train)
        t2 = sum(w["weeks_on"] * w["real"] for w in train)
        det = s11 * s22 - s12 * s12
        b, c = (t1 * s22 - t2 * s12) / det, (t2 * s11 - t1 * s12) / det
        fitted["multiplicative_k"].append(k)
        fitted["additive_b"].append(b)
        fitted["additive_c_per_week"].append(c)
        for w in test:
            out["raw"].append((w["pred"], w["real"]))
            out["multiplicative"].append((k * w["pred"], w["real"]))
            out["additive_per_week"].append((b * w["pred"] + c * w["weeks_on"], w["real"]))
    result = {name: {"mae": bs.mean(abs(p - r) for p, r in pairs), "bias": bs.mean(p - r for p, r in pairs),
                     "spearman": bs.spearman([p for p, _ in pairs], [r for _, r in pairs])}
              for name, pairs in out.items()}
    result["fitted_ranges"] = {key: [min(v), max(v)] for key, v in fitted.items()}
    # Among players the product would list (predicted >= 5): bias with and without.
    listed = [i for i, (p, _r) in enumerate(out["raw"]) if p >= 5]
    result["listed_only"] = {name: {"mae": bs.mean(abs(pairs[i][0] - pairs[i][1]) for i in listed),
                                    "bias": bs.mean(pairs[i][0] - pairs[i][1] for i in listed)}
                             for name, pairs in out.items()}
    return result


def analyse(rows, team_rows, wins, n, reps, extra):
    priced = [r for r in rows if r["status"] == "priced"]
    strict = [w for w in wins if not w["unknown"]]
    splits = {"all_priced": priced,
              "projected_starters": [r for r in priced if r["projected_starter"]],
              "projected_bench": [r for r in priced if not r["projected_starter"]]}
    for g in sorted({r["group"] for r in priced}):
        splits[f"position_{g}"] = [r for r in priced if r["group"] == g]
    for w in WEEKS:
        splits[f"week_{w}"] = [r for r in priced if r["week"] == w]
    weekly = {k: calib(v, n, reps) for k, v in splits.items()}
    window_parts = {"all": wins}
    for lo, hi in ((1, 2), (3, 4), (5, 6), (7, 9)):
        window_parts[f"length_{lo}_{hi}"] = [w for w in window_parts["all"] if lo <= w["length"] <= hi]
    windows_calib = {k: calib(v, n, reps) for k, v in window_parts.items()}
    status = Counter(r["status"] for r in rows)
    unknown = [r for r in rows if r["status"] == "unknown"]
    tw = team_rows
    validation = {
        "team_weeks": len(tw),
        "starters_sum_equals_sleeper_points": sum(abs(t["starters_sum"] - t["sleeper_points"]) < .006 for t in tw),
        "realised_best_below_sleeper_points": sum(t["realised_best"] < t["sleeper_points"] - .006 for t in tw),
        "realised_best_equals_sleeper_points": sum(abs(t["realised_best"] - t["sleeper_points"]) < .006 for t in tw),
        "mean_realised_best_minus_sleeper_points": bs.mean(t["realised_best"] - t["sleeper_points"] for t in tw),
        "team_weeks_with_an_empty_started_slot": sum(t["starters_filled"] < t["slots"] for t in tw),
        "exhaustive_check_team_weeks": sum(t["projected_ok"] is not None for t in tw),
        "exhaustive_check_projected_mismatches": sum(t["projected_ok"] is False for t in tw),
        "exhaustive_check_realised_mismatches": sum(t["realised_ok"] is False for t in tw),
        "removal_check": extra.pop("removal_check"),
    }
    team_gap = bs.bootstrap(by_league(tw, n), lambda ts: {
        "mean_projected_best": bs.mean(t["projected_best"] for t in ts),
        "mean_realised_best": bs.mean(t["realised_best"] for t in ts),
        "mean_realised_best_minus_projected_best": bs.mean(t["realised_best"] - t["projected_best"] for t in ts),
        "mean_realised_best_minus_sleeper_points": bs.mean(t["realised_best"] - t["sleeper_points"] for t in ts)}, reps, 71)
    return {
        "sample": {"leagues": n, "weeks": WEEKS, "team_weeks": len(tw), "player_weeks": len(rows),
                   "player_weeks_by_status": dict(status),
                   "player_weeks_by_position": dict(Counter(r["group"] for r in priced)),
                   "priced_projected_starters": len(splits["projected_starters"]),
                   "priced_projected_bench": len(splits["projected_bench"]),
                   "roster_windows": len({(w["league"], w["roster"], w["start"]) for w in wins}),
                   "player_windows": len(wins), "player_windows_unknown": sum(w["unknown"] for w in wins),
                   **extra},
        "solver_validation": validation,
        "team_level_max_pf": team_gap,
        "weekly_calibration": weekly,
        "weekly_calibration_table": table_with_ci(priced, n, reps, WEEKLY_EDGES),
        "weekly_calibration_table_projected_bench": table_with_ci(splits["projected_bench"], n, reps, WEEKLY_EDGES),
        "unknown_player_weeks": {"n": len(unknown), "share_realised_above_0": bs.mean(r["real"] > 0 for r in unknown),
                                 "share_actual_points_0": bs.mean(r["actual_points"] == 0 for r in unknown),
                                 "mean_realised": bs.mean(r["real"] for r in unknown)},
        "gap_opening_removals": {"predicted": sum(r["gap_pred"] for r in priced), "realised": sum(r["gap_real"] for r in rows)},
        "zero_zero_priced_rows": {"share_projected_0_and_actual_0": bs.mean((r["projected_points"] or 0) == 0 and r["actual_points"] == 0 for r in priced)},
        "risk2": risk2(priced, n, reps),
        "window_calibration": windows_calib,
        "window_calibration_table_5plus_weeks": table_with_ci([w for w in window_parts["all"] if w["length"] >= 5], n, reps, WINDOW_EDGES),
        "window_calibration_table_all": table_with_ci(window_parts["all"], n, reps, WINDOW_EDGES),
        "list_quality": list_quality(wins, n, reps),
        "list_quality_strict_unknown_excluded": list_quality(strict, n, reps),
        "window_calibration_strict_unknown_excluded": {
            "all": calib(strict, n, reps), "length_5_plus": calib([w for w in strict if w["length"] >= 5], n, reps)},
        "corrections_leave_one_league_out": corrections(wins, n),
        "simple_rule": simple_rule(priced, wins, n, reps),
        "thresholds": thresholds(wins, n, reps),
    }


def removal_check(cache, ids, rng, count=150):
    """Exhaustive DP vs the realised removals on a random sample of team-weeks."""
    metadata = load(cache, "https://api.sleeper.app/v1/players/nfl")
    checked = mismatched = 0
    for _ in range(count):
        index = rng.randrange(len(ids))
        week = rng.choice(WEEKS)
        league = load(cache, f"https://api.sleeper.app/v1/league/{ids[index]}")
        slots = [s for s in league["roster_positions"] if s not in {"BN", "IR", "TAXI"}]
        team = rng.choice(load(cache, f"https://api.sleeper.app/v1/league/{ids[index]}/matchups/{week}"))
        pts = team.get("players_points") or {}
        players = [{"player_id": str(p), "positions": metadata[str(p)]["fantasy_positions"], "points": Decimal(str(pts.get(str(p), 0)))}
                   for p in team.get("players") or [] if (metadata.get(str(p)) or {}).get("fantasy_positions")]
        total, _starters, drops, _gaps = hindsight_drops(slots, players)
        for p in players:
            rest = [(q["positions"], q["points"]) for q in players if q is not p]
            checked += 1
            mismatched += exhaustive_best(slots, rest) != total - drops[p["player_id"]]
    return {"team_weeks": count, "removals_checked": checked, "mismatches": mismatched}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cache")
    parser.add_argument("--out", default=str(HERE / "result.json"))
    parser.add_argument("--reps", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--rows", help="optional per-row dump WITH ids; must be outside the repo")
    args = parser.parse_args()
    socket.socket = _no_network
    cache = Path(args.cache)
    ids = league_ids(cache)
    rng = random.Random(5)
    tasks = [(str(cache), lid, i, w, rng.random() < .5) for i, lid in enumerate(ids) for w in WEEKS]
    if args.workers > 1:
        from multiprocessing import get_context
        with get_context("spawn").Pool(args.workers) as pool:
            parts = pool.map(_work, tasks)
    else:
        parts = [_work(t) for t in tasks]
    rows = [r for p in parts for r in p[0]]
    team_rows = [t for p in parts for t in p[1]]
    extra = {"player_weeks_without_positions_dropped": sum(p[2] for p in parts),
             "removal_check": removal_check(cache, ids, random.Random(3))}
    if args.rows:
        if Path(args.rows).resolve().is_relative_to(ROOT):
            raise SystemExit("--rows must be outside the repository")
        Path(args.rows).write_text(json.dumps({"rows": rows, "teams": team_rows}))
    wins = windows(rows)
    result = {"question": "Is the predicted max PF change (projected best lineup with and without a player) close to the realised change (hindsight best lineup from actual points)?",
              "season": SEASON, "bootstrap": f"{args.reps} draws of whole leagues with replacement; 95% percentile intervals",
              "units": "fantasy points in each league's own scoring; drops are positive (a drop of 10 = max PF 10 lower)",
              **analyse(rows, team_rows, wins, len(ids), args.reps, extra)}
    Path(args.out).write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(json.dumps(result["sample"], indent=1))


if __name__ == "__main__":
    main()
