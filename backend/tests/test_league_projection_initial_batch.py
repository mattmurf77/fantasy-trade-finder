"""Operator-only initial preparation keeps the ordinary cadence and fences."""
import json
from datetime import datetime, timezone
import pytest
from backend import database as db, outlook_calibration, server
from backend.league_projections import batch, store
from backend.tests.test_league_projection_batch import scheduled
from backend.tests.test_outlook_calibration_persistence import engine


def reset_future(engine):
    due = batch.next_weekly_slot()
    with engine.begin() as conn:
        conn.execute(db.league_projection_targets_table.update().values(next_due_at=due))
    return due


def test_initial_baseline_is_bounded_and_never_repeats_even_after_failure(scheduled):
    due = reset_future(scheduled)
    assert batch.dispatch(None)['queued'] == 0
    assert batch.dispatch(None, initial=True)['queued'] == 1
    row = store.claim()
    assert json.loads(row['input_json'])['scheduled_slot'].startswith('initial:')
    from backend.league_projections.core import Unavailable
    store.fail(row, Unavailable('synthetic_failure'))
    assert batch.dispatch(None, initial=True)['queued'] == 0
    assert batch.target('account', '123')['next_due_at'] == due
    assert batch.dispatch(None)['queued'] == 0


def test_initial_selection_requires_current_own_action_cohort(scheduled, monkeypatch):
    reset_future(scheduled)
    monkeypatch.setattr(outlook_calibration, 'connected_targets', lambda: ([], []))
    assert batch.dispatch(None, initial=True)['queued'] == 0


def test_scoped_initial_cannot_enqueue_another_owner_or_league(scheduled):
    reset_future(scheduled)
    assert batch.dispatch(None, initial=True, user_id='account-1', league_id='123')['queued'] == 0
    assert batch.dispatch(None, initial=True, user_id='account', league_id='456')['queued'] == 0
    assert batch.dispatch(None, initial=True, user_id='account', league_id='123')['queued'] == 1


@pytest.mark.parametrize('kwargs', [dict(initial=1), dict(initial=True, limit=True), dict(initial=True, limit=5),
                                  dict(initial=True, user_id='account'), dict(limit=1), dict(initial=True, league_id='abc', user_id='account')])
def test_invalid_initial_options_refuse(scheduled, kwargs):
    with pytest.raises(ValueError):
        batch.dispatch(None, **kwargs)


def test_initial_create_crash_still_consumes_initial_attempt(scheduled, monkeypatch):
    reset_future(scheduled)
    original = store.create
    class Crash(BaseException): pass
    def crash(*a, **k):
        original(*a, **k)
        raise Crash()
    monkeypatch.setattr(store, 'create', crash)
    with pytest.raises(Crash): batch.dispatch(None, initial=True)
    row = store.claim()
    store.finish(row, {'synthetic': 'complete'})
    monkeypatch.setattr(store, 'create', original)
    assert batch.dispatch(None, initial=True)['queued'] == 0


def test_initial_endpoint_requires_cron_auth_and_rejects_unknown_options(monkeypatch):
    monkeypatch.setattr(server, '_CRON_SECRET', 'synthetic-secret')
    monkeypatch.setattr(server, '_IS_PROD_ENV', True)
    called = []
    monkeypatch.setattr(batch, 'dispatch', lambda fetch, **kw: called.append(kw) or {'queued': 1})
    client = server.app.test_client()
    path = '/api/cron/league-projections'
    assert client.post(path, json={'initial': True}).status_code == 401
    assert client.post(path, json={'initial': True}, headers={'X-Cron-Secret': 'wrong'}).status_code == 401
    assert not called
    headers = {'X-Cron-Secret': 'synthetic-secret'}
    assert client.post(path, json={'force': True}, headers=headers).status_code == 400
    assert client.post(path, json={'initial': True, 'limit': 1}, headers=headers).status_code == 200
    assert called == [{'initial': True, 'limit': 1}]
