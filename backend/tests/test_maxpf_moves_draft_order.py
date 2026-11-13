"""Max PF moves: the per-league draft-order answer (contract §7, plan B5).

An independent Flask app with `api.install` (no `backend.server` import) on
an in-memory database.

- test_member_answer_is_stored_for_the_whole_league: a member's answer is
  read back by another member of the same league; last answer wins;
  `not_sure` writes nothing.
- test_authz: flag off, forecast flag off, another league (a non-member's
  session) → 404; an unverified session is refused by `write_denial`; a
  non-Sleeper league → 422 `sleeper_only`; no league row → 404. Sabotages:
  skip the league-match check; skip the flag check.
- test_bad_bodies_are_400_and_large_is_413. Sabotage: accept any string.
- test_migration_adds_both_columns_to_an_existing_database: `_migrate_db`
  on a database created before the change adds the two columns, twice is a
  no-op, and the helpers work on it (the `median_game` precedent).
  Sabotage: drop one `_migrate_db` row.
"""
from __future__ import annotations

from types import SimpleNamespace as N
from unittest.mock import patch

import pytest
from flask import Flask, jsonify
from sqlalchemy import create_engine, inspect, text

from backend import database as db
from backend.league_projections import api, batch, provider, service, store
from backend.tests.test_outlook_calibration_persistence import engine  # noqa: F401  (fixture)


@pytest.fixture
def client(engine, monkeypatch):  # noqa: F811
    flags = {"league.projections": True, "league.max_pf_moves": True}
    app = Flask("maxpf-draft-order")
    state = {"sess": {"user_id": "account", "league": N(league_id="123", platform="sleeper")}, "verified": True}
    monkeypatch.setattr(api, "is_enabled", lambda key: flags.get(key, False))
    for module, name in ((service, "wake"), (provider, "capture"), (batch, "dispatch"), (store, "create")):
        monkeypatch.setattr(module, name, lambda *a, **k: pytest.fail("no compute from this route"))

    def write_denial(sess):
        return None if state["verified"] else (jsonify(error="verification_required"), 403)
    api.install(app, require_session=lambda: state["sess"], read_denial=lambda s: None, write_denial=write_denial,
                league_user_id=lambda s: "account", fetch_json=lambda url: pytest.fail("no network"))
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert(), [
            {"sleeper_league_id": "123", "user_id": "account", "platform": "sleeper"},
            {"sleeper_league_id": "456", "user_id": "other", "platform": "sleeper"},
            {"sleeper_league_id": "789", "user_id": "account", "platform": "espn"}])
    return app.test_client(), state, flags


def post(http, league, body):
    return http.post(f"/api/leagues/{league}/draft-order-rule", json=body)


def test_member_answer_is_stored_for_the_whole_league(client):
    http, state, _ = client
    response = post(http, "123", {"rule": "reverse_standings"})
    assert response.status_code == 200
    stored = response.json["draft_order"]
    assert stored["rule"] == "reverse_standings" and stored["set_at"]
    # A second member of the same league sees and overwrites the same answer.
    state["sess"] = {"user_id": "account-2", "league": N(league_id="123", platform="sleeper")}
    assert db.get_league_draft_order_rule("123")["rule"] == "reverse_standings"
    assert post(http, "123", {"rule": "not_sure"}).json["draft_order"]["rule"] == "reverse_standings"
    assert post(http, "123", {"rule": "maxpf_lowest_first"}).json["draft_order"]["rule"] == "maxpf_lowest_first"
    assert db.get_league_draft_order_rule("123")["rule"] == "maxpf_lowest_first"
    assert db.get_league_draft_order_rule("456") == {"rule": None, "set_at": None}
    # not_sure on an unanswered league writes nothing.
    state["sess"] = {"user_id": "x", "league": N(league_id="456", platform="sleeper")}
    assert post(http, "456", {"rule": "not_sure"}).json == {"draft_order": {"rule": None, "set_at": None}}


def test_authz(client, engine):  # noqa: F811
    http, state, flags = client
    assert post(http, "456", {"rule": "reverse_standings"}).status_code == 404  # not this session's league
    assert db.get_league_draft_order_rule("456")["rule"] is None
    state["verified"] = False
    assert post(http, "123", {"rule": "reverse_standings"}).status_code == 403
    state["verified"] = True
    flags["league.max_pf_moves"] = False
    assert post(http, "123", {"rule": "reverse_standings"}).json == {"error": "feature_disabled"}
    assert post(http, "123", {"rule": "reverse_standings"}).status_code == 404
    flags["league.max_pf_moves"] = True
    flags["league.projections"] = False
    assert post(http, "123", {"rule": "reverse_standings"}).status_code == 404
    flags["league.projections"] = True
    assert db.get_league_draft_order_rule("123")["rule"] is None
    state["sess"] = {"user_id": "account", "league": N(league_id="789", platform="espn")}
    response = post(http, "789", {"rule": "reverse_standings"})
    assert response.status_code == 422 and response.json["reason"] == "sleeper_only"
    state["sess"] = {"user_id": "account", "league": N(league_id="999", platform="sleeper")}
    assert post(http, "999", {"rule": "reverse_standings"}).status_code == 404


@pytest.mark.parametrize("body", [{}, {"rule": "tanking"}, {"rule": "MAXPF_LOWEST_FIRST"}, {"rule": None},
                                  {"rule": "reverse_standings", "source": "x"}, ["reverse_standings"], "reverse_standings"])
def test_bad_bodies_are_400_and_large_is_413(client, body):
    http, _, _ = client
    response = post(http, "123", body)
    assert response.status_code == 400 and response.json == {"error": "invalid_draft_order_rule"}
    assert http.post("/api/leagues/123/draft-order-rule", data="").status_code == 400
    big = http.post("/api/leagues/123/draft-order-rule", data='{"rule": "' + "x" * 2000 + '"}',
                    content_type="application/json")
    assert big.status_code == 413
    assert db.get_league_draft_order_rule("123")["rule"] is None


def test_migration_adds_both_columns_to_an_existing_database(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    db.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE leagues DROP COLUMN draft_order_rule"))
        conn.execute(text("ALTER TABLE leagues DROP COLUMN draft_order_rule_set_at"))
        conn.execute(text("INSERT INTO leagues (sleeper_league_id, user_id) VALUES ('123', 'u')"))
    assert "draft_order_rule" not in {c["name"] for c in inspect(eng).get_columns("leagues")}
    with patch.object(db, "engine", eng), patch.object(db, "DATABASE_URL", "sqlite:///old"):
        db._migrate_db()
        db._migrate_db()
        columns = {c["name"] for c in inspect(eng).get_columns("leagues")}
        assert {"draft_order_rule", "draft_order_rule_set_at"} <= columns
        assert db.get_league_draft_order_rule("123") == {"rule": None, "set_at": None}
        assert db.set_league_draft_order_rule("123", "lottery_or_other")["rule"] == "lottery_or_other"
        assert db.set_league_draft_order_rule("nope", "lottery_or_other") is None
        with pytest.raises(ValueError):
            db.set_league_draft_order_rule("123", "not_sure")
