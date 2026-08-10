"""Backtest the PRESEASON `roster_value` strength source — #169, offline.

The 2026-08-09 calibration report could not score this source and said so
plainly: *"RosterValueStrength — NO, not backtestable ... FTF has no dated
value snapshots"*. It is the source a user sees FIRST (`auto` resolves to it
at `completed_weeks == 0`), so leaving it unvalidated blocked the whole
preseason surface.

`backend/dp_values_history.py` removes that blocker: the DynastyProcess repo
keeps the git history of `values-players.csv`, so a 2022 roster can be priced
with a 2022 board. This script does exactly that, once per league-season, at
as-of week 0.

WHAT IS AND IS NOT REWOUND
--------------------------
The calibration harness rewinds standings but NOT rosters — it notes that
`player_ids` stay at the current (2026) Sleeper snapshot, which is harmless
for `trailing_scores` (it never reads rosters) and fatal for `roster_value`
(it reads nothing else). So this script rewinds BOTH:

  standings  `backtest.as_of(full, 0)`  — 0-0-0, no weekly scores, week 0.
  rosters    each team's ACTUAL week-1 roster from `/matchups/1`, which
             Sleeper serves complete (starters + bench) for that exact week.
  values     the DP board as it stood on kickoff day (the last board
             published before a single game was played).

Nothing the simulator then reads postdates kickoff, except the remaining-week
pairing schedule — published in full before week 1 (calibration report BUG-2)
and worth ~5 % of playoff Brier either way.

BASELINES
---------
B1 climatology only. The calibration report's B2/B3 standings extrapolations
are **degenerate at week 0** — every team is 0-0-0 with 0 points-for, so they
reduce to "the first `playoff_slots` roster ids", i.e. an arbitrary ordering,
and reporting them as beaten baselines would be dishonest. Two *references*
are reported instead:
  R-wk3   the already-validated week-3 `trailing_scores` model on the same
          league-seasons — the alternative to showing preseason odds at all
          is showing nothing until week 3, so this is the real decision.
  R-today the same preseason pipeline priced with TODAY's (2026-08-09) board
          instead of the period-correct one. It is NOT a legitimate predictor;
          it exists to size the hindsight bias the three prior docs feared.

    python3 scripts/outlook_preseason_backtest.py --sims 10000

Offline: DP boards from `backend/tests/fixtures/dp-values-history/`, Sleeper
responses from `backend/tests/fixtures/outlook-calibration/`, positions from
`backend/tests/fixtures/outlook-hypotheses/`. Never touches the network.
Changes nothing under `backend/outlook/`; reads no feature flag.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.outlook_calibration_backtest as backtest  # noqa: E402
from backend import dp_values_history as dvh  # noqa: E402
from backend.data_loader import normalise_name  # noqa: E402
from backend.outlook.pipeline import run_outlook  # noqa: E402
from backend.outlook.strength import select_starting_lineup  # noqa: E402

HYP_FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backend", "tests", "fixtures", "outlook-hypotheses",
)
TODAY_BOARD = os.path.join(HYP_FIXTURES, "dp-values-players-2026-08-09.csv")

# league-season -> season year (same 6 the calibration report scored)
SEASONS = {
    "lakeview-2025": 2025, "lakeview-2024": 2024,
    "ffv3-2025": 2025, "ffv3-2024": 2024,
    "ffv3-2023": 2023, "ffv3-2022": 2022,
}
REGULAR_WEEKS = 14
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def player_positions() -> dict[str, dict]:
    with open(os.path.join(HYP_FIXTURES, "player-positions.json")) as f:
        return json.load(f)


def roster_name_index(pos_map: dict[str, dict]) -> dict[tuple[str, str], str]:
    """Tier-3 join index: (normalised Sleeper name, position) -> sleeper id,
    restricted to the players actually rostered in these 6 seasons.

    `db_playerids.csv` is a CURRENT file — it has dropped some players who
    were rostered in 2022 — and DP sometimes writes a short form Sleeper does
    not ("Ken Walker III" vs "Kenneth Walker"). Position-strict (#127)."""
    idx: dict[tuple[str, str], str] = {}
    for pid, meta in pos_map.items():
        nm = normalise_name(meta.get("full_name") or "")
        pos = (meta.get("position") or "").upper()
        if nm and pos:
            idx.setdefault((nm, pos), pid)
    return idx


def scoring_format_for(fx: dict) -> str:
    """DP value column to price this league with, from its own slots."""
    slots = (fx["league"] or {}).get("roster_positions") or []
    return "2qb" if any(s in ("SUPER_FLEX", "SUPERFLEX") for s in slots) else "1qb"


def week_roster(fx: dict, week: int, roster_id: int) -> list[str]:
    for row in fx["matchups"].get(str(week), []):
        if row.get("roster_id") == roster_id:
            return [str(p) for p in (row.get("players") or [])]
    return []


def today_board_values(scoring: str, extra_name_pos):
    with open(TODAY_BOARD, newline="") as f:
        rows = list(csv.DictReader(f))
    return dvh.build_value_map(rows, scoring=scoring,
                               extra_name_pos=extra_name_pos)


def rewind_rosters(state, fx: dict):
    """Swap each team's CURRENT player_ids for its real week-1 roster."""
    missing = []
    for t in state.teams:
        wk1 = week_roster(fx, 1, t.roster_id)
        if not wk1:
            missing.append(t.roster_id)
            continue
        t.player_ids = wk1
    return missing


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

def coverage(state, values, player_pos) -> tuple[float, float]:
    """(roster id coverage, starting-slot coverage) at skill positions.

    Roster coverage is the honest denominator for "did the board resolve";
    starting-slot coverage is what actually moves mu, since
    `starting_lineup_value` only sums the selected lineup."""
    ros_tot = ros_hit = slot_tot = slot_hit = 0
    for t in state.teams:
        for pid in t.player_ids:
            if (player_pos.get(pid) or "?") in SKILL_POSITIONS:
                ros_tot += 1
                ros_hit += 1 if values.get(pid) else 0
        selected = select_starting_lineup(t.player_ids, values, player_pos,
                                          state.roster_slots)
        for pid in selected:
            if (player_pos.get(pid) or "?") in SKILL_POSITIONS:
                slot_tot += 1
                slot_hit += 1 if values.get(pid) else 0
    return (ros_hit / ros_tot if ros_tot else 0.0,
            slot_hit / slot_tot if slot_tot else 0.0)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def cluster_bootstrap(records, key, iters=4000, seed=20260809):
    """90 % CI on Brier skill vs climatology, resampling LEAGUE-SEASONS.

    Same unit and same caveat as the calibration report: the 12 team-seasons
    inside one league are mechanically dependent, and 6 clusters is a very
    small bootstrap — read the interval as wide, not precise."""
    rng = random.Random(seed)
    by_league = defaultdict(list)
    for r in records:
        by_league[r["league"]].append(r)
    leagues = list(by_league)

    def skill(sample):
        rows = [r for lg in sample for r in by_league[lg]]
        model = backtest.brier([(r["p_" + key], r["y_" + key]) for r in rows])
        clim = backtest.brier([(r["clim_" + key], r["y_" + key]) for r in rows])
        return 1 - model / clim if clim else float("nan")

    draws = sorted(skill([rng.choice(leagues) for _ in leagues])
                   for _ in range(iters))
    return skill(leagues), draws[int(0.05 * len(draws))], draws[int(0.95 * len(draws))]


def paired_bootstrap(records, a, b, key, iters=4000, seed=20260809):
    """90 % CI on the Brier DELTA (a - b) for the same team-seasons. Negative
    means predictor `a` is better."""
    rng = random.Random(seed)
    by_league = defaultdict(list)
    for r in records:
        by_league[r["league"]].append(r)
    leagues = list(by_league)

    def delta(sample):
        rows = [r for lg in sample for r in by_league[lg]]
        return (backtest.brier([(r[a + "_" + key], r["y_" + key]) for r in rows])
                - backtest.brier([(r[b + "_" + key], r["y_" + key]) for r in rows]))

    draws = sorted(delta([rng.choice(leagues) for _ in leagues])
                   for _ in range(iters))
    return delta(leagues), draws[int(0.05 * len(draws))], draws[int(0.95 * len(draws))]


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        out = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2.0 + 1
            i = j + 1
        return out
    rx, ry = rank(xs), rank(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else float("nan")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=10000)
    args = ap.parse_args()

    pos_map = player_positions()
    player_pos = {pid: (m.get("position") or "?") for pid, m in pos_map.items()}
    extra_idx = roster_name_index(pos_map)

    records = []
    print("\n## Board coverage per league-season (as-of week 0)\n")
    print("| league-season | scoring | board date | sha | DP rows | unmatched DP rows |"
          " roster coverage | starting-slot coverage |")
    print("|---|---|---|---|---|---|---|---|")

    order_rows = []
    for name, season in SEASONS.items():
        fx = backtest.load_fixture(name)
        full = backtest.build_full_state(fx)
        field, champ = backtest.truth(fx, full.playoff_slots)
        scoring = scoring_format_for(fx)

        key = dvh.week_boundary(season, 0)
        values, rep, meta = dvh.values_as_of(key, scoring=scoring,
                                            extra_name_pos=extra_idx)
        today_vals, today_rep = today_board_values(scoring, extra_idx)

        st0 = backtest.as_of(full, 0)
        gaps = rewind_rosters(st0, fx)
        assert not gaps, "no week-1 roster for %s rosters %s" % (name, gaps)
        assert st0.completed_weeks == 0

        ros_cov, slot_cov = coverage(st0, values, player_pos)
        print("| %s | %s | %s | %s | %d | %d (%.1f%%) | %.1f%% | %.1f%% |"
              % (name, scoring, key.isoformat(), meta["sha"][:10],
                 rep.total_rows, rep.unmatched, 100 * rep.unmatched_rate,
                 100 * ros_cov, 100 * slot_cov))

        payload = run_outlook(st0, player_value=values, player_pos=player_pos,
                              model_cfg={}, basis="consensus",
                              source_override="auto", n_sims=args.sims)
        assert payload["meta"]["strength_source"] == "roster_value", \
            payload["meta"]["strength_source"]

        today_payload = run_outlook(st0, player_value=today_vals,
                                    player_pos=player_pos, model_cfg={},
                                    basis="consensus", source_override="auto",
                                    n_sims=args.sims)

        # already-validated reference: the week-3 trailing-scores model
        st3 = backtest.as_of(full, 3)
        wk3 = run_outlook(st3, player_value={}, player_pos={}, model_cfg={},
                          basis="consensus", source_override="auto",
                          n_sims=args.sims)
        assert wk3["meta"]["strength_source"] == "trailing_scores"

        by_rid = {t["roster_id"]: t for t in payload["teams"]}
        today_by_rid = {t["roster_id"]: t for t in today_payload["teams"]}
        wk3_by_rid = {t["roster_id"]: t for t in wk3["teams"]}
        final = backtest.as_of(full, REGULAR_WEEKS)
        wins = {t.roster_id: t.win_credit for t in final.teams}

        n = len(full.teams)
        for t in full.teams:
            rid = t.roster_id
            records.append({
                "league": name, "season": season, "roster_id": rid,
                "median_match": backtest.median_mode(fx),
                "mu": by_rid[rid]["odds"]["projected_wins"],
                "p_playoff": by_rid[rid]["odds"]["playoff_pct"],
                "p_title": by_rid[rid]["odds"]["title_pct"],
                "today_playoff": today_by_rid[rid]["odds"]["playoff_pct"],
                "today_title": today_by_rid[rid]["odds"]["title_pct"],
                "wk3_playoff": wk3_by_rid[rid]["odds"]["playoff_pct"],
                "wk3_title": wk3_by_rid[rid]["odds"]["title_pct"],
                "clim_playoff": full.playoff_slots / n,
                "clim_title": 1.0 / n,
                "y_playoff": 1.0 if rid in field else 0.0,
                "y_title": 1.0 if rid == champ else 0.0,
                "actual_wins": wins[rid],
            })
        order_rows.append((name, [r for r in records if r["league"] == name]))

    print("\n  (roster coverage = share of rostered QB/RB/WR/TE with a value on"
          " that dated board; starting-slot coverage = share of the SELECTED"
          " starting lineup's skill slots that are priced)")

    # ---------------------------------------------------------------- headline
    def col(k):
        return [(r[k], r["y_" + k.split("_")[-1]]) for r in records]

    mp = [(r["p_playoff"], r["y_playoff"]) for r in records]
    mt = [(r["p_title"], r["y_title"]) for r in records]
    cp = [(r["clim_playoff"], r["y_playoff"]) for r in records]
    ct = [(r["clim_title"], r["y_title"]) for r in records]
    tp = [(r["today_playoff"], r["y_playoff"]) for r in records]
    tt = [(r["today_title"], r["y_title"]) for r in records]
    w3p = [(r["wk3_playoff"], r["y_playoff"]) for r in records]
    w3t = [(r["wk3_title"], r["y_title"]) for r in records]

    print("\n## Headline — preseason (as-of week 0), n = %d team-seasons\n" % len(records))
    print("| predictor | playoff Brier | skill vs climatology | title Brier | skill vs climatology |")
    print("|---|---|---|---|---|")
    for label, p, t in [
        ("preseason roster_value (period-correct board)", mp, mt),
        ("B1 climatology", cp, ct),
        ("R-wk3 trailing_scores (reference)", w3p, w3t),
        ("R-today roster_value w/ 2026 board (hindsight control)", tp, tt),
    ]:
        print("| %s | %.4f | %+.1f %% | %.4f | %+.1f %% |"
              % (label, backtest.brier(p),
                 100 * (1 - backtest.brier(p) / backtest.brier(cp)),
                 backtest.brier(t),
                 100 * (1 - backtest.brier(t) / backtest.brier(ct))))
    print("\n  log-loss: playoff %.4f  title %.4f"
          % (backtest.logloss(mp), backtest.logloss(mt)))

    print("\n## Cluster bootstrap over 6 league-seasons (90 %% interval)\n")
    for key in ("playoff", "title"):
        obs, lo, hi = cluster_bootstrap(records, key)
        print("  preseason %-7s skill vs climatology: %+.1f %%  90%% CI [%+.1f %%, %+.1f %%]  -> %s"
              % (key, 100 * obs, 100 * lo, 100 * hi,
                 "EXCLUDES 0" if lo > 0 else "INCLUDES 0"))
    for key in ("playoff", "title"):
        d, lo, hi = paired_bootstrap(records, "p", "wk3", key)
        print("  preseason - week3 %-7s Brier delta: %+.4f  90%% CI [%+.4f, %+.4f]  -> %s"
              % (key, d, lo, hi,
                 "preseason BETTER" if hi < 0 else
                 "week 3 BETTER" if lo > 0 else "indistinguishable"))
    for key in ("playoff", "title"):
        d, lo, hi = paired_bootstrap(records, "p", "today", key)
        print("  period-correct - today %-7s Brier delta: %+.4f  90%% CI [%+.4f, %+.4f]  -> %s"
              % (key, d, lo, hi,
                 "period-correct BETTER" if hi < 0 else
                 "today's board BETTER (hindsight)" if lo > 0 else "indistinguishable"))

    print("\n## Calibration — preseason playoff odds\n")
    print(backtest.fmt_cal(backtest.calibration_table(mp)))
    print("\n## Calibration — preseason title odds\n")
    print(backtest.fmt_cal(backtest.calibration_table(mt)))

    print("\n## Ordering skill — does the preseason board rank teams correctly?\n")
    print("| league-season | Spearman(mu, actual wins) | Spearman(playoff odds, wins) |"
          " playoff-field overlap | median match |")
    print("|---|---|---|---|---|")
    overlaps = []
    for name, rows in order_rows:
        mus = [r["mu"] for r in rows]
        wins = [r["actual_wins"] for r in rows]
        pods = [r["p_playoff"] for r in rows]
        k = int(sum(r["y_playoff"] for r in rows))
        predicted = {r["roster_id"] for r in sorted(rows, key=lambda r: -r["p_playoff"])[:k]}
        actual = {r["roster_id"] for r in rows if r["y_playoff"] == 1.0}
        overlaps.append(len(predicted & actual))
        print("| %s | %+.3f | %+.3f | %d/%d | %s |"
              % (name, spearman(mus, wins), spearman(pods, wins),
                 len(predicted & actual), k, rows[0]["median_match"]))
    print("| **pooled** | | | **%d/%d** | |" % (sum(overlaps), 6 * 6))

    print("\n## Per-league-season Brier\n")
    print("| league-season | preseason playoff | wk3 playoff | climatology |"
          " preseason title | wk3 title |")
    print("|---|---|---|---|---|---|")
    for name, rows in order_rows:
        print("| %s | %.4f | %.4f | %.4f | %.4f | %.4f |"
              % (name,
                 backtest.brier([(r["p_playoff"], r["y_playoff"]) for r in rows]),
                 backtest.brier([(r["wk3_playoff"], r["y_playoff"]) for r in rows]),
                 backtest.brier([(r["clim_playoff"], r["y_playoff"]) for r in rows]),
                 backtest.brier([(r["p_title"], r["y_title"]) for r in rows]),
                 backtest.brier([(r["wk3_title"], r["y_title"]) for r in rows])))

    print("\n## Shrinkage sensitivity — IN-SAMPLE, not a fitted recommendation\n")
    print("  The calibration table above is over-confident at the extremes, which"
          "\n  is the shape a shrink toward climatology fixes. Reported so the"
          "\n  operator can see the size of the effect; lambda is NOT tuned on"
          "\n  held-out data and must not be read as a validated parameter.\n")
    print("| lambda (weight on model) | playoff Brier | title Brier |")
    print("|---|---|---|")
    for lam in (1.0, 0.9, 0.75, 0.5, 0.25, 0.0):
        sp = [(lam * r["p_playoff"] + (1 - lam) * r["clim_playoff"], r["y_playoff"])
              for r in records]
        stt = [(lam * r["p_title"] + (1 - lam) * r["clim_title"], r["y_title"])
               for r in records]
        print("| %.2f | %.4f | %.4f |" % (lam, backtest.brier(sp), backtest.brier(stt)))

    beat = sum(1 for _n, rows in order_rows
               if backtest.brier([(r["p_playoff"], r["y_playoff"]) for r in rows])
               < 0.25)
    print("\n  league-seasons where preseason playoff Brier beats climatology:"
          " %d / %d" % (beat, len(order_rows)))

    print("\n## Median-match split (BUG-1 interaction)\n")
    for flag, label in ((True, "median-match leagues (Lakeview)"),
                        (False, "H2H-only leagues (FFv3)")):
        sub = [r for r in records if r["median_match"] is flag]
        print("  %-34s n=%2d  preseason playoff Brier=%.4f  climatology=%.4f  wk3=%.4f"
              % (label, len(sub),
                 backtest.brier([(r["p_playoff"], r["y_playoff"]) for r in sub]),
                 backtest.brier([(r["clim_playoff"], r["y_playoff"]) for r in sub]),
                 backtest.brier([(r["wk3_playoff"], r["y_playoff"]) for r in sub])))

    out = os.path.join(HYP_FIXTURES, "preseason-backtest-records.json")
    with open(out, "w") as f:
        json.dump(records, f, indent=1, sort_keys=True)
        f.write("\n")
    print("\n  per-team records -> %s" % out)


if __name__ == "__main__":
    main()
