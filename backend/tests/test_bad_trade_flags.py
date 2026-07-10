"""Bad-trade flags (feedback #85) — "this is a bad trade" on the swipe deck.

Covers:
  (a) POST /api/trades/flag persists the full card context — package,
      counterparty, scoring format, and engine telemetry pulled from the
      live in-memory card when trade_id resolves
  (b) telemetry fallback: card gone from the deck → client-echoed values
      are persisted instead
  (c) idempotency: re-flagging the same package (even with player-id order
      shuffled) returns duplicate:true and never double-inserts
  (d) validation (missing sides → 400) and session auth (no token → 401)
  (e) GET /api/trades/flags/admin — CRON_SECRET auth (401 wrong/missing,
      503 fail-closed in prod without secret) and since_id/limit paging,
      mirroring /api/feedback/admin
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata
from backend.ranking_service import Player
from backend.trade_service import League, LeagueMember, TradeCard

ME = "user_me"
SECRET = "unit-test-cron-secret"
TOKEN = "test-token-badflag"

CARD = TradeCard(
    trade_id="t-1",
    league_id="L1",
    proposing_user_id=ME,
    target_user_id="user_them",
    target_username="them",
    give_player_ids=["p1", "p2"],
    receive_player_ids=["p9"],
    mismatch_score=180.0,
    fairness_score=0.82,
    composite_score=61.5,
    partner_fit=0.7,
    need_fit=0.4,
)


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    trade_svc = SimpleNamespace(_trade_cards={CARD.trade_id: CARD})
    league = League(league_id="L1", name="L1", platform="sleeper",
                    members=[LeagueMember(user_id=ME, username="me",
                                          roster=[], elo_ratings={})])
    sess = {
        "user_id":       ME,
        "username":      "me",
        "display_name":  "me",
        "league":        league,
        "players":       [Player(id="p1", name="P1", position="RB",
                                 team="AAA", age=25)],
        "trade_svcs":    {"1qb_ppr": trade_svc},
        "trade_svc":     trade_svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(db_module, "engine", engine):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield client
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


def _flag(client, body=None, token=TOKEN):
    payload = {
        "trade_id":           CARD.trade_id,
        "league_id":          "L1",
        "give_player_ids":    ["p1", "p2"],
        "receive_player_ids": ["p9"],
    }
    if body:
        payload.update(body)
    headers = {"X-Session-Token": token} if token else {}
    return client.post("/api/trades/flag",
                       data=json.dumps(payload),
                       content_type="application/json",
                       headers=headers)


def _admin_items(client, qs=""):
    res = client.get(f"/api/trades/flags/admin{qs}")
    assert res.status_code == 200
    return res.get_json()


# ---------------------------------------------------------------------------
# (a) full-context persistence from the live card
# ---------------------------------------------------------------------------

def test_flag_persists_full_context_from_live_card(harness):
    client = harness
    res = _flag(client)
    assert res.status_code == 201
    body = res.get_json()
    assert body["ok"] is True and body["flag_id"] >= 1
    assert body["duplicate"] is False

    items = _admin_items(client)["items"]
    assert len(items) == 1
    row = items[0]
    assert row["user_id"] == ME
    assert row["username"] == "me"
    assert row["league_id"] == "L1"
    assert row["target_user_id"] == "user_them"
    assert row["target_username"] == "them"
    assert row["give_player_ids"] == ["p1", "p2"]
    assert row["receive_player_ids"] == ["p9"]
    assert row["scoring_format"] == "1qb_ppr"
    assert row["trade_id"] == "t-1"
    # Telemetry came from the in-memory card, not the (absent) client echo.
    assert row["mismatch_score"] == 180.0
    assert row["fairness_score"] == 0.82
    assert row["composite_score"] == 61.5
    assert row["partner_fit"] == 0.7
    assert row["need_fit"] == 0.4
    assert row["basis"] == "divergence"
    assert row["created_at"]


def test_flag_optional_reason_is_persisted_and_truncated(harness):
    client = harness
    res = _flag(client, {"reason": "  engine ignored my QB need " + "x" * 600})
    assert res.status_code == 201
    row = _admin_items(client)["items"][0]
    assert row["reason"].startswith("engine ignored my QB need")
    assert len(row["reason"]) <= 500


# ---------------------------------------------------------------------------
# (b) telemetry fallback when the in-memory card is gone
# ---------------------------------------------------------------------------

def test_flag_falls_back_to_client_telemetry(harness):
    client = harness
    res = _flag(client, {
        "trade_id":        "gone-after-restart",
        "fairness_score":  0.5,
        "basis":           "consensus",
        "target_user_id":  "user_them",
        "target_username": "them",
    })
    assert res.status_code == 201
    row = _admin_items(client)["items"][0]
    assert row["fairness_score"] == 0.5
    assert row["basis"] == "consensus"
    assert row["target_user_id"] == "user_them"
    # Fields the client didn't echo stay null.
    assert row["mismatch_score"] is None
    assert row["composite_score"] is None


# ---------------------------------------------------------------------------
# (c) idempotency — one flag per (user, league, package)
# ---------------------------------------------------------------------------

def test_duplicate_flag_does_not_double_insert(harness):
    client = harness
    first = _flag(client)
    assert first.status_code == 201
    flag_id = first.get_json()["flag_id"]

    dup = _flag(client)
    assert dup.status_code == 200
    dup_body = dup.get_json()
    assert dup_body["duplicate"] is True
    assert dup_body["flag_id"] == flag_id

    # Order-insensitive: shuffled give side is the same package.
    shuffled = _flag(client, {"give_player_ids": ["p2", "p1"]})
    assert shuffled.status_code == 200
    assert shuffled.get_json()["duplicate"] is True

    assert _admin_items(client)["count"] == 1


def test_different_package_is_a_new_flag(harness):
    client = harness
    assert _flag(client).status_code == 201
    other = _flag(client, {"trade_id": "t-2",
                           "give_player_ids": ["p3"],
                           "receive_player_ids": ["p9"]})
    assert other.status_code == 201
    assert _admin_items(client)["count"] == 2


# ---------------------------------------------------------------------------
# (d) validation + session auth
# ---------------------------------------------------------------------------

def test_missing_sides_are_400(harness):
    client = harness
    res = _flag(client, {"give_player_ids": []})
    assert res.status_code == 400
    assert res.get_json()["field"] == "give_player_ids"

    res2 = _flag(client, {"receive_player_ids": None})
    assert res2.status_code == 400
    assert res2.get_json()["field"] == "receive_player_ids"


def test_flag_requires_session(harness):
    client = harness
    res = _flag(client, token=None)
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# (e) admin readback — auth + paging
# ---------------------------------------------------------------------------

def test_admin_auth_401_and_503(harness):
    client = harness
    with patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True):
        assert client.get("/api/trades/flags/admin").status_code == 401
        assert client.get("/api/trades/flags/admin",
                          headers={"X-Cron-Secret": "wrong"}).status_code == 401
        ok = client.get("/api/trades/flags/admin",
                        headers={"X-Cron-Secret": SECRET})
        assert ok.status_code == 200

    # Prod misconfig (secret unset) fails closed.
    with patch.object(server, "_CRON_SECRET", ""), \
         patch.object(server, "_IS_PROD_ENV", True):
        assert client.get("/api/trades/flags/admin").status_code == 503


def test_admin_paging_since_id_and_limit(harness):
    client = harness
    for i in range(3):
        assert _flag(client, {"trade_id": f"t-{i}",
                              "give_player_ids": [f"g{i}"],
                              "receive_player_ids": [f"r{i}"]}).status_code == 201

    page1 = _admin_items(client, "?since_id=0&limit=2")
    assert page1["count"] == 2
    assert [it["id"] for it in page1["items"]] == sorted(
        it["id"] for it in page1["items"])          # oldest first
    cursor = page1["next_since_id"]
    assert cursor == page1["items"][-1]["id"]

    page2 = _admin_items(client, f"?since_id={cursor}&limit=2")
    assert page2["count"] == 1
    assert page2["items"][0]["id"] > cursor

    # Empty page echoes the input cursor back.
    page3 = _admin_items(client, f"?since_id={page2['next_since_id']}")
    assert page3["count"] == 0
    assert page3["next_since_id"] == page2["next_since_id"]
