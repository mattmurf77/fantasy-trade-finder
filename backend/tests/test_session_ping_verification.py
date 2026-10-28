"""GET /api/session/ping returns `verification` (head-eng 2026-10-28).

An account-only session (Apple-first, no league) never reaches
/api/session/init, until now the only source of the additive `verification`
field, so its client asks ping instead. Pinned here: ping returns the same
four fields, from the same sources session/init uses (this session's own
`verified` stamp, and the user_id's stored verified_via), for an
account-only session restored after a restart too.
"""
import time
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.server as server
from backend import accounts
from backend.database import metadata
from backend.tests import test_persistent_sessions as persist_t

ACCT_UID = "acct_ping0001"
SLEEPER_UID = "777777777700000077"
TOKEN = "sess-ping-verification-token"


@pytest.fixture()
def env():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with patch.object(db_module, "engine", engine):
        try:
            yield c, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


def _put(sess):
    with server._sessions_lock:
        server._sessions[TOKEN] = sess


def _ping(c):
    return c.get("/api/session/ping", headers={"X-Session-Token": TOKEN})


def _user(engine, uid, via):
    with engine.begin() as conn:
        conn.execute(insert(db_module.users_table).values(sleeper_user_id=uid))
    if via:
        accounts.mark_user_verified(uid, via)


def test_an_account_only_apple_session_reads_verified(env):
    c, engine = env
    _user(engine, ACCT_UID, "apple")
    _put({"user_id": ACCT_UID, "active_format": "1qb_ppr", "last_active": time.time(),
          "verified": True, "verified_via": "apple", "account_only": True})
    with patch.object(server, "is_enabled", lambda k: k == "auth.enforce_verified_writes"):
        r = _ping(c)
    assert r.status_code == 200
    assert r.get_json()["verification"] == {
        "session_verified": True, "user_verified": True,
        "verified_via": "apple", "enforced": True}


def test_an_unverified_session_reads_unverified(env):
    c, engine = env
    _user(engine, SLEEPER_UID, None)
    _put({"user_id": SLEEPER_UID, "active_format": "1qb_ppr", "last_active": time.time()})
    with patch.object(server, "is_enabled", lambda k: False):
        body = _ping(c).get_json()
    assert body["verification"] == {
        "session_verified": False, "user_verified": False,
        "verified_via": None, "enforced": False}


def test_an_unverified_session_for_a_verified_user_reads_the_squatter_case(env):
    """THIS session unproven while another controller verified the user_id:
    the same shape session/init reports (user_verified true)."""
    c, engine = env
    _user(engine, SLEEPER_UID, "sleeper")
    _put({"user_id": SLEEPER_UID, "active_format": "1qb_ppr", "last_active": time.time()})
    with patch.object(server, "is_enabled", lambda k: False):
        v = _ping(c).get_json()["verification"]
    assert (v["session_verified"], v["user_verified"], v["verified_via"]) == (False, True, "sleeper")


def test_a_restored_account_only_session_reads_verified(env):
    """After a restart the session comes back from its durable row (only
    verified sessions persist), and ping still answers verified."""
    c, engine = env
    _user(engine, ACCT_UID, "apple")
    with patch.object(server, "is_enabled", lambda k: k == "auth.persistent_sessions"):
        server._persist_session_if_eligible(
            TOKEN, persist_t._mk_sess(ACCT_UID, verified=True, account_only=True))
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)          # the restart
        ext, acct = persist_t._fake_builders()
        with ext, acct:
            r = _ping(c)
    assert r.status_code == 200
    v = r.get_json()["verification"]
    assert v["session_verified"] is True and v["verified_via"] == "apple"


def test_a_verified_via_lookup_failure_never_fails_the_ping(env):
    c, engine = env
    _put({"user_id": ACCT_UID, "active_format": "1qb_ppr", "last_active": time.time(), "verified": True})
    with patch.object(accounts, "get_user_verified_via", side_effect=RuntimeError("db down")), \
         patch.object(server, "is_enabled", lambda k: False):
        r = _ping(c)
    assert r.status_code == 200
    assert r.get_json()["verification"]["session_verified"] is True
    assert r.get_json()["verification"]["user_verified"] is False


def test_no_session_is_still_a_401_without_verification(env):
    c, _ = env
    r = _ping(c)
    assert r.status_code == 401 and "verification" not in (r.get_json() or {})
