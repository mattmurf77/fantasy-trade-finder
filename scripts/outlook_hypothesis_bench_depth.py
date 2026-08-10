"""Hypothesis 1c — bench depth vs season-long fragility (#169 outlook engine).

OPERATOR HYPOTHESIS: "Strong replacements on the bench per position suggest
less injury fragility and stronger season-long results." Teams whose bench
holds high-value players AT THE POSITIONS THEY START (positional depth, not
raw bench total) should outperform their starting-lineup-value-implied
expectation over a full season, because injuries/byes cost them less.

This script is READ-ONLY empirical validation. It imports (never
reimplements) the app's own logic:
  - backend.outlook.strength.starting_lineup_value / _FLEX_ELIGIBLE
    for the greedy best-lineup assignment and position-eligibility rules.
  - backend.outlook.pipeline.run_outlook for the preseason (week-0)
    implied wins/points/playoff/title expectation, run through the SAME
    RosterValueStrength provider the shipped preseason default uses.
  - backend.data_loader.load_consensus_maps / backend.trade_service.elo_to_value
    for the dynasty value board (DynastyProcess consensus -> Elo -> value),
    the same affine pipeline production uses.
  - scripts/outlook_calibration_backtest's as_of()/truth()/load_fixture()/
    offline_fetch()/build_full_state() — the already-validated as-of rewind
    and ground-truth extraction, reused rather than re-derived.

DATA CAVEAT (load-bearing, see the report's Method section):
Sleeper exposes no historical rosters, so "bench depth" here is measured on
each fixture's captured roster snapshot (the roster Sleeper still reports for
that closed league instance) with a CURRENT (2026-08-09) DynastyProcess value
board applied retroactively. This is the same limitation the #169 calibration
report already flagged for RosterValueStrength ("not backtestable... no dated
value snapshots") and this script inherits it rather than working around it.
`total_moves` (Sleeper roster setting) is used to build a low-transaction
sub-sample as a partial robustness check.

Usage (fully offline; needs the fixtures committed under
backend/tests/fixtures/outlook-hypotheses/ and outlook-calibration/):

    python3 scripts/outlook_hypothesis_bench_depth.py
"""

from __future__ import annotations

import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from backend import data_loader  # noqa: E402
from backend.outlook.pipeline import run_outlook  # noqa: E402
from backend.outlook.strength import _FLEX_ELIGIBLE, starting_lineup_value  # noqa: E402
from backend.trade_service import elo_to_value  # noqa: E402

from scripts.outlook_calibration_backtest import (  # noqa: E402
    as_of, build_full_state, load_fixture, median_mode, truth,
)

FIXTURES_CAL = os.path.join(REPO, "backend", "tests", "fixtures", "outlook-calibration")
FIXTURES_HYP = os.path.join(REPO, "backend", "tests", "fixtures", "outlook-hypotheses")
PLAYERS_SLIM = os.path.join(FIXTURES_HYP, "players-slim.json")
DP_CSV = os.path.join(FIXTURES_HYP, "dp-values-players-2026-08-09.csv")

SEASONS = [
    ("lakeview-2025", "sf_tep"), ("lakeview-2024", "sf_tep"),
    ("ffv3-2025", "1qb_ppr"), ("ffv3-2024", "1qb_ppr"),
    ("ffv3-2023", "1qb_ppr"), ("ffv3-2022", "1qb_ppr"),
]
SKILL_POS = ("QB", "RB", "WR", "TE")


# ---------------------------------------------------------------------------
# Value board — the app's own DP -> Elo -> value pipeline, offline
# ---------------------------------------------------------------------------

