"""Actual durable prepared batches through strict HTTP, before suffix writes.

Synthetic local leagues and SQL; no provider/device timing is claimed.
"""
import copy
import time

import pytest

from backend import database as db, server, feature_flags as ff, entitlements
from backend import prepared_trade_runtime as runtime, prepared_trade_store as legacy_store
from backend import prepared_trade_store_v2 as paged_store
from backend.tests.test_owner_generator_routes import harness, owner_harness, rows, ME, LEAGUE, TOKEN
from backend.tests.test_owner_only_routes import exclusive, large_exclusive
from backend.tests.test_prepared_trade_runtime import prepared
from backend.tests.test_prepared_trade_runtime_review import headless, new_claim
from backend.tests.test_paywall_preview import _config

HEADERS = {'X-Session-Token': TOKEN, 'X-FTF-Current-Only': '1', 'X-Device': 'iphone'}


@pytest.fixture(autouse=True)
def restore_dynamic_harness_recorder():
    # This module resolves the existing harness dynamically after monkeypatch
    # has started. Preserve its recorder across the opposite teardown order;
    # keep the shared harness's established fixture ordering unchanged.
    original = server.record_event
    yield
    server.record_event = original


def ready(request, monkeypatch, kind):
    if kind == 'legacy':
        fixture, original, *_ = request.getfixturevalue('prepared')
        for flag in ('trade.first_page_store', 'trade.packed_evidence'):
            monkeypatch.setitem(ff._flags_cache, flag, True)
        expected = [r['runtime']['trade_id'] for r in original['prepared_bundle']['cards']]
        store = legacy_store
    else:
        fixture, target = request.getfixturevalue('headless')
        for flag in ('trade.first_page_store', 'trade.packed_evidence'):
            monkeypatch.setitem(ff._flags_cache, flag, True)
        scope, _, claim = new_claim(target)
        runtime.prepare_target(server, claim)
        assert paged_store.peek_inventory(scope) is not None
        # Fresh session/context, using the actual prepared dependency receipt.
        fresh = runtime.build_session(server, copy.deepcopy(target))
        fixture[2].update(fresh)
        fixture = (fixture[0], fixture[1], fixture[2], fresh['trade_svc'], fresh['league'])
        store = paged_store
        # Runtime-review tests compare the entire sealed v2 order. Here the
        # prefix shown before suffix writes must equal its final HTTP page.
        expected = None
    monkeypatch.setattr(server, '_trade_jobs', {})
    monkeypatch.setattr(server, '_trade_jobs_by_key', {})
    workers = []
    monkeypatch.setattr(server, '_start_trade_job_thread',
                        lambda *, target, args, kwargs: workers.append((target, args, kwargs)))
    monkeypatch.setattr(server, '_start_deck_evidence_thread', lambda *, target, args: target(*args))
    monkeypatch.setattr(server, 'record_event', lambda *a, **k: None)
    return fixture, store, expected, workers


def finish(client, response, workers):
    # Run the captured worker after kickoff's request context has exited, as
    # the real background worker does. Nested requests inside generate would
    # share Flask g and corrupt lifecycle teardown in this synthetic harness.
    assert response.status_code == 200 and response.json['status'] == 'running', response.json
    assert len(workers) == 1
    target, args, kwargs = workers.pop()
    target(*args, **kwargs)
    return client.get('/api/trades/status?job_id=' + response.json['job_id'] + '&cursor=0', headers=HEADERS)


