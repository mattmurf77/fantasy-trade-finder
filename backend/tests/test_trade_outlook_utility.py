"""Outlook utility contract in docs/plans/trade-model-activation/outlook-utility.md.

Whole-lineup losses, complementary horizons, precedence, conservative missing
evidence, unit separation, normalization, deduplication, and roster protection.
All projections below are synthetic test inputs, never production defaults.
"""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from backend.trade_outlook_utility import evaluate_outlook_utility, resolve_outlook
from backend.trade_roster import Asset, Rules, Team, evaluate


def asset(pid, pos="RB", value=100, **kw):
    return Asset(pid, frozenset(pos.split("+")), value, **kw)


def utility(before_ids, after_ids, pool, *, slots=("RB",), points=None, **kw):
    params = dict(before=Team("me", tuple(before_ids)), after=Team("me", tuple(after_ids)),
                  assets={a.id: a for a in pool}, rules=Rules(slots, "observed", 30),
                  explicit_outlook="contender")
    if points is not None:
        params.update(projections=points, projection_basis="test model; PPR; 2026 rest of season",
                      projection_unit="fantasy_points_per_game", projections_fresh=True)
    params.update(kw)
    return evaluate_outlook_utility(**params)


def test_contender_rb2_plus_five_wr3_minus_nine_is_whole_team_loss():
    points = {"rb1": 20, "rb2": 10, "wr1": 25, "wr2": 20, "wr3": 18,
              "new_rb2": 15, "new_wr3": 9}
    pool = [asset(p, "RB" if "rb" in p else "WR") for p in points]
    result = utility(["rb1", "rb2", "wr1", "wr2", "wr3"],
                     ["rb1", "new_rb2", "wr1", "wr2", "new_wr3"], pool,
                     slots=("RB", "RB", "WR", "WR", "WR"), points=points)
    production = result["components"]["current_production"]
    assert (production["before"], production["after"], production["delta"]) == (93, 89, -4)
    assert production["normalized_gain"] == pytest.approx(-4 / 93)
    assert result["normalized_gain"] == pytest.approx(.75 * -4 / 93)
    assert result["ready_for_enforcement"]


def test_complementary_contender_and_rebuilder_both_gain_and_remain_protected():
    pool = [asset("vet", value=100), asset("young", value=160),
            asset("c_backup", value=50), asset("r_backup", value=50),
            asset("first", "PICK", 80, is_pick=True)]
    assets = {a.id: a for a in pool}
    contender = Team("c", ("young", "c_backup", "first"))
    rebuilder = Team("r", ("vet", "r_backup"))
    rules = Rules(("RB",), "observed", 30)
    roster_result = evaluate(viewer=contender, partner=rebuilder, give=["young", "first"],
                             receive=["vet"], assets=assets, rules=rules)
    assert roster_result["eligible"]
    for before, after_ids, outlook in ((contender, ("vet", "c_backup"), "contender"),
                                      (rebuilder, ("young", "r_backup", "first"), "rebuilder")):
        result = evaluate_outlook_utility(
            before=before, after=replace(before, roster=after_ids), assets=assets, rules=rules,
            explicit_outlook=outlook, projections={"vet": 20, "young": 10,
                                                  "c_backup": 5, "r_backup": 5},
            projection_basis="test model; PPR; 2026", projection_unit="fantasy_points_per_game",
            projections_fresh=True)
        assert result["normalized_gain"] > 0
        if outlook == "rebuilder":
            assert result["components"]["current_production"]["delta"] == -10
            assert result["components"]["future_assets"]["delta"] == 140
        roster_result["teams"][before.id]["outlook_utility"] = result
    assert roster_result["eligible"]
    json.dumps(roster_result, allow_nan=False)


