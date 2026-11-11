"""Fast deck v2: rules-first construction in the trade worker (ADR-030; fast-deck-v2 design §5-§7).

Flag ``deck.rules_first`` (code default off, shipped on). The ADR-028 flags
``trade.fast_deck`` / ``trade.fast_deck_shadow`` are retired no-ops.

Helper (``backend/trade_fast_deck.py``), on the synthetic league:
- ``serve`` builds the whole admitted inventory with the page search, and the
  same deck as the gated full solve, card for card and proof for proof;
- it declines (None) a generator without a parity suite; a pinned request, an
  unproven page (over the work limit) or a failing page falls back to the
  gated full solve and says why; a cancellation propagates;
- the page gets the module's own work limit.

Worker (``server._run_trade_job`` on the owner route harness, real generator,
isolated SQLite, deck quality filters on):
- flag off: ``deck_rules`` and ``trade_fast_deck`` are never imported, the
  generator is called once as before, the published deck is the full solve
  after the downstream filters, and the safety signature is unchanged;
- flag on: the published deck equals the deck the gated full solve publishes
  (same packages, same order, same count), the same SET as flag off, and the
  downstream quality filter removes none of the admitted cards;
- the fallback fires and logs one line when the page cannot be proven; a
  failing construction serves today's full solve; a cancellation cancels;
- pinned, opponent-scoped and intent requests, an unsupported generator (one
  info line, not a warning), and decks with no live per-card rule keep
  today's path; background sources are built rules-first too;
- the retired flags do nothing.

Worker with PRODUCTION's flag combination (``production``: likes-you, fatigue,
standing offers and suggestion telemetry on, significance enforced, fit block
on; the ``revised`` harness turns those off only to keep its decks free of
injected cards). Liked trades are an overlay evaluated after generation:
- rules-first: a liked mirror that fails a deck rule (so is not generated) is
  proven by the job's owner evaluator and reaches the top with the flag, an
  engine proof and fit context; one the evaluator finds ineligible is today's
  consensus card; a liked package the generator built is flagged in place (one
  card); an evaluator error serves today's card and never fails the job;
- the generated inventory, its report and the safety signature are the same
  whether or not a league-mate liked something;
- flag off: no on-demand proof, today's likes-you cards;
- a co-owner viewer: the rules the worker builds agree, card by card, with
  what the worker's own downstream significance gate and quality filter
  remove;
- a deck.quality_filters reload mid-job: the downstream filter follows the
  rules the job built (nothing lost, nothing double-served).
"""
import functools
import json
import logging
import sys
import time
from pathlib import Path

import pytest

import backend
from backend import database as db, feature_flags as ff, server, trade_service as ts
from backend import deck_quality as dq, trade_fast_deck as fast, trade_first_page as fp
from backend import trade_gen_bilateral as bilateral, trade_gen_bilateral_candidate as candidate
from backend import trade_gen_bilateral_r4 as revision_4
from backend import trade_gen_outlook_evidence as outlook_evidence, trade_gen_owner as owner
from backend.eval import served_deck_replay as replay, synthetic_league
from backend.tests.test_owner_generator_routes import (  # noqa: F401  (fixtures)
    harness, owner_harness, rows, ME, OPP, LEAGUE, TOKEN)
from backend.trade_work_control import TradeWorkCancelled

REPO = Path(__file__).resolve().parents[2]


def league(**overrides):
    return synthetic_league.build(teams=5, ranked_opponents=2, **overrides)


def rules(context):
    return replay.Request(context, replay.DEFAULT_SLOTS, significance=None).rules()


def identities(cards):
    return [fast._identity(card) for card in cards]


# ── helper ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module", [bilateral, candidate])
def test_serve_builds_the_whole_admitted_inventory_as_the_gated_solve_does(module):
    cards, report, info = fast.serve(module.generate_bilateral_trades, league(), rules(league()))
    gated, _ = fast.gated_full(module.generate_bilateral_trades, league(), rules(league()))
    assert info["path"] == "page" and info["fallback"] is None and info["cards"] == len(cards)
    assert len(cards) > 30 and identities(cards) == identities(gated)
    assert [c.owner_evaluation.as_dict() for c in cards] == [c.owner_evaluation.as_dict() for c in gated]
    data = report.diagnostics()
    assert data["complete"] is True and data["rules_version"] == "deck-rules-1"
    assert data["rules_rejected"] > 0 and data["generator_version"] == module.VERSION


