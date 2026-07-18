"""End-to-end tests for the MFL league-linking routes (Phase 1, flag
`mfl.link` — docs/plans/multi-platform-linking-plan-2026-07-17.md):

  POST /api/mfl/link     — preview (choose franchise) + import (persist)
  GET  /api/mfl/leagues  — linked leagues w/ membership snapshot
  POST /api/mfl/import   — re-sync rosters for a linked league

Flask test client against an isolated in-memory SQLite DB. No network: the MFL
bundle comes from the fixture (patched over mfl_service.fetch_league_bundle),
the host from a patched resolve_host, and the crosswalk from the DP snapshot
(patched over espn_service.get_crosswalk). Flag forced on via patched is_enabled.
"""
import copy
import json
import os
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.espn_service as es
import backend.mfl_service as mfl
import backend.server as server
from backend.database import metadata

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
BUNDLE_FIXTURE = os.path.join(FIXTURES, "mfl_league_snapshot_2026-07-17.json")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")

USER = "313560442465169408"
MFL_LEAGUE = "10005"


def _bundle():
    with open(BUNDLE_FIXTURE) as f:
        return json.load(f)


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "mfl-sess-tok"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    xwalk = es.load_crosswalk(XWALK_FIXTURE)
    bundle = _bundle()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k == "mfl.link"), \
         patch.object(es, "get_crosswalk", lambda _opener=None: xwalk), \
         patch.object(mfl, "resolve_host", lambda *a, **kw: "www48.myfantasyleague.com"), \
         patch.object(mfl, "fetch_league_bundle",
                      lambda *a, **kw: copy.deepcopy(bundle)):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _link(c, token, **extra):
    body = {"mfl_league_id": MFL_LEAGUE, "year": 2026, **extra}
    return c.post("/api/mfl/link", headers=_h(token), data=json.dumps(body))


def test_routes_404_when_flag_off(client):
    c, token, _ = client
    with patch.object(server, "is_enabled", lambda k: False):
        assert _link(c, token).status_code == 404
        assert c.get("/api/mfl/leagues", headers=_h(token)).status_code == 404
        assert c.post("/api/mfl/import", headers=_h(token),
                      data=json.dumps({"league_id": MFL_LEAGUE})).status_code == 404


def test_link_preview_returns_teams_and_persists_nothing(client):
    c, token, engine = client
    r = _link(c, token)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["status"] == "choose_team"
    assert body["league"]["name"].startswith("Masters Copper Dynasty")
    assert body["league"]["host"] == "www48.myfantasyleague.com"
    assert len(body["teams"]) == 3
    assert all(t["mapped_players"] == 8 for t in body["teams"])
    assert body["report"]["match_rate"] == 1.0
    with engine.connect() as conn:
        assert conn.execute(select(db_module.leagues_table)).fetchall() == []
        assert conn.execute(select(db_module.league_members_table)).fetchall() == []


def test_link_import_persists_league_members_and_picks(client):
    c, token, engine = client
    r = _link(c, token, franchise_id="0001")
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["platform"] == "mfl"
    assert body["auth"] == "public"
    assert body["teams_imported"] == 3
    assert body["my_team_id"] == "0001"
    assert len(body["my_roster"]) == 8
    assert body["report"]["pool_players"] == 24
    assert body["report"]["match_rate"] == 1.0
    assert body["future_picks_stored"] > 0

    with engine.connect() as conn:
        lg = conn.execute(select(db_module.leagues_table)).fetchone()._mapping
        assert lg["sleeper_league_id"] == MFL_LEAGUE
        assert lg["platform"] == "mfl"
        assert lg["user_id"] == USER
        assert lg["platform_season"] == 2026
        assert lg["platform_host"] == "www48.myfantasyleague.com"
        assert lg["platform_auth"] == "public"
        assert lg["platform_my_team"] == "0001"
        assert lg["total_rosters"] == 3
        # futureDraftPicks stored raw (JSON list) — NOT engine-wired
        picks = json.loads(lg["platform_future_picks"])
        assert len(picks) > 0
        assert set(picks[0]) == {"franchise_id", "year", "round", "original_owner"}

        members = conn.execute(select(db_module.league_members_table)).fetchall()
        by_uid = {m.user_id: m for m in members}
        assert len(members) == 3
        assert USER in by_uid                       # chosen franchise binds to session user
        others = [uid for uid in by_uid if uid != USER]
        assert all(uid.startswith("mfl:") for uid in others)
        my_ids = json.loads(by_uid[USER].roster_data)
        assert my_ids == body["my_roster"]
        assert all(str(pid).isdigit() for pid in my_ids)


