"""Proof-based ESPN/MFL sign-in at POST /api/entry/platform (2026-10-26).

The team-claim step of the sessionless entry route no longer mints a
claim-only `entry:*` session. It PROVES the claim, then signs into an account
anchored on the proven identity (design D1-D10; scope block in
docs/plans/platform-sign-in/scope.md):

  * ESPN (D4): pair present → cookie read OK → anonymous read must need auth
    (else espn_public_league) → the same espn_s2 with ANOTHER member's SWID
    must need auth (else espn_unproven_pair: the leaguemate attack) → the
    claimed team's owner_swid must be the pair's SWID (wrong_account;
    ownerless → espn_ownerless_team). Any non-auth answer on the two extra
    reads → espn_unavailable (fail closed).
  * MFL (D5): login + myleagues must list the claimed (league, franchise).
  * D3/D6: identity row → that account (bound Sleeper user restored);
    no row but the subject sits in another user's imported credential →
    409 platform_identity_in_use; else find_or_create_account. The
    uq_linked_identity race signs the loser into the winner's account.
  * D7: failed proofs rate-limited per IP (30/10 min, rightmost XFF) and per
    subject (5/15 min) → 429 too_many_attempts + Retry-After.
  * D9: one PLATFORM-SIGNIN audit line per claim, never a SWID / username /
    cookie / password.

head-eng's conditions (review 2026-10-27) are the `test_c<N>_*` tests; each
has a recorded sabotage in living-memory/TEST_LEDGER.md.

No network: most tests model ESPN with FakeEspn and MFL with an in-memory
user table. The condition-1 and condition-3 tests instead run the REAL
espn_service.fetch_league / mfl_service.login / fetch_my_leagues on top of a
fake urllib opener (FakeNet), so the real obs.api_events outbound capture and
error mapping are exercised. Session builders are faked (the real ones warm
the Sleeper player cache) but honour their contract: upsert the users row
and register the session.
"""
import ast
import copy
import hashlib
import importlib.util
import inspect
import io
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from http.client import HTTPMessage
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select, update
from sqlalchemy.exc import OperationalError

import backend.accounts as accounts
import backend.api_observability as api_obs
import backend.database as db_module
import backend.espn_service as es
import backend.mfl_service as mfl
import backend.server as server
from backend.database import metadata

# The real service functions, captured before any fixture patches them.
REAL_FETCH_LEAGUE = es.fetch_league
REAL_MFL_LOGIN = mfl.login
REAL_MFL_MY_LEAGUES = mfl.fetch_my_leagues

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
ESPN_FIXTURE = os.path.join(FIXTURES, "espn_league_snapshot_2026-07-11.json")
MFL_FIXTURE = os.path.join(FIXTURES, "mfl_league_snapshot_2026-07-17.json")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

ESPN_LEAGUE = "987654321"
MFL_LEAGUE = "10005"
# ESPN fixture: team 1 "Chalk Dusters" owned by A, 2 "Icy Veins" by B, 3 by C.
# D is a pair ESPN issued to a league member who owns no team.
SWID_A = "{A1111111-1111-1111-1111-111111111111}"
SWID_B = "{B2222222-2222-2222-2222-222222222222}"
SWID_C = "{C3333333-3333-3333-3333-333333333333}"
SWID_D = "{D4444444-4444-4444-4444-444444444444}"
S2_A = "s2-cookie-for-member-a%2Bxyz"
S2_B = "s2-cookie-for-member-b%2Bxyz"
S2_D = "s2-cookie-for-member-d%2Bxyz"
SLEEPER_UID = "313560442465169408"

FLAGS = {"landing.platform_options", "espn.link", "mfl.link",
         "espn.league_picker", "mfl.auth_link", "auth.persistent_sessions",
         "account.data_export"}

# MFL "server": login handle (case-insensitive) → (password, myleagues rows).
MFL_USERS = {
    "mattm": ("hunter2", [{"league_id": MFL_LEAGUE, "name": "Clobberin League",
                           "host": "www48.myfantasyleague.com",
                           "franchise_id": "0001",
                           "franchise_name": "Clobberin Time 2"}]),
    "rival": ("pw-rival", [{"league_id": MFL_LEAGUE, "name": "Clobberin League",
                            "host": "www48.myfantasyleague.com",
                            "franchise_id": "0002",
                            "franchise_name": "Other Franchise"}]),
    "loner": ("pw-loner", [{"league_id": "99999", "name": "Elsewhere",
                            "host": "www48.myfantasyleague.com",
                            "franchise_id": "0001",
                            "franchise_name": "Far Away"}]),
}


class FakeEspn:
    """ESPN's league read. `public`: every read is served. Private: an
    anonymous read needs auth; a cookie read needs an espn_s2 ESPN issued,
    and — when `bound` — the SWID that espn_s2 was issued with."""

    def __init__(self, payload, *, public=False, bound=True):
        self.payload = payload
        self.public = public
        self.bound = bound
        self.issued = {S2_A: SWID_A, S2_B: SWID_B, S2_D: SWID_D}
        self.calls = []

    def __call__(self, league_id, season, espn_s2=None, swid=None, **kw):
        cookie = bool(espn_s2 and swid)
        self.calls.append(("cookie" if cookie else "anon",
                           es.canonical_swid(swid).upper() if cookie else None))
        if self.public:
            return copy.deepcopy(self.payload)
        if not cookie:
            raise es.EspnAuthError()
        owner = self.issued.get(espn_s2)
        if owner is None:
            raise es.EspnAuthError()
        if self.bound and es.canonical_swid(swid).upper() != owner.upper():
            raise es.EspnAuthError()
        return copy.deepcopy(self.payload)


def _fake_login(username, password, year, **kw):
    rec = MFL_USERS.get(username.strip().lower())
    if rec is None or rec[0] != password:
        raise mfl.MflAuthError("MFL rejected the username/password")
    return {"cookie": f"MFL_USER_ID=c-{username.strip().lower()}",
            "mfl_user_id": "x"}


def _fake_my_leagues(cookie, year, **kw):
    handle = cookie.split("c-", 1)[1]
    return copy.deepcopy(MFL_USERS[handle][1])


def _register(user_id, username, display_name, avatar=None, **extra):
    tok = "tok-" + secrets.token_hex(8)
    payload = {"user_id": user_id, "username": username,
               "display_name": display_name, "active_format": "1qb_ppr",
               "last_active": time.time(), **extra}
    with db_module.engine.begin() as conn:
        exists = conn.execute(
            select(db_module.users_table.c.sleeper_user_id).where(
                db_module.users_table.c.sleeper_user_id == user_id)
        ).fetchone()
        if exists is None:
            conn.execute(insert(db_module.users_table).values(
                sleeper_user_id=user_id, username=username,
                display_name=display_name, created_at="2026-10-26"))
    with server._sessions_lock:
        server._sessions[tok] = payload
    return tok, payload


def _fake_extension_builder(user_id, username, display_name, avatar,
                            token=None):
    return _register(user_id, username, display_name, avatar)


def _fake_account_builder(user_id, display_name, token=None):
    return _register(user_id, "", display_name, account_only=True)