def test_the_page_gets_the_fast_decks_own_work_limit(monkeypatch):
    seen = []
    real = fp.PageSearch
    class Recording(real):
        def __init__(self, **kwargs):
            seen.append(kwargs["max_verifications"])
            super().__init__(**kwargs)
    monkeypatch.setattr(fp, "PageSearch", Recording)
    assert fast.serve(candidate.generate_bilateral_trades, league(), rules(league()))[2]["path"] == "page"
    assert seen == [fast.MAX_VERIFICATIONS] and fast.MAX_VERIFICATIONS == 12000


@pytest.mark.parametrize("generate", [owner.generate_owner_trades, outlook_evidence.generate_bilateral_trades,
                                      revision_4.generate_bilateral_trades, lambda **kwargs: ([], None)])
def test_serve_declines_a_generator_without_a_parity_suite(generate):
    assert fast.serve(generate, league(), rules(league())) is None
    assert not fast.supported(generate)


@pytest.mark.parametrize("extra,reason", [({"pinned_give_players": ["p00_00"]}, "unsupported_request"),
                                          ({"require_all_give": True}, "unsupported_request")])
def test_an_unsupported_request_falls_back_to_the_gated_solve(extra, reason):
    context = {**league(), **extra}
    cards, _, info = fast.serve(candidate.generate_bilateral_trades, context, rules(context))
    gated, _ = fast.gated_full(candidate.generate_bilateral_trades, context, rules(context))
    assert (info["path"], info["fallback"]) == ("gated_full", reason)
    assert identities(cards) == identities(gated)


def test_an_unproven_page_falls_back_to_the_gated_solve(monkeypatch):
    monkeypatch.setattr(fast, "MAX_VERIFICATIONS", 20)
    cards, report, info = fast.serve(candidate.generate_bilateral_trades, league(), rules(league()))
    gated, _ = fast.gated_full(candidate.generate_bilateral_trades, league(), rules(league()))
    assert (info["path"], info["fallback"]) == ("gated_full", "over_limit")
    assert identities(cards) == identities(gated) and report.diagnostics()["construction"] == "rules_first_gated_full"


def test_a_failing_page_falls_back_and_a_cancellation_propagates(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("page search broke")
    monkeypatch.setattr(fast, "page", broken)
    info = fast.serve(candidate.generate_bilateral_trades, league(), rules(league()))[2]
    assert (info["path"], info["fallback"]) == ("gated_full", "error:RuntimeError")
    def cancelled():
        raise TradeWorkCancelled("inputs_changed")
    monkeypatch.undo()
    with pytest.raises(TradeWorkCancelled):
        fast.serve(candidate.generate_bilateral_trades, league(), rules(league()), check=cancelled)


# ── worker ──────────────────────────────────────────────────────────────────

@pytest.fixture
def revised(owner_harness, monkeypatch):
    """Production's shape: owner-only serving of bilateral revision 2, deck quality filters on."""
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.,
                   bakeoff_owner_only=1.)
    ff._flags_cache["deck.quality_filters"] = True
    for name in ("_deck_exploration_enabled", "_deck_first_session_enabled", "_likes_you_enabled",
                 "_suggestion_telemetry_enabled", "_deck_fatigue_enabled", "_deck_taste_enabled",
                 "_deck_diversity_enabled", "_thompson_deck_enabled"):
        monkeypatch.setattr(server, name, lambda: False)
    return owner_harness


def run(monkeypatch, *, expected="complete", **job_fields):
    job_id = "fast-deck-worker"
    job = {"job_id": job_id, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
           "started_at": time.monotonic(), "finished_at": None, "cards": [],
           "opponents_done": 0, "opponents_total": 2, "error": None,
           "fairness_threshold": .5, "outlook_value": None, "is_pinned": False,
           "owner_model": server._bakeoff.owner_arm(),
           "owner_model_version": server._bakeoff.owner_version(), **job_fields}
    monkeypatch.setitem(server._trade_jobs, job_id, job)
    server._run_trade_job(job_id, TOKEN, LEAGUE, .5, [], [], None)
    assert job["status"] == expected, job
    return job


