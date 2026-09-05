"""Historical-validation scope: leak exclusions, joins, exact metrics, clustering.

All fixtures are synthetic test oracles, never empirical calibration evidence.
"""
from copy import deepcopy
import math

import pytest

from backend.season_calibration import evaluate_calibration


def fixture():
    teams = [{"roster_id": i, "wins": 2 if i <= 2 else 0,
              "playoff": i <= 4, "champion": i == 1} for i in range(1, 9)]
    outcomes = {"schema_version": 1, "seasons": [{"league_id": "a", "season": 2025,
        "lineage_id": "lineage-a", "settings": {"playoff_teams": 4, "playoff_week_start": 15},
        "model_support": {"supported": True}, "outcomes": {"status": "valid", "teams": teams}}]}
    record = {"league_id": "a", "season": 2025, "as_of_week": 0,
        "model_family": "win_now_player_week", "model_version": "player_week_normal_v1_experimental",
        "cutoff": "2025-09-04T23:00:00Z", "forecast_captured_at": "2025-09-01T00:00:00Z",
        "league_state_captured_at": "2025-09-01T00:00:00Z", "prediction_created_at": "2025-09-02T00:00:00Z",
        "forecast_season": 2025, "forecast_as_of_week": 0, "forecast_weeks": list(range(1, 17)),
        "league_state_season": 2025, "league_state_as_of_week": 0,
        "provenance": {"kind": "archived_prediction", **{f"{part}_{field}": value
            for part in ("forecast", "league_state", "prediction")
            for field, value in (("sha256", "a" * 64), ("evidence_ref", "synthetic test oracle"))}},
        "teams": [{"roster_id": i, "playoff_probability": .5, "championship_probability": .125,
                   "expected_wins": 1} for i in range(1, 9)]}
    predictions = {"schema_version": 1, "records": [record]}
    checkpoints = {"schema_version": 1, "checkpoints": [{"league_id": "a", "season": 2025,
        "as_of_week": 0, "cutoff": record["cutoff"], "evidence_ref": "synthetic kickoff oracle"}]}
    return outcomes, predictions, checkpoints


def test_missing_forecasts_reports_availability_without_inventing_metrics():
    outcomes, _, _ = fixture()
    report = evaluate_calibration(outcomes)
    assert report["status"] == "missing_eligible_archived_predictions"
    assert report["availability"]["valid_outcome_seasons"] == 1
    assert report["availability"]["missing_eligible_predictions"] == [{"league_id": "a", "season": "2025"}]
    assert report["groups"] == []
    assert report["certified"] is False


def test_uniform_baselines_exact_oracle_and_never_trust_operator_timestamps():
    report = evaluate_calibration(*fixture())
    group = report["groups"][0]
    assert group["metrics"]["playoff"]["brier"] == .25
    assert group["metrics"]["playoff"]["log_loss"] == pytest.approx(math.log(2))
    assert group["metrics"]["title"]["brier"] == .109375
    assert group["metrics"]["title"]["log_loss"] == pytest.approx(-(math.log(.125) + 7 * math.log(.875)) / 8)
    assert group["metrics"]["title"]["brier_skill"] == 0
    assert group["metrics"]["playoff"]["log_loss_skill"] == 0
    assert group["expected_wins"] == {"team_rows": 8, "mae": 1}
    assert group["metrics"]["playoff"]["reliability_bins"][5]["count"] == 8
    assert group["metrics"]["title"]["lineage_bootstrap_95"] is None
    assert group["championship_events"] == group["lineages"] == 1
    assert report["certified"] is False
    assert "unverified" in report["provenance_scope"]


