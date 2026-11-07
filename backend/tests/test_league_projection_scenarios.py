import json
from types import SimpleNamespace
from flask import Flask
import pytest
from backend import database as db
from backend.league_projections import api, simulation, store, service, batch
from backend.tests.test_outlook_calibration_persistence import engine
from backend.tests.test_league_projection_simulation import config, snapshot


def test_explicit_comparison_freezes_owned_baseline_and_does_not_wake_worker(engine,monkeypatch):
    cfg=simulation.config(config()); source=snapshot()
    baseline='a'*32
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.insert().values(run_id=baseline,user_id='account',league_id='123',status='complete',
            created_at=store.utc_now(),updated_at=store.utc_now(),expires_at='2026-01-01T00:00:00+00:00',
            request_hash='baseline',input_json='{}',snapshot_json=json.dumps(source),result_json=json.dumps({'config':cfg})))
    monkeypatch.setattr(api,'is_enabled',lambda k:True)
    monkeypatch.setattr(batch,'settings',lambda:{'policy_approved':True, 'retention_days':7})
    monkeypatch.setattr(service,'wake',lambda *a:pytest.fail('explicit POST queues; cron owns work'))
    app=Flask('projection-scenario-test');sess={'user_id':'account','league':SimpleNamespace(league_id='123',platform='sleeper')}
    api.install(app,require_session=lambda:sess,read_denial=lambda s:None,write_denial=lambda s:None,league_user_id=lambda s:'account',fetch_json=lambda *a:pytest.fail('POST fetched provider'))
    client=app.test_client()
    response=client.post('/api/leagues/123/projection-runs',json={'baseline_run_id':baseline,'config':{**cfg,'historical_weight':.4}})
    assert response.status_code==202
    queued=store.get(response.json['run_id'],'account','123')
    assert queued['status']=='queued' and json.loads(queued['snapshot_json'])==source
    assert json.loads(queued['input_json'])['kind']=='scenario'
    assert json.loads(queued['input_json'])['baseline_run_id']==baseline
    response=client.post('/api/leagues/123/projection-runs',json={'baseline_run_id':baseline,'config':{**cfg,'ir_maxpf':'exclude'}})
    assert response.status_code==400 and response.json['error']=='scenario_requires_new_eligibility_snapshot'


@pytest.mark.parametrize('provider_approved,policy_approved', [(False, False), (False, True), (True, False)])
def test_scenario_cannot_bypass_provider_or_policy_gate(engine, monkeypatch, provider_approved, policy_approved):
    monkeypatch.setattr(api, 'is_enabled', lambda key: key == 'league.projections' or provider_approved)
    monkeypatch.setattr(batch, 'settings', lambda: {'policy_approved': policy_approved})
    monkeypatch.setattr(store, 'create', lambda *a, **k: pytest.fail('unapproved scenario enqueued'))
    app = Flask('gated-projection'); sess = {'user_id': 'account', 'league': SimpleNamespace(league_id='123')}
    api.install(app, require_session=lambda: sess, read_denial=lambda s: None, write_denial=lambda s: None,
                league_user_id=lambda s: 'account', fetch_json=lambda *a: pytest.fail('provider fetch'))
    response = app.test_client().post('/api/leagues/123/projection-runs', json={'config': config()})
    assert response.status_code == 422
    assert response.json['reason'] == ('new_projection_provider_approval_pending' if not provider_approved else 'projection_policy_approval_pending')


def test_scenario_cannot_relabel_strict_snapshot_as_sparse(engine, monkeypatch):
    cfg = simulation.config(config()); baseline = 'c' * 32
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.insert().values(run_id=baseline,user_id='account',league_id='123',status='complete',
            created_at=store.utc_now(),updated_at=store.utc_now(),expires_at=store.utc_now(),request_hash='strict',input_json='{}',
            snapshot_json=json.dumps(snapshot()),result_json=json.dumps({'config':cfg})))
    monkeypatch.setattr(api, 'is_enabled', lambda key: True)
    monkeypatch.setattr(batch, 'settings', lambda: {'policy_approved': True, 'retention_days':7})
    app=Flask('projection-contract'); sess={'user_id':'account','league':SimpleNamespace(league_id='123')}
    api.install(app,require_session=lambda:sess,read_denial=lambda s:None,write_denial=lambda s:None,league_user_id=lambda s:'account',fetch_json=lambda *a:None)
    response=app.test_client().post('/api/leagues/123/projection-runs',json={'baseline_run_id':baseline,'config':{**cfg,'scoring_contract':'sleeper_sparse_offense_v1'}})
    assert response.status_code==400
    assert response.json['error']=='scenario_requires_new_eligibility_snapshot'
