"""Independent synthetic release controls for explicit first-baseline preparation."""
import json
from datetime import datetime, timezone
import pytest
from sqlalchemy import event
from backend import database as db, outlook_calibration as calibration
from backend.league_projections import batch,store,service
from backend.tests.test_outlook_calibration_persistence import engine

@pytest.fixture
def world(engine,monkeypatch):
    monkeypatch.setattr(batch,'is_enabled',lambda key:True)
    monkeypatch.setattr(service,'wake',lambda *a, **kw:None)
    opts={**batch.settings(),'policy_approved':True}
    monkeypatch.setattr(batch,'settings',lambda:opts)
    pairs=[{'user_id':'account','league_user_id':'account','league_id':'123'}]
    monkeypatch.setattr(calibration,'connected_targets',lambda:(pairs,{}))
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id='123',user_id='account',platform='sleeper',season='2026'))
    batch.register('account','123','account',2026)
    return engine,pairs

def no_fetch(*args,**kwargs):pytest.fail('dispatch must enqueue, not fetch provider')

def initial():return batch.dispatch(no_fetch,initial=True,user_id='account',league_id='123')

def rows(engine):
    with engine.connect() as conn:return list(conn.execute(db.select(db.league_projection_runs_table)).mappings())

@pytest.mark.parametrize('finish',['failed','complete'])
def test_initial_once_preserves_weekly_and_never_restarts_attempted_target(world,finish):
    engine,_=world
    assert batch.dispatch(no_fetch)['queued']==0
    before=batch.target('account','123')['next_due_at']
    assert initial()['queued']==1
    target=batch.target('account','123');job=rows(engine)[0]
    assert target['next_due_at']==before
    assert json.loads(job['input_json'])['scheduled_slot'].startswith('initial:')
    assert initial()['queued']==0 and batch.dispatch(no_fetch)['queued']==0
    claimed=store.claim()
    if finish=='complete':assert store.finish(claimed,{'model_version':'synthetic','captured_at':'synthetic'})
    else:
        from backend.league_projections.core import Unavailable
        store.fail(claimed,Unavailable('synthetic_unavailable'))
    assert initial()['queued']==0 and len(rows(engine))==1


def test_initial_overdue_target_does_not_trigger_second_baseline_next_tick(world):
    engine,_=world
    with engine.begin() as conn:conn.execute(db.league_projection_targets_table.update().values(next_due_at='2020-01-01T00:00:00+00:00'))
    assert initial()['queued']==1
    assert datetime.fromisoformat(batch.target('account','123')['next_due_at'])>datetime.now(timezone.utc)
    assert batch.dispatch(no_fetch)['queued']==0 and len(rows(engine))==1


def test_stale_initial_selection_cannot_overwrite_an_attempt_before_lease_CAS(world):
    engine,_=world;trigger=[]
    def race(conn,cursor,statement,parameters,context,executemany):
        if not trigger and statement.startswith('UPDATE league_projection_targets SET lease_until='):
            trigger.append(True)
            conn.exec_driver_sql("UPDATE league_projection_targets SET last_attempt_id='racing-attempt' WHERE league_id='123'")
    event.listen(engine,'before_cursor_execute',race)
    try:assert initial()['queued']==0
    finally:event.remove(engine,'before_cursor_execute',race)
    assert trigger and not rows(engine)
    assert batch.target('account','123')['last_attempt_id']=='racing-attempt'


def test_own_action_removed_target_is_not_initially_enqueued(world):
    engine,pairs=world;pairs.clear()
    assert initial()['queued']==0 and not rows(engine)


def test_crash_after_atomic_initial_insert_still_consumes_initial_once(world,monkeypatch):
    engine,_=world;original=store.create
    class Crash(BaseException):pass
    def crash(*args,**kwargs):original(*args,**kwargs);raise Crash()
    monkeypatch.setattr(store,'create',crash)
    with pytest.raises(Crash):initial()
    monkeypatch.setattr(store,'create',original)
    assert initial()['queued']==0 and batch.dispatch(no_fetch)['queued']==0 and len(rows(engine))==1


def test_deleted_recreated_account_during_initial_cannot_restore_target(world,monkeypatch):
    engine,_=world;original=store.create
    def recreate(*args,**kwargs):
        with engine.begin() as conn:
            conn.execute(db.league_projection_targets_table.delete())
            conn.execute(db.users_table.delete().where(db.users_table.c.sleeper_user_id=='account'))
            conn.execute(db.users_table.insert().values(sleeper_user_id='account',created_at='2099-01-01',verified_via='sleeper'))
        return original(*args,**kwargs)
    monkeypatch.setattr(store,'create',recreate)
    assert initial()['queued']==0 and not rows(engine)
    assert batch.target('account','123') is None

@pytest.mark.parametrize('options',[{'initial':1},{'initial':True,'limit':True},{'initial':True,'limit':5},{'initial':True,'user_id':'account'},{'initial':False,'limit':1}])
def test_initial_input_contract_refuses_coercion(world,options):
    with pytest.raises(ValueError):batch.dispatch(no_fetch,**options)
    assert not rows(world[0])
