"""Bounded post-policy player-complexity presentation (small-trade-packages PRD).

Pure permutation and occurrence bookkeeping only: no generation, valuation,
database access or flag reads. The caller supplies actual execution metadata.
"""
from collections import defaultdict
import math

from .pick_values import parse_generic_pick_id


VERSION = "simple-player-v1"
WINDOW_SIZE = 6
OFF = (0, None)
_LOCKS = ("likes_you", "standing_offer_reason", "wildcard", "fatigue_retest", "retest")


def mode(value):
    """Only the Float setting's exact finite numeric one enables v1."""
    enabled = (isinstance(value, (int, float)) and not isinstance(value, bool)
               and value == 1 and math.isfinite(value))
    return (1, VERSION) if enabled else OFF


def player_count(ids, players, league_id, owned_pick_parser, player_positions, is_pick_asset):
    """Known players count once per asset occurrence; picks contribute zero.

    A conflicting pick identity/player position, unknown ID or malformed side
    is unknown, never an attractive guessed zero. Owned picks use the existing
    league-aware parser and require its schema's nonempty original-roster part.
    """
    if not isinstance(ids, (list, tuple)) or not ids:
        return None
    count = 0
    for pid in ids:
        if not isinstance(pid, str) or not pid:
            return None
        player = players.get(pid)
        pos = getattr(player, "position", None)
        pseudo_pick = is_pick_asset(player)
        generic = parse_generic_pick_id(pid)
        owned = owned_pick_parser(pid, league_id)
        if owned:
            tail = pid[len(league_id) + 1:].split("_", 2)
            owned = (all(isinstance(n, int) and n > 0 for n in owned)
                     and len(tail) == 3 and bool(tail[2]))
        if generic or owned:
            if pos is not None and not pseudo_pick:
                return None
        elif not isinstance(pos, str) or pos not in player_positions or pseudo_pick:
            return None
        else:
            count += 1
    return count


def slot_class(card, result, *, bakeoff_expected, bakeoff_run, grouped):
    """Original arm/group/policy slots, never reconstructed source credit."""
    if result is None or getattr(result, "eligible", None) is not True:
        return None
    policy_lane = getattr(result, "lane", None)
    if not isinstance(policy_lane, str) or not policy_lane:
        return None
    lane, basis = getattr(card, "lane", None), getattr(card, "basis", None)
    if any(value is not None and not isinstance(value, str) for value in (lane, basis)):
        return None
    if bakeoff_expected:
        if bakeoff_run is None:
            return None
        try:
            attr = bakeoff_run.attribution_for(card)
            group = bakeoff_run.group_for(card)
        except (AttributeError, KeyError, TypeError, ValueError):
            return None
        if (not isinstance(attr, tuple) or len(attr) != 2
                or not isinstance(attr[0], str) or not attr[0]
                or type(attr[1]) is not int or attr[1] < 0):
            return None
        if group is None:
            if grouped:
                return None
            group_key = lane_slot = None
        elif (isinstance(group, tuple) and len(group) == 3
              and isinstance(group[0], str) and group[0]
              and type(group[1]) is int and group[1] >= 0
              and (group[2] is None or isinstance(group[2], str) and bool(group[2]))):
            group_key, _rank, lane_slot = group
        else:
            return None
        source = attr[0]
    else:
        source, group_key, lane_slot = None, None, None
    return (source, group_key, lane_slot, lane, basis, policy_lane)


def present(cards, *, players, league_id, owned_pick_parser, player_positions, is_pick_asset,
            policy_results, bakeoff_expected, bakeoff_run, grouped):
    """One stable six-absolute-slot pass, returning the same occurrences.

    Metadata follows each occurrence, including repeated object references.
    `final_index` is deliberately added only by the actual impression writer.
    """
    records, classes = [], []
    for index, card in enumerate(cards):
        give = player_count(getattr(card, "give_player_ids", None),
                            players, league_id, owned_pick_parser, player_positions, is_pick_asset)
        receive = player_count(getattr(card, "receive_player_ids", None),
                               players, league_id, owned_pick_parser, player_positions, is_pick_asset)
        records.append({"version": VERSION, "window_size": WINDOW_SIZE,
                        "original_index": index, "give_player_count": give,
                        "receive_player_count": receive})
        locked = (give is None or receive is None or give + receive == 0
                  or any(getattr(card, marker, False) for marker in _LOCKS))
        cls = None if locked else slot_class(
            card, policy_results.get(id(card)), bakeoff_expected=bakeoff_expected,
            bakeoff_run=bakeoff_run, grouped=grouped)
        classes.append(cls)
    order = list(range(len(cards)))
    for start in range(0, len(cards), WINDOW_SIZE):
        slots = defaultdict(list)
        for index in range(start, min(start + WINDOW_SIZE, len(cards))):
            if classes[index] is not None:
                slots[classes[index]].append(index)
        for indices in slots.values():
            ranked = sorted(indices, key=lambda i: (
                max(records[i]["give_player_count"], records[i]["receive_player_count"]),
                records[i]["give_player_count"] + records[i]["receive_player_count"]))
            for destination, original in zip(indices, ranked):
                order[destination] = original
    return [cards[i] for i in order], [records[i] for i in order]


def retain_occurrences(cards, records, survivors):
    """Carry records through an order-preserving authoritative removal.

    Identity plus occurrence order preserves duplicates. Never zip a shortened
    survivor list against stale records or recompute original positions.
    """
    entries = iter(zip(cards, records))
    return [next(record for original, record in entries if original is card)
            for card in survivors]
