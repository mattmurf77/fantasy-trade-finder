"""#318 — dismiss "Awaiting them" trades (POST /api/trades/awaiting/dismiss).

"Awaiting them" is derived state: the caller's live like rows minus matured
matches, deduped by (league_id, frozenset(give), frozenset(receive)).
Dismissal retracts EVERY live like row sharing that key (nullable
trade_decisions.retracted_at; the rows are never rewritten or deleted), so
the trade leaves the caller's Awaiting list, stops feeding the partner's
deck injection, and can never mature into a match. A later re-like writes a
fresh NULL row — that is the revive path.

Covers plan #318 tests 1, 4, 5, 6, 7, 8, 9 plus the frozen response-byte
contract (tests 2 and 3 — the receiver-side query filters — live in
test_trade_match_flow.py beside the queries they filter). Route exercised
through Flask's test client with an injected session against an isolated
in-memory SQLite engine (test_disposition_route.py pattern).
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    load_awaiting_trades,
    load_trade_decisions,
    metadata,
    retract_awaiting_likes,
    swipe_decisions_table,
    trade_decisions_table,
)

LEAGUE = "league_ad"
ME = "user_me"
PARTNER = "user_partner"

GIVE = ["a1", "a2"]
RECEIVE = ["x1"]


def _insert_like(conn, user_id, give, receive, *, league_id=LEAGUE,
                 age_days=1, retracted_at=None):
    created = (datetime.now(timezone.utc).replace(tzinfo=None)
               - timedelta(days=age_days)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, "
        " created_at, retracted_at) "
        "VALUES (:u, :l, :g, :r, 'like', :c, :ra)"
    ), {"u": user_id, "l": league_id, "g": json.dumps(list(give)),
        "r": json.dumps(list(receive)), "c": created, "ra": retracted_at})


def _seed_members(conn):
    """league_members rosters so load_awaiting_trades can resolve the
    counterparty by receive-player ownership."""
    for uid, roster in ((ME, GIVE), (PARTNER, RECEIVE)):
        conn.execute(text(
            "INSERT INTO league_members "
            "(league_id, user_id, username, roster_data, updated_at) "
            "VALUES (:l, :u, :u, :r, :t)"
        ), {"l": LEAGUE, "u": uid, "r": json.dumps(list(roster)),
            "t": "2026-08-13T00:00:00"})


@pytest.fixture()
def harness():
    """Isolated DB + injected session + spies on the partner-deck
    invalidation and the server-fired event."""
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)

    token = "awaiting-dismiss-sess"
    sess = {"verified": True, "user_id": ME, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    invalidate_spy = MagicMock(return_value=1)
    event_spy = MagicMock()

    with patch.object(db_module, "engine", eng), \
         patch.object(server, "_invalidate_trade_jobs", invalidate_spy), \
         patch.object(server, "record_event", event_spy):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, eng, token, invalidate_spy, event_spy
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _post(client, token, body):
    return client.post("/api/trades/awaiting/dismiss", json=body,
                       headers={"X-Session-Token": token})


def _dismiss_body(**over):
    body = {"league_id": LEAGUE, "my_give": GIVE, "my_receive": RECEIVE,
            "partner_id": PARTNER}
    body.update(over)
    return body


# ---------------------------------------------------------------------------
# 1 — a re-liked trade has MULTIPLE rows sharing one key; one dismiss marks
#     them all and the Awaiting list empties
# ---------------------------------------------------------------------------

def test_dismiss_marks_every_duplicate_like_row(harness):
    client, eng, token, _, event_spy = harness
    with eng.begin() as conn:
        _seed_members(conn)
        _insert_like(conn, ME, GIVE, RECEIVE, age_days=2)
        # Re-liked across deck regenerations — different id order, same key.
        _insert_like(conn, ME, list(reversed(GIVE)), RECEIVE, age_days=1)

    assert len(load_awaiting_trades(ME)) == 1   # deduped to one tile

    resp = _post(client, token, _dismiss_body())
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json() == {"status": "ok", "dismissed_likes": 2}

    assert load_awaiting_trades(ME) == []
    # Both rows carry the marker; neither was deleted.
    with eng.connect() as conn:
        rows = conn.execute(select(trade_decisions_table)).fetchall()
    assert len(rows) == 2 and all(r.retracted_at for r in rows)
    # ≥1 row marked → the INTENT event fires with the server-known count.
    event_spy.assert_called_once()
    args, kwargs = event_spy.call_args
    assert args == (ME, "awaiting_trade_dismissed")
    assert kwargs["props"] == {"partner_id": PARTNER, "dismissed_likes": 2}
    assert kwargs["league_id"] == LEAGUE
    assert kwargs["source"] == "api"


# ---------------------------------------------------------------------------
# 4 — idempotent repeat → 200 dismissed_likes: 0, never a 404; and the
#     0-row repeat fires NO phantom intent event
# ---------------------------------------------------------------------------

def test_repeat_dismiss_is_idempotent_200_zero(harness):
    client, eng, token, _, event_spy = harness
    with eng.begin() as conn:
        _seed_members(conn)
        _insert_like(conn, ME, GIVE, RECEIVE)

    assert _post(client, token, _dismiss_body()).status_code == 200
    event_spy.reset_mock()

    resp = _post(client, token, _dismiss_body())
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json() == {"status": "ok", "dismissed_likes": 0}
    assert not event_spy.called

    # Absent key (nothing ever liked) is the same 0-is-ok, not a 404.
    resp = _post(client, token, _dismiss_body(my_give=["ghost"]))
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "dismissed_likes": 0}


# ---------------------------------------------------------------------------
# 5 — a like re-swiped AFTER the dismissal legitimately reappears
# ---------------------------------------------------------------------------

def test_relike_after_dismiss_revives_awaiting(harness):
    client, eng, token, _, _ = harness
    with eng.begin() as conn:
        _seed_members(conn)
        _insert_like(conn, ME, GIVE, RECEIVE, age_days=2)

    _post(client, token, _dismiss_body())
    assert load_awaiting_trades(ME) == []

    # The user likes the same trade again → fresh row, NULL retracted_at.
    with eng.begin() as conn:
        _insert_like(conn, ME, GIVE, RECEIVE, age_days=0)

    awaiting = load_awaiting_trades(ME)
    assert len(awaiting) == 1
    assert awaiting[0]["partner_id"] == PARTNER


# ---------------------------------------------------------------------------
# 6 — no Elo path: dismiss writes NO swipe rows and never rewrites decision
# ---------------------------------------------------------------------------

def test_dismiss_writes_no_swipes_and_keeps_decision(harness):
    client, eng, token, _, _ = harness
    with eng.begin() as conn:
        _seed_members(conn)
        _insert_like(conn, ME, GIVE, RECEIVE)

    _post(client, token, _dismiss_body())

    with eng.connect() as conn:
        swipes = conn.execute(select(swipe_decisions_table)).fetchall()
        decisions = conn.execute(select(trade_decisions_table)).fetchall()
    assert swipes == []
    assert [d.decision for d in decisions] == ["like"]
    assert all(d.retracted_at for d in decisions)


# ---------------------------------------------------------------------------
# 7 — caller-scoped: the partner's OWN like rows (same key, their user_id)
#     are never touched by my dismiss
# ---------------------------------------------------------------------------

def test_dismiss_never_marks_partners_own_rows(harness):
    client, eng, token, _, _ = harness
    with eng.begin() as conn:
        _seed_members(conn)
        _insert_like(conn, ME, GIVE, RECEIVE)
        # Partner liked an unrelated trade involving the same players.
        _insert_like(conn, PARTNER, GIVE, RECEIVE)

    resp = _post(client, token, _dismiss_body())
    assert resp.get_json() == {"status": "ok", "dismissed_likes": 1}

    with eng.connect() as conn:
        rows = conn.execute(select(trade_decisions_table)).fetchall()
    by_user = {r.user_id: r for r in rows}
    assert by_user[ME].retracted_at is not None
    assert by_user[PARTNER].retracted_at is None


# ---------------------------------------------------------------------------
# 8 — the PARTNER's cached deck job is invalidated (never the caller's)
# ---------------------------------------------------------------------------

def test_dismiss_invalidates_partners_deck_job(harness):
    client, eng, token, invalidate_spy, _ = harness
    with eng.begin() as conn:
        _seed_members(conn)
        _insert_like(conn, ME, GIVE, RECEIVE)

    _post(client, token, _dismiss_body())

    invalidate_spy.assert_called_once_with(user_id=PARTNER, league_id=LEAGUE)


# ---------------------------------------------------------------------------
# 9 — the past-decisions load (dismisser's own deck suppression) still sees
#     retracted rows: the dismissed trade must not resurface as a fresh card
# ---------------------------------------------------------------------------

def test_past_decisions_load_still_sees_retracted_rows(harness):
    client, eng, token, _, _ = harness
    with eng.begin() as conn:
        _seed_members(conn)
        _insert_like(conn, ME, GIVE, RECEIVE)

    _post(client, token, _dismiss_body())

    past = load_trade_decisions(user_id=ME, league_id=LEAGUE, since_days=7)
    keys = {(frozenset(td["give_player_ids"]),
             frozenset(td["receive_player_ids"])) for td in past}
    assert (frozenset(GIVE), frozenset(RECEIVE)) in keys


# ---------------------------------------------------------------------------
# Frozen contract bytes — 400 shapes
# ---------------------------------------------------------------------------

_REQUIRED_ERR = {"error": "league_id, my_give, my_receive, "
                          "partner_id are required"}


@pytest.mark.parametrize("missing", ["league_id", "my_give", "my_receive",
                                     "partner_id"])
def test_missing_field_is_400_with_contract_error(harness, missing):
    client, _, token, invalidate_spy, event_spy = harness
    body = _dismiss_body()
    del body[missing]
    resp = _post(client, token, body)
    assert resp.status_code == 400
    assert resp.get_json() == _REQUIRED_ERR
    assert not invalidate_spy.called and not event_spy.called


def test_empty_lists_and_malformed_body_are_400(harness):
    client, _, token, _, _ = harness
    resp = _post(client, token, _dismiss_body(my_give=[]))
    assert resp.status_code == 400
    assert resp.get_json() == _REQUIRED_ERR
    # Malformed JSON body → same 400 (get_json(silent=True) → empty).
    resp = client.post("/api/trades/awaiting/dismiss", data="{not json",
                       content_type="application/json",
                       headers={"X-Session-Token": token})
    assert resp.status_code == 400
    assert resp.get_json() == _REQUIRED_ERR


def test_session_without_user_is_unverified(harness):
    client, _, _, _, _ = harness
    token = "awaiting-dismiss-nouser"
    with server._sessions_lock:
        server._sessions[token] = {"user_id": None, "active_format": "1qb_ppr",
                                   "last_active": 0.0}
    try:
        resp = _post(client, token, _dismiss_body())
    finally:
        with server._sessions_lock:
            server._sessions.pop(token, None)
    assert resp.status_code == 403
    assert resp.get_json() == {"error": "verification_required"}


# ---------------------------------------------------------------------------
# retract_awaiting_likes unit edge — set-equality is order-insensitive but
# never subset/superset
# ---------------------------------------------------------------------------

def test_retract_matches_sets_exactly(harness):
    _, eng, _, _, _ = harness
    with eng.begin() as conn:
        _insert_like(conn, ME, GIVE, RECEIVE)
        _insert_like(conn, ME, GIVE + ["extra"], RECEIVE)   # superset ≠ match

    assert retract_awaiting_likes(ME, LEAGUE, list(reversed(GIVE)),
                                  RECEIVE) == 1
    with eng.connect() as conn:
        rows = conn.execute(select(trade_decisions_table)).fetchall()
    marked = [r for r in rows if r.retracted_at]
    assert len(marked) == 1
    assert set(json.loads(marked[0].give_player_ids)) == set(GIVE)
