"""Rules-first deck construction: what the user is SERVED (ADR-030; fast-deck-v2 design §5.3, §6).

The 2026-11-11 incident passed every generator-level parity test and served 2
cards: the tests compared generator output, never the served deck. These
compare the deck after every downstream stage that runs offline (discovery
significance, the bilateral presentment, ``deck_quality.filter_deck`` with its
repeat cap; the stand-in is ``backend/eval/served_deck_replay.Request``), on
synthetic leagues:

- acceptance (invariants 1, 2, 4): the served deck from the page path equals
  the served deck from the gated full solve, card for card and in order, and
  as a SET equals today's pipeline (full solve, then the filters), same count;
- the downstream copies of the rules remove nothing from a rules-first deck
  (invariant 3);
- no thin deck by placement: a league where ~90% of the generator's first 150
  cards fail the rules serves exactly today's full count (the old 150-card
  fast deck served a handful), and the repeat cap's first 30 reach deep into
  the inventory yet match between paths;
- one definition per rule: ``DeckRules`` (the server's, through
  ``server._rules_first_deck_rules``) agrees card by card with
  ``_evaluate_trade_significance`` and ``deck_quality.filter_deck`` on
  generated inventories, and the eval tool's offline rules agree with the
  server's;
- the page search to exhaustion equals the gated full solve, which equals the
  generator's ranker over the admitted survivors, for both revisions;
- ``PageSearch(admit=None)`` is unchanged and an admit-everything predicate
  changes no card or proof;
- "Match strength" (the clients' mismatch_score / 300 x 100) does not move
  with the rollout: every rules-first card reads 100, what nearly every card
  today's full solve serves reads, whatever the inventory size or position;
  composite_score, the ordering key, is untouched;
- large leagues (incumbent budgets bind): the page builds the whole admitted
  universe, a superset of the budgeted gated solve, equal to it with the
  budgets lifted; protected cards always pass the gate;
- revision 5 (WI-8, invariant I18): with usable evidence, page path = gated full
  solve = ranker over the admitted survivors, card for card and proof for proof,
  and a finite page's first k = the gated deck's first k, over the fixture league
  (12 teams, two board seeds, stage 2) and synthetic 12/14/16-team leagues, for
  All-in, Contending, Rebuilding and Tanking viewers; without usable evidence or
  for a Not-sure viewer, revision 2's rules-first deck; a negative season input
  falls back to the gated solve. Sabotages (red, then green on revert): bound a
  season lineup from ``_lineup_assets`` (5 synthetic worlds miss cards at k = 5
  or 30; the fixture worlds do not reach it: their real evidence never puts a
  season gain above the dynasty bound where it decides the stop); ignore the shed
  term in the bounds (4 worlds red).
"""
import copy

import pytest

from backend import deck_quality as dq, server, trade_fast_deck as fast, trade_first_page as fp
from backend import trade_gen_bilateral as bilateral, trade_gen_bilateral_candidate as candidate
from backend import season_value as sv, trade_gen_bilateral_season as season, trade_service as ts
from backend.eval import served_deck_replay as replay, synthetic_league
from backend.tests import test_trade_gen_bilateral_season as season_fixture
from backend.tests.test_trade_first_page import SEASON_SLOTS, season_evidence

ENFORCE = replay.ENFORCE
_CACHE = {}


def identities(cards):
    return [fast._identity(c) for c in cards]


def admitted(rules, cards):
    return [c for c in cards if rules.admits(c.target_user_id, c.give_player_ids, c.receive_player_ids)]


def world(module, teams, seed, **extra):
    """(request, today's full solve, rules-first deck, gated deck), cached per world."""
    key = module.__name__, teams, seed, tuple(sorted(extra))
    if key not in _CACHE:
        context = {**synthetic_league.build(teams=teams, seed=seed), **extra}
        request = replay.Request(context, replay.DEFAULT_SLOTS)
        full, _ = module.generate_bilateral_trades(**context)
        built, _, info = fast.serve(module.generate_bilateral_trades, context, request.rules())
        gated, _ = fast.gated_full(module.generate_bilateral_trades, context, request.rules())
        assert info["path"] == "page"
        _CACHE[key] = request, full, built, gated
    return _CACHE[key]


