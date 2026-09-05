"""Whole-roster outlook benefit; pure inputs, no flags, providers or I/O.

See docs/plans/trade-model-activation/outlook-utility.md for the integration
contract. Dynasty values never stand in for projected fantasy points.
"""
from dataclasses import replace
import math
from typing import Mapping

from .trade_roster import Asset, ELIGIBILITY, Rules, Team, assign

# Match the existing outlook blend defaults, without importing its config/DB.
# These are transparent preference weights, not fitted acceptance probabilities.
_NOW_WEIGHT = {"championship": 1.0, "contender": .75, "balanced": .5,
               "rebuilder": .25, "jets": .1}
_POINT_UNITS = {"fantasy_points_per_game", "fantasy_points_for_period"}


def resolve_outlook(*, explicit: str | None = None, inferred: str | None = None,
                    inference_fresh: bool = False) -> dict:
    """Resolve ONE manager's intent; freshness must be asserted by the caller.

    Explicit `not_sure` is a choice, not a gap for inference to overwrite.
    Inference confidence is a conservative evidence weight, not the unbounded
    direction score returned by trade_service.infer_team_outlook.
    """
    explicit = "balanced" if explicit == "not_sure" else explicit
    inferred = "balanced" if inferred == "not_sure" else inferred
    if explicit in _NOW_WEIGHT:
        return {"value": explicit, "source": "explicit", "confidence": 1.0,
                "reason": "manager_declared_outlook", "uncertainties": []}
    if explicit is not None:
        reason = "invalid_explicit_outlook"
    elif inferred in _NOW_WEIGHT and inference_fresh:
        value = {"championship": "contender", "jets": "rebuilder"}.get(inferred, inferred)
        return {"value": value, "source": "inferred", "confidence": .5,
                "reason": "fresh_roster_inference",
                "uncertainties": ["manager_intent_inferred"]}
    else:
        reason = "outlook_inference_stale_or_unknown" if inferred else "outlook_unavailable"
    return {"value": "balanced", "source": "fallback", "confidence": .25,
            "reason": reason, "uncertainties": [reason]}


