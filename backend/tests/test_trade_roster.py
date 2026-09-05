"""Roster guarantees, independent of generator arms or package mutations."""
from dataclasses import replace
from itertools import permutations
import random
from types import SimpleNamespace

import pytest

from backend.trade_roster import Asset, Context, Rules, Team, assign, evaluate
from backend.trade_roster_adapter import build_context


def asset(pid, pos, value=100, **kw):
    return Asset(pid, frozenset(pos.split("+")), value, **kw)


def exchange(assets, mine, theirs, give, receive, slots=("RB", "WR", "FLEX"), **kw):
    return evaluate(viewer=Team("me", tuple(mine)), partner=Team("them", tuple(theirs)),
                    assets={a.id: a for a in assets}, give=give, receive=receive,
                    rules=kw.pop("rules", Rules(slots, "observed", 30)), **kw)


def test_exact_assignment_handles_overlapping_flex_and_multi_position_eligibility():
    pool = [asset("r", "RB", 100), asset("w", "WR", 80), asset("t", "TE", 70)]
    assert assign(("WRRB_FLEX", "REC_FLEX", "RB"), pool) == ["w", "t", "r"]
    pool = [asset("dual", "QB+WR", 200), asset("q", "QB", 100)]
    assert assign(("QB", "WR"), pool) == ["q", "dual"]


def test_assignment_matches_exhaustive_optimum_small_rosters():
    rng = random.Random(29)
    slots = ("RB", "WRRB_FLEX", "REC_FLEX")
    from backend.trade_roster import ELIGIBILITY
    for _ in range(35):
        pool = [asset(str(i), rng.choice(("RB", "WR", "TE", "RB+WR")), rng.randrange(1, 150))
                for i in range(5)]
        by_id = {a.id: a for a in pool}
        actual = assign(slots, pool)
        actual_key = (sum(p is not None for p in actual), sum(by_id[p].value for p in actual if p))
        optimum = (0, 0)
        for candidate in permutations(pool + [None] * len(slots), len(slots)):
            if all(a is None or a.positions & ELIGIBILITY[s] for a, s in zip(candidate, slots)):
                optimum = max(optimum, (sum(a is not None for a in candidate),
                                        sum(a.value for a in candidate if a)))
        assert actual_key == optimum
        assert len(set(p for p in actual if p)) == actual_key[0]


@pytest.mark.parametrize("bad", [{"available": False}, {"startable": False}])
def test_spare_body_cannot_hide_loss_of_usable_starter(bad):
    pool = [asset("r", "RB"), asset("spare", "RB", 10, **bad), asset("w", "WR"), asset("w2", "WR")]
    result = exchange(pool, ["r", "spare", "w"], ["w2"], ["r"], ["w2"], slots=("RB", "WR"))
    assert not result["eligible"]
    assert "deficits:RB" in result["teams"]["me"]["blockers"]


def test_satisfying_dedicated_slots_does_not_hide_new_flex_deficiency():
    pool = [asset("r", "RB"), asset("w", "WR"), asset("t", "TE"), asset("q", "QB")]
    result = exchange(pool, ["r", "w", "t"], ["q"], ["t"], ["q"])
    assert result["teams"]["me"]["after"]["filled_slots"] == 2
    assert "deficits:RB+TE+WR" in result["teams"]["me"]["blockers"]


def test_superflex_can_use_a_receiver_but_not_duplicate_a_quarterback():
    pool = [asset("q", "QB"), asset("w", "WR")]
    assert assign(("QB", "SUPER_FLEX"), pool) == ["q", "w"]
    assert assign(("QB", "SUPER_FLEX"), pool[:1]).count(None) == 1


def test_both_managers_checked_and_mirror_verdict_is_symmetric():
    pool = [asset("r", "RB"), asset("r2", "RB"), asset("w", "WR"), asset("w2", "WR")]
    a = exchange(pool, ["r", "r2", "w"], ["w2"], ["r2"], ["w2"], slots=("RB", "WR"))
    b = exchange(pool, ["w2"], ["r", "r2", "w"], ["w2"], ["r2"], slots=("RB", "WR"))
    assert a["status"] == b["status"] == "blocked"
    assert "deficits:WR" in a["teams"]["them"]["blockers"]