def presented(module):
    return module is candidate   # production runs the bilateral presentment for revision 2


WORLDS = [(candidate, 5, 7), (candidate, 12, 7), (candidate, 12, 11), (bilateral, 5, 7), (bilateral, 12, 7)]


@pytest.mark.parametrize("module,teams,seed", WORLDS)
def test_served_deck_page_equals_gated_and_same_set_as_today(module, teams, seed):
    request, full, built, gated = world(module, teams, seed)
    p = presented(module)
    page_served, page_counts = request.served(built, presentment=p)
    gated_served, _ = request.served(gated, presentment=p)
    today, today_counts = request.served(full, presentment=p)
    assert identities(page_served) == identities(gated_served)                 # invariant 1
    assert len(page_served) == len(today) >= 30                                # invariant 4
    assert set(identities(page_served)) == set(identities(today))              # invariant 2
    assert sum(today_counts[k] for k in ("significance", "breakup", "filler", "redundant")) > 0
    assert all(page_counts[k] == 0 for k in ("significance", "breakup", "filler", "redundant"))  # invariant 3


def test_served_deck_with_a_trade_block_preference():
    roster = synthetic_league.build(teams=12)["user_roster"]
    preferences = {"me": {"trade_block": roster[1:9:2] + roster[-2:], "untouchables": [roster[0]]}}
    request, full, built, gated = world(candidate, 12, 7, manager_preferences=preferences)
    page_served, _ = request.served(built)
    assert identities(page_served) == identities(request.served(gated)[0])
    assert set(identities(page_served)) == set(identities(request.served(full)[0]))


def test_no_thin_deck_by_placement():
    """The incident's shape: most of the generator's first 150 cards fail the
    rules (bench padding), so a 150-card page served a handful."""
    request, full, built, _ = world(candidate, 5, 7)
    rules = request.rules()
    failing = sum(not rules.admits(c.target_user_id, c.give_player_ids, c.receive_player_ids)
                  for c in full[:150])
    assert failing >= .85 * 150
    old_fast_deck, _ = request.served(full[:150])
    served, _ = request.served(built)
    assert len(served) == len(request.served(full)[0]) >= 30
    assert len(old_fast_deck) < len(served) / 4


def test_the_repeat_cap_window_reaches_deep_and_still_matches():
    """The cap defers repeats past the first 30, so the served first 30 depend on
    cards far down the admitted inventory; both paths must agree on them."""
    request, _, built, gated = world(candidate, 12, 11)
    served, counts = request.served(built)
    assert counts["deferred"] > 0
    position = {fast._identity(c): i for i, c in enumerate(built)}
    assert max(position[i] for i in identities(served[:30])) >= 30
    assert identities(served[:30]) == identities(request.served(gated)[0][:30])


@pytest.mark.parametrize("module,teams,seed", WORLDS[:2] + WORLDS[3:4])
def test_page_to_exhaustion_equals_gated_equals_rank_of_admitted(module, teams, seed):
    request, full, built, gated = world(module, teams, seed)
    assert identities(built) == identities(gated)
    assert [c.owner_evaluation.as_dict() for c in built] == [c.owner_evaluation.as_dict() for c in gated]
    assert identities(gated) == identities(module._rank(admitted(request.rules(), full)))


@pytest.fixture
def server_rules(monkeypatch):
    """The worker's own DeckRules for a synthetic request (quality on, significance enforced)."""
    monkeypatch.setattr(server, "_deck_quality_filters_enabled", lambda: True)
    monkeypatch.setattr(server, "_league_lineup_slots", lambda league_id: list(replay.DEFAULT_SLOTS))
    def build(context, capture=ENFORCE):
        return server._rules_first_deck_rules(
            viewer_team="me", league=context["league"], user_roster=context["user_roster"],
            seed_map=context["seed_elo"], players_dict=context["players"], league_id="L",
            significance_capture=capture, user_elo=context["user_elo"], scoring_format="1qb_ppr",
            user_sources=None)
    return build


