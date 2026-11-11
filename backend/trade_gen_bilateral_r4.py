"""Bilateral revision 4: what real offers say about picks and consolidation asks.

Built on revision 2 (owner-v2-bilateral-2, the serving revision), never on
revision 3. Spec: docs/plans/offer-learnings/plan.md §3 WS1; evidence:
docs/plans/realtime-trade-engine/offer-history.md findings 4-6. These are
effects to build and grade, not fitted parameters.

Three rules change ORDER only. Inventory, eligibility, terms, the market floor
and the overpay gate are revision 2's: every rule acts on support scores the
ranker and presentment already read, never on `utility`, `market_gain_fraction`
or the priced package. Size (organic 1x1/1x2/2x1) is unchanged and pinned.

1. Owned-pick premium (R4). Picks the other manager would give up count above
   market in THEIR market-acceptability component, by their outlook.
2. Pay-picks tie-breaker (R1). Inside the existing comparable set only.
3. Best-asset rule (R5). The other manager giving up the trade's most valuable
   asset for several lesser ones is demoted, except picks to a rebuilder/tanker.
4. Partner activity (R8, plan §3 WS7). Only when the worker passes
   `partner_activity` (flag `trade.partner_activity`): offers to a manager who
   completes clearly fewer trades than their league-mates are demoted. The
   threshold is the league's own; a league where everyone trades, or with too
   little history, demotes nobody. Absent input: WS1's bytes exactly.

No database, server, provider or network access occurs in this module.
"""

from collections import Counter, defaultdict
import heapq
import statistics
from time import perf_counter

from . import trade_gen_owner as owner
from . import trade_gen_bilateral as incumbent
from . import trade_gen_bilateral_candidate as previous


ARM = previous.ARM
BILATERAL_GENERATOR_VERSION = VERSION = "owner-v2-bilateral-4"
RULES_VERSION = "offer-learnings-1"
# The other manager's resolved outlook (owner._OUTLOOKS normalizes "tanking" to
# "jets") -> premium on the market value of the picks they would give up.
# Starting values (plan §3 WS1: about 20% at the top). Any other value: none.
PICK_PREMIUM = {"jets": .20, "rebuilder": .20, "not_sure": .10,
                "contender": 0.0, "championship": 0.0}
_PICK_WANTING = frozenset(("jets", "rebuilder"))
# Four of the ranker's own quality tolerances: below near-equal offers, never
# below one that is clearly worse on both managers' support.
BEST_ASSET_DEMOTION = 4 * incumbent._QUALITY_TOLERANCE
_PICK_CLASS = {"pays_picks": 0, "players_only": 1, "picks_both_ways": 1, "asks_picks": 2}
# Partner activity (WS7). Input: {league manager id: completed trades this
# league year} from the stored public manager profiles. Starting rule (plan
# §3 WS7): flagged at or below a third of the league median, only when that
# median is at least two and at least half the league's managers have a
# profile. A manager with no profile is never flagged.
RULES_VERSION_PARTNER_ACTIVITY = "offer-learnings-1+partner-activity-1"
PARTNER_ACTIVITY_THRESHOLD_SHARE = 1 / 3
PARTNER_ACTIVITY_MIN_MEDIAN = 2
PARTNER_ACTIVITY_MIN_PROFILED_SHARE = .5
# Half the best-asset demotion: a one-season count is a weaker, noisier signal
# than an offer's own shape. Still past the comparable set (.025 weaker, .05
# total), so it moves a flagged offer below near-equal ones, not below
# clearly better ones.
PARTNER_ACTIVITY_DEMOTION = 2 * incumbent._QUALITY_TOLERANCE


