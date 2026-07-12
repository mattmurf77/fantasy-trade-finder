"""Account-first identity (P2.6, feedback #116) — docs/plans/
account-auth-plan-2026-07-11.md §P2.6.

Covers:

  1. Account-only lifecycle: Sign in with Apple with NO session and NO bound
     Sleeper source mints an account-keyed session (working key
     acct_<account_id>), verified_via='apple'; re-auth with the same Apple
     sub restores the SAME key (board survives sign-out/sign-in).
  2. The synthetic key never binds into accounts.sleeper_user_id.
  3. Gate composition: the acct_ users row is born with a verified
     controller, so a hostile session naming that key (e.g. via
     /api/session/init's body-trusting user_id) is read- AND write-403'd by
     the existing P1/P2.5 gates; the real account session passes both.
  4. POST /api/account/link-sleeper — the full merge matrix:
     fresh adopt / migrate / merge_choice_required / keep_sleeper /
     keep_account / sticky-conflict / first-verified-wins deny / flag-off /
     no-account, plus first-verified-wins composition AFTER the link.
  5. accounts.board_data_summary / migrate_board_data unit behavior.

Same isolation pattern as test_accounts.py + test_verified_sessions.py:
Flask test client, in-memory SQLite, injected sessions, JWKS + Sleeper
lookups mocked, session builders faked (the real builders need the player
cache; their contract — "registers the session and upserts the users row" —
is honored by the fakes).
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

SLEEPER_UID = "313560442465169408"
OTHER_SLEEPER_UID = "999999999999999999"


# ---------------------------------------------------------------------------
# JWT / JWKS helpers (same scheme as test_accounts.py)
# ---------------------------------------------------------------------------

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _make_token(claims: dict) -> str:
    header = {"alg": "RS256", "kid": "k1"}
    signing_input = (
        f"{_b64url(json.dumps(header).encode())}."
        f"{_b64url(json.dumps(claims).encode())}"
    )
    sig = _KEY.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(sig)}"


def _jwks() -> list[dict]:
    pub = _KEY.public_key().public_numbers()
    n = pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big")
    e = pub.e.to_bytes((pub.e.bit_length() + 7) // 8, "big")
    return [{"kty": "RSA", "kid": "k1", "use": "sig", "alg": "RS256",
             "n": _b64url(n), "e": _b64url(e)}]


def _apple_token(sub: str = "apple-sub-p26") -> str:
    return _make_token({
        "iss": accounts.APPLE_ISSUER,
        "aud": accounts.APPLE_AUDIENCE,
        "sub": sub,
        "exp": int(time.time()) + 600,
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _fake_account_builder(user_id: str, display_name: str):
    """Honors _account_build_session's contract minus the heavy services:
    upserts the users row and registers the session."""
    token = f"acct-sess-{user_id}"
    payload = {"user_id": user_id, "display_name": display_name,
               "active_format": "1qb_ppr", "last_active": time.time(),
               "account_only": True}
    with db_module.engine.begin() as conn:
        exists = conn.execute(
            select(db_module.users_table.c.sleeper_user_id).where(
                db_module.users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
        if exists is None:
            conn.execute(insert(db_module.users_table).values(
                sleeper_user_id=user_id, display_name=display_name,
                created_at="2026-07-12"))
    with server._sessions_lock:
        server._sessions[token] = payload
    return token, payload


def _fake_extension_builder(user_id: str, username: str,
                            display_name: str, avatar):
    token = f"link-sess-{user_id}"
    payload = {"user_id": user_id, "username": username,
               "display_name": display_name,
               "active_format": "1qb_ppr", "last_active": time.time()}
    with db_module.engine.begin() as conn:
        exists = conn.execute(
            select(db_module.users_table.c.sleeper_user_id).where(
                db_module.users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
        if exists is None:
            conn.execute(insert(db_module.users_table).values(
                sleeper_user_id=user_id, username=username,
                display_name=display_name, created_at="2026-07-12"))
    with server._sessions_lock:
        server._sessions[token] = payload
    return token, payload


@pytest.fixture(autouse=True)
def _mock_jwks(monkeypatch):
    monkeypatch.setattr(accounts, "_fetch_jwks", lambda url: _jwks())
    accounts._jwks_cache.clear()
    yield
    accounts._jwks_cache.clear()


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    c = server.app.test_client()

    flags_on = {"auth.accounts"}
    injected_before = set(server._sessions)
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags_on), \
         patch.object(server, "_account_build_session",
                      _fake_account_builder), \
         patch.object(server, "_extension_build_session",
                      _fake_extension_builder):
        try:
            yield c, engine, flags_on
        finally:
            with server._sessions_lock:
                for t in set(server._sessions) - injected_before:
                    server._sessions.pop(t, None)


def _post_apple(c, sub="apple-sub-p26", headers=None, body_extra=None):
    body = {"identity_token": _apple_token(sub)}
    if body_extra:
        body.update(body_extra)
    return c.post("/api/auth/apple", data=json.dumps(body),
                  headers={"Content-Type": "application/json",
                           **(headers or {})})


def _seed_board(engine, uid, swipes=1, tiers=False, method=None):
    with engine.begin() as conn:
        exists = conn.execute(
            select(db_module.users_table.c.sleeper_user_id).where(
                db_module.users_table.c.sleeper_user_id == uid)
        ).fetchone()
        if exists is None:
            conn.execute(insert(db_module.users_table).values(
                sleeper_user_id=uid, created_at="2026-07-12"))
        for _ in range(swipes):
            conn.execute(insert(db_module.swipe_decisions_table).values(
                user_id=uid, winner_player_id="p1", loser_player_id="p2",
                decision_type="rank", k_factor=32.0))
        if tiers or method:
            vals = {}
            if tiers:
                vals["tier_overrides"] = json.dumps({"1qb_ppr": {"p1": 1800}})
            if method:
                vals["ranking_method"] = method
            from sqlalchemy import update
            conn.execute(update(db_module.users_table).where(
                db_module.users_table.c.sleeper_user_id == uid).values(**vals))


def _swipe_uids(engine):
    with engine.connect() as conn:
        return [r.user_id for r in conn.execute(
            select(db_module.swipe_decisions_table.c.user_id)).fetchall()]


# ---------------------------------------------------------------------------
# 1–2. Account-only sign-in lifecycle
# ---------------------------------------------------------------------------

def test_account_first_mints_account_keyed_session(client):
    c, engine, _ = client
    r = _post_apple(c, body_extra={"display_name": "Matt"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["account_only"] is True
    assert body["linked"] is False
    assert body["session_token"]
    assert body["user_id"] == accounts.account_user_id(body["account_id"])
    assert body["verified_via"] == "apple"
    assert body["league_id"] == server.ACCOUNT_NO_LEAGUE_ID
    assert body["display_name"] == "Matt"

    # Session is verified (passes the P1/P2.5 gates).
    with server._sessions_lock:
        sess = server._sessions[body["session_token"]]
    assert sess["verified"] is True and sess["verified_via"] == "apple"
    assert sess["account_only"] is True

    # Persisted controller marker — arms the gates against key-squatting.
    assert accounts.get_user_verified_via(body["user_id"]) == "apple"
    # The synthetic key is NOT a Sleeper binding.
    assert accounts.get_account(body["account_id"])["sleeper_user_id"] is None


def test_account_reauth_restores_same_working_key(client):
    c, engine, _ = client
    first = _post_apple(c).get_json()
    _seed_board(engine, first["user_id"], swipes=3)
    # Sign out (client-side) then sign in again — same Apple sub.
    second = _post_apple(c).get_json()
    assert second["user_id"] == first["user_id"]
    assert second["account_id"] == first["account_id"]
    # Board is still keyed to the restored working key.
    assert _swipe_uids(engine) == [first["user_id"]] * 3


def test_account_session_reauth_never_binds_synthetic_key(client):
    c, engine, _ = client
    first = _post_apple(c).get_json()
    # Re-post the token WITH the account session attached (e.g. app retry).
    r = _post_apple(c, headers={"X-Session-Token": first["session_token"]})
    body = r.get_json()
    assert body["conflict"] is False
    assert body.get("account_only") is True
    # acct_* must never appear as the account's Sleeper binding.
    assert accounts.get_account(first["account_id"])["sleeper_user_id"] is None


# ---------------------------------------------------------------------------
# 3. Gate composition on the account key
# ---------------------------------------------------------------------------

def test_hostile_session_on_account_key_is_gated(client):
    """A session that names the acct_ key without provider proof (e.g. a
    hostile /api/session/init) hits the verified-controller branch of BOTH
    gates — write and read 403 even in grace."""
    c, engine, _ = client
    acct_uid = _post_apple(c).get_json()["user_id"]

    hostile_tok = "hostile-acct-sess"
    with server._sessions_lock:
        server._sessions[hostile_tok] = {
            "user_id": acct_uid, "active_format": "1qb_ppr",
            "last_active": time.time()}
    h = {"X-Session-Token": hostile_tok, "Content-Type": "application/json"}

    r = c.post("/api/ranking-method", headers=h,
               data=json.dumps({"method": "trio"}))
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"

    r = c.get("/api/tiers/status", headers=h)
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"


def test_account_session_passes_write_gate(client):
    c, engine, _ = client
    body = _post_apple(c).get_json()
    h = {"X-Session-Token": body["session_token"],
         "Content-Type": "application/json"}
    r = c.post("/api/ranking-method", headers=h,
               data=json.dumps({"method": "trio"}))
    assert r.status_code == 200
    # Persisted under the account working key.
    with db_module.engine.connect() as conn:
        row = conn.execute(
            select(db_module.users_table.c.ranking_method).where(
                db_module.users_table.c.sleeper_user_id == body["user_id"])
        ).fetchone()
    assert row.ranking_method == "trio"


# ---------------------------------------------------------------------------
# 4. POST /api/account/link-sleeper — merge matrix
# ---------------------------------------------------------------------------

def _sleeper_lookup(url, *a, **k):
    return {"user_id": SLEEPER_UID, "display_name": "RealManager",
            "username": "realmanager", "avatar": None}


def _link(c, token, username="realmanager", strategy=None):
    body = {"username": username}
    if strategy:
        body["strategy"] = strategy
    with patch.object(server, "_sleeper_get", _sleeper_lookup):
        return c.post("/api/account/link-sleeper", data=json.dumps(body),
                      headers={"X-Session-Token": token,
                               "Content-Type": "application/json"})


def test_link_fresh_sleeper_migrates_account_board(client):
    c, engine, _ = client
    acct = _post_apple(c).get_json()
    _seed_board(engine, acct["user_id"], swipes=2, tiers=True, method="trio")

    r = _link(c, acct["session_token"])
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["sleeper_user_id"] == SLEEPER_UID
    assert body["merge"] == "migrated"
    assert body["session_token"]

    # Board re-keyed to the Sleeper id; acct_ users row gone.
    assert set(_swipe_uids(engine)) == {SLEEPER_UID}
    with engine.connect() as conn:
        rows = conn.execute(select(db_module.users_table)).fetchall()
    by_uid = {r.sleeper_user_id: r for r in rows}
    assert acct["user_id"] not in by_uid
    assert by_uid[SLEEPER_UID].tier_overrides
    assert by_uid[SLEEPER_UID].ranking_method == "trio"

    # Sticky binding recorded + first-verified-wins armed on the Sleeper id.
    assert accounts.get_account(acct["account_id"])["sleeper_user_id"] == SLEEPER_UID
    assert accounts.get_user_verified_via(SLEEPER_UID) == "apple"

    # Old account-keyed session evicted; new one live and verified.
    with server._sessions_lock:
        assert acct["session_token"] not in server._sessions
        new_sess = server._sessions[body["session_token"]]
    assert new_sess["verified"] is True and new_sess["user_id"] == SLEEPER_UID


def test_link_denied_when_sleeper_id_already_claimed(client):
    """First-verified-wins: the Sleeper id's real owner proved control
    (verified_via='sleeper') — an account cannot take it over."""
    c, engine, _ = client
    acct = _post_apple(c).get_json()
    _seed_board(engine, SLEEPER_UID, swipes=1)
    accounts.mark_user_verified(SLEEPER_UID, "sleeper")

    r = _link(c, acct["session_token"])
    assert r.status_code == 403
    assert r.get_json()["error"] == "sleeper_already_claimed"
    # Nothing moved, nothing bound.
    assert accounts.get_account(acct["account_id"])["sleeper_user_id"] is None
    assert set(_swipe_uids(engine)) == {SLEEPER_UID}


def test_link_both_boards_requires_explicit_choice(client):
    c, engine, _ = client
    acct = _post_apple(c).get_json()
    _seed_board(engine, acct["user_id"], swipes=2)
    _seed_board(engine, SLEEPER_UID, swipes=5)

    r = _link(c, acct["session_token"])
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "merge_choice_required"
    assert body["account_board"]["swipes"] == 2
    assert body["sleeper_board"]["swipes"] == 5
    # No data touched, no binding made.
    assert accounts.get_account(acct["account_id"])["sleeper_user_id"] is None
    uids = _swipe_uids(engine)
    assert uids.count(acct["user_id"]) == 2 and uids.count(SLEEPER_UID) == 5


def test_link_keep_sleeper_wipes_account_board(client):
    c, engine, _ = client
    acct = _post_apple(c).get_json()
    _seed_board(engine, acct["user_id"], swipes=2)
    _seed_board(engine, SLEEPER_UID, swipes=5)

    r = _link(c, acct["session_token"], strategy="keep_sleeper")
    assert r.status_code == 200
    assert r.get_json()["merge"] == "kept_sleeper"
    uids = _swipe_uids(engine)
    assert uids.count(SLEEPER_UID) == 5 and acct["user_id"] not in uids
    assert accounts.get_account(acct["account_id"])["sleeper_user_id"] == SLEEPER_UID


def test_link_keep_account_replaces_sleeper_board(client):
    c, engine, _ = client
    acct = _post_apple(c).get_json()
    _seed_board(engine, acct["user_id"], swipes=2, method="manual")
    _seed_board(engine, SLEEPER_UID, swipes=5, method="tiers")

    r = _link(c, acct["session_token"], strategy="keep_account")
    assert r.status_code == 200
    assert r.get_json()["merge"] == "kept_account"
    uids = _swipe_uids(engine)
    # Sleeper's 5 wiped, the account's 2 migrated in.
    assert uids.count(SLEEPER_UID) == 2 and acct["user_id"] not in uids
    with engine.connect() as conn:
        row = conn.execute(
            select(db_module.users_table.c.ranking_method).where(
                db_module.users_table.c.sleeper_user_id == SLEEPER_UID)
        ).fetchone()
    assert row.ranking_method == "manual"


def test_link_sticky_conflict_on_differently_bound_account(client):
    c, engine, _ = client
    acct = _post_apple(c).get_json()
    # Account already bound elsewhere (e.g. via a P2 session bind).
    accounts.bind_sleeper_user(acct["account_id"], OTHER_SLEEPER_UID)

    r = _link(c, acct["session_token"])
    assert r.status_code == 409
    assert r.get_json()["error"] == "sleeper_conflict"
    assert accounts.get_account(acct["account_id"])["sleeper_user_id"] == OTHER_SLEEPER_UID


def test_link_requires_account_session(client):
    c, engine, _ = client
    tok = "plain-username-sess"
    with server._sessions_lock:
        server._sessions[tok] = {"user_id": SLEEPER_UID,
                                 "active_format": "1qb_ppr",
                                 "last_active": time.time()}
    r = _link(c, tok)
    assert r.status_code == 400
    assert r.get_json()["error"] == "no_account"


def test_link_404_when_flag_off(client):
    c, engine, flags_on = client
    acct = _post_apple(c).get_json()
    flags_on.discard("auth.accounts")
    r = _link(c, acct["session_token"])
    assert r.status_code == 404


def test_first_verified_wins_composes_after_link(client):
    """After link-sleeper, the Sleeper id has verified_via='apple' — a
    username-only session for that id loses reads and writes immediately."""
    c, engine, _ = client
    acct = _post_apple(c).get_json()
    r = _link(c, acct["session_token"])
    assert r.status_code == 200

    squat_tok = "squatter-sess"
    with server._sessions_lock:
        server._sessions[squat_tok] = {"user_id": SLEEPER_UID,
                                       "active_format": "1qb_ppr",
                                       "last_active": time.time()}
    h = {"X-Session-Token": squat_tok, "Content-Type": "application/json"}
    assert c.post("/api/ranking-method", headers=h,
                  data=json.dumps({"method": "trio"})).status_code == 403
    assert c.get("/api/tiers/status", headers=h).status_code == 403


# ---------------------------------------------------------------------------
# 5. accounts helpers
# ---------------------------------------------------------------------------

def test_account_user_id_helpers():
    assert accounts.account_user_id("abc") == "acct_abc"
    assert accounts.is_account_user_id("acct_abc") is True
    assert accounts.is_account_user_id("313560442465169408") is False
    assert accounts.is_account_user_id(None) is False


def test_board_data_summary_and_migrate(client):
    _, engine, _ = client
    src, dst = "acct_src", SLEEPER_UID
    _seed_board(engine, src, swipes=2, tiers=True, method="anchor")
    with engine.begin() as conn:
        conn.execute(insert(db_module.user_player_skips_table).values(
            user_id=src, player_id="p9", scoring_format="1qb_ppr"))
        conn.execute(insert(db_module.member_rankings_table).values(
            user_id=src, league_id=server.ACCOUNT_NO_LEAGUE_ID,
            player_id="p1", elo=1500.0))

    summary = accounts.board_data_summary(src)
    assert summary["swipes"] == 2
    assert summary["tier_overrides"] is True
    assert summary["ranking_method"] == "anchor"
    assert summary["any"] is True
    assert accounts.board_data_summary(dst)["any"] is False

    counts = accounts.migrate_board_data(src, dst)
    assert counts["swipe_decisions_moved"] == 2
    assert counts["user_player_skips_moved"] == 1
    assert counts["member_rankings_dropped"] == 1

    dst_summary = accounts.board_data_summary(dst)
    assert dst_summary["swipes"] == 2
    assert dst_summary["tier_overrides"] is True
    assert dst_summary["ranking_method"] == "anchor"
    assert accounts.board_data_summary(src)["any"] is False
    with engine.connect() as conn:
        assert conn.execute(
            select(db_module.users_table.c.sleeper_user_id).where(
                db_module.users_table.c.sleeper_user_id == src)
        ).fetchone() is None
