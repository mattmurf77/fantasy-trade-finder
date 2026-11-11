"""Weekly projection batch: one baseline per slot, crash and recreation fences,
and the operator-only retry_incomplete option (a target whose last attempt
stopped incomplete under the current model is made due now; nothing else is,
scheduled ticks never pass it, and it is refused outside weekly mode)."""
import pytest
from backend import database as db,feature_flags as ff
from backend.league_projections import batch,store,service
from backend.tests.test_outlook_calibration_persistence import engine
from backend.tests.test_league_projection_simulation import config

@pytest.fixture
def scheduled(engine,monkeypatch):
    monkeypatch.setattr(batch,'is_enabled',lambda key:True)
    options={**batch.settings(),'policy_approved':True,'model':config()}
    monkeypatch.setattr(batch,'settings',lambda:options)
    monkeypatch.setattr(service,'wake',lambda *a, **kw:None)
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id='123',user_id='account',platform='sleeper',season='2026'))
    batch.register('account','123','account',2026)
    with engine.begin() as conn:
        conn.execute(db.league_projection_targets_table.update().values(next_due_at='2020-01-01T00:00:00+00:00'))
    return engine


def test_deleted_and_recreated_account_cannot_inherit_stale_batch_request(scheduled,monkeypatch):
    original=store.create
    def recreate_then_create(*args,**kwargs):
        with scheduled.begin() as conn:
            conn.execute(db.league_projection_targets_table.delete().where(db.league_projection_targets_table.c.user_id=='account'))
            conn.execute(db.league_projection_runs_table.delete().where(db.league_projection_runs_table.c.user_id=='account'))
            conn.execute(db.users_table.delete().where(db.users_table.c.sleeper_user_id=='account'))
            conn.execute(db.users_table.insert().values(sleeper_user_id='account',created_at='2099-01-01T00:00:00+00:00',verified_via='sleeper'))
        return original(*args,**kwargs)
    monkeypatch.setattr(store,'create',recreate_then_create)
    batch.dispatch(lambda *a:pytest.fail('unexpected provider access during enqueue'))
    with scheduled.connect() as conn:
        rows=conn.execute(db.select(db.league_projection_runs_table)).mappings().all()
    assert rows==[]


def test_repeated_cron_and_roster_sync_do_not_create_extra_weekly_baselines(scheduled):
    first=batch.dispatch(lambda *a:pytest.fail('enqueue only'))
    assert first['queued']==1
    due=batch.target('account','123')['next_due_at']
    batch.register('account','123','account',2026)
    assert batch.target('account','123')['next_due_at']==due
    second=batch.dispatch(lambda *a:pytest.fail('enqueue only'))
    assert second['queued']==0
    with scheduled.connect() as conn:
        assert len(conn.execute(db.select(db.league_projection_runs_table)).all())==1


def test_new_registered_league_waits_next_weekly_slot(scheduled):
    with scheduled.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id='456',user_id='account',platform='sleeper',season='2026'))
    batch.register('account','456','account',2026)
    from datetime import datetime,timezone
    assert datetime.fromisoformat(batch.target('account','456')['next_due_at'])>datetime.now(timezone.utc)
    batch.dispatch(lambda *a:pytest.fail('enqueue only'))
    with scheduled.connect() as conn:
        assert not conn.execute(db.select(db.league_projection_runs_table).where(db.league_projection_runs_table.c.league_id=='456')).all()
    assert batch.view('account','456')['state']=='no_run'


def test_crash_after_enqueue_cannot_generate_second_baseline_same_slot(scheduled,monkeypatch):
    from datetime import datetime,timezone,timedelta
    original=store.create
    class Crash(BaseException): pass
    def create_then_crash(*args,**kwargs):
        original(*args,**kwargs)
        raise Crash()
    monkeypatch.setattr(store,'create',create_then_crash)
    with pytest.raises(Crash):
        batch.dispatch(lambda *a:pytest.fail('enqueue only'))
    row=store.claim()
    assert store.finish(row,{'synthetic':'complete'})
    with scheduled.begin() as conn:
        conn.execute(db.league_projection_targets_table.update().values(lease_until=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()))
    monkeypatch.setattr(store,'create',original)
    batch.dispatch(lambda *a:pytest.fail('enqueue only'))
    with scheduled.connect() as conn:
        rows=conn.execute(db.select(db.league_projection_runs_table)).mappings().all()
    assert len(rows)==1, 'Durable enqueue must consume its weekly slot even if dispatcher dies before bookkeeping'


def test_finish_baseline_publishes_last_success_without_second_commit(scheduled):
    batch.dispatch(lambda *a:pytest.fail('enqueue only'))
    row=store.claim()
    assert store.finish(row,{'synthetic':'complete'})
    assert batch.target('account','123')['last_success_id']==row['run_id'], 'Worker death after finish must not hide a successfully persisted baseline'


