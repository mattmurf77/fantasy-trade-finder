from datetime import datetime,timedelta,timezone
import json
import pytest
from backend import database as db
from backend.league_projections import store,batch,service,provider
from backend.tests.test_outlook_calibration_persistence import engine
from backend.tests.test_league_projection_batch import scheduled


def expire(engine,run_id):
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.update().where(db.league_projection_runs_table.c.run_id==run_id).values(expires_at='2000-01-01T00:00:00+00:00'))


def test_recovery_reuses_frozen_snapshot_and_old_worker_cannot_publish(engine,monkeypatch):
    created=store.create('account','123',{'league_user_id':'account','kind':'scenario','config':{}})
    first=store.claim()
    snapshot={'captured_at':'2026-11-01T00:00:00+00:00','source':'synthetic'}
    store.save_snapshot(first,snapshot,{})
    expire(engine,first['run_id']);store.maintenance()
    recovered=store.claim()
    assert recovered['run_id']==first['run_id'] and recovered['worker_token']!=first['worker_token']
    assert json.loads(recovered['snapshot_json'])==snapshot
    assert store.finish(first,{'old':'must_not_publish'}) is False
    assert store.finish(recovered,{'new':'valid'}) is True


def test_recovery_count_is_bounded(engine):
    store.create('account','123',{'kind':'scenario','config':{}})
    first=store.claim();expire(engine,first['run_id']);store.maintenance()
    second=store.claim();assert second
    expire(engine,second['run_id']);store.maintenance()
    assert store.claim() is None
    assert store.get(second['run_id'],'account','123')['status']=='failed'


def test_failed_weekly_refresh_retains_previous_success_beyond_history_retention(scheduled):
    now=datetime.now(timezone.utc)
    with scheduled.begin() as conn:
        conn.execute(db.league_projection_runs_table.insert(),[
            {'run_id':'a'*32,'user_id':'account','league_id':'123','status':'complete','created_at':(now-timedelta(days=8)).isoformat(),'updated_at':(now-timedelta(days=8)).isoformat(),'expires_at':(now-timedelta(days=8)).isoformat(),'request_hash':'old','input_json':'{}','result_json':'{"old_success":true}'},
            {'run_id':'b'*32,'user_id':'account','league_id':'123','status':'failed','created_at':now.isoformat(),'updated_at':now.isoformat(),'expires_at':now.isoformat(),'request_hash':'new','input_json':'{}','result_json':None}])
        conn.execute(db.league_projection_targets_table.update().values(last_success_id='a'*32,last_attempt_id='b'*32))
    store.maintenance()
    state=batch.view('account','123')
    assert state['state']=='refresh_failed'
    assert state['run']['run_id']=='a'*32
    assert json.loads(state['run']['result_json'])=={'old_success':True}


def test_resumed_service_does_not_refetch_or_replace_captured_snapshot(engine,monkeypatch):
    store.create('account','123',{'league_user_id':'account','kind':'scenario','config':{}})
    first=store.claim();snapshot={'captured_at':'2026-11-01T00:00:00+00:00','source':'frozen'}
    store.save_snapshot(first,snapshot,{})
    expire(engine,first['run_id']);store.maintenance()
    monkeypatch.setattr(service,'is_enabled',lambda key:True)
    monkeypatch.setattr(batch,'settings',lambda:{'policy_approved':True, 'retention_days':7})
    monkeypatch.setattr(provider,'capture',lambda *a,**k:pytest.fail('recovery must reuse frozen capture'))
    calls=[]
    def simulate(value,cfg,**kwargs):
        calls.append(value)
        assert value==snapshot
        return {'complete':True}
    monkeypatch.setattr(service,'simulate',simulate)
    service._run(lambda *a:pytest.fail('unexpected provider fetch'))
    assert calls==[snapshot]
    assert store.get(first['run_id'],'account','123')['status']=='complete'


def test_identical_semantic_snapshot_reuses_result_despite_new_ingestion_clock(engine):
    from backend.league_projections.core import digest
    def snapshot(at):
        row={'game_id':'g1','kickoff_at':'2026-11-15T18:00:00+00:00','captured_at':at,'stats':{'rec':5}}
        return {'captured_at':at,'capture_completed_at':at,'source_captured_at':at,'source':'synthetic',
                'player_week_inputs':[{'player_id':'p','source_hash':digest(row),'input':row}]}
    store.create('account','123',{'kind':'scenario','config':{}})
    first=store.claim();store.save_snapshot(first,snapshot('2026-11-01T00:00:00+00:00'),{})
    assert store.finish(first,{'frozen_result':'same model inputs'})
    store.create('account','123',{'kind':'scenario','config':{}})
    second=store.claim()
    previous=store.save_snapshot(second,snapshot('2026-11-01T00:05:00+00:00'),{})
    assert previous=={'frozen_result':'same model inputs'}