@pytest.mark.parametrize("field,value,reason", [
    ("forecast_captured_at", "2026-09-01T00:00:00Z", "post_cutoff_or_post_creation_snapshot"),
    ("league_state_captured_at", "2025-10-01T00:00:00Z", "post_cutoff_or_post_creation_snapshot"),
    ("prediction_created_at", "2026-01-01T00:00:00Z", "post_cutoff_prediction"),
    ("forecast_captured_at", "2025-09-01", "timezone_required"),
    ("forecast_captured_at", None, "timestamp_required"),
    ("forecast_captured_at", "broken", "invalid_timestamp"),
    ("forecast_season", 2024, "snapshot_checkpoint_mismatch"),
    ("league_state_as_of_week", 1, "snapshot_checkpoint_mismatch"),
    ("forecast_weeks", [1], "incomplete_or_stitched_forecast_horizon"),
    ("as_of_week", 14, "invalid_as_of_week"),
    ("as_of_week", True, "invalid_as_of_week"),
    ("model_family", "outlook", "wrong_or_missing_model_identity"),
    ("model_version", None, "wrong_or_missing_model_identity"),
    ("cutoff", "2025-09-05T00:00:00Z", "checkpoint_mismatch"),
    ("season", 2024, "missing_or_invalid_outcome_season"),
    ("league_id", "wrong", "missing_or_invalid_outcome_season"),
])
def test_rejects_leakage_and_wrong_joins(field, value, reason):
    outcomes, predictions, checkpoints = fixture()
    predictions["records"][0][field] = value
    report = evaluate_calibration(outcomes, predictions, checkpoints)
    assert not report["groups"]
    assert report["prediction_rejections"][0]["reason"] == reason


def test_provider_updated_date_cannot_replace_actual_capture_or_archive_provenance():
    outcomes, predictions, checkpoints = fixture()
    record = predictions["records"][0]
    record["source_updated_at"] = "2025-09-01T00:00:00Z"
    record["forecast_captured_at"] = "2026-09-01T00:00:00Z"
    assert not evaluate_calibration(outcomes, predictions, checkpoints)["groups"]
    record["forecast_captured_at"] = record["source_updated_at"]
    record["provenance"]["kind"] = "current_fetch"
    assert evaluate_calibration(outcomes, predictions, checkpoints)["prediction_rejections"][0]["reason"] == "missing_archived_provenance"
    record["provenance"] = {}
    assert not evaluate_calibration(outcomes, predictions, checkpoints)["groups"]