def test_existing_unrelated_deficit_does_not_veto_same_position_upgrade():
    pool = [asset("r", "RB", 50), asset("r2", "RB", 100)]
    result = exchange(pool, ["r"], ["r2"], ["r"], ["r2"], slots=("RB", "TE"))
    assert result["eligible"]
    assert result["teams"]["me"]["after"]["deficits"]["TE"] == 1


def test_last_backup_is_protected_but_extra_surplus_can_move():
    pool = [asset("r"+str(i), "RB") for i in range(3)] + [asset("w", "WR")]
    unsafe = exchange(pool, ["r0", "r1"], ["w"], ["r1"], ["w"], slots=("RB",))
    safe = exchange(pool, ["r0", "r1", "r2"], ["w"], ["r2"], ["w"], slots=("RB",))
    assert "backup_depth:RB" in unsafe["teams"]["me"]["blockers"]
    assert safe["eligible"]


def test_shared_flex_last_backup_is_protected():
    pool = [asset("r", "RB"), asset("w", "WR"), asset("t", "TE"), asset("q", "QB")]
    result = exchange(pool, ["r", "w", "t"], ["q"], ["t"], ["q"], slots=("RB", "FLEX"))
    assert result["teams"]["me"]["after"]["filled_slots"] == 2
    assert "backup_depth:RB+TE+WR" in result["teams"]["me"]["blockers"]


def test_reserve_and_taxi_never_count_as_available_depth():
    assets = {a.id: a for a in [asset("r", "RB"), asset("taxi", "RB"), asset("w", "WR")]}
    result = evaluate(viewer=Team("me", ("r", "taxi"), frozenset(("taxi",))),
        partner=Team("them", ("w",)), give=["r"], receive=["w"], assets=assets,
        rules=Rules(("RB",), "observed", 5))
    assert result["teams"]["me"]["after"]["filled_slots"] == 0


def test_uneven_packages_require_real_cut_plan_and_recheck_it():
    pool = [asset("r", "RB", 200), asset("r2", "RB", 150), asset("w", "WR", 10)]
    rules = Rules(("RB",), "observed", 1)
    raw = exchange(pool, ["r"], ["r2", "w"], ["r"], ["r2", "w"], rules=rules)
    assert "cuts_required" in raw["teams"]["me"]["blockers"]
    # Explicit incoming cuts are invalid: the engine must not suggest getting
    # a player only to drop them as an unmentioned repair.
    cut = exchange(pool, ["r"], ["r2", "w"], ["r"], ["r2", "w"], rules=rules, cuts={"me": ["w"]})
    assert not cut["eligible"]
    assert "invalid_cut_plan" in cut["teams"]["me"]["unknowns"]


def test_explicit_existing_bench_cut_is_supported_and_can_create_a_deficiency():
    pool = [asset("r", "RB"), asset("bench", "WR", 5), asset("r2", "RB"), asset("new", "TE", 10)]
    result = exchange(pool, ["r", "bench"], ["r2", "new"], ["r"], ["r2", "new"],
                      rules=Rules(("RB",), "observed", 2), cuts={"me": ["bench"]})
    assert result["eligible"]
    broken = exchange(pool, ["r", "bench"], ["r2", "new"], ["r"], ["r2", "new"],
                      rules=Rules(("RB", "WR"), "observed", 2), cuts={"me": ["bench"]})
    assert not broken["eligible"]
    assert "deficits:WR" in broken["teams"]["me"]["blockers"]


def test_picks_do_not_fill_slots_or_consume_capacity():
    pool = [asset("r", "RB"), asset("r2", "RB"), asset("p", "", 50, is_pick=True)]
    result = exchange(pool, ["r"], ["r2", "p"], ["r"], ["r2", "p"],
                      rules=Rules(("RB",), "observed", 1))
    assert result["eligible"]
    assert result["teams"]["me"]["after"]["active_count"] == 1


