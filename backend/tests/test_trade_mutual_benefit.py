"""Item 3: docs/plans/trade-model-activation/mutual-benefit.md.

Pins maximin whole-team ranking, total/shape ties, mirrored outcomes, honest
unknown preference evidence, zero tolerance, finite output and lane handoff.
No generator, server, DB, flags, or acceptance model is needed by the helper.
"""
from copy import deepcopy
import json
import math
import random
import sys
from types import MappingProxyType, SimpleNamespace

import pytest

from backend import trade_mutual_benefit as mb


def benefit(gain, confidence=0.9, basis="whole_team_outlook_proxy"):
    return {"normalized_gain": gain, "confidence": confidence, "basis": basis,
            "ready_for_enforcement": True,
            "components": {"starter_delta": 0.02, "future_delta": 0.03},
            "reason": None, "uncertainty": ["not_an_acceptance_probability"]}


def observed(a, b, **kwargs):
    return mb.evaluate_mutual_benefit(
        benefit(a), benefit(b), viewer_preference_source="observed",
        partner_preference_source="observed", **kwargs)


def key(result, give=1, receive=1):
    return mb.rank_key(result, give_count=give, receive_count=receive)


def test_large_win_cannot_hide_the_other_managers_loss():
    losing = observed(1000, -0.04)
    winning = observed(0.02, 0.03)
    assert losing["total_gain"] > winning["total_gain"]
    assert losing["weaker_gain"] == -0.04
    assert losing["status"] == "blocked"
    assert losing["reason"] == "mutual_negative_gain"
    assert not losing["eligible"] and not losing["fallback_candidate"]
    assert key(winning) < key(losing)


def test_two_positive_asymmetric_gains_rank_by_the_weaker_manager_first():
    asymmetric = observed(0.015, 0.8)
    balanced = observed(0.03, 0.04)
    assert asymmetric["eligible"] and balanced["eligible"]
    assert asymmetric["total_gain"] > balanced["total_gain"]
    # Even extra assets cannot move simplicity ahead of a greater weak gain.
    assert key(balanced, 3, 3) < key(asymmetric)


def test_total_gain_breaks_equal_weak_benefit_before_package_size():
    a, b = observed(0.02, 0.03), observed(0.02, 0.06)
    assert key(b, 3, 3) < key(a)


def test_equal_benefits_prefer_fewer_assets_then_less_imbalance():
    result = observed(0.03, 0.03)
    assert key(result, 1, 1) < key(result, 1, 2) < key(result, 2, 2)
    assert key(result, 2, 2) < key(result, 1, 3)
    assert key(result, 1, 2) == key(result, 2, 1)
    assert key(result) == (0, -0.03, -0.06, 2, 0)


def test_more_gain_on_the_weaker_side_never_worsens_rank():
    keys = [key(observed(gain, 0.2)) for gain in (0.01, 0.02, 0.03, 0.1, 0.2)]
    assert keys == sorted(keys, reverse=True)


@pytest.mark.parametrize("gains,sources,confidences", [
    ((0.02, 0.2), ("observed", "observed"), (0.9, 0.6)),
    ((0.02, 0.2), ("observed", "unknown"), (0.9, 0.9)),
    ((-0.04, None), ("estimated", "unknown"), (0.2, 0)),
    ((0, 0.2), ("unknown", "observed"), (0, 1)),
    ((float("nan"), 0.2), ("observed", "observed"), (1, 1)),
    ((sys.float_info.max, sys.float_info.max), ("observed", "observed"), (1, 1)),
])
def test_mirrored_sides_preserve_every_aggregate_and_reverse_only_side_evidence(gains, sources, confidences):
    a, b = (benefit(gain, conf) for gain, conf in zip(gains, confidences))
    forward = mb.evaluate_mutual_benefit(a, b, viewer_preference_source=sources[0],
                                       partner_preference_source=sources[1])
    mirror = mb.evaluate_mutual_benefit(b, a, viewer_preference_source=sources[1],
                                      partner_preference_source=sources[0])
    assert key(forward, 1, 3) == key(mirror, 3, 1)
    assert forward == {**mirror, "sides": {"viewer": mirror["sides"]["partner"],
                                         "partner": mirror["sides"]["viewer"]}}


