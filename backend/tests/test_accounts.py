"""Tests for the account-auth P2 surface (backend/accounts.py + server routes):

  * Identity-token verification against a mocked JWKS — valid / expired /
    wrong-aud / wrong-iss / bad-signature / unknown-kid, Apple and Google.
  * find_or_create_account + sticky Sleeper binding rules.
  * delete_user_data — row-level assertions per table, including the
    counterparty-safe anonymization of shared rows.
  * Route behavior: auth.accounts flag-off parity (404 everywhere except
    DELETE /api/account, which is App-Store-mandated and always live) and
    the verified-session guard on deletion.

All DB work runs against an isolated in-memory SQLite engine; the only
network call in the module (_fetch_jwks) is monkeypatched.
"""
import base64
import json
import time
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import create_engine, insert, select

import backend.accounts as accounts
import backend.database as db_module
import backend.server as server
from backend.database import metadata

USER = "user_me"
OTHER = "user_other"
LEAGUE = "league_1"


# ---------------------------------------------------------------------------
# JWT / JWKS helpers
# ---------------------------------------------------------------------------

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _make_token(claims: dict, *, kid: str = "k1", key=_KEY, alg: str = "RS256") -> str:
    header = {"alg": alg, "kid": kid}
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
    sig = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(sig)}"


