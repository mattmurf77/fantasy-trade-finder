"""Preference-led focal construction and exact-package bilateral support.

The score is an interpretable launch policy, never an acceptance probability.
Personal tiers/order select intentions; the captured existing market reference
prices terms. The owner-v1 authority, package pricing and immutable proof types
are reused without changing its generator or accepting its surviving cards.
No database, server, provider or network access occurs in this module.
"""

from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import replace
import hashlib
import uuid

from . import trade_gen_owner as owner
from .ranking_service import ORDERED_TIERS, RankingService


ARM = "owner_v2_bilateral"
BILATERAL_GENERATOR_VERSION = VERSION = "owner-v2-bilateral-1"
_EPS = 1e-9
_WEIGHTS = {"preference_fulfillment": .45, "market_acceptability": .35,
            "team_plan": .20}
_QUALITY_TOLERANCE = .025
_YOUNG = {"QB": 27, "WR": 25, "TE": 25, "RB": 24}


def _clip(value, low=-1.0, high=1.0):
    return max(low, min(high, value))


def _percentile(value, ordered):
    return (bisect_left(ordered, value) + bisect_right(ordered, value)) / (2 * len(ordered))


def _identity(card):
    return (card.target_user_id, tuple(card.give_player_ids), tuple(card.receive_player_ids))


