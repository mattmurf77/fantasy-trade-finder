"""Tier-2 diagnostic: roster-value prior vs Sleeper projections as the
outlook engine's strength source, on the operator's CURRENT 2026 leagues.

SCRIPT-ONLY, DIAGNOSTIC, NEVER SHIPPED. The projections source implemented
here deliberately lives outside backend/outlook/ — `SleeperProjectionsStrength`
stays a registered stub until someone decides to take on the unofficial-endpoint
dependency. This script exists to answer one question: do the two sources
disagree enough to worry about?

    python3 scripts/outlook_strength_source_compare.py

Reads only committed fixtures (backend/tests/fixtures/outlook-calibration/):
  * lakeview-2026.json / ffv3-2026.json  — league, rosters, users, schedule
  * sleeper-projections-2026.json        — weekly pts_ppr per rostered player

Player VALUES for the roster-value side come from FTF's own universal pool
(the same machinery /api/league/outlook uses), which needs the Sleeper player
cache; pass --players-cache if it is not at the default repo path.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.outlook.league_state import SleeperLeagueState  # noqa: E402
from backend.outlook.playoff_format import StandardFormat  # noqa: E402
from backend.outlook.simulator import simulate  # noqa: E402
from backend.outlook.strength import (  # noqa: E402
    RosterValueStrength, StrengthContext, TeamStrength, starting_lineup_value,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(REPO, "backend", "tests", "fixtures", "outlook-calibration")

# league fixture -> FTF scoring format (Lakeview is SF/TEP; FFv3 is 1QB + IDP)
LEAGUES = [("lakeview-2026", "sf_tep"), ("ffv3-2026", "1qb_ppr")]
SIGMA_DEFAULT = 25.0


# ---------------------------------------------------------------------------
# The script-only projections strength source
# ---------------------------------------------------------------------------

class SleeperProjectionsStrengthScript:
    """mu = projected weekly points of the best legal starting lineup.

    No affine calibration is needed (unlike RosterValueStrength): a projection
    feed is already denominated in fantasy points, so the lineup sum IS mu.
    sigma stays the league-default heuristic — the endpoint gives a mean, not
    a spread."""

    name = "sleeper_projections_script"

    def __init__(self, weekly: dict, sigma: float = SIGMA_DEFAULT):
        # player_id -> mean projected weekly pts_ppr across the regular season
        acc: dict[str, list[float]] = {}
        for _wk, players in weekly.items():
            for pid, row in players.items():
                acc.setdefault(pid, []).append(float(row["pts_ppr"]))
        self.mean_pts = {pid: statistics.fmean(v) for pid, v in acc.items()}
        self.pos = {}
        for _wk, players in weekly.items():
            for pid, row in players.items():
                if row.get("pos"):
                    self.pos[pid] = row["pos"]
        self.sigma = sigma

    def estimate(self, state, ctx):
        out = {}
        for t in state.teams:
            mu = starting_lineup_value(t.player_ids, self.mean_pts,
                                       self.pos, state.roster_slots)
            out[t.roster_id] = TeamStrength(t.roster_id, mu, self.sigma)
        return out

    def coverage(self, state):
        have = tot = 0
        for t in state.teams:
            for pid in t.player_ids:
                tot += 1
                have += 1 if str(pid) in self.mean_pts else 0
        return have, tot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load(name):
    with open(os.path.join(FIXTURES, name + ".json")) as f:
        return json.load(f)


def offline_fetch(fx):
    lid, base = fx["league_id"], "https://api.sleeper.app/v1/"
    table = {base + "league/%s" % lid: fx["league"],
             base + "league/%s/rosters" % lid: fx["rosters"],
             base + "league/%s/users" % lid: fx["users"]}
    for wk, rows in (fx.get("matchups") or {}).items():
        table[base + "league/%s/matchups/%s" % (lid, wk)] = rows
    return lambda url: table.get(url, [] if "/matchups/" in url else None)


def spearman(a: list[float], b: list[float]) -> float:
    def rank(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")


def ftf_values(scoring_format, players_cache):
    """FTF consensus player values + positions, via the shipped pool."""
    from pathlib import Path
    import backend.server as server
    if players_cache:
        server.PLAYERS_CACHE_FILE = Path(players_cache)
        server._sleeper_cache = None
        server.g_universal_by_format.clear()
    pool, seed = server._get_universal_pool(scoring_format)
    e2v = server._trade_service_mod.elo_to_value
    value = {pid: e2v(elo) for pid, elo in seed.items()}
    pos = {p.id: (getattr(p, "position", None) or "?") for p in pool}
    return value, pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=10000)
    ap.add_argument("--players-cache", default=os.path.join(
        REPO, "data", ".sleeper_players_cache.json"),
        help="Sleeper player cache (a git worktree usually has none — point "
             "this at the main checkout's data/.sleeper_players_cache.json)")
    args = ap.parse_args()

    proj_doc = load("sleeper-projections-2026")
    proj = SleeperProjectionsStrengthScript(proj_doc["weeks"])
    print("projections fixture: season %s, %d weeks, %d players"
          % (proj_doc["season"], len(proj_doc["weeks"]), len(proj.mean_pts)))

    for name, fmt_key in LEAGUES:
        fx = load(name)
        state = SleeperLeagueState(fetch=offline_fetch(fx)).load(fx["league_id"])
        print("\n" + "=" * 78)
        print("%s  (%s)  teams=%d  slots=%d  completed_weeks=%d  "
              "schedule_weeks=%d" % (name, fmt_key, len(state.teams),
                                     state.playoff_slots, state.completed_weeks,
                                     len(state.schedule)))
        if not state.schedule:
            print("  NOTE: no pairings published (league is pre-draft) — the "
                  "simulator falls back to random re-pairing each week.")
        have, tot = proj.coverage(state)
        print("  projection coverage: %d/%d rostered players (%.0f%%)"
              % (have, tot, 100.0 * have / tot if tot else 0))

        value, pos = ftf_values(fmt_key, args.players_cache)
        ctx = StrengthContext(player_value=value, player_pos=pos, cfg={})
        s_val = RosterValueStrength().estimate(state, ctx)
        s_prj = proj.estimate(state, ctx)

        fmt = StandardFormat(state.playoff_slots, state.num_byes,
                             state.num_divisions)
        r_val = simulate(state, s_val, fmt, n_sims=args.sims, config_seed=0)
        r_prj = simulate(state, s_prj, fmt, n_sims=args.sims, config_seed=0)

        rows = []
        for t in state.teams:
            rid = t.roster_id
            rows.append((rid, t.display_name[:18],
                         s_val[rid].mu, s_prj[rid].mu,
                         r_val.playoff_pct(rid), r_prj.playoff_pct(rid),
                         r_val.title_pct(rid), r_prj.title_pct(rid)))
        rows.sort(key=lambda r: -r[4])

        print("\n| roster | team | mu(value) | mu(proj) | playoff value | "
              "playoff proj | delta | title value | title proj |")
        print("|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            print("| %d | %s | %.1f | %.1f | %.3f | %.3f | %+.3f | %.3f | %.3f |"
                  % (r[0], r[1], r[2], r[3], r[4], r[5], r[5] - r[4], r[6], r[7]))

        dp = [abs(r[5] - r[4]) for r in rows]
        dt = [abs(r[7] - r[6]) for r in rows]
        print("\n  playoff-odds delta: mean %.3f  max %.3f" % (sum(dp) / len(dp), max(dp)))
        print("  title-odds   delta: mean %.3f  max %.3f" % (sum(dt) / len(dt), max(dt)))
        print("  Spearman(mu value, mu proj)          = %+.3f"
              % spearman([r[2] for r in rows], [r[3] for r in rows]))
        print("  Spearman(playoff value, playoff proj)= %+.3f"
              % spearman([r[4] for r in rows], [r[5] for r in rows]))
        top6_v = {r[0] for r in sorted(rows, key=lambda r: -r[4])[:state.playoff_slots]}
        top6_p = {r[0] for r in sorted(rows, key=lambda r: -r[5])[:state.playoff_slots]}
        print("  projected playoff field overlap: %d/%d"
              % (len(top6_v & top6_p), state.playoff_slots))


if __name__ == "__main__":
    main()