def spy(monkeypatch, target, name, replacement=None):
    calls, real = [], getattr(target, name)
    @functools.wraps(real)  # the helper selects the page search by the generator's module
    def wrapper(*args, **kwargs):
        result = (replacement or real)(*args, **kwargs)
        calls.append(result)
        return result
    monkeypatch.setattr(target, name, wrapper)
    return calls


def package(card):
    return card["target_user_id"], tuple(p["id"] if isinstance(p, dict) else p for p in card["give"]), \
        tuple(p["id"] if isinstance(p, dict) else p for p in card["receive"])


def served(job):
    return [package(c) for c in job["cards"]]


def removed(filter_calls):
    """Cards the downstream quality filter removed (it runs once per job)."""
    (_, counts), = filter_calls
    return sum(counts[k] for k in ("breakup", "filler", "redundant"))


def messages(caplog, needle):
    return [r.getMessage() for r in caplog.records if needle in r.getMessage()]


def test_flag_defaults_off_in_code_and_ships_on():
    shipped = json.loads((REPO / "config" / "features.json").read_text())
    assert ff.DEFAULT_FLAGS["deck.rules_first"] is False and shipped["deck.rules_first"] is True
    for key in ("trade.fast_deck", "trade.fast_deck_shadow"):   # retired, still parse
        assert ff.DEFAULT_FLAGS[key] is False and shipped[key] is False


def test_flag_off_is_todays_pipeline(revised, monkeypatch):
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    filtered = spy(monkeypatch, dq, "filter_deck")
    for name in ("backend.trade_fast_deck", "backend.deck_rules"):
        monkeypatch.delitem(sys.modules, name, raising=False)
        monkeypatch.delattr(backend, name.split(".")[1], raising=False)
    job = run(monkeypatch)
    assert "backend.trade_fast_deck" not in sys.modules and "backend.deck_rules" not in sys.modules
    assert len(full_solve) == 1 and job["cards"]
    # The full solve, then the filters: the filter removed cards and its output is the deck.
    assert removed(filtered) > 0
    assert [c["trade_id"] for c in job["cards"]] == [c.trade_id for c in filtered[0][0]]
    assert "rules_first" not in job["safety_policy"]
    # Flag off, Match strength is what it always was: the full solve's position from the bottom.
    emitted = full_solve[0][0]
    assert all(c.mismatch_score == c.composite_score == float(len(emitted) - i) for i, c in enumerate(emitted))


def test_the_safety_signature_stamps_rules_first_only_when_on():
    off = server._trade_safety_signature((True, True, True), rules_first=False)
    on = server._trade_safety_signature((True, True, True), rules_first=True)
    assert "rules_first" in on and "rules_first" not in off
    assert [key for key in on if key != "rules_first"] == off
    assert "rules_first" not in server._trade_safety_signature((True, True, False), rules_first=True)


def test_flag_on_serves_the_gated_solves_deck_and_the_same_set_as_today(revised, monkeypatch, caplog):
    today = served(run(monkeypatch))
    ff._flags_cache["deck.rules_first"] = True
    built = spy(monkeypatch, fast, "serve")
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    filtered = spy(monkeypatch, dq, "filter_deck")
    with caplog.at_level(logging.INFO):
        job = run(monkeypatch)
    assert len(built) == 1 and built[0][2]["path"] == "page" and not full_solve
    page_deck = served(job)
    assert len(page_deck) == len(today) and set(page_deck) == set(today)   # same cards served
    # Guards drop nothing: the downstream copy of the rules removes no admitted card.
    assert removed(filtered) == 0
    assert not messages(caplog, "rules-first guard")
    assert len(messages(caplog, "rules-first: {")) == 1
    assert "rules_first" in job["safety_policy"]
    # Match strength is constant on rules-first cards (300 -> 100%), what today's served
    # cards read; flag off it is the generator's position from the bottom.
    assert {c["mismatch_score"] for c in job["cards"]} == {fast.MATCH_SCALE}
    # Served-deck parity: force the gated full solve; same packages, same order.
    monkeypatch.setattr(fast, "page", lambda *a, **k: (None, "over_limit"))
    assert served(run(monkeypatch)) == page_deck


