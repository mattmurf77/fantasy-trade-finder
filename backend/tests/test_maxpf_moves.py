"""Max PF moves: the pure calculation (contract §13, plan B2, exploration §7.1 / §11).

Two worlds. (1) The season-signal fixture: real `provider.capture` over a
12-team league, 14 future weeks, best-available contract, free agents in the
feed (seven slots are free-agent filled). (2) Hand-built snapshots for the
exploration's worked example and edge cases. No network, no database.

- test_parity_reproduces_every_saved_team_week (both scoring contracts): with
  nobody removed, the re-solve equals the saved projected score and projected
  max PF for every team-week, free-agent-filled weeks included. Sabotage: skip
  `free_agent_fill` in the re-solve.
- test_kept_pool_gives_the_same_answers_as_every_free_agent: the side
  channel's kept pool and an unbounded pool give identical re-solves for
  every candidate of every team. Sabotage: provider.SIDECAR_EXTRA_SLOTS = 0.
- test_worked_example (exploration §6): Sato −31 (Mercer 4 weeks, Quill 1),
  Okafor −28 (Mercer 4 weeks, bye in week 12). Sabotage: build the lineup lane
  from the max PF pool.
- test_taxi_player_replaces_only_in_the_max_pf_lane, test_only_tight_end_is_
  replaced_by_a_free_agent, test_reserve_and_unprojected_players_are_left_out,
  test_provider_out_week_is_a_known_zero, test_superflex_chain.
- test_fixture_sanity: removal never raises a lane total; a week's drop never
  exceeds the player's own points; a player outside the max PF lineup in every
  week has 0.
- test_unchanged_roster_gives_exactly_zero: lowering by nothing reproduces the
  5,000-run simulation bit for bit, and the "after" figures equal the saved
  ones exactly. Sabotage: a different seed for the "after" run.
- test_same_input_same_output.
- test_after_figures_are_valid_probabilities. Sabotage: drop the clamp.
- test_threshold_edges. Sabotage: `>` for `>=`.
- test_paired_change_tolerance (about 20 s): on a 5-week cut of the fixture,
  the 5,000-run change for the top candidate is within the stated tolerance
  of the 100,000-run change (pick if you miss 0.05 of a slot, top-3 and
  playoff chance 0.03).
- test_not_eligible_team.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
import json

import pytest

from backend.league_projections import batch, maxpf_moves, provider, simulation
from backend.league_projections.scoring import BEST_AVAILABLE, CONTRACT as SPARSE
from backend.tests.test_season_points import CAPTURED_AT, LEAGUE_ID, capture_cfg, sleeper_world

OPTIONS = {"simulations_per_candidate": 5000, "candidates": 8, "min_drop_points": 5,
           "min_pick_change": 0.1, "min_top3_change": 0.02, "time_budget_seconds": 60}


def model_cfg(iterations=20000):
    return simulation.config({**batch.settings()["model"], "draft_season": 2027, "iterations": iterations})


@lru_cache(maxsize=None)
def _world(contract=BEST_AVAILABLE, extra=None):
    """`extra` None keeps provider.SIDECAR_EXTRA_SLOTS as shipped."""
    source = sleeper_world(strict=contract != BEST_AVAILABLE)
    side = {}
    old = provider.SIDECAR_EXTRA_SLOTS
    provider.SIDECAR_EXTRA_SLOTS = old if extra is None else extra
    try:
        snap = provider.capture(LEAGUE_ID, "me", capture_cfg(contract), lambda url: deepcopy(source[url]),
                                captured_at=CAPTURED_AT, clock=lambda: CAPTURED_AT, sidecar=side)
    finally:
        provider.SIDECAR_EXTRA_SLOTS = old
    return snap, side


def world(contract=BEST_AVAILABLE, extra=None):
    snap, side = _world(contract, extra)
    return deepcopy(snap), deepcopy(side)


@lru_cache(maxsize=None)
def _result():
    snap, _ = _world()
    return simulation.simulate(snap, model_cfg())


def result():
    return deepcopy(_result())


# ---------------------------------------------------------------------------
# Hand-built snapshots
# ---------------------------------------------------------------------------

def hand_snapshot(slots, players, *, weeks=(10, 11, 12, 13, 14), taxi=(), reserve=(), free_agents=None):
    """players: {pid: (name, position, {week: points | 'bye' | None | 'out'})}.
    A one-team league (the re-solve never needs the others)."""
    inputs = []
    for pid, (name, pos, by_week) in players.items():
        for w in weeks:
            value = by_week.get(w, by_week.get("all"))
            if value is None:
                continue
            row = {"bye": False, "availability": 1, "projection_status": "available",
                   "stats": {"rec": value} if isinstance(value, (int, float)) else {}, "supported_keys": ["rec"]}
            if value == "bye":
                row = {"bye": True, "bye_evidence": True}
            elif value == "out":
                row = {"bye": False, "availability": 0, "stats": {}, "supported_keys": ["rec"]}
            inputs.append({"week": w, "player_id": pid, "positions": [pos], "input": row})
    detail = {"actual": {"lineup": []}, "maxpf": {"lineup": []}, "replacement_means": {}}
    roster = {"players": sorted(players), "taxi": sorted(taxi), "reserve": sorted(reserve)}
    snap = {"viewer_roster_id": 1, "slots": list(slots), "scoring": {"rec": 1},
            "coverage": {"scoring_contract": BEST_AVAILABLE}, "player_week_inputs": inputs,
            "teams": [{"roster_id": 1, "roster": roster}],
            "weeks": [{"week": w, "teams": {"1": deepcopy(detail)}} for w in weeks]}
    names = {pid: name for pid, (name, _, _) in players.items()}
    for w, pool in (free_agents or {}).items():
        for p in pool:
            names.setdefault(p["player_id"], p["name"])
    return snap, names


HAND_CFG = {"ir_maxpf": "exclude", "empty_slots": "fill_available"}
EXAMPLE_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"]
EXAMPLE = {
    "qb": ("Nico Varga", "QB", {"all": 19}),
    "sato": ("Rhett Sato", "RB", {"all": 15}),
    "pike": ("Jonah Pike", "RB", {"all": 12}),
    "mercer": ("Cal Mercer", "RB", {"all": 10}),
    "okafor": ("Dale Okafor", "WR", {"all": 17, 12: "bye"}),
    "brandt": ("Milo Brandt", "WR", {"all": 13}),
    "lund": ("Tavi Lund", "WR", {"all": 11}),
    "quill": ("Ezra Quill", "WR", {"all": 4}),
    "te": ("Bo Halvorsen", "TE", {"all": 9}),
}


def solve(snap, names, pool=None):
    return maxpf_moves.resolve(snap, HAND_CFG, pool or {}, 1, names=names)


def reps(candidate):
    out = {}
    for wk in candidate["weeks"]:
        for r in wk["replaced_by"]:
            out[r["name"]] = out.get(r["name"], 0) + 1
    return out


def test_worked_example():
    snap, names = hand_snapshot(EXAMPLE_SLOTS, EXAMPLE)
    c = solve(snap, names)["candidates"]
    assert c["sato"]["dM"] == 31 and c["sato"]["dA"] == 31
    assert reps(c["sato"]) == {"Cal Mercer": 4, "Ezra Quill": 1}
    assert c["okafor"]["dM"] == 28 and reps(c["okafor"]) == {"Cal Mercer": 4}
    assert [w["status"] for w in c["okafor"]["weeks"]] == ["changed", "changed", "bye", "changed", "changed"]
    assert [w["dM"] for w in c["sato"]["weeks"]] == [5, 5, 11, 5, 5]
    assert c["quill"]["dM"] == 0 and c["quill"]["dA"] == 0  # never starts, even in the bye week
    assert {w["status"] for w in c["quill"]["weeks"]} == {"no_change"}


def test_taxi_player_replaces_only_in_the_max_pf_lane():
    players = {"qb": ("Q One", "QB", {"all": 20}), "wr1": ("W One", "WR", {"all": 15}),
               "wr2": ("W Two", "WR", {"all": 6}), "taxi": ("T Rookie", "WR", {"all": 12})}
    snap, names = hand_snapshot(["QB", "WR"], players, taxi=["taxi"])
    c = solve(snap, names)["candidates"]
    assert c["wr1"]["dA"] == 5 * 9 and c["wr1"]["dM"] == 5 * 3  # lineup: wr2 (6); max PF: taxi (12)
    assert reps(c["wr1"]) == {"T Rookie": 5}
    assert c["taxi"]["dA"] == 0 and c["taxi"]["dM"] == 0  # he never beats wr1


def test_only_tight_end_is_replaced_by_a_free_agent():
    pool = {str(w): [{"player_id": "fa_te", "name": "Free Tight", "positions": ["TE"], "points": "3"}] for w in range(10, 15)}
    players = {"qb": ("Q One", "QB", {"all": 20}), "te": ("Only Tight", "TE", {"all": 9})}
    snap, names = hand_snapshot(["QB", "TE"], players, free_agents=pool)
    c = solve(snap, names, pool)["candidates"]
    assert c["te"]["dM"] == 5 * 6
    week = c["te"]["weeks"][0]
    assert week["replaced_by"] == [{"player_id": "fa_te", "name": "Free Tight", "short_name": "F. Tight", "free_agent": True}]
    # Without the kept free agent the slot would score zero: the overstatement the side channel exists to prevent.
    assert solve(snap, names)["candidates"]["te"]["dM"] == 5 * 9


def test_reserve_and_unprojected_players_are_left_out():
    players = {"qb": ("Q One", "QB", {"all": 20}), "hurt": ("On Reserve", "QB", {"all": 30}),
               "nodata": ("No Projection", "QB", {10: 25})}
    snap, names = hand_snapshot(["QB"], players, reserve=["hurt"])
    solved = solve(snap, names)
    assert "hurt" not in solved["candidates"] and "hurt" not in solved["unknown"]
    assert solved["unknown"] == ["nodata"] and "nodata" not in solved["candidates"]


def test_provider_out_week_is_a_known_zero():
    players = {"qb": ("Q One", "QB", {"all": 20, 11: "out"}), "qb2": ("Q Two", "QB", {"all": 14})}
    snap, names = hand_snapshot(["QB"], players)
    c = solve(snap, names)["candidates"]
    assert c["qb"]["dM"] == 4 * 6 and [w["dM"] for w in c["qb"]["weeks"]][1] == 0


def test_superflex_chain():
    players = {"qb1": ("Q One", "QB", {"all": 22}), "qb2": ("Q Two", "QB", {"all": 18}),
               "rb1": ("R One", "RB", {"all": 14}), "rb2": ("R Two", "RB", {"all": 8})}
    snap, names = hand_snapshot(["QB", "RB", "SUPER_FLEX"], players)
    c = solve(snap, names)["candidates"]
    # Losing qb1: qb2 moves to QB, rb2 takes the superflex. 54 -> 40.
    assert c["qb1"]["dM"] == 5 * 14 and reps(c["qb1"]) == {"R Two": 5}


# ---------------------------------------------------------------------------
# The fixture world
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("contract", [BEST_AVAILABLE, SPARSE])
def test_parity_reproduces_every_saved_team_week(contract):
    snap, side = world(contract)
    proof = maxpf_moves.parity(snap, model_cfg(), side["free_agents"])
    assert proof["mismatches"] == []
    assert proof["checked"] == 12 * 14 and proof["skipped"] == 0
    if contract == BEST_AVAILABLE:
        fills = sum(len(t["projection_coverage"]["free_agent_fills"]) + len(t["projection_coverage"]["maxpf_free_agent_fills"])
                    for week in snap["weeks"] for t in week["teams"].values())
        assert fills >= 7


def _strip(solved):
    return {pid: (c["dA"], c["dM"], json.dumps(c["weeks"], default=str)) for pid, c in solved["candidates"].items()}


def test_kept_pool_gives_the_same_answers_as_every_free_agent():
    snap, side = world()
    _, full = world(extra=1000)
    assert sum(map(len, full["free_agents"].values())) > sum(map(len, side["free_agents"].values()))
    for team in snap["teams"]:
        rid = team["roster_id"]
        kept = maxpf_moves.resolve(snap, model_cfg(), side["free_agents"], rid)
        every = maxpf_moves.resolve(snap, model_cfg(), full["free_agents"], rid)
        assert _strip(kept) == _strip(every), rid


def test_fixture_sanity():
    """Without free agents, removing a player never raises either lane's
    total. With them it can: the fill takes only open slots, so a free agent
    who outprojects the removed starter raises the total (contract §3.5)."""
    snap, side = world()
    points = maxpf_moves.season_points.player_points(snap)
    raised = 0
    for team in snap["teams"]:
        for pool in ({}, side["free_agents"]):
            solved = maxpf_moves.resolve(snap, model_cfg(), pool, team["roster_id"])
            for pid, cand in solved["candidates"].items():
                for wk in cand["weeks"]:
                    if not pool:
                        assert wk["dA"] >= 0 and wk["dM"] >= 0
                    elif wk["dM"] < 0:
                        raised += 1
                        assert any(r["free_agent"] for r in wk["replaced_by"])
                    own = points[wk["week"]].get(pid)
                    if isinstance(own, Decimal):
                        assert wk["dM"] <= own
                    else:
                        assert wk["dM"] == 0
                    if wk["dM"] == 0:
                        assert wk["replaced_by"] == []


def test_unchanged_roster_gives_exactly_zero():
    snap, _ = world()
    small = {**model_cfg(), "iterations": 5000}
    before = simulation.simulate(snap, small)
    same = simulation.simulate(maxpf_moves._lowered(snap, snap["viewer_roster_id"], {}), small)
    assert json.dumps(before, sort_keys=True) == json.dumps(same, sort_keys=True)
    saved = result()
    after = maxpf_moves._after_teams(saved, before, same)
    for team in saved["teams"]:
        mine = after[team["roster_id"]]
        assert mine["playoff_probability"] == team["playoff_probability"]
        assert mine["pick_probabilities"] == team["pick_probabilities"]
        assert mine["conditional_expected_pick"] == team["conditional_expected_pick"]


def test_same_input_same_output():
    snap, side = world()
    first = _block()
    second = maxpf_moves.compute(snap, result(), side["free_agents"], OPTIONS, names=side["names"])
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["computed"] and len(first["rows"]) == 8 and first["candidates_total"] >= 8


def test_compute_with_no_change_returns_the_saved_figures(monkeypatch):
    """The whole compute path, paired: a candidate whose weekly changes are all
    zero gets "after" equal to "now", exactly."""
    snap, side = world()
    real = maxpf_moves.resolve

    def zeroed(*args, **kwargs):
        solved = real(*args, **kwargs)
        for cand in solved["candidates"].values():
            for wk in cand["weeks"]:
                wk["dA"] = wk["dM"] = Decimal(0)
        first = sorted(solved["candidates"])[0]
        solved["candidates"] = {first: {**solved["candidates"][first], "dM": Decimal(1), "dA": Decimal(1)}}
        return solved

    monkeypatch.setattr(maxpf_moves, "resolve", zeroed)
    block = maxpf_moves.compute(snap, result(), side["free_agents"], {**OPTIONS, "simulations_per_candidate": 2000})
    row = block["rows"][0]
    for key in ("playoff_probability", "pick_if_miss", "top3_probability", "label_slot"):
        assert row[key]["after"] == row[key]["now"], key


@lru_cache(maxsize=None)
def _block():
    snap, side = _world()
    return maxpf_moves.compute(snap, _result(), side["free_agents"], OPTIONS, names=side["names"])


def test_after_figures_are_valid_probabilities():
    block = deepcopy(_block())
    saved = result()
    viewer = next(t for t in saved["teams"] if t["roster_id"] == block["viewer_roster_id"])
    assert block["baseline"]["label"] and block["baseline"]["weeks_remaining"] == 14
    assert block["baseline"]["top3_probability"] == sum(viewer["pick_probabilities"][:3])
    previous = None
    for row in block["rows"]:
        assert 0 <= row["playoff_probability"]["after"] <= 1
        assert 0 <= row["top3_probability"]["after"] <= 1
        assert all(p >= 0 for p in row["after_pick_probabilities"])
        assert abs(sum(row["after_pick_probabilities"]) - (1 - row["after_playoff_probability"])) < 1e-9
        assert row["maxpf_change"] < 0 and row["playoff_probability"]["now"] == viewer["playoff_probability"]
        key = (Decimal(row["maxpf_change_exact"]), Decimal(row["lineup_change_exact"]), row["player_id"])
        assert previous is None or previous <= key
        previous = key
        assert len(row["replacements"]) <= 3 and row["weeks_affected"] <= 14
        assert all(r["weeks"] >= 1 for r in row["replacements"])
        # A bigger drop never makes the pick worse on this fixture.
        assert row["pick_if_miss"]["after"] <= row["pick_if_miss"]["now"]


def test_after_clamps_a_negative_difference():
    """A tiny saved probability plus a larger negative paired difference is
    clamped at 0, and the row is rescaled to the team's non-playoff chance."""
    team = {"roster_id": 1, "playoff_probability": .5, "pick_probabilities": [.00001, .49999],
            "conditional_expected_pick": 1.9, "expected_record": [5, 5, 0]}
    before = {"teams": [{**team, "pick_probabilities": [.01, .49]}]}
    after = {"teams": [{**team, "pick_probabilities": [.005, .495]}]}
    out = maxpf_moves._after_teams({"teams": [team]}, before, after)[1]
    assert out["pick_probabilities"][0] == 0.0
    assert abs(sum(out["pick_probabilities"]) - .5) < 1e-12


