"""Independent SQLite worker/capture fences for the one in-execution retry."""
import json
from copy import deepcopy
import pytest
from backend import database as db
from backend.league_projections import provider,service,store,batch
from backend.league_projections.core import VERSION,Unavailable
from backend.tests.test_outlook_calibration_persistence import engine
from backend.tests.test_league_projection_provider import world
from backend.tests.test_league_projection_simulation import config

@pytest.fixture
def queued(engine,monkeypatch):
    flags={'league.projections':True,'league.projections_provider_approved':True};policy={'policy_approved':True,'retention_days':7}
    monkeypatch.setattr(service,'is_enabled',lambda key:flags.get(key,False));monkeypatch.setattr(batch,'settings',lambda:policy)
    job=store.create('account','123',{'kind':'scenario','league_user_id':'account','config':config()})
    simulations=[]
    monkeypatch.setattr(service,'simulate',lambda snap,cfg,**kw:simulations.append(snap) or {'source':snap.get('source'),'model_version':VERSION})
    return job,flags,policy,simulations

def saved(q):return store.get(q[0]['run_id'],'account','123')
def update(engine,q,**values):
    with engine.begin() as conn:conn.execute(db.league_projection_runs_table.update().where(db.league_projection_runs_table.c.run_id==q[0]['run_id']).values(**values))

def test_actual_provider_capture_restarts_entire_input_window_after_race(queued,monkeypatch):
    source,feed=world();source[f'{provider.API}/league/123/rosters'][0]['owner_id']='account'
    source[f'{provider.API}/league/123']['settings']['playoff_seed_type']=0
    fetches=[];league_reads=0;claims=[]
    def fetch(url):
        nonlocal league_reads
        fetches.append(url)
        if url==f'{provider.API}/league/123':
            league_reads+=1
            if league_reads==2:source[url]['settings']['playoff_seed_type']=1
            if league_reads==3:assert saved(queued)['snapshot_json'] is None
        return deepcopy(source[url])
    original=provider.capture
    def capture(*a,**kw):
        row=saved(queued);claims.append((row['worker_token'],row['expires_at']))
        return original(*a,**kw,feed=feed,captured_at='2026-11-01T00:00:00+00:00',clock=lambda:'2026-11-01T00:00:01+00:00')
    monkeypatch.setattr(provider,'capture',capture)
    service._run(fetch)
    row=saved(queued)
    assert len(claims)==2 and claims[0]==claims[1]
    assert fetches.count(f'{provider.API}/state/nfl')==4 and league_reads==4
    assert row['status']=='complete' and row['retry_count']==0
    assert json.loads(row['snapshot_json'])['coverage']['native_playoff_seed_type']==1
    assert len(queued[3])==1

@pytest.mark.parametrize('reason',['inputs_changed_during_capture','game_started_during_capture','unsupported_playoff_bracket','provider_unavailable'])
def test_exact_reason_budget_and_no_failed_capture_persistence(queued,monkeypatch,reason):
    calls=[]
    def capture(*a,**kw):calls.append(1);raise Unavailable(reason,state='stale')
    monkeypatch.setattr(provider,'capture',capture);service._run(None)
    assert len(calls)==(2 if reason=='inputs_changed_during_capture' else 1)
    row=saved(queued);assert row['snapshot_json'] is None and row['result_json'] is None and queued[3]==[]
    assert row['reason']==reason

