"""Bounded Win Now search over frozen, cardinal-valued league snapshots.

The calculator and search share ``evaluate_candidate``. No network, database,
Elo learning, or baseline mutation occurs here. Shared package pricing/filler
policy is read through trade_service; callers must freeze its config revision
in their scenario snapshot. ``evaluate_trade(buyer, partner, give, receive)``
returns both teams' before/after/delta and paired metric uncertainty. Finalists
also require an independently seeded ``confirmation_delta`` per metric.

Required context: buyer_roster_id, assets (canonical ID -> asset incl owner,
market_value and is_pick), buyer_values, partner_values, partner_evidence,
objective, max_dynasty_spend_pct, league {trades_allowed, roster_capacity,
lineup_slots}. lineup_slots contains eligible-position lists (e.g. ["RB",
"WR", "TE"] for FLEX). Capacity may be an int or map of roster ID -> int.
Projection screening uses marginal_lineup_gain(buyer, give, receive), or
asset.lineup_gain, already computed against the buyer's actual legal lineup.
Picks never receive direct lineup credit. Evidence values are cardinal dynasty
values on the market's scale; raw Elo is not an accepted currency.
Optional max_simulated and max_results are positive integer request limits,
bounded by POLICY's hard ceilings; they never modify the shared policy.
"""

from collections import Counter, deque
from collections.abc import Mapping
from itertools import combinations
import math

from . import trade_service as pricing


POLICY_VERSION = "win-now-v1"
POLICY = {
    "market_floor": 0.75,
    "market_fallback_floor": 0.90,
    "fallback_surplus_fraction": 0.02,
    "min_partner_surplus": 1.0,
    "max_side_assets": 3,
    "max_total_assets": 4,
    "pool_size": 18,
    "max_screened": 12000,
    "max_simulated": 48,
    "max_results": 20,
    "min_lineup_gain": 0.01,
    "min_delta": {"wins": 0.02, "playoffs": 0.002, "championship": 0.002},
    "equivalent_delta": {"wins": 0.01, "playoffs": 0.001, "championship": 0.001},
    "unknown_season_loss": {"wins": 0.01, "playoffs": 0.001, "championship": 0.001},
}
METRICS = {
    "wins": "next_three_week_expected_wins",
    "playoffs": "playoff_probability",
    "championship": "championship_probability",
}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("non_finite_or_non_numeric_value")
    return float(value)


def _unit(value):
    result = _number(value)
    if not 0 <= result <= 1:
        raise ValueError("invalid_fraction")
    return result


def _limit(context, key):
    value = _number(context.get(key, POLICY[key]))
    if value != int(value) or not 1 <= value <= POLICY[key]:
        raise ValueError(f"invalid_{key}")
    return int(value)


def _value(values, asset_id, assets, evidence=None):
    market = _number(assets[asset_id]["market_value"])
    personal = _number(values.get(asset_id, market))
    if min(market, personal) < 0:
        raise ValueError("negative_asset_value")
    if evidence is None:
        return personal
    if evidence.get("basis") != "personal" or asset_id not in values:
        return market
    per_asset = evidence.get("assets", {}).get(asset_id, {})
    # Explicit manual placement is evidence; unchanged consensus seeds are not.
    confidence = per_asset.get("confidence", evidence.get("confidence", 0))
    if per_asset.get("source") == "consensus_seed":
        confidence = 0
    weight = _unit(confidence) * _unit(evidence.get("coverage", 0))
    return weight * personal + (1 - weight) * market


