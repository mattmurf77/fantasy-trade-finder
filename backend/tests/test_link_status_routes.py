"""Send-auth lazy flow (2026-08-11): link-STATUS reads + the ESPN
credential-only store.

  GET  /api/espn/link      — {connected, expires_at, expired, verified_at},
                             mirroring GET /api/sleeper/link. Never returns
                             cookies. `connected` additionally requires a
                             verified_at stamp (credential-honesty fix,
                             2026-08-12) — an unproven pair reads as false.
  POST /api/espn/link      — credential-only branch: {espn_s2, swid} with NO
                             espn_league_id VERIFIES the pair with one live
                             read whose RESULT IS ASSERTED, then persists it
                             (encrypted, verified_at stamped) and returns
                             {connected: true, verified: true, verified_via}.
                             Rejected — or proved nothing — → 403
                             espn_bad_credentials, NOT stored; ESPN
                             unreachable → 502 espn_unavailable, NOT stored.
  GET  /api/mfl/auth-link  — {connected, mfl_username, year}; also true for
                             the key-less session-only cookie fallback.

The verification-oracle section at the bottom covers WHICH read counts as
proof (verification-oracle fix, 2026-08-12): an authenticated read of a
linked private league when the user has one, the weaker fan-profile probe
otherwise, and an empty/unrecognised probe result never passing.

Exercised through Flask's test client against an isolated in-memory SQLite
DB with an injected session. ZERO network, twice over: every probe is
patched per-test, AND the `_no_live_espn` autouse fixture turns any
unpatched ESPN call into an immediate AssertionError instead of a real HTTP
request. The GET status paths still make no ESPN call at all (they must
stay cheap: the send button reads them on every send).
"""
import copy
import json
import os
import urllib.error
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.espn_service as es
import backend.server as server
from backend.database import metadata

USER = "313560442465169408"

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
LEAGUE_FIXTURE = os.path.join(FIXTURES, "espn_league_snapshot_2026-07-11.json")
LINKED_LEAGUE = "987654321"          # id inside the league fixture payload


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


def _league_payload():
    with open(LEAGUE_FIXTURE) as f:
        return json.load(f)


def _link_league(auth: str, league_id: str = LINKED_LEAGUE, season: int = 2026):
    """Give USER a linked ESPN league row + membership binding.

    `auth='cookie'` is a league ESPN only serves to an authenticated member
    (the STRONG verification oracle); `auth='public'` is one anyone can read
    (proves nothing about a cookie pair, so the route must not use it)."""
    db_module.upsert_espn_league(
        league_id=league_id, user_id=USER, name="Fixture League",
        espn_season=season, espn_auth=auth, espn_my_team_id=1,
        total_rosters=2)
    db_module.replace_espn_league_members(league_id, [
        {"user_id": USER, "username": "me", "display_name": "Me",
         "player_ids": []},
    ])


@contextmanager
def _fan_probe(football=(), fantasy_entries=None, recognized=True,
               error=None, calls=None):
    """Patch the fan-profile probe — under BOTH the name today's code calls
    (`fetch_fan_leagues`) and the name the fixed route calls
    (`probe_fan_profile`, patched with create=True so this same test runs
    against the pre-fix tree). Either way: zero network."""
    entries = len(football) if fantasy_entries is None else fantasy_entries

    def _legacy(espn_s2, swid, timeout=15, _opener=None):
        if calls is not None:
            calls.append(("fan", espn_s2, swid))
        if error:
            raise error
        return [dict(f) for f in football]

    def _probe(espn_s2, swid, timeout=15, _opener=None):
        if calls is not None:
            calls.append(("fan", espn_s2, swid))
        if error:
            raise error
        return {"football_leagues": [dict(f) for f in football],
                "fantasy_entries": entries,
                "recognized": recognized}

    with patch.object(es, "fetch_fan_leagues", _legacy), \
         patch.object(es, "probe_fan_profile", _probe, create=True):
        yield


@contextmanager
def _league_read(payload=None, error=None, calls=None):
    """Patch espn_service.fetch_league (the STRONG oracle) — never network."""
    def _fetch(league_id, season, espn_s2=None, swid=None, timeout=15,
               _opener=None):
        if calls is not None:
            calls.append(("league", str(league_id), espn_s2, swid))
        if error:
            raise error
        return copy.deepcopy(payload if payload is not None
                             else _league_payload())

    with patch.object(es, "fetch_league", _fetch):
        yield


