"""Tests for POST /api/entry/platform — sessionless ESPN/MFL entry
(landing platform options v2, D-164; docs/plans/landing-platform-options/).

The route is the platform twin of /api/extension/auth's claim-a-username
door: preview a league with no session, then mint a session for a
DETERMINISTIC user id derived from the claimed team. The league import
itself stays on the canonical /api/{espn,mfl}/link routes, driven by the
freshly minted token — the last test proves that handoff end-to-end.

Flask test client against an isolated in-memory SQLite DB. No network:
ESPN payload and MFL bundle come from the existing link-route fixtures,
the crosswalk from the DP snapshot. `_extension_build_session` is replaced
with the lightweight fake from test_account_first.py (the real one warms
the whole Sleeper player cache), which still upserts the users row and
registers the session — the seams this suite asserts on.
"""
import copy
import json
import os
import time
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.espn_service as es
import backend.mfl_service as mfl
import backend.server as server
from backend.database import metadata

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
ESPN_FIXTURE = os.path.join(FIXTURES, "espn_league_snapshot_2026-07-11.json")
MFL_FIXTURE = os.path.join(FIXTURES, "mfl_league_snapshot_2026-07-17.json")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")

ESPN_LEAGUE = "987654321"
MFL_LEAGUE = "10005"
# From the fixtures: ESPN team 1 = "Chalk Dusters", owner SWID {A111…};
# MFL franchise 0001 = "Clobberin Time 2".
ESPN_TEAM_1_SWID = "{A1111111-1111-1111-1111-111111111111}"

ENTRY_FLAGS = {"landing.platform_options", "espn.link", "mfl.link"}


def _fake_extension_builder(user_id, username, display_name, avatar,
                            token=None):
    tok = token or f"entry-sess-{user_id}"
    payload = {"user_id": user_id, "username": username,
               "display_name": display_name,
               "active_format": "1qb_ppr", "last_active": time.time()}
    with db_module.engine.begin() as conn:
        exists = conn.execute(
            select(db_module.users_table.c.sleeper_user_id).where(
                db_module.users_table.c.sleeper_user_id == user_id
            )
        ).fetchone()
        if exists is None:
            conn.execute(insert(db_module.users_table).values(
                sleeper_user_id=user_id, username=username,
                display_name=display_name, created_at="2026-08-26"))
    with server._sessions_lock:
        server._sessions[tok] = payload
    return tok, payload


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    xwalk = es.load_crosswalk(XWALK_FIXTURE)
    with open(ESPN_FIXTURE) as f:
        espn_payload = json.load(f)
    with open(MFL_FIXTURE) as f:
        mfl_bundle = json.load(f)

    with server._sessions_lock:
        before = set(server._sessions)

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in ENTRY_FLAGS), \
         patch.object(es, "get_crosswalk", lambda _opener=None: xwalk), \
         patch.object(es, "fetch_league",
                      lambda *a, **kw: copy.deepcopy(espn_payload)), \
         patch.object(mfl, "resolve_host",
                      lambda *a, **kw: "www48.myfantasyleague.com"), \
         patch.object(mfl, "fetch_league_bundle",
                      lambda *a, **kw: copy.deepcopy(mfl_bundle)), \
         patch.object(server, "_extension_build_session",
                      _fake_extension_builder), \
         patch.object(server, "_link_device_identity",
                      lambda **kw: None):
        try:
            yield c, engine
        finally:
            with server._sessions_lock:
                for t in set(server._sessions) - before:
                    server._sessions.pop(t, None)


def _entry(c, **body):
    return c.post("/api/entry/platform",
                  headers={"Content-Type": "application/json"},
                  data=json.dumps(body))


# ── flag gating ─────────────────────────────────────────────────────────────

def test_404_when_feature_flag_off(client):
    c, _ = client
    with patch.object(server, "is_enabled",
                      lambda k: k in ENTRY_FLAGS - {"landing.platform_options"}):
        r = _entry(c, platform="mfl", mfl_league_id=MFL_LEAGUE, year=2026)
        assert r.status_code == 404


def test_404_when_platform_flag_off(client):
    c, _ = client
    with patch.object(server, "is_enabled",
                      lambda k: k in ENTRY_FLAGS - {"mfl.link"}):
        r = _entry(c, platform="mfl", mfl_league_id=MFL_LEAGUE, year=2026)
        assert r.status_code == 404
    with patch.object(server, "is_enabled",
                      lambda k: k in ENTRY_FLAGS - {"espn.link"}):
        r = _entry(c, platform="espn", espn_league_id=ESPN_LEAGUE)
        assert r.status_code == 404


def test_400_bad_platform(client):
    c, _ = client
    r = _entry(c, platform="fleaflicker")
    assert r.status_code == 400
    assert r.get_json()["error"] == "bad_platform"


# ── MFL ─────────────────────────────────────────────────────────────────────

def test_mfl_preview_mints_nothing_persists_nothing(client):
    c, engine = client
    with server._sessions_lock:
        sessions_before = set(server._sessions)
    r = _entry(c, platform="mfl", mfl_league_id=MFL_LEAGUE, year=2026)
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "choose_team"
    assert body["league"]["mfl_league_id"] == MFL_LEAGUE
    assert {t["team_id"] for t in body["teams"]} == {"0001", "0002", "0003"}
    assert "session_token" not in body
    with server._sessions_lock:
        assert set(server._sessions) == sessions_before
    with engine.connect() as conn:
        assert conn.execute(select(db_module.users_table)).fetchall() == []
        assert conn.execute(select(db_module.leagues_table)).fetchall() == []