def test_rebuilder_future_gain_does_not_override_a_roster_blocker():
    pool = [asset("last_rb", value=100), asset("pick", "PICK", 500, is_pick=True)]
    result = utility(["last_rb"], ["pick"], pool, points={"last_rb": 20},
                     explicit_outlook="rebuilder")
    assert result["normalized_gain"] > 0
    protected = evaluate(viewer=Team("me", ("last_rb",)), partner=Team("them", ("pick",)),
                         give=["last_rb"], receive=["pick"], assets={a.id: a for a in pool},
                         rules=Rules(("RB",), "observed", 30))
    protected["teams"]["me"]["outlook_utility"] = result
    assert "deficits:RB" in protected["teams"]["me"]["blockers"]
    assert protected["status"] == "blocked"
    assert not protected["eligible"]
    assert "eligible" not in result


@pytest.mark.parametrize("explicit,expected", [("championship", "championship"),
    ("contender", "contender"), ("not_sure", "balanced"), ("balanced", "balanced"),
    ("rebuilder", "rebuilder"), ("jets", "jets")])
def test_every_explicit_outlook_including_uncertain_wins(explicit, expected):
    resolved = resolve_outlook(explicit=explicit, inferred="contender", inference_fresh=True)
    assert resolved == {"value": expected, "source": "explicit", "confidence": 1.0,
                        "reason": "manager_declared_outlook", "uncertainties": []}


def test_fresh_inference_has_lower_confidence_and_cannot_infer_extremes():
    for inferred, expected in (("championship", "contender"), ("jets", "rebuilder")):
        result = resolve_outlook(inferred=inferred, inference_fresh=True)
        assert result["value"] == expected
        assert result["source"] == "inferred"
        assert result["confidence"] == .5
        assert "manager_intent_inferred" in result["uncertainties"]


@pytest.mark.parametrize("kwargs", [{}, {"inferred": "rebuilder"},
    {"inferred": "contender", "inference_fresh": False},
    {"inferred": "invalid", "inference_fresh": True},
    {"explicit": "invalid", "inferred": "contender", "inference_fresh": True}])
def test_missing_stale_or_invalid_intent_is_conservative(kwargs):
    result = resolve_outlook(**kwargs)
    assert result["value"] == "balanced"
    assert result["source"] == "fallback"
    assert result["confidence"] == .25
    assert result["uncertainties"]


def test_loss_of_outlook_provenance_is_not_treated_as_explicit_intent():
    pool = [asset("old"), asset("new", value=200)]
    result = utility(["old"], ["new"], pool, explicit_outlook=None,
                     before=Team("me", ("old",), outlook="jets"))
    assert result["outlook"]["source"] == "fallback"
    assert result["outlook"]["value"] == "balanced"


def test_missing_projections_retains_only_weighted_dynasty_with_low_confidence():
    result = utility(["old"], ["new"], [asset("old"), asset("new", value=200)])
    assert result["basis"] == "dynasty_only"
    assert result["normalized_gain"] == .25 * .5
    assert result["confidence"] == .25 * .5
    production = result["components"]["current_production"]
    assert production["before"] is production["after"] is production["normalized_gain"] is None
    assert production["unit"] is None
    assert result["components"]["future_assets"]["unit"] == "dynasty_value"
    assert "projections_unavailable" in result["uncertainties"]
    assert not result["ready_for_enforcement"]
    proxy = result["components"]["lineup_dynasty_proxy"]
    assert (proxy["before"], proxy["after"], proxy["delta"]) == (100, 200, 100)
    assert proxy["basis"] == "starting_lineup_dynasty_proxy"
    assert proxy["unit"] == "dynasty_value"
    assert proxy["weight"] == 0


def test_pure_current_outlook_without_projections_has_no_measured_gain():
    result = utility(["old"], ["new"], [asset("old"), asset("new", value=200)],
                     explicit_outlook="championship")
    assert result["normalized_gain"] is None
    assert result["confidence"] == 0
    assert result["components"]["future_assets"]["delta"] == 100


@pytest.mark.parametrize("override,code", [({"projections_fresh": False}, "projections_stale_or_unknown"),
    ({"projection_basis": None}, "projection_basis_missing"),
    ({"projection_unit": "dynasty_value"}, "projection_units_unsupported_or_missing"),
    ({"projection_unit": None}, "projection_units_unsupported_or_missing")])
