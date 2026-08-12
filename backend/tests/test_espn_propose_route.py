"""End-to-end tests for the "Send in ESPN" surface in backend/server.py:

  POST /api/trades/propose-espn   — send a trade into ESPN

Flask test client + isolated in-memory SQLite, real injected session, real
encryption key. Mocked: `espn_write.propose_trade` (the actual ESPN write) and
`espn_service.fetch_league` (the pre-flight read) — ZERO live network,
mirroring test_mfl_propose_route.py. The flag is forced on via a patched
`is_enabled`; the crosswalk is a tiny fake with the four LIVE-VERIFIED
espn↔sleeper id pairs from the 2026-08-11 capture.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.espn_service as espn_service
import backend.espn_write as espn_write
import backend.server as server
from backend.database import metadata
from backend.espn_service import EspnAuthError, EspnError
from backend.espn_write import EspnWriteAuthError, EspnWriteError

USER = "313560442465169408"
LEAGUE = "11896"                      # ESPN league ids are numeric (misroute class)
MY_TEAM, THEIR_TEAM = 5, 12
MY_SWID = "{AAAA1111-0000-0000-0000-000000000001}"
THEIR_SWID = "{BBBB2222-0000-0000-0000-000000000002}"
THEIR_MEMBER = f"espn:{THEIR_SWID}"

# Live-verified id pairs (capture doc §Resolved 1): sleeper ↔ espn.
SLEEPER_GIVE, SLEEPER_RECV = "12485", "8136"     # Tez Johnson / Rachaad White
ESPN_GIVE, ESPN_RECV = 4608810, 4697815

_FAKE_XWALK = SimpleNamespace(by_espn_id={str(ESPN_GIVE): SLEEPER_GIVE,
                                          str(ESPN_RECV): SLEEPER_RECV})

# Raw mTeam+mRoster payload the mocked pre-flight read returns. Tez sits in a
# real lineup slot (2) so the route's slot plumbing is observable; Rachaad is
# benched (20) like both captured items.
RAW_LEAGUE = {
    "id": int(LEAGUE),
    "seasonId": 2026,
    "scoringPeriodId": 0,
    "status": {"latestScoringPeriod": 0},
    "members": [{"id": MY_SWID, "displayName": "matt"},
                {"id": THEIR_SWID, "displayName": "rival"}],
    "settings": {"name": "QA ESPN League", "size": 2},
    "teams": [
        {"id": MY_TEAM, "name": "My Team", "primaryOwner": MY_SWID,
         "roster": {"entries": [
             {"lineupSlotId": 2, "playerPoolEntry": {"player": {
                 "id": ESPN_GIVE, "fullName": "Tez Johnson",
                 "defaultPositionId": 3}}},
         ]}},
        {"id": THEIR_TEAM, "name": "Their Team", "primaryOwner": THEIR_SWID,
         "roster": {"entries": [
             {"lineupSlotId": 20, "playerPoolEntry": {"player": {
                 "id": ESPN_RECV, "fullName": "Rachaad White",
                 "defaultPositionId": 2}}},
         ]}},
    ],
}


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


def _propose_body(**over):
    body = {"league_id": LEAGUE, "their_user_id": THEIR_MEMBER,
            "give_player_ids": [SLEEPER_GIVE],
            "receive_player_ids": [SLEEPER_RECV]}
    body.update(over)
    return json.dumps(body)


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "sess-tok-espn"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0,
            "verified": True}

    server.app.config["TESTING"] = True
    server._espn_reverse_xwalk_cache = None     # cache is per-crosswalk-object
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k == "espn.send"), \
         patch.object(server, "_shared_crosswalk", lambda: _FAKE_XWALK), \
         patch.object(espn_service, "fetch_league",
                      MagicMock(return_value=RAW_LEAGUE)), \
         patch.object(server, "touch_user_activity", MagicMock()):
        # Linked ESPN league bound to USER, cookie-auth, team binding set.
        db_module.upsert_espn_league(
            league_id=LEAGUE, user_id=USER, name="QA ESPN League",
            espn_season=2026, espn_auth="cookie", espn_my_team_id=MY_TEAM,
            total_rosters=2)
        # Stored, decryptable ESPN cookie pair.
        db_module.upsert_espn_credential(
            USER, MY_SWID, server._sleeper_write.encrypt_token("s2%3Avalue"))
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)
            server._espn_reverse_xwalk_cache = None


# ---------------------------------------------------------------------------
# POST /api/trades/propose-espn — happy path
# ---------------------------------------------------------------------------

def test_propose_happy_path_reverse_maps_and_resolves_teams(client):
    c, token = client
    fake = MagicMock(return_value={"transaction_id": "abc-123",
                                   "status": "PENDING", "raw": {}})
    with patch.object(espn_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body())
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["status"] == "proposed"
    assert body["transaction_id"] == "abc-123"
    assert body["espn_status"] == "PENDING"
    (espn_s2, swid, req), _ = fake.call_args
    assert espn_s2 == "s2%3Avalue"                 # decrypted stored cookie
    assert swid == MY_SWID
    # BOTH team ids resolved server-side: mine from the leagues row binding,
    # theirs from the synthetic member id against the live team list.
    assert req.my_team_id == MY_TEAM
    assert req.their_team_id == THEIR_TEAM
    assert req.member_swid == MY_SWID
    # players crossed sleeper→ESPN id space, nothing dropped
    assert req.give_espn_player_ids == [ESPN_GIVE]
    assert req.receive_espn_player_ids == [ESPN_RECV]
    # scoringPeriodId read from league status (offseason 0), never hardcoded
    assert req.scoring_period_id == 0
    # real lineup slots threaded from the roster read (bench fallback aside)
    assert req.lineup_slots[ESPN_GIVE] == 2
    assert req.lineup_slots[ESPN_RECV] == 20
    assert req.season == 2026 and req.league_id == LEAGUE


def test_propose_resolves_counterparty_from_team_shaped_member_id(client):
    """The `espn:{league}.t{N}` synthetic-id shape (SWID-less teams)."""
    c, token = client
    fake = MagicMock(return_value={"transaction_id": "x", "status": "PENDING",
                                   "raw": {}})
    with patch.object(espn_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body(
                       their_user_id=f"espn:{LEAGUE}.t{THEIR_TEAM}"))
    assert r.status_code == 200, r.get_data(as_text=True)
    (_, _, req), _ = fake.call_args
    assert req.their_team_id == THEIR_TEAM


def test_propose_accepts_explicit_team_id_but_verifies_it_live(client):
    c, token = client
    fake = MagicMock(return_value={"transaction_id": "x", "status": "PENDING",
                                   "raw": {}})
    with patch.object(espn_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body(their_user_id=None,
                                      their_team_id=THEIR_TEAM))
    assert r.status_code == 200, r.get_data(as_text=True)
    # A team id that is NOT in the live league list is refused, not trusted.
    with patch.object(espn_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body(their_user_id=None, their_team_id=99))
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Hard blocks — picks (unverified encoding) and unmapped players. An offer
# must NEVER silently drop an asset; nothing may reach the write.
# ---------------------------------------------------------------------------

def test_propose_hard_blocks_pick_asset(client):
    """THE pick guardrail: ESPN pick encoding is UNVERIFIED, so ANY pick
    asset refuses the whole send — never guessed at, never dropped."""
    c, token = client
    my_pick = f"{LEAGUE}_2027_1_{THEIR_TEAM}"      # FTF owned-pick id shape
    fake = MagicMock()
    with patch.object(espn_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body(
                       give_player_ids=[SLEEPER_GIVE, my_pick]))
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "espn_pick_unsupported"
    assert body["picks"] == [my_pick]
    fake.assert_not_called()        # nothing reached ESPN


def test_propose_hard_blocks_generic_pick(client):
    c, token = client
    fake = MagicMock()
    with patch.object(espn_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body(
                       receive_player_ids=[SLEEPER_RECV, "generic_pick_1_early"]))
    assert r.status_code == 422
    assert r.get_json()["error"] == "espn_pick_unsupported"
    assert r.get_json()["picks"] == ["generic_pick_1_early"]
    fake.assert_not_called()


def test_propose_hard_blocks_on_unmapped_player(client):
    """THE player guardrail: a player the crosswalk can't place blocks the
    whole send — a partially-mapped trade is a DIFFERENT trade."""
    c, token = client
    fake = MagicMock()
    with patch.object(espn_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body(
                       give_player_ids=[SLEEPER_GIVE, "424242"]))
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "espn_asset_unmapped"
    assert body["unmapped"] == ["424242"]
    fake.assert_not_called()        # nothing reached ESPN


# ---------------------------------------------------------------------------
# Auth failures — 401/403 (write OR pre-flight) → structured 409 + the stored
# credential is dropped so the client re-prompts the ESPN connect flow.
# ---------------------------------------------------------------------------

def test_propose_write_auth_rejection_drops_credential_returns_409(client):
    c, token = client
    with patch.object(espn_write, "propose_trade",
                      MagicMock(side_effect=EspnWriteAuthError(detail="HTTP 401"))):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body())
    assert r.status_code == 409 and r.get_json()["error"] == "espn_auth_expired"
    # dead credential was dropped so the client re-prompts the connect flow
    assert db_module.get_espn_credential(USER) is None


def test_propose_preflight_auth_rejection_drops_credential_returns_409(client):
    c, token = client
    with patch.object(espn_service, "fetch_league",
                      MagicMock(side_effect=EspnAuthError())):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body())
    assert r.status_code == 409 and r.get_json()["error"] == "espn_auth_expired"
    assert db_module.get_espn_credential(USER) is None


def test_propose_write_failure_returns_502(client):
    c, token = client
    with patch.object(espn_write, "propose_trade",
                      MagicMock(side_effect=EspnWriteError("boom", kind="network"))):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body())
    assert r.status_code == 502 and r.get_json()["error"] == "espn_write_failed"


def test_propose_preflight_unavailable_maps_structured(client):
    c, token = client
    with patch.object(espn_service, "fetch_league",
                      MagicMock(side_effect=EspnError("down", kind="http"))):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body())
    assert r.status_code == 502 and r.get_json()["error"] == "espn_unavailable"


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def test_propose_requires_verified_session(client):
    c, token = client
    with server._sessions_lock:
        server._sessions[token]["verified"] = False
    r = c.post("/api/trades/propose-espn", headers=_h(token), data=_propose_body())
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"


def test_propose_feature_off_returns_404(client):
    c, token = client
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body())
    assert r.status_code == 404 and r.get_json()["error"] == "feature_disabled"


def test_propose_unlinked_league_returns_404(client):
    c, token = client
    r = c.post("/api/trades/propose-espn", headers=_h(token),
               data=_propose_body(league_id="99999",
                                  their_user_id=f"espn:{THEIR_SWID}"))
    assert r.status_code == 404 and r.get_json()["error"] == "espn_not_linked"


def test_propose_no_credential_returns_409_not_connected(client):
    c, token = client
    db_module.delete_espn_credential(USER)
    r = c.post("/api/trades/propose-espn", headers=_h(token), data=_propose_body())
    assert r.status_code == 409 and r.get_json()["error"] == "espn_not_connected"


def test_propose_refuses_own_team_and_garbage_counterparty(client):
    c, token = client
    r = c.post("/api/trades/propose-espn", headers=_h(token), data=_propose_body(
        their_user_id=f"espn:{MY_SWID}"))
    assert r.status_code == 400
    r = c.post("/api/trades/propose-espn", headers=_h(token), data=_propose_body(
        their_user_id="someone_else"))           # not a synthetic ESPN member id
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# trade_sent analytics (taxonomy 2026-08-11, rescoped to non-Sleeper
# platforms) — fires on confirmed success ONLY, platform 'espn' mandatory and
# non-null (the NULL-platform incident is why this is asserted, not assumed).
# ---------------------------------------------------------------------------

def _trade_sent_rows():
    from sqlalchemy import select
    with db_module.engine.connect() as conn:
        rows = conn.execute(
            select(db_module.user_events_table)
            .where(db_module.user_events_table.c.event_type == "trade_sent")
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def test_propose_success_fires_trade_sent_platform_espn(client):
    c, token = client
    fake = MagicMock(return_value={"transaction_id": "x", "status": "PENDING",
                                   "raw": {}})
    with patch.object(espn_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body())
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = _trade_sent_rows()
    assert len(rows) == 1
    assert rows[0]["user_id"] == USER
    assert rows[0]["league_id"] == LEAGUE
    props = json.loads(rows[0]["props"])
    assert props["platform"] == "espn"                # mandatory, non-null
    assert props["give_count"] == 1
    assert props["receive_count"] == 1
    assert props["outcome"] == "proposed"


def test_propose_hard_blocks_fire_no_trade_sent(client):
    """Both 422 hard blocks are refusals, not sends — neither may land a
    trade_sent row."""
    c, token = client
    with patch.object(espn_write, "propose_trade", MagicMock()):
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body(
                       give_player_ids=[SLEEPER_GIVE, "424242"]))
        assert r.status_code == 422
        r = c.post("/api/trades/propose-espn", headers=_h(token),
                   data=_propose_body(
                       give_player_ids=[SLEEPER_GIVE,
                                        f"{LEAGUE}_2027_1_{THEIR_TEAM}"]))
        assert r.status_code == 422
    assert _trade_sent_rows() == []
