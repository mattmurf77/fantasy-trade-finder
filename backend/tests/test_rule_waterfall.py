"""The decline waterfall (founder review, use case 2; rule-waterfall-design.md §3-§4).

Sums: on synthetic 5- and 12-team leagues (revisions 1 and 2) and the 12-team fixture league
(revision 2, and revision 5 with its real season evidence), started - sum(removed) = served,
each candidate counted once; rows follow the catalog's waterfall order; stage totals add up.

Honesty: the deck the waterfall's diagnostic ranks is the rules-first deck the worker serves
(``trade_fast_deck.serve``), card for card and proof for proof; and through the real worker
(``server._run_trade_job`` with production's flags: likes-you, decline suppression,
significance enforced, quality filters), the waterfall's served count, computed inside the job
at construction time with the worker's own downstream functions, equals the size of the deck
the job publishes, with two liked trades added (one with no centerpiece, which the job exempts from the
significance re-check), a liked trade flagged in place and a declined near-copy suppressed.

Neutrality (instrumentation, not a fork): the evaluator rows equal the counts the generator's
own report gives without the recorder; running the waterfall changes neither the request's
inputs nor the served deck built after it; no engine module is modified (the freeze/golden
suites run unchanged).

Also: the search budget's row (budget forced low) keeps the sums; after-the-deck stages count
only the generated cards they remove and report additions separately; a live stage that
cannot be replayed is "not measured"; out-of-scope requests are refused; the output is
aggregate-only (no player, user or league id).
"""
import copy
import functools
import json

import pytest

from backend import feature_flags as ff, rule_catalog as rc, rule_waterfall as rw, server
from backend import trade_fast_deck as fast, trade_gen_bilateral as bilateral
from backend import trade_gen_bilateral_candidate as candidate, trade_gen_bilateral_season as season
from backend.eval import served_deck_replay as replay, synthetic_league
from backend.tests import test_trade_gen_bilateral_season as season_fixture
from backend.tests.test_trade_fast_deck import (  # noqa: F401  (fixtures)
    GENERATED, LIKED, LEAGUE, ME, OPP, harness, like, owner_harness, production, revised, run)

_CACHE = {}


def world(name):
    """(generate, context, request) for a named world, cached."""
    if name not in _CACHE:
        if name.startswith("fixture"):
            context, slots = season_fixture.world("contender"), list(season_fixture.SLOTS)
            generate = candidate.generate_bilateral_trades
            if name == "fixture-r5":
                context = {**context, "season_evidence": season_fixture.evidence()}
                generate = season.generate_bilateral_trades
        else:
            module, teams = {"r2-5": (candidate, 5), "r2-12": (candidate, 12), "r1-5": (bilateral, 5)}[name]
            context, slots = synthetic_league.build(teams=teams, seed=7), replay.DEFAULT_SLOTS
            generate = module.generate_bilateral_trades
        _CACHE[name] = generate, context, replay.Request(context, slots)
    return _CACHE[name]


def waterfall(name, **kwargs):
    generate, context, request = world(name)
    return rw.compute(generate, context, request.rules(), **kwargs)


def check_sums(out):
    rows = out["rows"]
    assert [r["key"] for r in rows] == [r.key for r in rc.waterfall_rules()]
    assert out["started"] - sum(r["removed"] for r in rows) == out["served_generated"]
    assert out["served"] == out["served_generated"] + out["added"]
    remaining = out["started"]
    for row in rows:
        assert row["started"] == remaining and row["remaining"] == remaining - row["removed"] >= 0
        remaining = row["remaining"]
    assert sum(s["removed"] for s in out["stages"]) == out["started"] - out["served_generated"]


@pytest.mark.parametrize("name", ["r2-5", "r2-12", "r1-5", "fixture-r2", "fixture-r5"])
def test_rows_sum_to_the_served_deck(name):
    out = waterfall(name)
    check_sums(out)
    removed = {r["key"]: r["removed"] for r in out["rows"]}
    assert out["started"] > out["served"] >= 30
    assert removed["market_floor"] > 0 and sum(removed[k] for k in ("breakup", "filler", "redundant")) > 0
    expected = {"r1-5": bilateral.VERSION, "fixture-r5": season.VERSION}.get(name, candidate.VERSION)
    assert out["generator_version"] == expected


def deck_of(name):
    generate, context, request = world(name)
    deck, counts = rw.diagnostic_solve(generate, context, request.rules())
    return deck, counts


@pytest.mark.parametrize("name", ["r2-5", "r2-12", "r1-5", "fixture-r5"])
def test_the_diagnostic_ranks_the_deck_the_worker_serves(name):
    generate, context, request = world(name)
    deck, counts = deck_of(name)
    built, _, info = fast.serve(generate, context, request.rules())
    assert info["path"] == "page"
    assert [fast._identity(c) for c in deck] == [fast._identity(c) for c in built]
    assert [c.owner_evaluation.as_dict() for c in deck] == [c.owner_evaluation.as_dict() for c in built]
    assert counts["admitted"] == len(built)


@pytest.mark.parametrize("name", ["r2-5", "fixture-r5"])
def test_evaluator_rows_equal_the_generators_own_counts(name):
    """The recorder adds nothing: the un-instrumented full solve over the same universe reports
    the same per-reason rejections the waterfall shows."""
    generate, context, request = world(name)
    config = {**(context.get("config") or {}), **rw._DIAGNOSTIC_BUDGETS}
    _, report = generate(**{**context, "config": config})
    out = waterfall(name)
    rows = {r["key"]: r["removed"] for r in out["rows"]}
    assert {k: rows[k] for k in report.as_dict()["rejections"]} == report.as_dict()["rejections"]
    evaluated = report.as_dict()["evaluated"]
    assert out["started"] - rows["not_expanded"] - rows["search_budget"] == evaluated


