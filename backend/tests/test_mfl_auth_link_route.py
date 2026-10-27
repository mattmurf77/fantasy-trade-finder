"""Tests for MFL authenticated linking (#177, flag `mfl.auth_link`):

  POST /api/mfl/auth-link   — MFL login → myleagues list, cookie stored
  POST /api/mfl/auth-import — import selected leagues (default ALL),
                              franchise auto-bound from myleagues

plus the mfl_service login/myleagues adapters (injected _opener, no network).

Credential-safety invariants asserted here:
  * the password is used transiently — never logged, never persisted anywhere
  * only the returned MFL cookie is stored, Fernet-encrypted (SLEEPER_TOKEN_KEY)
  * with no encryption key the cookie is SESSION-ONLY (nothing hits the DB)

Flask test client + in-memory SQLite; MFL HTTP is patched (login /
fetch_my_leagues / fetch_league_bundle / resolve_host) — no live creds, no
network. Mirrors test_mfl_link_route.py / test_espn_link_route.py patterns.
"""
import copy
import json
import logging
import os
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.espn_service as es
import backend.mfl_service as mfl
import backend.server as server
import backend.sleeper_write as sw
from backend.database import metadata

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
BUNDLE_FIXTURE = os.path.join(FIXTURES, "mfl_league_snapshot_2026-07-17.json")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")

USER = "313560442465169408"
PASSWORD = "s3cret-hunter2-pw"           # only ever passed in request bodies
COOKIE_VALUE = "user_0123abc+/=="        # base64-ish, per MFL docs
COOKIE = f"MFL_USER_ID={COOKIE_VALUE}"

MY_LEAGUES = [
    {"league_id": "10005", "name": "Masters Copper Dynasty League",
     "host": "www48.myfantasyleague.com", "franchise_id": "0001",
     "franchise_name": "Team One"},
    {"league_id": "20007", "name": "Second Dynasty League",
     "host": "www45.myfantasyleague.com", "franchise_id": "0002",
     "franchise_name": "Deuce"},
]


def _bundle():
    with open(BUNDLE_FIXTURE) as f:
        return json.load(f)


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "mfl-auth-sess-tok"
    sess = {"verified": True, "user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    xwalk = es.load_crosswalk(XWALK_FIXTURE)
    bundle = _bundle()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k == "mfl.auth_link"), \
         patch.object(es, "get_crosswalk", lambda _opener=None: xwalk), \
         patch.object(mfl, "resolve_host",
                      lambda *a, **kw: "www48.myfantasyleague.com"), \
         patch.object(mfl, "login",
                      lambda u, p, y, **kw: {"cookie": COOKIE,
                                             "mfl_user_id": COOKIE_VALUE}), \
         patch.object(mfl, "fetch_my_leagues",
                      lambda cookie, year, **kw: copy.deepcopy(MY_LEAGUES)), \
         patch.object(mfl, "fetch_league_bundle",
                      lambda *a, **kw: copy.deepcopy(bundle)):
        with server._sessions_lock:
            server._sessions[token] = sess
        # POST auth-link shares the platform sign-in's in-process D7 limiter
        # (feat/mfl-auth-link-throttle): start and end every test clean.
        server._reset_signin_limiter()
        try:
            yield c, token, engine, sess
        finally:
            server._reset_signin_limiter()
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _auth_link(c, token, **extra):
    body = {"username": "mattm", "password": PASSWORD, "year": 2026, **extra}
    return c.post("/api/mfl/auth-link", headers=_h(token), data=json.dumps(body))


def _auth_import(c, token, **extra):
    return c.post("/api/mfl/auth-import", headers=_h(token),
                  data=json.dumps({"year": 2026, **extra}))


# ── auth-link ────────────────────────────────────────────────────────────────

def test_routes_404_when_flag_off(client):
    c, token, _, _ = client
    with patch.object(server, "is_enabled", lambda k: False):
        assert _auth_link(c, token).status_code == 404
        assert _auth_import(c, token).status_code == 404


