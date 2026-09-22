"""Scorecard §§1, 3–7: both sides, unknowns, legal slots and reference bands.

The synthetic A/B/C cases are evaluator contracts, not measured model quality.
Negative controls execute named stud-band, swapped-board and dynasty-as-points
sabotages and prove the corresponding independent assertion turns red.
"""

from copy import deepcopy
import itertools
import json
from pathlib import Path
import random

import pytest

from backend.eval import scorecard_dimensions as score


FIXTURE = Path(__file__).parent / "fixtures/model-evaluation/dimensions/opposite-objectives.json"


def base_offer():
    return json.loads(FIXTURE.read_text())


def provenance(offer, source="synthetic-independent-review"):
    return {"source": source, "as_of": "2026-09-21", "version": "fixture-rubric-1",
            "snapshot_id": offer["snapshot_id"], "independent": True, "kind": "synthetic_fixture"}


def annotated_offer():
    offer = base_offer()
    reviews = {}
    for dimension in score.DIMENSIONS:
        if dimension == "stud_tax":
            continue
        managers = {}
        for role, manager in offer["managers"].items():
            grade = 2 if dimension == "team_needs" and role == "A" else 3
            managers[manager["manager_id"]] = {side: {"grade": grade, "reasons": ["worked_case_a_independent_context"]}
                                               for side in score.SIDES}
        reviews[dimension] = {"provenance": provenance(offer), "terms_hash": score.offer_terms_hash(offer),
                              "managers": managers}
    offer["evidence"]["reviews"] = reviews
    offer["evidence"]["stud_tax"] = {
        "provenance": provenance(offer, "synthetic-reviewed-consolidation-band"),
        "terms_hash": score.offer_terms_hash(offer), "best_asset_id": "rb", "minimum_return": 2.5,
        "maximum_return": 2.7, "units": "first_equivalents", "convention": "return_total",
        "first_round_exemption_reviewed": True,
    }
    return offer


def cell(result, dimension, role="A", side="package"):
    return result["dimensions"][dimension]["managers"][role][side]


def test_worked_case_a_supports_both_managers_without_claiming_acceptance():
    result = score.evaluate_offer(annotated_offer())
    assert result["integrity_status"] == "valid"
    assert result["rubric_status"] == "draft_unratified"
    assert result["behavioral_acceptance"]["status"] == "unknown"
    for dimension in score.DIMENSIONS:
        assert result["dimensions"][dimension]["bilateral_status"] == "pass"
        for role, side in itertools.product(("A", "B"), score.SIDES):
            expected = 2 if dimension == "stud_tax" or (dimension == "team_needs" and role == "A") else 3
            assert cell(result, dimension, role, side)["grade"] == expected
            assert cell(result, dimension, role, side)["evidence"]
    assert cell(result, "team_needs", "B")["raw_features"]["lineup"]["net_starter_delta"] == 3
    assert cell(result, "team_needs")["raw_features"]["immediate_starter_improvement"]["status"] == "not_applicable"
    assert cell(result, "outlook")["raw_features"]["intent"] == "tanking"
    assert cell(result, "outlook")["raw_features"]["authority"] == "selected"


def test_worked_case_b_missing_board_and_projection_never_pass():
    offer = annotated_offer()
    del offer["managers"]["B"]["personal_board"]
    del offer["managers"]["B"]["projections"]
    result = score.evaluate_offer(offer)
    for dimension in ("personal_ranks", "team_needs"):
        for side in score.SIDES:
            assert cell(result, dimension, "B", side)["status"] == "unknown"
            assert cell(result, dimension, "B", side)["grade"] is None
        assert result["dimensions"][dimension]["bilateral_status"] == "evidence-limited"
    assert cell(result, "personal_ranks", "A")["grade"] == 3


def test_worked_case_c_counterparty_hole_overrides_positive_incoming_and_selection():
    offer = annotated_offer()
    offer["managers"]["B"]["give"].append("b_qb")
    offer["managers"]["B"]["explicit_selection"] = {"give": ["b_qb"]}
    # The updated fixture review deliberately contains an incorrect favorable
    # package grade. Independently established slot harm must still defeat it.
    for review in offer["evidence"]["reviews"].values():
        review["terms_hash"] = score.offer_terms_hash(offer)
    result = score.evaluate_offer(offer)
    assert cell(result, "team_needs", "B", "give")["grade"] == 0
    assert cell(result, "team_needs", "B")["grade"] == 0
    assert cell(result, "team_needs", "B", "receive")["grade"] == 3
    assert result["dimensions"]["team_needs"]["bilateral_status"] == "fail"