def _jwks(key=_KEY, kid: str = "k1") -> list[dict]:
    pub = key.public_key().public_numbers()
    n = pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big")
    e = pub.e.to_bytes((pub.e.bit_length() + 7) // 8, "big")
    return [{"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256",
             "n": _b64url(n), "e": _b64url(e)}]


def _apple_claims(**over) -> dict:
    claims = {
        "iss": accounts.APPLE_ISSUER,
        "aud": accounts.APPLE_AUDIENCE,
        "sub": "apple-sub-001",
        "exp": int(time.time()) + 600,
    }
    claims.update(over)
    return claims


@pytest.fixture(autouse=True)
def _mock_jwks(monkeypatch):
    """Serve our test JWKS for every provider URL; clear the module cache."""
    monkeypatch.setattr(accounts, "_fetch_jwks", lambda url: _jwks())
    accounts._jwks_cache.clear()
    yield
    accounts._jwks_cache.clear()


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------

def test_apple_token_valid():
    claims = accounts.verify_apple_token(_make_token(_apple_claims()))
    assert claims["sub"] == "apple-sub-001"


def test_apple_token_expired():
    tok = _make_token(_apple_claims(exp=int(time.time()) - 3600))
    with pytest.raises(accounts.TokenVerificationError) as e:
        accounts.verify_apple_token(tok)
    assert e.value.reason == "expired"


def test_apple_token_wrong_audience():
    tok = _make_token(_apple_claims(aud="com.somebody.else"))
    with pytest.raises(accounts.TokenVerificationError) as e:
        accounts.verify_apple_token(tok)
    assert e.value.reason == "wrong_audience"


def test_apple_token_wrong_issuer():
    tok = _make_token(_apple_claims(iss="https://evil.example.com"))
    with pytest.raises(accounts.TokenVerificationError) as e:
        accounts.verify_apple_token(tok)
    assert e.value.reason == "wrong_issuer"


def test_apple_token_bad_signature():
    tok = _make_token(_apple_claims(), key=_OTHER_KEY)  # kid matches, key doesn't
    with pytest.raises(accounts.TokenVerificationError) as e:
        accounts.verify_apple_token(tok)
    assert e.value.reason == "bad_signature"


def test_apple_token_unknown_kid():
    tok = _make_token(_apple_claims(), kid="k-rotated-away")
    with pytest.raises(accounts.TokenVerificationError) as e:
        accounts.verify_apple_token(tok)
    assert e.value.reason == "unknown_kid"


def test_apple_token_rejects_non_rs256():
    tok = _make_token(_apple_claims(), alg="HS256")
    with pytest.raises(accounts.TokenVerificationError) as e:
        accounts.verify_apple_token(tok)
    assert e.value.reason == "bad_alg"


def test_malformed_token():
    with pytest.raises(accounts.TokenVerificationError) as e:
        accounts.verify_apple_token("not-a-jwt")
    assert e.value.reason == "malformed_token"


def test_google_token_valid_and_wrong_audience():
    claims = {"iss": "https://accounts.google.com", "aud": "client-123",
              "sub": "google-sub-9", "exp": int(time.time()) + 600}
    assert accounts.verify_google_token(
        _make_token(claims), "client-123")["sub"] == "google-sub-9"
    with pytest.raises(accounts.TokenVerificationError) as e:
        accounts.verify_google_token(_make_token(claims), "other-client")
    assert e.value.reason == "wrong_audience"


def test_google_token_accepts_bare_issuer():
    claims = {"iss": "accounts.google.com", "aud": "client-123",
              "sub": "g", "exp": int(time.time()) + 600}
    assert accounts.verify_google_token(_make_token(claims), "client-123")["sub"] == "g"


# ---------------------------------------------------------------------------
# find-or-create + binding rules
# ---------------------------------------------------------------------------

def test_find_or_create_and_sticky_binding(engine):
    a1 = accounts.find_or_create_account("apple", "sub-1", "emailhash")
    assert a1["created"] is True and a1["sleeper_user_id"] is None

    a2 = accounts.find_or_create_account("apple", "sub-1")
    assert a2["created"] is False
    assert a2["account_id"] == a1["account_id"]

    # Same sub under a different provider is a DIFFERENT account.
    g = accounts.find_or_create_account("google", "sub-1")
    assert g["account_id"] != a1["account_id"]

    # Unbound → binds.
    bind = accounts.bind_sleeper_user(a1["account_id"], USER)
    assert bind == {"sleeper_user_id": USER, "conflict": False}
    # Same id → idempotent no-op.
    bind = accounts.bind_sleeper_user(a1["account_id"], USER)
    assert bind == {"sleeper_user_id": USER, "conflict": False}
    # Different id → sticky: original binding kept, conflict flagged.
    bind = accounts.bind_sleeper_user(a1["account_id"], OTHER)
    assert bind == {"sleeper_user_id": USER, "conflict": True}

    acct = accounts.get_account_for_user(USER)
    assert acct["account_id"] == a1["account_id"]
    assert acct["identities"] == [
        {"provider": "apple", "linked_at": acct["identities"][0]["linked_at"]}
    ]
    assert accounts.get_account_for_user(OTHER) is None


def test_mark_user_verified(engine):
    with engine.begin() as conn:
        conn.execute(insert(db_module.users_table).values(sleeper_user_id=USER))
    assert accounts.get_user_verified_via(USER) is None
    accounts.mark_user_verified(USER, "apple")
    assert accounts.get_user_verified_via(USER) == "apple"


# ---------------------------------------------------------------------------
# Deletion matrix
# ---------------------------------------------------------------------------

def _seed_deletion_fixture(engine):
    """USER + a counterparty (OTHER) with data in every affected table."""
    d = db_module
    with engine.begin() as conn:
        for uid in (USER, OTHER):
            conn.execute(insert(d.users_table).values(
                sleeper_user_id=uid, username=f"name_{uid}"))
            conn.execute(insert(d.swipe_decisions_table).values(
                user_id=uid, winner_player_id="p1", loser_player_id="p2",
                decision_type="rank", k_factor=32.0))
            conn.execute(insert(d.trade_decisions_table).values(
                user_id=uid, league_id=LEAGUE, give_player_ids="[]",
                receive_player_ids="[]", decision="like"))
            conn.execute(insert(d.member_rankings_table).values(
                user_id=uid, league_id=LEAGUE, player_id="p1", elo=1500.0))
            conn.execute(insert(d.elo_history_table).values(
                user_id=uid, player_id="p1", scoring_format="1qb_ppr",
                elo=1500.0, snapshot_at="2026-07-11"))
            conn.execute(insert(d.user_events_table).values(
                user_id=uid, event_type="login", occurred_at="2026-07-11"))
            conn.execute(insert(d.device_tokens_table).values(
                user_id=uid, device_token=f"tok-{uid}", platform="ios"))
            conn.execute(insert(d.sleeper_credentials_table).values(
                user_id=uid, token_encrypted="ciphertext",
                created_at="2026-07-11", updated_at="2026-07-11"))
            conn.execute(insert(d.league_members_table).values(
                league_id=LEAGUE, user_id=uid))
            conn.execute(insert(d.app_feedback_table).values(
                client_id=f"fb-{uid}", user_id=uid, username=f"name_{uid}",
                screen="Settings", severity="idea", text="note",
                created_at="2026-07-11"))
        conn.execute(insert(d.leagues_table).values(
            sleeper_league_id=LEAGUE, user_id=USER))
        # Shared match: USER is side A, OTHER is side B.
        conn.execute(insert(d.trade_matches_table).values(
            league_id=LEAGUE, user_a_id=USER, user_b_id=OTHER,
            user_a_give='["p1"]', user_a_receive='["p2"]',
            status="accepted", user_a_decision="accept",
            user_b_decision="accept"))
        # USER's own flag + OTHER's flag that targets USER.
        conn.execute(insert(d.bad_trade_flags_table).values(
            dedupe_key=f"{USER}|{LEAGUE}|a|b", user_id=USER, league_id=LEAGUE,
            give_player_ids="[]", receive_player_ids="[]",
            created_at="2026-07-11"))
        conn.execute(insert(d.bad_trade_flags_table).values(
            dedupe_key=f"{OTHER}|{LEAGUE}|a|b", user_id=OTHER, league_id=LEAGUE,
            target_user_id=USER, target_username=f"name_{USER}",
            give_player_ids="[]", receive_player_ids="[]",
            created_at="2026-07-11"))
        # USER's own impression + OTHER's impression targeting USER.
        conn.execute(insert(d.trade_impressions_table).values(
            user_id=USER, league_id=LEAGUE, give_player_ids="[]",
            receive_player_ids="[]"))
        conn.execute(insert(d.trade_impressions_table).values(
            user_id=OTHER, league_id=LEAGUE, target_user_id=USER,
            give_player_ids="[]", receive_player_ids="[]"))
    acct = accounts.find_or_create_account("apple", "del-sub")
    accounts.bind_sleeper_user(acct["account_id"], USER)
    return acct


def test_delete_user_data_matrix(engine):
    d = db_module
    _seed_deletion_fixture(engine)

    counts = accounts.delete_user_data(USER)

    def rows(tbl):
        with engine.connect() as conn:
            return conn.execute(select(tbl)).fetchall()

    # Hard-deleted, own rows only — counterparty rows intact.
    for tbl, name in [
        (d.swipe_decisions_table, "swipe_decisions"),
        (d.trade_decisions_table, "trade_decisions"),
        (d.member_rankings_table, "member_rankings"),
        (d.elo_history_table, "elo_history"),
        (d.user_events_table, "user_events"),
        (d.device_tokens_table, "device_tokens"),
        (d.sleeper_credentials_table, "sleeper_credentials"),
        (d.league_members_table, "league_members"),
    ]:
        remaining = rows(tbl)
        assert all(r.user_id == OTHER for r in remaining), name
        assert len(remaining) == 1, name
        assert counts[f"{name}_deleted"] == 1, name

    # users: only OTHER's record survives.
    remaining_users = rows(d.users_table)
    assert [r.sleeper_user_id for r in remaining_users] == [OTHER]

    # leagues row synced by USER is dropped (recreated from Sleeper's
    # public API by any member's next session_init).
    assert rows(d.leagues_table) == []

    # trade_matches: shared row is KEPT; the deleted side is tombstoned and
    # the counterparty's side + outcome are untouched.
    (match,) = rows(d.trade_matches_table)
    assert match.user_a_id == accounts.DELETED_USER_PLACEHOLDER
    assert match.user_b_id == OTHER
    assert match.status == "accepted"
    assert match.user_b_decision == "accept"
    assert counts["trade_matches_anonymized"] == 1

    # bad_trade_flags: own flag deleted (dedupe_key embeds the user id);
    # the counterparty's flag survives with the target reference cleared.
    (flag,) = rows(d.bad_trade_flags_table)
    assert flag.user_id == OTHER
    assert flag.target_user_id is None and flag.target_username is None

    # trade_impressions: own deck rows deleted; the counterparty's row
    # survives with target_user_id cleared.
    (impression,) = rows(d.trade_impressions_table)
    assert impression.user_id == OTHER
    assert impression.target_user_id is None

    # app_feedback: retained as an anonymous product record.
    fb = {r.client_id: r for r in rows(d.app_feedback_table)}
    assert len(fb) == 2
    assert fb[f"fb-{USER}"].user_id is None and fb[f"fb-{USER}"].username is None
    assert fb[f"fb-{USER}"].text == "note"          # content kept
    assert fb[f"fb-{OTHER}"].user_id == OTHER        # counterparty untouched

    # Identity layer fully removed.
    assert rows(d.accounts_table) == []
    assert rows(d.linked_identities_table) == []
    assert counts["users_deleted"] == 1
    assert counts["accounts_deleted"] == 1
    assert counts["linked_identities_deleted"] == 1


# ---------------------------------------------------------------------------
# Routes — flag gating + session behavior
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(engine):
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    token = "acct-sess-tok"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}
    with server._sessions_lock:
        server._sessions[token] = sess
    try:
        yield c, token, sess
    finally:
        with server._sessions_lock:
            server._sessions.pop(token, None)


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


