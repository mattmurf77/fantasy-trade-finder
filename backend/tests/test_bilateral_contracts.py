"""Independent, adversarial contracts for the bilateral owner model.

All boards and people here are synthetic. These are tests of recommendation
behavior, not human acceptance labels or calibrated probability evidence.
Only public entry points are used; no generator internals are patched.
"""

from copy import deepcopy
import json

import pytest

from backend import feature_flags as ff, trade_service as ts
from backend.ranking_service import Player
from backend.trade_gen_bilateral import (
    evaluate_bilateral_trades, generate_bilateral_trades,
)
from backend.trade_gen_owner import generate_owner_trades


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    ts._cfg.update(age_pref_mult_u23=1.0, age_pref_mult_30plus=1.0)


def world(*, own=("give",), other=("target",), market=None,
          viewer=None, partner=None, positions=None, ages=None, **kwargs):
    ids = sorted(set(own) | set(other))
    market = market or dict.fromkeys(ids, 1000.)
    players = {pid: Player(pid, pid, (positions or {}).get(pid, "WR"),
                           "PICK" if (positions or {}).get(pid) == "PICK" else "TST",
                           (ages or {}).get(pid, 26)) for pid in ids}
    # None denotes a real neutral board; {} denotes no personal board.
    viewer = market if viewer is None else viewer
    partner = market if partner is None else partner
    member = ts.LeagueMember(
        "partner", "Partner", list(other),
        {pid: ts.value_to_elo(v) for pid, v in partner.items()}, bool(partner),
        confidence_sources=dict.fromkeys(partner, "explicit"))
    args = dict(players=players,
                league=ts.League("synthetic_bilateral", "Synthetic", "sleeper", [member]),
                user_id="viewer", user_roster=list(own),
                seed_elo={pid: ts.value_to_elo(v) for pid, v in market.items()},
                user_elo={pid: ts.value_to_elo(v) for pid, v in viewer.items()},
                user_sources=dict.fromkeys(viewer, "explicit"),
                opponent_sources={"partner": dict.fromkeys(partner, "explicit")},
                outlook="not_sure", opponent_outlooks={"partner": "not_sure"},
                fairness_threshold=.75, scoring_format="1qb_ppr")
    args.update(kwargs)
    return args


def favorable(**kwargs):
    return world(viewer={"give": 800., "target": 1300.},
                 partner={"give": 1300., "target": 800.}, **kwargs)


def packages(cards):
    return {(c.target_user_id, frozenset(c.give_player_ids),
             frozenset(c.receive_player_ids)) for c in cards}


def package(give, receive):
    return "partner", frozenset(give), frozenset(receive)


def test_weaker_side_leads_over_a_larger_viewer_windfall():
    args = world(other=("windfall", "balanced"),
                 viewer={"give": 800., "windfall": 1800., "balanced": 1300.},
                 partner={"give": 1200., "windfall": 1190., "balanced": 800.})
    cards, _ = generate_bilateral_trades(**args)
    assert packages(cards) >= {package(["give"], ["windfall"]),
                               package(["give"], ["balanced"])}
    assert cards[0].receive_player_ids == ["balanced"]
    snapshots = {c.receive_player_ids[0]: c.owner_evaluation.as_dict()
                 for c in cards if len(c.receive_player_ids) == 1}
    assert (snapshots["balanced"]["bilateral"]["weaker_support"] >
            snapshots["windfall"]["bilateral"]["weaker_support"])


def test_flipping_a_frozen_personal_board_changes_the_focal_targets():
    args = world(other=("alpha", "beta"),
                 viewer={"give": 1000., "alpha": 1500., "beta": 700.},
                 partner={"give": 1400., "alpha": 800., "beta": 800.})
    before, _ = generate_bilateral_trades(**args)
    changed = deepcopy(args)
    changed["user_elo"].update(alpha=ts.value_to_elo(700), beta=ts.value_to_elo(1500))
    after, _ = generate_bilateral_trades(**changed)
    assert package(["give"], ["alpha"]) in packages(before)
    assert package(["give"], ["beta"]) not in packages(before)
    assert package(["give"], ["beta"]) in packages(after)
    assert package(["give"], ["alpha"]) not in packages(after)


