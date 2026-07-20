"""Teardown 06-03 (W3B task 1) — persistent sessions, flag
`auth.persistent_sessions`.

Verified sessions get a durable DB row (token SHA-256-hashed at rest) and
are rebuilt from it after a restart / idle sweep; username-only UNVERIFIED
sessions deliberately stay memory-only (their 4h posture is part of the
impersonation defense). Flag off = the legacy in-memory-only behavior.

Isolation pattern mirrors test_profile_visibility.py: Flask test client,
in-memory SQLite, injected sessions, no network. Session REBUILDS are
exercised by stubbing the heavy builders (_account_build_session /
_extension_build_session) with light fakes honoring the same contract:
register the payload in _sessions under the passed token.
"""
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata

SLEEPER_UID = "777777777700000001"
ACCT_UID = "acct_deadbeef"
TOKEN = "sess-persist-test-token"


def _flags(*enabled):
    on = set(enabled)
    return lambda k: k in on


def _mk_sess(user_id, verified=True, **extra):
    s = {
        "user_id":       user_id,
        "active_format": "1qb_ppr",
        "last_active":   time.time(),
        "display_name":  "Persist Tester",
    }
    if verified:
        s["verified"] = True
        s["verified_via"] = "apple"
    s.update(extra)
    return s


@pytest.fixture()
def env():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    db_patch = patch.object(db_module, "engine", engine)
    db_patch.start()
    try:
        yield c
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
        db_patch.stop()


def _fake_builders():
    """Patch both heavy session builders with light fakes that honor the
    token-reuse contract (register payload under the given token)."""
    def fake_ext(user_id, username, display_name, avatar, token=None):
        import secrets
        token = token or secrets.token_urlsafe(32)
        payload = {
            "user_id": user_id, "username": username,
            "display_name": display_name, "active_format": "1qb_ppr",
            "last_active": time.time(),
        }
        with server._sessions_lock:
            server._sessions[token] = payload
        return token, payload

    def fake_acct(user_id, display_name, token=None):
        token, payload = fake_ext(user_id, "", display_name, None, token=token)
        payload["account_only"] = True
        return token, payload

    return (patch.object(server, "_extension_build_session", fake_ext),
            patch.object(server, "_account_build_session", fake_acct))


# ── Persist-eligibility + flag-off darkness ─────────────────────────────


def test_flag_off_persists_nothing_and_never_reads_db(env):
    sess = _mk_sess(ACCT_UID, verified=True, account_only=True)
    with patch.object(server, "is_enabled", _flags()):
        server._persist_session_if_eligible(TOKEN, sess)
        assert db_module.load_persisted_session(TOKEN) is None
        # Even with a row planted (e.g. from a past flag-on period), a
        # memory miss stays a miss — flag-off behavior is the legacy 401.
        db_module.persist_session(TOKEN, user_id=ACCT_UID)
        assert server._get_session(TOKEN) is None


def test_unverified_username_session_is_never_persisted(env):
    """The 4h squatter posture survives flag-on: no DB row for an
    unverified session ⇒ memory eviction/restart stays terminal."""
    sess = _mk_sess(SLEEPER_UID, verified=False)
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")):
        server._persist_session_if_eligible(TOKEN, sess)
        assert db_module.load_persisted_session(TOKEN) is None
        # Simulated restart: nothing to restore → 401.
        r = env.get("/api/session/ping", headers={"X-Session-Token": TOKEN})
        assert r.status_code == 401


def test_demo_session_is_never_persisted(env):
    sess = _mk_sess("demo_user_1", verified=True, is_demo=True)
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")):
        server._persist_session_if_eligible(TOKEN, sess)
    assert db_module.load_persisted_session(TOKEN) is None


def test_verified_session_row_is_hashed_at_rest(env):
    sess = _mk_sess(ACCT_UID, verified=True, account_only=True,
                    account_id="deadbeef")
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")):
        server._persist_session_if_eligible(TOKEN, sess)
    row = db_module.load_persisted_session(TOKEN)
    assert row is not None
    assert row["user_id"] == ACCT_UID
    assert row["verified_via"] == "apple"
    assert row["account_only"] == 1
    assert row["token_hash"] == db_module.session_token_hash(TOKEN)
    assert TOKEN not in row["token_hash"]          # raw token never stored
    assert row["created_at"] and row["last_seen_at"]


def test_heartbeat_is_throttled(env):
    sess = _mk_sess(SLEEPER_UID, verified=True)
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")):
        server._persist_session_if_eligible(TOKEN, sess)
        first_seen = db_module.load_persisted_session(TOKEN)["last_seen_at"]
        # Second call inside the throttle window: no DB write.
        server._persist_session_if_eligible(TOKEN, sess)
        assert db_module.load_persisted_session(TOKEN)["last_seen_at"] == first_seen
        # Past the window: refreshed.
        sess["_persisted_at"] = time.time() - server._PERSISTED_TOUCH_THROTTLE_S - 1
        server._persist_session_if_eligible(TOKEN, sess)
        assert db_module.load_persisted_session(TOKEN)["last_seen_at"] >= first_seen


# ── Restart survival (restore path) ─────────────────────────────────────


