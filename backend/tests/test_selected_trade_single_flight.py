"""Strict selected requests join only an exactly matching live worker.

Synthetic sessions/SQLite; production services and provider HTTP are not used.
The actual route, admission lock, current-only serve and lifecycle fences run.
"""
import copy
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine

from backend import database as db, feature_flags as ff, server, trade_service as ts
from backend.tests.test_trade_page_store import p1, spawned
from backend.tests.test_i1_serve_filter import live, UID, OPP, LEAGUE, TOKEN

HEADERS = {"X-Session-Token": TOKEN, "X-FTF-Current-Only": "1"}
BODY = {"league_id": LEAGUE, "fairness_threshold": .5,
        "pinned_give_players": ["g2"], "page": 1}


@pytest.fixture
def world(p1, spawned, monkeypatch):
    monkeypatch.setattr(server, "_selected_trade_jobs", {})
    monkeypatch.setitem(ff._flags_cache, "trade.finder_targeting", True)
    monkeypatch.setitem(ff._flags_cache, "trades.intent_modes", True)
    return (*p1, spawned)


def post(world, *, headers=None, **changes):
    response = world[0].post('/api/trades/generate',
        headers=HEADERS if headers is None else headers, json={**BODY, **changes})
    assert response.status_code == 200, response.json
    return response.json


def test_identical_selected_requests_join_but_echo_each_search(world):
    first = post(world, search_id='first')
    second = post(world, search_id='second')
    assert first['job_id'] == second['job_id']
    assert first['search_id'] == 'first' and second['search_id'] == 'second'
    assert first['current_validated'] and second['current_validated']
    assert len(world[3]) == 1
    assert server._trade_jobs_by_key == {}
    assert len(server._selected_trade_jobs) == 1


@pytest.mark.parametrize('change', [
    {'pinned_give_players': ['g1']}, {'pinned_give_players': ['g2', 'g1']},
    {'pinned_give_players': ['g2', 'g2']}, {'pinned_give_mode': 'all'},
    {'pinned_receive_players': ['r2']}, {'opponent_user_id': OPP},
    {'trade_intent': 'tier_up'}, {'fairness_threshold': .5000000000000001},
])
def test_different_effective_or_raw_selectors_do_not_join_or_cancel(world, change):
    a = post(world)
    b = post(world, **change)
    assert a['job_id'] != b['job_id'] and len(world[3]) == 2
    assert server._job_live(server._trade_jobs[a['job_id']])


def test_ordered_legs_and_intent_are_exact(world):
    a = post(world, pinned_give_players=['g1', 'g2'], pinned_receive_players=['r1', 'r2'])
    b = post(world, pinned_give_players=['g2', 'g1'], pinned_receive_players=['r1', 'r2'])
    c = post(world, pinned_give_players=['g1', 'g2'], pinned_receive_players=['r2', 'r1'])
    d = post(world, trade_intent='tier_up')
    assert post(world, trade_intent='tier_up')['job_id'] == d['job_id']
    assert len({a['job_id'], b['job_id'], c['job_id'], d['job_id']}) == 4


@pytest.mark.parametrize('status', ['complete', 'error', 'revoked', 'stalled'])
def test_terminal_revoked_or_stalled_job_never_joins(world, status):
    a = post(world)
    job = server._trade_jobs[a['job_id']]
    if status == 'revoked':
        server._revoke_trade_job_locked(job)
    elif status == 'stalled':
        job['started_at'] = time.monotonic() - server._JOB_HARD_TIMEOUT - 1
    else:
        server._finish_trade_job(a['job_id'], error='failed' if status == 'error' else None)
        assert '_selected_source' not in job
    b = post(world)
    assert b['job_id'] != a['job_id'] and len(world[3]) == 2
    assert '_selected_source' not in job


