"""FB-01 — Matches accept/decline reliability + cross-league correctness.

Covers the disposition route (`backend/server.py` `disposition_trade_match`):

  (a) same-league accept   → 200, in-memory ELO applied, decision persisted
  (b) cross-league accept  → 200, in-memory ELO NOT applied to the active
                              service, but decision still persisted (replays
                              on the other league's next session_init)
  (c) decline              → 200, decision persisted
  (d) already-decided      → 409
  (e) not-found            → 404

All five must return the documented status WITHOUT raising — the whole point
of FB-01 is that a tap never turns into a bare 500 "Action failed".

The route is exercised through Flask's test client with a real in-memory
session and a real RankingService, against an isolated in-memory SQLite DB so
`record_match_disposition` runs for real. The DB-write / push / notification
side-effects are mocked so the test stays focused on routing + ELO placement.
"""
import json
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.server as server
from backend.database import metadata, trade_matches_table
from backend.ranking_service import RankingService, Player
from backend.trade_service import League, LeagueMember


ACTIVE_LEAGUE = "league_active"
OTHER_LEAGUE = "league_other"
ME = "user_me"
PARTNER = "user_partner"

# Player IDs used by the matches. user_a gives [g1,g2], receives [r1,r2].
GIVE = ["g1", "g2"]
RECEIVE = ["r1", "r2"]


def _make_service():
    """A RankingService whose pool contains every player ID the matches touch,
    so record_disposition_signal would actually mutate it when applied."""
    pool = [
        Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
        for pid in (GIVE + RECEIVE)
    ]
    return RankingService(players=pool)


def _make_league():
    members = [
        LeagueMember(user_id=ME, username="me", roster=[], elo_ratings={}),
        LeagueMember(user_id=PARTNER, username="partner", roster=[], elo_ratings={}),
    ]
    return League(league_id=ACTIVE_LEAGUE, name="Active League",
                  platform="sleeper", members=members)


def _insert_match(engine, *, league_id, a_decision=None, b_decision=None):
    """Insert a trade_matches row. user_a=PARTNER (swiped first),
    user_b=ME (the caller). Returns the new match id."""
    with engine.begin() as conn:
        res = conn.execute(insert(trade_matches_table).values(
            league_id      = league_id,
            user_a_id      = PARTNER,
            user_b_id      = ME,
            user_a_give    = json.dumps(GIVE),
            user_a_receive = json.dumps(RECEIVE),
            matched_at     = "2026-01-01T00:00:00",
            status         = "pending",
            user_a_decision = a_decision,
            user_b_decision = b_decision,
        ))
        return res.inserted_primary_key[0]


