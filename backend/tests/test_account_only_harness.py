"""P0-5 — the unified harness seam, server half (mobile UX audit 2026-08-09).

Spec: docs/plans/audit-p0-remediation/hld.md §5.3 + lld-p0-5.md §10 (T-1…T-4).
Branch: p0-remediation-2026-08-10.

`_test_mode_identity()` lets a Maestro run mint a REAL account-only session
through the production path: `FTF_TEST_MODE=1` + an identity token of the form
`ftf-test-apple:<sub>` substitutes for `verify_apple_token` and NOTHING else.
Everything downstream — `_provider_auth_response`, `_mint_account_only_session`,
the sentinel league, `verified_via='apple'` — is production code, which is the
entire justification for the seam existing rather than a stubbed fixture.

WHY THIS IS A SEPARATE FILE. `test_account_first.py` is P0-5's stated
must-stay-green-UNTOUCHED contract (hld.md §10.5); extending it would make the
regression proof and the new behaviour share a file.

WHY `monkeypatch.setattr(server, "_TEST_MODE", …)` AND NOT `setenv`.
`server._TEST_MODE` is `os.environ.get("FTF_TEST_MODE") == "1"` evaluated ONCE
at import (server.py:486). Setting the env var after import has no effect. The
helper reads the module constant for exactly the same reason, so the test and
the production gate agree by construction.
"""
import base64
import copy
import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, insert, select

import backend.accounts as accounts
import backend.database as db_module
import backend.espn_service as es
import backend.server as server
from backend.database import metadata

HARNESS_SUB = "qa-apple-p05"
HARNESS_TOKEN = f"ftf-test-apple:{HARNESS_SUB}"
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


# ---------------------------------------------------------------------------
# JWT / JWKS helpers (same scheme as test_account_first.py)
# ---------------------------------------------------------------------------

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _jwks() -> list[dict]:
    pub = _KEY.public_key().public_numbers()
    n = pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big")
    e = pub.e.to_bytes((pub.e.bit_length() + 7) // 8, "big")
    return [{"kty": "RSA", "kid": "k1", "use": "sig", "alg": "RS256",
             "n": _b64url(n), "e": _b64url(e)}]


def _fake_account_builder(user_id: str, display_name: str):
    """Honors _account_build_session's contract minus the heavy services."""
    token = f"acct-sess-{user_id}"
    payload = {"user_id": user_id, "display_name": display_name,
               "active_format": "1qb_ppr", "last_active": time.time(),
               "account_only": True}
    with db_module.engine.begin() as conn:
        exists = conn.execute(
            select(db_module.users_table.c.sleeper_user_id).where(
                db_module.users_table.c.sleeper_user_id == user_id)).fetchone()
        if exists is None:
            conn.execute(insert(db_module.users_table).values(
                sleeper_user_id=user_id, display_name=display_name,
                created_at="2026-08-10"))
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
         patch.object(server, "_account_build_session", _fake_account_builder):
        try:
            yield c, engine, flags_on
        finally:
            with server._sessions_lock:
                for t in set(server._sessions) - injected_before:
                    server._sessions.pop(t, None)


def _post_apple(c, token=HARNESS_TOKEN, headers=None, body_extra=None):
    body = {"identity_token": token}
    if body_extra:
        body.update(body_extra)
    return c.post("/api/auth/apple", data=json.dumps(body),
                  headers={"Content-Type": "application/json",
                           **(headers or {})})


# ═══════════════════════════════════════════════════════════════════════════
# T-1 — the production gate, ASSERTED not assumed
# ═══════════════════════════════════════════════════════════════════════════

def test_apple_harness_token_401s_when_test_mode_unset(client):
    """The whole safety argument in one assertion. No monkeypatching of any
    kind: the suite runs with FTF_TEST_MODE unset, which IS the deployed
    condition, and the harness token is rejected as an unverifiable JWT."""
    c, _, _ = client
    r = _post_apple(c)
    assert r.status_code == 401
    assert r.get_json()["error"] == "invalid_token"


def test_test_mode_identity_returns_none_in_every_deployed_config():
    """Unit-level twin of T-1, plus the shape guards. With the gate ON, only a
    correctly-prefixed NON-EMPTY sub produces an identity."""
    assert server._TEST_MODE is False, "FTF_TEST_MODE must be unset under pytest"
    assert server._test_mode_identity(HARNESS_TOKEN) is None

    with patch.object(server, "_TEST_MODE", True):
        assert server._test_mode_identity(HARNESS_TOKEN) == {"sub": HARNESS_SUB}
        assert server._test_mode_identity("ftf-test-apple:") is None
        assert server._test_mode_identity("ftf-test-apple:   ") is None
        assert server._test_mode_identity("some.real.jwt") is None
        assert server._test_mode_identity("") is None


# ═══════════════════════════════════════════════════════════════════════════
# T-2 — the seam runs the PRODUCTION mint path
# ═══════════════════════════════════════════════════════════════════════════

def test_apple_harness_token_mints_real_account_only_session_in_test_mode(
        client, monkeypatch):
    c, _, _ = client
    monkeypatch.setattr(server, "_TEST_MODE", True)

    r = _post_apple(c, body_extra={"display_name": "QA Apple"})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()

    assert body["account_only"] is True
    assert body["linked"] is False
    assert body["user_id"] == accounts.account_user_id(body["account_id"])
    assert body["league_id"] == server.ACCOUNT_NO_LEAGUE_ID
    assert body["verified_via"] == "apple"
    # The verified marker is set by _mint_account_only_session, i.e. by the
    # production path — not by the seam.
    with server._sessions_lock:
        assert server._sessions[body["session_token"]]["verified"] is True


def test_the_same_harness_sub_restores_the_same_account_key(client, monkeypatch):
    """The seam is stable across relaunches, which is what the flow's leg-4
    persistence check rests on."""
    c, _, _ = client
    monkeypatch.setattr(server, "_TEST_MODE", True)
    first = _post_apple(c).get_json()
    second = _post_apple(c).get_json()
    assert first["user_id"] == second["user_id"]
    assert first["account_id"] == second["account_id"]


# ═══════════════════════════════════════════════════════════════════════════
# T-3 — the claim the design rests on: an account-only session can link
# ═══════════════════════════════════════════════════════════════════════════

def test_account_only_session_can_post_espn_link(monkeypatch):
    """GATE COMPOSITION, not ESPN behaviour. `@_gate_unverified_write` passes
    because account-only sessions carry verified=True, and `_require_session`
    yields the acct_ key as user_id — so NO SLEEPER IDENTITY IS REQUIRED TO
    LINK A LEAGUE. If that ever changes, this design's escape hatch closes and
    this test is the alarm."""
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    acct_uid = "acct_p05harness"
    token = "acct-espn-tok"
    sess = {"user_id": acct_uid, "active_format": "1qb_ppr", "last_active": 0.0,
            "account_only": True, "verified": True, "verified_via": "apple"}

    with open(os.path.join(
            FIXTURES, "espn_league_snapshot_2026-07-11.json")) as f:
        payload = json.load(f)
    xwalk = es.load_crosswalk(os.path.join(
        FIXTURES, "dp_playerids_snapshot_2026-07-11.csv"))

    server.app.config["TESTING"] = True
    c = server.app.test_client()
    flags_on = {"espn.link", "auth.accounts"}

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags_on), \
         patch.object(es, "get_crosswalk", lambda _opener=None: xwalk), \
         patch.object(es, "fetch_league", lambda *a, **kw: copy.deepcopy(payload)):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            r = c.post("/api/espn/link",
                       headers={"X-Session-Token": token,
                                "Content-Type": "application/json"},
                       data=json.dumps({"espn_league_id": "987654321",
                                        "season": 2026}))
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)

    assert r.status_code not in (401, 403), r.get_data(as_text=True)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json().get("teams"), r.get_json()


