"""Synthetic exact-term regressions for the separately versioned candidate.

These are behavioral fixtures, not acceptance annotations or probability tests.
"""

from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json

import pytest

from backend import feature_flags as ff, trade_service as ts
from backend import trade_gen_bilateral as incumbent
from backend import trade_gen_bilateral_candidate as candidate
from backend.tests.test_bilateral_contracts import favorable, world, package, packages


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    ts._cfg.update(age_pref_mult_u23=1.0, age_pref_mult_30plus=1.0)


def terms(args, give, receive):
    return ts.TradeCard("fixture", args["league"].league_id, args["user_id"],
                        "partner", "Partner", list(give), list(receive), 0, 0, 0)


def proof(args, give, receive):
    return candidate.evaluate_bilateral_trade(terms(args, give, receive), **args)


def test_incumbent_frozen_card_and_report_byte_parity():
    cards, report = incumbent.generate_bilateral_trades(**favorable())
    encoded = [asdict(c) for c in cards]
    for card in encoded:
        for key in ("trade_id", "created_at", "expires_at"):
            card[key] = "variable-occurrence"
    report = report.as_dict()
    # The parent's config registration is intentionally outside generator parity.
    report["config"].pop("owner_bilateral_revision_enabled", None)
    digest = hashlib.sha256(json.dumps([encoded, report], sort_keys=True).encode()).hexdigest()
    assert digest == "608aba2e6362d1148515cda183aa2822c50b0282bff5b29aa377baf55cc1b302"


def test_candidate_version_agrees_and_does_not_mutate_input_or_incumbent():
    args = favorable()
    before = deepcopy(args)
    cards, report = candidate.generate_bilateral_trades(**args)
    assert args == before
    assert cards and candidate.VERSION == "owner-v2-bilateral-2"
    assert report.as_dict()["generator_version"] == candidate.VERSION
    for card, decision in zip(cards, candidate.evaluate_bilateral_trades(cards, **args)):
        assert decision.eligible and decision.matches(card)
        assert decision.as_dict() == card.owner_evaluation.as_dict()
        assert decision.as_dict()["generator_version"] == candidate.VERSION
    assert incumbent.VERSION == "owner-v2-bilateral-1"


def companion_world(*, useful=False, **kwargs):
    return world(own=("give", "extra"),
        market={"give": 1000., "target": 1000., "extra": 150.},
        viewer={"give": 700., "target": 1400., "extra": 150.},
        partner={"give": 1600., "target": 600., "extra": 600. if useful else 150.},
        **kwargs)


def test_needless_companion_is_retained_but_efficient_terms_rank_first():
    args = companion_world()
    cards, _ = candidate.generate_bilateral_trades(**args)
    assert packages(cards) >= {package(["give"], ["target"]), package(["give", "extra"], ["target"])}
    assert cards[0].give_player_ids == ["give"]
    larger = proof(args, ["give", "extra"], ["target"]).as_dict()
    assert larger["term_efficiency"]["avoidable_companions"] == ["extra"]
    assert larger["term_efficiency"]["efficient"] is False


def test_real_counterparty_preference_benefit_preserves_distinct_companion():
    args = companion_world(useful=True)
    decision = proof(args, ["give", "extra"], ["target"])
    assert decision.eligible
    assert decision.as_dict()["term_efficiency"]["efficient"] is True
    assert decision.as_dict()["term_efficiency"]["useful_companions"][0]["benefits"] == ["known_personal_target"]


def test_stronger_focal_liking_does_not_raise_preferred_asking_terms():
    args = companion_world()
    before, _ = candidate.generate_bilateral_trades(**args)
    args["user_elo"]["target"] = ts.value_to_elo(100000.)
    after, _ = candidate.generate_bilateral_trades(**args)
    assert packages(before) == packages(after)
    assert before[0].give_player_ids == after[0].give_player_ids == ["give"]
    assert before[0].give_value == after[0].give_value
    assert proof(args, ["give", "extra"], ["target"]).as_dict()["term_efficiency"]["efficient"] is False


