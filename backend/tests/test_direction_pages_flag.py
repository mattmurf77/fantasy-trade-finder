"""Improve pages, step 1: the `league.direction_pages` flag (spec
docs/plans/league-projections/direction-pages/spec.md §8, §10.3; D-265).

Step 1 is app-only. The backend's whole job is to register the flag, ship it
off, mirror it in the three flag fixtures, and serve it to the app; no
backend code reads it, so no response changes in either state.

- test_flag_is_registered_and_ships_off: in FLAG_KEYS, false by default,
  false in config/features.json with its `_comment_` line, false in the three
  fixtures. Sabotage: drop the key from FLAG_KEYS; set it true in
  config/features.json; drop it from profiles-on.json.
- test_flag_reaches_the_app: GET /api/feature-flags (the app's flag source)
  serves it, false by default and true when turned on.
- test_no_backend_code_reads_the_flag: the only backend module naming it is
  feature_flags.py. Sabotage: gate anything on it in a backend module.
- test_forecast_read_is_byte_identical_in_either_state: the forecast read
  (`/latest`, with Max PF moves and Playoff targets on) answers the same bytes
  with the flag on and off.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

import backend.feature_flags as feature_flags
from backend.league_projections import api
from backend.tests.test_league_projection_routes import client, engine  # noqa: F401  (fixtures)
from backend.tests.test_maxpf_moves import _result
from backend.tests.test_maxpf_moves_read import latest, seed
from backend.tests.test_playoff_targets import VIEWER, _targets

REPO = Path(__file__).resolve().parents[2]
KEY = "league.direction_pages"
FIXTURES = ("release", "onboarding-v2", "profiles-on")


def test_flag_is_registered_and_ships_off():
    assert KEY in feature_flags.FLAG_KEYS and feature_flags.DEFAULT_FLAGS[KEY] is False
    features = json.loads((REPO / "config/features.json").read_text())
    assert features[KEY] is False
    assert "D-265" in features["_comment_league_direction_pages"]
    for name in FIXTURES:
        assert json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())[KEY] is False, name


def test_flag_reaches_the_app():
    import backend.server as server
    server.app.config["TESTING"] = True
    http = server.app.test_client()
    old = feature_flags._flags_cache
    try:
        feature_flags._flags_cache = dict(feature_flags.DEFAULT_FLAGS)
        assert http.get("/api/feature-flags").get_json()["flags"][KEY] is False
        feature_flags._flags_cache = {**feature_flags.DEFAULT_FLAGS, KEY: True}
        assert http.get("/api/feature-flags").get_json()["flags"][KEY] is True
    finally:
        feature_flags._flags_cache = old


def test_no_backend_code_reads_the_flag():
    readers = sorted(
        str(p.relative_to(REPO)) for p in (REPO / "backend").rglob("*.py")
        if "tests" not in p.parts and KEY in p.read_text(encoding="utf-8")
    )
    assert readers == ["backend/feature_flags.py"], readers


@pytest.fixture(scope="module")
def _saved():
    """Build the fixture forecast before `client` forbids capture in this process."""
    return {**deepcopy(_result()), "viewer_roster_id": VIEWER,
            "playoff_targets": deepcopy(_targets(outlooks=((3, "rebuilder"),)))}


def test_forecast_read_is_byte_identical_in_either_state(_saved, client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    seed(engine, _saved)
    answers = []
    for on in (False, True):
        monkeypatch.setattr(api, "is_enabled", lambda key, on=on: key != KEY or on)
        answers.append(latest(http).get_data())
    assert answers[0] == answers[1]
    body = json.loads(answers[0])
    assert "playoff_targets" in body and "max_pf_moves" in body, "both blocks are served, so the read is a real one"
