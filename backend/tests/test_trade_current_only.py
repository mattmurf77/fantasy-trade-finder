"""Opt-in current-input contract; legacy pages retain their existing semantics."""
from dataclasses import replace

import pytest
from sqlalchemy import delete, insert, select, func

from backend import database as db, server
from backend.tests.test_i1_serve_filter import live, UID, OPP, LEAGUE, TOKEN
from backend.tests.test_trade_fingerprint_reads_unlocked import init_harness
from backend.tests.test_trade_page_store import p1, spawned, build_page, set_row

HEADERS = {"X-Session-Token": TOKEN, "X-FTF-Current-Only": "1"}


def status(client, job_id, *, deck=False, cursor=0, strict=True):
    query = f"{'deck' if deck else 'job_id'}={job_id}&cursor={cursor}"
    return client.get('/api/trades/status?' + query,
                      headers=HEADERS if strict else {"X-Session-Token": TOKEN})


def test_valid_stored_pages_acknowledge_and_preserve_order(p1):
    client, _, _ = p1
    job = build_page()
    legacy = status(client, job, strict=False)
    strict = status(client, job)
    assert legacy.status_code == strict.status_code == 200
    assert 'current_validated' not in legacy.json
    body = strict.json
    assert body.pop('current_validated') is True
    assert body == legacy.json
    generated = client.post('/api/trades/generate', headers=HEADERS,
                            json={'league_id': LEAGUE, 'fairness_threshold': .5, 'page': 1})
    assert generated.status_code == 200, generated.json
    assert generated.json['current_validated'] is True


def test_stale_kickoff_joins_rebuild_without_returning_the_legacy_page(p1, spawned):
    client, engine, _ = p1
    build_page()
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    set_row(engine, state='stale')
    body = {'league_id': LEAGUE, 'fairness_threshold': .5, 'page': 1}
    legacy = client.post('/api/trades/generate', headers={'X-Session-Token': TOKEN}, json=body)
    assert legacy.status_code == 200 and legacy.json['cards']
    assert legacy.json['serve_source'] == 'page'
    strict = client.post('/api/trades/generate', headers=HEADERS, json=body)
    assert strict.status_code == 200 and strict.json['current_validated'] is True
    assert strict.json['status'] == 'running' and strict.json['cards'] == []
    assert len(spawned) == 1  # Joins the existing rebuild; no duplicate generation.


@pytest.mark.parametrize('change', [
    {'state': 'stale'}, {'roster_fp': 'obsolete'}, {'values_snapshot_id': 'obsolete'},
    {'config_signature': 'obsolete'}, {'engine_version': 'obsolete'},
    {'experiment_digest': 'obsolete'}, {'expires_at': '2000-01-01'},
])
@pytest.mark.parametrize('deck', [False, True])
def test_stale_stored_continuations_refuse_before_delivery(p1, monkeypatch, change, deck):
    client, engine, _ = p1
    job = build_page()
    set_row(engine, **change)
    deliveries = []
    monkeypatch.setattr(server, '_deck_evidence_delivered_stored', lambda *a, **k: deliveries.append(1))
    strict = status(client, job, deck=deck, cursor=30)
    assert strict.status_code == 409
    assert strict.json == {'error': 'trade_snapshot_changed', 'status': 'error',
                           'cards': [], 'total_ready': 0}
    assert not deliveries
    # The opt-in changes neither status code nor legacy response keys.
    assert status(client, job, deck=deck, cursor=30, strict=False).status_code == 200


def test_linked_stale_page_is_not_relabelled_current(p1, monkeypatch):
    client, engine, _ = p1
    job = build_page()
    set_row(engine, state='stale')
    original = server._trade_current_snapshot
    def linked(*args, **kwargs):
        snapshot, values = original(*args, **kwargs)
        return replace(snapshot, linked=True), values
    monkeypatch.setattr(server, '_trade_current_snapshot', linked)
    assert status(client, job, strict=False).json['freshness_state'] == 'fresh'
    assert status(client, job).status_code == 409


def test_real_config_change_refuses_live_continuation(p1, monkeypatch):
    client, engine, _ = p1
    job = build_page()
    with engine.begin() as conn:
        conn.execute(delete(db.trade_page_store_table))
    before = status(client, job)
    assert before.status_code == 200 and before.json['current_validated'] is True
    monkeypatch.setitem(server._trade_service_mod._cfg, 'trade_page_size', 31.)
    assert status(client, job).status_code == 409
    assert status(client, job, strict=False).status_code == 200


def test_revoked_stored_deck_is_never_a_current_response(p1):
    client, _, _ = p1
    job = build_page()
    with server._trade_jobs_lock:
        server._revoke_trade_job_locked(server._trade_jobs[job])
    assert status(client, job).status_code == 409


@pytest.mark.parametrize('live_job', [False, True])
def test_participant_epoch_change_during_projection_prevents_delivery(p1, monkeypatch, live_job):
    client, engine, _ = p1
    job = build_page()
    if live_job:
        with engine.begin() as conn:
            conn.execute(delete(db.trade_page_store_table))
    original = server._project_trade_dispositions
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        with server._trade_jobs_lock:
            server._trade_input_epochs[(OPP, LEAGUE)].revoked = True
        return result
    monkeypatch.setattr(server, '_project_trade_dispositions', changed)
    deliveries = []
    monkeypatch.setattr(server, '_deck_evidence_delivered_stored', lambda *a, **k: deliveries.append(1))
    monkeypatch.setattr(server, '_deck_evidence_delivered', lambda *a, **k: deliveries.append(1))
    response = status(client, job)
    assert response.status_code == 409 and not response.json['cards']
    assert not deliveries


