"""Pure, two-sided post-trade roster evaluation; no HTTP, DB or flag reads.

Values are dynasty-value proxies, not fantasy-point projections. Missing data
stays unknown. Slots share one exact assignment, so FLEX cannot reuse a starter.
See docs/plans/post-trade-roster-evaluation/scope.md for rollout boundaries.
"""
from dataclasses import dataclass, field
from itertools import combinations
import math
from typing import Mapping

POSITIONS = frozenset(("QB", "RB", "WR", "TE"))
ELIGIBILITY = {
    "QB": frozenset(("QB",)), "RB": frozenset(("RB",)),
    "WR": frozenset(("WR",)), "TE": frozenset(("TE",)),
    "FLEX": frozenset(("RB", "WR", "TE")),
    "WRRB_FLEX": frozenset(("RB", "WR")),
    "REC_FLEX": frozenset(("WR", "TE")), "SUPER_FLEX": POSITIONS,
}
UNAVAILABLE = frozenset(("OUT", "IR", "PUP", "SUSP", "SUSPENDED", "DOUBTFUL", "INACTIVE"))


@dataclass(frozen=True)
class Asset:
    id: str
    positions: frozenset[str]
    value: float
    startable: bool = True
    available: bool = True
    is_pick: bool = False


@dataclass(frozen=True)
class Rules:
    slots: tuple[str, ...]
    source: str = "unknown"  # observed / estimated / unknown
    capacity: int | None = None  # active roster; reserve/taxi do not use it
    observed_at: str | None = None
    uncertainties: tuple[str, ...] = ()


@dataclass(frozen=True)
class Team:
    id: str
    roster: tuple[str, ...]
    inactive: frozenset[str] = frozenset()  # reserve + taxi
    outlook: str = "balanced"
    availability_known: bool = True


def assign(slots: tuple[str, ...], assets: list[Asset]) -> list[str | None]:
    """Rectangular Hungarian matching, O(slots² * roster).

    Dummy columns leave a slot empty. Occupancy dominates aggregate value;
    input sorting makes ties deterministic. Ineligible edges cost more than
    any feasible assignment. Each real asset can occupy at most one slot.
    """
    assets = sorted(assets, key=lambda a: a.id)
    n, m = len(slots), len(assets) + len(slots)
    if not n:
        return []
    bonus = 1 + sum(max(0, a.value) for a in assets)
    cost = [[-(bonus + max(0, a.value)) if a.positions & ELIGIBILITY[s]
             else bonus * (n + 1) for a in assets] + [0.] * n for s in slots]
    u, v, p, way = [0.] * (n + 1), [0.] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minimum, used = [math.inf] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], math.inf, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minimum[j]:
                        minimum[j], way[j] = cur, j0
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
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if not j0:
                break
    result = [None] * n
    for j in range(1, len(assets) + 1):
        if p[j]:
            result[p[j] - 1] = assets[j - 1].id
    return result


