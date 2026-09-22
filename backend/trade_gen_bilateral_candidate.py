"""Versioned bilateral candidate with explicit term and portfolio diagnostics.

Preference identifies desired assets; captured market pricing bounds the terms.
Support weights and efficiency thresholds are provisional policy, not calibrated
acceptance evidence. No provider calls, public private-board fields or output cap.
The incumbent remains separately callable with its original defaults and proof.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
import heapq
from time import perf_counter

from . import trade_gen_bilateral as incumbent
from . import trade_gen_owner as owner
from .ranking_service import ORDERED_TIERS


ARM = incumbent.ARM
BILATERAL_GENERATOR_VERSION = VERSION = "owner-v2-bilateral-2"
_WEIGHTS = dict(incumbent._WEIGHTS)
_MIN_COMPANION_SHARE = .05
_MIN_TERM_IMPROVEMENT = .025
TERM_ORDERING_VERSION = "same-focal-terms-1"
TERM_LOOKAHEAD = 32


class _Search(incumbent._Search):
    def _plan_asset(self, team, pid):
        """A future portfolio gain jointly uses horizon and known preference."""
        if team["outlook"] not in ("jets", "rebuilder"):
            return super()._plan_asset(team, pid)
        key = team["uid"], pid
        if key not in self._plan_cache:
            pos, age = self._position(pid), getattr(self.players[pid], "age", None)
            feature = self._features[team["uid"], pid]
            direction = feature["direction"]
            if pos == "PICK":
                fit = 1.0
            elif not owner._finite(age):
                fit = 0.0
            elif pos == "RB":
                elite = feature["known"] and feature["personal_tier"] in ORDERED_TIERS[:3]
                # Discounted prospects remain eligible under the incumbent's
                # exact exception. Youth alone does not make an RB a target.
                fit = .4 if elite else -.15 if age <= incumbent._YOUNG["RB"] else -1.0
            elif pos in ("WR", "TE", "QB") and age <= incumbent._YOUNG[pos]:
                fit = .85 if direction is not None and direction >= .025 else (
                    -.10 if direction is not None and direction <= -.025 else .45)
            else:
                fit = -.45
            self._plan_cache[key] = fit * (1.0 if team["outlook"] == "jets" else .6)
        return self._plan_cache[key]

    def _composition(self, team, ids):
        gross = sum(self.market[p] for p in ids)
        def share(predicate):
            return sum(self.market[p] for p in ids if predicate(p)) / gross
        def favored_horizon(pid):
            pos, age = self._position(pid), getattr(self.players[pid], "age", None)
            feature = self._features[team["uid"], pid]
            return (pos in ("WR", "TE", "QB") and owner._finite(age)
                    and age <= incumbent._YOUNG[pos] and feature["known"]
                    and (feature["direction"] or 0) >= .025)
        return {"market_value": gross, "asset_count": len(ids),
            "pick_share": share(lambda p: self._position(p) == "PICK"),
            "rb_share": share(lambda p: self._position(p) == "RB"),
            "favored_horizon_player_share": share(favored_horizon),
            "unknown_age_ids": sorted(p for p in ids if self._position(p) != "PICK"
                                       and not owner._finite(getattr(self.players[p], "age", None)))}

    def _owner(self, team, give, receive):
        result = super()._owner(team, give, receive)
        if "plan_composition" in result:
            return result
        # Leave support weights unchanged: same-focal efficiency is a separate
        # comparison, not a market-equality objective hidden in new weights.
        result["plan_composition"] = {"outgoing": self._composition(team, give),
                                      "incoming": self._composition(team, receive)}
        # Current request inputs have slots/inactive IDs and dynasty values,
        # but no projection horizon, freshness or per-player projected points.
        # Never turn the legal value-based assignment into a points claim.
        result["starter_evidence"] = {"state": "unknown", "projected_starter_delta": None,
            "immediate_starter_applicability": "not_applicable" if team["outlook"] == "jets" else "unknown",
            "proxy": result["lineup_proxy"], "slot_source": team["lineup_source"],
            "missing": ["fresh_scoring_compatible_projections", "projection_horizon",
                        "availability_as_of", "required_cut_evidence"]}
        result["benefits"] = ["dynasty_roster_fit_proxy" if b == "usable_roster_improvement" else b
                              for b in result["benefits"]]
        result["decomposition"] = {"personal_preference": result["intent"]["net_preference"],
            "portfolio_and_roster_proxy": result["team_plan_gain"],
            "adjusted_market_gain": result["market_gain_fraction"],
            "roster_proxy_utility": result["need_utility"],
            "projected_starter_delta": None, "support_range": result["support"]["range"]}
        _, outgoing, incoming = self._package(give, receive, self.market)
        raw_outgoing = sum(self.market[p] for p in give)
        raw_incoming = sum(self.market[p] for p in receive)
        result["market_terms"] = {"raw_outgoing": raw_outgoing, "raw_incoming": raw_incoming,
            "adjusted_outgoing": outgoing, "adjusted_incoming": incoming,
            "outgoing_adjustment": outgoing - raw_outgoing,
            "incoming_adjustment": incoming - raw_incoming,
            "convention": "existing_market_package_pricing_once",
            "best_asset_ids": sorted(p for p in give + receive
                                     if self.market[p] == max(self.market[q] for q in give + receive))}
        result["consideration_profile"] = {
            "manager_id": team["uid"],
            "known_personal": all(self._features[team["uid"], p]["known"] for p in give + receive),
            "raw_outgoing_personal": sum(team["values"][p] for p in give),
            "raw_incoming_personal": sum(team["values"][p] for p in receive),
            "outgoing_plan_mean": sum(self.market[p] * self._plan_asset(team, p) for p in give) / raw_outgoing,
            "incoming_plan_mean": sum(self.market[p] * self._plan_asset(team, p) for p in receive) / raw_incoming,
            "outgoing_positions": sorted(self._position(p) for p in give),
            "incoming_positions": sorted(self._position(p) for p in receive),
            "availability_shape": [sorted((self._position(p), p in self._lineup_assets and p not in team["inactive"])
                                          for p in ids) for ids in (give, receive)]}
        return result

    def _freeze_decision(self, card, data, reason, eligible):
        data["generator_version"] = VERSION
        if "construction" in data:
            data["construction"].update(policy="price_efficient_bilateral_portfolio", coefficients=_WEIGHTS)
        return super()._freeze_decision(card, data, reason, eligible)

    def _companion_benefits(self, team, pid, focal_value):
        """Explain the recipient's additional benefit independently of support.

        A dynasty-value proxy alone is insufficient to assert an extra starter.
        A lower-priced companion is still allowed when needed to clear pricing.
        """
        if self.market[pid] / focal_value < _MIN_COMPANION_SHARE:
            return []
        feature, pref = self._features[team["uid"], pid], team["preferences"]
        benefits = []
        if feature["known"] and (feature["direction"] or 0) >= .025:
            benefits.append("known_personal_target")
        if (pid in pref.get("targets", ()) or self._position(pid) in pref.get("acquire_positions", ())):
            benefits.append("declared_target")
        if team["outlook"] in ("jets", "rebuilder") and self._plan_asset(team, pid) >= .5:
            benefits.append("future_portfolio")
        return benefits

    def evaluate(self, card, *, partial=False):
        # Core retains both managers' safety, explicit intent and pricing gates.
        # Efficiency changes ordering rather than deleting a valid alternative.
        result = self._core(card, partial=partial)
        if result.eligible:
            data = result.as_dict()
            avoidable, useful, comparisons = [], [], []
            market_loss = max(-data[s]["market_gain_fraction"] for s in ("viewer", "counterparty"))
            for side, pins, recipient in (
                    ("give_player_ids", self.give_pins, self.teams[card.target_user_id]),
                    ("receive_player_ids", self.recv_pins, self.teams[self.user_id])):
                ids = tuple(getattr(card, side))
                focal = self._head(ids, self.market)
                for pid in sorted(ids):
                    if len(ids) <= 1 or pid == focal or pid in pins:
                        continue
                    simple = replace(card, **{side: [p for p in ids if p != pid]})
                    simple_proof = self._core(simple, partial=partial)
                    if not simple_proof.eligible:
                        continue  # Required price/authority compensation survives.
                    smaller = simple_proof.as_dict()
                    simpler_loss = max(-smaller[s]["market_gain_fraction"] for s in ("viewer", "counterparty"))
                    benefits = self._companion_benefits(recipient, pid, self.market[focal])
                    if simpler_loss - market_loss >= _MIN_TERM_IMPROVEMENT:
                        benefits.append("improved_bilateral_market_balance")
                    if benefits:
                        useful.append({"asset_id": pid, "recipient": recipient["uid"], "benefits": benefits})
                    else:
                        avoidable.append(pid)
                    comparisons.append({"asset_id": pid, "recipient": recipient["uid"],
                        "simpler_give_ids": sorted(simple.give_player_ids),
                        "simpler_receive_ids": sorted(simple.receive_player_ids),
                        "simpler_worst_market_loss": simpler_loss,
                        "incremental_market_balance": simpler_loss - market_loss})
            data["term_efficiency"] = {"efficient": not avoidable,
                "avoidable_companions": sorted(avoidable), "useful_companions": sorted(useful, key=lambda x: x["asset_id"]),
                "comparisons": sorted(comparisons, key=lambda x: x["asset_id"]),
                "worst_adjusted_market_loss": market_loss,
                "audited_alternatives": len(comparisons),
                "scope": "same_focal_partner_single_companion_removal",
                "ordering_version": TERM_ORDERING_VERSION,
                "thresholds": {"minimum_companion_value_share": _MIN_COMPANION_SHARE,
                               "minimum_bilateral_market_improvement": _MIN_TERM_IMPROVEMENT},
                "policy": "rank_efficient_first_preserve_valid_inventory"}
            result = replace(result, snapshot_json=owner._dump(data))
        self._decisions[incumbent._identity(card)] = result
        return result


@dataclass(frozen=True, slots=True)
class _GenerationRejection:
    """Final internal status only; never an external or served-offer proof."""
    reason: str

    @property
    def eligible(self):
        return False

    def as_dict(self):
        raise RuntimeError("Internal generation rejection has no diagnostic payload")

    def __getattr__(self, name):
        # A default-valued getattr must not hide a new evidence consumer.
        raise RuntimeError(f"Internal generation rejection has no field {name!r}")


class _GenerationSearch(_Search):
    """Generation alone consumes rejected results as final status/reason."""
    def _freeze_decision(self, card, data, reason, eligible):
        if not eligible:
            return _GenerationRejection(reason)
        return super()._freeze_decision(card, data, reason, eligible)


def evaluate_bilateral_trades(cards, **kwargs):
    search = _Search(**kwargs)
    with search.ts._cfg_override(search.config), search.ts.stud_tax_override("market"):
        return [search.evaluate(c, partial=owner._authenticated_partial(c, search)) for c in cards]


def evaluate_bilateral_trade(card, **kwargs):
    return evaluate_bilateral_trades([card], **kwargs)[0]


def _profile_no_worse(earlier, later):
    """Compare independent personal costs/benefits, not summed support."""
    return (earlier["known_personal"] and later["known_personal"]
        and earlier["outgoing_positions"] == later["outgoing_positions"]
        and earlier["incoming_positions"] == later["incoming_positions"]
        and earlier["availability_shape"] == later["availability_shape"]
        and earlier["raw_outgoing_personal"] <= later["raw_outgoing_personal"] + owner._EPS
        and earlier["raw_incoming_personal"] + owner._EPS >= later["raw_incoming_personal"]
        and earlier["outgoing_plan_mean"] <= later["outgoing_plan_mean"] + owner._EPS
        and earlier["incoming_plan_mean"] + owner._EPS >= later["incoming_plan_mean"])


def term_evidence_valid(data, *, user_id, target_user_id):
    """Fail closed on incomplete private metadata; useful to serving callers."""
    try:
        terms = data["term_efficiency"]
        if (data["generator"] != ARM or data["generator_version"] != VERSION
                or terms["ordering_version"] != TERM_ORDERING_VERSION
                or data["eligible"] is not True or data["reason"] != "eligible"
                or not owner._finite(terms["worst_adjusted_market_loss"])
                or not 0 <= terms["worst_adjusted_market_loss"] <= 1
                or not isinstance(terms["avoidable_companions"], list)
                or any(not isinstance(p, str) for p in terms["avoidable_companions"])):
            return False
        for side, uid in (("viewer", user_id), ("counterparty", target_user_id)):
            profile = data[side]["consideration_profile"]
            if profile["manager_id"] != uid or type(profile["known_personal"]) is not bool:
                return False
            for field in ("raw_outgoing_personal", "raw_incoming_personal",
                          "outgoing_plan_mean", "incoming_plan_mean"):
                if not owner._finite(profile[field]):
                    return False
            for field in ("outgoing_positions", "incoming_positions"):
                if (not isinstance(profile[field], list) or not profile[field]
                        or any(p not in (*owner._POSITIONS, "PICK") for p in profile[field])):
                    return False
            availability = profile["availability_shape"]
            if not isinstance(availability, list) or len(availability) != 2:
                return False
            for shape in availability:
                if not isinstance(shape, list) or any(not isinstance(item, list) or len(item) != 2
                    or item[0] not in (*owner._POSITIONS, "PICK") or type(item[1]) is not bool for item in shape):
                    return False
    except (KeyError, TypeError, AttributeError):
        return False
    return True


def term_precedence(cards):
    """Return index dependencies from immutable proofs, without changing cards.

    Only same-partner, same exact give OR receive alternatives are compared.
    Among at most 32 lower-cost representatives per family, the cheaper terms
    precede terms with no additional known personal/portfolio/position benefit.
    Missing boards never become proof of equivalent personal benefit. Separately
    audited removable companions use their explicit no-benefit diagnosis.
    This is a bounded price-efficiency audit, not an exhaustive Pareto claim.
    """
    records, families = {}, defaultdict(list)
    for index, card in enumerate(cards):
        proof = getattr(card, "owner_evaluation", None)
        try:
            if not isinstance(proof, owner.OwnerDecisionContext) or not proof.matches(card):
                continue
            data = proof.as_dict()
            if (not term_evidence_valid(data, user_id=proof.user_id, target_user_id=proof.target_user_id)
                    or data.get("construction", {}).get("explicit_selection")):
                continue
        except (KeyError, TypeError, AttributeError, ValueError):
            continue
        terms = data["term_efficiency"]
        give, receive = frozenset(proof.give_ids), frozenset(proof.receive_ids)
        cost = terms["worst_adjusted_market_loss"], len(give) + len(receive)
        records[index] = (data, give, receive, cost)
        for direction, ids in (("give", give), ("receive", receive)):
            families[proof.user_id, proof.target_user_id, direction, ids].append(index)
    predecessors = defaultdict(set)
    for family in families.values():
        family.sort(key=lambda index: (records[index][3], tuple(sorted(records[index][1])),
                                       tuple(sorted(records[index][2]))))
        representatives = family[:TERM_LOOKAHEAD]
        for later_index in family:
            later, later_give, later_receive, later_cost = records[later_index]
            for earlier_index in representatives:
                earlier, earlier_give, earlier_receive, earlier_cost = records[earlier_index]
                if earlier_cost >= later_cost:
                    continue
                removed = (later_give - earlier_give) | (later_receive - earlier_receive)
                needless = (bool(removed) and earlier_give <= later_give and earlier_receive <= later_receive
                    and removed <= set(later["term_efficiency"]["avoidable_companions"]))
                equivalent = all(_profile_no_worse(earlier[side]["consideration_profile"],
                    later[side]["consideration_profile"]) for side in ("viewer", "counterparty"))
                if needless or equivalent:
                    predecessors[later_index].add(earlier_index)
    return dict(predecessors)


def _rank(cards):
    baseline = incumbent._rank(cards)
    predecessors = term_precedence(baseline)
    successors = defaultdict(list)
    for later, earlier in predecessors.items():
        for index in earlier:
            successors[index].append(later)
    pending = [i for i in range(len(baseline)) if not predecessors.get(i)]
    heapq.heapify(pending)
    ranked = []
    while pending:
        index = heapq.heappop(pending)
        ranked.append(baseline[index])
        for later in successors[index]:
            predecessors[later].remove(index)
            if not predecessors[later]:
                heapq.heappush(pending, later)
    return ranked


def generate_bilateral_trades(**kwargs):
    started = perf_counter()
    search = _GenerationSearch(**kwargs)
    cards, raw_report = incumbent._generate_with_search(search, ranker=_rank, version=VERSION)
    report = raw_report.as_dict()
    counts = Counter()
    for card in cards:
        data = card.owner_evaluation.as_dict()
        counts["efficient" if data["term_efficiency"]["efficient"] else "avoidable_alternative"] += 1
        counts["companion_comparisons"] += data["term_efficiency"]["audited_alternatives"]
    report.update(support_weights=_WEIGHTS, term_efficiency=dict(counts),
        term_ordering={"version": TERM_ORDERING_VERSION, "comparisons_per_family": TERM_LOOKAHEAD,
                       "policy": "same_focal_precedence_preserve_inventory"},
        starter_evidence="dynasty_proxy_only_no_projected_points",
        elapsed_seconds=round(perf_counter() - started, 6))
    return cards, owner.OwnerGenerationReport(owner._dump(report))