def _context_errors(context):
    errors = []
    objective = context.get("objective")
    if objective not in METRICS:
        errors.append("unsupported_objective")
    if objective == "championship" and context.get("championship_supported") is not True:
        errors.append("championship_unavailable")
    league = context.get("league", {})
    if league.get("trades_allowed") is not True or league.get("deadline_passed"):
        errors.append("trade_deadline_or_unavailable")
    if league.get("stale") or league.get("live_week_unsupported"):
        errors.append("stale_or_unsupported_snapshot")
    if "roster_capacity" not in league or not league.get("lineup_slots"):
        errors.append("missing_roster_rules")
    try:
        budget = _number(context["max_dynasty_spend_pct"])
        if not 0 <= budget <= 100:
            errors.append("invalid_dynasty_budget")
        _unit(context.get("min_fairness", POLICY["market_floor"]))
        _limit(context, "max_simulated")
        _limit(context, "max_results")
        assets = context["assets"]
        if not any(a.get("owner_roster_id") == context["buyer_roster_id"] for a in assets.values()):
            errors.append("missing_buyer_roster")
        for pid in assets:
            _value(context["buyer_values"], pid, assets, context.get("buyer_evidence"))
        for values in context.get("partner_values", {}).values():
            for value in values.values():
                if _number(value) < 0:
                    errors.append("negative_asset_value")
    except (KeyError, TypeError, ValueError):
        errors.append("invalid_policy_input")
    return errors


def _fits_lineup(asset_ids, assets, slots):
    """Bipartite matching counts every flexible slot and every player once."""
    choices = []
    for slot in slots:
        eligible = {slot} if isinstance(slot, str) else set(slot)
        choices.append([pid for pid in asset_ids if not assets[pid]["is_pick"]
                        and not assets[pid].get("lineup_ineligible", False)
                        and eligible.intersection(assets[pid].get("eligible_positions")
                                                  or [assets[pid].get("position")])])
    assigned = {}

    def match(index, seen):
        for pid in choices[index]:
            if pid in seen:
                continue
            seen.add(pid)
            if pid not in assigned or match(assigned[pid], seen):
                assigned[pid] = index
                return True
        return False

    return all(match(i, set()) for i in sorted(range(len(choices)), key=lambda i: len(choices[i])))


def _legality(context, partner, give, receive):
    assets = context["assets"]
    buyer = context["buyer_roster_id"]
    if not give or not receive:
        return ["empty_side"]
    if len(give) != len(set(give)) or len(receive) != len(set(receive)) or set(give) & set(receive):
        return ["duplicate_asset"]
    if max(len(give), len(receive)) > POLICY["max_side_assets"] or len(give) + len(receive) > POLICY["max_total_assets"]:
        return ["package_too_large"]
    if buyer == partner or any(pid not in assets for pid in give + receive):
        return ["invalid_asset_or_partner"]
    if any(assets[pid].get("id") != pid or assets[pid].get("owner_roster_id") != owner
           for side, owner in ((give, buyer), (receive, partner)) for pid in side):
        return ["asset_ownership"]
    if any("is_pick" not in assets[pid] for pid in give + receive):
        return ["missing_asset_type"]
    if any(assets[pid].get("locked") or assets[pid].get("tradeable") is False
           for pid in give + receive):
        return ["locked_asset"]
    if set(give) & set(context.get("protected_ids", [])):
        return ["protected_asset"]
    partner_protected = context.get("partner_protected_ids", {}).get(partner, [])
    if set(receive) & set(partner_protected):
        return ["partner_protected_asset"]
    if not set(context.get("pinned_give", [])).issubset(give) or not set(context.get("pinned_receive", [])).issubset(receive):
        return ["pin_not_satisfied"]
    league = context["league"]
    for owner, outgoing, incoming in ((buyer, give, receive), (partner, receive, give)):
        roster = {pid for pid, asset in assets.items() if asset.get("owner_roster_id") == owner}
        after = (roster - set(outgoing)) | set(incoming)
        capacity = league["roster_capacity"]
        if isinstance(capacity, Mapping):
            capacity = capacity.get(owner)
        if capacity is None or _number(capacity) < 1 or int(capacity) != capacity:
            return ["missing_roster_capacity"]
        if sum(not assets[pid]["is_pick"] for pid in after) > capacity:
            return ["mandatory_drop_unhandled"]
        if not _fits_lineup(after, assets, league["lineup_slots"]):
            return ["illegal_post_trade_lineup"]
    return []