def test_more_expensive_neutral_consideration_is_not_preferred_for_same_target():
    args = world(own=("cheap", "costly"),
        market={"cheap": 1000., "costly": 1150., "target": 1000.},
        viewer={"cheap": 700., "costly": 700., "target": 1600.},
        partner={"cheap": 1400., "costly": 1400., "target": 600.})
    before, _ = candidate.generate_bilateral_trades(**args)
    args["user_elo"]["target"] = ts.value_to_elo(100000.)
    after, _ = candidate.generate_bilateral_trades(**args)
    assert before[0].give_player_ids == after[0].give_player_ids == ["cheap"]
    assert package(["costly"], ["target"]) in packages(before)


def test_constructor_to_survivor_presentment_keeps_price_under_preference_perturbation():
    from backend.trade_bilateral_presentment import present
    args = world(own=("cheap", "costly"),
        market={"cheap": 1000., "costly": 1150., "target": 1000.},
        viewer={"cheap": 700., "costly": 700., "target": 1600.},
        partner={"cheap": 1400., "costly": 1400., "target": 600.})
    for target_liking in (1600., 100000.):
        args["user_elo"]["target"] = ts.value_to_elo(target_liking)
        cards, _ = candidate.generate_bilateral_trades(**args)
        # Both synthetic players qualify individually; these are final survivors.
        survivors = [c for c in cards if c.receive_player_ids == ["target"]]
        before = {id(c): c.owner_evaluation.snapshot_json for c in survivors}
        presented, _ = present(survivors)
        assert presented[0].give_player_ids == ["cheap"]
        assert {id(c): c.owner_evaluation.snapshot_json for c in presented} == before


def test_term_precedence_preserves_real_partner_benefit_and_unknown_boards():
    args = world(own=("cheap", "costly"),
        market={"cheap": 1000., "costly": 1150., "target": 1000.},
        viewer={"cheap": 700., "costly": 700., "target": 100000.},
        partner={"cheap": 1400., "costly": 1800., "target": 600.})
    for missing_board in (False, True):
        if missing_board:
            args["opponent_sources"] = {"partner": {}}
        cards, _ = candidate.generate_bilateral_trades(**args)
        assert packages(cards) >= {package(["cheap"], ["target"]), package(["costly"], ["target"])}
        assert candidate.term_precedence(cards) == {}


def test_term_precedence_never_compares_unrelated_focal_deals():
    first_args = favorable()
    first, _ = candidate.generate_bilateral_trades(**first_args)
    second_args = world(own=("other_give",), other=("other_target",),
        viewer={"other_give": 700., "other_target": 1400.},
        partner={"other_give": 1400., "other_target": 700.})
    second, _ = candidate.generate_bilateral_trades(**second_args)
    assert first and second
    assert candidate.term_precedence(first + second) == {}


@pytest.mark.parametrize("defect", ["market_loss", "profile", "manager", "personal_nan", "availability", "version"])
def test_term_precedence_fails_closed_on_malformed_private_evidence(defect):
    cards, _ = candidate.generate_bilateral_trades(**favorable())
    card = cards[0]
    data = card.owner_evaluation.as_dict()
    if defect == "market_loss":
        del data["term_efficiency"]["worst_adjusted_market_loss"]
    elif defect == "profile":
        del data["viewer"]["consideration_profile"]
    elif defect == "manager":
        data["viewer"]["consideration_profile"]["manager_id"] = "different_manager"
    elif defect == "personal_nan":
        data["viewer"]["consideration_profile"]["raw_outgoing_personal"] = float("nan")
    elif defect == "availability":
        data["viewer"]["consideration_profile"]["availability_shape"] = [None, None]
    else:
        data["term_efficiency"]["ordering_version"] = "unknown"
    card.owner_evaluation = replace(card.owner_evaluation, snapshot_json=json.dumps(data))
    assert candidate.term_precedence(cards) == {}
    assert not candidate.term_evidence_valid(data, user_id="viewer", target_user_id="partner")