def test_auth_link_missing_credentials_400(client):
    c, token, _, _ = client
    r = _auth_link(c, token, password="")
    assert r.status_code == 400
    assert r.get_json()["error"] == "mfl_missing_credentials"


def test_auth_link_bad_credentials_403(client):
    c, token, engine, _ = client

    def _reject(u, p, y, **kw):
        raise mfl.MflAuthError("MFL rejected the username/password")

    with patch.object(mfl, "login", _reject):
        r = _auth_link(c, token)
    assert r.status_code == 403
    assert r.get_json()["error"] == "mfl_bad_credentials"
    with engine.connect() as conn:
        assert conn.execute(select(db_module.mfl_credentials_table)).fetchall() == []


def test_auth_link_lists_leagues_and_stores_encrypted_cookie(client):
    c, token, engine, sess = client
    r = _auth_link(c, token)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["storage"] == "encrypted"
    assert [lg["league_id"] for lg in body["leagues"]] == ["10005", "20007"]
    assert body["leagues"][0]["franchise_id"] == "0001"
    # cookie never appears in the response
    assert COOKIE_VALUE not in r.get_data(as_text=True)

    with engine.connect() as conn:
        row = conn.execute(select(db_module.mfl_credentials_table)).fetchone()._mapping
    assert row["user_id"] == USER
    assert row["mfl_username"] == "mattm"
    assert row["year"] == 2026
    # encrypted at rest: ciphertext, not the cookie — and it round-trips
    assert row["cookie_encrypted"] != COOKIE
    assert COOKIE_VALUE not in row["cookie_encrypted"]
    assert sw.decrypt_token(row["cookie_encrypted"]) == COOKIE
    # encrypted path leaves nothing in the in-memory session
    assert "mfl_cookie" not in sess


def test_auth_link_never_logs_or_persists_the_password(client, caplog):
    c, token, engine, _ = client
    with caplog.at_level(logging.DEBUG):
        r = _auth_link(c, token)
    assert r.status_code == 200
    assert PASSWORD not in caplog.text
    with engine.connect() as conn:
        row = conn.execute(select(db_module.mfl_credentials_table)).fetchone()._mapping
    assert PASSWORD not in json.dumps({k: str(v) for k, v in row.items()})


def test_auth_link_without_key_falls_back_to_session_only(client, monkeypatch):
    c, token, engine, sess = client
    monkeypatch.delenv("SLEEPER_TOKEN_KEY", raising=False)
    r = _auth_link(c, token)
    assert r.status_code == 200
    assert r.get_json()["storage"] == "session"
    with engine.connect() as conn:
        assert conn.execute(select(db_module.mfl_credentials_table)).fetchall() == []
    assert sess["mfl_cookie"] == COOKIE
    # …and the session-only cookie still powers an import
    r2 = _auth_import(c, token)
    assert r2.status_code == 200
    assert len(r2.get_json()["imported"]) == 2


# ── Platform linking requires an already verified account owner ──────────
# MFL credentials alone do not prove control of the claimed app identity.
# Successful linking records its platform marker without granting a claimant
# access to somebody else's private state.

def test_auth_link_verified_owner_persists_platform_marker(client):
    from backend import accounts
    c, token, engine, sess = client
    assert sess.get("verified")
    r = _auth_link(c, token)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["verified"] is True
    assert sess.get("verified") is True
    assert sess.get("verified_via") == "mfl_login"
    # persisted controller marker (first-verified-wins applies from here)
    assert accounts.get_user_verified_via(USER) == "mfl_login"


