"""#169 outlook engine — pick-capital hypothesis test (1a vs 1b), offline.

Tests two OPPOSITE-signed operator hypotheses about draft-pick capital on the
same 6 real backtested Sleeper dynasty league-seasons already captured for
`outlook_calibration_backtest.py`:

  1a "lots of picks -> in-season moves to get STRONGER"  (buy players w/ picks)
  1b "lots of picks -> signals a REBUILD, sheds players"  (sell players for picks)

Method (see the report for full writeup):
  1. Season-start pick capital per roster = replay every `type=='trade'`
     transaction Sleeper buckets under week 1 (empirically verified to mean
     "everything before this week's games completed" -- i.e. the whole
     off-season, see the module docstring section "WEEK-1 BUCKETING") onto a
     pristine "everyone owns their own future picks" grid, for future draft
     classes season+1..season+3. Priced two ways: raw count, and value via
     the SHIPPED `backend.pick_values.pick_pool_value` ladder (imported, not
     reimplemented).
  2. In-season roster change = optimal starting-lineup value (via the SHIPPED
     `backend.outlook.strength.starting_lineup_value`, imported not
     reimplemented) of the roster as of week 1 vs the roster as of the last
     regular-season week, using each player's OWN-SEASON points-per-game as
     the value input (see "WHY POINTS, NOT DYNASTY VALUE" below) so both
     snapshots are priced on the same fixed scale and only WHICH PLAYERS are
     rostered can move the number.
  3. Outperformance = actual regular-season wins (H2H-only scale, via the
     backtest's own clean `as_of()` rewind -- deliberately side-steps BUG-1,
     see the calibration report) minus week-3 trailing-scores `projected_wins`
     from the SAME shipped `run_outlook()` the backtest scores.
  4. A trade-level mechanism tag (picks-for-players / players-for-picks) from
     each in-season trade transaction's own `draft_picks` + `adds`/`drops`.

WHY POINTS, NOT DYNASTY VALUE (deviation from a literal reading of the brief)
------------------------------------------------------------------------------
`starting_lineup_value()` was designed to take a DYNASTY VALUE map. Scoring
roster change in dynasty-value terms for a past season would need a
historical, dated value board -- and the calibration report already
established FTF has none ("RosterValueStrength -- NO, not backtestable...
Sleeper exposes no historical rosters and FTF has no dated value snapshots").
Using TODAY's live value board on a 2022-2025 roster would price it with
hindsight (a since-broken-out player scores high in 2022 because of what he
did in 2024-25, not what was known in 2022) -- exactly the kind of dressed-up
result the brief's honesty section forbids. Feeding the SAME function each
player's own-season fantasy points-per-game instead is (a) contemporaneous,
no hindsight, (b) still literally `starting_lineup_value()`, unmodified,
(c) more directly on-topic for the hypotheses at hand, which are about
whether a roster got objectively BETTER OR WORSE AT SCORING POINTS, not
whether its dynasty trade value moved.

WEEK-1 BUCKETING (verified empirically, see this script's git history /
scratch probes -- not re-derived here)
------------------------------------------------------------------------------
Sleeper's `/transactions/{week}` for week=1 returns every transaction from
league creation/rollover through the end of week 1 (trades dated back to
March were observed in a week=1 bucket); week>=2 buckets are the real
single-week windows. So "season-start pick capital" = replay week==1 trades
only; "in-season change" = replay week>=2 (capped at `regular_season_weeks`,
so playoff-week trades aren't counted as "during the season that earned the
seed").

Repeatable offline: all new data was captured 2026-08-09 via
`scripts/outlook_pick_capital_capture.py` into
`backend/tests/fixtures/outlook-hypotheses/`. This script never touches the
network. Reuses `backend/tests/fixtures/outlook-calibration/` (rosters,
matchups, winners_bracket) and `scripts/outlook_calibration_backtest.py`
(fixture loader, `as_of()` rewind, `truth()`) rather than recreating them.

    python3 scripts/outlook_pick_capital_hypothesis.py
"""

from __future__ import annotations

import json
import os
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.outlook_calibration_backtest as backtest  # noqa: E402
from backend.outlook.league_state import _BENCH_SLOTS  # noqa: E402
from backend.outlook.pipeline import run_outlook  # noqa: E402
from backend.outlook.strength import starting_lineup_value  # noqa: E402
from backend.pick_values import pick_pool_value  # noqa: E402