@pytest.mark.parametrize('kind', ['legacy', 'v2'])
@pytest.mark.parametrize('preview', [False, True])
def test_strict_prefix_available_before_suffix_with_real_delivery_and_preview(request, monkeypatch, kind, preview):
    fixture, store, expected, workers = ready(request, monkeypatch, kind)
    client, engine, _, service, _ = fixture
    if preview:
        _config(engine, paywall_enforce_enabled=1., paywall_preview_pages=1.)
        monkeypatch.setattr(entitlements, 'is_enabled', lambda key: key in {'monetize.entitlements', 'monetize.paywall'})
    observations, commits = [], []
    started = time.monotonic()
    original = store.ensure_adoption_evidence

    def observe_inner(*args, **kwargs):
        job = next(j for j in server._trade_jobs.values()
                   if j.get('prepared_inventory_id') == args[0]['inventory_id'] and j['status'] == 'running')
        if commits:
            assert job['status'] == 'running' and job['evidence_mode'] == 'live'
            assert job.get('evidence') is None
            assert job['_ranked_prefix_snapshot'] is job['cards']
            if preview:
                passive = client.get('/api/trades/status?job_id=' + job['job_id'] + '&cursor=0',
                                     headers={**HEADERS, 'X-FTF-Prewarm': '1'})
                assert passive.status_code == 409 and passive.json['error'] == 'prewarm_requires_tap'
                assert not rows(engine, db.paywall_previews_table)
            response = client.get('/api/trades/status?job_id=' + job['job_id'] + '&cursor=0', headers=HEADERS)
            assert response.status_code == 200, response.json
            body = response.json
            assert body['current_validated'] is True and body['ranked_prefix_ready'] is True
            assert body['status'] == 'running' and body['cards']
            assert len(body['cards']) <= 30
            assert 'prepared_evidence_job_id' not in body
            persisted = rows(engine, db.deck_impressions_table)
            assert len(persisted) == 30  # Suffix has not committed.
            shown = {c['impression_id'] for c in body['cards']}
            assert shown <= {r['impression_id'] for r in persisted if r['delivered_at']}
            assert {r['deck_job_id'] for r in persisted} == {job['prepared_evidence_job_id']}
            assert job['prepared_evidence_job_id'] != job['job_id']
            if preview:
                preview_rows = rows(engine, db.paywall_previews_table)
                assert len(preview_rows) == 1 and preview_rows[0]['deck_key'] == job['job_id']
                assert client.get('/api/trades/status?job_id=' + job['job_id'] + '&cursor=30', headers=HEADERS).status_code == 402
            observations.append((time.monotonic() - started, copy.deepcopy(body['cards'])))
        else:
            assert not job['cards'] and '_ranked_prefix_snapshot' not in job
            assert job['evidence_mode'] == 'deferred' and job.get('evidence') is not None
            assert not rows(engine, db.deck_impressions_table)
            if preview:
                assert not rows(engine, db.paywall_previews_table)
        result = original(*args, **kwargs)
        commits.append(len(kwargs['rows']))
        return result

    def observe(*args, **kwargs):
        try:
            return observe_inner(*args, **kwargs)
        except AssertionError as exc:
            pytest.fail(str(exc))  # Do not let the adoption fallback swallow a test assertion.

    monkeypatch.setattr(store, 'ensure_adoption_evidence', observe)
    response = client.post('/api/trades/generate', headers=HEADERS,
                           json={'league_id': LEAGUE, 'fairness_threshold': .5, 'page': 1})
    response = finish(client, response, workers)
    elapsed = time.monotonic() - started
    assert response.status_code == 200, response.json
    assert response.json['status'] == 'complete', response.json
    assert observations and observations[0][0] < elapsed
    job = server._trade_jobs[response.json['job_id']]
    assert '_ranked_prefix_snapshot' not in job
    assert len(job['cards']) >= 64
    if expected is not None:
        assert [c['trade_id'] for c in job['cards']] == expected
    first = observations[0][1]
    assert first == response.json['cards']
    for card in first:
        assert service._trade_cards[card['trade_id']].owner_evaluation is not None
    print(f'prepared-prefix {kind} preview={preview}: first_http_ms={observations[0][0]*1000:.1f} complete_http_ms={elapsed*1000:.1f} cards={len(job["cards"])}')