def test_projections_require_freshness_source_and_real_point_units(override, code):
    result = utility(["old"], ["new"], [asset("old"), asset("new")],
                     points={"old": 10, "new": 20}, **override)
    assert result["basis"] == "dynasty_only"
    assert result["components"]["current_production"]["delta"] is None
    assert code in result["uncertainties"]
    assert not result["ready_for_enforcement"]


def test_missing_bench_projection_is_unknown_not_zero_or_dynasty_imputation():
    result = utility(["starter", "bench"], ["new", "bench"],
                     [asset("starter"), asset("bench", value=1), asset("new")],
                     points={"starter": 10, "new": 20})
    assert result["basis"] == "dynasty_only"
    assert result["components"]["current_production"]["missing_player_ids"] == ["bench"]
    assert "projections_incomplete" in result["uncertainties"]


@pytest.mark.parametrize("missing", ["outgoing", "incoming"])
def test_projection_coverage_includes_players_unique_to_either_roster(missing):
    points = {"outgoing": 15, "incoming": 20}
    del points[missing]
    result = utility(["outgoing"], ["incoming"],
                     [asset("outgoing"), asset("incoming"), asset("outside_rosters")], points=points)
    assert result["components"]["current_production"]["missing_player_ids"] == [missing]
    assert result["components"]["current_production"]["normalized_gain"] is None
    assert not result["ready_for_enforcement"]


def test_assignment_uses_real_projections_and_does_not_reuse_flex_players():
    pool = [asset("expensive", value=999), asset("efficient", value=5),
            asset("dual", "RB+WR", 10), asset("new", "WR", 100)]
    points = {"expensive": 2, "efficient": 20, "dual": 25, "new": 10}
    result = utility(["expensive", "efficient", "dual"], ["expensive", "efficient", "dual", "new"],
                     pool, slots=("RB", "WR", "FLEX"), points=points)
    production = result["components"]["current_production"]
    assert (production["before"], production["after"], production["delta"]) == (47, 55, 8)
    assert set(production["lineups"]["after"]) == {"efficient", "dual", "new"}


def test_real_projection_not_dynasty_startable_threshold_selects_production():
    result = utility(["old"], ["new"], [asset("old"), asset("new", startable=False)],
                     points={"old": 5, "new": 15})
    assert result["components"]["current_production"]["delta"] == 10


def test_inactive_unavailable_and_picks_have_value_but_no_current_production():
    pool = [asset("starter"), asset("ir", value=200), asset("out", value=300, available=False),
            asset("pick", "PICK", 400, is_pick=True), asset("new", value=200)]
    team = Team("me", ("starter", "ir", "out", "pick"), inactive=frozenset({"ir"}))
    result = utility([], [], pool, before=team, after=replace(team, roster=("new", "ir", "out", "pick")),
                     points={"starter": 10, "new": 15})
    assert result["components"]["current_production"]["delta"] == 5
    future = result["components"]["future_assets"]
    assert (future["before"], future["after"]) == (1000, 1100)
    assert future["picks"] == {"before": 400, "after": 400}


def test_normalization_is_bounded_scale_invariant_and_reverse_symmetric():
    pool = [asset("old", value=100), asset("new", value=200)]
    a = utility(["old"], ["new"], pool, points={"old": 10, "new": 20})
    scaled = utility(["old"], ["new"], [replace(p, value=p.value * .001) for p in pool],
                     points={"old": 170, "new": 340}, projection_unit="fantasy_points_for_period")
    reverse = utility(["new"], ["old"], pool, points={"old": 20, "new": 10})
    mirror = utility(["new"], ["old"], pool, points={"old": 10, "new": 20})
    assert a["normalized_gain"] == pytest.approx(scaled["normalized_gain"])
    assert a["normalized_gain"] == pytest.approx(-mirror["normalized_gain"])
    for result in (a, scaled, reverse, mirror):
        assert -1 <= result["normalized_gain"] <= 1
        assert 0 <= result["confidence"] <= 1


