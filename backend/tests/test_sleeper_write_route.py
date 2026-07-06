"""End-to-end tests for the "Send in Sleeper" routes in backend/server.py:

  POST/GET/DELETE /api/sleeper/link   — link, status, disconnect
  POST /api/trades/propose            — send a trade to Sleeper

Exercised through Flask's test client against an isolated in-memory SQLite DB,
with a real injected session and a real encryption key. The one thing mocked is
the network: `_sleeper_get` (roster lookup) and `sleeper_write.propose_trade`
(the actual Sleeper call) — so nothing here touches Sleeper or the ToS-adverse
endpoint. The flag is forced on via a patched `is_enabled`.
"""
import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata
from backend.sleeper_write import SleeperAuthError

USER = "user_me"
SLEEPER_UID = "313560442465169408"
LEAGUE = "1312140920132497408"


def _fake_jwt(claims):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'HS256'})}.{b64(claims)}.sig"


def _token(exp_offset=3600):
    return _fake_jwt({"user_id": SLEEPER_UID, "exp": int(time.time()) + exp_offset})


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "sess-tok"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k == "trade.send_in_sleeper"), \
         patch.object(server, "touch_user_activity", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def test_link_status_unlink_round_trip(client):
    c, token = client
    r = c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["connected"] is True
    assert body["sleeper_user_id"] == SLEEPER_UID

    r = c.get("/api/sleeper/link", headers=_h(token))
    assert r.get_json() == {**r.get_json(), "connected": True, "expired": False}

    r = c.delete("/api/sleeper/link", headers=_h(token))
    assert r.get_json()["connected"] is False
    assert c.get("/api/sleeper/link", headers=_h(token)).get_json()["connected"] is False


def test_link_rejects_expired_and_malformed(client):
    c, token = client
    r = c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token(-10)}))
    assert r.status_code == 400 and r.get_json()["error"] == "token_expired"

    r = c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": "nope"}))
    assert r.status_code == 400 and r.get_json()["error"] == "invalid_token"


def test_propose_happy_path_resolves_my_roster(client):
    c, token = client
    c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    rosters = [{"owner_id": SLEEPER_UID, "roster_id": 1}, {"owner_id": "other", "roster_id": 2}]
    fake = MagicMock(return_value={"transaction_id": "TX1", "status": "proposed", "raw": {}})
    with patch.object(server, "_sleeper_get", return_value=rosters), \
         patch.object(server._sleeper_write, "propose_trade", fake):
        r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
            "league_id": LEAGUE, "their_roster_id": 2,
            "give_player_ids": ["100"], "receive_player_ids": ["200"],
        }))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["transaction_id"] == "TX1"
    # server resolved MY roster (1) authoritatively; client only sent theirs (2)
    sent_req = fake.call_args[0][1]
    assert sent_req.my_roster_id == 1 and sent_req.their_roster_id == 2


def test_propose_resolves_their_roster_from_user_id(client):
    c, token = client
    c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    rosters = [{"owner_id": SLEEPER_UID, "roster_id": 1}, {"owner_id": "opp_uid", "roster_id": 7}]
    fake = MagicMock(return_value={"transaction_id": "TX2", "status": "proposed", "raw": {}})
    with patch.object(server, "_sleeper_get", return_value=rosters), \
         patch.object(server._sleeper_write, "propose_trade", fake):
        r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
            "league_id": LEAGUE, "their_user_id": "opp_uid",   # no roster_id — resolve it
            "give_player_ids": ["100"], "receive_player_ids": ["200"],
        }))
    assert r.status_code == 200, r.get_data(as_text=True)
    sent_req = fake.call_args[0][1]
    assert sent_req.my_roster_id == 1 and sent_req.their_roster_id == 7


def test_propose_unknown_opponent_returns_400(client):
    c, token = client
    c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    rosters = [{"owner_id": SLEEPER_UID, "roster_id": 1}]   # opponent not in league
    with patch.object(server, "_sleeper_get", return_value=rosters):
        r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
            "league_id": LEAGUE, "their_user_id": "ghost",
            "give_player_ids": ["100"], "receive_player_ids": ["200"]}))
    assert r.status_code == 400 and r.get_json()["error"] == "opponent_roster_not_found"


def test_propose_not_linked_returns_409(client):
    c, token = client
    r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
        "league_id": LEAGUE, "their_roster_id": 2,
        "give_player_ids": ["1"], "receive_player_ids": ["2"]}))
    assert r.status_code == 409 and r.get_json()["error"] == "sleeper_not_linked"