def test_failed_current_read_never_acknowledges_nonempty_page(p1, monkeypatch):
    client, _, _ = p1
    job = build_page()
    monkeypatch.setattr(server, '_trade_current_snapshot', lambda *a, **k: None)
    assert status(client, job).status_code == 409
    assert status(client, job, strict=False).status_code == 200


def test_strict_status_cannot_cross_request_league_or_format(p1):
    client, _, _ = p1
    job = build_page()
    for headers in [{**HEADERS, 'X-Scoring-Format': 'sf_tep'}]:
        response = client.get('/api/trades/status?job_id=' + job, headers=headers)
        assert response.status_code == 409


@pytest.mark.parametrize('platform', ['espn', 'mfl'])
def test_actual_linked_platform_kickoff_and_continuation_acknowledge_current_pages(p1, platform):
    client, engine, _ = p1
    with engine.begin() as conn:
        conn.execute(insert(db.leagues_table).values(sleeper_league_id=LEAGUE,
            user_id=UID, name='Synthetic linked', platform=platform))
    job = build_page()
    response = client.post('/api/trades/generate', headers=HEADERS,
        json={'league_id': LEAGUE, 'fairness_threshold': .5, 'page': 1})
    assert response.status_code == 200 and response.json['cards'], response.json
    assert response.json['current_validated'] is True
    assert status(client, job, deck=True, cursor=30).json['current_validated'] is True
    with engine.begin() as conn:
        conn.execute(delete(db.league_members_table))
    assert status(client, job).status_code == 409  # Missing rows are not a fresh linked cohort.


@pytest.mark.parametrize('i1_mode', [0., 1., 2.])
def test_real_demo_kickoff_and_status_do_not_require_a_persisted_cohort(p1, monkeypatch, i1_mode):
    client, _, sess = p1
    sess['is_demo'] = True
    sess['league'].league_id = 'league_demo'
    sess['trade_svc'].add_league(sess['league'])
    monkeypatch.setitem(server._trade_service_mod._cfg, 'trade_i1_mode', i1_mode)
    monkeypatch.setattr(server, '_start_trade_job_thread', lambda *, target, args, kwargs: target(*args, **kwargs))
    response = client.post('/api/trades/generate', headers=HEADERS,
        json={'league_id': 'league_demo', 'fairness_threshold': .5, 'page': 1})
    assert response.status_code == 200, response.json
    assert response.json['status'] == 'complete' and response.json['current_validated'] is True
    follow = client.get('/api/trades/status?job_id=' + response.json['job_id'], headers=HEADERS)
    assert follow.status_code == 200 and follow.json['current_validated'] is True, follow.json


def test_valid_empty_result_is_complete_not_a_snapshot_error(p1):
    client, engine, _ = p1
    job = build_page()
    with engine.begin() as conn:
        conn.execute(delete(db.trade_page_store_table))
    server._trade_jobs[job]['cards'] = []
    response = status(client, job)
    assert response.status_code == 200
    assert response.json['status'] == 'complete' and response.json['cards'] == []
    assert response.json['current_validated'] is True


def test_fingerprint_kill_keeps_legacy_behavior_and_refuses_unverifiable_strict_cards(p1, monkeypatch):
    client, _, _ = p1
    job = build_page()
    monkeypatch.setitem(server._trade_service_mod._cfg, 'trade_i1_mode', 0.)
    assert status(client, job, strict=False).status_code == 200
    assert status(client, job).status_code == 409


@pytest.mark.parametrize('kill', ['store_flag', 'packed_flag', 'paging'])
def test_live_strict_contract_remains_available_with_page_store_or_paging_off(p1, monkeypatch, kill):
    from backend import feature_flags
    client, _, _ = p1
    if kill == 'paging':
        monkeypatch.setitem(server._trade_service_mod._cfg, 'trade_paged_responses', 0.)
    else:
        flag = 'trade.first_page_store' if kill == 'store_flag' else 'trade.packed_evidence'
        monkeypatch.setitem(feature_flags._flags_cache, flag, False)
    monkeypatch.setattr(server, '_start_trade_job_thread', lambda *, target, args, kwargs: target(*args, **kwargs))
    response = client.post('/api/trades/generate', headers=HEADERS,
        json={'league_id': LEAGUE, 'fairness_threshold': .5, 'page': 1})
    assert response.status_code == 200 and response.json['current_validated'] is True, response.json
    assert status(client, response.json['job_id']).json['current_validated'] is True


def test_strict_header_does_not_authorize_a_request_without_a_session(p1):
    client, _, _ = p1
    for method, path in [('get', '/api/trades/status?job_id=foreign'), ('post', '/api/trades/generate')]:
        response = getattr(client, method)(path, headers={'X-FTF-Current-Only': '1'}, json={})
        assert response.status_code == 401 and not response.json.get('current_validated')


def test_refused_stale_page_never_spends_the_real_free_preview(p1, monkeypatch):
    from backend import entitlements
    from backend.tests.test_paywall_preview import _config
    client, engine, _ = p1
    _config(engine, paywall_enforce_enabled=1., paywall_preview_pages=1.)
    monkeypatch.setattr(entitlements, 'is_enabled', lambda k: k in {'monetize.entitlements', 'monetize.paywall'})
    job = build_page()
    set_row(engine, state='stale')
    headers = {**HEADERS, 'X-Device': 'iphone'}
    refused = client.get('/api/trades/status?job_id=' + job + '&cursor=0', headers=headers)
    assert refused.status_code == 409 and refused.json['error'] == 'trade_snapshot_changed'
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.paywall_previews_table)).scalar() == 0
    legacy = client.get('/api/trades/status?job_id=' + job + '&cursor=0',
        headers={'X-Session-Token': TOKEN, 'X-Device': 'iphone'})
    assert legacy.status_code == 200 and legacy.json['cards']
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.paywall_previews_table)).scalar() == 1
