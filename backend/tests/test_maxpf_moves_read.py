"""Max PF moves: the forecast read (contract §2-§4, §8; plan B6).

An independent Flask app with `api.install` on an in-memory database; the
saved run is the real fixture forecast (test_maxpf_moves) with its real
saved block. No network, no `backend.server` import.

- test_flag_off_read_is_unchanged_with_or_without_a_saved_block: with the flag
  off, `/latest` and `/projection-runs/<id>` answer byte-identically for a run
  saved with a block and the same run saved without one, carry no
  `max_pf_moves` anywhere, and serve the stored result verbatim. Sabotage:
  stop stripping in `public()`.
- test_raw_block_is_never_served_even_with_the_flag_on.
- test_ready_block_shape_and_values: state, baseline and rows from the saved
  run; Keep from the asset preferences; unpriced without a projection.
- test_every_state_in_precedence_order (contract §4.1), and every
  `unavailable` reason the read can produce. Sabotages: read the draft order
  from the user's preferences (draft_order state red); test the deadline
  after the draft order (precedence red).
- test_pick_values_equal_the_engine_price: `pick_value.now` equals
  `pick_values.priced_pool_value` for the viewer's pick with this run's
  distribution and the league's projection knobs; `after` uses the saved
  after-distribution. Sabotage: price "after" with the "now" distribution.
- test_example_payload_matches_the_composer: the contract's §5.1 example has
  exactly the composer's keys and JSON types, at every level.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from types import SimpleNamespace as N

import pytest
from flask import Flask

from backend import database as db, pick_projection, pick_values
from backend.league_projections import api, batch, maxpf_moves
from backend.tests.test_league_projection_routes import client, engine  # noqa: F401  (fixtures)
from backend.tests.test_maxpf_moves import _block, _result

REPO = Path(__file__).resolve().parents[2]
RUN = "b" * 32
NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def _prime():
    """Build the fixture forecast before `client` forbids capture in this process."""
    _block()


def saved_run(**changes):
    result = {**deepcopy(_result()), "max_pf_moves": deepcopy(_block())}
    for key, value in changes.items():
        result[key] = value
    return result


def seed(engine, result, *, age_days=0):  # noqa: F811
    now = NOW
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.delete())
        conn.execute(db.league_projection_targets_table.delete())
        conn.execute(db.league_projection_runs_table.insert().values(
            run_id=RUN, user_id="account", league_id="123", status="complete",
            created_at=(now - timedelta(days=age_days)).isoformat(), updated_at=now.isoformat(),
            expires_at=now.isoformat(), request_hash="synthetic", input_json="{}", input_hash="synthetic",
            result_json=json.dumps(result)))
        conn.execute(db.league_projection_targets_table.insert().values(
            target_id="target", user_id="account", league_id="123", league_user_id="account", season=2026,
            created_at=now.isoformat(), next_due_at=(now + timedelta(days=7)).isoformat(),
            last_success_id=RUN, last_attempt_id=RUN))


def latest(http):
    return http.get("/api/leagues/123/projection-runs/latest")


def flags(monkeypatch, on):
    monkeypatch.setattr(api, "is_enabled", lambda key: on or key != "league.max_pf_moves")


def test_flag_off_read_is_unchanged_with_or_without_a_saved_block(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch, False)
    bare = {k: v for k, v in saved_run().items() if k != "max_pf_moves"}
    seed(engine, bare)
    without = (latest(http).get_data(), http.get(f"/api/projection-runs/{RUN}").get_data())
    seed(engine, saved_run())
    with_block = (latest(http).get_data(), http.get(f"/api/projection-runs/{RUN}").get_data())
    assert without == with_block
    assert b"max_pf_moves" not in with_block[0] and b"max_pf_moves" not in with_block[1]
    body = json.loads(without[0])
    assert body["run"]["result"] == bare and body["state"] == "current"


def test_raw_block_is_never_served_even_with_the_flag_on(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch, True)
    seed(engine, saved_run())
    body = latest(http).json
    assert "max_pf_moves" not in body["run"]["result"] and "max_pf_moves" in body
    assert "max_pf_moves" not in http.get(f"/api/projection-runs/{RUN}").json["result"]
    assert "free_agent_pool" not in json.dumps(body) and "after_pick_probabilities" not in json.dumps(body)


def test_ready_block_shape_and_values(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch, True)
    saved = saved_run()
    seed(engine, saved)
    keep = saved["max_pf_moves"]["rows"][1]["player_id"]
    monkeypatch.setattr(db, "load_asset_preferences", lambda user_id, league_id: {"untouchables": [keep]}
                        if (user_id, league_id) == ("account", "123") else {"untouchables": []})
    db.upsert_league_preference("account", "123", "jets")
    block = latest(http).json["max_pf_moves"]
    team = next(t for t in saved["teams"] if t["roster_id"] == saved["viewer_roster_id"])
    assert block["version"] == 1 and block["state"] == "ready" and block["reason"] is None
    assert block["viewer_roster_id"] == saved["viewer_roster_id"] and block["draft_season"] == 2027
    assert block["saved_outlook"] == "jets" and block["draft_order"] == {"rule": None, "set_at": None}
    assert block["pick_owner"] == {"owns_own_pick": True, "owner_roster_id": team["roster_id"], "owner_name": team["name"]}
    base = block["baseline"]
    assert base["playoff_probability"] == team["playoff_probability"]
    assert base["pick_if_miss"] == team["conditional_expected_pick"]
    assert base["playoff_band"] == "championship" and base["pick_value"] is None and base["pick_value_status"] == "not_priced"
    assert len(block["rows"]) == 8 and [r["rank"] for r in block["rows"]] == list(range(1, 9))
    assert [r["keep"] for r in block["rows"]] == [r["player_id"] == keep for r in block["rows"]]
    assert all(r["pick_value"] is None for r in block["rows"])
    assert block["roster_player_ids"] == saved["max_pf_moves"]["roster_player_ids"]


def compose(saved, state="current", **kw):
    return maxpf_moves.compose(state, saved, cuts=(.15, .75), **kw)


def test_every_state_in_precedence_order(client, engine, monkeypatch):  # noqa: F811
    saved = saved_run()
    assert compose(saved)["state"] == "ready"
    # unavailable reasons
    assert compose(None, "no_run")["reason"] == "no_forecast"
    assert compose(None, "running")["reason"] == "update_pending"
    assert compose(saved, "stale")["reason"] == "stale"
    assert compose(saved, "refresh_failed")["reason"] == "refresh_failed"
    assert compose(saved, "unsupported_policy")["reason"] == "unsupported"
    assert compose({**saved, "model_version": "old"})["reason"] == "old_model"
    assert compose({**saved, "coverage": {"estimate_status": "incomplete"}})["reason"] == "incomplete"
    assert compose(None, "refresh_failed", failure_reason="missing_weekly_projections")["reason"] == "missing_projections"
    assert compose({**saved, "viewer_roster_id": 99})["reason"] == "team_not_found"
    no_block = {k: v for k, v in saved.items() if k != "max_pf_moves"}
    out = compose(no_block)
    assert out["state"] == "unavailable" and out["reason"] == "not_computed" and out["pick_owner"] is not None
    assert compose({**saved, "max_pf_moves": {**saved["max_pf_moves"], "computed": False}})["reason"] == "not_computed"
    # the server states, each beating every later one
    raw = saved["max_pf_moves"]
    over = {**saved, "max_pf_moves": {**raw, "baseline": {**raw["baseline"], "weeks_remaining": 0}, "trade_deadline": 1},
            "completed_weeks": 5}
    assert compose(over, draft_order={"rule": "reverse_standings", "set_at": "x"})["state"] == "season_over"
    late = {**saved, "max_pf_moves": {**raw, "trade_deadline": 5}, "completed_weeks": 5}
    assert compose(late, draft_order={"rule": "reverse_standings", "set_at": "x"})["state"] == "after_trade_deadline"
    assert compose({**late, "completed_weeks": 4})["state"] == "ready"
    for rule in ("reverse_standings", "lottery_or_other"):
        out = compose(saved, draft_order={"rule": rule, "set_at": "x"})
        assert out["state"] == "draft_order_not_maxpf" and out["baseline"] is None and out["rows"] == []
    assert compose(saved, draft_order={"rule": "maxpf_lowest_first", "set_at": "x"})["state"] == "ready"
    teams = [dict(t, conditional_expected_pick=None) if t["roster_id"] == saved["viewer_roster_id"] else t for t in saved["teams"]]
    out = compose({**saved, "teams": teams})
    assert out["state"] == "no_miss" and out["baseline"]["pick_if_miss"] is None and out["rows"] == []
    flat = {**saved, "max_pf_moves": {**raw, "rows": [dict(r, passes_threshold=False) for r in raw["rows"]]}}
    out = compose(flat)
    assert out["state"] == "no_moves" and len(out["rows"]) == 8
    # Through the route: a league answer from the leagues row reaches the read.
    http, _ = client
    flags(monkeypatch, True)
    seed(engine, saved)
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id="123", user_id="other", platform="sleeper"))
    db.set_league_draft_order_rule("123", "lottery_or_other")
    block = latest(http).json["max_pf_moves"]
    assert block["state"] == "draft_order_not_maxpf" and block["draft_order"]["rule"] == "lottery_or_other"
    seed(engine, saved, age_days=8)
    assert latest(http).json["max_pf_moves"]["reason"] == "stale"


def priced_app(engine, monkeypatch, projection):  # noqa: F811
    app = Flask("maxpf-priced")
    sess = {"user_id": "account", "league": N(league_id="123", platform="sleeper")}
    flags(monkeypatch, True)
    options = {**batch.settings(), "policy_approved": True}
    monkeypatch.setattr(batch, "settings", lambda: options)
    monkeypatch.setattr(batch, "is_enabled", lambda key: True)
    api.install(app, require_session=lambda: sess, read_denial=lambda s: None, write_denial=lambda s: None,
                league_user_id=lambda s: "account", fetch_json=lambda url: pytest.fail("no network"),
                pick_projection=lambda league_id: projection, active_format=lambda s: "1qb_ppr")
    return app.test_client()


def test_pick_values_equal_the_engine_price(engine, monkeypatch):  # noqa: F811
    saved = saved_run()
    n = len(saved["teams"])
    curve = [float(3000 - 200 * k) for k in range(n)]
    monkeypatch.setattr(pick_values, "market_pick_pool_value", lambda season, round_, fmt: 1860.0)
    monkeypatch.setattr(pick_values, "_r1_yoy_floored", lambda market, season, round_, fmt: market)
    monkeypatch.setattr(pick_values, "projected_slot_curve", lambda teams, season, round_, fmt="1qb_ppr": curve)
    summary = pick_projection.compact(saved, run_id="league", created_at=datetime.now(timezone.utc).isoformat())
    projection = pick_projection.usable(summary, model_version=saved["model_version"], now=datetime.now(timezone.utc),
                                        weight=1.0, min_weeks=0, max_age_days=30, max_round=1)
    assert projection is not None
    http = priced_app(engine, monkeypatch, projection)
    seed(engine, saved)
    block = http.get("/api/leagues/123/projection-runs/latest").json["max_pf_moves"]
    viewer = saved["viewer_roster_id"]
    team = next(t for t in saved["teams"] if t["roster_id"] == viewer)
    spots = saved["playoff_spots"]
    row_pick = {"season": 2027, "round": 1, "original_roster_id": viewer, "pool_value": 0}
    now = round(pick_values.priced_pool_value(row_pick, scoring_format="1qb_ppr", mode="market_slots",
                                              projection=projection), 1)  # this run IS the league's projection
    assert block["baseline"]["pick_value"] == now and block["baseline"]["pick_value_status"] == "priced"
    first = block["rows"][0]
    raw = saved["max_pf_moves"]["rows"][0]
    dist = raw["after_pick_probabilities"] + [raw["after_playoff_probability"] / spots] * spots
    expected = round(1860.0 * pick_projection.factor(projection, dist, curve), 1)
    assert first["pick_value"]["now"] == now and first["pick_value"]["after"] == expected
    assert first["pick_value"]["change"] == round(expected - now, 1) and first["pick_value"]["change"] > 0
    assert team["pick_owner_roster_id"] == viewer


def _types(value):
    if isinstance(value, dict):
        return {k: _types(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_types(value[0])] if value else []
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return type(value).__name__
    return "number"


def _merge_nullable(a, b):
    """Key sets must match exactly; a value may be null on one side."""
    if isinstance(a, dict) and isinstance(b, dict):
        assert set(a) == set(b), (sorted(set(a) ^ set(b)))
        for k in a:
            _merge_nullable(a[k], b[k])
    elif isinstance(a, list) and isinstance(b, list):
        if a and b:
            _merge_nullable(a[0], b[0])
    elif "NoneType" not in (a, b):
        assert a == b, (a, b)


def test_example_payload_matches_the_composer(engine, monkeypatch):  # noqa: F811
    text = (REPO / "docs/plans/league-projections/max-pf-trade-away/contract.md").read_text()
    section = text[text.index("### 5.1"):text.index("### 5.2")]
    example = json.loads(re.search(r"```json\n(.*?)```", section, re.S).group(1))["max_pf_moves"]
    saved = saved_run()
    curve = [float(3000 - 200 * k) for k in range(len(saved["teams"]))]
    monkeypatch.setattr(pick_values, "market_pick_pool_value", lambda season, round_, fmt: 1860.0)
    monkeypatch.setattr(pick_values, "_r1_yoy_floored", lambda market, season, round_, fmt: market)
    monkeypatch.setattr(pick_values, "projected_slot_curve", lambda teams, season, round_, fmt="1qb_ppr": curve)
    summary = pick_projection.compact(saved, run_id="league", created_at=datetime.now(timezone.utc).isoformat())
    projection = pick_projection.usable(summary, model_version=saved["model_version"], now=datetime.now(timezone.utc),
                                        weight=1.0, min_weeks=0, max_age_days=30, max_round=1)
    http = priced_app(engine, monkeypatch, projection)
    seed(engine, saved)
    block = http.get("/api/leagues/123/projection-runs/latest").json["max_pf_moves"]
    _merge_nullable(_types(example), _types(block))