def test_threshold_edges():
    f = maxpf_moves.passes_threshold
    assert f(Decimal("-5"), 3.7, 3.6, .40, .40, OPTIONS)            # exactly 5 points, exactly 0.1
    assert not f(Decimal("-4.99"), 3.7, 2.0, .40, .90, OPTIONS)      # under 5 points
    assert f(Decimal("-9"), 3.3, 3.2, .40, .40, OPTIONS)             # 0.1 with float noise
    assert not f(Decimal("-9"), 3.7, 3.65, .40, .41, OPTIONS)        # both changes too small
    assert f(Decimal("-9"), None, None, .40, .42, OPTIONS)           # exactly 0.02 on top-3
    assert f(Decimal("-9"), 3.7, None, .40, .43, OPTIONS)


def test_not_eligible_team():
    snap, side = world()
    block = maxpf_moves.compute(snap, result(), side["free_agents"], OPTIONS, roster_id=99)
    assert block["computed"] is False and block["reason"] == "not_eligible" and block["rows"] == []


def test_paired_change_tolerance():
    """Measured about 20 s locally; runs in CI."""
    snap, side = world()
    snap["weeks"] = snap["weeks"][-5:]
    cut = simulation.simulate(snap, model_cfg(100000))
    small = maxpf_moves.compute(snap, cut, side["free_agents"], {**OPTIONS, "candidates": 1})
    large = maxpf_moves.compute(snap, cut, side["free_agents"], {**OPTIONS, "candidates": 1, "simulations_per_candidate": 100000})
    a, b = small["rows"][0], large["rows"][0]
    assert a["player_id"] == b["player_id"]
    assert abs(a["pick_if_miss"]["after"] - b["pick_if_miss"]["after"]) <= 0.05
    assert abs(a["top3_probability"]["after"] - b["top3_probability"]["after"]) <= 0.03
    assert abs(a["playoff_probability"]["after"] - b["playoff_probability"]["after"]) <= 0.03