def test_flag_off_parity(client, engine):
    """auth.accounts off → sign-in surface 404s; DELETE stays reachable."""
    c, token, _sess = client
    with patch.object(server, "is_enabled", lambda k: False):
        assert c.post("/api/auth/apple", headers=_h(token),
                      data=json.dumps({"identity_token": "x"})).status_code == 404
        assert c.post("/api/auth/google", headers=_h(token),
                      data=json.dumps({"id_token": "x"})).status_code == 404
        assert c.get("/api/account", headers=_h(token)).status_code == 404
        with engine.begin() as conn:
            conn.execute(insert(db_module.users_table).values(
                sleeper_user_id=USER))
        r = c.delete("/api/account", headers=_h(token))
        assert r.status_code == 200
        assert r.get_json()["ok"] is True


def test_auth_apple_binds_session_and_verifies(client, engine):
    c, token, sess = client
    with engine.begin() as conn:
        conn.execute(insert(db_module.users_table).values(sleeper_user_id=USER))
    tok = _make_token(_apple_claims())
    with patch.object(server, "is_enabled", lambda k: k == "auth.accounts"):
        r = c.post("/api/auth/apple", headers=_h(token),
                   data=json.dumps({"identity_token": tok}))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["linked"] is True
    assert body["sleeper_user_id"] == USER
    assert body["conflict"] is False
    assert body["verified_via"] == "apple"
    assert sess["verified"] is True and sess["verified_via"] == "apple"
    assert accounts.get_user_verified_via(USER) == "apple"
    # Account row exists and is bound.
    acct = accounts.get_account_for_user(USER)
    assert acct["identities"][0]["provider"] == "apple"

    # GET /api/account reflects it.
    with patch.object(server, "is_enabled", lambda k: k == "auth.accounts"):
        r = c.get("/api/account", headers=_h(token))
    body = r.get_json()
    assert body["verified_via"] == "apple"
    assert body["account"]["account_id"] == acct["account_id"]