def _league_activity(counts, team_ids):
    """The league's threshold from completed-trade counts, computed once per search."""
    counts = {str(uid): n for uid, n in (counts or {}).items()
              if isinstance(n, int) and not isinstance(n, bool) and n >= 0}
    profiled = sorted(counts[uid] for uid in team_ids if uid in counts)
    managers = len(team_ids)
    median = statistics.median(profiled) if profiled else None
    if not profiled or len(profiled) < PARTNER_ACTIVITY_MIN_PROFILED_SHARE * managers:
        reason = "league_history_thin"
    elif median < PARTNER_ACTIVITY_MIN_MEDIAN:
        reason = "league_median_below_minimum"
    else:
        reason = None
    threshold = median * PARTNER_ACTIVITY_THRESHOLD_SHARE if reason is None else None
    flagged = frozenset(uid for uid in team_ids if threshold is not None
                        and uid in counts and counts[uid] <= threshold)
    if reason is None and not flagged:
        reason = "every_manager_active"
    return {"counts": counts, "flagged": flagged, "summary": {
        "managers": managers, "managers_with_profile": len(profiled),
        "league_median": median, "threshold": threshold,
        "flagged_managers": len(flagged), "applies": bool(flagged),
        "reason_not_applied": reason,
        "threshold_share": PARTNER_ACTIVITY_THRESHOLD_SHARE,
        "min_league_median": PARTNER_ACTIVITY_MIN_MEDIAN,
        "min_profiled_share": PARTNER_ACTIVITY_MIN_PROFILED_SHARE,
        "demotion": PARTNER_ACTIVITY_DEMOTION}}


def _shift(side, delta, adjustments):
    """A detached side with its support moved; the cached side is untouched."""
    support = dict(side["support"])
    support.update(score=incumbent._clip(support["score"] + delta, 0, 1),
                   range=[incumbent._clip(bound + delta, 0, 1) for bound in support["range"]],
                   revision_2_score=support["score"], revision_4_adjustments=adjustments)
    return {**side, "support": support}


