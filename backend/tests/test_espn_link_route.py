"""End-to-end tests for the ESPN league-linking routes (Phase 1, flag
`espn.link` — docs/plans/espn-league-linking-plan-2026-07-11.md):

  POST /api/espn/link     — preview (choose team) + import (persist)
  GET  /api/espn/leagues  — linked leagues w/ membership snapshot
  POST /api/espn/import   — re-sync rosters for a linked league

Exercised through Flask's test client against an isolated in-memory SQLite
DB with an injected session. Nothing touches the network: the ESPN payload
comes from fixtures/espn_league_snapshot_2026-07-11.json (patched over
espn_service.fetch_league) and the crosswalk from the DP snapshot fixture
(patched over espn_service.get_crosswalk). The flag is forced on via a
patched `is_enabled`.
"""
import copy
import json
import os
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.espn_service as es
import backend.server as server
from backend.database import metadata

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
LEAGUE_FIXTURE = os.path.join(FIXTURES, "espn_league_snapshot_2026-07-11.json")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")

USER = "313560442465169408"
ESPN_LEAGUE = "987654321"     # id inside the fixture payload


def _fixture_payload():
    with open(LEAGUE_FIXTURE) as f:
        return json.load(f)


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "espn-sess-tok"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    xwalk = es.load_crosswalk(XWALK_FIXTURE)
    payload = _fixture_payload()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k == "espn.link"), \
         patch.object(es, "get_crosswalk", lambda _opener=None: xwalk), \
         patch.object(es, "fetch_league",
                      lambda *a, **kw: copy.deepcopy(payload)) as fetch:
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _link(c, token, **extra):
    body = {"espn_league_id": ESPN_LEAGUE, "season": 2026, **extra}
    return c.post("/api/espn/link", headers=_h(token), data=json.dumps(body))


# ---------------------------------------------------------------------------
# flag gating
# ---------------------------------------------------------------------------

def test_routes_404_when_flag_off(client):
    c, token, _ = client
    with patch.object(server, "is_enabled", lambda k: False):
        assert _link(c, token).status_code == 404
        assert c.get("/api/espn/leagues", headers=_h(token)).status_code == 404
        assert c.post("/api/espn/import", headers=_h(token),
                      data=json.dumps({"league_id": ESPN_LEAGUE})).status_code == 404


# ---------------------------------------------------------------------------
# link — preview + import
# ---------------------------------------------------------------------------

def test_link_preview_returns_teams_and_persists_nothing(client):
    c, token, engine = client
    r = _link(c, token)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["status"] == "choose_team"
    assert body["league"]["name"] == "Recorded Shape Dynasty"
    assert len(body["teams"]) == 3
    assert {t["team_id"] for t in body["teams"]} == {1, 2, 3}
    assert all(t["mapped_players"] == 8 for t in body["teams"])
    assert body["report"]["match_rate"] == 1.0
    # preview never writes
    with engine.connect() as conn:
        assert conn.execute(select(db_module.leagues_table)).fetchall() == []
        assert conn.execute(select(db_module.league_members_table)).fetchall() == []


def test_link_import_persists_league_and_crosswalked_members(client):
    c, token, engine = client
    r = _link(c, token, team_id=1)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["platform"] == "espn"
    assert body["auth"] == "public"
    assert body["teams_imported"] == 3
    assert body["my_team_id"] == 1
    assert len(body["my_roster"]) == 8
    # fixture rosters crosswalk 24/24 (K/DST out of pool, not failures)
    assert body["report"]["pool_players"] == 24
    assert body["report"]["match_rate"] == 1.0
    assert body["report"]["unmatched"] == []
    assert body["report"]["out_of_pool"] == 2

    with engine.connect() as conn:
        lg = conn.execute(select(db_module.leagues_table)).fetchone()._mapping
        assert lg["sleeper_league_id"] == ESPN_LEAGUE
        assert lg["platform"] == "espn"
        assert lg["user_id"] == USER
        assert lg["espn_season"] == 2026
        assert lg["espn_auth"] == "public"
        assert lg["espn_my_team_id"] == 1
        assert lg["total_rosters"] == 3

        members = conn.execute(select(db_module.league_members_table)).fetchall()
        by_uid = {m.user_id: m for m in members}
        assert len(members) == 3
        # the chosen team binds to the SESSION user id
        assert USER in by_uid
        # counterparties get synthetic espn: ids (SWID-based, deterministic)
        others = [uid for uid in by_uid if uid != USER]
        assert all(uid.startswith("espn:") for uid in others)
        # rosters persist as Sleeper-id JSON arrays
        my_ids = json.loads(by_uid[USER].roster_data)
        assert my_ids == body["my_roster"]
        assert all(str(pid).isdigit() for pid in my_ids)


def test_link_is_idempotent_on_relink(client):
    c, token, engine = client
    assert _link(c, token, team_id=1).status_code == 200
    r = _link(c, token, team_id=2)   # re-link, different team choice
    assert r.status_code == 200
    with engine.connect() as conn:
        leagues = conn.execute(select(db_module.leagues_table)).fetchall()
        members = conn.execute(select(db_module.league_members_table)).fetchall()
    assert len(leagues) == 1
    assert leagues[0]._mapping["espn_my_team_id"] == 2
    assert len(members) == 3          # replaced, not duplicated
    assert sum(1 for m in members if m.user_id == USER) == 1


