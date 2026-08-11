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
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}

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
        try:
            yield c, token, engine, sess
        finally:
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


# ── auth-link session verification (operator decision 2026-08-11) ────────────
# A successful MFL login counts as a verified session — the MFL analogue of
# the Sleeper-JWT oracle — so MFL-only users can pass the hard-verified
# propose gates. Mirrors test_verified_sessions.py's link assertions.

def test_auth_link_success_verifies_session_and_persists_marker(client):
    from backend import accounts
    c, token, engine, sess = client
    assert not sess.get("verified")
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
    assert not sess.get("verified")
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
