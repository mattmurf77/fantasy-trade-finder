"""Exact lineup memoization: output equivalence, private scope and bounded state."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend import trade_roster as roster


def context():
    assets = {p: roster.Asset(p, frozenset(pos.split("+")), value,
                             startable=p != "bench", available=p != "injured")
              for p, pos, value in [
                  ("q", "QB", 200), ("r", "RB", 120), ("w", "WR", 110),
                  ("bench", "WR", 10), ("dual", "RB+WR", 90),
                  ("r2", "RB", 125), ("w2", "WR", 100), ("injured", "TE", 80)]}
    return roster.Context("me", {
        "me": roster.Team("me", ("q", "r", "w", "bench", "dual")),
        "them": roster.Team("them", ("r2", "w2", "injured")),
    }, assets, roster.Rules(("QB", "RB", "WR", "FLEX"), "observed", 8))


def cards():
    return [SimpleNamespace(target_user_id="them", give_player_ids=give, receive_player_ids=receive)
            for give, receive in [(["r"], ["r2"]), (["w"], ["w2"]),
                                  (["r", "w"], ["r2", "w2"])]]


@pytest.mark.parametrize("projections", ["absent", "fresh", "stale"])
@pytest.mark.parametrize("availability_known", [False, True])
def test_memo_preserves_every_structural_and_outlook_field(projections, availability_known):
    cached = context()
    cached.teams = {uid: replace(team, availability_known=availability_known)
                    for uid, team in cached.teams.items()}
    if projections != "absent":
        # Projected points deliberately rank WRs differently from dynasty value.
        inputs = {"projections": {p: float(i + 1) for i, p in enumerate(cached.assets)},
                  "projection_basis": "synthetic-week", "projection_unit": "fantasy_points_for_period",
                  "projections_fresh": projections == "fresh", "explicit_outlook": "contender"}
        cached.utility_inputs = {uid: deepcopy(inputs) for uid in cached.teams}
    uncached = deepcopy(cached)
    uncached._assign = roster.assign
    for card in cards():
        assert cached.card(card) == uncached.card(card)


def test_repeated_rosters_share_solutions_without_sharing_returned_lists(monkeypatch):
    ctx = context()
    original, calls = roster.assign, []
    def counted(slots, pool):
        calls.append(1)
        return original(slots, pool)
    monkeypatch.setattr(roster, "assign", counted)
    first = ctx._assign(("RB", "WR"), list(ctx.assets.values()))
    first[:] = ["corrupted"]
    assert ctx._assign(("RB", "WR"), list(reversed(list(ctx.assets.values())))) == ["r2", "w"]
    assert len(calls) == 1
    other = context()
    assert other._assign(("RB", "WR"), list(other.assets.values())) == ["r2", "w"]
    assert len(calls) == 2  # No global or cross-context private roster cache.


def test_slots_values_and_asset_flags_are_part_of_exact_input_identity():
    ctx = context()
    pool = [ctx.assets["w"], ctx.assets["w2"]]
    assert ctx._assign(("WR",), pool) == ["w"]
    changed = [pool[0], replace(pool[1], value=200)]
    assert ctx._assign(("WR",), changed) == ["w2"]
    assert ctx._assign(("RB",), changed) == [None]
    changed[0] = replace(changed[0], startable=False, available=False, positions=frozenset(["RB"]))
    assert ctx._assign(("RB",), changed) == ["w"]


def test_assignment_state_is_bounded_for_many_speculative_rosters():
    ctx = context()
    for i in range(300):
        pool = [roster.Asset(str(i), frozenset(["WR"]), float(i))]
        assert ctx._assign(("WR",), pool) == [str(i)]
        assert len(ctx._assignments) <= 128
    # Eviction changes work only, never the answer.
    assert ctx._assign(("WR",), [roster.Asset("0", frozenset(["WR"]), 0.)]) == ["0"]


def test_real_card_evaluation_reuses_lineups_across_both_evaluators(monkeypatch):
    cached, uncached = context(), context()
    original, calls = roster.assign, []
    def counted(slots, pool):
        calls.append(1)
        return original(slots, pool)
    monkeypatch.setattr(roster, "assign", counted)
    expected = [cached.card(card) for card in cards()]
    memo_calls = len(calls)
    calls.clear()
    uncached._assign = counted
    assert [uncached.card(card) for card in cards()] == expected
    assert memo_calls < len(calls)


def test_availability_scenarios_and_cuts_keep_exact_results():
    ctx = context()
    args = dict(viewer=ctx.teams["me"], partner=ctx.teams["them"],
                give=["r"], receive=["r2"], assets=ctx.assets, rules=ctx.rules,
                cuts={"me": ["bench"]}, scenarios={"one-absence": frozenset(["w"])})
    assert roster.evaluate(**args, _assign=ctx._assign) == roster.evaluate(**args)
