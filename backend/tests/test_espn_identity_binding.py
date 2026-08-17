"""#321 ESPN identity binding (2026-08-16) — T1-T10 from the PRD test plan
(docs/feedback/items/321-espn-token-bleed/prd.md §7.1).

A `verified_at` stamp used to prove SESSION VALIDITY only: any live ESPN
session — including another human's — passed the oracle and was stored as
the caller's. These tests pin the identity-binding fix:

  R1  membership assertion on every verify, across ALL bound leagues
      (set semantics; precedence mismatch > accept > unavailable)
  R2  new verdict wrong_account → 403, wire code UNCHANGED
      (espn_bad_credentials) + additive `reason: "wrong_account"`
  R3  team-binding assertion regardless of cookie provenance (+ stamp
      nulled when the mismatching SWID is the stored credential's)
  R3b re-sync assertion in /api/espn/import
  R4  a PUBLIC-league import fetch no longer stamps verified_at by itself
  R5  zero false rejects (ownerless bound team → inconclusive-accept)
  R6  membership-read outage → 502, fail-open, nothing stored
  R10 pre-release stamp eviction migration (idempotent, date-bounded)

Every test's docstring names its SABOTAGE: the one-line mutation that was
applied and reverted during development to prove the test is non-vacuous
(evidence table in docs/feedback/items/321-espn-token-bleed/status.md).

Nothing touches the network: fetch_league / probe_fan_profile are patched
per-test over the league fixture, whose owner SWIDs are OWNER1/2/3 below.
"""
import copy
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import urllib.error
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.espn_service as es
import backend.server as server
from backend.database import metadata

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
LEAGUE_FIXTURE = os.path.join(FIXTURES, "espn_league_snapshot_2026-07-11.json")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")

USER = "313560442465169408"
LEAGUE_A = "987654321"            # id inside the fixture payload
# Second league (doctored copy). Sorts AFTER league A so the matching league
# is evaluated first — which is what makes T2b's SAB-first-league-wins
# sabotage (accept on the first league's verdict) actually flip the test.
LEAGUE_B = "999888777"

# Owner SWIDs inside the fixture: team N is owned by OWNER<N>.
OWNER1 = "{A1111111-1111-1111-1111-111111111111}"
OWNER2 = "{B2222222-2222-2222-2222-222222222222}"
WRONG_HUMAN = "{FFFFFFFF-0000-0000-0000-FFFFFFFFFFFF}"   # nobody's owner

FFL = ({"league_id": "111", "league_name": "Dynasty", "season": 2026,
        "team_name": "Team"},)


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


def _payload(league_id: str = LEAGUE_A):
    with open(LEAGUE_FIXTURE) as f:
        p = json.load(f)
    p["id"] = int(league_id) if league_id.isdigit() else league_id
    return p


def _link_league(auth: str, league_id: str = LEAGUE_A, team_id: int = 1,
                 season: int = 2026):
    """Linked ESPN league row + membership binding for USER (team bound)."""
    db_module.upsert_espn_league(
        league_id=league_id, user_id=USER, name=f"Fixture {league_id}",
        espn_season=season, espn_auth=auth, espn_my_team_id=team_id,
        total_rosters=3)
    db_module.replace_espn_league_members(league_id, [
        {"user_id": USER, "username": "me", "display_name": "Me",
         "player_ids": []},
    ])


@contextmanager
def _fan_probe(football=FFL, fantasy_entries=None, error=None, calls=None):
    entries = len(football) if fantasy_entries is None else fantasy_entries

    def _probe(espn_s2, swid, timeout=15, _opener=None):
        if calls is not None:
            calls.append(("fan", espn_s2, swid))
        if error:
            raise error
        return {"football_leagues": [dict(f) for f in football],
                "fantasy_entries": entries, "recognized": True}

    with patch.object(es, "probe_fan_profile", _probe):
        yield