def test_auth_link_bad_credentials_do_not_verify(client):
    from backend import accounts
    c, token, _, sess = client

    def _reject(u, p, y, **kw):
        raise mfl.MflAuthError("MFL rejected the username/password")

    with patch.object(mfl, "login", _reject):
        r = _auth_link(c, token)
    assert r.status_code == 403
    assert sess.get("verified")  # A failed platform login cannot revoke account proof.
    assert accounts.get_user_verified_via(USER) is None


def test_auth_link_verification_grants_long_expiry_durable_row(client):
    """D-018: the 90d rolling expiry is verified-only and rides the durable
    sessions row. MFL verification must not half-set it — with the
    persistent-sessions flag on, a successful auth-link persists the row
    (verified_via='mfl_login') and that row reads back unexpired."""
    c, token, engine, sess = client
    with patch.object(server, "is_enabled",
                      lambda k: k in ("mfl.auth_link", "auth.persistent_sessions")):
        r = _auth_link(c, token)
    assert r.status_code == 200, r.get_data(as_text=True)
    # the session became persist-eligible the moment it verified…
    assert server._session_persist_eligible(sess) is True
    # …and the durable row actually exists, carries the marker, and is not
    # expired under the 90d rolling read-time check.
    row = db_module.load_persisted_session(token)
    assert row is not None
    assert row["user_id"] == USER
    assert row["verified_via"] == "mfl_login"
    assert server._persisted_row_expired(row) is False


# ── D7 limiter on the password login (feat/mfl-auth-link-throttle) ──────────
# POST auth-link used to be an unthrottled MFL password oracle for any
# verified session. It now shares the platform sign-in's windows: per subject
# (accounts.platform_subject("mfl", username) — lower-cased) and per client
# IP, counting only MFL bad logins, admission (failures + in-flight) checked
# BEFORE the MFL call, a good login clearing the subject.

TOO_MANY = "Too many sign-in attempts. Try again in a few minutes."  # row 13


def _counting_login(calls):
    def login(u, p, y, **kw):
        calls.append(u)
        if p != PASSWORD:
            raise mfl.MflAuthError("MFL rejected the username/password")
        return {"cookie": COOKIE, "mfl_user_id": COOKIE_VALUE}
    return login


def _auth_link_from(c, token, ip, **extra):
    body = {"username": "mattm", "password": PASSWORD, "year": 2026, **extra}
    return c.post("/api/mfl/auth-link",
                  headers={**_h(token), "X-Forwarded-For": ip},
                  data=json.dumps(body))


def test_auth_link_d7_sixth_attempt_after_five_bad_logins_is_429_no_mfl_call(
        client):
    c, token, engine, _ = client
    calls: list = []
    with patch.object(mfl, "login", _counting_login(calls)):
        for i in range(5):   # five bad passwords for one login, from 5 IPs
            r = _auth_link_from(c, token, f"192.0.2.{i}", password="bad")
            assert r.status_code == 403
            assert r.get_json()["error"] == "mfl_bad_credentials"
        # The RIGHT password now — and in another case: still refused, with
        # no MFL call, so the answer says nothing about the password.
        r = _auth_link_from(c, token, "192.0.2.200", username="MattM")
    assert r.status_code == 429
    assert r.get_json() == {"error": "too_many_attempts", "message": TOO_MANY}
    assert server._SIGNIN_TOO_MANY_MSG == TOO_MANY        # reused, not new copy
    assert 0 < int(r.headers["Retry-After"]) <= server._SIGNIN_SUBJECT_WINDOW_S
    assert len(calls) == 5                                 # none for the 6th
    with engine.connect() as conn:
        assert conn.execute(select(db_module.mfl_credentials_table)).fetchall() == []
    # Other MFL logins are unaffected.
    with patch.object(mfl, "login", _counting_login(calls)):
        assert _auth_link_from(c, token, "192.0.2.201",
                               username="someone-else").status_code == 200


