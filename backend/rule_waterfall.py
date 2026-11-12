"""Decline waterfall: how many candidate trades each yes/no rule removes, in order.

Founders' review, use case 2 (docs/plans/founder-review/rule-waterfall-design.md). For one
viewer's organic deck request it answers "we started with N candidate trades; this rule removed
so many; M were served", one row per rule of ``rule_catalog`` in waterfall order.

Basis: a DIAGNOSTIC FULL SOLVE, not the served page path. The page search that serves today
(``trade_fast_deck.serve``) skips candidates its bounds prove cannot pass, so it never learns
which rule each skipped candidate would have failed. Here every candidate the generator
enumerates is evaluated by the generator's own, unmodified evaluator and counted once, at the
first rule that stops it:

1. Started with: every 1-for-1, 2-for-1 and 1-for-2 trade that can be built from the players
   the search considers (each manager's pool of up to 16 per other team), ``universe``.
2. Candidate building: the expansions the generator never tries because their core 1-for-1
   failed an incurable rule (``not_expanded``); the stream budget (``search_budget``, raised to
   its maximum here so it binds only from about 30 teams, as the served page ignores it).
3. Both-sides check: the evaluator's own reason for each evaluated candidate (the generator's
   report counts exactly these; the two must agree). Then ``duplicate``.
4. Deck rules: ``DeckRules.reason`` on each survivor (significance, breakup, filler, redundant),
   the predicate the served path admits with.
5. After the deck is built: the worker's downstream stages, passed in as ``after`` (see
   ``server_stages``), each counted by the generated cards it removes. Cards a stage ADDS (liked
   trades, standing offers) are reported separately, never netted into a rule's row.

Identity: started - sum(removed) = served_generated; served_total = served_generated + added.
The admitted deck it ranks is the rules-first deck (``trade_fast_deck.serve``) card for card
whenever the page serves and the budgets do not bind (pinned by ``test_rule_waterfall``).

Instrumentation, not a fork: the only engine-facing code is a subclass of the generator's own
search class whose ``evaluate`` calls the original and records the result's reason. No engine
module changes; the served path never runs this. Aggregate output only: counts, shares, names
of rules, the generator version. No player, user, league or roster ids leave this module.
"""
from __future__ import annotations

from collections import Counter
from math import comb
from time import perf_counter

from . import rule_catalog

VERSION = "rule-waterfall-1"
# The diagnostic lifts the incumbent stream budgets to the evaluator's own maxima so its universe
# is the served page's (which ignores them). trade_gen_owner._limit clamps to these.
_DIAGNOSTIC_BUDGETS = {"owner_total_budget": 120000.0, "owner_pair_budget": 16384.0}
_UNSUPPORTED = ("pinned_give_players", "pinned_receive_players", "exact_give", "require_all_give",
                "opponent_user_id", "trade_intent", "swap_positions")
STARTED_DEFINITION = ("Every 1-for-1, 2-for-1 and 1-for-2 trade between you and each other team "
                      "that can be built from the up-to-16 players per side the search considers.")


class Unsupported(ValueError):
    """The request is outside the waterfall's scope (the rules-first organic deck)."""


def supported(context) -> bool:
    return not any(context.get(name) for name in _UNSUPPORTED)


def _module(generate):
    from . import trade_fast_deck
    return trade_fast_deck._module(generate)


def _universe(pools):
    """Every 1x1, 2x1 and 1x2 package of one opponent's two pools, as (give, receive) frozensets."""
    give, receive = pools["give"], pools["receive"]
    out = []
    for g in give:
        for r in receive:
            out.append((frozenset((g,)), frozenset((r,))))
    for r in receive:
        for i, a in enumerate(give):
            for b in give[i + 1:]:
                out.append((frozenset((a, b)), frozenset((r,))))
    for g in give:
        for i, a in enumerate(receive):
            for b in receive[i + 1:]:
                out.append((frozenset((g,)), frozenset((a, b))))
    return out


def _possible(n_give, n_receive):
    return n_give * n_receive + n_receive * comb(n_give, 2) + n_give * comb(n_receive, 2)


