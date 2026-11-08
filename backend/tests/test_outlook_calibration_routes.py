"""Independent real Flask auth, ownership, rollout/rollback and round readback."""
import json
from types import SimpleNamespace
import pytest
from backend import server, feature_flags as ff, database as db, outlook_calibration as oc
from backend.tests.test_outlook_calibration_persistence import engine, session, card, answer

TOKEN='synthetic-independent-calibration-token'
AUTH={'X-Session-Token':TOKEN}

@pytest.fixture
def route_client(engine,monkeypatch):
    monkeypatch.setattr(ff,'_flags_cache',{**ff.DEFAULT_FLAGS,'grading.blind':True,'grading.outlook_round':True})
    monkeypatch.setattr(oc,'kick_worker',lambda:None)
    from backend import outlook_calibration_adapter as adapter
    monkeypatch.setattr(adapter,'is_current',lambda *a,**k:True)
    sess={'user_id':'account','league_user_id':'seat','verified':True,'last_active':0.,
          'league':SimpleNamespace(league_id='league',platform='sleeper'),'players':[], 'trade_svc':object()}
    server._sessions[TOKEN]=sess
    server.app.config['TESTING']=True
    yield server.app.test_client(),sess
    server._sessions.pop(TOKEN,None)

def test_new_round_public_audience_start_and_old_history_isolation(route_client):
    client,sess=route_client
    db.insert_grading_session(session('old',round_id=None),[card('old-c','old')])
    before=db.load_grading_session('old')
    r=client.post('/api/grading/sessions',json={'league_id':'league'},headers=AUTH)
    assert r.status_code==202,r.json
    assert r.json['session']['session_id']!='old'
    assert r.json['session']['status']=='building'
    source=json.loads(db.load_grading_session(r.json['session']['session_id'])['source_json'])
    assert source['seat']=='seat'
    assert db.load_grading_session('old')==before
    assert server._calibration_allowed(sess) is True

def test_actual_auth_foreign_ownership_and_unverified_fail_closed(route_client):
    client,sess=route_client
    db.insert_grading_session(session('s'),[card('c','s')])
    paths=['/api/grading/sessions/s/next','/api/grading/sessions/s/results']
    current_path='/api/grading/sessions/current?league_id=league'
    for path in [*paths,current_path]:assert client.get(path).status_code==404
    sess['user_id']='foreign'
    for path in paths:assert client.get(path,headers=AUTH).status_code==404
    current=client.get(current_path,headers=AUTH)
    assert current.status_code==200 and current.json=={'session':None}
    assert client.post('/api/grading/cards/c',json={'grade':5},headers=AUTH).status_code==404
    sess['user_id']='account';sess['verified']=False
    assert client.get(paths[0],headers=AUTH).status_code==403
    assert client.get(current_path,headers=AUTH).status_code==403

def test_rollout_off_preserves_owned_partial_answer_and_exact_results(route_client):
    client,sess=route_client
    db.insert_grading_session(session('s'),[card('c1','s'),card('c2','s',2,arms=('value_core',))])
    assert client.get('/api/grading/sessions/s/next',headers=AUTH).status_code==200
    first=client.post('/api/grading/cards/c1',json={'grade':5},headers=AUTH)
    assert first.status_code==200 and first.json['session_status']=='open'
    ff._flags_cache['grading.outlook_round']=False
    current=client.get('/api/grading/sessions/current?league_id=league',headers=AUTH)
    assert current.status_code==200 and current.json['session']['session_id']=='s'
    nextcard=client.get('/api/grading/sessions/s/next',headers=AUTH)
    assert nextcard.status_code==200 and nextcard.json['done'] is False
    assert 'private-version' not in json.dumps(nextcard.json)
    last=client.post('/api/grading/cards/c2',json={'grade':1},headers=AUTH)
    assert last.status_code==200 and last.json['session_status']=='completed'
    retry=client.post('/api/grading/cards/c2',json={'grade':1},headers=AUTH)
    assert retry.status_code==200 and retry.json==last.json
    conflict=client.post('/api/grading/cards/c2',json={'grade':5},headers=AUTH)
    assert conflict.status_code==409 and conflict.json['error']=='answer_conflict'
    result=client.get('/api/grading/sessions/s/results',headers=AUTH)
    assert result.status_code==200
    assert result.json['model_versions']==oc.MODEL_VERSIONS
    assert result.json['round_id']==oc.ROUND_ID
    assert result.json['arms']['current']['n']==1
    assert result.json['arms']['value_core']['n']==1
    assert 'private-version' not in json.dumps(result.json)

