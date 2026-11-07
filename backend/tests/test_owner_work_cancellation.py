"""Cancellation interrupts work; unchanged jobs keep full proofs and ordering."""
from datetime import datetime, timedelta, timezone
from itertools import count
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend import database as db, server, trade_service as ts
from backend import trade_gen_owner as owner, trade_gen_bilateral as bilateral
from backend import trade_gen_bilateral_candidate as candidate, trade_gen_outlook_evidence as outlook
from backend import prepared_trade_runtime as runtime, prepared_trade_store as store
from backend import prepared_trade_store_v2 as paged
from backend.trade_work_control import TradeWorkCancelled
from backend.tests.test_trade_gen_bilateral import favorable
from backend.tests.test_owner_generator_routes import harness, owner_harness, worker, rows, ME, LEAGUE, TOKEN
from backend.tests.test_owner_only_routes import exclusive, large_exclusive
from backend.tests.test_prepared_trade_runtime_review import headless, new_claim

ARMS = [(owner.generate_owner_trades, owner.evaluate_owner_trades),
        (bilateral.generate_bilateral_trades, bilateral.evaluate_bilateral_trades),
        (candidate.generate_bilateral_trades, candidate.evaluate_bilateral_trades),
        (outlook.generate_bilateral_trades, outlook.evaluate_bilateral_trades)]


@pytest.mark.parametrize('generate,evaluate', ARMS)
def test_live_callback_preserves_all_ordered_proofs_and_report(generate, evaluate, monkeypatch):
    monkeypatch.setattr(ts, '_cfg', dict(ts._DEFAULT_CFG))
    args = favorable()
    baseline, raw = generate(**args)
    ticks = []
    checked, report = generate(**args, _check_current=lambda: ticks.append(1))
    assert baseline and ticks
    assert [c.owner_evaluation.as_dict() for c in checked] == [c.owner_evaluation.as_dict() for c in baseline]
    left, right = raw.as_dict(), report.as_dict()
    left.pop('elapsed_seconds', None); right.pop('elapsed_seconds', None)
    assert left == right
    assert [p.as_dict() for p in evaluate(checked, **args, _check_current=lambda: None)] == [
        p.as_dict() for p in evaluate(baseline, **args)]


@pytest.mark.parametrize('generate,evaluate', ARMS)
def test_cancel_before_constructor_and_during_final_occurrences_never_returns_partial(generate, evaluate):
    args = favorable()
    def cancelled():
        raise TradeWorkCancelled()
    with pytest.raises(TradeWorkCancelled):
        generate(**args, _check_current=cancelled)
    cards, _ = generate(**args)
    seen = count()
    # Constructor then first occurrence are allowed; next checkpoint aborts.
    def after_one():
        if next(seen) >= 3:
            raise TradeWorkCancelled()
    with pytest.raises(TradeWorkCancelled):
        evaluate(cards * 5, **args, _check_current=after_one)


def test_superseded_real_worker_stops_search_and_replacement_completes(large_exclusive, monkeypatch):
    _, engine, _, service, _ = large_exclusive
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.)
    original = candidate._GenerationSearch.evaluate
    evaluated = []
    def invalidate(search, card, **kwargs):
        evaluated.append(card)
        result = original(search, card, **kwargs)
        if len(evaluated) == 1:
            with server._trade_jobs_lock:
                server._revoke_trade_job_locked(server._trade_jobs['owner-route-worker'])
                old = server._trade_jobs['owner-route-worker']
                replacement = {**old, 'job_id': 'replacement', 'status': 'running',
                               'superseded': False, 'cards': [], 'error': None, 'finished_at': None}
                server._trade_jobs['replacement'] = replacement
        return result
    monkeypatch.setattr(candidate._GenerationSearch, 'evaluate', invalidate)
    # Existing helper asserts terminal state; cancellation retains no public prefix.
    worker(large_exclusive, monkeypatch, expected_error='inputs_changed')
    assert server._trade_jobs['owner-route-worker']['cards'] == []
    assert len(evaluated) == 1
    assert not rows(engine, db.deck_impressions_table)
    assert server._trade_jobs['replacement']['status'] == 'running'
    monkeypatch.setattr(candidate._GenerationSearch, 'evaluate', original)
    server._run_trade_job('replacement', TOKEN, LEAGUE, .5, [])
    replacement = server._trade_jobs['replacement']
    assert replacement['status'] == 'complete', replacement
    assert len(replacement['cards']) >= 64
    assert rows(engine, db.deck_impressions_table)


def target_row(engine, target_id):
    with engine.connect() as conn:
        return dict(conn.execute(select(db.prepared_trade_targets_table).where(
            db.prepared_trade_targets_table.c.target_id == target_id)).mappings().one())