def _health(team: Team, roster: set[str], assets: Mapping[str, Asset], rules: Rules,
            absent: frozenset[str] = frozenset()) -> dict:
    available = [assets[p] for p in sorted(roster) if p in assets
                 and not assets[p].is_pick and assets[p].available
                 and p not in team.inactive and p not in absent]
    usable = [a for a in available if a.startable]
    assignment = assign(rules.slots, available)
    quality_assignment = assign(rules.slots, usable)
    # Every union of slot-eligible positions is a Hall constraint. This
    # catches a lost FLEX body even when all dedicated counts still pass.
    deficits, legal_deficits, coverage = {}, {}, {}
    for size in range(1, 5):
        for group in combinations(sorted(POSITIONS), size):
            positions = frozenset(group)
            constrained = [ELIGIBILITY[s] for s in rules.slots if ELIGIBILITY[s] <= positions]
            # Only actual unions of slot eligibility are constraints. An
            # unrelated WR must not count as backup for an RB-only lineup.
            if not constrained or frozenset().union(*constrained) != positions:
                continue
            demand = len(constrained)
            if demand:
                key = "+".join(group)
                supply = sum(bool(a.positions & positions) for a in usable)
                coverage[key] = {"demand": demand, "supply": supply}
                deficits[key] = max(0, demand - supply)
                legal_deficits[key] = max(0, demand - sum(bool(a.positions & positions) for a in available))
    selected = {p for p in quality_assignment if p}
    depth = {pos: sum(pos in a.positions for a in usable if a.id not in selected)
             for pos in sorted(POSITIONS)}
    counts = {pos: sum(pos in a.positions for a in usable) for pos in sorted(POSITIONS)}
    return {
        "lineup": [{"slot": s, "player_id": p} for s, p in zip(rules.slots, assignment)],
        "filled_slots": sum(p is not None for p in assignment),
        "usable_filled_slots": len(selected),
        "starter_value": round(sum(assets[p].value for p in assignment if p), 3),
        "roster_value": round(sum(assets[p].value for p in roster if p in assets), 3),
        "usable_counts": counts, "bench_depth": depth,
        "deficits": deficits, "legal_deficits": legal_deficits, "coverage": coverage,
        "active_count": sum(p not in team.inactive and not assets[p].is_pick
                            for p in roster if p in assets),
    }


def _team_result(team, outgoing, incoming, assets, rules, cuts, scenarios):
    before_ids = set(team.roster)
    after_ids = (before_ids - set(outgoing)) | set(incoming)
    unknown, blockers = [], []
    if not set(outgoing) <= before_ids:
        unknown.append("outgoing_asset_not_owned")
    if set(incoming) & before_ids:
        unknown.append("incoming_asset_already_owned")
    if len(team.roster) != len(before_ids):
        unknown.append("duplicate_roster_asset")
    if not team.availability_known:
        unknown.append("availability_unknown")
    if any(p not in assets for p in before_ids | after_ids):
        unknown.append("unresolved_roster_asset")
    if not set(cuts) <= after_ids or set(cuts) & set(incoming):
        unknown.append("invalid_cut_plan")
    after_ids -= set(cuts)
    before, after = _health(team, before_ids, assets, rules), _health(team, after_ids, assets, rules)
    for field_name in ("legal_deficits", "deficits"):
        for group, deficit in after[field_name].items():
            if deficit > before[field_name].get(group, 0):
                blockers.append(f"{field_name}:{group}")
    # Preserve one usable replacement per constrained group, including FLEX
    # groups. This is the Hall condition for surviving a single absence;
    # raw dedicated-position counts alone miss shared-slot depth losses.
    for group, coverage in after["coverage"].items():
        protected = min(coverage["demand"] + 1, before["coverage"][group]["supply"])
        if coverage["supply"] < protected:
            blockers.append(f"backup_depth:{group}")
    overflow = 0
    if rules.capacity is not None:
        overflow = max(0, after["active_count"] - rules.capacity)
        if overflow > max(0, before["active_count"] - rules.capacity):
            blockers.append("cuts_required")
    else:
        unknown.append("capacity_unknown")
    for label, absent in scenarios.items():
        b = _health(team, before_ids, assets, rules, frozenset(absent))
        a = _health(team, after_ids, assets, rules, frozenset(absent))
        if any(a["deficits"][g] > b["deficits"][g] for g in a["deficits"]):
            blockers.append(f"availability_scenario:{label}")
    starter_delta = (after["starter_value"] - before["starter_value"]) / max(1, before["starter_value"])
    roster_delta = (after["roster_value"] - before["roster_value"]) / max(1, before["roster_value"])
    # Bounded, comparable signals for both managers. Outlook changes utility,
    # never structural eligibility. Future value uses dynasty values/picks.
    outlook = {"championship": "contender", "jets": "rebuilder"}.get(team.outlook, team.outlook)
    outlook = outlook if outlook in ("contender", "rebuilder") else "balanced"
    weight = {"contender": .75, "balanced": .5, "rebuilder": .25}[outlook]
    utility = weight * starter_delta + (1 - weight) * roster_delta
    replacements = []
    post_starters = {r["player_id"] for r in after["lineup"] if r["player_id"]}
    pre_starters = {r["player_id"] for r in before["lineup"] if r["player_id"]}
    # Report whole-lineup promotions; assigning one replacement to a traded
    # player would misrepresent cascades through overlapping flex slots.
    for pid in sorted(pre_starters & set(outgoing)):
        replacements.append({"outgoing_starter_id": pid,
                             "entering_starter_ids": sorted(post_starters - pre_starters)})
    return {"team_id": team.id, "outlook": outlook, "before": before, "after": after,
            "blockers": sorted(set(blockers)), "unknowns": sorted(set(unknown)),
            "cuts_required": overflow, "cuts": sorted(cuts), "replacements": replacements,
            "utility": round(utility, 6), "starter_value_delta": round(starter_delta, 6),
            "roster_value_delta": round(roster_delta, 6)}