def test_mirror_preserves_each_managers_support_plan_and_term_efficiency():
    args = companion_world()
    original = proof(args, ["give", "extra"], ["target"]).as_dict()
    reverse = deepcopy(args)
    member = args["league"].members[0]
    reverse.update(user_id="partner", user_roster=list(member.roster),
        user_elo=dict(member.elo_ratings), user_sources=dict(member.confidence_sources),
        opponent_sources={"viewer": args["user_sources"]},
        opponent_outlooks={"viewer": args["outlook"]})
    reverse["league"].members = [ts.LeagueMember("viewer", "Viewer", args["user_roster"],
        args["user_elo"], True, confidence_sources=args["user_sources"])]
    mirrored = ts.TradeCard("mirror", args["league"].league_id, "partner", "viewer", "Viewer",
                           ["target"], ["extra", "give"], 0, 0, 0)
    decision = candidate.evaluate_bilateral_trade(mirrored, **reverse)
    assert decision.eligible
    data = decision.as_dict()
    assert original["viewer"] == data["counterparty"]
    assert original["counterparty"] == data["viewer"]
    assert original["bilateral"] == data["bilateral"]
    for key in ("efficient", "avoidable_companions", "useful_companions", "worst_adjusted_market_loss"):
        assert original["term_efficiency"][key] == data["term_efficiency"][key]


def test_asset_permutation_does_not_change_semantic_evaluation_or_rank():
    args = companion_world(useful=True)
    first = proof(args, ["give", "extra"], ["target"]).as_dict()
    second = proof(args, ["extra", "give"], ["target"]).as_dict()
    for key in ("market", "viewer", "counterparty", "bilateral", "term_efficiency"):
        assert first[key] == second[key]
    before, _ = candidate.generate_bilateral_trades(**args)
    args["user_roster"].reverse()
    args["user_elo"] = dict(reversed(list(args["user_elo"].items())))
    after, _ = candidate.generate_bilateral_trades(**args)
    assert [(set(c.give_player_ids), set(c.receive_player_ids)) for c in before] == [
        (set(c.give_player_ids), set(c.receive_player_ids)) for c in after]


def test_missing_starter_projection_is_unknown_and_proxy_is_named():
    args = favorable(outlook="contending")
    args["manager_preferences"] = {"viewer": {"starter_slots": ["WR", "FLEX"]}}
    data = proof(args, ["give"], ["target"]).as_dict()
    for side in ("viewer", "counterparty"):
        evidence = data[side]["starter_evidence"]
        assert evidence["state"] == "unknown"
        assert evidence["projected_starter_delta"] is None
        assert evidence["proxy"] == "market_usable_depth_v1"
        assert "usable_roster_improvement" not in data[side]["benefits"]


def test_unknown_counterparty_is_never_known_and_evidence_stays_private():
    args = favorable()
    args["opponent_sources"] = {"partner": {}}
    cards, report = candidate.generate_bilateral_trades(**args)
    assert cards
    for card in cards:
        data = card.owner_evaluation.as_dict()
        assert data["counterparty"]["preference_evidence"]["state"] == "unknown"
        assert data["bilateral"]["score_kind"] == "interpretable_support_not_probability"
        assert "term_efficiency" not in card.match_context
    assert report.as_dict()["elapsed_seconds"] >= 0


@pytest.mark.parametrize("outlook", ["tanking", "rebuilding", "contending", "all_in"])
def test_selected_outlook_wins_and_each_manager_keeps_own_plan(outlook):
    args = favorable(outlook=outlook, inferred_outlooks={"viewer": "all_in"},
        opponent_outlooks={"partner": "contending"}, ages={"give": 29, "target": 23})
    data = proof(args, ["give"], ["target"]).as_dict()
    assert data["viewer"]["outlook"] == {"tanking": "jets", "rebuilding": "rebuilder",
        "contending": "contender", "all_in": "championship"}[outlook]
    assert data["viewer"]["outlook_source"] == "declared"
    assert data["counterparty"]["outlook"] == "contender"


def test_tanker_plan_prefers_favored_long_horizon_return_over_neutral_youth():
    args = world(own=("give",), other=("favored", "neutral"), outlook="jets",
        positions={"give": "RB"}, ages={"give": 29, "favored": 23, "neutral": 23},
        viewer={"give": 700., "favored": 1600., "neutral": 1000.},
        partner={"give": 1500., "favored": 700., "neutral": 700.})
    liked = proof(args, ["give"], ["favored"]).as_dict()["viewer"]
    neutral = proof(args, ["give"], ["neutral"]).as_dict()["viewer"]
    assert liked["team_plan_gain"] > neutral["team_plan_gain"]
    assert liked["plan_composition"]["incoming"]["favored_horizon_player_share"] == 1.
    assert neutral["plan_composition"]["incoming"]["favored_horizon_player_share"] == 0.
    assert liked["plan_composition"]["outgoing"]["rb_share"] == 1.