@pytest.fixture()
def env(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    xwalk = es.load_crosswalk(XWALK_FIXTURE)
    with open(ESPN_FIXTURE) as f:
        espn_payload = json.load(f)
    with open(MFL_FIXTURE) as f:
        mfl_bundle = json.load(f)
    fake = FakeEspn(espn_payload)
    with server._sessions_lock:
        before = set(server._sessions)
    server._reset_signin_limiter()

    class Env:
        pass

    e = Env()
    e.client = server.app.test_client()
    e.engine = engine
    e.espn = fake
    e.espn_payload = espn_payload
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in FLAGS), \
         patch.object(es, "get_crosswalk", lambda _opener=None: xwalk), \
         patch.object(es, "fetch_league", fake), \
         patch.object(mfl, "resolve_host",
                      lambda *a, **kw: "www48.myfantasyleague.com"), \
         patch.object(mfl, "fetch_league_bundle",
                      lambda *a, **kw: copy.deepcopy(mfl_bundle)), \
         patch.object(mfl, "login", _fake_login), \
         patch.object(mfl, "fetch_my_leagues", _fake_my_leagues), \
         patch.object(server, "_extension_build_session",
                      _fake_extension_builder), \
         patch.object(server, "_account_build_session",
                      _fake_account_builder), \
         patch.object(server, "_link_device_identity", lambda **kw: None):
        try:
            yield e
        finally:
            server._reset_signin_limiter()
            with server._sessions_lock:
                for t in set(server._sessions) - before:
                    server._sessions.pop(t, None)


def _post(env, ip="203.0.113.7", **body):
    return env.client.post("/api/entry/platform", json=body,
                           headers={"X-Forwarded-For": ip})


def _espn_claim(env, team_id=1, s2=S2_A, swid=SWID_A, **kw):
    body = {"platform": "espn", "espn_league_id": ESPN_LEAGUE,
            "team_id": team_id}
    if s2:
        body["espn_s2"] = s2
    if swid:
        body["swid"] = swid
    body.update(kw)
    return _post(env, **body)


def _mfl_claim(env, username="MattM", password="hunter2", franchise_id="0001",
               **kw):
    body = {"platform": "mfl", "mfl_league_id": MFL_LEAGUE, "year": 2026,
            "franchise_id": franchise_id}
    if username is not None:
        body["username"] = username
    if password is not None:
        body["password"] = password
    body.update(kw)
    return _post(env, **body)


def _rows(env, table):
    with env.engine.connect() as conn:
        return conn.execute(select(table)).fetchall()


def _assert_no_entry_ids(env):
    for row in _rows(env, db_module.users_table):
        assert not str(row.sleeper_user_id).startswith("entry:")
    for row in _rows(env, db_module.sessions_table):
        assert not str(row.user_id).startswith("entry:")
    with server._sessions_lock:
        assert not any(str(s.get("user_id", "")).startswith("entry:")
                       for s in server._sessions.values())


def _assert_nothing_created(env):
    assert _rows(env, db_module.accounts_table) == []
    assert _rows(env, db_module.linked_identities_table) == []
    assert _rows(env, db_module.users_table) == []
    assert _rows(env, db_module.sessions_table) == []


# ── ESPN proof (D4) ─────────────────────────────────────────────────────────

def test_espn_private_bound_pair_mints_verified_persisted_acct_session(env):
    r = _espn_claim(env)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    acct = body["account_id"]
    assert body["user_id"] == f"acct_{acct}"
    assert body["stage"] == "connected"
    assert body["verified"] is True and body["verified_via"] == "espn"
    assert body["account_only"] is True and body["username"] == ""
    assert body["account_created"] is True
    assert body["display_name"] == "Chalk Dusters"
    assert body["platform"] == "espn"
    assert body["league_id"] == ESPN_LEAGUE and body["team_id"] == 1
    assert body["avatar"] is None
    # Persisted session → the 90-day idle window, not the 4h unverified one.
    assert body["expires_at"] > time.time() + 89 * 86400
    # The reads, in D4 order: cookie read, anonymous read, control read with
    # ANOTHER member's SWID (never the pair's own).
    assert env.espn.calls == [("cookie", SWID_A), ("anon", None),
                              ("cookie", SWID_B)]
    sess = server._sessions[body["session_token"]]
    assert sess["verified"] is True and sess["verified_via"] == "espn"
    assert sess["account_id"] == acct
    [ident] = _rows(env, db_module.linked_identities_table)
    assert (ident.provider, ident.provider_subject) == ("espn", SWID_A.upper())
    assert accounts.get_user_verified_via(f"acct_{acct}") == "espn"
    [persisted] = _rows(env, db_module.sessions_table)
    assert persisted.user_id == f"acct_{acct}"
    assert persisted.verified_via == "espn" and persisted.account_id == acct
    # The mint stores no ESPN credential (the import does, later).
    assert _rows(env, db_module.espn_credentials_table) == []
    _assert_no_entry_ids(env)


def test_espn_session_expiry_is_4h_when_persistence_is_off(env):
    with patch.object(server, "is_enabled",
                      lambda k: k in FLAGS - {"auth.persistent_sessions"}):
        r = _espn_claim(env)
    assert r.status_code == 200
    assert r.get_json()["expires_at"] <= time.time() + 4 * 3600 + 5
    assert _rows(env, db_module.sessions_table) == []


def test_c7_refusal_espn_public_league(env):
    env.espn.public = True
    r = _espn_claim(env)
    assert r.status_code == 403
    body = r.get_json()
    assert body["error"] == "proof_unavailable"
    assert body["reason"] == "espn_public_league"
    assert body["message"].startswith("We can’t confirm this team is yours")
    _assert_nothing_created(env)


def test_c7_refusal_espn_unproven_pair_leaguemate_attack(env, caplog):
    """Member B's own valid espn_s2 + victim A's league-visible SWID, claiming
    A's team. If ESPN ignores the SWID, steps 2, 3 and 5 all pass; only the
    pair-binding control (same espn_s2, another member's SWID) catches it."""
    caplog.set_level(logging.WARNING, logger="trade_finder")
    env.espn.bound = False
    r = _espn_claim(env, s2=S2_B, swid=SWID_A)
    assert r.status_code == 403
    body = r.get_json()
    assert body["error"] == "proof_unavailable"
    assert body["reason"] == "espn_unproven_pair"
    unbound = [rec.getMessage() for rec in caplog.records
               if "ESPN-PAIR-UNBOUND" in rec.getMessage()]
    assert len(unbound) == 1
    assert "1111" not in unbound[0] and "2222" not in unbound[0]
    _assert_nothing_created(env)


def test_espn_leaguemate_attack_fails_the_cookie_read_when_pair_is_bound(env):
    r = _espn_claim(env, s2=S2_B, swid=SWID_A)
    assert r.status_code == 403
    assert r.get_json()["error"] == "espn_auth_required"
    _assert_nothing_created(env)


def test_espn_no_second_owner_swid_is_unproven(env, caplog):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    for t in env.espn.payload["teams"]:
        if t["id"] != 1:
            t["primaryOwner"] = ""
            t["owners"] = []
    r = _espn_claim(env)
    assert r.status_code == 403
    assert r.get_json()["reason"] == "espn_unproven_pair"
    assert "ESPN-PAIR-UNBOUND" not in caplog.text   # no control read happened
    assert ("cookie", SWID_B) not in env.espn.calls
    _assert_nothing_created(env)


