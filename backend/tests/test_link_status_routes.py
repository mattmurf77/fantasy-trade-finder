"""Send-auth lazy flow (2026-08-11): link-STATUS reads + the ESPN
credential-only store.

  GET  /api/espn/link      — {connected, expires_at, expired, verified_at},
                             mirroring GET /api/sleeper/link. Never returns
                             cookies. `connected` additionally requires a
                             verified_at stamp (credential-honesty fix,
                             2026-08-12) — an unproven pair reads as false.
  POST /api/espn/link      — credential-only branch: {espn_s2, swid} with NO
                             espn_league_id VERIFIES the pair with one live
                             authenticated fan-profile read (patched here —
                             tests never touch the network), then persists it
                             (encrypted, verified_at stamped) and returns
                             {connected: true, verified: true}. Rejected pair
                             → 403 espn_bad_credentials, NOT stored; ESPN
                             unreachable → 502 espn_unavailable, NOT stored.
  GET  /api/mfl/auth-link  — {connected, mfl_username, year}; also true for
                             the key-less session-only cookie fallback.

Exercised through Flask's test client against an isolated in-memory SQLite
DB with an injected session. ZERO network: the ONE live call the store path
now makes (espn_service.fetch_fan_leagues) is patched in the fixture — an
unpatched call would be a real HTTP request and a test failure by
construction. The GET status paths still make no ESPN call at all (they
must stay cheap: the send button reads them on every send).
"""
import json
import os
import urllib.error
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.espn_service as es
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
    # Default probe: an authenticated fan with zero FFL leagues — a VALID
    # credential (an empty league list is an honest success). Failure-mode
    # tests re-patch this per-test. Never the network.
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags), \
         patch.object(es, "fetch_fan_leagues",
                      lambda espn_s2, swid, timeout=15, _opener=None: []):
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
    db_module.upsert_espn_credential(USER, "{ABCD-1234}", encrypt_token("s2val"),
                                     verified_at="2026-08-12T00:00:00+00:00")
    r = c.get("/api/espn/link", headers=_h(token))
    assert r.status_code == 200
    body = r.get_json()
    assert body["connected"] is True
    assert body["expired"] is False
    assert body["expires_at"] is None
    assert body["verified_at"] == "2026-08-12T00:00:00+00:00"
    # never the cookies themselves
    assert "swid" not in body and "espn_s2" not in body


def test_espn_link_status_swidless_row_is_not_connected(client):
    """A row missing its SWID can't authenticate anything — the propose
    route treats it as espn_not_connected, so the status must agree."""
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_espn_credential(USER, None, encrypt_token("s2val"),
                                     verified_at="2026-08-12T00:00:00+00:00")
    r = c.get("/api/espn/link", headers=_h(token))
    assert r.get_json() == {"connected": False}


def test_espn_link_status_unverified_row_is_not_connected(client):
    """Credential-honesty fix (2026-08-12): a stored pair with no
    verified_at was never proven against ESPN (legacy pre-verification
    rows), so `connected` must NOT claim it works — the client re-runs the
    sign-in flow, which verifies before storing."""
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_espn_credential(USER, "{ABCD-1234}", encrypt_token("s2val"))
    r = c.get("/api/espn/link", headers=_h(token))
    assert r.get_json() == {"connected": False}


def test_espn_link_status_reports_expired_hint(client):
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_espn_credential(USER, "{ABCD-1234}", encrypt_token("s2val"),
                                     expires_hint_at="2020-01-01T00:00:00+00:00",
                                     verified_at="2026-08-12T00:00:00+00:00")
    body = c.get("/api/espn/link", headers=_h(token)).get_json()
    assert body["connected"] is True
    assert body["expired"] is True


# ---------------------------------------------------------------------------
# POST /api/espn/link — credential-only store
# ---------------------------------------------------------------------------

def test_credential_only_store_verifies_then_persists_encrypted_pair(client):
    """Valid cookies: the pair is probed against ESPN (patched fan-profile
    read), stored encrypted with verified_at stamped, and the status read
    agrees. The probe must receive the exact pair the client sent."""
    c, token, engine, _ = client
    s2 = "AEB%2FvS0me%2Bencoded%3Dvalue"
    swid = "{ABCD-1234}"
    probed = []
    with patch.object(es, "fetch_fan_leagues",
                      lambda espn_s2, swid, timeout=15, _opener=None:
                      probed.append((espn_s2, swid)) or []):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": s2, "swid": swid}))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json() == {"connected": True, "stored": "credential",
                            "verified": True}
    assert probed == [(s2, swid)]                  # exactly one live probe

    with engine.connect() as conn:
        row = conn.execute(select(db_module.espn_credentials_table)).fetchone()._mapping
        # credential only — NO league row is created or touched
        assert conn.execute(select(db_module.leagues_table)).fetchall() == []
    assert row["user_id"] == USER
    assert row["swid"] == swid
    assert row["espn_s2_encrypted"] != s2          # never plaintext
    assert row["verified_at"]                      # proof recorded
    from backend.sleeper_write import decrypt_token
    assert decrypt_token(row["espn_s2_encrypted"]) == s2

    # and the status read now agrees
    assert c.get("/api/espn/link", headers=_h(token)).get_json()["connected"] is True


def test_credential_only_store_rejected_pair_is_not_stored(client):
    """Invalid cookies (ESPN 401/403/404 → EspnAuthError): 403
    espn_bad_credentials, NOTHING stored, and the status read still says
    not connected — the user is told sign-in didn't take at sign-in time,
    not at their next trade send."""
    c, token, engine, _ = client

    def _reject(espn_s2, swid, timeout=15, _opener=None):
        raise es.EspnAuthError()

    with patch.object(es, "fetch_fan_leagues", _reject):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": "stale-s2", "swid": "{BAD-1}"}))
    assert r.status_code == 403
    assert r.get_json()["error"] == "espn_bad_credentials"
    with engine.connect() as conn:
        assert conn.execute(select(db_module.espn_credentials_table)).fetchall() == []
    assert c.get("/api/espn/link", headers=_h(token)).get_json() == {"connected": False}


def test_credential_only_store_espn_outage_is_retryable_not_stored(client):
    """ESPN unreachable / 5xx / non-JSON is NOT a credential verdict: a
    distinct retryable 502 espn_unavailable — never espn_bad_credentials —
    and the unproven pair still does not reach the DB."""
    c, token, engine, _ = client

    def _http_5xx(espn_s2, swid, timeout=15, _opener=None):
        raise es.EspnError("ESPN fan API HTTP 503", kind="http")

    def _transport(espn_s2, swid, timeout=15, _opener=None):
        raise urllib.error.URLError("dns failure")   # OSError subclass

    for failure in (_http_5xx, _transport):
        with patch.object(es, "fetch_fan_leagues", failure):
            r = c.post("/api/espn/link", headers=_h(token),
                       data=json.dumps({"espn_s2": "good-s2", "swid": "{OK-1}"}))
        assert r.status_code == 502, r.get_data(as_text=True)
        assert r.get_json()["error"] == "espn_unavailable"
        with engine.connect() as conn:
            assert conn.execute(
                select(db_module.espn_credentials_table)).fetchall() == []
    assert c.get("/api/espn/link", headers=_h(token)).get_json() == {"connected": False}


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

    def _must_not_probe(espn_s2, swid, timeout=15, _opener=None):
        raise AssertionError("no ESPN probe when the pair can't be stored anyway")

    with patch.object(es, "fetch_fan_leagues", _must_not_probe):
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