class _Search(owner._Search):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._decisions = {}
        self._core_cache = {}
        self._side_cache = {}
        self._plan_cache = {}
        self._features = {}
        self._tier_coordinates = {}
        # Full board universe: adding/removing an unrelated roster member must
        # not change a player's ordinal preference. Missing entries are still
        # explicitly unknown; fallback only supplies the ordering reference.
        universe = [p for p in self.seed if p in self.players and owner._finite(self.seed[p])]
        market_coordinates = {p: self._coordinate(p, self.seed[p])[0] for p in universe}
        market_order = sorted(market_coordinates.values())
        members = {m.user_id: m for m in self.league.members}
        for uid, team in self.teams.items():
            raw = kwargs["user_elo"] if uid == self.user_id else members[uid].elo_ratings
            sources = (kwargs.get("user_sources") if uid == self.user_id else
                       kwargs["opponent_sources"].get(uid) if kwargs.get("opponent_sources") is not None
                       else members[uid].confidence_sources)
            real = uid == self.user_id or members[uid].has_rankings
            known = set()
            for pid in universe:
                if not (owner._finite(raw.get(pid)) and
                        (sources.get(pid) in owner._PERSONAL_SOURCES if sources is not None else real)):
                    continue
                try:
                    value = self.ts.elo_to_value(raw[pid])
                except OverflowError:
                    continue
                if owner._finite(value) and value > 0:
                    known.add(pid)
            coordinates = {p: self._coordinate(p, raw[p] if p in known else self.seed[p])[0]
                           for p in universe}
            ordered = sorted(coordinates.values())
            team["has_personal_board"] = bool(known)
            team["board_snapshot_sha256"] = hashlib.sha256(owner._dump(
                {p: {"elo": raw[p], "source": sources.get(p) if sources is not None else "legacy"}
                 for p in sorted(known)}).encode()).hexdigest()
            for pid in self.market:
                personal = team["sources"][pid] != "consensus_fallback"
                personal_coordinate, personal_tier = self._coordinate(pid, team["tier_elos"][pid])
                market_coordinate, market_tier = self._coordinate(pid, self.seed[pid])
                pp = _percentile(coordinates[pid], ordered)
                mp = _percentile(market_coordinates[pid], market_order)
                # Tier steps and board ordinal movement share bounded units;
                # a tiny price denominator can never create unlimited appeal.
                direction = _clip(.7 * (personal_coordinate - market_coordinate) / 3
                                  + .3 * (pp - mp)) if personal else None
                self._features[uid, pid] = {"known": personal, "source": team["sources"][pid],
                    "direction": direction, "personal_tier": personal_tier if personal else None,
                    "market_tier": market_tier, "personal_percentile": pp if personal else None,
                    "market_percentile": mp}
        self.market_snapshot = {"source": "captured_existing_consensus", "new_blend_applied": False,
            "scoring_format": self.fmt, "seed_sha256": hashlib.sha256(owner._dump(
                {p: self.seed[p] for p in sorted(self.market)}).encode()).hexdigest(),
            "asset_values_sha256": hashlib.sha256(owner._dump(self.market).encode()).hexdigest()}
        self.market_snapshot["caller_provenance"] = self.teams[self.user_id]["preferences"].get(
            "market_source_snapshot", {})

    def _coordinate(self, pid, elo):
        key = pid, elo
        if key not in self._tier_coordinates:
            pos = self._position(pid)
            if pos == "PICK":
                # Pick Elo is an explicit common pick-equivalent value. Do not
                # use the fake position attached to generic-pick pseudo players.
                pos = "RB"
            if pos not in owner._POSITIONS:
                self._tier_coordinates[key] = (-1.0, None)
            else:
                tier = RankingService.tier_for_elo(elo, pos, self.fmt)
                if tier is None:
                    self._tier_coordinates[key] = (-1.0, None)
                else:
                    low, high = RankingService.tier_bands_for(pos, self.fmt)[tier]
                    within = _clip((elo - low) / max(high - low, 1), 0, 1)
                    self._tier_coordinates[key] = (len(ORDERED_TIERS) - 1 - ORDERED_TIERS.index(tier)
                                                   + within, tier)
        return self._tier_coordinates[key]

    def _plan_asset(self, team, pid):
        key = team["uid"], pid
        if key in self._plan_cache:
            return self._plan_cache[key]
        pos, age = self._position(pid), getattr(self.players[pid], "age", None)
        if team["outlook"] in ("jets", "rebuilder"):
            if pos == "PICK":
                fit = 1.0
            elif not owner._finite(age):
                fit = 0.0  # Missing age is not evidence of youth.
            elif pos == "RB":
                feature = self._features[team["uid"], pid]
                elite = feature["known"] and feature["personal_tier"] in ORDERED_TIERS[:3]
                fit = .4 if elite else (.05 if age <= _YOUNG["RB"] else -.8)
            else:
                fit = .7 if age <= _YOUNG.get(pos, 0) else -.45
            fit *= 1.0 if team["outlook"] == "jets" else .6
        else:
            lean = -.25 if pos == "PICK" else self.ts._now_lean(pos, age)
            fit = _clip(2 * owner._WINDOW_WEIGHT.get(team["outlook"], 0) * lean)
        self._plan_cache[key] = fit
        return fit

    def _asset_interest(self, team, pid, direction):
        key = pid, direction
        if key not in team["asset_interest"]:
            feature = self._features[team["uid"], pid]
            preference = direction * (feature["direction"] or 0)
            plan = direction * self._plan_asset(team, pid)
            pref, pos = team["preferences"], self._position(pid)
            declared = direction * .15 * ((pos in pref.get("acquire_positions", ()))
                                         - (pos in pref.get("trade_away_positions", ())))
            if direction > 0:
                declared += .3 * ((pid in pref.get("targets", ()))
                                 - (pid in pref.get("not_interested", ())))
            # Marginal usable roster evidence, never an instruction for a
            # tanking team to fill its immediate lineup holes.
            after = self._lineup(team["roster"] | {pid} if direction > 0 else team["roster"] - {pid}, team)
            need = sum(after[p] - team["lineup_before"][p] for p in owner._POSITIONS)
            need = _clip(need / max(self.market[pid], 1))
            weight = 0 if team["outlook"] == "jets" else .025 if team["outlook"] == "rebuilder" else .15
            team["asset_interest"][key] = preference + .3 * plan + weight * need + declared
        return team["asset_interest"][key]

    def _owner(self, team, give, receive):
        key = team["uid"], tuple(sorted(give)), tuple(sorted(receive))
        if key in self._side_cache:
            return self._side_cache[key]
        result = super()._owner(team, give, receive)
        _, outgoing, incoming = self._package(give, receive, self.market)
        gross = sum(self.market[p] for p in give + receive)
        market_gain = (incoming - outgoing) / max(incoming, outgoing)
        weighted_preference = sum(sign * self.market[p] * (self._features[team["uid"], p]["direction"] or 0)
                                  for sign, ids in ((1, receive), (-1, give)) for p in ids) / gross
        focal_in, focal_out = self._head(receive, self.market), self._head(give, self.market)
        buy = self._features[team["uid"], focal_in]["direction"]
        sell = self._features[team["uid"], focal_out]["direction"]
        focal = max(buy or 0, -(sell or 0), 0)
        pref = team["preferences"]
        declared = (focal_in in pref.get("targets", ())
                    or self._position(focal_in) in pref.get("acquire_positions", ())
                    or self._position(focal_out) in pref.get("trade_away_positions", ()))
        explicit = team["uid"] == self.user_id and (bool(set(give) & set(self.give_pins))
                                                    or bool(set(receive) & set(self.recv_pins)))
        plan_shift = sum(sign * self.market[p] * self._plan_asset(team, p)
                         for sign, ids in ((1, receive), (-1, give)) for p in ids) / gross
        need = _clip(result["need_utility"] * 4)
        plan_gain = _clip(plan_shift + need)
        personal_intent = focal >= .025 and weighted_preference >= -.025
        declared_plan = team["outlook_source"] == "declared" and plan_gain >= .10
        path = ("explicit_selection" if explicit else "personal_board" if personal_intent else
                "declared_intent" if declared or declared_plan else
                "missing_board" if not team["has_personal_board"] else "unfulfilled")
        qualified = path != "unfulfilled" and (path != "missing_board" or plan_gain > .01 or market_gain > .01)
        # Fairness remains a price ceiling; stronger liking changes support,
        # never increases the consideration or relaxes the account threshold.
        tolerance = max(1 - self.floor, .05)
        components = {"preference_fulfillment": _clip(.5 + weighted_preference, 0, 1),
                      "market_acceptability": _clip(.5 + .5 * market_gain / tolerance, 0, 1),
                      "team_plan": _clip(.5 + .5 * plan_gain, 0, 1)}
        support = sum(_WEIGHTS[k] * components[k] for k in _WEIGHTS)
        known = sum(self._features[team["uid"], p]["known"] for p in give + receive)
        state = "unknown" if not known else "known" if known == len(give + receive) else "partial"
        uncertainty = .12 if state == "unknown" else .06 if state == "partial" else .025
        if team["outlook_source"] != "declared":
            uncertainty += .025
        benefits = []
        if personal_intent:
            benefits.append("personal_preference")
        if explicit or declared:
            benefits.append("declared_intent")
        if plan_shift > .01:
            benefits.append("outlook")
        if need > .01:
            benefits.append("usable_roster_improvement")
        if market_gain > .01:
            benefits.append("market_terms")
        # Unknown/neutral evidence remains plausible at fair market terms;
        # this is explicitly not a claim that another manager will accept.
        if not benefits:
            benefits.append("plausible_market_terms")
        result.update(support={"score": support, "range": [_clip(support - uncertainty, 0, 1),
                      _clip(support + uncertainty, 0, 1)], "components": components, "weights": _WEIGHTS},
            intent={"qualified": qualified, "path": path, "focal_preference": focal,
                    "net_preference": weighted_preference, "buy_target": focal_in,
                    "sell_candidate": focal_out, "declared_match": bool(declared)},
            preference_evidence={"state": state, "known_assets": known, "assets": len(give + receive),
                                 "board_sha256": team["board_snapshot_sha256"]},
            team_plan_evidence={"next_draft_year": pref.get("next_draft_year"),
                "own_next_draft_pick_ids": list(pref.get("own_next_draft_pick_ids") or ()),
                "expired_pick_ids": list(pref.get("expired_pick_ids") or ()),
                "missing_age_ids": [p for p in give + receive if self._position(p) != "PICK"
                                    and not owner._finite(getattr(self.players[p], "age", None))]},
            market_gain_fraction=market_gain, team_plan_gain=plan_gain,
            # Superclass eligibility only needs a positive utility. The
            # original fields above remain available for captured diagnostics.
            utility=support - .35, benefits=benefits,
            personal_loss_rescued=result["personal_gain_fraction"] < -_EPS and plan_gain > .1)
        self._side_cache[key] = result
        return result

    def _core(self, card, *, partial=False):
        key = _identity(card), partial, card.league_id, card.proposing_user_id
        if key in self._core_cache:
            return self._core_cache[key]
        decision = super().evaluate(card, partial=partial)
        self._core_cache[key] = decision
        return decision

    def _decision(self, card, data, reason, eligible=False):
        data.update(generator=ARM, generator_version=VERSION)
        if "market" in data:
            data["market"]["source_snapshot"] = self.market_snapshot
        if eligible:
            give, receive = tuple(card.give_player_ids), tuple(card.receive_player_ids)
            viewer, other = data["viewer"], data["counterparty"]
            data["bilateral"] = {"score_kind": "interpretable_support_not_probability",
                "weaker_support": min(viewer["support"]["score"], other["support"]["score"]),
                "total_support": viewer["support"]["score"] + other["support"]["score"],
                "preference_fulfillment": viewer["intent"]["net_preference"] + other["intent"]["net_preference"],
                "diversity_tolerance": _QUALITY_TOLERANCE}
            data["construction"].update(policy="matched_focal_minimal_consideration", coefficients=_WEIGHTS)
            data["construction"].pop("utility_coefficients", None)
            if not viewer["intent"]["qualified"]:
                reason = "viewer_intent_unfulfilled"
            for team, outgoing, incoming, side, selected in (
                    (self.teams[self.user_id], give, receive, viewer, self.give_pins),
                    (self.teams[card.target_user_id], receive, give, other, ())):
                pref = team["preferences"]
                if set(outgoing + incoming) & set(pref.get("expired_pick_ids", ())):
                    reason = "expired_draft_asset"
                if side["intent"]["net_preference"] < -.15 and side["team_plan_gain"] < .20:
                    reason = "known_preference_harm"
                if team["outlook"] != "jets":
                    continue
                if (set(outgoing) & set(pref.get("own_next_draft_pick_ids", ()))) - set(selected):
                    reason = "tanking_own_next_draft_pick"
                for pid in incoming:
                    if self._position(pid) != "RB":
                        continue
                    feature, age = self._features[team["uid"], pid], getattr(self.players[pid], "age", None)
                    elite = feature["known"] and feature["personal_tier"] in ORDERED_TIERS[:3]
                    prospect = (owner._finite(age) and age <= _YOUNG["RB"] and feature["known"]
                                and (feature["direction"] or 0) >= .025 and side["market_gain_fraction"] >= .05)
                    selected_in = team["uid"] == self.user_id and pid in self.recv_pins
                    if not (elite or prospect or selected_in):
                        reason = "tanking_rb_without_long_term_exception"
                for pid in outgoing:
                    age = getattr(self.players[pid], "age", None)
                    feature = self._features[team["uid"], pid]
                    if (self._position(pid) in ("WR", "TE", "QB") and owner._finite(age)
                            and age <= _YOUNG[self._position(pid)] and feature["known"]
                            and (feature["direction"] or 0) >= .025 and pid not in selected
                            and side["intent"]["net_preference"] < -.025):
                        reason = "tanking_favored_young_asset"
            for asset in data["assets"]:
                asset["viewer_preference"] = self._features[self.user_id, asset["id"]]
                asset["counterparty_preference"] = self._features[card.target_user_id, asset["id"]]
        return super()._decision(card, data, reason, reason == "eligible")

    def evaluate(self, card, *, partial=False):
        result = self._core(card, partial=partial)
        if result.eligible:
            # A simpler valid offer dominates unnecessary compensation. Pinned
            # assets cannot be removed; distinct useful companions survive.
            data = result.as_dict()
            for side, pins in (("give_player_ids", self.give_pins), ("receive_player_ids", self.recv_pins)):
                ids = getattr(card, side)
                if len(ids) <= 1:
                    continue
                for pid in ids:
                    if pid in pins:
                        continue
                    simple = replace(card, **{side: [p for p in ids if p != pid]})
                    proof = self._core(simple, partial=partial)
                    if not proof.eligible:
                        continue
                    smaller = proof.as_dict()
                    supports = [data[k]["support"]["score"] for k in ("viewer", "counterparty")]
                    prior = [smaller[k]["support"]["score"] for k in ("viewer", "counterparty")]
                    dominated = all(a <= b + _EPS for a, b in zip(supports, prior))
                    weak_gain = min(supports) - min(prior)
                    needless_cost = weak_gain < .025 and any(a < b - .015 for a, b in zip(supports, prior))
                    if dominated or needless_cost:
                        data.update(eligible=False, reason="unnecessary_compensation")
                        result = replace(result, eligible=False, reason=data["reason"], snapshot_json=owner._dump(data))
                        break
                if not result.eligible:
                    break
        self._decisions[_identity(card)] = result
        return result

    def candidates(self, member, *, partial=False):
        viewer, other = self.teams[self.user_id], self.teams[member.user_id]
        give_pool = list(dict.fromkeys([p for p in self.give_pins if p in viewer["roster"]] + self._pool(viewer, other)))
        receive_pool = list(dict.fromkeys([p for p in self.recv_pins if p in other["roster"]] + self._pool(other, viewer)))
        self.pools[member.user_id] = {"give": give_pool, "receive": receive_pool}
        def anchors(pool, pins, exact=False):
            if exact:
                return [pins] if pins else []
            if pins:
                return [(p,) for p in pins if p in pool] if partial else [pins]
            return [(p,) for p in pool]
        focal = [(g, r) for g in anchors(give_pool, self.give_pins, self.exact_give)
                 for r in anchors(receive_pool, self.recv_pins)]
        def appeal(pair):
            give, receive = pair
            if any(p not in self.market for p in give + receive):
                return -1000.0
            a = sum(self._asset_interest(viewer, p, 1) + self._asset_interest(other, p, -1) for p in receive)
            b = sum(self._asset_interest(other, p, 1) + self._asset_interest(viewer, p, -1) for p in give)
            return min(a, b) + .25 * (a + b)
        focal.sort(key=lambda pair: (-appeal(pair), pair))
        seen, expansion = set(), []
        def make(give, receive):
            return self.ts.TradeCard("", self.league.league_id, self.user_id, member.user_id,
                                    member.username, list(give), list(receive), 0, 0, 0)
        # Each simpler match is tested before allocating budget to companions.
        for give, receive in focal:
            card = make(give, receive)
            signature = (frozenset(give), frozenset(receive))
            if signature in seen:
                continue
            seen.add(signature)
            yield card
            proof = self._decisions.get(_identity(card))
            if proof is None or any(p not in self.market for p in give + receive):
                continue
            # Authority/intent failures are not cured by an incidental filler.
            if not proof.eligible and proof.reason not in (
                    "market_floor", "market_overpay", "viewer_no_benefit", "counterparty_no_benefit",
                    "known_preference_harm", "tanking_rb_without_long_term_exception"):
                continue
            for side, pool in (("give", give_pool), ("receive", receive_pool)):
                if side == "give" and self.exact_give:
                    continue
                if len(give if side == "give" else receive) >= 2:
                    continue
                # Organic packages stop at 2x1/1x2. Explicit larger anchors
                # retain their requested shape and may find consideration.
                if len(give) + len(receive) >= 3 and not (len(self.give_pins) > 1 or len(self.recv_pins) > 1):
                    continue
                recipient = other if side == "give" else viewer
                sender = viewer if side == "give" else other
                for pid in pool:
                    if pid in give + receive:
                        continue
                    g, r = (give + (pid,), receive) if side == "give" else (give, receive + (pid,))
                    # Companion priority combines the weaker side's intent and
                    # market gap; strong liking never raises an asking price.
                    joint = self._asset_interest(recipient, pid, 1) + self._asset_interest(sender, pid, -1)
                    gap = abs(sum(self.market[p] for p in g) - sum(self.market[p] for p in r))
                    cost = gap / max(sum(self.market[p] for p in g + r), 1)
                    expansion.append((joint - cost, g, r))
        expansion.sort(key=lambda item: (-item[0], item[1], item[2]))
        for _, give, receive in expansion:
            signature = frozenset(give), frozenset(receive)
            if signature not in seen:
                seen.add(signature)
                yield make(give, receive)


