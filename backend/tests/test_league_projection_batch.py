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
