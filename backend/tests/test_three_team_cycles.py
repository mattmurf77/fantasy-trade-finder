"""TC-ENG-004 — 3-team cycle clearing (trade_optimizer.find_three_team_cycles).

This exercises genuinely-uncovered code: `find_three_team_cycles` (work item 3.3,
kidney-exchange-style clearing) is defined + exported but NOT wired into the
generation path (no caller in server.py / trade_service.py — the trade.three_team
flag is referenced only in a comment). Tested directly so it is known-good for
when it IS wired.

  - A Pareto-improving A->B->C->A cycle is found, with correct transfers + nets.
  - No beneficial cycle -> empty.
  - < 3 ranked members -> empty.
  - Lineup feasibility is enforced (a transfer that breaks a lineup is rejected).
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_optimizer import find_three_team_cycles
from backend.trade_service import League, LeagueMember


@pytest.fixture(autouse=True)
def _isolate():
    of, oc = ff._flags_cache, dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)   # marginal OFF -> raw member values
    ts._cfg.clear(); ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = of
        ts._cfg.clear(); ts._cfg.update(oc)


class _P:
    def __init__(s, i, pos):
        s.id, s.name, s.position, s.team, s.age, s.ktc_value = i, i, pos, "T", 24, None


def _full_lineup(uid):
    """A legal lineup (QB1/RB2/WR2/TE) + the cyclic RB asset r{uid}."""
    return {
        f"r{uid}": "RB", f"rb{uid}": "RB", f"qb{uid}": "QB",
        f"wr{uid}a": "WR", f"wr{uid}b": "WR", f"te{uid}": "TE",
    }


def _build():
    positions = {}
    for u in ("A", "B", "C"):
        positions.update(_full_lineup(u))
    players = {pid: _P(pid, pos) for pid, pos in positions.items()}
    rosters = {u: list(_full_lineup(u)) for u in ("A", "B", "C")}
    members = [LeagueMember(user_id=u, username=u, roster=rosters[u],
                            elo_ratings={}, has_rankings=True) for u in ("A", "B", "C")]
    league = League(league_id="L", name="T", platform="demo", members=members)
    return league, players, positions


def _baseline_values(positions):
    """Every member values every player at a neutral 1500-ish baseline."""
    return {pid: 1500.0 for pid in positions}


def test_finds_pareto_cycle():
    league, players, positions = _build()
    # Cycle: A covets rC, B covets rA, C covets rB. Each holder undervalues
    # their own cyclic asset. A->B (rA), B->C (rB), C->A (rC).
    base = _baseline_values(positions)
    mv = {u: dict(base) for u in ("A", "B", "C")}
    mv["A"]["rA"] = 1000.0; mv["A"]["rC"] = 2500.0   # A: give rA, want rC
    mv["B"]["rB"] = 1000.0; mv["B"]["rA"] = 2500.0   # B: give rB, want rA
    mv["C"]["rC"] = 1000.0; mv["C"]["rB"] = 2500.0   # C: give rC, want rB
    seed = {pid: 1500.0 for pid in positions}

    cycles = find_three_team_cycles(league=league, member_values=mv,
                                    seed_elo=seed, players=players)
    assert cycles, "a clearly Pareto-improving 3-cycle should be found"
    top = cycles[0]
    assert set(top["teams"]) == {"A", "B", "C"}
    # Each team nets > 0 and the min net clears cycle_min_net (200).
    assert top["min_net"] >= 200.0, top
    assert all(net > 0 for net in top["nets"].values()), top["nets"]
    # The transfers move each cyclic asset to the team that coveted it.
    moved = {(t["from"], t["player_id"]) for t in top["transfers"]}
    assert ("A", "rA") in moved and ("B", "rB") in moved and ("C", "rC") in moved


def test_no_cycle_when_no_mutual_benefit():
    league, players, positions = _build()
    # Everyone values everything the same -> no beneficial directed edges.
    base = _baseline_values(positions)
    mv = {u: dict(base) for u in ("A", "B", "C")}
    seed = {pid: 1500.0 for pid in positions}
    assert find_three_team_cycles(league=league, member_values=mv,
                                  seed_elo=seed, players=players) == []


def test_fewer_than_three_ranked_members():
    league, players, positions = _build()
    base = _baseline_values(positions)
    # Only two members appear in member_values -> the third is skipped.
    mv = {u: dict(base) for u in ("A", "B")}
    seed = {pid: 1500.0 for pid in positions}
    assert find_three_team_cycles(league=league, member_values=mv,
                                  seed_elo=seed, players=players) == []


def test_feasibility_blocks_lineup_breaking_cycle():
    """If a team's cyclic asset is its ONLY player at a position the lineup
    needs, giving it away breaks the lineup and the cycle must be rejected."""
    # Make rA a QB that A has only one of (lineup needs QB1). After A gives rA
    # it would have 0 QB -> infeasible, so no cycle should clear even though the
    # value cycle is beneficial.
    positions = {}
    for u in ("A", "B", "C"):
        positions.update(_full_lineup(u))
    positions["rA"] = "QB"   # A's cyclic asset is now its second QB...
    del positions["qbA"]     # ...and remove A's other QB so rA is the only one
    players = {pid: _P(pid, pos) for pid, pos in positions.items()}
    rosters = {u: [p for p in _full_lineup(u)] for u in ("A", "B", "C")}
    rosters["A"] = [p for p in rosters["A"] if p != "qbA"]
    members = [LeagueMember(user_id=u, username=u, roster=rosters[u],
                            elo_ratings={}, has_rankings=True) for u in ("A", "B", "C")]
    league = League(league_id="L", name="T", platform="demo", members=members)
    base = {pid: 1500.0 for pid in positions}
    mv = {u: dict(base) for u in ("A", "B", "C")}
    mv["A"]["rA"] = 1000.0; mv["A"]["rC"] = 2500.0
    mv["B"]["rB"] = 1000.0; mv["B"]["rA"] = 2500.0
    mv["C"]["rC"] = 1000.0; mv["C"]["rB"] = 2500.0
    seed = {pid: 1500.0 for pid in positions}
    # A giving its only QB (rA) breaks A's lineup -> that edge/cycle is infeasible.
    cycles = find_three_team_cycles(league=league, member_values=mv,
                                    seed_elo=seed, players=players)
    assert all("A" not in c["teams"] or
               not any(t["from"] == "A" and t["player_id"] == "rA" for t in c["transfers"])
               for c in cycles), "a lineup-breaking QB handoff must not clear"
