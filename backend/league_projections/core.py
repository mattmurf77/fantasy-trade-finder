"""Pure Decimal scoring and exact native-slot assignment. No provider or database I/O."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json

VERSION = "joint-season-scenario-v3"
SLOTS = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"},
    "FLEX": {"RB", "WR", "TE"}, "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "REC_FLEX": {"WR", "TE"}, "WRRB_FLEX": {"WR", "RB"},
    "DL": {"DL", "DE", "DT"}, "LB": {"LB", "ILB", "OLB"},
    "DB": {"DB", "CB", "SS", "FS", "S"},
    "IDP_FLEX": {"DL", "DE", "DT", "LB", "ILB", "OLB", "DB", "CB", "SS", "FS", "S"},
}
IDP = {"DL", "LB", "DB", "IDP_FLEX"}


class Unavailable(ValueError):
    def __init__(self, reason, *, state="unsupported_policy", details=None):
        super().__init__(reason)
        self.reason, self.state, self.details = reason, state, details or {}


def decimal(value):
    if isinstance(value, bool) or value is None:
        raise Unavailable("invalid_numeric_input", state="incomplete_projections")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise Unavailable("invalid_numeric_input", state="incomplete_projections") from None
    if not result.is_finite() or abs(result) > 10000000:
        raise Unavailable("invalid_numeric_input", state="incomplete_projections")
    return result


def split_points(integer, fractional):
    """Signed provider components: -2 and -35 => -2.35, not -1.65."""
    whole, fraction = decimal(integer), decimal(fractional)
    if whole != whole.to_integral_value() or fraction != fraction.to_integral_value() or abs(fraction) >= 100:
        raise Unavailable("invalid_split_points")
    # Positive fractional digits accompanying a negative whole are ambiguous.
    if whole < 0 < fraction:
        raise Unavailable("ambiguous_negative_split_points")
    return whole + fraction / 100


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def semantic_facts(value):
    """Remove ingestion clocks only; keep provider revisions, kickoff and facts."""
    if isinstance(value, dict):
        return {k: semantic_facts(v) for k, v in value.items()
                if k not in {"captured_at", "source_captured_at", "capture_completed_at", "fetched_at", "source_hash"}}
    if isinstance(value, list):
        return [semantic_facts(v) for v in value]
    return value


def score(stats, coefficients, supported_keys, *, inapplicable_keys=()):
    """Unknown/missing events are not zeros. A provider must attest applicability.

    Bonus coefficients require their own expected indicator/event vector; deriving
    E[bonus(X)] from E[X] would silently change custom scoring.
    """
    total = Decimal(0)
    for key, raw in coefficients.items():
        coefficient = decimal(raw)
        if not coefficient or key in inapplicable_keys:
            continue
        if key not in supported_keys:
            raise Unavailable("unsupported_scoring", details={"keys": [key]})
        if key not in stats:
            raise Unavailable("missing_scoring_stat", state="incomplete_projections", details={"keys": [key]})
        total += coefficient * decimal(stats[key])
    return total


def _hungarian(cost):
    """Rectangular exact minimum assignment using Decimal potentials (rows<=cols)."""
    n, m = len(cost), len(cost[0]) if cost else 0
    u, v, p, way = [Decimal(0)] * (n + 1), [Decimal(0)] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minimum, used = [Decimal("Infinity")] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], Decimal("Infinity"), 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                current = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if current < minimum[j]:
                    minimum[j], way[j] = current, j0
                if minimum[j] < delta:
                    delta, j1 = minimum[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if not p[j0]:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    result = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            result[p[j] - 1] = j - 1
    return result


def optimize(slots, players, *, empty_policy, locked=None, locked_bench=(), hindsight=False):
    """Maximum-weight legal assignment, optionally prioritizing occupied slots.

    locked maps slot index to player id or None (a locked empty slot). Hindsight
    ignores actual locks, so a Thursday bench player remains Max PF eligible.
    """
    if empty_policy not in {"allow", "fill_available"}:
        raise Unavailable("empty_slot_policy_required")
    if len(slots) > 24 or any(slot not in SLOTS for slot in slots) or len(players) > 150:
        raise Unavailable("unsupported_lineup")
    if hindsight:
        players = [{**p, "points": p.get("actual_points", p["points"])} for p in players]
    ids = [str(p["player_id"]) for p in players]
    if len(ids) != len(set(ids)):
        raise Unavailable("duplicate_player")
    pool = {str(p["player_id"]): p for p in players}
    locked = {} if hindsight else (locked or {})
    chosen, used = {}, set()
    for raw_index, pid in locked.items():
        index = int(raw_index)
        if index < 0 or index >= len(slots):
            raise Unavailable("invalid_locked_slot")
        if pid is None:
            chosen[index] = None
            continue
        pid = str(pid)
        if pid not in pool or pid in used or not SLOTS[slots[index]].intersection(pool[pid]["positions"]):
            raise Unavailable("invalid_locked_starter")
        if "actual_points" not in pool[pid]:
            raise Unavailable("missing_locked_actual", state="incomplete_projections")
        chosen[index] = {**pool[pid], "points": str(decimal(pool[pid]["actual_points"])), "locked_actual": True}
        used.add(pid)
    excluded = used | (set() if hindsight else set(map(str, locked_bench)))
    candidates = sorted((p for p in players if str(p["player_id"]) not in excluded), key=lambda p: str(p["player_id"]))
    remaining = [i for i in range(len(slots)) if i not in chosen]
    limit = sum(max([abs(decimal(p["points"]))] + [abs(decimal(v)) for v in p.get("slot_points", {}).values()]) for p in candidates) + 1
    bonus = limit * 2 if empty_policy == "fill_available" else Decimal(0)
    priority_bonus = (limit + bonus) * (len(slots) + 2)
    forbidden = priority_bonus * (len(slots) + 2)
    costs = []
    for i in remaining:
        costs.append([-(decimal(p.get("slot_points", {}).get(slots[i], p["points"])) + bonus + (priority_bonus if p.get("real_priority") else 0))
                      if SLOTS[slots[i]].intersection(p["positions"]) and slots[i] in p.get("allowed_slots", slots) else forbidden
                      for p in candidates] + [Decimal(0)] * len(remaining))
    for index, column in zip(remaining, _hungarian(costs)):
        p = candidates[column] if column < len(candidates) and costs[remaining.index(index)][column] < forbidden else None
        chosen[index] = ({**p, "points": str(decimal(p.get("slot_points", {}).get(slots[index], p["points"])))} if p else None)
    lineup = [{"slot_index": i, "slot": slot, "player": chosen[i]} for i, slot in enumerate(slots)]
    return {"points": str(sum((decimal(row["player"]["points"]) for row in lineup if row["player"]), Decimal(0))),
            "lineup": lineup, "gaps": [row["slot_index"] for row in lineup if row["player"] is None]}


def idp_bye_fill(slots, healthy, bye_players, means, *, empty_policy):
    """Lexicographic counterfactual: keep maximum real coverage, then fill byes.

    Slot reassignment is legal; replacing real coverage with a virtual upgrade
    is not. Voluntarily leaving a negative scorer empty cannot authorize an FA.
    """
    if empty_policy not in {"allow", "fill_available"}:
        raise Unavailable("empty_slot_policy_required")
    real = optimize(slots, healthy, empty_policy="fill_available")
    if not bye_players or not any(slots[i] in IDP for i in real["gaps"]):
        return optimize(slots, healthy, empty_policy=empty_policy)
    # Eligibility alone identifies the position means that are actually needed.
    virtual = []
    for player in bye_players:
        allowed = [slot for slot in slots if slot in IDP and SLOTS[slot].intersection(player["positions"])]
        if allowed:
            virtual.append({"player_id": "hypothetical:" + str(player["player_id"]), "positions": player["positions"],
                            "points": "0", "allowed_slots": allowed, "hypothetical": True,
                            "bye_player_id": str(player["player_id"])})
    if not virtual:
        return optimize(slots, healthy, empty_policy=empty_policy)
    candidates = [{**p, "real_priority": True} for p in healthy] + virtual
    eligibility = optimize(slots, candidates, empty_policy="fill_available")
    used_slots = {r["slot"] for r in eligibility["lineup"] if r["player"] and r["player"].get("hypothetical")}
    if not used_slots:
        return optimize(slots, healthy, empty_policy=empty_policy)
    # A position with missing history is unknown, never a synthetic zero.
    possible_slots = {slot for p in virtual for slot in p["allowed_slots"]}
    if not possible_slots <= set(means):
        raise Unavailable("missing_idp_replacement_mean", state="incomplete_projections")
    for player in virtual:
        player["slot_points"] = {slot: str(decimal(means[slot])) for slot in player["allowed_slots"]}
    result = optimize(slots, [{**p, "real_priority": True} for p in healthy] + virtual, empty_policy="fill_available")
    for row in result["lineup"]:
        if row["player"]:
            row["player"].pop("real_priority", None)
            if empty_policy == "allow" and decimal(row["player"]["points"]) < 0:
                row["player"] = None
    result["gaps"] = [r["slot_index"] for r in result["lineup"] if r["player"] is None]
    result["points"] = str(sum((decimal(r["player"]["points"]) for r in result["lineup"] if r["player"]), Decimal(0)))
    return result