def test_c7_refusal_espn_ownerless_team(env):
    for t in env.espn.payload["teams"]:
        if t["id"] == 1:
            t["primaryOwner"] = ""
            t["owners"] = []
    r = _espn_claim(env)
    assert r.status_code == 403
    body = r.get_json()
    assert body["error"] == "proof_unavailable"
    assert body["reason"] == "espn_ownerless_team"
    _assert_nothing_created(env)


def test_c7_c8_refusal_espn_wrong_account_names_the_team_this_login_owns(env):
    """Condition 8: B's proven pair claims A's team → the message names B's
    own team in this league (B can see it as a member anyway)."""
    r = _espn_claim(env, team_id=1, s2=S2_B, swid=SWID_B)
    assert r.status_code == 403
    assert r.get_json() == {
        "error": "espn_bad_credentials", "reason": "wrong_account",
        "message": "This ESPN login owns Icy Veins in this league, not the "
                   "team you picked."}
    _assert_nothing_created(env)


def test_c8_espn_wrong_account_generic_when_login_owns_no_team_here(env):
    r = _espn_claim(env, team_id=1, s2=S2_D, swid=SWID_D)
    assert r.status_code == 403
    assert r.get_json() == {"error": "espn_bad_credentials",
                            "reason": "wrong_account",
                            "message": server._ESPN_WRONG_ACCOUNT_MSG}


def test_c8_nothing_is_named_before_the_proof_read(env):
    """A rejected pair (step-2 cookie read fails) gets the plain auth error —
    no team name, no wrong_account."""
    r = _espn_claim(env, team_id=1, s2="not-issued", swid=SWID_B)
    assert r.status_code == 403
    assert r.get_json()["error"] == "espn_auth_required"
    assert "Icy Veins" not in r.get_data(as_text=True)
    r = _mfl_claim(env, username="Rival", password="wrong")
    assert "Other Franchise" not in r.get_data(as_text=True)


def test_c7_refusal_espn_proof_required(env):
    r = _espn_claim(env, s2=None, swid=None)
    assert r.status_code == 403
    body = r.get_json()
    assert body["error"] == "proof_required" and body["message"]
    assert env.espn.calls == []          # refused before any ESPN read
    _assert_nothing_created(env)


# ── MFL proof (D5) ──────────────────────────────────────────────────────────

def test_mfl_login_proves_the_franchise_and_mints_acct_session(env):
    r = _mfl_claim(env)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["user_id"] == f"acct_{body['account_id']}"
    assert body["verified"] is True and body["verified_via"] == "mfl_login"
    assert body["account_only"] is True and body["username"] == ""
    assert body["account_created"] is True
    assert body["display_name"] == "Clobberin Time 2"
    assert body["team_id"] == "0001"
    assert "hunter2" not in r.get_data(as_text=True)
    [ident] = _rows(env, db_module.linked_identities_table)
    assert (ident.provider, ident.provider_subject) == ("mfl", "mattm")
    assert _rows(env, db_module.mfl_credentials_table) == []   # stores nothing
    _assert_no_entry_ids(env)


def test_mfl_bad_login_is_one_body(env):
    r = _mfl_claim(env, password="wrong")
    assert r.status_code == 403
    assert r.get_json() == {"error": "mfl_bad_credentials",
                            "message": "MFL didn't accept that username "
                                       "and password."}
    r2 = _mfl_claim(env, username="nobody", password="x")
    assert r2.get_json() == r.get_json()
    _assert_nothing_created(env)


def test_c7_c8_refusal_mfl_wrong_account_names_the_franchise_this_login_owns(env):
    r = _mfl_claim(env, username="Rival", password="pw-rival",
                   franchise_id="0001")
    assert r.status_code == 403
    assert r.get_json() == {
        "error": "mfl_bad_credentials", "reason": "wrong_account",
        "message": "This MFL login owns Other Franchise in this league, not "
                   "the team you picked."}
    _assert_nothing_created(env)


def test_c8_mfl_wrong_account_generic_when_login_owns_nothing_here(env):
    r = _mfl_claim(env, username="loner", password="pw-loner",
                   franchise_id="0001")
    assert r.status_code == 403
    assert r.get_json() == {"error": "mfl_bad_credentials",
                            "reason": "wrong_account",
                            "message": server._SIGNIN_MFL_WRONG_ACCOUNT_MSG}


def test_c7_refusal_mfl_proof_required(env):
    for kw in ({"username": None, "password": None},
               {"password": None}, {"username": None}):
        r = _mfl_claim(env, **kw)
        assert r.status_code == 403
        assert r.get_json()["error"] == "proof_required"
        assert r.get_json()["message"]
    _assert_nothing_created(env)


# ── Account + session (D3 / D6) ─────────────────────────────────────────────

def test_c9_second_sign_in_same_identity_returns_the_same_account(env):
    first = _espn_claim(env).get_json()
    second = _espn_claim(env).get_json()
    assert first["account_created"] is True
    assert second["account_created"] is False
    assert second["account_id"] == first["account_id"]
    assert second["user_id"] == first["user_id"]
    assert second["session_token"] != first["session_token"]
    assert len(_rows(env, db_module.accounts_table)) == 1
    assert len(_rows(env, db_module.linked_identities_table)) == 1
    m1 = _mfl_claim(env, username="MattM").get_json()
    m2 = _mfl_claim(env, username="  mattm ").get_json()   # trimmed + lowered
    assert m1["account_id"] == m2["account_id"] != first["account_id"]
    assert (m1["account_created"], m2["account_created"]) == (True, False)


def test_returning_sign_in_keeps_the_stored_display_name(env):
    first = _espn_claim(env).get_json()
    with env.engine.begin() as conn:
        conn.execute(update(db_module.users_table)
                     .where(db_module.users_table.c.sleeper_user_id
                            == first["user_id"])
                     .values(display_name="Matt's Board"))
    again = _espn_claim(env).get_json()
    assert again["display_name"] == "Matt's Board"
    assert server._sessions[again["session_token"]]["display_name"] == \
        "Matt's Board"
    # Nothing stored → the claimed team's name is the fallback.
    with env.engine.begin() as conn:
        conn.execute(update(db_module.users_table)
                     .where(db_module.users_table.c.sleeper_user_id
                            == first["user_id"])
                     .values(display_name=None))
    assert _espn_claim(env).get_json()["display_name"] == "Chalk Dusters"


def test_bound_sleeper_account_restores_the_sleeper_user(env):
    first = _espn_claim(env).get_json()
    accounts.bind_sleeper_user(first["account_id"], SLEEPER_UID)
    with env.engine.begin() as conn:
        conn.execute(insert(db_module.users_table).values(
            sleeper_user_id=SLEEPER_UID, username="mattsleeper",
            display_name="Matt S", created_at="2026-10-01"))
    r = _espn_claim(env)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["user_id"] == SLEEPER_UID
    assert body["account_only"] is False
    assert body["account_created"] is False
    assert body["username"] == "mattsleeper"
    assert body["display_name"] == "Matt S"
    assert body["account_id"] == first["account_id"]
    assert body["verified_via"] == "espn"
    sess = server._sessions[body["session_token"]]
    assert sess["verified"] is True and sess["account_id"] == first["account_id"]
    assert accounts.get_user_verified_via(SLEEPER_UID) == "espn"


