"""GET /api/session/ping returns `verification` (head-eng 2026-10-28).

An account-only session (Apple-first, no league) never reaches
/api/session/init, until now the only source of the additive `verification`
field, so its client asks ping instead. Pinned here: ping returns the same
four fields, from the same sources session/init uses (this session's own
`verified` stamp, and the user_id's stored verified_via), for an
account-only session restored after a restart too.

An unverified or demo session (session/init answers it 403) gets the constant
unverified answer with no lookup at all: otherwise ping would tell anyone who
can name a user_id whether that account exists and which provider proved it
(legal R28.9 row 4 / R28.14; release-lead #524 QA P1).
"""
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, insert

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


def test_a_verified_session_reads_the_user_row_not_its_own_stamp(env):
    """session/init's source: the user_id's stored verified_via (here Apple,
    linked later), not the provider this session was verified with."""
    c, engine = env
    _user(engine, SLEEPER_UID, "apple")
    _put({"user_id": SLEEPER_UID, "active_format": "1qb_ppr", "last_active": time.time(),
          "verified": True, "verified_via": "sleeper"})
    with patch.object(server, "is_enabled", lambda k: False):
        v = _ping(c).get_json()["verification"]
    assert v == {"session_verified": True, "user_verified": True,
                 "verified_via": "apple", "enforced": False}


UNVERIFIED = {"session_verified": False, "user_verified": False,
              "verified_via": None, "enforced": False}


def test_an_unverified_session_for_a_verified_user_learns_nothing_about_it(env):
    """THIS session unproven while another controller verified the user_id
    (a squatter, or anyone who typed a public Sleeper username): the constant
    unverified answer, never the user's provider."""
    c, engine = env
    _user(engine, SLEEPER_UID, "sleeper")
    _put({"user_id": SLEEPER_UID, "active_format": "1qb_ppr", "last_active": time.time()})
    with patch.object(server, "is_enabled", lambda k: False), \
         patch.object(accounts, "get_user_verified_via") as lookup:
        v = _ping(c).get_json()["verification"]
    assert v == UNVERIFIED
    lookup.assert_not_called()


def test_a_demo_session_reads_unverified_even_if_stamped(env):
    c, engine = env
    _user(engine, ACCT_UID, "apple")
    _put({"user_id": ACCT_UID, "active_format": "1qb_ppr", "last_active": time.time(),
          "verified": True, "verified_via": "apple", "is_demo": True})
    with patch.object(server, "is_enabled", lambda k: False), \
         patch.object(accounts, "get_user_verified_via") as lookup:
        v = _ping(c).get_json()["verification"]
    assert v == UNVERIFIED
    lookup.assert_not_called()


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


# Every session type the server mints. Ping's body and its `verification`
# carry exactly these keys, so an extra top-level field (an entitlement, the
# user's provider) goes red here.
PING_KEYS = {"ok", "user_id", "league", "verification"}
VERIFICATION_KEYS = {"session_verified", "user_verified", "verified_via", "enforced"}
SESSION_TYPES = {
    "account_only_apple": {"user_id": ACCT_UID, "verified": True, "verified_via": "apple",
                           "account_only": True},
    "verified_league":    {"user_id": SLEEPER_UID, "verified": True, "verified_via": "sleeper",
                           "league": SimpleNamespace(name="Dynasty League")},
    "unverified_sleeper": {"user_id": SLEEPER_UID},
    "squatter":           {"user_id": ACCT_UID},
    "entry_claim":        {"user_id": "espn_entry_0001", "account_only": True},
    "extension":          {"user_id": SLEEPER_UID, "extension": True},
    "demo":               {"user_id": "demo_0001", "is_demo": True},
}


@pytest.mark.parametrize("kind", sorted(SESSION_TYPES))
def test_ping_carries_exactly_its_keys_for_every_session_type(env, kind):
    c, engine = env
    _user(engine, ACCT_UID, "apple")
    _user(engine, SLEEPER_UID, "sleeper")
    _put({"active_format": "1qb_ppr", "last_active": time.time(), **SESSION_TYPES[kind]})
    with patch.object(server, "is_enabled", lambda k: False):
        r = _ping(c)
    assert r.status_code == 200
    body = r.get_json()
    assert set(body) == PING_KEYS
    assert set(body["verification"]) == VERIFICATION_KEYS
    if not SESSION_TYPES[kind].get("verified") or SESSION_TYPES[kind].get("is_demo"):
        assert body["verification"] == UNVERIFIED


def _count_sql(engine):
    seen = []
    event.listen(engine, "before_cursor_execute",
                 lambda *a, **k: seen.append(a[2]))
    return seen


@pytest.mark.parametrize("token", ["", "sess-nobody-has-this-token"])
def test_an_anonymous_ping_runs_no_sql(env, token):
    c, engine = env
    seen = _count_sql(engine)
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.get("/api/session/ping", headers={"X-Session-Token": token} if token else {})
    assert r.status_code == 401
    assert seen == []


@pytest.mark.parametrize("kind", ["unverified_sleeper", "squatter", "entry_claim", "demo"])
def test_an_unverified_ping_runs_no_sql(env, kind):
    c, engine = env
    _user(engine, ACCT_UID, "apple")
    _user(engine, SLEEPER_UID, "sleeper")
    _put({"active_format": "1qb_ppr", "last_active": time.time(), **SESSION_TYPES[kind]})
    seen = _count_sql(engine)
    with patch.object(server, "is_enabled", lambda k: False):
        assert _ping(c).status_code == 200
    assert seen == []


def test_a_verified_ping_reads_the_user_row(env):
    """The positive control for the 0-SQL tests: the counter sees the lookup."""
    c, engine = env
    _user(engine, ACCT_UID, "apple")
    _put({"active_format": "1qb_ppr", "last_active": time.time(),
          **SESSION_TYPES["account_only_apple"]})
    seen = _count_sql(engine)
    with patch.object(server, "is_enabled", lambda k: False):
        assert _ping(c).get_json()["verification"]["verified_via"] == "apple"
    assert seen


FOREIGN_UID = "acct_foreign0001"


@pytest.mark.parametrize("kind", ["account_only_apple", "unverified_sleeper"])
def test_a_foreign_user_id_in_the_request_is_ignored(env, kind):
    """Ping answers for the session's own user only: a user_id in the query
    or an X-User-Id header names nobody."""
    c, engine = env
    _user(engine, ACCT_UID, "apple")
    _user(engine, SLEEPER_UID, None)
    _user(engine, FOREIGN_UID, "google")
    sess = SESSION_TYPES[kind]
    _put({"active_format": "1qb_ppr", "last_active": time.time(), **sess})
    with patch.object(server, "is_enabled", lambda k: False):
        body = c.get(f"/api/session/ping?user_id={FOREIGN_UID}",
                     headers={"X-Session-Token": TOKEN, "X-User-Id": FOREIGN_UID}).get_json()
    assert body["user_id"] == sess["user_id"]
    if sess.get("verified"):
        assert body["verification"]["verified_via"] == "apple"
    else:
        assert body["verification"] == UNVERIFIED
