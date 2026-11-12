"""Onboarding test profile — REAL ESPN / MFL linking (option A).

Plan: docs/plans/onboarding-test-profile/design.md §11 (operator ruling
2026-11-11: linking must be the production flows; option A chosen).

The production linking routes run unchanged for a test profile except for
two seams in backend/test_profile.py:
  storage_league_id(user, real_id)  — WRITE seam: identity for every real
      user; `qa_tp:<real>:<id>` for the test profile `qa_tp_<real>`.
  native_league_id(stored_id)       — READ seam, called inside the platform
      URL builders (espn_service.league_url, mfl_service.export_url /
      resolve_host) and where ESPN credential verification reads the
      caller's linked leagues.

Covers:
  seams     identity (`is`) for real users, mapping + idempotence for the
            test profile; URL builders read the native id and are
            byte-identical for real ids; an AST guard fails if a linking
            write site anywhere in server.py skips the write seam
  flows     ESPN preview + import, ESPN credential-only store, MFL public
            link, MFL login + auth-import — all through the production
            routes, with every platform read made with the native id and
            every row written under the profile's namespace / user id
  first run the linked league initializes (/api/session/init) with the
            profile's roster, synthetic opponents and the league's format
  (c)       linking the SAME ESPN and MFL leagues the real account has
            linked leaves every real row — league, members, rankings,
            preferences, credentials — byte-identical
  failures  incomplete cookies, private league (auth), wrong password /
            rejected sign-in, wrong ESPN account (#321), ESPN outage, zero
            leagues, MFL bad password / missing fields / outage: the test
            profile gets exactly the response a brand-new real user gets
  reset     deletes the credential rows and namespaced league rows that
            linking created, and nothing else
  fence     Sleeper / Fleaflicker linking stay refused; ESPN / MFL are open

Harness: test_espn_link_route.py / test_mfl_auth_link_route.py patterns —
in-memory SQLite, fixture payloads patched over the platform fetchers, no
network (no_real_network).
"""
import ast
import copy
import json
import os
import pathlib
import time
import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db
import backend.espn_service as es
import backend.mfl_service as mfl
import backend.server as server
import backend.test_profile as tp

pytestmark = pytest.mark.usefixtures("no_real_network")

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
ESPN_FIXTURE = FIX / "espn_league_snapshot_2026-07-11.json"
MFL_FIXTURE = FIX / "mfl_league_snapshot_2026-07-17.json"
XWALK_FIXTURE = FIX / "dp_playerids_snapshot_2026-07-11.csv"

REAL = "111222333"
NEWU = "444555666"          # a brand-new REAL user — the parity baseline
PID = "qa_tp_" + REAL
ESPN_LG = "987654321"       # the id inside the ESPN fixture
MFL_LG = "10005"
OWNER1 = "{A1111111-1111-1111-1111-111111111111}"   # owns ESPN team 1
OWNER2 = "{B2222222-2222-2222-2222-222222222222}"
TOK = {REAL: "tpl-real", NEWU: "tpl-newu", PID: "tpl-test"}
COOKIE = "MFL_USER_ID=user_0123abc"
MY_MFL = [{"league_id": MFL_LG, "name": "Masters Copper Dynasty League",
           "host": "www48.myfantasyleague.com", "franchise_id": "0001",
           "franchise_name": "Team One"}]


def _espn_payload():
    return json.loads(ESPN_FIXTURE.read_text())


def _h(uid):
    return {"X-Session-Token": TOK[uid], "Content-Type": "application/json"}


def _dump(engine):
    out = {}
    with engine.connect() as conn:
        for t in db.metadata.sorted_tables:
            out[t.name] = sorted((tuple(r) for r in conn.execute(select(t))), key=repr)
    return out


def _not_test(dump):
    return {t: [r for r in rows if PID not in repr(r) and "qa_tp:" not in repr(r)]
            for t, rows in dump.items()}