@pytest.mark.parametrize('kind', ['legacy', 'v2'])
@pytest.mark.parametrize('failure', ['first_write', 'checkpoint', 'second_write', 'changed_inputs'])
def test_failure_never_exposes_uncommitted_or_revoked_prefix(request, monkeypatch, kind, failure):
    fixture, store, _, workers = ready(request, monkeypatch, kind)
    client, engine, *_ = fixture
    writes, fallback, shown = [], [], []
    original = store.ensure_adoption_evidence

    def write(*args, **kwargs):
        if failure == 'first_write':
            raise RuntimeError('synthetic first write outage')
        if writes and failure in ('second_write', 'changed_inputs'):
            job = next(j for j in server._trade_jobs.values()
                       if j.get('prepared_inventory_id') == args[0]['inventory_id'] and j['status'] == 'running')
            page = client.get('/api/trades/status?job_id=' + job['job_id'] + '&cursor=0', headers=HEADERS)
            if page.status_code != 200 or not page.json.get('ranked_prefix_ready'):
                pytest.fail(f'committed first prefix not visible: {page.json}')
            shown.extend(c['impression_id'] for c in page.json['cards'])
        if writes and failure == 'second_write':
            raise RuntimeError('synthetic suffix write outage')
        result = original(*args, **kwargs)
        writes.append(len(kwargs['rows']))
        if len(writes) == 2 and failure == 'changed_inputs':
            server.g_universal_by_format['1qb_ppr']['seed']['g'] += 1.
        return result

    def generation(job_id, *args, **kwargs):
        fallback.append(job_id)
        # Stop at the boundary: failure before durable adoption is allowed to
        # run the original generator, with its deferred sink still attached.
        job = server._trade_jobs[job_id]
        assert not job['cards'] and '_ranked_prefix_snapshot' not in job
        assert job['evidence_mode'] == 'deferred' and job.get('evidence') is not None
        assert 'prepared_inventory_id' not in job and 'prepared_evidence_job_id' not in job
        server._finish_trade_job(job_id, error='synthetic_fallback_stopped')

    monkeypatch.setattr(server, '_run_trade_job', generation)
    monkeypatch.setattr(store, 'ensure_adoption_evidence', write)
    if failure == 'checkpoint':
        def fail_checkpoint(*args, **kwargs):
            raise RuntimeError('synthetic checkpoint outage after commit')
        monkeypatch.setattr(store, 'checkpoint_adoption', fail_checkpoint)
    response = client.post('/api/trades/generate', headers=HEADERS,
                           json={'league_id': LEAGUE, 'fairness_threshold': .5, 'page': 1})
    response = finish(client, response, workers)
    assert response.status_code in (200, 409), response.json
    assert response.json['cards'] == [] and not response.json.get('ranked_prefix_ready')
    if failure == 'first_write':
        assert len(fallback) == 1 and not rows(engine, db.deck_impressions_table)
    else:
        assert not fallback  # Never splice regenerated cards into committed evidence.
        persisted = rows(engine, db.deck_impressions_table)
        assert len(persisted) == (64 if failure == 'changed_inputs' else 30)
        assert {row['impression_id'] for row in persisted if row['delivered_at']} == set(shown)
        job = next(j for j in server._trade_jobs.values()
                   if j.get('prepared_inventory_id') and j['status'] == 'error')
        assert '_ranked_prefix_snapshot' not in job
        if failure == 'changed_inputs':
            assert job['cards'] == [] and job['superseded'] is True


@pytest.mark.parametrize('kind', ['legacy', 'v2'])
def test_input_change_before_first_preview_refuses_without_delivery_or_consumption(request, monkeypatch, kind):
    fixture, store, _, workers = ready(request, monkeypatch, kind)
    client, engine, *_ = fixture
    _config(engine, paywall_enforce_enabled=1., paywall_preview_pages=1.)
    monkeypatch.setattr(entitlements, 'is_enabled', lambda key: key in {'monetize.entitlements', 'monetize.paywall'})
    original = store.ensure_adoption_evidence
    writes, responses = [], []
    def write(*args, **kwargs):
        if writes:
            job = next(j for j in server._trade_jobs.values()
                       if j.get('prepared_inventory_id') == args[0]['inventory_id'] and j['status'] == 'running')
            server.g_universal_by_format['1qb_ppr']['seed']['g'] += 1.
            responses.append(client.get('/api/trades/status?job_id=' + job['job_id'] + '&cursor=0', headers=HEADERS))
        result = original(*args, **kwargs)
        writes.append(1)
        return result
    monkeypatch.setattr(store, 'ensure_adoption_evidence', write)
    response = client.post('/api/trades/generate', headers=HEADERS,
                           json={'league_id': LEAGUE, 'fairness_threshold': .5, 'page': 1})
    response = finish(client, response, workers)
    assert responses and responses[0].status_code == response.status_code == 409
    assert not responses[0].json['cards'] and not response.json['cards']
    assert not rows(engine, db.paywall_previews_table)
    assert not any(row['delivered_at'] for row in rows(engine, db.deck_impressions_table))