def test_c7_refusal_espn_platform_identity_in_use(env):
    with env.engine.begin() as conn:
        conn.execute(insert(db_module.espn_credentials_table).values(
            user_id="some_sleeper_user",
            swid=SWID_A.strip("{}").lower(),     # stored bare, lower-case
            espn_s2_encrypted="ciphertext", created_at="x", updated_at="x"))
    r = _espn_claim(env)
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "platform_identity_in_use" and body["message"]
    assert _rows(env, db_module.accounts_table) == []
    assert _rows(env, db_module.linked_identities_table) == []
    assert _rows(env, db_module.sessions_table) == []


def test_c7_refusal_mfl_platform_identity_in_use_case_insensitive(env):
    with env.engine.begin() as conn:
        conn.execute(insert(db_module.mfl_credentials_table).values(
            user_id="some_sleeper_user", mfl_username="  MaTTm ",
            cookie_encrypted="ciphertext", created_at="x", updated_at="x"))
    r = _mfl_claim(env, username="mattM")
    assert r.status_code == 409
    assert r.get_json()["error"] == "platform_identity_in_use"
    assert _rows(env, db_module.accounts_table) == []
    assert _rows(env, db_module.linked_identities_table) == []


def test_existing_identity_row_wins_over_a_credential_conflict(env):
    """D6 runs only when NO identity row exists: once an ESPN account exists,
    its own later import must not lock its owner out."""
    first = _espn_claim(env).get_json()
    with env.engine.begin() as conn:
        conn.execute(insert(db_module.espn_credentials_table).values(
            user_id=first["user_id"], swid=SWID_A,
            espn_s2_encrypted="ciphertext", created_at="x", updated_at="x"))
    again = _espn_claim(env)
    assert again.status_code == 200
    assert again.get_json()["account_id"] == first["account_id"]


def test_c7_c9_uq_linked_identity_race_signs_into_the_winner(env):
    winner = "f" * 32
    real_create = accounts.find_or_create_account

    def _lose_the_race(provider, subject, *a, **kw):
        # The winner commits between our read and our insert ...
        with env.engine.begin() as conn:
            conn.execute(insert(db_module.accounts_table).values(
                account_id=winner, created_at="2026-10-26"))
            conn.execute(insert(db_module.linked_identities_table).values(
                account_id=winner, provider=provider,
                provider_subject=subject, linked_at="2026-10-26"))
        # ... so our insert hits the real uq_linked_identity constraint.
        with env.engine.begin() as conn:
            conn.execute(insert(db_module.accounts_table).values(
                account_id="loser", created_at="2026-10-26"))
            conn.execute(insert(db_module.linked_identities_table).values(
                account_id="loser", provider=provider,
                provider_subject=subject, linked_at="2026-10-26"))
        return real_create(provider, subject, *a, **kw)  # pragma: no cover

    with patch.object(server._accounts, "find_or_create_account",
                      _lose_the_race):
        r = _espn_claim(env)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["account_id"] == winner
    assert body["user_id"] == f"acct_{winner}"
    assert body["account_created"] is False
    assert [a.account_id for a in _rows(env, db_module.accounts_table)] == [winner]


def test_platform_providers_stay_out_of_PROVIDERS(env):
    assert accounts.PROVIDERS == ("apple", "google")
    assert accounts.PLATFORM_PROVIDERS == ("espn", "mfl")
    acct = accounts.find_or_create_account("mfl", "someone")
    assert acct["created"] is True
    with pytest.raises(ValueError):
        accounts.find_or_create_account("fleaflicker", "someone")


# ── Condition 2: one canonical SWID form ────────────────────────────────────

def test_c2_swid_normaliser_folds_braces_case_and_whitespace():
    want = "{A1111111-1111-1111-1111-111111111111}"
    for raw in (want, want.lower(), want.strip("{}"), want.strip("{}").lower(),
                f"  {want.lower()} ", "{a1111111-1111-1111-1111-111111111111",
                "{ A1111111-1111-1111-1111-111111111111 }"):
        assert es.swid_identity(raw) == want, raw
        assert accounts.platform_subject("espn", raw) == want, raw
    assert es.swid_identity("") == "" and es.swid_identity(None) == ""
    assert accounts.platform_subject("mfl", "  MaTT ") == "matt"


def test_c2_formatting_cannot_dodge_identity_exists(env):
    first = _espn_claim(env, swid=SWID_A.lower()).get_json()      # braced, lower
    again = _espn_claim(env, swid=SWID_A.strip("{}")).get_json()  # bare, upper
    assert first["account_created"] is True
    assert again["account_created"] is False
    assert again["account_id"] == first["account_id"]
    [ident] = _rows(env, db_module.linked_identities_table)
    assert ident.provider_subject == SWID_A.upper()


@pytest.mark.parametrize("stored, claimed", [
    ("{a1111111-1111-1111-1111-111111111111}",
     "A1111111-1111-1111-1111-111111111111"),
    (" A1111111-1111-1111-1111-111111111111 ",
     "{a1111111-1111-1111-1111-111111111111}"),
])
def test_c2_formatting_cannot_dodge_the_d6_conflict(env, stored, claimed):
    with env.engine.begin() as conn:
        conn.execute(insert(db_module.espn_credentials_table).values(
            user_id="some_sleeper_user", swid=stored,
            espn_s2_encrypted="ciphertext", created_at="x", updated_at="x"))
    r = _espn_claim(env, swid=claimed)
    assert r.status_code == 409
    assert r.get_json()["error"] == "platform_identity_in_use"


# ── Rate limits (D7) + condition 4 ──────────────────────────────────────────

def test_c7_too_many_attempts_ip_limit_counts_claims_and_actions(env):
    ip = "198.51.100.20"
    for i in range(15):   # failed auth_leagues logins
        r = _post(env, ip=ip, platform="mfl", action="auth_leagues",
                  username=f"user{i}", password="bad")
        assert r.status_code == 403
    for i in range(15):   # failed team-claim proofs
        r = _mfl_claim(env, ip=ip, username=f"claimer{i}", password="bad")
        assert r.status_code == 403
    r = _mfl_claim(env, ip=ip)                       # correct creds, but...
    assert r.status_code == 429
    assert r.get_json()["error"] == "too_many_attempts"
    assert r.get_json()["message"]
    assert 0 < int(r.headers["Retry-After"]) <= server._SIGNIN_IP_WINDOW_S
    # Another client IP is unaffected.
    assert _mfl_claim(env, ip="198.51.100.99").status_code == 200


def test_c4_spoofed_leading_xff_neither_resets_nor_splits_the_ip_count(env):
    real = "198.51.100.40"     # the hop Render's proxy appends (rightmost)
    for i in range(server._SIGNIN_IP_MAX_FAILURES):
        # Half the failures carry no spoof, half a different forged first hop.
        xff = real if i % 2 else f"10.66.{i}.1, {real}"
        r = _mfl_claim(env, ip=xff, username=f"spoofer{i}", password="bad")
        assert r.status_code == 403
    r = _mfl_claim(env, ip=f"192.0.2.250, 10.0.0.1, {real}")   # fresh forgery
    assert r.status_code == 429
    assert _mfl_claim(env, ip=real).status_code == 429
    # The forged values are not buckets of their own either.
    assert _mfl_claim(env, ip="10.66.0.1").status_code == 200


