"""Re-test of #169 pick-capital hypothesis 1b with PERIOD-CORRECT value boards.

`hypothesis-pick-capital-2026-08-09.md` measured "Δ starting-lineup value"
with each player's own-season points-per-game, and said why:

    "there is no historical, dated dynasty-value board ... Pricing a 2022
     roster with today's live values would score a since-broken-out rookie as
     valuable in 2022 because of what he did in 2024-25"

`backend/dp_values_history.py` supplies the missing board, so the sub-test can
now be run the way the operator originally asked — in dynasty-value terms,
with no hindsight. Three pricings are computed for the SAME rosters:

  V0  own-season points-per-game, fixed        — the published method, rerun
                                                 verbatim as a control.
  V1  week-1 roster @ the kickoff board,
      week-14 roster @ the week-14 board       — HEADLINE. Fully
                                                 contemporaneous: each roster
                                                 is priced by the market that
                                                 existed when it was held.
  V2  BOTH rosters @ the kickoff board         — isolates roster construction.
                                                 V1 mixes "which players are
                                                 rostered" with "how the market
                                                 moved during the season"; V2
                                                 removes the second, and is the
                                                 dynasty-value analogue of V0's
                                                 fixed price list.

Everything else in the report — (ii) win outperformance, (iii) playoff berth,
and §6.2's buy:sell gradient — is recomputed here unchanged, to demonstrate
which numbers the correction can and cannot move.

    python3 scripts/outlook_pick_capital_dated_values.py

Offline. Reuses `scripts/outlook_pick_capital_hypothesis.py` (pick replay,
mechanism tags, stats) and `scripts/outlook_calibration_backtest.py` (fixtures,
as-of rewind, truth) rather than reimplementing either.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.outlook_calibration_backtest as backtest  # noqa: E402
import scripts.outlook_pick_capital_hypothesis as pch  # noqa: E402
from backend import dp_values_history as dvh  # noqa: E402
from backend.outlook.strength import starting_lineup_value  # noqa: E402
from scripts.outlook_preseason_backtest import (  # noqa: E402
    player_positions, roster_name_index, scoring_format_for,
)

REGULAR_WEEKS = 14


def priced(player_ids, values, player_pos, slots) -> float:
    pos = {pid: (player_pos.get(pid) or "?") for pid in player_ids}
    return starting_lineup_value(player_ids, values, pos, slots)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=10000)
    args = ap.parse_args()

    pos_map = player_positions()
    player_pos = {pid: (m.get("position") or "?") for pid, m in pos_map.items()}
    extra_idx = roster_name_index(pos_map)

    records = []
    mech_rows = []

    print("\n## Dated boards used\n")
    print("| league-season | scoring | kickoff board | week-14 board |"
          " unmatched (kickoff) | unmatched (wk14) |")
    print("|---|---|---|---|---|---|")

    for name, season in pch.SEASONS.items():
        fx_cal = backtest.load_fixture(name)
        fx_hyp = pch.load_hyp_fixture(name)
        roster_ids = [int(r["roster_id"]) for r in fx_cal["rosters"]]
        scoring = scoring_format_for(fx_cal)
        slots = pch.roster_slots_for(fx_cal)

        v_start, rep_start, meta_start = dvh.values_as_of(
            dvh.week_boundary(season, 0), scoring=scoring, extra_name_pos=extra_idx)
        v_end, rep_end, meta_end = dvh.values_as_of(
            dvh.week_boundary(season, REGULAR_WEEKS), scoring=scoring,
            extra_name_pos=extra_idx)
        print("| %s | %s | %s (%s) | %s (%s) | %.1f%% | %.1f%% |"
              % (name, scoring, meta_start["scrape_date"], meta_start["sha"][:8],
                 meta_end["scrape_date"], meta_end["sha"][:8],
                 100 * rep_start.unmatched_rate, 100 * rep_end.unmatched_rate))

        # unchanged inputs (pick capital, win residual, playoff berth, mechanism)
        trades_by_week = fx_hyp["transactions_trades"]
        preseason_trades = trades_by_week.get("1", [])
        inseason_trades = [t for wk, rows in trades_by_week.items()
                           if 2 <= int(wk) <= REGULAR_WEEKS for t in rows]
        start_grid = pch._apply_trades(pch._pristine_grid(season, roster_ids),
                                       preseason_trades)
        start_capital = pch.capital_by_roster(start_grid, season, roster_ids)

        ppg = pch.season_player_ppg(fx_cal, REGULAR_WEEKS)
        win_data = pch.week3_projected_wins_and_actual(fx_cal)
        field, _champ = backtest.truth(
            fx_cal, backtest.build_full_state(fx_cal).playoff_slots)
        mech = pch.mechanism_counts(inseason_trades, roster_ids)

        for rid in roster_ids:
            wk1 = pch.week_roster(fx_cal, 1, rid)
            wkN = pch.week_roster(fx_cal, REGULAR_WEEKS, rid)
            if not wk1 or not wkN:
                continue
            raw_c, val_c = start_capital[rid]
            proj_w, act_w = win_data[rid]
            records.append({
                "league": name, "roster_id": rid,
                "capital_raw": raw_c, "capital_value": val_c,
                # V0 — published method (points-per-game, fixed price list)
                "sl1_v0": pch.sl_value(wk1, ppg, slots),
                "slN_v0": pch.sl_value(wkN, ppg, slots),
                # V1 — each roster priced by its own contemporaneous board
                "sl1_v1": priced(wk1, v_start, player_pos, slots),
                "slN_v1": priced(wkN, v_end, player_pos, slots),
                # V2 — both rosters priced by the kickoff board
                "sl1_v2": priced(wk1, v_start, player_pos, slots),
                "slN_v2": priced(wkN, v_start, player_pos, slots),
                "win_residual": act_w - proj_w,
                "playoff": 1.0 if rid in field else 0.0,
            })
            mech_rows.append({"league": name, "roster_id": rid,
                              "capital_value": val_c, **mech[rid]})

    for r in records:
        for v in ("v0", "v1", "v2"):
            r["delta_" + v] = r["slN_" + v] - r["sl1_" + v]

    n_leagues = len({r["league"] for r in records})
    print("\n## Sample\n")
    print("  %d team-seasons across %d league-seasons (unchanged from the"
          " published report)" % (len(records), n_leagues))

    variants = [
        ("V0 own-season PPG, fixed (published)", "v0"),
        ("V1 contemporaneous boards (headline)", "v1"),
        ("V2 kickoff board, both ends", "v2"),
    ]

    print("\n## Confound check — season-start capital vs WEEK-1 lineup strength\n")
    print("| pricing | capital measure | Pearson r | 90% CI (cluster bootstrap) | reading |")
    print("|---|---|---|---|---|")
    for label, v in variants:
        for xk, xlabel in (("capital_raw", "raw count"),
                           ("capital_value", "value-weighted")):
            obs, ci = pch.cluster_bootstrap_corr(records, xk, "sl1_" + v)
            print("| %s | %s | %+.3f | [%+.3f, %+.3f] | %s |"
                  % (label, xlabel, obs, ci[0], ci[1],
                     "excludes 0" if (ci[0] > 0 or ci[1] < 0) else "includes 0"))

    print("\n## Hypothesis (i) — capital vs Δ starting-lineup value\n")
    print("| pricing | capital measure | Pearson r | Spearman rho |"
          " 90% CI (cluster bootstrap) | reading |")
    print("|---|---|---|---|---|---|")
    for label, v in variants:
        for xk, xlabel in (("capital_raw", "raw count"),
                           ("capital_value", "value-weighted")):
            xs = [r[xk] for r in records]
            ys = [r["delta_" + v] for r in records]
            obs, ci = pch.cluster_bootstrap_corr(records, xk, "delta_" + v)
            print("| %s | %s | %+.3f | %+.3f | [%+.3f, %+.3f] | %s |"
                  % (label, xlabel, pch.pearson(xs, ys), pch.spearman(xs, ys),
                     ci[0], ci[1],
                     "excludes 0" if (ci[0] > 0 or ci[1] < 0) else "includes 0"))

    print("\n## Outcome means by season-start capital tercile (value-weighted)\n")
    ordered = sorted(records, key=lambda r: r["capital_value"])
    m = len(ordered)
    thirds = [ordered[:m // 3], ordered[m // 3:2 * m // 3], ordered[2 * m // 3:]]
    labels = ["low (bottom third)", "mid", "high (top third)"]
    print("| tercile | n | mean capital | mean Δ V0 (PPG) | mean Δ V1 (dated) |"
          " mean Δ V2 (kickoff board) | mean win residual | playoff rate |")
    print("|---|---|---|---|---|---|---|---|")
    for lab, grp in zip(labels, thirds):
        print("| %s | %d | %.1f | %+.2f | %+.0f | %+.0f | %+.2f | %.0f%% |"
              % (lab, len(grp),
                 statistics.fmean(g["capital_value"] for g in grp),
                 statistics.fmean(g["delta_v0"] for g in grp),
                 statistics.fmean(g["delta_v1"] for g in grp),
                 statistics.fmean(g["delta_v2"] for g in grp),
                 statistics.fmean(g["win_residual"] for g in grp),
                 100 * statistics.fmean(g["playoff"] for g in grp)))

    print("\n## Value-independent results — recomputed, expected unchanged\n")
    for xk, xlabel in (("capital_raw", "raw count"), ("capital_value", "value-weighted")):
        xs = [r[xk] for r in records]
        ys = [r["win_residual"] for r in records]
        obs, ci = pch.cluster_bootstrap_corr(records, xk, "win_residual")
        print("  (ii) win outperformance   %-16s r=%+.3f  rho=%+.3f  90%% CI [%+.3f, %+.3f]"
              % (xlabel, pch.pearson(xs, ys), pch.spearman(xs, ys), ci[0], ci[1]))
    for xk, xlabel in (("capital_raw", "raw count"), ("capital_value", "value-weighted")):
        xs = [r[xk] for r in records]
        ys = [r["playoff"] for r in records]
        made = [r[xk] for r in records if r["playoff"] == 1.0]
        missed = [r[xk] for r in records if r["playoff"] == 0.0]
        print("  (iii) playoff berth       %-16s r=%+.3f  rho=%+.3f  mean(made)=%.1f mean(missed)=%.1f"
              % (xlabel, pch.pearson(xs, ys), pch.spearman(xs, ys),
                 statistics.fmean(made), statistics.fmean(missed)))

    print("\n## §6.2 buy:sell gradient — recomputed, value-board independent\n")
    ordered_m = sorted(mech_rows, key=lambda r: r["capital_value"])
    n = len(ordered_m)
    for lab, grp in zip(labels, [ordered_m[:n // 3], ordered_m[n // 3:2 * n // 3],
                                 ordered_m[2 * n // 3:]]):
        bought = sum(g["bought"] for g in grp)
        sold = sum(g["sold"] for g in grp)
        print("  %-20s n=%2d  bought=%2d  sold=%2d  buy:sell = %.1f : 1"
              % (lab, len(grp), bought, sold,
                 (bought / sold) if sold else float("inf")))


if __name__ == "__main__":
    main()
