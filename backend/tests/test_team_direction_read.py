"""The `team_direction` block on the forecast read, and its two flags (spec
docs/plans/league-projections/direction-pages/spec.md §7, §8, §10.1; D-265,
D-270).

An independent Flask app with `api.install` on an in-memory database, as
test_playoff_targets_read; the saved run is the real fixture forecast with
the real saved Max PF moves block (viewer roster 1) and, where named, the
real saved Playoff targets block. No network, no `backend.server` except the
flags endpoint.

- test_flag_off_read_is_byte_identical: with `league.direction_card` off the
  read answers the same bytes as a server without the block's code (the
  composer replaced by one that fails the test), and names no
  `team_direction`. Sabotage: compose the block without the flag check.
- test_ready_block_on_the_read: the block equals the composer over the same
  saved run and the two blocks the read serves; the projected pick equals
  the served `max_pf_moves.baseline.label`.
- test_options_follow_the_served_blocks_and_flags: a feature flag off reads
  `feature_off`; a stored draft order that is not max PF hides the pick and
  reads `draft_order_not_maxpf`. Sabotage: read the draft order from the
  user's preferences.
- test_unusable_reads: no run, stale (figures kept as last saved), a failed
  read (`read_failed`, the forecast itself still served).
- test_flags_code_default_off_shipped_on_and_reach_the_app: both flags in
  FLAG_KEYS, false by default in code, true in config/features.json with a
  comment and true in the three fixtures (ON from 2026-11-15, D-271), served
  on GET /api/feature-flags.
- test_no_backend_code_reads_the_sheet_flag: `league.direction_view_sheet`
  is app-only; `league.direction_card` is checked only by the forecast read.
  Sabotage: name the sheet flag in a backend module.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

import backend.feature_flags as feature_flags
from backend import database as db
from backend.league_projections import api, team_direction
from backend.tests.test_league_projection_routes import client, engine  # noqa: F401  (fixtures)
from backend.tests.test_maxpf_moves import _block, _result
from backend.tests.test_maxpf_moves_read import latest, seed

REPO = Path(__file__).resolve().parents[2]
CARD, SHEET = "league.direction_card", "league.direction_view_sheet"
FIXTURES = ("release", "onboarding-v2", "profiles-on")


@pytest.fixture(scope="module", autouse=True)
def _prime():
    """Build the fixture forecast before `client` forbids capture in this process."""
    _block()


def saved_run():
    return {**deepcopy(_result()), "max_pf_moves": deepcopy(_block())}


def flags(monkeypatch, *, card=True, max_pf=True, targets=False):
    off = {CARD: not card, "league.max_pf_moves": not max_pf, "league.playoff_targets": not targets}
    monkeypatch.setattr(api, "is_enabled", lambda key: not off.get(key, False))


def test_flag_off_read_is_byte_identical(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    seed(engine, saved_run())
    flags(monkeypatch, card=False)
    with_code = latest(http).get_data()
    monkeypatch.setattr(team_direction, "compose", lambda *a, **k: pytest.fail("composed with the flag off"))
    monkeypatch.setattr(team_direction, "settings", lambda: pytest.fail("settings read with the flag off"))
    without = latest(http).get_data()
    assert with_code == without and b"team_direction" not in with_code
    body = json.loads(with_code)
    assert "max_pf_moves" in body and body["state"] == "current", "a real read, with the other blocks served"


def test_ready_block_on_the_read(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch)
    saved = saved_run()
    seed(engine, saved)
    db.upsert_league_preference("account", "123", "contender")
    body = latest(http).json
    block = body["team_direction"]
    assert block == team_direction.compose(
        "current", saved, saved_outlook="contender", draft_order=None, cuts=team_direction.settings(),
        max_pf_on=True, max_pf_block=body["max_pf_moves"], targets_on=False, targets_block=None)
    team = next(t for t in saved["teams"] if t["roster_id"] == saved["viewer_roster_id"])
    assert block["state"] == "ready" and block["reason"] is None and block["version"] == 1
    assert block["playoff_probability"] == team["playoff_probability"] and block["band"] == "high"
    assert block["captured_at"] == saved["captured_at"]
    # The guard: the card's figure is the draft-pick page's "today".
    assert block["projected_pick"]["label"] == body["max_pf_moves"]["baseline"]["label"] == "1.11"
    assert body["max_pf_moves"]["state"] == "ready"
    assert block["options"] == {"draft_pick": {"offered": True, "reason": None},
                                "playoffs": {"offered": False, "reason": "feature_off"}}
    # 88% and Contender lean to the playoffs, which is not offered: the draft pick leads.
    assert block["primary"] == "draft_pick"
    # Nothing is saved: the stored run is unchanged and serves no block.
    assert "team_direction" not in body["run"]["result"]
    with engine.connect() as conn:
        stored = conn.execute(db.select(db.league_projection_runs_table.c.result_json)).scalar()
    assert json.loads(stored) == saved


def test_options_follow_the_served_blocks_and_flags(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    saved = saved_run()
    seed(engine, saved)
    flags(monkeypatch, max_pf=False)
    block = latest(http).json["team_direction"]
    assert block["options"]["draft_pick"] == {"offered": False, "reason": "feature_off"}
    assert block["primary"] is None and block["state"] == "ready"
    flags(monkeypatch)
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id="123", user_id="other", platform="sleeper"))
    db.set_league_draft_order_rule("123", "reverse_standings")
    body = latest(http).json
    block = body["team_direction"]
    assert body["max_pf_moves"]["state"] == "draft_order_not_maxpf"
    assert block["projected_pick"] is None
    assert block["options"]["draft_pick"] == {"offered": False, "reason": "draft_order_not_maxpf"}
    # A preference-held answer is never read: only the leagues row decides.
    db.set_league_draft_order_rule("123", "maxpf_lowest_first")
    assert latest(http).json["team_direction"]["projected_pick"]["label"] == "1.11"


def test_unusable_reads(client, engine, monkeypatch):  # noqa: F811
    http, _ = client
    flags(monkeypatch)
    block = latest(http).json["team_direction"]
    assert block["state"] == "unavailable" and block["reason"] == "no_forecast"
    assert block["captured_at"] is None and block["projected_pick"] is None and block["primary"] is None
    saved = saved_run()
    seed(engine, saved, age_days=8)
    block = latest(http).json["team_direction"]
    assert block["state"] == "unavailable" and block["reason"] == "stale" and block["band"] is None
    assert block["projected_pick"]["label"] == "1.11" and block["playoff_probability"] is not None
    assert block["options"]["draft_pick"] == {"offered": False, "reason": "unavailable"}
    seed(engine, saved)
    monkeypatch.setattr(team_direction, "settings", lambda: (_ for _ in ()).throw(ValueError("bad config")))
    body = latest(http).json
    assert body["team_direction"] == team_direction.read_failed(True, False)
    assert body["run"]["result"]["teams"] and body["max_pf_moves"]["state"] != "unavailable"


def test_flags_code_default_off_shipped_on_and_reach_the_app():
    """D-271 (operator, 2026-11-15): both flags ship ON. The code default stays
    off; the three flag fixtures mirror the shipped value."""
    features = json.loads((REPO / "config/features.json").read_text())
    for key, comment in ((CARD, "_comment_league_direction_card"), (SHEET, "_comment_league_direction_view_sheet")):
        assert key in feature_flags.FLAG_KEYS and feature_flags.DEFAULT_FLAGS[key] is False, key
        assert features[key] is True and "D-270" in features[comment], key
        for name in FIXTURES:
            assert json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())[key] is True, (key, name)
    assert "league.direction_both_middle" not in feature_flags.FLAG_KEYS, "cell B is deferred (D-270)"
    import backend.server as server
    server.app.config["TESTING"] = True
    http = server.app.test_client()
    old = feature_flags._flags_cache
    try:
        feature_flags._flags_cache = dict(feature_flags.DEFAULT_FLAGS)
        served = http.get("/api/feature-flags").get_json()["flags"]
        assert served[CARD] is False and served[SHEET] is False
        feature_flags._flags_cache = {**feature_flags.DEFAULT_FLAGS, CARD: True, SHEET: True}
        served = http.get("/api/feature-flags").get_json()["flags"]
        assert served[CARD] is True and served[SHEET] is True
    finally:
        feature_flags._flags_cache = old


def test_no_backend_code_reads_the_sheet_flag():
    def readers(key):
        # A quoted literal is a read; prose in a comment (the taxonomy names
        # the flag in its tile vocabulary) is not.
        return sorted(str(p.relative_to(REPO)) for p in (REPO / "backend").rglob("*.py")
                      if "tests" not in p.parts and (f'"{key}"' in p.read_text(encoding="utf-8")
                                                     or f"'{key}'" in p.read_text(encoding="utf-8")))
    assert readers(SHEET) == ["backend/feature_flags.py"]
    gates = sorted(str(p.relative_to(REPO)) for p in (REPO / "backend").rglob("*.py")
                   if "tests" not in p.parts and f'is_enabled("{CARD}")' in p.read_text(encoding="utf-8"))
    assert gates == ["backend/league_projections/api.py"], "only the forecast read checks the card flag"