def test_mfl_mint_returns_deterministic_entry_session(client):
    c, engine = client
    r = _entry(c, platform="mfl", mfl_league_id=MFL_LEAGUE, year=2026,
               franchise_id="0001")
    assert r.status_code == 200
    body = r.get_json()
    expected_uid = f"entry:mfl:{MFL_LEAGUE}.f0001"
    assert body["stage"] == "connected"
    assert body["user_id"] == expected_uid
    assert body["platform"] == "mfl"
    assert body["team_id"] == "0001"
    assert body["display_name"] == "Clobberin Time 2"
    token = body["session_token"]
    with server._sessions_lock:
        assert server._sessions[token]["user_id"] == expected_uid
    with engine.connect() as conn:
        row = conn.execute(
            select(db_module.users_table.c.display_name).where(
                db_module.users_table.c.sleeper_user_id == expected_uid)
        ).fetchone()
    assert row is not None and row[0] == "Clobberin Time 2"

    # Re-claiming the same franchise = same identity, fresh token.
    r2 = _entry(c, platform="mfl", mfl_league_id=MFL_LEAGUE, year=2026,
                franchise_id="0001")
    assert r2.status_code == 200
    assert r2.get_json()["user_id"] == expected_uid


def test_mfl_bad_franchise_400(client):
    c, _ = client
    r = _entry(c, platform="mfl", mfl_league_id=MFL_LEAGUE, year=2026,
               franchise_id="0099")
    assert r.status_code == 400
    assert r.get_json()["error"] == "mfl_bad_team_id"


def test_mfl_minted_token_drives_the_canonical_import(client):
    """The money test: mint → the real /api/mfl/link import under the fresh
    token binds the claimed franchise to the entry user in league_members."""
    c, engine = client
    entry_uid = f"entry:mfl:{MFL_LEAGUE}.f0001"
    token = _entry(c, platform="mfl", mfl_league_id=MFL_LEAGUE, year=2026,
                   franchise_id="0001").get_json()["session_token"]
    r = c.post("/api/mfl/link",
               headers={"X-Session-Token": token,
                        "Content-Type": "application/json"},
               data=json.dumps({"mfl_league_id": MFL_LEAGUE, "year": 2026,
                                "franchise_id": "0001"}))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["ok"] is True
    with engine.connect() as conn:
        members = conn.execute(
            select(db_module.league_members_table.c.user_id).where(
                db_module.league_members_table.c.league_id == MFL_LEAGUE)
        ).fetchall()
        league = conn.execute(
            select(db_module.leagues_table.c.user_id).where(
                db_module.leagues_table.c.sleeper_league_id == MFL_LEAGUE)
        ).fetchone()
    member_ids = {m[0] for m in members}
    assert entry_uid in member_ids
    assert all(uid == entry_uid or uid.startswith("mfl:")
               for uid in member_ids)
    assert league is not None and league[0] == entry_uid


# ── ESPN ────────────────────────────────────────────────────────────────────

def test_espn_preview_shape(client):
    c, _ = client
    r = _entry(c, platform="espn", espn_league_id=ESPN_LEAGUE)
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "choose_team"
    assert body["league"]["espn_league_id"] == ESPN_LEAGUE
    assert {t["team_id"] for t in body["teams"]} == {1, 2, 3}


def test_espn_bad_league_id_and_cookie_xor(client):
    c, _ = client
    assert _entry(c, platform="espn",
                  espn_league_id="not-a-number").status_code == 400
    r = _entry(c, platform="espn", espn_league_id=ESPN_LEAGUE,
               espn_s2="only-half")
    assert r.status_code == 400
    assert r.get_json()["error"] == "espn_cookies_incomplete"


def test_espn_mint_swid_keyed_identity(client):
    c, engine = client
    r = _entry(c, platform="espn", espn_league_id=ESPN_LEAGUE, team_id=1)
    assert r.status_code == 200
    body = r.get_json()
    assert body["user_id"] == f"entry:espn:{ESPN_TEAM_1_SWID}"
    assert body["display_name"] == "Chalk Dusters"
    with server._sessions_lock:
        assert server._sessions[body["session_token"]]["user_id"] == body["user_id"]


def test_espn_mint_wrong_account_403(client):
    """#321 parity: a cookie pair whose SWID doesn't own the claimed team is
    refused with the same wrong_account shape the link route uses."""
    c, _ = client
    r = _entry(c, platform="espn", espn_league_id=ESPN_LEAGUE, team_id=1,
               espn_s2="live-cookie",
               swid="{B2222222-2222-2222-2222-222222222222}")
    assert r.status_code == 403
    body = r.get_json()
    assert body["error"] == "espn_bad_credentials"
    assert body["reason"] == "wrong_account"


def test_espn_bad_team_400(client):
    c, _ = client
    r = _entry(c, platform="espn", espn_league_id=ESPN_LEAGUE, team_id=99)
    assert r.status_code == 400
    assert r.get_json()["error"] == "espn_bad_team_id"


def test_espn_private_league_maps_to_auth_required(client):
    c, _ = client
    with patch.object(es, "fetch_league",
                      side_effect=es.EspnError("private", kind="auth")):
        r = _entry(c, platform="espn", espn_league_id=ESPN_LEAGUE)
    assert r.status_code == 403
    assert r.get_json()["error"] == "espn_auth_required"