def test_raw_features_available_without_review_not_fabricated_good_grades():
    result = score.evaluate_offer(base_offer())
    assert all(d["bilateral_status"] == "evidence-limited" for d in result["dimensions"].values())
    raw = cell(result, "personal_ranks", "A", "give")["raw_features"]
    assert raw["signed_gaps"]["rb"]["sign"] == -1
    assert raw["target_or_sell_hits"] == ["rb"]
    assert raw["focal_hit_value_mass"] == 2.4
    assert raw["known_value_mass_share"] == 1
    assert cell(result, "personal_ranks", "A", "receive")["raw_features"]["target_or_sell_hits"] == ["wr"]
    assert cell(result, "fairness")["raw_features"]["market_net"] == pytest.approx(.2)


def test_mirror_order_and_input_immutability():
    offer = annotated_offer()
    frozen = deepcopy(offer)
    expected = score.evaluate_offer(offer)
    assert offer == frozen
    mirror = deepcopy(offer)
    mirror["managers"]["A"], mirror["managers"]["B"] = mirror["managers"]["B"], mirror["managers"]["A"]
    for manager in mirror["managers"].values():
        manager["give"].reverse()
        manager["roster"].reverse()
    observed = score.evaluate_offer(mirror)
    assert observed["terms_hash"] == expected["terms_hash"]
    for dimension in score.DIMENSIONS:
        for role, other in (("A", "B"), ("B", "A")):
            left = expected["dimensions"][dimension]["managers"][role]
            right = observed["dimensions"][dimension]["managers"][other]
            assert left == right
    reordered = deepcopy(offer)
    reordered["managers"]["B"]["give"].reverse()
    assert score.evaluate_offer(reordered) == expected


@pytest.mark.parametrize("attack", ["duplicate", "wrong_owner", "same_managers", "unknown_asset", "schema"])
def test_invalid_identity_quarantined(attack):
    offer = annotated_offer()
    if attack == "duplicate":
        offer["managers"]["A"]["give"].append("rb")
    elif attack == "wrong_owner":
        offer["assets"]["rb"]["owner_id"] = "someone_else"
    elif attack == "same_managers":
        offer["managers"]["B"]["manager_id"] = "tanker"
    elif attack == "unknown_asset":
        offer["managers"]["A"]["give"] = ["missing"]
    else:
        offer["schema_version"] = 999
    result = score.evaluate_offer(offer)
    assert result["integrity_status"] == "invalid"
    assert result["integrity_errors"]
    assert all(d["bilateral_status"] == "evidence-limited" for d in result["dimensions"].values())


@pytest.mark.parametrize("attack", ["model_review", "wrong_terms", "stale_snapshot", "no_independence", "synthetic_on_real"])
def test_annotations_need_independence_exact_terms_and_snapshot(attack):
    offer = annotated_offer()
    review = offer["evidence"]["reviews"]["fairness"]
    if attack == "model_review":
        review["provenance"]["kind"] = "model_utility"
    elif attack == "wrong_terms":
        review["terms_hash"] = "other-terms"
    elif attack == "stale_snapshot":
        review["provenance"]["snapshot_id"] = "old-snapshot"
    elif attack == "no_independence":
        review["provenance"]["independent"] = False
    else:
        offer["data_kind"] = "captured"
    assert cell(score.evaluate_offer(offer), "fairness")["status"] == "unknown"


@pytest.mark.parametrize("attack", ["swapped", "consensus_filled", "different_universe", "unranked_headliner", "stale"])
def test_personal_evidence_does_not_infer_conviction(attack):
    offer = annotated_offer()
    board = offer["managers"]["B"]["personal_board"]
    if attack == "swapped":
        offer["managers"]["B"]["personal_board"] = offer["managers"]["A"]["personal_board"]
    elif attack == "consensus_filled":
        board["entries"]["rb"]["explicit"] = False
    elif attack == "different_universe":
        board["universe_id"] = "other-format"
    elif attack == "unranked_headliner":
        del board["entries"]["rb"]
    else:
        board["provenance"]["fresh"] = False
    result = score.evaluate_offer(offer)
    assert cell(result, "personal_ranks", "B", "receive")["status"] == "unknown"
    assert cell(result, "personal_ranks", "B")["status"] == "unknown"


