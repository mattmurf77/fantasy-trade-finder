"""Saved views exclude private snapshots, collapse duplicate reads and preserve JSON."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from backend import database as db
from backend.league_projections import api, batch, store
from backend.tests.test_league_projection_routes import client, engine

PUBLIC_FIELDS = {'run_id', 'status', 'created_at', 'updated_at', 'input_hash', 'reason', 'details_json', 'result_json'}


def seed(engine, *, attempt='same', age=0):
    now = datetime.now(timezone.utc)
    first = 'a' * 32
    second = first if attempt == 'same' else 'b' * 32
    result = {'teams': [{'roster_id': 1, 'weeks': [{'week': 9, 'actual_mean': 100}],
                        'pick_owner_roster_id': 1, 'playoff_probability': .6, 'nonplayoff_probability': .4,
                        'maxpf_mean': 120, 'conditional_expected_pick': 1.5, 'nonplayoff_samples': 400}],
              'schema': 'synthetic', 'model_version': 'synthetic', 'config': {}, 'seed': 1, 'iterations': 1000,
              'snapshot_hash': 'synthetic', 'source': 'synthetic', 'captured_at': now.isoformat(), 'coverage': {}, 'warnings': []}
    row = {'run_id': first, 'user_id': 'account', 'league_id': '123', 'status': 'complete',
           'created_at': (now-timedelta(days=age)).isoformat(), 'updated_at': now.isoformat(),
           'expires_at': now.isoformat(), 'request_hash': 'synthetic', 'input_json': '{"private_input":true}',
           'snapshot_json': json.dumps({'private_snapshot': 'x' * (2 * 1024 * 1024)}),
           'result_json': json.dumps(result), 'details_json': '{"coverage":"partial"}', 'input_hash': 'synthetic', 'worker_token': 'private-token'}
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.insert().values(**row))
        if attempt != 'same':
            conn.execute(db.league_projection_runs_table.insert().values(**{**row, 'run_id': second,
                'status': attempt, 'result_json': None if attempt != 'complete' else json.dumps({**result, 'seed': 2}),
                'reason': 'synthetic_failure' if attempt == 'failed' else None}))
        conn.execute(db.league_projection_targets_table.insert().values(target_id='target', user_id='account', league_id='123',
            league_user_id='account', season=2026, created_at=now.isoformat(),
            next_due_at=(now+timedelta(days=7)).isoformat(), last_success_id=first, last_attempt_id=second))
    return first, second


@contextmanager
def selected(engine):
    statements=[]
    def before(conn, clause, multiparams, params, execution_options):
        if getattr(clause, 'is_select', False) and 'league_projection_runs' in str(clause):
            statements.append(clause)
    event.listen(engine, 'before_execute', before)
    try:
        yield statements
    finally:
        event.remove(engine, 'before_execute', before)


def test_public_select_excludes_large_private_payload_and_has_all_identity_predicates(engine):
    first, _ = seed(engine)
    with selected(engine) as statements:
        rows = store.public_rows((first, first, None), 'account', '123')
    assert len(statements) == 1 and set(rows[first]) == PUBLIC_FIELDS
    statement = statements[0]
    assert {c.name for c in statement.selected_columns} == PUBLIC_FIELDS
    compiled = statement.compile(dialect=postgresql.dialect())
    assert list(compiled.params.values()) == [[first], 'account', '123']
    assert 'league_projection_runs.user_id =' in str(compiled)
    assert 'league_projection_runs.league_id =' in str(compiled)
    full = store.get(first, 'account', '123')
    assert len(full['snapshot_json']) > 2 * 1024 * 1024
    assert rows[first] == {k: full[k] for k in PUBLIC_FIELDS}


@pytest.mark.parametrize('uid,lid', [('other', '123'), ('account', '456')])
def test_wrong_identity_never_returns_public_row(engine, uid, lid):
    first, _ = seed(engine)
    assert store.public_rows((first,), uid, lid) == {}


def test_empty_missing_and_deleted_ids_are_not_cached(engine):
    with selected(engine) as statements:
        assert store.public_rows((None,), 'account', '123') == {}
    assert statements == []
    first, _ = seed(engine)
    assert store.public_rows((first, 'missing'), 'account', '123').keys() == {first}
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.delete())
    assert store.public_rows((first,), 'account', '123') == {}


@pytest.mark.parametrize('attempt,age,state', [('same',0,'current'), ('same',10,'stale'), ('running',0,'running'),
                                             ('queued',0,'queued'), ('failed',0,'refresh_failed'), ('complete',0,'current')])
def test_latest_one_query_and_exact_full_row_response_parity(client, engine, monkeypatch, attempt, age, state):
    http, _ = client
    first, second = seed(engine, attempt=attempt, age=age)
    with selected(engine) as statements:
        actual = http.get('/api/leagues/123/projection-runs/latest')
    assert actual.status_code == 200 and actual.json['state'] == state
    assert len(statements) == 1
    assert set(statements[0].compile().params['run_id_1']) == {first, second}
    # Previous path: two independent full-row gets, including duplicated IDs.
    def previous_rows(ids, uid, lid):
        return {rid: store.get(rid, uid, lid) for rid in ids if rid}
    monkeypatch.setattr(store, 'public_rows', previous_rows)
    expected = http.get('/api/leagues/123/projection-runs/latest')
    assert actual.data == expected.data


def test_same_latest_result_is_decoded_once(client, engine, monkeypatch):
    http, _ = client
    first, _ = seed(engine)
    full = store.get(first, 'account', '123')
    original = api.json.loads
    calls=[]
    def loads(text, *a, **kw):
        if text == full['result_json']:
            calls.append(text)
        return original(text, *a, **kw)
    monkeypatch.setattr(api.json, 'loads', loads)
    response = http.get('/api/leagues/123/projection-runs/latest')
    assert len(calls) == 1
    assert response.json['run'] == response.json['attempt']


@pytest.mark.parametrize('suffix', ['', '/teams', '/draft', '/teams/1/weeks', '/export/manifest', '/export/csv'])
def test_read_and_export_response_parity_without_snapshot(client, engine, monkeypatch, suffix):
    http, _ = client
    first, _ = seed(engine)
    url = '/api/projection-runs/' + first + suffix
    with selected(engine) as statements:
        actual = http.get(url)
    assert actual.status_code == 200 and len(statements) == 1
    assert {c.name for c in statements[0].selected_columns} == PUBLIC_FIELDS
    monkeypatch.setattr(store, 'public_rows', lambda ids, uid, lid: {rid: store.get(rid, uid, lid) for rid in ids})
    expected = http.get(url)
    assert actual.data == expected.data and actual.content_type == expected.content_type