def test_auth_link_d7_shares_the_subject_window_with_platform_sign_in(client):
    """Same subject key as POST /api/entry/platform: 5 bad logins here lock
    the MFL sign-in for that username too (no 5 + 5 budget)."""
    c, token, _, _ = client
    with patch.object(mfl, "login", _counting_login([])):
        for i in range(5):
            assert _auth_link_from(c, token, f"192.0.2.{i}",
                                   password="bad").status_code == 403
    flags = {"landing.platform_options", "mfl.link", "mfl.auth_link"}
    with patch.object(server, "is_enabled", lambda k: k in flags), \
         patch.object(mfl, "login") as login:
        r = c.post("/api/entry/platform",
                   json={"platform": "mfl", "mfl_league_id": "10005",
                         "year": 2026, "franchise_id": "0001",
                         "username": "MATTM", "password": PASSWORD},
                   headers={"X-Forwarded-For": "192.0.2.99"})
    assert r.status_code == 429
    assert r.get_json()["error"] == "too_many_attempts"
    login.assert_not_called()


def test_auth_link_d7_per_ip_window(client, monkeypatch):
    """Distinct usernames from ONE client IP share the IP window (cap
    patched down from 300); the rightmost X-Forwarded-For hop is the key, so
    another client is unaffected."""
    c, token, _, _ = client
    monkeypatch.setattr(server, "_SIGNIN_IP_MAX_FAILURES", 3)
    calls: list = []
    ip = "198.51.100.40"
    with patch.object(mfl, "login", _counting_login(calls)):
        for i in range(3):
            assert _auth_link_from(c, token, ip, username=f"guess{i}",
                                   password="bad").status_code == 403
        r = _auth_link_from(c, token, f"10.0.0.1, {ip}", username="fresh")
        assert r.status_code == 429
        assert r.get_json()["error"] == "too_many_attempts"
        assert "Retry-After" in r.headers
        assert len(calls) == 3
        assert _auth_link_from(c, token, "198.51.100.41",
                               username="fresh").status_code == 200


def test_auth_link_d7_good_login_clears_the_subject_not_the_ip(client):
    c, token, _, _ = client
    ip = "198.51.100.150"
    with patch.object(mfl, "login", _counting_login([])):
        for _ in range(4):
            assert _auth_link_from(c, token, ip,
                                   password="bad").status_code == 403
        assert _auth_link_from(c, token, ip).status_code == 200   # clears
        for _ in range(4):          # would be 429 at the 5th if not cleared
            assert _auth_link_from(c, token, ip,
                                   password="bad").status_code == 403
        assert _auth_link_from(c, token, ip).status_code == 200
    assert len(server._signin_failures["ip:" + ip]) == 8          # IP untouched
    assert server._signin_inflight == {}


def test_auth_link_d7_uncounted_outcomes_never_consume_the_budget(client):
    """An MFL outage and input errors (missing password) aren't the caller's
    credential failure: six of each, then the owner's login still works."""
    c, token, _, _ = client

    def down(u, p, y, **kw):
        raise mfl.MflError("MFL login HTTP 503", kind="http")

    with patch.object(mfl, "login", down):
        for _ in range(6):
            assert _auth_link(c, token).status_code == 502
    for _ in range(6):
        assert _auth_link(c, token, password="").status_code == 400
    assert server._signin_failures == {}
    assert _auth_link(c, token).status_code == 200


def test_auth_link_d7_in_flight_slot_is_released_on_an_exception(client):
    c, token, _, _ = client

    def boom(*a, **kw):
        raise RuntimeError("boom")

    with patch.object(mfl, "login", boom):
        for _ in range(server._SIGNIN_SUBJECT_MAX_FAILURES + 2):
            r = _auth_link(c, token)
            assert r.status_code == 500
            assert r.get_json()["error"] == "internal_error"
    assert server._signin_inflight == {}
    assert server._signin_failures == {}    # an exception isn't counted
    assert _auth_link(c, token).status_code == 200