def test_ip_limit_ignores_successes(env):
    ip = "198.51.100.30"
    for _ in range(server._SIGNIN_IP_MAX_FAILURES + 5):
        r = _post(env, ip=ip, platform="mfl", action="auth_leagues",
                  username="MattM", password="hunter2")
        assert r.status_code == 200


def test_c7_too_many_attempts_subject_limit(env):
    for i in range(5):    # five bad passwords for one login, from 5 IPs
        r = _mfl_claim(env, ip=f"192.0.2.{i}", password="bad")
        assert r.status_code == 403
    r = _mfl_claim(env, ip="192.0.2.200")          # right password now
    assert r.status_code == 429
    assert 0 < int(r.headers["Retry-After"]) <= server._SIGNIN_SUBJECT_WINDOW_S
    # The username is the subject regardless of case, and the auth_leagues
    # proxy shares the budget.
    r = _post(env, ip="192.0.2.201", platform="mfl", action="auth_leagues",
              username="MATTM", password="hunter2")
    assert r.status_code == 429
    # Other subjects are unaffected.
    assert _mfl_claim(env, ip="192.0.2.202", username="Rival",
                      password="pw-rival", franchise_id="0002"
                      ).status_code == 200


def test_espn_subject_limit_covers_the_claimed_swid(env):
    env.espn.public = True       # every claim is a failed proof
    for i in range(5):
        assert _espn_claim(env, ip=f"192.0.2.{i}").status_code == 403
    env.espn.public = False
    r = _espn_claim(env, ip="192.0.2.99", swid=SWID_A.lower())  # any format
    assert r.status_code == 429
    assert "Retry-After" in r.headers


# ── Audit log (D9) ──────────────────────────────────────────────────────────

def test_audit_log_one_line_per_claim_and_no_secrets(env, caplog):
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="trade_finder")
    ok = _espn_claim(env).get_json()
    env.espn.bound = False
    _espn_claim(env, s2=S2_B, swid=SWID_A)          # leaguemate attack
    env.espn.bound = True
    _mfl_claim(env)                                  # proven
    _mfl_claim(env, password="wrong-pass-123")       # bad login
    _espn_claim(env, s2=None, swid=None)             # proof_required
    _post(env, platform="espn", espn_league_id=ESPN_LEAGUE)   # preview: no line
    lines = [r.getMessage() for r in caplog.records
             if r.getMessage().startswith("PLATFORM-SIGNIN")]
    assert len(lines) == 5
    assert (f"PLATFORM-SIGNIN provider=espn outcome=proven reason=ok "
            f"account_id={ok['account_id']} created=true") == lines[0]
    assert lines[1] == ("PLATFORM-SIGNIN provider=espn outcome=refused "
                        "reason=espn_unproven_pair")
    assert lines[2].startswith("PLATFORM-SIGNIN provider=mfl outcome=proven")
    assert lines[3] == ("PLATFORM-SIGNIN provider=mfl outcome=refused "
                        "reason=mfl_bad_credentials")
    assert lines[4] == ("PLATFORM-SIGNIN provider=espn outcome=refused "
                        "reason=proof_required")
    text = caplog.text
    for secret in (SWID_A, SWID_B, SWID_A.strip("{}"), SWID_A.upper(),
                   SWID_A.strip("{}").lower(), S2_A, S2_B, "mattm", "MattM",
                   "hunter2", "wrong-pass-123", "MFL_USER_ID"):
        assert secret not in text, secret


def test_audit_log_marks_limited(env, caplog):
    caplog.set_level(logging.INFO, logger="trade_finder")
    for i in range(5):
        _mfl_claim(env, ip=f"192.0.2.{i}", password="bad")
    _mfl_claim(env, ip="192.0.2.50")
    assert ("PLATFORM-SIGNIN provider=mfl outcome=limited "
            "reason=subject_limit") in caplog.text


# ── FakeNet: the REAL service functions over a fake urllib opener ───────────

class _Resp:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "x", HTTPMessage(), io.BytesIO(b""))


class FakeNet:
    """urllib.request.urlopen stand-in for ESPN's league read + fan API and
    MFL's login + myleagues. `fail[kind]` forces an answer for one kind of
    read: an HTTP status (int), "nonjson" (a 200 with an HTML body) or an
    exception instance. ESPN kinds: 'cookie' (the pair's own read), 'anon',
    'control' (an issued espn_s2 sent with a SWID it wasn't issued with)."""

    def __init__(self, payload, issued, mfl_users):
        self.payload = payload
        self.issued = issued
        self.mfl_users = mfl_users
        self.public = False
        self.bound = True
        self.fail: dict = {}
        self.requests = []

    def _forced(self, kind, url):
        f = self.fail.get(kind)
        if f is None:
            return None
        if f == "nonjson":
            return _Resp(b"<html>edge page</html>")
        if isinstance(f, int):
            raise _http_error(url, f)
        raise f

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.requests.append((req.get_method(), url))
        host = urllib.parse.urlsplit(url).hostname
        if host == "lm-api-reads.fantasy.espn.com":
            jar = dict(p.split("=", 1) for p in
                       (req.get_header("Cookie") or "").split("; ") if "=" in p)
            s2, swid = jar.get("espn_s2"), jar.get("SWID")
            if not s2:
                kind = "anon"
            elif s2 in self.issued and es.swid_identity(swid) != \
                    es.swid_identity(self.issued[s2]):
                kind = "control"
            else:
                kind = "cookie"
            forced = self._forced(kind, url)
            if forced is not None:
                return forced
            body = json.dumps(self.payload).encode()
            if self.public:
                return _Resp(body)
            owner = self.issued.get(s2)
            if kind == "anon" or owner is None or (
                    self.bound and es.swid_identity(swid)
                    != es.swid_identity(owner)):
                raise _http_error(url, 401)
            return _Resp(body)
        if host == "fan.api.espn.com":
            raise _http_error(url, 401)
        if host == mfl.MFL_API_HOST and url.endswith("/login"):
            forced = self._forced("mfl_login", url)
            if forced is not None:
                return forced
            form = urllib.parse.parse_qs(req.data.decode())
            user = form["USERNAME"][0].strip().lower()
            rec = self.mfl_users.get(user)
            if rec is None or rec[0] != form["PASSWORD"][0]:
                return _Resp(b"<error>Invalid login</error>")
            n = list(self.mfl_users).index(user)
            return _Resp(f'<status MFL_USER_ID="mflcookie-{n}">OK'
                         f'</status>'.encode())
        if host == mfl.MFL_API_HOST and "TYPE=myleagues" in url:
            cookie = req.get_header("Cookie")
            user = next(u for n, u in enumerate(self.mfl_users)
                        if cookie == f"MFL_USER_ID=mflcookie-{n}")
            return _Resp(json.dumps(
                {"leagues": {"league": self.mfl_users[user][1]}}).encode())
        raise AssertionError(f"unexpected egress to {host}")


def _real_services(net):
    return (patch.object(urllib.request, "urlopen", net),
            patch.object(es, "fetch_league", REAL_FETCH_LEAGUE),
            patch.object(mfl, "login", REAL_MFL_LOGIN),
            patch.object(mfl, "fetch_my_leagues", REAL_MFL_MY_LEAGUES))


# ── Condition 3: steps 3 and 4 fail closed ──────────────────────────────────