def test_neutral_real_board_is_not_organic_preference_fulfillment():
    args = world(partner={"give": 1400., "target": 800.})
    assert generate_bilateral_trades(**args)[0] == []
    explicit, _ = generate_bilateral_trades(
        **args, pinned_receive_players=["target"])
    assert explicit
    assert explicit[0].owner_evaluation.as_dict()["viewer"]["intent"]["qualified"]


def test_missing_counterparty_board_stays_eligible_and_explicitly_unknown():
    args = world(viewer={"give": 800., "target": 1300.}, partner={})
    cards, _ = generate_bilateral_trades(**args)
    assert package(["give"], ["target"]) in packages(cards)
    snapshot = cards[0].owner_evaluation.as_dict()
    assert snapshot["counterparty"]["preference_evidence"]["state"] == "unknown"
    assert all(a["counterparty_source"] == "consensus_fallback" for a in snapshot["assets"])
    assert snapshot["bilateral"]["score_kind"] == "interpretable_support_not_probability"
    serialized = json.dumps(snapshot).lower()
    assert '"acceptance_probability"' not in serialized
    assert '"mutual_acceptance_probability"' not in serialized
    assert '"calibrated_probability"' not in serialized


@pytest.mark.parametrize("source", ["explicit", "votes", "cross_format", "legacy"])
def test_every_deliberate_ranking_method_retains_full_authority(source):
    args = favorable()
    baseline, _ = generate_bilateral_trades(**args)
    args["user_sources"] = dict.fromkeys(args["user_elo"], source)
    changed, _ = generate_bilateral_trades(**args)
    assert packages(changed) == packages(baseline)
    assert (changed[0].owner_evaluation.as_dict()["bilateral"]["weaker_support"] ==
            baseline[0].owner_evaluation.as_dict()["bilateral"]["weaker_support"])


def test_seed_rows_cannot_fabricate_personal_conviction():
    args = world(viewer={"give": 1000., "target": 100000.},
                 partner={"give": 1400., "target": 800.})
    args["user_sources"]["target"] = "seed"
    seeded, _ = generate_bilateral_trades(**args)
    del args["user_elo"]["target"]
    del args["user_sources"]["target"]
    missing, _ = generate_bilateral_trades(**args)
    assert packages(seeded) == packages(missing)
    assert seeded == []


def test_liking_the_target_more_does_not_raise_its_market_price():
    args = favorable()
    before, _ = generate_bilateral_trades(**args)
    args["user_elo"]["target"] = ts.value_to_elo(100000.)
    after, _ = generate_bilateral_trades(**args)
    assert packages(before) == packages(after)
    assert [(c.give_value, c.receive_value, c.fairness_score) for c in before] == [
        (c.give_value, c.receive_value, c.fairness_score) for c in after]


def test_strong_conviction_cannot_buy_counterparty_consent_with_extreme_overpay():
    args = world(market={"give": 3000., "target": 700.},
                 viewer={"give": 500., "target": 20000.},
                 partner={"give": 4000., "target": 500.})
    assert generate_bilateral_trades(**args)[0] == []


def test_tier_up_uses_the_personal_board_even_when_market_direction_is_down():
    args = world(market={"give": 1100., "target": 1000.},
                 viewer={"give": 400., "target": 1800.},
                 partner={"give": 1500., "target": 700.}, trade_intent="tier_up")
    cards, _ = generate_bilateral_trades(**args)
    assert package(["give"], ["target"]) in packages(cards)
    assert cards[0].give_value > cards[0].receive_value
    snapshot = cards[0].owner_evaluation.as_dict()
    assert snapshot["direction"] == "upgrade"
    assert snapshot["personal_tiers"]["receive"] < snapshot["personal_tiers"]["give"]


def test_full_selected_package_precedes_any_partial_exploration():
    args = favorable(pinned_give_players=["give"],
                     pinned_receive_players=["target"], exact_give=True)
    cards, report = generate_bilateral_trades(**args)
    assert packages(cards) == {package(["give"], ["target"])}
    assert not report.as_dict()["partial_search"]
    assert all(c.owner_evaluation.as_dict()["selection"]["coverage"] == "full" for c in cards)