@pytest.mark.parametrize("rules, reason", [
    (Rules(("RB",), "estimated", 4), "lineup_settings_estimated"),
    (Rules(("RB", "IDP"), "observed", 4), "unsupported_or_missing_lineup"),
    (Rules(("RB",), "observed", 4, uncertainties=("stale",)), "stale"),
])
def test_uncertain_settings_never_pass(rules, reason):
    result = exchange([asset("r", "RB"), asset("r2", "RB")], ["r"], ["r2"], ["r"], ["r2"], rules=rules)
    assert result["status"] == "unknown"
    assert reason in result["unknowns"]


def test_unresolved_roster_asset_and_missing_capacity_are_explicit():
    result = exchange([asset("r", "RB"), asset("r2", "RB")], ["r", "missing"], ["r2"], ["r"], ["r2"],
                      rules=Rules(("RB",), "observed"))
    assert result["status"] == "unknown"
    assert result["teams"]["me"]["unknowns"] == ["capacity_unknown", "unresolved_roster_asset"]


def test_supplied_bye_scenario_catches_concentration():
    pool = [asset("r", "RB"), asset("backup", "RB"), asset("r2", "RB")]
    result = exchange(pool, ["r", "backup"], ["r2"], ["r"], ["r2"], slots=("RB",),
                      scenarios={"week9": frozenset(("backup", "r2"))})
    assert "availability_scenario:week9" in result["teams"]["me"]["blockers"]
    assert result["schedule_coverage"] == "supplied_scenarios"


def test_outlook_changes_utility_but_cannot_relax_coverage():
    assets = {a.id: a for a in [asset("r", "RB", 100), asset("r2", "RB", 120), asset("p", "", 50, is_pick=True)]}
    kwargs = dict(partner=Team("them", ("r2",)), give=["r", "p"], receive=["r2"], assets=assets,
                  rules=Rules(("RB",), "observed", 5))
    win = evaluate(viewer=Team("me", ("r", "p"), outlook="championship"), **kwargs)
    rebuild = evaluate(viewer=Team("me", ("r", "p"), outlook="rebuilder"), **kwargs)
    assert win["eligible"] == rebuild["eligible"] is True
    assert win["teams"]["me"]["utility"] > 0 > rebuild["teams"]["me"]["utility"]
    assert win["schedule_coverage"] == "unknown"


def test_adapter_observes_ownership_reserve_and_multi_position_and_handles_platform_estimates():
    players = {p: SimpleNamespace(position="RB", injury_status=None) for p in ("a", "b", "c")}
    league = SimpleNamespace(members=[SimpleNamespace(user_id="me", roster=["stale"]),
                                      SimpleNamespace(user_id="them", roster=["b"])])
    ctx = build_context(viewer_id="me", league=league, players=players,
        consensus_value=lambda pid: 100, startable=lambda *a: True,
        slots=["RB"], platform="sleeper", capacity=3, availability_fresh=True,
        raw_rosters=[{"owner_id": "me", "players": ["a", "c"], "taxi": ["c"]},
                     {"owner_id": "them", "players": ["b"]}],
        player_metadata={"a": {"fantasy_positions": ["RB", "WR"]}, "c": {"injury_status": "Out"}})
    assert ctx.teams["me"].roster == ("a", "c")
    assert ctx.teams["me"].inactive == frozenset(("c",))
    assert ctx.assets["a"].positions == frozenset(("RB", "WR"))
    assert not ctx.assets["c"].available
    card = SimpleNamespace(target_user_id="them", give_player_ids=["a"], receive_player_ids=["b"])
    assert ctx.card(card)["eligible"]
    ctx.rules = replace(ctx.rules, source="estimated")
    ctx.cache.clear()
    assert ctx.card(card)["status"] == "unknown"


def test_empty_exchange_is_not_a_trade_suggestion():
    result = exchange([asset('r', 'RB'), asset('r2', 'RB')], ['r'], ['r2'], [], [], slots=('RB',))
    assert result['status'] == 'unknown'
    assert 'invalid_exchange' in result['unknowns']
