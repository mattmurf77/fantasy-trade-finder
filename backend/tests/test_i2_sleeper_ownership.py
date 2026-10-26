"""I-2 (1/4): Sleeper send-time player-ownership revalidation, plus R3.

PRD: docs/plans/trade-time-to-suggestion/prd.md §5.3 I-2 (platforms-pm R1–R5)
and AC-6a. Head-eng gave the GO on 2026-10-26; this is the condition of the
operator's 200 ms waiver W-AC-L5.

`_sleeper_propose_core` serves POST /api/trades/propose AND the team-overhaul
send, which calls the same core. It now checks every PLAYER on both sides
against the live rosters read it already makes, before any provider write:

  * a give player off the caller's live roster    → 422 `asset_not_owned`
  * a receive player off the counterparty's roster → 422 `counterparty_asset_not_owned`
  * IR / taxi players are listed in `players`, so they count as owned
  * the rosters READ failing (exception, None or non-list body, the open 429
    circuit) → 502 `sleeper_write_failed`, `kind: "network"` (R3). It used to
    be the misleading 400 `roster_not_found`, which now stays only for a
    SUCCESSFUL read that genuinely lacks the caller's roster.

Players are checked before picks, so a moved player refuses the send without
the pick path's extra reads. No network: `_sleeper_get` (or the unguarded
getter behind the real circuit) is stubbed and `sleeper_write.propose_trade`
is a mock.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import insert

import backend.database as db_module
import backend.server as server
import backend.sleeper_http as sh
from backend import overhaul_api
from backend.tests import test_overhaul_api as ovh_t
from backend.tests import test_sleeper_write_route as propose_t

UID, LEAGUE = propose_t.SLEEPER_UID, propose_t.LEAGUE
_h, _token = propose_t._h, propose_t._token

MINE = {"owner_id": UID, "roster_id": 1, "players": ["100", "101"]}
THEIRS = {"owner_id": "opp", "roster_id": 2, "players": ["200", "201"]}
ROSTERS = [MINE, THEIRS]

TAIL = ", so nothing was sent. Find a new trade."
R3_COPY = ("Couldn't confirm rosters with Sleeper right now, so nothing was sent. "
           "Try again in a moment.")


@pytest.fixture(autouse=True)
def _circuit():
    sh.reset()
    yield
    sh.reset()


@pytest.fixture()
def client(monkeypatch):
    yield from propose_t.client.__wrapped__(monkeypatch)


def _name(pid, full_name):
    with db_module.engine.begin() as conn:
        conn.execute(insert(db_module.players_table).values(player_id=pid, full_name=full_name))


def _send(client, give, receive, *, rosters=ROSTERS, getter=None, their_roster_id=2, arm=None):
    """Link, then POST /api/trades/propose. `getter` stands in for
    `_sleeper_get` (default: it returns `rosters`). `arm` runs after linking,
    e.g. to open the circuit. Pick reads are mocked so a test can show they
    never happen. Returns (response, propose_trade mock, traded_picks mock)."""
    c, token = client
    c.post("/api/sleeper/link", headers=_h(token), data=json.dumps({"token": _token()}))
    if arm is not None:
        arm()
    fake = MagicMock(return_value={"transaction_id": "TX1", "status": "proposed", "raw": {}})
    traded = MagicMock(return_value=propose_t.TRADED)
    body = {"league_id": LEAGUE, "give_player_ids": give, "receive_player_ids": receive}
    if their_roster_id is None:
        body["their_user_id"] = "opp"
    else:
        body["their_roster_id"] = their_roster_id
    with patch.object(server, "_sleeper_get",
                      getter if getter is not None else MagicMock(return_value=rosters)), \
         patch.object(server._sleeper_write, "propose_trade", fake), \
         patch.object(server, "load_draft_picks", MagicMock(return_value=propose_t.GRID)), \
         patch.object(server, "_fetch_sleeper_traded_picks", traded), \
         patch.object(server, "_fetch_sleeper_drafts", MagicMock(return_value=propose_t.DRAFTS_PRE)), \
         patch.object(server, "_fetch_sleeper_league_meta", MagicMock(return_value=propose_t.META)):
        r = c.post("/api/trades/propose", headers=_h(token), data=json.dumps(body))
    return r, fake, traded


# ---------------------------------------------------------------------------
# 422 asset_not_owned / counterparty_asset_not_owned
# ---------------------------------------------------------------------------

def test_give_player_off_my_roster_refuses_before_any_read_or_write(client):
    _name("102", "Josh Allen")
    r, fake, traded = _send(client, ["100", "102", propose_t.MY_2027_2ND], ["200"])
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "asset_not_owned" and body["assets"] == ["102"]
    assert body["message"] == "Josh Allen is no longer on your roster" + TAIL
    assert body["detail"] == body["message"]
    fake.assert_not_called()                       # no GraphQL propose
    traded.assert_not_called()                     # players first: no pick reads


def test_plural_give_refusal_names_every_moved_player(client):
    _name("102", "Josh Allen")
    _name("103", "Bijan Robinson")
    r, fake, _ = _send(client, ["102", "100", "103"], ["200"])
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["assets"] == ["102", "103"]
    assert body["message"] == "Josh Allen and Bijan Robinson are no longer on your roster" + TAIL
    assert body["detail"] == body["message"]
    fake.assert_not_called()


def test_receive_player_off_their_roster_names_the_team(client):
    _name("299", "Puka Nacua")
    db_module.upsert_league_members(LEAGUE, [{"user_id": "opp", "username": "oppy",
                                              "display_name": "Gridiron Gang",
                                              "player_ids": ["200"]}])
    r, fake, traded = _send(client, ["100"], ["200", "299"], their_roster_id=None)
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "counterparty_asset_not_owned" and body["assets"] == ["299"]
    assert body["message"] == "Puka Nacua is no longer on Gridiron Gang's roster" + TAIL
    assert body["detail"] == body["message"]
    fake.assert_not_called()
    traded.assert_not_called()


def test_receive_refusal_falls_back_to_their_roster_and_raw_ids(client):
    # No league_members row and no players_table names: the copy still reads.
    r, fake, _ = _send(client, ["100"], ["299", "298", "297"])
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "counterparty_asset_not_owned"
    assert body["message"] == "299, 298 and 297 are no longer on their roster" + TAIL
    assert body["detail"] == body["message"]
    fake.assert_not_called()


def test_give_side_is_reported_before_receive_side(client):
    r, fake, _ = _send(client, ["102"], ["299"])
    assert r.status_code == 422
    assert r.get_json()["error"] == "asset_not_owned" and r.get_json()["assets"] == ["102"]
    fake.assert_not_called()


def test_ir_and_taxi_players_count_as_owned(client):
    mine = {**MINE, "players": ["100", "150", "160"], "reserve": ["150"], "taxi": ["160"]}
    theirs = {**THEIRS, "players": ["200", "250", "260"], "reserve": ["250"], "taxi": ["260"]}
    r, fake, _ = _send(client, ["150", "160"], ["250", "260"], rosters=[mine, theirs])
    assert r.status_code == 200, r.get_data(as_text=True)
    req = fake.call_args[0][1]
    assert req.give_player_ids == ["150", "160"] and req.receive_player_ids == ["250", "260"]


def test_everything_owned_proceeds_to_the_provider(client):
    r, fake, traded = _send(client, ["100", "101"], ["200"])
    assert r.status_code == 200, r.get_data(as_text=True)
    fake.assert_called_once()
    req = fake.call_args[0][1]
    assert (req.my_roster_id, req.their_roster_id) == (1, 2)
    assert req.give_player_ids == ["100", "101"] and req.receive_player_ids == ["200"]
    traded.assert_not_called()                     # player-only send: no pick reads


def test_owned_players_then_the_pick_checks_still_run(client):
    r, fake, traded = _send(client, ["100", propose_t.MY_2027_2ND], ["200"])
    assert r.status_code == 200, r.get_data(as_text=True)
    traded.assert_called_once()
    assert fake.call_args[0][1].draft_picks == ["1,2027,2,1,2"]


def test_co_owner_passes_at_roster_level(client):
    mine = {"owner_id": "primary", "co_owners": [UID], "roster_id": 1, "players": ["100"]}
    r, fake, _ = _send(client, ["100"], ["200"], rosters=[mine, THEIRS])
    assert r.status_code == 200, r.get_data(as_text=True)
    assert fake.call_args[0][1].my_roster_id == 1


def test_refusal_helper_is_platform_neutral():
    body, status = server._ownership_refusal("give", ["a", "b", "c"], {"a": "Al", "b": "Bo"})
    assert status == 422
    assert body == {"error": "asset_not_owned", "assets": ["a", "b", "c"],
                    "message": "Al, Bo and c are no longer on your roster" + TAIL,
                    "detail": "Al, Bo and c are no longer on your roster" + TAIL}
    body, _ = server._ownership_refusal("receive", ["x"], {}, "Team Z")
    assert body["message"] == "x is no longer on Team Z's roster" + TAIL
    assert server._roster_read_failed_copy("MFL") == (
        "Couldn't confirm rosters with MFL right now, so nothing was sent. Try again in a moment.")


# ---------------------------------------------------------------------------
# R3: a failed rosters READ blocks the send; a successful read without the
# caller's roster stays 400
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("getter", [
    lambda: MagicMock(side_effect=OSError("connection reset")),
    lambda: MagicMock(return_value=None),
    lambda: MagicMock(return_value={"message": "Forbidden"}),
], ids=["raises", "none", "non_list"])
def test_failed_rosters_read_blocks_with_readable_502(client, getter):
    r, fake, _ = _send(client, ["100"], ["200"], getter=getter())
    assert r.status_code == 502, r.get_data(as_text=True)
    assert r.get_json() == {"error": "sleeper_write_failed", "kind": "network",
                            "message": R3_COPY, "detail": R3_COPY}
    fake.assert_not_called()


def test_open_429_circuit_blocks_the_send_without_a_read(client, monkeypatch):
    unguarded = MagicMock(return_value=ROSTERS)    # would succeed if it were read
    monkeypatch.setattr(server, "_sleeper_get_unguarded", unguarded)

    def arm():
        unguarded.reset_mock()
        sh.record_429("60")

    r, fake, _ = _send(client, ["100"], ["200"], getter=server._sleeper_get, arm=arm)
    assert r.status_code == 502, r.get_data(as_text=True)
    assert r.get_json()["kind"] == "network" and r.get_json()["detail"] == R3_COPY
    unguarded.assert_not_called()                  # the real circuit refused the read
    fake.assert_not_called()


@pytest.mark.parametrize("rosters", [[THEIRS], []], ids=["caller_absent", "empty_list"])
def test_successful_read_without_my_roster_stays_400(client, rosters):
    r, fake, _ = _send(client, ["100"], ["200"], rosters=rosters)
    assert r.status_code == 400 and r.get_json() == {"error": "roster_not_found"}
    fake.assert_not_called()


def test_their_roster_id_missing_from_the_read_is_never_sent_unchecked(client):
    r, fake, _ = _send(client, ["100"], ["200"], their_roster_id=9)
    assert r.status_code == 400 and r.get_json() == {"error": "opponent_roster_not_found"}
    fake.assert_not_called()


# ---------------------------------------------------------------------------
# Through the team-overhaul send: send_core → the REAL _sleeper_propose_core
# ---------------------------------------------------------------------------

@pytest.fixture()
def overhaul(monkeypatch):
    """test_overhaul_api's harness with its fake Sleeper core swapped for the
    real one. The league id is numeric because the real core 400s anything
    else; the overhaul's own fetch keeps the old rosters, so its receipt
    passes and only the core's live read sees the move."""
    real_install = overhaul_api.install

    def install(app, **kw):
        kw["sleeper_propose"] = server._sleeper_propose_core
        return real_install(app, **kw)

    monkeypatch.setattr(overhaul_api, "install", install)
    monkeypatch.setattr(ovh_t, "LEAGUE", LEAGUE)
    monkeypatch.setattr(ovh_t._League, "league_id", LEAGUE)
    live = {}
    fake = MagicMock(return_value={"transaction_id": "TXO", "status": "proposed", "raw": {}})
    monkeypatch.setattr(server, "get_sleeper_credential",
                        lambda uid: {"token_encrypted": "ct", "sleeper_user_id": uid})
    monkeypatch.setattr(server._sleeper_write, "decrypt_token", lambda ct: "tok")
    monkeypatch.setattr(server._sleeper_write, "is_expired", lambda tok: False)
    monkeypatch.setattr(server._sleeper_write, "propose_trade", fake)
    monkeypatch.setattr(server, "_fetch_league_rosters", lambda lid: live["rosters"])
    world = ovh_t.World()
    for c in ovh_t.api.__wrapped__(world):
        yield c, world, live, fake