@pytest.mark.parametrize("step", ["anon", "control"])
@pytest.mark.parametrize("failure", [
    500, 503, 429, 404, 418, "nonjson", TimeoutError("timed out"),
    urllib.error.URLError("connection reset"), ConnectionResetError("reset"),
], ids=["5xx-500", "5xx-503", "espn-rate-limit-429", "404", "unexpected-418",
        "parse-error", "timeout", "urlerror", "connection-reset"])
def test_c3_any_non_auth_answer_on_steps_3_and_4_refuses(env, step, failure):
    net = FakeNet(env.espn_payload, {S2_A: SWID_A, S2_B: SWID_B}, {})
    net.fail[step] = failure
    p1, p2, p3, p4 = _real_services(net)
    with p1, p2, p3, p4:
        r = _espn_claim(env)
    assert r.status_code == 403, r.get_data(as_text=True)
    assert r.get_json() == {"error": "proof_unavailable",
                            "reason": "espn_unavailable",
                            "message": server._SIGNIN_ESPN_UNAVAILABLE_MSG}
    assert SWID_B.strip("{}") not in r.get_data(as_text=True)   # control SWID
    _assert_nothing_created(env)
    # Sanity: the same claim passes once the failure clears.
    net.fail.clear()
    with p1, p2, p3, p4:
        assert _espn_claim(env).status_code == 200


# ── Condition 1: no secret reaches a log, an event or a body ────────────────

M_S2 = "S2MARKERone%2Bq"
M_S2_TWO = "S2MARKERtwo%2Bq"
M_S2_UNISSUED = "S2MARKERzz%2Bq"
M_SWID = "{5111DMARK-1111-4111-8111-111111111111}"      # team 1
M_SWID_TWO = "{5222DMARK-2222-4222-8222-222222222222}"  # team 2 (control SWID)
M_SWID_THREE = "{5333DMARK-3333-4333-8333-333333333333}"  # team 3
M_USER = "USERMARKER-Matt"
M_USER_TWO = "USERMARKER-Rival"
M_USER_TAKEN = "USERMARKER-Taken"
M_PW = "PWMARKER-hunter2"
M_PW_BAD = "PWMARKER-wrong"
NEVER_ANYWHERE = ("S2MARKER", "PWMARKER", "MFL_USER_ID", "mflcookie")
SWID_TAGS = ("5111DMARK", "5222DMARK", "5333DMARK")


def _marker_payload(payload):
    p = copy.deepcopy(payload)
    owners = {1: M_SWID, 2: M_SWID_TWO, 3: M_SWID_THREE}
    for t in p["teams"]:
        t["primaryOwner"] = owners[t["id"]]
        t["owners"] = [owners[t["id"]]]
    p["members"] = [{"id": s, "displayName": f"Member {i}"}
                    for i, s in owners.items()]
    return p


def test_c1_markers_never_leak_through_any_outcome(env, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="trade_finder")
    net = FakeNet(_marker_payload(env.espn_payload),
                  {M_S2: M_SWID, M_S2_TWO: M_SWID_TWO},
                  {M_USER.lower(): (M_PW, MFL_USERS["mattm"][1]),
                   M_USER_TWO.lower(): ("PWMARKER-rival", MFL_USERS["rival"][1]),
                   M_USER_TAKEN.lower(): ("PWMARKER-taken", MFL_USERS["mattm"][1])})
    seen: list[str] = []

    def call(path="/api/entry/platform", token=None, **body):
        headers = {"X-Forwarded-For": "203.0.113.9"}
        if token:
            headers["X-Session-Token"] = token
        r = env.client.post(path, json=body, headers=headers)
        seen.append(r.get_data(as_text=True))
        seen.append(json.dumps(dict(r.headers)))
        return r

    def espn(team_id=1, **kw):
        return call(platform="espn", espn_league_id=ESPN_LEAGUE,
                    team_id=team_id, **kw)

    def mfl_claim(username, password, franchise_id="0001"):
        return call(platform="mfl", mfl_league_id=MFL_LEAGUE, year=2026,
                    franchise_id=franchise_id, username=username,
                    password=password)

    p1, p2, p3, p4 = _real_services(net)
    with p1, p2, p3, p4, \
         patch.object(api_obs, "is_enabled", lambda k: k == "obs.api_events"), \
         patch.object(db_module, "ingest_engine", env.engine):
        # A forced DB error inside the sign-in: its message carries the SQL
        # parameters, i.e. the SWID.
        def _db_down(provider, subject, *a, **kw):
            raise OperationalError("INSERT INTO linked_identities",
                                   {"provider_subject": subject},
                                   Exception("disk I/O error"))
        with patch.object(server._accounts, "find_or_create_account", _db_down):
            assert espn(espn_s2=M_S2, swid=M_SWID).status_code == 500
        assert espn(espn_s2=M_S2, swid=M_SWID).status_code == 200   # proven
        assert espn(team_id=2, espn_s2=M_S2, swid=M_SWID).status_code == 403
        assert espn(espn_s2=M_S2).status_code == 400            # incomplete
        assert espn().status_code == 403                         # proof_required
        assert espn(espn_s2=M_S2_UNISSUED,                       # step 2 refused
                    swid=M_SWID_THREE).status_code == 403
        net.public = True
        assert espn(espn_s2=M_S2, swid=M_SWID).get_json()["reason"] == \
            "espn_public_league"
        net.public, net.bound = False, False
        assert espn(espn_s2=M_S2_TWO, swid=M_SWID).get_json()["reason"] == \
            "espn_unproven_pair"
        net.bound = True
        net.fail["anon"] = 503
        assert espn(espn_s2=M_S2, swid=M_SWID).get_json()["reason"] == \
            "espn_unavailable"
        # Forced exceptions whose MESSAGES carry the secrets.
        net.fail = {"control": RuntimeError("boom " + M_S2 + " " + M_SWID_TWO)}
        assert espn(espn_s2=M_S2, swid=M_SWID).get_json()["reason"] == \
            "espn_unavailable"
        net.fail = {"cookie": RuntimeError("boom " + M_S2 + " " + M_SWID)}
        assert espn(espn_s2=M_S2, swid=M_SWID).status_code == 500
        net.fail = {}
        with env.engine.begin() as conn:                         # D6 conflict
            conn.execute(insert(db_module.espn_credentials_table).values(
                user_id="other_user", swid=M_SWID_TWO,
                espn_s2_encrypted="ciphertext", created_at="x", updated_at="x"))
        assert espn(team_id=2, espn_s2=M_S2_TWO,
                    swid=M_SWID_TWO).status_code == 409
        for _ in range(5):                                       # → 429
            espn(team_id=3, espn_s2=M_S2_UNISSUED, swid=M_SWID_THREE)
        assert espn(team_id=3, espn_s2=M_S2_UNISSUED,
                    swid=M_SWID_THREE).status_code == 429
        call(platform="espn", action="my_leagues",               # action
             espn_s2=M_S2, swid=M_SWID)

        assert mfl_claim(M_USER, M_PW).status_code == 200        # proven
        assert mfl_claim(M_USER, M_PW_BAD).status_code == 403    # bad login
        assert mfl_claim(M_USER_TWO, "PWMARKER-rival").status_code == 403
        assert call(platform="mfl", mfl_league_id=MFL_LEAGUE, year=2026,
                    franchise_id="0001", username=M_USER).status_code == 403
        with env.engine.begin() as conn:                         # D6 conflict
            conn.execute(insert(db_module.mfl_credentials_table).values(
                user_id="other_user", mfl_username=M_USER_TAKEN.upper(),
                cookie_encrypted="ciphertext", created_at="x", updated_at="x"))
        assert mfl_claim(M_USER_TAKEN, "PWMARKER-taken").status_code == 409
        net.fail = {"mfl_login": RuntimeError("boom " + M_PW + " " + M_USER)}
        assert mfl_claim(M_USER, M_PW).status_code == 500
        net.fail = {}
        for _ in range(5):
            mfl_claim(M_USER_TWO, M_PW_BAD)
        assert mfl_claim(M_USER_TWO, "PWMARKER-rival").status_code == 429
        call(platform="mfl", action="auth_leagues", username=M_USER,
             password=M_PW_BAD)

        # The #279 AUTH-DENY handler, fed the same secrets.
        squat = "tok-squat-" + secrets.token_hex(4)
        with server._sessions_lock:
            server._sessions[squat] = {"user_id": "squatter",
                                       "active_format": "1qb_ppr",
                                       "last_active": time.time()}
        assert call("/api/espn/link", token=squat, espn_league_id=ESPN_LEAGUE,
                    team_id=1, espn_s2=M_S2, swid=M_SWID).status_code == 403

    out = capsys.readouterr()
    surfaces = {"logs": caplog.text, "responses": "\n".join(seen),
                "stdout/stderr": out.out + out.err}
    with env.engine.connect() as conn:
        events = conn.execute(select(db_module.user_events_table)).fetchall()
    assert events, "obs.api_events captured nothing — the test isn't wired"
    surfaces["obs.api_events"] = "\n".join(str(tuple(e)) for e in events)
    for where, text in surfaces.items():
        low = text.lower()
        for m in NEVER_ANYWHERE + SWID_TAGS + ("usermarker",):
            assert m.lower() not in low, (where, m)
    # The database: s2 / password / cookie nowhere; a SWID or MFL username
    # only in its intended stored places.
    allowed = {"linked_identities": ("provider_subject",),
               "espn_credentials": ("swid",),
               "mfl_credentials": ("mfl_username",)}
    with env.engine.connect() as conn:
        for table in metadata.sorted_tables:
            for row in conn.execute(select(table)).mappings():
                for col, value in row.items():
                    low = str(value).lower()
                    for m in NEVER_ANYWHERE:
                        assert m.lower() not in low, (table.name, col)
                    if col in allowed.get(table.name, ()):
                        continue
                    for m in SWID_TAGS + ("usermarker",):
                        assert m.lower() not in low, (table.name, col, m)