def test_tiny_liked_filler_cannot_rescue_wrong_focal_diagnostics():
    offer = base_offer()
    offer["assets"]["wr"]["market_value"] = 100
    offer["assets"]["first"].update(kind="player", position="WR", market_value=.001)
    board = offer["managers"]["A"]["personal_board"]
    board["entries"]["wr"]["tier"] = 4
    board["entries"]["first"]["tier"] = 1
    offer["evidence"]["market"]["entries"]["first"]["tier"] = 5
    raw = cell(score.evaluate_offer(offer), "personal_ranks", "A", "receive")["raw_features"]
    assert raw["target_or_sell_hits"] == ["first"]
    assert raw["wrong_direction_value_mass"] == 100
    assert raw["focal_hit_value_mass"] == .001
    assert raw["focal_hit_value_mass"] / raw["market_total"] < .0001


def test_within_tier_gap_and_no_board_mutation_or_implicit_learning():
    offer = base_offer()
    personal = offer["managers"]["A"]["personal_board"]["entries"]["rb"]
    personal.update(tier=2, order=3)
    before = deepcopy(offer)
    result = score.evaluate_offer(offer)
    assert cell(result, "personal_ranks", "A", "give")["raw_features"]["signed_gaps"]["rb"] == {
        "tier_gap": 0, "within_tier_order_gap": -2, "sign": -1}
    assert score.evaluate_offer(offer) == result
    assert offer == before


def test_tanking_own_next_pick_and_selection_authority():
    offer = base_offer()
    offer["managers"]["B"]["selected_outlook"] = "jets"
    result = score.evaluate_offer(offer)
    assert cell(result, "outlook", "B", "give")["grade"] == 0
    assert cell(result, "outlook", "B")["grade"] == 0
    offer["managers"]["B"]["explicit_selection"] = {"give": ["first"]}
    selected = score.evaluate_offer(offer)
    assert cell(selected, "outlook", "B")["status"] == "unknown"
    assert cell(selected, "outlook", "B")["raw_features"]["explicit_selection"] == {"give": ["first"]}


def test_tanking_rb_exception_needs_rationale_not_a_boolean():
    offer = base_offer()
    offer["managers"]["B"].update(selected_outlook="jets", explicit_selection={"give": ["first"]}, rb_exception=True)
    result = score.evaluate_offer(offer)
    assert cell(result, "outlook", "B", "receive")["reasons"] == ["tanking_rb_requires_independent_exception_rationale"]
    review = annotated_offer()["evidence"]["reviews"]["outlook"]
    review["managers"]["contender"]["receive"]["reasons"] = ["reviewed_discounted_long_term_rb_prospect"]
    review["managers"]["contender"]["package"]["reasons"] = ["reviewed_price_and_portfolio_exception"]
    offer["evidence"]["reviews"] = {"outlook": review}
    assert cell(score.evaluate_offer(offer), "outlook", "B", "receive")["grade"] == 3


@pytest.mark.parametrize("attack", ["dynasty_units", "stale", "missing_player", "unknown_rules", "missing_cuts", "duplicate_cut", "missing_position"])
def test_lineup_missingness_cuts_and_proxy_attacks(attack):
    offer = annotated_offer()
    manager = offer["managers"]["A"]
    if attack == "dynasty_units":
        manager["projections"]["units"] = "dynasty_value"
    elif attack == "stale":
        manager["projections"]["provenance"]["fresh"] = False
    elif attack == "missing_player":
        del manager["projections"]["entries"]["wr"]
    elif attack == "unknown_rules":
        manager["lineup"]["rules_complete"] = False
    elif attack == "duplicate_cut":
        manager["lineup"]["cuts"] = ["a_wr", "a_wr"]
    elif attack == "missing_position":
        del offer["assets"]["wr"]["position"]
    else:
        manager["lineup"]["roster_limit"] = 3
        offer["assets"]["first"].update(kind="player", position="TE")
    assert cell(score.evaluate_offer(offer), "team_needs")["status"] == "unknown"


