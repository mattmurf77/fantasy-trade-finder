"""Bilateral revision 5: revision 2 plus the win-now season signal.

Built on revision 2 (owner-v2-bilateral-2), never on revision 3 or 4. Spec:
docs/plans/win-now-season-signal/lld.md §3 (algorithm) and §4 (proof fields);
the rules per outlook are the PRD's §1, §2 and §5.

The search takes one new input, `season_evidence` (`season_value.build_evidence`).
Absent or not usable: every override below defers to revision 2, so the cards,
terms and order are revision 2's and only the version stamp and one evidence
record differ. Usable:

- An All-in or Contending team (the viewer; every such team in stage 2) has its
  lineup scored in projected points per game, starters only, at RATE value
  points per point, and its plan fit read from a small label table instead of
  the age curve.
- Candidate seats: the viewer's receive pools guarantee places to players who
  would start for the viewer; the give pools to the viewer's picks and
  non-starters.
- Plan conflict (`season_value.plan_conflict`, the one predicate): a card that
  works against the viewer's saved plan is flagged; when it qualified through the
  viewer's own rankings, both support scores fall by `season_conflict_demotion`
  after eligibility (order only, never inventory or terms), as revision 4 demotes.
- Stage 2 (`season_partner_matching == 1`): the label table also reads every
  league-mate's plan fit, Rebuilding and Tanking teams by a mirror table.

Prices, package pricing, the fairness score, the market floor and the overpay
gate are revision 2's. No database, server, provider or network access occurs in
this module.
"""

from collections import Counter
from itertools import zip_longest
from time import perf_counter

from . import season_value as sv
from . import trade_gen_owner as owner
from . import trade_gen_bilateral as incumbent
from . import trade_gen_bilateral_candidate as previous
from .ranking_service import ORDERED_TIERS
from .trade_roster import ELIGIBILITY, Asset, assign


ARM = previous.ARM
BILATERAL_GENERATOR_VERSION = VERSION = "owner-v2-bilateral-5"
RULES_VERSION = sv.RULES_VERSION
LABEL_RULES_VERSION = sv.LABEL_RULES_VERSION
RATE = sv.RATE                      # value points per projected point a week (lld §3.2)
START_GAIN = .5                     # points a week a player must add to "start for" a team (starting value)
SCORED_OUTLOOKS = ("championship", "contender")
MIRROR_OUTLOOKS = ("rebuilder", "jets")
# Plan-fit leans for a season-scored team (lld §3.3): the top and bottom of the
# age lean revision 2 uses, so the plan term keeps its range.
LEAN_STARTS_LABELLED, LEAN_STARTS, LEAN_BENCH = .40, .25, -.25
# Stage 2 mirror table for Rebuilding / Tanking teams (starting values).
MIRROR_LEAN = {"rebuild": .7, "cornerstone_young": .45, "cornerstone": .2,
               "win_now_rb": -.8, "win_now": -.45}
MIRROR_SCALE = {"jets": 1.0, "rebuilder": .6}
DEMOTION_KEY, MATCHING_KEY = "season_conflict_demotion", "season_partner_matching"
# Conflict kinds: "board" (qualified through the viewer's own rankings) or the
# viewer's declaration that matched, in this precedence (revision 2's own order):
# the incoming player is on the target list, the outgoing player is on the trade
# block, the incoming player's position is asked for, the outgoing player's
# position is being shopped.
DECLARED_KINDS = ("target", "trade_block", "position", "trade_away")
# Which conflict kinds are pushed down (PRD §5.2): only a card that qualified
# through the viewer's own rankings. A card the viewer asked for (any declared
# kind) is flagged and stated, never demoted. The switch is this set.
DEMOTED_KINDS = frozenset(("board",))
POLICY = "price_efficient_bilateral_portfolio_season_signal"


def _shift(side, delta, adjustments):
    """A detached side with its support moved; the cached side is untouched."""
    support = dict(side["support"])
    support.update(score=incumbent._clip(support["score"] + delta, 0, 1),
                   range=[incumbent._clip(bound + delta, 0, 1) for bound in support["range"]],
                   season_unadjusted_score=support["score"], season_adjustments=adjustments)
    return {**side, "support": support}