@pytest.mark.parametrize("module", [bilateral, candidate])
def test_each_rule_is_the_downstream_gates_definition_card_by_card(server_rules, module):
    request, full, _, _ = world(module, 12, 7)
    context = request.context
    rules = server_rules(context)
    seen = set()
    for card in full:
        kept, _, _ = server._evaluate_trade_significance(
            [card], capture=ENFORCE, players=context["players"], user_elo=context["user_elo"],
            seed_elo=context["seed_elo"], scoring_format="1qb_ppr")
        if not kept:
            want = "significance"
        else:
            out, counts = dq.filter_deck([card], viewer_id="me", market=request.market,
                                         position=request.position, rosters=request.rosters,
                                         lineup_slots=replay.DEFAULT_SLOTS)
            want = next((k for k in ("breakup", "filler", "redundant") if counts[k]), None)
            assert bool(out) == (want is None)
        got = rules.reason(card.target_user_id, card.give_player_ids, card.receive_player_ids)
        assert got == want, (card.give_player_ids, card.receive_player_ids)
        seen.add(want)
        # The offline replay tool applies the same definition.
        assert request.rules().reason(card.target_user_id, card.give_player_ids, card.receive_player_ids) == want
    assert seen == {None, "significance", "breakup", "filler", "redundant"}


def test_no_live_rule_builds_no_rules(server_rules, monkeypatch):
    context = synthetic_league.build(teams=5)
    monkeypatch.setattr(server, "_deck_quality_filters_enabled", lambda: False)
    assert server_rules(context, capture=(1, "significance-v1", "second", True)) is None
    assert server_rules(context).quality is False and server_rules(context).significance is not None


def test_protected_cards_always_pass_the_gate():
    request, full, _, _ = world(candidate, 5, 7)
    rules = request.rules()
    failing = next(c for c in full if not rules.admits(c.target_user_id, c.give_player_ids, c.receive_player_ids))
    assert not rules.admits_card(failing)
    for attr in dq.PROTECTED_ATTRS:
        protected = copy.copy(failing)
        setattr(protected, attr, True)
        assert rules.admits_card(protected), attr
        assert dq.filter_deck([protected], viewer_id="me", market=request.market, position=request.position,
                              rosters=request.rosters, lineup_slots=replay.DEFAULT_SLOTS)[0] == [protected]


def test_admit_none_is_unchanged_and_admitting_everything_changes_no_card():
    context = synthetic_league.build(teams=5, ranked_opponents=2)
    plain, plain_report = fp.PageSearch(generator=candidate, **context).take(40)
    everything, report = fp.PageSearch(generator=candidate, admit=lambda *a: True, rules_version="x",
                                       **context).take(40)
    assert identities(plain) == identities(everything)
    assert [c.owner_evaluation.as_dict() for c in plain] == [c.owner_evaluation.as_dict() for c in everything]
    data, plain_data = report.as_dict(), plain_report.as_dict()
    assert not {"rules_version", "rules_rejected", "rules_unheld"} & set(plain_data)
    assert (data.pop("rules_version"), data.pop("rules_rejected"), data.pop("rules_unheld")) == ("x", 0, 0)
    data.pop("elapsed_ms"), plain_data.pop("elapsed_ms")
    assert data == plain_data


def test_a_large_league_builds_the_whole_admitted_universe():
    """16 teams: the incumbent's 60,000-evaluation budget binds, so its full solve
    is truncated. The page covers the un-budgeted universe (no silent cap); with
    the budgets lifted, the gated solve builds exactly the same deck."""
    context = synthetic_league.build(teams=16)
    request = replay.Request(context, replay.DEFAULT_SLOTS)
    built, _, info = fast.serve(candidate.generate_bilateral_trades, context, request.rules())
    assert (info["path"], info["budgets_bind"]) == ("page", True)
    budgeted, _ = fast.gated_full(candidate.generate_bilateral_trades, context, request.rules())
    assert set(identities(budgeted)) <= set(identities(built))
    lifted = {**context, "config": {**ts._cfg, "owner_total_budget": 120000}}
    unbudgeted, _ = fast.gated_full(candidate.generate_bilateral_trades, lifted, request.rules())
    assert identities(unbudgeted) == identities(built)


