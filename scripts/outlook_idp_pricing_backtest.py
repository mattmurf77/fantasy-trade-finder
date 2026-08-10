"""BUG-5 — how much does the unpriced IDP/K half of an IDP league's starting
lineup cost the preseason `roster_value` source, and does any available fix
recover it? Offline, #169.

THE DEFECT
----------
`RosterValueStrength` prices a team's starting lineup with the DynastyProcess
board, which carries QB/RB/WR/TE only (676 rows, zero IDP, zero K — verified
against the live file 2026-08-09). The FFv3 league — 4 of the 6 backtested
league-seasons — starts
`QB,RB,RB,WR,WR,TE,FLEX,K,DL,DL,LB,LB,DB,DB,IDP_FLEX`, so **8 of 15 starting
slots price at exactly 0.0**. Worse, `select_starting_lineup` matched the slot
name against the player's NFL `position` string, so a "DL" slot only accepted
a player whose position was literally "DL" — never a DE, DT or NT — and
`IDP_FLEX` matched nothing at all.

WHAT THIS SCRIPT MEASURES
-------------------------
Four pricings of the same rewound week-0 state (same rosters, same board,
same seed, same 10k sims), scored against the same reality:

  V0  status quo               shipped `RosterValueStrength`, pre-BUG-5 selection
  V1  eligibility fix only     BUG-5 slot eligibility; IDP slots now FILL
  V2  league-mean fallback     V1 + every unpriceable FILLED slot priced at the
                               league's mean priced-slot value
  V3  coverage attenuation     V1 + the z-score scaled by the priced share of
                               the starting lineup (linear and sqrt variants)

V1 is expected to be bit-identical to V0 on Brier: the newly-filled slots are
filled with players the board prices at 0.0, so `starting_lineup_value` is
unchanged. The script asserts that rather than assuming it.

Everything is reported SPLIT BY LEAGUE, because only FFv3 is affected —
Lakeview (`QB,RB,RB,WR,WR,WR,TE,FLEX,FLEX,SUPER_FLEX`) has full coverage and
must come out unchanged under every variant.

    python3 scripts/outlook_idp_pricing_backtest.py --sims 10000

Offline: DP boards from `backend/tests/fixtures/dp-values-history/`, Sleeper
responses from `backend/tests/fixtures/outlook-calibration/`, positions from
`backend/tests/fixtures/outlook-hypotheses/`. No network, no DB, no flag read.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.outlook_calibration_backtest as backtest  # noqa: E402
import scripts.outlook_preseason_backtest as preseason  # noqa: E402
from backend import dp_values_history as dvh  # noqa: E402
from backend.outlook import strength as st  # noqa: E402
from backend.outlook.pipeline import run_outlook  # noqa: E402

SEASONS = preseason.SEASONS
REGULAR_WEEKS = 14
OFFENSE = ("QB", "RB", "WR", "TE")


# ---------------------------------------------------------------------------
# The pre-BUG-5 selection, kept verbatim so V0 is the real status quo and not
# a reconstruction of it.
# ---------------------------------------------------------------------------

def legacy_select(player_ids, player_value, player_pos, roster_slots):
    if not roster_slots:
        return []
    by_pos: dict[str, list[tuple[float, str]]] = {}
    for pid in player_ids:
        pid = str(pid)
        by_pos.setdefault(player_pos.get(pid, "?"), []).append(
            (player_value.get(pid, 0.0), pid))
    for pairs in by_pos.values():
        pairs.sort(key=lambda pv: pv[0], reverse=True)
    selected = []
    for slot in [s for s in roster_slots if s not in st._FLEX_ELIGIBLE]:
        pool = by_pos.get(slot)
        if pool:
            selected.append(pool.pop(0)[1])
    for slot in [s for s in roster_slots if s in st._FLEX_ELIGIBLE]:
        best_pos, best_val = None, None
        for pos in st._FLEX_ELIGIBLE[slot]:
            pool = by_pos.get(pos)
            if pool and (best_val is None or pool[0][0] > best_val):
                best_pos, best_val = pos, pool[0][0]
        if best_pos is not None:
            selected.append(by_pos[best_pos].pop(0)[1])
    return selected


# ---------------------------------------------------------------------------
# Variant strength providers. All four share the shipped affine mapping; they
# differ only in how an unpriceable starting slot is treated.
# ---------------------------------------------------------------------------

class _Variant:
    """Shared plumbing: per-team lineup value -> z -> mu."""
    name = "?"
    select = staticmethod(st.select_starting_lineup)

    def lineup_values(self, state, ctx):
        return {
            t.roster_id: sum(
                ctx.player_value.get(pid, 0.0)
                for pid in self.select(t.player_ids, ctx.player_value,
                                       ctx.player_pos, state.roster_slots))
            for t in state.teams
        }

    def z_scale(self, state, ctx):
        return 1.0

    def estimate(self, state, ctx):
        mean_pts = st._knob(ctx.cfg, "outlook_mean_points")
        pts_per_sd = st._knob(ctx.cfg, "outlook_points_per_value_sd")
        sigma = st._knob(ctx.cfg, "outlook_sigma_default")
        values = self.lineup_values(state, ctx)
        vlist = list(values.values())
        mean_v = statistics.fmean(vlist) if vlist else 0.0
        sd_v = statistics.pstdev(vlist) if len(vlist) > 1 else 0.0
        scale = self.z_scale(state, ctx)
        out = {}
        for rid, v in values.items():
            z = (v - mean_v) / sd_v if sd_v > 0 else 0.0
            out[rid] = st.TeamStrength(rid, mu=mean_pts + pts_per_sd * z * scale,
                                       sigma=sigma)
        return out


class V0StatusQuo(_Variant):
    name = "V0 status quo"
    select = staticmethod(legacy_select)


class V1Eligibility(_Variant):
    name = "V1 eligibility fix"


class V2LeagueMean(_Variant):
    """Every unpriceable FILLED starting slot is priced at the league's mean
    priced-slot value, so a filled IDP slot contributes *something*."""
    name = "V2 league-mean fallback"

    def lineup_values(self, state, ctx):
        sel = {t.roster_id: self.select(t.player_ids, ctx.player_value,
                                        ctx.player_pos, state.roster_slots)
               for t in state.teams}
        priced_vals = [ctx.player_value.get(pid, 0.0)
                       for pids in sel.values() for pid in pids
                       if ctx.player_value.get(pid, 0.0) > 0]
        fill = statistics.fmean(priced_vals) if priced_vals else 0.0
        out = {}
        for rid, pids in sel.items():
            tot = 0.0
            for pid in pids:
                v = ctx.player_value.get(pid, 0.0)
                tot += v if v > 0 else fill
            out[rid] = tot
        return out


class V3Attenuated(_Variant):
    """z scaled by the priced share of the starting lineup."""

    def __init__(self, mode):
        self.mode = mode
        self.name = "V3 attenuation (%s)" % mode

    def z_scale(self, state, ctx):
        cov = st.lineup_pricing(state.roster_slots, ctx.player_value,
                                ctx.player_pos).coverage
        if self.mode == "linear":
            return cov
        if self.mode == "sqrt":
            return cov ** 0.5
        raise ValueError(self.mode)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def cluster_bootstrap_delta(records, a, b, key, leagues=None,
                            iters=4000, seed=20260809):
    """90 % CI on the paired Brier delta (a - b). Negative = `a` better."""
    rng = random.Random(seed)
    by_league = defaultdict(list)
    for r in records:
        if leagues is None or r["league"] in leagues:
            by_league[r["league"]].append(r)
    names = list(by_league)

    def delta(sample):
        rows = [r for lg in sample for r in by_league[lg]]
        return (backtest.brier([(r[a][key], r["y_" + key]) for r in rows])
                - backtest.brier([(r[b][key], r["y_" + key]) for r in rows]))

    draws = sorted(delta([rng.choice(names) for _ in names]) for _ in range(iters))
    return (delta(names), draws[int(0.05 * len(draws))],
            draws[int(0.95 * len(draws))])


def skill(records, variant, key, leagues=None):
    rows = [r for r in records if leagues is None or r["league"] in leagues]
    m = backtest.brier([(r[variant][key], r["y_" + key]) for r in rows])
    c = backtest.brier([(r["clim"][key], r["y_" + key]) for r in rows])
    return m, (1 - m / c if c else float("nan"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=10000)
    args = ap.parse_args()

    variants = [V0StatusQuo(), V1Eligibility(), V2LeagueMean(),
                V3Attenuated("sqrt"), V3Attenuated("linear")]

    pos_meta = preseason.player_positions()
    player_pos = {pid: (m.get("position") or "?") for pid, m in pos_meta.items()}
    extra_idx = preseason.roster_name_index(pos_meta)

    records = []
    idp_leagues, off_leagues = set(), set()

    print("\n## 1. Unpriced starting-slot fraction per league-season\n")
    print("| league-season | starting slots | priceable | unpriceable | "
          "**unpriced slot share** | unpriceable slots |")
    print("|---|---|---|---|---|---|")

    lineup_val = {}
    for name, season in SEASONS.items():
        fx = backtest.load_fixture(name)
        full = backtest.build_full_state(fx)
        field, champ = backtest.truth(fx, full.playoff_slots)
        scoring = preseason.scoring_format_for(fx)
        values, _rep, _meta = dvh.values_as_of(
            dvh.week_boundary(season, 0), scoring=scoring,
            extra_name_pos=extra_idx)

        st0 = backtest.as_of(full, 0)
        gaps = preseason.rewind_rosters(st0, fx)
        assert not gaps, (name, gaps)
        assert st0.completed_weeks == 0

        lp = st.lineup_pricing(st0.roster_slots, values, player_pos)
        (idp_leagues if lp.coverage < 1.0 else off_leagues).add(name)
        print("| %s | %d | %d | %d | **%.1f %%** | %s |"
              % (name, lp.total_slots, lp.priceable_slots,
                 lp.total_slots - lp.priceable_slots,
                 100 * (1 - lp.coverage),
                 ", ".join(lp.unpriceable_slots) or "—"))

        ctx = st.StrengthContext(player_value=values, player_pos=player_pos,
                                 cfg={})
        payloads = {}
        for v in variants:
            lineup_val[(name, v.name)] = v.lineup_values(st0, ctx)
            strengths = v.estimate(st0, ctx)
            payloads[v.name] = _run(st0, strengths, args.sims)

        final = backtest.as_of(full, REGULAR_WEEKS)
        wins = {t.roster_id: t.win_credit for t in final.teams}
        n = len(full.teams)
        for t in full.teams:
            rid = t.roster_id
            rec = {"league": name, "season": season, "roster_id": rid,
                   "median_match": backtest.median_mode(fx),
                   "y_playoff": 1.0 if rid in field else 0.0,
                   "y_title": 1.0 if rid == champ else 0.0,
                   "actual_wins": wins[rid],
                   "clim": {"playoff": full.playoff_slots / n, "title": 1.0 / n}}
            for v in variants:
                odds = {x["roster_id"]: x["odds"] for x in payloads[v.name]["teams"]}
                rec[v.name] = {"playoff": odds[rid]["playoff_pct"],
                               "title": odds[rid]["title_pct"],
                               "mu": odds[rid]["projected_wins"]}
            records.append(rec)

    # ---- V1 must not move a single number -----------------------------------
    same = all(abs(lineup_val[(n, "V0 status quo")][rid]
                   - lineup_val[(n, "V1 eligibility fix")][rid]) < 1e-9
               for n in SEASONS for rid in lineup_val[(n, "V0 status quo")])
    assert same, "eligibility fix changed a starting-lineup VALUE — investigate"
    moved = [r for r in records
             if abs(r["V0 status quo"]["playoff"] - r["V1 eligibility fix"]["playoff"]) > 1e-12]
    print("\n  eligibility fix (V1 vs V0): starting-lineup values identical for "
          "all %d team-seasons; %d/%d playoff odds differ"
          % (len(records), len(moved), len(records)))

    print("\n## 2. Brier by variant, SPLIT BY LEAGUE\n")
    splits = [("all 6 league-seasons", None),
              ("FFv3 — IDP, 4 seasons", idp_leagues),
              ("Lakeview — no IDP, 2 seasons", off_leagues)]
    for label, lg in splits:
        rows = [r for r in records if lg is None or r["league"] in lg]
        print("\n**%s** (n = %d team-seasons)\n" % (label, len(rows)))
        print("| variant | playoff Brier | skill vs clim | title Brier | "
              "Δ playoff vs V0 | 90 % CI | reading |")
        print("|---|---|---|---|---|---|---|")
        for v in variants:
            b, sk = skill(records, v.name, "playoff", lg)
            bt, _ = skill(records, v.name, "title", lg)
            if v.name == "V0 status quo":
                print("| %s | %.4f | %+.1f %% | %.4f | — | — | baseline |"
                      % (v.name, b, 100 * sk, bt))
                continue
            d, lo, hi = cluster_bootstrap_delta(records, v.name,
                                                "V0 status quo", "playoff", lg)
            read = ("BETTER" if hi < 0 else "WORSE" if lo > 0
                    else "indistinguishable")
            print("| %s | %.4f | %+.1f %% | %.4f | %+.4f | [%+.4f, %+.4f] | %s |"
                  % (v.name, b, 100 * sk, bt, d, lo, hi, read))

    print("\n## 3. Per-league-season playoff Brier\n")
    print("| league-season | " + " | ".join(v.name for v in variants)
          + " | climatology |")
    print("|---" * (len(variants) + 2) + "|")
    for name in SEASONS:
        rows = [r for r in records if r["league"] == name]
        cells = ["%.4f" % backtest.brier([(r[v.name]["playoff"], r["y_playoff"])
                                          for r in rows]) for v in variants]
        clim = backtest.brier([(r["clim"]["playoff"], r["y_playoff"]) for r in rows])
        print("| %s | %s | %.4f |" % (name, " | ".join(cells), clim))

    print("\n## 4. Ordering skill — Spearman(projected wins, actual wins)\n")
    print("| league-season | " + " | ".join(v.name for v in variants) + " |")
    print("|---" * (len(variants) + 1) + "|")
    for name in SEASONS:
        rows = [r for r in records if r["league"] == name]
        w = [r["actual_wins"] for r in rows]
        cells = ["%+.3f" % preseason.spearman([r[v.name]["mu"] for r in rows], w)
                 for v in variants]
        print("| %s | %s |" % (name, " | ".join(cells)))

    out = os.path.join(preseason.HYP_FIXTURES, "idp-pricing-backtest-records.json")
    with open(out, "w") as f:
        json.dump(records, f, indent=1, sort_keys=True)
        f.write("\n")
    print("\n  per-team records -> %s" % out)


def _run(state, strengths, n_sims):
    """Run phases 3-5 with a pre-computed strength map, through the SAME
    pipeline the product uses (a one-shot provider registered under a scratch
    key, so nothing about the simulator/serializer differs between variants)."""
    key = "_idp_variant"
    st.STRENGTH_PROVIDERS[key] = lambda: _Fixed(strengths)
    try:
        return run_outlook(state, player_value={}, player_pos={}, model_cfg={},
                           basis="consensus", source_override=key, n_sims=n_sims)
    finally:
        st.STRENGTH_PROVIDERS.pop(key, None)


class _Fixed:
    name = "_idp_variant"

    def __init__(self, strengths):
        self._s = strengths

    def estimate(self, state, ctx):
        return self._s


if __name__ == "__main__":
    main()
