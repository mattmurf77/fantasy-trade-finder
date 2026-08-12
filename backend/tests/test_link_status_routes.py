"""Send-auth lazy flow (2026-08-11): link-STATUS reads + the ESPN
credential-only store.

  GET  /api/espn/link      — {connected, expires_at, expired}, mirroring
                             GET /api/sleeper/link. Never returns cookies.
  POST /api/espn/link      — NEW credential-only branch: {espn_s2, swid}
                             with NO espn_league_id persists the pair
                             (encrypted) and returns {connected: true}
                             without touching ESPN or any league row.
  GET  /api/mfl/auth-link  — {connected, mfl_username, year}; also true for
                             the key-less session-only cookie fallback.

Exercised through Flask's test client against an isolated in-memory SQLite
DB with an injected session. ZERO network: no ESPN/MFL fetch is patched in
because none of these paths may make one — a fetch attempt would be a real
HTTP call and a test failure by construction (the credential-only store is
deliberately oracle-free; validity is proven by the propose pre-flight).
"""
import json
import os
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.server as server
from backend.database import metadata

USER = "313560442465169408"


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "link-status-sess-tok"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    flags = {"espn.link", "mfl.auth_link"}
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, engine, sess
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


# ---------------------------------------------------------------------------
# GET /api/espn/link — status
# ---------------------------------------------------------------------------

def test_espn_link_status_404_when_flag_off(client):
    c, token, _, _ = client
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.get("/api/espn/link", headers=_h(token))
    assert r.status_code == 404
    assert r.get_json()["error"] == "feature_disabled"


def test_espn_link_status_requires_session():
    c = server.app.test_client()
    with patch.object(server, "is_enabled", lambda k: k == "espn.link"):
        r = c.get("/api/espn/link")
    assert r.status_code == 401


def test_espn_link_status_not_connected(client):
    c, token, _, _ = client
    r = c.get("/api/espn/link", headers=_h(token))
    assert r.status_code == 200
    assert r.get_json() == {"connected": False}


def test_espn_link_status_connected_after_store(client):
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_espn_credential(USER, "{ABCD-1234}", encrypt_token("s2val"))
    r = c.get("/api/espn/link", headers=_h(token))
    assert r.status_code == 200
    body = r.get_json()
    assert body["connected"] is True
    assert body["expired"] is False
    assert body["expires_at"] is None
    # never the cookies themselves
    assert "swid" not in body and "espn_s2" not in body


def test_espn_link_status_swidless_row_is_not_connected(client):
    """A row missing its SWID can't authenticate anything — the propose
    route treats it as espn_not_connected, so the status must agree."""
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_espn_credential(USER, None, encrypt_token("s2val"))
    r = c.get("/api/espn/link", headers=_h(token))
    assert r.get_json() == {"connected": False}


def test_espn_link_status_reports_expired_hint(client):
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_espn_credential(USER, "{ABCD-1234}", encrypt_token("s2val"),
                                     expires_hint_at="2020-01-01T00:00:00+00:00")
    body = c.get("/api/espn/link", headers=_h(token)).get_json()
    assert body["connected"] is True
    assert body["expired"] is True


# ---------------------------------------------------------------------------
# POST /api/espn/link — credential-only store
# ---------------------------------------------------------------------------

def test_credential_only_store_persists_encrypted_pair(client):
    c, token, engine, _ = client
    s2 = "AEB%2FvS0me%2Bencoded%3Dvalue"
    swid = "{ABCD-1234}"
    r = c.post("/api/espn/link", headers=_h(token),
               data=json.dumps({"espn_s2": s2, "swid": swid}))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json() == {"connected": True, "stored": "credential"}

    with engine.connect() as conn:
        row = conn.execute(select(db_module.espn_credentials_table)).fetchone()._mapping
        # credential only — NO league row is created or touched
        assert conn.execute(select(db_module.leagues_table)).fetchall() == []
    assert row["user_id"] == USER
    assert row["swid"] == swid
    assert row["espn_s2_encrypted"] != s2          # never plaintext
    from backend.sleeper_write import decrypt_token
    assert decrypt_token(row["espn_s2_encrypted"]) == s2

    # and the status read now agrees
    assert c.get("/api/espn/link", headers=_h(token)).get_json()["connected"] is True


def test_credential_only_store_needs_both_cookies(client):
    c, token, _, _ = client
    r = c.post("/api/espn/link", headers=_h(token),
               data=json.dumps({"espn_s2": "only-half"}))
    assert r.status_code == 400
    assert r.get_json()["error"] == "espn_cookies_incomplete"


def test_post_without_cookies_still_requires_league_id(client):
    """The pre-existing contract survives the new branch: a cookie-less POST
    with no/invalid league id keeps 400ing espn_bad_league_id."""
    c, token, _, _ = client
    r = c.post("/api/espn/link", headers=_h(token), data=json.dumps({}))
    assert r.status_code == 400
    assert r.get_json()["error"] == "espn_bad_league_id"
    r = c.post("/api/espn/link", headers=_h(token),
               data=json.dumps({"espn_league_id": "not-numeric"}))
    assert r.status_code == 400
    assert r.get_json()["error"] == "espn_bad_league_id"


def test_credential_only_store_503s_without_encryption_key(client, monkeypatch):
    monkeypatch.delenv("SLEEPER_TOKEN_KEY", raising=False)
    c, token, engine, _ = client
    r = c.post("/api/espn/link", headers=_h(token),
               data=json.dumps({"espn_s2": "s2", "swid": "{X}"}))
    assert r.status_code == 503
    assert r.get_json()["error"] == "espn_unconfigured"
    with engine.connect() as conn:
        assert conn.execute(select(db_module.espn_credentials_table)).fetchall() == []


# ---------------------------------------------------------------------------
# GET /api/mfl/auth-link — status
# ---------------------------------------------------------------------------

def test_mfl_status_404_when_flag_off(client):
    c, token, _, _ = client
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.get("/api/mfl/auth-link", headers=_h(token))
    assert r.status_code == 404
    assert r.get_json()["error"] == "feature_disabled"


def test_mfl_status_not_connected(client):
    c, token, _, _ = client
    r = c.get("/api/mfl/auth-link", headers=_h(token))
    assert r.status_code == 200
    assert r.get_json() == {"connected": False}


def test_mfl_status_connected_from_credential_row(client):
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_mfl_credential(USER, "mfluser", encrypt_token("MFL_USER_ID=abc"), 2026)
    r = c.get("/api/mfl/auth-link", headers=_h(token))
    body = r.get_json()
    assert body["connected"] is True
    assert body["mfl_username"] == "mfluser"
    assert body["year"] == 2026
    assert "cookie" not in json.dumps(body).lower() or "cookie_encrypted" not in body


def test_mfl_status_connected_from_session_only_cookie(client):
    """Key-less deployments store the cookie in the in-memory session only —
    the status read must see that fallback too."""
    c, token, _, sess = client
    sess["mfl_cookie"] = "MFL_USER_ID=session-only"
    r = c.get("/api/mfl/auth-link", headers=_h(token))
    body = r.get_json()
    assert body["connected"] is True
    assert body["mfl_username"] is None
    assert body["year"] is None