class SeasonLayer:
    """The season layer as a mixin over revision 2's search. Holds no revision 2 logic."""

    def __init__(self, *, season_evidence=None, **kwargs):
        from . import trade_service as ts
        given = kwargs.get("config") or {}
        # Read before the base constructor drops the dark knobs from its config.
        self.season_conflict_demotion = float(given.get(DEMOTION_KEY, ts._c(DEMOTION_KEY)))
        self.season_partner_matching = given.get(MATCHING_KEY, ts._c(MATCHING_KEY)) == 1.0
        self.season_evidence = season_evidence
        self._season_on = sv.usable(season_evidence)
        self._season_ppg = {pid: item["ppg"] for pid, item in
                            ((season_evidence or {}).get("players") or {}).items()} if self._season_on else {}
        self._season_assets = None
        self._season_totals = {}
        self._season_gains = {}
        self._profile = None
        super().__init__(**kwargs)
        if self._season_on:
            self._profile = sv.league_profile(
                season_evidence,
                rosters={uid: sorted(team["roster"]) for uid, team in self.teams.items()},
                position={pid: self._position(pid) for team in self.teams.values() for pid in team["roster"]},
                market=self.market,
                age={pid: getattr(self.players.get(pid), "age", None)
                     for team in self.teams.values() for pid in team["roster"]},
                inactive=set().union(*(team["inactive"] for team in self.teams.values()))
                | {pid for pid in self.market if self._position(pid) in owner._POSITIONS
                   and pid not in self._lineup_assets})

    # --- which teams, and their season lineup (lld §3.1, §3.2) -----------------

    def _season_scored(self, team):
        return (self._season_on and team["outlook"] in SCORED_OUTLOOKS
                and (team["uid"] == self.user_id or self.season_partner_matching)
                and not team.get("native_bounds"))

    def _team(self, uid, roster, *args):
        if self._season_assets is None:
            # `_lineup_assets` (today's injury rule) is filled; teams are not built yet.
            self._season_assets = {pid: Asset(pid, asset.positions, RATE * self._season_ppg[pid])
                                   for pid, asset in self._lineup_assets.items() if pid in self._season_ppg}
        return super()._team(uid, roster, *args)

    def _season_total(self, roster, team):
        """(points a week, starters, {position: value units}) of the team's best season lineup."""
        key = team["uid"], frozenset(roster)
        if key not in self._season_totals:
            usable = [self._season_assets[p] for p in roster
                      if p in self._season_assets and p not in team["inactive"]]
            fill = self.season_evidence.get("free_agent_level") or {}
            points, starters = 0.0, set()
            units = {pos: 0.0 for pos in owner._POSITIONS}
            for slot, pid in zip(team["slots"], assign(team["slots"], usable)):
                if pid:
                    points += self._season_ppg[pid]
                    units[self._position(pid)] += RATE * self._season_ppg[pid]
                    starters.add(pid)
                else:
                    # An empty slot is filled by the best projected free agent for it (PRD §2.3).
                    level, pos = max((float(fill.get(p) or 0.0), p) for p in owner._POSITIONS
                                     if p in ELIGIBILITY[slot])
                    points += level
                    units[pos] += RATE * level
            self._season_totals[key] = (round(points, 6), frozenset(starters), units)
        return self._season_totals[key]

    def _lineup(self, roster, team):
        if not self._season_scored(team):
            return super()._lineup(roster, team)
        return dict(self._season_total(roster, team)[2])

    def season_gain(self, team, pid):
        """Points a week the team's best season lineup gains with `pid` against without him."""
        key = team["uid"], pid
        if key not in self._season_gains:
            roster = set(team["roster"])
            self._season_gains[key] = round(self._season_total(roster | {pid}, team)[0]
                                            - self._season_total(roster - {pid}, team)[0], 6)
        return self._season_gains[key]

    def starts_for(self, team, pid):
        return pid in self._season_ppg and self.season_gain(team, pid) >= START_GAIN - owner._EPS

    def _label(self, pid):
        return ((self._profile or {}).get("players", {}).get(pid) or {}).get("label")

    # --- plan fit from the label table (lld §3.3) ------------------------------

    def _season_lean(self, team, pid):
        """The table lean for a season-scored team, or None where today's rule decides."""
        if self._position(pid) == "PICK":
            return LEAN_BENCH
        if pid not in self._season_ppg:
            return None  # unprojected: today's age rule, no season claim
        if not self.starts_for(team, pid):
            return LEAN_BENCH
        return LEAN_STARTS_LABELLED if self._label(pid) in ("win_now", "cornerstone") else LEAN_STARTS

    def _mirror_fit(self, team, pid):
        """Stage 2: a Rebuilding or Tanking team's fit from the labels, or None for today's rule."""
        pos, age = self._position(pid), getattr(self.players[pid], "age", None)
        if pos == "PICK":
            return 1.0 * MIRROR_SCALE[team["outlook"]]
        feature = self._features[team["uid"], pid]
        direction = feature["direction"]
        # Revision 2's board-led refinements keep precedence (trade_gen_bilateral_candidate.py:43-51).
        if pos == "RB" and feature["known"] and feature["personal_tier"] in ORDERED_TIERS[:3]:
            fit = .4
        elif (pos in ("WR", "TE", "QB") and owner._finite(age) and age <= incumbent._YOUNG[pos]
              and direction is not None and abs(direction) >= .025):
            fit = .85 if direction >= .025 else -.10
        else:
            label = self._label(pid)
            if label == "rebuild":
                fit = MIRROR_LEAN["rebuild"]
            elif label == "cornerstone":
                fit = MIRROR_LEAN["cornerstone_young" if sv.young(pos, age) else "cornerstone"]
            elif label == "win_now":
                fit = MIRROR_LEAN["win_now_rb" if pos == "RB" else "win_now"]
            else:
                return None
        return fit * MIRROR_SCALE[team["outlook"]]

    def _plan_asset(self, team, pid):
        key = team["uid"], pid
        if key in self._plan_cache:
            return self._plan_cache[key]
        if self._season_scored(team):
            lean = self._season_lean(team, pid)
            if lean is None:
                return super()._plan_asset(team, pid)
            fit = incumbent._clip(2 * owner._WINDOW_WEIGHT[team["outlook"]] * lean)
        elif self._season_on and self.season_partner_matching and team["outlook"] in MIRROR_OUTLOOKS:
            fit = self._mirror_fit(team, pid)
            if fit is None:
                return super()._plan_asset(team, pid)
        else:
            return super()._plan_asset(team, pid)
        self._plan_cache[key] = fit
        return fit

    def _plan_fit(self, team, give, receive):
        """The plan part of team plan (revision 2's plan shift), recorded beside lineup gain."""
        gross = sum(self.market[p] for p in give + receive)
        return sum(sign * self.market[p] * self._plan_asset(team, p)
                   for sign, ids in ((1, receive), (-1, give)) for p in ids) / gross

    # --- candidate seats (lld §3.4) ------------------------------------------

    def _pool(self, team, other):
        viewer = self.teams[self.user_id]
        if not self._season_scored(viewer) or viewer["uid"] not in (team["uid"], other["uid"]):
            return super()._pool(team, other)
        available = sorted(p for p in team["roster"] if p in self.market)
        if other is viewer:
            # Receive pool: the partner's players who would start for the viewer.
            seats = sorted((p for p in available if self.starts_for(viewer, p)),
                           key=lambda p: (-self.season_gain(viewer, p), p))
        else:
            # Give pool: the viewer's picks and non-starters, future value first.
            starters = self._season_total(viewer["roster"], viewer)[1]
            seats = sorted((p for p in available if p not in starters),
                           key=lambda p: (-self.market[p], p))
        # Revision 2's interleave (trade_gen_owner._pool) with the seats as a second list.
        def interest(pid):
            return self._asset_interest(other, pid, 1) + self._asset_interest(team, pid, -1)
        preferred = sorted(available, key=lambda p: (-interest(p), p))
        by_value = sorted(available, key=lambda p: (-self.market[p], p))
        bands = [by_value[i * len(by_value) // 3:(i + 1) * len(by_value) // 3] for i in range(3)]
        positions = [sorted((p for p in available if self._position(p) == pos),
                            key=lambda p: (-interest(p), -self.market[p], p))
                     for pos in (*owner._POSITIONS, "PICK")]
        ordered = []
        for group in zip_longest(preferred, seats, *bands, *positions):
            for pid in group:
                if pid is not None and pid not in ordered:
                    ordered.append(pid)
                if len(ordered) >= self.pool_size:
                    return ordered
        return ordered

    # --- the season record per side and per card (lld §3.5, §4) ---------------

    def _owner(self, team, give, receive):
        result = super()._owner(team, give, receive)
        if "season" in result or not self._season_scored(team):
            return result
        before, held, _ = self._season_total(team["roster"], team)
        after, starters, _ = self._season_total((team["roster"] - set(give)) | set(receive), team)
        delta = round(after - before, 2)
        result["season"] = {"state": "projected", "delta_pts_week": delta,
                            "before": round(before, 2), "after": round(after, 2),
                            "incoming_starters": sorted(p for p in receive if p in starters),
                            "outgoing_starters": sorted(p for p in give if p in held)}
        result["lineup_proxy"] = "season_points_per_game_v1"
        result["starter_evidence"] = {"state": "projected", "projected_starter_delta": delta,
            "proxy": "season_points_per_game_v1", "slot_source": team["lineup_source"],
            "weeks": list(self.season_evidence["weeks"]), "evidence_digest": self.season_evidence["digest"]}
        result["decomposition"]["projected_starter_delta"] = delta
        return result

    def _season_signal(self, card, data):
        evidence = self.season_evidence
        if not self._season_on:
            data["season_signal"] = {"evidence": {
                "state": "absent" if evidence is None else evidence.get("state"),
                "reason": None if evidence is None else evidence.get("reason")}}
            return
        give, receive = tuple(card.give_player_ids), tuple(card.receive_player_ids)
        viewer, side = self.teams[self.user_id], data["viewer"]
        scored, season = self._season_scored(viewer), side.get("season")
        plan, intent = viewer["outlook"], side["intent"]
        fired = sv.plan_conflict(plan=plan, declared=viewer["outlook_source"] == "declared",
            usable_evidence=True, pinned=bool(self.give_pins or self.recv_pins or self.opponent_id),
            delta_pts_week=season["delta_pts_week"] if season else None,
            receive=receive, give=give, profile=self._profile, market=self.market)
        buy, sell = intent["buy_target"], intent["sell_candidate"]
        if intent["path"] == "personal_board":
            kind = "board"
        elif intent["path"] == "declared_intent" and intent["declared_match"]:
            # The declaration that matched, in revision 2's own order
            # (trade_gen_bilateral.py `declared`): DECLARED_KINDS.
            prefs = viewer["preferences"]
            kind = next((k for k, matched in zip(DECLARED_KINDS, (
                buy in prefs.get("targets", ()),
                sell in prefs.get("trade_block", ()),
                self._position(buy) in prefs.get("acquire_positions", ()),
                self._position(sell) in prefs.get("trade_away_positions", ()))) if matched), None)
        else:
            kind = None  # qualified by the plan itself, or otherwise: no conflict recorded
        fired = fired and kind is not None
        named = None
        if fired:
            if kind == "board":
                lean_in = self._features[self.user_id, buy]["direction"] or 0
                lean_out = self._features[self.user_id, sell]["direction"] or 0
                named = buy if lean_in >= -lean_out else sell
            else:
                # The asset the declaration is about: incoming for a target or an
                # asked-for position, outgoing for the trade block or a shopped position.
                named = sell if kind in ("trade_block", "trade_away") else buy
        demotion = (self.season_conflict_demotion
                    if fired and kind in DEMOTED_KINDS and self.season_conflict_demotion > 0 else 0.0)
        plan_fit = self._plan_fit(viewer, give, receive)
        lineup_gain = incumbent._clip(side["need_utility"] * 4)
        roster_total = round(sum(self.market.get(p, 0.0) for p in viewer["roster"]), 2)
        market = data["market"]
        assets = []
        for pid in give + receive:
            projected = pid in self._season_ppg
            info = (self._profile["players"].get(pid) or {})
            assets.append({"id": pid, "ppg": self._season_ppg.get(pid), "label": info.get("label"),
                "future": info.get("future"),
                "starts_for_viewer": self.starts_for(viewer, pid) if projected else None,
                "gain_for_viewer": self.season_gain(viewer, pid) if projected else None,
                "plan_lean": self._season_lean(viewer, pid) if scored else None})
        data["season_signal"] = {"rules_version": RULES_VERSION, "label_rules_version": LABEL_RULES_VERSION,
            "evidence": {"state": evidence["state"], "reason": evidence["reason"], "digest": evidence["digest"],
                         "run_id": evidence.get("run_id"), "captured_at": evidence.get("captured_at"),
                         "weeks": list(evidence["weeks"])},
            "viewer": {"scored": scored, "outlook": plan, "outlook_source": viewer["outlook_source"],
                       **({"delta_pts_week": season["delta_pts_week"], "lineup_before": season["before"],
                           "lineup_after": season["after"], "incoming_starters": season["incoming_starters"],
                           "outgoing_starters": season["outgoing_starters"]} if season else {}),
                       "dynasty_cost_pct": round(100 * (market["give"] - market["receive"]) / roster_total, 2)
                       if roster_total > 0 else None,
                       "roster_market_total": roster_total},
            "assets": assets,
            "conflict": {"fired": fired, "plan": plan, "kind": kind if fired else None, "named": named,
                         "threshold": sv.CONFLICT_DROP.get(plan), "demotion": demotion},
            "components": {"plan_fit": plan_fit, "lineup_gain": lineup_gain,
                           "team_plan": side["support"]["components"]["team_plan"],
                           "ranges": {"plan_fit": [-1, 1], "lineup_gain": [-1, 1], "team_plan": [0, 1]}}}
        if demotion:
            # Both sides, as revision 4 demotes: the weaker score falls by the full
            # amount and presentment, which reads both, cannot undo it.
            adjustment = {"plan_conflict_demotion": -demotion}
            data["viewer"] = _shift(data["viewer"], -demotion, adjustment)
            data["counterparty"] = _shift(data["counterparty"], -demotion, adjustment)

    def _decision(self, card, data, reason, eligible=False):
        # Before bilateral-1 builds the weaker/total support block from the sides,
        # and after utility and eligibility: the push-down cannot reject a card.
        if eligible and "viewer" in data and "counterparty" in data:
            self._season_signal(card, data)
        return super()._decision(card, data, reason, eligible)

    def _freeze_decision(self, card, data, reason, eligible):
        data["generator_version"] = VERSION
        if "construction" in data:
            data["construction"].update(policy=POLICY, coefficients=previous._WEIGHTS)
        return owner._Search._freeze_decision(self, card, data, reason, eligible)


class _Search(SeasonLayer, previous._Search):
    pass


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


def _rank(cards):
    """Revision 2's ranker; the version binds its term-precedence evidence check."""
    return previous._rank(cards, version=VERSION)


def generate_bilateral_trades(**kwargs):
    started = perf_counter()
    search = _GenerationSearch(**kwargs)
    cards, raw = incumbent._generate_with_search(search, ranker=_rank, version=VERSION)
    report, counts, season = raw.as_dict(), Counter(), Counter()
    for card in cards:
        data = card.owner_evaluation.as_dict()
        counts["efficient" if data["term_efficiency"]["efficient"] else "avoidable_alternative"] += 1
        counts["companion_comparisons"] += data["term_efficiency"]["audited_alternatives"]
        conflict = data["season_signal"].get("conflict")
        if conflict and conflict["fired"]:
            season["conflicts"] += 1
            season["conflict_kind:" + conflict["kind"]] += 1
            season["demoted"] += conflict["demotion"] > 0
    evidence = search.season_evidence
    viewer_scored = search._season_scored(search.teams[search.user_id])
    report.update(support_weights=previous._WEIGHTS, term_efficiency=dict(counts),
        term_ordering={"version": previous.TERM_ORDERING_VERSION,
                       "comparisons_per_family": previous.TERM_LOOKAHEAD,
                       "policy": "same_focal_precedence_preserve_inventory"},
        starter_evidence="projected_points_viewer" if viewer_scored else "dynasty_proxy_only_no_projected_points",
        season_signal={"rules_version": RULES_VERSION, "label_rules_version": LABEL_RULES_VERSION,
            "evidence_state": "absent" if evidence is None else evidence.get("state"),
            "evidence_reason": None if evidence is None else evidence.get("reason"),
            "evidence_digest": evidence.get("digest") if search._season_on else None,
            "viewer_scored": viewer_scored, "partner_matching": search.season_partner_matching,
            "conflict_demotion": search.season_conflict_demotion, **dict(season)},
        elapsed_seconds=round(perf_counter() - started, 6))
    return cards, owner.OwnerGenerationReport(owner._dump(report))