def _must_not_call(kind):
    def _boom(*a, **kw):
        raise AssertionError(f"{kind} must not be consulted here")
    return _boom


FFL = ({"league_id": "111", "league_name": "Dynasty", "season": 2026,
        "team_name": "Team"},)

# #321 — team 1's owner in the league fixture; `_link_league` binds team 1,
# so a pair carrying this SWID passes the membership assertion.
OWNER1_SWID = "{A1111111-1111-1111-1111-111111111111}"


@pytest.fixture(autouse=True)
def _no_live_espn():
    """Hard network floor for this module. Every ESPN probe in the store path
    is patched per-test; this makes an UNPATCHED one an immediate, obvious
    test failure instead of a real request to ESPN (which is how a route
    change that switches probes could otherwise start calling the network
    from the suite)."""
    def _boom(*a, **kw):
        raise AssertionError("live ESPN call attempted from a test")

    with patch.object(es, "_fetch_fan_payload", _boom), \
         patch.object(es.urllib.request, "urlopen", _boom):
        yield


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "link-status-sess-tok"
    sess = {"verified": True, "user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    flags = {"espn.link", "mfl.auth_link"}
    # Default probe: an authenticated fan whose profile came back with this
    # account's fantasy data — the only thing that counts as proof on the
    # weak oracle (verification-oracle fix, 2026-08-12; an EMPTY result is
    # NOT an honest success, which is exactly the bug that shipped). Tests
    # that care re-patch per-test. Never the network.
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in flags), \
         patch.object(es, "probe_fan_profile",
                      lambda espn_s2, swid, timeout=15, _opener=None:
                      {"football_leagues": [dict(FFL[0])],
                       "fantasy_entries": 1, "recognized": True}), \
         patch.object(es, "fetch_fan_leagues",
                      lambda espn_s2, swid, timeout=15, _opener=None:
                      [dict(FFL[0])]):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, engine, sess
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


# ---------------------------------------------------------------------------
# GET /api/espn/link — status
# ---------------------------------------------------------------------------

def test_espn_link_status_404_when_flag_off(client):
    c, token, _, _ = client
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.get("/api/espn/link", headers=_h(token))
    assert r.status_code == 404
    assert r.get_json()["error"] == "feature_disabled"


def test_espn_link_status_requires_session():
    c = server.app.test_client()
    with patch.object(server, "is_enabled", lambda k: k == "espn.link"):
        r = c.get("/api/espn/link")
    assert r.status_code == 401


def test_espn_link_status_not_connected(client):
    c, token, _, _ = client
    r = c.get("/api/espn/link", headers=_h(token))
    assert r.status_code == 200
    assert r.get_json() == {"connected": False}


def test_espn_link_status_connected_after_store(client):
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_espn_credential(USER, "{ABCD-1234}", encrypt_token("s2val"),
                                     verified_at="2026-08-12T00:00:00+00:00")
    r = c.get("/api/espn/link", headers=_h(token))
    assert r.status_code == 200
    body = r.get_json()
    assert body["connected"] is True
    assert body["expired"] is False
    assert body["expires_at"] is None
    assert body["verified_at"] == "2026-08-12T00:00:00+00:00"
    # never the cookies themselves
    assert "swid" not in body and "espn_s2" not in body


def test_espn_link_status_swidless_row_is_not_connected(client):
    """A row missing its SWID can't authenticate anything — the propose
    route treats it as espn_not_connected, so the status must agree."""
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_espn_credential(USER, None, encrypt_token("s2val"),
                                     verified_at="2026-08-12T00:00:00+00:00")
    r = c.get("/api/espn/link", headers=_h(token))
    assert r.get_json() == {"connected": False}


def test_espn_link_status_unverified_row_is_not_connected(client):
    """Credential-honesty fix (2026-08-12): a stored pair with no
    verified_at was never proven against ESPN (legacy pre-verification
    rows), so `connected` must NOT claim it works — the client re-runs the
    sign-in flow, which verifies before storing."""
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_espn_credential(USER, "{ABCD-1234}", encrypt_token("s2val"))
    r = c.get("/api/espn/link", headers=_h(token))
    assert r.get_json() == {"connected": False}


