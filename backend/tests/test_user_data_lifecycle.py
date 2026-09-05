"""Real concurrent admissions, deletion draining, and stale work rejection."""
import threading
import uuid

import pytest
from sqlalchemy import create_engine, insert, select

from backend import accounts, database as db, server, user_data_lifecycle as lifecycle


def test_concurrent_work_is_admitted_and_deletion_drains_both():
    uid = uuid.uuid4().hex
    release = threading.Event()
    entered = [threading.Event(), threading.Event()]
    deleted = threading.Event()
    errors = []
    old = lifecycle.capture(uid)

    def work(index):
        try:
            with old.active() as active:
                assert active
                entered[index].set()
                assert release.wait(3)
                # A synchronous child must finish even after deletion starts waiting.
                with old.active() as nested:
                    assert nested
        except Exception as error:
            errors.append(error)

    def delete():
        with lifecycle.hold([uid]):
            lifecycle.invalidate([uid])
            deleted.set()

    workers = [threading.Thread(target=work, args=(i,)) for i in range(2)]
    for thread in workers:
        thread.start()
    deletion = None
    try:
        assert all(event.wait(2) for event in entered), 'job must not block status requests'
        deletion = threading.Thread(target=delete)
        deletion.start()
        assert not deleted.wait(0.05)
    finally:
        release.set()
        for thread in workers + ([deletion] if deletion else []):
            thread.join(3)
            assert not thread.is_alive()
    assert not errors
    assert deleted.is_set()
    with old.active() as active:
        assert not active
    with lifecycle.capture(uid).active() as active:
        assert active, 'fresh registration after deletion is allowed'


def test_timeout_leaves_work_valid_and_reopens_admission():
    uid = uuid.uuid4().hex
    lease = lifecycle.capture(uid)
    with lease.active() as active:
        assert active
        with pytest.raises(lifecycle.UserDataBusy):
            with lifecycle.hold([uid], timeout=0.01):
                pytest.fail('cannot delete active data')
        with lease.active() as active_again:
            assert active_again


def test_snapshot_rejects_identity_resolved_after_deletion():
    uid = uuid.uuid4().hex
    started = lifecycle.snapshot()
    with lifecycle.hold([uid]):
        lifecycle.invalidate([uid])
    with lifecycle.capture(uid, started=started).active() as active:
        assert not active


def test_background_work_cannot_recreate_deleted_counterparty_data():
    owner, counterparty = uuid.uuid4().hex, uuid.uuid4().hex
    queued = lifecycle.capture(owner)
    with lifecycle.hold([counterparty]):
        lifecycle.invalidate([counterparty])
    with queued.active() as active:
        assert active
        with lifecycle.capture(counterparty).active() as target_active:
            assert not target_active
    with lifecycle.capture(counterparty).active() as fresh:
        assert fresh, 'the originating revision must be cleared after work exits'


@pytest.fixture
def data_env(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'lifecycle.sqlite'),
                           connect_args={'check_same_thread': False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, 'engine', engine)
    monkeypatch.setattr(server, 'is_enabled', lambda key: False)
    monkeypatch.setattr(accounts, 'has_apple_identity', lambda *a, **kw: False)
    uid, token = uuid.uuid4().hex, uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=uid))
    with server._sessions_lock:
        server._sessions[token] = {'user_id': uid, 'verified': True}
    yield engine, uid, token
    with server._sessions_lock:
        server._sessions.pop(token, None)
    engine.dispose()


def test_delete_waits_for_authorized_http_write_then_removes_it(data_env, monkeypatch):
    engine, uid, token = data_env
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    results = []

    def delayed_route():
        entered.set()
        assert release.wait(3)
        db.record_event(uid, 'late_fixture_event')
        return {'ok': True}

    monkeypatch.setitem(server.app.view_functions, 'get_account_route', delayed_route)
    def request():
        with server.app.test_client() as client:
            results.append(client.get('/api/account', headers={'X-Session-Token': token}).status_code)
    def delete():
        with server.app.test_client() as client:
            results.append(client.delete('/api/account', headers={'X-Session-Token': token}).status_code)
        finished.set()
    worker = threading.Thread(target=request)
    worker.start()
    deletion = None
    try:
        assert entered.wait(2)
        deletion = threading.Thread(target=delete)
        deletion.start()
        assert not finished.wait(0.05)
    finally:
        release.set()
        for thread in [worker] + ([deletion] if deletion else []):
            thread.join(3)
            assert not thread.is_alive()
    assert results == [200, 200]
    with engine.connect() as conn:
        assert not conn.execute(select(db.user_events_table).where(db.user_events_table.c.user_id == uid)).first()
        assert not conn.execute(select(db.users_table).where(db.users_table.c.sleeper_user_id == uid)).first()


def test_queued_generation_never_runs_after_deletion(data_env, monkeypatch):
    _, uid, token = data_env
    queued, ran = [], []
    class DeferredThread:
        def __init__(self, *, target, args=(), kwargs=None, **ignored):
            self.call = lambda: target(*args, **(kwargs or {}))
        def start(self):
            queued.append(self.call)
    monkeypatch.setattr(server.threading, 'Thread', DeferredThread)
    monkeypatch.setattr(server, '_run_trade_job', lambda *a, **kw: ran.append(True))
    job = server._kickoff_trade_job(token, uid, 'fixture-league', '1qb_ppr')
    try:
        response = server.app.test_client().delete('/api/account', headers={'X-Session-Token': token})
        assert response.status_code == 200
        queued[0]()
        assert not ran
        assert server._trade_jobs[job]['error'] == 'account_deleted'
    finally:
        server._trade_jobs.pop(job, None)
        server._trade_jobs_by_key.pop(server._trade_job_key(uid, 'fixture-league', '1qb_ppr'), None)


def test_late_auth_and_notification_cannot_recreate_deleted_user(data_env, monkeypatch):
    engine, uid, _ = data_env
    monkeypatch.setattr(server, '_load_sleeper_cache', lambda: {})
    with server.app.test_request_context('/api/extension/auth', method='POST'):
        server._acquire_user_data_lease()
        accounts.delete_user_data(uid)
        with pytest.raises(server._SessionExpired):
            server._extension_build_session(uid, 'fixture', 'Fixture', None)
        server._write_inbox_row(uid, 'match_expiring', title='Fixture', body='Fixture')
    with engine.connect() as conn:
        assert not conn.execute(select(db.users_table).where(db.users_table.c.sleeper_user_id == uid)).first()
        assert not conn.execute(select(db.notifications_table).where(db.notifications_table.c.user_id == uid)).first()


def test_provider_proof_started_before_delete_cannot_create_replacement_account(data_env):
    engine, uid, _ = data_env
    account = accounts.find_or_create_account('apple', 'synthetic-provider-subject')
    accounts.bind_sleeper_user(account['account_id'], uid)
    with server.app.test_request_context('/api/auth/apple', method='POST', json={}):
        server._acquire_user_data_lease()
        accounts.delete_user_data(uid)
        with pytest.raises(server._SessionExpired):
            server._provider_auth_response('apple', {'sub': 'synthetic-provider-subject'})
    with engine.connect() as conn:
        assert not conn.execute(select(db.accounts_table)).first()
        assert not conn.execute(select(db.linked_identities_table)).first()
    # A later explicit sign-in has a new revision and remains supported.
    with server.app.test_request_context('/api/auth/apple', method='POST', json={}):
        server._acquire_user_data_lease()
        server._hold_request_user_data(accounts.identity_work_key('apple', 'synthetic-provider-subject'))