def _price(context, partner, give, receive):
    assets = context["assets"]
    evidence = dict(context.get("partner_evidence", {}).get(partner, {}))
    partner_values = context.get("partner_values", {}).get(partner, {})
    relevant = give + receive
    has_personal_evidence = any(
        pid in partner_values and evidence.get("assets", {}).get(pid, {}).get("source") != "consensus_seed"
        and _unit(evidence.get("assets", {}).get(pid, {}).get("confidence", evidence.get("confidence", 0))) > 0
        for pid in relevant)
    if (not partner_values or evidence.get("basis") != "personal"
            or _unit(evidence.get("coverage", 0)) == 0 or not has_personal_evidence):
        evidence.update(basis="market", confidence=0, coverage=0)
    evidence.setdefault("confidence", 0)
    evidence.setdefault("coverage", 0)
    _unit(evidence["confidence"])
    _unit(evidence["coverage"])
    buyer_value = lambda pid: _value(context["buyer_values"], pid, assets, context.get("buyer_evidence"))
    partner_value = lambda pid: _value(partner_values, pid, assets, evidence)
    market_value = lambda pid: _value({}, pid, assets)
    with pricing.stud_tax_override("market"):
        market = pricing.price_consensus_package(give, receive, value_of=market_value)
        buyer = pricing.price_consensus_package(give, receive, value_of=buyer_value)
        seller = pricing.price_consensus_package(give, receive, value_of=partner_value)
        filler = pricing.filler_ok(give, receive, buyer_value, partner_value)
        overpay = pricing.overpay_ok(give, receive, market_value)
    if market is None or buyer is None or seller is None:
        raise ValueError("nonpositive_package_value")
    baseline = sum(buyer_value(pid) for pid, asset in assets.items()
                   if asset.get("owner_roster_id") == context["buyer_roster_id"])
    raw_loss = sum(buyer_value(pid) for pid in give) - sum(buyer_value(pid) for pid in receive)
    # Charge the larger sacrifice: depth/crown credit must not refund real loss.
    cost = max(0.0, buyer[1] - buyer[2], raw_loss)
    for value in (*market, *buyer, *seller, baseline, raw_loss, cost):
        _number(value)
    fallback = evidence["basis"] == "market"
    floor = max(context.get("min_fairness", POLICY["market_floor"]), POLICY["market_floor"],
                POLICY["market_fallback_floor"] if fallback else 0)
    return {
        "market_ratio": market[0], "market_give_value": market[1], "market_receive_value": market[2],
        "buyer_give_value": buyer[1], "buyer_receive_value": buyer[2],
        "buyer_dynasty_delta": buyer[2] - buyer[1], "buyer_dynasty_cost": cost,
        "buyer_baseline_value": baseline,
        "dynasty_budget": baseline * context["max_dynasty_spend_pct"] / 100,
        "partner_dynasty_surplus": seller[1] - seller[2],
        "partner_give_value": seller[2], "partner_receive_value": seller[1],
        "market_floor": floor, "filler_ok": filler, "overpay_ok": overpay,
        "partner_evidence": {k: evidence.get(k) for k in ("basis", "confidence", "coverage", "intent", "declared")},
    }