def test_espn_link_status_reports_expired_hint(client):
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_espn_credential(USER, "{ABCD-1234}", encrypt_token("s2val"),
                                     expires_hint_at="2020-01-01T00:00:00+00:00",
                                     verified_at="2026-08-12T00:00:00+00:00")
    body = c.get("/api/espn/link", headers=_h(token)).get_json()
    assert body["connected"] is True
    assert body["expired"] is True


# ---------------------------------------------------------------------------
# POST /api/espn/link — credential-only store
# ---------------------------------------------------------------------------

def test_credential_only_store_verifies_then_persists_encrypted_pair(client):
    """Valid cookies: the pair is probed against ESPN (patched fan-profile
    read), stored encrypted with verified_at stamped, and the status read
    agrees. The probe must receive the exact pair the client sent."""
    c, token, engine, _ = client
    s2 = "AEB%2FvS0me%2Bencoded%3Dvalue"
    swid = "{ABCD-1234}"
    probed = []
    with _fan_probe(football=FFL, calls=probed):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": s2, "swid": swid}))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json() == {"connected": True, "stored": "credential",
                            "verified": True, "verified_via": "fan_profile"}
    assert probed == [("fan", s2, swid)]           # exactly one live probe

    with engine.connect() as conn:
        row = conn.execute(select(db_module.espn_credentials_table)).fetchone()._mapping
        # credential only — NO league row is created or touched
        assert conn.execute(select(db_module.leagues_table)).fetchall() == []
    assert row["user_id"] == USER
    assert row["swid"] == swid
    assert row["espn_s2_encrypted"] != s2          # never plaintext
    assert row["verified_at"]                      # proof recorded
    from backend.sleeper_write import decrypt_token
    assert decrypt_token(row["espn_s2_encrypted"]) == s2

    # and the status read now agrees
    assert c.get("/api/espn/link", headers=_h(token)).get_json()["connected"] is True


def test_credential_only_store_rejected_pair_is_not_stored(client):
    """Invalid cookies (ESPN 401/403/404 → EspnAuthError): 403
    espn_bad_credentials, NOTHING stored, and the status read still says
    not connected — the user is told sign-in didn't take at sign-in time,
    not at their next trade send."""
    c, token, engine, _ = client

    with _fan_probe(error=es.EspnAuthError()):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": "stale-s2", "swid": "{BAD-1}"}))
    assert r.status_code == 403
    assert r.get_json()["error"] == "espn_bad_credentials"
    with engine.connect() as conn:
        assert conn.execute(select(db_module.espn_credentials_table)).fetchall() == []
    assert c.get("/api/espn/link", headers=_h(token)).get_json() == {"connected": False}


def test_credential_only_store_espn_outage_is_retryable_not_stored(client):
    """ESPN unreachable / 5xx / non-JSON is NOT a credential verdict: a
    distinct retryable 502 espn_unavailable — never espn_bad_credentials —
    and the unproven pair still does not reach the DB."""
    c, token, engine, _ = client

    for failure in (es.EspnError("ESPN fan API HTTP 503", kind="http"),
                    urllib.error.URLError("dns failure")):   # OSError subclass
        with _fan_probe(error=failure):
            r = c.post("/api/espn/link", headers=_h(token),
                       data=json.dumps({"espn_s2": "good-s2", "swid": "{OK-1}"}))
        assert r.status_code == 502, r.get_data(as_text=True)
        assert r.get_json()["error"] == "espn_unavailable"
        with engine.connect() as conn:
            assert conn.execute(
                select(db_module.espn_credentials_table)).fetchall() == []
    assert c.get("/api/espn/link", headers=_h(token)).get_json() == {"connected": False}


def test_credential_only_store_needs_both_cookies(client):
    c, token, _, _ = client
    r = c.post("/api/espn/link", headers=_h(token),
               data=json.dumps({"espn_s2": "only-half"}))
    assert r.status_code == 400
    assert r.get_json()["error"] == "espn_cookies_incomplete"


