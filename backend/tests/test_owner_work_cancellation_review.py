"""Independent cancellation controls promoted to hermetic regressions.

The direct worker fixture skips admission; the final-evaluation tests attach
its real consumed-participant epoch tokens before entering the actual worker.
"""
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import select
from backend import server, database as db, prepared_trade_store as store
from backend.trade_work_control import TradeWorkCancelled
from backend.tests.test_prepared_trade_runtime_review import headless, new_claim
from backend.tests.test_owner_generator_routes import harness, owner_harness, ME, LEAGUE
from backend.tests.test_owner_only_routes import exclusive, large_exclusive

def test_completed_job_never_enters_work_callback(monkeypatch):
    job = {'job_id': 'synthetic-complete', 'status': 'complete', 'cards': [{'known': 'committed'}]}
    monkeypatch.setattr(server, '_trade_jobs', {'synthetic-complete': job})
    calls = []

    def work():
        calls.append(1)
        raise TradeWorkCancelled()
    server._run_trade_job('synthetic-complete', '', LEAGUE, 0.5, [], work_check=work)
    assert calls == []
    assert job['status'] == 'complete' and job['cards'] == [{'known': 'committed'}]

def test_typed_cancel_clears_pending_final_state_without_success(monkeypatch):
    job = {'job_id': 'synthetic-running', 'status': 'running', 'cards': [], 'final_checks_pending': True}
    monkeypatch.setattr(server, '_trade_jobs', {'synthetic-running': job})

    def work():
        raise TradeWorkCancelled('interactive_work')
    server._run_trade_job('synthetic-running', '', LEAGUE, 0.5, [], work_check=work, prepare_sink=object())
    assert job['status'] == 'error' and job['error'] == 'interactive_work'
    assert job['final_checks_pending'] is False
    assert isinstance(job['prepared_failure'], TradeWorkCancelled)

def test_refund_preserves_prior_real_failure_count(headless):
    fixture, target = headless
    _, engine, *_ = fixture
    now = datetime.now(timezone.utc)
    _, sweep, claim = new_claim(target, now=now)
    with engine.begin() as conn:
        conn.execute(db.prepared_trade_targets_table.update().where(db.prepared_trade_targets_table.c.target_id == claim['target_id']).values(attempts=3, max_attempts=3))
    store.defer_target_for_interactive(claim, now=now)
    with engine.connect() as conn:
        row = conn.execute(select(db.prepared_trade_targets_table).where(db.prepared_trade_targets_table.c.target_id == claim['target_id'])).mappings().one()
    assert row['attempts'] == 2 and row['status'] == 'pending' and (row['reason'] == 'interactive_work')
    retry = store.claim_target(sweep, now=now + timedelta(seconds=31))
    assert retry
    store.complete_target(retry, status='error', reason='preparation_failed', now=now + timedelta(seconds=31))
    assert store.sweep_status(sweep)['remaining_count'] == 0

@pytest.mark.parametrize('changed', ['viewer', 'counterparty'])
def test_real_final_evaluation_stops_after_input_invalidation(large_exclusive, monkeypatch, changed):
    from backend import trade_gen_bilateral_candidate as candidate, trade_service as ts
    from backend.tests.test_owner_generator_routes import worker, rows
    _, engine, *_ = large_exclusive
    ts._cfg.update(owner_bilateral_enabled=1.0, owner_bilateral_revision_enabled=1.0)
    original = candidate._Search.evaluate
    final_calls = []

    def evaluate(search, card, **kwargs):
        result = original(search, card, **kwargs)
        if type(search) is candidate._Search:
            final_calls.append(card)
            if len(final_calls) == 1:
                uid = ME if changed == 'viewer' else card.target_user_id
                server._invalidate_trade_jobs(user_id=uid, league_id=LEAGUE)
        return result
    monkeypatch.setattr(candidate._Search, 'evaluate', evaluate)
    original_run = server._run_trade_job

    def admitted(job_id, *args, **kwargs):
        server._trade_jobs[job_id]['input_epochs'] = server._capture_trade_input_epochs(ME, LEAGUE, participant_ids=[m.user_id for m in large_exclusive[-1].members])
        return original_run(job_id, *args, **kwargs)
    monkeypatch.setattr(server, '_run_trade_job', admitted)
    job = worker(large_exclusive, monkeypatch, expected_error='inputs_changed')
    assert len(final_calls) == 1
    assert job['cards'] == [] and (not job['final_checks_pending'])
    assert not rows(engine, db.deck_impressions_table)
