"""Scorecard §2: overlap, frozen origin/denominator, attrition and exposure attacks.

Synthetic evidence only. No DB/server/network; named sabotage controls are
exercised by the parent in isolated copies, never by changing production data.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random

import pytest

from backend.eval.scorecard_outcomes import reduce_episode, summarize_cohort


ZERO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def stamp(day):
    return (ZERO + timedelta(days=day)).isoformat().replace("+00:00", "Z")


def event(kind, day, actor="a", event_id=None, **fields):
    result = {"event_id": event_id or f"{kind}-{day}-{actor}", "at": stamp(day),
              "type": kind, "concept_id": "concept", **fields}
    if actor is not None:
        result["actor_id"] = actor
    if kind == "view":
        result["verified"] = True
    return result


def episode(events=(), *, index=0, arm="X", **fields):
    result = {
        "episode_id": f"episode-{index}", "concept_id": "concept", "participants": ["a", "b"],
        "generated_at": stamp(0), "start_at": stamp(0), "expires_at": stamp(14),
        "origin": {"cohort_id": "test", "manager_id": "a", "league_id": "league",
                   "request_id": "request", "assignment_arm": arm, "model_id": "constructor",
                   "model_version": "1", "selected_source": "constructor", "generating_sources": ["constructor"]},
        "followup": {"post_milestone_seconds": 7 * 86400, "completion_seconds": 14 * 86400,
                     "ingestion_lag_seconds": 86400},
        "observation": {"complete_through": stamp(60), "post_milestone_complete_through": stamp(60),
                        "completion_supported": True, "completion_complete_through": stamp(60)},
        "events": [event("view", 0), *deepcopy(events)], **fields,
    }
    return result


def mutual(*extra, index=0, arm="X"):
    return episode([event("like", 1), event("view", 3, "b"), event("like", 3, "b"), *extra], index=index, arm=arm)


def cohort(count=1, *, arm="X", **fields):
    return {
        "cohort_id": "test", "eligibility_rule": "pre-period linked measured leagues v1",
        "frozen_at": stamp(-2), "window_start": stamp(0), "window_end": stamp(14),
        "followup": episode()["followup"],
        "members": [{"manager_id": "a" if i == 0 else f"a-{i}", "league_id": "league",
                     "cluster_id": "cluster", "assigned_at": stamp(-1), "assignment_arm": arm,
                     "request_count": 1 if i == 0 else 0, "observation_complete": True} for i in range(count)], **fields,
    }


def test_valid_overlap_is_immutable_after_withdrawal():
    result = reduce_episode(mutual(event("withdraw", 5)), stamp(6))
    assert result["historical_mutual"] is True
    assert result["mutual_at"] == stamp(3)
    assert result["currently_actionable_mutual"] is False
    assert result["actors"]["a"]["interest_intervals"] == [{"start": stamp(1), "end": stamp(5)}]
    assert [r["type"] for r in result["post_milestone"]["reversals"]] == ["withdraw"]
    assert result["post_milestone"]["non_reversed"] is None  # elapsed != complete
    final = reduce_episode(mutual(event("withdraw", 5)), stamp(40))
    assert final["historical_mutual"] is True
    assert final["post_milestone"]["non_reversed"] is False


def test_nonoverlapping_likes_are_not_mutual():
    result = reduce_episode(episode([event("like", 1), event("withdraw", 2),
                                     event("view", 3, "b"), event("like", 3, "b")]), stamp(40))
    assert not result["historical_mutual"]
    assert all(actor["expressed_interest"] for actor in result["actors"].values())


def test_simultaneous_withdrawal_and_other_like_has_no_overlap():
    source = episode([event("like", 1), event("withdraw", 3), event("view", 3, "b"), event("like", 3, "b")])
    assert not reduce_episode(source, stamp(40))["historical_mutual"]


def test_deadline_never_moves_with_late_view_redisplay_or_deployment():
    source = episode([event("like", 1), event("view", 13, "b"),
                      event("redisplay", 14, source="likes-you", new_arm="Y"), event("like", 15, "b")])
    result = reduce_episode(source, stamp(40))
    assert result["deadline"] == stamp(14)
    assert not result["historical_mutual"]
    assert result["origin"]["assignment_arm"] == "X"
    assert result["origin"]["model_id"] == "constructor"
    assert result["exposure_sources"] == ["likes-you"]


def test_start_must_be_first_verified_view_and_expiry_is_clamped():
    source = episode(expires_at=stamp(100))
    assert reduce_episode(source, stamp(40))["deadline"] == stamp(14)
    source["start_at"] = stamp(2)
    with pytest.raises(ValueError, match="predates frozen start"):
        reduce_episode(source, stamp(40))


@pytest.mark.parametrize("day", [14, 15])
def test_interest_at_or_after_expiry_cannot_match(day):
    source = episode([event("like", 1), event("view", 3, "b"), event("like", day, "b")])
    assert not reduce_episode(source, stamp(40))["historical_mutual"]


def test_expiry_closure_does_not_accelerate_maturity_or_invent_rejection():
    source = mutual()
    source["expires_at"] = stamp(4)
    result = reduce_episode(source, stamp(4))
    assert result["lifecycle"]["reason"] == "expired"
    assert not result["maturity"]["elapsed"]  # separate ingestion lag
    assert result["historical_mutual"]
    assert result["actors"]["a"]["decision"] == "like"
    summary = summarize_cohort(cohort(), [source], stamp(5))
    assert not summary["maturity"]["elapsed"]  # fixed cohort last possible deadline
    assert summary["primary_yield"]["denominator"] == 1


def test_missing_telemetry_is_distinct_from_elapsed_or_invalidated():
    source = episode([event("invalidate", 1, None)])
    source["observation"]["complete_through"] = stamp(1)
    result = reduce_episode(source, stamp(40))
    assert result["lifecycle"]["reason"] == "invalidate"
    assert result["maturity"]["elapsed"]
    assert not result["observation"]["complete"]
    summary = summarize_cohort(cohort(100), [source], stamp(40))
    assert summary["primary_yield"] == {"numerator": 0, "denominator": 100, "value": 0}
    assert summary["yield_bounds"]["upper"] is None
    assert summary["exposed_interest_conversion"]["denominator"] == 0


def test_fixed_denominator_defeats_one_of_one_vs_two_of_ten_attack():
    one = summarize_cohort(cohort(100), [mutual()], stamp(40))
    ten = []
    for i in range(10):
        row = mutual(index=i) if i < 2 else episode(index=i)
        row["concept_id"] = f"concept-{i}"
        for action in row["events"]:
            action["concept_id"] = row["concept_id"]
        ten.append(row)
    two = summarize_cohort(cohort(100), ten, stamp(40))
    assert one["episode_conversion"]["value"] == 1
    assert two["episode_conversion"]["value"] == .2
    assert one["primary_yield"]["value"] == .01 < two["primary_yield"]["value"] == .02
    assert one["no_request_rate"]["value"] == .99


def test_ten_likes_ninety_silent_are_not_universal_willingness():
    rows = []
    for i in range(100):
        row = episode([event("like", 1)] if i < 10 else [], index=i)
        row["concept_id"] = f"concept-{i}"
        for action in row["events"]:
            action["concept_id"] = row["concept_id"]
        rows.append(row)
    result = summarize_cohort(cohort(100), rows, stamp(40))
    assert result["responder_conditional_like_share"]["value"] == 1
    assert result["exposed_interest_conversion"]["value"] == .1
    assert result["response_coverage"]["value"] == .1
    assert result["willingness_probability"] is None
    assert result["no_remaining_decision_count"] == 90


def test_overlapping_constructor_sources_and_injection_count_once():
    source = mutual(event("redisplay", 4, source="likes-you"))
    source["origin"]["generating_sources"] = ["constructor-X", "constructor-Y"]
    source["origin"]["selected_source"] = None
    duplicate = deepcopy(source)
    duplicate["episode_id"] = "mirrored"
    duplicate["participants"].reverse()
    result = summarize_cohort(cohort(), [source, duplicate, source], stamp(40))
    assert result["primary_yield"]["numerator"] == 1
    assert result["episodes"][0]["selected_source_credit"] == "shared"
    assert result["episodes"][0]["origin"]["generating_sources"] == ["constructor-X", "constructor-Y"]


def test_unknown_selected_source_is_not_guessed_from_single_constructor():
    source = mutual()
    source["origin"]["selected_source"] = None
    assert reduce_episode(source, stamp(40))["selected_source_credit"] == "unknown"


@pytest.mark.parametrize("generated,start,reason", [(-3, -2, "carry_in"), (-2, 0, "pre_generated_inventory")])
def test_carry_in_and_pre_generated_inventory_are_separate(generated, start, reason):
    source = mutual()
    source["generated_at"] = stamp(generated)
    source["start_at"] = stamp(start)
    source["events"][0]["at"] = stamp(start)
    result = summarize_cohort(cohort(), [source], stamp(40))
    assert result["primary_yield"]["numerator"] == 0
    assert result["excluded_episodes"] == [{"episode_id": "episode-0", "reason": reason}]


def test_outcome_after_deployment_retains_original_assignment():
    source = mutual(event("redisplay", 2, source="new-release", assignment_arm="Y"))
    result = summarize_cohort(cohort(), [source], stamp(40))
    assert result["by_assignment_arm"]["X"]["primary_yield"]["numerator"] == 1
    assert "Y" not in result["by_assignment_arm"]


def test_transient_three_vs_durable_two_never_auto_promotes():
    def rows(count, reverse):
        result = []
        for i in range(count):
            extra = [event("withdraw", 5)] if reverse else [event("confirm", 5), event("confirm", 5, "b")]
            if not reverse and i == 0:
                extra.append(event("complete", 6, None, verified=True, provider_transaction_id="provider-1"))
            row = mutual(*extra, index=i)
            row["concept_id"] = f"concept-{i}"
            for action in row["events"]:
                action["concept_id"] = row["concept_id"]
            result.append(row)
        return result
    declaration = {"preregistration_id": "synthetic-example-only", "max_reversal_rate": .1,
                   "min_confirmation_rate": .5, "min_followup_coverage": 1}
    fixed = cohort(100, guardrails=declaration)
    transient = summarize_cohort(fixed, rows(3, True), stamp(40))
    durable = summarize_cohort(fixed, rows(2, False), stamp(40))
    assert transient["primary_yield"]["value"] == .03
    assert durable["primary_yield"]["value"] == .02
    assert transient["non_reversed_yield"]["value"] == 0
    assert durable["non_reversed_yield"]["value"] == .02
    assert transient["guardrails"]["status"] == "failed"
    assert durable["guardrails"]["status"] == "within_declared_limits"
    assert transient["promotion"] == durable["promotion"] == "not_evaluated"
    assert durable["verified_completion_yield"]["value"] == .01


def test_followup_gaps_cannot_be_counted_as_retained():
    source = mutual()
    source["observation"]["post_milestone_complete_through"] = stamp(4)
    result = summarize_cohort(cohort(), [source], stamp(40))
    assert result["non_reversed_yield"]["numerator"] == 0
    assert result["post_milestone_coverage"]["numerator"] == 0
    assert result["guardrails"]["status"] == "unratified"


def test_provider_send_is_interest_not_completion():
    source = episode([event("send", 1), event("view", 2, "b"), event("like", 2, "b")])
    result = reduce_episode(source, stamp(40))
    assert result["historical_mutual"]
    assert result["completion"]["provider_send_count"] == 1
    assert not result["completion"]["verified_by_horizon"]
    assert result["completion"]["verified_at"] is None


@pytest.mark.parametrize("fields", [{"verified": False, "provider_transaction_id": "id"}, {"verified": True}])
def test_unverified_or_unlinked_completion_does_not_count(fields):
    result = reduce_episode(mutual(event("complete", 6, None, **fields)), stamp(40))
    assert not result["completion"]["verified_by_horizon"]


def test_undo_preserves_history_and_restores_last_nonundone_decision():
    source = mutual(event("pass", 4, event_id="pass"), event("undo", 5, target_event_id="pass"))
    result = reduce_episode(source, stamp(6))
    assert result["historical_mutual"]
    assert result["currently_actionable_mutual"]
    assert result["actors"]["a"]["decision"] == "like"
    assert result["actors"]["a"]["interest_intervals"] == [
        {"start": stamp(1), "end": stamp(4)}, {"start": stamp(5), "end": None}]
    assert [r["type"] for r in result["post_milestone"]["reversals"]] == ["pass"]


def test_undo_like_does_not_retroactively_erase_valid_overlap():
    source = mutual(event("undo", 4, target_event_id="like-1-a"))
    result = reduce_episode(source, stamp(40))
    assert result["historical_mutual"]
    assert result["actors"]["a"]["decision"] is None
    assert result["post_milestone"]["non_reversed"] is False


def test_out_of_order_duplicate_events_deterministic_input_immutable():
    source = mutual(event("withdraw", 5))
    frozen = deepcopy(source)
    expected = reduce_episode(source, stamp(40))
    shuffled = deepcopy(source)
    shuffled["events"].append(deepcopy(shuffled["events"][1]))
    random.Random(21).shuffle(shuffled["events"])
    assert reduce_episode(shuffled, stamp(40)) == expected
    assert source == frozen


def test_future_events_do_not_change_as_of_result():
    old = mutual()
    new = mutual(event("withdraw", 8))
    left, right = reduce_episode(old, stamp(6)), reduce_episode(new, stamp(6))
    left.pop("event_count")
    right.pop("event_count")
    assert left == right


@pytest.mark.parametrize("field,value", [("start_at", None), ("start_at", "2026-01-01"), ("expires_at", "bad"), ("concept_id", None)])
def test_unknown_timestamp_or_identity_fails_explicitly(field, value):
    source = mutual()
    source[field] = value
    with pytest.raises(ValueError):
        reduce_episode(source, stamp(40))
    result = summarize_cohort(cohort(100), [source], stamp(40))
    assert result["quarantined"]
    assert result["primary_yield"]["denominator"] == 100
    assert result["yield_bounds"]["upper"] is None


def test_exact_package_binding_and_unknown_actor_refuse_guessing():
    for key, value in (("concept_id", "amended"), ("actor_id", "unknown")):
        source = mutual()
        source["events"][1][key] = value
        with pytest.raises(ValueError):
            reduce_episode(source, stamp(40))


def test_conflicting_duplicate_event_is_quarantined():
    source = mutual()
    duplicate = deepcopy(source["events"][1])
    duplicate["type"] = "pass"
    source["events"].append(duplicate)
    with pytest.raises(ValueError, match="conflicting duplicate"):
        reduce_episode(source, stamp(40))


def test_simultaneous_same_actor_decisions_require_sequence():
    source = episode([event("like", 1), event("pass", 1)])
    with pytest.raises(ValueError, match="sequence"):
        reduce_episode(source, stamp(40))
    source["events"][1]["sequence"] = 1
    source["events"][2]["sequence"] = 2
    assert reduce_episode(source, stamp(40))["actors"]["a"]["decision"] == "pass"


def test_action_is_not_exposure_without_documented_fallback():
    source = episode()
    source["events"] = [event("like", 0)]
    with pytest.raises(ValueError, match="verified exposure"):
        reduce_episode(source, stamp(40))
    source["allow_action_exposure"] = True
    source["events"][0].update(exposure_qualified=True, evidence_class="validated_action")
    assert reduce_episode(source, stamp(40))["actors"]["a"]["expressed_interest"]


def test_missing_counterparty_exposure_keeps_action_orphaned():
    source = episode([event("like", 1), event("like", 3, "b")])
    result = reduce_episode(source, stamp(40))
    assert not result["historical_mutual"]
    assert result["observation"]["orphan_actions"] == ["like-3-b"]


def test_eligibility_assignment_and_duplicate_member_guards():
    source = cohort()
    source["frozen_at"] = stamp(1)
    with pytest.raises(ValueError, match="frozen_at"):
        summarize_cohort(source, [], stamp(40))
    source = cohort()
    source["members"].append(deepcopy(source["members"][0]))
    with pytest.raises(ValueError, match="duplicate eligible"):
        summarize_cohort(source, [], stamp(40))


def test_naive_cutoff_rejected_and_offsets_normalize_to_utc():
    source = mutual()
    with pytest.raises(ValueError, match="timezone-aware"):
        reduce_episode(source, "2026-02-01T00:00:00")
    source["events"][0]["at"] = "2025-12-31T19:00:00-05:00"
    assert reduce_episode(source, stamp(40))["start_at"] == stamp(0)


def test_committed_synthetic_fixture_reconciles_and_is_not_a_model_grade():
    path = Path(__file__).parent / "fixtures/model-evaluation/outcomes/synthetic-mutual-withdrawal.json"
    source = json.loads(path.read_text())
    result = summarize_cohort(source["cohort"], source["episodes"], source["cutoff"])
    assert result["primary_yield"]["numerator"] == source["expected"]["historical_mutual_numerator"]
    assert result["primary_yield"]["denominator"] == source["expected"]["fixed_eligible_denominator"]
    assert result["non_reversed_yield"]["numerator"] == source["expected"]["non_reversed_numerator"]
    assert result["guardrails"]["status"] == source["expected"]["guardrail_status"]
    assert result["willingness_probability"] is None


def test_no_request_and_failed_or_empty_search_members_remain_in_denominator():
    fixed = cohort(3)
    fixed["members"][1]["request_count"] = 1  # empty request
    fixed["members"][2]["request_count"] = 1  # failed request, later telemetry outage
    fixed["members"][2]["observation_complete"] = False
    result = summarize_cohort(fixed, [mutual()], stamp(40))
    assert result["primary_yield"]["denominator"] == 3
    assert result["request_yield"]["denominator"] == 3
    assert result["coverage"]["value"] == 2 / 3
    assert result["yield_bounds"]["upper"] is None


def test_no_guardrail_limits_cannot_be_passing_even_with_preregistration_id():
    fixed = cohort(guardrails={"preregistration_id": "empty-does-not-ratify"})
    result = summarize_cohort(fixed, [mutual()], stamp(40))
    assert result["guardrails"]["status"] == "unratified"


def test_verified_completion_counts_even_if_like_telemetry_is_missing():
    source = episode([event("complete", 7, None, verified=True, provider_transaction_id="tx-exact")])
    result = summarize_cohort(cohort(), [source], stamp(40))
    assert result["primary_yield"]["numerator"] == 0
    assert result["verified_completion_yield"]["numerator"] == 1


def test_expiry_with_unsupported_completion_is_not_proven_noncompletion():
    source = mutual()
    source["followup"]["post_milestone_seconds"] = 14 * 86400
    source["observation"]["completion_supported"] = False
    source["observation"]["completion_complete_through"] = None
    result = reduce_episode(source, stamp(40))
    assert result["post_milestone"]["expired_without_confirmed_outcome"]
    assert result["post_milestone"]["expired_without_completion"] is None
    assert result["post_milestone"]["non_reversed"] is True
    assert result["currently_actionable_mutual"] is False


def test_counterparty_exposure_after_withdrawal_stays_separate():
    source = episode([event("like", 1), event("withdraw", 2), event("view", 3, "b"), event("like", 3, "b")])
    result = summarize_cohort(cohort(), [source], stamp(40))
    assert result["counterparty_conversion_after_first_interest"] == {"numerator": 0, "denominator": 1, "value": 0}
    assert result["episodes"][0]["counterparty_after_first_interest"]["exposure_lag_seconds"] == 2 * 86400
    assert result["counterparty_by_active_interest_at_exposure"]["false"]["denominator"] == 1
    assert result["nonresponse_count"] == 0
    assert result["withdrawn_or_undone_decision_count"] == 1


def test_conflicting_frozen_origins_are_unknown_not_double_arm_credit():
    left = mutual()
    right = deepcopy(left)
    right["episode_id"] = "alternate"
    right["origin"]["request_id"] = "conflicting-request"
    result = summarize_cohort(cohort(), [left, right], stamp(40))
    assert result["ambiguous_origin_concepts"] == ["concept"]
    assert result["observed_product_mutual_concepts"] == 1
    assert not result["observation_complete"]


def test_cluster_assignment_conflict_is_not_an_independent_card_experiment():
    fixed = cohort(2)
    fixed["members"][1]["assignment_arm"] = "Y"
    with pytest.raises(ValueError, match="connected cluster"):
        summarize_cohort(fixed, [], stamp(40))


def test_late_events_and_short_validity_keep_original_time_at_risk():
    source = episode([event("like", 1), event("view", 13, "b"), event("like", 13, "b")])
    result = reduce_episode(source, stamp(40))
    assert result["post_milestone"]["remaining_validity_seconds"] == 86400
    assert result["post_milestone"]["time_at_risk_seconds"] == 86400
    assert result["post_milestone"]["deadline"] == stamp(20)
    assert result["deadline"] == stamp(14)


def test_mirror_and_event_list_order_do_not_change_canonical_outcome():
    source = mutual()
    mirrored = deepcopy(source)
    mirrored["participants"].reverse()
    mirrored["events"].reverse()
    assert reduce_episode(source, stamp(40)) == reduce_episode(mirrored, stamp(40))


def test_simultaneous_rejection_cannot_make_zero_duration_mutual_interest():
    source = episode([event("like", 1), event("view", 3, "b"),
                      event("like", 3, "b"), event("reject", 3, event_id="zzz-reject")])
    result = reduce_episode(source, stamp(40))
    assert not result["historical_mutual"]
    assert not result["actors"]["b"]["expressed_interest"]


def test_late_attrition_preserved_but_fixed_followup_result_not_rewritten():
    source = mutual(event("withdraw", 12))  # post-milestone horizon ended day 10
    result = reduce_episode(source, stamp(40))
    assert result["historical_mutual"]
    assert result["post_milestone"]["non_reversed"] is True
    assert result["post_milestone"]["reversals"] == []
    assert [e["type"] for e in result["later_attrition"]] == ["withdraw"]
    assert not result["currently_actionable_mutual"]


def test_queue_undo_restoring_like_does_not_reverse_continuous_interest():
    source = mutual(event("queue", 4, event_id="queued"), event("undo", 5, target_event_id="queued"))
    result = reduce_episode(source, stamp(40))
    assert result["actors"]["a"]["decision"] == "like"
    assert result["post_milestone"]["non_reversed"] is True
    assert result["post_milestone"]["reversals"] == []


def test_exact_completion_closes_actionable_lifecycle_without_inventing_reversal():
    source = mutual(event("complete", 4, None, verified=True, provider_transaction_id="tx"))
    result = reduce_episode(source, stamp(6))
    assert result["lifecycle"] == {"state": "closed", "reason": "completed", "closed_at": stamp(4)}
    assert not result["currently_actionable_mutual"]
    assert result["historical_mutual"]
    assert result["later_attrition"] == []


@pytest.mark.parametrize("complete", [True, False])
def test_ownership_invalidation_is_not_manager_rejection(complete):
    events = [event("invalidate", 5, None, reason="ownership_changed")]
    if complete:
        events.append(event("complete", 4, None, verified=True, provider_transaction_id="tx"))
    result = reduce_episode(mutual(*events), stamp(40))
    assert result["historical_mutual"]
    assert result["post_milestone"]["non_reversed"] is True
    assert [row["type"] for row in result["post_milestone"]["validity_attrition"]] == ["invalidate"]
    assert result["post_milestone"]["reversals"] == []
    assert result["lifecycle"]["reason"] == ("completed" if complete else "invalidate")


def test_actual_match_cancellation_remains_an_explicit_reversal():
    result = reduce_episode(mutual(event("cancel", 5, None)), stamp(40))
    assert result["post_milestone"]["non_reversed"] is False
    assert [row["type"] for row in result["post_milestone"]["reversals"]] == ["cancel"]


def test_conflicting_same_window_history_cannot_hide_a_withdrawal():
    original = mutual()
    changed = mutual(event("withdraw", 5), index=1)
    declaration = {"preregistration_id": "fixture", "min_followup_coverage": 1, "max_reversal_rate": 0}
    result = summarize_cohort(cohort(guardrails=declaration), [original, changed], stamp(40))
    assert result["primary_yield"]["numerator"] == 1
    assert result["non_reversed_yield"]["numerator"] == 0
    assert result["guardrails"]["status"] == "evidence-limited"
    assert result["ambiguous_history_concepts"] == ["concept"]


@pytest.mark.parametrize("field,value", [("model_id", "other-model"), ("model_version", "other-version"), ("selected_source", None)])
def test_conflicting_frozen_model_or_source_identity_cannot_choose_convenient_row(field, value):
    original = mutual()
    changed = mutual(index=1)
    changed["origin"][field] = value
    result = summarize_cohort(cohort(), [original, changed], stamp(40))
    assert result["ambiguous_origin_concepts"] == ["concept"]
    assert not result["observation_complete"]


def test_completion_without_prior_overlap_does_not_backfill_mutual_likes():
    result = reduce_episode(episode([event("complete", 4, None, verified=True, provider_transaction_id="tx")]), stamp(6))
    assert not result["historical_mutual"]
    assert result["completion"]["verified_by_horizon"]
    assert result["lifecycle"]["reason"] == "completed"


@pytest.mark.parametrize("kind", ["invalidate", "cancel", "reject"])
def test_early_nonexpiry_closure_is_not_later_relabelled_as_expiry(kind):
    source = mutual(event(kind, 4))
    source["followup"]["post_milestone_seconds"] = 14 * 86400
    result = reduce_episode(source, stamp(40))
    assert result["lifecycle"]["reason"] == kind
    assert result["post_milestone"]["expired_without_confirmed_outcome"] is False


def test_explicit_early_expiry_uses_its_actual_time_for_expiry_diagnostic():
    result = reduce_episode(mutual(event("expire", 5, None)), stamp(40))
    assert result["lifecycle"]["closed_at"] == stamp(5)
    assert result["post_milestone"]["expired_without_confirmed_outcome"] is True


def test_post_completion_withdrawal_is_stale_evidence_not_reliable_reversal():
    source = mutual(event("complete", 4, None, verified=True, provider_transaction_id="tx"), event("withdraw", 5))
    result = reduce_episode(source, stamp(40))
    assert result["historical_mutual"]
    assert result["completion"]["verified_by_horizon"]
    assert result["lifecycle"]["reason"] == "completed"
    assert result["post_milestone"]["reversals"] == []
    assert result["post_milestone"]["non_reversed"] is None
    assert result["post_milestone"]["complete"] is False
    assert [action["type"] for action in result["stale_after_completion_actions"]] == ["withdraw"]


def test_real_precompletion_withdrawal_remains_separate_from_later_completion():
    source = mutual(event("withdraw", 4), event("complete", 5, None, verified=True, provider_transaction_id="tx"))
    result = reduce_episode(source, stamp(40))
    assert result["post_milestone"]["non_reversed"] is False
    assert [action["type"] for action in result["post_milestone"]["reversals"]] == ["withdraw"]
    assert result["stale_after_completion_actions"] == []
    assert result["completion"]["verified_by_horizon"]