def test_post_without_cookies_still_requires_league_id(client):
    """The pre-existing contract survives the new branch: a cookie-less POST
    with no/invalid league id keeps 400ing espn_bad_league_id."""
    c, token, _, _ = client
    r = c.post("/api/espn/link", headers=_h(token), data=json.dumps({}))
    assert r.status_code == 400
    assert r.get_json()["error"] == "espn_bad_league_id"
    r = c.post("/api/espn/link", headers=_h(token),
               data=json.dumps({"espn_league_id": "not-numeric"}))
    assert r.status_code == 400
    assert r.get_json()["error"] == "espn_bad_league_id"


def test_credential_only_store_503s_without_encryption_key(client, monkeypatch):
    monkeypatch.delenv("SLEEPER_TOKEN_KEY", raising=False)
    c, token, engine, _ = client

    def _must_not_probe(espn_s2, swid, timeout=15, _opener=None):
        raise AssertionError("no ESPN probe when the pair can't be stored anyway")

    with patch.object(es, "fetch_fan_leagues", _must_not_probe):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": "s2", "swid": "{X}"}))
    assert r.status_code == 503
    assert r.get_json()["error"] == "espn_unconfigured"
    with engine.connect() as conn:
        assert conn.execute(select(db_module.espn_credentials_table)).fetchall() == []


# ---------------------------------------------------------------------------
# POST /api/espn/link — WHAT the verification actually proves
# (verification-oracle fix, 2026-08-12). Production repro: the operator's
# first ESPN connect fired espn_connect_captured in ~10s with no login
# prompt, the store returned {connected:true}, and the very next trade send
# 409'd on a pre-flight that ESPN refused. The store's probe result was
# never bound, and `_parse_fan_leagues` never raises — so a 200 whose
# payload contained no fantasy evidence at all (what an anonymous/partial
# cookie pair produces) sailed through as "verified".
# ---------------------------------------------------------------------------

def test_credential_only_store_refuses_a_probe_that_proved_nothing(client):
    """FAILING-FIRST repro: the probe came back with NOTHING — no football
    leagues, no fantasy entries of any sport. That is not a successful
    authenticated read, so the pair must not be stored and must not be
    stamped verified; the caller gets a credential verdict instead."""
    c, token, engine, _ = client
    with _fan_probe(), \
         patch.object(es, "fetch_league", _must_not_call("the league oracle")):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": "anon-s2", "swid": "{ANON-1}"}))
    assert r.status_code == 403, r.get_data(as_text=True)
    assert r.get_json()["error"] == "espn_bad_credentials"
    with engine.connect() as conn:
        assert conn.execute(
            select(db_module.espn_credentials_table)).fetchall() == []
    assert c.get("/api/espn/link", headers=_h(token)).get_json() == {
        "connected": False}


def test_credential_only_store_accepts_a_fan_with_football_leagues(client):
    """The weak fallback's positive case: the fan profile lists real FFL
    leagues, so the read returned account-specific data. Stored + stamped,
    and the response records WHICH oracle proved it."""
    c, token, engine, _ = client
    with _fan_probe(football=FFL):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": "s2", "swid": "{OK-1}"}))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["verified_via"] == "fan_profile"
    with engine.connect() as conn:
        row = conn.execute(
            select(db_module.espn_credentials_table)).fetchone()._mapping
    assert row["verified_at"]


def test_credential_only_store_accepts_account_with_zero_football_leagues(client):
    """NO FALSE REJECTS: a legitimate ESPN account can have zero FOOTBALL
    leagues (baseball/hockey only, or a fresh fantasy account). The rule is
    'the read returned this account's fantasy data', not 'there is at least
    one football league' — so fantasy entries of any sport still pass."""
    c, token, engine, _ = client
    with _fan_probe(football=(), fantasy_entries=3):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": "s2", "swid": "{HOCKEY-1}"}))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["verified_via"] == "fan_profile"
    with engine.connect() as conn:
        assert conn.execute(
            select(db_module.espn_credentials_table)).fetchone()._mapping[
                "verified_at"]