def evaluate_bilateral_trades(cards, **kwargs):
    """Revalidate immutable exact occurrences against the captured new policy."""
    search = _Search(**kwargs)
    with search.ts._cfg_override(search.config), search.ts.stud_tax_override("market"):
        return [search.evaluate(c, partial=owner._authenticated_partial(c, search)) for c in cards]


def evaluate_bilateral_trade(card, **kwargs):
    return evaluate_bilateral_trades([card], **kwargs)[0]


def _rank(cards):
    qualities, identities = {}, {}
    for card in cards:
        data = card.owner_evaluation.as_dict()
        s = data["bilateral"]
        qualities[id(card)] = (-s["weaker_support"], -s["total_support"], -s["preference_fulfillment"],
            len(card.give_player_ids) + len(card.receive_player_ids), card.target_user_id,
            tuple(card.give_player_ids), tuple(card.receive_player_ids))
        identities[id(card)] = (("give", data["viewer"]["intent"]["sell_candidate"]),
            ("receive", data["viewer"]["intent"]["buy_target"]), ("partner", card.target_user_id))
    ordered = iter(sorted(cards, key=lambda c: qualities[id(c)]))
    # Fixed lookahead makes diversity O(32*N), avoiding quadratic list pops
    # or repeated JSON decoding for thousands of uncapped offers.
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
                      if qualities[id(pending[i])][0] <= leader[0] + _QUALITY_TOLERANCE
                      and qualities[id(pending[i])][1] <= leader[1] + 2 * _QUALITY_TOLERANCE]
        index = min(comparable, key=lambda i: (sum(used[k] for k in identities[id(pending[i])]), i))
        card = pending.pop(index)
        used.update(identities[id(card)])
        ranked.append(card)
        card = next(ordered, None)
        if card is not None:
            pending.append(card)
    return ranked