# ═══════════════════════════════════════════════════════════════════════════
# T-4 — the latent 403: session/init must not drop `verified` for acct_ keys
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def init_client(monkeypatch):
    """The minimum session_init world: a tiny universal pool, no Sleeper
    network, no background daemons. Copied from test_verified_sessions.py."""
    from cryptography.fernet import Fernet
    from backend.ranking_service import Player
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    acct_uid = "acct_p05init"
    token = "acct-init-tok"
    sess = {"user_id": acct_uid, "active_format": "1qb_ppr", "last_active": 0.0,
            "account_only": True}

    pool = [
        Player("qb_1", "QB One", "QB", "AAA", 25, 3),
        Player("rb_1", "RB One", "RB", "BBB", 24, 2),
        Player("wr_1", "WR One", "WR", "CCC", 23, 1),
    ]
    seed = {p.id: 1500.0 for p in pool}
    fake_pools = {"1qb_ppr": {"players": pool, "seed": seed},
                  "sf_tep":  {"players": pool, "seed": seed}}
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format", fake_pools)
    monkeypatch.setattr(server, "g_universal_players", pool)
    monkeypatch.setattr(server, "_kickoff_trade_job", MagicMock())
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta", lambda lid: None)

    # SELECTIVE: only the bg-writes thread is inerted; the session-init-rank
    # workers must actually run or fut.result() deadlocks.
    real_thread = server.threading.Thread

    class _SelectiveThread(real_thread):
        def start(self):
            if self.name == "session-init-bg-writes":
                return
            super().start()

    monkeypatch.setattr(server.threading, "Thread", _SelectiveThread)

    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k == "auth.accounts"), \
         patch.object(server, "touch_user_activity", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, acct_uid
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def test_session_init_reuses_token_and_preserves_verified_for_account_user(
        init_client):
    """Without this, the P2.5 read/write gates would 403 an account-only user
    out of their own board the moment they linked their first league — a
    failure that would look like "ESPN linking is broken" and be debugged
    nowhere near this code. test_verified_sessions.py covers the
    Sleeper-keyed carryover; the acct_ case is untested today.

    The mechanism: `user_changed` is false for a same-acct_ re-init, so the
    incoming token is reused and the `verified` pop is skipped.
    """
    c, token, acct_uid = init_client
    with server._sessions_lock:
        server._sessions[token]["verified"] = True
        server._sessions[token]["verified_via"] = "apple"
    db_module.upsert_user(sleeper_user_id=acct_uid)
    accounts.mark_user_verified(acct_uid, "apple")

    r = c.post("/api/session/init",
               headers={"X-Session-Token": token,
                        "Content-Type": "application/json"},
               data=json.dumps({
                   "user_id": acct_uid,
                   "league_id": "league_x",
                   "league_name": "Test League",
                   "user_player_ids": ["qb_1"],
                   "opponent_rosters": [
                       {"user_id": "opp_1", "username": "Opp",
                        "player_ids": ["rb_1"]},
                   ],
               }))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["token"] == token                 # SAME token, not rotated
    v = body["verification"]
    assert v["session_verified"] is True
    assert v["user_verified"] is True and v["verified_via"] == "apple"