def test_missing_preferences_are_not_inferred_from_personal_sounding_basis():
    result = mb.evaluate_mutual_benefit(benefit(0.03, 1, "personal"), benefit(0.03, 1, "personal"))
    assert result["status"] == "unknown" and not result["eligible"]
    assert result["fallback_candidate"]
    assert result["confidence"] == 0.25
    assert result["reason"] == "mutual_evidence_incomplete"
    assert "mutual_preferences_unknown" in result["reasons"]
    assert all(s["preference_source"] == "unknown" for s in result["sides"].values())


def test_one_observed_board_and_no_opponent_preferences_remain_useful_fallback():
    fallback = mb.evaluate_mutual_benefit(benefit(0.1), benefit(0.2, 0.8, "consensus_proxy"),
                                        viewer_preference_source="observed")
    assert fallback["fallback_candidate"] and not fallback["eligible"]
    assert fallback["confidence"] == 0.25
    assert fallback["weaker_gain"] == 0.1
    assert fallback["sides"]["partner"]["basis"] == "consensus_proxy"
    stronger_fallback = mb.evaluate_mutual_benefit(benefit(0.2), benefit(0.3))
    assert key(observed(0.01, 0.01)) < key(stronger_fallback) < key(fallback)


def test_estimated_preferences_cannot_become_observed_by_lowering_confidence_threshold():
    estimated = mb.evaluate_mutual_benefit(benefit(0.03, 1), benefit(0.04, 1),
        viewer_preference_source="observed", partner_preference_source="estimated",
        minimum_confidence=0.1)
    assert estimated["confidence"] == 0.5
    assert estimated["status"] == "unknown" and estimated["fallback_candidate"]
    assert "mutual_preferences_estimated" in estimated["reasons"]
    assert estimated["sides"]["partner"]["preference_source"] == "estimated"


def test_low_confidence_does_not_change_the_sign_or_inflate_benefit():
    result = mb.evaluate_mutual_benefit(benefit(0.03), benefit(0.2, 0.05),
        viewer_preference_source="observed", partner_preference_source="observed")
    assert result["status"] == "unknown" and result["fallback_candidate"]
    assert result["confidence"] == 0.05 and result["weaker_gain"] == 0.03
    assert result["total_gain"] == pytest.approx(0.23)
    assert "mutual_low_confidence" in result["reasons"]
    negative = mb.evaluate_mutual_benefit(benefit(1), benefit(-0.1, 0))
    assert negative["status"] == "blocked" and negative["weaker_gain"] == -0.1


def test_confidence_is_an_evidence_gate_not_an_extra_sort_objective():
    strong = observed(0.03, 0.1)
    adequate = mb.evaluate_mutual_benefit(benefit(0.03, 0.5), benefit(0.1, 0.5),
        viewer_preference_source="observed", partner_preference_source="observed")
    assert adequate["eligible"] and key(adequate) == key(strong)


@pytest.mark.parametrize("other", [None, {}, benefit(None), benefit(float("nan"))])
def test_unknown_benefit_is_not_zero_and_does_not_hide_a_known_loss(other):
    unknown = mb.evaluate_mutual_benefit(benefit(0.03), other)
    assert unknown["status"] == "unknown" and not unknown["fallback_candidate"]
    assert unknown["weaker_gain"] is None and unknown["total_gain"] is None
    assert unknown["sides"]["partner"]["normalized_gain"] is None
    loss = mb.evaluate_mutual_benefit(benefit(-0.03), other)
    assert loss["status"] == "blocked" and loss["reason"] == "mutual_negative_gain"