HYP_FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backend", "tests", "fixtures", "outlook-hypotheses",
)

# name -> season int (must match backend/tests/fixtures/outlook-calibration/*)
SEASONS = {
    "lakeview-2025": 2025,
    "lakeview-2024": 2024,
    "ffv3-2025": 2025,
    "ffv3-2024": 2024,
    "ffv3-2023": 2023,
    "ffv3-2022": 2022,
}
FUTURE_YEARS_OUT = (1, 2, 3)   # season+1 .. season+3 = "future" pick capital


def load_hyp_fixture(name: str) -> dict:
    with open(os.path.join(HYP_FIXTURES, "%s.json" % name)) as f:
        return json.load(f)


PLAYER_POS = json.load(open(os.path.join(HYP_FIXTURES, "player-positions.json")))


# ---------------------------------------------------------------------------
# Pick-capital reconstruction (spine step 1)
# ---------------------------------------------------------------------------

def _pristine_grid(season: int, roster_ids: list[int]) -> dict:
    return {
        (season + y, rnd, rid): rid
        for y in FUTURE_YEARS_OUT
        for rnd in range(1, 5)
        for rid in roster_ids
    }


def _apply_trades(grid: dict, trades: list[dict]) -> dict:
    """Chronologically replay trade transactions' `draft_picks` entries onto
    `grid` (mutates a copy, returns it). Dynamically extends the grid for any
    (season, round, orig_roster) key not already present, mirroring
    `database.sync_draft_picks`'s "pick from a season/round not in our grid
    -- add it" step, so an off-ladder round or an already-current-season pick
    traded pre-draft is still tracked rather than silently dropped."""
    g = dict(grid)
    ordered = sorted(trades, key=lambda t: t.get("status_updated") or t.get("created") or 0)
    for t in ordered:
        for dp in (t.get("draft_picks") or []):
            try:
                season = int(dp["season"])
                rnd = int(dp["round"])
                orig = int(dp["roster_id"])
                new_owner = int(dp["owner_id"])
            except (KeyError, TypeError, ValueError):
                continue
            key = (season, rnd, orig)
            g.setdefault(key, orig)
            g[key] = new_owner
    return g


def capital_by_roster(grid: dict, season: int, roster_ids: list[int]) -> dict:
    """{roster_id: (raw_count, value_weighted)} of picks owned for
    season+1..season+3, priced via the SHIPPED `pick_pool_value` ladder.
    `scoring_format` is a documented no-op in `pick_pool_value` today (see
    that module), so the default is used uniformly."""
    out = {rid: [0, 0.0] for rid in roster_ids}
    for (pick_season, rnd, _orig), owner in grid.items():
        years_out = pick_season - season
        if years_out not in FUTURE_YEARS_OUT:
            continue
        if owner not in out:
            continue
        out[owner][0] += 1
        out[owner][1] += pick_pool_value(rnd, years_out)
    return {rid: (c, round(v, 1)) for rid, (c, v) in out.items()}


# ---------------------------------------------------------------------------
# Roster-strength reconstruction (spine step 2) — points-per-game pricing
# ---------------------------------------------------------------------------

def season_player_ppg(fx_cal: dict, regular_weeks: int) -> dict[str, float]:
    """{player_id: mean points across weeks 1..regular_weeks they were
    rostered by anyone (0.0 counted for a rostered-but-inactive/bye week --
    a limitation, see the report; applied symmetrically to both snapshots
    below so it cannot structurally favor 1a or 1b)."""
    pts: dict[str, list[float]] = defaultdict(list)
    for wk in range(1, regular_weeks + 1):
        for row in fx_cal["matchups"].get(str(wk), []):
            for pid, p in (row.get("players_points") or {}).items():
                pts[str(pid)].append(float(p or 0.0))
    return {pid: (sum(v) / len(v) if v else 0.0) for pid, v in pts.items()}


def roster_slots_for(fx_cal: dict) -> list[str]:
    positions = (fx_cal["league"] or {}).get("roster_positions") or []
    return [p for p in positions if p not in _BENCH_SLOTS]


def week_roster(fx_cal: dict, week: int, roster_id: int) -> list[str]:
    for row in fx_cal["matchups"].get(str(week), []):
        if row.get("roster_id") == roster_id:
            return [str(p) for p in (row.get("players") or [])]
    return []


