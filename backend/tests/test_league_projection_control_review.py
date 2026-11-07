"""Independent scalar SQL and unchanged cancellation/output controls."""
import json
from copy import deepcopy
import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from backend import accounts,database as db
from backend.league_projections import store,service,provider,batch,simulation
from backend.tests.test_outlook_calibration_persistence import engine
from backend.tests.test_league_projection_simulation import snapshot,config


def test_actual_select_shape_payload_absence_and_owned_where_parameters(engine):
    row=store.create('account','123',{'kind':'scenario','config':{}});claimed=store.claim()
    with engine.begin() as conn:conn.execute(db.league_projection_runs_table.update().values(snapshot_json='private-'+('x'*1000000),result_json='private-result',details_json='private-details'))
    clauses=[];sqls=[]
    def clause(conn,element,*args):clauses.append(element)
    def sql(conn,cursor,statement,params,context,many):sqls.append((statement,params))
    event.listen(engine,'before_execute',clause);event.listen(engine,'before_cursor_execute',sql)
    try:
        answer=store.control(row['run_id'],'account','123')
        assert store.control(row['run_id'],'account-1','123') is None
        assert store.control(row['run_id'],'account','456') is None
        assert store.control('foreign-run','account','123') is None
    finally:event.remove(engine,'before_execute',clause);event.remove(engine,'before_cursor_execute',sql)
    assert set(answer)=={'status','worker_token','expires_at'}
    assert answer=={k:claimed[k] for k in answer}
    assert len(clauses)==len(sqls)==4
    for element,(statement,params) in zip(clauses,sqls):
        assert list(element.selected_columns.keys())==['status','worker_token','expires_at']
        assert all(k not in statement for k in ('snapshot_json','input_json','result_json','details_json'))
        postgres=element.compile(dialect=postgresql.dialect())
        assert list(postgres.params.values())==list(params)
        assert set(element.get_final_froms())=={db.league_projection_runs_table}
    assert sqls[0][1]==(row['run_id'],'account','123')

@pytest.mark.parametrize('status',['queued','running','stale','cancelled','failed','complete'])
@pytest.mark.parametrize('token',[None,'original','replacement'])
@pytest.mark.parametrize('expiry',['2000-01-01T00:00:00+00:00','2099-01-01T00:00:00+00:00'])
def test_scalar_fact_predicate_equals_old_full_row_for_all_states(engine,status,token,expiry):
    row=store.create('account','123',{'kind':'scenario','config':{}})
    with engine.begin() as conn:conn.execute(db.league_projection_runs_table.update().values(status=status,worker_token=token,expires_at=expiry))
    full=store.get(row['run_id'],'account','123');tiny=store.control(row['run_id'],'account','123')
    predicate=lambda r:not r or r['status']!='running' or r.get('worker_token')!='original' or r['expires_at']<=store.utc_now()
    assert predicate(full)==predicate(tiny)
    assert tiny=={k:full[k] for k in ('status','worker_token','expires_at')}


def test_actual_account_delete_recreate_never_revives_old_control_or_publish(engine):
    row=store.create('account','123',{'kind':'scenario','config':{}});claimed=store.claim()
    assert store.control(row['run_id'],'account','123')['status']=='running'
    accounts.delete_user_data('account')
    with engine.begin() as conn:conn.execute(db.users_table.insert().values(sleeper_user_id='account',created_at='2099-01-01',verified_via='sleeper'))
    assert store.control(row['run_id'],'account','123') is None
    assert store.get(row['run_id'],'account','123') is None
    assert store.finish(claimed,{'must_not_restore':True}) is False

@pytest.mark.parametrize('race',['cancel','token','delete_recreate'])
def test_control_read_is_not_authority_to_publish_after_later_race(engine,monkeypatch,race):
    row=store.create('account','123',{'kind':'scenario','league_user_id':'account','config':{}})
    monkeypatch.setattr(service,'is_enabled',lambda key:True);monkeypatch.setattr(batch,'settings',lambda:{'policy_approved':True,'retention_days':7})
    monkeypatch.setattr(provider,'capture',lambda *a,**kw:{'source':'synthetic','captured_at':'2026-11-01T00:00:00+00:00'})
    def simulate(snap,cfg,*,cancelled):
        assert cancelled() is False
        if race=='cancel':store.cancel(row['run_id'],'account','123')
        elif race=='token':
            with engine.begin() as conn:conn.execute(db.league_projection_runs_table.update().values(worker_token='new-claim'))
        else:
            accounts.delete_user_data('account')
            with engine.begin() as conn:conn.execute(db.users_table.insert().values(sleeper_user_id='account',created_at='2099-01-01',verified_via='sleeper'))
        return {'must_not_publish':True}
    monkeypatch.setattr(service,'simulate',simulate);service._run(None)
    actual=store.get(row['run_id'],'account','123')
    assert actual is None or actual['result_json'] is None

@pytest.mark.parametrize('use_old_full_read',[False,True])
def test_real_simulation_outputs_and_checkpoint_count_identical(engine,monkeypatch,use_old_full_read):
    frozen=snapshot();cfg=config();expected=simulation.simulate(deepcopy(frozen),cfg)
    queued=store.create('account','123',{'kind':'scenario','league_user_id':'account','config':cfg},snapshot=frozen)
    monkeypatch.setattr(service,'is_enabled',lambda key:True);monkeypatch.setattr(batch,'settings',lambda:{'policy_approved':True,'retention_days':7})
    calls=[];reader=store.get if use_old_full_read else store.control
    def read(*args):calls.append(args);return reader(*args)
    monkeypatch.setattr(store,'control',read)
    service._run(lambda *a:pytest.fail('saved snapshot cannot fetch'))
    result=json.loads(store.get(queued['run_id'],'account','123')['result_json'])
    assert result=={**expected,'reused_compatible_result':False,'verified_at':frozen['captured_at']}
    #2 worker pre/post save + simulation iteration0/500 checks at1000 draws.
    assert len(calls)==4
    assert set(calls)=={(queued['run_id'],'account','123')}