# ── Condition 5: the R1 operator script ─────────────────────────────────────

def _load_r1_script():
    path = os.path.join(REPO_ROOT, "scripts", "espn_pair_check.py")
    spec = importlib.util.spec_from_file_location("espn_pair_check", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


def test_c5_r1_script_is_stdlib_only_and_matches_espn_service():
    mod, path = _load_r1_script()
    tree = ast.parse(open(path).read())
    imported = {a.name.split(".")[0] for n in ast.walk(tree)
                if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree)
                 if isinstance(n, ast.ImportFrom)}
    assert imported <= {"json", "os", "sys", "urllib", "uuid"}, imported
    assert mod.league_url(ESPN_LEAGUE, 2026) == es.league_url(ESPN_LEAGUE, 2026)
    assert mod.HEADERS == es.BROWSER_HEADERS
    for s2 in ("abc+/=", "abc%2B%2F%3D", ""):
        assert mod.canonical_espn_s2(s2) == es.canonical_espn_s2(s2)
    for sw in (SWID_A, SWID_A.strip("{}"), " " + SWID_A, ""):
        assert mod.canonical_swid(sw) == es.canonical_swid(sw)


@pytest.mark.parametrize("statuses, expected", [
    ((200, 401, 401, 401), "PAIR_BOUND"),
    ((200, 403, 403, 403), "PAIR_BOUND"),
    ((200, 401, 200, 401), "PAIR_NOT_BOUND"),
    ((200, 401, 401, 200), "PAIR_NOT_BOUND"),
    ((200, 200, 200, 200), "INCONCLUSIVE"),          # public league
    ((401, 401, 401, 401), "INCONCLUSIVE"),          # bad cookies
    ((200, 401, "skipped (no other member)", 401), "INCONCLUSIVE"),
    ((200, 401, 503, 401), "INCONCLUSIVE"),
    ((200, 401, "error:TimeoutError", 200), "PAIR_NOT_BOUND"),
])
def test_c5_r1_script_verdicts(statuses, expected):
    mod, _ = _load_r1_script()
    assert mod.verdict(*statuses) == expected


@pytest.mark.parametrize("bound, expected", [(True, "PAIR_BOUND"),
                                             (False, "PAIR_NOT_BOUND")])
def test_c5_r1_script_env_only_get_only_espn_only_prints_statuses(
        env, capsys, bound, expected):
    mod, _ = _load_r1_script()
    net = FakeNet(_marker_payload(env.espn_payload), {M_S2: M_SWID}, {})
    net.bound = bound
    check_env = {"ESPN_CHECK_S2": M_S2, "ESPN_CHECK_SWID": M_SWID,
                 "ESPN_CHECK_LEAGUE": ESPN_LEAGUE, "ESPN_CHECK_SEASON": "2026"}
    with patch.object(urllib.request, "urlopen", net), \
         patch("builtins.open", side_effect=AssertionError("file access")):
        assert mod.main(check_env) == 0
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert len(lines) == 5 and lines[-1] == f"verdict: {expected}"
    for line in lines[:4]:
        assert line.rsplit(":", 1)[1].strip().isdigit(), line
    for m in ("S2MARKER",) + SWID_TAGS:
        assert m.lower() not in out.lower()
    assert len(net.requests) == 4
    assert all(method == "GET" and urllib.parse.urlsplit(url).hostname
               == "lm-api-reads.fantasy.espn.com"
               for method, url in net.requests)


# ── Condition 6: disconnect keeps the sign-in identity ──────────────────────

def test_c6_espn_disconnect_keeps_the_identity_then_same_account(env):
    first = _espn_claim(env).get_json()
    tok = first["session_token"]
    link = {"espn_league_id": ESPN_LEAGUE, "team_id": 1, "espn_s2": S2_A,
            "swid": SWID_A}
    assert env.client.post("/api/espn/link", json=link,
                           headers={"X-Session-Token": tok}).status_code == 200
    assert len(_rows(env, db_module.espn_credentials_table)) == 1
    r = env.client.delete("/api/espn/link", headers={"X-Session-Token": tok})
    assert r.status_code == 200 and r.get_json() == {"connected": False}
    assert _rows(env, db_module.espn_credentials_table) == []
    assert len(_rows(env, db_module.linked_identities_table)) == 1
    again = _espn_claim(env).get_json()
    assert again["account_created"] is False
    assert again["account_id"] == first["account_id"]