@pytest.mark.parametrize("delta", [-0.3, 0.0, 0.3])
@pytest.mark.parametrize("override", [
    {"ready_for_enforcement": False}, {"ready_for_enforcement": None},
    {"ready_for_enforcement": 1}, {"ready_for_enforcement": "true"},
    {"basis": "dynasty_only"}, {"basis": "unavailable"}, {"basis": "unknown"},
    {"basis": None}, {"basis": ""},
])
def test_partial_utility_never_establishes_whole_team_harm_or_gain(delta, override):
    partial = {**benefit(delta), **override}
    result = mb.evaluate_mutual_benefit(benefit(0.1), partial,
        viewer_preference_source="observed", partner_preference_source="observed")
    assert result["status"] == "unknown" and not result["fallback_candidate"]
    assert result["weaker_gain"] is None and result["total_gain"] is None
    assert result["reasons"] == ["mutual_low_confidence", "mutual_utility_incomplete"]
    assert result["confidence"] == 0
    assert result["sides"]["partner"]["reported_gain"] == delta
    assert result["sides"]["partner"]["normalized_gain"] is None
    mirror = mb.evaluate_mutual_benefit(partial, benefit(0.1),
        viewer_preference_source="observed", partner_preference_source="observed")
    assert key(result) == key(mirror)


def test_missing_readiness_is_unknown_and_complete_negative_still_blocks():
    partial = benefit(-0.2)
    partial.pop("ready_for_enforcement")
    result = mb.evaluate_mutual_benefit(benefit(0.1), partial)
    assert result["status"] == "unknown"
    assert "mutual_negative_gain" not in result["reasons"]
    complete_loss = mb.evaluate_mutual_benefit(benefit(-0.01), partial)
    assert complete_loss["status"] == "blocked"
    assert complete_loss["reason"] == "mutual_negative_gain"


@pytest.mark.parametrize("gain,status,reason", [
    (-2e-9, "blocked", "mutual_negative_gain"),
    (-0.5e-9, "blocked", "mutual_gain_below_minimum"),
    (-0.0, "blocked", "mutual_gain_below_minimum"),
    (0.5e-9, "blocked", "mutual_gain_below_minimum"),
    (0.005, "blocked", "mutual_gain_below_minimum"),
    (0.01 - 2e-9, "blocked", "mutual_gain_below_minimum"),
    (0.01 - 0.5e-9, "eligible", "mutual_meaningful_gain"),
    (0.01, "eligible", "mutual_meaningful_gain"),
    (0.01 + 2e-9, "eligible", "mutual_meaningful_gain"),
])
def test_zero_and_meaningful_threshold_have_absolute_tolerance(gain, status, reason):
    result = observed(gain, 0.2)
    assert result["status"] == status and result["reason"] == reason
    if abs(gain) <= mb.TOLERANCE:
        assert result["weaker_gain"] == 0.0


def test_thresholds_are_explicit_and_do_not_relax_simplicity_or_sign_rules():
    assert observed(0.015, 0.1)["eligible"]
    assert not observed(0.015, 0.1, minimum_gain=0.02)["eligible"]
    assert observed(0.1, 0.1, minimum_confidence=0.95)["status"] == "unknown"
    assert not observed(-1e-12, 0.1, tolerance=0)["eligible"]


@pytest.mark.parametrize("overrides", [
    {"minimum_gain": 0}, {"minimum_gain": -1}, {"minimum_gain": float("nan")},
    {"minimum_gain": float("inf")}, {"minimum_gain": True},
    {"minimum_gain": 1e-9}, {"tolerance": -1}, {"tolerance": float("inf")},
    {"minimum_confidence": 0}, {"minimum_confidence": 1.01},
    {"minimum_confidence": float("nan")}, {"minimum_confidence": "0.5"},
])
def test_invalid_configuration_fails_explicitly(overrides):
    with pytest.raises(ValueError):
        observed(0.1, 0.1, **overrides)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"),
                                  10 ** 400, True, "0.1", [], {}])
