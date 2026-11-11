"""Fast deck wiring (ADR-028; docs/plans/realtime-trade-engine/scope.md).

Flags ``trade.fast_deck`` and ``trade.fast_deck_shadow``, both default off.

Helper (``backend/trade_fast_deck.py``), on the synthetic league:
- ``serve`` returns the full solve's first k cards, in order, with equal
  proofs, for both parity-tested bilateral generators;
- it passes the page its own work limit;
- it declines (None) a generator without a parity suite, a pinned request, an
  unproven page and a league where the incumbent's stream budgets bind;
- ``shadow`` reports agreement and the first divergence without touching the
  full solve's cards;
- the worker's currentness check is forwarded, not swallowed.

Worker (``server._run_trade_job`` on the owner route harness, real generator,
isolated SQLite):
- both flags off: the module is never imported and the deck is unchanged;
- serve on: the published deck is the page, in order, and every impression's
  frozen generation diagnostics name the page search;
- an unavailable or failing fast deck serves the full solve, unshadowed;
- background sources (replenishment) keep the full solve with the flag on;
- shadow on: the full solve is served, one comparison is logged, and a failing
  comparison changes nothing; serve wins when both are on;
- a cancellation raised inside the fast deck ends the job as cancelled.
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
from backend import trade_fast_deck as fast, trade_first_page as fp
from backend import trade_gen_bilateral as bilateral, trade_gen_bilateral_candidate as candidate
from backend import trade_gen_outlook_evidence as outlook_evidence, trade_gen_owner as owner
from backend.eval import synthetic_league
from backend.tests.test_owner_generator_routes import (  # noqa: F401  (fixtures)
    harness, owner_harness, rows, ME, LEAGUE, TOKEN)
from backend.trade_work_control import TradeWorkCancelled

REPO = Path(__file__).resolve().parents[2]
_FULL = {}


def league(**overrides):
    return synthetic_league.build(teams=5, ranked_opponents=2, **overrides)


def full(module):
    if module not in _FULL:
        _FULL[module] = module.generate_bilateral_trades(**league())[0]
    return _FULL[module]


def identities(cards):
    return [fast._identity(card) for card in cards]


# ── helper ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module", [bilateral, candidate])
@pytest.mark.parametrize("k", [10, 60])
def test_serve_is_the_full_solves_first_k(module, k):
    cards, report = fast.serve(module.generate_bilateral_trades, league(), k=k)
    want = full(module)[:k]
    assert len(want) == k and identities(cards) == identities(want)
    assert [c.owner_evaluation.as_dict() for c in cards] == [c.owner_evaluation.as_dict() for c in want]
    data = report.diagnostics()
    assert data["page_first_version"] == fp.PAGE_FIRST_VERSION and data["k"] == k
    assert data["generator_version"] == module.VERSION and data["complete"] is True


def test_deck_size_covers_every_observed_session():
    # Deepest card acted on in production, 2026-09-01 to 2026-11-10: index 65.
    assert fast.DECK_SIZE == 150


def test_the_page_gets_the_fast_decks_own_work_limit(monkeypatch):
    # The heaviest recorded production request needed 5,015 exact evaluations.
    seen = []
    real = fp.first_page
    def recording(**kwargs):
        seen.append(kwargs["max_verifications"])
        return real(**kwargs)
    monkeypatch.setattr(fp, "first_page", recording)
    assert fast.serve(candidate.generate_bilateral_trades, league(), k=5) is not None
    assert seen == [fast.MAX_VERIFICATIONS] and fast.MAX_VERIFICATIONS == 12000


@pytest.mark.parametrize("generate,extra", [
    (owner.generate_owner_trades, {}),
    (outlook_evidence.generate_bilateral_trades, {}),
    (candidate.generate_bilateral_trades, {"pinned_give_players": ["p00_00"]}),
    (candidate.generate_bilateral_trades, {"require_all_give": True}),
    (lambda **kwargs: ([], None), {}),
])
def test_serve_declines_what_the_page_search_cannot_answer(generate, extra):
    assert fast.serve(generate, {**league(), **extra}) is None
    assert fast.shadow([], generate, {**league(), **extra}) is None


@pytest.mark.parametrize("field,value", [("complete", False), ("incumbent_budgets_bind", True)])
def test_serve_declines_an_unproven_or_budget_bound_page(monkeypatch, field, value):
    real = fp.first_page
    def altered(**kwargs):
        cards, report = real(**kwargs)
        return cards, owner.OwnerGenerationReport(owner._dump({**report.as_dict(), field: value}))
    monkeypatch.setattr(fp, "first_page", altered)
    assert fast.serve(candidate.generate_bilateral_trades, league(), k=5) is None
    assert fast.shadow(full(candidate), candidate.generate_bilateral_trades, league(), k=5)[
        "complete" if field == "complete" else "budgets_bind"] is value


def test_shadow_reports_agreement_and_first_divergence():
    cards = list(full(bilateral))
    before = identities(cards)
    same = fast.shadow(cards, bilateral.generate_bilateral_trades, league(), k=20)
    assert (same["identical"], same["agree_prefix"], same["page"], same["full"]) == (True, 20, 20, len(cards))
    assert same["page_first_version"] == fp.PAGE_FIRST_VERSION and same["page_ms"] > 0
    swapped = [cards[0], cards[1], cards[3], cards[2], *cards[4:]]
    moved = fast.shadow(swapped, bilateral.generate_bilateral_trades, league(), k=20)
    assert (moved["identical"], moved["agree_prefix"]) == (False, 2)
    assert identities(cards) == before
    assert set(json.loads(json.dumps(same))) == {
        "k", "identical", "agree_prefix", "page", "full", "complete", "budgets_bind",
        "verified", "page_first_version", "page_ms"}  # counts only: nothing private to log


def test_currentness_check_is_forwarded_not_swallowed():
    def cancelled():
        raise TradeWorkCancelled("inputs_changed")
    with pytest.raises(TradeWorkCancelled):
        fast.serve(candidate.generate_bilateral_trades, league(), check=cancelled)


# ── worker ──────────────────────────────────────────────────────────────────

@pytest.fixture
def revised(owner_harness, monkeypatch):
    """Production's shape: owner-only serving of bilateral revision 2."""
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.,
                   bakeoff_owner_only=1.)
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
    return card["target_user_id"], tuple(card["give"]), tuple(card["receive"])


