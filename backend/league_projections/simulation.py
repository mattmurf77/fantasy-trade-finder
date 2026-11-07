"""Deterministic shared-world actual-score / Max PF scenarios, with bounded work."""
from __future__ import annotations

from collections import Counter
import math
import random
import statistics

from .core import Unavailable, VERSION, decimal, digest

POLICIES = {
    "seeding": {"record_pf_higher_pa_random"},
    "draft_tie": {"random_exact_ties"},
    "ir_maxpf": {"include", "exclude"},
    "reserve_activation": {"exclude_current_reserve"},
    "empty_slots": {"allow", "fill_available"},
    "maxpf_variance": {"reconstructed_history", "actual_history_proxy"},
    "scoring_contract": {"strict_supplied_v1", "sleeper_sparse_offense_v1"},
    "availability_scenario": {"require_verified", "conditional_provider_forecast"},
}


def config(raw):
    if not isinstance(raw, dict):
        raise ValueError("configuration_required")
    allowed = set(POLICIES) | {"iterations", "seed", "historical_weight", "min_pick_samples", "persistent_sd", "residual_correlation", "score_decimals", "draft_season", "draft_round"}
    if set(raw) - allowed:
        raise ValueError("unknown_configuration")
    result = dict(raw)
    result.setdefault("availability_scenario", "require_verified")
    result.setdefault("scoring_contract", "strict_supplied_v1")
    for key, values in POLICIES.items():
        if result.get(key) not in values:
            raise Unavailable("policy_required", details={"policy": key, "options": sorted(values)})
    for key, default, low, high in (("iterations", 250000, 100, 250000), ("seed", 42, 0, 2147483647),
                                   ("min_pick_samples", 100, 1, 10000), ("score_decimals", 2, 0, 3),
                                   ("draft_round", 1, 1, 10), ("draft_season", 2027, 2020, 2100)):
        value = result.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError("invalid_" + key)
        result[key] = value
    for key, default, low, high in (("historical_weight", .6, 0, 1), ("persistent_sd", 5, 0, 50)):
        value = float(decimal(result.get(key, default)))
        if not low <= value <= high:
            raise ValueError("invalid_" + key)
        result[key] = value
    # No universal 0.818 correlation: caller must choose a visible scenario or
    # request a paired-history estimate with sufficient reconstructed weeks.
    rho = result.get("residual_correlation")
    if rho != "estimate_history":
        if rho is None or not -1 <= float(decimal(rho)) <= 1:
            raise Unavailable("correlation_scenario_required")
        rho = float(decimal(rho))
    result["residual_correlation"] = rho
    return result


def _variance(values):
    return statistics.variance(values) if len(values) > 1 else None


def _quantile(values, fraction):
    return values[min(len(values) - 1, int((len(values) - 1) * fraction))]