def test_replay_today_with_archived_inputs_is_conditional_not_prospective():
    outcomes, predictions, checkpoints = fixture()
    record = predictions["records"][0]
    record["prediction_created_at"] = "2026-09-04T00:00:00Z"
    record["provenance"]["kind"] = "retrospective_replay"
    record["evaluation_protocol"] = {"kind": "frozen_holdout", "fitting_cutoff": "2025-08-01T00:00:00Z",
                                     "holdout_ref": "synthetic protocol"}
    assert evaluate_calibration(outcomes, predictions, checkpoints)["groups"][0]["prediction_kind"] == "retrospective_replay"
    record["evaluation_protocol"]["fitting_cutoff"] = "2026-01-01T00:00:00Z"
    assert not evaluate_calibration(outcomes, predictions, checkpoints)["groups"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong", "nan", "mass", "title_mass", "title_exceeds", "wins"])
def test_full_cohort_and_probability_validation(mutation):
    outcomes, predictions, checkpoints = fixture()
    teams = predictions["records"][0]["teams"]
    if mutation == "missing":
        teams.pop()
    elif mutation == "duplicate":
        teams.append(deepcopy(teams[0]))
    elif mutation == "wrong":
        teams[0]["roster_id"] = 100
    elif mutation == "nan":
        teams[0]["playoff_probability"] = float("nan")
    elif mutation == "mass":
        teams[0]["playoff_probability"] = .6
    elif mutation == "title_mass":
        teams[0]["championship_probability"] = .2
    elif mutation == "title_exceeds":
        teams[0]["championship_probability"] = .8
    else:
        teams[0]["expected_wins"] = 15
    assert not evaluate_calibration(outcomes, predictions, checkpoints)["groups"]


def test_duplicate_cohorts_all_excluded_and_models_never_pooled():
    outcomes, predictions, checkpoints = fixture()
    predictions["records"].append(deepcopy(predictions["records"][0]))
    report = evaluate_calibration(outcomes, predictions, checkpoints)
    assert not report["groups"]
    assert len(report["prediction_rejections"]) == 2
    predictions["records"][1]["model_version"] = "candidate-v2"
    report = evaluate_calibration(outcomes, predictions, checkpoints)
    assert len(report["groups"]) == 2
    assert report["availability"]["eligible_unique_league_seasons"] == 1
    assert all(g["team_rows"] == 8 for g in report["groups"])


def test_lineage_bootstrap_preserves_whole_cohorts_and_is_deterministic():
    outcomes, predictions, checkpoints = fixture()
    for league_id, lineage in (("b", "lineage-a"), ("c", "lineage-c")):
        season = deepcopy(outcomes["seasons"][0])
        season.update(league_id=league_id, lineage_id=lineage)
        outcomes["seasons"].append(season)
        record = deepcopy(predictions["records"][0])
        record["league_id"] = league_id
        predictions["records"].append(record)
        reference = deepcopy(checkpoints["checkpoints"][0])
        reference["league_id"] = league_id
        checkpoints["checkpoints"].append(reference)
    report = evaluate_calibration(outcomes, predictions, checkpoints, bootstrap_samples=100)
    assert report == evaluate_calibration(outcomes, predictions, checkpoints, bootstrap_samples=100)
    group = report["groups"][0]
    assert (group["team_rows"], group["league_seasons"], group["lineages"], group["championship_events"]) == (24, 3, 2, 3)
    assert group["metrics"]["playoff"]["lineage_bootstrap_95"]["brier"] == [.25, .25]


def test_no_independently_supplied_checkpoint_no_metrics():
    outcomes, predictions, checkpoints = fixture()
    assert not evaluate_calibration(outcomes, predictions)["groups"]
    checkpoints["checkpoints"].append(deepcopy(checkpoints["checkpoints"][0]))
    assert not evaluate_calibration(outcomes, predictions, checkpoints)["groups"]


def test_invalid_outcomes_and_unsupported_model_are_not_scored():
    outcomes, predictions, checkpoints = fixture()
    outcomes["seasons"][0]["model_support"]["supported"] = False
    report = evaluate_calibration(outcomes, predictions, checkpoints)
    assert report["availability"]["valid_outcome_seasons"] == 1
    assert report["prediction_rejections"][0]["reason"] == "unsupported_win_now_league"
    outcomes["seasons"][0]["outcomes"]["teams"][1]["champion"] = True
    assert evaluate_calibration(outcomes, predictions, checkpoints)["outcome_exclusions"][0]["reason"] == "incomplete_outcome_labels"


def test_median_outcomes_and_wins_use_two_games_per_week():
    outcomes, predictions, checkpoints = fixture()
    outcomes["seasons"][0]["settings"]["league_average_match"] = 1
    outcomes["seasons"][0]["outcomes"]["teams"][0]["wins"] = 22
    predictions["records"][0]["teams"][0]["expected_wins"] = 20
    report = evaluate_calibration(outcomes, predictions, checkpoints)
    assert report["availability"]["valid_outcome_seasons"] == 1
    assert report["groups"][0]["expected_wins"]["mae"] == 9 / 8


def test_no_partial_expected_wins_selection():
    outcomes, predictions, checkpoints = fixture()
    del predictions["records"][0]["teams"][0]["expected_wins"]
    assert evaluate_calibration(outcomes, predictions, checkpoints)["prediction_rejections"][0]["reason"] == "partial_expected_wins_cohort"
    for team in predictions["records"][0]["teams"]:
        team.pop("expected_wins", None)
    assert evaluate_calibration(outcomes, predictions, checkpoints)["groups"][0]["expected_wins"] == {"team_rows": 0, "mae": None}


def test_exact_kickoff_captures_fail_closed():
    outcomes, predictions, checkpoints = fixture()
    predictions["records"][0]["forecast_captured_at"] = predictions["records"][0]["cutoff"]
    assert not evaluate_calibration(outcomes, predictions, checkpoints)["groups"]


def test_support_readiness_missing_is_not_assumed_true():
    outcomes, predictions, checkpoints = fixture()
    del outcomes["seasons"][0]["model_support"]
    report = evaluate_calibration(outcomes, predictions, checkpoints)
    assert report["availability"]["model_supported_outcome_seasons"] == 0
    assert report["availability"]["model_support_exclusions"][0]["reasons"] == ["model_support_not_established"]
    assert not report["groups"]


@pytest.mark.parametrize("document,field,value", [
    ("predictions", "as_of_week", []), ("predictions", "model_version", {}),
    ("predictions", "league_id", []), ("checkpoints", "as_of_week", []),
])
def test_malformed_unhashable_input_is_controlled(document, field, value):
    outcomes, predictions, checkpoints = fixture()
    target = predictions["records"][0] if document == "predictions" else checkpoints["checkpoints"][0]
    target[field] = value
    with pytest.raises(ValueError, match="invalid_"):
        evaluate_calibration(outcomes, predictions, checkpoints)


def test_wrong_number_teams_and_duplicate_outcome_seasons_excluded():
    outcomes, predictions, checkpoints = fixture()
    outcomes["seasons"][0]["settings"]["num_teams"] = 12
    assert not evaluate_calibration(outcomes, predictions, checkpoints)["groups"]
    outcomes, predictions, checkpoints = fixture()
    outcomes["seasons"].append(deepcopy(outcomes["seasons"][0]))
    report = evaluate_calibration(outcomes, predictions, checkpoints)
    assert report["availability"]["valid_outcome_seasons"] == 0
    assert all(e["reason"] == "duplicate_outcome_season" for e in report["outcome_exclusions"])


def test_perfect_forecast_bins_include_one_and_log_loss_is_finite():
    outcomes, predictions, checkpoints = fixture()
    for t in predictions["records"][0]["teams"]:
        t["playoff_probability"] = float(t["roster_id"] <= 4)
        t["championship_probability"] = float(t["roster_id"] == 1)
    group = evaluate_calibration(outcomes, predictions, checkpoints)["groups"][0]
    assert group["metrics"]["playoff"]["brier"] == 0
    assert group["metrics"]["title"]["brier_skill"] == 1
    assert group["metrics"]["title"]["log_loss"] < 1e-12
    assert group["metrics"]["playoff"]["reliability_bins"][9]["count"] == 4


def diagnostic_fixture():
    outcomes, predictions, checkpoints = fixture()
    record = predictions['records'][0]
    record.update(forecast_captured_at='2026-09-04T10:00:00Z',
                  league_state_captured_at='2026-09-04T10:01:00Z',
                  prediction_created_at='2026-09-04T10:02:00Z',
                  assumptions=['Historical provider data are revised; outcome leakage is possible.'])
    record['provenance']['kind'] = 'revised_historical_diagnostic'
    return outcomes, predictions, checkpoints


def test_exploratory_requires_explicit_mode_and_preserves_honest_timestamps():
    data = diagnostic_fixture()
    before = deepcopy(data)
    strict = evaluate_calibration(*data)
    assert strict['groups'] == []
    assert strict['prediction_rejections'][0]['reason'] == 'post_cutoff_or_post_creation_snapshot'
    report = evaluate_calibration(*data, mode='exploratory_revised_inputs')
    assert data == before
    assert report['status'] == 'exploratory_diagnostic_metrics'
    assert report['groups'][0]['prediction_kind'] == 'revised_historical_diagnostic'
    assert report['groups'][0]['metrics']['playoff']['brier'] == .25
    assert report['exploratory_assumptions'][0]['assumptions'] == data[1]['records'][0]['assumptions']
    assert report['production_change'] is report['certified'] is False
    assert 'not historical calibration' in report['provenance_scope']
    assert 'outcome leakage' in report['provenance_scope']


@pytest.mark.parametrize('assumptions', [None, [], '', [''], ['  '], [False], ['Valid', None]])
def test_exploratory_rejects_missing_or_invalid_assumptions(assumptions):
    outcomes, predictions, checkpoints = diagnostic_fixture()
    predictions['records'][0]['assumptions'] = assumptions
    report = evaluate_calibration(outcomes, predictions, checkpoints, mode='exploratory_revised_inputs')
    assert report['status'] == 'missing_eligible_exploratory_predictions'
    assert report['prediction_rejections'][0]['reason'] == 'missing_exploratory_assumptions'


@pytest.mark.parametrize('mutation,reason', [
    ('capture_after_creation', 'post_cutoff_or_post_creation_snapshot'),
    ('missing_hash', 'missing_archive_evidence'),
    ('missing_reference', 'missing_archive_evidence'),
    ('missing_checkpoint', 'missing_checkpoint_reference'),
    ('unsupported', 'unsupported_win_now_league'),
    ('wrong_model', 'wrong_or_missing_model_identity'),
    ('wrong_origin', 'snapshot_checkpoint_mismatch'),
    ('partial_horizon', 'incomplete_or_stitched_forecast_horizon'),
    ('partial_cohort', 'incomplete_duplicate_or_wrong_team_cohort'),
    ('invalid_probability', 'invalid_probability'),
])
def test_exploratory_retains_evidence_model_and_numeric_guards(mutation, reason):
    outcomes, predictions, checkpoints = diagnostic_fixture()
    record = predictions['records'][0]
    if mutation == 'capture_after_creation':
        record['forecast_captured_at'] = '2026-09-05T00:00:00Z'
    elif mutation == 'missing_hash':
        del record['provenance']['forecast_sha256']
    elif mutation == 'missing_reference':
        record['provenance']['league_state_evidence_ref'] = ''
    elif mutation == 'missing_checkpoint':
        checkpoints = None
    elif mutation == 'unsupported':
        outcomes['seasons'][0]['model_support']['supported'] = False
    elif mutation == 'wrong_model':
        record['model_family'] = 'outlook'
    elif mutation == 'wrong_origin':
        record['forecast_as_of_week'] = 1
    elif mutation == 'partial_horizon':
        record['forecast_weeks'].pop()
    elif mutation == 'partial_cohort':
        record['teams'].pop()
    else:
        record['teams'][0]['playoff_probability'] = float('nan')
    report = evaluate_calibration(outcomes, predictions, checkpoints, mode='exploratory_revised_inputs')
    assert report['groups'] == []
    assert report['prediction_rejections'][0]['reason'] == reason


def test_exploratory_does_not_relax_archived_kind_and_strict_rejects_revised_kind():
    outcomes, predictions, checkpoints = diagnostic_fixture()
    predictions['records'][0]['provenance']['kind'] = 'archived_prediction'
    assert not evaluate_calibration(outcomes, predictions, checkpoints, mode='exploratory_revised_inputs')['groups']
    outcomes, predictions, checkpoints = fixture()
    predictions['records'][0]['provenance']['kind'] = 'revised_historical_diagnostic'
    report = evaluate_calibration(outcomes, predictions, checkpoints)
    assert report['prediction_rejections'][0]['reason'] == 'missing_archived_provenance'


def test_explicit_strict_mode_is_identical_to_default():
    assert evaluate_calibration(*fixture()) == evaluate_calibration(*fixture(), mode='strict')
    with pytest.raises(ValueError, match='invalid_evaluation_mode'):
        evaluate_calibration(*fixture(), mode='anything')