def _screen(context, partner, give, receive, *, context_checked=False):
    row = {"policy_version": POLICY_VERSION, "objective": context.get("objective"),
           "buyer_roster_id": context.get("buyer_roster_id"), "partner_roster_id": partner,
           "give_ids": give, "receive_ids": receive, "eligible": False, "rejection_reasons": []}
    reasons = row["rejection_reasons"]
    if not context_checked:
        reasons.extend(_context_errors(context))
    if reasons:
        return row
    try:
        reasons.extend(_legality(context, partner, give, receive))
        if reasons:
            return row
        row.update(_price(context, partner, give, receive))
    except (KeyError, TypeError, ValueError) as error:
        reasons.append(str(error) if isinstance(error, ValueError) else "invalid_snapshot")
        return row
    if not row["filler_ok"]:
        reasons.append("junk_filler")
    if not row["overpay_ok"] or row["market_ratio"] < row["market_floor"]:
        reasons.append("market_fairness")
    if row["buyer_dynasty_cost"] > row["dynasty_budget"] + 1e-9:
        reasons.append("dynasty_budget_exceeded")
    min_surplus = POLICY["min_partner_surplus"]
    if row["partner_evidence"]["basis"] == "market":
        min_surplus = max(min_surplus, row["partner_give_value"] * POLICY["fallback_surplus_fraction"])
    if row["partner_dynasty_surplus"] < min_surplus:
        reasons.append("partner_dynasty_loss_or_negligible_gain")
    if all(context["assets"][pid]["is_pick"] for pid in receive):
        reasons.append("no_projected_lineup_contribution")
    return row


def _season_gate(context, row, result):
    reasons = row["rejection_reasons"]
    metric = METRICS[context["objective"]]
    buyer = result["buyer"]
    partner = result["partner"]
    # Validate the entire before/after/delta block, not just the sort metric.
    for team in (buyer, partner):
        for key, delta in team["delta"].items():
            d = _number(delta)
            before, after = _number(team["before"][key]), _number(team["after"][key])
            if not math.isclose(after - before, d, abs_tol=1e-7):
                raise ValueError("inconsistent_season_delta")
            if "probability" in key:
                _unit(before)
                _unit(after)
    delta = _number(buyer["delta"][metric])
    uncertainty = buyer.get("uncertainty", {}).get(metric, {})
    lower = _number(uncertainty["lower_bound"])
    confirmation = _number(uncertainty["confirmation_delta"])
    if _number(uncertainty["standard_error"]) < 0:
        raise ValueError("invalid_standard_error")
    if lower > delta + 1e-9:
        raise ValueError("invalid_uncertainty_bound")
    if result.get("paired") is not True or uncertainty.get("paired") is not True:
        reasons.append("unpaired_season_evaluation")
    conservative = min(lower, confirmation)
    if conservative < POLICY["min_delta"][context["objective"]]:
        reasons.append("season_gain_not_reliable")
    lineup_key = {"wins": "next_three_week_lineup_gain", "playoffs": "lineup_gain",
                  "championship": "playoff_lineup_gain"}[context["objective"]]
    if _number(buyer.get(lineup_key, buyer["lineup_gain"])) < POLICY["min_lineup_gain"]:
        reasons.append("no_meaningful_lineup_gain")
    evidence = row["partner_evidence"]
    intent = evidence.get("intent") if evidence.get("declared") is True else "not_sure"
    if intent in ("championship", "contender"):
        partner_metric = "championship_probability" if intent == "championship" else "expected_remaining_wins"
        if _number(partner["delta"][partner_metric]) <= 0:
            reasons.append("partner_competitive_misfit")
    elif intent != "rebuilder":
        # Jets, inferred intent and poor records confer no consent to rebuild.
        for objective, key in METRICS.items():
            if _number(partner["delta"][key]) < -POLICY["unknown_season_loss"][objective]:
                reasons.append("unknown_partner_season_loss")
                break
        if (_number(partner["delta"]["expected_remaining_wins"]) < -POLICY["unknown_season_loss"]["wins"]
                and "unknown_partner_season_loss" not in reasons):
            reasons.append("unknown_partner_season_loss")
    if context.get("protect_remaining_wins") and _number(buyer["delta"]["expected_remaining_wins"]) < 0:
        reasons.append("remaining_wins_protection")
    row.update(season=result, conservative_season_gain=conservative, season_delta=delta)


