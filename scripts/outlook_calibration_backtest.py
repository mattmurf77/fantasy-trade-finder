"""Offline as-of backtest for the #169 outlook odds engine.

Runs the SHIPPED pipeline (backend/outlook/) against captured past seasons of
the operator's real Sleeper leagues and scores its playoff / title predictions
against what actually happened.

Repeatable offline: every Sleeper response it needs is committed under
backend/tests/fixtures/outlook-calibration/ (captured 2026-08-09, public
read-only API). This script NEVER touches the network.

    python3 scripts/outlook_calibration_backtest.py            # full run
    python3 scripts/outlook_calibration_backtest.py --sims 2000

AS-OF SEMANTICS (the load-bearing part)
---------------------------------------
Phase 1 (`SleeperLeagueState.load`) reads *current* standings off
`/rosters`, which for a completed season are FINAL — running it unmodified on
a past season leaks the answer and leaves nothing to simulate. So this harness
loads the real full-season state through the shipped provider and then rewinds
it to week W with `as_of()`, which:
  * recomputes wins / losses / ties / points_for from weeks 1..W ONLY,
  * truncates weekly_scores to weeks 1..W,
  * sets completed_weeks = W.
Everything else the simulator reads (the pairing schedule, playoff_slots,
regular_season_weeks) is genuinely known before the season starts — the
schedule assumption is validated in `check_future_pairings()` below.

Team `player_ids` are NOT rewound (Sleeper does not expose historical rosters),
which is exactly why this backtest only scores the `trailing_scores` source.
See the calibration report for the consequence.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.outlook.league_state import SleeperLeagueState  # noqa: E402
from backend.outlook.pipeline import run_outlook  # noqa: E402

FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backend", "tests", "fixtures", "outlook-calibration",
)
PAST_SEASONS = [
    "lakeview-2025", "lakeview-2024",
    "ffv3-2025", "ffv3-2024", "ffv3-2023", "ffv3-2022",
]
AS_OF_WEEKS = [3, 6, 9, 12]


# ---------------------------------------------------------------------------
# Fixture plumbing — an offline stand-in for server._sleeper_get
# ---------------------------------------------------------------------------

def load_fixture(name: str) -> dict:
    with open(os.path.join(FIXTURES, "%s.json" % name)) as f:
        return json.load(f)


def offline_fetch(fx: dict):
    """Return a `fetch(url)` callable serving the captured responses."""
    lid = fx["league_id"]
    base = "https://api.sleeper.app/v1/"
    table = {
        base + "league/%s" % lid: fx["league"],
        base + "league/%s/rosters" % lid: fx["rosters"],
        base + "league/%s/users" % lid: fx["users"],
    }
    for wk, rows in (fx.get("matchups") or {}).items():
        table[base + "league/%s/matchups/%s" % (lid, wk)] = rows

    def fetch(url):
        if url not in table:
            # A week we never captured -> the real API would return [] too.
            if "/matchups/" in url:
                return []
            raise AssertionError("backtest tried to fetch un-captured %s" % url)
        return table[url]

    return fetch


def build_full_state(fx: dict):
    """Full-season LeagueState via the SHIPPED Phase-1 provider."""
    provider = SleeperLeagueState(fetch=offline_fetch(fx))
    return provider.load(fx["league_id"])


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------

def truth(fx: dict, playoff_slots: int):
    """(playoff_field:set[int], champion:int) from Sleeper's winners bracket.

    The winners bracket is authoritative — it encodes the league's real
    seeding/tiebreak outcome rather than us re-deriving it."""
    wb = fx.get("winners_bracket") or []
    field, champ = set(), None
    for m in wb:
        for key in ("t1", "t2"):
            v = m.get(key)
            if isinstance(v, int):
                field.add(v)
        if m.get("p") == 1 and isinstance(m.get("w"), int):
            champ = m["w"]
    assert len(field) == playoff_slots, (
        "bracket field %d != playoff_slots %d" % (len(field), playoff_slots))
    assert champ is not None, "no championship match (p==1) in bracket"
    return field, champ


# ---------------------------------------------------------------------------
# As-of rewind
# ---------------------------------------------------------------------------

def as_of(state, week: int):
    """Rewind a completed-season LeagueState to the end of `week`.

    Mutates a deep-ish copy: standings recomputed from weeks 1..week only."""
    import copy
    st = copy.deepcopy(state)
    by_rid = {t.roster_id: t for t in st.teams}
    for t in st.teams:
        t.wins = t.losses = t.ties = 0
        t.points_for = 0.0
        t.points_against = 0.0

    # weekly_scores[rid] is week-ordered for completed weeks -> index w-1
    scores = state.weekly_scores
    for w in range(1, week + 1):
        for a, b in state.schedule.get(w, []):
            sa = scores.get(a, [])[w - 1] if len(scores.get(a, [])) >= w else 0.0
            sb = scores.get(b, [])[w - 1] if len(scores.get(b, [])) >= w else 0.0
            by_rid[a].points_for += sa
            by_rid[b].points_for += sb
            by_rid[a].points_against += sb
            by_rid[b].points_against += sa
            if sa > sb:
                by_rid[a].wins += 1
                by_rid[b].losses += 1
            elif sb > sa:
                by_rid[b].wins += 1
                by_rid[a].losses += 1
            else:
                by_rid[a].ties += 1
                by_rid[b].ties += 1
    for t in st.teams:
        t.points_for = round(t.points_for, 2)
        t.points_against = round(t.points_against, 2)
    st.weekly_scores = {rid: list(v[:week]) for rid, v in scores.items()}
    st.completed_weeks = week
    return st


def median_mode(fx: dict) -> bool:
    """True when the league runs Sleeper's 'median match' (league_average_match)
    — every team plays its H2H opponent AND the league median each week, so a
    14-week season books 28 W/L decisions, not 14."""
    return bool(((fx.get("league") or {}).get("settings") or {})
                .get("league_average_match"))


def as_of_shipped_ingestion(state, week: int, median: bool):
    """What the SHIPPED Phase-1 provider would hand the simulator at week W.

    `SleeperLeagueState` copies wins/losses/ties straight off /rosters. In a
    median-match league those counters are on a 2-decisions-per-week scale
    while `simulate()` only ever adds 1 win per remaining week — the scale
    mismatch this variant reproduces (see BUG-1 in the calibration report)."""
    import copy
    st = copy.deepcopy(as_of(state, week))
    if not median:
        return st
    by_rid = {t.roster_id: t for t in st.teams}
    scores = state.weekly_scores
    for w in range(1, week + 1):
        vals = sorted(scores.get(t.roster_id, [0.0] * w)[w - 1]
                      for t in state.teams)
        n = len(vals)
        med = (vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0)
        for t in state.teams:
            s = scores.get(t.roster_id, [])
            v = s[w - 1] if len(s) >= w else 0.0
            if v > med:
                by_rid[t.roster_id].wins += 1
            elif v < med:
                by_rid[t.roster_id].losses += 1
            else:
                by_rid[t.roster_id].ties += 1
    return st


def strip_future_schedule(state, week: int):
    """Diagnostic variant: drop pairings for unplayed weeks, forcing the
    simulator's random-re-pairing fallback (what happens on a platform that
    doesn't publish future matchups)."""
    import copy
    st = copy.deepcopy(state)
    st.schedule = {w: p for w, p in st.schedule.items() if w <= week}
    return st


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