@pytest.mark.parametrize('field', ['request_signature', 'roster_fp', 'values_snapshot_id'])
def test_missing_stored_identity_never_uses_permissive_legacy_match(world, field):
    a = post(world)
    server._trade_jobs[a['job_id']].pop(field)
    assert post(world)['job_id'] != a['job_id']


@pytest.mark.parametrize('current', [None, (None, 'values'), ('roster', None)])
def test_missing_current_fingerprints_never_join(world, monkeypatch, current):
    a = post(world)
    monkeypatch.setattr(server, '_trade_current_fingerprints', lambda *a, **kw: current)
    assert post(world)['job_id'] != a['job_id']


@pytest.mark.parametrize('actor', [UID, OPP])
def test_consumed_member_epoch_change_refuses_prior_worker(world, actor):
    a = post(world)
    server._invalidate_trade_jobs(user_id=actor, league_id=LEAGUE)
    assert post(world)['job_id'] != a['job_id']
    assert server._trade_job_revoked(server._trade_jobs[a['job_id']])


def test_policy_change_and_restoration_do_not_join_intervening_job(world, monkeypatch):
    a = post(world)
    monkeypatch.setitem(ts._cfg, 'owner_pool_size', 123.)
    b = post(world)
    assert a['job_id'] != b['job_id']


@pytest.mark.parametrize('knob', [0., 1.])
def test_force_always_starts_fresh_and_does_not_revoke_independent_selection(world, monkeypatch, knob):
    monkeypatch.setattr(server, '_force_supersede_enabled', lambda: bool(knob))
    a = post(world)
    b = post(world, force=True)
    c = post(world, force=True)
    assert len({a['job_id'], b['job_id'], c['job_id']}) == 3
    assert all(server._job_live(server._trade_jobs[x['job_id']]) for x in (a, b, c))
    assert post(world)['job_id'] == c['job_id']


def test_legacy_selected_and_intent_only_keep_existing_semantics(world):
    legacy = {'X-Session-Token': TOKEN}
    a, b = post(world, headers=legacy), post(world, headers=legacy)
    assert a['job_id'] != b['job_id']
    organic = post(world, pinned_give_players=[])
    intent = post(world, pinned_give_players=[], trade_intent='tier_up')
    assert server._trade_job_revoked(server._trade_jobs[organic['job_id']])
    assert post(world, pinned_give_players=[], trade_intent='tier_up')['job_id'] == intent['job_id']
    selected = post(world)
    assert server._job_live(server._trade_jobs[intent['job_id']])
    assert server._job_live(server._trade_jobs[selected['job_id']])


@pytest.mark.parametrize('field', ['service', 'trade_svc', 'league', 'players', 'user_roster', 'league_user_id'])
def test_replaced_source_or_seat_cannot_join_old_session_work(world, field):
    a = post(world)
    sess = world[2]
    if field == 'service':
        sess['services']['1qb_ppr'] = copy.copy(sess['service'])
    elif field == 'trade_svc':
        sess['trade_svcs']['1qb_ppr'] = copy.copy(sess['trade_svc'])
    elif field == 'league':
        sess[field] = copy.deepcopy(sess[field])
    elif field == 'players':
        sess[field] = [copy.copy(p) for p in sess[field]]
    elif field == 'user_roster':
        sess[field] = list(reversed(sess[field]))
    else:
        sess[field] = OPP
    assert post(world)['job_id'] != a['job_id']


def test_other_session_token_cannot_join_even_when_aliases_match(world, monkeypatch):
    a = post(world)
    monkeypatch.setitem(server._sessions, 'second-selected-token', world[2])
    assert post(world, headers={**HEADERS, 'X-Session-Token': 'second-selected-token'})['job_id'] != a['job_id']