def test_an_unproven_page_falls_back_with_one_log_line(revised, monkeypatch, caplog):
    ff._flags_cache["deck.rules_first"] = True
    page_deck = served(run(monkeypatch))
    monkeypatch.setattr(fast, "MAX_VERIFICATIONS", 1)
    with caplog.at_level(logging.INFO):
        job = run(monkeypatch)
    lines = messages(caplog, "rules-first")
    assert len(lines) == 1 and "page search not proven (over_limit)" in lines[0]
    assert '"path": "gated_full"' in lines[0] and served(job) == page_deck


def test_a_failing_construction_serves_todays_full_solve(revised, monkeypatch, caplog):
    today = served(run(monkeypatch))
    ff._flags_cache["deck.rules_first"] = True
    def broken(*args, **kwargs):
        raise RuntimeError("construction broke")
    monkeypatch.setattr(fast, "serve", broken)
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    with caplog.at_level(logging.INFO):
        job = run(monkeypatch)
    assert len(full_solve) == 1 and served(job) == today
    assert messages(caplog, "rules-first construction failed")


def test_a_cancellation_inside_construction_cancels_the_job(revised, monkeypatch):
    _, engine, *_ = revised
    ff._flags_cache["deck.rules_first"] = True
    def cancelled(*args, **kwargs):
        raise TradeWorkCancelled("inputs_changed")
    monkeypatch.setattr(fast, "serve", cancelled)
    job = run(monkeypatch, expected="error")
    assert job["error"] == "inputs_changed" and not job["cards"]
    assert not rows(engine, db.deck_impressions_table)


def test_background_sources_are_built_rules_first(revised, monkeypatch):
    ff._flags_cache["deck.rules_first"] = True
    built = spy(monkeypatch, fast, "serve")
    run(monkeypatch, source="replenish")
    assert len(built) == 1


def test_no_live_per_card_rule_keeps_todays_path(revised, monkeypatch):
    ff._flags_cache.update({"deck.rules_first": True, "deck.quality_filters": False})
    built = spy(monkeypatch, fast, "serve")
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    run(monkeypatch)    # significance is not enforced in this harness
    assert not built and len(full_solve) == 1


def test_an_unsupported_generator_keeps_todays_path(revised, monkeypatch, caplog):
    ff._flags_cache["deck.rules_first"] = True
    ts._cfg.update(owner_bilateral_revision_4_enabled=1.)
    full_solve = spy(monkeypatch, revision_4, "generate_bilateral_trades")
    with caplog.at_level(logging.INFO):
        run(monkeypatch, owner_model_version=server._bakeoff.owner_version())
    # Expected, so info-level: a selectable generator must not warn on every job.
    lines = [r for r in caplog.records if "rules-first" in r.getMessage()]
    assert len(full_solve) == 1 and len(lines) == 1
    assert "no rules-first construction (full solve)" in lines[0].getMessage()
    assert lines[0].levelno == logging.INFO


def test_a_pinned_request_keeps_todays_path(revised, monkeypatch):
    ff._flags_cache["deck.rules_first"] = True
    built = spy(monkeypatch, fast, "serve")
    job_id = "fast-deck-pinned"
    job = {"job_id": job_id, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
           "started_at": time.monotonic(), "finished_at": None, "cards": [], "opponents_done": 0,
           "opponents_total": 2, "error": None, "fairness_threshold": .5, "outlook_value": None,
           "is_pinned": True, "owner_model": server._bakeoff.owner_arm(),
           "owner_model_version": server._bakeoff.owner_version()}
    monkeypatch.setitem(server._trade_jobs, job_id, job)
    server._run_trade_job(job_id, TOKEN, LEAGUE, .5, ["a1"], [], None)
    assert job["status"] == "complete" and not built


