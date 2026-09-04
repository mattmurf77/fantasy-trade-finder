"""Win Now full-league season counterfactuals, independent of dynasty valuation.

Legal lineups are selected from forecasts BEFORE outcomes are realized. Seeded
player/week worlds are reusable across roster changes and bracket traversal.
Normal residuals are an explicitly uncalibrated experimental approximation;
Monte Carlo standard errors describe sampling error only, never model accuracy.
"""
from __future__ import annotations

from array import array
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import math
import random
import statistics

from .season_forecasts import (ForecastValidationError, MODEL_VERSION, content_hash,
                               score_stat_vector)

SLOT_POSITIONS = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
                  "FLEX": {"RB", "WR", "TE"}, "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
                  "REC_FLEX": {"WR", "TE"}, "WRRB_FLEX": {"WR", "RB"}}
BENCH_SLOTS = {"BN", "IR", "TAXI"}
METRICS = ("expected_wins", "expected_losses", "expected_ties", "expected_remaining_wins",
           "next_three_week_expected_wins", "win_credit", "projected_seed",
           "playoff_probability", "bye_probability", "championship_probability",
           "next_matchup_win_probability")


def _unsupported(reasons):
    return {"meta": {"supported": False, "reasons": sorted(set(reasons)),
                     "model_version": MODEL_VERSION}, "teams": []}


def required_forecast_weeks(league):
    start = int(league.get("completed_weeks", 0)) + 1
    end = int(league["regular_season_weeks"]) + (2 if int(league["playoff_slots"]) == 4 else 3)
    return list(range(start, end + 1))


def _validate(league, forecasts, n_sims):
    reasons = []
    if not isinstance(n_sims, int) or isinstance(n_sims, bool) or not 1 <= n_sims <= 10000:
        reasons.append("simulation_count_out_of_bounds")
    teams = league.get("teams") or []
    if not 4 <= len(teams) <= 20 or len({t["roster_id"] for t in teams}) != len(teams):
        reasons.append("unsupported_team_count")
    ids = [str(p) for t in teams for p in t.get("player_ids", [])]
    if len(ids) != len(set(ids)):
        reasons.append("duplicate_player_ownership")
    if len(ids) > 1000:
        reasons.append("roster_size_out_of_bounds")
    slots = [s for s in league.get("roster_slots", []) if s not in BENCH_SLOTS]
    if not slots or len(slots) > 12 or any(s not in SLOT_POSITIONS for s in slots):
        reasons.append("unsupported_roster_slots")
    if not league.get("scoring_settings"):
        reasons.append("missing_scoring_settings")
    pslots = int(league.get("playoff_slots", 0))
    if pslots not in {4, 6, 8} or pslots > len(teams):
        reasons.append("unsupported_playoff_format")
    if league.get("num_byes", 0) != (2 if pslots == 6 else 0):
        reasons.append("unsupported_playoff_byes")
    if league.get("num_divisions", 0):
        reasons.append("unsupported_division_seeding")
    if league.get("playoff_seed_type", 0) not in {0, 1}:
        reasons.append("unsupported_playoff_seed_type")
    if league.get("playoff_round_weeks", 1) != 1 or league.get("playoff_type", 0) != 0:
        reasons.append("unsupported_playoff_rounds")
    completed, regular = int(league.get("completed_weeks", 0)), int(league.get("regular_season_weeks", 0))
    if completed < 0 or regular < 1 or completed >= regular:
        reasons.append("unsupported_postseason_or_checkpoint")
    if league.get("playoff_start_week", regular + 1) != regular + 1:
        reasons.append("unsupported_playoff_start")
    if regular + (2 if pslots == 4 else 3) > 18:
        reasons.append("playoffs_exceed_nfl_horizon")
    if league.get("current_week_started") or league.get("status") in {"complete", "post_season", "in_game", "live"}:
        reasons.append("unsupported_live_or_completed_state")
    if league.get("doubleheaders") or league.get("custom_standings"):
        reasons.append("unsupported_standings_rules")
    if league.get("best_ball"):
        reasons.append("best_ball_unsupported")
    if not forecasts.get("supported", False):
        reasons += forecasts.get("reasons") or ["forecast_unavailable"]
    if str(forecasts.get("season")) != str(league.get("season")):
        reasons.append("forecast_season_mismatch")
    team_ids = {t["roster_id"] for t in teams}
    schedule = league.get("schedule", {})
    for week in range(completed + 1, regular + 1):
        pairs = schedule.get(week, schedule.get(str(week), []))
        seen = []
        for pair in pairs:
            if len(pair) != 2 or pair[0] == pair[1] or not set(pair) <= team_ids:
                reasons.append(f"invalid_schedule:{week}")
                continue
            seen.extend(pair)
        if Counter(seen) != Counter({rid: 1 for rid in team_ids}):
            reasons.append(f"incomplete_or_doubleheader_schedule:{week}")
    return sorted(set(reasons))


