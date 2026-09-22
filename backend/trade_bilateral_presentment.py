"""One post-significance permutation of revision-two bilateral survivors.

This private serving policy uses existing support evidence, not an acceptance
probability or an independent quality grade. It cannot change eligibility,
terms, proofs, card scores, occurrence count, or another source's slots.
"""
from collections import Counter, defaultdict
import math

from .trade_gen_owner import OwnerDecisionContext, _PERSONAL_SOURCES


VERSION = "bilateral-survivors-3"
GENERATOR_VERSION = "owner-v2-bilateral-2"
QUALITY_TOLERANCE = .025
LOOKAHEAD = 32
_ARM = "owner_v2_bilateral"
_EPS = 1e-9
_PROTECTED = ("likes_you", "source_like_impression_id", "standing_offer_reason",
              "injected", "wildcard", "fatigue_retest", "retest", "owner_published")


def _focal_directions(data, card):
    """Four raw personal-vs-market co-headliner profiles, not support scores.

    BUY favors personal > market; SELL favors personal < market. A recognized
    personal source and finite positive values are required. Each profile keeps
    Unknown count separate from sorted known categories for ALL exact max-market
    ties, independent of tie-broken intent IDs or package asset order.
    """
    rows = data["assets"]
    if (not isinstance(rows, list) or any(not isinstance(row, dict)
            or not isinstance(row.get("id"), str) for row in rows)):
        raise ValueError("invalid_focal_assets")
    assets = {row["id"]: row for row in rows}
    if (len(assets) != len(rows)
            or set(assets) != set(card.give_player_ids + card.receive_player_ids)):
        raise ValueError("invalid_focal_assets")
    if any(not isinstance(row.get("market"), (float, int)) or isinstance(row["market"], bool)
           or not math.isfinite(row["market"]) or row["market"] <= 0 for row in rows):
        raise ValueError("unknown_market_headliner")
    directions = []
    for side, outgoing, incoming in (
            ("viewer", card.give_player_ids, card.receive_player_ids),
            ("counterparty", card.receive_player_ids, card.give_player_ids)):
        for field, ids, sign in (("buy_target", incoming, 1), ("sell_candidate", outgoing, -1)):
            maximum = max(assets[pid]["market"] for pid in ids)
            focal_ids = [pid for pid in ids if assets[pid]["market"] == maximum]
            if data[side]["intent"].get(field) not in focal_ids:
                raise ValueError("invalid_focal_identity")
            known, unknown = [], 0
            for focal in focal_ids:
                asset = assets[focal]
                personal, market = asset.get(side + "_personal"), asset["market"]
                source = asset.get(side + "_source")
                if (not isinstance(source, str) or source not in _PERSONAL_SOURCES
                        or not isinstance(personal, (float, int)) or isinstance(personal, bool)
                        or not math.isfinite(personal) or personal <= 0):
                    unknown += 1
                    continue
                difference = sign * (personal - market)
                known.append(1 if difference > _EPS else -1 if difference < -_EPS else 0)
            directions.append((unknown, tuple(sorted(known))))
    return tuple(directions)


def _within_focal_direction(candidate, baseline):
    # Equal tie counts and Unknown counts; each sorted known category cannot
    # worsen. A minimum alone could hide losing a favorable co-headliner when
    # another adverse one already exists. Check both fixed destinations.
    return all(actual_unknown == reference_unknown and len(actual) == len(reference)
               and all(value >= expected for value, expected in zip(actual, reference))
               for (actual_unknown, actual), (reference_unknown, reference) in zip(candidate, baseline))


def _evidence(card):
    """Unknown or incompatible metadata stays in its exact original slot."""
    if any(getattr(card, key, False) for key in _PROTECTED):
        return None
    if any(getattr(card, key, None) not in (None, _ARM)
           for key in ("source", "model_arm", "generator", "generator_arm")):
        return None
    proof = getattr(card, "owner_evaluation", None)
    if (not isinstance(proof, OwnerDecisionContext) or proof.eligible is not True
            or proof.reason != "eligible"):
        return None
    try:
        if not proof.matches(card):
            return None
        data = proof.as_dict()
        if (data["generator"] != _ARM or data["generator_version"] != GENERATOR_VERSION
                or data["eligible"] is not True or data["reason"] != "eligible"
                or data["construction"]["explicit_selection"] is not False
                or data["selection"]["exact_give"]
                or any(data["selection"][side]["requested"] for side in ("give", "receive"))):
            return None
        support = tuple(data[side]["support"]["score"] for side in ("viewer", "counterparty"))
        if any(not isinstance(score, (float, int)) or isinstance(score, bool)
               or not math.isfinite(score) or not 0 <= score <= 1 for score in support):
            return None
        intent = data["viewer"]["intent"]
        give, receive = intent["sell_candidate"], intent["buy_target"]
        direction, path = data["direction"], intent["path"]
        if (intent["qualified"] is not True or give not in card.give_player_ids
                or receive not in card.receive_player_ids
                or direction not in ("upgrade", "downgrade", "lateral")
                or not isinstance(path, str) or not path):
            return None
        slot_class = tuple(getattr(card, key, None) for key in ("basis", "lane"))
        if any(value is not None and not isinstance(value, str) for value in slot_class):
            return None
        shape = len(card.give_player_ids), len(card.receive_player_ids)
        purpose = direction, path, shape
        novelty = (("purpose", purpose), ("give", give), ("receive", receive),
                   ("partner", card.target_user_id),
                   ("concept", give, receive, card.target_user_id, purpose))
        from .trade_gen_bilateral_candidate import term_evidence_valid
        if not term_evidence_valid(data, user_id=proof.user_id, target_user_id=proof.target_user_id):
            return None
        term_ordering = data["term_efficiency"]["ordering_version"]
        return slot_class, support, novelty, term_ordering, _focal_directions(data, card)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return None