@pytest.fixture()
def world(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv(tp.ENV_VAR, REAL)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    flags = {"dev.test_profile", "espn.link", "espn.league_picker", "mfl.link", "mfl.auth_link"}
    monkeypatch.setattr(server, "is_enabled", lambda k: k in flags)

    xwalk = es.load_crosswalk(str(XWALK_FIXTURE))
    calls = {"espn": [], "mfl": []}
    state = {"espn_error": None, "probe_error": None, "fan_leagues": [],
             "mfl_login_error": None, "mfl_fetch_error": None}

    def _fetch_league(league_id, season, espn_s2=None, swid=None, timeout=15, _opener=None):
        calls["espn"].append(str(league_id))
        err = state["espn_error"]
        if err:
            raise err
        if str(league_id) != ESPN_LG:
            raise es.EspnError("no such league", kind="not_found")
        return _espn_payload()

    def _probe(espn_s2, swid, timeout=15, _opener=None):
        if state["probe_error"]:
            raise state["probe_error"]
        return {"football_leagues": [{"league_id": ESPN_LG}], "fantasy_entries": 1,
                "recognized": True}

    def _fan_leagues(espn_s2, swid, timeout=15, _opener=None):
        return copy.deepcopy(state["fan_leagues"])

    def _bundle(league_id, year, host, cookie=None, timeout=15, _opener=None):
        calls["mfl"].append(str(league_id))
        if state["mfl_fetch_error"]:
            raise state["mfl_fetch_error"]
        return json.loads(MFL_FIXTURE.read_text())

    def _login(u, p, y, **kw):
        if state["mfl_login_error"]:
            raise state["mfl_login_error"]
        return {"cookie": COOKIE, "mfl_user_id": "user_0123abc"}

    def _resolve(league_id, year, timeout=15, _opener=None):
        calls["mfl"].append(str(league_id))
        return "www48.myfantasyleague.com"

    monkeypatch.setattr(es, "get_crosswalk", lambda _opener=None: xwalk)
    monkeypatch.setattr(es, "fetch_league", _fetch_league)
    monkeypatch.setattr(es, "probe_fan_profile", _probe)
    monkeypatch.setattr(es, "fetch_fan_leagues", _fan_leagues)
    monkeypatch.setattr(mfl, "fetch_league_bundle", _bundle)
    monkeypatch.setattr(mfl, "login", _login)
    monkeypatch.setattr(mfl, "fetch_my_leagues", lambda cookie, year, **kw: copy.deepcopy(MY_MFL))
    monkeypatch.setattr(mfl, "resolve_host", _resolve)

    for uid in (REAL, NEWU):
        db.upsert_user(uid, username=f"u{uid}", display_name=f"U {uid}")
    db.upsert_user(PID, username=PID, display_name="Test profile")
    with server._sessions_lock:
        for uid, tok in TOK.items():
            server._sessions[tok] = {"user_id": uid, "verified": True, "active_format": "1qb_ppr",
                                     "last_active": time.time(), "_persisted_at": time.time()}
    server._reset_signin_limiter()
    server.app.config["TESTING"] = True
    try:
        yield {"client": server.app.test_client(), "engine": engine, "calls": calls,
               "state": state}
    finally:
        server._reset_signin_limiter()
        with server._sessions_lock:
            for tok in TOK.values():
                server._sessions.pop(tok, None)
        engine.dispose()


def _post(w, uid, path, body):
    return w["client"].post(path, headers=_h(uid), data=json.dumps(body))


def _espn_import(w, uid, **extra):
    return _post(w, uid, "/api/espn/link", {"espn_league_id": ESPN_LG, "season": 2026,
                                           "team_id": 1, **extra})


def _seed_real_links(w):
    """The REAL account has linked the same ESPN and MFL leagues, ranked in
    them, saved preferences and stored credentials."""
    assert _espn_import(w, REAL).status_code == 200
    assert _post(w, REAL, "/api/mfl/auth-link",
                 {"username": "realmfl", "password": "pw", "year": 2026}).status_code == 200
    assert _post(w, REAL, "/api/mfl/auth-import", {"year": 2026}).status_code == 200
    assert _post(w, REAL, "/api/espn/link", {"espn_s2": "REALS2", "swid": OWNER1}).status_code == 200
    with w["engine"].begin() as conn:
        for lid in (ESPN_LG, MFL_LG):
            conn.execute(insert(db.member_rankings_table).values(
                user_id=REAL, league_id=lid, player_id="4046", elo=1600.0,
                scoring_format="1qb_ppr", updated_at="2026-11-01T00:00:00"))
            conn.execute(insert(db.league_preferences_table).values(
                user_id=REAL, league_id=lid, team_outlook="contender",
                updated_at="2026-11-01T00:00:00"))


# ── seams ──────────────────────────────────────────────────────────────────

def test_seams_are_identity_for_real_users_and_map_the_test_profile():
    for real_lid in ("987654321", "10005", "local_league", ""):
        assert tp.storage_league_id(REAL, real_lid) is real_lid
        assert tp.storage_league_id("acct_9f8e", real_lid) is real_lid
        assert tp.native_league_id(real_lid) is real_lid
    assert tp.storage_league_id(PID, ESPN_LG) == f"qa_tp:{REAL}:{ESPN_LG}"
    stored = tp.storage_league_id(PID, ESPN_LG)
    assert tp.storage_league_id(PID, stored) == stored            # idempotent
    assert tp.native_league_id(stored) == ESPN_LG
    assert tp.native_league_id("qa_tp:acct_9f8e:10005") == "10005"


def test_platform_url_builders_read_the_native_id():
    stored = f"qa_tp:{REAL}:{ESPN_LG}"
    assert es.league_url(stored, 2026) == es.league_url(ESPN_LG, 2026)
    assert "qa_tp" not in es.league_url(stored, 2026)
    assert mfl.export_url("www48.myfantasyleague.com", 2026, "league", f"qa_tp:{REAL}:{MFL_LG}") \
        == mfl.export_url("www48.myfantasyleague.com", 2026, "league", MFL_LG)
    seen = []

    def _opener(req, timeout=15):
        seen.append(req.full_url)
        return "https://www48.myfantasyleague.com/2026/home/10005"

    for lid in (MFL_LG, f"qa_tp:{REAL}:{MFL_LG}"):
        assert mfl.resolve_host(lid, 2026, _opener=_opener) == "www48.myfantasyleague.com"
    assert len(seen) == 2 and seen[0] == seen[1] and "qa_tp" not in seen[0]


SERVER = pathlib.Path(server.__file__)
WRITERS = {"upsert_espn_league", "upsert_platform_league", "replace_espn_league_members",
           "_platform_roster_history_on_sync", "_sync_mfl_owned_picks", "_mfl_store_scoring_format"}
# Linking routes: their league ids come from the request / the platform.
SEAMED = {"espn_link", "espn_import", "mfl_link", "mfl_import", "_mfl_import_league_authed"}
# Callers whose league id is already a STORED id (read from a leagues row or
# the session league), so it is in the right namespace by construction.
STORED_ID_CALLERS = {"session_init", "_session_init_background_writes_impl",
                     "_refresh_league_draft_status", "mfl_leagues"}
# Fenced off for a test-profile session (backend/server.py _TP_BLOCKED_ENDPOINTS).
FENCED = {"fleaflicker_link", "fleaflicker_import"}


def _league_arg(call):
    for kw in call.keywords:
        if kw.arg == "league_id":
            return kw.value
    return call.args[0] if call.args else None


def test_every_linking_write_site_goes_through_the_write_seam():
    tree = ast.parse(SERVER.read_text())
    found = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in WRITERS:
                found.setdefault(fn.name, []).append(node)
    unknown = set(found) - SEAMED - STORED_ID_CALLERS - FENCED - set(WRITERS)
    assert not unknown, f"new linking write site(s) without the seam: {sorted(unknown)}"
    assert SEAMED <= set(found), f"seamed routes lost their writes: {SEAMED - set(found)}"
    for name in SEAMED:
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
        seams = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "store_lid" for t in n.targets)]
        assert len(seams) == 1, f"{name}: exactly one store_lid assignment"
        val = seams[0].value
        assert isinstance(val, ast.Call) and ast.unparse(val.func) == "_tp.storage_league_id", name
        for call in found[name]:
            arg = _league_arg(call)
            assert isinstance(arg, ast.Name) and arg.id == "store_lid", \
                f"{name}: {call.func.id} writes {ast.unparse(arg) if arg else None}, not store_lid"
        # The id handed back to the client is the stored one.
        for d in (n for n in ast.walk(fn) if isinstance(n, ast.Dict)):
            for k, v in zip(d.keys, d.values):
                if isinstance(k, ast.Constant) and k.value == "league_id" \
                        and isinstance(v, ast.Name) and v.id == "league_id":
                    pytest.fail(f"{name}: returns the native league_id, not store_lid")
    for name in FENCED:
        assert name in server._TP_BLOCKED_ENDPOINTS


