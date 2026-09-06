"""Owner-v1: bounded, small-package construction from both owners' interests.

Scope: docs/plans/owner-engine-challenger/scope.md. This is a separate
generator, not a reranker or a wrapper around a legacy generator's survivors.
Raw personal entries select opportunities; established market package pricing
sets terms. Outlook/usable roster improvement can justify a bounded dynasty
loss. The utility coefficients are provisional, versioned experimental choices,
not calibrated acceptance probabilities or projected fantasy points.

No database, provider, server, or direct flag reads. Callers capture the
request and boards. Shared package/tier helpers retain the shipped calculator
currency, with stud adjustment always in market mode. Evidence is immutable
and private: never serialize another manager's board to the public card.
"""

from __future__ import annotations

import json
import math
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations, zip_longest


VERSION = "owner-v1"
SCHEMA_VERSION = 1
ARM = "owner_v1"
_POSITIONS = ("QB", "RB", "WR", "TE")
_PERSONAL_SOURCES = frozenset(("explicit", "votes", "cross_format", "legacy"))
_OUTLOOKS = {"all_in": "championship", "all-in": "championship",
             "allin": "championship", "contending": "contender",
             "rebuilding": "rebuilder", "tanking": "jets"}
_WINDOW_WEIGHT = {"championship": 1.0, "contender": .6,
                  "rebuilder": -.6, "jets": -1.0}
_EPS = 1e-9
_LIMITS = {"owner_pool_size": 16, "owner_pair_budget": 4096,
           "owner_total_budget": 60000}


@dataclass(frozen=True)
class OwnerDecisionContext:
    """Frozen decision plus exact-package binding, safe to deep-copy.

    JSON is stored as a string so even nested board/context structures cannot
    be changed after eligibility. ``as_dict`` returns a detached PRIVATE copy.
    """
    eligible: bool
    reason: str
    league_id: str
    user_id: str
    target_user_id: str
    give_ids: tuple[str, ...]
    receive_ids: tuple[str, ...]
    snapshot_json: str

    def as_dict(self):
        return json.loads(self.snapshot_json)

    @property
    def effective_floor(self):
        return self.as_dict().get("market", {}).get("effective_floor")

    def matches(self, card):
        if not (self.eligible and self.league_id == card.league_id
                and self.user_id == card.proposing_user_id
                and self.target_user_id == card.target_user_id
                and self.give_ids == tuple(card.give_player_ids)
                and self.receive_ids == tuple(card.receive_player_ids)):
            return False
        market = self.as_dict()["market"]
        return all(isinstance(actual, (int, float)) and not isinstance(actual, bool)
                   and math.isfinite(actual) and abs(actual - expected) <= _EPS
                   for actual, expected in (
                       (card.give_value, market["give"]),
                       (card.receive_value, market["receive"]),
                       (card.fairness_score, market["ratio"])))


@dataclass(frozen=True)
class OwnerGenerationReport:
    snapshot_json: str

    def as_dict(self):
        return json.loads(self.snapshot_json)

    def diagnostics(self):
        return self.as_dict()


