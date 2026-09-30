"""Performance bounds for the value-core core (docs/plans/value-core-engine/specs.md section 5.1)."""
import math
import random
import time

from backend.value_core.core import MAX_CHECKS_PER_PARTNER, find_fair_trades
from backend.value_core.types import *   # in tests only

PERF_SLOTS = ("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "FLEX", "SUPER_FLEX")
ROSTER = ("QB",) * 3 + ("RB",) * 8 + ("WR",) * 10 + ("TE",) * 5 + ("PICK",) * 6


def A(id, pos, market, age=25.0):
    kind = "pick" if pos == "PICK" else "player"
    return Asset(id, kind, pos, id.upper(), None if kind == "pick" else age, float(market))


BODIES = lambda t: [A(f"{t}qb", "QB", 300), A(f"{t}rb1", "RB", 300), A(f"{t}rb2", "RB", 300),
                    A(f"{t}wr1", "WR", 300), A(f"{t}wr2", "WR", 300), A(f"{t}te", "TE", 300)]
SLOTS = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX")


def snap(teams, *, slots=SLOTS, max_players=None, other=None, windows=None):
    assets = {a.id: a for lst in teams.values() for a in lst}
    return LeagueSnapshot("L1", "1qb_ppr", assets,
        {t: Team(t, t, tuple(a.id for a in lst), (other or {}).get(t, 0),
                 (windows or {}).get(t, DEFAULT_WINDOW)) for t, lst in teams.items()},
        RosterRules(tuple(slots), max_players), first_round_value=1492.0, elite_value=8457.0)


def fourteen_team_league():
    """14 teams x (26 core players + 6 picks), lognormal markets, seeded."""
    rng = random.Random(11)
    teams = {}
    for t in range(14):
        tid = f"T{t:02d}"
        roster = []
        for i, pos in enumerate(ROSTER):
            market = min(9500.0, max(100.0, math.exp(rng.gauss(math.log(1200), 1.0))))
            age = None if pos == "PICK" else rng.uniform(21, 33)
            roster.append(Asset(f"{tid}_{i:02d}", "pick" if pos == "PICK" else "player", pos,
                                f"{tid}_{i:02d}", age, market))
        teams[tid] = roster
    return snap(teams, slots=PERF_SLOTS, max_players=30)


def test_fourteen_team_league_bounded():
    s = fourteen_team_league()
    t0 = time.perf_counter()
    trades, diag = find_fair_trades(s, Request("T00"), CoreConfig())
    elapsed = time.perf_counter() - t0
    print(f"\nvalue-core perf (14 teams): {elapsed * 1000:.0f} ms; partners={diag.partners} "
          f"packages_viewer={diag.packages_viewer} pairs_checked={diag.pairs_checked} "
          f"fair={diag.fair} kept={len(trades)} truncated_partners={diag.truncated_partners} "
          f"rejected={diag.rejected}")
    assert diag.partners == 13
    assert diag.pairs_checked <= 13 * MAX_CHECKS_PER_PARTNER
    assert not diag.budget_exhausted
    assert len(trades) <= 13 * 200
    assert elapsed < 10.0


def test_package_count_bound():
    # 20 equal-market WRs: the top 14 by id plus 3 pins from outside them = 17 candidates.
    viewer = [A(f"v{i:02d}", "WR", 1000) for i in range(20)] + BODIES("V")
    s = snap({"V": viewer, "P": [A("p1", "WR", 1000)] + BODIES("P")})
    pins = frozenset({"v17", "v18", "v19"})
    _, diag = find_fair_trades(s, Request("V", pinned_give_ids=pins), CoreConfig())
    assert diag.packages_viewer <= 833            # C(17,1) + C(17,2) + C(17,3)
    # every package over the 17 candidates that holds at least one pin: 833 - (14 + 91 + 364)
    assert diag.packages_viewer == 833 - 469