# ── flows ──────────────────────────────────────────────────────────────────

def test_espn_preview_and_import_run_the_production_route(world):
    w = world
    prev_new = _post(w, NEWU, "/api/espn/link", {"espn_league_id": ESPN_LG, "season": 2026})
    prev_test = _post(w, PID, "/api/espn/link", {"espn_league_id": ESPN_LG, "season": 2026})
    assert prev_test.status_code == prev_new.status_code == 200
    assert prev_test.get_json() == prev_new.get_json()          # identical preview
    r = _espn_import(w, PID)
    assert r.status_code == 200, r.get_json()
    stored = f"qa_tp:{REAL}:{ESPN_LG}"
    assert r.get_json()["league_id"] == stored
    assert set(w["calls"]["espn"]) == {ESPN_LG}                 # platform read: native only
    ids = {m["user_id"] for m in db.load_league_members(stored)}
    assert PID in ids and all(i == PID or i.startswith("qa_tpo_") for i in ids)
    assert db.load_league_members(ESPN_LG) == []                # nothing native written
    listed = w["client"].get("/api/espn/leagues", headers=_h(PID)).get_json()["leagues"]
    assert [lg["league_id"] for lg in listed] == [stored]
    # Re-sync of the stored id: the production import route, same seam.
    w["calls"]["espn"].clear()
    r2 = _post(w, PID, "/api/espn/import", {"league_id": stored})
    assert r2.status_code == 200 and r2.get_json()["league_id"] == stored
    assert set(w["calls"]["espn"]) == {ESPN_LG}