def build_value_boards() -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """Returns (value_by_pid[fmt], pos_by_pid) for the 870 rostered player ids.

    value_by_pid[fmt][pid] uses backend.data_loader.load_consensus_maps (the
    exact function build_universal_pool calls) fed the committed DP CSV
    snapshot via the FTF_DP_VALUES_FILE hermetic seam, then
    backend.trade_service.elo_to_value (the exact function RosterValueStrength
    consumers use) — same two-step affine pipeline as production, offline.
    Players absent from the DP snapshot (retired/off current boards) are left
    out of the dict; starting_lineup_value()'s own `.get(pid, 0.0)` fallback
    handles them identically to how the shipped pool would price an unranked
    player."""
    slim = json.load(open(PLAYERS_SLIM))["players"]
    pos_by_pid = {pid: (rec.get("position") or "?") for pid, rec in slim.items()}

    prev = os.environ.get("FTF_DP_VALUES_FILE")
    os.environ["FTF_DP_VALUES_FILE"] = DP_CSV
    try:
        value_by_fmt: dict[str, dict[str, float]] = {}
        for fmt in ("1qb_ppr", "sf_tep"):
            elo_map, _value_map, _pos_map = data_loader.load_consensus_maps(scoring=fmt)
            name_value = {name: elo_to_value(elo) for name, elo in elo_map.items()}
            by_pid = {}
            for pid, rec in slim.items():
                key = data_loader.normalise_name(rec.get("full_name") or "")
                if key in name_value:
                    by_pid[pid] = name_value[key]
            value_by_fmt[fmt] = by_pid
    finally:
        if prev is None:
            os.environ.pop("FTF_DP_VALUES_FILE", None)
        else:
            os.environ["FTF_DP_VALUES_FILE"] = prev
    return value_by_fmt, pos_by_pid


# ---------------------------------------------------------------------------
# Greedy lineup decomposition — mirrors strength.starting_lineup_value()
# EXACTLY (same dedicated-then-flex order, same tie-break rule), but also
# returns WHICH player filled each slot and what is left in each position's
# pool, so per-position "next man up" and drop-off can be read off.
# ---------------------------------------------------------------------------

def slot_assignment(player_ids, player_value, player_pos, roster_slots):
    by_pos: dict[str, list[tuple[float, str]]] = {}
    for pid in player_ids:
        pid = str(pid)
        pos = player_pos.get(pid, "?")
        by_pos.setdefault(pos, []).append((player_value.get(pid, 0.0), pid))
    for vals in by_pos.values():
        vals.sort(key=lambda x: x[0], reverse=True)

    dedicated = [s for s in roster_slots if s not in _FLEX_ELIGIBLE]
    flex = [s for s in roster_slots if s in _FLEX_ELIGIBLE]
    assigned = []  # [{slot, position, pid, value}]

    for slot in dedicated:
        pool = by_pos.get(slot)
        if pool:
            val, pid = pool.pop(0)
            assigned.append({"slot": slot, "position": slot, "pid": pid, "value": val})
    for slot in flex:
        elig = _FLEX_ELIGIBLE[slot]
        best_pos, best_val = None, None
        for pos in elig:
            pool = by_pos.get(pos)
            if pool and (best_val is None or pool[0][0] > best_val):
                best_pos, best_val = pos, pool[0][0]
        if best_pos is not None:
            val, pid = by_pos[best_pos].pop(0)
            assigned.append({"slot": slot, "position": best_pos, "pid": pid, "value": val})

    remaining_by_pos = {pos: [v for v, _pid in vals] for pos, vals in by_pos.items()}
    return assigned, remaining_by_pos


def depth_metrics(player_ids, player_value, player_pos, roster_slots):
    assigned, remaining = slot_assignment(player_ids, player_value, player_pos, roster_slots)
    starter_total = sum(a["value"] for a in assigned)

    # sanity: must match the shipped aggregate function exactly
    ship_total = starting_lineup_value(player_ids, player_value, player_pos, roster_slots)
    assert abs(starter_total - ship_total) < 1e-6, (
        f"decomposition diverged from starting_lineup_value(): "
        f"{starter_total} != {ship_total}")

    roster_total = sum(player_value.get(str(pid), 0.0) for pid in player_ids)
    bench_raw_sum = roster_total - starter_total

    starters_by_pos = defaultdict(list)
    for a in assigned:
        starters_by_pos[a["position"]].append(a["value"])

    next_man_up = {}
    dropoff = {}
    for pos in SKILL_POS:
        starters = starters_by_pos.get(pos, [])
        weakest = min(starters) if starters else 0.0
        pool = remaining.get(pos, [])
        nxt = pool[0] if pool else 0.0
        next_man_up[pos] = nxt
        dropoff[pos] = (nxt / weakest) if weakest > 0 else None

    next_man_up_total = sum(next_man_up[p] for p in SKILL_POS)
    ratios = [v for v in dropoff.values() if v is not None]
    dropoff_ratio_avg = statistics.fmean(ratios) if ratios else None

    return {
        "starter_total": starter_total,
        "bench_raw_sum": bench_raw_sum,
        "next_man_up_by_pos": next_man_up,
        "next_man_up_total": next_man_up_total,
        "dropoff_by_pos": dropoff,
        "dropoff_ratio_avg": dropoff_ratio_avg,
        "dropoff_positions_n": len(ratios),
    }