def test_restart_restores_account_only_session(env):
    """New store instance (empty _sessions) + durable row ⇒ the token stays
    valid and the rebuilt session is verified/account-only."""
    sess = _mk_sess(ACCT_UID, verified=True, account_only=True,
                    account_id="deadbeef")
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")):
        server._persist_session_if_eligible(TOKEN, sess)
    # Simulated deploy/restart: the in-memory store never saw this token.
    with server._sessions_lock:
        assert TOKEN not in server._sessions
    p1, p2 = _fake_builders()
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")), p1, p2:
        r = env.get("/api/session/ping", headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200
    assert r.get_json()["user_id"] == ACCT_UID
    with server._sessions_lock:
        restored = server._sessions[TOKEN]
    assert restored["verified"] is True
    assert restored["verified_via"] == "apple"
    assert restored["account_id"] == "deadbeef"
    assert restored["account_only"] is True


def test_restart_restores_sleeper_keyed_verified_session(env):
    db_module.upsert_user(sleeper_user_id=SLEEPER_UID,
                          username="persist_bob", display_name="Bob")
    sess = _mk_sess(SLEEPER_UID, verified=True, username="persist_bob")
    sess["verified_via"] = "sleeper"
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")):
        server._persist_session_if_eligible(TOKEN, sess)
    p1, p2 = _fake_builders()
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")), p1, p2:
        restored = server._get_session(TOKEN)
    assert restored is not None
    assert restored["user_id"] == SLEEPER_UID
    assert restored["verified"] is True
    assert restored["verified_via"] == "sleeper"


def test_expired_row_is_rejected_and_purged(env):
    sess = _mk_sess(ACCT_UID, verified=True)
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")):
        server._persist_session_if_eligible(TOKEN, sess)
    # Age the row past the rolling 90d window.
    stale = (datetime.now(timezone.utc)
             - timedelta(days=server._PERSISTED_SESSION_IDLE_DAYS + 1)).isoformat()
    from sqlalchemy import update as sa_update
    with db_module.engine.begin() as conn:
        conn.execute(sa_update(db_module.sessions_table)
                     .values(last_seen_at=stale))
    p1, p2 = _fake_builders()
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")), p1, p2:
        assert server._get_session(TOKEN) is None
    assert db_module.load_persisted_session(TOKEN) is None   # purged on read


def test_purge_sweep_removes_stale_rows_only(env):
    db_module.persist_session("fresh-token", user_id=SLEEPER_UID)
    db_module.persist_session("stale-token", user_id=SLEEPER_UID)
    stale = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    from sqlalchemy import update as sa_update
    with db_module.engine.begin() as conn:
        conn.execute(
            sa_update(db_module.sessions_table)
            .where(db_module.sessions_table.c.token_hash
                   == db_module.session_token_hash("stale-token"))
            .values(last_seen_at=stale))
    assert db_module.purge_stale_persisted_sessions(90) == 1
    assert db_module.load_persisted_session("fresh-token") is not None
    assert db_module.load_persisted_session("stale-token") is None


# ── Eviction paths delete durable rows ──────────────────────────────────


def test_signout_deletes_durable_row(env):
    sess = _mk_sess(ACCT_UID, verified=True)
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")):
        server._persist_session_if_eligible(TOKEN, sess)
        assert db_module.load_persisted_session(TOKEN) is not None
        r = env.post("/api/session/signout",
                     headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200
    assert r.get_json()["evicted"] is True
    assert db_module.load_persisted_session(TOKEN) is None
    with server._sessions_lock:
        assert TOKEN not in server._sessions


def test_signout_flag_off_contract_unchanged(env):
    """No durable row, flag off — response is byte-identical to legacy."""
    with server._sessions_lock:
        server._sessions[TOKEN] = _mk_sess(SLEEPER_UID, verified=False)
    with patch.object(server, "is_enabled", _flags()):
        r = env.post("/api/session/signout",
                     headers={"X-Session-Token": TOKEN})
        assert r.status_code == 200
        assert r.get_json() == {"ok": True, "evicted": True}
        r = env.post("/api/session/signout",
                     headers={"X-Session-Token": TOKEN})
        assert r.get_json() == {"ok": True, "evicted": False}


def test_account_deletion_deletes_every_durable_row_for_user(env):
    db_module.upsert_user(sleeper_user_id=SLEEPER_UID,
                          username="persist_del", display_name="Del")
    sess = _mk_sess(SLEEPER_UID, verified=True)
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")):
        server._persist_session_if_eligible(TOKEN, sess)
        db_module.persist_session("second-device-token", user_id=SLEEPER_UID)
        with patch.object(server._accounts, "has_apple_identity",
                          return_value=False), \
             patch.object(server._accounts, "delete_user_data",
                          return_value={"users": 1}):
            r = env.delete("/api/account",
                           headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200
    assert db_module.load_persisted_session(TOKEN) is None
    assert db_module.load_persisted_session("second-device-token") is None
    with server._sessions_lock:
        assert TOKEN not in server._sessions


def test_session_init_user_change_deletes_stale_row(env):
    """Re-pointing a token at a different user must not leave a durable row
    that could resurrect the OLD identity (parity with session_init's
    in-memory verified-state pop; exercised via the extracted helper the
    route calls)."""
    db_module.persist_session(TOKEN, user_id=SLEEPER_UID,
                              verified_via="sleeper")
    sess = _mk_sess("777777777700000002", verified=False,
                    _persisted_at=time.time())
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")):
        server._sync_persisted_session_after_init(TOKEN, sess,
                                                  user_changed=True)
    assert db_module.load_persisted_session(TOKEN) is None
    assert "_persisted_at" not in sess


def test_session_init_same_user_refreshes_row(env):
    sess = _mk_sess(SLEEPER_UID, verified=True)
    with patch.object(server, "is_enabled",
                      _flags("auth.persistent_sessions")):
        server._sync_persisted_session_after_init(TOKEN, sess,
                                                  user_changed=False)
    row = db_module.load_persisted_session(TOKEN)
    assert row is not None and row["user_id"] == SLEEPER_UID


def test_persisted_row_expired_fails_closed_on_garbage(env):
    assert server._persisted_row_expired({"last_seen_at": "not-a-date"}) is True
    fresh = {"last_seen_at": datetime.now(timezone.utc).isoformat()}
    assert server._persisted_row_expired(fresh) is False