def _finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _ids(values):
    return tuple(dict.fromkeys(str(v) for v in (values or ())))


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class _Search:
    def __init__(self, *, players, league, user_id, user_roster, user_elo,
                 seed_elo, scoring_format="1qb_ppr", fairness_threshold=.5,
                 outlook=None, opponent_outlooks=None, inferred_outlooks=None, user_sources=None,
                 opponent_sources=None, manager_preferences=None,
                 acquire_positions=None, trade_away_positions=None,
                 avoid_positions=None, pinned_give_players=None,
                 pinned_receive_players=None, exact_give=False,
                 opponent_user_id=None, trade_intent=None, swap_positions=None,
                 lateral_scope=None, past_decision_keys=None,
                 exclusion_keys=None, max_cards=None, config=None):
        from . import trade_service as ts
        self.ts = ts
        self.players, self.league, self.user_id = players, league, user_id
        self.fmt = scoring_format
        self.config = {key: ts._c(key) for key in ts._DEFAULT_CFG}
        self.config.update(_LIMITS)
        self.config.update({key: ts._cfg.get(key, default) for key, default in _LIMITS.items()})
        self.config.update(config or {})
        self.pool_size = self._limit("owner_pool_size", 4, 32)
        self.pair_budget = self._limit("owner_pair_budget", 1, 16384)
        self.total_budget = self._limit("owner_total_budget", 1, 120000)
        self.requested_floor = fairness_threshold
        self.valid_floor = _finite(fairness_threshold) and 0 <= fairness_threshold <= 1
        self.floor = max(float(fairness_threshold), self.config["market_floor_absolute"]) if self.valid_floor else 1.0
        self.seed = dict(seed_elo)
        self.market = {}
        with ts._cfg_override(self.config):
            cval = ts.make_consensus_value_fn(self.seed, players)
            for pid in set(user_roster).union(*(set(m.roster) for m in league.members)):
                if pid in players and _finite(seed_elo.get(pid)):
                    value = cval(pid)
                    if _finite(value) and value > 0:
                        self.market[pid] = value
        self.give_pins = _ids(pinned_give_players)
        self.recv_pins = _ids(pinned_receive_players)
        self.exact_give = bool(exact_give)
        self.opponent_id = opponent_user_id
        self.intent = trade_intent
        self.swap = frozenset(swap_positions or ())
        self.avoid = frozenset(avoid_positions or ())
        self.lateral_scope = lateral_scope
        self.max_cards = max_cards
        self.exclusions = set(past_decision_keys or ()) | set(exclusion_keys or ())
        prefs = manager_preferences or {}
        viewer_prefs = dict(prefs.get(user_id) or {})
        if (inferred_outlooks or {}).get(user_id) is not None:
            viewer_prefs["inferred_outlook"] = inferred_outlooks[user_id]
        if acquire_positions is not None:
            viewer_prefs["acquire_positions"] = list(acquire_positions)
        if trade_away_positions is not None:
            viewer_prefs["trade_away_positions"] = list(trade_away_positions)
        self.teams = {}
        self.teams[user_id] = self._team(user_id, user_roster, user_elo,
            user_sources, viewer_prefs, outlook, True)
        for member in league.members:
            if member.user_id != user_id:
                sources = ((opponent_sources or {}).get(member.user_id)
                           if opponent_sources is not None else member.confidence_sources)
                member_prefs = dict(prefs.get(member.user_id) or {})
                if (inferred_outlooks or {}).get(member.user_id) is not None:
                    member_prefs["inferred_outlook"] = inferred_outlooks[member.user_id]
                self.teams[member.user_id] = self._team(member.user_id, member.roster,
                    member.elo_ratings, sources, member_prefs,
                    (opponent_outlooks or {}).get(member.user_id), member.has_rankings)
        self.members = sorted((m for m in league.members if m.user_id != user_id
            and m.roster and (not opponent_user_id or m.user_id == opponent_user_id)),
            key=lambda m: m.user_id)
        self.pools = {}

    def _limit(self, name, low, high):
        value = self.config.get(name)
        return max(low, min(high, int(value))) if _finite(value) else _LIMITS[name]

    def _team(self, uid, roster, board, sources, prefs, outlook, real_board):
        values, provenance, tier_elos = {}, {}, {}
        with self.ts._cfg_override(self.config):
            for pid, market in self.market.items():
                source = sources.get(pid) if sources is not None else ("legacy" if real_board else "seed")
                raw = board.get(pid)
                personal = source in _PERSONAL_SOURCES and _finite(raw)
                try:
                    value = self.ts.elo_to_value(raw) if personal else market
                except OverflowError:
                    value, personal = market, False
                if not _finite(value) or value <= 0:
                    value, personal = market, False
                values[pid] = value
                tier_elos[pid] = raw if personal else self.seed[pid]
                provenance[pid] = source if personal else "consensus_fallback"
        selected_outlook = outlook if outlook is not None else prefs.get("team_outlook")
        source = "declared" if selected_outlook is not None else "inferred"
        if selected_outlook is None:
            selected_outlook = prefs.get("inferred_outlook")
        if selected_outlook is None:
            with self.ts._cfg_override(self.config):
                selected_outlook = self.ts.infer_team_outlook(
                    list(roster), self.players,
                    num_teams=len({self.user_id, *(m.user_id for m in self.league.members)}))[0]
        selected_outlook = _OUTLOOKS.get(selected_outlook, selected_outlook)
        starts = {"QB": 2 if self.fmt.startswith(("sf", "2qb")) else 1, "RB": 2, "WR": 3, "TE": 1}
        for pos, count in (prefs.get("starter_requirements") or {}).items():
            if pos in starts and type(count) is int and 0 <= count <= 12:
                starts[pos] = count
        from .trade_roster import ELIGIBILITY
        requested_slots = prefs.get("starter_slots")
        unsupported = [s for s in (requested_slots or ()) if s not in ELIGIBILITY]
        valid_slots = requested_slots is not None and bool(requested_slots) and not unsupported
        slots = tuple(requested_slots) if valid_slots else tuple(p for p, n in starts.items() for _ in range(n))
        capacity = prefs.get("roster_capacity")
        capacity = capacity if type(capacity) is int and capacity >= 0 else None
        team = {"uid": uid, "roster": frozenset(roster), "values": values,
                "sources": provenance, "tier_elos": tier_elos, "outlook": selected_outlook,
                "outlook_source": source, "preferences": dict(prefs), "starts": starts,
                "slots": slots, "lineup_source": prefs.get("lineup_source", "observed") if valid_slots else "estimated",
                "unsupported_slots": unsupported, "capacity": capacity,
                "inactive": frozenset(prefs.get("inactive_ids") or ())}
        team["unresolved_roster_assets"] = sorted(p for p in roster if p not in self.market)
        team["lineup_before"] = self._lineup(team["roster"], team)
        team["asset_interest"] = {}
        return team

    def _position(self, pid):
        player = self.players.get(pid)
        return "PICK" if self.ts.is_pick_asset(player) else getattr(player, "position", None)

    def _lineup(self, roster, team):
        # A transparent market-based usable-depth proxy, NOT fantasy points.
        # Only the best N and ONE 15%-weighted backup at each position count;
        # arbitrary bench churn cannot earn a need benefit.
        from .trade_roster import Asset, ELIGIBILITY, UNAVAILABLE, assign
        usable = []
        for pid in roster:
            pos = self._position(pid)
            if pos in _POSITIONS and pid in self.market and pid not in team["inactive"]:
                player = self.players[pid]
                status = str(getattr(player, "injury_status", "") or "").upper()
                if status not in UNAVAILABLE:
                    usable.append(Asset(pid, frozenset([pos]), self.market[pid]
                        * self.ts.age_now_mult(pos, getattr(player, "age", None))))
        assignment = {pid for pid in assign(team["slots"], usable) if pid}
        result = {pos: 0.0 for pos in _POSITIONS}
        bench = defaultdict(list)
        for asset in usable:
            pos = self._position(asset.id)
            if asset.id in assignment:
                result[pos] += asset.value
            else:
                bench[pos].append(asset.value)
        for pos, vals in bench.items():
            if any(pos in ELIGIBILITY[s] for s in team["slots"]):
                result[pos] += .15 * max(vals)
        return result

    def _package(self, give, receive, values):
        return self.ts.price_consensus_package(list(give), list(receive), value_of=values.__getitem__)

    def _owner(self, team, give, receive):
        _, outgoing, incoming = self._package(give, receive, team["values"])
        personal_gain = (incoming - outgoing) / max(incoming, outgoing)
        denominator = sum(self.market[p] for p in give + receive)
        window = _WINDOW_WEIGHT.get(team["outlook"], 0.0)
        raw_shift = 0.0
        for direction, ids in ((1, receive), (-1, give)):
            for pid in ids:
                p = self.players[pid]
                lean = (-.25 if self._position(pid) == "PICK" else
                        self.ts._now_lean(self._position(pid), getattr(p, "age", None)))
                raw_shift += direction * self.market[pid] * lean
        outlook_utility = .5 * window * raw_shift / denominator
        after = self._lineup((team["roster"] - set(give)) | set(receive), team)
        deltas = {pos: after[pos] - team["lineup_before"][pos] for pos in _POSITIONS}
        need_weight = 0.0 if team["outlook"] == "jets" else (.05 if team["outlook"] == "rebuilder" else .25)
        need_utility = need_weight * sum(deltas.values()) / denominator
        utility = personal_gain + outlook_utility + need_utility
        benefit = []
        if personal_gain > _EPS:
            benefit.append("personal_preference")
        if outlook_utility > _EPS:
            benefit.append("outlook")
        if need_utility > _EPS:
            benefit.append("usable_roster_improvement")
        return {"outgoing_personal": outgoing, "incoming_personal": incoming,
            "personal_gain_fraction": personal_gain, "outlook": team["outlook"],
            "outlook_source": team["outlook_source"], "outlook_utility": outlook_utility,
            "need_utility": need_utility, "usable_depth_delta": deltas,
            "usable_depth_before": team["lineup_before"], "usable_depth_after": after,
            "roster_ids": sorted(team["roster"]), "inactive_ids": sorted(team["inactive"]),
            "preferences": {key: list(team["preferences"].get(key) or ()) for key in
                ("acquire_positions", "trade_away_positions", "untouchables", "targets", "not_interested")},
            "starter_requirements": team["starts"], "lineup_proxy": "market_usable_depth_v1",
            "starter_slots": team["slots"], "lineup_source": team["lineup_source"],
            "unsupported_slots": team["unsupported_slots"], "roster_capacity": team["capacity"],
            "unresolved_roster_assets": team["unresolved_roster_assets"],
            "legality": "separate_final_roster_check_required",
            "utility": utility, "benefits": benefit,
            "personal_loss_rescued": personal_gain < -_EPS and utility > _EPS}

    def _head(self, ids, values):
        return max(ids, key=lambda pid: (values[pid], pid))

    def _direction(self, give, receive):
        from .ranking_service import ORDERED_TIERS, RankingService
        board = self.teams[self.user_id]["values"]
        def tier(pid):
            elo = self.teams[self.user_id]["tier_elos"][pid]
            name = RankingService.tier_for_elo(elo, self._position(pid), self.fmt)
            return ORDERED_TIERS.index(name) if name in ORDERED_TIERS else len(ORDERED_TIERS)
        g = min(give, key=lambda pid: (tier(pid), -board[pid], pid))
        r = min(receive, key=lambda pid: (tier(pid), -board[pid], pid))
        gt, rt = tier(g), tier(r)
        # Same broad tier may still contain a meaningful personal upgrade.
        direction = ("upgrade" if rt < gt or (rt == gt and board[r] > board[g] * 1.05) else
                     "downgrade" if gt < rt or (rt == gt and board[g] > board[r] * 1.05) else "lateral")
        return direction, {"give": gt, "receive": rt, "basis": "personal_with_consensus_fallback"}

    def _selection(self, give, receive):
        out = {}
        for name, wanted, actual in (("give", self.give_pins, give), ("receive", self.recv_pins, receive)):
            out[name] = {"requested": list(wanted), "included": [p for p in wanted if p in actual],
                         "omitted": [p for p in wanted if p not in actual]}
        out["coverage"] = "partial" if any(out[s]["omitted"] for s in ("give", "receive")) else "full"
        out["exact_give"] = self.exact_give
        return out

    def evaluate(self, card, *, partial=False):
        give, receive = tuple(card.give_player_ids), tuple(card.receive_player_ids)
        target = card.target_user_id
        data = {"schema_version": SCHEMA_VERSION, "generator": ARM, "generator_version": VERSION,
                "selection": self._selection(give, receive)}
        def finish(reason, eligible=False):
            data.update(eligible=eligible, reason=reason)
            return OwnerDecisionContext(eligible, reason, self.league.league_id, self.user_id,
                target, give, receive, _dump(data))
        if not self.valid_floor:
            return finish("invalid_fairness")
        if (card.league_id != self.league.league_id or card.proposing_user_id != self.user_id
                or target not in self.teams or target == self.user_id
                or (self.opponent_id and target != self.opponent_id)):
            return finish("invalid_partner")
        if (not give or not receive or len(set(give)) != len(give)
                or len(set(receive)) != len(receive) or set(give) & set(receive)
                or any(pid not in self.market for pid in give + receive)):
            return finish("invalid_assets")
        viewer, opponent = self.teams[self.user_id], self.teams[target]
        if (not set(give) <= viewer["roster"] or not set(receive) <= opponent["roster"]
                or set(receive) & viewer["roster"] or set(give) & opponent["roster"]):
            return finish("assets_not_owned")
        if self.exact_give and give != self.give_pins:
            return finish("exact_give_mismatch")
        for pins, ids in ((self.give_pins, give), (self.recv_pins, receive)):
            if pins and (not set(pins) & set(ids) if partial else not set(pins) <= set(ids)):
                return finish("selection_mismatch")
        if any(self._position(p) in self.avoid for p in receive):
            return finish("avoided_position")
        if (frozenset(give), frozenset(receive)) in self.exclusions:
            return finish("previous_disposition")
        if (len(give), len(receive)) not in ((1, 1), (1, 2), (2, 1)) and not (len(self.give_pins) > 1 or len(self.recv_pins) > 1):
            return finish("organic_shape")
        direction, tiers = self._direction(give, receive)
        expected = {"tier_up": "upgrade", "consolidate": "upgrade", "upgrade": "upgrade",
                    "tier_down": "downgrade", "downgrade": "downgrade",
                    "same_value": "lateral", "lateral": "lateral"}.get(self.intent)
        tier_lateral = expected == "lateral" and self.lateral_scope == "tier" and tiers["give"] == tiers["receive"]
        if expected and direction != expected and not tier_lateral:
            return finish("tier_direction")
        if self.swap:
            head = self._head(receive, viewer["values"])
            if self._position(head) not in self.swap:
                return finish("selected_position")
        priced = self._package(give, receive, self.market)
        if priced is None:
            return finish("invalid_market_value")
        ratio, gv, rv = priced
        data["market"] = {"give": gv, "receive": rv, "ratio": ratio,
            "requested_floor": self.requested_floor, "effective_floor": self.floor,
            "absolute_floor": self.config["market_floor_absolute"], "stud_mode": "market",
            "max_overpay_frac": self.config["max_overpay_frac"],
            "max_overpay_min_value": self.config["max_overpay_min_value"],
            "overpay_adjusted": self.config["overpay_adjusted"]}
        if ratio < self.floor - _EPS:
            return finish("market_floor")
        if not self.ts.overpay_ok(give, receive, self.market.__getitem__):
            return finish("market_overpay")
        owner = self._owner(viewer, give, receive)
        other = self._owner(opponent, receive, give)
        groups = [direction]
        if self.lateral_scope == "tier" and tiers["give"] == tiers["receive"] and "lateral" not in groups:
            groups.append("lateral")
        data.update(viewer=owner, counterparty=other, direction=direction,
                    compatible_groups=groups, personal_tiers=tiers)
        for name, result in (("viewer", owner), ("counterparty", other)):
            if result["utility"] <= _EPS or not result["benefits"]:
                return finish(name + "_no_benefit")
        for team, outgoing, incoming, out_market, in_market, explicit in (
                (viewer, give, receive, gv, rv, self.give_pins),
                # A viewer selecting GET is not the counterparty consenting
                # to sell their own untouchable. Only own SEND overrides it.
                (opponent, receive, give, rv, gv, ())):
            tagged = set(team["preferences"].get("untouchables") or ()) & set(outgoing) - set(explicit)
            if tagged and (in_market <= out_market + _EPS or any(
                    self._position(p) != "PICK" and not any(self._position(q) == self._position(p) for q in incoming)
                    for p in tagged)):
                return finish("untouchable_return")
        priority = 0
        for team, outgoing, incoming in ((viewer, give, receive), (opponent, receive, give)):
            pref = team["preferences"]
            priority += sum(self._position(p) in pref.get("acquire_positions", ()) for p in incoming)
            priority -= sum(self._position(p) in pref.get("acquire_positions", ()) for p in outgoing)
            priority += sum(self._position(p) in pref.get("trade_away_positions", ()) for p in outgoing)
            priority -= sum(self._position(p) in pref.get("trade_away_positions", ()) for p in incoming)
            priority += sum(p in pref.get("targets", ()) for p in incoming)
            priority -= sum(p in pref.get("not_interested", ()) for p in incoming)
        data["preference_priority"] = priority
        data["construction"] = {"shape": f"{len(give)}x{len(receive)}",
            "small": (len(give), len(receive)) in ((1, 1), (1, 2), (2, 1)),
            "explicit_selection": bool(self.give_pins or self.recv_pins),
            "partial_alternative": partial, "utility_coefficients": {"outlook": .5, "need": .25,
                "rebuilding_need": .05, "tanking_need": 0.0}}
        data["assets"] = [{"id": pid, "market": self.market[pid],
            "viewer_personal": viewer["values"][pid], "viewer_source": viewer["sources"][pid],
            "counterparty_personal": opponent["values"][pid], "counterparty_source": opponent["sources"][pid]}
            for pid in give + receive]
        return finish("eligible", True)

    def _asset_interest(self, team, pid, direction):
        """Joint target selection BEFORE package pricing or market gating.

        Ranking preference, outlook and marginal roster usefulness all help
        choose assets to explore. Market values normalize units, not decide
        whether a target enters the search. Package pricing happens later.
        """
        key = (pid, direction)
        if key in team["asset_interest"]:
            return team["asset_interest"][key]
        market = self.market[pid]
        personal = direction * (team["values"][pid] - market) / market
        pos = self._position(pid)
        player = self.players[pid]
        lean = -.25 if pos == "PICK" else self.ts._now_lean(pos, getattr(player, "age", None))
        outlook = .5 * direction * _WINDOW_WEIGHT.get(team["outlook"], 0.0) * lean
        after_roster = team["roster"] | {pid} if direction > 0 else team["roster"] - {pid}
        after = self._lineup(after_roster, team)
        weight = 0.0 if team["outlook"] == "jets" else (.05 if team["outlook"] == "rebuilder" else .25)
        need = weight * sum(after[p] - team["lineup_before"][p] for p in _POSITIONS) / market
        pref = team["preferences"]
        priority = .1 * direction * ((pos in pref.get("acquire_positions", ()))
                                     - (pos in pref.get("trade_away_positions", ())))
        if direction > 0:
            priority += .1 * ((pid in pref.get("targets", ())) - (pid in pref.get("not_interested", ())))
        team["asset_interest"][key] = personal + outlook + need + priority
        return team["asset_interest"][key]

    def _pool(self, team, other):
        available = sorted(p for p in team["roster"] if p in self.market)
        def interest(pid):
            return self._asset_interest(other, pid, 1) + self._asset_interest(team, pid, -1)
        # Interleave preference leaders, all market bands, and each position.
        # An expensive-only pool otherwise prevents inexpensive need trades.
        preferred = sorted(available, key=lambda p: (-interest(p), p))
        by_value = sorted(available, key=lambda p: (-self.market[p], p))
        bands = [by_value[i * len(by_value) // 3:(i + 1) * len(by_value) // 3]
                 for i in range(3)]
        positions = [sorted((p for p in available if self._position(p) == pos),
                            key=lambda p: (-interest(p), -self.market[p], p))
                     for pos in (*_POSITIONS, "PICK")]
        ordered = []
        for group in zip_longest(preferred, *bands, *positions):
            for pid in group:
                if pid is not None and pid not in ordered:
                    ordered.append(pid)
                if len(ordered) >= self.pool_size:
                    return ordered
        return ordered

    def _packages(self, pool, pins, *, exact=False, partial=False):
        if exact:
            return [pins] if pins else []
        if pins:
            if partial:
                anchors = [(p,) for p in pins if p in pool]
            else:
                anchors = [pins]
            out = []
            for anchor in anchors:
                out.append(anchor)
                if len(anchor) < 2:
                    out.extend(anchor + (p,) for p in pool if p not in anchor)
            return out
        return [(p,) for p in pool] + list(combinations(pool, 2))

    def candidates(self, member, *, partial=False):
        viewer, opponent = self.teams[self.user_id], self.teams[member.user_id]
        give_pool = self._pool(viewer, opponent)
        recv_pool = self._pool(opponent, viewer)
        # Explicit assets never fall out through stratification/truncation.
        give_pool = list(dict.fromkeys([p for p in self.give_pins if p in viewer["roster"]] + give_pool))
        recv_pool = list(dict.fromkeys([p for p in self.recv_pins if p in opponent["roster"]] + recv_pool))
        self.pools[member.user_id] = {"give": give_pool, "receive": recv_pool}
        gp = self._packages(give_pool, self.give_pins, exact=self.exact_give, partial=partial)
        rp = self._packages(recv_pool, self.recv_pins, partial=partial)
        # Small structures first; broad shapes only when multiple requested
        # assets require them. Round robin partners is performed by caller.
        for broad in (False, True):
            if broad and not (len(self.give_pins) > 1 or len(self.recv_pins) > 1):
                continue
            for give in gp:
                for receive in rp:
                    small = (len(give), len(receive)) in ((1, 1), (1, 2), (2, 1))
                    if small == broad:
                        continue
                    yield self.ts.TradeCard("", self.league.league_id, self.user_id,
                        member.user_id, member.username, list(give), list(receive), 0, 0, 0)


def _authenticated_partial(card, search):
    """A prior occurrence can authorize only its original partial request."""
    stored = getattr(card, "owner_evaluation", None)
    if isinstance(stored, OwnerDecisionContext) and stored.matches(card):
        selection = stored.as_dict()["selection"]
        return (selection["coverage"] == "partial"
            and tuple(selection["give"]["requested"]) == search.give_pins
            and tuple(selection["receive"]["requested"]) == search.recv_pins
            and selection["exact_give"] == search.exact_give)
    return False


def evaluate_owner_trades(cards, **kwargs):
    """Revalidate each occurrence, in input order, using one captured context.

    Do not deduplicate repeated cards: callers associate each returned proof
    with its corresponding publication occurrence. Partial authority remains
    independently bound to each card's immutable original selection evidence.
    """
    search = _Search(**kwargs)
    with search.ts._cfg_override(search.config), search.ts.stud_tax_override("market"):
        return [search.evaluate(card, partial=_authenticated_partial(card, search))
                for card in cards]


def evaluate_owner_trade(card, **kwargs):
    """Evaluate an exact package from fresh caller-captured owner inputs."""
    return evaluate_owner_trades([card], **kwargs)[0]


def generate_owner_trades(**kwargs):
    """Return ordinary TradeCards plus deterministic construction diagnostics.

    Every manager gets one candidate evaluation per round before a second is
    considered for anyone. Per-pair and total caps cannot silently spend the
    entire budget on the first roster. Zero small supply remains an honest
    shortage; there is no unselected 1x3/3x1 or larger fallback.
    """
    search = _Search(**kwargs)
    report = {"generator": ARM, "generator_version": VERSION, "evaluated": 0,
              "rejections": {}, "per_opponent": {}, "partial_search": False,
              "budget_exhausted": False, "small_supply": 0, "emitted": 0,
              "limits": {k: getattr(search, attr) for k, attr in (
                  ("pool", "pool_size"), ("per_pair", "pair_budget"), ("total", "total_budget"))}}
    rejects = Counter()
    per_pair = Counter()
    survivors = []
    with search.ts._cfg_override(search.config), search.ts.stud_tax_override("market"):
        for partial in (False, True):
            if partial:
                if survivors or not ((len(search.give_pins) > 1 and not search.exact_give)
                                     or len(search.recv_pins) > 1):
                    break
                report["partial_search"] = True
            streams = {m.user_id: iter(search.candidates(m, partial=partial)) for m in search.members}
            while streams and report["evaluated"] < search.total_budget:
                for uid in list(streams):
                    if per_pair[uid] >= search.pair_budget or report["evaluated"] >= search.total_budget:
                        streams.pop(uid)
                        report["budget_exhausted"] = True
                        continue
                    card = next(streams[uid], None)
                    if card is None:
                        streams.pop(uid)
                        continue
                    per_pair[uid] += 1
                    report["evaluated"] += 1
                    evidence = search.evaluate(card, partial=partial)
                    if not evidence.eligible:
                        rejects[evidence.reason] += 1
                        continue
                    snapshot = evidence.as_dict()
                    card.owner_evaluation = evidence
                    card.owner_group = snapshot["direction"]
                    card.owner_groups = tuple(snapshot["compatible_groups"])
                    card.give_value = snapshot["market"]["give"]
                    card.receive_value = snapshot["market"]["receive"]
                    card.fairness_score = snapshot["market"]["ratio"]
                    card.basis = ("divergence" if any(a["viewer_source"] != "consensus_fallback"
                        or a["counterparty_source"] != "consensus_fallback" for a in snapshot["assets"]) else "consensus")
                    card.lane = "window" if snapshot["viewer"]["outlook_utility"] > _EPS else "value"
                    card.reasons = (["Closest alternative — some selected assets could not be included."]
                        if partial else [])
                    if not snapshot["construction"]["small"]:
                        card.reasons.append("Larger package to include your selected assets.")
                    # No private opponent valuations in public rationale.
                    card.match_context = {"owner_benefits": snapshot["viewer"]["benefits"],
                        "counterparty_benefits": snapshot["counterparty"]["benefits"]}
                    survivors.append(card)
            if streams:
                report["budget_exhausted"] = True
        small = [c for c in survivors if c.owner_evaluation.as_dict()["construction"]["small"]]
        report["small_supply"] = len(small)
        if small:
            survivors = small
        def key(card):
            s = card.owner_evaluation.as_dict()
            # Suitability is already two-sided. Window/declared preferences,
            # simple shape and least market loss lead; not aggregate gain.
            return (-int(s["viewer"]["outlook_utility"] > _EPS), -s["preference_priority"],
                    max(len(card.give_player_ids), len(card.receive_player_ids)),
                    -card.fairness_score, card.target_user_id,
                    tuple(card.give_player_ids), tuple(card.receive_player_ids))
        survivors.sort(key=key)
        seen, emitted = set(), []
        for card in survivors:
            # One best companion variant per pair of headliners and shape.
            signature = (card.target_user_id,
                search._head(card.give_player_ids, search.market),
                search._head(card.receive_player_ids, search.market),
                len(card.give_player_ids), len(card.receive_player_ids))
            if signature in seen:
                continue
            seen.add(signature)
            card.trade_id = "owner_" + uuid.uuid4().hex
            card.composite_score = float(len(survivors) - len(emitted))
            card.mismatch_score = card.composite_score
            emitted.append(card)
        if search.max_cards is not None:
            emitted = emitted[:max(0, int(search.max_cards))]
    report["rejections"] = dict(rejects)
    report["pools"] = search.pools
    report["config"] = {key: value for key, value in search.config.items()
        if key.startswith(("owner_", "package_", "crown_", "age_pref_", "elo_value_", "max_overpay_"))
        or key in ("overpay_adjusted", "market_floor_absolute")}
    report["per_opponent"] = {m.user_id: {"evaluated": per_pair[m.user_id],
        "emitted": sum(c.target_user_id == m.user_id for c in emitted)} for m in search.members}
    report["emitted"] = len(emitted)
    report["shortage"] = not emitted
    return emitted, OwnerGenerationReport(_dump(report))