@pytest.mark.parametrize('status',['building','failed'])
def test_noncompleted_round_never_claims_done(route_client,status):
    client,_=route_client
    db.insert_grading_session(session('s',status=status),[])
    response=client.get('/api/grading/sessions/s/next',headers=AUTH)
    assert response.status_code==409
    assert response.json.get('done') is not True

def test_first_exposure_freezes_unanswered_deck_across_later_input_changes(route_client,monkeypatch):
    from backend import outlook_calibration_adapter as adapter
    client,_=route_client
    row=session('s');row['source_json']=json.dumps({'seat':'seat','snapshot':{'captured_at':'2026-11-06T12:00:00+00:00'}})
    db.insert_grading_session(row,[card('c','s')])
    first=client.get('/api/grading/sessions/s/next',headers=AUTH)
    assert first.status_code==200 and not first.json['done']
    assert db.load_grading_session('s')['first_exposed_at'] is not None
    monkeypatch.setattr(adapter,'is_current',lambda *a,**k:False)
    current=client.get('/api/grading/sessions/current?league_id=league',headers=AUTH)
    assert current.status_code==200 and current.json['session']['session_id']=='s'
    repeated=client.get('/api/grading/sessions/s/next',headers=AUTH)
    assert repeated.status_code==200 and repeated.json==first.json

def test_current_leaves_stale_ready_deck_for_first_card_to_recheck(route_client, monkeypatch):
    from backend import outlook_calibration_adapter as adapter
    client, _ = route_client
    snapshot = {'captured_at': '2026-11-06T12:00:00+00:00'}
    row = session('s')
    row['source_json'] = json.dumps({'seat': 'seat', 'snapshot': snapshot, 'proofs': {'private': True}})
    db.insert_grading_session(row, [card('c', 's')])
    before = db.load_grading_session('s')
    cards = db.load_grading_cards('s')
    checks, kicks = [], []

    def stale(source, **scope):
        checks.append((source, scope))
        return False

    monkeypatch.setattr(adapter, 'is_current', stale)
    monkeypatch.setattr(oc, 'kick_worker', lambda: kicks.append(True))
    current_path = '/api/grading/sessions/current?league_id=league'
    for _ in range(2):
        current = client.get(current_path, headers=AUTH)
        assert current.status_code == 200
        assert current.json == {'session': {
            'session_id': 's', 'league_id': 'league', 'status': 'open',
            'created_at': before['created_at'], 'completed_at': None,
            'progress': {'answered': 0, 'total': 1}, 'error': None,
            'captured_at': snapshot['captured_at'],
        }}
    assert checks == kicks == []
    assert db.load_grading_session('s') == before
    assert db.load_grading_cards('s') == cards

    next_path = '/api/grading/sessions/s/next'
    response = client.get(next_path, headers=AUTH)
    assert response.status_code == 409
    assert response.json == {'error': 'comparison_not_ready'}
    assert checks == [(snapshot, {'user_id': 'account', 'league_user_id': 'seat', 'league_id': 'league'})]
    assert len(kicks) == 1
    retired = db.load_grading_session('s')
    assert retired['status'] == 'failed'
    assert json.loads(retired['error_json']) == {'code': 'comparison_stale'}
    assert retired['first_exposed_at'] is None
    assert db.load_grading_cards('s') == cards

    # A client must rediscover /current; retrying this retired ID cannot
    # resume the replacement and must never expose the old private deck.
    current = client.get(current_path, headers=AUTH)
    assert current.status_code == 200
    assert current.json['session']['session_id'] != 's'
    assert current.json['session']['status'] == 'building'
    assert len(kicks) == 2  # A saved building session can recover its worker.
    for _ in range(2):
        repeated = client.get(next_path, headers=AUTH)
        assert repeated.status_code == 409
        assert repeated.json == {'error': 'comparison_not_ready'}
    assert len(checks) == 1
    assert len(kicks) == 2

def test_round_rollback_blocks_new_first_exposure_but_preserves_visible_cohort(route_client):
    client,_=route_client
    row=session('unopened');row['source_json']=json.dumps({'seat':'seat','snapshot':{}})
    db.insert_grading_session(row,[card('unopened-c','unopened')])
    row=session('visible');row['source_json']=json.dumps({'seat':'seat','snapshot':{}})
    db.insert_grading_session(row,[card('visible-c','visible')])
    first=client.get('/api/grading/sessions/visible/next',headers=AUTH)
    assert first.status_code==200 and first.json['done'] is False
    ff._flags_cache['grading.outlook_round']=False
    hidden=client.get('/api/grading/sessions/unopened/next',headers=AUTH)
    assert hidden.status_code==409
    assert db.load_grading_session('unopened')['first_exposed_at'] is None
    repeat=client.get('/api/grading/sessions/visible/next',headers=AUTH)
    assert repeat.status_code==200 and repeat.json==first.json
    grade=client.post('/api/grading/cards/visible-c',json={'grade':5},headers=AUTH)
    assert grade.status_code==200 and grade.json['session_status']=='completed'