@contextmanager
def _league_read(payloads=None, error=None, calls=None):
    """Patch fetch_league. `payloads` maps league_id → payload dict (default:
    the fixture for LEAGUE_A). `error` may be an exception (raised always) or
    a callable(league_id, espn_s2, swid) returning an exception or None."""
    def _fetch(league_id, season, espn_s2=None, swid=None, timeout=15,
               _opener=None):
        lid = str(league_id)
        if calls is not None:
            calls.append((lid, espn_s2, swid))
        err = error(lid, espn_s2, swid) if callable(error) else error
        if err:
            raise err
        table = payloads if payloads is not None else {LEAGUE_A: _payload()}
        if lid not in table:
            raise es.EspnError("no such league in test table", kind="not_found")
        return copy.deepcopy(table[lid])

    with patch.object(es, "fetch_league", _fetch):
        yield


def _must_not_call(kind):
    def _boom(*a, **kw):
        raise AssertionError(f"{kind} must not be consulted here")
    return _boom


@pytest.fixture(autouse=True)
def _no_live_espn():
    """Hard network floor — an unpatched ESPN probe is a loud test failure,
    never a real request."""
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

    token = "fb321-sess-tok"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    xwalk = es.load_crosswalk(XWALK_FIXTURE)
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k == "espn.link"), \
         patch.object(es, "get_crosswalk", lambda _opener=None: xwalk):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _store_pair(c, token, swid, s2="s2"):
    return c.post("/api/espn/link", headers=_h(token),
                  data=json.dumps({"espn_s2": s2, "swid": swid}))


def _link(c, token, league_id=LEAGUE_A, **extra):
    body = {"espn_league_id": league_id, "season": 2026, **extra}
    return c.post("/api/espn/link", headers=_h(token), data=json.dumps(body))


def _cred_rows(engine):
    with engine.connect() as conn:
        return conn.execute(select(db_module.espn_credentials_table)).fetchall()


def _assert_wrong_account_403(r):
    assert r.status_code == 403, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "espn_bad_credentials"   # wire code UNCHANGED
    assert body["reason"] == "wrong_account"
    assert "owns your team" in body["message"]


# ---------------------------------------------------------------------------
# T1 / T2 / T2b — verify-time membership assertion (R1/R2)
# ---------------------------------------------------------------------------

def test_verify_wrong_swid_cookie_league(client):
    """T1 — valid pair, SWID ≠ bound team's owner, cookie league → 403 with
    wire code espn_bad_credentials + reason wrong_account; nothing stored.

    Sabotage SAB-skip-membership: comment out the R1 membership assertion on
    the strong-oracle path (return `auth` unconditionally) — must flip RED.
    """
    c, token, engine = client
    _link_league("cookie")               # bound to team 1 (OWNER1)
    with _league_read():                 # authenticated read succeeds (valid session)
        r = _store_pair(c, token, OWNER2)
    _assert_wrong_account_403(r)
    assert _cred_rows(engine) == []      # absent — never stored


def test_verify_wrong_swid_public_league(client):
    """T2 — only a PUBLIC linked league: the membership read runs anyway (the
    §2 gap case) → 403 wrong_account.

    Sabotage SAB-public-skip: gate the membership loop on
    `espn_auth == 'cookie'` — must flip RED.
    """
    c, token, engine = client
    _link_league("public")
    with _fan_probe(), _league_read():
        r = _store_pair(c, token, OWNER2)
    _assert_wrong_account_403(r)
    assert _cred_rows(engine) == []


def test_verify_two_league_mixed_verdict(client):
    """T2b — two bound leagues; the pair matches league A's bound team but
    conclusively mismatches league B's → 403 wrong_account (R1 precedence:
    ANY conclusive mismatch rejects — one ESPN human owns one SWID, so a
    mixed verdict means a wrong binding somewhere, and re-link recovery is
    the intended surface).

    Sabotage SAB-first-league-wins: `break` after the first league's verdict
    (accept on match) — must flip RED.
    """
    c, token, engine = client
    _link_league("public", LEAGUE_A, team_id=1)      # OWNER1's team
    _link_league("public", LEAGUE_B, team_id=1)
    doctored = _payload(LEAGUE_B)
    doctored["teams"][0]["primaryOwner"] = OWNER2    # league B team 1 → OWNER2
    doctored["teams"][0]["owners"] = [OWNER2]
    with _fan_probe(), \
         _league_read(payloads={LEAGUE_A: _payload(), LEAGUE_B: doctored}):
        r = _store_pair(c, token, OWNER1)
    _assert_wrong_account_403(r)
    assert _cred_rows(engine) == []