def test_infeasible_full_selection_gets_honest_bound_partial_alternatives():
    args = world(own=("g1", "g2"),
                 viewer={"g1": 700., "g2": 700., "target": 1800.},
                 partner={"g1": 1500., "g2": 1500., "target": 700.},
                 pinned_give_players=["g1", "g2"], pinned_receive_players=["target"])
    cards, report = generate_bilateral_trades(**args)
    assert cards and report.as_dict()["partial_search"]
    for card in cards:
        selection = card.owner_evaluation.as_dict()["selection"]
        assert selection["coverage"] == "partial"
        assert set(selection["give"]["requested"]) == {"g1", "g2"}
        assert len(selection["give"]["included"]) == len(selection["give"]["omitted"]) == 1
        assert selection["receive"]["included"] == ["target"]
    assert all(result.eligible for result in evaluate_bilateral_trades(cards, **args))
    forged = deepcopy(cards[0])
    forged.owner_evaluation = None
    assert not evaluate_bilateral_trades([forged], **args)[0].eligible


def test_request_authority_does_not_rewrite_a_saved_untouchable_tag():
    preferences = {"viewer": {"untouchables": ["give"]}}
    before = deepcopy(preferences)
    args = favorable(manager_preferences=preferences,
                     pinned_give_players=["give"], exact_give=True)
    assert generate_bilateral_trades(**args)[0]
    assert preferences == before


@pytest.mark.parametrize("bad_give", ["target", "unknown"])
def test_explicit_selection_never_overrides_ownership(bad_give):
    args = favorable(pinned_give_players=[bad_give], exact_give=True)
    assert generate_bilateral_trades(**args)[0] == []


def test_minimal_terms_do_not_add_a_gift_to_the_already_stronger_side():
    args = world(own=("give", "filler"), market={"give": 1000., "target": 1000., "filler": 200.},
                 viewer={"give": 800., "target": 1300., "filler": 200.},
                 partner={"give": 1800., "target": 500., "filler": 200.})
    cards, _ = generate_bilateral_trades(**args)
    assert package(["give"], ["target"]) in packages(cards)
    assert package(["give", "filler"], ["target"]) not in packages(cards)


def test_no_total_offer_cap_or_diversity_deletion_of_distinct_good_returns():
    own = tuple(f"g{i:02d}" for i in range(11))
    other = tuple(f"r{i:02d}" for i in range(11))
    args = world(own=own, other=other,
                 viewer={**dict.fromkeys(own, 700.), **dict.fromkeys(other, 1400.)},
                 partner={**dict.fromkeys(own, 1400.), **dict.fromkeys(other, 700.)})
    cards, _ = generate_bilateral_trades(**args)
    requested_cap, _ = generate_bilateral_trades(**args, max_cards=1)
    expected = {package([g], [r]) for g in own for r in other}
    assert packages(cards) == packages(requested_cap) == expected
    assert len(cards) == 121


def test_exact_terms_and_prices_are_bound_to_detached_immutable_evidence():
    args = favorable()
    cards, _ = generate_bilateral_trades(**args)
    card = cards[0]
    evidence = card.owner_evaluation
    assert evidence.matches(card)
    detached = evidence.as_dict()
    detached["viewer"]["support"]["score"] = -100.
    assert evidence.as_dict()["viewer"]["support"]["score"] >= 0
    card.give_value += 1
    assert not evidence.matches(card)
    card.give_value -= 1
    card.receive_player_ids.append("different_terms")
    assert not evidence.matches(card)


def test_generation_does_not_mutate_boards_and_old_model_output_is_unchanged():
    args = favorable()
    before = deepcopy(args)
    legacy_before, legacy_report_before = generate_owner_trades(**args)
    generate_bilateral_trades(**args)
    legacy_after, legacy_report_after = generate_owner_trades(**args)
    assert args == before
    assert packages(legacy_before) == packages(legacy_after)
    assert [c.owner_evaluation.as_dict() for c in legacy_before] == [
        c.owner_evaluation.as_dict() for c in legacy_after]
    assert legacy_report_before.as_dict() == legacy_report_after.as_dict()


def test_public_card_output_contains_no_counterparty_board_or_support():
    from backend.server import trade_card_to_dict
    args = favorable()
    cards, _ = generate_bilateral_trades(**args)
    payload = trade_card_to_dict(cards[0], args["players"])
    assert payload["model_arm"] == "owner_v2_bilateral"
    text = json.dumps(payload)
    for private in ("owner_evaluation", "valuation_json", "counterparty_personal",
                    "counterparty_source", "outgoing_personal", "incoming_personal",
                    "preference_evidence", "weaker_support", "user_elo", "support"):
        assert '"' + private + '"' not in text
    assert payload["match_context"]["owner_benefits"]