def published(job):
    return [(c["trade_id"], c["impression_id"]) for c in job["cards"]]


def test_flags_ship_dark():
    shipped = json.loads((REPO / "config" / "features.json").read_text())
    for key in ("trade.fast_deck", "trade.fast_deck_shadow"):
        assert ff.DEFAULT_FLAGS[key] is False and shipped[key] is False


def test_both_flags_off_never_import_the_module(revised, monkeypatch):
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    monkeypatch.delitem(sys.modules, "backend.trade_fast_deck")
    monkeypatch.delattr(backend, "trade_fast_deck")
    job = run(monkeypatch)
    assert "backend.trade_fast_deck" not in sys.modules and not hasattr(backend, "trade_fast_deck")
    assert job["cards"] and len(full_solve) == 1
    assert [c["trade_id"] for c in job["cards"]] == [c.trade_id for c in full_solve[0][0]]


def test_serve_flag_publishes_the_page_with_attributed_evidence(revised, monkeypatch):
    _, engine, *_ = revised
    ff._flags_cache["trade.fast_deck"] = True
    served = spy(monkeypatch, fast, "serve")
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    job = run(monkeypatch)
    assert len(served) == 1 and not full_solve
    cards, report = served[0]
    assert cards and [c["trade_id"] for c in job["cards"]] == [c.trade_id for c in cards]
    assert all(impression for _, impression in published(job))
    records = rows(engine, db.deck_impressions_table)
    assert len(records) == len(cards)
    for record in records:
        generation = db.load_deck_diagnostics(record["impression_id"], record["user_id"])["owner_generation"]
        assert generation["page_first_version"] == fp.PAGE_FIRST_VERSION
        assert generation["generator_version"] == candidate.VERSION
        assert generation["k"] == fast.DECK_SIZE


