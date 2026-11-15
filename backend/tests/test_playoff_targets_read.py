"""Playoff targets: the forecast read (contract §2-§4, §8).

An independent Flask app with `api.install` on an in-memory database, as
test_maxpf_moves_read; the saved run is the real fixture forecast with a real
saved block for roster 7 (69% in the fixture). No network, no `backend.server`.

- test_flag_off_read_is_unchanged_with_or_without_a_saved_block: with the flag
  off, `/latest` and `/projection-runs/<id>` answer byte-identically for a run
  saved with a block and the same run saved without one, and carry no
  `playoff_targets` anywhere. Sabotage: stop stripping in `public()`.
- test_raw_block_is_never_served_even_with_the_flag_on.
- test_ready_block_comes_from_the_saved_run: state, baseline, rows and the
  viewer's own saved outlook.
- test_the_read_looks_the_outlooks_up_again: a team that was a seller only
  through its manager's saved Rebuilding outlook keeps its rows while that
  outlook (or Tanking) is saved for the owner or a co-owner, and loses them
  when it is changed or cleared. Sabotage: pass `live_outlooks=None`.
- test_an_unreadable_saved_block_is_read_failed, test_no_run_and_stale.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from backend import database as db
from backend.league_projections import api, playoff_targets
from backend.tests.test_league_projection_routes import client, engine  # noqa: F401  (fixtures)
from backend.tests.test_maxpf_moves import _result
from backend.tests.test_maxpf_moves_read import RUN, latest, seed
from backend.tests.test_playoff_targets import VIEWER, _targets


@pytest.fixture(scope="module", autouse=True)
def _prime():
    """Build the fixture forecast before `client` forbids capture in this process."""
    _targets(outlooks=((3, "rebuilder"),))


def saved_run(outlooks=((3, "rebuilder"),)):
    return {**deepcopy(_result()), "viewer_roster_id": VIEWER, "playoff_targets": deepcopy(_targets(outlooks=outlooks))}


def flags(monkeypatch, on):
    monkeypatch.setattr(api, "is_enabled", lambda key: key != "league.max_pf_moves" and (on or key != "league.playoff_targets"))


def test_flag_off_read_is_unchanged_with_or_without_a_saved_block(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch, False)
    bare = {k: v for k, v in saved_run().items() if k != "playoff_targets"}
    seed(engine, bare)
    without = (latest(http).get_data(), http.get(f"/api/projection-runs/{RUN}").get_data())
    seed(engine, saved_run())
    with_block = (latest(http).get_data(), http.get(f"/api/projection-runs/{RUN}").get_data())
    assert without == with_block
    assert b"playoff_targets" not in with_block[0] and b"playoff_targets" not in with_block[1]
    body = json.loads(without[0])
    assert body["run"]["result"] == bare and body["state"] == "current"


def test_raw_block_is_never_served_even_with_the_flag_on(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch, True)
    seed(engine, saved_run())
    body = latest(http).json
    assert "playoff_targets" not in body["run"]["result"] and "playoff_targets" in body
    assert "playoff_targets" not in http.get(f"/api/projection-runs/{RUN}").json["result"]
    text = json.dumps(body)
    assert "owner_ids" not in text and "settings_hash" not in text and "seller_roster_id" not in text


def test_ready_block_comes_from_the_saved_run(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch, True)
    saved = saved_run(outlooks=())
    seed(engine, saved)
    db.upsert_league_preference("account", "123", "contender")
    block = latest(http).json["playoff_targets"]
    team = next(t for t in saved["teams"] if t["roster_id"] == VIEWER)
    raw = saved["playoff_targets"]
    assert block["version"] == 1 and block["state"] == "ready" and block["reason"] is None
    assert block["viewer_roster_id"] == VIEWER and block["captured_at"] == saved["captured_at"]
    assert block["saved_outlook"] == "contender"
    assert block["baseline"] == {**raw["baseline"], "playoff_probability": team["playoff_probability"],
                                 "playoff_band": "contender", "playoff_clinched": False, "playoff_eliminated": False}
    assert block["eligible_teams"] == 6 and block["sellers_changed"] is False
    assert block["candidates_total"] == raw["candidates_total"]
    assert [r["player_id"] for r in block["rows"]] == [r["player_id"] for r in raw["rows"]]
    names = {t["roster_id"]: t for t in saved["teams"]}
    for row, saved_row in zip(block["rows"], raw["rows"]):
        seller = names[saved_row["seller_roster_id"]]
        assert row["seller"] == {"roster_id": seller["roster_id"], "name": seller["name"],
                                 "playoff_probability": seller["playoff_probability"],
                                 "playoff_clinched": False, "playoff_eliminated": False}
        assert seller["playoff_probability"] < 0.5
        assert row["playoff_probability"] == saved_row["playoff_probability"]


def test_the_read_looks_the_outlooks_up_again(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch, True)
    saved = saved_run()
    raw = saved["playoff_targets"]
    raw["sellers"]["3"]["owner_ids"] = ["owner3", "co3"]
    seed(engine, saved)
    from_three = {r["player_id"] for r in raw["rows"] if r["seller_roster_id"] == 3}
    assert from_three and raw["sellers"]["3"]["playoff_probability"] > 0.9

    def listed():
        block = latest(http).json["playoff_targets"]
        return block, {r["player_id"] for r in block["rows"]}

    # Nothing saved now (the outlook the job saw is gone): the team's rows are not served.
    block, ids = listed()
    assert not ids & from_three and block["eligible_teams"] == 6 and block["sellers_changed"] is True
    assert block["state"] in ("ready", "no_targets")
    # The owner has Rebuilding saved: served.
    db.upsert_league_preference("owner3", "123", "rebuilder")
    block, ids = listed()
    assert from_three <= ids and block["eligible_teams"] == 7 and block["sellers_changed"] is False
    # Changed to Tanking: still a seller.
    db.upsert_league_preference("owner3", "123", "jets")
    assert from_three <= listed()[1]
    # Changed to Contender: gone at once, without a new forecast.
    db.upsert_league_preference("owner3", "123", "contender")
    block, ids = listed()
    assert not ids & from_three and block["sellers_changed"] is True
    # The same outlook saved for another league does not count.
    db.upsert_league_preference("owner3", "999", "rebuilder")
    assert not listed()[1] & from_three
    # The primary owner's saved outlook comes first; a co-owner's is used only when the owner has none.
    db.upsert_league_preference("co3", "123", "rebuilder")
    assert not listed()[1] & from_three
    with engine.begin() as conn:
        conn.execute(db.league_preferences_table.delete().where(db.league_preferences_table.c.user_id == "owner3"))
    assert from_three <= listed()[1]


def test_an_unreadable_saved_block_is_read_failed(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch, True)
    seed(engine, saved_run())
    monkeypatch.setattr(playoff_targets, "sellers_now", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    body = latest(http).json
    assert body["playoff_targets"] == {**playoff_targets.compose("no_run", None), "reason": "read_failed"}
    assert body["run"]["result"]["teams"]  # the forecast itself is still served


def test_no_run_and_stale(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch, True)
    block = latest(http).json["playoff_targets"]
    assert block["state"] == "unavailable" and block["reason"] == "no_forecast" and block["rows"] == []
    seed(engine, saved_run(), age_days=8)
    block = latest(http).json["playoff_targets"]
    assert block["state"] == "unavailable" and block["reason"] == "stale" and block["viewer_roster_id"] is None