def evaluate_candidate(context, partner_roster_id, give_ids, receive_ids, evaluate_trade):
    """Evaluate a caller's exact package with the same hard gates as search.

    Always returns a diagnostic row; an ineligible calculator trade is never
    silently amended. Callback failures propagate, but invalid numeric/model
    output becomes a fail-closed rejection. The input snapshot is never edited.
    """
    row = _screen(context, partner_roster_id, list(give_ids), list(receive_ids))
    if row["rejection_reasons"]:
        return row
    result = evaluate_trade(context["buyer_roster_id"], partner_roster_id, list(row["give_ids"]), list(row["receive_ids"]))
    try:
        _season_gate(context, row, result)
    except (KeyError, TypeError, ValueError) as error:
        row["rejection_reasons"].append(str(error) if isinstance(error, ValueError) else "missing_season_evidence")
    row["eligible"] = not row["rejection_reasons"]
    return row


def _lineup_screen(context, give, receive):
    assets = context["assets"]
    # A callback models replacements/interactions; metadata is only a shortlist
    # approximation. The full paired evaluator remains the eligibility gate.
    incoming_players = [pid for pid in receive if not assets[pid]["is_pick"]]
    if not incoming_players:
        return 0.0
    callback = context.get("marginal_lineup_gain")
    if callback:
        return _number(callback(context["buyer_roster_id"], give, receive))
    return (sum(_number(assets[pid].get("lineup_gain", 0)) for pid in incoming_players)
            - sum(_number(assets[pid].get("lineup_loss", 0)) for pid in give if not assets[pid]["is_pick"]))


def _packages(pool, pins):
    for count in range(1, POLICY["max_side_assets"] + 1):
        for package in combinations(pool, count):
            if set(pins).issubset(package):
                yield list(package)


def _package_pairs(outgoing, incoming, give_pins, receive_pins):
    """Cover every singleton core, then rotate through larger package shapes.

    Within each shape, visit every incoming package before advancing the give
    package. A high-projection but unaffordable star cannot consume all work
    before lower-ranked targets get any core offers.
    """
    give_groups = {count: [] for count in range(1, POLICY["max_side_assets"] + 1)}
    receive_groups = {count: [] for count in give_groups}
    for package in _packages(outgoing, give_pins):
        give_groups[len(package)].append(package)
    for package in _packages(incoming, receive_pins):
        receive_groups[len(package)].append(package)

    def pairs(give_count, receive_count):
        for give in give_groups[give_count]:
            for receive in receive_groups[receive_count]:
                yield give, receive

    yield from pairs(1, 1)
    lanes = deque(pairs(g, r) for g, r in ((2, 1), (1, 2), (3, 1), (2, 2), (1, 3))
                  if give_groups[g] and receive_groups[r])
    while lanes:
        lane = lanes.popleft()
        try:
            yield next(lane)
            lanes.append(lane)
        except StopIteration:
            pass


def _rank_frontier(rows, objective, max_results=None):
    tolerance = POLICY["equivalent_delta"][objective]
    frontier = [row for row in rows if not any(
        other is not row and other["conservative_season_gain"] >= row["conservative_season_gain"]
        and other["buyer_dynasty_cost"] <= row["buyer_dynasty_cost"]
        and (other["conservative_season_gain"] > row["conservative_season_gain"]
             or other["buyer_dynasty_cost"] < row["buyer_dynasty_cost"])
        for other in rows)]
    # Stable groups anchored to the best remaining gain avoid a nontransitive
    # approximate-equality comparator. Cheaper packages win inside a group.
    ranked = []
    remaining = sorted(frontier, key=lambda row: -row["conservative_season_gain"])
    while remaining:
        anchor = remaining[0]["conservative_season_gain"]
        group = [r for r in remaining if anchor - r["conservative_season_gain"] <= tolerance]
        remaining = remaining[len(group):]
        ranked.extend(sorted(group, key=lambda r: (r["buyer_dynasty_cost"], -r["partner_dynasty_surplus"],
                                                    -r["market_ratio"], tuple(r["give_ids"]), tuple(r["receive_ids"]))))
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
        row["on_frontier"] = True
    return ranked[:POLICY["max_results"] if max_results is None else max_results]


