"""Team Review against the engine as it is today (docs/feedback/items/357-team-review/
2026-11-12-current-data-fixes.md). Server side of fixes 1, 2, 3 and 5:

1. "N firsts" counts picks by their numeric round, so slotted ("2026 1.08") and
   projected-slot ("2027 1.02 · projected") labels count.
2. The standing beat's playoff line is the SAVED weekly forecast (Home's tile),
   `standing.playoff_chance`; the old `outlook.odds` band is never shipped as
   `standing.outlook`, and nothing is shown when no saved forecast is usable.
3. `window.outlook_rules` names the rules an outlook switches on in the rule
   catalog's own words.
5. POST /api/league/preferences accepts a positions-only body that leaves the
   stored outlook exactly as it was (unsaved stays unsaved), and every old
   body shape behaves as before.
"""
import ast
import json
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

from backend import database as db, rule_catalog
from backend.league_projections import batch, recommendation
from backend.league_projections.core import VERSION
from backend.tests.test_league_projection_routes import client, engine  # noqa: F401

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
SERVER = pathlib.Path(__file__).resolve().parents[1] / "server.py"


# ── 1. firsts by round ─────────────────────────────────────────────────────

def test_first_round_count_reads_the_round_not_the_label():
    import backend.server as server
    owned = [
        {"label": "2027 1st", "round": 1},
        {"label": "2026 1.08", "round": 1},
        {"label": "2027 1.02 · projected", "round": "1"},
        {"label": "2026 2.01", "round": 2},
        {"label": "2028 1st", "round": None},     # no round: not counted
    ]
    assert server._first_round_pick_count(owned) == 3
    assert server._first_round_pick_count([]) == 0
    assert server._first_round_pick_count(None) == 0


def test_team_review_route_counts_firsts_through_the_round_helper():
    """The wiring is the defect class (#368), so pin it: the route's
    `first_rounds[uid]` is the helper over the owner's picks."""
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    route = next(n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "league_team_review_route")
    src = ast.get_source_segment(SERVER.read_text(encoding="utf-8"), route)
    assert "first_rounds[uid] = _first_round_pick_count(owned)" in src
    assert '"1st" in' not in src


# ── 2. the saved forecast on the standing beat ─────────────────────────────

def _view(probability=.6, *, state="current", model=VERSION, captured="2026-11-10T15:00:00+00:00",
          due_days=3, status="complete", roster=1):
    result = {"model_version": model, "viewer_roster_id": roster, "captured_at": captured,
              "coverage": {"estimate_status": "complete"},
              "teams": [{"roster_id": 1, "playoff_probability": probability},
                        {"roster_id": 2, "playoff_probability": .99}]}
    return {"state": state, "run": {"status": status, "result_json": json.dumps(result)},
            "next_attempt_not_before": (NOW + timedelta(days=due_days)).isoformat()}


@pytest.mark.parametrize("view,current", [
    (_view(), True),
    (_view(state="stale"), False),                 # Home: "last saved"
    (_view(state="refresh_failed"), False),
    (_view(model="joint-season-scenario-v4"), False),
    (_view(due_days=-1), False),                   # past the next weekly update
])
def test_saved_chance_is_shown_whenever_home_shows_a_percentage(view, current):
    chance = recommendation.saved_chance(view, NOW)
    assert chance == {"playoff_probability": .6, "captured_at": "2026-11-10T15:00:00+00:00",
                      "current": current}


@pytest.mark.parametrize("view", [
    None, {"state": "no_run", "run": None},
    _view(status="failed"), _view(roster=7), _view(probability=1.5),
    _view(probability=True), _view(captured="2026-11-13T00:00:00+00:00"), _view(captured="nope"),
])
def test_saved_chance_is_none_when_home_shows_no_percentage(view):
    assert recommendation.saved_chance(view, NOW) is None


