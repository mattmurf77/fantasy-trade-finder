"""Independent benchmark contracts, adverse fixtures and deliberate red controls."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.eval import bilateral_revision_benchmark as benchmark
from backend.eval import scorecard_dimensions as score


BASE = Path(__file__).parent / "fixtures/model-evaluation/dimensions/opposite-objectives.json"


def fixture():
    return json.loads(BASE.read_text())


def cell(result, dimension, role="A", side="package"):
    return result["dimensions"][dimension]["managers"][role][side]


def card(give=("g",), receive=("r",), target="B"):
    return SimpleNamespace(give_player_ids=list(give), receive_player_ids=list(receive), target_user_id=target)


def raw_input():
    return {"user_roster": ["g", "sweetener"], "members": [{"id": "B", "roster": ["r"]}],
            "players": {"g": {"position": "RB"}, "sweetener": {"position": "TE"}, "r": {"position": "WR"}}}


def test_gate_is_frozen_with_honest_limits_and_full_four_sides():
    gate = json.loads((benchmark.FIXTURES / "gates.json").read_text())
    assert gate["frozen_before_candidate_results"] is True
    assert gate["baseline_commit"] == "ecda17d1"
    assert gate["release"]["critical_regressions_allowed"] == 0
    assert gate["release"]["offline_result_cannot_authorize_broad_promotion"]
    assert gate["release"]["empirical_thresholds_ratified"] is False
    assert len(gate["dimensions"]) == 6 and len(gate["assessments"]) == 6
    assert gate["rank_cuts"] == [1, 5, 10, 30]


def test_archetypes_cover_all_outlook_pairs_and_board_states_without_fake_observations():
    records = benchmark.constructed_requests()
    organic = [r["owner_request"] for r in records if not r["owner_request"].get("counterfactual_of")]
    assert len(organic) == 4 * 4 * 3
    pairs = {(r["input"]["outlook"], r["input"]["opponent_outlooks"]["B"]) for r in organic}
    assert len(pairs) == 16
    inventory = benchmark.context_inventory(records)
    assert inventory["counts"]["synthetic_contexts"] == len(records)
    assert inventory["counts"]["counterfactual_contexts"] == 9
    assert inventory["independent_observed_contexts"] is None
    assert inventory["known_owner_league_clusters"] == 0


def test_capture_dedup_uses_input_not_untrusted_reused_hash_and_retains_invalid():
    one = {"owner_request": {"input": {"x": 1}, "request_hash": "same"}}
    two = {"owner_request": {"input": {"x": 2}, "request_hash": "same"}}
    result, repeated = benchmark.request_records({"requests": [one, deepcopy(one), two, {}]})
    assert len(result) == 3 and repeated == 1 and result[-1]["invalid_capture"]


def test_frozen_holdout_never_splits_shared_managers_across_leagues():
    def record(league, viewer, partner):
        return {"league_id": league, "owner_request": {"input": {"user_id": viewer, "members": [{"id": partner}]}}}
    records = [record("L1", "a", "b"), record("L2", "c", "b"), record("L3", "d", "e")]
    split = benchmark.frozen_split(records)
    assert split["connected_components"] == 2 and split["status"] == "frozen"
    assert split["assignments"][0] == split["assignments"][1]
    assert split["assignments"][0] != split["assignments"][2]
    single = benchmark.frozen_split(records[:2])
    assert single["status"] == "evidence-limited" and "holdout" not in single["cohort_counts"]


def test_diagnostic_panel_frozen_from_inputs_retains_all_strata_and_holdout():
    records = benchmark.constructed_requests()[:4]
    for record in records:
        record["owner_request"].pop("data_kind")
    split = {"assignments": {0: "development", 1: "development", 2: "development", 3: "holdout"}}
    selected = benchmark.diagnostic_panel(records, split)
    assert 3 in selected
    strata = lambda rows: {(r["owner_request"]["input"]["outlook"], r["owner_request"]["input"]["scoring_format"]) for r in rows}
    assert strata([records[i] for i in selected]) == strata(records)
    assert len(selected) <= 2


def test_price_diagnostics_independent_of_utility_and_keep_adverse_seller_terms():
    k = raw_input()
    c = card()
    c.owner_evaluation = SimpleNamespace(as_dict=lambda: (_ for _ in ()).throw(AssertionError("model truth read")))
    result = benchmark.raw_diagnostics([c], k, {"g": 100, "r": 75, "sweetener": 10})
    assert result["raw_market_return"]["mean"] == -.25
    assert result["best_asset_seller_raw_return"]["mean"] == -.25
    assert result["counts"]["give_contains_rb"] == 1
    assert result["counts"]["receive_contains_rb"] == 0


def test_cheapest_target_price_does_not_reward_added_sweetener():
    result = benchmark.raw_diagnostics([card(("g", "sweetener")), card()], raw_input(),
                                       {"g": 100, "r": 100, "sweetener": 10})
    assert list(result["private_cheapest_exact_target_prices"].values()) == [100]
    assert result["offers"] == 2


def test_named_red_control_enthusiasm_price_extraction_fails_frozen_probe():
    low = {"private_focused_target_prices": {"same_exact_return": 100}, "private_first_exact_target_prices": {"same_exact_return": 100}}
    high = {"private_focused_target_prices": {"same_exact_return": 110}, "private_first_exact_target_prices": {"same_exact_return": 110}}
    assert benchmark.preference_price_probe(low, high)["status"] == "fail"
    assert benchmark.preference_price_probe(low, low)["status"] == "pass"
    assert benchmark.preference_price_probe(low, {})["status"] == "evidence-limited"


def test_first_price_extraction_detected_even_when_cheapest_inventory_unchanged():
    low = {"private_focused_target_prices": {"return": 100}, "private_first_exact_target_prices": {"return": 100}}
    high = {"private_focused_target_prices": {"return": 100}, "private_first_exact_target_prices": {"return": 110}}
    result = benchmark.preference_price_probe(low, high)
    assert result["status"] == result["first_offer_status"] == "fail"
    assert result["cheapest_price_status"] == "pass"


@pytest.mark.parametrize("attack", ["variant", "version", "source", "benchmark_source_sha256", "benchmark_version", "input_sha256", "config_sha256"])
def test_reuse_rejects_every_stale_or_wrong_identity_binding(attack):
    raw, capture, source = {"input": {}}, {"config": []}, {"head": "ecda17d1", "file_sha256": {"f": "h"}}
    result = {"variant": "incumbent", "version": "owner-v2-bilateral-1", "status": "ok",
        "benchmark_version": benchmark.VERSION, "input_sha256": benchmark.digest(raw),
        "config_sha256": benchmark.digest(capture), "source": source, "benchmark_source_sha256": "runner"}
    kwargs = dict(raw=raw, capture=capture, source=source, runner_sha="runner")
    benchmark.validate_reused_incumbent(result, **kwargs)
    corrupted = deepcopy(result)
    corrupted[attack] = "wrong"
    with pytest.raises(ValueError, match="evidence/source/version mismatch"):
        benchmark.validate_reused_incumbent(corrupted, **kwargs)


def test_common_pick_overlay_preserves_captured_authority_without_inventing_valid_ledger():
    offer = fixture()
    offer["assets"]["first"].pop("original_owner_id")
    offer["assets"]["first"].pop("pick_validation")
    offer["managers"]["B"]["selected_outlook"] = "jets"
    raw = {"captured_at": offer["captured_at"], "version": "captured-test", "input": {"manager_preferences": {
        "contender": {"next_draft_year": 2027, "own_next_draft_pick_ids": ["first"], "expired_pick_ids": []}}}}
    before = deepcopy(offer)
    normalized = benchmark.captured_metadata_overlay(offer, raw)
    assert offer == before
    assert normalized["assets"]["first"]["original_owner_id"] == "contender"
    assert "pick_validation" not in normalized["assets"]["first"]
    assert cell(score.evaluate_offer(normalized), "outlook", "B")["grade"] == 0
    raw["input"]["manager_preferences"]["contender"]["expired_pick_ids"] = ["first"]
    expired = benchmark.captured_metadata_overlay(offer, raw)
    assert score.evaluate_offer(expired)["integrity_status"] == "invalid"
    absent = benchmark.captured_metadata_overlay(offer, {"input": {}})
    assert "original_owner_id" not in absent["assets"]["first"]


def test_direct_captured_pick_guards_do_not_depend_on_core_original_owner_coverage():
    k = {"user_id": "A", "user_roster": ["L_2027_1_A"], "members": [{"id": "B", "roster": ["r"]}],
        "players": {"L_2027_1_A": {"position": "PICK"}, "r": {"position": "WR"}}, "outlook": "jets",
        "manager_preferences": {"A": {"own_next_draft_pick_ids": ["L_2027_1_A"], "expired_pick_ids": ["L_2027_1_A"]}}}
    result = benchmark.raw_diagnostics([card(("L_2027_1_A",))], k, {"L_2027_1_A": 100, "r": 100})
    assert result["counts"]["known_unselected_own_next_pick_occurrences"] == 1
    assert result["counts"]["known_expired_pick_occurrences"] == 1


@pytest.mark.parametrize("attack", ["lost_pin", "wrong_owner", "duplicate_asset", "duplicate_offer"])
def test_independent_corruption_diagnostics_do_not_silently_pass(attack):
    k = raw_input()
    cards = [card()]
    expected = "invalid_ownership_or_duplicate_asset"
    if attack == "lost_pin":
        k["pinned_give_players"] = ["sweetener"]
        expected = "lost_selected_asset"
    elif attack == "wrong_owner":
        cards = [card(("r",), ("g",))]
    elif attack == "duplicate_asset":
        cards = [card(("g", "g"))]
    else:
        cards = [card(), card()]
        expected = "exact_duplicate_occurrences"
    assert benchmark.raw_diagnostics(cards, k, {"g": 100, "r": 100})["counts"][expected] == 1


@pytest.mark.parametrize("attack", ["drop", "clone", "double"])
def test_named_red_control_inventory_assertion_rejects_deliberate_policy_bug(attack):
    cards = [card(), card(("sweetener",))]
    corrupted = cards[:1] if attack == "drop" else deepcopy(cards) if attack == "clone" else cards + [cards[0]]
    with pytest.raises(AssertionError, match="survivor_inventory_changed"):
        benchmark.assert_survivor_permutation(cards, corrupted)
    benchmark.assert_survivor_permutation(cards, cards[::-1])


@pytest.mark.parametrize("attack", [None, "missing_metric", "missing_row", "wrong_identity", "wrong_version", "prefix_order", "duplicate_identity"])
def test_retained_policy_bridge_requires_complete_exact_stage_inventories(attack):
    identities = [benchmark.digest(("B", (give,), ("r",))) for give in ("g", "sweetener")]
    manifest = {"contexts": {"ctx": {"managers": {"B": {"manager_id": "B"}}}}, "offers": []}
    result = {"status": "ok", "stages": {}}
    for stage in ("native", "post_significance", "post_survivor_order"):
        for view in ("full", *(f"first{cut}" for cut in benchmark.CUTS)):
            name = stage + "." + view
            count = 1 if view == "first1" else 2
            result["stages"][name] = {"offers": count}
            for rank, give in enumerate(("g", "sweetener")[:count], 1):
                manifest["offers"].append({"stage": name, "model_id": "candidate", "model_version": "owner-v2-bilateral-2",
                    "context_id": "ctx", "offer_id": identities[rank - 1], "native_rank": rank, "terms": {"A": [give], "B": ["r"]}})
    if attack == "missing_metric":
        result["stages"].pop("native.first5")
    elif attack == "missing_row":
        manifest["offers"].pop()
    elif attack == "wrong_identity":
        manifest["offers"][0]["terms"]["A"] = ["wrong"]
    elif attack == "wrong_version":
        manifest["offers"][0]["model_version"] = "owner-v2-bilateral-1"
    elif attack == "prefix_order":
        row = next(row for row in manifest["offers"] if row["stage"] == "native.first1")
        row.update(offer_id=identities[1], terms={"A": ["sweetener"], "B": ["r"]})
    elif attack == "duplicate_identity":
        manifest["offers"][1].update(offer_id=identities[0], terms={"A": ["g"], "B": ["r"]})
    if attack:
        with pytest.raises(ValueError):
            benchmark.validate_retained_manifest(manifest, result)
    else:
        grouped = benchmark.validate_retained_manifest(manifest, result)
        assert len(grouped) == 15 and len(grouped["native.full"]) == 2


def test_no_contextual_grades_invented_by_good_raw_trade_or_missing_board():
    offer = fixture()
    offer["managers"]["B"].pop("personal_board")
    result = score.evaluate_offer(offer)
    assert result["behavioral_acceptance"]["status"] == "unknown"
    for side in score.SIDES:
        assert cell(result, "personal_ranks", "B", side)["status"] == "unknown"
        assert cell(result, "fairness", "A", side)["grade"] is None
        assert cell(result, "stud_tax", "A", side)["grade"] is None


def test_legal_projection_displacement_and_named_cut_harm_are_independent():
    offer = fixture()
    result = score.evaluate_offer(offer)
    lineup = cell(result, "team_needs", "B")["raw_features"]["lineup"]
    assert lineup["net_starter_delta"] == 3
    assert len(set(lineup["after"]["assignments"].values())) == len(lineup["after"]["assignments"])
    assert cell(result, "team_needs", "A")["raw_features"]["immediate_starter_improvement"]["status"] == "not_applicable"
    offer["managers"]["B"]["lineup"]["cuts"] = ["b_qb"]
    result = score.evaluate_offer(offer)
    assert cell(result, "team_needs", "B")["grade"] == 0
    assert cell(result, "team_needs", "B")["raw_features"]["lineup"]["net_starter_delta"] == -16


def test_unidentified_required_cuts_are_unknown_not_zero_cost():
    offer = fixture()
    offer["assets"]["first"].update(kind="player", position="TE")
    offer["managers"]["A"]["lineup"]["roster_limit"] = 3
    assert cell(score.evaluate_offer(offer), "team_needs")["reasons"] == ["required_cuts_not_identified"]


def test_own_next_draft_pick_wrong_plan_and_explicit_exception():
    offer = fixture()
    offer["managers"]["B"]["selected_outlook"] = "jets"
    assert cell(score.evaluate_offer(offer), "outlook", "B")["grade"] == 0
    offer["managers"]["B"]["explicit_selection"] = {"give": ["first"]}
    assert cell(score.evaluate_offer(offer), "outlook", "B")["grade"] is None


@pytest.mark.parametrize("returned,expected_seller,expected_buyer", [(2.6, 2, 2), (2.0, 0, 2), (3.2, 2, 0)])
def test_constructed_independent_stud_band_has_both_adverse_directions(returned, expected_seller, expected_buyer):
    offer = fixture()
    offer["assets"]["wr"]["market_value"] = returned - 1
    offer["evidence"]["stud_tax"] = {
        "provenance": {"source": "constructed-independent-band", "as_of": "2026-09-21", "version": "1",
            "snapshot_id": offer["snapshot_id"], "independent": True, "kind": "synthetic_fixture"},
        "terms_hash": score.offer_terms_hash(offer), "best_asset_id": "rb", "minimum_return": 2.5,
        "maximum_return": 2.7, "units": "first_equivalents", "convention": "return_total",
        "first_round_exemption_reviewed": True}
    result = score.evaluate_offer(offer)
    assert cell(result, "stud_tax", "A")["grade"] == expected_seller
    assert cell(result, "stud_tax", "B")["grade"] == expected_buyer


def test_focal_preference_not_rescued_by_tiny_liked_throwin():
    offer = fixture()
    offer["managers"]["A"]["personal_board"]["entries"]["wr"].update(tier=4)
    offer["assets"]["first"].update(kind="player", position="TE", market_value=.01)
    offer["managers"]["A"]["personal_board"]["entries"]["first"].update(tier=5)
    offer["evidence"]["market"]["entries"]["first"].update(tier=7)
    raw = cell(score.evaluate_offer(offer), "personal_ranks", "A", "receive")["raw_features"]
    assert "wr" in raw["wrong_direction_assets"]
    assert raw["focal_hit_rate"] == 0
    assert "first" in raw["target_or_sell_hits"]


def test_individual_significance_not_a_sum_of_scraps_and_selected_stays_explicit():
    offer = fixture()
    offer["assets"]["first"].update(kind="player", position="TE")
    for asset in offer["assets"].values():
        asset["market_value"] = .2
    for board in [offer["evidence"]["market"], *(m["personal_board"] for m in offer["managers"].values())]:
        for entry in board["entries"].values():
            entry["tier"] = 7
    result = score.evaluate_offer(offer)
    assert result["dimensions"]["meaningful"]["bilateral_status"] == "fail"
    assert cell(result, "meaningful")["grade"] == 0
    offer["context"] = "selected_search"
    selected = score.evaluate_offer(offer)
    assert cell(selected, "meaningful")["grade"] is None


def test_independent_four_side_result_is_mirror_invariant():
    offer = fixture()
    a = score.evaluate_offer(offer)
    offer["managers"] = {"A": offer["managers"]["B"], "B": offer["managers"]["A"]}
    b = score.evaluate_offer(offer)
    for dimension in score.DIMENSIONS:
        assert a["dimensions"][dimension]["bilateral_status"] == b["dimensions"][dimension]["bilateral_status"]
        for side in score.SIDES:
            assert cell(a, dimension, "A", side) == cell(b, dimension, "B", side)
            assert cell(a, dimension, "B", side) == cell(b, dimension, "A", side)


def test_empty_and_error_comparison_cannot_be_a_pass():
    error = benchmark.compare_pair({"status": "error"}, {"status": "empty"})
    assert error["status"] == "error"
    empty = benchmark.raw_diagnostics([], raw_input(), {})
    assert empty["offers"] == 0 and empty["raw_market_return"]["mean"] is None