def test_preparation_yields_after_real_candidate_and_refunds_only_own_attempt(headless, monkeypatch):
    fixture, target = headless
    _, engine, *_ = fixture
    scope, sweep, claim = new_claim(target)
    original = candidate._GenerationSearch.evaluate
    evaluated = []
    def foreground_arrives(search, card, **kwargs):
        evaluated.append(card)
        result = original(search, card, **kwargs)
        server._trade_jobs['interactive'] = {'job_id': 'interactive', 'status': 'running', 'cards': []}
        return result
    monkeypatch.setattr(candidate._GenerationSearch, 'evaluate', foreground_arrives)
    runtime.prepare_target(server, claim)
    row = target_row(engine, claim['target_id'])
    assert len(evaluated) == 1
    assert row['status'] == 'pending' and row['reason'] == 'interactive_work' and row['attempts'] == 0
    assert row['lease_token'] is None
    assert not rows(engine, paged.M)  # Aborted before releasing the stage's lease.
    assert not rows(engine, db.deck_impressions_table)
    assert server._trade_jobs['interactive']['status'] == 'running'
    assert paged.peek_inventory(scope) is None
    # Once foreground is gone, this same target still completes full work.
    server._trade_jobs.pop('interactive')
    monkeypatch.setattr(candidate._GenerationSearch, 'evaluate', original)
    now = datetime.now(timezone.utc) + timedelta(seconds=31)
    retry = store.claim_target(sweep, now=now)
    assert retry and retry['target_id'] == claim['target_id']
    runtime.prepare_target(server, retry)
    assert paged.peek_inventory(scope).header['card_count'] >= 64


def test_repeated_interactive_deferrals_do_not_exhaust_failure_budget_or_revive_claim(headless):
    fixture, target = headless
    _, engine, *_ = fixture
    now = datetime.now(timezone.utc)
    _, sweep, claim = new_claim(target, now=now)
    for _ in range(8):
        store.defer_target_for_interactive(claim, now=now)
        assert target_row(engine, claim['target_id'])['attempts'] == 0
        assert store.sweep_status(sweep)['status'] == 'running'
        old = claim
        now += timedelta(seconds=31)
        claim = store.claim_target(sweep, now=now)
        with pytest.raises(store.StaleWork):
            store.defer_target_for_interactive(old, now=now)
        assert target_row(engine, claim['target_id'])['lease_token'] == claim['lease_token']


def test_stop_sweep_during_real_search_cancels_without_completing_a_stale_claim(headless, monkeypatch):
    fixture, target = headless
    _, engine, *_ = fixture
    scope, sweep, claim = new_claim(target)
    clock = count(0, 2)
    monkeypatch.setattr(runtime, 'time', SimpleNamespace(time=runtime.time.time, monotonic=lambda: next(clock)))
    original = candidate._GenerationSearch.evaluate
    evaluated = []
    def stop(search, card, **kwargs):
        evaluated.append(card)
        result = original(search, card, **kwargs)
        store.stop_sweep(sweep)
        return result
    monkeypatch.setattr(candidate._GenerationSearch, 'evaluate', stop)
    runtime.prepare_target(server, claim)
    assert len(evaluated) == 1
    assert store.sweep_status(sweep)['status'] == 'stopped'
    assert target_row(engine, claim['target_id'])['status'] == 'cancelled'
    assert paged.peek_inventory(scope) is None
    assert not rows(engine, db.deck_impressions_table)


@pytest.mark.parametrize('selection', [{'give': ['g']}, {'receive': ['r0-0']}, {'opponent': 'opponent-0'}])
def test_targeted_worker_does_not_swallow_cancellation_as_empty_supply(large_exclusive, monkeypatch, selection):
    _, engine, *_ = large_exclusive
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.)
    calls = []
    def interrupt(search, card, **kwargs):
        calls.append(card)
        raise TradeWorkCancelled('inputs_changed')
    monkeypatch.setattr(candidate._GenerationSearch, 'evaluate', interrupt)
    def no_bakeoff(**kwargs):
        pytest.fail('selected request unexpectedly entered bakeoff')
    monkeypatch.setattr(server._bakeoff, 'run_bakeoff', no_bakeoff)
    job = worker(large_exclusive, monkeypatch, expected_error='inputs_changed', **selection)
    assert len(calls) == 1 and job['cards'] == []
    assert not rows(engine, db.deck_impressions_table)


def test_transient_stage_check_failure_cannot_seal_an_empty_success(headless, monkeypatch):
    fixture, target = headless
    _, engine, *_ = fixture
    scope, sweep, claim = new_claim(target)
    clock = count(0, 2)
    monkeypatch.setattr(runtime, 'time', SimpleNamespace(time=runtime.time.time, monotonic=lambda: next(clock)))
    original = paged.check_generation_stage
    calls = []
    def transient(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:  # Inside actual owner constructor/bakeoff, then recovers.
            raise RuntimeError('synthetic transient SQL outage')
        return original(*args, **kwargs)
    monkeypatch.setattr(paged, 'check_generation_stage', transient)
    with pytest.raises(TradeWorkCancelled, match='preparation_check_unavailable'):
        runtime.prepare_target(server, claim)
    assert len(calls) == 2
    assert paged.peek_inventory(scope) is None
    assert not rows(engine, paged.M)
    assert not rows(engine, db.deck_impressions_table)
    row = target_row(engine, claim['target_id'])
    assert row['status'] == 'running' and row['attempts'] == 1  # Scheduler owns normal bounded error retry.