def test_auth_link_year_out_of_range_is_400_before_any_mfl_call(client):
    """Same 2000..season+1 range as the sign-in, so an odd year can't turn a
    wrong guess into an uncounted upstream error."""
    c, token, _, _ = client
    with patch.object(mfl, "login") as login:
        for year in (1999, server._MFL_DEFAULT_YEAR + 2):
            r = _auth_link(c, token, year=year)
            assert r.status_code == 400
            assert r.get_json()["error"] == "mfl_bad_year"
    login.assert_not_called()
    assert server._signin_failures == {} and server._signin_inflight == {}


@pytest.mark.parametrize("raw_year", ["Infinity", "-Infinity", "1e400"])
def test_auth_link_and_auth_import_non_finite_year_is_400_not_500(client,
                                                                  raw_year):
    """json.loads turns these into ±inf; int(±inf) raises OverflowError,
    which used to escape the year parse as a 500."""
    c, token, _, _ = client
    link_body = ('{"username": "mattm", "password": "%s", "year": %s}'
                 % (PASSWORD, raw_year))
    import_body = '{"year": %s}' % raw_year
    with patch.object(mfl, "login") as login, \
         patch.object(mfl, "fetch_my_leagues") as my_leagues:
        for path, body in (("/api/mfl/auth-link", link_body),
                           ("/api/mfl/auth-import", import_body)):
            r = c.post(path, headers=_h(token), data=body)
            assert r.status_code == 400, (path, r.get_data(as_text=True))
            assert r.get_json() == {"error": "mfl_bad_year",
                                    "message": "year must be numeric"}
    login.assert_not_called()
    my_leagues.assert_not_called()
    assert server._signin_failures == {} and server._signin_inflight == {}


# ── The mfl_login marker block: what it actually does (finding) ──────────────
# Since #279, @_gate_unverified_write 403s unverified sessions before the
# route runs (test_auth_link_unverified_claim_cannot_upgrade_… below), so the
# block's old "a login verifies the session / first-verified-wins" story is
# stale. It is NOT dead code, though: it runs on every successful POST.
# Behaviour is unchanged on feat/mfl-auth-link-throttle; these pin it so a
# future change is a deliberate one.

def test_auth_link_verify_block_restamps_a_verified_sessions_verified_via(
        client):
    from backend import accounts
    c, token, _, sess = client
    server.upsert_user(sleeper_user_id=USER)
    accounts.mark_user_verified(USER, "sleeper")
    sess["verified_via"] = "sleeper"
    r = _auth_link(c, token)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert sess["verified"] is True
    assert sess["verified_via"] == "mfl_login"                  # overwritten
    assert accounts.get_user_verified_via(USER) == "mfl_login"  # overwritten


def test_auth_link_verify_block_runs_for_an_unverified_demo_session(client):
    """The #279 gate exempts synthetic demo sessions, so an UNVERIFIED demo
    session reaches the block and comes out verified via mfl_login (in
    memory; demo sessions are never persisted)."""
    from backend import accounts
    c, _, _, _ = client
    demo_tok, demo_uid = "demo-tok-auth-link", "demo_user_ab12cd34"
    demo = {"user_id": demo_uid, "is_demo": True, "active_format": "1qb_ppr",
            "last_active": 0.0}
    with server._sessions_lock:
        server._sessions[demo_tok] = demo
    try:
        r = _auth_link(c, demo_tok)
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["verified"] is True
        assert demo["verified"] is True
        assert demo["verified_via"] == "mfl_login"
        assert accounts.get_user_verified_via(demo_uid) == "mfl_login"
        assert server._session_persist_eligible(demo) is False
    finally:
        with server._sessions_lock:
            server._sessions.pop(demo_tok, None)


# ── auth-import ──────────────────────────────────────────────────────────────

def test_auth_import_requires_signin(client):
    c, token, _, _ = client
    r = _auth_import(c, token)
    assert r.status_code == 409
    assert r.get_json()["error"] == "mfl_not_connected"


