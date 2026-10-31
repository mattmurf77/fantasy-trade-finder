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
    sess = {"verified": True, "user_id": UID, "active_format": "1qb_ppr", "last_active": 0.0}

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
    server._sessions[token]["verified"] = False
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
        for creator, tok in ((UID, "SHARE_TOKEN_MINE_0000000"),
                             ("other_uid", "SHARE_TOKEN_THEIRS_00000")):
            conn.execute(insert(db_module.trade_share_tokens_table).values(
                token=tok, match_id=1, created_by=creator,
                created_at="2026-10-20T00:00:00+00:00",
            ))

    r = c.get("/api/account/export", headers=_h(token))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert "attachment" in r.headers.get("Content-Disposition", "")
    archive = r.get_json()
    assert archive["user_id"] == UID and archive["export_version"] == 2

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
        "trade_matches", "accounts", "linked_identities", "trade_share_tokens",
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
    # Build O8: the user's own trade share links, without the bearer token.
    shares = tables["trade_share_tokens"]
    assert [(s["created_by"], s["match_id"]) for s in shares] == [(UID, 1)]
    assert "token" not in shares[0]
    exported = json.dumps(archive)
    assert "SHARE_TOKEN_MINE" not in exported and "SHARE_TOKEN_THEIRS" not in exported


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
            return 200, {"refresh_token": "rt-1", "id_token": _id_token("apple-sub-123")}
        return 200, {}

    with patch.object(accounts, "_apple_form_post", side_effect=fake_post):
        assert accounts.revoke_apple_tokens(
            "auth-code-1", expected_subjects={"apple-sub-123"}) is True

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


def _id_token(sub):
    """An Apple-shaped id_token (the payload is all the server reads)."""
    import base64

    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{seg({'alg': 'RS256', 'kid': 'k'})}.{seg({'iss': 'https://appleid.apple.com', 'sub': sub})}.sig"


def _apple_env(monkeypatch):
    monkeypatch.setattr(accounts, "_apple_client_secret", lambda: "synthetic-client-secret")


def _apple_server(sub_in_code=None):
    """A fake Apple: /auth/token answers with an id_token for `sub_in_code`
    (or none); /auth/revoke answers 200. Records every call."""
    posts = []

    def fake_post(url, fields):
        posts.append(url)
        if url == accounts.APPLE_TOKEN_URL:
            out = {"refresh_token": "rt-9"}
            if sub_in_code is not None:
                out["id_token"] = _id_token(sub_in_code)
            return 200, out
        return 200, {}
    return posts, fake_post


# release-lead QA on #446 (d): the code's own Apple `sub` must be the one
# this account linked, or a different Apple ID's grant would be revoked.

def test_a_matching_sub_revokes(client, monkeypatch):
    _apple_env(monkeypatch)
    posts, fake = _apple_server("apple-sub-123")
    with patch.object(accounts, "_apple_form_post", side_effect=fake):
        assert accounts.revoke_apple_tokens("code-m", expected_subjects={"apple-sub-123"}) is True
    assert posts == [accounts.APPLE_TOKEN_URL, accounts.APPLE_REVOKE_URL]


@pytest.mark.parametrize("sub_in_code, expected", [
    ("someone-elses-apple-sub", {"apple-sub-123"}),   # another Apple ID on the device
    (None, {"apple-sub-123"}),                        # no id_token in Apple's answer
    ("apple-sub-123", None),                          # no linked subject to match
    ("apple-sub-123", set()),
])
def test_no_revoke_without_a_matching_sub(client, monkeypatch, capsys, sub_in_code, expected):
    _apple_env(monkeypatch)
    posts, fake = _apple_server(sub_in_code)
    with patch.object(accounts, "_apple_form_post", side_effect=fake):
        assert accounts.revoke_apple_tokens("code-x", expected_subjects=expected) is False
    assert accounts.APPLE_REVOKE_URL not in posts
    # The log says which: no id_token, or a different Apple account.
    out = capsys.readouterr().out
    assert ("no usable id_token" in out) == (sub_in_code is None), out


@pytest.mark.parametrize("sub_in_code", ["someone-elses-apple-sub", None])
def test_delete_route_mismatch_or_no_id_token_still_deletes_without_revoking(client, monkeypatch, sub_in_code):
    c, token, _ = client
    db_module.upsert_user(sleeper_user_id=UID)
    _link_apple_account()
    _apple_env(monkeypatch)
    posts, fake = _apple_server(sub_in_code)
    with patch.object(accounts, "_apple_form_post", side_effect=fake):
        r = c.delete("/api/account", headers=_h(token),
                     data=json.dumps({"apple_authorization_code": "code-y"}))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["apple_revoked"] is False
    assert body["deleted"]["users_deleted"] == 1
    assert posts == [accounts.APPLE_TOKEN_URL]          # exchanged, never revoked


def test_delete_route_matching_sub_revokes_then_deletes(client, monkeypatch):
    c, token, _ = client
    db_module.upsert_user(sleeper_user_id=UID)
    _link_apple_account()
    _apple_env(monkeypatch)
    posts, fake = _apple_server("apple-sub-123")
    with patch.object(accounts, "_apple_form_post", side_effect=fake):
        r = c.delete("/api/account", headers=_h(token),
                     data=json.dumps({"apple_authorization_code": "code-z"}))
    assert r.status_code == 200 and r.get_json()["apple_revoked"] is True
    assert r.get_json()["deleted"]["users_deleted"] == 1
    assert posts == [accounts.APPLE_TOKEN_URL, accounts.APPLE_REVOKE_URL]


def test_no_log_line_names_an_apple_sub(client, monkeypatch, capsys):
    _apple_env(monkeypatch)
    posts, fake = _apple_server("someone-elses-apple-sub")
    with patch.object(accounts, "_apple_form_post", side_effect=fake):
        accounts.revoke_apple_tokens("code-l", expected_subjects={"apple-sub-123"})
    out = capsys.readouterr().out
    assert "skipped" in out
    assert "someone-elses-apple-sub" not in out and "apple-sub-123" not in out


def test_each_apple_http_call_times_out_at_5s():
    """release-lead QA on #446: deletion makes up to two Apple calls before it
    deletes, and the app's DELETE gives up at 15 s, so each call is capped at
    5 s (2 x 5 s < 15 s) and a slow Apple can't outlast the client."""
    assert accounts.APPLE_HTTP_TIMEOUT_S == 5
    seen = {}

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout=None, context=None):
        seen["timeout"] = timeout
        return _Resp()

    with patch.object(accounts.urllib.request, "urlopen", side_effect=fake_urlopen):
        assert accounts._apple_form_post(accounts.APPLE_TOKEN_URL, {"code": "c"}) == (200, {})
    assert seen["timeout"] == accounts.APPLE_HTTP_TIMEOUT_S
    assert 2 * accounts.APPLE_HTTP_TIMEOUT_S < 15


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
    revoke.assert_called_once_with("code-9", expected_subjects={"apple-sub-123"})
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
    # Exact contract, in the order the route emits. P0-3 appended the invite
    # JOIN path (/app/league/join/*) — see backend/tests/test_invite_links.py.
    assert detail["paths"] == ["/u/*", "/s/*", "/app/league/join/*"]


def test_aasa_team_id_env_override(client, monkeypatch):
    c, _, _ = client
    monkeypatch.setenv("APPLE_TEAM_ID", "OTHERTEAM1")
    r = c.get("/.well-known/apple-app-site-association")
    assert r.get_json()["applinks"]["details"][0]["appID"] == \
        "OTHERTEAM1.com.fantasytradefinder.app"