def test_private_preparation_queues_without_public_first_exposure(route_client,engine,monkeypatch):
    client,_=route_client
    monkeypatch.setattr(server,'_CRON_SECRET','synthetic-cron-secret')
    ff._flags_cache.update({'grading.outlook_prepare':True,'grading.outlook_round':False})
    with engine.begin() as conn:
        conn.execute(db.users_table.update().where(db.users_table.c.sleeper_user_id == 'account').values(verified_via='sleeper'))
        conn.execute(db.leagues_table.insert().values(sleeper_league_id='league',user_id='account'))
    response=client.post('/api/admin/grading/pregenerate',json={},headers={'X-Cron-Secret':'synthetic-cron-secret'})
    assert response.status_code==202,response.json
    assert response.json['round_id']==oc.ROUND_ID
    assert response.json['batch_pairs']==1
    assert response.json['batch_status_counts']=={'building':1}
    row=session('ready');row['source_json']=json.dumps({'seat':'seat','snapshot':{}})
    db.insert_grading_session(row,[card('ready-c','ready')])
    hidden=client.get('/api/grading/sessions/ready/next',headers=AUTH)
    assert hidden.status_code==409 and hidden.json['error']=='round_paused'
    assert db.load_grading_session('ready')['first_exposed_at'] is None
    noauth=client.post('/api/admin/grading/pregenerate',json={})
    assert noauth.status_code==401


def test_transiently_unavailable_inputs_leave_ready_deck_intact(route_client, monkeypatch):
    from backend import outlook_calibration_adapter as adapter, blind_grading as bg
    client, _ = route_client
    row = session('ready')
    row['source_json'] = json.dumps({'seat': 'seat', 'snapshot': {}})
    db.insert_grading_session(row, [card('c', 'ready')])
    before = db.load_grading_session('ready')
    cards = db.load_grading_cards('ready')

    def unavailable(*a, **kw):
        raise bg.GradingError('comparison_inputs_unavailable', 503)

    monkeypatch.setattr(adapter, 'is_current', unavailable)
    monkeypatch.setattr(oc, 'kick_worker', lambda: pytest.fail('unavailable inputs started a build'))
    current = client.get('/api/grading/sessions/current?league_id=league', headers=AUTH)
    assert current.status_code == 200
    assert current.json['session']['session_id'] == 'ready'
    assert current.json['session']['status'] == 'open'

    next_path = '/api/grading/sessions/ready/next'
    first = client.get(next_path, headers=AUTH)
    start = client.post('/api/grading/sessions', json={'league_id': 'league'}, headers=AUTH)
    for response in (first, start):
        assert response.status_code == 503
        assert response.json == {'error': 'comparison_inputs_unavailable'}
    assert db.load_grading_session('ready') == before
    assert db.load_grading_cards('ready') == cards

    monkeypatch.setattr(adapter, 'is_current', lambda *a, **kw: True)
    retry = client.get(next_path, headers=AUTH)
    assert retry.status_code == 200
    assert retry.json['card']['card_id'] == 'c'
    assert db.load_grading_session('ready')['first_exposed_at'] is not None


@pytest.mark.parametrize('code', ['provider_lineup_unsupported','league_membership_required',
    'provider_account_binding_unavailable'])
def test_failed_current_poll_is_read_only_and_never_requeues(route_client,monkeypatch,code):
    client,_=route_client
    row=session('failed-coverage',status='failed')
    row['error_json']=json.dumps({'code':code})
    db.insert_grading_session(row,[])
    monkeypatch.setattr(oc,'kick_worker',lambda:pytest.fail('failed GET started worker'))
    monkeypatch.setattr(oc,'start_session',lambda **kw:pytest.fail('failed GET requeued'))
    before=db.load_grading_session('failed-coverage')
    for _ in range(5):
        response=client.get('/api/grading/sessions/current?league_id=league',headers=AUTH)
        assert response.status_code==200
        assert response.json['session']['status']=='failed'
        assert response.json['session']['error']=={'code':code}
    assert db.load_grading_session('failed-coverage')==before