def baselines(state, playoff_slots: int):
    """B1 climatology, B2 hard standings-extrapolation, B3 shrunk standings."""
    n = len(state.teams)
    b1_p, b1_t = playoff_slots / n, 1.0 / n
    order = sorted(state.teams,
                   key=lambda t: (-t.win_credit, -t.points_for, t.roster_id))
    b2_p, b2_t = {}, {}
    for i, t in enumerate(order):
        b2_p[t.roster_id] = 1.0 if i < playoff_slots else 0.0
        b2_t[t.roster_id] = 1.0 if i == 0 else 0.0
    out = {}
    for t in state.teams:
        rid = t.roster_id
        out[rid] = {
            "B1_climatology": (b1_p, b1_t),
            "B2_standings_hard": (b2_p[rid], b2_t[rid]),
            "B3_standings_shrunk": (0.5 * b2_p[rid] + 0.5 * b1_p,
                                    0.5 * b2_t[rid] + 0.5 * b1_t),
        }
    return out


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def brier(pairs):
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs) if pairs else float("nan")


def logloss(pairs, eps=1e-6):
    if not pairs:
        return float("nan")
    tot = 0.0
    for p, y in pairs:
        p = min(max(p, eps), 1 - eps)
        tot += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return tot / len(pairs)


def calibration_table(pairs, bins=10):
    rows = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        sel = [(p, y) for p, y in pairs
               if (p >= lo and p < hi) or (i == bins - 1 and p == 1.0)]
        if not sel:
            rows.append((lo, hi, 0, None, None))
            continue
        rows.append((lo, hi, len(sel),
                     sum(p for p, _ in sel) / len(sel),
                     sum(y for _, y in sel) / len(sel)))
    return rows