# ---------------------------------------------------------------------------
# T3 / T4 / T5 / T6 — accept paths and fail-open (R5/R6)
# ---------------------------------------------------------------------------

def test_verify_correct_swid_each_oracle(client):
    """T3 — the owning SWID passes via the strong oracle AND via
    weak-oracle + membership read: stored, verified_at stamped, 200.

    Sabotage SAB-invert-compare: invert the SWID equality in the membership
    assertion — must flip RED.
    """
    c, token, engine = client
    # Strong oracle (cookie league): membership reuses the oracle's teams.
    _link_league("cookie")
    with _league_read():
        r = _store_pair(c, token, OWNER1)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["verified_via"] == "league_read"
    rows = _cred_rows(engine)
    assert len(rows) == 1 and rows[0]._mapping["verified_at"]

    # Weak oracle + membership read (public league).
    db_module.delete_espn_credential(USER)
    db_module.upsert_espn_league(
        league_id=LEAGUE_A, user_id=USER, name="Fixture", espn_season=2026,
        espn_auth="public", espn_my_team_id=1, total_rosters=3)
    with _fan_probe(), _league_read():
        r = _store_pair(c, token, OWNER1)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["verified_via"] == "fan_profile"
    rows = _cred_rows(engine)
    assert len(rows) == 1 and rows[0]._mapping["verified_at"]


def test_verify_ownerless_team_inconclusive(client):
    """T4 — the bound team has no owner_swid → INCONCLUSIVE-ACCEPT (R5),
    stored. (Deliberately no plan-§F1 "is any team's owner" fallback.)

    Sabotage SAB-reject-ownerless: treat a missing owner_swid as a mismatch
    — must flip RED.
    """
    c, token, engine = client
    _link_league("cookie")
    ownerless = _payload()
    ownerless["teams"][0]["primaryOwner"] = ""
    ownerless["teams"][0]["owners"] = []
    with _league_read(payloads={LEAGUE_A: ownerless}):
        r = _store_pair(c, token, WRONG_HUMAN)
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = _cred_rows(engine)
    assert len(rows) == 1 and rows[0]._mapping["verified_at"]


def test_verify_no_linked_league_unchanged(client):
    """T5 — no league rows: the membership check is vacuous, the weak-oracle
    verdict stands, and NO league fetch is attempted.

    Sabotage SAB-force-fetch: unconditionally require a membership league
    read (treat an empty bound set as `unavailable`) — must flip RED.
    """
    c, token, engine = client
    with _fan_probe(), \
         patch.object(es, "fetch_league", _must_not_call("a league read")):
        r = _store_pair(c, token, WRONG_HUMAN)
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = _cred_rows(engine)
    assert len(rows) == 1 and rows[0]._mapping["verified_at"]


def test_verify_membership_read_outage(client):
    """T6 — the membership fetch_league raises a transport error → 502
    espn_unavailable, NOTHING stored (R6 fail-open: a good sign-in is never
    called bad because ESPN was down).

    Sabotage SAB-outage-as-bad: map the membership-read exception to verdict
    `bad` (403) — must flip RED.
    """
    c, token, engine = client
    _link_league("public")
    with _fan_probe(), \
         _league_read(error=urllib.error.URLError("dns failure")):
        r = _store_pair(c, token, OWNER1)
    assert r.status_code == 502, r.get_data(as_text=True)
    assert r.get_json()["error"] == "espn_unavailable"
    assert _cred_rows(engine) == []


# ---------------------------------------------------------------------------
# T7 / T8 / T8b — league-link path (R3/R4)
# ---------------------------------------------------------------------------