@pytest.mark.parametrize("age,discount,allowed", [(22, True, True), (22, False, False), (None, True, False)])
def test_discounted_rb_prospect_exception_is_preserved(age, discount, allowed):
    args = world(market={"give": 850. if discount else 1000., "target": 1000.},
        viewer={"give": 600., "target": 1500.}, partner={"give": 1500., "target": 700.},
        positions={"target": "RB"}, ages={"give": 29, "target": age}, outlook="jets")
    assert bool(candidate.generate_bilateral_trades(**args)[0]) is allowed


@pytest.mark.parametrize("tier", ["firsts_2", "firsts_3", "firsts_4plus"])
def test_elite_rb_personal_tier_exception_is_preserved(tier):
    from backend.ranking_service import RankingService
    low, high = RankingService.tier_bands_for("RB", "1qb_ppr")[tier]
    args = world(viewer={"give": 700., "target": ts.elo_to_value((low + high) / 2)},
        partner={"give": 1500., "target": 700.}, positions={"target": "RB"},
        ages={"give": 29, "target": 27}, outlook="jets")
    assert candidate.generate_bilateral_trades(**args)[0]


def test_favored_young_asset_protection_is_preserved():
    args = world(viewer={"give": 1600., "target": 1000.}, partner={"give": 1500., "target": 700.},
        positions={"target": "PICK"}, ages={"give": 23}, outlook="jets")
    assert not candidate.generate_bilateral_trades(**args)[0]
    assert candidate.generate_bilateral_trades(**args, pinned_give_players=["give"])[0]


def test_own_next_pick_protection_and_explicit_send_authority():
    args = world(own=("own_first",), viewer={"own_first": 800., "target": 1600.},
        partner={"own_first": 1500., "target": 700.}, positions={"own_first": "PICK"},
        ages={"target": 23}, outlook="jets", manager_preferences={"viewer": {
            "own_next_draft_pick_ids": ["own_first"]}})
    assert not candidate.generate_bilateral_trades(**args)[0]
    assert candidate.generate_bilateral_trades(**args, pinned_give_players=["own_first"], exact_give=True)[0]


def test_exact_and_partial_selection_revalidation():
    exact = companion_world(pinned_give_players=["give", "extra"], exact_give=True)
    cards, _ = candidate.generate_bilateral_trades(**exact)
    assert cards and all(c.give_player_ids == ["give", "extra"] for c in cards)
    assert all(c.owner_evaluation.as_dict()["term_efficiency"]["efficient"] for c in cards)
    args = world(own=("g1", "g2"), viewer={"g1": 700., "g2": 700., "target": 1800.},
        partner={"g1": 1500., "g2": 1500., "target": 700.},
        pinned_give_players=["g1", "g2"], pinned_receive_players=["target"])
    cards, report = candidate.generate_bilateral_trades(**args)
    assert cards and report.as_dict()["partial_search"]
    assert all(d.eligible for d in candidate.evaluate_bilateral_trades(cards, **args))
    forged = deepcopy(cards[0])
    forged.owner_evaluation = None
    assert not candidate.evaluate_bilateral_trade(forged, **args).eligible


def test_search_budgets_do_not_become_output_caps():
    own, other = tuple(f"g{i}" for i in range(11)), tuple(f"r{i}" for i in range(11))
    args = world(own=own, other=other,
        viewer={**dict.fromkeys(own, 700.), **dict.fromkeys(other, 1400.)},
        partner={**dict.fromkeys(own, 1400.), **dict.fromkeys(other, 700.)})
    cards, report = candidate.generate_bilateral_trades(**args, max_cards=1)
    assert len(cards) >= 121
    assert report.as_dict()["limits"] == {"pool": 16, "per_pair": 4096, "total": 60000}
    limited, budget = candidate.generate_bilateral_trades(**args, config={"owner_total_budget": 7})
    assert budget.as_dict()["evaluated"] == 7
    assert budget.as_dict()["budget_exhausted"]
    assert len(limited) <= 7
