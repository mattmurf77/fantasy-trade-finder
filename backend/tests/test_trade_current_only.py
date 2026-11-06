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


@pytest.mark.parametrize('extra', [
    {'unknown_filter': 'WR'}, {'positions': ['WR']},
    {'fairness_threshold': True}, {'fairness_threshold': '0.75'},
    {'fairness_threshold': None}, {'fairness_threshold': float('nan')},
    {'fairness_threshold': float('inf')}, {'fairness_threshold': -.01},
    {'fairness_threshold': 1.01}, {'fairness_threshold': 10 ** 400},
    {'force': 'false'}, {'refresh_fatigue': 1},
    {'pinned_give_players': 'g2'}, {'pinned_receive_players': [123]},
    {'pinned_give_players': [None]}, {'pinned_give_players': ['']},
    {'pinned_give_mode': 'junk'}, {'pinned_give_mode': 'all'},
    {'trade_intent': 'unknown'}, {'opponent_user_id': []},
    {'league_id': 123},
])
def test_strict_invalid_filters_never_start_or_deliver(p1, spawned, monkeypatch, extra):
    client, _, _ = p1
    deliveries = []
    monkeypatch.setattr(server, '_deck_evidence_delivered_stored',
                        lambda *a, **k: deliveries.append(1))
    response = client.post('/api/trades/generate', headers=HEADERS,
        json={'league_id': LEAGUE, 'page': 1, **extra})
    assert response.status_code == 400, response.json
    assert response.json == {'error': 'unsupported_trade_filter'}
    assert not spawned and not deliveries and not server._trade_jobs


@pytest.mark.parametrize('payload, flag', [
    ({'pinned_receive_players': ['r2']}, 'trade.finder_targeting'),
    ({'trade_intent': 'tier_up'}, 'trades.intent_modes'),
    ({'refresh_fatigue': True}, 'deck.fatigue'),
])
def test_strict_disabled_filters_are_not_silently_ignored(p1, spawned, monkeypatch, payload, flag):
    from backend import feature_flags
    client, _, _ = p1
    monkeypatch.setitem(feature_flags._flags_cache, flag, False)
    if flag == 'deck.fatigue':
        monkeypatch.setattr(server, '_deck_fatigue_enabled', lambda: False)
    response = client.post('/api/trades/generate', headers=HEADERS,
                           json={'league_id': LEAGUE, 'page': 1, **payload})
    assert response.status_code == 400 and not spawned
    # Legacy feature-off normalization is deliberately unchanged.
    legacy = client.post('/api/trades/generate', headers={'X-Session-Token': TOKEN},
                         json={'league_id': LEAGUE, 'page': 1, **payload})
    assert legacy.status_code == 200, legacy.json


@pytest.mark.parametrize('payload', [[], ['filter'], 7, 'filter'])
def test_strict_generate_requires_an_object(p1, spawned, payload):
    client, _, _ = p1
    response = client.post('/api/trades/generate', headers=HEADERS, json=payload)
    assert response.status_code == 400 and not spawned


def test_strict_league_mismatch_refuses_before_job_start(p1, spawned):
    client, _, _ = p1
    response = client.post('/api/trades/generate', headers=HEADERS,
        json={'league_id': 'another-league', 'page': 1})
    assert response.status_code == 409 and response.json['cards'] == []
    assert not spawned and not server._trade_jobs


def test_precise_fairness_cannot_reuse_rounded_stored_page(p1, spawned):
    client, _, _ = p1
    build_page()  # Stored scope 0.50.
    response = client.post('/api/trades/generate', headers=HEADERS,
        json={'league_id': LEAGUE, 'fairness_threshold': .496, 'page': 1})
    assert response.status_code == 200, response.json
    assert response.json['cards'] == [] and response.json['status'] == 'running'
    job = server._trade_jobs[response.json['job_id']]
    assert job['fairness_threshold'] == .496 and job.get('page_scope') is None
    assert len(spawned) == 1


@pytest.mark.parametrize('threshold, expected', [
    (.75, 'organic:f=0.75'), (.5, 'organic:f=0.50'),
    (.746, None), (.754, None), (float('nan'), None), (float('inf'), None),
])
def test_page_scope_does_not_alias_different_fairness(threshold, expected):
    assert server._trade_page_scope(threshold) == expected


@pytest.mark.parametrize('payload', [
    {'fairness_threshold': 0}, {'fairness_threshold': 1},
    {'pinned_give_players': ['g2'], 'pinned_give_mode': 'all'},
    {'pinned_receive_players': ['r2']}, {'opponent_user_id': OPP},
    {'trade_intent': 'consolidate'}, {'force': False}, {'refresh_fatigue': True},
])
def test_supported_strict_filters_keep_the_requested_job_scope(p1, spawned, monkeypatch, payload):
    from backend import feature_flags
    client, _, _ = p1
    monkeypatch.setitem(feature_flags._flags_cache, 'trade.finder_targeting', True)
    monkeypatch.setitem(feature_flags._flags_cache, 'trades.intent_modes', True)
    monkeypatch.setattr(server, '_deck_fatigue_enabled', lambda: True)
    response = client.post('/api/trades/generate', headers=HEADERS,
        json={'league_id': LEAGUE, 'page': 1, **payload})
    assert response.status_code == 200, response.json
    assert response.json['current_validated'] is True and len(spawned) == 1
    job = server._trade_jobs[response.json['job_id']]
    if 'fairness_threshold' in payload:
        assert job['fairness_threshold'] == payload['fairness_threshold']
    if 'trade_intent' in payload:
        assert job['trade_intent'] == payload['trade_intent']
    if any(name in payload for name in ('pinned_give_players', 'pinned_receive_players', 'opponent_user_id')):
        assert job['is_pinned'] and not job.get('page_scope')