def generate_candidates(context, evaluate_trade, *, diagnostics=None):
    """Return validated frontier rows; optional diagnostics receives counts.

    Enumeration is deterministic and bounded, with no positive buyer-dynasty
    filter. Exact calculator packages use evaluate_candidate independently of
    these search bounds. Missing projection contribution yields no candidates.
    """
    rejected = Counter()
    errors = _context_errors(context)
    if errors:
        if diagnostics is not None:
            diagnostics.update(rejections=dict(Counter(errors)), screened=0, simulated=0)
        return []
    assets = context["assets"]
    buyer = context["buyer_roster_id"]
    max_simulated = _limit(context, "max_simulated")
    max_results = _limit(context, "max_results")
    give_pins, receive_pins = context.get("pinned_give", []), context.get("pinned_receive", [])
    protected = set(context.get("protected_ids", []))
    def movable(pid):
        return not assets[pid].get("locked") and assets[pid].get("tradeable") is not False
    own = [pid for pid, asset in assets.items() if asset.get("owner_roster_id") == buyer
           and pid not in protected and movable(pid)]
    partners = sorted({asset.get("owner_roster_id") for asset in assets.values()
                       if asset.get("owner_roster_id") is not None and asset.get("owner_roster_id") != buyer}, key=str)
    shortlist, screened = [], 0
    partner_limit = max(1, POLICY["max_screened"] // max(len(partners), 1))
    for partner in partners:
        if screened >= POLICY["max_screened"]:
            break
        partner_screened = 0
        partner_values = context.get("partner_values", {}).get(partner, {})
        outgoing = sorted(own, key=lambda pid: (pid not in give_pins,
                          -_number(partner_values.get(pid, assets[pid]["market_value"])), pid))[:POLICY["pool_size"]]
        partner_protected = set(context.get("partner_protected_ids", {}).get(partner, []))
        incoming = [pid for pid, asset in assets.items() if asset.get("owner_roster_id") == partner
                    and pid not in partner_protected and movable(pid)]
        incoming.sort(key=lambda pid: (pid not in receive_pins, -_lineup_screen(context, [], [pid]), pid))
        incoming = incoming[:POLICY["pool_size"]]
        for give, receive in _package_pairs(outgoing, incoming, give_pins, receive_pins):
            if partner_screened >= partner_limit or screened >= POLICY["max_screened"]:
                break
            screened += 1
            partner_screened += 1
            row = _screen(context, partner, give, receive, context_checked=True)
            if row["rejection_reasons"]:
                rejected.update(row["rejection_reasons"])
                continue
            gain = _lineup_screen(context, give, receive)
            if gain <= 0:
                rejected["no_projected_lineup_contribution"] += 1
                continue
            shortlist.append((gain, row))
    shortlist.sort(key=lambda pair: (-pair[0], pair[1]["buyer_dynasty_cost"],
                                    str(pair[1]["partner_roster_id"]), tuple(pair[1]["give_ids"]), tuple(pair[1]["receive_ids"])))
    accepted = []
    for _, screened_row in shortlist[:max_simulated]:
        row = evaluate_candidate(context, screened_row["partner_roster_id"], screened_row["give_ids"], screened_row["receive_ids"], evaluate_trade)
        if row["eligible"]:
            accepted.append(row)
        else:
            rejected.update(row["rejection_reasons"])
    if diagnostics is not None:
        diagnostics.update(rejections=dict(rejected), screened=min(screened, POLICY["max_screened"]),
                           simulated=min(len(shortlist), max_simulated))
    return _rank_frontier(accepted, context["objective"], max_results)
