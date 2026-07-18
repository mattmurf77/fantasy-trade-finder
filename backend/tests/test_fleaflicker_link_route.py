"""End-to-end tests for the Fleaflicker league-linking routes (Phase 1, flag
`fleaflicker.link` — docs/plans/multi-platform-linking-plan-2026-07-17.md):

  POST /api/fleaflicker/link      — preview (choose team) + import (persist)
  GET  /api/fleaflicker/leagues   — linked leagues w/ membership snapshot
  POST /api/fleaflicker/import    — re-sync rosters
  POST /api/fleaflicker/discover  — list a user's leagues by email

Flask test client against an in-memory SQLite DB. No network: bundle from the
fixture (patched over fleaflicker_service.fetch_league_bundle), crosswalk from
the DP snapshot (patched over espn_service.get_crosswalk). Flag forced on.
"""
import copy
import json
import os
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.espn_service as es
import backend.fleaflicker_service as fl
import backend.server as server
from backend.database import metadata

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
BUNDLE_FIXTURE = os.path.join(FIXTURES, "fleaflicker_league_snapshot_2026-07-17.json")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")

USER = "313560442465169408"
FLEA_LEAGUE = "312861"


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

    token = "flea-sess-tok"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    xwalk = es.load_crosswalk(XWALK_FIXTURE)
    bundle = _bundle()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k == "fleaflicker.link"), \
         patch.object(es, "get_crosswalk", lambda _opener=None: xwalk), \
         patch.object(fl, "fetch_league_bundle",
                      lambda *a, **kw: copy.deepcopy(bundle)):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _team_ids(bundle):
    return [str(t["team"]["id"]) for t in bundle["rosters"]["rosters"]]


def _link(c, token, **extra):
    body = {"fleaflicker_league_id": FLEA_LEAGUE, **extra}
    return c.post("/api/fleaflicker/link", headers=_h(token), data=json.dumps(body))


def test_routes_404_when_flag_off(client):
    c, token, _ = client
    with patch.object(server, "is_enabled", lambda k: False):
        assert _link(c, token).status_code == 404
        assert c.get("/api/fleaflicker/leagues", headers=_h(token)).status_code == 404
        assert c.post("/api/fleaflicker/import", headers=_h(token),
                      data=json.dumps({"league_id": FLEA_LEAGUE})).status_code == 404


def test_link_preview_persists_nothing(client):
    c, token, engine = client
    r = _link(c, token)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["status"] == "choose_team"
    assert body["league"]["name"] == "Avid Auctioneers Alliance"
    assert len(body["teams"]) == 3
    assert body["report"]["match_rate"] == 1.0
    with engine.connect() as conn:
        assert conn.execute(select(db_module.leagues_table)).fetchall() == []


def test_link_import_persists_crosswalked_members(client):
    c, token, engine = client
    tid = _team_ids(_bundle())[0]
    r = _link(c, token, team_id=tid)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["platform"] == "fleaflicker"
    assert body["teams_imported"] == 3
    assert body["my_team_id"] == tid
    assert len(body["my_roster"]) == 8
    assert body["report"]["pool_players"] == 24
    assert body["report"]["out_of_pool"] == 1        # synthetic kicker

    with engine.connect() as conn:
        lg = conn.execute(select(db_module.leagues_table)).fetchone()._mapping
        assert lg["platform"] == "fleaflicker"
        assert lg["platform_my_team"] == tid
        members = conn.execute(select(db_module.league_members_table)).fetchall()
        by_uid = {m.user_id: m for m in members}
        assert USER in by_uid
        others = [uid for uid in by_uid if uid != USER]
        assert all(uid.startswith("flea:") for uid in others)
        assert all(str(pid).isdigit()
                   for pid in json.loads(by_uid[USER].roster_data))


def test_link_is_idempotent_on_relink(client):
    c, token, engine = client
    ids = _team_ids(_bundle())
    assert _link(c, token, team_id=ids[0]).status_code == 200
    assert _link(c, token, team_id=ids[1]).status_code == 200
    with engine.connect() as conn:
        leagues = conn.execute(select(db_module.leagues_table)).fetchall()
        members = conn.execute(select(db_module.league_members_table)).fetchall()
    assert len(leagues) == 1
    assert leagues[0]._mapping["platform_my_team"] == ids[1]
    assert len(members) == 3


def test_link_bad_league_id_400(client):
    c, token, _ = client
    r = c.post("/api/fleaflicker/link", headers=_h(token),
               data=json.dumps({"fleaflicker_league_id": "not-numeric"}))
    assert r.status_code == 400 and r.get_json()["error"] == "fleaflicker_bad_league_id"


def test_link_bad_team_400(client):
    c, token, _ = client
    r = _link(c, token, team_id="99999999")
    assert r.status_code == 400 and r.get_json()["error"] == "fleaflicker_bad_team_id"


def test_discover_lists_user_leagues(client):
    c, token, _ = client
    with patch.object(fl, "fetch_user_leagues",
                      lambda email, **kw: [{"league_id": FLEA_LEAGUE,
                                            "name": "Avid Auctioneers Alliance",
                                            "size": 12}]):
        r = c.post("/api/fleaflicker/discover", headers=_h(token),
                   data=json.dumps({"email": "me@example.com"}))
    assert r.status_code == 200
    assert r.get_json()["leagues"][0]["league_id"] == FLEA_LEAGUE


def test_leagues_lists_linked_with_rosters(client):
    c, token, _ = client
    assert c.get("/api/fleaflicker/leagues", headers=_h(token)).get_json() == {"leagues": []}
    tid = _team_ids(_bundle())[0]
    _link(c, token, team_id=tid)
    lg = c.get("/api/fleaflicker/leagues", headers=_h(token)).get_json()["leagues"][0]
    assert lg["league_id"] == FLEA_LEAGUE
    assert lg["platform"] == "fleaflicker"
    assert lg["my_team"] == tid
    mine = next(m for m in lg["members"] if m["user_id"] == USER)
    assert len(mine["player_ids"]) == 8


def test_import_resyncs_preserving_binding(client):
    c, token, engine = client
    ids = _team_ids(_bundle())
    _link(c, token, team_id=ids[0])
    changed = _bundle()
    dropped = changed["rosters"]["rosters"][0]["players"].pop(0)
    changed["rosters"]["rosters"][1]["players"].append(dropped)
    with patch.object(fl, "fetch_league_bundle", lambda *a, **kw: changed):
        r = c.post("/api/fleaflicker/import", headers=_h(token),
                   data=json.dumps({"league_id": FLEA_LEAGUE}))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["my_team_id"] == ids[0]


def test_import_unknown_league_404(client):
    c, token, _ = client
    r = c.post("/api/fleaflicker/import", headers=_h(token),
               data=json.dumps({"league_id": "99999999"}))
    assert r.status_code == 404 and r.get_json()["error"] == "fleaflicker_not_linked"
