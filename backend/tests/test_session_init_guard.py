"""Init requires a verified existing token; demo bootstrap is separate.

A verified request must provide user_id. Accepted account-only requests
reach the player-cache guard without any upstream or real database access.
"""
import json
from unittest.mock import patch

import pytest

import backend.server as server
import backend.database as db
from sqlalchemy import create_engine


CACHE_MISS_ERROR = "Player database not cached"


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    server.app.config["TESTING"] = True
    with server._sessions_lock:
        server._sessions["some-token"] = {
            "user_id": "sleeper_123", "verified": True, "account_only": True}
    try:
        yield server.app.test_client()
    finally:
        with server._sessions_lock:
            server._sessions.pop("some-token", None)
        engine.dispose()


def _post_init(client, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Session-Token"] = token
    return client.post("/api/session/init", headers=headers,
                       data=json.dumps(body))


# ---------------------------------------------------------------------------
# Guard fires: token present, user_id absent (or empty) → 400 missing_user_id
# ---------------------------------------------------------------------------

def test_token_without_user_id_fails_fast(client):
    resp = _post_init(client, {"league_id": "lg1"}, token="some-token")

    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert resp.get_json()["error"] == "missing_user_id"


def test_token_with_empty_user_id_fails_fast(client):
    resp = _post_init(client, {"user_id": "", "league_id": "lg1"},
                      token="some-token")

    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert resp.get_json()["error"] == "missing_user_id"


# ---------------------------------------------------------------------------
# Verified identity plus account-only league reaches the pool guard.
# Tokenless init is rejected; the dedicated demo route remains available.
# ---------------------------------------------------------------------------

def test_token_with_user_id_passes_guard(client):
    with patch.object(server, "_load_sleeper_cache", return_value=None):
        resp = _post_init(client, {"user_id": "sleeper_123", "league_id": "no_league"},
                          token="some-token")

    assert resp.status_code == 400
    assert CACHE_MISS_ERROR in resp.get_json()["error"]


def test_tokenless_init_is_rejected(client):
    with patch.object(server, "_load_sleeper_cache",
                      side_effect=AssertionError("pool must not be reached")):
        resp = _post_init(client, {})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "session_expired"


# ---------------------------------------------------------------------------
# /api/session/demo bootstrap is untouched by the guard.
# ---------------------------------------------------------------------------

def test_session_demo_still_works(client):
    with patch.object(server, "is_enabled",
                      lambda flag: flag == "landing.try_before_sync"):
        resp = client.post("/api/session/demo")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["demo"] is True
    assert body["token"]
    assert body["user_roster"]

    # Drop the session the bootstrap registered so tests stay isolated.
    with server._sessions_lock:
        server._sessions.pop(body["token"], None)
