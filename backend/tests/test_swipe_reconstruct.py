"""FB-46 — restart-proof trade swipes.

Trade decks live in the per-session TradeService's memory; a Render deploy
(or session re-init) wipes them while the client may still be displaying
the old deck. Before this fix, every swipe on a stale deck failed with
"Unknown trade_id" → the mobile "Swipe didn't save" toast on every card.

Covers POST /api/trades/swipe:
  (a) unknown trade_id + card context in payload → 200, card reconstructed,
      decision recorded + persisted, Elo signal applied
  (b) unknown trade_id, no context (legacy payload) → 400, no crash
  (c) known trade_id (normal path) → 200, unchanged behavior

Same harness style as test_disposition_route.py: Flask test client, real
in-memory session, isolated in-memory SQLite, side-effects mocked.
"""
import json
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.server as server
from backend.database import metadata, trade_decisions_table
from backend.ranking_service import RankingService, Player
from backend.trade_service import TradeService, TradeCard, League, LeagueMember

ME = "user_me"
PARTNER = "user_partner"
LEAGUE = "league_swipe_test"
GIVE = ["g1"]
RECEIVE = ["r1"]
ALL_PIDS = GIVE + RECEIVE


def _players():
    return [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ALL_PIDS]


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    players = _players()
    service = RankingService(players=players)
    trade_svc = TradeService(players={p.id: p for p in players})
    league = League(league_id=LEAGUE, name="Swipe Test League", platform="sleeper",
                    members=[
                        LeagueMember(user_id=ME, username="me", roster=[], elo_ratings={}),
                        LeagueMember(user_id=PARTNER, username="partner", roster=[], elo_ratings={}),
                    ])

    token = "test-token-fb46"
    sess = {
        "user_id":       ME,
        "league":        league,
        "players":       players,
        "services":      {"1qb_ppr": service},
        "service":       service,
        "trade_svcs":    {"1qb_ppr": trade_svc},
        "trade_svc":     trade_svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "save_trade_swipes", MagicMock()), \
         patch.object(server, "record_event", MagicMock()), \
         patch.object(server, "create_notification", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, engine, trade_svc, service, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _swipe(client, token, body):
    return client.post(
        "/api/trades/swipe",
        data=json.dumps(body),
        content_type="application/json",
        headers={"X-Session-Token": token},
    )


def test_unknown_trade_id_with_context_reconstructs(harness):
    client, engine, trade_svc, service, token = harness
    assert trade_svc._trade_cards == {}          # deck lost (restart)

    res = _swipe(client, token, {
        "trade_id":           "stale123",
        "decision":           "like",
        "league_id":          LEAGUE,
        "give_player_ids":    GIVE,
        "receive_player_ids": RECEIVE,
        "target_user_id":     PARTNER,
        "target_username":    "partner",
    })
    assert res.status_code == 200, res.get_data(as_text=True)

    # Card registered + decision recorded in memory
    card = trade_svc._trade_cards["stale123"]
    assert card.decision == "like"
    assert card.give_player_ids == GIVE
    assert card.target_user_id == PARTNER

    # Elo like-signal applied to the ranking service
    assert len(service._trade_swipes) == 1

    # Decision persisted to the DB (real write against the mem engine)
    with engine.connect() as conn:
        rows = conn.execute(select(trade_decisions_table)).fetchall()
    assert len(rows) == 1
    assert rows[0].trade_id == "stale123"
    assert rows[0].decision == "like"


def test_unknown_trade_id_without_context_is_400(harness):
    client, _engine, trade_svc, _service, token = harness

    res = _swipe(client, token, {"trade_id": "stale456", "decision": "pass"})
    assert res.status_code == 400
    assert "Unknown trade_id" in res.get_json()["error"]
    assert "stale456" not in trade_svc._trade_cards


def test_known_trade_id_normal_path_unchanged(harness):
    client, _engine, trade_svc, service, token = harness
    card = TradeCard(
        trade_id="known789", league_id=LEAGUE, proposing_user_id=ME,
        target_user_id=PARTNER, target_username="partner",
        give_player_ids=GIVE, receive_player_ids=RECEIVE,
        mismatch_score=100.0, fairness_score=0.9, composite_score=0.8,
    )
    trade_svc._trade_cards[card.trade_id] = card

    res = _swipe(client, token, {"trade_id": "known789", "decision": "pass"})
    assert res.status_code == 200
    assert trade_svc._trade_cards["known789"].decision == "pass"
    assert len(service._trade_swipes) == 1