def test_credential_only_store_prefers_the_linked_league_oracle(client):
    """A league the user already belongs to that ESPN only serves to an
    authenticated member is a REAL authentication oracle (it is the read
    that rejected the bad pair in production, as the send-path 409). When
    one exists it is used, and the weak fan probe is not consulted.

    #321: the pair's SWID is the fixture's team-1 owner (the bound team), so
    the membership assertion passes off the SAME read — exactly one league
    fetch, no re-read."""
    c, token, engine, _ = client
    _link_league("cookie")
    calls = []
    with _league_read(calls=calls), \
         patch.object(es, "probe_fan_profile",
                      _must_not_call("the fan probe"), create=True), \
         patch.object(es, "fetch_fan_leagues", _must_not_call("the fan probe")):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": "s2", "swid": OWNER1_SWID}))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["verified_via"] == "league_read"
    # probed the LINKED league, with the pair the client sent — ONCE (the
    # membership assertion reuses the oracle's parsed teams)
    assert calls == [("league", LINKED_LEAGUE, "s2", OWNER1_SWID)]
    with engine.connect() as conn:
        assert conn.execute(
            select(db_module.espn_credentials_table)).fetchone()._mapping[
                "verified_at"]


def test_credential_only_store_league_oracle_rejection_is_403(client):
    """ESPN 401/403 on the authenticated league read is a credential
    verdict: 403 espn_bad_credentials, nothing stored, and no second-guess
    via the weaker probe. The pair may be a valid sign-in for SOME account
    (the incident's shape: someone else's cookies) — storing it anyway would
    just defer the failure to the send, so the copy names the real recovery
    instead."""
    c, token, engine, _ = client
    _link_league("cookie")
    with _league_read(error=es.EspnAuthError()), \
         patch.object(es, "probe_fan_profile",
                      _must_not_call("the fan probe"), create=True), \
         patch.object(es, "fetch_fan_leagues", _must_not_call("the fan probe")):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": "bad", "swid": "{BAD-1}"}))
    assert r.status_code == 403
    body = r.get_json()
    assert body["error"] == "espn_bad_credentials"
    assert "owns your team" in body["message"]
    with engine.connect() as conn:
        assert conn.execute(
            select(db_module.espn_credentials_table)).fetchall() == []


def test_credential_only_store_league_oracle_outage_is_502(client):
    """ESPN 5xx / transport failure on the strong oracle is NOT a verdict on
    the cookies — retryable 502, nothing stored, and the fallback probe is
    not used to manufacture an answer during an outage."""
    c, token, engine, _ = client
    _link_league("cookie")
    for failure in (es.EspnError("ESPN HTTP 503", kind="http"),
                    urllib.error.URLError("dns failure")):
        with _league_read(error=failure), \
             patch.object(es, "probe_fan_profile",
                          _must_not_call("the fan probe"), create=True), \
             patch.object(es, "fetch_fan_leagues",
                          _must_not_call("the fan probe")):
            r = c.post("/api/espn/link", headers=_h(token),
                       data=json.dumps({"espn_s2": "s2", "swid": "{OK-1}"}))
        assert r.status_code == 502, r.get_data(as_text=True)
        assert r.get_json()["error"] == "espn_unavailable"
        with engine.connect() as conn:
            assert conn.execute(
                select(db_module.espn_credentials_table)).fetchall() == []


def test_credential_only_store_league_oracle_200_must_parse_as_a_league(client):
    """BIND AND ASSERT: a 200 that doesn't parse into this league's team data
    proves nothing (an edge/interstitial page answers 200 too). Treated as
    'couldn't confirm' — retryable 502, nothing stored."""
    c, token, engine, _ = client
    _link_league("cookie")
    with _league_read(payload={"not": "a league"}), \
         patch.object(es, "probe_fan_profile",
                      _must_not_call("the fan probe"), create=True), \
         patch.object(es, "fetch_fan_leagues", _must_not_call("the fan probe")):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": "s2", "swid": "{OK-1}"}))
    assert r.status_code == 502, r.get_data(as_text=True)
    assert r.get_json()["error"] == "espn_unavailable"
    with engine.connect() as conn:
        assert conn.execute(
            select(db_module.espn_credentials_table)).fetchall() == []


