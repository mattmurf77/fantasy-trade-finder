"""Current v4 cannot silently reuse pre-v4 saved inputs or queued requests."""
import json
import pytest
from backend import database as db
from backend.league_projections import store, service, batch
from backend.league_projections.core import VERSION
from backend.tests.test_outlook_calibration_persistence import engine
from backend.tests.test_league_projection_simulation import snapshot, config
from backend.tests.test_league_projection_routes import client
def test_v3_saved_result_readable_but_not_weight_only_v4_baseline(client,engine):
 http,_=client;run_id='c'*32
 result={'model_version':'joint-season-scenario-v3','config':config(),'historical_saved_result':True}
 with engine.begin() as conn:
  conn.execute(db.league_projection_runs_table.insert().values(run_id=run_id,user_id='account',league_id='123',status='complete',created_at='2026-11-01T00:00:00+00:00',updated_at='2026-11-01T00:00:00+00:00',expires_at='2099-01-01T00:00:00+00:00',request_hash='old-version',input_json='{}',snapshot_json='{"source":"frozen-v2"}',result_json=json.dumps(result)))
  conn.execute(db.league_projection_targets_table.insert().values(target_id='old-target',user_id='account',league_id='123',league_user_id='account',season=2026,created_at='2026-11-01T00:00:00+00:00',next_due_at='2099-01-01T00:00:00+00:00',last_success_id=run_id,last_attempt_id=run_id))
 assert http.get('/api/leagues/123/projection-runs/latest').json['run']['result']==result
 response=http.post('/api/leagues/123/projection-runs',json={'config':{**config(),'historical_weight':.4},'baseline_run_id':run_id})
 assert response.status_code==400 and response.json['error']=='comparison_requires_current_model_baseline'
 assert http.get('/api/projection-runs/'+run_id).json['result']==result
 with engine.connect() as conn:assert len(conn.execute(db.select(db.league_projection_runs_table)).all())==1


def test_old_queued_scenario_cannot_cross_model_version_during_worker_resume(engine,monkeypatch):
 old_id='d'*32;frozen=snapshot()
 from datetime import datetime,timezone
 created=datetime.now(timezone.utc).isoformat()
 with engine.begin() as conn:
  conn.execute(db.league_projection_runs_table.insert().values(run_id=old_id,user_id='account',league_id='123',status='complete',created_at=created,updated_at=created,expires_at='2099-01-01T00:00:00+00:00',request_hash='v2-baseline',input_json='{}',snapshot_json=json.dumps(frozen),result_json=json.dumps({'model_version':'joint-season-scenario-v3','config':config()})))
 queued=store.create('account','123',{'league_user_id':'account','kind':'scenario','baseline_run_id':old_id,'config':config()},snapshot=frozen)
 monkeypatch.setattr(service,'is_enabled',lambda key:True)
 options={**batch.settings(),'policy_approved':True};monkeypatch.setattr(batch,'settings',lambda:options)
 called=[]
 def simulate(value,cfg,**kw):called.append(True);return {'model_version':VERSION,'source':'wrong-version-comparison'}
 monkeypatch.setattr(service,'simulate',simulate)
 service._run(lambda *a:pytest.fail('saved scenario must not fetch'))
 saved=store.get(queued['run_id'],'account','123')
 assert called==[], 'Worker must revalidate baseline version after deploy/recovery, before simulation or result reuse'
 assert saved['result_json'] is None and saved['reason']=='comparison_requires_current_model_baseline'


@pytest.mark.parametrize('old_version',[None,'joint-season-scenario-v3'])
def test_legacy_unversioned_or_old_version_queue_cannot_resume_as_current_model(engine,monkeypatch,old_version):
 queued=store.create('account','123',{'league_user_id':'account','kind':'scenario','config':config()},snapshot=snapshot())
 inputs=json.loads(queued['input_json'])
 if old_version is None:inputs.pop('expected_model_version')
 else:inputs['expected_model_version']=old_version
 with engine.begin() as conn:conn.execute(db.league_projection_runs_table.update().where(db.league_projection_runs_table.c.run_id==queued['run_id']).values(input_json=json.dumps(inputs)))
 monkeypatch.setattr(service,'is_enabled',lambda key:True)
 options={**batch.settings(),'policy_approved':True};monkeypatch.setattr(batch,'settings',lambda:options)
 monkeypatch.setattr(service,'simulate',lambda *a,**k:pytest.fail('old queue version must fail before compute'))
 service._run(lambda *a:pytest.fail('old queue version must fail before provider fetch'))
 saved=store.get(queued['run_id'],'account','123')
 assert saved['status']=='failed' and saved['reason']=='queued_projection_model_changed' and saved['result_json'] is None