def sl_value(player_ids: list[str], ppg: dict[str, float], slots: list[str]) -> float:
    player_pos = {pid: (PLAYER_POS.get(pid) or {}).get("position") or "?"
                  for pid in player_ids}
    return starting_lineup_value(player_ids, ppg, player_pos, slots)


# ---------------------------------------------------------------------------
# Outperformance (spine step 3) — reuses the backtest's own machinery
# ---------------------------------------------------------------------------

def week3_projected_wins_and_actual(fx_cal: dict) -> dict[int, tuple[float, float]]:
    """{roster_id: (week3_projected_wins, actual_regular_season_wins)}.
    Both on the H2H-only win_credit scale the simulator itself uses --
    deliberately side-steps BUG-1 (median-match double counting), which only
    afflicts the SHIPPED Phase-1 ingestion, not `as_of()`'s clean rewind."""
    full = backtest.build_full_state(fx_cal)
    st3 = backtest.as_of(full, 3)
    payload = run_outlook(st3, player_value={}, player_pos={}, model_cfg={},
                          basis="consensus", source_override="auto", n_sims=10000)
    proj = {t["roster_id"]: t["odds"]["projected_wins"] for t in payload["teams"]}
    final = backtest.as_of(full, full.regular_season_weeks)
    actual = {t.roster_id: t.win_credit for t in final.teams}
    return {rid: (proj[rid], actual[rid]) for rid in proj}


# ---------------------------------------------------------------------------
# Mechanism tag — picks-for-players vs players-for-picks per in-season trade
# ---------------------------------------------------------------------------

def mechanism_counts(trades: list[dict], roster_ids: list[int]) -> dict[int, dict[str, int]]:
    """{roster_id: {"bought": n, "sold": n, "mixed_or_other": n}} across the
    given trade set (caller passes the in-season-only subset). "bought" = net
    gave picks, received players (1a-style); "sold" = net gave players,
    received picks (1b-style)."""
    out = {rid: {"bought": 0, "sold": 0, "mixed_or_other": 0} for rid in roster_ids}
    for t in trades:
        adds = t.get("adds") or {}     # player_id -> receiving roster_id
        drops = t.get("drops") or {}   # player_id -> giving roster_id
        dps = t.get("draft_picks") or []
        for rid in (t.get("roster_ids") or []):
            if rid not in out:
                continue
            players_in = sum(1 for _, r in adds.items() if r == rid)
            players_out = sum(1 for _, r in drops.items() if r == rid)
            picks_in = sum(1 for dp in dps if dp.get("owner_id") == rid
                           and dp.get("previous_owner_id") != rid)
            picks_out = sum(1 for dp in dps if dp.get("previous_owner_id") == rid
                            and dp.get("owner_id") != rid)
            net_players = players_in - players_out
            net_picks = picks_in - picks_out
            if net_players > 0 and net_picks < 0:
                out[rid]["bought"] += 1
            elif net_players < 0 and net_picks > 0:
                out[rid]["sold"] += 1
            elif net_players or net_picks:
                out[rid]["mixed_or_other"] += 1
    return out


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(xs, ys):
    n = len(xs)
    if n < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return float("nan")
    return cov / (vx ** 0.5 * vy ** 0.5)


def spearman(xs, ys):
    return pearson(_rank(xs), _rank(ys))