def test_link_unmatched_players_are_skipped_and_reported(client):
    c, token, _ = client
    doctored = _fixture_payload()
    entry = doctored["teams"][0]["roster"]["entries"][0]
    player = entry["playerPoolEntry"]["player"]
    player["id"] = 999999999
    player["fullName"] = "Totally Unknown"
    entry["playerId"] = 999999999
    with patch.object(es, "fetch_league", lambda *a, **kw: doctored):
        r = _link(c, token, team_id=1)
    assert r.status_code == 200
    body = r.get_json()
    assert [u["name"] for u in body["report"]["unmatched"]] == ["Totally Unknown"]
    assert body["report"]["match_rate"] == pytest.approx(23 / 24, abs=1e-4)
    assert len(body["my_roster"]) == 7   # dropped, never a placeholder


def test_link_input_validation(client):
    c, token, _ = client
    r = c.post("/api/espn/link", headers=_h(token),
               data=json.dumps({"espn_league_id": "not-numeric"}))
    assert r.status_code == 400 and r.get_json()["error"] == "espn_bad_league_id"
    # one cookie without the other
    r = _link(c, token, espn_s2="AEB%2Fxyz")
    assert r.status_code == 400 and r.get_json()["error"] == "espn_cookies_incomplete"
    # team not in the league
    r = _link(c, token, team_id=99)
    assert r.status_code == 400 and r.get_json()["error"] == "espn_bad_team_id"


def test_link_maps_espn_auth_error_to_403(client):
    c, token, _ = client
    def _raise(*a, **kw):
        raise es.EspnAuthError()
    with patch.object(es, "fetch_league", _raise):
        r = _link(c, token)
    assert r.status_code == 403
    assert r.get_json()["error"] == "espn_auth_required"


def test_link_private_league_stores_encrypted_cookies(client):
    c, token, engine = client
    s2 = "AEB%2FvS0me%2Bencoded%3Dvalue"
    swid = "{ABCD-1234}"
    r = _link(c, token, team_id=1, espn_s2=s2, swid=swid)
    assert r.status_code == 200
    assert r.get_json()["auth"] == "cookie"
    with engine.connect() as conn:
        row = conn.execute(select(db_module.espn_credentials_table)).fetchone()._mapping
    assert row["user_id"] == USER
    assert row["swid"] == swid
    assert row["espn_s2_encrypted"] != s2          # never plaintext
    from backend.sleeper_write import decrypt_token
    assert decrypt_token(row["espn_s2_encrypted"]) == s2
    with engine.connect() as conn:
        lg = conn.execute(select(db_module.leagues_table)).fetchone()._mapping
    assert lg["espn_auth"] == "cookie"


# ---------------------------------------------------------------------------
# GET /api/espn/leagues
# ---------------------------------------------------------------------------

def test_espn_leagues_lists_linked_league_with_rosters(client):
    c, token, _ = client
    assert c.get("/api/espn/leagues", headers=_h(token)).get_json() == {"leagues": []}
    _link(c, token, team_id=1)
    r = c.get("/api/espn/leagues", headers=_h(token))
    assert r.status_code == 200
    leagues = r.get_json()["leagues"]
    assert len(leagues) == 1
    lg = leagues[0]
    assert lg["league_id"] == ESPN_LEAGUE
    assert lg["platform"] == "espn"
    assert lg["my_team_id"] == 1
    assert lg["season"] == 2026
    assert len(lg["members"]) == 3
    mine = next(m for m in lg["members"] if m["user_id"] == USER)
    assert len(mine["player_ids"]) == 8


# ---------------------------------------------------------------------------
# POST /api/espn/import — re-sync
# ---------------------------------------------------------------------------

def test_import_resyncs_rosters_preserving_binding(client):
    c, token, engine = client
    _link(c, token, team_id=1)
    # simulate a roster move on ESPN: team 1 loses its first skill player
    changed = _fixture_payload()
    dropped = changed["teams"][0]["roster"]["entries"].pop(0)
    changed["teams"][1]["roster"]["entries"].append(dropped)
    with patch.object(es, "fetch_league", lambda *a, **kw: changed):
        r = c.post("/api/espn/import", headers=_h(token),
                   data=json.dumps({"league_id": ESPN_LEAGUE}))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["my_team_id"] == 1
    assert len(body["my_roster"]) == 7
    with engine.connect() as conn:
        members = conn.execute(select(db_module.league_members_table)).fetchall()
    by_uid = {m.user_id: json.loads(m.roster_data) for m in members}
    assert len(by_uid[USER]) == 7
    assert max(len(ids) for ids in by_uid.values()) == 9


def test_import_unknown_league_404s(client):
    c, token, _ = client
    r = c.post("/api/espn/import", headers=_h(token),
               data=json.dumps({"league_id": "12345"}))
    assert r.status_code == 404 and r.get_json()["error"] == "espn_not_linked"


# ---------------------------------------------------------------------------
# crosswalk cache fallback (espn_service.get_crosswalk)
# ---------------------------------------------------------------------------

def test_get_crosswalk_falls_back_to_snapshot_when_fetch_fails(monkeypatch):
    # reset module cache
    monkeypatch.setattr(es, "_xwalk_cache", None)
    monkeypatch.setattr(es, "_xwalk_fetched_at", 0.0)
    monkeypatch.setattr(es, "_xwalk_is_snapshot", False)

    def _failing_opener(request, timeout=None):
        raise OSError("offline")

    xw = es.get_crosswalk(_opener=_failing_opener)
    assert xw.by_espn_id.get("4362628") == "7564"   # snapshot content served
    assert es._xwalk_is_snapshot is True
    # cached — a second call inside the retry window doesn't refetch
    calls = {"n": 0}
    def _counting_opener(request, timeout=None):
        calls["n"] += 1
        raise OSError("offline")
    assert es.get_crosswalk(_opener=_counting_opener) is xw
    assert calls["n"] == 0