@pytest.fixture()
def harness():
    """Isolated DB + injected session + mocked side-effects.

    Yields (client, engine, service, token, spies) where `spies` exposes the
    MagicMock for save_trade_swipes so tests can assert persistence.
    """
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    service = _make_service()
    league = _make_league()
    players = [
        Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
        for pid in (GIVE + RECEIVE)
    ]

    token = "test-token-fb01"
    sess = {
        "user_id":       ME,
        "league":        league,
        "players":       players,
        "services":      {"1qb_ppr": service},
        "service":       service,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    save_swipes = MagicMock()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "save_trade_swipes", save_swipes), \
         patch.object(server, "load_matches", MagicMock(return_value=[])), \
         patch.object(server, "record_event", MagicMock()), \
         patch.object(server, "create_notification", MagicMock()), \
         patch.object(server, "_send_typed_push", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, engine, service, token, save_swipes
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _post(client, token, match_id, decision):
    return client.post(
        f"/api/trades/matches/{match_id}/disposition",
        headers={"X-Session-Token": token, "Content-Type": "application/json"},
        data=json.dumps({"decision": decision}),
    )


# ---------------------------------------------------------------------------
# (a) same-league accept → 200, ELO applied to active service, persisted
# ---------------------------------------------------------------------------

def test_same_league_accept_applies_elo_and_persists(harness):
    client, engine, service, token, save_swipes = harness
    # Partner already accepted → my accept completes the match (both_decided).
    match_id = _insert_match(engine, league_id=ACTIVE_LEAGUE, a_decision="accept")

    before = len(service._trade_swipes)
    resp = _post(client, token, match_id, "accept")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["both_decided"] is True
    assert body["outcome"] == "accepted"
    # In-memory ELO WAS applied to the active service (same league).
    assert len(service._trade_swipes) > before
    # Decision persisted for BOTH users.
    assert save_swipes.call_count == 2


# ---------------------------------------------------------------------------
# (b) cross-league accept → 200, ELO NOT applied to active service, persisted
# ---------------------------------------------------------------------------

def test_cross_league_accept_persists_without_touching_active_service(harness):
    client, engine, service, token, save_swipes = harness
    # Match belongs to a DIFFERENT league than the active session league.
    match_id = _insert_match(engine, league_id=OTHER_LEAGUE, a_decision="accept")

    before = len(service._trade_swipes)
    resp = _post(client, token, match_id, "accept")

    # Must still succeed — never fail the user's tap for a cross-league match.
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["both_decided"] is True
    assert body["outcome"] == "accepted"
    # The active-league service must NOT have been mutated — its ratings are
    # for a different league. The signal replays on the other league's
    # next session_init via persistence instead.
    assert len(service._trade_swipes) == before
    # Decision STILL persisted for both users (this is what enables replay).
    assert save_swipes.call_count == 2


# ---------------------------------------------------------------------------
# (c) decline → 200, persisted
# ---------------------------------------------------------------------------

def test_decline_succeeds_and_persists(harness):
    client, engine, service, token, save_swipes = harness
    # Partner already accepted; my decline completes the match as 'declined'.
    match_id = _insert_match(engine, league_id=ACTIVE_LEAGUE, a_decision="accept")

    resp = _post(client, token, match_id, "decline")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["both_decided"] is True
    assert body["outcome"] == "declined"
    assert save_swipes.call_count == 2


# ---------------------------------------------------------------------------
# (d) already-decided:
#   - CONFLICTING decision → 409
#   - SAME decision → 200 idempotent success (feedback #77: clients ≤1.3.0
#     show Accept/Decline on every match tile — including already-decided
#     ones — and render any non-2xx as a generic "Action failed" toast, so a
#     harmless re-accept must not error). No second ELO signal, no re-persist.
# ---------------------------------------------------------------------------

def test_already_decided_conflicting_decision_returns_409(harness):
    client, engine, service, token, save_swipes = harness
    # The caller (user_b = ME) has already ACCEPTED; a DECLINE now conflicts.
    match_id = _insert_match(engine, league_id=ACTIVE_LEAGUE, b_decision="accept")

    resp = _post(client, token, match_id, "decline")

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert save_swipes.call_count == 0


def test_repeat_same_decision_is_idempotent_200(harness):
    client, engine, service, token, save_swipes = harness
    # The caller (user_b = ME) already accepted; partner hasn't decided yet.
    match_id = _insert_match(engine, league_id=ACTIVE_LEAGUE, b_decision="accept")

    before = len(service._trade_swipes)
    resp = _post(client, token, match_id, "accept")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["idempotent"] is True
    assert body["both_decided"] is False
    assert body["outcome"] is None
    # `matches` must be ABSENT (not an empty list): the web client re-renders
    # from data.matches when the key is present, and [] would wipe its inbox.
    assert "matches" not in body
    # No double ELO / persistence from the retry.
    assert len(service._trade_swipes) == before
    assert save_swipes.call_count == 0


def test_repeat_after_both_decided_reports_outcome(harness):
    client, engine, service, token, save_swipes = harness
    # Both parties accepted earlier — a re-accept reports the settled outcome.
    match_id = _insert_match(engine, league_id=ACTIVE_LEAGUE,
                             a_decision="accept", b_decision="accept")

    before = len(service._trade_swipes)
    resp = _post(client, token, match_id, "accept")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["idempotent"] is True
    assert body["both_decided"] is True
    assert body["outcome"] == "accepted"
    assert len(service._trade_swipes) == before
    assert save_swipes.call_count == 0


# ---------------------------------------------------------------------------
# (e) not-found → 404
# ---------------------------------------------------------------------------

def test_not_found_returns_404(harness):
    client, engine, service, token, save_swipes = harness
    resp = _post(client, token, 999999, "accept")  # no such match

    assert resp.status_code == 404, resp.get_data(as_text=True)
    assert save_swipes.call_count == 0


# ---------------------------------------------------------------------------
# Single-sided decision (not both_decided yet) still succeeds — no ELO,
# no persistence, but a clean 200. Guards against the route assuming
# elo_signals is always present.
# ---------------------------------------------------------------------------

def test_first_decision_pending_returns_200_without_elo(harness):
    client, engine, service, token, save_swipes = harness
    # Fresh match — neither side has decided. My accept is the FIRST decision.
    match_id = _insert_match(engine, league_id=ACTIVE_LEAGUE)

    before = len(service._trade_swipes)
    resp = _post(client, token, match_id, "accept")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["both_decided"] is False
    assert len(service._trade_swipes) == before
    assert save_swipes.call_count == 0
