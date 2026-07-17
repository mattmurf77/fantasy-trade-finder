"""Account-auth P2.5 — READ privacy for board content.

Extends P1's write gate to reads (docs/plans/account-auth-plan-2026-07-11.md
§"P2.5"): "ranks hidden behind an account" means an attacker with just a
username must not be able to VIEW the victim's board once the real owner
has verified. Rule under test (@_gate_unverified_read):

  unverified session + verified controller exists → 403 verification_required
  unverified session, no controller               → allow (onboarding/grace)
  verified session                                → allow
  enforcement flag                                → irrelevant to reads

Same isolation pattern as test_verified_sessions.py: Flask test client,
in-memory SQLite, injected bare sessions, no network.
"""
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.accounts as accounts
import backend.database as db_module
import backend.server as server
from backend.database import metadata

from .test_verified_sessions import UID, _h, _token

# Every read route carrying @_gate_unverified_read (plus Mode B of
# /api/trade/evaluate, gated inline — exercised separately below). The gate
# runs BEFORE the route body, so paths whose handlers need an initialized
# session (league/players/services) still 403 cleanly from a bare session.
GATED_READS = [
    "/api/rankings",
    "/api/progress",
    "/api/rankings/progress",
    "/api/me/streak",
    "/api/tiers/status",
    "/api/tiers/community-diff?position=RB",
    "/api/tiers/stability",
    "/api/anchor/scale",
    "/api/trades",
    "/api/trades/status?job_id=nope",
    "/api/trades/liked",
    "/api/trades/matches",
    "/api/trades/matches/all",
    "/api/trades/awaiting",
    "/api/league/preferences",
    "/api/league/asset-prefs",
    "/api/league/free-agents",
    "/api/feedback/mine",
    "/api/notifications",
    "/api/trends/risers-fallers",
    "/api/trends/contrarian",
    "/api/trends/consensus-gap",
    "/api/extension/rankings",
]

# Subset whose handlers work from a bare session + empty DB (no in-memory
# ranking/trade services needed) — used for the allow-side assertions where
# the request must reach the handler and return 200.
BARE_SESSION_200_READS = [
    "/api/me/streak",
    "/api/tiers/status",
    "/api/anchor/scale",
    "/api/feedback/mine",
    "/api/notifications",
    "/api/trades/matches/all",
    "/api/trades/awaiting",
]


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "sess-read-tok"
    sess = {"user_id": UID, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    flags_on = {"trade.send_in_sleeper"}
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


def _sess(token):
    with server._sessions_lock:
        return server._sessions[token]


def _mark_controller():
    db_module.upsert_user(sleeper_user_id=UID)
    accounts.mark_user_verified(UID, "sleeper")


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------

def test_unverified_with_controller_denied_on_every_gated_read(client):
    """Squatter case: someone verified this user_id → every board-content
    read 403s from an unverified session, no grace."""
    c, token, _ = client
    _mark_controller()
    for path in GATED_READS:
        r = c.get(path, headers=_h(token))
        assert r.status_code == 403, f"{path} → {r.status_code}"
        assert r.get_json()["error"] == "verification_required", path


def test_unverified_without_controller_reads_allowed(client):
    """Onboarding case: nobody has verified this user_id → reads work
    exactly as before the gate existed."""
    c, token, _ = client
    for path in BARE_SESSION_200_READS:
        r = c.get(path, headers=_h(token))
        assert r.status_code == 200, f"{path} → {r.status_code}"


def test_enforcement_flag_does_not_deny_reads(client):
    """auth.enforce_verified_writes hard-denies WRITES only; a user mid-
    onboarding (no controller anywhere) must still see their own board."""
    c, token, flags_on = client
    flags_on.add("auth.enforce_verified_writes")
    for path in BARE_SESSION_200_READS:
        r = c.get(path, headers=_h(token))
        assert r.status_code == 200, f"{path} → {r.status_code}"


def test_verified_session_reads_allowed_with_controller(client):
    """The owner's own verified session reads fine after verification."""
    c, token, _ = client
    _mark_controller()
    _sess(token)["verified"] = True
    for path in BARE_SESSION_200_READS:
        r = c.get(path, headers=_h(token))
        assert r.status_code == 200, f"{path} → {r.status_code}"


def test_trade_evaluate_mode_b_read_gated_mode_a_public(client):
    """/api/trade/evaluate: Mode B (league_id + opponent_user_id) prices by
    the caller's board → inline read gate applies. Mode A stays public by
    design and never sees the gate (asserted via a session-less call —
    a gated Mode A would 403/401 here before reaching the engine)."""
    c, token, _ = client
    _mark_controller()

    r = c.post("/api/trade/evaluate", headers=_h(token),
               data=json.dumps({"give_player_ids": ["1"],
                                "receive_player_ids": ["2"],
                                "league_id": "lg1",
                                "opponent_user_id": "opp1"}))
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"

    # Mode A: same trade, no league context, no session header at all.
    with patch.object(server, "_get_universal_pool",
                      return_value=([], {"1": 1500.0, "2": 1500.0})):
        r = c.post("/api/trade/evaluate",
                   headers={"Content-Type": "application/json"},
                   data=json.dumps({"give_player_ids": ["1"],
                                    "receive_player_ids": ["2"]}))
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Two-session end-to-end: owner verifies, squatter's reads die immediately
# ---------------------------------------------------------------------------

def test_owner_verifies_and_squatters_reads_die(client):
    c, token_owner, _ = client
    token_squatter = "sess-read-squatter"
    with server._sessions_lock:
        server._sessions[token_squatter] = {"user_id": UID,
                                            "active_format": "1qb_ppr",
                                            "last_active": 0.0}
    try:
        # Pre-verification: the squatter can read (grace-era behavior).
        assert c.get("/api/tiers/status",
                     headers=_h(token_squatter)).status_code == 200

        # Owner proves control via the Sleeper-JWT link (oracle mocked OK).
        with patch.object(server._sleeper_write, "verify_token_live",
                          MagicMock(return_value={"raw": {}})):
            r = c.post("/api/sleeper/link", headers=_h(token_owner),
                       data=json.dumps({"token": _token()}))
        assert r.get_json()["verified"] is True

        # Squatter's next read 403s — no restart, no session expiry.
        r = c.get("/api/tiers/status", headers=_h(token_squatter))
        assert r.status_code == 403
        assert r.get_json()["error"] == "verification_required"

        # The owner's verified session keeps reading.
        assert c.get("/api/tiers/status",
                     headers=_h(token_owner)).status_code == 200
    finally:
        with server._sessions_lock:
            server._sessions.pop(token_squatter, None)
