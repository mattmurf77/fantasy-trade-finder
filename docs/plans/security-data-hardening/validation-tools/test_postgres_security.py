"""Actual local PostgreSQL remediation and concurrent SQL correctness."""
import concurrent.futures
import hashlib
import threading

import pytest
from sqlalchemy import insert, select, text
from pg_validation_support import isolated_engine
from backend import database as db
from backend import analytics_ingest as ingest
from scripts.remediate_analytics_tokens import remediate


@pytest.fixture
def pg(monkeypatch):
    eng = isolated_engine()
    db.metadata.create_all(eng)
    monkeypatch.setattr(db, 'engine', eng)
    yield eng
    eng.dispose()


def seed_tokens(eng):
    with eng.begin() as conn:
        for token in ('exposed', 'unexposed'):
            conn.execute(insert(db.sessions_table).values(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                user_id='synthetic', created_at='2026-09-04', last_seen_at='2026-09-04'))
        for token, source, etype in [('exposed','api','signup'), ('exposed','mobile','screen_view'),
                                       ('expired','api','league_synced'), ('device','mobile','screen_view')]:
            conn.execute(insert(db.user_events_table).values(user_id='synthetic', event_type=etype,
                occurred_at='2026-09-04', session_id=token, source=source))


def test_pg_dry_run_apply_targeted_idempotent(pg):
    seed_tokens(pg)
    assert remediate(pg.url.render_as_string(hide_password=False)) == {'mode':'dry_run','event_rows':3,'distinct_identifiers':2,'durable_sessions_to_revoke':1}
    with pg.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM sessions')).scalar_one() == 2
        assert conn.execute(text('SELECT count(*) FROM user_events WHERE session_id IS NOT NULL')).scalar_one() == 4
    assert remediate(pg.url.render_as_string(hide_password=False), apply=True)['durable_sessions_revoked'] == 1
    assert remediate(pg.url.render_as_string(hide_password=False), apply=True)['event_rows'] == 0
    with pg.connect() as conn:
        assert conn.execute(select(db.sessions_table.c.token_hash)).scalars().all() == [hashlib.sha256(b'unexposed').hexdigest()]
        assert conn.execute(text('SELECT session_id FROM user_events WHERE session_id IS NOT NULL')).scalars().all() == ['device']


def test_pg_cleanup_failure_rolls_back(pg):
    seed_tokens(pg)
    with pg.begin() as conn:
        conn.execute(text("CREATE OR REPLACE FUNCTION synthetic_deny() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic deny'; END $$"))
        conn.execute(text('CREATE TRIGGER synthetic_deny BEFORE DELETE ON sessions FOR EACH ROW EXECUTE FUNCTION synthetic_deny()'))
    try:
        with pytest.raises(Exception, match='synthetic deny'):
            remediate(pg.url.render_as_string(hide_password=False), apply=True)
        with pg.connect() as conn:
            assert conn.execute(text('SELECT count(*) FROM sessions')).scalar_one() == 2
            assert conn.execute(text('SELECT count(*) FROM user_events WHERE session_id IS NOT NULL')).scalar_one() == 4
    finally:
        with pg.begin() as conn:
            conn.execute(text('DROP TRIGGER synthetic_deny ON sessions'))
            conn.execute(text('DROP FUNCTION synthetic_deny()'))


def test_pg_concurrent_outcomes_enforce_atomic_caps_and_ownership(pg):
    with pg.begin() as conn:
        conn.execute(insert(db.deck_impressions_table).values(impression_id='concurrent', user_id='owner',
            league_id='league', deck_job_id='job', card_index=0, propensity=1.0, served_at='2026-09-04'))
    assert db.save_deck_outcome('concurrent','like',acting_user_id='foreign') is False
    def submit(action): return db.save_deck_outcome('concurrent',action,acting_user_id='owner')
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(submit, ['viewed'] * 16)) == 1
        assert sum(pool.map(submit, ['undo'] * 48)) == 32


def test_pg_concurrent_conflict_returns_one_actual_insert(pg):
    barrier = threading.Barrier(2)
    def submit(_):
        with pg.begin() as conn:
            barrier.wait(timeout=5)
            return ingest._insert_events_ignore(conn, [dict(event_id='same-event',user_id='owner',event_type='swipe_undone',occurred_at='2026-09-04')])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results.count({'same-event'}) == 1
    assert results.count(set()) == 1


def test_pg_concurrent_ingest_undo_callback_runs_once(pg, monkeypatch):
    from datetime import datetime, timezone
    from backend import server
    from backend.tests import test_outcome_ingest_security as cases
    monkeypatch.setattr(db, 'ingest_engine', pg)
    monkeypatch.setattr(ingest, 'is_enabled', lambda _: True)
    monkeypatch.setattr(ingest, '_rate_exceeded', lambda *_: False)
    monkeypatch.setattr(server, '_deck_signal_v2_enabled', lambda: True)
    monkeypatch.setattr(server, '_deck_taste_enabled', lambda: False)
    monkeypatch.setattr(server, '_sessions', {'verified-test': {'user_id':'owner','verified':True}})
    with pg.begin() as conn:
        conn.execute(insert(db.deck_impressions_table).values(impression_id='owned-impression', user_id='owner',
            league_id='league',deck_job_id='job',card_index=0,propensity=1.0,served_at=datetime.now(timezone.utc).isoformat()))
    barrier = threading.Barrier(2)
    original = ingest._insert_events_ignore
    def raced_insert(conn, rows):
        barrier.wait(timeout=5)
        return original(conn, rows)
    monkeypatch.setattr(ingest, '_insert_events_ignore', raced_insert)
    calls = []
    original_callback = server._save_deck_outcome_safe
    def tracked_callback(*args, **kwargs):
        calls.append((args, kwargs))
        return original_callback(*args, **kwargs)
    monkeypatch.setattr(server, '_save_deck_outcome_safe', tracked_callback)
    env = cases.event(event_type='swipe_undone')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: cases.submit([env]), range(2)))
    assert sorted(r['accepted'] for r in responses) == [0,1]
    assert sum(r['deduped'] for r in responses) == 1
    assert len(calls) == 1
    assert calls[0][0] == ('owned-impression', 'undo')
    with pg.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM deck_outcomes WHERE action='undo'")).scalar_one() == 1
        assert conn.execute(text('SELECT count(*) FROM user_events')).scalar_one() == 1