def test_the_retired_fast_deck_flags_do_nothing(revised, monkeypatch):
    ff._flags_cache.update({"trade.fast_deck": True, "trade.fast_deck_shadow": True})
    monkeypatch.delitem(sys.modules, "backend.trade_fast_deck")
    monkeypatch.delattr(backend, "trade_fast_deck")
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    run(monkeypatch)
    assert "backend.trade_fast_deck" not in sys.modules and len(full_solve) == 1


def test_opponent_scoped_and_intent_requests_keep_todays_path(revised, monkeypatch):
    """No served-deck parity suite covers them (ADR-030), so they take the full solve."""
    ff._flags_cache["deck.rules_first"] = True
    built = spy(monkeypatch, fast, "serve")
    rules = spy(monkeypatch, server, "_rules_first_deck_rules")
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    for job_id, args, kwargs in (("fast-deck-opponent", (OPP,), {}),
                                 ("fast-deck-intent", (None,), {"trade_intent": "upgrade"})):
        job = {"job_id": job_id, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
               "started_at": time.monotonic(), "finished_at": None, "cards": [], "opponents_done": 0,
               "opponents_total": 2, "error": None, "fairness_threshold": .5, "outlook_value": None,
               "is_pinned": False, "owner_model": server._bakeoff.owner_arm(),
               "owner_model_version": server._bakeoff.owner_version()}
        monkeypatch.setitem(server._trade_jobs, job_id, job)
        server._run_trade_job(job_id, TOKEN, LEAGUE, .5, [], [], *args, **kwargs)
        assert job["status"] == "complete", job
    assert not built and not rules and len(full_solve) == 2


# ── production's flag combination ──────────────────────────────────────────

LIKED = (["b5", "b1"], ["a1"])        # OPP gives b5+b1 for my a1: fails "filler" for me
SYNTHESIZED = (["b1", "b2"], ["a1", "a2"])   # a 2x2: the owner evaluator's organic shapes exclude it
GENERATED = (["b1"], ["a1"])          # a1 for b1: passes the rules, the generator builds it


@pytest.fixture
def production(revised, monkeypatch):
    """``revised`` plus what production runs that it turns off: likes-you, fatigue,
    standing offers and suggestion telemetry on, significance enforced, the fit
    block on. Likes are real rows in the job's league (``like``)."""
    for name in ("_likes_you_enabled", "_deck_fatigue_enabled", "_standing_offers_enabled",
                 "_suggestion_telemetry_enabled"):
        monkeypatch.setattr(server, name, lambda: True)
    ff._flags_cache["trade.fit_first_copy"] = True
    ts._cfg["significance_mode"] = 2.
    return revised


def like(trade_id, package):
    """OPP's hand-queued like of ``package`` (their give, their receive) for ME.
    Hand-queued (D-170) skips the D-096 ladder, whose filler_ok would otherwise
    drop a filler-failing mirror before it reached the deck at all."""
    give, receive = package
    assert db.save_trade_decision(OPP, LEAGUE, trade_id, give, receive, "like",
                                  impression_id="src-" + trade_id, queue_target_user_id=ME)


def find(job, package):
    want = (OPP, tuple(sorted(package[1])), tuple(sorted(package[0])))
    found = [(i, c) for i, c in enumerate(job["cards"])
             if (c["target_user_id"], *map(tuple, map(sorted, package_of(c)))) == want]
    assert len(found) == 1, found      # never a double card
    return found[0]


def package_of(card):
    return package(card)[1:]