def test_auth_apple_invalid_token_401(client, engine):
    c, token, _sess = client
    bad = _make_token(_apple_claims(exp=int(time.time()) - 3600))
    with patch.object(server, "is_enabled", lambda k: k == "auth.accounts"):
        r = c.post("/api/auth/apple", headers=_h(token),
                   data=json.dumps({"identity_token": bad}))
    assert r.status_code == 401
    assert r.get_json() == {"error": "invalid_token", "reason": "expired"}


def test_auth_apple_new_identity_without_session(client, engine):
    """No session + unbound identity → ACCOUNT-FIRST (P2.6): an
    account-keyed session is minted (working key acct_<account_id>) instead
    of the old P2 dead-end. Full lifecycle coverage: test_account_first.py."""
    c, _token, _sess = client
    tok = _make_token(_apple_claims(sub="fresh-sub"))
    with patch.object(server, "is_enabled", lambda k: k == "auth.accounts"), \
         patch.object(server, "_account_build_session",
                      lambda user_id, display_name: (
                          "acct-first-tok",
                          {"user_id": user_id, "display_name": display_name,
                           "last_active": 0.0})):
        r = c.post("/api/auth/apple", data=json.dumps({"identity_token": tok}),
                   headers={"Content-Type": "application/json"})
    body = r.get_json()
    assert r.status_code == 200
    assert body["linked"] is False
    assert body["account_only"] is True
    assert body["session_token"] == "acct-first-tok"
    assert body["user_id"] == accounts.account_user_id(body["account_id"])