def evaluate(*, viewer: Team, partner: Team, give: list[str], receive: list[str],
             assets: Mapping[str, Asset], rules: Rules,
             cuts: Mapping[str, list[str]] | None = None,
             scenarios: Mapping[str, frozenset[str]] | None = None) -> dict:
    """Evaluate a fully assembled exchange on both complete rosters.

    `safe` means only the declared checks passed; weekly schedule risk remains
    unknown without supplied scenarios. Explicit cuts are evaluated, never
    invented. Consumers must not enforce or advertise estimated inputs as safe.
    """
    unknown = list(rules.uncertainties)
    if rules.source != "observed":
        unknown.append("lineup_settings_" + rules.source)
    valid_slots = bool(rules.slots) and all(s in ELIGIBILITY for s in rules.slots)
    if not valid_slots:
        unknown.append("unsupported_or_missing_lineup")
    if (not give or not receive or len(set(give)) != len(give) or len(set(receive)) != len(receive)
            or set(give) & set(receive) or viewer.id == partner.id):
        unknown.append("invalid_exchange")
    if any(not math.isfinite(a.value) or a.value < 0 for a in assets.values()):
        unknown.append("invalid_values")
    result = {"schema_version": 1, "value_basis": "consensus_dynasty_proxy",
              "settings_source": rules.source, "observed_at": rules.observed_at,
              "schedule_coverage": "supplied_scenarios" if scenarios else "unknown",
              "unknowns": unknown, "teams": {}, "status": "unknown", "eligible": False}
    if not valid_slots or "invalid_values" in unknown:
        return result
    for team, outgoing, incoming in ((viewer, give, receive), (partner, receive, give)):
        result["teams"][team.id] = _team_result(team, outgoing, incoming, assets, rules,
                                               (cuts or {}).get(team.id, []), scenarios or {})
    teams = list(result["teams"].values())
    blocked = any(t["blockers"] for t in teams)
    uncertain = bool(unknown) or any(t["unknowns"] for t in teams)
    result["status"] = "blocked" if blocked else "unknown" if uncertain else "safe"
    result["eligible"] = result["status"] == "safe"
    result["mutual_utility"] = min(t["utility"] for t in teams)
    return result


@dataclass
class Context:
    """Immutable inputs captured once per deck, with per-package memoization."""
    viewer_id: str
    teams: Mapping[str, Team]
    assets: Mapping[str, Asset]
    rules: Rules
    cache: dict = field(default_factory=dict)

    def card(self, card) -> dict:
        key = (card.target_user_id, tuple(sorted(card.give_player_ids)),
               tuple(sorted(card.receive_player_ids)))
        if key not in self.cache:
            if self.viewer_id not in self.teams or card.target_user_id not in self.teams:
                self.cache[key] = {"schema_version": 1, "status": "unknown", "eligible": False,
                                   "unknowns": ["missing_team"], "teams": {}}
            else:
                self.cache[key] = evaluate(viewer=self.teams[self.viewer_id],
                    partner=self.teams[card.target_user_id], give=card.give_player_ids,
                    receive=card.receive_player_ids, assets=self.assets, rules=self.rules)
        return self.cache[key]
