"""Teardown 06-01 (S6B-01) — league-preferences authz regression.

GET/POST /api/league/preferences used to accept an arbitrary `user_id`
from the query/body (`user_id = body.get("user_id") or g_user_id`), letting
any authenticated session read or overwrite ANY other user's team outlook
and positional preferences — which drive the trade engine's valuations.
Both routes are now hard-scoped to the session user; the request-supplied
override is ignored.

Isolation pattern mirrors test_verified_sessions.py: Flask test client,
in-memory SQLite, injected sessions, no network.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata

USER_A = "111111111111111111"
USER_B = "222222222222222222"
LEAGUE = "league_authz_test"


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


def _mk_sess(user_id):
    """Minimal session that satisfies _require_initialized_session."""
    return {
        "user_id":       user_id,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
        "league":        SimpleNamespace(league_id=LEAGUE),
        "players":       [],
        "trade_svc":     object(),
        "trade_svcs":    {"1qb_ppr": object()},
    }


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token_a, token_b = "sess-authz-a", "sess-authz-b"
    server.app.config["TESTING"] = True
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: False), \
         patch.object(server, "touch_user_activity", MagicMock()):
        with server._sessions_lock:
            server._sessions[token_a] = _mk_sess(USER_A)
            server._sessions[token_b] = _mk_sess(USER_B)
        try:
            yield c, token_a, token_b
        finally:
            with server._sessions_lock:
                server._sessions.pop(token_a, None)
                server._sessions.pop(token_b, None)


def _post_prefs(c, token, extra=None):
    body = {"league_id": LEAGUE, "team_outlook": "contender",
            "acquire_positions": ["WR"], "trade_away_positions": ["QB"]}
    body.update(extra or {})
    return c.post("/api/league/preferences", headers=_h(token),
                  data=json.dumps(body))


def test_post_ignores_body_user_id_cross_user_write_impossible(client):
    """Session A writing with body user_id=B lands on A; B stays untouched."""
    c, token_a, _ = client
    r = _post_prefs(c, token_a, extra={"user_id": USER_B})
    assert r.status_code == 200, r.get_data(as_text=True)

    # The write landed on the SESSION user (A), not the body-named user (B).
    assert db_module.load_league_preference(user_id=USER_B,
                                            league_id=LEAGUE) is None
    prefs_a = db_module.load_league_preference(user_id=USER_A, league_id=LEAGUE)
    assert prefs_a and prefs_a["team_outlook"] == "contender"


def test_post_cannot_overwrite_existing_prefs_of_other_user(client):
    """The sabotage scenario: B has declared prefs; A's spoofed write must
    not change them."""
    c, token_a, _ = client
    db_module.upsert_league_preference(
        user_id=USER_B, league_id=LEAGUE, team_outlook="rebuilder",
        acquire_positions=["TE"], trade_away_positions=[],
    )
    r = _post_prefs(c, token_a, extra={"user_id": USER_B})
    assert r.status_code == 200

    prefs_b = db_module.load_league_preference(user_id=USER_B, league_id=LEAGUE)
    assert prefs_b["team_outlook"] == "rebuilder"          # unchanged
    assert prefs_b["acquire_positions"] == ["TE"]


def test_self_write_path_unchanged(client):
    """Legitimate client payload (no user_id key) keeps working as before."""
    c, token_a, _ = client
    r = _post_prefs(c, token_a)
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["team_outlook"] == "contender"
    prefs = db_module.load_league_preference(user_id=USER_A, league_id=LEAGUE)
    assert prefs["team_outlook"] == "contender"


def test_get_ignores_query_user_id(client):
    """Session A reading with ?user_id=B gets A's prefs, never B's."""
    c, token_a, token_b = client
    db_module.upsert_league_preference(
        user_id=USER_B, league_id=LEAGUE, team_outlook="rebuilder",
        acquire_positions=[], trade_away_positions=[],
    )
    db_module.upsert_league_preference(
        user_id=USER_A, league_id=LEAGUE, team_outlook="championship",
        acquire_positions=[], trade_away_positions=[],
    )
    r = c.get(f"/api/league/preferences?league_id={LEAGUE}&user_id={USER_B}",
              headers=_h(token_a))
    assert r.status_code == 200
    assert r.get_json()["team_outlook"] == "championship"   # A's, not B's

    # And B still reads their own through their own session.
    r = c.get(f"/api/league/preferences?league_id={LEAGUE}",
              headers=_h(token_b))
    assert r.get_json()["team_outlook"] == "rebuilder"
