"""Post-significance bilateral ordering: bounded quality, exact occurrences.

Synthetic survivor fixtures isolate presentation from constructor acceptance.
No server, database, network, or production inputs are used.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from backend import trade_bilateral_presentment as presentment
from backend.trade_gen_owner import OwnerDecisionContext


def card(give, receive, *, partner="other", scores=(.70, .70), purpose="lateral",
         version="owner-v2-bilateral-2", **attrs):
    data = {
        "generator": "owner_v2_bilateral", "generator_version": version,
        "eligible": True, "reason": "eligible",
        "market": {"give": 1000., "receive": 1000., "ratio": 1.},
        "direction": purpose,
        "selection": {"give": {"requested": []}, "receive": {"requested": []},
                      "exact_give": False, "coverage": "full"},
        "construction": {"explicit_selection": False, "shape": "1x1"},
        "viewer": {"support": {"score": scores[0]}, "intent": {
            "qualified": True, "path": "personal", "sell_candidate": give,
            "buy_target": receive}},
        "counterparty": {"support": {"score": scores[1]}, "intent": {
            "qualified": False, "buy_target": give, "sell_candidate": receive}},
        "assets": [{"id": pid, "market": 1000., "viewer_personal": 1000.,
                    "viewer_source": "explicit", "counterparty_personal": 1000.,
                    "counterparty_source": "explicit"} for pid in (give, receive)],
        "term_efficiency": {"ordering_version": "same-focal-terms-1",
                            "worst_adjusted_market_loss": 0., "avoidable_companions": []},
    }
    for side, uid in (("viewer", "me"), ("counterparty", partner)):
        data[side]["consideration_profile"] = {
            "manager_id": uid, "known_personal": True,
            "raw_outgoing_personal": 1000., "raw_incoming_personal": 1000.,
            "outgoing_plan_mean": 0., "incoming_plan_mean": 0.,
            "outgoing_positions": ["WR"], "incoming_positions": ["WR"],
            "availability_shape": [[["WR", True]], [["WR", True]]],
        }
    result = SimpleNamespace(
        trade_id=f"unstable-{give}-{receive}", league_id="league",
        proposing_user_id="me", target_user_id=partner,
        give_player_ids=[give], receive_player_ids=[receive],
        give_value=1000., receive_value=1000., fairness_score=1.,
        basis="divergence", lane="value", composite_score=500.,
        owner_evaluation=OwnerDecisionContext(True, "eligible", "league", "me",
            partner, (give,), (receive,), json.dumps(data)))
    result.__dict__.update(attrs)
    return result


def headliner_count(cards, n=30):
    return max(Counter(c.give_player_ids[0] for c in cards[:n]).values(), default=0)


def survivor_fixture():
    hot = [card("a-hot", f"return-{i:03}", partner=f"partner-{i % 3}") for i in range(17)]
    fillers = [card(f"filler-{i}", f"low-{i}", insignificant=True) for i in range(19)]
    alternatives = [card(f"b-alternative-{i:03}", f"target-{i:03}",
                         partner=f"partner-{i % 5}") for i in range(43)]
    return hot[:11] + fillers + hot[11:] + alternatives


def test_survivor_pass_repairs_11_to_17_of_30_concentration_without_removing_cards():
    native = survivor_fixture()
    survivors = [c for c in native if not getattr(c, "insignificant", False)]
    assert headliner_count(native) == 11
    assert headliner_count(survivors) == 17
    before = deepcopy([c.__dict__ for c in survivors])
    ordered, diagnostics = presentment.present(survivors)
    assert headliner_count(ordered) <= 10
    assert ordered[0] is survivors[0]
    assert Counter(map(id, ordered)) == Counter(map(id, survivors))
    assert [c.__dict__ for c in survivors] == before
    assert diagnostics["count"] == 60
    assert diagnostics["eligible_count"] == 60
    assert diagnostics["moved_count"] > 0
    assert diagnostics["quality_tolerance"] == .025
    assert diagnostics["version"] == presentment.VERSION
    assert all(ordered[i] is survivors[original]
               for i, original in enumerate(diagnostics["occurrence_original_indices"]))


@pytest.mark.parametrize("weak_side", [0, 1])
def test_novelty_cannot_trade_away_either_managers_quality(weak_side):
    # Equal weaker/total support is NOT enough: managers' scores are reversed.
    strong_scores = [.90, .65]
    if weak_side:
        strong_scores.reverse()
    good = [card("a-hot", f"return-{i:03}", scores=strong_scores) for i in range(40)]
    tempting = card("z-novel", "novel-target", scores=strong_scores[::-1])
    ordered, _ = presentment.present(good + [tempting])
    assert ordered[-1] is tempting


def test_quality_bounds_hold_at_every_position_and_max_displacement_is_bounded():
    # Both-manager checks are relative to the fixed quality baseline, preventing
    # repeated small swaps from accumulating an unbounded quality regression.
    cards = [card("a-hot" if i % 3 else f"alternative-{i:03}", f"target-{i:03}",
                  scores=(.90 - .002 * i, .87 - .001 * i)) for i in range(150)]
    baseline = sorted(cards, key=lambda c: (
        -min(c.owner_evaluation.as_dict()[s]["support"]["score"] for s in ("viewer", "counterparty")),
        -sum(c.owner_evaluation.as_dict()[s]["support"]["score"] for s in ("viewer", "counterparty"))))
    baseline_rank = {id(c): i for i, c in enumerate(baseline)}
    ordered, _ = presentment.present(cards)
    assert ordered[0] is baseline[0]
    for position, (actual, reference) in enumerate(zip(ordered, baseline)):
        for side in ("viewer", "counterparty"):
            assert actual.owner_evaluation.as_dict()[side]["support"]["score"] >= (
                reference.owner_evaluation.as_dict()[side]["support"]["score"] - .025 - 1e-9)
        assert abs(position - baseline_rank[id(actual)]) < presentment.LOOKAHEAD


@pytest.mark.parametrize("marker,value", [
    ("likes_you", True), ("source_like_impression_id", "old-interest"),
    ("standing_offer_reason", "old-offer"), ("injected", True),
    ("wildcard", True), ("fatigue_retest", True), ("retest", True),
    ("model_arm", "fit"), ("source", "injected"),
])
@pytest.mark.parametrize("slot", [0, 7, 29, 42])
def test_protected_cards_keep_arbitrary_exact_slots(marker, value, slot):
    cards = [c for c in survivor_fixture() if not getattr(c, "insignificant", False)]
    protected = card("protected", "target", **{marker: value})
    cards.insert(slot, protected)
    ordered, _ = presentment.present(cards)
    assert ordered[slot] is protected
    assert Counter(map(id, ordered)) == Counter(map(id, cards))


def test_sources_and_versions_cannot_cross_slots():
    cards = [c for c in survivor_fixture() if not getattr(c, "insignificant", False)]
    for i, item in enumerate(cards):
        item.basis = "consensus" if i % 2 else "divergence"
        item.lane = "window" if i % 3 else "value"
    old = card("legacy", "target", version="owner-v2-bilateral-1")
    owner = card("owner", "target", version="owner-v1")
    cards[5:5] = [old, owner]
    ordered, _ = presentment.present(cards)
    assert ordered[5] is old and ordered[6] is owner
    assert [(c.basis, c.lane) for c in ordered] == [(c.basis, c.lane) for c in cards]


@pytest.mark.parametrize("search", [
    {"selected_give": ["g"]}, {"selected_receive": ["r"]},
    {"opponent_user_id": "other"},
])
def test_explicit_search_is_complete_noop(search):
    cards = [c for c in survivor_fixture() if not getattr(c, "insignificant", False)]
    ordered, diagnostics = presentment.present(cards, **search)
    assert all(a is b for a, b in zip(ordered, cards))
    assert diagnostics["moved_count"] == 0
    assert diagnostics["reason"] == "explicit_search"


@pytest.mark.parametrize("defect", [
    "missing", "wrong_type", "ineligible", "proof_reason", "mismatch", "snapshot_ineligible",
    "explicit", "selected", "no_support", "nan_support", "bool_support",
    "no_focal", "unknown_purpose", "viewer_unqualified", "missing_terms", "malformed_terms",
])
def test_missing_or_unacceptable_evidence_stays_fixed(defect):
    item = card("z-unknown", "z-target")
    data = item.owner_evaluation.as_dict()
    if defect == "missing":
        del item.owner_evaluation
    elif defect == "wrong_type":
        item.owner_evaluation = SimpleNamespace(eligible=True, as_dict=lambda: data,
                                               matches=lambda _: True)
    elif defect == "ineligible":
        item.owner_evaluation = replace(item.owner_evaluation, eligible=False)
    elif defect == "proof_reason":
        item.owner_evaluation = replace(item.owner_evaluation, reason="known_preference_harm")
    elif defect == "mismatch":
        item.receive_player_ids = ["changed"]
    else:
        if defect == "snapshot_ineligible":
            data["eligible"] = False
        elif defect == "explicit":
            data["construction"]["explicit_selection"] = True
        elif defect == "selected":
            data["selection"]["give"]["requested"] = ["z-unknown"]
        elif defect in ("no_support", "nan_support", "bool_support"):
            data["counterparty"]["support"]["score"] = {
                "no_support": None, "nan_support": float("nan"), "bool_support": True}[defect]
        elif defect == "no_focal":
            del data["viewer"]["intent"]["buy_target"]
        elif defect == "unknown_purpose":
            del data["direction"]
        elif defect == "viewer_unqualified":
            data["viewer"]["intent"]["qualified"] = False
        elif defect == "missing_terms":
            del data["term_efficiency"]
        elif defect == "malformed_terms":
            del data["counterparty"]["consideration_profile"]["raw_outgoing_personal"]
        item.owner_evaluation = replace(item.owner_evaluation, snapshot_json=json.dumps(data))
    cards = [card("a-hot", f"return-{i}") for i in range(4)] + [item]
    ordered, _ = presentment.present(cards)
    assert ordered[4] is item


def test_exact_duplicate_occurrences_and_proofs_are_preserved():
    duplicate = card("a-hot", "first")
    cards = [duplicate, duplicate, card("b-alternative", "second"), deepcopy(duplicate)]
    proofs = [c.owner_evaluation for c in cards]
    ordered, diagnostics = presentment.present(cards)
    assert Counter(map(id, ordered)) == Counter(map(id, cards))
    assert sorted(diagnostics["occurrence_original_indices"]) == list(range(4))
    assert all(c.owner_evaluation is proof for c, proof in zip(cards, proofs))


def test_unstable_ids_do_not_supply_novelty_or_tiebreaks():
    cards = [c for c in survivor_fixture() if not getattr(c, "insignificant", False)]
    first, _ = presentment.present(cards)
    for i, item in enumerate(cards):
        item.trade_id = f"new-{len(cards) - i}"
    second, _ = presentment.present(cards)
    assert all(a is b for a, b in zip(first, second))


@pytest.mark.parametrize("different", ["purpose", "give", "receive", "partner"])
def test_each_meaningful_novelty_axis_can_surface_a_comparable_alternative(different):
    cards = [card("a-give", "a-receive", partner="a-partner") for _ in range(8)]
    alternative = card("z-give" if different == "give" else "a-give",
                       "z-receive" if different == "receive" else "a-receive",
                       partner="z-partner" if different == "partner" else "a-partner",
                       purpose="upgrade" if different == "purpose" else "lateral")
    ordered, _ = presentment.present(cards + [alternative])
    assert ordered[0] is cards[0]
    assert ordered[1] is alternative


def test_empty_and_no_novelty_preserve_full_constructor_baseline():
    assert presentment.present([])[0] == []
    cards = [card("a-hot", "same-target", scores=(.6 + i * .001, .6 + i * .001))
             for i in range(80)]
    ordered, _ = presentment.present(cards)
    assert ordered == cards


def test_constructor_term_precedence_is_not_replaced_by_support_sorting():
    efficient = card("a-efficient", "same-target", scores=(.725, .577))
    more_expensive = card("z-expensive", "same-target", scores=(.627, .632))
    ordered, diagnostics = presentment.present([efficient, more_expensive])
    assert ordered == [efficient, more_expensive]
    assert diagnostics["baseline"] == "candidate_native_order"


@pytest.mark.parametrize("stronger_liking", [False, True])
def test_real_constructor_price_precedence_survives_final_survivor_ordering(monkeypatch, stronger_liking):
    from backend import feature_flags as ff, trade_service as ts
    from backend import trade_gen_bilateral_candidate as candidate
    from backend.tests.test_bilateral_contracts import world

    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    ts._cfg.update(age_pref_mult_u23=1., age_pref_mult_30plus=1.)
    args = world(own=("cheap", "costly"),
        market={"cheap": 1000., "costly": 1150., "target": 1000.},
        viewer={"cheap": 700., "costly": 700., "target": 1600.},
        partner={"cheap": 1400., "costly": 1400., "target": 600.})
    if stronger_liking:
        args["user_elo"]["target"] = ts.value_to_elo(100000.)
    native, _ = candidate.generate_bilateral_trades(**args)
    # Final eligibility revalidation supplies immutable candidate proof; both
    # exact offers survive this fixture's significance boundary.
    survivors = [item for item, proof in zip(native,
        candidate.evaluate_bilateral_trades(native, **args)) if proof.eligible]
    ordered, _ = presentment.present(survivors)
    assert ordered[0].give_player_ids == ["cheap"]
    assert any(item.give_player_ids == ["costly"] for item in ordered)
    assert Counter(map(id, ordered)) == Counter(map(id, survivors))


def test_real_novel_companion_cannot_jump_its_surviving_cheaper_terms(monkeypatch):
    from backend import feature_flags as ff, trade_service as ts
    from backend import trade_gen_bilateral_candidate as candidate
    from backend.tests.test_bilateral_contracts import world

    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    ts._cfg.update(age_pref_mult_u23=1., age_pref_mult_30plus=1.)
    args = world(own=("give", "extra"), other=("first_target", "target"),
        market={"give": 1000., "extra": 25., "first_target": 1000., "target": 1000.},
        viewer={"give": 700., "extra": 25., "first_target": 1400., "target": 1400.},
        partner={"give": 1600., "extra": 25., "first_target": 600., "target": 600.})
    survivors, _ = candidate.generate_bilateral_trades(**args)
    ordered, diagnostics = presentment.present(survivors)
    for target in ("first_target", "target"):
        simple = next(i for i, item in enumerate(ordered)
                      if item.give_player_ids == ["give"] and item.receive_player_ids == [target])
        larger = next(i for i, item in enumerate(ordered)
                      if len(item.give_player_ids) == 2 and item.receive_player_ids == [target])
        assert simple < larger
    assert diagnostics["term_precedence_edges"] == 2
    assert Counter(map(id, ordered)) == Counter(map(id, survivors))


@pytest.mark.parametrize("dependent_lane", ["value", "window"])
def test_displacing_a_leader_cannot_cross_its_dependent_even_across_source_slots(monkeypatch, dependent_lane):
    cards = [card("a-hot", "same-target"), card("a-hot", "same-target"),
             card("a-hot", "same-target", lane=dependent_lane), card("z-novel", "new-target")]
    monkeypatch.setattr(presentment, "_term_precedence", lambda *args: {2: {1}})
    ordered, _ = presentment.present(cards)
    positions = {id(item): index for index, item in enumerate(ordered)}
    assert positions[id(cards[1])] < positions[id(cards[2])]
    assert ordered[0] is cards[0]


def test_ten_thousand_cards_use_a_bounded_comparison_budget():
    cards = [card(f"give-{i % 100:03}", f"receive-{i:05}", partner=f"p-{i % 31}")
             for i in range(10000)]
    ordered, diagnostics = presentment.present(cards)
    assert len(ordered) == 10000
    assert Counter(map(id, ordered)) == Counter(map(id, cards))
    assert diagnostics["candidate_comparisons"] <= len(cards) * presentment.LOOKAHEAD
    assert len(diagnostics["occurrence_original_indices"]) == len(cards)


def focal_card(give, receive, *, directions=(1, 1, 1, 1), **kwargs):
    """Action-oriented categories: viewer buy/sell, counterparty buy/sell."""
    item = card(give, receive, **kwargs)
    data = item.owner_evaluation.as_dict()
    data["counterparty"]["intent"].update(buy_target=give, sell_candidate=receive)
    assets = {pid: {"id": pid, "market": 1000.} for pid in (give, receive)}
    for side, outgoing, incoming, offset in (
            ("viewer", give, receive, 0), ("counterparty", receive, give, 2)):
        for index, pid, sign in ((offset, incoming, 1), (offset + 1, outgoing, -1)):
            direction = directions[index]
            assets[pid][side + "_personal"] = 1000. + sign * (direction or 0) * 100.
            assets[pid][side + "_source"] = "explicit" if direction is not None else "consensus_fallback"
    data["assets"] = list(assets.values())
    item.owner_evaluation = replace(item.owner_evaluation, snapshot_json=json.dumps(data))
    return item


@pytest.mark.parametrize("focal_index", range(4), ids=["viewer_buy", "viewer_sell", "other_buy", "other_sell"])
@pytest.mark.parametrize("worse", [0, -1, None], ids=["neutral", "adverse", "unknown"])
def test_novelty_cannot_erase_either_managers_known_focal_direction(focal_index, worse):
    hot = [focal_card("hot", "repeated") for _ in range(5)]
    directions = [1, 1, 1, 1]
    directions[focal_index] = worse
    novel = focal_card("novel", "different", directions=directions)
    ordered, _ = presentment.present(hot + [novel])
    assert ordered == hot + [novel]


@pytest.mark.parametrize("source", [None, "consensus_fallback", "seed", "untrusted"])
def test_missing_personal_source_cannot_hide_a_favorable_focal_direction(source):
    hot = [focal_card("hot", "repeated") for _ in range(4)]
    novel = focal_card("novel", "different")
    data = novel.owner_evaluation.as_dict()
    # A fabricated favorable value with no recognized personal source is unknown.
    data["assets"][1]["viewer_personal"] = 5000.
    if source is None:
        data["assets"][1].pop("viewer_source")
    else:
        data["assets"][1]["viewer_source"] = source
    novel.owner_evaluation = replace(novel.owner_evaluation, snapshot_json=json.dumps(data))
    assert presentment.present(hot + [novel])[0] == hot + [novel]


@pytest.mark.parametrize("directions", [(1, 1, 1, 1), (0, 1, -1, 0), (None, None, None, None)])
def test_unchanged_focal_categories_still_allow_beneficial_novelty(directions):
    hot = [focal_card("hot", "repeated", directions=directions) for _ in range(5)]
    novel = focal_card("novel", "different", directions=directions)
    ordered, _ = presentment.present(hot + [novel])
    assert ordered[0] is hot[0] and ordered[1] is novel
    assert Counter(map(id, ordered)) == Counter(map(id, hot + [novel]))


def test_unknown_and_known_focal_evidence_are_not_exchangeable_in_either_direction():
    hot = [focal_card("hot", "repeated", directions=(None, 1, 1, 1)) for _ in range(4)]
    novel = focal_card("novel", "different")
    assert presentment.present(hot + [novel])[0] == hot + [novel]


def test_focal_categories_remain_bound_to_fixed_positions_through_repeated_swaps():
    cards, categories = [], {}
    for index in range(90):
        values = (1 if index % 5 else 0, 1 if index % 7 else None,
                  1 if index % 3 else -1, 1)
        item = focal_card("hot" if index % 4 else f"give-{index}", f"target-{index % 6}",
                          directions=values)
        cards.append(item)
        categories[id(item)] = values
    ordered, diagnostics = presentment.present(cards)
    assert diagnostics["moved_count"] > 0
    for actual, baseline in zip(ordered, cards):
        for observed, expected in zip(categories[id(actual)], categories[id(baseline)]):
            if expected is None or observed is None:
                assert observed is expected
            else:
                assert observed >= expected
    assert Counter(map(id, ordered)) == Counter(map(id, cards))


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), 0., -1., "1400", 10 ** 400])
@pytest.mark.parametrize("field", ["market", "viewer_personal"])
def test_invalid_focal_values_do_not_become_known_preferences(value, field):
    hot = [focal_card("hot", "repeated") for _ in range(4)]
    novel = focal_card("novel", "different")
    data = novel.owner_evaluation.as_dict()
    data["assets"][1][field] = value
    novel.owner_evaluation = replace(novel.owner_evaluation, snapshot_json=json.dumps(data))
    assert presentment.present(hot + [novel])[0] == hot + [novel]


@pytest.mark.parametrize("defect", ["missing_assets", "duplicate_asset", "wrong_asset_id", "wrong_focal_id"])
def test_malformed_focal_identity_keeps_exact_slot(defect):
    hot = [focal_card("hot", "repeated") for _ in range(4)]
    novel = focal_card("novel", "different")
    data = novel.owner_evaluation.as_dict()
    if defect == "missing_assets":
        data.pop("assets")
    elif defect == "duplicate_asset":
        data["assets"].append(data["assets"][0])
    elif defect == "wrong_asset_id":
        data["assets"][1]["id"] = ["different"]
    else:
        data["counterparty"]["intent"]["buy_target"] = "different"
    novel.owner_evaluation = replace(novel.owner_evaluation, snapshot_json=json.dumps(data))
    assert presentment.present(hot + [novel])[0] == hot + [novel]


def test_real_constructor_survivors_do_not_exchange_known_buy_direction_for_novelty(monkeypatch):
    from backend import feature_flags as ff, trade_service as ts
    from backend import trade_gen_bilateral_candidate as candidate
    from backend.tests.test_bilateral_contracts import world

    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    ts._cfg.update(age_pref_mult_u23=1., age_pref_mult_30plus=1.)
    own, other = ("hot", "novel", "other"), ("favored1", "favored2", "less_favored")
    args = world(own=own, other=other, market=dict.fromkeys(own + other, 1000.),
        viewer={**dict.fromkeys(own, 700.), "favored1": 1001., "favored2": 1001., "less_favored": 999.},
        partner={**dict.fromkeys(own, 1400.), **dict.fromkeys(other, 600.)})
    native, _ = candidate.generate_bilateral_trades(**args)
    # Model a final filter by removal only. These exact real proofs and their
    # native relative ordering are not rewritten to manufacture equal support.
    retained = {(("hot",), ("favored1",)), (("hot",), ("favored2",)),
                (("novel",), ("less_favored",))}
    survivors = [item for item in native
                 if (tuple(item.give_player_ids), tuple(item.receive_player_ids)) in retained]
    assert len(survivors) == 3
    assert [item.receive_player_ids[0] for item in survivors] == ["favored1", "favored2", "less_favored"]
    assert all(result.eligible for result in candidate.evaluate_bilateral_trades(survivors, **args))
    proofs = [item.owner_evaluation for item in survivors]
    for side in ("viewer", "counterparty"):
        supports = [proof.as_dict()[side]["support"]["score"] for proof in proofs]
        assert max(supports) - min(supports) < presentment.QUALITY_TOLERANCE
    ordered, _ = presentment.present(survivors)
    assert all(actual is baseline for actual, baseline in zip(ordered, survivors))
    assert all(item.owner_evaluation is proof for item, proof in zip(survivors, proofs))


def tied_focal_card(name, *, focal_index, values, reverse=False):
    item = focal_card(name + "-give", name + "-receive")
    data = item.owner_evaluation.as_dict()
    side = "viewer" if focal_index < 2 else "counterparty"
    buy = focal_index % 2 == 0
    tied_give = focal_index in (1, 2)
    tied_ids = item.give_player_ids if tied_give else item.receive_player_ids
    rows = {row["id"]: row for row in data["assets"]}
    first = rows[tied_ids[0]]
    for index, value in enumerate(values):
        if index:
            extra = deepcopy(first)
            extra["id"] = name + "-extra-" + str(index)
            rows[extra["id"]] = extra
            tied_ids.append(extra["id"])
        row = rows[tied_ids[index]]
        row[side + "_personal"] = 1000. + (1 if buy else -1) * (value or 0) * 100.
        row[side + "_source"] = "explicit" if value is not None else "consensus_fallback"
    single_ids = item.receive_player_ids if tied_give else item.give_player_ids
    single = rows[single_ids[0]]
    for key in ("market", "viewer_personal", "counterparty_personal"):
        single[key] *= len(values)
    if reverse:
        tied_ids.reverse()
        data["viewer"]["intent"]["sell_candidate" if tied_give else "buy_target"] = tied_ids[0]
        data["counterparty"]["intent"]["buy_target" if tied_give else "sell_candidate"] = tied_ids[0]
    item.give_value = item.receive_value = 1000. * len(values)
    data["market"].update(give=item.give_value, receive=item.receive_value)
    data["assets"] = list(rows.values())
    item.owner_evaluation = replace(item.owner_evaluation,
        give_ids=tuple(item.give_player_ids), receive_ids=tuple(item.receive_player_ids),
        snapshot_json=json.dumps(data))
    return item


@pytest.mark.parametrize("focal_index", range(4))
@pytest.mark.parametrize("baseline,regression", [((1, 1), (1, -1)), ((1, 1), (1, None)),
                                               ((-1, 1), (-1, -1)), ((None, 1), (None, -1))])
@pytest.mark.parametrize("reverse", [False, True])
def test_all_tied_headliners_preserve_categories_not_just_first_or_minimum(focal_index, baseline, regression, reverse):
    hot = [tied_focal_card("hot", focal_index=focal_index, values=baseline, reverse=reverse) for _ in range(4)]
    novel = tied_focal_card("novel", focal_index=focal_index, values=regression, reverse=reverse)
    assert presentment.present(hot + [novel])[0] == hot + [novel]


@pytest.mark.parametrize("focal_index", range(4))
@pytest.mark.parametrize("categories", [(1, -1), (1, None)])
def test_tie_permutations_with_same_evidence_allow_novelty(focal_index, categories):
    hot = [tied_focal_card("hot", focal_index=focal_index, values=categories) for _ in range(4)]
    novel = tied_focal_card("novel", focal_index=focal_index, values=categories[::-1], reverse=True)
    ordered, _ = presentment.present(hot + [novel])
    assert ordered[0] is hot[0] and ordered[1] is novel


def test_different_co_headliner_counts_keep_their_native_positions():
    hot = [tied_focal_card("hot", focal_index=0, values=(1, 1)) for _ in range(4)]
    novel = tied_focal_card("novel", focal_index=0, values=(1, 1, 1))
    assert presentment.present(hot + [novel])[0] == hot + [novel]