def test_overhaul_send_inherits_the_refusal(overhaul):
    c, world, live, fake = overhaul
    oid, rm, prep = ovh_t._tie_then_prepare(c, world)
    # Between prepare and send: A leaves my live roster, X3 leaves o3's.
    rosters = world.raw_rosters()
    for r in rosters:
        if r["owner_id"] == ovh_t.USER:
            r["players"].remove("A")
        if r["owner_id"] == "o3":
            r["players"].remove("X3")
    live["rosters"] = rosters
    r = c.post(f"/api/overhauls/{oid}/send", headers=ovh_t._h(), json={
        "prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"],
        "version": rm["version"], "idempotency_key": "i2"})
    assert r.status_code == 200, r.get_json()
    give_of = {p["package_id"]: p["give_ids"][0] for p in rm["packages"]}
    by_give = {}
    for a in r.get_json()["attempts"]:
        by_give.setdefault(give_of[a["package_id"]], []).append(a)
    assert [a["state"] for a in by_give["A"]] == ["send_failed", "send_failed"]   # the tie
    for a in by_give["A"]:
        assert a["error"] == {"code": "asset_not_owned",
                              "message": "A is no longer on your roster" + TAIL}
    assert [a["error"] for a in by_give["B"]] == [
        {"code": "counterparty_asset_not_owned", "message": "X3 is no longer on their roster" + TAIL}]
    assert [a["state"] for a in by_give["C"] + by_give["D"]] == ["proposed", "proposed"]
    # Only the two still-owned offers reached the provider.
    assert sorted(call[0][1].give_player_ids[0] for call in fake.call_args_list) == ["C", "D"]