def test_espn_credentials_store_under_the_test_profile(world):
    w = world
    r = _post(w, PID, "/api/espn/link", {"espn_s2": "TESTS2", "swid": OWNER1})
    assert r.status_code == 200, r.get_json()
    with w["engine"].connect() as conn:
        users = [row.user_id for row in conn.execute(select(db.espn_credentials_table))]
    assert users == [PID]
    status = w["client"].get("/api/espn/link", headers=_h(PID)).get_json()
    assert status["connected"] is True and "espn_s2" not in json.dumps(status).lower()


def test_mfl_public_link_and_authed_import_run_the_production_routes(world):
    w = world
    r = _post(w, PID, "/api/mfl/link", {"mfl_league_id": MFL_LG, "year": 2026,
                                        "franchise_id": "0001"})
    assert r.status_code == 200, r.get_json()
    stored = f"qa_tp:{REAL}:{MFL_LG}"
    assert r.get_json()["league_id"] == stored
    a = _post(w, PID, "/api/mfl/auth-link", {"username": "realmfl", "password": "pw", "year": 2026})
    assert a.status_code == 200, a.get_json()
    i = _post(w, PID, "/api/mfl/auth-import", {"year": 2026})
    assert i.status_code == 200, i.get_json()
    assert [lg["league_id"] for lg in i.get_json()["imported"]] == [stored]
    assert all("qa_tp" not in c for c in w["calls"]["mfl"])     # platform read: native only
    ids = {m["user_id"] for m in db.load_league_members(stored)}
    assert PID in ids and all(x == PID or x.startswith("qa_tpo_") for x in ids)
    with w["engine"].connect() as conn:
        assert [row.user_id for row in conn.execute(select(db.mfl_credentials_table))] == [PID]
    assert db.load_league_members(MFL_LG) == []


@pytest.fixture()
def init_world(world, monkeypatch):
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format", {})
    monkeypatch.setattr(server, "g_universal_players", [])
    monkeypatch.setattr(server, "_kickoff_trade_job", MagicMock())
    monkeypatch.setattr(server, "_send_typed_push", MagicMock())
    real_thread = server.threading.Thread

    class _Inline(real_thread):
        def start(self):
            if self.name == "session-init-bg-writes":
                self.run()
                return
            super().start()

    monkeypatch.setattr(server.threading, "Thread", _Inline)
    return world


def _pool_from_league(lid):
    """The universal pool = every player on the imported rosters."""
    from backend.ranking_service import Player
    ids = sorted({p for m in db.load_league_members(lid) for p in m["player_ids"]})
    pool = [Player(i, f"P{i}", "RB", "AAA", 25, 1) for i in ids]
    seed = {p.id: 1500.0 for p in pool}
    server.g_universal_by_format.clear()
    server.g_universal_by_format.update(
        {"1qb_ppr": {"players": pool, "seed": seed}, "sf_tep": {"players": pool, "seed": seed}})