def diagnostic_solve(generate, context, rules, *, check=None):
    """``(admitted deck, counts)``: the generator's full solve with every evaluation recorded.

    ``counts``: {"universe", "possible_full_roster", "teams", reason: n, ...} over the both-sides
    and building rows, "duplicate", the deck rules' reasons and "admitted"."""
    module = _module(generate)
    if module is None:
        raise Unsupported("generator has no rules-first construction")
    if not supported(context):
        raise Unsupported("pinned, opponent-scoped or intent request")
    from . import trade_first_page, trade_gen_bilateral as bilateral
    base = getattr(module, "_GenerationSearch", None) or module._Search
    evaluated = {}            # (uid, give, receive) -> reason ("eligible" when it passed)

    class _Recorded(base):
        def evaluate(self, card, *, partial=False):
            result = super().evaluate(card, partial=partial)
            evaluated[(card.target_user_id, frozenset(card.give_player_ids),
                       frozenset(card.receive_player_ids))] = (
                "eligible" if result.eligible else result.reason)
            return result

    survivors = []

    def ranker(cards):
        survivors.extend(cards)
        return module._rank([c for c in cards if rules.admits(
            c.target_user_id, c.give_player_ids, c.receive_player_ids)])

    config = {**(context.get("config") or {}), **_DIAGNOSTIC_BUDGETS}
    search = _Recorded(**{**context, "config": config}, _check_current=check)
    deck, report = bilateral._generate_with_search(search, ranker=ranker, version=module.VERSION)
    report = report.as_dict()

    counts = Counter()
    reasons = Counter(r for r in evaluated.values() if r != "eligible")
    if dict(reasons) != report["rejections"]:      # the recorder saw every evaluation
        raise RuntimeError("waterfall recorder disagrees with the generator's own rejections")
    curable = set(trade_first_page._CURABLE)
    full_roster = 0
    viewer_roster = [p for p in search.teams[search.user_id]["roster"] if p in search.market]
    for member in search.members:
        pools = search.pools.get(member.user_id) or {"give": [], "receive": []}
        theirs = [p for p in search.teams[member.user_id]["roster"] if p in search.market]
        full_roster += _possible(len(viewer_roster), len(theirs))
        for give, receive in _universe(pools):
            counts["universe"] += 1
            key = (member.user_id, give, receive)
            if key in evaluated:
                continue
            # Never evaluated: a 2-asset side whose parents (the 1x1s it extends) all failed an
            # incurable reason was never generated; anything else was cut by the stream budget.
            parents = ([(member.user_id, frozenset((g,)), receive) for g in give] if len(give) == 2
                       else [(member.user_id, give, frozenset((r,))) for r in receive])
            states = [evaluated.get(parent) for parent in parents]
            if all(s is not None and s != "eligible" and s not in curable for s in states):
                counts["not_expanded"] += 1
            else:
                counts["search_budget"] += 1
    if counts["universe"] - counts["not_expanded"] - counts["search_budget"] != len(evaluated):
        raise RuntimeError("evaluated candidates fall outside the pooled universe")
    counts.update(reasons)
    eligible = sum(r == "eligible" for r in evaluated.values())
    counts["duplicate"] = eligible - len(survivors)
    for card in survivors:
        reason = rules.reason(card.target_user_id, card.give_player_ids, card.receive_player_ids)
        if reason is not None:
            counts[reason] += 1
    counts["admitted"] = len(deck)
    counts["possible_full_roster"] = full_roster
    counts["teams"] = len(search.members) + 1
    counts["generator_version"] = module.VERSION
    return deck, counts


def compute(generate, context, rules, *, after=(), check=None) -> dict:
    """The waterfall for one request. ``after``: ``[(catalog key, stage)]`` in the worker's
    order, each ``stage(cards) -> cards`` (None: the stage is live but cannot be replayed
    without side effects; its row says "not measured"). Returns aggregates only."""
    started_at = perf_counter()
    deck, counts = diagnostic_solve(generate, context, rules, check=check)
    removed = {key: counts.get(key, 0) for key in rule_catalog.ENGINE_REASONS}
    removed.update(not_expanded=counts["not_expanded"], search_budget=counts["search_budget"],
                   duplicate=counts["duplicate"])
    unknown = {k for k in counts if k not in removed and k not in (
        "universe", "admitted", "possible_full_roster", "teams", "generator_version")}
    if unknown:
        raise RuntimeError(f"engine reasons missing from the rule catalog: {sorted(unknown)}")

    measured = {}
    generated = {id(c) for c in deck}
    cards = list(deck)
    for key, stage in after:
        if rule_catalog.BY_KEY[key].stage != rule_catalog.AFTER:
            raise ValueError(f"{key} is not an after-the-deck stage")
        if stage is None:
            measured[key] = False
            continue
        before = {id(c) for c in cards} & generated
        cards = list(stage(cards))
        after_ids = {id(c) for c in cards}
        removed[key] = removed.get(key, 0) + len(before - after_ids)
        measured[key] = True
    served_generated = sum(id(c) in generated for c in cards)
    added = len(cards) - served_generated

    rows, remaining = [], counts["universe"]
    started = counts["universe"]
    for rule in rule_catalog.waterfall_rules():
        if rule.stage == rule_catalog.AFTER and rule.key not in measured:
            status = "not_run"
        elif measured.get(rule.key) is False:
            status = "not_measured"
        else:
            status = "measured"
        n = removed.get(rule.key, 0)
        rows.append({"key": rule.key, "name": rule.name, "description": rule.description,
                     "stage": rule.stage, "kind": rule.kind, "status": status,
                     "started": remaining, "removed": n, "remaining": remaining - n,
                     "share_of_started": round(n / started, 6) if started else 0.0,
                     "share_of_reaching": round(n / remaining, 6) if remaining else 0.0})
        remaining -= n
    if remaining != served_generated:
        raise RuntimeError("waterfall rows do not sum to the served deck")
    return {"version": VERSION, "catalog_version": rule_catalog.VERSION,
            "generator_version": counts["generator_version"],
            "rules_version": getattr(rules, "VERSION", None) or _rules_version(),
            "basis": "diagnostic_full_solve", "started_definition": STARTED_DEFINITION,
            "teams": counts["teams"], "possible_full_roster": counts["possible_full_roster"],
            "started": started, "served_generated": served_generated, "added": added,
            "served": served_generated + added, "admitted": counts["admitted"],
            "stages": [{"stage": s, "removed": sum(r["removed"] for r in rows if r["stage"] == s)}
                       for s in rule_catalog.STAGES],
            "rows": rows, "elapsed_ms": round((perf_counter() - started_at) * 1000, 1)}