def test_bad_gain_is_unknown_and_output_is_finite_json(bad):
    result = mb.evaluate_mutual_benefit(benefit(bad), benefit(0.1))
    assert result["status"] == "unknown" and not result["fallback_candidate"]
    assert result["sides"]["viewer"]["normalized_gain"] is None
    assert "mutual_gain_invalid" in result["reasons"]
    json.dumps(result, allow_nan=False)
    assert all(math.isfinite(n) for n in key(result))


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -1, 1.1, True, "1"])
def test_invalid_confidence_cannot_pass_even_with_observed_preferences(bad):
    result = mb.evaluate_mutual_benefit(benefit(0.1, bad), benefit(0.2),
        viewer_preference_source="observed", partner_preference_source="observed")
    assert result["status"] == "unknown" and result["confidence"] == 0
    assert not result["fallback_candidate"]
    assert "mutual_confidence_invalid" in result["reasons"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("bad_source", [None, "personal", "consensus", True, {}, []])
def test_unrecognized_provenance_is_unknown(bad_source):
    result = mb.evaluate_mutual_benefit(benefit(0.1), benefit(0.2),
                                      partner_preference_source=bad_source)
    assert result["status"] == "unknown"
    assert "mutual_preference_source_invalid" in result["reasons"]
    assert result["sides"]["partner"]["preference_source"] == "unknown"


def test_extreme_finite_gains_saturate_total_without_changing_sign_or_eligibility():
    huge = sys.float_info.max
    positive, negative, mixed = observed(huge, huge), observed(-huge, -huge), observed(huge, -huge)
    assert positive["eligible"] and positive["total_gain"] == huge
    assert negative["status"] == mixed["status"] == "blocked"
    assert negative["total_gain"] == -huge and mixed["total_gain"] == 0
    for result in (positive, negative):
        assert result["numeric_notes"] == ["mutual_total_saturated"]
    for result in (positive, negative, mixed):
        json.dumps(result, allow_nan=False)
        assert all(math.isfinite(n) for n in key(result))


def test_repeated_calls_are_pure_and_seeded_sort_is_symmetric_for_many_candidates():
    original = benefit(0.03)
    saved = deepcopy(original)
    result = mb.evaluate_mutual_benefit(MappingProxyType(original), original)
    assert mb.evaluate_mutual_benefit(original, original) == result
    result["sides"]["viewer"]["reasons"].append("changed")
    assert original == saved
    rng = random.Random(812)
    for _ in range(100):
        a, b = rng.uniform(-0.05, 0.5), rng.uniform(-0.05, 0.5)
        n, m = rng.randint(1, 4), rng.randint(1, 4)
        assert key(observed(a, b), n, m) == key(observed(b, a), m, n)


@pytest.mark.parametrize("give,receive", [(0, 1), (1, 0), (-1, 2), (True, 1), (1.5, 2), (1, None)])
def test_invalid_package_counts_are_not_ranked_as_simple(give, receive):
    with pytest.raises(ValueError):
        key(observed(0.03, 0.04), give, receive)


def test_order_handoff_keeps_market_lanes_and_realized_conviction_quota(monkeypatch):
    from backend import trade_policy as tp

    knobs = {"deck_core_lead_cards": 3, "conviction_deck_share": 0.2, "deck_core_min_share": 0.7}
    monkeypatch.setattr(tp, "_c", knobs.__getitem__)
    entries = []
    for lane, count, gain in ((tp.LANE_CORE, 8, 0.03), (tp.LANE_CONVICTION, 5, 0.2),
                              (tp.LANE_FALLBACK, 3, 0.5)):
        for i in range(count):
            card = SimpleNamespace(benefit=observed(gain + i / 100, gain + i / 100))
            entries.append((card, SimpleNamespace(lane=lane)))
    entries.sort(key=lambda entry: key(entry[0].benefit))
    kept, dropped = tp.compose_deck(entries, size=10)
    lanes = [policy.lane for _, policy in kept]
    assert lanes[:3] == [tp.LANE_CORE] * 3
    assert lanes.count(tp.LANE_CONVICTION) == 2
    assert lanes.count(tp.LANE_CORE) == 8 and tp.LANE_FALLBACK not in lanes
    assert dropped
    core_keys = [key(c.benefit) for c, r in kept if r.lane == tp.LANE_CORE]
    assert core_keys == sorted(core_keys)


def test_no_board_only_supply_retains_existing_fallback_composition(monkeypatch):
    from backend import trade_policy as tp

    knobs = {"deck_core_lead_cards": 3, "conviction_deck_share": 0.2, "deck_core_min_share": 0.7}
    monkeypatch.setattr(tp, "_c", knobs.__getitem__)
    # Current composition sheds Conviction for Core shortfall, not Fallback.
    entries = [(object(), SimpleNamespace(lane=tp.LANE_FALLBACK)) for _ in range(4)]
    kept, dropped = tp.compose_deck(entries, size=10)
    assert kept == entries and not dropped