def generate_bilateral_trades(**kwargs):
    """Build focal bilateral matches under computational, never output, caps."""
    search = _Search(**kwargs)
    report = {"generator": ARM, "generator_version": VERSION, "evaluated": 0,
              "partial_search": False, "budget_exhausted": False,
              "limits": {"pool": search.pool_size, "per_pair": search.pair_budget, "total": search.total_budget},
              "max_cards_ignored": search.max_cards is not None, "market_source_snapshot": search.market_snapshot,
              "score_kind": "interpretable_support_not_probability", "support_weights": _WEIGHTS}
    rejected, counts, survivors, seen = Counter(), Counter(), [], set()
    with search.ts._cfg_override(search.config), search.ts.stud_tax_override("market"):
        for partial in (False, True):
            if partial:
                if survivors or not ((len(search.give_pins) > 1 and not search.exact_give) or len(search.recv_pins) > 1):
                    break
                report["partial_search"] = True
            streams = {m.user_id: iter(search.candidates(m, partial=partial)) for m in search.members}
            while streams and report["evaluated"] < search.total_budget:
                for uid in list(streams):
                    if counts[uid] >= search.pair_budget or report["evaluated"] >= search.total_budget:
                        streams.pop(uid)
                        report["budget_exhausted"] = True
                        continue
                    card = next(streams[uid], None)
                    if card is None:
                        streams.pop(uid)
                        continue
                    counts[uid] += 1
                    report["evaluated"] += 1
                    proof = search.evaluate(card, partial=partial)
                    if not proof.eligible:
                        rejected[proof.reason] += 1
                        continue
                    signature = uid, frozenset(card.give_player_ids), frozenset(card.receive_player_ids)
                    if signature in seen:
                        continue
                    seen.add(signature)
                    data = proof.as_dict()
                    card.owner_evaluation = proof
                    card.owner_group, card.owner_groups = data["direction"], tuple(data["compatible_groups"])
                    card.give_value, card.receive_value = data["market"]["give"], data["market"]["receive"]
                    card.fairness_score = data["market"]["ratio"]
                    card.trade_id = "bilateral_" + uuid.uuid4().hex
                    card.basis = "consensus" if data["viewer"]["preference_evidence"]["state"] == "unknown" else "divergence"
                    card.lane = "window" if data["viewer"]["team_plan_gain"] > .01 else "value"
                    card.reasons = ["Closest alternative — some selected assets could not be included."] if partial else []
                    if not data["construction"]["small"]:
                        card.reasons.append("Larger package to include your selected assets.")
                    if data["counterparty"]["preference_evidence"]["state"] == "unknown":
                        card.reasons.append("Other manager’s preferences are unknown; fit uses market and team context.")
                    # Private ranking/tier values never enter public rationale.
                    card.match_context = {"owner_benefits": data["viewer"]["benefits"],
                        "counterparty_benefits": data["counterparty"]["benefits"],
                        "counterparty_preference_evidence": data["counterparty"]["preference_evidence"]["state"],
                        "support_kind": "interpretable_support_not_probability"}
                    survivors.append(card)
            if streams:
                report["budget_exhausted"] = True
        emitted = _rank(survivors)
        for index, card in enumerate(emitted):
            # Presentation rank, not a probability. Detailed support lives in
            # immutable private evidence and survives final revalidation.
            card.composite_score = card.mismatch_score = float(len(emitted) - index)
    report.update(rejections=dict(rejected), pools=search.pools, emitted=len(emitted), shortage=not emitted,
        small_supply=sum(c.owner_evaluation.as_dict()["construction"]["small"] for c in emitted),
        per_opponent={m.user_id: {"evaluated": counts[m.user_id],
            "emitted": sum(c.target_user_id == m.user_id for c in emitted)} for m in search.members},
        config={k: v for k, v in search.config.items() if k.startswith(("owner_", "package_", "crown_", "elo_value_", "max_overpay_"))
                or k in ("overpay_adjusted", "market_floor_absolute")})
    return emitted, owner.OwnerGenerationReport(owner._dump(report))