def test_propose_auth_error_drops_credential(client):
    c, token = client
    c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    rosters = [{"owner_id": SLEEPER_UID, "roster_id": 1}]
    with patch.object(server, "_sleeper_get", return_value=rosters), \
         patch.object(server._sleeper_write, "propose_trade",
                      MagicMock(side_effect=SleeperAuthError("dead"))):
        r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
            "league_id": LEAGUE, "their_roster_id": 2,
            "give_player_ids": ["1"], "receive_player_ids": ["2"]}))
    assert r.status_code == 409 and r.get_json()["error"] == "sleeper_expired"
    # dead token was cleared → now shows disconnected
    assert c.get("/api/sleeper/link", headers=_h(token)).get_json()["connected"] is False


def test_feature_off_returns_404(client):
    c, token = client
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
        assert r.status_code == 404
        r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
            "league_id": LEAGUE, "their_roster_id": 2,
            "give_player_ids": ["1"], "receive_player_ids": ["2"]}))
        assert r.status_code == 404


# ── Error-contract coverage ──────────────────────────────────────────────
# Each branch below maps to a specific client behavior in SendInSleeperButton
# (reconnect prompt / deep-link fallback / "unavailable" alert). Locking them
# so a route refactor can't silently break the mobile handling.

def test_link_post_without_key_returns_503(client):
    """No SLEEPER_TOKEN_KEY → POST link fails closed (client shows 'unavailable',
    never stores a plaintext token)."""
    c, token = client
    with patch.object(server._sleeper_write, "token_encryption_available", lambda: False):
        r = c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    assert r.status_code == 503 and r.get_json()["error"] == "sleeper_unconfigured"


def test_propose_bad_request(client):
    """Non-numeric league_id, or neither their_user_id nor their_roster_id → 400
    bad_request (checked before the linked-credential gate)."""
    c, token = client
    r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
        "league_id": "not-a-number", "their_roster_id": 2,
        "give_player_ids": ["1"], "receive_player_ids": ["2"]}))
    assert r.status_code == 400 and r.get_json()["error"] == "bad_request"

    r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
        "league_id": LEAGUE,   # no their_user_id AND no their_roster_id
        "give_player_ids": ["1"], "receive_player_ids": ["2"]}))
    assert r.status_code == 400 and r.get_json()["error"] == "bad_request"


def test_propose_expired_stored_token_returns_409_and_clears(client):
    """The common real case: token aged out between sessions. Pre-flight
    is_expired catches it → 409 sleeper_expired (client → reconnect) and the
    dead credential is dropped."""
    c, token = client
    c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    # Overwrite the stored credential with an already-expired token (can't link
    # one directly — the POST route rejects expired tokens up front).
    expired_ct = server._sleeper_write.encrypt_token(_token(-10))
    server.upsert_sleeper_credential(USER, SLEEPER_UID, expired_ct, None)

    r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
        "league_id": LEAGUE, "their_roster_id": 2,
        "give_player_ids": ["1"], "receive_player_ids": ["2"]}))
    assert r.status_code == 409 and r.get_json()["error"] == "sleeper_expired"
    assert c.get("/api/sleeper/link", headers=_h(token)).get_json()["connected"] is False


def test_propose_write_failure_returns_502(client):
    """A non-auth Sleeper failure (network / GraphQL error) → 502
    sleeper_write_failed, which the client maps to the deep-link fallback."""
    from backend.sleeper_write import SleeperWriteError
    c, token = client
    c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    rosters = [{"owner_id": SLEEPER_UID, "roster_id": 1}, {"owner_id": "opp", "roster_id": 2}]
    with patch.object(server, "_sleeper_get", return_value=rosters), \
         patch.object(server._sleeper_write, "propose_trade",
                      MagicMock(side_effect=SleeperWriteError("boom", kind="network"))):
        r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
            "league_id": LEAGUE, "their_roster_id": 2,
            "give_player_ids": ["1"], "receive_player_ids": ["2"]}))
    assert r.status_code == 502 and r.get_json()["error"] == "sleeper_write_failed"


def test_propose_roster_fetch_failure_degrades_gracefully(client):
    """A transient rosters-fetch failure must not 500 — it degrades to a
    structured 400 (client → deep-link fallback), never an unhandled crash."""
    c, token = client
    c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    with patch.object(server, "_sleeper_get", side_effect=Exception("network")):
        r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
            "league_id": LEAGUE, "their_roster_id": 2,
            "give_player_ids": ["1"], "receive_player_ids": ["2"]}))
    assert r.status_code == 400 and r.get_json()["error"] == "roster_not_found"


def test_link_get_reports_expired_flag(client):
    """GET surfaces an expired-but-still-stored credential as expired:true so the
    client can prompt a proactive reconnect before the user even taps Send."""
    c, token = client
    c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    ct = server._sleeper_write.encrypt_token(_token())
    server.upsert_sleeper_credential(USER, SLEEPER_UID, ct, "2000-01-01T00:00:00+00:00")
    body = c.get("/api/sleeper/link", headers=_h(token)).get_json()
    assert body["connected"] is True and body["expired"] is True