def _apply_trades(league, trades):
    changed = deepcopy(league)
    teams = {t["roster_id"]: t for t in changed["teams"]}
    for trade in trades or []:
        a, b = trade["buyer_roster_id"], trade["partner_roster_id"]
        give, receive = list(map(str, trade.get("give_ids", []))), list(map(str, trade.get("receive_ids", [])))
        if a == b or a not in teams or b not in teams:
            raise ForecastValidationError("invalid_trade_rosters")
        if len(give + receive) != len(set(give + receive)):
            raise ForecastValidationError("duplicate_trade_asset")
        aset, bset = set(map(str, teams[a]["player_ids"])), set(map(str, teams[b]["player_ids"]))
        if not set(give) <= aset or not set(receive) <= bset:
            raise ForecastValidationError("trade_asset_not_owned")
        teams[a]["player_ids"] = sorted(aset - set(give) | set(receive))
        teams[b]["player_ids"] = sorted(bset - set(receive) | set(give))
        # Starter metadata is historical lineup intent. Transferred starters no
        # longer belong to the roster; future assignments are recomputed below.
        teams[a]["starters"] = [p for p in teams[a].get("starters", []) if str(p) not in give]
        teams[b]["starters"] = [p for p in teams[b].get("starters", []) if str(p) not in receive]
    return changed


