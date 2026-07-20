"""Teardown 06-03 (W2C task 8) — POST /api/session/signout.

Client sign-out previously only cleared device storage; the server-side
session token stayed live until idle eviction. The route evicts the
calling token. Idempotent, unflagged, never errors (best-effort caller).
"""
from unittest.mock import patch

import pytest

import backend.server as server

TOKEN = "sess-signout-test"


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with patch.object(server, "is_enabled", lambda k: False):
        with server._sessions_lock:
            server._sessions[TOKEN] = {"user_id": "u1", "last_active": 0.0}
        try:
            yield c
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


def test_signout_evicts_the_calling_token(client):
    r = client.post("/api/session/signout",
                    headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "evicted": True}
    with server._sessions_lock:
        assert TOKEN not in server._sessions


def test_signout_is_idempotent_and_tolerates_unknown_tokens(client):
    r = client.post("/api/session/signout",
                    headers={"X-Session-Token": TOKEN})
    assert r.get_json()["evicted"] is True
    r = client.post("/api/session/signout",
                    headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "evicted": False}


def test_signout_without_token_is_a_safe_no_op(client):
    r = client.post("/api/session/signout")
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "evicted": False}
    with server._sessions_lock:
        assert TOKEN in server._sessions  # untouched