def test_link_is_idempotent_on_relink(client):
    c, token, engine = client
    assert _link(c, token, franchise_id="0001").status_code == 200
    r = _link(c, token, franchise_id="0002")
    assert r.status_code == 200
    with engine.connect() as conn:
        leagues = conn.execute(select(db_module.leagues_table)).fetchall()
        members = conn.execute(select(db_module.league_members_table)).fetchall()
    assert len(leagues) == 1
    assert leagues[0]._mapping["platform_my_team"] == "0002"
    assert len(members) == 3
    assert sum(1 for m in members if m.user_id == USER) == 1


def test_link_url_input_parses_host_and_id(client):
    c, token, _ = client
    # a pasted league URL supplies both id and host (no resolve_host needed)
    body = {"mfl_league_url": "https://www48.myfantasyleague.com/2026/home/10005"}
    r = c.post("/api/mfl/link", headers=_h(token), data=json.dumps(body))
    assert r.status_code == 200
    assert r.get_json()["league"]["host"] == "www48.myfantasyleague.com"


def test_link_unmatched_players_are_skipped_and_reported(client):
    c, token, _ = client
    doctored = _bundle()
    # swap one roster player for a WR that's in-pool (position known) but whose
    # mfl id + name resolve to nothing → a genuine unmatched (not out-of-pool)
    doctored["rosters"]["rosters"]["franchise"][0]["player"][0]["id"] = "99999999"
    doctored["players"]["players"]["player"].append(
        {"id": "99999999", "name": "Unknown, Totally", "position": "WR"})
    with patch.object(mfl, "fetch_league_bundle", lambda *a, **kw: doctored):
        r = _link(c, token, franchise_id="0001")
    assert r.status_code == 200
    body = r.get_json()
    assert body["report"]["match_rate"] == pytest.approx(23 / 24, abs=1e-4)
    assert len(body["my_roster"]) == 7


def test_link_bad_franchise_400(client):
    c, token, _ = client
    r = _link(c, token, franchise_id="9999")
    assert r.status_code == 400 and r.get_json()["error"] == "mfl_bad_team_id"


def test_leagues_lists_linked_with_rosters(client):
    c, token, _ = client
    assert c.get("/api/mfl/leagues", headers=_h(token)).get_json() == {"leagues": []}
    _link(c, token, franchise_id="0001")
    r = c.get("/api/mfl/leagues", headers=_h(token))
    leagues = r.get_json()["leagues"]
    assert len(leagues) == 1
    lg = leagues[0]
    assert lg["league_id"] == MFL_LEAGUE
    assert lg["platform"] == "mfl"
    assert lg["my_team"] == "0001"
    assert len(lg["members"]) == 3
    mine = next(m for m in lg["members"] if m["user_id"] == USER)
    assert len(mine["player_ids"]) == 8


def test_import_resyncs_preserving_binding(client):
    c, token, engine = client
    _link(c, token, franchise_id="0001")
    changed = _bundle()
    dropped = changed["rosters"]["rosters"]["franchise"][0]["player"].pop(0)
    changed["rosters"]["rosters"]["franchise"][1]["player"].append(dropped)
    with patch.object(mfl, "fetch_league_bundle", lambda *a, **kw: changed):
        r = c.post("/api/mfl/import", headers=_h(token),
                   data=json.dumps({"league_id": MFL_LEAGUE}))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["my_team_id"] == "0001"
    assert len(body["my_roster"]) == 7


def test_import_unknown_league_404(client):
    c, token, _ = client
    r = c.post("/api/mfl/import", headers=_h(token),
               data=json.dumps({"league_id": "99999"}))
    assert r.status_code == 404 and r.get_json()["error"] == "mfl_not_linked"
