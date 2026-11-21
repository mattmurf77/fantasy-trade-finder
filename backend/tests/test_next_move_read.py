"""Home's next move on the forecast read, and its flag (docs/plans/home-next-move/
scope.md §2, §3; D-278).

An independent Flask app with `api.install` on an in-memory database, as
test_team_direction_read; the saved run is the real fixture forecast with the
real saved Max PF moves block (viewer roster 1, 88%). No network, no
`backend.server` except the flags endpoint.

- test_flag_off_read_is_byte_identical: with `league.next_move` off the read
  answers the same bytes as a server whose composer fails the test, and names
  no `next_move`. Sabotage: compose without the flag check.
- test_ready_sell_on_the_read: a saved Rebuilding outlook and an answered
  draft order: the block is the composer over the three blocks the same read
  serves, a sell of the served list's first row, and nothing is saved.
- test_gates_on_the_read: the draft-order question unanswered (suggests);
  answered reverse_standings / lottery_or_other (nothing: no rows, no pick);
  the card's fallback to the draft pick at 88% (collapsed list); the
  direction card off.
- test_a_failure_is_read_failed: the forecast and the other blocks still served.
- test_flag_registered_shipped_on_and_reaches_the_app, test_not_env_forced,
  test_client_compiled_default_matches_config,
  test_only_the_forecast_read_checks_the_flag.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

import backend.feature_flags as feature_flags
from backend import database as db
from backend.league_projections import api, next_move
from backend.tests.test_league_projection_routes import client, engine  # noqa: F401  (fixtures)
from backend.tests.test_maxpf_moves import _block, _result
from backend.tests.test_maxpf_moves_read import latest, seed

REPO = Path(__file__).resolve().parents[2]
FLAG = "league.next_move"
FIXTURES = ("release", "onboarding-v2", "profiles-on")


@pytest.fixture(scope="module", autouse=True)
def _prime():
    """Build the fixture forecast before `client` forbids capture in this process."""
    _block()


def saved_run():
    return {**deepcopy(_result()), "max_pf_moves": deepcopy(_block())}


def flags(monkeypatch, *, on=True, card=True):
    off = {FLAG: not on, "league.direction_card": not card, "league.playoff_targets": True}
    monkeypatch.setattr(api, "is_enabled", lambda key: not off.get(key, False))


def answered(engine):
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id="123", user_id="other", platform="sleeper"))
    db.set_league_draft_order_rule("123", "maxpf_lowest_first")


def test_flag_off_read_is_byte_identical(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    seed(engine, saved_run())
    db.upsert_league_preference("account", "123", "rebuilder")
    flags(monkeypatch, on=False)
    with_code = latest(http).get_data()
    monkeypatch.setattr(next_move, "compose", lambda *a, **k: pytest.fail("composed with the flag off"))
    without = latest(http).get_data()
    assert with_code == without and b"next_move" not in with_code
    body = json.loads(with_code)
    assert "team_direction" in body and "max_pf_moves" in body and body["state"] == "current"


def test_ready_sell_on_the_read(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch)
    saved = saved_run()
    seed(engine, saved)
    answered(engine)
    db.upsert_league_preference("account", "123", "rebuilder")
    body = latest(http).json
    block = body["next_move"]
    assert block == next_move.compose(body["team_direction"], body["max_pf_moves"], body.get("playoff_targets"))
    assert body["team_direction"]["primary"] == "draft_pick"
    first = min(body["max_pf_moves"]["rows"], key=lambda r: r["rank"])
    assert block["state"] == "ready" and block["action"] == "sell" and block["direction"] == "draft_pick"
    assert block["player"] == {k: first[k] for k in ("player_id", "name", "short_name", "position")}
    assert block["pick"] == first["label"] and block["playoff_probability"] == first["playoff_probability"]
    assert "roster_player_ids" not in block and block["player"]["player_id"] in body["max_pf_moves"]["roster_player_ids"]
    # Nothing is saved: the stored run is unchanged and serves no block.
    assert "next_move" not in body["run"]["result"]
    with engine.connect() as conn:
        stored = conn.execute(db.select(db.league_projection_runs_table.c.result_json)).scalar()
    assert json.loads(stored) == saved


def test_gates_on_the_read(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch)
    seed(engine, saved_run())
    db.upsert_league_preference("account", "123", "rebuilder")
    # The draft-order question unanswered: the list still shows its rows
    # under the question, so the sell is suggested.
    block = latest(http).json["next_move"]
    assert block["state"] == "ready" and block["action"] == "sell"
    # Answered with a non-max-PF order: no rows, no draft-pick direction, no projected pick: nothing.
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id="123", user_id="other", platform="sleeper"))
    for rule in ("reverse_standings", "lottery_or_other"):
        db.set_league_draft_order_rule("123", rule)
        body = latest(http).json
        assert body["max_pf_moves"]["state"] == "draft_order_not_maxpf"
        assert body["team_direction"]["projected_pick"] is None and body["team_direction"]["primary"] is None
        assert (body["next_move"]["state"], body["next_move"]["reason"]) == ("none", "no_direction")
    db.set_league_draft_order_rule("123", "maxpf_lowest_first")
    # Contender at 88%: the card leads with the draft pick only because the
    # playoffs are not offered here; the list would start behind "Show moves".
    db.upsert_league_preference("account", "123", "contender")
    body = latest(http).json
    assert body["team_direction"]["primary"] == "draft_pick"
    assert (body["next_move"]["state"], body["next_move"]["reason"]) == ("none", "collapsed")
    flags(monkeypatch, card=False)
    body = latest(http).json
    assert "team_direction" not in body and body["next_move"]["reason"] == "direction_off"


def test_no_run_and_stale(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch)
    assert latest(http).json["next_move"]["reason"] == "unavailable"
    seed(engine, saved_run(), age_days=8)
    assert latest(http).json["next_move"]["reason"] == "unavailable"


def test_a_failure_is_read_failed(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch)
    seed(engine, saved_run())
    monkeypatch.setattr(next_move, "compose", lambda *a, **k: (_ for _ in ()).throw(KeyError("boom")))
    body = latest(http).json
    assert body["next_move"] == next_move.read_failed()
    assert body["run"]["result"]["teams"] and body["team_direction"]["state"] == "ready"


def test_flag_registered_shipped_on_and_reaches_the_app():
    assert FLAG in feature_flags.FLAG_KEYS and feature_flags.DEFAULT_FLAGS[FLAG] is False
    features = json.loads((REPO / "config/features.json").read_text())
    assert features[FLAG] is True and "D-278" in features["_comment_league_next_move"]
    # It needs the card's block, which ships on too.
    assert features["league.direction_card"] is True
    for name in FIXTURES:
        fixture = json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())
        assert fixture[FLAG] is True and fixture["league.direction_card"] is True, name
    import backend.server as server
    server.app.config["TESTING"] = True
    http = server.app.test_client()
    old = feature_flags._flags_cache
    try:
        feature_flags._flags_cache = dict(feature_flags.DEFAULT_FLAGS)
        assert http.get("/api/feature-flags").get_json()["flags"][FLAG] is False
        feature_flags._flags_cache = {**feature_flags.DEFAULT_FLAGS, FLAG: True}
        assert http.get("/api/feature-flags").get_json()["flags"][FLAG] is True
    finally:
        feature_flags._flags_cache = old


def test_not_env_forced():
    assert FLAG not in (REPO / "render.yaml").read_text()


def test_client_compiled_default_matches_config():
    src = (REPO / "mobile/src/state/useFeatureFlags.ts").read_text()
    assert f"  '{FLAG}': true,\n" in src


def test_only_the_forecast_read_checks_the_flag():
    gates = sorted(str(p.relative_to(REPO)) for p in (REPO / "backend").rglob("*.py")
                   if "tests" not in p.parts and f'is_enabled("{FLAG}")' in p.read_text(encoding="utf-8"))
    assert gates == ["backend/league_projections/api.py"]