def _finite(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def _component(before, after, unit, weight=0.0) -> dict:
    known = before is not None and after is not None
    # No additive unit-dependent floor; reversible and invariant to rescaling.
    scale = max(before, after) if known else None
    gain = (after - before) / scale if scale else 0.0 if known else None
    return {"before": before, "after": after,
            "delta": after - before if known else None,
            "normalized_gain": gain, "normalization_scale": scale,
            "unit": unit, "weight": weight}


def evaluate_outlook_utility(*, before: Team, after: Team,
                             assets: Mapping[str, Asset], rules: Rules,
                             explicit_outlook: str | None = None,
                             inferred_outlook: str | None = None,
                             inference_fresh: bool = False,
                             projections: Mapping[str, float] | None = None,
                             projection_basis: str | None = None,
                             projection_unit: str | None = None,
                             projections_fresh: bool = False) -> dict:
    """Compare complete rosters AFTER any caller-resolved cuts/inactive changes.

    Return a JSON-ready dict; attach it under a roster team's outlook_utility.
    Team.outlook is intentionally ignored: that field loses explicit/inferred
    provenance. Pass each manager's declaration or fresh inference separately.
    Projections must cover every available eligible player on BOTH rosters,
    share one scoring scheme/horizon, and be explicitly fresh. No imputation.

    This measures preference benefit, never eligibility. The caller must keep
    trade_roster's two-team blockers/unknowns and all existing policy gates.
    """
    outlook = resolve_outlook(explicit=explicit_outlook, inferred=inferred_outlook,
                              inference_fresh=inference_fresh)
    now_weight = _NOW_WEIGHT[outlook["value"]]
    future_weight = 1 - now_weight
    uncertainties = list(outlook["uncertainties"])
    production = _component(None, None, projection_unit, now_weight)
    future = _component(None, None, "dynasty_value", future_weight)
    depth = _component(None, None, "usable_reserve_players")
    lineup_proxy = _component(None, None, "dynasty_value")
    result = {"normalized_gain": None, "confidence": 0.0, "basis": "unavailable",
              "ready_for_enforcement": False,
              "outlook": outlook,
              "components": {"current_production": production,
                             "future_assets": future, "depth": depth,
                             "lineup_dynasty_proxy": lineup_proxy},
              "uncertainties": uncertainties, "reason": "Complete roster inputs required."}
    before_ids, after_ids = set(before.roster), set(after.roster)
    roster_ids = before_ids | after_ids
    if before.id != after.id:
        uncertainties.append("manager_mismatch")
    if any(pid not in assets for pid in roster_ids):
        uncertainties.append("unresolved_roster_asset")
    if any(pid in assets and (assets[pid].id != pid or not _finite(assets[pid].value))
           for pid in roster_ids):
        uncertainties.append("invalid_dynasty_asset")
    if any(code in uncertainties for code in
           ("manager_mismatch", "unresolved_roster_asset", "invalid_dynasty_asset")):
        return result

    evidence_factor = 1.0
    if len(before_ids) != len(before.roster) or len(after_ids) != len(after.roster):
        uncertainties.append("duplicate_roster_asset_deduplicated")
        evidence_factor *= .5
    if not before.availability_known or not after.availability_known:
        uncertainties.append("availability_unknown")
        evidence_factor *= .5
    if rules.source != "observed":
        uncertainties.append("lineup_settings_" + rules.source)
        evidence_factor *= .5
    uncertainties.extend(rules.uncertainties)
    if rules.uncertainties:
        evidence_factor *= .5

    # Players (including inactive ones) and picks form a disjoint partition.
    # Subtotals explain the total; neither is added again as another reward.
    totals = []
    for ids in (before_ids, after_ids):
        totals.append({"players": sum(assets[p].value for p in sorted(ids) if not assets[p].is_pick),
                       "picks": sum(assets[p].value for p in sorted(ids) if assets[p].is_pick)})
    before_total, after_total = (sum(t.values()) for t in totals)
    if not _finite(before_total) or not _finite(after_total):
        uncertainties.append("invalid_dynasty_total")
        return result
    future.update(_component(float(before_total), float(after_total), "dynasty_value", future_weight))
    future.update({"players": {"before": totals[0]["players"], "after": totals[1]["players"]},
                   "picks": {"before": totals[0]["picks"], "after": totals[1]["picks"]},
                   "basis": "supplied_dynasty_values", "confidence": .5})
    uncertainties.append("dynasty_value_is_not_future_points")

    valid_slots = bool(rules.slots) and all(s in ELIGIBILITY for s in rules.slots)
    if not valid_slots:
        uncertainties.append("unsupported_or_missing_lineup")
    pools = []
    if valid_slots:
        eligible = frozenset().union(*(ELIGIBILITY[s] for s in rules.slots))
        for team, ids in ((before, before_ids), (after, after_ids)):
            pools.append([assets[p] for p in sorted(ids) if not assets[p].is_pick
                          and assets[p].available and p not in team.inactive
                          and assets[p].positions & eligible])

    projection_errors = []
    if projections is None:
        projection_errors.append("projections_unavailable")
    else:
        if not projections_fresh:
            projection_errors.append("projections_stale_or_unknown")
        if not isinstance(projection_basis, str) or not projection_basis.strip():
            projection_errors.append("projection_basis_missing")
        if projection_unit not in _POINT_UNITS:
            projection_errors.append("projection_units_unsupported_or_missing")
        required = {a.id for pool in pools for a in pool}
        missing = sorted(p for p in required if p not in projections)
        invalid = sorted(p for p in required if p in projections and not _finite(projections[p]))
        if missing:
            production["missing_player_ids"] = missing
            projection_errors.append("projections_incomplete")
        if invalid:
            production["invalid_player_ids"] = invalid
            projection_errors.append("projections_invalid")
    uncertainties.extend(projection_errors)
    production["basis"] = projection_basis
    use_points = valid_slots and not projection_errors
    if use_points:
        lineups, scores = [], []
        for pool in pools:
            # Re-optimize the WHOLE lineup in real points, not dynasty value.
            lineup = assign(rules.slots, [replace(a, value=float(projections[a.id])) for a in pool])
            lineups.append(lineup)
            scores.append(sum(float(projections[p]) for p in lineup if p is not None))
        if all(_finite(score) for score in scores):
            production.update(_component(*scores, projection_unit, now_weight))
            production.update({"lineups": {"before": lineups[0], "after": lineups[1]},
                               "confidence": .85})
        else:
            uncertainties.append("invalid_projection_total")
            use_points = False

    if valid_slots:
        if not use_points:
            proxy_lineups = [assign(rules.slots, pool) for pool in pools]
            proxy_totals = [sum(assets[p].value for p in lineup if p is not None)
                            for lineup in proxy_lineups]
            lineup_proxy.update(_component(*proxy_totals, "dynasty_value"))
            lineup_proxy.update({"basis": "starting_lineup_dynasty_proxy", "confidence": .35,
                                 "lineups": {"before": proxy_lineups[0], "after": proxy_lineups[1]},
                                 "reason": "Shadow diagnostic only; not projected points. "
                                           "Starter dynasty value is already in future_assets."})
        reserve_ids = []
        for pool in pools:
            usable = [a for a in pool if a.startable]
            lineup = set(assign(rules.slots, usable))
            reserve_ids.append(sorted(a.id for a in usable if a.id not in lineup))
        depth.update(_component(*(len(ids) for ids in reserve_ids), "usable_reserve_players"))
        depth.update({"reserve_ids": {"before": reserve_ids[0], "after": reserve_ids[1]},
                      "basis": "unique_usable_reserves_after_dynasty_lineup",
                      "reason": "Diagnostic only; reserve value is already in future_assets. "
                                "Positional protection remains the roster evaluator's job."})

    # Missing production leaves only its KNOWN weighted counterpart, without
    # renormalizing future value into a fully evidenced current-season gain.
    terms = [(future_weight, future["normalized_gain"], .5)]
    if use_points:
        terms.append((now_weight, production["normalized_gain"], .85))
    if any(weight > 0 for weight, _, _ in terms):
        result["normalized_gain"] = float(sum(weight * gain for weight, gain, _ in terms))
        result["confidence"] = float(outlook["confidence"] * evidence_factor
                                     * sum(weight * confidence for weight, _, confidence in terms))
        result["basis"] = "projected_production_and_dynasty" if use_points else "dynasty_only"
        result["reason"] = ("Whole-lineup production and whole-roster dynasty changes weighted by manager outlook."
                            if use_points else "Only the weighted dynasty contribution is known; "
                            "current-season benefit is unmeasured.")
        result["ready_for_enforcement"] = bool(use_points and evidence_factor == 1.0
                                                and outlook["source"] == "explicit")
    else:
        result["reason"] = "No measured component has weight under this manager's outlook."
    uncertainties[:] = sorted(set(uncertainties))
    return result