def test_named_cut_and_unavailable_player_are_not_silently_counted():
    offer = base_offer()
    manager = offer["managers"]["B"]
    manager["lineup"]["cuts"] = ["b_qb"]
    manager["projections"]["entries"]["rb"]["available"] = False
    result = score.evaluate_offer(offer)
    raw = cell(result, "team_needs", "B")["raw_features"]["lineup"]
    assert raw["cuts"] == ["b_qb"]
    assert raw["new_empty_slots"] == ["QB"]
    assert raw["receive_marginal_points"] == 0
    assert cell(result, "team_needs", "B")["grade"] == 0


def brute_force(roster, assets, entries, slots):
    choices = [[None] + [p for p in roster if entries[p]["available"] and assets[p]["position"] in s["eligible_positions"]]
               for s in slots]
    best = (0, 0)
    for assignment in itertools.product(*choices):
        players = [p for p in assignment if p is not None]
        if len(players) == len(set(players)):
            best = max(best, (sum(entries[p]["points"] for p in players), len(players)))
    return best


def test_lineup_matches_independent_exhaustive_oracle_including_flex_superflex():
    rng = random.Random(102)
    slots = [{"id": "QB", "eligible_positions": ["QB"]}, {"id": "RB", "eligible_positions": ["RB"]},
             {"id": "FLEX", "eligible_positions": ["RB", "WR", "TE"]},
             {"id": "SUPERFLEX", "eligible_positions": ["QB", "RB", "WR", "TE"]}]
    for _ in range(40):
        roster = [str(i) for i in range(7)]
        assets = {p: {"position": rng.choice(["QB", "RB", "WR", "TE"])} for p in roster}
        entries = {p: {"points": rng.randint(0, 25), "available": rng.choice([True, True, False])} for p in roster}
        actual = score.best_lineup(roster, assets, entries, slots)
        assert (actual["points"], len(actual["assignments"])) == brute_force(roster, assets, entries, slots)
        assert len(set(actual["assignments"].values())) == len(actual["assignments"])


def test_individual_significance_not_raw_addition_and_second_pick_distinction():
    offer = base_offer()
    for asset_id in ("rb", "wr"):
        offer["assets"][asset_id]["market_value"] = .3
        for manager in offer["managers"].values():
            manager["personal_board"]["entries"][asset_id]["tier"] = 5
    offer["assets"]["first"].update(pick_round=2, market_value=.3)
    result = score.evaluate_offer(offer)
    assert cell(result, "meaningful")["grade"] == 0
    assert cell(result, "meaningful", "B", "give")["raw_features"]["market_total"] == .6
    assert result["dimensions"]["meaningful"]["bilateral_status"] == "fail"
    offer["context"] = "explicit_selected_search"
    assert cell(score.evaluate_offer(offer), "meaningful")["status"] == "unknown"


def test_unknown_youth_and_unknown_personal_significance_are_not_false_facts():
    offer = base_offer()
    del offer["managers"]["A"]["personal_board"]
    offer["assets"]["wr"]["market_value"] = .1
    raw = cell(score.evaluate_offer(offer), "meaningful", "A", "receive")["raw_features"]
    assert raw["individual_significance"]["wr"] is None
    assert raw["young_wr_te_qb_value_share"] is None


def test_significance_can_use_position_aware_market_tiers_without_scalar_floor():
    offer = base_offer()
    market = offer["evidence"]["market"]
    del market["second_round_player_floor"]
    market["second_round_tier"] = 4
    del offer["managers"]["A"]["personal_board"]
    offer["assets"]["rb"]["market_value"] = .001
    raw = cell(score.evaluate_offer(offer), "meaningful", "A", "give")["raw_features"]
    assert raw["individual_significance"]["rb"] is True
    market["provenance"]["timestamp_semantics"] = "capture_not_market_publication"
    result = score.evaluate_offer(offer)
    assert any("freshness is unestablished" in limitation for limitation in result["limitations"])