def simulate(snapshot, raw_config, *, cancelled=lambda: False):
    cfg = config(raw_config)
    teams = sorted(snapshot["teams"], key=lambda t: t["roster_id"])
    ids = [t["roster_id"] for t in teams]
    n, iterations = len(ids), cfg["iterations"]
    if n < 2 or n > 32 or len(set(ids)) != n:
        raise Unavailable("invalid_team_set")
    playoff, byes = int(snapshot["playoff_spots"]), int(snapshot["playoff_byes"])
    if not 0 < playoff <= n or not 0 <= byes <= playoff:
        raise Unavailable("invalid_playoff_configuration")
    weeks = sorted(snapshot["weeks"], key=lambda w: w["week"])
    if len(weeks) > 18:
        raise Unavailable("invalid_horizon")
    index = {rid: i for i, rid in enumerate(ids)}
    games, means, max_means, details = [], [], [], []
    weight = cfg["historical_weight"]
    actual_history = [[float(decimal(v)) for v in t["actual_history"]] for t in teams]
    max_history = [[float(decimal(v)) for v in t["maxpf_history"]] for t in teams]
    completed = snapshot["completed_weeks"]
    if any(len(h) != completed for h in actual_history):
        raise Unavailable("missing_actual_history", state="incomplete_projections")
    if any(len(h) not in (0, completed) for h in max_history):
        raise Unavailable("partial_maxpf_history", state="incomplete_projections")
    # With no/one observed week, explicit projection residual scales are required.
    pooled = [v - statistics.mean(h) for h in actual_history if len(h) > 1 for v in h]
    pool_var = _variance(pooled)
    sd = []
    max_sd = []
    for i, team in enumerate(teams):
        team_var = _variance(actual_history[i])
        variance = .5 * team_var + .5 * pool_var if team_var is not None and pool_var is not None else None
        if not weeks:
            variance = 0
        if variance is None:
            if "projection_weekly_sd" not in team:
                raise Unavailable("short_history_variance_prior_required", state="incomplete_projections")
            variance = float(decimal(team["projection_weekly_sd"])) ** 2
        sd.append(math.sqrt(max(0, variance)))
        mv = _variance(max_history[i])
        if not weeks:
            mv = 0
        if mv is None and cfg["maxpf_variance"] == "actual_history_proxy":
            mv = variance
        if mv is None:
            if "maxpf_weekly_sd" not in team:
                raise Unavailable("maxpf_variance_prior_required", state="incomplete_projections")
            mv = float(decimal(team["maxpf_weekly_sd"])) ** 2
        max_sd.append(math.sqrt(max(0, mv)))
    rho = cfg["residual_correlation"]
    if rho == "estimate_history":
        paired = [(a - statistics.mean(ah), m - statistics.mean(mh))
                  for ah, mh in zip(actual_history, max_history) if len(ah) == len(mh) and len(ah) >= 4
                  for a, m in zip(ah, mh)]
        if len(paired) < 24:
            raise Unavailable("insufficient_paired_history", state="incomplete_projections")
        x, y = zip(*paired)
        if not statistics.stdev(x) or not statistics.stdev(y):
            raise Unavailable("degenerate_paired_history", state="incomplete_projections")
        rho = max(-1., min(1., statistics.correlation(x, y)))
    for week in weeks:
        matchups = [(index[a], index[b]) for a, b in week["games"] if a in index and b in index]
        participants = [i for pair in matchups for i in pair]
        if len(participants) != n or sorted(participants) != list(range(n)) or any(a == b for a, b in matchups):
            raise Unavailable("incomplete_or_multiple_matchups", state="incomplete_projections")
        if set(week["teams"]) != set(map(str, ids)):
            raise Unavailable("incomplete_week_teams", state="incomplete_projections")
        wm, mm, wd = [], [], []
        for i, team in enumerate(teams):
            detail = week["teams"][str(team["roster_id"])]
            optimized, optimal = float(decimal(detail["actual"]["points"])), float(decimal(detail["maxpf"]["points"]))
            history = float(decimal(team["points_for"])) / completed if completed else optimized
            max_base = float(decimal(team["maxpf"])) / completed if completed else optimal
            wm.append(weight * history + (1 - weight) * optimized)
            mm.append(weight * max_base + (1 - weight) * optimal)
            wd.append(detail)
        games.append(matchups)
        means.append(wm)
        max_means.append(mm)
        details.append(wd)
    base_records = [[int(t[k]) for k in ("wins", "losses", "ties")] for t in teams]
    if any(sum(r) != completed or min(r) < 0 for r in base_records):
        raise Unavailable("unreconciled_records")
    if sum(r[0] for r in base_records) != sum(r[1] for r in base_records):
        raise Unavailable("unreconciled_league_records")
    base_pf = [float(decimal(t["points_for"])) for t in teams]
    base_pa = [float(decimal(t["points_against"])) for t in teams]
    base_max = [float(decimal(t["maxpf"])) for t in teams]
    if any(abs(sum(h) - pf) > .001 for h, pf in zip(actual_history, base_pf)):
        raise Unavailable("unreconciled_points_for")
    maxpf_discrepancy = [sum(h) - maximum if h else None for h, maximum in zip(max_history, base_max)]
    picks = n - playoff
    record_counts, pick_counts = [Counter() for _ in teams], [[0] * picks for _ in teams]
    playoff_counts, bye_counts = [0] * n, [0] * n
    max_totals = [[] for _ in teams]
    weekly_outcomes = [[[0, 0, 0] for _ in teams] for _ in weeks]
    # Streaming moments expose the uplift introduced by the joint-world floor.
    maxpf_diagnostics = [[[0., 0., 0., 0] for _ in teams] for _ in weeks]
    owner_for = {rid: rid for rid in ids}
    for pick in snapshot.get("pick_ownership", []):
        if pick["season"] == cfg["draft_season"] and pick["round"] == cfg["draft_round"]:
            if pick["original_roster_id"] not in index or pick["owner_roster_id"] not in index:
                raise Unavailable("unknown_pick_owner", state="incomplete_projections")
            owner_for[pick["original_roster_id"]] = pick["owner_roster_id"]
    owner_count, owner_any = [0] * n, [0] * n
    rng, precision = random.Random(cfg["seed"]), cfg["score_decimals"]
    for iteration in range(iterations):
        if iteration % 500 == 0 and cancelled():
            raise Unavailable("cancelled", state="cancelled")
        records = [r[:] for r in base_records]
        pf, pa, maxpf = base_pf[:], base_pa[:], base_max[:]
        strength = [rng.gauss(0, cfg["persistent_sd"]) for _ in teams]
        for w, matchups in enumerate(games):
            scores = []
            for i in range(n):
                z = rng.gauss(0, 1)
                actual = round(means[w][i] + strength[i] + sd[i] * z, precision)
                maximum = round(max_means[w][i] + strength[i] + max_sd[i] * (rho * z + math.sqrt(1 - rho * rho) * rng.gauss(0, 1)), precision)
                before_floor = maximum
                if details[w][i].get("maxpf_dominates_actual"):
                    maximum = max(maximum, actual)
                diagnostic = maxpf_diagnostics[w][i]
                diagnostic[0] += before_floor
                diagnostic[1] += maximum
                diagnostic[2] += maximum - before_floor
                diagnostic[3] += int(maximum > before_floor)
                scores.append(actual)
                pf[i] += actual
                maxpf[i] += maximum
            for a, b in matchups:
                pa[a] += scores[b]
                pa[b] += scores[a]
                outcome = 0 if scores[a] > scores[b] else 1 if scores[a] < scores[b] else 2
                opposite = 1 - outcome if outcome < 2 else 2
                records[a][outcome] += 1
                records[b][opposite] += 1
                weekly_outcomes[w][a][outcome] += 1
                weekly_outcomes[w][b][opposite] += 1
        # Fresh seeded tie lottery in each world, never provider roster ordering.
        lottery = [rng.random() for _ in teams]
        standings = sorted(range(n), key=lambda i: (2 * records[i][0] + records[i][2], round(pf[i], precision), round(pa[i], precision), lottery[i]), reverse=True)
        for i in standings[:playoff]:
            playoff_counts[i] += 1
        for i in standings[:byes]:
            bye_counts[i] += 1
        nonplayoff = sorted(standings[playoff:], key=lambda i: (round(maxpf[i], precision), rng.random()))
        owners = Counter()
        for slot, i in enumerate(nonplayoff):
            pick_counts[i][slot] += 1
            owners[index[owner_for[ids[i]]]] += 1
        for i, count in owners.items():
            owner_count[i] += count
            owner_any[i] += 1
        for i in range(n):
            record_counts[i][tuple(records[i])] += 1
            max_totals[i].append(maxpf[i])
    output = []
    for i, team in enumerate(teams):
        missed = iterations - playoff_counts[i]
        totals = sorted(max_totals[i])
        probability = playoff_counts[i] / iterations
        counts = pick_counts[i]
        modal = sorted(record_counts[i], key=lambda r: (-record_counts[i][r], r))[0]
        output.append({"roster_id": ids[i], "name": team["name"], "current_record": base_records[i],
                       "current_points_for": base_pf[i], "current_ppg": base_pf[i] / completed if completed else None,
                       "current_maxpf": base_max[i], "expected_record": [sum(r[k] * count for r, count in record_counts[i].items()) / iterations for k in range(3)],
                       "final_record_distribution": [{"record": list(r), "probability": count / iterations} for r, count in sorted(record_counts[i].items())],
                       "maxpf_history_minus_official": maxpf_discrepancy[i],
                       "modal_record": list(modal), "modal_record_probability": record_counts[i][modal] / iterations,
                       "playoff_probability": probability, "playoff_mc_standard_error": math.sqrt(probability * (1 - probability) / iterations),
                       "bye_probability": bye_counts[i] / iterations, "nonplayoff_probability": missed / iterations,
                       "pick_probabilities": [count / iterations for count in counts],
                       "conditional_pick_probabilities": [count / missed for count in counts] if missed >= cfg["min_pick_samples"] else None,
                       "conditional_expected_pick": sum((k + 1) * count for k, count in enumerate(counts)) / missed if missed >= cfg["min_pick_samples"] else None,
                       "nonplayoff_samples": missed, "maxpf_mean": statistics.mean(totals),
                       "maxpf_quantiles": {str(q): _quantile(totals, q) for q in (.1, .5, .9)},
                       "maxpf_history": team["maxpf_history"], "maxpf_per_completed_week": base_max[i] / completed if completed else None,
                       "pick_owner_roster_id": owner_for[ids[i]], "owner_expected_nonplayoff_picks": owner_count[i] / iterations,
                       "owner_probability_at_least_one": owner_any[i] / iterations,
                       "owner_expected_picks_by_slot": [sum(pick_counts[j][k] for j in range(n) if owner_for[ids[j]] == ids[i]) / iterations for k in range(picks)],
                       "weeks": [{"week": week["week"], **details[w][i], "win_probability": weekly_outcomes[w][i][0] / iterations,
                                  "maxpf_floor": {"input_mean": max_means[w][i],
                                      "simulated_pre_floor_mean": maxpf_diagnostics[w][i][0] / iterations,
                                      "simulated_mean": maxpf_diagnostics[w][i][1] / iterations,
                                      "mean_uplift": maxpf_diagnostics[w][i][2] / iterations,
                                      "frequency": maxpf_diagnostics[w][i][3] / iterations},
                                  "modeled_score_mean": means[w][i], "historical_component": weight * base_pf[i] / completed if completed else 0,
                                  "projection_component": (1 - weight) * float(decimal(details[w][i]["actual"]["points"])) if completed else means[w][i], "modeled_score_sd": math.sqrt(sd[i] ** 2 + cfg["persistent_sd"] ** 2),
                                  "score_distribution": "normal_scenario_rounded_to_league_precision",
                                  "win_equivalent_probability": (weekly_outcomes[w][i][0] + .5 * weekly_outcomes[w][i][2]) / iterations,
                                  "loss_probability": weekly_outcomes[w][i][1] / iterations, "tie_probability": weekly_outcomes[w][i][2] / iterations,
                                  "opponent_roster_id": ids[next(b if a == i else a for a, b in games[w] if i in (a, b))]}
                                 for w, week in enumerate(weeks)]})
    return {"schema": 1, "league_name": snapshot.get("league_name", "League"), "season": snapshot.get("season"),
            "completed_weeks": completed, "playoff_spots": playoff, "playoff_byes": byes, "scoring": snapshot.get("scoring", {}),
            "model_version": VERSION, "status": "complete", "provisional": iterations < 250000,
            "iterations": iterations, "seed": cfg["seed"], "config": cfg, "snapshot_hash": digest(snapshot),
            "source": snapshot["source"], "captured_at": snapshot["captured_at"], "coverage": snapshot.get("coverage", {}),
            "residual_correlation_used": rho, "teams": output, "draft_sort": "projected_maxpf_mean",
            "warnings": ["Scenario estimates; model accuracy has not been established.",
                         "Monte Carlo error excludes model and provider uncertainty.",
                         "Optimizing expected points understates the expected hindsight optimum.",
                         "The joint model floors eligible Max PF at actual scores; this increases its mean and affects draft odds. Weekly diagnostics quantify this uncalibrated effect.",
                         "Playoff-team draft positions are not projected.",
                         "IDP bye replacements are hypothetical, not verified waiver availability."] +
                        (["Short history: fewer than four completed weeks."] if completed < 4 else []) +
                        (["Reconstructed Max PF history differs from official totals; only its variance is used."] if any(d is not None and abs(d) > .001 for d in maxpf_discrepancy) else []) + snapshot.get("warnings", [])}