def stop_last_attempt(engine, status, model_version=None):
    """Queue the weekly baseline, then rewrite that attempt's outcome; the target is left due next week."""
    import json
    assert batch.dispatch(lambda *a:pytest.fail('enqueue only'))['queued']==1
    t,r=db.league_projection_targets_table,db.league_projection_runs_table
    with engine.begin() as conn:
        run_id=conn.execute(db.select(t.c.last_attempt_id)).scalar()
        inputs=json.loads(conn.execute(db.select(r.c.input_json).where(r.c.run_id==run_id)).scalar())
        if model_version is not None:
            inputs['expected_model_version']=model_version
        conn.execute(r.update().where(r.c.run_id==run_id).values(status=status,input_json=json.dumps(inputs)))
    return batch.target('account','123')['next_due_at']


def run_count(engine):
    with engine.connect() as conn:
        return len(conn.execute(db.select(db.league_projection_runs_table)).all())


def test_retry_incomplete_requeues_a_current_model_incomplete_baseline_once(scheduled):
    due=stop_last_attempt(scheduled,'incomplete_projections')
    plain=batch.dispatch(lambda *a:pytest.fail('enqueue only'))
    assert plain['queued']==0 and 'retried' not in plain, 'Ordinary ticks keep their shape and never retry'
    result=batch.dispatch(lambda *a:pytest.fail('enqueue only'),retry_incomplete=True)
    assert (result['queued'],result['retried'])==(1,1)
    assert run_count(scheduled)==2
    assert batch.target('account','123')['next_due_at']==batch.next_weekly_slot()>=due


@pytest.mark.parametrize('status',['complete','unsupported_policy','failed','queued','running','stale','cancelled'])
def test_retry_incomplete_leaves_other_outcomes_on_their_weekly_slot(scheduled,status):
    due=stop_last_attempt(scheduled,status)
    result=batch.dispatch(lambda *a:pytest.fail('enqueue only'),retry_incomplete=True)
    assert (result['queued'],result['retried'])==(0,0)
    assert batch.target('account','123')['next_due_at']==due and run_count(scheduled)==1


def test_incomplete_under_another_model_stays_with_the_other_model_rule(scheduled):
    stop_last_attempt(scheduled,'incomplete_projections',model_version='joint-season-scenario-v2')
    result=batch.dispatch(lambda *a:pytest.fail('enqueue only'),retry_incomplete=True)
    assert (result['queued'],result['retried'])==(1,0), 'The model-change rule refreshes it; retry must not count it'


def test_other_model_rule_alone_is_unchanged(scheduled):
    stop_last_attempt(scheduled,'incomplete_projections',model_version='joint-season-scenario-v2')
    result=batch.dispatch(lambda *a:pytest.fail('enqueue only'))
    assert result['queued']==1 and 'retried' not in result


def test_retry_incomplete_skips_a_leased_target(scheduled):
    from datetime import datetime,timezone,timedelta
    due=stop_last_attempt(scheduled,'incomplete_projections')
    with scheduled.begin() as conn:
        conn.execute(db.league_projection_targets_table.update().values(lease_until=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()))
    result=batch.dispatch(lambda *a:pytest.fail('enqueue only'),retry_incomplete=True)
    assert (result['queued'],result['retried'])==(0,0)
    assert batch.target('account','123')['next_due_at']==due


@pytest.mark.parametrize('kwargs',[dict(retry_incomplete=True,initial=True),dict(retry_incomplete=1),dict(retry_incomplete='true')])
def test_retry_incomplete_refuses_initial_mode_and_non_bool(scheduled,kwargs):
    with pytest.raises(ValueError):
        batch.dispatch(None,**kwargs)


@pytest.mark.parametrize('off,expected',[('league.projections',{'status':'disabled','queued':0}),
                                         ('league.projections_provider_approved',{'status':'approval_pending','queued':0})])
def test_retry_incomplete_marks_nothing_when_dispatch_returns_early(scheduled,monkeypatch,off,expected):
    due=stop_last_attempt(scheduled,'incomplete_projections')
    monkeypatch.setattr(batch,'is_enabled',lambda key:key!=off)
    assert batch.dispatch(lambda *a:pytest.fail('enqueue only'),retry_incomplete=True)==expected
    assert batch.target('account','123')['next_due_at']==due


def test_cron_route_passes_retry_incomplete_and_realtime_tick_never_does(monkeypatch):
    from backend import server
    monkeypatch.setattr(server,'_CRON_SECRET','synthetic-secret')
    monkeypatch.setattr(server,'_IS_PROD_ENV',True)
    called=[]
    monkeypatch.setattr(batch,'dispatch',lambda fetch,**kw:called.append(kw) or {'queued':0})
    client,path,headers=server.app.test_client(),'/api/cron/league-projections',{'X-Cron-Secret':'synthetic-secret'}
    assert client.post(path,json={'retry_incomplete':True}).status_code==401
    assert client.post(path,json={'retry_incomplete':True,'force':True},headers=headers).status_code==400
    assert not called
    assert client.post(path,json={'retry_incomplete':True},headers=headers).status_code==200
    assert called==[{'retry_incomplete':True,'foreground_busy':server._projection_foreground_busy}]
    called.clear()
    monkeypatch.setattr(server,'is_enabled',lambda key:key=='league.projections')
    monkeypatch.setattr(server,'load_pending_matches_older_than',lambda cutoff:[])
    assert client.post('/api/cron/realtime-tick',headers=headers).status_code==200
    assert called==[{'foreground_busy':server._projection_foreground_busy}], 'Scheduled ticks never retry on their own'