def test_index_bound_eviction_and_removed_jobs_leave_only_small_pointers(world, monkeypatch):
    monkeypatch.setattr(server, '_SELECTED_TRADE_JOIN_LIMIT', 2)
    ids = [post(world, fairness_threshold=f)['job_id'] for f in (.5, .6, .7)]
    assert len(server._selected_trade_jobs) == 2
    assert all(type(k) is str and len(k) == 64 and type(v) is str
               for k, v in server._selected_trade_jobs.items())
    assert all(server._job_live(server._trade_jobs[j]) for j in ids)
    server._trade_jobs.pop(ids[-1])
    post(world, fairness_threshold=.8)
    assert ids[-1] not in server._selected_trade_jobs.values()
    assert len(server._selected_trade_jobs) == 2


def test_oversized_identity_skips_join_without_changing_underlying_request(world, monkeypatch):
    monkeypatch.setattr(server, '_SELECTED_TRADE_SHAPE_BYTES', 1)
    a, b = post(world), post(world)
    assert a['job_id'] != b['job_id']
    assert server._selected_trade_jobs == {}
    assert world[3][0]['args'][4] == ['g2']


def test_actual_concurrent_routes_claim_one_worker(world, monkeypatch, tmp_path):
    # The fixture's in-memory SQLite connection is thread-local. Clone only its
    # synthetic data to a temporary file so both real request threads can read.
    filename = tmp_path / 'selected-world.sqlite'
    source = world[1].raw_connection()
    destination = sqlite3.connect(filename)
    source.driver_connection.backup(destination)
    destination.close()
    source.close()
    engine = create_engine('sqlite:///' + str(filename))
    monkeypatch.setattr(db, 'engine', engine)
    barrier = Barrier(2)
    original = server._capture_trade_execution
    def capture(*a, **kw):
        result = original(*a, **kw)
        barrier.wait(timeout=5)
        return result
    monkeypatch.setattr(server, '_capture_trade_execution', capture)
    def request_one(n):
        with server.app.test_client() as client:
            response = client.post('/api/trades/generate', headers=HEADERS,
                                   json={**BODY, 'search_id': f'concurrent_{n}'})
            assert response.status_code == 200, response.json
            return response.json
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(request_one, (1, 2)))
        assert a['job_id'] == b['job_id']
        assert a['search_id'] != b['search_id']
        assert len(world[3]) == 1
    finally:
        engine.dispose()


def test_deleted_account_lifetime_and_admission_epoch_races_refuse_join(world, monkeypatch):
    a = post(world)
    # Exercise the real lifecycle primitive while leaving epochs deliberately
    # unchanged: source lifetime binding must independently refuse the old job.
    lifecycle = server._user_data_lifecycle
    with lifecycle.hold([UID]):
        lifecycle.invalidate([UID])
    b = post(world)
    assert b['job_id'] != a['job_id']
    original = server._capture_trade_execution
    def capture(*args, **kwargs):
        context = original(*args, **kwargs)
        server._invalidate_trade_jobs(user_id=OPP, league_id=LEAGUE)
        return context
    monkeypatch.setattr(server, '_capture_trade_execution', capture)
    response = world[0].post('/api/trades/generate', headers=HEADERS, json=BODY)
    # Counterparty capture happens after the owned league is known, so this
    # change predates the new capture; it must replace b, never revive it.
    assert response.status_code == 200, response.json
    assert response.json['job_id'] != b['job_id']
    assert not server._job_live(server._trade_jobs[b['job_id']])


def test_viewer_revocation_during_capture_never_schedules_or_indexes_stale_job(world, monkeypatch):
    original = server._capture_trade_execution
    def capture(*args, **kwargs):
        context = original(*args, **kwargs)
        server._invalidate_trade_jobs(user_id=UID, league_id=LEAGUE)
        return context
    monkeypatch.setattr(server, '_capture_trade_execution', capture)
    response = world[0].post('/api/trades/generate', headers=HEADERS, json=BODY)
    assert response.status_code == 409, response.json
    assert not world[3] and not server._selected_trade_jobs
    assert all(j['status'] == 'error' for j in server._trade_jobs.values())


