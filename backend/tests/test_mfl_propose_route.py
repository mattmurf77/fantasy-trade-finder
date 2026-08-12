"""End-to-end tests for the "Send in MFL" surface in backend/server.py:

  POST /api/trades/propose-mfl   — send a trade into MFL
  POST /api/trades/validate      — the MFL pre-flight branch (#180 parity)

Flask test client + isolated in-memory SQLite, real injected session, real
encryption key. Mocked: `mfl_write.propose_trade` (the actual MFL import) and
`mfl_service.fetch_rosters` (the validate pre-flight read) — zero live
network, mirroring test_sleeper_write_route.py. The flag is forced on via a
patched `is_enabled`; the crosswalk is a tiny fake with a known
sleeper↔MFL id map.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.mfl_write as mfl_write
import backend.server as server
from backend.database import metadata
from backend.mfl_write import MflWriteAuthError, MflWriteError

USER = "313560442465169408"
LEAGUE = "62846"                       # MFL league ids are numeric (misroute class)
MY_FID, THEIR_FID = "0001", "0005"
THEIR_MEMBER = f"mfl:{LEAGUE}.f{THEIR_FID}"

# sleeper_id → roster; crosswalk maps sleeper→mfl 1:1 below.
SLEEPER_GIVE, SLEEPER_RECV = "4034", "6786"      # my CMC for their Jaylen Waddle, say
MFL_GIVE, MFL_RECV = "13130", "14085"

_FAKE_XWALK = SimpleNamespace(by_mfl_sleeper={MFL_GIVE: SLEEPER_GIVE,
                                              MFL_RECV: SLEEPER_RECV})

# FTF pick ids ride the SAME arrays as players (database.make_pick_id:
# `{league}_{season}_{round}_{original_roster}`; for MFL leagues the roster
# part is the MFL franchise id). Ground truth for encoding is the stored
# futureDraftPicks snapshot below (values as strings — MFL's JSON returns
# strings and parse_future_picks stores them raw).
MY_PICK = f"{LEAGUE}_2027_1_{THEIR_FID}"       # I own their original 2027 1st
THEIR_PICK = f"{LEAGUE}_2028_2_{THEIR_FID}"    # they own their own 2028 2nd
FUTURE_PICKS = [
    {"franchise_id": MY_FID, "year": "2027", "round": "1",
     "original_owner": THEIR_FID},
    {"franchise_id": THEIR_FID, "year": "2028", "round": "2",
     "original_owner": THEIR_FID},
]


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

    token = "sess-tok-mfl"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0,
            "verified": True}

    server.app.config["TESTING"] = True
    server._mfl_reverse_xwalk_cache = None      # cache is per-crosswalk-object
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k == "trade.send_in_mfl"), \
         patch.object(server, "_shared_crosswalk", lambda: _FAKE_XWALK), \
         patch.object(server, "touch_user_activity", MagicMock()):
        # Linked MFL league bound to USER, host already resolved.
        db_module.upsert_platform_league(
            league_id=LEAGUE, user_id=USER, name="QA MFL League",
            platform="mfl", season=2026, auth="cookie", my_team=MY_FID,
            total_rosters=12, host="www76.myfantasyleague.com",
            future_picks=FUTURE_PICKS)
        # Stored, decryptable MFL cookie.
        db_module.upsert_mfl_credential(
            USER, "qa_mfl_user",
            server._sleeper_write.encrypt_token("MFL_USER_ID=abc123"), 2026)
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)
            server._mfl_reverse_xwalk_cache = None


# ---------------------------------------------------------------------------
# POST /api/trades/propose-mfl
# ---------------------------------------------------------------------------

def test_propose_happy_path_reverse_maps_and_resolves_franchises(client):
    c, token = client
    fake = MagicMock(return_value={"status": "OK", "raw": "<status>OK</status>"})
    with patch.object(mfl_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-mfl", headers=_h(token),
                   data=_propose_body())
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == "proposed"
    (cookie, host, year, req), _ = fake.call_args
    assert cookie == "MFL_USER_ID=abc123"
    assert host == "www76.myfantasyleague.com" and year == 2026
    # counterparty parsed server-side from the synthetic member id
    assert req.offered_to == THEIR_FID
    # players crossed sleeper→MFL id space, nothing dropped
    assert req.will_give_up == [MFL_GIVE]
    assert req.will_receive == [MFL_RECV]


def test_propose_accepts_pick_assets_preencoded(client):
    c, token = client
    fake = MagicMock(return_value={"status": "OK", "raw": ""})
    with patch.object(mfl_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body(
            give_pick_assets=["FP_0001_2027_1"], receive_pick_assets=["DP_02_05"]))
    assert r.status_code == 200, r.get_data(as_text=True)
    (_, _, _, req), _ = fake.call_args
    assert req.will_give_up == [MFL_GIVE, "FP_0001_2027_1"]
    assert req.will_receive == [MFL_RECV, "DP_02_05"]


def test_propose_encodes_owned_picks_from_snapshot(client):
    """Picks ride the same arrays as players; the route splits them out and
    encodes FTF pick ids → MFL `FP_…` strings against the stored
    futureDraftPicks snapshot (verified shape 2026-08-11: originalPickFor
    4-digit padded, round 1-based unpadded)."""
    c, token = client
    fake = MagicMock(return_value={"status": "OK", "raw": ""})
    with patch.object(mfl_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body(
            give_player_ids=[SLEEPER_GIVE, MY_PICK],
            receive_player_ids=[SLEEPER_RECV, THEIR_PICK]))
    assert r.status_code == 200, r.get_data(as_text=True)
    (_, _, _, req), _ = fake.call_args
    assert req.will_give_up == [MFL_GIVE, f"FP_{THEIR_FID}_2027_1"]
    assert req.will_receive == [MFL_RECV, f"FP_{THEIR_FID}_2028_2"]


def test_propose_hard_blocks_pick_missing_from_snapshot(client):
    """THE pick guardrail: a pick that isn't in the league's futureDraftPicks
    snapshot blocks the whole send — never encoded on faith, never dropped."""
    c, token = client
    ghost = f"{LEAGUE}_2030_1_{MY_FID}"        # no such pick in the snapshot
    fake = MagicMock()
    with patch.object(mfl_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body(
            give_player_ids=[SLEEPER_GIVE, ghost]))
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "mfl_asset_unmapped"
    assert body["unmapped"] == [ghost]
    fake.assert_not_called()        # nothing reached MFL


def test_propose_hard_blocks_generic_pick(client):
    """A generic ladder rung ('Early 1st') names no concrete MFL pick — it
    must hard-block, never guess at an encoding."""
    c, token = client
    fake = MagicMock()
    with patch.object(mfl_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body(
            receive_player_ids=[SLEEPER_RECV, "generic_pick_1_early"]))
    assert r.status_code == 422
    assert r.get_json()["unmapped"] == ["generic_pick_1_early"]
    fake.assert_not_called()


def test_propose_rejects_malformed_pick_assets(client):
    c, token = client
    r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body(
        give_pick_assets=["FP_5_2027_1"]))     # unpadded franchise — never sent
    assert r.status_code == 400 and r.get_json()["error"] == "bad_request"


def test_propose_hard_blocks_on_unmapped_asset(client):
    """THE guardrail: an asset that fails the reverse crosswalk blocks the
    whole send — an offer must never silently lose an asset."""
    c, token = client
    fake = MagicMock()
    with patch.object(mfl_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body(
            give_player_ids=[SLEEPER_GIVE, "9999_no_such_player"]))
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "mfl_asset_unmapped"
    assert body["unmapped"] == ["9999_no_such_player"]
    fake.assert_not_called()        # nothing reached MFL


def test_propose_expired_cookie_drops_credential_returns_409(client):
    c, token = client
    with patch.object(mfl_write, "propose_trade",
                      MagicMock(side_effect=MflWriteAuthError(detail="HTTP 403"))):
        r = c.post("/api/trades/propose-mfl", headers=_h(token),
                   data=_propose_body())
    assert r.status_code == 409 and r.get_json()["error"] == "mfl_auth_expired"
    # dead credential was dropped so the client re-prompts sign-in
    assert db_module.get_mfl_credential(USER) is None


def test_propose_write_failure_returns_502(client):
    c, token = client
    with patch.object(mfl_write, "propose_trade",
                      MagicMock(side_effect=MflWriteError("boom", kind="network"))):
        r = c.post("/api/trades/propose-mfl", headers=_h(token),
                   data=_propose_body())
    assert r.status_code == 502 and r.get_json()["error"] == "mfl_write_failed"


def test_propose_requires_verified_session(client):
    c, token = client
    with server._sessions_lock:
        server._sessions[token]["verified"] = False
    r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body())
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"


def test_propose_feature_off_returns_404(client):
    c, token = client
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.post("/api/trades/propose-mfl", headers=_h(token),
                   data=_propose_body())
    assert r.status_code == 404 and r.get_json()["error"] == "feature_disabled"


def test_propose_unlinked_league_returns_404(client):
    c, token = client
    r = c.post("/api/trades/propose-mfl", headers=_h(token),
               data=_propose_body(league_id="99999",
                                  their_user_id="mfl:99999.f0005"))
    assert r.status_code == 404 and r.get_json()["error"] == "mfl_not_linked"


def test_propose_no_cookie_returns_409_not_connected(client):
    c, token = client
    db_module.delete_mfl_credential(USER)
    r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body())
    assert r.status_code == 409 and r.get_json()["error"] == "mfl_not_connected"


def test_propose_refuses_own_franchise_and_garbage_counterparty(client):
    c, token = client
    r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body(
        their_user_id=f"mfl:{LEAGUE}.f{MY_FID}"))
    assert r.status_code == 400
    r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body(
        their_user_id="someone_else"))          # not a synthetic MFL member id
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# trade_sent analytics (taxonomy addendum 2026-08-11) — fires on confirmed
# success only, platform always present and non-null (the NULL-platform
# incident is the reason this is asserted, not assumed).
# ---------------------------------------------------------------------------

def _trade_sent_rows():
    from sqlalchemy import select
    with db_module.engine.connect() as conn:
        rows = conn.execute(
            select(db_module.user_events_table)
            .where(db_module.user_events_table.c.event_type == "trade_sent")
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def test_propose_success_fires_trade_sent_platform_mfl(client):
    c, token = client
    fake = MagicMock(return_value={"status": "OK", "raw": ""})
    with patch.object(mfl_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body(
            give_pick_assets=["FP_0001_2027_1"]))
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = _trade_sent_rows()
    assert len(rows) == 1
    assert rows[0]["user_id"] == USER
    assert rows[0]["league_id"] == LEAGUE
    props = json.loads(rows[0]["props"])
    assert props["platform"] == "mfl"                 # mandatory, non-null
    assert props["give_count"] == 2                   # 1 player + 1 pick (side-attributed)
    assert props["receive_count"] == 1
    assert props["outcome"] == "proposed"


def test_propose_trade_sent_counts_in_array_picks(client):
    """A pick riding give_player_ids folds into give_count the same as a
    pre-encoded pick asset (both are side-attributed)."""
    c, token = client
    fake = MagicMock(return_value={"status": "OK", "raw": ""})
    with patch.object(mfl_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body(
            give_player_ids=[SLEEPER_GIVE, MY_PICK]))
    assert r.status_code == 200, r.get_data(as_text=True)
    props = json.loads(_trade_sent_rows()[0]["props"])
    assert props["give_count"] == 2 and props["receive_count"] == 1


def test_propose_unmapped_hard_block_fires_no_trade_sent(client):
    """The mfl_asset_unmapped hard block is a refusal, not a send — it must
    never land a trade_sent row."""
    c, token = client
    with patch.object(mfl_write, "propose_trade", MagicMock()):
        r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body(
            give_player_ids=[SLEEPER_GIVE, "9999_no_such_player"]))
    assert r.status_code == 422
    assert _trade_sent_rows() == []


def test_mfl_only_user_verifies_via_auth_link_then_proposes(client):
    """Operator decision 2026-08-11: a successful MFL login (#177 auth-link)
    IS session verification, so an MFL-only user — never verified via
    Sleeper/Apple/Google — passes the propose-mfl hard gate."""
    import backend.mfl_service as mfl
    c, token = client
    with server._sessions_lock:
        server._sessions[token].pop("verified", None)
    # Unverified session: the hard gate denies.
    r = c.post("/api/trades/propose-mfl", headers=_h(token), data=_propose_body())
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"
    # MFL sign-in (patched login — no network), then the same propose passes.
    with patch.object(server, "is_enabled",
                      lambda k: k in ("trade.send_in_mfl", "mfl.auth_link")), \
         patch.object(mfl, "login",
                      lambda u, p, y, **kw: {"cookie": "MFL_USER_ID=abc123",
                                             "mfl_user_id": "abc123"}), \
         patch.object(mfl, "fetch_my_leagues", lambda cookie, year, **kw: []):
        r = c.post("/api/mfl/auth-link", headers=_h(token), data=json.dumps(
            {"username": "mattm", "password": "pw", "year": 2026}))
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["verified"] is True
        fake = MagicMock(return_value={"status": "OK", "raw": ""})
        with patch.object(mfl_write, "propose_trade", fake):
            r = c.post("/api/trades/propose-mfl", headers=_h(token),
                       data=_propose_body())
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == "proposed"


# ---------------------------------------------------------------------------
# POST /api/trades/validate — MFL branch (#180 parity, advisory)
# ---------------------------------------------------------------------------

_ROSTERS_EXPORT = {"rosters": {"franchise": [
    {"id": MY_FID, "player": [{"id": MFL_GIVE}]},
    {"id": THEIR_FID, "player": [{"id": MFL_RECV}]},
]}}


def test_validate_mfl_clean_trade_no_warnings(client):
    c, token = client
    import backend.mfl_service as mfl_service
    with patch.object(mfl_service, "fetch_rosters",
                      MagicMock(return_value=_ROSTERS_EXPORT)):
        r = c.post("/api/trades/validate", headers=_h(token), data=_propose_body())
    body = r.get_json()
    assert r.status_code == 200 and body["checked"] is True
    assert body["warnings"] == []


def test_validate_mfl_flags_moved_player(client):
    c, token = client
    import backend.mfl_service as mfl_service
    moved = {"rosters": {"franchise": [
        {"id": MY_FID, "player": []},            # my give-side player is gone
        {"id": THEIR_FID, "player": [{"id": MFL_RECV}]},
    ]}}
    with patch.object(mfl_service, "fetch_rosters",
                      MagicMock(return_value=moved)):
        r = c.post("/api/trades/validate", headers=_h(token), data=_propose_body())
    warnings = r.get_json()["warnings"]
    assert [w["code"] for w in warnings] == ["player_moved"]
    assert warnings[0]["severity"] == "blocking"


def test_validate_mfl_flags_unmapped_asset(client):
    c, token = client
    import backend.mfl_service as mfl_service
    with patch.object(mfl_service, "fetch_rosters",
                      MagicMock(return_value=_ROSTERS_EXPORT)):
        r = c.post("/api/trades/validate", headers=_h(token), data=_propose_body(
            give_player_ids=[SLEEPER_GIVE, "9999_no_such_player"]))
    codes = [w["code"] for w in r.get_json()["warnings"]]
    assert "asset_unmapped" in codes


def test_validate_mfl_snapshot_pick_passes_clean(client):
    """A pick present in the snapshot and owned by the expected side raises
    no findings (it is skipped by the roster/player checks)."""
    c, token = client
    import backend.mfl_service as mfl_service
    with patch.object(mfl_service, "fetch_rosters",
                      MagicMock(return_value=_ROSTERS_EXPORT)):
        r = c.post("/api/trades/validate", headers=_h(token), data=_propose_body(
            give_player_ids=[SLEEPER_GIVE, MY_PICK],
            receive_player_ids=[SLEEPER_RECV, THEIR_PICK]))
    body = r.get_json()
    assert r.status_code == 200 and body["checked"] is True
    assert body["warnings"] == []


def test_validate_mfl_flags_unknown_pick(client):
    """Advisory mirror of the pick hard block: a pick outside the snapshot
    surfaces as asset_unmapped before the user hits the 422."""
    c, token = client
    import backend.mfl_service as mfl_service
    with patch.object(mfl_service, "fetch_rosters",
                      MagicMock(return_value=_ROSTERS_EXPORT)):
        r = c.post("/api/trades/validate", headers=_h(token), data=_propose_body(
            give_player_ids=[SLEEPER_GIVE, f"{LEAGUE}_2030_1_{MY_FID}"]))
    codes = [w["code"] for w in r.get_json()["warnings"]]
    assert "asset_unmapped" in codes


def test_validate_mfl_flags_pick_owned_by_wrong_franchise(client):
    """Pick twin of player_moved: the snapshot says THEIR franchise owns the
    2028 2nd, so offering it from MY side flags pick_moved (blocking)."""
    c, token = client
    import backend.mfl_service as mfl_service
    with patch.object(mfl_service, "fetch_rosters",
                      MagicMock(return_value=_ROSTERS_EXPORT)):
        r = c.post("/api/trades/validate", headers=_h(token), data=_propose_body(
            give_player_ids=[SLEEPER_GIVE, THEIR_PICK]))
    warnings = r.get_json()["warnings"]
    assert [w["code"] for w in warnings] == ["pick_moved"]
    assert warnings[0]["severity"] == "blocking"


def test_validate_mfl_unreachable_degrades_to_unchecked(client):
    c, token = client
    import backend.mfl_service as mfl_service
    with patch.object(mfl_service, "fetch_rosters", MagicMock(return_value={})):
        r = c.post("/api/trades/validate", headers=_h(token), data=_propose_body())
    body = r.get_json()
    assert body["ok"] is True and body["checked"] is False
    assert body["warnings"] == []