@pytest.mark.parametrize('phase',['before','during'])
@pytest.mark.parametrize('change',['cancel','expires','worker_token','delete_recreate','flag','policy'])
def test_revocation_before_or_during_retry_never_publishes(queued,engine,monkeypatch,phase,change):
    calls=[]
    # Isolate one worker execution; ordinary expired-job recovery is a separate claim.
    claim=store.claim; claimed=[]
    def once():
        if claimed:return None
        claimed.append(True);return claim()
    monkeypatch.setattr(store,'claim',once)
    def revoke():
        if change=='cancel':store.cancel(queued[0]['run_id'],'account','123')
        elif change=='expires':update(engine,queued,expires_at='2000-01-01T00:00:00+00:00')
        elif change=='worker_token':update(engine,queued,worker_token='replacement')
        elif change=='flag':queued[1]['league.projections']=False
        elif change=='policy':queued[2]['policy_approved']=False
        else:
            with engine.begin() as conn:
                conn.execute(db.league_projection_runs_table.delete().where(db.league_projection_runs_table.c.user_id=='account'))
                conn.execute(db.users_table.delete().where(db.users_table.c.sleeper_user_id=='account'))
                conn.execute(db.users_table.insert().values(sleeper_user_id='account',created_at='2099-01-01',verified_via='sleeper'))
    def capture(*a,**kw):
        calls.append(1)
        if len(calls)==1:
            if phase=='before':revoke()
            raise Unavailable('inputs_changed_during_capture',state='stale')
        revoke();return {'source':'must-not-persist','captured_at':'2026-11-01T00:00:00+00:00'}
    monkeypatch.setattr(provider,'capture',capture);service._run(None)
    assert len(calls)==(1 if phase=='before' else 2)
    row=saved(queued);assert row is None or (row['snapshot_json'] is None and row['result_json'] is None)
    assert queued[3]==[]


def test_original_elapsed_deadline_is_not_reset_for_retry(queued,monkeypatch):
    elapsed=[0];calls=[];monkeypatch.setattr(service.time,'monotonic',lambda:elapsed[0])
    def capture(*a,**kw):
        calls.append(1)
        if len(calls)==1:
            elapsed[0]=539;raise Unavailable('inputs_changed_during_capture',state='stale')
        elapsed[0]=541;return {'source':'late','captured_at':'2026-11-01T00:00:00+00:00'}
    monkeypatch.setattr(provider,'capture',capture);service._run(None)
    assert len(calls)==2 and saved(queued)['snapshot_json'] is None and queued[3]==[]


def test_revoked_comparison_baseline_blocks_second_capture(queued,engine,monkeypatch):
    baseline='b'*32
    with engine.begin() as conn:conn.execute(db.league_projection_runs_table.insert().values(run_id=baseline,user_id='account',league_id='123',status='complete',created_at=store.utc_now(),updated_at=store.utc_now(),expires_at='2099-01-01T00:00:00+00:00',request_hash='baseline',input_json='{}',result_json=json.dumps({'model_version':VERSION})))
    inputs=json.loads(queued[0]['input_json']);inputs.update(baseline_run_id=baseline,expected_baseline_model_version=VERSION);update(engine,queued,input_json=json.dumps(inputs));calls=[]
    def capture(*a,**kw):
        calls.append(1)
        with engine.begin() as conn:conn.execute(db.league_projection_runs_table.delete().where(db.league_projection_runs_table.c.run_id==baseline))
        raise Unavailable('inputs_changed_during_capture',state='stale')
    monkeypatch.setattr(provider,'capture',capture);service._run(None)
    assert len(calls)==1 and saved(queued)['reason']=='comparison_requires_current_model_baseline'
    assert saved(queued)['snapshot_json'] is None and queued[3]==[]


def test_viewer_binding_is_read_fresh_before_second_capture(queued,monkeypatch):
    identities=iter(['former-binding','current-binding']);seen=[]
    monkeypatch.setattr(service,'_viewer_identity',lambda uid:next(identities))
    def capture(*a,**kw):
        seen.append(kw['viewer_user_id'])
        if len(seen)==1:raise Unavailable('inputs_changed_during_capture',state='stale')
        raise PermissionError('current binding no longer owns seat')
    monkeypatch.setattr(provider,'capture',capture);service._run(None)
    assert seen==['former-binding','current-binding']
    assert saved(queued)['reason']=='league_membership_changed' and saved(queued)['snapshot_json'] is None

@pytest.mark.parametrize('error',[ConnectionError('synthetic connection'),PermissionError('synthetic membership')])
def test_other_exception_classes_never_trigger_source_retry(queued,monkeypatch,error):
    calls=[]
    def capture(*a,**kw):calls.append(1);raise error
    monkeypatch.setattr(provider,'capture',capture);service._run(None)
    assert len(calls)==1 and saved(queued)['snapshot_json'] is None and queued[3]==[]