def test_personal_significance_does_not_require_a_comparable_market_board():
    offer = base_offer()
    del offer["evidence"]["market"]
    result = score.evaluate_offer(offer)
    raw = cell(result, "meaningful", "A", "give")["raw_features"]
    assert raw["individual_significance"]["rb"] is True
    assert raw["highest_known_personal_tier"] == 3
    assert cell(result, "personal_ranks", "A", "give")["status"] == "unknown"


def test_applicability_is_explicit_and_does_not_manufacture_a_bilateral_pass():
    offer = annotated_offer()
    for annotation in offer["evidence"]["reviews"]["meaningful"]["managers"]["tanker"].values():
        annotation.update(status="not_applicable", grade=None, reasons=["reviewed_non_discovery_context"])
    result = score.evaluate_offer(offer)
    assert cell(result, "meaningful")["status"] == "not_applicable"
    assert result["dimensions"]["meaningful"]["bilateral_status"] == "not_applicable"
    assert result["dimensions"]["meaningful"]["applicability"]["A"]["package"] is False


def test_stud_band_required_and_undercompensation_not_hidden_by_balanced_price():
    offer = annotated_offer()
    offer["evidence"]["stud_tax"]["minimum_return"] = 2.65
    result = score.evaluate_offer(offer)
    assert cell(result, "stud_tax")["grade"] == 0
    assert cell(result, "stud_tax", "B")["grade"] == 2
    assert result["dimensions"]["stud_tax"]["bilateral_status"] == "fail"
    del offer["evidence"]["stud_tax"]
    assert cell(score.evaluate_offer(offer), "stud_tax")["status"] == "unknown"


def test_buyer_excessive_premium_exemption_and_no_double_charge():
    offer = annotated_offer()
    offer["evidence"]["stud_tax"]["maximum_return"] = 2.55
    result = score.evaluate_offer(offer)
    assert cell(result, "stud_tax", "B")["grade"] == 0
    assert cell(result, "stud_tax")["grade"] == 2
    assert cell(result, "stud_tax")["raw_features"]["adjustment_applied"] == 0
    offer["evidence"]["stud_tax"]["first_round_exemption_reviewed"] = False
    assert cell(score.evaluate_offer(offer), "stud_tax")["status"] == "unknown"


def test_tied_headliners_do_not_invent_a_seller_or_universal_tax():
    offer = annotated_offer()
    offer["assets"]["wr"]["market_value"] = 2.4
    result = score.evaluate_offer(offer)
    assert cell(result, "stud_tax")["status"] == "unknown"
    assert cell(result, "stud_tax")["raw_features"]["market_headliners"] == ["rb", "wr"]


@pytest.mark.parametrize("attack", ["turn_off_stud_tax", "swap_personal_boards", "dynasty_value_as_points"])
def test_named_sabotage_controls_turn_the_guard_assertion_red(monkeypatch, attack):
    offer = annotated_offer()
    if attack == "turn_off_stud_tax":
        offer["evidence"]["stud_tax"]["minimum_return"] = 2.65
        original = score._stud_tax
        def broken(o, output):
            original(o, output)
            for manager in output["managers"].values():
                for c in manager.values():
                    c["grade"] = 2
        monkeypatch.setattr(score, "_stud_tax", broken)
        def guard(result):
            assert cell(result, "stud_tax")["grade"] == 0
    elif attack == "swap_personal_boards":
        original = score._preferences
        def broken(o, manager, ids, focal, direction):
            other = next(m for m in o["managers"].values() if m["manager_id"] != manager["manager_id"])
            return original(o, other, ids, focal, direction)
        monkeypatch.setattr(score, "_preferences", broken)
        def guard(result):
            assert cell(result, "personal_ranks", "A", "give")["raw_features"]["signed_gaps"]["rb"]["sign"] == -1
    else:
        original = score.best_lineup
        def broken(roster, assets, entries, slots):
            dynasty = {p: {**entry, "points": assets[p]["market_value"]} for p, entry in entries.items()}
            return original(roster, assets, dynasty, slots)
        monkeypatch.setattr(score, "best_lineup", broken)
        def guard(result):
            assert cell(result, "team_needs", "B")["raw_features"]["lineup"]["net_starter_delta"] == 3
    with pytest.raises(AssertionError):
        guard(score.evaluate_offer(offer))