class _Search(previous._Search):
    def __init__(self, *, partner_activity=None, **kwargs):
        super().__init__(**kwargs)
        self.partner_activity = (None if partner_activity is None
                                 else _league_activity(partner_activity, sorted(self.teams)))

    def _partner_activity(self, target):
        league = self.partner_activity
        fired = target in league["flagged"]
        return {**league["summary"], "counterparty_trades": league["counts"].get(target),
                "counterparty_has_profile": target in league["counts"], "fired": fired,
                "demotion": PARTNER_ACTIVITY_DEMOTION if fired else 0.0,
                "source": "public_completed_trades_this_league_year",
                "scope": "both_support_scores_order_only_inventory_kept"}

    def _pick_direction(self, give, receive):
        pays = any(self._position(p) == "PICK" for p in give)
        asks = any(self._position(p) == "PICK" for p in receive)
        return ("picks_both_ways" if pays and asks else "pays_picks" if pays
                else "asks_picks" if asks else "players_only")

    def _revision_4(self, card, data):
        """Record and apply the premium and best-asset rule to one eligible offer."""
        give, receive = tuple(card.give_player_ids), tuple(card.receive_player_ids)
        other = self.teams[card.target_user_id]
        outlook = other["outlook"]
        rate = PICK_PREMIUM.get(outlook, 0.0)
        # The other manager's side: what they give up is the viewer's receive.
        picks = sorted(p for p in receive if self._position(p) == "PICK")
        _, outgoing, incoming = self._package(receive, give, self.market)
        premium = rate * sum(self.market[p] for p in picks)
        tolerance = max(1 - self.floor, .05)
        perceived = outgoing + premium
        gain = (incoming - perceived) / max(incoming, perceived)
        before = data["counterparty"]["support"]["components"]["market_acceptability"]
        after = incumbent._clip(.5 + .5 * gain / tolerance, 0, 1)
        premium_delta = incumbent._WEIGHTS["market_acceptability"] * (after - before)

        top = max(self.market[p] for p in give + receive)
        best = sorted(p for p in give + receive if self.market[p] == top)
        consolidation = (len(give) > len(receive) and any(p in receive for p in best)
                         and all(self.market[p] < top for p in give))
        excepted = (consolidation and outlook in _PICK_WANTING
                    and all(self._position(p) == "PICK" for p in give))
        fired = consolidation and not excepted
        demotion = BEST_ASSET_DEMOTION if fired else 0.0

        data["revision_4"] = {"rules_version": RULES_VERSION,
            "pick_premium": {"counterparty_outlook": outlook,
                "outlook_source": other["outlook_source"], "rate": rate,
                "pick_ids": picks, "raw_pick_market": sum(self.market[p] for p in picks),
                "premium_value": premium, "applied": premium > 0,
                "market_acceptability_before": before, "market_acceptability_after": after,
                "support_delta": premium_delta,
                "scope": "counterparty_support_only_not_floor_or_overpay"},
            "best_asset_rule": {"consolidation_ask": consolidation, "fired": fired,
                "exception": "picks_to_rebuilding_or_tanking_team" if excepted else None,
                "best_asset_ids": best, "demotion": demotion,
                "scope": "both_support_scores_order_only_inventory_kept"},
            "pick_direction": self._pick_direction(give, receive),
            "tie_breaker": {"order": "pays_picks_before_players_before_asks_picks",
                "scope": "inside_existing_quality_tolerance",
                "quality_tolerance": incumbent._QUALITY_TOLERANCE}}
        counterparty = {"pick_premium": premium_delta, "best_asset_demotion": -demotion}
        viewer = {"pick_premium": 0.0, "best_asset_demotion": -demotion}
        activity = 0.0
        if self.partner_activity is not None:
            rule = self._partner_activity(card.target_user_id)
            activity = rule["demotion"]
            data["revision_4"].update(rules_version=RULES_VERSION_PARTNER_ACTIVITY,
                                      partner_activity=rule)
            counterparty["partner_activity_demotion"] = viewer["partner_activity_demotion"] = -activity
        # Both sides, as the best-asset rule: the weaker score falls by the
        # full amount, and presentment, which reads both, cannot undo it.
        data["counterparty"] = _shift(data["counterparty"], premium_delta - demotion - activity,
                                      counterparty)
        data["viewer"] = _shift(data["viewer"], -demotion - activity, viewer)

    def _decision(self, card, data, reason, eligible=False):
        # Before bilateral-1 builds the weaker/total support block from sides.
        if eligible and "viewer" in data and "counterparty" in data:
            self._revision_4(card, data)
        return super()._decision(card, data, reason, eligible)

    def _freeze_decision(self, card, data, reason, eligible):
        data["generator_version"] = VERSION
        if "construction" in data:
            data["construction"].update(policy="price_efficient_bilateral_portfolio_offer_learnings",
                                        coefficients=previous._WEIGHTS)
        return owner._Search._freeze_decision(self, card, data, reason, eligible)


class _GenerationSearch(_Search):
    def _freeze_decision(self, card, data, reason, eligible):
        if not eligible:
            return previous._GenerationRejection(reason)
        return super()._freeze_decision(card, data, reason, eligible)


def evaluate_bilateral_trades(cards, **kwargs):
    search = _Search(**kwargs)
    with search.ts._cfg_override(search.config), search.ts.stud_tax_override("market"):
        return search.evaluate_occurrences(cards)


def evaluate_bilateral_trade(card, **kwargs):
    return evaluate_bilateral_trades([card], **kwargs)[0]