# ---------------------------------------------------------------------------
# Absence proxy — a rostered starter scoring 0 while started (per brief)
# ---------------------------------------------------------------------------

def absence_events_by_roster(fx: dict, regular_weeks: int) -> dict[int, int]:
    """Per-roster count of (week, starter-slot) instances where the started
    player scored exactly 0.0, across weeks 1..regular_weeks. Placeholder
    empty-slot id "0" is excluded (Sleeper fills an unfilled slot with the
    string "0")."""
    counts: dict[int, int] = defaultdict(int)
    for wk_str, rows in (fx.get("matchups") or {}).items():
        wk = int(wk_str)
        if wk < 1 or wk > regular_weeks:
            continue
        for row in rows:
            rid = row.get("roster_id")
            if rid is None:
                continue
            pts = row.get("players_points") or {}
            for pid in row.get("starters") or []:
                if pid in ("0", 0, None):
                    continue
                if float(pts.get(pid, 0.0) or 0.0) == 0.0:
                    counts[int(rid)] += 1
    return counts


# ---------------------------------------------------------------------------
# Pure-Python stats (no numpy/scipy dependency, matches project convention)
# ---------------------------------------------------------------------------

def pearson(xs, ys):
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def fisher_ci(r, n, level=0.90):
    if n <= 3 or math.isnan(r) or abs(r) >= 1.0:
        return (float("nan"), float("nan"))
    z = math.atanh(r)
    se = 1.0 / math.sqrt(n - 3)
    zcrit = 1.645 if level == 0.90 else 1.96
    lo, hi = z - zcrit * se, z + zcrit * se
    return (math.tanh(lo), math.tanh(hi))


def partial_corr(x, y, z):
    rxy, rxz, rzy = pearson(x, y), pearson(x, z), pearson(z, y)
    denom = math.sqrt((1 - rxz ** 2) * (1 - rzy ** 2))
    if denom <= 0:
        return float("nan")
    return (rxy - rxz * rzy) / denom


def cluster_bootstrap_r(rows, iters=4000, seed=20260809):
    """rows: list of (league, x, y). Cluster-resample by league (6 clusters —
    same caveat as the calibration backtest's bootstrap: wide, not precise)."""
    rng = random.Random(seed)
    by_league = defaultdict(list)
    for lg, x, y in rows:
        by_league[lg].append((x, y))
    leagues = list(by_league)
    out = []
    for _ in range(iters):
        draw = [rng.choice(leagues) for _ in leagues]
        xs = [p[0] for lg in draw for p in by_league[lg]]
        ys = [p[1] for lg in draw for p in by_league[lg]]
        if len(xs) >= 4:
            out.append(pearson(xs, ys))
    out = [v for v in out if not math.isnan(v)]
    out.sort()
    if not out:
        return (float("nan"), float("nan"))
    lo = out[int(0.05 * len(out))]
    hi = out[int(0.95 * len(out)) - 1]
    return (lo, hi)


def cluster_bootstrap_partial_r(rows, iters=4000, seed=20260809):
    """rows: list of (league, x, y, z). Cluster-resample by league, recompute
    the partial correlation of x,y controlling for z each draw."""
    rng = random.Random(seed)
    by_league = defaultdict(list)
    for lg, x, y, z in rows:
        by_league[lg].append((x, y, z))
    leagues = list(by_league)
    out = []
    for _ in range(iters):
        draw = [rng.choice(leagues) for _ in leagues]
        xs = [p[0] for lg in draw for p in by_league[lg]]
        ys = [p[1] for lg in draw for p in by_league[lg]]
        zs = [p[2] for lg in draw for p in by_league[lg]]
        if len(xs) >= 6:
            out.append(partial_corr(xs, ys, zs))
    out = [v for v in out if not math.isnan(v)]
    out.sort()
    if not out:
        return (float("nan"), float("nan"))
    lo = out[int(0.05 * len(out))]
    hi = out[int(0.95 * len(out)) - 1]
    return (lo, hi)