def test_tanking_protects_verified_own_next_pick_but_honors_own_send_selection():
    args = world(own=("own_next_first",), other=("young_wr",),
                 viewer={"own_next_first": 800., "young_wr": 1600.},
                 partner={"own_next_first": 1500., "young_wr": 800.},
                 positions={"own_next_first": "PICK"}, ages={"young_wr": 23},
                 outlook="jets", manager_preferences={"viewer": {
                     "own_next_draft_pick_ids": ["own_next_first"]}})
    assert generate_bilateral_trades(**args)[0] == []
    selected, _ = generate_bilateral_trades(
        **args, pinned_give_players=["own_next_first"], exact_give=True)
    assert package(["own_next_first"], ["young_wr"]) in packages(selected)


def test_viewer_get_selection_does_not_authorize_tanker_selling_their_own_next_pick():
    args = world(other=("their_next_first",),
                 viewer={"give": 800., "their_next_first": 1600.},
                 partner={"give": 1600., "their_next_first": 800.},
                 positions={"their_next_first": "PICK"}, ages={"give": 23},
                 opponent_outlooks={"partner": "jets"},
                 manager_preferences={"partner": {"own_next_draft_pick_ids": ["their_next_first"]}},
                 pinned_receive_players=["their_next_first"])
    assert generate_bilateral_trades(**args)[0] == []


@pytest.mark.parametrize("age,discount,allowed", [(22, True, True), (22, False, False),
                                                (27, True, False), (None, True, False)])
def test_tanking_rb_prospect_requires_real_discount_youth_and_personal_preference(age, discount, allowed):
    args = world(market={"give": 850. if discount else 1000., "target": 1000.},
                 viewer={"give": 600., "target": 1500.},
                 partner={"give": 1500., "target": 700.},
                 positions={"target": "RB"}, ages={"give": 29, "target": age}, outlook="jets")
    cards, _ = generate_bilateral_trades(**args)
    assert bool(cards) is allowed


@pytest.mark.parametrize("tier", ["firsts_2", "firsts_3", "firsts_4plus"])
def test_tanking_rb_elite_exception_uses_canonical_user_tier(tier):
    from backend.ranking_service import RankingService
    floor, ceiling = RankingService.tier_bands_for("RB", "1qb_ppr")[tier]
    elite_value = ts.elo_to_value((floor + ceiling) / 2)
    args = world(viewer={"give": 700., "target": elite_value},
                 partner={"give": 1500., "target": 700.},
                 positions={"target": "RB"}, ages={"give": 29, "target": 27}, outlook="jets")
    cards, _ = generate_bilateral_trades(**args)
    assert cards
    target = next(a for a in cards[0].owner_evaluation.as_dict()["assets"] if a["id"] == "target")
    assert target["viewer_preference"]["personal_tier"] == tier


def test_verified_expired_pick_is_invalid_even_when_deliberately_selected():
    args = world(own=("expired_first",),
                 viewer={"expired_first": 800., "target": 1600.},
                 partner={"expired_first": 1600., "target": 800.},
                 positions={"expired_first": "PICK"},
                 manager_preferences={"viewer": {"expired_pick_ids": ["expired_first"]}},
                 pinned_give_players=["expired_first"], exact_give=True)
    assert generate_bilateral_trades(**args)[0] == []


def test_partial_sources_keep_unknown_assets_unknown_despite_a_member_board():
    args = favorable()
    args["opponent_sources"]["partner"]["target"] = "seed"
    cards, _ = generate_bilateral_trades(**args)
    assert cards
    snapshot = cards[0].owner_evaluation.as_dict()
    assert snapshot["counterparty"]["preference_evidence"]["state"] == "partial"
    target = next(a for a in snapshot["assets"] if a["id"] == "target")
    assert target["counterparty_source"] == "consensus_fallback"
    assert target["counterparty_preference"]["direction"] is None


@pytest.mark.parametrize("floor", [float("nan"), float("inf"), True, -.1, 1.1])
def test_invalid_account_price_tolerance_never_creates_an_offer(floor):
    assert generate_bilateral_trades(**favorable(fairness_threshold=floor))[0] == []
