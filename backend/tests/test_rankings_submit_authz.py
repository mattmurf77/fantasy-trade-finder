"""Teardown W2C task 1 — rankings-submit authz regression (W1A sibling).

POST /api/rankings/submit used to accept an arbitrary `user_id` from the
body (`user_id = body.get("user_id") or g_user_id`), letting any
authenticated session upsert member_rankings under ANY user_id — and
member_rankings feed leaguemates' trade generation. Same S6B-01 class as
the fixed league-preferences routes. The route is now hard-scoped to the
session user; the body override is ignored.

GET /api/league/coverage similarly ignored-not-honored: its `user_id`
query param (used as exclude_user_id for an aggregate count) now always
resolves to the session user.

Isolation pattern mirrors test_league_prefs_authz.py: Flask test client,
in-memory SQLite, injected sessions, no network.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.server as server
from backend.database import metadata, league_members_table

USER_A = "333333333333333333"
USER_B = "444444444444444444"
LEAGUE = "league_submit_authz"


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


def _mk_service(player_ids):
    """Fake RankingService: get_rankings() → .rankings of (player, elo)."""
    rankings = [
        SimpleNamespace(player=SimpleNamespace(id=pid), elo=1500.0 + i)
        for i, pid in enumerate(player_ids)
    ]
    return SimpleNamespace(
        get_rankings=lambda position=None: SimpleNamespace(rankings=rankings)
    )


def _mk_sess(user_id, player_ids):
    """Minimal session satisfying _require_initialized_session + submit."""
    svc = _mk_service(player_ids)
    return {
        "user_id":       user_id,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
        "league":        SimpleNamespace(league_id=LEAGUE),
        "players":       [],
        "service":       svc,
        "services":      {"1qb_ppr": svc},
        "trade_svc":     object(),
        "trade_svcs":    {"1qb_ppr": object()},
    }


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token_a, token_b = "sess-submit-a", "sess-submit-b"
    server.app.config["TESTING"] = True
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: False), \
         patch.object(server, "touch_user_activity", MagicMock()):
        with server._sessions_lock:
            server._sessions[token_a] = _mk_sess(USER_A, ["p1", "p2"])
            server._sessions[token_b] = _mk_sess(USER_B, ["p9"])
        try:
            yield c, token_a, token_b
        finally:
            with server._sessions_lock:
                server._sessions.pop(token_a, None)
                server._sessions.pop(token_b, None)


def _submit(c, token, extra=None):
    body = {"league_id": LEAGUE}
    body.update(extra or {})
    return c.post("/api/rankings/submit", headers=_h(token),
                  data=json.dumps(body))


def _stored_rankings():
    """member_rankings keyed by user_id (no exclusion)."""
    return db_module.load_member_rankings(
        league_id=LEAGUE, exclude_user_id="", scoring_format="1qb_ppr")


def test_spoofed_body_user_id_lands_on_session_user(client):
    """Session A submitting with body user_id=B writes A's snapshot; no
    rows appear under B."""
    c, token_a, _ = client
    r = _submit(c, token_a, extra={"user_id": USER_B})
    assert r.status_code == 200, r.get_data(as_text=True)
    stored = _stored_rankings()
    assert USER_A in stored
    assert USER_B not in stored
    assert set(stored[USER_A]["elo_ratings"]) == {"p1", "p2"}


def test_spoofed_write_leaves_target_snapshot_untouched(client):
    """The sabotage scenario: B has a published snapshot; A's spoofed
    submit must not replace it (the route's upsert DELETES the target
    user's rows first — the old override let A wipe B's real board)."""
    c, token_a, _ = client
    db_module.upsert_member_rankings(
        user_id=USER_B, league_id=LEAGUE,
        rankings=[{"player_id": "p9", "elo": 1777.0}],
        scoring_format="1qb_ppr",
    )
    r = _submit(c, token_a, extra={"user_id": USER_B})
    assert r.status_code == 200
    stored = _stored_rankings()
    assert stored[USER_B]["elo_ratings"] == {"p9": 1777.0}   # unchanged
    assert set(stored[USER_A]["elo_ratings"]) == {"p1", "p2"}


def test_self_submit_path_unchanged(client):
    """Legitimate payload (no user_id key) keeps working as before."""
    c, token_a, _ = client
    r = _submit(c, token_a)
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["submitted"] == 2
    assert USER_A in _stored_rankings()


def test_coverage_ignores_query_user_id(client):
    """GET /api/league/coverage?user_id=B still excludes the SESSION user
    (A), not the query-named user."""
    c, token_a, _ = client
    eng = db_module.engine
    with eng.begin() as conn:
        for uid, uname in ((USER_A, "alice"), (USER_B, "bob")):
            conn.execute(insert(league_members_table).values(
                league_id=LEAGUE, user_id=uid, username=uname))
    db_module.upsert_member_rankings(
        user_id=USER_B, league_id=LEAGUE,
        rankings=[{"player_id": "p9", "elo": 1600.0}],
        scoring_format="1qb_ppr",
    )
    r = c.get(f"/api/league/coverage?league_id={LEAGUE}&user_id={USER_B}",
              headers=_h(token_a))
    assert r.status_code == 200
    data = r.get_json()
    member_ids = {m["user_id"] for m in data["members"]}
    assert member_ids == {USER_B}          # A (session user) excluded
    assert data["ranked"] == 1 and data["total"] == 1