@pytest.mark.parametrize("platform", ["espn", "mfl"])
def test_first_run_completes_with_the_linked_league(init_world, platform):
    w = init_world
    if platform == "espn":
        lid = _espn_import(w, PID).get_json()["league_id"]
    else:
        lid = _post(w, PID, "/api/mfl/link", {"mfl_league_id": MFL_LG, "year": 2026,
                                              "franchise_id": "0001"}).get_json()["league_id"]
    _pool_from_league(lid)
    r = w["client"].post("/api/session/init", headers=_h(PID),
                         data=json.dumps({"user_id": PID, "league_id": lid}))
    assert r.status_code == 200, r.get_json()
    sess = server._get_session(TOK[PID])
    assert sess["league"].league_id == lid and sess["league"].platform == platform
    assert server._league_user_id(sess) == PID
    opp = {m.user_id for m in sess["league"].members}
    assert opp and all(x.startswith("qa_tpo_") for x in opp)  # synthetic opponents
    assert sess["active_format"] in ("1qb_ppr", "sf_tep")
    rosters = w["client"].get(f"/api/sleeper/rosters/{lid}", headers=_h(PID))
    assert rosters.status_code == 200 and rosters.get_json()


# ── (c) the real account's data is never touched ──────────────────────────

def test_linking_the_same_leagues_writes_nothing_real(world):
    w = world
    _seed_real_links(w)
    before = _not_test(_dump(w["engine"]))
    assert _espn_import(w, PID).status_code == 200
    assert _post(w, PID, "/api/espn/link", {"espn_s2": "TESTS2", "swid": OWNER1}).status_code == 200
    assert _post(w, PID, "/api/mfl/auth-link",
                 {"username": "realmfl", "password": "pw", "year": 2026}).status_code == 200
    assert _post(w, PID, "/api/mfl/auth-import", {"year": 2026}).status_code == 200
    after = _not_test(_dump(w["engine"]))
    assert after == before        # leagues, members, rankings, prefs, credentials
    # And the real account still resolves its own leagues and links.
    assert [lg["league_id"] for lg in db.load_espn_leagues_for_user(REAL)] == [ESPN_LG]
    assert w["client"].get("/api/espn/link", headers=_h(REAL)).get_json()["connected"] is True
    assert w["client"].get("/api/mfl/auth-link", headers=_h(REAL)).get_json()["connected"] is True


# ── failure paths: the test profile gets what a new real user gets ────────

def _wire(r):
    body = r.get_json() or {}
    return r.status_code, body.get("error"), body.get("reason")


FAILURES = {
    "espn_incomplete_cookies": lambda w, u: _post(
        w, u, "/api/espn/link", {"espn_league_id": ESPN_LG, "season": 2026, "espn_s2": "x"}),
    "espn_private_league": lambda w, u: (
        w["state"].update(espn_error=es.EspnAuthError("private")),
        _post(w, u, "/api/espn/link", {"espn_league_id": ESPN_LG, "season": 2026}))[1],
    "espn_outage": lambda w, u: (
        w["state"].update(espn_error=es.EspnError("down", kind="http")),
        _post(w, u, "/api/espn/link", {"espn_league_id": ESPN_LG, "season": 2026}))[1],
    "espn_rejected_sign_in": lambda w, u: (
        w["state"].update(probe_error=es.EspnAuthError("rejected")),
        _post(w, u, "/api/espn/link", {"espn_s2": "BAD", "swid": OWNER1}))[1],
    "espn_zero_leagues": lambda w, u: (
        _post(w, u, "/api/espn/link", {"espn_s2": "S2", "swid": OWNER1}),
        w["client"].get("/api/espn/my-leagues", headers=_h(u)))[1],
    "mfl_bad_password": lambda w, u: (
        w["state"].update(mfl_login_error=mfl.MflError("bad login", kind="auth")),
        _post(w, u, "/api/mfl/auth-link", {"username": "x", "password": "bad", "year": 2026}))[1],
    "mfl_missing_fields": lambda w, u: _post(
        w, u, "/api/mfl/auth-link", {"username": "x", "year": 2026}),
    "mfl_outage": lambda w, u: (
        w["state"].update(mfl_fetch_error=mfl.MflError("down", kind="http")),
        _post(w, u, "/api/mfl/link", {"mfl_league_id": MFL_LG, "year": 2026}))[1],
}


@pytest.mark.parametrize("case", sorted(FAILURES))
def test_failure_paths_match_a_new_real_user(world, case):
    w = world
    got = {}
    for uid in (NEWU, PID):
        w["state"].update(espn_error=None, probe_error=None, mfl_login_error=None,
                          mfl_fetch_error=None)
        server._reset_signin_limiter()
        got[uid] = _wire(FAILURES[case](w, uid))
    assert got[PID] == got[NEWU], got
    assert got[PID][0] in (200, 400, 401, 403, 409, 502, 503), got
    if case == "espn_zero_leagues":
        assert got[PID][0] == 200