@pytest.fixture
def tr(engine, monkeypatch):  # noqa: F811
    """GET /api/league/team-review over the power-rankings world, full payload."""
    import backend.server as server
    from backend.tests import test_power_rankings as pr
    flags = {"trades.team_review", "league.projections", "outlook.odds"}
    platform = {"name": "sleeper"}
    monkeypatch.setattr(server, "is_enabled", lambda key: key in flags)
    monkeypatch.setattr(server, "touch_user_activity", MagicMock())
    monkeypatch.setattr(server, "load_league_members", pr._members_rows)
    monkeypatch.setattr(server, "load_draft_picks", lambda league_id=None, **kw: pr._pick_rows(league_id))
    monkeypatch.setattr(server, "_get_universal_pool", pr._fake_pool)
    monkeypatch.setattr(server, "get_league_draft_context", lambda league_id: {"platform": platform["name"]})
    monkeypatch.setattr(server, "_league_lineup_slots", lambda league_id: None)

    def offline(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(server, "_outlook_sleeper_fetch", lambda *a, **k: offline)
    # A simulator band that WOULD exist: the standing beat must still not ship it.
    st = SimpleNamespace(teams=[SimpleNamespace(user_id="u_a", roster_id=1)])
    band = {"teams": [{"roster_id": 1, "odds": {"playoff_pct": .9, "projected_seed": 1}}], "meta": {}}
    monkeypatch.setattr(server, "_outlook_impact_baseline", lambda *a: (st, band, None, None, None, None))
    views = []

    def view(user_id, league_id):
        views.append((user_id, league_id))
        return {**_view(), "next_attempt_not_before": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()}
    monkeypatch.setattr(batch, "view", view)
    server.app.config["TESTING"] = True
    with server._sessions_lock:
        server._sessions[pr.TOKEN] = pr._mk_sess()

    def get():
        response = server.app.test_client().get(
            f"/api/league/team-review?league_id={pr.LEAGUE}", headers=pr._h())
        assert response.status_code == 200, response.data
        return response.json
    try:
        yield get, flags, platform, views
    finally:
        with server._sessions_lock:
            server._sessions.pop(pr.TOKEN, None)


def test_standing_ships_the_saved_chance_and_never_the_old_band(tr):
    get, _flags, _platform, views = tr
    body = get()
    assert body["standing"]["playoff_chance"]["playoff_probability"] == .6
    assert body["standing"]["playoff_chance"]["captured_at"] == "2026-11-10T15:00:00+00:00"
    assert body["standing"]["playoff_chance"]["current"] is True
    assert "outlook" not in body["standing"]
    assert ("u_a", "league_pr_test") in views


def test_no_usable_forecast_shows_nothing_rather_than_the_old_band(tr, monkeypatch):
    get, flags, platform, views = tr
    flags.discard("league.projections")
    body = get()
    assert "playoff_chance" not in body["standing"] and "outlook" not in body["standing"]
    assert views == []
    flags.add("league.projections")
    platform["name"] = "espn"
    body = get()
    assert "playoff_chance" not in body["standing"] and "outlook" not in body["standing"]
    assert views == []
    platform["name"] = "sleeper"
    monkeypatch.setattr(batch, "view", lambda *a: {"state": "no_run", "run": None})
    body = get()
    assert "playoff_chance" not in body["standing"] and "outlook" not in body["standing"]

    def broken(*a):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(batch, "view", broken)
    body = get()
    assert "playoff_chance" not in body["standing"] and "outlook" not in body["standing"]


# ── 3. the rules an outlook switches on, in the catalog's words ────────────

def test_outlook_rules_are_the_catalogs_live_tanking_rules():
    names = rule_catalog.outlook_rule_names()
    tanking = [r.name for r in rule_catalog.RULES if r.live and r.setting == "Team outlook: Tanking"]
    assert names == {"jets": tanking}
    assert tanking == ["Tanking teams keep next pick", "Tanking teams skip older RBs",
                       "Tanking teams keep young favourites"]


def test_team_review_window_carries_the_outlook_rules(tr):
    get, *_ = tr
    assert get()["window"]["outlook_rules"] == rule_catalog.outlook_rule_names()


# ── 5. positions-only preference saves ─────────────────────────────────────

USER, LEAGUE, TOKEN = "u_prefs", "league_prefs_only", "sess-prefs-only"


@pytest.fixture()
def prefs():
    import backend.server as server
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    server.app.config["TESTING"] = True
    sess = {"verified": True, "user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0,
            "league": SimpleNamespace(league_id=LEAGUE), "players": [],
            "trade_svc": object(), "trade_svcs": {"1qb_ppr": object()}}
    with patch.object(db, "engine", eng), patch.object(server, "is_enabled", lambda k: False), \
            patch.object(server, "touch_user_activity", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        c = server.app.test_client()

        def post(body):
            return c.post("/api/league/preferences", data=json.dumps({"league_id": LEAGUE, **body}),
                          headers={"X-Session-Token": TOKEN, "Content-Type": "application/json"})

        def get():
            return c.get(f"/api/league/preferences?league_id={LEAGUE}",
                         headers={"X-Session-Token": TOKEN}).json
        try:
            yield post, get, eng
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


def _stored():
    return db.load_league_preference(user_id=USER, league_id=LEAGUE)


def test_positions_only_save_with_nothing_saved_leaves_the_outlook_unsaved(prefs):
    post, get, eng = prefs
    r = post({"acquire_positions": ["WR"], "trade_away_positions": ["RB"]})
    assert r.status_code == 200, r.data
    assert r.json["team_outlook"] is None
    assert _stored() == {"team_outlook": None, "acquire_positions": ["WR"],
                         "trade_away_positions": ["RB"], "avoid_positions": []}
    assert db.load_league_preferences_bulk([USER], LEAGUE)[USER]["team_outlook"] is None
    assert get()["team_outlook"] is None
    with eng.connect() as conn:
        assert conn.execute(db.select(db.league_preferences_table.c.team_outlook)).scalar() == db.UNSAVED_OUTLOOK
    # An explicit null is the same positions-only save.
    assert post({"team_outlook": None, "acquire_positions": ["TE"]}).status_code == 200
    assert _stored()["team_outlook"] is None and _stored()["acquire_positions"] == ["TE"]
    # A later real choice saves it.
    assert post({"team_outlook": "jets"}).status_code == 200
    assert _stored()["team_outlook"] == "jets" and _stored()["acquire_positions"] == ["TE"]


def test_positions_only_save_keeps_a_saved_outlook(prefs):
    post, _get, _eng = prefs
    assert post({"team_outlook": "rebuilder", "acquire_positions": ["QB"]}).status_code == 200
    r = post({"trade_away_positions": ["WR"]})
    assert r.status_code == 200 and r.json["team_outlook"] == "rebuilder"
    assert _stored() == {"team_outlook": "rebuilder", "acquire_positions": ["QB"],
                         "trade_away_positions": ["WR"], "avoid_positions": []}


def test_every_old_body_shape_behaves_as_before(prefs):
    post, _get, _eng = prefs
    # Trade DNA / Home prompt / shipped builds: always send the outlook.
    r = post({"team_outlook": "contender", "acquire_positions": ["WR"], "trade_away_positions": []})
    assert r.status_code == 200 and r.json["team_outlook"] == "contender"
    assert _stored()["team_outlook"] == "contender"
    r = post({"team_outlook": "not_sure"})
    assert r.status_code == 200 and _stored()["team_outlook"] == "not_sure"
    assert _stored()["acquire_positions"] == ["WR"]
    # Still refused: nothing at all, or an outlook outside the five.
    assert post({}).status_code == 400
    assert post({"team_outlook": None}).status_code == 400
    assert post({"team_outlook": "tanking", "acquire_positions": ["WR"]}).status_code == 400
    assert post({"team_outlook": "", "acquire_positions": ["WR"]}).status_code == 400
    assert _stored()["team_outlook"] == "not_sure"


def test_database_rejects_an_unknown_outlook_but_accepts_none():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    with patch.object(db, "engine", eng):
        with pytest.raises(ValueError):
            db.upsert_league_preference("u", "l", "tanking")
        db.upsert_league_preference("u", "l", None, avoid_positions=["QB"])
        assert db.load_league_preference(user_id="u", league_id="l")["team_outlook"] is None
        db.upsert_league_preference("u", "l", "contender")
        db.upsert_league_preference("u", "l", None, acquire_positions=["RB"])
        assert db.load_league_preference(user_id="u", league_id="l") == {
            "team_outlook": "contender", "acquire_positions": ["RB"],
            "trade_away_positions": [], "avoid_positions": ["QB"]}


# ── #681: an outlook-only body leaves every stored position list alone ─────

def test_outlook_only_body_leaves_all_three_position_lists_unchanged(prefs):
    """The banner's one-tap Confirm (`saveLeagueOutlook`) sends only
    `team_outlook`. Positions saved without an outlook (Team Review's Chase /
    Shop, or Avoiding) must survive it."""
    post, _get, _eng = prefs
    assert post({"acquire_positions": ["WR"], "trade_away_positions": ["RB"],
                 "avoid_positions": ["TE"]}).status_code == 200
    assert _stored()["team_outlook"] is None
    r = post({"team_outlook": "rebuilder"})
    assert r.status_code == 200 and r.json["team_outlook"] == "rebuilder"
    assert _stored() == {"team_outlook": "rebuilder", "acquire_positions": ["WR"],
                         "trade_away_positions": ["RB"], "avoid_positions": ["TE"]}


def test_explicit_empty_lists_still_clear_them(prefs):
    """The old one-tap body (and any full save) sends `[]`: that still clears."""
    post, _get, _eng = prefs
    assert post({"team_outlook": "contender", "acquire_positions": ["WR"],
                 "trade_away_positions": ["RB"], "avoid_positions": ["TE"]}).status_code == 200
    assert post({"team_outlook": "jets", "acquire_positions": [], "trade_away_positions": [],
                 "avoid_positions": []}).status_code == 200
    assert _stored() == {"team_outlook": "jets", "acquire_positions": [],
                         "trade_away_positions": [], "avoid_positions": []}
