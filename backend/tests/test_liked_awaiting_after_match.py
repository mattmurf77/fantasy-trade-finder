"""A like that completes a match is not "awaiting"; Awaiting tiles carry chips.

Release sim pass, 2026-11-22 (branch fix/deck-match-moment-and-labels):

  A. Account M liked a deck card the other owner had already liked (the
     mirror). The swipe created the mutual match, yet the deck kept saying
     "1 liked trade awaiting their swipe". That line is the length of
     GET /api/trades/liked, which returned every in-session card with
     decision == 'like' — matched or not. The route now drops a card whose
     package has a trade_matches row (same league, same player sets, either
     orientation, any status), the rule load_awaiting_trades already applies.

  C4. Matches > Awaiting rendered every asset with an "FLX" position chip and
     team "FA" (picks and a real QB alike) while the mutual cards beside them
     showed the real values. GET /api/trades/matches/all ships
     my_give_teams / my_give_positions (and the receive pair); the awaiting
     route never did, so the client's adapter fell back. It now ships the
     same four parallel arrays, built the same way.

Flask test client, injected session, isolated in-memory SQLite (the
test_pick_labels_in_matches.py harness pattern). No network, no live DB.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    matched_package_keys,
    metadata,
    players_table,
    trade_matches_table,
)
from backend.trade_service import TradeCard

LEAGUE = "league_lam"
ME = "user_me"
PARTNER = "user_partner"

QB = "4881"        # a real QB
RB = "6790"
WR = "4034"
PICK = f"{LEAGUE}_2027_1_3"


def _seed_players(conn):
    for pid, name, pos, team in (
        (QB, "Lamar Jackson", "QB", "BAL"),
        (RB, "Bijan Robinson", "RB", "ATL"),
        (WR, "Ja'Marr Chase", "WR", "CIN"),
    ):
        conn.execute(insert(players_table).values(
            player_id=pid, full_name=name, position=pos, team=team))


def _seed_members(conn):
    for uid, roster in ((ME, [QB, WR]), (PARTNER, [RB])):
        conn.execute(text(
            "INSERT INTO league_members "
            "(league_id, user_id, username, roster_data, updated_at) "
            "VALUES (:l, :u, :u, :r, :t)"
        ), {"l": LEAGUE, "u": uid, "r": json.dumps(roster),
            "t": "2026-11-22T00:00:00"})


def _seed_pick(conn):
    conn.execute(text(
        "INSERT INTO draft_picks "
        "(pick_id, league_id, season, round, owner_user_id, "
        " original_roster_id, is_traded, platform) "
        "VALUES (:p, :l, 2027, 1, :o, '3', 0, 'sleeper')"
    ), {"p": PICK, "l": LEAGUE, "o": ME})


def _insert_like(conn, give, receive):
    created = (datetime.now(timezone.utc).replace(tzinfo=None)
               - timedelta(days=1)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, "
        " created_at, retracted_at) "
        "VALUES (:u, :l, :g, :r, 'like', :c, NULL)"
    ), {"u": ME, "l": LEAGUE, "g": json.dumps(list(give)),
        "r": json.dumps(list(receive)), "c": created})


def _insert_match(conn, *, user_a, user_b, a_give, a_receive):
    conn.execute(insert(trade_matches_table).values(
        league_id      = LEAGUE,
        user_a_id      = user_a,
        user_b_id      = user_b,
        user_a_give    = json.dumps(list(a_give)),
        user_a_receive = json.dumps(list(a_receive)),
        matched_at     = "2026-11-22T00:00:00",
        status         = "pending",
    ))


def _card(trade_id, give, receive):
    c = TradeCard(
        trade_id           = trade_id,
        league_id          = LEAGUE,
        proposing_user_id  = ME,
        target_user_id     = PARTNER,
        target_username    = "partner",
        give_player_ids    = list(give),
        receive_player_ids = list(receive),
        mismatch_score     = 120.0,
        fairness_score     = 0.9,
        composite_score    = 1.0,
    )
    c.decision = "like"
    return c


@pytest.fixture()
def harness():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with eng.begin() as conn:
        _seed_players(conn)
        _seed_members(conn)

    svc = MagicMock()
    svc.get_liked_trades.return_value = []
    token = "liked-awaiting-after-match"
    sess = {"verified": True,
        "user_id":       ME,
        "league":        SimpleNamespace(league_id=LEAGUE),
        "players":       [SimpleNamespace(id=pid, name=pid) for pid in (QB, RB, WR)],
        "trade_svcs":    {"1qb_ppr": svc},
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db_module, "engine", eng), \
         patch.object(server, "trade_card_to_dict",
                      lambda c, _pd: {"trade_id": c.trade_id}):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, eng, token, svc
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _get(client, token, path):
    r = client.get(path, headers={"X-Session-Token": token})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


# ---------------------------------------------------------------------------
# A — /api/trades/liked drops a like that matured into a match
# ---------------------------------------------------------------------------

def test_liked_excludes_a_like_that_formed_a_match_as_user_a(harness):
    client, eng, token, svc = harness
    matched = _card("t_matched", [QB], [RB])
    waiting = _card("t_waiting", [WR], [RB])
    svc.get_liked_trades.return_value = [matched, waiting]
    with eng.begin() as conn:
        # The swipe route writes the liker as user_a (create_trade_match).
        _insert_match(conn, user_a=ME, user_b=PARTNER, a_give=[QB], a_receive=[RB])
    body = _get(client, token, "/api/trades/liked")
    assert [c["trade_id"] for c in body] == ["t_waiting"]


def test_liked_excludes_a_match_the_partner_completed(harness):
    """The partner liked second, so they are user_a and the package is
    mirrored in the row. Set order inside a side does not matter."""
    client, eng, token, svc = harness
    svc.get_liked_trades.return_value = [_card("t_m", [WR, QB], [RB])]
    with eng.begin() as conn:
        _insert_match(conn, user_a=PARTNER, user_b=ME, a_give=[RB], a_receive=[QB, WR])
    assert _get(client, token, "/api/trades/liked") == []


def test_liked_keeps_every_like_when_nothing_matched(harness):
    client, eng, token, svc = harness
    svc.get_liked_trades.return_value = [_card("t1", [QB], [RB]), _card("t2", [WR], [RB])]
    with eng.begin() as conn:
        # A match on a DIFFERENT package (the mirror direction) leaves both.
        _insert_match(conn, user_a=ME, user_b=PARTNER, a_give=[RB], a_receive=[QB])
    assert [c["trade_id"] for c in _get(client, token, "/api/trades/liked")] == ["t1", "t2"]


def test_matched_package_keys_reads_both_orientations(harness):
    _client, eng, _token, _svc = harness
    with eng.begin() as conn:
        _insert_match(conn, user_a=ME, user_b=PARTNER, a_give=[QB], a_receive=[RB])
        _insert_match(conn, user_a=PARTNER, user_b=ME, a_give=[RB], a_receive=[WR])
    assert matched_package_keys(ME, {LEAGUE}) == {
        (LEAGUE, frozenset([QB]), frozenset([RB])),
        (LEAGUE, frozenset([WR]), frozenset([RB])),
    }
    assert matched_package_keys(ME, set()) == set()


# ---------------------------------------------------------------------------
# C4 — /api/trades/awaiting ships team + position like /matches/all
# ---------------------------------------------------------------------------

def test_awaiting_ships_team_and_position_arrays(harness):
    client, eng, token, _svc = harness
    with eng.begin() as conn:
        _seed_pick(conn)
        _insert_like(conn, [QB, PICK], [RB])
    row = _get(client, token, "/api/trades/awaiting")[0]
    assert row["my_give_positions"] == ["QB", ""]
    assert row["my_give_teams"] == ["BAL", ""]
    assert row["my_receive_positions"] == ["RB"]
    assert row["my_receive_teams"] == ["ATL"]
    # Index-parallel with the id arrays, like every other enrichment.
    for side in ("give", "receive"):
        n = len(row[f"my_{side}"])
        assert len(row[f"my_{side}_teams"]) == n
        assert len(row[f"my_{side}_positions"]) == n


def test_awaiting_and_matches_all_enrich_alike(harness):
    """The two Matches segments render through parallel adapters, so the
    same asset must carry the same chip on both."""
    client, eng, token, _svc = harness
    with eng.begin() as conn:
        _insert_like(conn, [QB], [RB])
        _insert_match(conn, user_a=ME, user_b=PARTNER, a_give=[WR], a_receive=[RB])
    aw = _get(client, token, "/api/trades/awaiting")[0]
    m = _get(client, token, "/api/trades/matches/all")[0]
    assert aw["my_receive_positions"] == m["my_receive_positions"] == ["RB"]
    assert aw["my_receive_teams"] == m["my_receive_teams"] == ["ATL"]
