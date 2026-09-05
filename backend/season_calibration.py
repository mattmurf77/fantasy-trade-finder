"""Offline Win Now calibration; historical-validation-scope.md evidence contract.

Inputs are JSON objects with schema_version=1. Outcomes use season_history's
seasons format. Predictions contain records; each record has league_id, season,
as_of_week (completed weeks), model_family='win_now_player_week', model_version,
cutoff, forecast_captured_at, league_state_captured_at, prediction_created_at,
forecast_season, forecast_as_of_week, forecast_weeks, league_state_season,
league_state_as_of_week, provenance, and teams (season_simulator's team rows).
The forecast must be ONE archived full-horizon snapshot, never a splice of later
weekly forecasts. Teams supply playoff_probability, championship_probability,
and optionally expected_wins (regular-season outright wins, ties not half-wins).

Provenance requires kind='archived_prediction' or 'retrospective_replay', and
forecast/league_state/prediction each have an _evidence_ref and _sha256. Replay
also requires evaluation_protocol={kind:'frozen_holdout', fitting_cutoff,
holdout_ref}. Captures precede cutoff and creation; archived predictions precede
cutoff, whereas replay creation can be later. Checkpoints are a separate
{schema_version:1, checkpoints:[{league_id,season,as_of_week,cutoff,evidence_ref}]}
file, or per-season checkpoints. They represent independently reviewed kickoff
boundaries, not dates inferred from as_of_week or a provider's updated_at.

Explicit mode='exploratory_revised_inputs' additionally accepts provenance kind
'revised_historical_diagnostic' with record.assumptions (nonempty strings). Its
capture/creation timestamps remain the actual modern timestamps; season and week
labels describe the historical origin, and cutoff still needs date evidence.
These revised inputs are diagnostics, never historical calibration or holdouts.

These fields are ASSERTIONS: this offline tool validates consistency, not archive
authenticity, model fitting, holdout independence, or kickoff evidence. Hashes and
citations alone are not proof. All scores remain conditional, never certification
or automatic production graduation. No network, database, or model imports.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
import random
import re


def _time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp_required")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid_timestamp") from exc
    if stamp.tzinfo is None:
        raise ValueError("timezone_required")
    return stamp.astimezone(timezone.utc)


def _number(value, low=0, high=1):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and low <= value <= high)


def _key(row):
    return str(row.get("league_id", "")), str(row.get("season", ""))


def _outcome_error(season):
    if season.get("outcomes", {}).get("status") != "valid":
        return "outcomes_unavailable_or_excluded"
    teams = season["outcomes"].get("teams", [])
    ids = [t.get("roster_id") for t in teams]
    slots = season.get("settings", {}).get("playoff_teams")
    regular = season.get("settings", {}).get("playoff_week_start", 0) - 1
    if (not teams or len(ids) != len(set(ids)) or any(type(i) is not int for i in ids)
            or type(slots) is not int or not 1 <= slots <= len(teams) or regular < 1
            or season.get("settings", {}).get("num_teams", len(teams)) != len(teams)
            or not season.get("lineage_id")):
        return "invalid_outcome_cohort"
    if any(type(t.get("playoff")) is not bool or type(t.get("champion")) is not bool
           or not _number(t.get("wins"), 0, regular * (1 + bool(season.get("settings", {}).get("league_average_match")))) for t in teams):
        return "invalid_outcome_labels"
    if (sum(t["playoff"] for t in teams) != slots or sum(t["champion"] for t in teams) != 1
            or any(t["champion"] and not t["playoff"] for t in teams)):
        return "incomplete_outcome_labels"
    return None


def _validate(record, season, checkpoint, *, mode="strict"):
    diagnostic = (mode == "exploratory_revised_inputs"
                  and record.get("provenance", {}).get("kind") == "revised_historical_diagnostic")
    if record.get("model_family") != "win_now_player_week" or not record.get("model_version"):
        raise ValueError("wrong_or_missing_model_identity")
    week = record.get("as_of_week")
    settings = season["settings"]
    regular = settings["playoff_week_start"] - 1
    if type(week) is not int or not 0 <= week < regular:
        raise ValueError("invalid_as_of_week")
    if season.get("model_support", {}).get("supported") is not True:
        raise ValueError("unsupported_win_now_league")
    if not checkpoint or not checkpoint.get("evidence_ref"):
        raise ValueError("missing_checkpoint_reference")
    cutoff = _time(record.get("cutoff"))
    if cutoff != _time(checkpoint.get("cutoff")) or cutoff.year != int(record["season"]):
        raise ValueError("checkpoint_mismatch")
    captures = [_time(record.get(k)) for k in ("forecast_captured_at", "league_state_captured_at")]
    created = _time(record.get("prediction_created_at"))
    if any(t > created or (not diagnostic and t >= cutoff) for t in captures):
        raise ValueError("post_cutoff_or_post_creation_snapshot")
    if not diagnostic and any(t.year != int(record["season"]) for t in captures):
        raise ValueError("snapshot_season_mismatch")
    for prefix in ("forecast", "league_state"):
        if (str(record.get(prefix + "_season")) != str(record["season"])
                or type(record.get(prefix + "_as_of_week")) is not int
                or record[prefix + "_as_of_week"] != week):
            raise ValueError("snapshot_checkpoint_mismatch")
    final = regular + (2 if settings["playoff_teams"] == 4 else 3)
    if record.get("forecast_weeks") != list(range(week + 1, final + 1)):
        raise ValueError("incomplete_or_stitched_forecast_horizon")
    provenance = record.get("provenance", {})
    kind = provenance.get("kind")
    if not diagnostic and kind not in {"archived_prediction", "retrospective_replay"}:
        raise ValueError("missing_archived_provenance")
    if diagnostic:
        assumptions = record.get("assumptions")
        if (not isinstance(assumptions, list) or not assumptions
                or any(not isinstance(a, str) or not a.strip() for a in assumptions)):
            raise ValueError("missing_exploratory_assumptions")
    for prefix in ("forecast", "league_state", "prediction"):
        if (not isinstance(provenance.get(prefix + "_evidence_ref"), str)
                or not provenance[prefix + "_evidence_ref"].strip()
                or not re.fullmatch(r"[0-9a-fA-F]{64}", str(provenance.get(prefix + "_sha256", "")))):
            raise ValueError("missing_archive_evidence")
    if kind == "archived_prediction" and created >= cutoff:
        raise ValueError("post_cutoff_prediction")
    if kind == "retrospective_replay":
        protocol = record.get("evaluation_protocol", {})
        if (protocol.get("kind") != "frozen_holdout" or not protocol.get("holdout_ref")
                or _time(protocol.get("fitting_cutoff")) >= cutoff):
            raise ValueError("missing_or_leaking_holdout_protocol")
    teams = record.get("teams", [])
    actual = {t["roster_id"]: t for t in season["outcomes"]["teams"]}
    ids = [t.get("roster_id") for t in teams]
    if (any(type(i) is not int for i in ids) or len(ids) != len(set(ids))
            or set(ids) != set(actual)):
        raise ValueError("incomplete_duplicate_or_wrong_team_cohort")
    if sum("expected_wins" in t for t in teams) not in {0, len(teams)}:
        raise ValueError("partial_expected_wins_cohort")
    for team in teams:
        if any(not _number(team.get(k)) for k in ("playoff_probability", "championship_probability")):
            raise ValueError("invalid_probability")
        if team["championship_probability"] > team["playoff_probability"] + 1e-9:
            raise ValueError("title_exceeds_playoff_probability")
        if "expected_wins" in team and not _number(team["expected_wins"], 0, regular * (1 + bool(settings.get("league_average_match")))):
            raise ValueError("invalid_expected_wins")
    if (abs(sum(t["playoff_probability"] for t in teams) - settings["playoff_teams"]) > 1e-5
            or abs(sum(t["championship_probability"] for t in teams) - 1) > 1e-5):
        raise ValueError("incomplete_probability_mass")
    return [{**t, "actual": actual[t["roster_id"]], "baseline_playoff": settings["playoff_teams"] / len(teams),
             "baseline_title": 1 / len(teams)} for t in teams]


def _loss(p, y):
    p = min(1 - 1e-15, max(1e-15, p))
    return -(y * math.log(p) + (1 - y) * math.log1p(-p))


def _scores(rows, probability, outcome, baseline):
    n = len(rows)
    brier = sum((r[probability] - r["actual"][outcome]) ** 2 for r in rows) / n
    base_brier = sum((r[baseline] - r["actual"][outcome]) ** 2 for r in rows) / n
    logloss = sum(_loss(r[probability], r["actual"][outcome]) for r in rows) / n
    base_logloss = sum(_loss(r[baseline], r["actual"][outcome]) for r in rows) / n
    return {"brier": brier, "log_loss": logloss, "baseline_brier": base_brier,
            "baseline_log_loss": base_logloss,
            "brier_skill": 1 - brier / base_brier if base_brier else None,
            "log_loss_skill": 1 - logloss / base_logloss if base_logloss else None}


def _group_report(cohorts, bootstrap_samples, seed):
    rows = [r for c in cohorts for r in c["rows"]]
    clusters = defaultdict(list)
    for c in cohorts:
        clusters[str(c["lineage_id"])].extend(c["rows"])
    report = {"team_rows": len(rows), "league_seasons": len(cohorts), "lineages": len(clusters),
              "championship_events": len(cohorts), "metrics": {}}
    for name, probability, outcome, baseline in (
            ("playoff", "playoff_probability", "playoff", "baseline_playoff"),
            ("title", "championship_probability", "champion", "baseline_title")):
        scores = _scores(rows, probability, outcome, baseline)
        bins = []
        for i in range(10):
            members = [r for r in rows if min(9, int(r[probability] * 10)) == i]
            bins.append({"lower": i / 10, "upper": (i + 1) / 10, "count": len(members),
                         "mean_prediction": sum(r[probability] for r in members) / len(members) if members else None,
                         "observed_rate": sum(r["actual"][outcome] for r in members) / len(members) if members else None})
        scores["reliability_bins"] = bins
        # Entire lineages (all seasons and teams) move together. One lineage
        # cannot provide an empirical between-lineage interval.
        scores["lineage_bootstrap_95"] = None
        if len(clusters) >= 2 and bootstrap_samples >= 100:
            rng = random.Random(seed)
            keys = sorted(clusters)
            samples = defaultdict(list)
            for _ in range(bootstrap_samples):
                draw = [r for key in rng.choices(keys, k=len(keys)) for r in clusters[key]]
                for metric, value in _scores(draw, probability, outcome, baseline).items():
                    if value is not None:
                        samples[metric].append(value)
            scores["lineage_bootstrap_95"] = {
                k: [sorted(v)[int(.025 * (len(v) - 1))], sorted(v)[int(.975 * (len(v) - 1))]]
                for k, v in samples.items()}
        report["metrics"][name] = scores
    wins = [r for r in rows if "expected_wins" in r]
    report["expected_wins"] = {"team_rows": len(wins), "mae":
        sum(abs(r["expected_wins"] - r["actual"]["wins"]) for r in wins) / len(wins) if wins else None}
    if len(clusters) >= 2 and bootstrap_samples >= 100 and wins:
        rng = random.Random(seed)
        keys = sorted(clusters)
        samples = []
        for _ in range(bootstrap_samples):
            draw = [r for key in rng.choices(keys, k=len(keys)) for r in clusters[key] if "expected_wins" in r]
            if draw:
                samples.append(sum(abs(r["expected_wins"] - r["actual"]["wins"]) for r in draw) / len(draw))
        samples.sort()
        report["expected_wins"]["lineage_bootstrap_95"] = [samples[int(.025 * (len(samples) - 1))], samples[int(.975 * (len(samples) - 1))]]
    report["uncertainty"] = {"method": "lineage_cluster_percentile_bootstrap", "samples": bootstrap_samples,
        "seed": seed, "status": "insufficient_lineages" if len(clusters) < 2 else "exploratory",
        "caution": "Conditional on supplied provenance and cohort; few lineages give unstable intervals. Team rows and championships within a lineage are not independent."}
    return report


def evaluate_calibration(outcomes, predictions=None, checkpoints=None, *, bootstrap_samples=1000, seed=1701, mode="strict"):
    """Return a deterministic readiness/conditional-calibration report, never a gate."""
    if mode not in {"strict", "exploratory_revised_inputs"}:
        raise ValueError("invalid_evaluation_mode")
    if not isinstance(outcomes, dict) or outcomes.get("schema_version") != 1 or not isinstance(outcomes.get("seasons"), list):
        raise ValueError("invalid_outcomes_document")
    if predictions is not None and (not isinstance(predictions, dict) or predictions.get("schema_version") != 1 or not isinstance(predictions.get("records"), list)):
        raise ValueError("invalid_predictions_document")
    if checkpoints is not None and (not isinstance(checkpoints, dict) or checkpoints.get("schema_version") != 1 or not isinstance(checkpoints.get("checkpoints"), list)):
        raise ValueError("invalid_checkpoints_document")
    if type(bootstrap_samples) is not int or not 0 <= bootstrap_samples <= 10000:
        raise ValueError("invalid_bootstrap_samples")
    seasons = outcomes["seasons"]
    records = (predictions or {}).get("records", [])
    checkpoint_input = (checkpoints or {}).get("checkpoints", [])
    for name, rows in (("seasons", seasons), ("records", records), ("checkpoints", checkpoint_input)):
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("invalid_" + name + "_row")
            if any(not isinstance(row.get(k), (str, int)) or isinstance(row.get(k), bool)
                   for k in ("league_id", "season")):
                raise ValueError("invalid_" + name + "_identity")
            if name != "seasons" and not isinstance(row.get("as_of_week"), (int, str)):
                raise ValueError("invalid_" + name + "_checkpoint")
            if name == "records" and not isinstance(row.get("model_version"), (str, type(None))):
                raise ValueError("invalid_records_model_version")
    for season in seasons:
        if (not isinstance(season.get("settings"), dict)
                or not isinstance(season.get("outcomes"), dict)
                or not isinstance(season.get("model_support", {}), dict)
                or not isinstance(season["outcomes"].get("teams", []), list)
                or any(not isinstance(t, dict) for t in season["outcomes"].get("teams", []))
                or not isinstance(season.get("checkpoints", []), list)):
            raise ValueError("invalid_season_shape")
        for c in season.get("checkpoints", []):
            if not isinstance(c, dict) or type(c.get("as_of_week")) is not int:
                raise ValueError("invalid_season_checkpoint")
    counts = Counter(_key(s) for s in seasons)
    available, excluded = {}, []
    checkpoint_rows = list((checkpoints or {}).get("checkpoints", []))
    for s in seasons:
        try:
            reason = "duplicate_outcome_season" if counts[_key(s)] > 1 else _outcome_error(s)
        except (ValueError, TypeError, KeyError):
            reason = "invalid_outcome_cohort"
        if reason:
            excluded.append({"league_id": s.get("league_id"), "season": s.get("season"), "reason": reason})
        else:
            available[_key(s)] = s
            checkpoint_rows.extend({**c, "league_id": s["league_id"], "season": s["season"]} for c in s.get("checkpoints", []))
    checkpoint_counts = Counter((*_key(c), c.get("as_of_week")) for c in checkpoint_rows)
    references = {(*_key(c), c.get("as_of_week")): c for c in checkpoint_rows
                  if checkpoint_counts[(*_key(c), c.get("as_of_week"))] == 1}
    records = (predictions or {}).get("records", [])
    # Multiple model versions are separate groups, never pooled. Duplicates
    # within a model/checkpoint exclude ALL copies rather than cherry-picking.
    duplicates = Counter((*_key(r), r.get("as_of_week"), r.get("model_version")) for r in records)
    groups, rejections = defaultdict(list), []
    diagnostic_assumptions = []
    for index, r in enumerate(records):
        try:
            if duplicates[(*_key(r), r.get("as_of_week"), r.get("model_version"))] > 1:
                raise ValueError("duplicate_prediction_cohort")
            if _key(r) not in available:
                raise ValueError("missing_or_invalid_outcome_season")
            s = available[_key(r)]
            rows = _validate(r, s, references.get((*_key(r), r.get("as_of_week"))), mode=mode)
            group = (r["model_version"], r["as_of_week"], r["provenance"]["kind"])
            if group[2] == "revised_historical_diagnostic":
                diagnostic_assumptions.append({"record_index": index, "league_id": r["league_id"],
                    "season": r["season"], "as_of_week": r["as_of_week"], "assumptions": r["assumptions"]})
            groups[group].append({"rows": rows, "lineage_id": s["lineage_id"], "key": _key(r)})
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            rejections.append({"record_index": index, "league_id": r.get("league_id"),
                               "season": r.get("season"), "reason": str(exc)})
    eligible = sum(map(len, groups.values()))
    joined = {c["key"] for cohorts in groups.values() for c in cohorts}
    report = {"schema_version": 1, "status": "conditional_metrics" if eligible else "missing_eligible_archived_predictions",
        "certified": False, "provenance_scope": "Supplied archive citations, hashes, timestamps, cutoff evidence and holdout claims are unverified assertions; scores are conditional, not proof of historical calibration.",
        "production_change": False, "legacy_outlook_substituted": False,
        "availability": {"captured_seasons": len(seasons), "valid_outcome_seasons": len(available),
            "valid_outcome_lineages": len({str(s["lineage_id"]) for s in available.values()}),
            "model_supported_outcome_seasons": sum(s.get("model_support", {}).get("supported") is True for s in available.values()),
            "model_support_exclusions": [{"league_id": s["league_id"], "season": s["season"],
                "reasons": s.get("model_support", {}).get("reasons", ["model_support_not_established"])}
                for s in available.values() if s.get("model_support", {}).get("supported") is not True],
            "prediction_records": len(records), "eligible_prediction_cohorts": eligible,
            "eligible_unique_league_seasons": len(joined),
            "missing_eligible_predictions": [{"league_id": k[0], "season": k[1]} for k in sorted(set(available) - joined)]},
        "capture_exclusions": outcomes.get("exclusions", []), "outcome_exclusions": excluded,
        "prediction_rejections": rejections,
        "groups": [{"model_version": model, "as_of_week": week, "prediction_kind": kind,
                    **_group_report(cohorts, bootstrap_samples, seed)}
                   for (model, week, kind), cohorts in sorted(groups.items())]}

    if mode == "exploratory_revised_inputs":
        report.update(mode=mode,
            status="exploratory_diagnostic_metrics" if eligible else "missing_eligible_exploratory_predictions",
            provenance_scope="Revised historical inputs captured after the games may contain outcome leakage. These exploratory diagnostic metrics are not historical calibration, frozen-holdout evidence, or production validation.",
            exploratory_assumptions=diagnostic_assumptions)
    return report
