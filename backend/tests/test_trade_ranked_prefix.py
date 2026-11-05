"""Only a current, durably published, fully ranked owner prefix may be used early."""
from datetime import datetime, timezone

import pytest

from backend import server, roster_snapshot, feature_flags, trade_service
from backend.tests.test_owner_generator_routes import harness, owner_harness, worker, ME, LEAGUE, TOKEN
from backend.tests.test_owner_only_routes import exclusive, large_exclusive
from backend.tests.test_owner_batch_publication import observe_batches


@pytest.fixture
def current_admission(large_exclusive, monkeypatch):
    _, _, sess, _, league = large_exclusive
    owners = {p: frozenset([m.user_id]) for m in league.members for p in m.roster}
    snap = roster_snapshot.RosterSnapshot('rfp1:synthetic', owners,
        datetime.now(timezone.utc).isoformat(), 'fresh', age_s=0.)
    monkeypatch.setattr(server, '_trade_current_snapshot', lambda *a, **k: (snap, 'vsn1:synthetic'))
    monkeypatch.setattr(server, '_trade_roster_snapshot', lambda *a, **k: snap)
    original = server._run_trade_job
    def admitted(job_id, *args, **kwargs):
        inputs = server._trade_page_request_inputs(sess, LEAGUE)
        server._trade_jobs[job_id].update(
            request_signature=inputs['request_signature'], input_epochs=inputs['input_epochs'],
            presentation_capture=inputs['presentation_capture'],
            roster_fp=snap.fp, values_snapshot_id='vsn1:synthetic')
        return original(job_id, *args, **kwargs)
    monkeypatch.setattr(server, '_run_trade_job', admitted)
    return large_exclusive


def test_real_committed_prefix_is_acknowledged_before_job_completion(current_admission, monkeypatch):
    client, engine, *_ = current_admission
    observed = []
    def after_publish(job, batch):
        response = client.get('/api/trades/status?job_id=owner-route-worker&cursor=0',
            headers={'X-Session-Token': TOKEN, 'X-FTF-Current-Only': '1'})
        assert response.status_code == 200, response.json
        assert response.json['current_validated'] is True
        assert response.json['status'] == 'running' and response.json['cards']
        assert response.json['ranked_prefix_ready'] is True
        observed.append(response.json['cards'])
    observe_batches(monkeypatch, engine, after_publish)
    job = worker(current_admission, monkeypatch)
    assert len(observed[0]) == 30 and len(job['cards']) == 64
    assert '_ranked_prefix_snapshot' not in job  # Completion ends the early-prefix protocol.
    assert [c['trade_id'] for c in observed[0]] == [c['trade_id'] for c in job['cards'][:30]]


@pytest.mark.parametrize('change', ['other_publisher', 'deferred'])
def test_another_publication_or_deferred_evidence_cannot_claim_durable_prefix(
        current_admission, monkeypatch, change):
    client, engine, *_ = current_admission
    observed = []
    def after_publish(job, batch):
        if change == 'other_publisher':
            job['cards'] = list(job['cards'])  # Same terms, different publication authority.
        else:
            job['evidence_mode'] = 'deferred'
        response = client.get('/api/trades/status?job_id=owner-route-worker&cursor=0',
            headers={'X-Session-Token': TOKEN, 'X-FTF-Current-Only': '1'})
        assert response.status_code == 200, response.json
        assert response.json['current_validated'] is True
        assert response.json['cards'] and 'ranked_prefix_ready' not in response.json
        observed.append(1)
    observe_batches(monkeypatch, engine, after_publish)
    worker(current_admission, monkeypatch)
    assert observed


@pytest.mark.parametrize('selection', [
    {}, {'pinned_give_players': ['g']}, {'pinned_receive_players': ['r0-0']},
    {'pinned_give_players': ['g'], 'pinned_receive_players': ['r0-0'], 'opponent_user_id': 'opponent-0'},
    {'trade_intent': 'tier_up'},
])
def test_real_bilateral_kickoff_and_status_accept_current_organic_and_selected_scopes(
        current_admission, monkeypatch, selection):
    client, *_ = current_admission
    monkeypatch.setitem(feature_flags._flags_cache, 'trade.finder_targeting', True)
    monkeypatch.setitem(feature_flags._flags_cache, 'trades.intent_modes', True)
    for key, value in [('owner_bilateral_enabled', 1.), ('owner_bilateral_revision_enabled', 1.),
                       ('simple_player_presentment', 2.)]:
        monkeypatch.setitem(trade_service._cfg, key, value)
    monkeypatch.setattr(server, '_start_trade_job_thread', lambda *, target, args, kwargs: target(*args, **kwargs))
    headers = {'X-Session-Token': TOKEN, 'X-FTF-Current-Only': '1'}
    response = client.post('/api/trades/generate', headers=headers,
        json={'league_id': LEAGUE, 'fairness_threshold': .5, 'page': 1, **selection})
    assert response.status_code == 200, response.json
    assert response.json['status'] == 'complete' and response.json['current_validated'] is True
    if selection.get('pinned_receive_players'):
        assert response.json['cards']
        assert all('r0-0' in {p['id'] for p in card['receive']} for card in response.json['cards'])
    follow = client.get('/api/trades/status?job_id=' + response.json['job_id'] + '&cursor=0', headers=headers)
    assert follow.status_code == 200 and follow.json['current_validated'] is True, follow.json