def permutation_group_diff(depth, outcome, group_hi, iters=5000, seed=20260809):
    """Permutation test on r(depth,outcome | high-absence) - r(... | low)."""
    rng = random.Random(seed)
    n = len(depth)
    idx_hi = [i for i in range(n) if group_hi[i]]
    idx_lo = [i for i in range(n) if not group_hi[i]]
    if len(idx_hi) < 4 or len(idx_lo) < 4:
        return None
    r_hi = pearson([depth[i] for i in idx_hi], [outcome[i] for i in idx_hi])
    r_lo = pearson([depth[i] for i in idx_lo], [outcome[i] for i in idx_lo])
    obs = r_hi - r_lo
    n_hi = len(idx_hi)
    all_idx = list(range(n))
    count = 0
    for _ in range(iters):
        rng.shuffle(all_idx)
        hi_ids = all_idx[:n_hi]
        lo_ids = all_idx[n_hi:]
        r1 = pearson([depth[i] for i in hi_ids], [outcome[i] for i in hi_ids])
        r2 = pearson([depth[i] for i in lo_ids], [outcome[i] for i in lo_ids])
        if not (math.isnan(r1) or math.isnan(r2)) and abs(r1 - r2) >= abs(obs):
            count += 1
    p = count / iters
    return {"r_high": r_hi, "r_low": r_lo, "diff": obs, "n_high": len(idx_hi),
            "n_low": len(idx_lo), "perm_p": p}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    value_by_fmt, pos_by_pid = build_value_boards()
    for fmt, d in value_by_fmt.items():
        print(f"value board [{fmt}]: {len(d)} rostered player ids priced "
              f"(of 870 total unique across the 6 seasons)")

    rows = []  # one dict per team-season
    for name, fmt in SEASONS:
        fx = load_fixture(name)
        full = build_full_state(fx)
        field, champ = truth(fx, full.playoff_slots)
        med = median_mode(fx)
        regular_weeks = full.regular_season_weeks
        week0 = as_of(full, 0)
        actual = as_of(full, regular_weeks)  # H2H-only actual wins, same scale
        # H2H-only regular season played straight through -> 0 games remain
        assert actual.completed_weeks == regular_weeks

        value = value_by_fmt[fmt]
        raw_by_id = {str(r["roster_id"]): r for r in fx["rosters"]}

        payload = run_outlook(
            week0, player_value=value, player_pos=pos_by_pid, model_cfg={},
            basis="consensus", source_override="auto", n_sims=10000)
        assert payload["meta"]["strength_source"] == "roster_value"
        implied = {t["roster_id"]: t for t in payload["teams"]}

        n_weeks = min(len(v) for v in full.weekly_scores.values())
        assert n_weeks == regular_weeks
        absence_by_rid = absence_events_by_roster(fx, regular_weeks)

        for t in full.teams:
            rid = t.roster_id
            dm = depth_metrics(t.player_ids, value, pos_by_pid, full.roster_slots)
            imp = implied[rid]
            actual_wins = next(a.wins for a in actual.teams if a.roster_id == rid)
            actual_points = sum(full.weekly_scores[rid])
            scoring_var = statistics.pvariance(full.weekly_scores[rid])
            implied_wins = imp["odds"]["projected_wins"]
            implied_points = imp["strength"]["mu"] * regular_weeks
            total_moves = int(((raw_by_id[str(rid)].get("settings") or {})
                               .get("total_moves") or 0))
            rows.append({
                "league": name, "roster_id": rid,
                "starter_total": dm["starter_total"],
                "bench_raw_sum": dm["bench_raw_sum"],
                "next_man_up_total": dm["next_man_up_total"],
                "dropoff_ratio_avg": dm["dropoff_ratio_avg"],
                "actual_wins": actual_wins,
                "implied_wins": implied_wins,
                "win_residual": actual_wins - implied_wins,
                "actual_points": actual_points,
                "implied_points": implied_points,
                "points_residual": actual_points - implied_points,
                "scoring_var": scoring_var,
                "playoff_actual": 1.0 if rid in field else 0.0,
                "playoff_implied": imp["odds"]["playoff_pct"],
                "title_actual": 1.0 if rid == champ else 0.0,
                "absence_events": absence_by_rid.get(rid, 0),
                "total_moves": total_moves,
                "median_match": med,
            })

    print(f"\nteam-seasons: {len(rows)}  leagues: {len(SEASONS)}  "
          f"playoff positives: {sum(r['playoff_actual'] for r in rows):.0f}  "
          f"title positives: {sum(r['title_actual'] for r in rows):.0f}")

    total_moves = [r["total_moves"] for r in rows]
    print(f"total_moves distribution: min={min(total_moves)} "
          f"median={statistics.median(total_moves)} max={max(total_moves)}")
    if max(total_moves) == 0:
        print("NOTE: Sleeper reports total_moves=0 for every roster in every "
              "one of these 6 closed league instances — the field is not "
              "retained/exposed for completed past seasons. The planned "
              "low-transaction robustness subsample is therefore NOT "
              "computable from this data; every team-season is equally "
              "unverifiable as 'preseason roster == captured roster'. "
              "Flagged as a limitation, not silently worked around.")

    dep_metrics = ["bench_raw_sum", "next_man_up_total", "dropoff_ratio_avg"]
    outcomes = ["win_residual", "points_residual", "playoff_actual", "scoring_var"]

    print("\n" + "=" * 78)
    print("PRIMARY RESULTS (n=%d, all 6 league-seasons)" % len(rows))
    print("=" * 78)
    report_block(rows, dep_metrics, outcomes)

    print("\n" + "=" * 78)
    print("MECHANISM — absence-interaction test")
    print("=" * 78)
    mechanism_block(rows, dep_metrics)

    dump = {
        "n_team_seasons": len(rows),
        "rows": rows,
    }
    out_path = os.path.join(FIXTURES_HYP, "hypothesis-1c-raw-results.json")
    with open(out_path, "w") as f:
        json.dump(dump, f, indent=1)
    print(f"\nraw per-team-season results written to {out_path}")