def test_rules_first_proves_a_liked_package_the_generator_did_not_build(production, monkeypatch, caplog):
    """A liked mirror that FAILS a deck rule is not generated rules-first; the
    likes-you step proves it with the job's owner evaluator after generation, so
    it reaches the top with the flag AND an engine proof and fit block. A liked
    package the evaluator finds ineligible stays today's consensus card."""
    _, _, _, trade_svc, _ = production
    like("calcq_liked", LIKED)
    like("calcq_synth", SYNTHESIZED)
    ff._flags_cache["deck.rules_first"] = True
    built = spy(monkeypatch, fast, "serve")
    filtered = spy(monkeypatch, dq, "filter_deck")
    with caplog.at_level(logging.INFO):
        job = run(monkeypatch)
    assert (OPP, tuple(LIKED[1]), tuple(LIKED[0])) not in identities(built[0][0])   # not generated
    index, card = find(job, LIKED)
    assert index < 2 and card["likes_you"] is True and card["trade_id"].startswith("likesyou_")
    assert card["model_arm"] == "owner_v2_bilateral" and card["generator_version"]
    assert card["mismatch_score"] == fast.MATCH_SCALE
    engine = trade_svc._trade_cards[card["trade_id"]]
    assert engine.owner_evaluation is not None and engine.owner_evaluation.matches(engine)
    assert engine.fit_context is not None and engine.owner_request_evidence is not None
    assert engine.source_like_impression_id == "src-calcq_liked"
    index, bare = find(job, SYNTHESIZED)
    assert index < 2 and bare["likes_you"] is True and bare["trade_id"].startswith("likesyou_")
    assert bare.get("model_arm") is None and bare["mismatch_score"] == 0.0     # today's card
    assert messages(caplog, "liked cards proven=1 consensus=1 errors=0")
    (_, counts), = filtered
    assert sum(counts[k] for k in ("breakup", "filler", "redundant")) == 0
    assert not messages(caplog, "rules-first guard")
    # The forced gated solve publishes the same deck.
    monkeypatch.setattr(fast, "page", lambda *a, **k: (None, "over_limit"))
    assert served(run(monkeypatch)) == served(job)


def test_flag_off_likes_are_todays(production, monkeypatch, caplog):
    """Flag off the injector gets no prover: the generated liked card is flagged in
    place, the 2x2 is today's consensus card, nothing is evaluated on demand."""
    like("calcq_liked", LIKED)
    like("calcq_synth", SYNTHESIZED)
    injector = record_kwargs(monkeypatch, server, "_inject_likes_you_cards_impl")
    with caplog.at_level(logging.INFO):
        job = run(monkeypatch)
    assert injector and all("prove" not in kwargs for kwargs in injector)
    _, card = find(job, LIKED)
    assert card["likes_you"] is True and card["trade_id"].startswith("bilateral_")
    _, bare = find(job, SYNTHESIZED)
    assert bare.get("model_arm") is None and bare["mismatch_score"] == 0.0
    assert not messages(caplog, "liked cards")


def test_rules_first_flags_a_generated_liked_card_in_place(production, monkeypatch, caplog):
    like("calcq_generated", GENERATED)
    ff._flags_cache["deck.rules_first"] = True
    with caplog.at_level(logging.INFO):
        job = run(monkeypatch)
    _, card = find(job, GENERATED)                    # one card, the engine's, flagged
    assert card["likes_you"] is True and card["trade_id"].startswith("bilateral_")
    assert not messages(caplog, "liked cards")         # nothing proven on demand


def test_the_generated_inventory_does_not_depend_on_likes(production, monkeypatch):
    ff._flags_cache["deck.rules_first"] = True
    built = spy(monkeypatch, fast, "serve")
    before = run(monkeypatch)
    like("calcq_liked", LIKED)
    like("calcq_generated", GENERATED)
    after = run(monkeypatch)
    (first, _, first_info), (second, _, second_info) = built
    assert identities(first) == identities(second)
    drop = lambda info: {k: v for k, v in info.items() if k != "ms"}
    assert drop(first_info) == drop(second_info)
    assert before["safety_policy"] == after["safety_policy"]


def test_a_failing_liked_proof_serves_todays_card(production, monkeypatch, caplog):
    like("calcq_liked", LIKED)
    ff._flags_cache["deck.rules_first"] = True
    real = server._bakeoff.owner_evaluator
    def evaluator(config=None):
        evaluate = real(config)
        def breaking(cards, **kwargs):
            if cards and cards[0].trade_id == "":       # the on-demand proof, not revalidation
                raise RuntimeError("evaluator broke")
            return evaluate(cards, **kwargs)
        return breaking
    monkeypatch.setattr(server._bakeoff, "owner_evaluator", evaluator)
    with caplog.at_level(logging.INFO):
        job = run(monkeypatch)
    _, card = find(job, LIKED)
    assert card["likes_you"] is True and card.get("model_arm") is None and card["mismatch_score"] == 0.0
    assert len(messages(caplog, "liked card proof failed (consensus card): RuntimeError")) == 1
    assert messages(caplog, "liked cards proven=0 consensus=0 errors=1")