def _rules_version():
    from .deck_rules import VERSION as RULES
    return RULES


def server_stages(server, *, context, rules, league, league_id, significance_capture,
                  lineup_slots=None) -> list:
    """The worker's after-the-deck stages for an organic owner-only rules-first deck, built from
    the worker's own functions on ``server`` (the module, passed in so this file never imports
    it), in ``_run_trade_job``'s order, each without side effects:

    likes-you and standing offers (``emit_exposure`` off, a private card registry, no on-demand
    proof: proving attaches evidence and never changes selection); decline-window suppression
    (a private mutation sink, so the one retest grant is not consumed); revised offers (building
    them writes, so the row is "not measured" when ``trade.next_move`` is on); owner
    revalidation; roster and personal-market policy (dark today: "not measured" if switched on);
    the significance re-check; dispositions (read-only); the quality re-check.
    ``context`` is the job's owner context, ``league`` the job's league object."""
    from types import SimpleNamespace
    from . import deck_quality
    user_id = context["user_id"]
    prefs = (context.get("manager_preferences") or {}).get(user_id) or {}
    inbound = set()
    stages = []
    if server._likes_you_enabled() and league_id != "league_demo":
        def likes_you(cards):
            shim = SimpleNamespace(
                _past_decision_keys=set(context.get("past_decision_keys") or ()), _trade_cards={},
                _players=context["players"], _organic_like_cap_drops=0, _standing_offer_cap_drops=0,
                _r4_excluded_keys=set())
            return server._inject_likes_you_cards(
                cards, shim, user_id, league_id=league_id, league=league,
                user_roster=context["user_roster"], seed_map=context["seed_elo"],
                untouchable_ids=set(prefs.get("untouchables") or ()) or None,
                not_interested_ids=set(prefs.get("not_interested") or ()) or None,
                exclusion_keys=set(context.get("exclusion_keys") or ()) or None,
                avoid_positions=set(prefs.get("avoid_positions") or ()) or None,
                significance_inbound_keys=inbound, emit_exposure=False)
        stages.append(("likes_you_added", likes_you))
    if server._deck_fatigue_enabled() and league_id != "league_demo":
        def decline(cards):
            kept, _note, _retest = server._apply_deck_suppression(
                cards, user_id=user_id, league_id=league_id, seed_map=context["seed_elo"],
                mutation_sink=[])
            return kept
        stages.append(("decline_window", decline))
    if server.is_enabled("trade.next_move") and league_id != "league_demo":
        stages.append(("revised_offer_replaced", None))

    def revalidate(cards):
        owner = [c for c in cards if getattr(c, "owner_evaluation", None) is not None]
        valid = {id(c) for c in server._owner_cards_valid(owner, context)} if owner else set()
        return [c for c in cards if getattr(c, "owner_evaluation", None) is None or id(c) in valid]
    stages.append(("revalidation", revalidate))
    if getattr(server.FLAGS, "trade_roster_protection", False) or getattr(
            server.FLAGS, "trade_mutual_benefit_v1", False):
        stages.append(("roster_protection", None))
    if server._trade_policy.policy_enabled() or getattr(server.FLAGS, "trade_mutual_benefit_v1", False):
        stages.append(("market_policy", None))

    def significance(cards):
        kept, _, _ = server._evaluate_trade_significance(
            cards, capture=significance_capture, players=context["players"],
            user_elo=context["user_elo"], seed_elo=context["seed_elo"],
            scoring_format=context.get("scoring_format", "1qb_ppr"), inbound_keys=inbound,
            user_sources=context.get("user_sources"))
        return kept
    stages.append(("significance_recheck", significance))
    stages.append(("dispositions", lambda cards: server._project_trade_dispositions(
        cards, user_id, league_id)))
    if rules.quality:
        slots = lineup_slots if lineup_slots is not None else server._league_lineup_slots(league_id)
        stages.append(("quality_recheck", lambda cards: deck_quality.filter_deck(
            cards, viewer_id=rules.viewer_id, market=rules.market, position=rules.position,
            rosters=rules.rosters, lineup_slots=slots)[0]))
    return stages