def test_auth_import_defaults_to_all_leagues_with_auto_franchise(client):
    c, token, engine, _ = client
    assert _auth_link(c, token).status_code == 200
    r = _auth_import(c, token)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["requested"] == 2
    assert body["failed"] == []
    assert [lg["league_id"] for lg in body["imported"]] == ["10005", "20007"]
    # franchise auto-bound from myleagues — no choose-team step
    assert body["imported"][0]["my_team_id"] == "0001"
    assert body["imported"][1]["my_team_id"] == "0002"

    with engine.connect() as conn:
        leagues = {row._mapping["sleeper_league_id"]: row._mapping
                   for row in conn.execute(select(db_module.leagues_table))}
        members = conn.execute(select(db_module.league_members_table)).fetchall()
    assert set(leagues) == {"10005", "20007"}
    for lid, my_team in (("10005", "0001"), ("20007", "0002")):
        assert leagues[lid]["platform"] == "mfl"
        assert leagues[lid]["platform_auth"] == "cookie"
        assert leagues[lid]["platform_my_team"] == my_team
        assert leagues[lid]["user_id"] == USER
    # the session user is bound once per league; others are synthetic mfl: ids
    mine = [m for m in members if m.user_id == USER]
    assert len(mine) == 2
    assert all(m.user_id == USER or m.user_id.startswith("mfl:") for m in members)


def test_auth_import_honors_league_ids_subset(client):
    c, token, engine, _ = client
    _auth_link(c, token)
    r = _auth_import(c, token, league_ids=["20007"])
    body = r.get_json()
    assert [lg["league_id"] for lg in body["imported"]] == ["20007"]
    with engine.connect() as conn:
        rows = conn.execute(select(db_module.leagues_table)).fetchall()
    assert [row._mapping["sleeper_league_id"] for row in rows] == ["20007"]


def test_auth_import_unknown_league_fails_that_league_only(client):
    c, token, _, _ = client
    _auth_link(c, token)
    r = _auth_import(c, token, league_ids=["10005", "99999"])
    body = r.get_json()
    assert [lg["league_id"] for lg in body["imported"]] == ["10005"]
    assert body["failed"] == [{"league_id": "99999",
                               "error": "mfl_not_your_league",
                               "message": "MFL doesn't list you in that league."}]


def test_auth_import_missing_franchise_reported_not_fatal(client):
    c, token, _, _ = client
    _auth_link(c, token)
    no_franchise = copy.deepcopy(MY_LEAGUES)
    no_franchise[1]["franchise_id"] = None
    with patch.object(mfl, "fetch_my_leagues",
                      lambda cookie, year, **kw: copy.deepcopy(no_franchise)):
        r = _auth_import(c, token)
    body = r.get_json()
    assert [lg["league_id"] for lg in body["imported"]] == ["10005"]
    assert body["failed"][0]["league_id"] == "20007"
    assert body["failed"][0]["error"] == "mfl_franchise_unknown"


def test_auth_import_fetch_failure_fails_that_league_only(client):
    c, token, _, _ = client
    _auth_link(c, token)
    bundle = _bundle()

    def _flaky(league_id, year, host, cookie=None, **kw):
        if str(league_id) == "20007":
            raise mfl.MflError("MFL HTTP 500", kind="http")
        return copy.deepcopy(bundle)

    with patch.object(mfl, "fetch_league_bundle", _flaky):
        r = _auth_import(c, token)
    body = r.get_json()
    assert [lg["league_id"] for lg in body["imported"]] == ["10005"]
    assert body["failed"][0] == {"league_id": "20007",
                                 "error": "mfl_unavailable",
                                 "message": "Couldn't reach MFL — try again shortly."}