def _quality_rank(cards, stats=None):
    """Bilateral-1's ranker plus the pay-picks key inside its comparable set.

    The comparable set is unchanged (leader +- the existing tolerance), so the
    new key can only choose among offers the old ranker already treated as
    equal in quality; diversity usage still decides first.
    """
    stats = Counter() if stats is None else stats
    qualities, identities, classes = {}, {}, {}
    for card in cards:
        data = card.owner_evaluation.as_dict()
        s = data["bilateral"]
        qualities[id(card)] = (-s["weaker_support"], -s["total_support"], -s["preference_fulfillment"],
            len(card.give_player_ids) + len(card.receive_player_ids), card.target_user_id,
            tuple(card.give_player_ids), tuple(card.receive_player_ids))
        identities[id(card)] = (("give", data["viewer"]["intent"]["sell_candidate"]),
            ("receive", data["viewer"]["intent"]["buy_target"]), ("partner", card.target_user_id))
        classes[id(card)] = _PICK_CLASS[data["revision_4"]["pick_direction"]]
    ordered = iter(sorted(cards, key=lambda c: qualities[id(c)]))
    pending = []
    for _ in range(32):
        card = next(ordered, None)
        if card is not None:
            pending.append(card)
    used = Counter()
    ranked = []
    while pending:
        leader = qualities[id(pending[0])]
        comparable = [i for i in range(min(32, len(pending)))
                      if qualities[id(pending[i])][0] <= leader[0] + incumbent._QUALITY_TOLERANCE
                      and qualities[id(pending[i])][1] <= leader[1] + 2 * incumbent._QUALITY_TOLERANCE]
        def usage(i):
            return sum(used[k] for k in identities[id(pending[i])])
        index = min(comparable, key=lambda i: (usage(i), classes[id(pending[i])], i))
        if index != min(comparable, key=lambda i: (usage(i), i)):
            stats["pay_picks_tie_breaks"] += 1
        card = pending.pop(index)
        used.update(identities[id(card)])
        ranked.append(card)
        card = next(ordered, None)
        if card is not None:
            pending.append(card)
    return ranked


def _rank(cards, stats=None):
    """Revision 2's ranker (term precedence over the quality order), new baseline."""
    baseline = _quality_rank(cards, stats)
    predecessors = previous.term_precedence(baseline, version=VERSION)
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
    stats = Counter()
    cards, raw = incumbent._generate_with_search(search,
        ranker=lambda survivors: _rank(survivors, stats), version=VERSION)
    report, counts, rules = raw.as_dict(), Counter(), Counter()
    for card in cards:
        evidence = card.owner_evaluation.as_dict()
        counts["efficient" if evidence["term_efficiency"]["efficient"] else "avoidable_alternative"] += 1
        counts["companion_comparisons"] += evidence["term_efficiency"]["audited_alternatives"]
        applied = evidence["revision_4"]
        rules["pick_premium_applied"] += applied["pick_premium"]["applied"]
        rules["best_asset_demoted"] += applied["best_asset_rule"]["fired"]
        rules["best_asset_excepted"] += applied["best_asset_rule"]["exception"] is not None
        rules["pick_direction:" + applied["pick_direction"]] += 1
        if "partner_activity" in applied:
            rules["partner_activity_demoted"] += applied["partner_activity"]["fired"]
    report.update(support_weights=previous._WEIGHTS, term_efficiency=dict(counts),
        term_ordering={"version": previous.TERM_ORDERING_VERSION,
                       "comparisons_per_family": previous.TERM_LOOKAHEAD,
                       "policy": "same_focal_precedence_preserve_inventory"},
        starter_evidence="dynasty_proxy_only_no_projected_points",
        revision_4={"rules_version": RULES_VERSION, "pick_premium": PICK_PREMIUM,
                    "best_asset_demotion": BEST_ASSET_DEMOTION,
                    "pay_picks_tie_breaks": stats["pay_picks_tie_breaks"], **dict(rules),
                    **({"rules_version": RULES_VERSION_PARTNER_ACTIVITY,
                        "partner_activity": search.partner_activity["summary"]}
                       if search.partner_activity is not None else {})},
        elapsed_seconds=round(perf_counter() - started, 6))
    return cards, owner.OwnerGenerationReport(owner._dump(report))