def test_running_the_waterfall_changes_no_input_and_no_served_deck():
    generate, context, request = world("r2-5")
    before = fast.serve(generate, context, request.rules())[0]
    snapshot = copy.deepcopy({k: v for k, v in context.items() if k not in ("players", "league")})
    rosters = [list(m.roster) for m in context["league"].members]
    waterfall("r2-5")
    after = fast.serve(generate, context, request.rules())[0]
    assert {k: v for k, v in context.items() if k not in ("players", "league")} == snapshot
    assert [list(m.roster) for m in context["league"].members] == rosters
    assert [fast._identity(c) for c in after] == [fast._identity(c) for c in before]
    assert ([(c.give_value, c.receive_value, c.fairness_score) for c in after]
            == [(c.give_value, c.receive_value, c.fairness_score) for c in before])


def test_the_search_budget_row_keeps_the_sums(monkeypatch):
    monkeypatch.setattr(rw, "_DIAGNOSTIC_BUDGETS", {"owner_total_budget": 5000.0, "owner_pair_budget": 1500.0})
    out = waterfall("r2-5")
    check_sums(out)
    budget = next(r for r in out["rows"] if r["key"] == "search_budget")
    assert budget["removed"] > 0


def test_after_stages_count_removals_and_report_additions_separately():
    extra = []

    def decline(cards):
        return cards[3:]

    def likes(cards):
        added = [copy.copy(cards[0]), copy.copy(cards[1])]
        extra.extend(added)
        return added + cards

    out = waterfall("r2-5", after=[("likes_you_added", likes), ("decline_window", decline),
                                   ("revised_offer_replaced", None)])
    check_sums(out)
    rows = {r["key"]: r for r in out["rows"]}
    assert rows["decline_window"]["removed"] == 1        # the two added copies took two of the three
    assert len(extra) == 2 and out["added"] == 0         # both additions were dropped again
    assert rows["revised_offer_replaced"]["status"] == "not_measured"
    assert rows["revalidation"]["status"] == "not_run" and rows["market_floor"]["status"] == "measured"
    with pytest.raises(ValueError):
        waterfall("r2-5", after=[("filler", lambda cards: cards)])


def test_refuses_requests_outside_its_scope():
    generate, context, request = world("r2-5")
    for extra in ({"pinned_give_players": ["p00_00"]}, {"opponent_user_id": "u01"}, {"trade_intent": "upgrade"}):
        with pytest.raises(rw.Unsupported):
            rw.compute(generate, {**context, **extra}, request.rules())
    with pytest.raises(rw.Unsupported):
        rw.compute(lambda **kw: None, context, request.rules())


def test_output_is_aggregate_only():
    generate, context, _ = world("fixture-r2")
    text = json.dumps(waterfall("fixture-r2"))
    ids = set(context["players"]) | {m.user_id for m in context["league"].members} | {
        context["user_id"], context["league"].league_id}
    assert not [i for i in ids if f'"{i}"' in text]


# ── the worker: the waterfall's served count is the deck the job publishes ──────────────

@pytest.mark.parametrize("min_tier", [2.0, 1.0])
def test_served_count_equals_the_workers_published_deck(production, monkeypatch, min_tier):
    """Production's downstream (likes-you, decline suppression, significance enforced, quality
    filters), measured at construction time inside the same job with the worker's own
    functions, and compared with what the job publishes. ``min_tier`` 1 (first-round tier
    only) makes significance reject the liked trade, which the job exempts as inbound."""
    ff._flags_cache["deck.rules_first"] = True
    from backend import trade_service as ts
    ts._cfg["significance_player_min_tier"] = min_tier
    like("calcq_liked", LIKED)            # fails a deck rule: added on top, proven on demand
    like("calcq_generated", GENERATED)    # the generator builds it: flagged in place
    like("calcq_junk", (["b5"], ["a3"]))  # no centerpiece: kept only because the job exempts likes
    contexts = []
    real = fast.serve

    def capture(generate, context, rules, *, check=None):
        contexts.append(context)
        return real(generate, context, rules, check=check)
    monkeypatch.setattr(fast, "serve", functools.wraps(real)(capture))
    first = run(monkeypatch)
    # Decline a generated (not liked) card's package: its near-copies are suppressed next time.
    declined = next(c for c in first["cards"] if c["trade_id"].startswith("bilateral_") and not c.get("likes_you"))
    ids = lambda side: [p["id"] if isinstance(p, dict) else p for p in declined[side]]
    server._save_decline_suppression(ME, LEAGUE, ids("give"), ids("receive"), contexts[0]["seed_elo"])

    measured = []

    def measure(generate, context, rules, *, check=None):
        stages = rw.server_stages(server, context=context, rules=rules, league=context["league"],
                                  league_id=LEAGUE, significance_capture=server._capture_trade_significance())
        measured.append(rw.compute(generate, context, rules, after=stages))
        return real(generate, context, rules, check=check)
    monkeypatch.setattr(fast, "serve", functools.wraps(real)(measure))
    job = run(monkeypatch)
    (out,) = measured
    check_sums(out)
    rows = {r["key"]: r for r in out["rows"]}
    assert out["served"] == len(job["cards"])
    assert out["added"] == sum(c["trade_id"].startswith("likesyou_") for c in job["cards"]) == 2
    assert rows["decline_window"]["status"] == "measured" and rows["decline_window"]["removed"] >= 1
    assert len(first["cards"]) - len(job["cards"]) == rows["decline_window"]["removed"]
    assert rows["significance_recheck"]["removed"] == rows["quality_recheck"]["removed"] == 0
    assert rows["revalidation"]["removed"] == rows["dispositions"]["removed"] == 0