def test_auth_import_expired_cookie_409_and_drops_credential(client):
    c, token, engine, _ = client
    _auth_link(c, token)

    def _expired(cookie, year, **kw):
        raise mfl.MflAuthError()

    with patch.object(mfl, "fetch_my_leagues", _expired):
        r = _auth_import(c, token)
    assert r.status_code == 409
    assert r.get_json()["error"] == "mfl_auth_expired"
    with engine.connect() as conn:
        assert conn.execute(select(db_module.mfl_credentials_table)).fetchall() == []


def test_auth_import_private_league_bundle_gets_cookie(client):
    c, token, _, _ = client
    _auth_link(c, token)
    seen = []
    bundle = _bundle()

    def _capture(league_id, year, host, cookie=None, **kw):
        seen.append(cookie)
        return copy.deepcopy(bundle)

    with patch.object(mfl, "fetch_league_bundle", _capture):
        r = _auth_import(c, token)
    assert r.status_code == 200
    assert seen == [COOKIE, COOKIE]


# ── mfl_service adapters (injected _opener, no network) ──────────────────────

class _Resp:
    def __init__(self, body: str):
        self._body = body

    def read(self):
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_login_posts_credentials_in_body_and_parses_cookie():
    captured = {}

    def opener(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["data"] = req.data.decode("utf-8")
        return _Resp(f'<status MFL_USER_ID="{COOKIE_VALUE}">OK</status>')

    out = mfl.login("mattm", PASSWORD, 2026, _opener=opener)
    assert out == {"cookie": COOKIE, "mfl_user_id": COOKIE_VALUE}
    assert captured["method"] == "POST"
    # password rides in the POST body, never the URL
    assert PASSWORD not in captured["url"]
    assert "PASSWORD=" in captured["data"]


def test_login_error_body_raises_auth_error():
    def opener(req, timeout=None):
        return _Resp("<error>Invalid Password</error>")

    with pytest.raises(mfl.MflAuthError):
        mfl.login("mattm", "wrong", 2026, _opener=opener)


def test_login_requires_credentials():
    with pytest.raises(mfl.MflError):
        mfl.login("", "pw", 2026, _opener=lambda *a, **kw: _Resp("x"))


def test_fetch_my_leagues_parses_and_falls_back_to_url_id():
    payload = {"leagues": {"league": [
        # documented shape: league_id + url + franchise fields
        {"league_id": "10005", "url": "https://www48.myfantasyleague.com/2026/home/10005",
         "name": "League A", "franchise_id": "0001", "franchise_name": "Mine"},
        # id-only-in-URL + MFL's scheme-mangled homeURL
        {"url": "https//www45.myfantasyleague.com/2026/home/20007", "name": "League B"},
    ]}}

    def opener(req, timeout=None):
        assert req.headers.get("Cookie") == COOKIE
        return _Resp(json.dumps(payload))

    out = mfl.fetch_my_leagues(COOKIE, 2026, _opener=opener)
    assert out == [
        {"league_id": "10005", "name": "League A",
         "host": "www48.myfantasyleague.com", "franchise_id": "0001",
         "franchise_name": "Mine"},
        {"league_id": "20007", "name": "League B",
         "host": "www45.myfantasyleague.com", "franchise_id": None,
         "franchise_name": None},
    ]


def test_fetch_my_leagues_error_payload_raises_auth():
    def opener(req, timeout=None):
        return _Resp(json.dumps({"error": "cookie expired"}))

    with pytest.raises(mfl.MflAuthError):
        mfl.fetch_my_leagues(COOKIE, 2026, _opener=opener)


def test_auth_link_unverified_claim_cannot_upgrade_with_unrelated_mfl_login(client):
    """MFL credentials cannot establish ownership of a claimed app identity."""
    c, token, _, sess = client
    sess["verified"] = False
    with patch.object(mfl, "login") as login:
        response = _auth_link(c, token)
    assert response.status_code == 403
    assert response.get_json()["error"] == "verification_required"
    login.assert_not_called()
    assert not sess["verified"]
