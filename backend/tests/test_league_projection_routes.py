from types import SimpleNamespace as N
import pytest
from flask import Flask
from backend import database as db
from backend.league_projections import api,batch,store,service,provider
from backend.tests.test_outlook_calibration_persistence import engine

@pytest.fixture
def client(engine,monkeypatch):
    app=Flask('independent-projections')
    sess={'user_id':'account','league':N(league_id='123',platform='sleeper')}
    monkeypatch.setattr(api,'is_enabled',lambda key:True)
    monkeypatch.setattr(batch,'is_enabled',lambda key:True)
    options={**batch.settings(),'policy_approved':True}
    monkeypatch.setattr(batch,'settings',lambda:options)
    def forbidden(*a,**k):pytest.fail('screen GET started compute/provider/mutation')
    for module,name in ((service,'wake'),(provider,'capture'),(batch,'dispatch'),(batch,'register'),(store,'maintenance'),(store,'create')):
        monkeypatch.setattr(module,name,forbidden)
    api.install(app,require_session=lambda:sess,read_denial=lambda s:None,write_denial=lambda s:None,league_user_id=lambda s:'account',fetch_json=forbidden)
    return app.test_client(),sess


def test_new_league_get_is_pure_and_has_no_fabricated_projection(client,engine):
    http,_=client
    response=http.get('/api/leagues/123/projection-runs/latest')
    assert response.status_code==200
    assert response.json['run'] is None and response.json['state']=='no_run'
    with engine.connect() as conn:
        assert not conn.execute(db.select(db.league_projection_runs_table)).all()
        assert not conn.execute(db.select(db.league_projection_targets_table)).all()


def test_other_league_cannot_be_read_using_current_session(client):
    http,_=client
    assert http.get('/api/leagues/456/projection-runs/latest').status_code==404


def test_pending_run_get_does_not_start_worker_and_ownership_enforced(client,engine):
    http,sess=client
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.insert().values(run_id='a'*32,user_id='account',league_id='123',status='queued',created_at='2026-11-01T00:00:00+00:00',updated_at='2026-11-01T00:00:00+00:00',expires_at='2099-01-01T00:00:00+00:00',request_hash='synthetic',input_json='{}'))
    assert http.get('/api/projection-runs/'+'a'*32).json['status']=='queued'
    sess['user_id']='another-account'
    assert http.get('/api/projection-runs/'+'a'*32).status_code==404