def _within_quality(candidate, reference):
    return all(actual + QUALITY_TOLERANCE + _EPS >= baseline
               for actual, baseline in zip(candidate, reference))


def _term_precedence(cards, evidence):
    """Use the constructor's immutable same-focal comparison, once per deck."""
    if not any(record[3] for record in evidence.values()):
        return {}
    from .trade_gen_bilateral_candidate import term_precedence
    indices = list(evidence)
    dependencies = term_precedence([cards[index] for index in indices])
    return {indices[later]: {indices[earlier] for earlier in before}
            for later, before in dependencies.items()}


def present(cards, *, selected_give=(), selected_receive=(), opponent_user_id=None):
    """Return exact card occurrences plus PRIVATE aggregate/order diagnostics.

    The native constructor order is the fixed baseline, including its efficient
    term precedence. Each source's first representative stays first. A novelty
    swap requires both managers' scores to differ by at most .025 between the
    two offers, and BOTH resulting positions retain each manager's score within
    .025 of that position's fixed quality baseline. The fixed baseline prevents
    chained swaps from accumulating quality losses. Neither occurrence may move
    32 or more class positions, preventing starvation.

    Each manager's raw personal BUY/SELL categories across ALL equally highest-
    market-value co-headliners must also be no worse at both fixed destinations.
    Equal tie counts and Unknown counts are required; sorted known categories
    cannot worsen. Missing personal evidence cannot conceal favorable direction.

    Surviving same-focal price dependencies must not be crossed by a swap.
    Work/memory are linear with bounded lookahead and bounded dependency edges,
    plus the constructor's family sorting. No database or provider access occurs.
    Call once after final removals and before durable publication, never on polls.
"""
    cards = list(cards)
    order = list(range(len(cards)))
    diagnostics = {"version": VERSION, "generator_version": GENERATOR_VERSION,
        "count": len(cards), "eligible_count": 0, "moved_count": 0,
        "quality_tolerance": QUALITY_TOLERANCE, "lookahead": LOOKAHEAD,
        "candidate_comparisons": 0, "term_precedence_edges": 0,
        "baseline": "candidate_native_order", "reason": "no_comparable_survivors",
        "occurrence_original_indices": order.copy()}
    if selected_give or selected_receive or opponent_user_id:
        diagnostics["reason"] = "explicit_search"
        return cards, diagnostics

    evidence, classes = {}, defaultdict(list)
    for index, item in enumerate(cards):
        record = _evidence(item)
        if record is not None:
            evidence[index] = record
            classes[record[0]].append(index)
    diagnostics["eligible_count"] = len(evidence)
    predecessors = _term_precedence(cards, evidence)
    successors = defaultdict(set)
    for later, earlier in predecessors.items():
        for index in earlier:
            successors[index].add(later)
    diagnostics["term_precedence_edges"] = sum(map(len, predecessors.values()))
    positions = list(range(len(cards)))
    for slots in classes.values():
        baseline = slots
        rank = {original: position for position, original in enumerate(baseline)}
        ranked = baseline.copy()
        used = Counter()
        for position in range(len(ranked)):
            leader = ranked[position]
            best = position
            best_novelty = sum(used[key] for key in evidence[leader][2])
            first_dependent = min((positions[index] for index in successors.get(leader, ())),
                                  default=len(cards))
            # Quality leads each source's first position; diversity influences
            # only subsequent representatives within the fixed tolerance.
            for candidate_position in range(position + 1, min(position + LOOKAHEAD, len(ranked))) if position else ():
                diagnostics["candidate_comparisons"] += 1
                candidate = ranked[candidate_position]
                if slots[candidate_position] >= first_dependent:
                    break  # Moving the leader past its dependent would invert terms.
                if any(positions[index] >= slots[position]
                       for index in predecessors.get(candidate, ())):
                    continue
                if (abs(rank[candidate] - position) >= LOOKAHEAD
                        or abs(rank[leader] - candidate_position) >= LOOKAHEAD
                        or not _within_quality(evidence[candidate][1], evidence[leader][1])
                        or not _within_quality(evidence[leader][1], evidence[candidate][1])
                        or not _within_quality(evidence[candidate][1], evidence[baseline[position]][1])
                        or not _within_quality(evidence[leader][1], evidence[baseline[candidate_position]][1])
                        or not _within_focal_direction(evidence[candidate][4], evidence[baseline[position]][4])
                        or not _within_focal_direction(evidence[leader][4], evidence[baseline[candidate_position]][4])):
                    continue
                novelty = sum(used[key] for key in evidence[candidate][2])
                if novelty < best_novelty:
                    best, best_novelty = candidate_position, novelty
            ranked[position], ranked[best] = ranked[best], leader
            positions[ranked[position]], positions[leader] = slots[position], slots[best]
            used.update(evidence[ranked[position]][2])
        for slot, original in zip(slots, ranked):
            order[slot] = original

    diagnostics["moved_count"] = sum(original != position for position, original in enumerate(order))
    diagnostics["occurrence_original_indices"] = order
    if len(evidence) > 1:
        diagnostics["reason"] = "ordered"
    return [cards[index] for index in order], diagnostics