def test_credential_only_store_public_linked_league_is_not_an_oracle(client):
    """A PUBLIC league reads without any cookies, so a successful read of one
    says nothing about the pair — AUTH must come from the fan probe.

    #321 amendment: the public league IS still read once, as the MEMBERSHIP
    oracle (its owner_swids are what the identity assertion compares
    against) — but `verified_via` stays `fan_profile`, because that read
    proved membership, not authentication."""
    c, token, engine, _ = client
    _link_league("public")
    fan_calls = []
    league_calls = []
    with _fan_probe(football=FFL, calls=fan_calls), \
         _league_read(calls=league_calls):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": "s2", "swid": OWNER1_SWID}))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["verified_via"] == "fan_profile"
    assert fan_calls == [("fan", "s2", OWNER1_SWID)]
    # exactly one league read — the membership assertion, pair attached
    assert league_calls == [("league", LINKED_LEAGUE, "s2", OWNER1_SWID)]


def test_credential_only_store_purged_league_falls_back_to_fan_probe(client):
    """ESPN purges old leagues: a 404 on the linked league means the ORACLE
    is gone, not that the credential is bad. Fall back to the fan probe
    instead of falsely rejecting a good sign-in."""
    c, token, engine, _ = client
    _link_league("cookie")
    calls = []
    with _league_read(error=es.EspnError("gone", kind="not_found")), \
         _fan_probe(football=FFL, calls=calls):
        r = c.post("/api/espn/link", headers=_h(token),
                   data=json.dumps({"espn_s2": "s2", "swid": "{OK-1}"}))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["verified_via"] == "fan_profile"
    assert calls == [("fan", "s2", "{OK-1}")]


# ---------------------------------------------------------------------------
# GET /api/mfl/auth-link — status
# ---------------------------------------------------------------------------

def test_mfl_status_404_when_flag_off(client):
    c, token, _, _ = client
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.get("/api/mfl/auth-link", headers=_h(token))
    assert r.status_code == 404
    assert r.get_json()["error"] == "feature_disabled"


def test_mfl_status_not_connected(client):
    c, token, _, _ = client
    r = c.get("/api/mfl/auth-link", headers=_h(token))
    assert r.status_code == 200
    assert r.get_json() == {"connected": False}


def test_mfl_status_connected_from_credential_row(client):
    from backend.sleeper_write import encrypt_token
    c, token, _, _ = client
    db_module.upsert_mfl_credential(USER, "mfluser", encrypt_token("MFL_USER_ID=abc"), 2026)
    r = c.get("/api/mfl/auth-link", headers=_h(token))
    body = r.get_json()
    assert body["connected"] is True
    assert body["mfl_username"] == "mfluser"
    assert body["year"] == 2026
    assert "cookie" not in json.dumps(body).lower() or "cookie_encrypted" not in body


def test_mfl_status_connected_from_session_only_cookie(client):
    """Key-less deployments store the cookie in the in-memory session only —
    the status read must see that fallback too."""
    c, token, _, sess = client
    sess["mfl_cookie"] = "MFL_USER_ID=session-only"
    r = c.get("/api/mfl/auth-link", headers=_h(token))
    body = r.get_json()
    assert body["connected"] is True
    assert body["mfl_username"] is None
    assert body["year"] is None


# ---------------------------------------------------------------------------
# DELETE /api/espn/link — disconnect (operator incident 2026-08-12: cookies
# captured from someone else's ESPN sign-in had NO user-facing removal path
# and had to be deleted straight from the production DB)
# ---------------------------------------------------------------------------

OTHER = "999888777666555444"


def test_espn_unlink_deletes_row_and_status_flips(client):
    from backend.sleeper_write import encrypt_token
    c, token, engine, _ = client
    db_module.upsert_espn_credential(USER, "{ABCD-1234}", encrypt_token("s2val"),
                                     verified_at="2026-08-12T00:00:00+00:00")
    assert c.get("/api/espn/link", headers=_h(token)).get_json()["connected"] is True

    r = c.delete("/api/espn/link", headers=_h(token))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json() == {"connected": False}

    with engine.connect() as conn:
        assert conn.execute(select(db_module.espn_credentials_table)).fetchall() == []
    assert c.get("/api/espn/link", headers=_h(token)).get_json() == {"connected": False}


def test_espn_unlink_is_idempotent_when_nothing_stored(client):
    """Deleting with no stored credential is a clean no-op, not an error —
    the client may retry a disconnect or race another device's."""
    c, token, _, _ = client
    r = c.delete("/api/espn/link", headers=_h(token))
    assert r.status_code == 200
    assert r.get_json() == {"connected": False}
    # and again — still clean
    r = c.delete("/api/espn/link", headers=_h(token))
    assert r.status_code == 200
    assert r.get_json() == {"connected": False}