def cluster_bootstrap_corr(records, key_x, key_y, method=pearson, iters=4000, seed=20260809):
    """Cluster bootstrap over league-seasons -- same resampling unit and
    rationale as outlook_calibration_backtest.bootstrap_skill: the 12
    team-seasons inside one league are not independent draws."""
    rng = random.Random(seed)
    by_league = defaultdict(list)
    for r in records:
        by_league[r["league"]].append(r)
    leagues = list(by_league)

    def corr_of(sample_leagues):
        rows = [r for lg in sample_leagues for r in by_league[lg]]
        xs = [r[key_x] for r in rows]
        ys = [r[key_y] for r in rows]
        return method(xs, ys)

    obs = corr_of(leagues)
    draws = []
    for _ in range(iters):
        sample = [rng.choice(leagues) for _ in leagues]
        v = corr_of(sample)
        if v == v:  # not NaN
            draws.append(v)
    draws.sort()
    if not draws:
        return obs, (float("nan"), float("nan"))
    lo = draws[int(0.05 * len(draws))]
    hi = draws[int(0.95 * len(draws))]
    return obs, (lo, hi)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    records = []          # one dict per team-season
    mech_rows = []         # per team-season mechanism tag counts
    validation_rows = []   # replay-vs-traded_picks agreement

    print("\n## Per-league-season pick-capital + roster-change summary\n")
    for name, season in SEASONS.items():
        fx_cal = backtest.load_fixture(name)
        fx_hyp = load_hyp_fixture(name)
        roster_ids = [int(r["roster_id"]) for r in fx_cal["rosters"]]
        regular_weeks = 14  # confirmed for all 6 fixtures (calibration report table)

        trades_by_week = fx_hyp["transactions_trades"]
        preseason_trades = trades_by_week.get("1", [])
        inseason_trades = [t for wk, rows in trades_by_week.items()
                           if 2 <= int(wk) <= regular_weeks for t in rows]
        all_reg_trades = preseason_trades + inseason_trades

        pristine = _pristine_grid(season, roster_ids)
        start_grid = _apply_trades(pristine, preseason_trades)
        end_grid = _apply_trades(start_grid, inseason_trades)
        start_capital = capital_by_roster(start_grid, season, roster_ids)
        end_capital = capital_by_roster(end_grid, season, roster_ids)

        # --- validation: replay ALL captured trades (wk 1-18) vs Sleeper's
        # own current traded_picks snapshot for this league_id ---
        all_trades = [t for rows in trades_by_week.values() for t in rows]
        full_grid = _apply_trades(pristine, all_trades)
        # Restrict to years_out 1-3 (future, undrafted classes) on BOTH sides
        # before comparing: Sleeper's own traded_picks purges a pick once its
        # draft completes, but the transaction ledger keeps the historical
        # record forever, so an unfiltered comparison would flag every
        # already-drafted current-season pick as a "mismatch" when it is
        # really just off Sleeper's list for an unrelated reason.
        replay_owner = {k: v for k, v in full_grid.items()
                        if v != k[2] and 1 <= k[0] - season <= 3}
        sleeper_owner = {}
        for tp in fx_hyp["traded_picks"]:
            try:
                k = (int(tp["season"]), int(tp["round"]), int(tp["roster_id"]))
                sleeper_owner[k] = int(tp["owner_id"])
            except (KeyError, TypeError, ValueError):
                continue
        sleeper_owner = {k: v for k, v in sleeper_owner.items()
                         if 1 <= k[0] - season <= 3}
        # Three-way split, not a raw match rate: keys BOTH sources have an
        # opinion on either agree or reveal a real replay bug; keys only
        # Sleeper still tracks are a genuine coverage gap (transactions/{week}
        # tops out at week 18, but real trading continues into the following
        # off-season, under the SAME league_id, until the next season's
        # league object is created -- invisible to an 18-week sweep); keys
        # only the replay has and Sleeper doesn't would mean the replay
        # invented a trade Sleeper has no record of (checked: never happens).
        both = set(replay_owner) & set(sleeper_owner)
        agree_both = sum(1 for k in both if replay_owner[k] == sleeper_owner[k])
        only_sleeper = len(set(sleeper_owner) - set(replay_owner))
        only_replay = len(set(replay_owner) - set(sleeper_owner))
        validation_rows.append((name, len(both), agree_both, only_sleeper, only_replay))

        ppg = season_player_ppg(fx_cal, regular_weeks)
        slots = roster_slots_for(fx_cal)
        win_data = week3_projected_wins_and_actual(fx_cal)
        field, champ = backtest.truth(fx_cal, backtest.build_full_state(fx_cal).playoff_slots)
        mech = mechanism_counts(inseason_trades, roster_ids)

        print("  %-14s season=%d teams=%d preseason_trades=%d inseason_trades=%d"
              % (name, season, len(roster_ids), len(preseason_trades), len(inseason_trades)))

        for rid in roster_ids:
            wk1 = week_roster(fx_cal, 1, rid)
            wkN = week_roster(fx_cal, regular_weeks, rid)
            sl1 = sl_value(wk1, ppg, slots) if wk1 else float("nan")
            slN = sl_value(wkN, ppg, slots) if wkN else float("nan")
            proj_w, act_w = win_data[rid]
            raw_c, val_c = start_capital[rid]
            raw_c_end, val_c_end = end_capital[rid]
            records.append({
                "league": name,
                "roster_id": rid,
                "capital_raw": raw_c,
                "capital_value": val_c,
                "capital_raw_end": raw_c_end,
                "capital_value_end": val_c_end,
                "sl_week1": sl1,
                "sl_final": slN,
                "delta_sl": (slN - sl1) if (sl1 == sl1 and slN == slN) else float("nan"),
                "proj_wins_wk3": proj_w,
                "actual_wins": act_w,
                "win_residual": act_w - proj_w,
                "playoff": 1.0 if rid in field else 0.0,
                "champion": 1.0 if rid == champ else 0.0,
            })
            mech_rows.append({
                "league": name, "roster_id": rid,
                "capital_value": val_c,
                "bought": mech[rid]["bought"], "sold": mech[rid]["sold"],
                "mixed": mech[rid]["mixed_or_other"],
            })

    print("\n## Pick-ownership replay validation (weeks 1-18 vs Sleeper's own traded_picks)\n")
    print("| league-season | keys both track | agree | only Sleeper (coverage gap) | only replay (bug?) |")
    print("|---|---|---|---|---|")
    tot_both = tot_agree = tot_only_sleeper = tot_only_replay = 0
    for name, n_both, agree, only_sleeper, only_replay in validation_rows:
        tot_both += n_both
        tot_agree += agree
        tot_only_sleeper += only_sleeper
        tot_only_replay += only_replay
        pct = 100 * agree / n_both if n_both else float("nan")
        print("| %s | %d | %d (%.1f%%) | %d | %d |"
              % (name, n_both, agree, pct, only_sleeper, only_replay))
    print("| **total** | **%d** | **%d (%.1f%%)** | **%d** | **%d** |"
          % (tot_both, tot_agree, 100 * tot_agree / tot_both if tot_both else 0,
             tot_only_sleeper, tot_only_replay))

    clean = [r for r in records if r["delta_sl"] == r["delta_sl"]]
    n_leagues = len(SEASONS)
    n_teams = len(clean)
    print("\n## Sample\n")
    print("  team-seasons: %d across %d league-seasons" % (n_teams, n_leagues))

    print("\n## Confound check — is season-start capital already correlated with week-1 roster strength?\n")
    for xk, label in [("capital_raw", "raw pick count"), ("capital_value", "value-weighted")]:
        xs = [r[xk] for r in clean]
        ys = [r["sl_week1"] for r in clean]
        obs, ci = cluster_bootstrap_corr(clean, xk, "sl_week1", method=pearson)
        print("  %-32s Pearson r=%+.3f vs week-1 lineup strength  bootstrap 90%% CI [%+.3f, %+.3f]"
              % (label, pearson(xs, ys), ci[0], ci[1]))

    print("\n## Hypothesis (i) — capital vs in-season roster-strength delta (points-scale)\n")
    for xk, label in [("capital_raw", "raw pick count"), ("capital_value", "value-weighted (pick_pool_value)")]:
        xs = [r[xk] for r in clean]
        ys = [r["delta_sl"] for r in clean]
        r_p = pearson(xs, ys)
        r_s = spearman(xs, ys)
        obs, ci = cluster_bootstrap_corr(clean, xk, "delta_sl", method=pearson)
        print("  %-32s Pearson r=%+.3f  Spearman rho=%+.3f  "
              "bootstrap 90%% CI [%+.3f, %+.3f]  -> %s"
              % (label, r_p, r_s, ci[0], ci[1],
                 "excludes 0" if (ci[0] > 0 or ci[1] < 0) else "includes 0"))

    print("\n## Hypothesis (ii) — capital vs win outperformance (actual - week3-implied)\n")
    for xk, label in [("capital_raw", "raw pick count"), ("capital_value", "value-weighted")]:
        xs = [r[xk] for r in clean]
        ys = [r["win_residual"] for r in clean]
        r_p = pearson(xs, ys)
        r_s = spearman(xs, ys)
        obs, ci = cluster_bootstrap_corr(clean, xk, "win_residual", method=pearson)
        print("  %-32s Pearson r=%+.3f  Spearman rho=%+.3f  "
              "bootstrap 90%% CI [%+.3f, %+.3f]  -> %s"
              % (label, r_p, r_s, ci[0], ci[1],
                 "excludes 0" if (ci[0] > 0 or ci[1] < 0) else "includes 0"))

    print("\n## Hypothesis (iii) — capital vs playoff berth\n")
    for xk, label in [("capital_raw", "raw pick count"), ("capital_value", "value-weighted")]:
        xs = [r[xk] for r in clean]
        ys = [r["playoff"] for r in clean]
        r_p = pearson(xs, ys)
        r_s = spearman(xs, ys)
        made = [r[xk] for r in clean if r["playoff"] == 1.0]
        missed = [r[xk] for r in clean if r["playoff"] == 0.0]
        print("  %-32s Pearson r=%+.3f  Spearman rho=%+.3f  "
              "mean(made playoffs)=%.2f  mean(missed)=%.2f"
              % (label, r_p, r_s,
                 sum(made) / len(made) if made else float("nan"),
                 sum(missed) / len(missed) if missed else float("nan")))

    print("\n## Moderator split — contender vs non-contender at week 7\n")
    # recompute week-7 win_credit rank per league to split top/bottom half
    contender_flag = {}
    for name in SEASONS:
        fx_cal = backtest.load_fixture(name)
        full = backtest.build_full_state(fx_cal)
        st7 = backtest.as_of(full, 7)
        order = sorted(st7.teams, key=lambda t: (-t.win_credit, -t.points_for))
        half = len(order) // 2
        for i, t in enumerate(order):
            contender_flag[(name, t.roster_id)] = (i < half)
    for tag, want in [("contenders (top half @ wk7)", True), ("non-contenders (bottom half @ wk7)", False)]:
        sub = [r for r in clean if contender_flag.get((r["league"], r["roster_id"])) == want]
        xs = [r["capital_value"] for r in sub]
        ys_sl = [r["delta_sl"] for r in sub]
        ys_win = [r["win_residual"] for r in sub]
        print("  %-38s n=%2d  capital-vs-delta_sl r=%+.3f   capital-vs-win_residual r=%+.3f"
              % (tag, len(sub), pearson(xs, ys_sl), pearson(xs, ys_win)))

    print("\n## Mechanism tag — in-season trade direction by season-start capital tercile\n")
    sorted_by_cap = sorted(mech_rows, key=lambda r: r["capital_value"])
    n = len(sorted_by_cap)
    thirds = [sorted_by_cap[:n // 3], sorted_by_cap[n // 3: 2 * n // 3], sorted_by_cap[2 * n // 3:]]
    labels = ["low capital (bottom third)", "mid capital", "high capital (top third)"]
    for lab, grp in zip(labels, thirds):
        bought = sum(g["bought"] for g in grp)
        sold = sum(g["sold"] for g in grp)
        mixed = sum(g["mixed"] for g in grp)
        print("  %-30s n=%2d  bought(picks->players)=%2d  sold(players->picks)=%2d  mixed=%2d"
              % (lab, len(grp), bought, sold, mixed))

    print("\n## Outcome means by season-start capital tercile (value-weighted)\n")
    clean_sorted = sorted(clean, key=lambda r: r["capital_value"])
    m = len(clean_sorted)
    cthirds = [clean_sorted[:m // 3], clean_sorted[m // 3: 2 * m // 3], clean_sorted[2 * m // 3:]]
    for lab, grp in zip(labels, cthirds):
        mean_cap = statistics.fmean(g["capital_value"] for g in grp)
        mean_dsl = statistics.fmean(g["delta_sl"] for g in grp)
        mean_wr = statistics.fmean(g["win_residual"] for g in grp)
        playoff_rate = statistics.fmean(g["playoff"] for g in grp)
        print("  %-30s n=%2d  mean_capital=%7.1f  mean_delta_sl=%+6.2f  "
              "mean_win_residual=%+.2f  playoff_rate=%.0f%%"
              % (lab, len(grp), mean_cap, mean_dsl, mean_wr, 100 * playoff_rate))

    print("\n## Per-league-season table (value-weighted capital, delta_sl, win_residual)\n")
    print("| league | roster | capital_value | delta_sl | win_residual | playoff |")
    print("|---|---|---|---|---|---|")
    for r in clean:
        print("| %s | %d | %.1f | %+.2f | %+.2f | %d |"
              % (r["league"], r["roster_id"], r["capital_value"],
                 r["delta_sl"], r["win_residual"], int(r["playoff"])))


if __name__ == "__main__":
    main()