def strength(card):
    """What the app shows as Match strength (mobile/src/api/trades.ts)."""
    return min(100.0, max(0.0, card.mismatch_score / 300 * 100))


def test_match_strength_is_constant_on_rules_first_cards():
    """Operator 2026-11-11: the rollout does not visibly move the bar. Every
    rules-first card reads 100, deep in a long inventory too (a 466-card deck
    on the old position scale read 0% past card 300)."""
    small, large = world(candidate, 5, 7), world(candidate, 12, 7)
    assert len(small[2]) != len(large[2]) and len(large[2]) > 300
    for _, full, built, _ in (small, large):
        assert {strength(c) for c in built} == {100.0} == {strength(full[0])}
        assert {c.mismatch_score for c in built} == {fast.MATCH_SCALE}
        # The full solve's served cards read 100 but for its last 300 emitted.
        assert all(strength(c) == 100.0 for c in full[:len(full) - 300])
        assert [c.composite_score for c in built] == [float(len(built) - i) for i in range(len(built))]


# ── Revision 5 (WI-8, invariant I18): the season layer on the rules-first path ──
# "fixture": the WI-1 12-team league with its real captured evidence (board noise
# seeded per ``seed``, as test_trade_gen_bilateral_season builds it). "synthetic":
# 12, 14 and 16-team synthetic leagues with constructed evidence
# (``test_trade_first_page.season_evidence``: noisy ppg, empty slots, starters below
# the free-agent level). 16 teams lift the incumbent's budgets so the gated solve
# covers the page's universe (see test_a_large_league_builds_the_whole_admitted_universe).

_SEASON_WORLDS = {}


def season_world(league, teams, seed, outlook, matching=0.0, state="usable", label_fit=1.0):
    """(request, today's full solve, rules-first deck, its info, gated deck), cached.
    ``league``: "fixture" (12 teams) or "synthetic". ``label_fit``: the viewer's label
    fit (``season_viewer_label_fit``, 2026-11-12)."""
    key = league, teams, seed, outlook, matching, state, label_fit
    if key not in _SEASON_WORLDS:
        if league == "fixture":
            context, slots = season_fixture.world(outlook, seed=seed), list(season_fixture.SLOTS)
            evidence = season_fixture.evidence()
        else:
            context, slots = synthetic_league.build(teams=teams, seed=seed, viewer_outlook=outlook), SEASON_SLOTS
            evidence = season_evidence(context, seed)
        evidence = {"usable": evidence, "absent": None, "unavailable": sv.unavailable("stale")}[state]
        config = {"season_partner_matching": matching, "season_viewer_label_fit": label_fit,
                  **({"owner_total_budget": 200000} if teams >= 16 else {})}
        context = {**context, "season_evidence": evidence, "config": config}
        request = replay.Request(context, slots)
        full, _ = season.generate_bilateral_trades(**context)
        built, _, info = fast.serve(season.generate_bilateral_trades, context, request.rules())
        gated, _ = fast.gated_full(season.generate_bilateral_trades, context, request.rules())
        _SEASON_WORLDS[key] = request, full, built, info, gated
    return _SEASON_WORLDS[key]


_OUTLOOKS = ("championship", "contender", "rebuilder", "jets")
_I18 = ([("fixture", 12, 0, o, 0.0) for o in _OUTLOOKS]
        + [("fixture", 12, 1, "championship", 0.0), ("fixture", 12, 1, "jets", 0.0)]
        + [("fixture", 12, 0, "championship", 1.0), ("fixture", 12, 0, "jets", 1.0)]
        + [("synthetic", 12, 1, "championship", 0.0), ("synthetic", 12, 2, "contender", 0.0)]
        + [("synthetic", 14, 3, o, 0.0) for o in _OUTLOOKS]
        + [("synthetic", 16, 5, "contender", 0.0), ("synthetic", 16, 5, "rebuilder", 0.0)])
