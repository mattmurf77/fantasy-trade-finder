"""Independent, offline six-dimension offer evidence (scorecard-spec §§1, 3–7).

Draft schema v1; not a calibrated release gate or acceptance predictor. No model,
database, server or network imports. Unknown contextual judgments require frozen
independent annotations; price equality alone never establishes willingness.

Input contract: ``schema_version``, ``offer_id``, ``snapshot_id``, ``captured_at``, ``assets`` and
``managers`` (A/B). Each manager has stable ``manager_id`` and ``give`` asset IDs;
the other manager's give is its receive. Assets have kind, owner_id, market_value
and, for players, position; picks have pick_round/year/original_owner_id.

Evidence provenance has source, as_of, version, snapshot_id, and optional
freshness attestation. ISO dates mean midnight UTC; datetimes require timezone.
Raw evidence dates must be <= captured_at. Independent retrospective reviews
must be <= evidence_cutoff (default captured_at). A missing/invalid capture date
leaves dependent evidence Unknown. ``fresh=False`` invalidates evidence;
projection claims additionally require ``fresh=True``. Missing market freshness
is not an attestation, even when its as-captured diagnostics are usable.
Market evidence also has units,
universe_id, entries (tier/order; lower is better), and second_round_tier or
an explicitly comparable second_round_player_floor (never assume a universal
cross-position price floor).
Personal boards have matching universe_id, manager_id, provenance, and entries
with tier/order/explicit. Gaps are signed lexicographic tier/order differences,
never production effective values. Focal assets meet the individual significance
reference or tie for the side's largest market value; no sum creates a focal.

Independent reviews at evidence.reviews[dimension] bind ``terms_hash`` from
offer_terms_hash(), and provenance additionally has independent=True and kind
domain_review or synthetic_fixture. Their managers.<canonical_manager_id>.give/receive/package
cells contain grade and nonempty reasons. Reviews do not override missing input
or integrity contradictions. Synthetic reviews are accepted only on data_kind
synthetic. Stud references at evidence.stud_tax use identical binding, kind
reference_band (or synthetic_fixture), best_asset_id, minimum_return,
maximum_return, units, convention='return_total', first_round_exemption_reviewed.
Bounds describe total raw return, so no second crown uplift is added.

Picks require typed year/round/original_owner_id plus asset.pick_validation with
status valid/invalid and snapshot-bound provenance from an audited ownership and
expiry ledger. Missing validation stays Unknown, not illegal. A sourced
evidence.draft_calendar.last_completed_draft_year can establish an expired pick.

Roster evidence: manager.roster, lineup.{slots:[{id,eligible_positions}],
roster_limit,cuts,rules_complete,provenance}, and projections.{provenance,
units:'fantasy_points',horizon,entries:{id:{points,available}}}. Exact assignment
uses a small slot-mask DP and never substitutes dynasty values for points. Cuts
must be named; unknown rules or >16 slots are unsupported, not inferred legal.

All outputs retain raw metrics even when an ordinal grade is Unknown. Snapshot
IDs attest input binding, not audit the upstream capture: real adapters must
validate contemporaneous capture/freshness before populating this contract.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math


EVALUATOR_VERSION = "bilateral-dimensions-draft-1"
DIMENSIONS = ("fairness", "outlook", "team_needs", "personal_ranks", "meaningful", "stud_tax")
SIDES = ("give", "receive", "package")
OUTLOOKS = {
    "jets": "tanking", "tanking": "tanking", "rebuilder": "rebuilding",
    "rebuilding": "rebuilding", "contender": "contending", "contending": "contending",
    "championship": "all_in", "all_in": "all_in", "balanced": "balanced",
    "not_sure": "not_sure",
}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def offer_terms_hash(offer):
    """Orientation/order-invariant identity; binds annotation to exact terms."""
    terms = sorted((manager["manager_id"], sorted(manager["give"]))
                   for manager in offer["managers"].values())
    return hashlib.sha256(json.dumps(terms, separators=(",", ":")).encode()).hexdigest()


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _provenance(offer, provenance, *, retrospective=False):
    captured = _time(offer.get("captured_at"))
    cutoff = _time(offer.get("evidence_cutoff", offer.get("captured_at")))
    as_of = _time(provenance.get("as_of")) if isinstance(provenance, dict) else None
    boundary = cutoff if retrospective else captured
    return (captured is not None and cutoff is not None and captured <= cutoff
            and as_of is not None and as_of <= boundary and isinstance(provenance, dict)
            and all(provenance.get(key) for key in ("source", "as_of", "version", "snapshot_id"))
            and provenance["snapshot_id"] == offer.get("snapshot_id")
            and provenance.get("fresh") is not False)


def _independent(offer, record, kinds):
    provenance = record.get("provenance", {})
    return (_provenance(offer, provenance, retrospective=True) and provenance.get("independent") is True
            and provenance.get("kind") in kinds
            and (provenance["kind"] != "synthetic_fixture" or offer.get("data_kind") == "synthetic")
            and record.get("terms_hash") == offer_terms_hash(offer))


def _cell(raw, grade=None, reason="independent_context_review_required", evidence=None, status=None):
    return {"grade": grade, "status": status or ("known" if grade is not None else "unknown"),
            "reasons": [reason], "raw_features": deepcopy(raw), "evidence": deepcopy(evidence or [])}


def _review(offer, dimension, role, side, raw):
    review = offer.get("evidence", {}).get("reviews", {}).get(dimension, {})
    if not _independent(offer, review, {"domain_review", "synthetic_fixture"}):
        return _cell(raw)
    manager_id = offer["managers"][role]["manager_id"]
    annotation = review.get("managers", {}).get(manager_id, {}).get(side, {})
    grade, reasons = annotation.get("grade"), annotation.get("reasons")
    if not isinstance(reasons, list) or not reasons or any(not isinstance(r, str) or not r for r in reasons):
        return _cell(raw, reason="invalid_or_missing_independent_annotation")
    if annotation.get("status") == "not_applicable" and grade is None:
        result = _cell(raw, status="not_applicable", evidence=[review["provenance"]])
        result["reasons"] = list(reasons)
        return result
    if type(grade) is not int or grade not in range(5):
        return _cell(raw, reason="invalid_or_missing_independent_annotation")
    result = _cell(raw, grade, evidence=[review["provenance"]])
    result["reasons"] = list(reasons)
    return result


def _force(cell, reason, grade=None):
    cell.update(grade=grade, status="known" if grade is not None else "unknown", reasons=[reason])


def _intent(manager):
    selected = manager.get("selected_outlook")
    inferred = manager.get("inferred_outlook")
    return OUTLOOKS.get(selected or inferred), "selected" if selected else "inferred" if inferred else "unknown"


def _pick_validity(offer, asset):
    if (type(asset.get("pick_year")) is not int or type(asset.get("pick_round")) is not int
            or asset["pick_round"] < 1 or not isinstance(asset.get("original_owner_id"), str)
            or not asset["original_owner_id"].strip()):
        return {"status": "unknown", "reason": "incomplete_pick_identity"}
    calendar = offer.get("evidence", {}).get("draft_calendar") or {}
    if (_provenance(offer, calendar.get("provenance"))
            and type(calendar.get("last_completed_draft_year")) is int
            and asset["pick_year"] <= calendar["last_completed_draft_year"]):
        return {"status": "invalid", "reason": "pick_draft_already_completed"}
    validation = asset.get("pick_validation") or {}
    if _provenance(offer, validation.get("provenance")) and validation.get("status") in {"valid", "invalid"}:
        return {"status": validation["status"], "reason": validation.get("reason", "audited_owned_unexpired_pick_ledger"),
                "evidence": deepcopy(validation["provenance"])}
    return {"status": "unknown", "reason": "pick_ownership_and_expiry_not_validated"}


def _integrity(offer):
    errors = []
    if offer.get("schema_version") != 1:
        errors.append("unsupported_schema_version")
    if not offer.get("offer_id") or not offer.get("snapshot_id"):
        errors.append("missing_offer_or_snapshot_identity")
    managers, assets = offer.get("managers", {}), offer.get("assets", {})
    if set(managers) != {"A", "B"}:
        return errors + ["exactly_two_managers_required"]
    ids = [managers[role].get("manager_id") for role in ("A", "B")]
    if not all(isinstance(value, str) and value for value in ids) or ids[0] == ids[1]:
        errors.append("invalid_manager_identity")
    seen = set()
    for manager in managers.values():
        given = manager.get("give")
        if not isinstance(given, list) or not given or any(not isinstance(x, str) for x in given):
            errors.append("missing_or_invalid_give_assets")
            continue
        for asset_id in given:
            asset = assets.get(asset_id, {})
            if asset_id in seen:
                errors.append("duplicate_asset")
            seen.add(asset_id)
            if asset.get("owner_id") != manager.get("manager_id"):
                errors.append("wrong_or_unknown_asset_owner")
            if asset.get("kind") not in {"player", "pick"}:
                errors.append("unknown_asset_kind")
            if asset.get("kind") == "pick" and _pick_validity(offer, asset)["status"] == "invalid":
                errors.append("invalid_or_expired_pick")
    return sorted(set(errors))


def _market(offer):
    evidence = offer.get("evidence", {}).get("market", {})
    return evidence if (_provenance(offer, evidence.get("provenance"))
                        and evidence.get("units") and evidence.get("universe_id")) else {}


def _total(offer, ids):
    values = [offer["assets"][asset_id].get("market_value") for asset_id in ids]
    return sum(values) if _market(offer) and all(_number(v) and v >= 0 for v in values) else None


def _qualifies(offer, manager, asset_id):
    asset, market = offer["assets"][asset_id], _market(offer)
    if asset["kind"] == "pick":
        return asset.get("pick_round") == 1 if _pick_validity(offer, asset)["status"] == "valid" else None
    floor = market.get("second_round_player_floor")
    value = asset.get("market_value")
    market_ok = value >= floor if _number(value) and _number(floor) and floor > 0 else None
    market_tier = market.get("entries", {}).get(asset_id, {}).get("tier")
    tier_floor = market.get("second_round_tier")
    if _number(market_tier) and _number(tier_floor):
        market_ok = market_tier <= tier_floor
    board = manager.get("personal_board", {})
    entry = board.get("entries", {}).get(asset_id, {})
    personal_floor = board.get("second_round_tier")
    personal_ok = (entry["tier"] <= personal_floor if _personal_entry_known(offer, manager, asset_id)
                   and _number(personal_floor) else None)
    if market_ok is True or personal_ok is True:
        return True
    return False if market_ok is False and personal_ok is False else None


def _personal_entry_known(offer, manager, asset_id):
    board = manager.get("personal_board", {})
    entry = board.get("entries", {}).get(asset_id, {})
    return (_provenance(offer, board.get("provenance"))
            and board.get("manager_id") == manager["manager_id"]
            and bool(board.get("universe_id")) and entry.get("explicit") is True
            and _number(entry.get("tier")))


def _board_known(offer, manager, asset_id):
    board, market = manager.get("personal_board", {}), _market(offer)
    personal, reference = board.get("entries", {}).get(asset_id, {}), market.get("entries", {}).get(asset_id, {})
    return (_personal_entry_known(offer, manager, asset_id)
            and board.get("universe_id") == market.get("universe_id")
            and all(_number(record.get(key)) for record in (personal, reference) for key in ("tier", "order")))


def _assets_raw(offer, manager, ids):
    assets, total = offer["assets"], _total(offer, ids)
    qualified = {asset_id: _qualifies(offer, manager, asset_id) for asset_id in ids}
    maximum = max((assets[x].get("market_value", 0) for x in ids), default=0) if total is not None else None
    focal = sorted(x for x in ids if qualified[x] is True or (
        maximum is not None and assets[x].get("market_value") == maximum))
    picks = sorted(x for x in ids if assets[x]["kind"] == "pick")
    rbs = sorted(x for x in ids if assets[x].get("position") == "RB")
    # Youth is only a supplied, evidenced classification. Missing age is never youth.
    young = sorted(x for x in ids if assets[x].get("position") in {"WR", "TE", "QB"}
                   and assets[x].get("young_for_position") is True
                   and _provenance(offer, assets[x].get("age_classification_provenance")))
    positions_known = all(assets[x].get("position") for x in ids if assets[x]["kind"] == "player")
    youth_known = positions_known and all(type(assets[x].get("young_for_position")) is bool
                      and _provenance(offer, assets[x].get("age_classification_provenance"))
                      for x in ids if assets[x].get("position") in {"WR", "TE", "QB"})
    personal_tiers = [manager["personal_board"]["entries"][x]["tier"] for x in ids if _personal_entry_known(offer, manager, x)]
    next_year = manager.get("next_draft_year")
    dated_picks = all(type(assets[x].get("pick_year")) is int for x in picks) and type(next_year) is int
    next_picks = [x for x in picks if assets[x].get("pick_year") == next_year] if dated_picks else []
    def share(group):
        value = _total(offer, group)
        return value / total if value is not None and total and total > 0 else None
    return {"assets": sorted(ids), "market_total": total, "asset_count": len(ids),
            "player_count": len(ids) - len(picks), "pick_count": len(picks),
            "pick_value_share": share(picks), "known_rb_count": len(rbs), "position_coverage_complete": positions_known,
            "rb_count": len(rbs) if positions_known else None, "rb_value_share": share(rbs) if positions_known else None,
            "next_draft_pick_count": len(next_picks) if dated_picks else None,
            "next_draft_pick_value_share": share(next_picks) if dated_picks else None,
            "later_pick_count": sum(assets[x]["pick_year"] > next_year for x in picks) if dated_picks else None,
            "young_wr_te_qb": young, "young_classification_complete": youth_known,
            "young_wr_te_qb_value_share": share(young) if youth_known else None,
            "highest_individual_market_value": maximum, "individual_significance": qualified,
            "highest_known_personal_tier": min(personal_tiers) if personal_tiers else None,
            "focal_assets": focal, "filler_value_share": share([x for x in ids if qualified[x] is False]),
            "first_round_picks": [x for x in picks if assets[x].get("pick_round") == 1],
            "pick_validity": {x: _pick_validity(offer, assets[x]) for x in picks},
            "own_next_draft_picks": [x for x in picks if assets[x].get("original_owner_id") == manager["manager_id"]
                                    and manager.get("next_draft_year") is not None
                                    and assets[x].get("pick_year") == manager["next_draft_year"]]}


def _preferences(offer, manager, ids, focal, direction):
    market = _market(offer)
    board = manager.get("personal_board", {}).get("entries", {})
    known = [x for x in ids if _board_known(offer, manager, x)]
    gaps = {}
    for asset_id in known:
        p, m = board[asset_id], market["entries"][asset_id]
        tier_gap, order_gap = m["tier"] - p["tier"], m["order"] - p["order"]
        signed = tier_gap if tier_gap else order_gap
        gaps[asset_id] = {"tier_gap": tier_gap, "within_tier_order_gap": order_gap,
                          "sign": (signed > 0) - (signed < 0)}
    target_sign = -1 if direction == "give" else 1
    hits = [x for x in known if gaps[x]["sign"] == target_sign]
    wrong = [x for x in known if gaps[x]["sign"] == -target_sign]
    total, known_total = _total(offer, ids), _total(offer, known)
    focal_known = [x for x in focal if x in known]
    focal_hits = [x for x in focal_known if x in hits]
    focal_total, focal_known_total = _total(offer, focal), _total(offer, focal_known)
    return {"gap_coordinate": "lexicographic_tier_then_within_tier_order_v1_lower_is_better",
            "signed_gaps": gaps, "known_count": len(known), "known_count_share": len(known) / len(ids) if ids else None,
            "known_value_mass_share": known_total / total if total and known_total is not None else None,
            "focal_known_count": len(focal_known), "focal_count": len(focal),
            "focal_known_value_mass_share": focal_known_total / focal_total if focal_total and focal_known_total is not None else None,
            "target_or_sell_hits": sorted(hits), "wrong_direction_assets": sorted(wrong),
            "preferred_asset_count": sum(gaps[x]["sign"] > 0 for x in known),
            "disfavored_asset_count": sum(gaps[x]["sign"] < 0 for x in known),
            "preferred_value_mass": _total(offer, [x for x in known if gaps[x]["sign"] > 0]),
            "disfavored_value_mass": _total(offer, [x for x in known if gaps[x]["sign"] < 0]),
            "focal_hit_count": len(focal_hits), "focal_hit_rate": len(focal_hits) / len(focal_known) if focal_known else None,
            "focal_hit_value_mass": _total(offer, focal_hits), "wrong_direction_value_mass": _total(offer, wrong),
            "favored_assets_sold": sorted(wrong) if direction == "give" else []}


def _slots_valid(slots):
    return (isinstance(slots, list) and bool(slots) and len(slots) <= 16
            and all(isinstance(s, dict) and isinstance(s.get("id"), str) and s["id"].strip()
                    and isinstance(s.get("eligible_positions"), (list, set)) and bool(s["eligible_positions"])
                    and all(isinstance(p, str) and p.strip() for p in s["eligible_positions"]) for s in slots)
            and len({s["id"] for s in slots}) == len(slots))


def best_lineup(roster, assets, entries, slots):
    """Max points, then filled slots; deterministic exact small-roster assignment.

    A slot-mask DP visits every eligible assignment with each player once. It
    supports FLEX/Superflex through supplied position sets, not hardcoded slots.
    The resource guard is explicit; larger/unknown formats remain unsupported.
    """
    if not _slots_valid(slots):
        raise ValueError("invalid_or_unsupported_lineup_slots")
    states = {0: (0.0, ())}
    for asset_id in sorted(roster):
        entry = entries[asset_id]
        if not entry["available"]:
            continue
        updated = dict(states)
        for mask, (points, assignments) in states.items():
            for i, slot in enumerate(slots):
                if mask & (1 << i) or assets[asset_id].get("position") not in slot["eligible_positions"]:
                    continue
                new_mask = mask | (1 << i)
                candidate = (points + entry["points"], assignments + ((slot["id"], asset_id),))
                previous = updated.get(new_mask)
                if previous is None or candidate[0] > previous[0] or (candidate[0] == previous[0] and candidate[1] < previous[1]):
                    updated[new_mask] = candidate
        states = updated
    mask, (points, pairs) = max(states.items(), key=lambda item: (item[1][0], item[0].bit_count(), item[1][1]))
    assignments = dict(sorted(pairs))
    return {"points": points, "assignments": assignments,
            "empty_slots": sorted(slot["id"] for slot in slots if slot["id"] not in assignments)}


def _lineup_evidence(offer, manager, incoming):
    rules, projection = manager.get("lineup", {}), manager.get("projections", {})
    roster, assets = manager.get("roster"), offer["assets"]
    if not isinstance(roster, list) or not _provenance(offer, rules.get("provenance")) or rules.get("rules_complete") is not True:
        return {"status": "unknown", "reason": "missing_complete_roster_rules"}
    if len(roster) != len(set(roster)) or any(x not in assets or assets[x].get("owner_id") != manager["manager_id"] for x in roster):
        return {"status": "unknown", "reason": "invalid_roster_identity"}
    if (not _provenance(offer, projection.get("provenance"))
            or projection["provenance"].get("fresh") is not True
            or projection.get("units") != "fantasy_points" or not projection.get("horizon")):
        return {"status": "unknown", "reason": "missing_or_non_point_projections"}
    slots, limit, cuts = rules.get("slots"), rules.get("roster_limit"), rules.get("cuts")
    if (not _slots_valid(slots)
            or type(limit) is not int or limit < len(roster) or not isinstance(cuts, list)):
        return {"status": "unknown", "reason": "incomplete_or_unsupported_lineup_rules"}
    given_players = {x for x in manager["give"] if assets[x]["kind"] == "player"}
    received_players = {x for x in incoming if assets[x]["kind"] == "player"}
    if not given_players <= set(roster):
        return {"status": "unknown", "reason": "outgoing_player_absent_from_roster"}
    after = (set(roster) - given_players) | received_players
    if len(cuts) != len(set(cuts)) or not set(cuts) <= after:
        return {"status": "unknown", "reason": "invalid_named_cuts"}
    after -= set(cuts)
    if len(after) > limit:
        return {"status": "unknown", "reason": "required_cuts_not_identified"}
    entries = projection.get("entries", {})
    relevant = set(roster) | received_players
    if any(assets[x].get("kind") != "player" or not isinstance(assets[x].get("position"), str)
           or not assets[x]["position"] for x in relevant):
        return {"status": "unknown", "reason": "incomplete_player_position_evidence"}
    if any(type(entries.get(x, {}).get("available")) is not bool or not _number(entries.get(x, {}).get("points")) for x in relevant):
        return {"status": "unknown", "reason": "incomplete_projection_coverage"}
    before = best_lineup(roster, assets, entries, slots)
    result = best_lineup(after, assets, entries, slots)
    without = best_lineup(set(roster) - given_players - set(cuts), assets, entries, slots)
    # Slot point declines remain visible even when another position improves more.
    slot_deltas = {s["id"]: (entries[result["assignments"][s["id"]]]["points"] if s["id"] in result["assignments"] else 0)
                   - (entries[before["assignments"][s["id"]]]["points"] if s["id"] in before["assignments"] else 0) for s in slots}
    return {"status": "known", "units": "fantasy_points", "horizon": projection["horizon"],
            "before": before, "after": result, "net_starter_delta": result["points"] - before["points"],
            "give_starter_cost": before["points"] - without["points"],
            "receive_marginal_points": result["points"] - without["points"], "slot_deltas": slot_deltas,
            "new_empty_slots": sorted(set(result["empty_slots"]) - set(before["empty_slots"])),
            "cuts": sorted(cuts), "outgoing_starters": sorted(given_players & set(before["assignments"].values())),
            "incoming_starters": sorted(received_players & set(result["assignments"].values())),
            "roster_count_before": len(roster), "roster_count_after": len(after),
            "evidence": [projection["provenance"], rules["provenance"]]}


def _stud_tax(offer, output):
    record = offer.get("evidence", {}).get("stud_tax", {})
    assets = offer["assets"]
    all_ids = [x for m in offer["managers"].values() for x in m["give"]]
    totals = {role: _total(offer, manager["give"]) for role, manager in offer["managers"].items()}
    best = max((assets[x].get("market_value", 0) for x in all_ids), default=0) if all(v is not None for v in totals.values()) else None
    headliners = sorted(x for x in all_ids if best is not None and assets[x].get("market_value") == best)
    personal_headliners = {}
    for role, manager in offer["managers"].items():
        if all(_board_known(offer, manager, x) for x in all_ids):
            entries = manager["personal_board"]["entries"]
            coordinate = min((entries[x]["tier"], entries[x]["order"]) for x in all_ids)
            personal_headliners[role] = sorted(x for x in all_ids if (entries[x]["tier"], entries[x]["order"]) == coordinate)
        else:
            personal_headliners[role] = None
    ordered_values = sorted((assets[x]["market_value"] for x in all_ids), reverse=True) if best is not None else []
    canonical_totals = {offer["managers"][role]["manager_id"]: total for role, total in totals.items()}
    canonical_personal = {offer["managers"][role]["manager_id"]: heads for role, heads in personal_headliners.items()}
    for role, cells in output["managers"].items():
        for cell in cells.values():
            cell["raw_features"].update(market_headliners=headliners, raw_totals=canonical_totals,
                                       personal_headliners=canonical_personal,
                                       second_best_gap=ordered_values[0] - ordered_values[1] if len(ordered_values) > 1 else None,
                                       adjustment_applied=0, adjustment_convention="independent_return_total_band")
    valid = (_independent(offer, record, {"reference_band", "synthetic_fixture"})
             and record.get("units") == _market(offer).get("units")
             and record.get("convention") == "return_total"
             and len(headliners) == 1 and record.get("best_asset_id") == headliners[0]
             and _number(record.get("minimum_return")) and _number(record.get("maximum_return"))
             and 0 <= record["minimum_return"] <= record["maximum_return"])
    has_first = any(assets[x]["kind"] == "pick" and assets[x].get("pick_round") == 1 for x in all_ids)
    if not valid or (has_first and record.get("first_round_exemption_reviewed") is not True):
        return
    seller = next(role for role, m in offer["managers"].items() if headliners[0] in m["give"])
    buyer = "B" if seller == "A" else "A"
    returned = totals[buyer]
    for role, cells in output["managers"].items():
        grade, reason = 2, "within_independent_compensation_band"
        if role == seller and returned < record["minimum_return"]:
            grade, reason = 0, "best_asset_seller_undercompensated"
        elif role == buyer and returned > record["maximum_return"]:
            grade, reason = 0, "best_asset_buyer_excessive_premium"
        elif returned < record["minimum_return"] or returned > record["maximum_return"]:
            reason = "own_terms_not_harmed_but_counterparty_fails"
        for cell in cells.values():
            cell.update(grade=grade, status="known", reasons=[reason], evidence=[deepcopy(record["provenance"])])
            cell["raw_features"].update(reference_minimum=record["minimum_return"], reference_maximum=record["maximum_return"],
                                       actual_return=returned, below_minimum=returned - record["minimum_return"],
                                       above_maximum=returned - record["maximum_return"])


def _bilateral(dimension):
    cells = [cell for manager in dimension["managers"].values() for cell in manager.values()]
    packages = [manager["package"] for manager in dimension["managers"].values()]
    known = [cell["grade"] for cell in packages if cell["status"] == "known"]
    dimension["applicability"] = {role: {side: cell["status"] != "not_applicable" for side, cell in manager.items()}
                                  for role, manager in dimension["managers"].items()}
    dimension["weaker_grade"] = min(known) if len(known) == 2 else None
    if any(cell["grade"] == 0 for cell in cells) or any(cell["grade"] == 1 for cell in packages):
        status = "fail"
    elif any(cell["status"] == "unknown" for cell in cells):
        status = "evidence-limited"
    elif any(cell["status"] == "not_applicable" for cell in packages):
        status = "not_applicable"
    else:
        status = "pass"
    dimension["bilateral_status"] = status


def evaluate_offer(offer):
    """Return independent features + provisional ordinal cells without mutation."""
    errors = _integrity(offer)
    result = {"schema_version": 1, "evaluator_version": EVALUATOR_VERSION,
              "rubric_status": "draft_unratified", "offer_id": offer.get("offer_id"),
              "integrity_status": "invalid" if errors else "valid", "integrity_errors": errors,
              "behavioral_acceptance": {"status": "unknown", "reason": "dimension_proxy_is_not_behavioral_outcome"},
              "dimensions": {d: {"managers": {r: {s: _cell({}, reason="invalid_offer_identity") for s in SIDES}
                                               for r in ("A", "B")}} for d in DIMENSIONS},
              "limitations": ["Draft rubric; no promotion thresholds or calibrated acceptance probabilities.",
                              "Independent annotations/reference bands required for contextual judgments.",
                              "No production snapshot capture or constructor behavior evaluated by this function."]}
    if errors:
        for dimension in result["dimensions"].values():
            _bilateral(dimension)
        return result
    market_provenance = offer.get("evidence", {}).get("market", {}).get("provenance", {})
    result["evidence_timing"] = {"captured_at": offer.get("captured_at"),
                                 "evidence_cutoff": offer.get("evidence_cutoff", offer.get("captured_at")),
                                 "market_freshness": "attested" if market_provenance.get("fresh") is True else "unknown"}
    if _time(offer.get("captured_at")) is None:
        result["limitations"].append("Frozen capture time is missing or invalid; dependent evidence is Unknown.")
    if market_provenance.get("timestamp_semantics") == "capture_not_market_publication":
        result["limitations"].append("Market as_of is capture time; source publication freshness is unestablished.")
    result["terms_hash"] = offer_terms_hash(offer)
    for role, manager in offer["managers"].items():
        incoming = offer["managers"]["B" if role == "A" else "A"]["give"]
        ids_by_side = {"give": manager["give"], "receive": incoming}
        raw = {s: _assets_raw(offer, manager, ids) for s, ids in ids_by_side.items()}
        raw["package"] = {"give": deepcopy(raw["give"]), "receive": deepcopy(raw["receive"]),
                          "shape": f'{len(manager["give"])}x{len(incoming)}',
                          "market_net": raw["receive"]["market_total"] - raw["give"]["market_total"]
                          if all(raw[s]["market_total"] is not None for s in ("give", "receive")) else None}
        intent, authority = _intent(manager)
        lineup = _lineup_evidence(offer, manager, incoming)
        preferences = {s: _preferences(offer, manager, ids, raw[s]["focal_assets"], s) for s, ids in ids_by_side.items()}
        for dimension in DIMENSIONS:
            for side in SIDES:
                features = deepcopy(raw[side])
                if dimension == "personal_ranks":
                    features.update(preferences[side] if side != "package" else {"preferences": preferences})
                if dimension == "outlook":
                    features.update(intent=intent, authority=authority, selected_outlook=manager.get("selected_outlook"),
                                    inferred_outlook=manager.get("inferred_outlook"), explicit_selection=manager.get("explicit_selection", {}))
                if dimension == "team_needs":
                    features["lineup"] = lineup
                    features["immediate_starter_improvement"] = {"status": "not_applicable" if intent in {"tanking", "rebuilding"} else lineup["status"]}
                cell = _review(offer, dimension, role, side, features)
                sources = [_market(offer).get("provenance")]
                if dimension == "personal_ranks":
                    sources.append(manager.get("personal_board", {}).get("provenance"))
                if dimension == "team_needs":
                    sources += lineup.get("evidence", [])
                cell["evidence"].extend(deepcopy([p for p in sources if p and _provenance(offer, p)]))
                result["dimensions"][dimension]["managers"][role][side] = cell
        dims = result["dimensions"]
        for side in SIDES:
            if side == "package":
                personal_complete = all(preferences[s]["known_count"] == len(ids_by_side[s]) for s in ids_by_side)
            else:
                personal_complete = preferences[side]["known_count"] == len(ids_by_side[side])
            if not personal_complete:
                _force(dims["personal_ranks"]["managers"][role][side], "missing_explicit_personal_board_coverage")
            if intent is None:
                _force(dims["outlook"]["managers"][role][side], "missing_or_unknown_outlook")
            if lineup["status"] != "known":
                _force(dims["team_needs"]["managers"][role][side], lineup["reason"])
            if raw["package"]["market_net"] is None:
                _force(dims["fairness"]["managers"][role][side], "missing_market_snapshot")
        if intent in {"contending", "all_in"} and lineup.get("new_empty_slots"):
            for side in ("give", "package"):
                _force(dims["team_needs"]["managers"][role][side], "new_unfilled_starter_slot", 0)
        # Selection is recorded authority, not permission to manufacture a grade.
        if intent == "tanking" and raw["give"]["own_next_draft_picks"]:
            selected = set(manager.get("explicit_selection", {}).get("give", []))
            if not set(raw["give"]["own_next_draft_picks"]) <= selected:
                for side in ("give", "package"):
                    _force(dims["outlook"]["managers"][role][side], "tanking_own_next_draft_pick_unselected", 0)
        if intent == "tanking" and raw["receive"]["rb_count"]:
            # A label/boolean exception is insufficient; full contextual independent review is required.
            for side in ("receive", "package"):
                cell = dims["outlook"]["managers"][role][side]
                if cell["status"] != "known":
                    _force(cell, "tanking_rb_requires_independent_exception_rationale")
        all_significance = list(raw["give"]["individual_significance"].values()) + list(raw["receive"]["individual_significance"].values())
        ordinary = offer.get("context", "ordinary_discovery") == "ordinary_discovery"
        if ordinary and all_significance and all(v is False for v in all_significance):
            for side in SIDES:
                _force(dims["meaningful"]["managers"][role][side], "no_individual_meaningful_asset", 0)
        elif any(v is None for v in all_significance) and not any(v is True for v in all_significance):
            for side in SIDES:
                _force(dims["meaningful"]["managers"][role][side], "missing_individual_significance_reference")
    # Stud grades can only come from an independent band, never supplied ordinal labels.
    for cells in result["dimensions"]["stud_tax"]["managers"].values():
        for cell in cells.values():
            _force(cell, "independent_compensation_band_required")
    _stud_tax(offer, result["dimensions"]["stud_tax"])
    # Unverified picks retain inspectable values but cannot produce verified
    # acceptability. This is an evidence limitation, not a live legality veto.
    for role, manager in offer["managers"].items():
        incoming = offer["managers"]["B" if role == "A" else "A"]["give"]
        for side, ids in (("give", manager["give"]), ("receive", incoming), ("package", manager["give"] + incoming)):
            unknown_picks = [x for x in ids if offer["assets"][x]["kind"] == "pick"
                             and _pick_validity(offer, offer["assets"][x])["status"] == "unknown"]
            if unknown_picks:
                for dimension in result["dimensions"].values():
                    assessment = dimension["managers"][role][side]
                    if assessment["grade"] not in (0, 1):
                        _force(assessment, "pick_identity_or_validity_unknown")
    for dimension in result["dimensions"].values():
        _bilateral(dimension)
    return result
