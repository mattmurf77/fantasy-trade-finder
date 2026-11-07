"""Evidence-bound bilateral v3, default dark and independently reversible.

This is a correction to evidential meaning, not a production forecast model.
Personal preference, transaction price and unknown future usefulness stay apart.
No provider calls, synthetic starting jobs, or second age multiplier on prices.
"""
from collections import Counter, OrderedDict
from copy import deepcopy
from time import perf_counter

from . import trade_gen_owner as owner
from . import trade_gen_bilateral as bilateral
from . import trade_gen_bilateral_candidate as previous
from .trade_input_evidence import _age
from .trade_roster import ELIGIBILITY, assign

ARM = previous.ARM
BILATERAL_GENERATOR_VERSION = VERSION = "owner-v2-bilateral-3"
INPUT_VERSION = "owner-outlook-input-1"
_HORIZONS = {"championship": (0, 1), "contender": (0, 1),
             "rebuilder": (1, 3), "jets": (2, 4)}


class _Search(previous._Search):
    def __init__(self, *, input_evidence=None, **kwargs):
        self.input_evidence = deepcopy(input_evidence) if isinstance(input_evidence, dict) else {}
        self._age_rows = {}
        self._roster_cache = OrderedDict()
        self._window_evidence_cache = {}
        self._baseline_coverage_cache = {}
        for pid, player in kwargs["players"].items():
            rows = self.input_evidence.get("age", {})
            row = rows.get(pid, {}) if isinstance(rows, dict) else {}
            row = row if isinstance(row, dict) else {}
            age = _age(row.get("age"))
            known = (self.input_evidence.get("schema_version") == INPUT_VERSION
                     and row.get("state") == "observed" and row.get("imputed") is False
                     and row.get("source") in ("players_db", "sleeper_cache")
                     and age is not None)
            self._age_rows[pid] = {"state": "observed" if known else "unknown",
                "age": age if known else None,
                "source": row.get("source") if known else "unknown",
                "observed_at": row.get("observed_at") if known else None}
        super().__init__(**kwargs)

    def _lineup_value(self, player, pos, value):
        # Existing shared market accessor remains the price authority. Do not
        # age-adjust that already dynasty-priced value again for lineup fit.
        return value

    def _team(self, uid, roster, board, sources, prefs, outlook, real_board):
        prefs = dict(prefs)
        if outlook is None and prefs.get("team_outlook") is None and prefs.get("inferred_outlook") is None:
            # No qualified independent inference: legacy imputed age cannot
            # silently manufacture a window. Explicit/injected inference wins.
            prefs["inferred_outlook"] = "not_sure"
        return super()._team(uid, roster, board, sources, prefs, outlook, real_board)

    def _need_utility(self, team, deltas, denominator):
        delta = sum(deltas.values()) / denominator
        if team["outlook"] in ("jets", "rebuilder"):
            # Small downside context only. A current RB hole cannot authorize
            # buying a short-window player for a multi-year rebuild.
            return .05 * min(delta, 0)
        return .25 * delta

    def _plan_asset(self, team, pid):
        if self._position(pid) != "PICK":
            return 0.0  # Neither youth, price nor a personal tier proves production.
        return {"jets": 1.0, "rebuilder": .6}.get(team["outlook"], 0.0)

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
            roster = team["roster"] | {pid} if direction > 0 else team["roster"] - {pid}
            after = self._lineup(roster, team)
            need = bilateral._clip(sum(after[p] - team["lineup_before"][p]
                                      for p in owner._POSITIONS) / max(self.market[pid], 1))
            rebuilding = team["outlook"] in ("jets", "rebuilder")
            need = .025 * min(need, 0) if rebuilding else .15 * need
            team["asset_interest"][key] = preference + .3 * plan + need + declared
        return team["asset_interest"][key]

    def _composition(self, team, ids):
        gross = sum(self.market[p] for p in ids)
        def share(predicate):
            return sum(self.market[p] for p in ids if predicate(p)) / gross
        return {"market_value": gross, "asset_count": len(ids),
            "pick_share": share(lambda p: self._position(p) == "PICK"),
            "rb_share": share(lambda p: self._position(p) == "RB"),
            "known_preferred_player_share": share(lambda p: self._position(p) != "PICK"
                and self._features[team["uid"], p]["known"]
                and (self._features[team["uid"], p]["direction"] or 0) >= .025),
            "unknown_age_ids": sorted(p for p in ids if self._position(p) != "PICK"
                                       and self._age_rows[p]["age"] is None)}

    def _roster_assignment(self, team, roster):
        key = team["uid"], frozenset(roster)
        if key not in self._roster_cache:
            usable = [self._lineup_assets[p] for p in roster
                      if p in self._lineup_assets and p not in team["inactive"]]
            if team.get("native_bounds"):
                from .calibration_native_lineup import choose, templates
                assignment = choose(team["native_bounds"], len(team["slots"]), usable)
            else:
                assignment = tuple(assign(team["slots"], usable))
            starters = set(assignment)
            result = {pos: 0.0 for pos in owner._POSITIONS}
            bench = {pos: 0.0 for pos in owner._POSITIONS}
            for asset in usable:
                pos = self._position(asset.id)
                if asset.id in starters:
                    result[pos] += asset.value
                elif (any(pos in template for template in templates(team["native_bounds"], len(team["slots"])))
                      if team.get("native_bounds") else any(pos in ELIGIBILITY[s] for s in team["slots"])):
                    bench[pos] = max(bench[pos], asset.value)
            for pos in result:
                result[pos] += .15 * bench[pos]
            self._roster_cache[key] = assignment, result
            if len(self._roster_cache) > 256:
                self._roster_cache.popitem(last=False)
        self._roster_cache.move_to_end(key)
        return self._roster_cache[key]

    def _lineup(self, roster, team):
        return self._roster_assignment(team, roster)[1]

    def _coverage(self, team, roster):
        baseline = roster is team["roster"]
        if baseline and team["uid"] in self._baseline_coverage_cache:
            return self._baseline_coverage_cache[team["uid"]]
        assignment, _ = self._roster_assignment(team, roster)
        selected_slots = getattr(assignment, "slots", team["slots"])
        from .calibration_native_lineup import max_positions
        result = {
            "roster_qb_ids": sorted(p for p in roster if self._position(p) == "QB"),
            "eligible_roster_qb_ids": sorted(p for p in roster if self._position(p) == "QB"
                and p in self._lineup_assets and p not in team["inactive"]),
            "availability_basis": "captured_injury_labels_and_inactive_ids",
            "availability_freshness": "unknown",
            "qb_eligible_slots": (max_positions(team["native_bounds"], len(team["slots"])).get("QB", 0)
                                  if team.get("native_bounds") else sum("QB" in ELIGIBILITY[s] for s in team["slots"])),
            "assignment": [{"slot": slot, "asset_id": pid,
                "position": self._position(pid) if pid else None}
                for slot, pid in zip(selected_slots, assignment) if "QB" in ELIGIBILITY[slot]],
            "nfl_starting_jobs": "unknown", "future_availability": "unknown"}
        if baseline:
            self._baseline_coverage_cache[team["uid"]] = result
        return result

    def _rb_acquisition_thesis(self, team, pid):
        pref = team["preferences"]
        if team["uid"] == self.user_id and pid in self.recv_pins:
            return "explicit_selection"
        if pid in pref.get("targets", ()) or "RB" in pref.get("acquire_positions", ()):
            return "declared_acquisition"
        feature = self._features[team["uid"], pid]
        if feature["known"] and (feature["direction"] or 0) >= .025:
            return "known_positive_personal_preference"
        return None

    def _rb_companion_thesis(self, team, pid, outgoing, incoming):
        """Incidental RBs need an independent focal buy and required pricing.

        A tiny desired asset or token pick cannot authorize an RB-centered buy.
        Neither necessity nor market gain alone is an acquisition thesis.
        """
        maximum = max(self.market[p] for p in incoming)
        focal = [p for p in incoming if self.market[p] == maximum and self._position(p) != "RB"]
        pref = team["preferences"]
        desired = any((team["uid"] == self.user_id and p in self.recv_pins)
            or p in pref.get("targets", ()) or self._position(p) in pref.get("acquire_positions", ())
            or (self._features[team["uid"], p]["known"]
                and (self._features[team["uid"], p]["direction"] or 0) >= .025) for p in focal)
        capital = (any(self._position(p) == "PICK" for p in focal)
            and sum(self.market[p] for p in incoming if self._position(p) == "PICK")
            > sum(self.market[p] for p in outgoing if self._position(p) == "PICK"))
        if not (desired or capital):
            return None
        simpler = tuple(p for p in incoming if p != pid)
        priced = self._package(outgoing, simpler, self.market)
        required = (priced is None or priced[0] < self.floor - owner._EPS
                    or not self.ts.overpay_ok(outgoing, simpler, self.market.__getitem__))
        return "required_price_companion_to_independent_focal_thesis" if required else None

    def _window_evidence(self, team, pid):
        key = team["uid"], pid
        if key in self._window_evidence_cache:
            return self._window_evidence_cache[key]
        pos = self._position(pid)
        horizon = _HORIZONS.get(team["outlook"])
        age = self._age_rows[pid]
        result = {"position": pos, "age": age if pos != "PICK" else {"state": "not_applicable", "age": None},
            "age_at_window": [age["age"] + year for year in horizon]
                if pos != "PICK" and age["age"] is not None and horizon else None,
            "production_fit": "not_applicable" if pos == "PICK" else "unknown",
            "qb_quality_class": "unknown" if pos == "QB" else "not_applicable",
            "position_context": {"RB": "role_and_availability_required_for_multiyear_fit",
                "QB": "production_and_starting_role_required",
                "WR": "production_and_receiving_role_required",
                "TE": "production_receiving_role_and_scoring_required",
                "PICK": "future_capital_not_projected_production"}.get(pos, "unknown"),
            "age_used_as_fit_score": False, "career_length_used_as_fit_score": False}
        # Request-local facts are read-only internally. Full JSON proof
        # serialization still detaches every offered occurrence at its boundary.
        self._window_evidence_cache[key] = result
        return result

    def _owner(self, team, give, receive):
        result = super()._owner(team, give, receive)
        if "window_evidence" in result:
            return result
        horizon = _HORIZONS.get(team["outlook"])
        result["lineup_proxy"] = "market_usable_depth_no_age_v3"
        result["outlook_utility"] = 0.0  # Retire inherited age-lean diagnostics too.
        result["starter_evidence"]["proxy"] = result["lineup_proxy"]
        result["benefits"] = ["future_pick_capital" if b == "outlook" else b for b in result["benefits"]]
        result["team_plan_evidence"]["missing_age_ids"] = [p for p in give + receive
            if self._position(p) != "PICK" and self._age_rows[p]["age"] is None]
        result["window_evidence"] = {"state": "unknown_production", "season_offsets": horizon,
            "horizon_source": "provisional_outlook_default" if horizon else "unknown",
            "outlook_source": team["outlook_source"],
            "assets": {p: self._window_evidence(team, p) for p in give + receive},
            "missing": ["qualified_production_history", "observed_starting_role",
                        "future_projections", "future_availability", "required_cuts"],
            "fit_policy": "neutral_players_future_capital_only"}
        result["qb_roster_context"] = {"basis": "legal_slots_and_market_prices_not_points_or_jobs",
            "slot_source": team["lineup_source"],
            "before": self._coverage(team, team["roster"]),
            "after": self._coverage(team, (team["roster"] - set(give)) | set(receive))}
        result["decomposition"].update(player_window_fit=None,
            future_capital_direction=sum(sign * self.market[p] * self._plan_asset(team, p)
                for sign, ids in ((1, receive), (-1, give)) for p in ids)
                / sum(self.market[p] for p in give + receive),
            roster_proxy_applicability="bounded_downside_only" if team["outlook"] in ("jets", "rebuilder")
                else "current_market_proxy_only")
        return result

    def _decision(self, card, data, reason, eligible=False):
        # Restate v1's non-age bilateral gates. Do not invoke its categorical
        # young-asset/RB-tier exceptions: those are the policy being replaced.
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
                "diversity_tolerance": bilateral._QUALITY_TOLERANCE}
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
                if team["outlook"] in ("jets", "rebuilder"):
                    maximum = max(self.market[p] for p in incoming)
                    # Each RB needs its own desire or a narrowly qualified
                    # consideration role. A lower price alone is not a thesis.
                    focal_rbs = [p for p in incoming if self._position(p) == "RB"
                                 and self.market[p] == maximum]
                    theses = {p: self._rb_acquisition_thesis(team, p) for p in focal_rbs}
                    companions = {p: (self._rb_acquisition_thesis(team, p)
                        or self._rb_companion_thesis(team, p, outgoing, incoming))
                        for p in incoming if self._position(p) == "RB" and self.market[p] < maximum}
                    side["rb_acquisition_evidence"] = {
                        "focal_theses": theses,
                        "companion_theses": companions,
                        "meaning": "manager_desire_not_longevity"}
                    if any(thesis is None for thesis in theses.values()):
                        reason = "rebuild_rb_acquisition_thesis_missing"
                    elif any(thesis is None for thesis in companions.values()):
                        reason = "rebuild_rb_companion_thesis_missing"
                if (team["outlook"] == "jets"
                        and (set(outgoing) & set(pref.get("own_next_draft_pick_ids", ()))) - set(selected)):
                    reason = "tanking_own_next_draft_pick"
            for asset in data["assets"]:
                asset["viewer_preference"] = self._features[self.user_id, asset["id"]]
                asset["counterparty_preference"] = self._features[card.target_user_id, asset["id"]]
        return owner._Search._decision(self, card, data, reason, reason == "eligible")

    def _freeze_decision(self, card, data, reason, eligible):
        data["generator_version"] = VERSION
        if "construction" in data:
            data["construction"].update(policy="evidence_bound_window_and_price_proxy", coefficients=previous._WEIGHTS)
        data["input_evidence"] = {"schema_version": INPUT_VERSION, "used_in_model": True,
            "age_use": "diagnostic_only_not_production_fit",
            "age": {p: self._age_rows[p] for p in card.give_player_ids + card.receive_player_ids if p in self._age_rows}}
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


def generate_bilateral_trades(**kwargs):
    started = perf_counter()
    search = _GenerationSearch(**kwargs)
    cards, raw = bilateral._generate_with_search(search,
        ranker=lambda cards: previous._rank(cards, version=VERSION), version=VERSION)
    report, counts = raw.as_dict(), Counter()
    for card in cards:
        evidence = card.owner_evaluation.as_dict()
        counts["efficient" if evidence["term_efficiency"]["efficient"] else "avoidable_alternative"] += 1
        counts["companion_comparisons"] += evidence["term_efficiency"]["audited_alternatives"]
    report.update(support_weights=previous._WEIGHTS, term_efficiency=dict(counts),
        term_ordering={"version": previous.TERM_ORDERING_VERSION,
                       "comparisons_per_family": previous.TERM_LOOKAHEAD,
                       "policy": "same_focal_precedence_preserve_inventory"},
        starter_evidence="unknown_no_qualified_owner_forecast",
        outlook_policy="neutral_players_future_capital_only",
        elapsed_seconds=round(perf_counter() - started, 6))
    return cards, owner.OwnerGenerationReport(owner._dump(report))
