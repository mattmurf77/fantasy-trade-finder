"""Tests for GET /api/espn/my-leagues (flag `espn.league_picker`,
2026-08-09 — feedback: "fetch all their ESPN leagues and let them pick,
instead of asking for a league ID").

Exercised through Flask's test client against an isolated in-memory SQLite
DB with an injected session, mirroring test_espn_link_route.py's harness.
Nothing touches the network: `espn_service.fetch_fan_leagues` is patched
directly per-test (this route's own fan-profile shape is UNVERIFIED from any
build session — see docs/integrations/espn.md §1.7 — so these tests pin the
CONTRACT the route promises, not ESPN's real payload).
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

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

    token = "espn-my-leagues-tok"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled",
                     lambda k: k in ("espn.link", "espn.league_picker")):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _store_credential(swid="{ABCD-1234}",
                      espn_s2="AEB%2FvS0me%2Bencoded%3Dvalue"):
    """Seed a stored ESPN credential row directly — the fixture's `with
    patch.object(db_module, "engine", engine)` is already active for the
    whole test body, so this hits the in-memory test DB like any other
    db_module call."""
    from backend.sleeper_write import encrypt_token
    db_module.upsert_espn_credential(USER, swid, encrypt_token(espn_s2))


# ---------------------------------------------------------------------------
# flag gating
# ---------------------------------------------------------------------------

def test_404_when_flag_off(client):
    c, token, _ = client
    with patch.object(server, "is_enabled", lambda k: k == "espn.link"):
        r = c.get("/api/espn/my-leagues", headers=_h(token))
    assert r.status_code == 404
    assert r.get_json()["error"] == "feature_disabled"


def test_404_when_flag_off_even_with_stored_credential(client):
    # espn.league_picker gates the ROUTE, independent of whether cookies
    # happen to be stored — off is off.
    c, token, _ = client
    _store_credential()
    with patch.object(server, "is_enabled", lambda k: k == "espn.link"):
        r = c.get("/api/espn/my-leagues", headers=_h(token))
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# auth / no-credential
# ---------------------------------------------------------------------------

def test_no_stored_credential_returns_espn_auth_required(client):
    c, token, _ = client
    r = c.get("/api/espn/my-leagues", headers=_h(token))
    assert r.status_code == 403
    assert r.get_json()["error"] == "espn_auth_required"


def test_no_session_returns_401(client):
    c, _, _ = client
    r = c.get("/api/espn/my-leagues", headers=_h("bogus-token"))
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# happy path / empty / malformed / ESPN auth failure — mocked fan API
# ---------------------------------------------------------------------------

def test_happy_path_returns_leagues_using_stored_cookies(client):
    c, token, _ = client
    _store_credential()

    captured = {}

    def _fake_fetch(espn_s2, swid, **kw):
        captured["espn_s2"] = espn_s2
        captured["swid"] = swid
        return [
            {"league_id": "987654321", "league_name": "Recorded Shape Dynasty",
             "season": 2026, "team_name": "The Dynasty Dominators"},
        ]

    with patch.object(es, "fetch_fan_leagues", _fake_fetch):
        r = c.get("/api/espn/my-leagues", headers=_h(token))
    assert r.status_code == 200
    body = r.get_json()
    assert body == {"leagues": [
        {"league_id": "987654321", "league_name": "Recorded Shape Dynasty",
         "season": 2026, "team_name": "The Dynasty Dominators"},
    ]}
    # The route decrypted the STORED credential and passed it straight
    # through — never re-derives or mutates the cookie values.
    assert captured["espn_s2"] == "AEB%2FvS0me%2Bencoded%3Dvalue"
    assert captured["swid"] == "{ABCD-1234}"


def test_empty_account_returns_empty_list_not_an_error(client):
    c, token, _ = client
    _store_credential()
    with patch.object(es, "fetch_fan_leagues", lambda *a, **kw: []):
        r = c.get("/api/espn/my-leagues", headers=_h(token))
    assert r.status_code == 200
    assert r.get_json() == {"leagues": []}


def test_espn_rejects_stored_cookies_maps_to_auth_required(client):
    c, token, _ = client
    _store_credential()

    def _raise(*a, **kw):
        raise es.EspnAuthError()

    with patch.object(es, "fetch_fan_leagues", _raise):
        r = c.get("/api/espn/my-leagues", headers=_h(token))
    assert r.status_code == 403
    assert r.get_json()["error"] == "espn_auth_required"


def test_malformed_fan_api_shape_never_500s(client):
    # A genuine HTTP-layer JSON parse failure inside fetch_fan_leagues
    # (EspnError kind='parse') must degrade to the existing 502 mapping —
    # never an uncaught 500. Shape drift WITHIN valid JSON is covered at the
    # service layer (test_espn_service.py's
    # test_parse_fan_leagues_shape_drift_never_raises) and never reaches
    # this route as an exception at all — it comes back as an empty/partial
    # list, exercised by test_empty_account_returns_empty_list_not_an_error.
    c, token, _ = client
    _store_credential()

    def _raise(*a, **kw):
        raise es.EspnError("ESPN fan API returned non-JSON", kind="parse")

    with patch.object(es, "fetch_fan_leagues", _raise):
        r = c.get("/api/espn/my-leagues", headers=_h(token))
    assert r.status_code == 502
    assert r.get_json()["error"] == "espn_unavailable"


def test_undecryptable_stored_cookie_returns_espn_unconfigured(client):
    c, token, _ = client
    # Store a credential encrypted under a DIFFERENT key than the one the
    # route will try to decrypt with (simulates a rotated SLEEPER_TOKEN_KEY)
    # — same fail-closed posture as espn_import.
    from cryptography.fernet import Fernet
    wrong_key_ciphertext = Fernet(Fernet.generate_key()).encrypt(b"s2value").decode()
    db_module.upsert_espn_credential(USER, "{ABCD-1234}", wrong_key_ciphertext)
    r = c.get("/api/espn/my-leagues", headers=_h(token))
    assert r.status_code == 503
    assert r.get_json()["error"] == "espn_unconfigured"