def test_wrong_espn_account_is_refused_for_the_test_profile_too(world):
    """#321: each user's linked league is bound to team 1 (OWNER1); storing a
    pair whose SWID is OWNER2 must fail as wrong_account. For the test
    profile the bound league is a qa_tp: id, which verification reads back
    as the native id (the read seam)."""
    w = world
    got = {}
    for uid in (NEWU, PID):
        assert _espn_import(w, uid).status_code == 200
        with w["engine"].begin() as conn:     # the bound league is cookie-gated
            conn.execute(db.leagues_table.update().where(
                db.leagues_table.c.user_id == uid).values(espn_auth="cookie"))
        got[uid] = _wire(_post(w, uid, "/api/espn/link", {"espn_s2": "S2", "swid": OWNER2}))
    assert got[PID] == got[NEWU] == (403, "espn_bad_credentials", "wrong_account"), got


# ── reset and fence ────────────────────────────────────────────────────────

def test_reset_removes_linked_credentials_and_namespaced_leagues_only(world):
    w = world
    _seed_real_links(w)
    before_real = _not_test(_dump(w["engine"]))
    _espn_import(w, PID)
    _post(w, PID, "/api/espn/link", {"espn_s2": "TESTS2", "swid": OWNER1})
    _post(w, PID, "/api/mfl/auth-link", {"username": "m", "password": "pw", "year": 2026})
    _post(w, PID, "/api/mfl/auth-import", {"year": 2026})
    counts = tp.reset_profile(PID)
    for table in ("espn_credentials", "mfl_credentials", "leagues", "league_members"):
        assert counts.get(table), (table, counts)
    after = _dump(w["engine"])
    assert not any(PID in repr(r) or "qa_tp:" in repr(r)
                   for rows in after.values() for r in rows)
    assert _not_test(after) == before_real


def test_sleeper_and_fleaflicker_linking_stay_fenced(world):
    w = world
    for path in ("/api/sleeper/link", "/api/fleaflicker/link", "/api/fleaflicker/import"):
        r = _post(w, PID, path, {})
        assert r.status_code == 403 and r.get_json()["error"] == "test_profile_blocked", path
    for name in ("espn_link", "espn_import", "mfl_link", "mfl_import", "mfl_auth_link",
                 "mfl_auth_import"):
        assert name not in server._TP_BLOCKED_ENDPOINTS


def test_espn_and_mfl_onboarding_scan(init_world):
    """The decisive scan for ESPN and MFL (operator ruling 2026-11-12, item 4):
    after the real account has linked both leagues and the test profile runs
    both onboardings end to end (link → import → session init), (a) no
    test-profile row carries a real member id or a real league id, (b) every
    user- or league-keyed real row is byte-identical, (c) nothing went out."""
    w = init_world
    _seed_real_links(w)
    sends = []
    server_send = server._send_expo_push
    server._send_expo_push = lambda msgs: sends.append(msgs)
    try:
        keyed = {name for name, *_ in tp.reset_scope()}
        before = {t: r for t, r in _not_test(_dump(w["engine"])).items() if t in keyed}
        real_members = {m["user_id"] for lid in (ESPN_LG, MFL_LG)
                        for m in db.load_league_members(lid)} - {REAL}
        assert real_members
        lid_e = _espn_import(w, PID).get_json()["league_id"]
        _post(w, PID, "/api/mfl/auth-link", {"username": "m", "password": "pw", "year": 2026})
        lid_m = _post(w, PID, "/api/mfl/auth-import", {"year": 2026}).get_json()["imported"][0]["league_id"]
        for lid in (lid_e, lid_m):
            _pool_from_league(lid)
            r = w["client"].post("/api/session/init", headers=_h(PID),
                                 data=json.dumps({"user_id": PID, "league_id": lid}))
            assert r.status_code == 200, r.get_json()
        after = _dump(w["engine"])
        leaks = []
        for t, rows in after.items():
            for row in rows:
                text = repr(row)
                if PID not in text and "qa_tp:" not in text and "qa_tpo_" not in text:
                    continue
                text = text.replace(f"qa_tp:{REAL}:{ESPN_LG}", "").replace(
                    f"qa_tp:{REAL}:{MFL_LG}", "").replace(PID, "")
                hits = [m for m in real_members if m in text]
                hits += [x for x in (ESPN_LG, MFL_LG, OWNER2) if x in text]
                if hits:
                    leaks.append((t, hits))
        assert leaks == []                                                     # (a)
        assert {t: r for t, r in _not_test(after).items() if t in keyed} == before   # (b)
        assert sends == []                                                     # (c)
    finally:
        server._send_expo_push = server_send
