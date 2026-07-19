"""POST /api/session/init fail-fast guard (mobile-testing S2 drill).

An authenticated request (X-Session-Token present) whose body omits
`user_id` used to silently default to DEMO_USER_ID and build a session
with an empty user_roster — which only surfaced much later as "session
missing required state for trade gen". The route now returns 400
{"error": "missing_user_id"} immediately.

The demo flow must keep working unchanged:
  - tokenless /api/session/init (first init / web demo) still defaults
    to DEMO_USER_ID and proceeds past the guard
  - /api/session/demo still bootstraps a seeded demo session

Requests that legitimately pass the guard are stopped one line later by
patching _load_sleeper_cache to return None ("Player database not
cached" 400), so the tests distinguish "guard fired" from "guard passed"
without building the full universal player pool.
"""
import json
from unittest.mock import patch

import pytest

import backend.server as server


CACHE_MISS_ERROR = "Player database not cached"


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


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
# Guard passes: token + user_id, or no token at all (demo / first init).
# _load_sleeper_cache is patched to None so the request stops at the very
# next check instead of building real session state.
# ---------------------------------------------------------------------------

def test_token_with_user_id_passes_guard(client):
    with patch.object(server, "_load_sleeper_cache", return_value=None):
        resp = _post_init(client, {"user_id": "sleeper_123"},
                          token="some-token")

    assert resp.status_code == 400
    assert CACHE_MISS_ERROR in resp.get_json()["error"]


def test_tokenless_demo_init_passes_guard(client):
    # No token, no user_id — the web demo / first-init path. Must NOT be
    # rejected as missing_user_id; it defaults to DEMO_USER_ID as before.
    with patch.object(server, "_load_sleeper_cache", return_value=None):
        resp = _post_init(client, {})

    assert resp.status_code == 400
    assert CACHE_MISS_ERROR in resp.get_json()["error"]


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