def test_repeated_tap_keeps_one_preview_receipt_and_checks_passive_access(world, monkeypatch):
    from backend import entitlements as entl, paywall_gate as gate
    from backend.tests.test_paywall_preview import _config
    from backend.tests.test_trade_page_store import page_card
    from sqlalchemy import func, select
    _config(world[1], paywall_enforce_enabled=1., paywall_preview_pages=1.)
    monkeypatch.setattr(entl, 'is_enabled', lambda key: key in ('monetize.entitlements', 'monetize.paywall'))
    headers = {**HEADERS, 'X-Device': 'iphone'}
    a = post(world, headers=headers, search_id='preview_first')
    b = post(world, headers=headers, search_id='preview_second')
    assert a['job_id'] == b['job_id'] and len(world[3]) == 1
    assert gate.preview_row(UID) is None  # Pending work is never consumption.
    job = server._trade_jobs[a['job_id']]
    # Isolate the delivery/accounting seam with an already committed synthetic
    # prefix; engine/publication parity is tested separately with the real worker.
    job['cards'] = [page_card(0)]
    job['_ranked_prefix_snapshot'] = job['cards']
    c = post(world, headers=headers, search_id='preview_visible')
    assert c['cards'] and c['job_id'] == a['job_id']
    assert gate.preview_row(UID)['deck_key'] == a['job_id']
    # A new generate tap stays blocked once the preview is spent; continuation
    # of that same deck remains allowed through the ordinary status route.
    repeated = world[0].post('/api/trades/generate', headers=headers, json=BODY)
    assert repeated.status_code == 402
    continued = world[0].get('/api/trades/status', headers=headers,
        query_string={'job_id': a['job_id'], 'cursor': 0})
    assert continued.status_code == 200 and continued.json['cards']
    with world[1].connect() as connection:
        assert connection.execute(select(func.count()).select_from(db.paywall_previews_table)).scalar() == 1
    denied = world[0].post('/api/trades/generate', headers={**headers, 'X-FTF-Prewarm': '1'}, json=BODY)
    assert denied.status_code in (402, 409)
    assert len(world[3]) == 1
    forced = world[0].post('/api/trades/generate', headers=headers, json={**BODY, 'force': True})
    assert forced.status_code == 402  # A fresh second deck is not a free preview.
    assert len(world[3]) == 1


def test_unauthorized_or_unknown_selectors_cannot_reach_existing_join(world):
    post(world)
    unauth = world[0].post('/api/trades/generate', headers={**HEADERS, 'X-Session-Token': 'absent'}, json=BODY)
    assert unauth.status_code == 401
    rejected = world[0].post('/api/trades/generate', headers=HEADERS, json={**BODY, 'unknown': True})
    assert rejected.status_code == 400
    wrong_league = world[0].post('/api/trades/generate', headers=HEADERS, json={**BODY, 'league_id': 'other'})
    assert wrong_league.status_code == 409
    assert len(world[3]) == 1


def test_request_format_and_account_binding_are_distinct(world):
    a = post(world)
    session = world[2]
    session['services']['sf_tep'] = session['service']
    session['trade_svcs']['sf_tep'] = session['trade_svc']
    b = post(world, headers={**HEADERS, 'X-Scoring-Format': 'sf_tep'})
    assert b['job_id'] != a['job_id']
    session['account_id'] = 'synthetic-rebound-account'
    c = post(world)
    assert c['job_id'] not in {a['job_id'], b['job_id']}
    assert '_selected' not in json.dumps(c)


def test_worker_start_failure_releases_source_refs_and_retry_is_independent(world, monkeypatch):
    def failed(**kwargs):
        raise RuntimeError('synthetic worker start failure')
    monkeypatch.setattr(server, '_start_trade_job_thread', failed)
    a = post(world)
    job = server._trade_jobs[a['job_id']]
    assert job['status'] == 'error' and job['error'] == 'worker_start_failed'
    assert '_selected_source' not in job and '_selected_shape' not in job
    assert post(world)['job_id'] != a['job_id']