def select_projected_lineup(player_ids, roster_slots, week_rows, scoring_settings,
                            supported_scoring_keys=None):
    """Maximum-weight bipartite assignment (Hungarian), including flex overlap.

    Empty dummy players let a genuinely empty slot score zero. Callers decide
    whether incomplete coverage is supportable. Complexity O(slots² * players).
    """
    slots = [s for s in roster_slots if s not in BENCH_SLOTS]
    if not slots or any(s not in SLOT_POSITIONS for s in slots):
        raise ForecastValidationError("unsupported_roster_slots")
    candidates = sorted(p for p in set(map(str, player_ids)) if p in week_rows
                        and week_rows[p].get("availability") is not None)
    means = {p: score_stat_vector(week_rows[p], scoring_settings, supported_scoring_keys)
             * week_rows[p]["availability"] for p in candidates}
    columns = candidates + [None] * len(slots)
    costs = [[(-means[p] if set(week_rows[p]["positions"]) & SLOT_POSITIONS[s] else 1e12)
              if p is not None else 0.0 for p in columns] for s in slots]
    n, m = len(slots), len(columns)
    u, v, matched, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        matched[0], j0 = i, 0
        minimum, used = [math.inf] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = matched[j0], math.inf, 0
            for j in range(1, m + 1):
                if not used[j]:
                    current = costs[i0 - 1][j - 1] - u[i0] - v[j]
                    if current < minimum[j]:
                        minimum[j], way[j] = current, j0
                    if minimum[j] < delta:
                        delta, j1 = minimum[j], j
            for j in range(m + 1):
                if used[j]:
                    u[matched[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if matched[j0] == 0:
                break
        while True:
            j1 = way[j0]
            matched[j0] = matched[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = [None] * n
    for j in range(1, m + 1):
        if matched[j]:
            assignment[matched[j] - 1] = columns[j - 1]
    return {"player_ids": [p for p in assignment if p is not None],
            "slots": [{"slot": s, "player_id": p} for s, p in zip(slots, assignment)],
            "projected_points": sum(means[p] for p in assignment if p is not None),
            "empty_slots": sum(p is None for p in assignment)}


def projected_lineup_points(league, forecasts, trades=None):
    """Cheap pure roster-sensitive screen; returns weekly expected legal lineups."""
    reasons = _validate(league, forecasts, 1)
    if reasons:
        return {"supported": False, "reasons": reasons, "teams": []}
    try:
        league = _apply_trades(league, trades)
        rows = {(int(r["week"]), str(r["player_id"])): r for r in forecasts["forecasts"]}
        if len(rows) != len(forecasts["forecasts"]):
            raise ForecastValidationError("duplicate_player_week")
        output, warnings = [], set()
        for team in league["teams"]:
            weekly, lineups, missing_by_week, empty_by_week = {}, {}, {}, {}
            pids = set(map(str, team.get("player_ids", [])))
            starters = set(map(str, team.get("starters", []))) - {"0", ""}
            for week in required_forecast_weeks(league):
                week_rows = {p: rows[(week, p)] for p in pids if (week, p) in rows}
                missing = pids - set(week_rows)
                if missing & starters:
                    raise ForecastValidationError(f"missing_starter_forecast:{team['roster_id']}:{week}")
                unknown = {p for p, row in week_rows.items() if row.get("availability") is None}
                if unknown & starters:
                    raise ForecastValidationError(f"unknown_starter_availability:{team['roster_id']}:{week}")
                lineup = select_projected_lineup(pids, league["roster_slots"], week_rows,
                                                league["scoring_settings"], forecasts.get("supported_scoring_keys"))
                if lineup["empty_slots"] and (missing or unknown):
                    raise ForecastValidationError(f"incomplete_lineup_coverage:{team['roster_id']}:{week}")
                if unknown:
                    optimistic_rows = {p: dict(r, availability=1) if p in unknown else r for p, r in week_rows.items()}
                    optimistic = select_projected_lineup(pids, league["roster_slots"], optimistic_rows,
                                                         league["scoring_settings"], forecasts.get("supported_scoring_keys"))
                    if optimistic["projected_points"] > lineup["projected_points"] + 1e-9:
                        raise ForecastValidationError(f"unknown_contributor_availability:{team['roster_id']}:{week}")
                if missing or unknown:
                    warnings.add("unprojected_bench_excluded")
                missing_by_week[week] = sorted(missing | unknown)
                empty_by_week[week] = lineup["empty_slots"]
                weekly[week], lineups[week] = lineup["projected_points"], lineup["player_ids"]
            output.append({"roster_id": team["roster_id"], "weekly_points": weekly,
                           "weekly_lineups": lineups, "excluded_bench_ids": missing_by_week,
                           "empty_slots_by_week": empty_by_week})
        return {"supported": True, "reasons": [], "teams": output, "warnings": sorted(warnings)}
    except (ForecastValidationError, ValueError, TypeError, KeyError) as exc:
        return {"supported": False, "reasons": [str(exc)], "teams": []}


@lru_cache(maxsize=512)
def _player_worlds(league_id, season, player_id, week, n_sims, seed):
    """Draw coordinates are independent of roster, matchup, bracket, and call order."""
    identity = [str(league_id), str(season), str(player_id), week, seed]
    rng = random.Random(int(content_hash(identity)[:16], 16))
    return array("d", (value for _ in range(n_sims) for value in (rng.random(), rng.gauss(0, 1))))


def _seed_order(teams, wins, ties, points):
    # Sleeper regular-season ties credit half a win; PF is the known tiebreak.
    # Remaining exact ties use stable roster ID, explicitly disclosed in meta.
    return sorted(teams, key=lambda rid: (-wins[rid] - 0.5 * ties[rid], -points[rid], str(rid)))


def _champion(order, pslots, seed_type, scores, first_week):
    field = order[:pslots]
    rank = {rid: i for i, rid in enumerate(order)}

    def winner(a, b, week):
        if a is None:
            return b
        if b is None:
            return a
        sa, sb = scores[week][a], scores[week][b]
        return a if sa > sb or (sa == sb and rank[a] < rank[b]) else b

    week = first_week
    if seed_type == 0:
        shape = [1, 4, 2, 3] if pslots == 4 else [1, 8, 4, 5, 2, 7, 3, 6]
        alive = [field[s - 1] if s <= pslots else None for s in shape]
        while len(alive) > 1:
            alive = [winner(alive[i], alive[i + 1], week) for i in range(0, len(alive), 2)]
            week += 1
        return alive[0]
    byes = field[:2] if pslots == 6 else []
    active = field[len(byes):]
    alive = byes + [winner(active[i], active[-i - 1], week) for i in range(len(active) // 2)]
    week += 1
    while len(alive) > 1:
        alive.sort(key=rank.get)
        alive = [winner(alive[i], alive[-i - 1], week) for i in range(len(alive) // 2)]
        week += 1
    return alive[0]


def _run(league, forecasts, n_sims, seed, trades=None):
    reasons = _validate(league, forecasts, n_sims)
    if reasons:
        return _unsupported(reasons), None
    projected = projected_lineup_points(league, forecasts, trades)
    if not projected["supported"]:
        return _unsupported(projected["reasons"]), None
    league = _apply_trades(league, trades)
    teams = {t["roster_id"]: t for t in league["teams"]}
    rows = {(r["week"], r["player_id"]): r for r in forecasts["forecasts"]}
    lineups = {t["roster_id"]: t for t in projected["teams"]}
    weeks = required_forecast_weeks(league)
    completed, regular = league.get("completed_weeks", 0), league["regular_season_weeks"]
    selected = {(w, p) for t in projected["teams"] for w, players in t["weekly_lineups"].items() for p in players}
    outcomes = {}
    for week, pid in sorted(selected):
        row = rows[(week, pid)]
        mu = score_stat_vector(row, league["scoring_settings"], forecasts.get("supported_scoring_keys"))
        sigma = row.get("point_stddev")
        if sigma is None:
            sigma = max(3.0, abs(mu) * 0.6)
        worlds = _player_worlds(league["league_id"], league["season"], pid, week, n_sims, seed)
        # Linear score residual permits negative fantasy totals. Bye/inactive
        # outcomes are exactly zero, not Gaussian noise around zero.
        coordinates = iter(worlds)
        outcomes[(week, pid)] = array("d", (mu + sigma * z if u < row["availability"] else 0.0
                                                for u, z in zip(coordinates, coordinates)))
    samples = {rid: {metric: [] for metric in METRICS} for rid in teams}
    finishes, weekly_wins, weekly_ties = {rid: Counter() for rid in teams}, {rid: Counter() for rid in teams}, {rid: Counter() for rid in teams}
    pslots = league["playoff_slots"]
    for iteration in range(n_sims):
        scores = {w: {rid: sum(outcomes[(w, p)][iteration] for p in lineups[rid]["weekly_lineups"][w])
                      for rid in teams} for w in weeks}
        wins = {rid: float(t.get("wins", 0)) for rid, t in teams.items()}
        losses = {rid: float(t.get("losses", 0)) for rid, t in teams.items()}
        ties = {rid: float(t.get("ties", 0)) for rid, t in teams.items()}
        points = {rid: float(t.get("points_for", 0)) for rid, t in teams.items()}
        near_wins, next_win = Counter(), Counter()
        for week in range(completed + 1, regular + 1):
            schedule = league["schedule"]
            pairs = schedule.get(week, schedule.get(str(week), []))
            for a, b in pairs:
                for rid, other in ((a, b), (b, a)):
                    win = scores[week][rid] > scores[week][other]
                    tie = scores[week][rid] == scores[week][other]
                    wins[rid] += win
                    ties[rid] += tie
                    losses[rid] += not win and not tie
                    weekly_wins[rid][week] += win
                    weekly_ties[rid][week] += tie
                    if week <= completed + 3:
                        near_wins[rid] += win
                    if week == completed + 1:
                        next_win[rid] = float(win)
            if league.get("median_match"):
                median = statistics.median(scores[week].values())
                for rid in teams:
                    win, tie = scores[week][rid] > median, scores[week][rid] == median
                    wins[rid] += win
                    ties[rid] += tie
                    losses[rid] += not win and not tie
                    if week <= completed + 3:
                        near_wins[rid] += win
            for rid in teams:
                points[rid] += scores[week][rid]
        order = _seed_order(teams, wins, ties, points)
        champion = _champion(order, pslots, league.get("playoff_seed_type", 0), scores, regular + 1)
        for position, rid in enumerate(order, 1):
            finishes[rid][position] += 1
            values = {"expected_wins": wins[rid], "expected_losses": losses[rid], "expected_ties": ties[rid],
                      "expected_remaining_wins": wins[rid] - teams[rid].get("wins", 0),
                      "next_three_week_expected_wins": near_wins[rid], "win_credit": wins[rid] + 0.5 * ties[rid],
                      "projected_seed": position, "playoff_probability": float(position <= pslots),
                      "bye_probability": float(position <= league.get("num_byes", 0)),
                      "championship_probability": float(rid == champion), "next_matchup_win_probability": next_win[rid]}
            for metric, value in values.items():
                samples[rid][metric].append(value)
    output = []
    for rid, team in teams.items():
        result = {"roster_id": rid, "user_id": team.get("user_id", ""), "username": team.get("username", "")}
        result.update({metric: statistics.fmean(values) for metric, values in samples[rid].items()})
        result["finish_distribution"] = {str(pos): finishes[rid][pos] / n_sims for pos in range(1, len(teams) + 1)}
        result["weekly_win_probabilities"] = {str(w): weekly_wins[rid][w] / n_sims for w in range(completed + 1, regular + 1)}
        result["weekly_tie_probabilities"] = {str(w): weekly_ties[rid][w] / n_sims for w in range(completed + 1, regular + 1)}
        result["projected_lineup_points"] = {str(w): p for w, p in lineups[rid]["weekly_points"].items()}
        result["projected_lineups"] = {str(w): p for w, p in lineups[rid]["weekly_lineups"].items()}
        result["coverage"] = {"excluded_bench_ids": {str(w): p for w, p in lineups[rid]["excluded_bench_ids"].items()},
                              "empty_slots_by_week": {str(w): n for w, n in lineups[rid]["empty_slots_by_week"].items()}}
        output.append(result)
    meta = {"supported": True, "reasons": [], "warnings": projected["warnings"], "experimental": True,
            "model_version": MODEL_VERSION, "forecast_snapshot_id": forecasts.get("snapshot_id"),
            "league_input_hash": content_hash(league), "n_sims": n_sims, "seed": seed,
            "effective_week": completed + 1, "weeks": weeks, "captured_at": forecasts.get("captured_at"),
            "earliest_kickoff_at": forecasts.get("earliest_kickoff_at"),
            "calibrated": False, "championship_graduated": False,
            "lineup_assumption": "maximum projected points before outcomes; no best-ball hindsight",
            "residual_model": "independent player/week normal; max(3,0.6*abs(mean)) unless explicit scale",
            "correlation_model": "not modeled: shared NFL game/team effects and multiweek availability risk",
            "uncertainty": "Monte Carlo sampling error only; excludes model/projection uncertainty",
            "standings_tiebreak": "win credit, points for, stable roster ID",
            "playoff_tiebreak": "higher original seed", "median_match": bool(league.get("median_match"))}
    return {"meta": meta, "teams": output}, samples


def simulate_season(league, forecasts, n_sims=2000, seed=42, trades=None):
    """Pure deterministic simulation; unsupported input returns reasons and no odds."""
    return _run(league, forecasts, n_sims, seed, trades)[0]


def evaluate_trade(league, forecasts, buyer_roster_id, partner_roster_id,
                   give_ids, receive_ids, n_sims=2000, seed=42, baseline=None):
    """Paired full-league before/after simulation, including the partner's roster.

    The optional serialized baseline is verified for identity but never trusted
    as a source of paired samples. Recomputing with cached player worlds avoids
    accidental unpaired uncertainty or stale-baseline cache reuse.
    """
    trade = {"buyer_roster_id": buyer_roster_id, "partner_roster_id": partner_roster_id,
             "give_ids": give_ids, "receive_ids": receive_ids}
    try:
        _apply_trades(league, [trade])
    except (ForecastValidationError, KeyError, TypeError) as exc:
        return {"supported": False, "reasons": [str(exc)]}
    rows = {(r["week"], str(r["player_id"])): r for r in forecasts.get("forecasts", [])}
    for pid in map(str, list(give_ids) + list(receive_ids)):
        for week in required_forecast_weeks(league):
            row = rows.get((week, pid))
            if row is None or row.get("availability") is None:
                return {"supported": False, "reasons": [f"trade_asset_forecast_unavailable:{pid}:{week}"]}
    before, b_samples = _run(league, forecasts, n_sims, seed)
    if not before["meta"]["supported"]:
        return {"supported": False, "reasons": before["meta"]["reasons"]}
    if baseline is not None:
        for key in ("league_input_hash", "forecast_snapshot_id", "n_sims", "seed", "model_version"):
            if baseline.get("meta", {}).get(key) != before["meta"].get(key):
                return {"supported": False, "reasons": ["baseline_revision_mismatch"]}
    after, a_samples = _run(league, forecasts, n_sims, seed, [trade])
    if not after["meta"]["supported"]:
        return {"supported": False, "reasons": after["meta"]["reasons"]}
    b_rows, a_rows = {t["roster_id"]: t for t in before["teams"]}, {t["roster_id"]: t for t in after["teams"]}
    result = {"supported": True, "reasons": [], "paired": True, "meta": before["meta"],
              "trade": trade, "before": before, "after": after}
    for label, rid in (("buyer", buyer_roster_id), ("partner", partner_roster_id)):
        delta = {metric: a_rows[rid][metric] - b_rows[rid][metric] for metric in METRICS}
        uncertainty = {}
        for metric in METRICS:
            differences = [a - b for a, b in zip(a_samples[rid][metric], b_samples[rid][metric])]
            se = statistics.stdev(differences) / math.sqrt(n_sims) if n_sims > 1 else None
            uncertainty[metric] = {"standard_error": se, "lower_bound": delta[metric] - 1.96 * se if se is not None else None,
                                   "upper_bound": delta[metric] + 1.96 * se if se is not None else None,
                                   "paired": True, "kind": "monte_carlo_only"}
        regular_weeks = list(range(league.get("completed_weeks", 0) + 1, league["regular_season_weeks"] + 1))
        lineup_gain = statistics.fmean(a_rows[rid]["projected_lineup_points"][str(w)] - b_rows[rid]["projected_lineup_points"][str(w)] for w in regular_weeks)
        near_weeks = regular_weeks[:3]
        playoff_weeks = list(range(league["regular_season_weeks"] + 1, max(before["meta"]["weeks"]) + 1))
        horizon_gain = lambda weeks: statistics.fmean(a_rows[rid]["projected_lineup_points"][str(w)]
                                                     - b_rows[rid]["projected_lineup_points"][str(w)] for w in weeks)
        result[label] = {"next_three_week_lineup_gain": horizon_gain(near_weeks),
                         "playoff_lineup_gain": horizon_gain(playoff_weeks), "before": b_rows[rid], "after": a_rows[rid], "delta": delta,
                         "lineup_gain": lineup_gain, "uncertainty": uncertainty}
    return result