_I18 = ([(*case, 1.0) for case in _I18]
        # The viewer's label fit (2026-11-12): more Rebuilding / Tanking seeds, and off.
        + [("fixture", 12, 1, "rebuilder", 0.0, 1.0), ("synthetic", 12, 6, "jets", 0.0, 1.0),
           ("synthetic", 12, 7, "rebuilder", 0.0, 1.0), ("fixture", 12, 0, "jets", 0.0, 0.0)])


@pytest.mark.parametrize("league,teams,seed,outlook,matching,label_fit", _I18)
def test_revision_5_page_equals_gated_equals_rank_of_admitted(league, teams, seed, outlook, matching, label_fit):
    """I18: with usable evidence, for All-in, Contending, Rebuilding and Tanking viewers
    (and stage 2), the page path to exhaustion = the gated full solve = revision 5's
    ranker over the admitted survivors, card for card and proof for proof; and a
    finite page's first k (where the bounds decide the stop) is the gated deck's
    first k. Rebuilding / Tanking run with the viewer's label fit on (and once off).
    Sabotages: bound a season team's lineup from ``_lineup_assets``; ignore the shed
    term in the bounds; bound a label-fit viewer's plan from ``_plan_asset``."""
    request, full, built, info, gated = season_world(league, teams, seed, outlook, matching,
                                                     label_fit=label_fit)
    assert (info["path"], info["fallback"]) == ("page", None)
    assert len(built) >= 30
    assert identities(built) == identities(gated)
    assert [c.owner_evaluation.as_dict() for c in built] == [c.owner_evaluation.as_dict() for c in gated]
    assert identities(gated) == identities(season._rank(admitted(request.rules(), full)))
    data = built[0].owner_evaluation.as_dict()
    assert data["generator_version"] == season.VERSION and data["season_signal"]["viewer"]["scored"]
    rules = request.rules()
    for k in (5, 30):
        page, report = fp.PageSearch(generator=season, admit=rules.admits, rules_version="x",
                                     **request.context).take(k)
        assert report.as_dict()["complete"] and identities(page) == identities(gated[:k])


@pytest.mark.parametrize("state,outlook", [("absent", "championship"), ("unavailable", "rebuilder"),
                                           ("usable", "not_sure")])
def test_revision_5_without_the_season_signal_builds_revision_2s_rules_first_deck(state, outlook):
    """Without usable evidence, and for a Not-sure viewer, revision 5's rules-first deck
    is revision 2's: same cards, order and terms (only the version stamp and the
    evidence record differ in the proofs)."""
    request, _, built, info, _ = season_world("fixture", 12, 0, outlook, state=state)
    context = {k: v for k, v in request.context.items() if k not in ("season_evidence", "config")}
    base, _, base_info = fast.serve(candidate.generate_bilateral_trades, context, request.rules())
    assert info["path"] == base_info["path"] == "page"
    terms = lambda cards: [(fast._identity(c), c.give_value, c.receive_value, c.fairness_score) for c in cards]
    assert terms(built) == terms(base) and len(built) >= 30
    assert {c.owner_evaluation.as_dict()["season_signal"]["evidence"]["state"] for c in built} == {
        {"absent": "absent", "unavailable": "unavailable", "usable": "usable"}[state]}


def test_revision_5_unsupported_inputs_fall_back_to_the_gated_solve():
    """A negative season input breaks the bounds' premise: the page declines
    (``unsupported_inputs:negative_season_value``, which the worker logs with its
    fallback line) and the gated full solve serves, equal to the ranker over the
    admitted survivors."""
    context = synthetic_league.build(teams=6, seed=2, viewer_outlook="jets")
    evidence = season_evidence(context, 2)
    evidence["players"][sorted(evidence["players"])[0]]["ppg"] = -2.0
    context = {**context, "season_evidence": evidence}
    request = replay.Request(context, SEASON_SLOTS)
    built, report, info = fast.serve(season.generate_bilateral_trades, context, request.rules())
    assert (info["path"], info["fallback"]) == ("gated_full", "unsupported_inputs:negative_season_value")
    full, _ = season.generate_bilateral_trades(**context)
    assert identities(built) == identities(season._rank(admitted(request.rules(), full)))
    data = report.as_dict()
    assert data["construction"] == "rules_first_gated_full" and data["season_signal"]["viewer_scored"]
