"""Only a discarded source-change capture gets one in-job retry."""
import json
import pytest
from backend import database as db
from backend.league_projections import batch, provider, service, store
from backend.league_projections.core import Unavailable
from backend.tests.test_outlook_calibration_persistence import engine

@pytest.fixture
def job(engine, monkeypatch):
    flags = {'league.projections': True, 'league.projections_provider_approved': True}
    policy = {'policy_approved': True, 'retention_days': 7}
    monkeypatch.setattr(service, 'is_enabled', lambda key: flags.get(key, False))
    monkeypatch.setattr(batch, 'settings', lambda: policy)
    row = store.create('account', '123', {'kind': 'scenario', 'league_user_id': 'account', 'config': {}})
    monkeypatch.setattr(service, 'simulate', lambda snapshot, cfg, **kw: {'source': snapshot['source']})
    return row, flags, policy

def read(job):
    return store.get(job[0]['run_id'], 'account', '123')

def test_retry_discards_first_capture_and_persists_only_complete_second(job, monkeypatch):
    calls = []
    def capture(*args, **kwargs):
        current = read(job)
        calls.append((current['worker_token'], current['expires_at']))
        assert current['snapshot_json'] is None
        if len(calls) == 1:
            raise Unavailable('inputs_changed_during_capture', state='stale')
        return {'captured_at': '2026-11-07T00:00:00+00:00', 'source': 'second'}
    monkeypatch.setattr(provider, 'capture', capture)
    service._run(lambda url: pytest.fail('no network'))
    result = read(job)
    assert len(calls) == 2 and calls[0] == calls[1]
    assert result['status'] == 'complete' and result['retry_count'] == 0
    assert json.loads(result['snapshot_json'])['source'] == 'second'
    assert json.loads(result['result_json'])['source'] == 'second'

@pytest.mark.parametrize('reason,state,count', [
    ('inputs_changed_during_capture', 'stale', 2),
    ('game_started_during_capture', 'incomplete_projections', 1),
    ('unsupported_playoff_bracket', 'unsupported_policy', 1),
    ('provider_unavailable', 'failed', 1),
])
def test_only_source_revision_failure_retries_and_bound_stays_terminal(job, monkeypatch, reason, state, count):
    calls=[]
    def capture(*a, **kw):
        calls.append(1)
        raise Unavailable(reason, state=state)
    monkeypatch.setattr(provider, 'capture', capture)
    service._run(lambda url: pytest.fail('no network'))
    result=read(job)
    assert len(calls)==count and result['status']==state and result['reason']==reason
    assert result['snapshot_json'] is None and result['result_json'] is None

@pytest.mark.parametrize('change', ['flag', 'provider', 'policy', 'cancel', 'lease', 'deadline', 'model', 'identity'])
def test_retry_rechecks_authority_policy_and_original_deadline(job, engine, monkeypatch, change):
    calls=[]; elapsed=[0.0]
    monkeypatch.setattr(service.time, 'monotonic', lambda: elapsed[0])
    def capture(*a, **kw):
        calls.append(1)
        if change=='flag': job[1]['league.projections']=False
        if change=='provider': job[1]['league.projections_provider_approved']=False
        if change=='policy': job[2]['policy_approved']=False
        if change=='cancel': store.cancel(job[0]['run_id'],'account','123')
        if change=='lease':
            with engine.begin() as conn:
                conn.execute(db.league_projection_runs_table.update().where(db.league_projection_runs_table.c.run_id==job[0]['run_id']).values(worker_token='replaced'))
        if change=='deadline': elapsed[0]=541
        if change=='model': monkeypatch.setattr(service, 'VERSION', 'changed-model')
        if change=='identity':
            monkeypatch.setattr(service, '_viewer_identity', lambda uid: (_ for _ in ()).throw(Unavailable('verified_sleeper_binding_required')))
        raise Unavailable('inputs_changed_during_capture',state='stale')
    monkeypatch.setattr(provider,'capture',capture)
    service._run(lambda url: pytest.fail('no network'))
    assert len(calls)==1
    assert read(job)['snapshot_json'] is None and read(job)['result_json'] is None