def record_kwargs(monkeypatch, target, name):
    calls, real = [], getattr(target, name)
    @functools.wraps(real)
    def wrapper(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)
    monkeypatch.setattr(target, name, wrapper)
    return calls


def record(monkeypatch, target, name):
    """Spy on a deck stage: per call (cards in, result, which cards were protected
    when the stage ran; publication later marks served owner cards protected)."""
    calls, real = [], getattr(target, name)
    @functools.wraps(real)
    def wrapper(cards, **kwargs):
        protected = {id(c) for c in cards if dq.is_protected(c)}
        result = real(cards, **kwargs)
        calls.append((list(cards), result, protected))
        return result
    monkeypatch.setattr(target, name, wrapper)
    return calls


def test_a_co_owner_gets_the_downstream_gates_verdicts(production, monkeypatch):
    """The rules the WORKER builds (its own ``_rules_first_deck_rules`` call; the
    viewer's league identity ME, account identity a co-owner's) agree card by
    card with what the same worker's downstream significance gate and quality
    filter remove from today's full solve."""
    _, _, sess, _, _ = production
    monkeypatch.setitem(sess, "user_id", "co_owner_account")
    monkeypatch.setitem(sess, "league_user_id", ME)
    ts._cfg["significance_player_min_tier"] = 1.   # first tier only, so significance rejects too
    significance = record(monkeypatch, server, "_evaluate_trade_significance")
    quality = record(monkeypatch, dq, "filter_deck")
    run(monkeypatch)                                   # today's path: full solve, then the gates
    downstream = [c for c in significance if c[0]]
    assert len(downstream) == 1 and len(quality) == 1
    ff._flags_cache["deck.rules_first"] = True
    worker_rules = spy(monkeypatch, server, "_rules_first_deck_rules")
    run(monkeypatch)
    (rules,) = worker_rules
    assert rules.viewer_id == ME and rules.significance is not None and rules.quality
    verdicts = {}
    cards, (kept, _, _), sig_protected = downstream[0]
    filter_in, (filter_out, _), quality_protected = quality[0]
    for stage, before, after, rejecting, protected in (
            ("significance", cards, kept, {"significance"}, sig_protected),
            ("quality", filter_in, filter_out, {"breakup", "filler", "redundant"}, quality_protected)):
        survivors = {id(c) for c in after}
        for card in before:
            if id(card) in protected:
                continue
            reason = rules.reason(card.target_user_id, card.give_player_ids, card.receive_player_ids)
            assert (id(card) not in survivors) == (reason in rejecting), (stage, reason, card.give_player_ids)
            verdicts[reason] = verdicts.get(reason, 0) + 1
    assert all(verdicts.get(k, 0) > 0 for k in (None, "significance", "filler"))


def test_a_quality_filters_reload_mid_job_follows_the_jobs_rules(production, monkeypatch):
    """deck.quality_filters is captured once per rules-first job: the downstream
    filter applies the rules the construction applied, so a reload between the
    two neither drops admitted cards nor serves cards the job never filtered."""
    ff._flags_cache["deck.rules_first"] = True
    on = served(run(monkeypatch))
    ff._flags_cache["deck.quality_filters"] = False
    off = served(run(monkeypatch))
    assert set(off) > set(on)                          # the quality rules reject something here
    real_serve = fast.serve
    filtered = spy(monkeypatch, dq, "filter_deck")
    for start, flipped, expected in ((True, False, on), (False, True, off)):
        ff._flags_cache["deck.quality_filters"] = start
        def flipping(*args, flipped=flipped, **kwargs):
            result = real_serve(*args, **kwargs)
            ff._flags_cache["deck.quality_filters"] = flipped     # a reload mid-job
            return result
        monkeypatch.setattr(fast, "serve", functools.wraps(real_serve)(flipping))
        calls = len(filtered)
        assert served(run(monkeypatch)) == expected
        assert len(filtered) - calls == int(start)     # the filter ran iff the job's rules had it