def test_old_worker_cannot_restore_deleted_account_evidence_after_recreation(engine):
    store.create('account','123',{'kind':'scenario','config':{}})
    old=store.claim()
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.delete().where(db.league_projection_runs_table.c.user_id=='account'))
        conn.execute(db.users_table.delete().where(db.users_table.c.sleeper_user_id=='account'))
        conn.execute(db.users_table.insert().values(sleeper_user_id='account',created_at='2099-01-01T00:00:00+00:00',verified_via='sleeper'))
    with pytest.raises(Exception) as error:
        store.save_snapshot(old,{'sensitive':'old private capture'},{})
    assert getattr(error.value,'reason',None)=='cancelled'
    assert store.finish(old,{'sensitive':'old private result'}) is False
    assert store.get(old['run_id'],'account','123') is None


def test_worker_rechecks_policy_before_provider_and_during_simulation(engine, monkeypatch):
    monkeypatch.setattr(service, 'is_enabled', lambda key: True)
    approved = [False]
    monkeypatch.setattr(batch, 'settings', lambda: {'policy_approved': approved[0], 'retention_days':7})
    queued = store.create('account','123',{'league_user_id':'account','kind':'scenario','config':{}})
    service._run(lambda *a: pytest.fail('closed policy fetched provider'))
    assert store.get(queued['run_id'],'account','123')['reason'] == 'projection_policy_approval_pending'
    approved[0] = True
    second = store.create('account','123',{'league_user_id':'account','kind':'scenario','config':{'seed':1}}, snapshot={'captured_at':'2026-11-01T00:00:00+00:00'})
    def simulate(snapshot, cfg, *, cancelled):
        approved[0] = False
        assert cancelled()
        from backend.league_projections.core import Unavailable
        raise Unavailable('cancelled', state='cancelled')
    monkeypatch.setattr(service, 'simulate', simulate)
    service._run(lambda *a: pytest.fail('frozen snapshot fetched provider'))
    assert store.get(second['run_id'],'account','123')['status'] == 'cancelled'


@pytest.mark.parametrize('old_engine,missing_version,recovery',[(True,False,False),(False,True,False),(True,False,True)])
def test_worker_never_migrates_queued_or_resumed_old_model(engine,monkeypatch,old_engine,missing_version,recovery):
    from backend.league_projections.core import VERSION
    monkeypatch.setattr(service,'is_enabled',lambda key:True)
    monkeypatch.setattr(batch,'settings',lambda:{'policy_approved':True,'retention_days':7})
    created=store.create('account','123',{'kind':'scenario','league_user_id':'account','config':{}},snapshot={'captured_at':'2026-11-01T00:00:00+00:00'})
    inputs=json.loads(created['input_json'])
    assert inputs['expected_model_version']==VERSION
    if missing_version:inputs.pop('expected_model_version')
    elif old_engine:inputs['expected_model_version']='joint-season-scenario-v2'
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.update().where(db.league_projection_runs_table.c.run_id==created['run_id']).values(input_json=json.dumps(inputs)))
    if recovery:
        claimed=store.claim();expire(engine,claimed['run_id']);store.maintenance()
    monkeypatch.setattr(service,'simulate',lambda *a,**k:pytest.fail('old-version simulation'))
    service._run(lambda *a:pytest.fail('old-version provider fetch'))
    assert store.get(created['run_id'],'account','123')['reason']=='queued_projection_model_changed'


def test_worker_rechecks_frozen_baseline_version_even_with_current_expected_engine(engine,monkeypatch):
    from backend.league_projections.core import VERSION
    monkeypatch.setattr(service,'is_enabled',lambda key:True)
    monkeypatch.setattr(batch,'settings',lambda:{'policy_approved':True,'retention_days':7})
    baseline='f'*32
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.insert().values(run_id=baseline,user_id='account',league_id='123',status='complete',
            created_at=store.utc_now(),updated_at=store.utc_now(),expires_at=store.utc_now(),request_hash='old',input_json='{}',result_json=json.dumps({'model_version':'joint-season-scenario-v2'})))
    created=store.create('account','123',{'kind':'scenario','league_user_id':'account','config':{},'baseline_run_id':baseline},snapshot={'captured_at':'2026-11-01T00:00:00+00:00'})
    assert json.loads(created['input_json'])['expected_baseline_model_version']==VERSION
    monkeypatch.setattr(service,'simulate',lambda *a,**k:pytest.fail('mismatched baseline simulation'))
    service._run(lambda *a:pytest.fail('mismatched baseline provider fetch'))
    assert store.get(created['run_id'],'account','123')['reason']=='comparison_requires_current_model_baseline'
    assert store.get(baseline,'account','123')['status']=='complete'
