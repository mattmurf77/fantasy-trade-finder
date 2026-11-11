"""Independent public-read boundary checks; synthetic SQLite, no provider requests."""
import json
import pytest
from sqlalchemy import event
from backend import database as db
from backend.league_projections import api,batch,store
from backend.league_projections.core import VERSION
from backend.league_projections.simulation import config
from backend.tests.test_league_projection_routes import client,engine
from backend.tests.test_league_projection_saved_reads import seed,selected,PUBLIC_FIELDS

@pytest.mark.parametrize('foreign', ['owner','league'])
def test_corrupt_foreign_target_pointers_never_expose_rows(client,engine,foreign):
    http,_=client
    rid,_=seed(engine)
    with engine.begin() as c:
        c.execute(db.league_projection_runs_table.update().values(**({'user_id':'account-1'} if foreign=='owner' else {'league_id':'456'})))
    reply=http.get('/api/leagues/123/projection-runs/latest')
    assert reply.status_code==200 and reply.json['run'] is None and reply.json['attempt'] is None
    assert http.get('/api/projection-runs/'+rid).status_code==404

@pytest.mark.parametrize('status', ['queued','running','failed','cancelled'])
def test_incomplete_read_export_exact_baseline_response(client,engine,monkeypatch,status):
    http,_=client;rid,_=seed(engine)
    with engine.begin() as c:
        c.execute(db.league_projection_runs_table.update().values(status=status,result_json=None,reason='known_reason'))
    urls=[f'/api/projection-runs/{rid}{s}' for s in ('','/teams','/draft','/teams/1/weeks','/export/manifest','/export/csv')]
    current=[http.get(u) for u in urls]
    monkeypatch.setattr(store,'public_rows',lambda ids,u,l:{i:row for i in ids if i and (row:=store.get(i,u,l))})
    old=[http.get(u) for u in urls]
    assert [(r.status_code,r.data,r.content_type) for r in current]==[(r.status_code,r.data,r.content_type) for r in old]
    assert current[0].status_code==200 and all(r.status_code==409 for r in current[1:])


def test_no_cached_result_after_owner_deletion_and_same_id_recreation(client,engine):
    http,_=client;rid,_=seed(engine)
    assert http.get('/api/projection-runs/'+rid).status_code==200
    # Production deletion removes target/run rows; no cache may survive that commit.
    with engine.begin() as c:
        c.execute(db.league_projection_targets_table.delete())
        c.execute(db.league_projection_runs_table.delete())
        c.execute(db.users_table.delete().where(db.users_table.c.sleeper_user_id=='account'))
        c.execute(db.users_table.insert().values(sleeper_user_id='account',verified_via='sleeper',created_at='2026-11-07T18:00:00+00:00'))
    assert http.get('/api/projection-runs/'+rid).status_code==404
    r=http.get('/api/leagues/123/projection-runs/latest').json
    assert r['run'] is None and r['attempt'] is None


def test_cancel_reads_only_public_columns_and_preserves_snapshot(client,engine):
    http,_=client;rid,_=seed(engine)
    before=store.get(rid,'account','123')
    with engine.begin() as c:
        c.execute(db.league_projection_runs_table.update().values(status='running'))
    with selected(engine) as statements:
        r=http.post(f'/api/projection-runs/{rid}/cancel')
    assert r.status_code==200 and r.json['status']=='cancelled'
    assert len(statements)==2
    assert all({col.name for col in s.selected_columns}==PUBLIC_FIELDS for s in statements)
    assert store.get(rid,'account','123')['snapshot_json']==before['snapshot_json']


def test_scenario_still_loads_exact_full_snapshot_but_never_exposes_it(client,engine,monkeypatch):
    http,_=client;rid,_=seed(engine)
    cfg=config(batch.settings()['model']);snapshot={'captured_at':'2026-11-07T10:00:00+00:00','private_saved_inputs':{'nested':[1,2,3]}}
    with engine.begin() as c:
        c.execute(db.league_projection_runs_table.update().values(snapshot_json=json.dumps(snapshot),result_json=json.dumps({'model_version':VERSION,'config':cfg})))
    saved=[]
    def create(uid,lid,inputs,**kw):
        saved.append((uid,lid,inputs,kw))
        return dict(run_id='b'*32,status='queued',created_at='now',updated_at='now')
    monkeypatch.setattr(store,'create',create)
    monkeypatch.setattr(store,'public_rows',lambda *a,**k:pytest.fail('scenario used public row instead of saved full inputs'))
    with selected(engine) as statements:
        r=http.post('/api/leagues/123/projection-runs',json={'baseline_run_id':rid,'config':{**cfg,'seed':cfg['seed']+1}})
    assert r.status_code==202 and saved[0][3]['snapshot']==snapshot
    assert saved[0][0:2]==('account','123')
    assert len(statements)==1 and 'snapshot_json' in {c.name for c in statements[0].selected_columns}
    assert 'private_saved_inputs' not in r.get_data(as_text=True)


def test_unknown_and_invalid_ids_do_not_turn_into_broad_reads(client,engine):
    http,_=client;seed(engine)
    with selected(engine) as statements:
        for rid in ('bad','Z'*32,'a'*33):
            assert http.get('/api/projection-runs/'+rid).status_code==404
    assert statements==[]
    assert http.get('/api/projection-runs/'+'c'*32).status_code==404


def test_latest_no_target_does_not_read_runs(client,engine):
    http,_=client
    with selected(engine) as statements:
        r=http.get('/api/leagues/123/projection-runs/latest')
    assert statements==[] and r.json['state']=='no_run'