@pytest.mark.parametrize("attack", ["missing_year", "missing_original_owner", "missing_validation"])
def test_pick_validity_missing_evidence_is_unknown_not_meaningful_pass(attack):
    offer = annotated_offer()
    key = {"missing_year": "pick_year", "missing_original_owner": "original_owner_id",
           "missing_validation": "pick_validation"}[attack]
    del offer["assets"]["first"][key]
    result = score.evaluate_offer(offer)
    assert result["integrity_status"] == "valid"
    assert cell(result, "meaningful", "A", "receive")["raw_features"]["individual_significance"]["first"] is None
    assert cell(result, "meaningful")["status"] == "unknown"


def test_pick_from_completed_draft_is_invalid_even_with_stale_valid_marker():
    offer = annotated_offer()
    offer["assets"]["first"]["pick_year"] = 2026
    offer["evidence"]["draft_calendar"] = {"last_completed_draft_year": 2026,
                                               "provenance": provenance(offer, "synthetic-draft-calendar")}
    result = score.evaluate_offer(offer)
    assert result["integrity_status"] == "invalid"
    assert "invalid_or_expired_pick" in result["integrity_errors"]


@pytest.mark.parametrize("positions", ["NOTQB", [], ["QB", 7], {"QB": True}])
def test_slot_positions_are_typed_exact_positions_not_substring_matching(positions):
    offer = annotated_offer()
    offer["managers"]["B"]["lineup"]["slots"][0]["eligible_positions"] = positions
    assert cell(score.evaluate_offer(offer), "team_needs", "B")["status"] == "unknown"


@pytest.mark.parametrize("attack", ["bad_projection_date", "future_market", "future_projection", "missing_capture", "unknown_projection_freshness"])
def test_frozen_evidence_dates_and_freshness_are_not_assumed(attack):
    offer = annotated_offer()
    dimension = "team_needs"
    if attack == "bad_projection_date":
        offer["managers"]["B"]["projections"]["provenance"]["as_of"] = "not-a-date"
    elif attack == "future_market":
        offer["evidence"]["market"]["provenance"]["as_of"] = "2099-01-01"
        dimension = "fairness"
    elif attack == "future_projection":
        offer["managers"]["B"]["projections"]["provenance"]["as_of"] = "2099-01-01"
    elif attack == "missing_capture":
        del offer["captured_at"]
    else:
        del offer["managers"]["B"]["projections"]["provenance"]["fresh"]
    assert cell(score.evaluate_offer(offer), dimension, "B")["status"] == "unknown"


def test_retrospective_review_date_is_bounded_separately_from_frozen_inputs():
    offer = annotated_offer()
    offer["evidence"]["reviews"]["fairness"]["provenance"]["as_of"] = "2026-09-22T01:00:00Z"
    assert cell(score.evaluate_offer(offer), "fairness")["status"] == "unknown"
    offer["evidence_cutoff"] = "2026-09-22T02:00:00Z"
    assert cell(score.evaluate_offer(offer), "fairness")["grade"] == 3
    offer["evidence"]["market"]["provenance"]["as_of"] = "2026-09-22T01:00:00Z"
    assert cell(score.evaluate_offer(offer), "fairness")["status"] == "unknown"


@pytest.mark.parametrize("attack", ["null", "future", "invalid", "wrong_snapshot"])
def test_pick_validation_is_an_as_of_audited_marker_not_a_boolean(attack):
    offer = annotated_offer()
    validation = offer["assets"]["first"]["pick_validation"]
    if attack == "null":
        offer["assets"]["first"]["pick_validation"] = None
    elif attack == "future":
        validation["provenance"]["as_of"] = "2099-01-01"
    elif attack == "wrong_snapshot":
        validation["provenance"]["snapshot_id"] = "other-snapshot"
    else:
        validation["status"] = "invalid"
    result = score.evaluate_offer(offer)
    if attack == "invalid":
        assert result["integrity_status"] == "invalid"
    else:
        assert result["integrity_status"] == "valid"
        assert cell(result, "meaningful")["status"] == "unknown"


def test_public_lineup_function_also_rejects_substring_slots():
    with pytest.raises(ValueError, match="invalid_or_unsupported_lineup_slots"):
        score.best_lineup(["q"], {"q": {"position": "QB"}},
                          {"q": {"available": True, "points": 10}},
                          [{"id": "BAD", "eligible_positions": "NOTQB"}])
