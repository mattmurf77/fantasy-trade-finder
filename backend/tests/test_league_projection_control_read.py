"""Cancellation reads keep exact owner predicates without transferring snapshots."""
import json
import pytest
from sqlalchemy import event
from backend import database as db
from backend.league_projections import store, service, batch, provider
from backend.tests.test_outlook_calibration_persistence import engine


def test_actual_sql_selects_only_control_columns_and_binds_all_identity_fields(engine):
    row=store.create('account','123',{'kind':'scenario','config':{}})
    claimed=store.claim()
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.update().values(snapshot_json='x'*1000000, result_json='y'*1000000, details_json='private'))
    statements=[]
    def observed(conn,cursor,statement,params,context,many): statements.append((statement,params))
    event.listen(engine,'before_cursor_execute',observed)
    try:
        result=store.control(row['run_id'],'account','123')
        assert store.control(row['run_id'],'account-1','123') is None
        assert store.control(row['run_id'],'account','other') is None
        assert store.control('other','account','123') is None
    finally: event.remove(engine,'before_cursor_execute',observed)
    assert result=={k:claimed[k] for k in ('status','worker_token','expires_at')}
    assert len(statements)==4
    for sql,params in statements:
        projection=sql.split('FROM')[0]
        assert 'snapshot_json' not in sql and 'result_json' not in sql and 'details_json' not in sql and 'input_json' not in sql
        assert projection.count('league_projection_runs.')==3
        assert all('league_projection_runs.'+k+' =' in sql for k in ('run_id','user_id','league_id'))
        assert len(params)==3


def test_control_matches_full_get_through_terminal_expired_and_missing_rows(engine):
    row=store.create('account','123',{'kind':'scenario','config':{}})
    for status in ('queued','running','cancelled','failed','complete'):
        with engine.begin() as conn:
            conn.execute(db.league_projection_runs_table.update().values(status=status,worker_token='lease',expires_at='2000-01-01T00:00:00+00:00'))
        full=store.get(row['run_id'],'account','123')
        assert store.control(row['run_id'],'account','123')=={k:full[k] for k in ('status','worker_token','expires_at')}
    with engine.begin() as conn: conn.execute(db.league_projection_runs_table.delete())
    assert store.control(row['run_id'],'account','123') is None


def test_worker_checkpoints_never_use_payload_get(engine,monkeypatch):
    row=store.create('account','123',{'kind':'scenario','league_user_id':'account','config':{}})
    monkeypatch.setattr(service,'is_enabled',lambda key:True)
    monkeypatch.setattr(batch,'settings',lambda:{'policy_approved':True,'retention_days':7})
    monkeypatch.setattr(provider,'capture',lambda *a,**kw:{'captured_at':'2026-11-07T00:00:00+00:00','source':'fixture'})
    original_get=store.get
    monkeypatch.setattr(store,'get',lambda *a,**kw:pytest.fail('cancellation fetched full payload'))
    def simulate(snapshot,cfg,*,cancelled):
        assert all(not cancelled() for _ in range(5))
        return {'source':'fixture'}
    monkeypatch.setattr(service,'simulate',simulate)
    service._run(lambda url:pytest.fail('no network'))
    assert original_get(row['run_id'],'account','123')['status']=='complete'