def fmt_cal(rows):
    out = ["| bucket | n | mean predicted | realized | gap |",
           "|---|---|---|---|---|"]
    for lo, hi, n, mp, rf in rows:
        if not n:
            out.append("| %.1f–%.1f | 0 | — | — | — |" % (lo, hi))
        else:
            out.append("| %.1f–%.1f | %d | %.3f | %.3f | %+.3f |"
                       % (lo, hi, n, mp, rf, rf - mp))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Future-pairing validation (resolves the LLD's flagged assumption)
# ---------------------------------------------------------------------------

def check_future_pairings():
    print("\n## Future-pairing availability (Sleeper)\n")
    for name in ["lakeview-2026", "ffv3-2026"]:
        fx = load_fixture(name)
        mm = fx.get("matchups") or {}
        status = (fx["league"] or {}).get("status")
        weeks = sorted(int(w) for w in mm)
        paired = [w for w in weeks
                  if len({r.get("matchup_id") for r in mm[str(w)]
                          if r.get("matchup_id") is not None}) > 0]
        scored = [w for w in weeks
                  if any(r.get("points") for r in mm[str(w)])]
        print("  %-14s status=%-10s weeks_returned=%d weeks_with_pairings=%d "
              "weeks_with_points=%d" % (name, status, len(weeks),
                                        len(paired), len(scored)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def scoring_distribution_summary():
    """Empirical check on the three flagged calibration knobs.

    `outlook_sigma_default` should match the WITHIN-team week-to-week scoring
    SD. `outlook_points_per_value_sd` should match the BETWEEN-team SD of true
    weekly scoring level. The naive between-team SD of observed season means is
    inflated by sampling noise, so we subtract it:
        var(true) = var(observed means) - sigma^2 / weeks
    """
    print("\n## Empirical scoring distribution (calibration evidence)\n")
    print("| league-season | league mean pts | within-team sigma | "
          "between-team SD (raw) | between-team SD (noise-corrected) |")
    print("|---|---|---|---|---|")
    sigmas, spreads, means = [], [], []
    for name in PAST_SEASONS:
        fx = load_fixture(name)
        st = build_full_state(fx)
        per_team = [v for v in st.weekly_scores.values() if len(v) >= 2]
        if not per_team:
            continue
        wk = min(len(v) for v in per_team)
        team_means = [sum(v) / len(v) for v in per_team]
        within = [_pstdev(v) for v in per_team]
        sigma = sum(within) / len(within)
        raw = _pstdev(team_means)
        corr2 = raw ** 2 - (sigma ** 2) / wk
        corr = corr2 ** 0.5 if corr2 > 0 else 0.0
        lm = sum(team_means) / len(team_means)
        sigmas.append(sigma)
        spreads.append(corr)
        means.append(lm)
        print("| %s | %.1f | %.1f | %.1f | %.1f |" % (name, lm, sigma, raw, corr))
    print("| **pooled mean** | **%.1f** | **%.1f** | — | **%.1f** |"
          % (sum(means) / len(means), sum(sigmas) / len(sigmas),
             sum(spreads) / len(spreads)))
    print("\n  shipped defaults: outlook_mean_points=110, "
          "outlook_sigma_default=25, outlook_points_per_value_sd=12")


def bootstrap_skill(records, n_leagues, iters=4000, seed=20260809):
    """Cluster bootstrap over LEAGUE-SEASONS — the only defensible resampling
    unit here, because the 12 team-seasons inside one league are mechanically
    dependent (exactly `playoff_slots` of them make the playoffs, exactly one
    wins). Six clusters is a very small bootstrap; the interval it produces is
    honest about that, and should be read as 'wide', not 'precise'."""
    import random as _r
    rng = _r.Random(seed)
    by_league = defaultdict(list)
    for lg, _wk, pp, yp, pt, yt in records:
        by_league[lg].append((pp, yp, pt, yt))
    leagues = list(by_league)

    def skill(sample_leagues):
        pp = [(r[0], r[1]) for lg in sample_leagues for r in by_league[lg]]
        pt = [(r[2], r[3]) for lg in sample_leagues for r in by_league[lg]]
        clim_p = 6.0 / 12
        clim_t = 1.0 / 12
        bp = brier(pp)
        bt = brier(pt)
        cp = brier([(clim_p, y) for _p, y in pp])
        ct = brier([(clim_t, y) for _p, y in pt])
        return (1 - bp / cp if cp else float("nan"),
                1 - bt / ct if ct else float("nan"))

    ps, ts = [], []
    for _ in range(iters):
        draw = [rng.choice(leagues) for _ in leagues]
        a, b = skill(draw)
        ps.append(a)
        ts.append(b)
    ps.sort()
    ts.sort()

    def ci(v):
        return v[int(0.05 * len(v))], v[int(0.95 * len(v))]

    pt_obs, tt_obs = skill(leagues)
    lo_p, hi_p = ci(ps)
    lo_t, hi_t = ci(ts)
    print("\n## Cluster bootstrap over %d league-seasons (90%% interval)\n" % n_leagues)
    print("  playoff skill vs climatology: %+.1f%%   90%% CI [%+.1f%%, %+.1f%%]  "
          "-> %s" % (100 * pt_obs, 100 * lo_p, 100 * hi_p,
                     "excludes 0" if lo_p > 0 else "INCLUDES 0"))
    print("  title   skill vs climatology: %+.1f%%   90%% CI [%+.1f%%, %+.1f%%]  "
          "-> %s" % (100 * tt_obs, 100 * lo_t, 100 * hi_t,
                     "excludes 0" if lo_t > 0 else "INCLUDES 0"))


def _pstdev(xs):
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=10000)
    args = ap.parse_args()

    check_future_pairings()
    scoring_distribution_summary()

    # accumulators: key -> list[(p, y)]
    model_p, model_t = defaultdict(list), defaultdict(list)
    base_p = defaultdict(lambda: defaultdict(list))
    base_t = defaultdict(lambda: defaultdict(list))
    nosched_p, nosched_t = defaultdict(list), defaultdict(list)
    shipped_p, shipped_t = defaultdict(list), defaultdict(list)
    clean_med_p, clean_med_t = defaultdict(list), defaultdict(list)
    per_league_rows = []
    sources_used = set()
    median_leagues = []
    # (league, week, p_playoff, y_playoff, p_title, y_title) for the bootstrap
    records: list[tuple] = []

    print("\n## Per-league / per-week runs\n")
    for name in PAST_SEASONS:
        fx = load_fixture(name)
        full = build_full_state(fx)
        field, champ = truth(fx, full.playoff_slots)
        med = median_mode(fx)
        if med:
            median_leagues.append(name)
        print("  %s: teams=%d reg_weeks=%d slots=%d byes=%d completed=%d "
              "median_match=%s champ=%s field=%s"
              % (name, len(full.teams), full.regular_season_weeks,
                 full.playoff_slots, full.num_byes, full.completed_weeks,
                 med, champ, sorted(field)))
        for wk in AS_OF_WEEKS:
            st = as_of(full, wk)
            payload = run_outlook(
                st, player_value={}, player_pos={}, model_cfg={},
                basis="consensus", source_override="auto", n_sims=args.sims)
            sources_used.add(payload["meta"]["strength_source"])
            bl = baselines(st, full.playoff_slots)
            for team in payload["teams"]:
                rid = team["roster_id"]
                y_p = 1.0 if rid in field else 0.0
                y_t = 1.0 if rid == champ else 0.0
                model_p[wk].append((team["odds"]["playoff_pct"], y_p))
                model_t[wk].append((team["odds"]["title_pct"], y_t))
                for bname, (bp, bt) in bl[rid].items():
                    base_p[wk][bname].append((bp, y_p))
                    base_t[wk][bname].append((bt, y_t))
                records.append((name, wk, team["odds"]["playoff_pct"], y_p,
                                team["odds"]["title_pct"], y_t))

            # diagnostic: no future schedule -> random re-pairing fallback
            st2 = strip_future_schedule(st, wk)
            pay2 = run_outlook(
                st2, player_value={}, player_pos={}, model_cfg={},
                basis="consensus", source_override="auto", n_sims=args.sims)
            for team in pay2["teams"]:
                rid = team["roster_id"]
                nosched_p[wk].append(
                    (team["odds"]["playoff_pct"], 1.0 if rid in field else 0.0))
                nosched_t[wk].append(
                    (team["odds"]["title_pct"], 1.0 if rid == champ else 0.0))

            # BUG-1 quantification: what the SHIPPED Phase-1 ingestion feeds in
            st3 = as_of_shipped_ingestion(full, wk, med)
            pay3 = run_outlook(
                st3, player_value={}, player_pos={}, model_cfg={},
                basis="consensus", source_override="auto", n_sims=args.sims)
            for team in pay3["teams"]:
                rid = team["roster_id"]
                y_p = 1.0 if rid in field else 0.0
                y_t = 1.0 if rid == champ else 0.0
                shipped_p[wk].append((team["odds"]["playoff_pct"], y_p))
                shipped_t[wk].append((team["odds"]["title_pct"], y_t))
                if med:
                    clean_med_p[wk].append(
                        (dict((t["roster_id"], t["odds"]["playoff_pct"])
                              for t in payload["teams"])[rid], y_p))
                    clean_med_t[wk].append(
                        (dict((t["roster_id"], t["odds"]["title_pct"])
                              for t in payload["teams"])[rid], y_t))

            per_league_rows.append((name, wk,
                                    brier(model_p[wk][-len(payload["teams"]):]),
                                    brier(model_t[wk][-len(payload["teams"]):])))

    print("\n  strength sources resolved by `auto`: %s" % sorted(sources_used))

    all_mp = [x for wk in AS_OF_WEEKS for x in model_p[wk]]
    all_mt = [x for wk in AS_OF_WEEKS for x in model_t[wk]]
    all_np = [x for wk in AS_OF_WEEKS for x in nosched_p[wk]]
    all_nt = [x for wk in AS_OF_WEEKS for x in nosched_t[wk]]

    print("\n## Headline (all as-of weeks pooled)\n")
    print("  team-week predictions : %d" % len(all_mp))
    print("  independent team-seasons: %d   champion events: %d"
          % (len(all_mp) // len(AS_OF_WEEKS), len(PAST_SEASONS)))
    print("  PLAYOFF  Brier model=%.4f  logloss=%.4f" % (brier(all_mp), logloss(all_mp)))
    print("  TITLE    Brier model=%.4f  logloss=%.4f" % (brier(all_mt), logloss(all_mt)))
    for bname in ["B1_climatology", "B2_standings_hard", "B3_standings_shrunk"]:
        bp = [x for wk in AS_OF_WEEKS for x in base_p[wk][bname]]
        bt = [x for wk in AS_OF_WEEKS for x in base_t[wk][bname]]
        print("  %-22s playoff Brier=%.4f (skill %+.1f%%)  title Brier=%.4f (skill %+.1f%%)"
              % (bname, brier(bp), 100 * (1 - brier(all_mp) / brier(bp)),
                 brier(bt), 100 * (1 - brier(all_mt) / brier(bt))))
    print("  no-future-schedule variant: playoff Brier=%.4f  title Brier=%.4f"
          % (brier(all_np), brier(all_nt)))

    print("\n## BUG-1 — shipped Phase-1 ingestion vs clean as-of standings\n")
    print("  median-match leagues in sample: %s" % (median_leagues or "none"))
    all_sp = [x for wk in AS_OF_WEEKS for x in shipped_p[wk]]
    all_st_ = [x for wk in AS_OF_WEEKS for x in shipped_t[wk]]
    print("  ALL leagues   clean playoff Brier=%.4f -> shipped %.4f  (%+.1f%%)"
          % (brier(all_mp), brier(all_sp),
             100 * (brier(all_sp) / brier(all_mp) - 1)))
    print("  ALL leagues   clean title   Brier=%.4f -> shipped %.4f  (%+.1f%%)"
          % (brier(all_mt), brier(all_st_),
             100 * (brier(all_st_) / brier(all_mt) - 1)))
    cm_p = [x for wk in AS_OF_WEEKS for x in clean_med_p[wk]]
    cm_t = [x for wk in AS_OF_WEEKS for x in clean_med_t[wk]]
    sm_p, sm_t = [], []
    for wk in AS_OF_WEEKS:
        # median-league slice of the shipped run, in the same order
        n_per = len(shipped_p[wk]) // len(PAST_SEASONS)
        for i, nm in enumerate(PAST_SEASONS):
            if nm in median_leagues:
                sm_p += shipped_p[wk][i * n_per:(i + 1) * n_per]
                sm_t += shipped_t[wk][i * n_per:(i + 1) * n_per]
    if cm_p:
        print("  MEDIAN-only   clean playoff Brier=%.4f -> shipped %.4f  (%+.1f%%)"
              % (brier(cm_p), brier(sm_p),
                 100 * (brier(sm_p) / brier(cm_p) - 1)))
        print("  MEDIAN-only   clean title   Brier=%.4f -> shipped %.4f  (%+.1f%%)"
              % (brier(cm_t), brier(sm_t),
                 100 * (brier(sm_t) / brier(cm_t) - 1)))
        print("  MEDIAN-only   shipped vs climatology playoff (0.2500): %s"
              % ("BEATS" if brier(sm_p) < 0.25 else "LOSES"))

    bootstrap_skill(records, len(PAST_SEASONS))

    print("\n## Per as-of week\n")
    print("| week | n | model playoff | B1 | B2 | B3 | model title | B1 t | B2 t | B3 t |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for wk in AS_OF_WEEKS:
        print("| %d | %d | %.4f | %.4f | %.4f | %.4f | %.4f | %.4f | %.4f | %.4f |" % (
            wk, len(model_p[wk]), brier(model_p[wk]),
            brier(base_p[wk]["B1_climatology"]),
            brier(base_p[wk]["B2_standings_hard"]),
            brier(base_p[wk]["B3_standings_shrunk"]),
            brier(model_t[wk]),
            brier(base_t[wk]["B1_climatology"]),
            brier(base_t[wk]["B2_standings_hard"]),
            brier(base_t[wk]["B3_standings_shrunk"])))

    print("\n## Calibration — playoff odds (all weeks pooled)\n")
    print(fmt_cal(calibration_table(all_mp)))
    print("\n## Calibration — title odds (all weeks pooled)\n")
    print(fmt_cal(calibration_table(all_mt)))

    print("\n## Per-league/week detail\n")
    print("| league-season | week | playoff Brier | title Brier |")
    print("|---|---|---|---|")
    for name, wk, bp, bt in per_league_rows:
        print("| %s | %d | %.4f | %.4f |" % (name, wk, bp, bt))


if __name__ == "__main__":
    main()
