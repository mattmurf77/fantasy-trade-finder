"""Teardown 06-04 (W2C task 3) — per-user public-profile opt-in.

`profiles.public_pages` is a single global flag; flipping it used to
publish EVERY user's tiers by enumerable username. With
`profiles.user_toggle` on, /u/<username> and /api/profile/<username> now
also require the user's own `users.profile_public` opt-in (default
private), and the session user manages it via GET/PUT
/api/profile/visibility.

Isolation pattern mirrors test_league_prefs_authz.py: Flask test client,
in-memory SQLite, injected sessions, no network.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata

USER_A = "555555555555555555"
UNAME_A = "vis_alice"
TOKEN = "sess-profile-vis"


def _h():
    return {"X-Session-Token": TOKEN, "Content-Type": "application/json"}


def _mk_sess(user_id, verified=False):
    return {
        "user_id":       user_id,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
        "verified":      verified,
    }


def _flags(*enabled):
    on = set(enabled)
    return lambda k: k in on


@pytest.fixture()
def env():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    c = server.app.test_client()

    db_patch = patch.object(db_module, "engine", engine)
    db_patch.start()
    db_module.upsert_user(sleeper_user_id=USER_A, username=UNAME_A,
                          display_name="Vis Alice")
    with server._sessions_lock:
        server._sessions[TOKEN] = _mk_sess(USER_A)
    try:
        yield c
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
        db_patch.stop()


# ── /api/profile/visibility (session-scoped toggle) ─────────────────────


def test_visibility_route_404_while_dark(env):
    c = env
    with patch.object(server, "is_enabled", _flags()):
        assert c.get("/api/profile/visibility", headers=_h()).status_code == 404
        r = c.put("/api/profile/visibility", headers=_h(),
                  data=json.dumps({"public": True}))
        assert r.status_code == 404
    assert db_module.get_profile_public(USER_A) is False


def test_visibility_get_defaults_private_and_put_persists(env):
    c = env
    with patch.object(server, "is_enabled", _flags("profiles.user_toggle")):
        r = c.get("/api/profile/visibility", headers=_h())
        assert r.status_code == 200 and r.get_json() == {"public": False}

        r = c.put("/api/profile/visibility", headers=_h(),
                  data=json.dumps({"public": True}))
        assert r.status_code == 200 and r.get_json() == {"public": True}
        assert db_module.get_profile_public(USER_A) is True

        r = c.get("/api/profile/visibility", headers=_h())
        assert r.get_json() == {"public": True}

        r = c.put("/api/profile/visibility", headers=_h(),
                  data=json.dumps({"public": False}))
        assert r.status_code == 200
        assert db_module.get_profile_public(USER_A) is False


def test_visibility_put_requires_public_key(env):
    c = env
    with patch.object(server, "is_enabled", _flags("profiles.user_toggle")):
        r = c.put("/api/profile/visibility", headers=_h(), data=json.dumps({}))
        assert r.status_code == 400


def test_visibility_put_denied_for_squatter_once_owner_verified(env):
    """Verified-write gate: after the real owner verifies, an unverified
    session can no longer flip the exposure toggle."""
    c = env
    from backend import accounts as accounts_module
    accounts_module.mark_user_verified(USER_A, "sleeper")
    with patch.object(server, "is_enabled", _flags("profiles.user_toggle")):
        r = c.put("/api/profile/visibility", headers=_h(),
                  data=json.dumps({"public": True}))
        assert r.status_code == 403
        assert r.get_json()["error"] == "verification_required"
    assert db_module.get_profile_public(USER_A) is False


# ── Public profile routes honor the opt-in ──────────────────────────────


def test_public_profile_legacy_behavior_when_toggle_flag_off(env):
    """profiles.public_pages alone (user_toggle dark) = pre-teardown
    behavior: profile serves without any per-user opt-in."""
    c = env
    with patch.object(server, "is_enabled", _flags("profiles.public_pages")):
        r = c.get(f"/api/profile/{UNAME_A}")
        assert r.status_code == 200
        assert r.get_json()["username"] == UNAME_A


def test_public_profile_404_without_opt_in(env):
    c = env
    with patch.object(server, "is_enabled",
                      _flags("profiles.public_pages", "profiles.user_toggle")):
        assert c.get(f"/api/profile/{UNAME_A}").status_code == 404
        assert c.get(f"/u/{UNAME_A}").status_code == 404


def test_public_profile_served_after_opt_in(env):
    c = env
    db_module.set_profile_public(USER_A, True)
    with patch.object(server, "is_enabled",
                      _flags("profiles.public_pages", "profiles.user_toggle")):
        r = c.get(f"/api/profile/{UNAME_A}")
        assert r.status_code == 200
        assert r.get_json()["username"] == UNAME_A
        assert c.get(f"/u/{UNAME_A}").status_code == 200


def test_unknown_username_still_404_with_toggle_on(env):
    """Opt-in denial is indistinguishable from not-found (no user
    enumeration through the privacy gate)."""
    c = env
    with patch.object(server, "is_enabled",
                      _flags("profiles.public_pages", "profiles.user_toggle")):
        assert c.get("/api/profile/no_such_user").status_code == 404
