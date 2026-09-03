"""End-to-end tests for the "Send in Sleeper" routes in backend/server.py:

  POST/GET/DELETE /api/sleeper/link   — link, status, disconnect
  POST /api/trades/propose            — send a trade to Sleeper

Exercised through Flask's test client against an isolated in-memory SQLite DB,
with a real injected session and a real encryption key. The one thing mocked is
the network: `_sleeper_get` (roster lookup), `sleeper_write.propose_trade`
(the actual Sleeper call), and `sleeper_write.verify_token_live` (the P1
verification oracle probe) — so nothing here touches Sleeper or the ToS-adverse
endpoint. The flag is forced on via a patched `is_enabled`.

Pick sends (#413): every `_sleeper_get` stub here is a single `return_value`
(the rosters list), and `_fetch_sleeper_traded_picks` also rides `_sleeper_get`
— so pick tests patch `server.load_draft_picks` (the grid) and
`server._fetch_sleeper_traded_picks` (the holder overlay) DIRECTLY, and the
route must reach neither on a pick-free send (T-10 pins that).

Account-auth P1 contract (docs/plans/account-auth-plan-2026-07-11.md):
POST /api/sleeper/link requires the token claim to match the session user
(so USER == SLEEPER_UID here) and marks the session verified on oracle
success; POST /api/trades/propose is hard-gated on that verified state.
The verification matrix itself lives in test_verified_sessions.py.
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

SLEEPER_UID = "313560442465169408"
# P1: the link route 403s unless the JWT's user_id claim == session user_id.
USER = SLEEPER_UID
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
         patch.object(server._sleeper_write, "verify_token_live",
                      MagicMock(return_value={"raw": {}})), \
         patch.object(server, "touch_user_activity", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _mark_verified(token):
    """Simulate a session that verified earlier (for propose tests that never
    POST /api/sleeper/link — the P1 gate runs before the credential checks)."""
    with server._sessions_lock:
        server._sessions[token]["verified"] = True


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
    _mark_verified(token)   # e.g. verified earlier, then unlinked
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
                      MagicMock(side_effect=SleeperAuthError("dead", detail="HTTP 403"))):
        r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
            "league_id": LEAGUE, "their_roster_id": 2,
            "give_player_ids": ["1"], "receive_player_ids": ["2"]}))
    # Sleeper rejected the write → `sleeper_rejected` (NOT `sleeper_expired`,
    # which the client would try to fix by reconnecting the same token). The
    # rejection reason is surfaced so the client can show it.
    body = r.get_json()
    assert r.status_code == 409 and body["error"] == "sleeper_rejected"
    assert body.get("detail") == "HTTP 403"
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
    _mark_verified(token)
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


def _trade_sent_rows():
    """user_events rows of type trade_sent in the patched test engine
    (taxonomy addendum 2026-08-11 — send-leg completion event)."""
    from sqlalchemy import select
    with db_module.engine.connect() as conn:
        rows = conn.execute(
            select(db_module.user_events_table)
            .where(db_module.user_events_table.c.event_type == "trade_sent")
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def _send_succeeded_rows():
    """user_events rows of type sleeper_send_succeeded (P0-7 server-fired)."""
    from sqlalchemy import select
    with db_module.engine.connect() as conn:
        rows = conn.execute(
            select(db_module.user_events_table)
            .where(db_module.user_events_table.c.event_type == "sleeper_send_succeeded")
        ).fetchall()
    return [dict(r._mapping) for r in rows]


# ── #413 — draft picks in the mixed arrays ────────────────────────────────
# Fixture shapes per docs/feedback/items/413-sleeper-send-draft-picks/lld-delta.md
# §7.2: rosters 1 = me, 2 = them; the grid holds my 2027 2nd (orig 1), roster
# 7's 2027 1st, and their 2026 1st (orig 2); traded_picks says roster 7's
# 2027 1st is now held by roster 1 (me).

ROSTERS_1V2 = [{"owner_id": SLEEPER_UID, "roster_id": 1}, {"owner_id": "opp", "roster_id": 2}]
GRID = [  # load_draft_picks rows — only the keys the encoder reads
    {"pick_id": f"{LEAGUE}_2027_2_1", "season": 2027, "round": 2, "original_roster_id": "1"},
    {"pick_id": f"{LEAGUE}_2027_1_7", "season": 2027, "round": 1, "original_roster_id": "7"},
    {"pick_id": f"{LEAGUE}_2026_1_2", "season": 2026, "round": 1, "original_roster_id": "2"},
]
TRADED = [{"season": "2027", "round": 1, "roster_id": 7, "owner_id": 1, "previous_owner_id": 7}]
MY_2027_2ND = f"{LEAGUE}_2027_2_1"
MY_ACQUIRED_2027_1ST = f"{LEAGUE}_2027_1_7"
THEIR_2026_1ST = f"{LEAGUE}_2026_1_2"
T3_BODY = {"give_player_ids": ["100", "101", MY_2027_2ND], "receive_player_ids": ["200"]}


def _propose(client, body, *, grid=GRID, traded=TRADED, fake=None, deck_outcome=None):
    """Link, then POST /api/trades/propose with the pick ground truth patched
    directly (never through `_sleeper_get`). Returns (response, propose_trade
    mock, load_draft_picks mock, _fetch_sleeper_traded_picks mock)."""
    c, token = client
    c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    fake = fake or MagicMock(return_value={"transaction_id": "TX9", "status": "proposed", "raw": {}})
    grid_mock = MagicMock(return_value=grid)
    traded_mock = MagicMock(return_value=traded)
    patches = [
        patch.object(server, "_sleeper_get", return_value=ROSTERS_1V2),
        patch.object(server._sleeper_write, "propose_trade", fake),
        patch.object(server, "load_draft_picks", grid_mock),
        patch.object(server, "_fetch_sleeper_traded_picks", traded_mock),
    ]
    if deck_outcome is not None:
        patches.append(patch.object(server, "_save_deck_outcome_safe", deck_outcome))
    for pt in patches:
        pt.start()
    try:
        r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps({
            "league_id": LEAGUE, "their_roster_id": 2, **body}))
    finally:
        for pt in reversed(patches):
            pt.stop()
    return r, fake, grid_mock, traded_mock


def test_propose_success_fires_no_trade_sent_on_sleeper(client):
    """T-3 — Analytics dedup (MFL merge, 2026-08-11): a confirmed Sleeper send
    is measured by `sleeper_send_succeeded` (P0-7, funnel stage 8 — covered in
    test_analytics_p0.py) and must NOT also land a `trade_sent` row —
    one event per real occurrence. `trade_sent` is the non-Sleeper
    confirmed-send event (POST /api/trades/propose-mfl only).

    #413 fixture fix: the pick rides `give_player_ids` (as every mount sends
    it) — the old `"draft_picks": ["2027_1"]` was a string the adapter would
    reject and passed only because `propose_trade` is mocked. The adapter
    must now receive players-only arrays plus the server-encoded pick."""
    r, fake, _, _ = _propose(client, T3_BODY)
    assert r.status_code == 200, r.get_data(as_text=True)
    sent_req = fake.call_args[0][1]
    assert sent_req.give_player_ids == ["100", "101"]
    assert sent_req.receive_player_ids == ["200"]
    assert sent_req.draft_picks == ["1,2027,2,1,2"]
    assert _trade_sent_rows() == []


def test_propose_success_labels_impression_propose(client):
    """T-3b — the positive spine assertion: a successful pick send still labels
    its impression `propose` exactly once. Without this, deleting the
    `_save_deck_outcome_safe` call would pass every negative test (T-11)."""
    outcome = MagicMock()
    r, _, _, _ = _propose(client, {**T3_BODY, "impression_id": "imp-1"},
                          deck_outcome=outcome)
    assert r.status_code == 200, r.get_data(as_text=True)
    outcome.assert_called_once_with("imp-1", "propose", acting_user_id=USER)


def test_propose_encodes_give_pick_from_to(client):
    """T-4 — give side: orig = the grid row's original roster, from = my
    roster, to = theirs."""
    r, fake, _, _ = _propose(client, {"give_player_ids": [MY_2027_2ND],
                                      "receive_player_ids": ["200"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert fake.call_args[0][1].draft_picks == ["1,2027,2,1,2"]


def test_propose_encodes_receive_pick_flips_from_to(client):
    """T-5 — receive side: from = THEIR roster, to = mine (orig 2 = them)."""
    r, fake, _, _ = _propose(client, {"give_player_ids": ["100"],
                                      "receive_player_ids": [THEIR_2026_1ST]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert fake.call_args[0][1].draft_picks == ["2,2026,1,2,1"]


def test_propose_acquired_pick_uses_traded_picks_holder(client):
    """T-6 — roster 7's 2027 1st is held by me per traded_picks, so giving it
    encodes (orig stays 7; from = me); the default-holder rule alone would
    have refused it as not_owned."""
    r, fake, _, _ = _propose(client, {"give_player_ids": [MY_ACQUIRED_2027_1ST],
                                      "receive_player_ids": ["200"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert fake.call_args[0][1].draft_picks == ["7,2027,1,1,2"]


def test_propose_hard_blocks_generic_pick(client):
    """T-7 — a generic rung names no real pick: 422 sleeper_pick_unmapped
    listing every failing id from BOTH sides (give-then-receive), `detail`
    byte-equal to `message` (fielded builds render `detail`), and the
    players are NOT sent without the picks."""
    r, fake, _, _ = _propose(client, {
        "give_player_ids": ["100", "generic_pick_1_early"],
        "receive_player_ids": ["200", "generic_pick_2_mid"]})
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "sleeper_pick_unmapped"
    assert body["picks"] == ["generic_pick_1_early", "generic_pick_2_mid"]
    assert body["detail"] == body["message"]
    assert "Early 1st" in body["message"]
    fake.assert_not_called()


def test_propose_hard_blocks_pick_missing_from_grid(client):
    """T-8 — a well-formed owned-pick id with no grid row (beyond the horizon,
    completed draft, phantom season…) is unmapped; existence is the grid,
    never inferred from the rosters list."""
    phantom = f"{LEAGUE}_2031_1_1"
    r, fake, _, _ = _propose(client, {"give_player_ids": [phantom],
                                      "receive_player_ids": ["200"]})
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "sleeper_pick_unmapped" and body["picks"] == [phantom]
    fake.assert_not_called()


def test_propose_hard_blocks_pick_not_owned(client):
    """T-9 — live traded_picks says my 2027 2nd is now held by roster 9: 422
    sleeper_pick_not_owned, `detail == message`, nothing sent."""
    traded = [{"season": "2027", "round": 2, "roster_id": 1, "owner_id": 9,
               "previous_owner_id": 1}]
    r, fake, _, _ = _propose(client, {"give_player_ids": [MY_2027_2ND],
                                      "receive_player_ids": ["200"]},
                             traded=traded)
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "sleeper_pick_not_owned"
    assert body["picks"] == [MY_2027_2ND]
    assert body["detail"] == body["message"]
    fake.assert_not_called()


def test_propose_pick_free_send_makes_no_traded_picks_fetch(client):
    """T-10 — the byte-identical player-only path: neither the grid read nor
    the traded_picks fetch happens when the trade carries no pick."""
    r, fake, grid_mock, traded_mock = _propose(client, {
        "give_player_ids": ["100"], "receive_player_ids": ["200"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    grid_mock.assert_not_called()
    traded_mock.assert_not_called()
    assert fake.call_args[0][1].draft_picks is None


def test_propose_422_fires_no_success_event_and_no_deck_outcome(client):
    """T-11 — a refusal is invisible to the success spine: no
    sleeper_send_succeeded row, no `propose` deck-outcome label, even with an
    impression_id present."""
    outcome = MagicMock()
    r, fake, _, _ = _propose(client, {
        "give_player_ids": ["100", "generic_pick_1_early"],
        "receive_player_ids": ["200", "generic_pick_2_mid"],
        "impression_id": "imp-1"}, deck_outcome=outcome)
    assert r.status_code == 422
    assert _send_succeeded_rows() == []
    outcome.assert_not_called()
    fake.assert_not_called()


def test_propose_rejects_client_supplied_draft_picks(client):
    """T-12 — the client never encodes: a non-empty `draft_picks` body key is
    400 bad_request (with message/detail); an empty list is accepted."""
    r, fake, _, _ = _propose(client, {"give_player_ids": ["100"],
                                      "receive_player_ids": ["200"],
                                      "draft_picks": ["1,2027,2,1,2"]})
    assert r.status_code == 400, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "bad_request"
    assert body["detail"] == body["message"] and "draft_picks" in body["message"]
    fake.assert_not_called()

    r, fake, _, _ = _propose(client, {"give_player_ids": ["100"],
                                      "receive_player_ids": ["200"],
                                      "draft_picks": []})
    assert r.status_code == 200, r.get_data(as_text=True)
    fake.assert_called_once()


def test_propose_success_pick_n_honest(client):
    """T-13 — sleeper_send_succeeded props count players in give_n/receive_n
    and encoded picks in pick_n (before #413 the pick was a "player" and
    pick_n was structurally 0)."""
    r, _, _, _ = _propose(client, T3_BODY)
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = _send_succeeded_rows()
    assert len(rows) == 1
    props = json.loads(rows[0]["props"])
    assert props == {"give_n": 2, "receive_n": 1, "pick_n": 1,
                     "from_deck": False, "transaction_id": "TX9"}


def test_propose_reports_unmapped_before_not_owned(client):
    """T-14 — an unmappable pick has no holder to check: with one generic rung
    and one traded-away pick, the 422 is unmapped and lists ONLY the rung."""
    traded = [{"season": "2027", "round": 2, "roster_id": 1, "owner_id": 9,
               "previous_owner_id": 1}]
    r, fake, _, _ = _propose(client, {
        "give_player_ids": ["generic_pick_1_early", MY_2027_2ND],
        "receive_player_ids": ["200"]}, traded=traded)
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "sleeper_pick_unmapped"
    assert body["picks"] == ["generic_pick_1_early"]
    fake.assert_not_called()


def test_propose_failure_fires_no_trade_sent(client):
    """trade_sent is confirmed-success only — a Sleeper write failure (502)
    must not land a row."""
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
    assert r.status_code == 502
    assert _trade_sent_rows() == []


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