def test_link_public_league_no_stamp(client):
    """T7 — import path, pasted cookies + PUBLIC league (the anonymous probe
    reads it), no identity mismatch, but the verify says the pair proved
    nothing → the import still succeeds 200, the pair is NOT stored, and the
    response says so (credential_stored: false + credential_reason). A
    fan-probe outage lands in credential_reason "unavailable", never a 502.

    Sabotage SAB-always-stamp: restore the unconditional store+stamp on the
    pasted-cookie import path — must flip RED.
    """
    c, token, engine = client
    # verify says BAD (fan probe answers with nothing account-specific)
    with _league_read(), _fan_probe(football=(), fantasy_entries=0):
        r = _link(c, token, team_id=1, espn_s2="s2", swid=OWNER1)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["credential_stored"] is False
    assert body["credential_reason"] == "unverified"
    assert _cred_rows(engine) == []          # pair never reached the DB

    # verify UNAVAILABLE (fan probe outage) → same, reason "unavailable"
    with _league_read(), _fan_probe(error=urllib.error.URLError("down")):
        r = _link(c, token, team_id=1, espn_s2="s2", swid=OWNER1)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["credential_stored"] is False
    assert body["credential_reason"] == "unavailable"
    assert _cred_rows(engine) == []


def test_link_chosen_team_swid_mismatch(client):
    """T8 — import with a team_id whose owner_swid ≠ the pasted SWID → 403
    wrong_account, nothing persisted (R3; comparison-only, the teams are in
    hand from the import fetch).

    Sabotage SAB-skip-link-check: bypass the link-path R3 assertion — must
    flip RED.
    """
    c, token, engine = client
    with _league_read():
        r = _link(c, token, team_id=2, espn_s2="s2", swid=OWNER1)
    _assert_wrong_account_403(r)
    assert _cred_rows(engine) == []
    with engine.connect() as conn:
        assert conn.execute(select(db_module.leagues_table)).fetchall() == []
        assert conn.execute(
            select(db_module.league_members_table)).fetchall() == []


def test_link_stored_cookie_fallback_mismatch(client):
    """T8b — the store-then-link hole: a wrong-human pair stored earlier
    under R5's vacuous accept (no league yet); the user then links a PUBLIC
    league picking their team via the STORED-cookie fallback
    (pasted_cookie=False) → 403 wrong_account, nothing imported, and the
    stored row's verified_at is NULLED so GET status stops lying.

    Sabotage SAB-pasted-only: gate the R3 assertion on `pasted_cookie` —
    must flip RED.
    """
    c, token, engine = client
    # 1. wrong-human pair stored with no linked league (vacuous accept)
    with _fan_probe(), \
         patch.object(es, "fetch_league", _must_not_call("a league read")):
        r = _store_pair(c, token, WRONG_HUMAN)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _cred_rows(engine)[0]._mapping["verified_at"]
    assert c.get("/api/espn/link", headers=_h(token)).get_json()["connected"] is True

    # 2. link a PUBLIC league, choose team 1 — NO cookies pasted, the stored
    #    pair rides along via the fallback and mismatches OWNER1.
    with _league_read():
        r = _link(c, token, team_id=1)
    _assert_wrong_account_403(r)
    with engine.connect() as conn:
        assert conn.execute(select(db_module.leagues_table)).fetchall() == []
    rows = _cred_rows(engine)
    assert len(rows) == 1                       # row kept (forensics posture)
    assert rows[0]._mapping["verified_at"] is None   # stamp nulled
    assert c.get("/api/espn/link", headers=_h(token)).get_json()["connected"] is False


# ---------------------------------------------------------------------------
# T8c — re-sync assertion (R3b)
# ---------------------------------------------------------------------------

def test_import_resync_swid_mismatch(client):
    """T8c — /api/espn/import re-sync where the STORED SWID no longer owns
    the row's bound team → 403 wrong_account and the stamp is nulled. This
    catches wrong-identity rows bound BEFORE the fix that the R10 migration
    alone cannot identify.

    Sabotage SAB-skip-resync-check: bypass the re-sync R3b assertion — must
    flip RED.
    """
    c, token, engine = client
    from backend.sleeper_write import encrypt_token
    _link_league("cookie")
    db_module.upsert_espn_credential(
        USER, WRONG_HUMAN, encrypt_token("s2"),
        verified_at=datetime.now(timezone.utc).isoformat())
    with _league_read():
        r = c.post("/api/espn/import", headers=_h(token),
                   data=json.dumps({"league_id": LEAGUE_A}))
    _assert_wrong_account_403(r)
    rows = _cred_rows(engine)
    assert len(rows) == 1 and rows[0]._mapping["verified_at"] is None