def test_c6_mfl_disconnect_keeps_the_identity_then_same_account(env):
    first = _mfl_claim(env).get_json()
    tok = first["session_token"]
    r = env.client.post("/api/mfl/auth-link",
                        json={"username": "MattM", "password": "hunter2",
                              "year": 2026},
                        headers={"X-Session-Token": tok})
    assert r.status_code == 200 and r.get_json()["storage"] == "encrypted"
    r = env.client.delete("/api/mfl/auth-link", headers={"X-Session-Token": tok})
    assert r.status_code == 200 and r.get_json() == {"connected": False}
    assert _rows(env, db_module.mfl_credentials_table) == []
    assert len(_rows(env, db_module.linked_identities_table)) == 1
    again = _mfl_claim(env).get_json()
    assert again["account_created"] is False
    assert again["account_id"] == first["account_id"]


# ── Condition 7: the #279 gate is pinned unchanged ──────────────────────────

# sha256 of each function's source on origin/main @ 732a6b7f (AST segment).
_GATE_PINS = {
    "_verified_write_denial":
        "185ab4158ce4dd87625023153ff5463f44801cd606e2ecd0a0e90e9dccf05dde",
    "_gate_unverified_write":
        "7b2dacb8e02195301d4aa5a8be4a528bec435d5613a7c243a64f36ed0f34dbf4",
    "_verified_read_denial":
        "efe1f59089bb4bd160c00a114a6b192848cd8e3c4a93141f25bcf60b017f55a3",
    "_gate_unverified_read":
        "f3a54e0f483b85284d1e6ff40617b56c59ecfd6d57cdc9430f6ef1314c951d53",
}


def test_c7_the_279_gate_is_byte_identical_and_still_on_the_link_routes(env):
    src = open(inspect.getsourcefile(server)).read()
    found = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name in _GATE_PINS:
            found[node.name] = hashlib.sha256(
                ast.get_source_segment(src, node).encode()).hexdigest()
    assert found == _GATE_PINS
    assert server._MUTATING_METHODS == ("POST", "PUT", "PATCH", "DELETE")
    gate_code = server._gate_unverified_write(lambda: None).__code__
    for endpoint in ("espn_link", "espn_import", "mfl_link", "mfl_auth_link"):
        view = server.app.view_functions[endpoint]
        assert view.__code__ is gate_code, endpoint
        assert getattr(view, "__wrapped__", None) is not None, endpoint


def test_c7_unverified_session_still_403s_on_espn_link_but_minted_passes(env):
    unverified = "tok-unverified-" + secrets.token_hex(4)
    with server._sessions_lock:
        server._sessions[unverified] = {"user_id": "squatter",
                                        "active_format": "1qb_ppr",
                                        "last_active": time.time()}
    link_body = {"espn_league_id": ESPN_LEAGUE, "team_id": 1,
                 "espn_s2": S2_A, "swid": SWID_A}
    denied = env.client.post("/api/espn/link", json=link_body,
                             headers={"X-Session-Token": unverified})
    assert denied.status_code == 403
    assert denied.get_json()["error"] == "verification_required"

    token = _espn_claim(env).get_json()["session_token"]
    ok = env.client.post("/api/espn/link", json=link_body,
                         headers={"X-Session-Token": token})
    assert ok.status_code == 200, ok.get_data(as_text=True)
    assert ok.get_json()["ok"] is True


# ── Conditions 7 + 11: mint → import → delete; deletion frees the identity ──

def test_c7_c11_mint_import_delete_then_a_fresh_sign_in_is_a_new_account(env):
    minted = _espn_claim(env).get_json()
    token, uid = minted["session_token"], minted["user_id"]
    r = env.client.post("/api/espn/link",
                        json={"espn_league_id": ESPN_LEAGUE, "team_id": 1,
                              "espn_s2": S2_A, "swid": SWID_A},
                        headers={"X-Session-Token": token})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert len(_rows(env, db_module.espn_credentials_table)) == 1
    assert len(_rows(env, db_module.sessions_table)) == 1

    r = env.client.delete("/api/account", headers={"X-Session-Token": token})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["ok"] is True
    assert _rows(env, db_module.accounts_table) == []
    assert _rows(env, db_module.linked_identities_table) == []
    assert _rows(env, db_module.sessions_table) == []
    assert _rows(env, db_module.espn_credentials_table) == []
    with env.engine.connect() as conn:
        assert conn.execute(select(db_module.users_table).where(
            db_module.users_table.c.sleeper_user_id == uid)).fetchall() == []
    assert token not in server._sessions
    # Condition 11: the identity is released — a fresh proof creates a NEW
    # account (never resurrects the deleted one).
    again = _espn_claim(env).get_json()
    assert again["account_created"] is True
    assert again["account_id"] != minted["account_id"]


def test_c11_mfl_deletion_releases_the_identity(env):
    minted = _mfl_claim(env).get_json()
    r = env.client.delete("/api/account",
                          headers={"X-Session-Token": minted["session_token"]})
    assert r.status_code == 200
    again = _mfl_claim(env).get_json()
    assert again["account_created"] is True
    assert again["account_id"] != minted["account_id"]


# ── Condition 10: export carries the identity, never the secrets ────────────

def test_c10_espn_export_has_the_identity_not_the_cookie(env):
    minted = _espn_claim(env).get_json()
    tok = minted["session_token"]
    assert env.client.post("/api/espn/link",
                           json={"espn_league_id": ESPN_LEAGUE, "team_id": 1,
                                 "espn_s2": S2_A, "swid": SWID_A},
                           headers={"X-Session-Token": tok}).status_code == 200
    [cred] = _rows(env, db_module.espn_credentials_table)
    r = env.client.get("/api/account/export", headers={"X-Session-Token": tok})
    assert r.status_code == 200, r.get_data(as_text=True)
    tables = r.get_json()["tables"]
    assert [(i["provider"], i["provider_subject"])
            for i in tables["linked_identities"]] == [("espn", SWID_A.upper())]
    assert all("espn_s2_encrypted" not in row
               for row in tables["espn_credentials"])
    text = r.get_data(as_text=True)
    assert S2_A not in text and cred.espn_s2_encrypted not in text


def test_c10_mfl_export_has_the_identity_not_the_cookie_or_password(env):
    minted = _mfl_claim(env).get_json()
    tok = minted["session_token"]
    assert env.client.post("/api/mfl/auth-link",
                           json={"username": "MattM", "password": "hunter2",
                                 "year": 2026},
                           headers={"X-Session-Token": tok}).status_code == 200
    [cred] = _rows(env, db_module.mfl_credentials_table)
    r = env.client.get("/api/account/export", headers={"X-Session-Token": tok})
    assert r.status_code == 200, r.get_data(as_text=True)
    tables = r.get_json()["tables"]
    assert [(i["provider"], i["provider_subject"])
            for i in tables["linked_identities"]] == [("mfl", "mattm")]
    assert all("cookie_encrypted" not in row
               for row in tables["mfl_credentials"])
    text = r.get_data(as_text=True)
    assert "hunter2" not in text and "MFL_USER_ID" not in text
    assert cred.cookie_encrypted not in text


# ── The entry:* invariant + MFL handoff ─────────────────────────────────────

def test_mfl_mint_then_auth_link_passes_the_unchanged_gate(env):
    """D1: /api/mfl/auth-link gets no exemption — the post-import cookie
    store just works because the minted session is verified."""
    token = _mfl_claim(env).get_json()["session_token"]
    r = env.client.post("/api/mfl/auth-link",
                        json={"username": "MattM", "password": "hunter2",
                              "year": 2026},
                        headers={"X-Session-Token": token})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["verified"] is True
