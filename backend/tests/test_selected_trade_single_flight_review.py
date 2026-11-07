"""Independent selected running admission controls; all data synthetic."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import copy
import json

import pytest
from sqlalchemy import insert
from backend import server, database as db, feature_flags as ff
from backend.tests.test_trade_job_admission import world, UID, LID, TOKEN, FMT

@pytest.fixture
def selected(world,monkeypatch):
    monkeypatch.setattr(server,'_selected_trade_jobs',{})
    monkeypatch.setitem(ff._flags_cache,'trade.finder_targeting',True)
    monkeypatch.setitem(ff._flags_cache,'trades.intent_modes',True)
    with world.engine.begin() as c:
        for m in world.session['league'].members:
            c.execute(insert(db.league_members_table).values(league_id=LID,user_id=m.user_id,roster_data=json.dumps(m.roster)))
    return world

def request(body=None,token=TOKEN,strict=True):
    b={'league_id':LID,'pinned_give_players':['give'],'fairness_threshold':.5,'page':1}
    if body:b.update(body)
    h={'X-Session-Token':token}
    if strict:h['X-FTF-Current-Only']='1'
    r=server.app.test_client().post('/api/trades/generate',json=b,headers=h)
    assert r.status_code==200,r.json
    return r.json

def test_simultaneous_real_routes_one_worker_and_individual_search_ids(selected,monkeypatch):
    barrier=Barrier(2);capture=server._capture_trade_execution
    def synchronized(*a):
        result=capture(*a);barrier.wait(timeout=5);return result
    monkeypatch.setattr(server,'_capture_trade_execution',synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda n:request({'search_id':'search-'+str(n)}),range(2)))
    assert results[0]['job_id']==results[1]['job_id']
    assert [r['search_id'] for r in results]==['search-0','search-1']
    assert len(selected.pending)==1
    assert not server._trade_jobs_by_key
    assert not any('_selected' in key for row in results for key in row)

@pytest.mark.parametrize('change',[
    {'pinned_give_players':['other','give']},{'pinned_receive_players':['receive']},
    {'pinned_give_mode':'all'},{'opponent_user_id':'opponent'},
    {'trade_intent':'tier_up'},{'fairness_threshold':.5001},
])
def test_changed_exact_request_is_independent_without_revoking_original(selected,change):
    first=request();second=request(change)
    assert first['job_id']!=second['job_id'] and len(selected.pending)==2
    assert all(server._job_live(j) for j in server._trade_jobs.values())

@pytest.mark.parametrize('change',['token','service','trader','league','players','roster','incarnation'])
def test_changed_source_identity_refuses_join(selected,monkeypatch,change):
    first=request();s=selected.session;tok=TOKEN
    if change=='token':
        tok='second-synthetic-token';monkeypatch.setitem(server._sessions,tok,s)
    if change=='service':
        new=copy.copy(s['service']);s['service']=new;s['services']={FMT:new}
    if change=='trader':
        new=copy.copy(s['trade_svc']);s['trade_svc']=new;s['trade_svcs']={FMT:new}
    if change=='league':s['league']=copy.deepcopy(s['league'])
    if change=='players':s['players']=list(reversed(s['players']))
    if change=='roster':s['user_roster']=list(reversed(s['user_roster']))
    if change=='incarnation':
        from backend import user_data_lifecycle as lifecycle
        with lifecycle.hold([UID]):lifecycle.invalidate([UID])
    second=request(token=tok)
    assert first['job_id']!=second['job_id'] and len(selected.pending)==2

@pytest.mark.parametrize('knob',[0.,1.])
def test_force_never_joins_or_revokes_selected_existing(selected,monkeypatch,knob):
    monkeypatch.setitem(server._trade_service_mod._cfg,'force_supersedes_running',knob)
    first=request();forced=request({'force':True})
    assert first['job_id']!=forced['job_id']
    assert all(server._job_live(j) for j in server._trade_jobs.values())
    assert request()['job_id']==forced['job_id']

@pytest.mark.parametrize('state',['complete','error','revoked','stalled'])
def test_terminal_or_stalled_job_never_joins(selected,monkeypatch,state):
    first=request();job=server._trade_jobs[first['job_id']]
    if state=='complete':server._finish_trade_job(first['job_id'])
    elif state=='error':server._finish_trade_job(first['job_id'],error='synthetic')
    elif state=='revoked':
        with server._trade_jobs_lock:server._revoke_trade_job_locked(job)
    else:monkeypatch.setattr(server,'_trade_job_stalled',lambda j,now: j is job)
    second=request();assert first['job_id']!=second['job_id']
    assert '_selected_source' not in job and '_selected_shape' not in job

@pytest.mark.parametrize('field',['request_signature','roster_fp','values_snapshot_id'])
def test_missing_stored_authority_cannot_use_permissive_legacy_helpers(selected,field):
    first=request();server._trade_jobs[first['job_id']].pop(field)
    second=request();assert first['job_id']!=second['job_id']


def test_member_edit_revokes_original_and_captured_copy(selected):
    first=request();job=server._trade_jobs[first['job_id']];copied=copy.deepcopy(job)
    server._invalidate_trade_jobs(user_id='opponent',league_id=LID)
    assert server._trade_job_revoked(job) and server._trade_job_revoked(copied)
    second=request();assert first['job_id']!=second['job_id']


def test_bounded_index_eviction_does_not_cancel_existing_workers(selected,monkeypatch):
    monkeypatch.setattr(server,'_SELECTED_TRADE_JOIN_LIMIT',2)
    results=[request({'pinned_give_players':[pid]}) for pid in ['give','other','receive']]
    assert len(server._selected_trade_jobs)==2
    assert len(selected.pending)==3
    assert all(server._job_live(server._trade_jobs[r['job_id']]) for r in results)
    assert request()['job_id']!=results[0]['job_id']


def test_legacy_requests_remain_independent(selected):
    first=request(strict=False);second=request(strict=False)
    assert first['job_id']!=second['job_id'] and not server._selected_trade_jobs

@pytest.mark.parametrize('fingerprints',[None,('', 'values'),('roster',''),(None,'values')])
def test_missing_current_authority_starts_independent_work(selected,monkeypatch,fingerprints):
    first=request()
    monkeypatch.setattr(server,'_trade_current_fingerprints',lambda *a,**kw:fingerprints)
    second=request()
    assert first['job_id']!=second['job_id'] and len(selected.pending)==2


def test_hash_collision_never_joins_different_shapes(selected,monkeypatch):
    monkeypatch.setattr(server,'_selected_trade_join_key',lambda shape:'deliberate-collision')
    first=request();second=request({'pinned_give_players':['other']})
    assert first['job_id']!=second['job_id'] and len(selected.pending)==2
    assert all(server._job_live(j) for j in server._trade_jobs.values())


def test_full_request_not_truncated_when_join_metadata_exceeds_bound(selected,monkeypatch):
    monkeypatch.setattr(server,'_SELECTED_TRADE_SHAPE_BYTES',1)
    first=request();second=request()
    assert first['job_id']!=second['job_id'] and not server._selected_trade_jobs
    assert [p['args'][4] for p in selected.pending]==[['give'],['give']]


def test_viewer_edit_during_second_capture_refuses_claim_and_delivery(selected,monkeypatch):
    first=request();capture=server._capture_trade_execution
    def changed(*a):
        result=capture(*a);server._invalidate_trade_jobs(user_id=UID,league_id=LID);return result
    monkeypatch.setattr(server,'_capture_trade_execution',changed)
    response=server.app.test_client().post('/api/trades/generate',json={'league_id':LID,'pinned_give_players':['give'],'fairness_threshold':.5,'page':1},headers={'X-Session-Token':TOKEN,'X-FTF-Current-Only':'1'})
    assert response.status_code==409 and not response.json['cards']
    assert len(selected.pending)==1 and server._trade_job_revoked(server._trade_jobs[first['job_id']])


def test_join_reenters_normal_serve_and_paywall_gate(selected,monkeypatch):
    first=request();seen=[];serve=server._serve_trade_job
    def record(*a,**kw):seen.append((a,kw));return serve(*a,**kw)
    monkeypatch.setattr(server,'_serve_trade_job',record)
    assert request({'search_id':'another-search'})['job_id']==first['job_id']
    assert len(seen)==1 and seen[0][0][1]['job_id']==first['job_id']
    monkeypatch.setattr(server._paywall_gate,'applies',lambda *a:True)
    monkeypatch.setattr(server._paywall_gate,'verdict',lambda *a,**kw:(402,{'error':'pro_required','gate':'synthetic-deny'}))
    response=server.app.test_client().post('/api/trades/generate',json={'league_id':LID,'pinned_give_players':['give'],'page':1},headers={'X-Session-Token':TOKEN,'X-FTF-Current-Only':'1'})
    assert response.status_code==402 and len(seen)==1 and len(selected.pending)==1


def test_join_currentness_failure_withholds_even_after_matching_claim(selected,monkeypatch):
    first=request();original=server._serve_trade_job
    def revoke_before_serve(*a,**kw):
        server._invalidate_trade_jobs(user_id=UID,league_id=LID)
        return original(*a,**kw)
    monkeypatch.setattr(server,'_serve_trade_job',revoke_before_serve)
    response=server.app.test_client().post('/api/trades/generate',json={'league_id':LID,'pinned_give_players':['give'],'fairness_threshold':.5,'page':1},headers={'X-Session-Token':TOKEN,'X-FTF-Current-Only':'1'})
    assert response.status_code==409 and not response.json['cards'] and len(selected.pending)==1
    assert server._trade_job_revoked(server._trade_jobs[first['job_id']])


def test_actual_account_delete_recreate_never_joins_or_executes_old_lease(selected,monkeypatch):
    with selected.engine.begin() as c:
        c.execute(insert(db.users_table).values(sleeper_user_id=UID,username='Synthetic',created_at='2026-01-01',verified_via='sleeper'))
    first=request();old_job=server._trade_jobs[first['job_id']];old_worker=selected.pending[0]
    monkeypatch.setattr(server,'_kick_deletion_scrub',lambda:None)
    deleted=server.app.test_client().delete('/api/account',headers={'X-Session-Token':TOKEN})
    assert deleted.status_code==200,deleted.json
    assert server._trade_job_revoked(old_job) and '_selected_source' not in old_job
    with selected.engine.begin() as c:
        c.execute(insert(db.users_table).values(sleeper_user_id=UID,username='Synthetic again',created_at='2026-11-07',verified_via='sleeper'))
    restored=dict(selected.session);restored.pop('_revoked',None)
    monkeypatch.setitem(server._sessions,TOKEN,restored)
    second=request();assert first['job_id']!=second['job_id']
    executions=[];monkeypatch.setattr(server,'_run_trade_job',lambda *a,**kw:executions.append(1))
    old_worker['target'](*old_worker['args'],**old_worker['kwargs'])
    assert not executions and server._trade_job_revoked(old_job)

@pytest.mark.parametrize('selection',[
    {'pinned_give_players':[],'pinned_receive_players':['receive']},
    {'pinned_give_players':[],'opponent_user_id':'opponent'},
    {'pinned_give_players':['give'],'trade_intent':'tier_up'},
])
def test_supported_selected_variants_join_running_exactly(selected,selection):
    first=request(selection);second=request(selection)
    assert first['job_id']==second['job_id'] and len(selected.pending)==1
    assert not server._trade_jobs_by_key


def test_selector_order_is_not_silently_normalized(selected):
    first=request({'pinned_give_players':['give','other']})
    second=request({'pinned_give_players':['other','give']})
    assert first['job_id']!=second['job_id'] and len(selected.pending)==2


def test_same_token_account_binding_change_cannot_join(selected):
    first=request();selected.session['account_id']='different-synthetic-account'
    second=request();assert first['job_id']!=second['job_id']