@pytest.mark.parametrize("old,new,expected", [(0, 0, 0), (0, 100, 1), (100, 0, -1)])
def test_zero_baselines_have_finite_dimensionless_normalization(old, new, expected):
    result = utility(["old"], ["new"], [asset("old", value=old), asset("new", value=new)],
                     points={"old": old, "new": new})
    assert result["normalized_gain"] == expected
    json.dumps(result, allow_nan=False)


def test_deduplicates_roster_and_does_not_reward_picks_or_depth_twice():
    pool = [asset("starter", "RB+WR", 100), asset("bench", "RB+WR", 50),
            asset("pick", "PICK", 50, is_pick=True)]
    result = utility(["starter"], ["starter", "bench", "pick", "pick", "bench"], pool)
    future, depth = (result["components"][name] for name in ("future_assets", "depth"))
    assert (future["before"], future["after"]) == (100, 200)
    assert depth["after"] == 1
    assert depth["weight"] == 0
    assert result["normalized_gain"] == .25 * .5
    assert "duplicate_roster_asset_deduplicated" in result["uncertainties"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True])
def test_invalid_dynasty_values_do_not_escape_as_json_numbers(bad):
    result = utility(["old"], ["new"], [asset("old"), asset("new", value=bad)])
    assert result["normalized_gain"] is None
    assert "invalid_dynasty_asset" in result["uncertainties"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True])
def test_invalid_projection_leaves_honest_dynasty_fallback(bad):
    result = utility(["old"], ["new"], [asset("old"), asset("new")], points={"old": 10, "new": bad})
    assert result["basis"] == "dynasty_only"
    assert "projections_invalid" in result["uncertainties"]
    json.dumps(result, allow_nan=False)


def test_unresolved_roster_or_mismatched_manager_cannot_claim_whole_team_gain():
    for override, code in (({}, "unresolved_roster_asset"),
                           ({"after": Team("someone_else", ("old",))}, "manager_mismatch")):
        result = utility(["old"], ["unknown"], [asset("old")], **override)
        assert result["normalized_gain"] is None
        assert result["confidence"] == 0
        assert code in result["uncertainties"]


def test_unknown_slots_do_not_manufacture_production_or_depth():
    result = utility(["old"], ["new"], [asset("old"), asset("new")],
                     slots=("IDP_FLEX",), points={"old": 10, "new": 20})
    assert result["basis"] == "dynasty_only"
    assert result["components"]["current_production"]["before"] is None
    assert result["components"]["depth"]["before"] is None
    assert "unsupported_or_missing_lineup" in result["uncertainties"]


def test_uncertainty_reduces_confidence_and_inputs_are_unchanged():
    before = Team("me", ("old",), availability_known=False)
    after = replace(before, roster=("new",))
    args = dict(before=before, after=after, assets={p.id: p for p in [asset("old"), asset("new")]},
                rules=Rules(("RB",), "estimated", uncertainties=("availability_stale_or_unknown",)),
                inferred_outlook="contender", inference_fresh=True)
    saved = deepcopy(args)
    result = evaluate_outlook_utility(**args)
    assert args == saved
    assert evaluate_outlook_utility(**args) == result
    assert 0 < result["confidence"] < .125
    assert "availability_unknown" in result["uncertainties"]
    assert not result["ready_for_enforcement"]


@pytest.mark.parametrize("overrides", [
    {"explicit_outlook": None},
    {"explicit_outlook": None, "inferred_outlook": "contender", "inference_fresh": True},
    {"before": Team("me", ("old",), availability_known=False)},
    {"rules": Rules(("RB",), "estimated", 30)},
    {"rules": Rules(("RB",), "observed", 30, uncertainties=("availability_stale_or_unknown",))},
])
def test_uncertain_intent_or_roster_cannot_enable_strict_gate_even_with_points(overrides):
    result = utility(["old"], ["new"], [asset("old"), asset("new")],
                     points={"old": 10, "new": 20}, **overrides)
    assert result["normalized_gain"] > 0
    assert not result["ready_for_enforcement"]