@pytest.mark.parametrize("failure", ["declined", "raised"])
def test_unavailable_fast_deck_serves_the_full_solve(revised, monkeypatch, failure):
    ff._flags_cache["trade.fast_deck"] = True
    def unavailable(*args, **kwargs):
        if failure == "raised":
            raise RuntimeError("page search broke")
        return None
    monkeypatch.setattr(fast, "serve", unavailable)
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    job = run(monkeypatch)
    assert len(full_solve) == 1
    assert job["cards"] and [c["trade_id"] for c in job["cards"]] == [c.trade_id for c in full_solve[0][0]]


def test_declined_fast_deck_is_not_shadowed(revised, monkeypatch):
    ff._flags_cache.update({"trade.fast_deck": True, "trade.fast_deck_shadow": True})
    monkeypatch.setattr(fast, "serve", lambda *args, **kwargs: None)
    compared = spy(monkeypatch, fast, "shadow")
    assert run(monkeypatch)["cards"] and not compared


def test_background_sources_keep_the_full_solve(revised, monkeypatch):
    ff._flags_cache.update({"trade.fast_deck": True, "trade.fast_deck_shadow": True})
    served, compared = spy(monkeypatch, fast, "serve"), spy(monkeypatch, fast, "shadow")
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    run(monkeypatch, source="replenish")
    assert len(full_solve) == 1 and not served and not compared


def test_shadow_flag_serves_the_full_solve_and_logs_one_comparison(revised, monkeypatch, caplog):
    ff._flags_cache["trade.fast_deck_shadow"] = True
    served, compared = spy(monkeypatch, fast, "serve"), spy(monkeypatch, fast, "shadow")
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    with caplog.at_level(logging.INFO):
        job = run(monkeypatch)
    assert not served and len(compared) == 1 and len(full_solve) == 1
    assert compared[0]["identical"] is True and compared[0]["full"] == len(full_solve[0][0])
    assert [c["trade_id"] for c in job["cards"]] == [c.trade_id for c in full_solve[0][0]]
    lines = [r.getMessage() for r in caplog.records if "fast-deck shadow" in r.getMessage()]
    assert len(lines) == 1 and '"identical": true' in lines[0] and "full_ms=" in lines[0]


def test_failing_shadow_changes_nothing(revised, monkeypatch):
    ff._flags_cache["trade.fast_deck_shadow"] = True
    def broken(*args, **kwargs):
        raise RuntimeError("comparison broke")
    monkeypatch.setattr(fast, "shadow", broken)
    full_solve = spy(monkeypatch, candidate, "generate_bilateral_trades")
    job = run(monkeypatch)
    assert job["cards"] and [c["trade_id"] for c in job["cards"]] == [c.trade_id for c in full_solve[0][0]]


def test_serve_wins_when_both_flags_are_on(revised, monkeypatch):
    ff._flags_cache.update({"trade.fast_deck": True, "trade.fast_deck_shadow": True})
    served, compared = spy(monkeypatch, fast, "serve"), spy(monkeypatch, fast, "shadow")
    run(monkeypatch)
    assert len(served) == 1 and not compared


@pytest.mark.parametrize("flag,name", [("trade.fast_deck", "serve"), ("trade.fast_deck_shadow", "shadow")])
def test_cancellation_inside_the_fast_deck_cancels_the_job(revised, monkeypatch, flag, name):
    _, engine, *_ = revised
    ff._flags_cache[flag] = True
    def cancelled(*args, **kwargs):
        raise TradeWorkCancelled("inputs_changed")
    monkeypatch.setattr(fast, name, cancelled)
    job = run(monkeypatch, expected="error")
    assert job["error"] == "inputs_changed" and not job["cards"]
    assert not rows(engine, db.deck_impressions_table)