def test_espn_unlink_404_when_flag_off(client):
    c, token, _, _ = client
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.delete("/api/espn/link", headers=_h(token))
    assert r.status_code == 404
    assert r.get_json()["error"] == "feature_disabled"


def test_espn_unlink_requires_session():
    c = server.app.test_client()
    with patch.object(server, "is_enabled", lambda k: k == "espn.link"):
        r = c.delete("/api/espn/link")
    assert r.status_code == 401


def test_espn_unlink_only_deletes_callers_row(client):
    """THE security property: one user's disconnect must never touch another
    user's credential row. Sabotaging delete_espn_credential's WHERE clause
    (deleting indiscriminately) must fail this test."""
    from backend.sleeper_write import encrypt_token
    c, token, engine, _ = client
    db_module.upsert_espn_credential(USER, "{MINE-1}", encrypt_token("mine-s2"),
                                     verified_at="2026-08-12T00:00:00+00:00")
    db_module.upsert_espn_credential(OTHER, "{THEIRS-1}", encrypt_token("their-s2"),
                                     verified_at="2026-08-12T00:00:00+00:00")

    r = c.delete("/api/espn/link", headers=_h(token))
    assert r.status_code == 200

    with engine.connect() as conn:
        rows = conn.execute(select(db_module.espn_credentials_table)).fetchall()
    remaining = {row._mapping["user_id"] for row in rows}
    assert USER not in remaining, "caller's row must be deleted"
    assert OTHER in remaining, "another user's row must be untouched"


# ---------------------------------------------------------------------------
# DELETE /api/mfl/auth-link — disconnect (same gap as ESPN, audited + fixed
# in the same pass; /api/mfl/link stores no credential and needs none)
# ---------------------------------------------------------------------------

def test_mfl_unlink_deletes_row_and_session_cookie(client):
    """DELETE must clear BOTH storage locations — the encrypted row and the
    key-less-deployment session-only copy — or GET would still say
    connected:true via the fallback."""
    from backend.sleeper_write import encrypt_token
    c, token, engine, sess = client
    db_module.upsert_mfl_credential(USER, "mfluser",
                                    encrypt_token("MFL_USER_ID=abc"), 2026)
    sess["mfl_cookie"] = "MFL_USER_ID=session-copy"
    assert c.get("/api/mfl/auth-link", headers=_h(token)).get_json()["connected"] is True

    r = c.delete("/api/mfl/auth-link", headers=_h(token))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json() == {"connected": False}

    assert "mfl_cookie" not in sess
    with engine.connect() as conn:
        assert conn.execute(select(db_module.mfl_credentials_table)).fetchall() == []
    assert c.get("/api/mfl/auth-link", headers=_h(token)).get_json() == {"connected": False}


def test_mfl_unlink_is_idempotent_when_nothing_stored(client):
    c, token, _, _ = client
    r = c.delete("/api/mfl/auth-link", headers=_h(token))
    assert r.status_code == 200
    assert r.get_json() == {"connected": False}


def test_mfl_unlink_404_when_flag_off(client):
    c, token, _, _ = client
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.delete("/api/mfl/auth-link", headers=_h(token))
    assert r.status_code == 404


def test_mfl_unlink_only_deletes_callers_row(client):
    """Same security property as ESPN: user-scoped deletion only."""
    from backend.sleeper_write import encrypt_token
    c, token, engine, _ = client
    db_module.upsert_mfl_credential(USER, "me",
                                    encrypt_token("MFL_USER_ID=mine"), 2026)
    db_module.upsert_mfl_credential(OTHER, "them",
                                    encrypt_token("MFL_USER_ID=theirs"), 2026)

    r = c.delete("/api/mfl/auth-link", headers=_h(token))
    assert r.status_code == 200

    with engine.connect() as conn:
        rows = conn.execute(select(db_module.mfl_credentials_table)).fetchall()
    remaining = {row._mapping["user_id"] for row in rows}
    assert USER not in remaining, "caller's row must be deleted"
    assert OTHER in remaining, "another user's row must be untouched"