def report_block(rows, dep_metrics, outcomes):
    d = {k: [r[k] for r in rows] for k in dep_metrics + outcomes + ["starter_total"]}
    league_of = [r["league"] for r in rows]

    for dm in dep_metrics:
        x_all = d[dm]
        print(f"\n--- depth metric: {dm} ---")
        for oc in outcomes:
            y_all = d[oc]
            pairs = [(x, y) for x, y in zip(x_all, y_all) if x is not None and y is not None]
            if len(pairs) < 8:
                print(f"  {oc:18s} n={len(pairs)} (too few — skipped)")
                continue
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            r = pearson(xs, ys)
            lo, hi = fisher_ci(r, len(pairs))
            zrows = [(lg, x, y) for lg, x, y in zip(league_of, x_all, y_all)
                     if x is not None and y is not None]
            blo, bhi = cluster_bootstrap_r(zrows)
            sv = [r2["starter_total"] for r2, x, y in
                  zip(rows, x_all, y_all) if x is not None and y is not None]
            pr = partial_corr(xs, ys, sv)
            pz_rows = [(lg, x, y, s) for lg, x, y, s in
                      zip(league_of, x_all, y_all, d["starter_total"])
                      if x is not None and y is not None]
            plo, phi = cluster_bootstrap_partial_r(pz_rows)
            print(f"  {oc:18s} n={len(pairs):3d}  raw r={r:+.3f} "
                  f"(Fisher 90% CI [{lo:+.3f}, {hi:+.3f}], "
                  f"cluster-boot 90% CI [{blo:+.3f}, {bhi:+.3f}])")
            print(f"  {'':18s}       controlled r={pr:+.3f} "
                  f"(partial on starter_total, cluster-boot 90% CI "
                  f"[{plo:+.3f}, {phi:+.3f}])")


def mechanism_block(rows, dep_metrics):
    absence = [r["absence_events"] for r in rows]
    med_abs = statistics.median(absence)
    group_hi = [a > med_abs for a in absence]
    print(f"absence_events distribution: min={min(absence)} median={med_abs} "
          f"max={max(absence)}  high-absence group (> median): "
          f"{sum(group_hi)} teams, low-absence: {len(rows) - sum(group_hi)} teams")
    for dm in dep_metrics:
        depth = [r[dm] for r in rows]
        for oc in ["win_residual", "scoring_var"]:
            outcome = [r[oc] for r in rows]
            pairs_idx = [i for i in range(len(rows))
                        if depth[i] is not None and outcome[i] is not None]
            d2 = [depth[i] for i in pairs_idx]
            o2 = [outcome[i] for i in pairs_idx]
            g2 = [group_hi[i] for i in pairs_idx]
            res = permutation_group_diff(d2, o2, g2)
            if res is None:
                print(f"  {dm:20s} vs {oc:14s}: insufficient n per group")
                continue
            print(f"  {dm:20s} vs {oc:14s}: r(high-absence, n={res['n_high']})="
                  f"{res['r_high']:+.3f}  r(low-absence, n={res['n_low']})="
                  f"{res['r_low']:+.3f}  diff={res['diff']:+.3f}  "
                  f"perm p={res['perm_p']:.3f}")


if __name__ == "__main__":
    main()
