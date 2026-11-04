"""Positive, durable first-init eligibility and atomic attribution contracts.

Set FTF_FIRST_INIT_PG_URL only to an explicitly provisioned disposable PG
cluster to run these same cases there. Every case owns a fresh private schema.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, insert, select, text

from backend import database as db, feature_flags, referral_ledger as rl, server

USER, REFERRER, LEAGUE = "first-init-user", "first-init-referrer", "12345678"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    pg_url = os.environ.get("FTF_FIRST_INIT_PG_URL")
    if pg_url:
        base = create_engine(pg_url)
        schema = "first_init_" + uuid.uuid4().hex
        with base.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = base.execution_options(schema_translate_map={None: schema})
    else:
        base = engine = create_engine(f"sqlite:///{tmp_path / 'first-init.db'}",
                                      connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(feature_flags, "is_enabled", lambda key: key == rl.LEDGER_FLAG)
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(
            sleeper_user_id=REFERRER, username="referrer", display_name="The Referrer"))
    try:
        yield engine
    finally:
        if pg_url:
            with base.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def _pending(engine, user=USER):
    with engine.connect() as conn:
        return conn.execute(select(db.users_table.c.first_init_pending).where(
            db.users_table.c.sleeper_user_id == user)).scalar_one()


def _rows(engine, table):
    with engine.connect() as conn:
        return conn.execute(select(table)).mappings().all()


def _initialize(invite_id=None, user=USER):
    return rl.initialize_first_session(
        user_id=user, league_id=LEAGUE, league_platform="sleeper",
        invite_id=invite_id, invited_by=None, new_username="New User",
        session_id="synthetic-first-init-session", device_info={})


@pytest.mark.parametrize("legacy", [None, 0])
def test_ordinary_updates_never_make_legacy_or_consumed_users_eligible(engine, legacy):
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(
            sleeper_user_id=USER, first_init_pending=legacy, invited_by="original"))
    db.upsert_user(USER, username="changed", invited_by="replacement")
    assert _pending(engine) == legacy
    first, _ = _initialize(db.create_referral_invite(REFERRER, LEAGUE, "league_home")["invite_id"])
    assert first is False
    assert [r["event_type"] for r in _rows(engine, db.user_events_table)] == ["app_open"]
    assert _rows(engine, db.referrals_table)[0]["referred_user_id"] is None
    assert next(r for r in _rows(engine, db.users_table)
                if r["sleeper_user_id"] == USER)["invited_by"] == "original"


def test_new_insert_marks_pending_and_repeat_init_is_consumed(engine):
    db.upsert_user(USER, username="new")
    assert _pending(engine) == 1
    token = db.create_referral_invite(REFERRER, LEAGUE, "league_home")["invite_id"]
    assert _initialize(token)[0] is True
    assert _pending(engine) == 0
    db.upsert_user(USER, username="reopened")
    assert _pending(engine) == 0
    assert _initialize(token)[0] is False
    events = _rows(engine, db.user_events_table)
    assert sum(r["event_type"] == "signup" for r in events) == 1
    assert sum(r["event_type"] == "referral_attributed" for r in events) == 1
    assert sum(r["event_type"] == "app_open" for r in events) == 1
    assert len(_rows(engine, db.notifications_table)) == 1


def test_parallel_first_inits_have_one_winner(engine):
    db.upsert_user(USER)
    token = db.create_referral_invite(REFERRER, LEAGUE, "league_home")["invite_id"]
    barrier = threading.Barrier(2)

    def run():
        barrier.wait(timeout=5)
        return _initialize(token)[0]

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: run(), range(2)))
    assert sorted(outcomes) == [False, True]
    assert sum(r["event_type"] == "signup" for r in _rows(engine, db.user_events_table)) == 1
    assert len(_rows(engine, db.notifications_table)) == 1


def test_failure_rolls_back_claim_credit_notification_and_event_then_retries(engine, monkeypatch):
    db.upsert_user(USER)
    token = db.create_referral_invite(REFERRER, LEAGUE, "league_home")["invite_id"]
    real = db.record_event

    def fail_signup(user, event, **kw):
        if event == "signup":
            raise RuntimeError("synthetic signup failure")
        return real(user, event, **kw)

    monkeypatch.setattr(db, "record_event", fail_signup)
    with pytest.raises(RuntimeError, match="synthetic signup failure"):
        _initialize(token)
    assert _pending(engine) == 1
    assert _rows(engine, db.referrals_table)[0]["referred_user_id"] is None
    assert not _rows(engine, db.notifications_table)
    assert not _rows(engine, db.user_events_table)
    assert next(r for r in _rows(engine, db.users_table)
                if r["sleeper_user_id"] == USER)["invited_by"] is None
    monkeypatch.setattr(db, "record_event", real)
    assert _initialize(token)[0] is True
    assert _initialize(token)[0] is False
    assert len(_rows(engine, db.notifications_table)) == 1


def test_handled_unique_conflicts_leave_outer_transaction_usable(engine):
    db.upsert_user(USER)
    token = db.create_referral_invite(REFERRER, LEAGUE, "league_home")["invite_id"]
    parent = db.get_referral_by_invite_token(token)
    existing = {**parent, "id": None, "invite_token": token + "~prior",
                "referred_user_id": USER, "status": "joined"}
    existing.pop("referrer_display_name", None)
    existing.pop("id")
    with engine.begin() as conn:
        conn.execute(insert(db.referrals_table).values(**existing))
    with db.first_init_transaction(USER) as (conn, first):
        assert first
        assert db.claim_referral(parent["id"], USER, "token", conn=conn) is False
        assert db.insert_referral_sibling(parent, USER, conn=conn) is None
        assert conn.execute(select(db.users_table.c.first_init_pending).where(
            db.users_table.c.sleeper_user_id == USER)).scalar_one() == 0
    assert _pending(engine) == 0


def test_deleted_user_cannot_reclaim_or_recreate_rows(engine):
    db.upsert_user(USER)
    token = db.create_referral_invite(REFERRER, LEAGUE, "league_home")["invite_id"]
    with engine.begin() as conn:
        conn.execute(db.users_table.delete().where(db.users_table.c.sleeper_user_id == USER))
    with pytest.raises(db.AccountGone):
        _initialize(token)
    assert not _rows(engine, db.notifications_table)
    assert not _rows(engine, db.user_events_table)
    assert _rows(engine, db.referrals_table)[0]["referred_user_id"] is None


def test_existing_nonempty_inviter_is_never_overwritten(engine):
    db.upsert_user(USER, invited_by="original")
    token = db.create_referral_invite(REFERRER, LEAGUE, "league_home")["invite_id"]
    assert _initialize(token)[0]
    assert next(r for r in _rows(engine, db.users_table)
                if r["sleeper_user_id"] == USER)["invited_by"] == "original"


def test_additive_migration_keeps_old_users_ineligible(engine):
    if engine.dialect.name != "sqlite":
        pytest.skip("legacy SQLite DDL fixture; shared transactions tested on both dialects")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users DROP COLUMN first_init_pending"))
        conn.execute(text("INSERT INTO users (sleeper_user_id) VALUES (:uid)"), {"uid": USER})
    db._migrate_db()
    assert _pending(engine) is None
    db.upsert_user(USER, username="legacy reopened")
    assert _pending(engine) is None
    db.upsert_user("new-after-migration")
    assert _pending(engine, "new-after-migration") == 1


@pytest.mark.parametrize("method", ["token", "league_match"])
def test_pg_referrer_deletion_after_candidate_read_cannot_credit_tombstone(engine, monkeypatch, method):
    if engine.dialect.name != "postgresql":
        pytest.skip("PG read/delete interleaving; SQLite BEGIN IMMEDIATE serializes it")
    from backend import accounts
    db.upsert_user(USER)
    token = db.create_referral_invite(REFERRER, LEAGUE, "league_home")["invite_id"]
    db.record_referral_landing_open(token, "open")
    entered, release = threading.Event(), threading.Event()
    helper = "get_referral_by_invite_token" if method == "token" else "league_match_candidates"
    original = getattr(db, helper)

    def paused(*args, **kw):
        result = original(*args, **kw)
        if kw.get("conn") is not None:
            entered.set()
            assert release.wait(10)
        return result

    monkeypatch.setattr(db, helper, paused)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(_initialize, token if method == "token" else None)
        try:
            assert entered.wait(10)
            accounts.delete_user_data(REFERRER)
        finally:
            release.set()
        assert pending.result(timeout=10)[0] is True
    row = _rows(engine, db.referrals_table)[0]
    assert row["referred_user_id"] is None
    assert row["share_token"] is None
    assert not _rows(engine, db.notifications_table)
    assert not any(r["event_type"] == "referral_attributed"
                   for r in _rows(engine, db.user_events_table))


@pytest.mark.parametrize("stored_platform, expected", [
    ("MFL", "mfl"), ("espn", "espn"), (None, "sleeper"), ("missing-row", None),
])
def test_cross_league_first_init_shares_d1_platform_lookup(engine, stored_platform, expected):
    """The D1 lookup remains lowercase/None-aware while referral attribution
    borrows its first-init connection and reports the credited league."""
    other_league = "87654321"
    db.upsert_user(USER)
    with engine.begin() as conn:
        if stored_platform != "missing-row":
            conn.execute(insert(db.leagues_table).values(
                sleeper_league_id=other_league, user_id=REFERRER,
                platform=stored_platform))
        conn.execute(insert(db.league_members_table).values(
            league_id=other_league, user_id=USER, username="New User",
            roster_data="[]"))
    # This is the exact behavior the free-agent capability uses; absent
    # metadata stays distinguishable from a stored Sleeper/default league.
    assert db.get_league_platform(other_league) == expected
    token = db.create_referral_invite(REFERRER, other_league, "league_home")["invite_id"]
    assert _initialize(token)[0] is True
    (event,) = [r for r in _rows(engine, db.user_events_table)
                if r["event_type"] == "referral_attributed"]
    props = json.loads(event["props"])
    assert props["league_id"] == other_league
    assert props["league_platform"] == (expected or "sleeper")
    assert _rows(engine, db.referrals_table)[0]["referred_user_id"] == USER