# ---------------------------------------------------------------------------
# T9 — R10 migration
# ---------------------------------------------------------------------------

def test_migration_nulls_prerelease(client):
    """T9 — every stamp `< RELEASE_CUTOFF` is nulled regardless of vintage;
    a born-NULL legacy row is untouched; the exact-cutoff boundary and
    post-cutoff stamps (including a microsecond-bearing one inside the
    margin's lexicographic edge) survive; a re-run is a structural no-op
    (NULL fails `<`); GET reports connected:false for the nulled row.

    Sabotage SAB-invert-cutoff: flip `<` to `>=` in the eviction WHERE —
    must flip RED.
    """
    c, token, engine = client
    from backend.sleeper_write import encrypt_token
    cutoff = db_module._ESPN_VERIFIED_AT_RELEASE_CUTOFF
    fixtures = {
        # user_id suffix → verified_at
        "born_null":   None,                            # pre-2fa1ff2 shape
        "dishonest":   "2026-08-12T12:00:00+00:00",     # broken-verify window
        "post_oracle": "2026-08-14T00:00:00+00:00",     # honest-but-identityless
        "boundary":    cutoff,                          # exact cutoff — survives
        "micro":       cutoff.replace("+00:00", ".123456+00:00"),  # '.' > '+'
        "new_code":    "2026-09-01T00:00:00+00:00",     # post-release stamp
    }
    for suffix, stamp in fixtures.items():
        db_module.upsert_espn_credential(
            f"user-{suffix}", OWNER1, encrypt_token("s2"), verified_at=stamp)

    evicted = db_module._evict_prerelease_espn_verified_stamps()
    assert evicted == 2                                  # dishonest + post_oracle

    def stamp_of(suffix):
        return (db_module.get_espn_credential(f"user-{suffix}") or {}).get(
            "verified_at")

    assert stamp_of("born_null") is None
    assert stamp_of("dishonest") is None
    assert stamp_of("post_oracle") is None
    assert stamp_of("boundary") == fixtures["boundary"]
    assert stamp_of("micro") == fixtures["micro"]
    assert stamp_of("new_code") == fixtures["new_code"]

    # Re-run: structural no-op — nulled rows fail `<` under three-valued
    # NULL, so nothing matches and survivors stay untouched.
    assert db_module._evict_prerelease_espn_verified_stamps() == 0
    assert stamp_of("boundary") == fixtures["boundary"]

    # GET honesty gate: an evicted row reads as NOT connected.
    with server._sessions_lock:
        server._sessions["t9-tok"] = {"user_id": "user-dishonest",
                                      "active_format": "1qb_ppr",
                                      "last_active": 0.0}
    try:
        r = c.get("/api/espn/link", headers=_h("t9-tok"))
    finally:
        with server._sessions_lock:
            server._sessions.pop("t9-tok", None)
    assert r.status_code == 200 and r.get_json()["connected"] is False


# ---------------------------------------------------------------------------
# T10 — additive 403 shape
# ---------------------------------------------------------------------------

def test_403_shape_additive(client):
    """T10 — the wrong-account 403 carries error + message + reason; a PLAIN
    bad-credential rejection carries NO reason key (R2 — clients narrowing
    on `error === 'espn_bad_credentials'` keep working unchanged; the
    sabotage doubles as the espnCredentialsRejected compatibility proof).

    Sabotage SAB-rename-code: change the wrong-account `error` value to
    `espn_wrong_account` — must flip RED.
    """
    c, token, engine = client
    # wrong-account rejection: all three fields
    _link_league("cookie")
    with _league_read():
        r = _store_pair(c, token, OWNER2)
    _assert_wrong_account_403(r)

    # plain rejection (fan probe returned nothing account-specific): no reason
    with engine.begin() as conn:
        conn.execute(db_module.leagues_table.delete())
        conn.execute(db_module.league_members_table.delete())
    with _fan_probe(football=(), fantasy_entries=0):
        r = _store_pair(c, token, OWNER2)
    assert r.status_code == 403
    body = r.get_json()
    assert body["error"] == "espn_bad_credentials"
    assert "message" in body
    assert "reason" not in body
