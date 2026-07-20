"""Teardown 06-02 — data export (`account.data_export`) + SIWA revocation,
and the 01-nav PRD-03 AASA route.

Covers:
  1. GET /api/account/export — 404 dark; demo 400; verified-user step-up
     403; happy path returns the deletion-matrix table set with the user's
     rows and never the Sleeper token ciphertext.
  2. DELETE /api/account — best-effort Apple revocation is attempted when
     an Apple identity is linked, passes the client's fresh authorization
     code through, and never blocks deletion.
  3. accounts.revoke_apple_tokens / _apple_client_secret — env-key guard,
     exchange→revoke flow against a mocked Apple endpoint.
  4. /.well-known/apple-app-site-association — JSON, right appID, declared
     paths, no redirect.

Isolation pattern mirrors test_verified_sessions.py.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert

import backend.accounts as accounts
import backend.database as db_module
import backend.server as server
from backend.database import metadata

UID = "313560442465169408"


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "sess-export-tok"
    sess = {"user_id": UID, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    flags_on: set = set()
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags_on), \
         patch.object(server, "touch_user_activity", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, flags_on
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


# ---------------------------------------------------------------------------
# 1. GET /api/account/export
# ---------------------------------------------------------------------------

def test_export_404_while_dark(client):
    c, token, _ = client
    assert c.get("/api/account/export", headers=_h(token)).status_code == 404


def test_export_requires_session(client):
    c, _, flags_on = client
    flags_on.add("account.data_export")
    assert c.get("/api/account/export").status_code == 401


def test_export_demo_blocked(client):
    c, _, flags_on = client
    flags_on.add("account.data_export")
    demo_token = "sess-export-demo"
    with server._sessions_lock:
        server._sessions[demo_token] = {"user_id": "demo_user_1",
                                        "active_format": "1qb_ppr",
                                        "last_active": 0.0}
    try:
        r = c.get("/api/account/export", headers=_h(demo_token))
    finally:
        with server._sessions_lock:
            server._sessions.pop(demo_token, None)
    assert r.status_code == 400
    assert r.get_json()["error"] == "demo_session"


def test_export_verified_user_requires_verified_session(client):
    c, token, flags_on = client
    flags_on.add("account.data_export")
    db_module.upsert_user(sleeper_user_id=UID)
    accounts.mark_user_verified(UID, "sleeper")
    r = c.get("/api/account/export", headers=_h(token))
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"


def test_export_happy_path_matches_deletion_matrix(client):
    c, token, flags_on = client
    flags_on.add("account.data_export")

    # Seed user-keyed rows across representative matrix tables.
    db_module.upsert_user(sleeper_user_id=UID)
    db_module.save_ranking_swipes(user_id=UID, ordered_ids=["1", "2"],
                                  scoring_format="1qb_ppr")
    db_module.upsert_league_preference(
        user_id=UID, league_id="lg1", team_outlook="contender",
        acquire_positions=["WR"], trade_away_positions=[],
    )
    db_module.upsert_notification_prefs(UID, tz="America/Los_Angeles")
    with db_module.engine.begin() as conn:
        conn.execute(insert(db_module.sleeper_credentials_table).values(
            user_id=UID, sleeper_user_id=UID, token_encrypted="CIPHERTEXT",
            created_at="2026-01-01", updated_at="2026-01-01",
        ))
        conn.execute(insert(db_module.trade_matches_table).values(
            league_id="lg1", user_a_id="other_uid", user_b_id=UID,
            user_a_give="[]", user_a_receive="[]", status="pending",
        ))

    r = c.get("/api/account/export", headers=_h(token))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert "attachment" in r.headers.get("Content-Disposition", "")
    archive = r.get_json()
    assert archive["user_id"] == UID and archive["export_version"] == 1

    tables = archive["tables"]
    # Every deletion-matrix table key is present in the archive.
    expected = {
        "users", "swipe_decisions", "trade_decisions", "member_rankings",
        "elo_history", "league_preferences", "asset_preferences",
        "user_player_skips", "notifications", "device_tokens",
        "notification_prefs", "notification_events_log",
        "notification_queue", "user_events", "wrapped_events",
        "sleeper_credentials", "league_members", "leagues",
        "bad_trade_flags", "trade_impressions", "app_feedback",
        "trade_matches", "accounts", "linked_identities",
    }
    assert expected <= set(tables.keys())

    assert len(tables["users"]) == 1
    assert len(tables["swipe_decisions"]) == 1
    assert tables["league_preferences"][0]["team_outlook"] == "contender"
    assert tables["notification_prefs"][0]["tz"] == "America/Los_Angeles"
    assert len(tables["trade_matches"]) == 1        # user_b side included
    # Encrypted Sleeper credential is never exported.
    assert len(tables["sleeper_credentials"]) == 1
    assert "token_encrypted" not in tables["sleeper_credentials"][0]


# ---------------------------------------------------------------------------
# 2 + 3. Apple revocation on deletion
# ---------------------------------------------------------------------------

def _link_apple_account():
    acct = accounts.find_or_create_account("apple", "apple-sub-123")
    accounts.bind_sleeper_user(acct["account_id"], UID)
    return acct["account_id"]


def test_has_apple_identity(client):
    assert accounts.has_apple_identity(UID) is False
    _link_apple_account()
    assert accounts.has_apple_identity(UID) is True


def test_revoke_skipped_without_env_keys(client, monkeypatch):
    for k in ("APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_PRIVATE_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert accounts.revoke_apple_tokens("some-code") is False


def test_revoke_exchange_and_revoke_flow(client, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    monkeypatch.setenv("APPLE_TEAM_ID", "N5Y4N2Q49A")
    monkeypatch.setenv("APPLE_KEY_ID", "KEYID12345")
    monkeypatch.setenv("APPLE_PRIVATE_KEY", pem)

    posts = []
    def fake_post(url, fields):
        posts.append((url, fields))
        if url == accounts.APPLE_TOKEN_URL:
            return 200, {"refresh_token": "rt-1"}
        return 200, {}

    with patch.object(accounts, "_apple_form_post", side_effect=fake_post):
        assert accounts.revoke_apple_tokens("auth-code-1") is True

    assert posts[0][0] == accounts.APPLE_TOKEN_URL
    assert posts[0][1]["code"] == "auth-code-1"
    assert posts[0][1]["client_id"] == accounts.APPLE_AUDIENCE
    assert posts[1][0] == accounts.APPLE_REVOKE_URL
    assert posts[1][1]["token"] == "rt-1"
    assert posts[1][1]["token_type_hint"] == "refresh_token"

    # No code → no network calls, False.
    posts.clear()
    with patch.object(accounts, "_apple_form_post", side_effect=fake_post):
        assert accounts.revoke_apple_tokens(None) is False
    assert posts == []


def test_delete_attempts_revocation_and_never_blocks(client):
    c, token, _ = client
    db_module.upsert_user(sleeper_user_id=UID)
    _link_apple_account()

    with patch.object(accounts, "revoke_apple_tokens",
                      MagicMock(return_value=False)) as revoke:
        r = c.delete("/api/account", headers=_h(token),
                     data=json.dumps({"apple_authorization_code": "code-9"}))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True and body["apple_revoked"] is False
    revoke.assert_called_once_with("code-9")
    # Local deletion completed regardless of the failed revoke.
    assert body["deleted"]["users_deleted"] == 1
    assert body["deleted"]["linked_identities_deleted"] == 1


def test_delete_without_apple_identity_skips_revocation(client):
    c, token, _ = client
    db_module.upsert_user(sleeper_user_id=UID)
    with patch.object(accounts, "revoke_apple_tokens", MagicMock()) as revoke:
        r = c.delete("/api/account", headers=_h(token))
    assert r.status_code == 200
    revoke.assert_not_called()


# ---------------------------------------------------------------------------
# 4. AASA route
# ---------------------------------------------------------------------------

def test_aasa_served_as_json_with_app_id(client, monkeypatch):
    c, _, _ = client
    monkeypatch.delenv("APPLE_TEAM_ID", raising=False)
    r = c.get("/.well-known/apple-app-site-association")
    assert r.status_code == 200                      # direct 200, no redirect
    assert r.content_type.startswith("application/json")
    body = r.get_json()
    detail = body["applinks"]["details"][0]
    assert detail["appID"] == "N5Y4N2Q49A.com.fantasytradefinder.app"
    assert detail["appIDs"] == ["N5Y4N2Q49A.com.fantasytradefinder.app"]
    assert {"/": "/u/*"} in detail["components"]
    assert {"/": "/s/*"} in detail["components"]
    assert {"/": "/", "?": {"ref": "?*"}} in detail["components"]
    assert detail["paths"] == ["/u/*", "/s/*"]


def test_aasa_team_id_env_override(client, monkeypatch):
    c, _, _ = client
    monkeypatch.setenv("APPLE_TEAM_ID", "OTHERTEAM1")
    r = c.get("/.well-known/apple-app-site-association")
    assert r.get_json()["applinks"]["details"][0]["appID"] == \
        "OTHERTEAM1.com.fantasytradefinder.app"