def test_auth_apple_restore_session_for_bound_account(client, engine):
    """No session + already-bound identity → device-loss restore path."""
    c, _token, _sess = client
    with engine.begin() as conn:
        conn.execute(insert(db_module.users_table).values(
            sleeper_user_id=USER, username="matt", display_name="Matt"))
    acct = accounts.find_or_create_account("apple", "restore-sub")
    accounts.bind_sleeper_user(acct["account_id"], USER)

    fake_payload: dict = {}
    with patch.object(server, "is_enabled", lambda k: k == "auth.accounts"), \
         patch.object(server, "_extension_build_session",
                      lambda **kw: ("restored-tok", fake_payload)):
        tok = _make_token(_apple_claims(sub="restore-sub"))
        r = c.post("/api/auth/apple", data=json.dumps({"identity_token": tok}),
                   headers={"Content-Type": "application/json"})
    body = r.get_json()
    assert r.status_code == 200
    assert body["linked"] is True
    assert body["session_token"] == "restored-tok"
    assert body["username"] == "matt"
    assert fake_payload["verified"] is True
    assert fake_payload["verified_via"] == "apple"
    assert accounts.get_user_verified_via(USER) == "apple"


def test_auth_apple_conflict_does_not_rebind(client, engine):
    """A session for a different user can't steal a bound identity."""
    c, token, sess = client
    acct = accounts.find_or_create_account("apple", "bound-sub")
    accounts.bind_sleeper_user(acct["account_id"], OTHER)
    tok = _make_token(_apple_claims(sub="bound-sub"))
    with patch.object(server, "is_enabled", lambda k: k == "auth.accounts"):
        r = c.post("/api/auth/apple", headers=_h(token),
                   data=json.dumps({"identity_token": tok}))
    body = r.get_json()
    assert body["conflict"] is True
    assert body["sleeper_user_id"] == OTHER          # original binding kept
    assert sess.get("verified") is not True          # no verification granted


def test_google_route_unconfigured_503(client, monkeypatch):
    c, token, _sess = client
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    with patch.object(server, "is_enabled", lambda k: k == "auth.accounts"):
        r = c.post("/api/auth/google", headers=_h(token),
                   data=json.dumps({"id_token": "x"}))
    assert r.status_code == 503
    assert r.get_json()["error"] == "not_configured"


def test_google_route_verifies_when_configured(client, engine, monkeypatch):
    c, token, sess = client
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    with engine.begin() as conn:
        conn.execute(insert(db_module.users_table).values(sleeper_user_id=USER))
    claims = {"iss": "https://accounts.google.com", "aud": "client-123",
              "sub": "g-sub", "exp": int(time.time()) + 600}
    with patch.object(server, "is_enabled", lambda k: k == "auth.accounts"):
        r = c.post("/api/auth/google", headers=_h(token),
                   data=json.dumps({"id_token": _make_token(claims)}))
    assert r.status_code == 200
    assert r.get_json()["verified_via"] == "google"
    assert sess["verified_via"] == "google"


def test_delete_account_requires_verified_session_when_user_verified(client, engine):
    c, token, sess = client
    with engine.begin() as conn:
        conn.execute(insert(db_module.users_table).values(
            sleeper_user_id=USER, verified_via="sleeper",
            verified_at="2026-07-11"))
    # Unverified session on a verified user → refused.
    r = c.delete("/api/account", headers=_h(token))
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"
    # Verified session → allowed; user row gone; session evicted.
    sess["verified"] = True
    r = c.delete("/api/account", headers=_h(token))
    assert r.status_code == 200
    with engine.connect() as conn:
        assert conn.execute(select(db_module.users_table)).fetchall() == []
    with server._sessions_lock:
        assert token not in server._sessions


def test_delete_account_demo_session_400(client):
    c, _token, _sess = client
    demo_tok = "demo-sess-tok"
    with server._sessions_lock:
        server._sessions[demo_tok] = {"user_id": "demo_user_ab12",
                                      "is_demo": True, "last_active": 0.0}
    try:
        r = c.delete("/api/account", headers=_h(demo_tok))
        assert r.status_code == 400
        assert r.get_json()["error"] == "demo_session"
    finally:
        with server._sessions_lock:
            server._sessions.pop(demo_tok, None)
