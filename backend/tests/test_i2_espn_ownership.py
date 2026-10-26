"""I-2 (3/4): ESPN send-time player ownership, validate routing, and NEXT.md 0f.

PRD: docs/plans/trade-time-to-suggestion/prd.md §5.3 I-2 (platforms-pm R1: the
ESPN send "already fetches the live league with view=mRoster … no new platform
call") and AC-6a. Stacked on I-2 PRs 1–2 (#411, #412) for the shared
`_ownership_refusal` / `_roster_read_failed_copy`.

  * `_espn_propose_core` (POST /api/trades/propose-espn and the team-overhaul
    send) checks give/receive players against the mRoster read it already
    makes, before any provider write → 422 `asset_not_owned` /
    `counterparty_asset_not_owned`. Picks stay blanket-refused
    (`espn_pick_unsupported`).
  * R3: a failed mRoster read → 502 `espn_unavailable`, `kind: "network"`
    (the core's existing read-failure code; SendInEspnButton shows it via its
    catch-all, while `espn_write_failed` would read "ESPN rejected the request").
  * `/api/trades/validate` on an ESPN league checks ESPN's live roster and
    never calls Sleeper. Any other linked-platform id → `checked:false`, also
    without a Sleeper call (G-014 / G-030).
  * NEXT.md 0f: `_sleeper_propose_core` refuses a linked-platform league id
    (400 `bad_request`, prd-p0-6 §6.2) before any Sleeper call.

No network: `espn_service.fetch_league` and `espn_write.propose_trade` are
mocks; the Sleeper reads are mocks asserted never called.
"""
import copy
import http.client
import json
import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import insert

import backend.database as db_module
import backend.espn_service as espn_service
import backend.espn_write as espn_write
import backend.server as server
from backend import overhaul_api
from backend.espn_service import EspnError
from backend.tests import test_espn_propose_route as espn_t
from backend.tests import test_overhaul_api as ovh_t
from backend.tests import test_sleeper_write_route as propose_t

LEAGUE, MY_TEAM, THEIR_TEAM = espn_t.LEAGUE, espn_t.MY_TEAM, espn_t.THEIR_TEAM
GIVE, RECV = espn_t.SLEEPER_GIVE, espn_t.SLEEPER_RECV
ESPN_GIVE, ESPN_RECV = espn_t.ESPN_GIVE, espn_t.ESPN_RECV
_h = espn_t._h

TAIL = ", so nothing was sent. Find a new trade."
R3_COPY = ("Couldn’t confirm rosters with ESPN right now, so nothing was sent. "
           "Try again in a moment.")


@pytest.fixture()
def client(monkeypatch):
    yield from espn_t.client.__wrapped__(monkeypatch)


def _raw(*, mine=None, theirs=None, ir_on_mine=False):
    raw = copy.deepcopy(espn_t.RAW_LEAGUE)
    if mine is not None:
        raw["teams"][0]["roster"]["entries"] = mine
    if theirs is not None:
        raw["teams"][1]["roster"]["entries"] = theirs
    if ir_on_mine:
        raw["teams"][0]["roster"]["entries"][0]["lineupSlotId"] = 21     # IR
    return raw


def _send(client, *, raw=None, fetch=None, give=(GIVE,), receive=(RECV,)):
    c, token = client
    fake = MagicMock(return_value={"transaction_id": "tx-1", "status": "PENDING", "raw": {}})
    fetch = fetch or MagicMock(return_value=raw if raw is not None else _raw())
    with patch.object(espn_service, "fetch_league", fetch), \
         patch.object(espn_write, "propose_trade", fake):
        r = c.post("/api/trades/propose-espn", headers=_h(token), data=json.dumps({
            "league_id": LEAGUE, "their_user_id": espn_t.THEIR_MEMBER,
            "give_player_ids": list(give), "receive_player_ids": list(receive)}))
    return r, fake


def _name(pid, full_name):
    with db_module.engine.begin() as conn:
        conn.execute(insert(db_module.players_table).values(player_id=pid, full_name=full_name))


# ---------------------------------------------------------------------------
# Send: 422 refusals
# ---------------------------------------------------------------------------

def test_moved_give_player_refuses_before_the_provider(client):
    _name(GIVE, "Tez Johnson")
    r, fake = _send(client, raw=_raw(mine=[]))
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "asset_not_owned" and body["assets"] == [GIVE]
    assert body["message"] == "Tez Johnson is no longer on your roster" + TAIL
    assert body["detail"] == body["message"]
    fake.assert_not_called()


def test_moved_receive_player_names_the_live_team(client):
    _name(RECV, "Rachaad White")
    r, fake = _send(client, raw=_raw(theirs=[]))
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "counterparty_asset_not_owned" and body["assets"] == [RECV]
    assert body["message"] == "Rachaad White is no longer on Their Team’s roster" + TAIL
    assert body["detail"] == body["message"]
    fake.assert_not_called()


def test_unnamed_moved_player_is_counted_never_shown_by_id(client):
    r, fake = _send(client, raw=_raw(theirs=[]))
    body = r.get_json()
    assert body["message"] == "A player in this trade is no longer on Their Team’s roster" + TAIL
    assert RECV not in body["message"] and str(ESPN_RECV) not in body["message"]
    fake.assert_not_called()


def test_ir_player_counts_as_owned(client):
    r, fake = _send(client, raw=_raw(ir_on_mine=True))
    assert r.status_code == 200, r.get_data(as_text=True)
    fake.assert_called_once()


def test_everything_owned_reaches_the_provider(client):
    r, fake = _send(client)
    assert r.status_code == 200, r.get_data(as_text=True)
    (_, _, req), _ = fake.call_args
    assert req.give_espn_player_ids == [ESPN_GIVE] and req.receive_espn_player_ids == [ESPN_RECV]


# ---------------------------------------------------------------------------
# Send: R3
# ---------------------------------------------------------------------------

def _no_roster_object(raw):
    raw["teams"][1].pop("roster")
    return raw


@pytest.mark.parametrize("fetch", [
    lambda: MagicMock(side_effect=EspnError("ESPN HTTP 503", kind="http")),
    lambda: MagicMock(side_effect=EspnError("ESPN returned non-JSON", kind="parse")),
    lambda: MagicMock(side_effect=urllib.error.URLError(TimeoutError("timed out"))),
    lambda: MagicMock(return_value=["not", "a", "league"]),
    lambda: MagicMock(return_value={"messages": ["Service unavailable"]}),
    lambda: MagicMock(return_value=_no_roster_object(_raw())),
], ids=["http", "parse", "urlerror", "non_dict", "no_teams", "team_without_roster"])
def test_failed_mroster_read_blocks_with_readable_502(client, fetch):
    r, fake = _send(client, fetch=fetch())
    assert r.status_code == 502, r.get_data(as_text=True)
    assert r.get_json() == {"error": "espn_unavailable", "kind": "network",
                            "message": R3_COPY, "detail": R3_COPY}
    fake.assert_not_called()


@pytest.mark.parametrize("exc", [
    lambda: http.client.IncompleteRead(b'{"teams"'),
    lambda: http.client.BadStatusLine("garbage"),
    lambda: http.client.RemoteDisconnected("Remote end closed connection"),
    lambda: UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "invalid start byte"),
], ids=["incomplete_read", "bad_status_line", "remote_disconnected", "non_utf8_body"])
def test_unwrapped_read_failures_are_a_readable_502_not_a_500(client, exc):
    """P3: `fetch_league` wraps only HTTPError and bad JSON. An
    `http.client.HTTPException` or a body that isn't UTF-8 escaped as a 500."""
    r, fake = _send(client, fetch=MagicMock(side_effect=exc()))
    assert r.status_code == 502, r.get_data(as_text=True)
    assert r.get_json() == {"error": "espn_unavailable", "kind": "network",
                            "message": R3_COPY, "detail": R3_COPY}
    fake.assert_not_called()


def test_league_not_found_keeps_its_own_code(client):
    r, fake = _send(client, fetch=MagicMock(side_effect=EspnError("gone", kind="not_found")))
    assert r.status_code == 404 and r.get_json()["error"] == "espn_league_not_found"
    fake.assert_not_called()


# ---------------------------------------------------------------------------
# /api/trades/validate on an ESPN league: ESPN's live roster, never Sleeper
# ---------------------------------------------------------------------------

def _validate(client, *, raw=None, fetch=None, flags=("trade.send_in_sleeper", "espn.send"), **over):
    c, token = client
    sleeper_get = MagicMock(side_effect=AssertionError("Sleeper must not be called"))
    meta = MagicMock(side_effect=AssertionError("Sleeper must not be called"))
    fetch = fetch or MagicMock(return_value=raw if raw is not None else _raw())
    body = {"league_id": LEAGUE, "their_user_id": espn_t.THEIR_MEMBER,
            "give_player_ids": [GIVE], "receive_player_ids": [RECV], **over}
    with patch.object(server, "is_enabled", lambda k: k in flags), \
         patch.object(server, "_sleeper_get", sleeper_get), \
         patch.object(server, "_fetch_sleeper_league_meta", meta), \
         patch.object(espn_service, "fetch_league", fetch):
        r = c.post("/api/trades/validate", headers=_h(token), data=json.dumps(body))
    sleeper_get.assert_not_called()
    meta.assert_not_called()
    return r


def test_validate_espn_clean_trade_checks_live_roster(client):
    r = _validate(client)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json() == {"ok": True, "checked": True, "warnings": []}


def test_validate_espn_moved_player_warns(client):
    r = _validate(client, raw=_raw(theirs=[]))
    body = r.get_json()
    assert body["checked"] is True
    assert [w["code"] for w in body["warnings"]] == ["player_moved"]
    assert "ESPN will reject the offer" in body["warnings"][0]["message"]


def test_validate_espn_unknown_team_warns_roster_not_found(client):
    r = _validate(client, their_user_id=f"espn:{LEAGUE}.t99")
    assert [w["code"] for w in r.get_json()["warnings"]] == ["roster_not_found"]


def test_validate_espn_unreachable_reports_nothing_checked(client):
    r = _validate(client, fetch=MagicMock(side_effect=EspnError("down", kind="http")))
    assert r.get_json() == {"ok": True, "checked": False, "warnings": []}


def test_validate_other_linked_platform_never_reaches_sleeper(client):
    # espn.send off: the ESPN branch is skipped, and the linked-platform guard
    # still keeps the id away from Sleeper.
    fetch = MagicMock(side_effect=AssertionError("no ESPN read either"))
    r = _validate(client, fetch=fetch, flags=("trade.send_in_sleeper",))
    assert r.get_json() == {"ok": True, "checked": False, "warnings": []}
    fetch.assert_not_called()


# ---------------------------------------------------------------------------
# NEXT.md 0f: a linked-platform id never reaches Sleeper through the propose core
# ---------------------------------------------------------------------------

@pytest.fixture()
def sleeper_client(monkeypatch):
    yield from propose_t.client.__wrapped__(monkeypatch)


@pytest.mark.parametrize("platform", ["mfl", "espn"])
def test_sleeper_core_refuses_a_linked_platform_league(sleeper_client, platform):
    c, token = sleeper_client
    c.post("/api/sleeper/link", headers=propose_t._h(token),
           data=json.dumps({"token": propose_t._token()}))
    if platform == "mfl":
        db_module.upsert_platform_league(
            league_id=propose_t.LEAGUE, user_id=propose_t.USER, name="M", platform="mfl",
            season=2026, auth="public", my_team="0001", total_rosters=12)
    else:
        db_module.upsert_espn_league(
            league_id=propose_t.LEAGUE, user_id=propose_t.USER, name="E", espn_season=2026,
            espn_auth="public", espn_my_team_id=1, total_rosters=12)
    sleeper_get, fake = MagicMock(return_value=propose_t.ROSTERS_1V2), MagicMock()
    with patch.object(server, "_sleeper_get", sleeper_get), \
         patch.object(server._sleeper_write, "propose_trade", fake):
        r = c.post("/api/trades/propose", headers=propose_t._h(token), data=json.dumps({
            "league_id": propose_t.LEAGUE, "their_roster_id": 2,
            "give_player_ids": ["100"], "receive_player_ids": ["200"]}))
    msg = "This league isn't on Sleeper, so it can't be sent there."
    assert r.status_code == 400
    assert r.get_json() == {"error": "bad_request", "message": msg, "detail": msg}
    sleeper_get.assert_not_called()
    fake.assert_not_called()


# ---------------------------------------------------------------------------
# Through the team-overhaul send: send_core → the REAL _espn_propose_core
# ---------------------------------------------------------------------------

TEAM_OF = {"o1": 2, "o2": 3, "o3": 4, "o4": 5, "o5": 6}


def _syn(team_id):
    return f"espn:{LEAGUE}.t{team_id}"


@pytest.fixture()
def overhaul(monkeypatch):
    """test_overhaul_api's harness on an ESPN league with its fake ESPN core
    swapped for the real one. Counterparties are synthetic `espn:{L}.t{N}`
    member ids (the core resolves them against the live teams), and the
    league id is numeric. The overhaul's own roster read keeps the old
    rosters, so its receipt passes and only the core's live read sees the move."""
    real_install = overhaul_api.install

    def install(app, **kw):
        kw["espn_propose"] = server._espn_propose_core
        return real_install(app, **kw)

    monkeypatch.setattr(overhaul_api, "install", install)
    monkeypatch.setattr(ovh_t, "LEAGUE", LEAGUE)
    monkeypatch.setattr(ovh_t._League, "league_id", LEAGUE)
    monkeypatch.setattr(ovh_t, "OPPONENTS", {_syn(TEAM_OF[o]): r for o, r in ovh_t.OPPONENTS.items()})
    players = ["A", "B", "C", "D", "E", "F", "X1", "X2", "X3", "X4", "X5"]
    espn_id = {p: 30000 + i for i, p in enumerate(players)}
    monkeypatch.setattr(server, "_shared_crosswalk",
                        lambda: SimpleNamespace(by_espn_id={str(e): p for p, e in espn_id.items()}))
    monkeypatch.setattr(server, "_espn_reverse_xwalk_cache", None)
    monkeypatch.setattr(db_module, "get_espn_credential",
                        lambda uid: {"swid": "{S}", "espn_s2_encrypted": "ct"})
    monkeypatch.setattr(server._sleeper_write, "decrypt_token", lambda ct: "s2")
    fake = MagicMock(return_value={"transaction_id": "tx-o", "status": "PENDING", "raw": {}})
    monkeypatch.setattr(espn_write, "propose_trade", fake)
    live = {}
    monkeypatch.setattr(espn_service, "fetch_league", lambda *a, **kw: live["raw"])
    world = ovh_t.World()
    world.platform = "espn"
    world.script = {k: [(g, r, _syn(TEAM_OF[cp])) for g, r, cp in v] for k, v in world.script.items()}
    for c in ovh_t.api.__wrapped__(world):
        db_module.upsert_espn_league(
            league_id=LEAGUE, user_id=ovh_t.USER, name="QA ESPN", espn_season=2026,
            espn_auth="cookie", espn_my_team_id=1, total_rosters=6)
        yield c, world, live, fake, espn_id


def test_overhaul_send_inherits_the_espn_refusal(overhaul):
    c, world, live, fake, espn_id = overhaul
    oid, rm, prep = ovh_t._tie_then_prepare(c, world)
    # Between prepare and send: A leaves my live roster, X3 leaves team 4's.
    tid_of = {ovh_t.USER: 1, **{_syn(t): t for t in TEAM_OF.values()}}
    names = {1: "My Squad", 4: "Third Team"}
    teams = []
    for owner, roster in world.rosters.items():
        tid = tid_of[owner]
        keep = [p for p in roster if p not in ("A", "X3")]
        teams.append({"id": tid, "name": names.get(tid, f"Team {tid}"),
                      "roster": {"entries": [{"lineupSlotId": 20, "playerPoolEntry": {
                          "player": {"id": espn_id[p], "fullName": p}}} for p in keep]}})
    live["raw"] = {"id": int(LEAGUE), "scoringPeriodId": 0, "settings": {"size": 6},
                   "members": [], "teams": teams}
    r = c.post(f"/api/overhauls/{oid}/send", headers=ovh_t._h(), json={
        "prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"],
        "version": rm["version"], "idempotency_key": "i2-espn"})
    assert r.status_code == 200, r.get_json()
    give_of = {p["package_id"]: p["give_ids"][0] for p in rm["packages"]}
    by_give = {}
    for a in r.get_json()["attempts"]:
        by_give.setdefault(give_of[a["package_id"]], []).append(a)
    assert [a["state"] for a in by_give["A"]] == ["send_failed", "send_failed"]   # the tie
    for a in by_give["A"]:
        assert a["error"] == {"code": "asset_not_owned",
                              "message": "A player in this trade is no longer on your roster" + TAIL}
    assert [a["error"] for a in by_give["B"]] == [
        {"code": "counterparty_asset_not_owned",
         "message": "A player in this trade is no longer on Third Team’s roster" + TAIL}]
    assert [a["state"] for a in by_give["C"] + by_give["D"]] == ["proposed", "proposed"]
    sent = sorted(call[0][2].give_espn_player_ids[0] for call in fake.call_args_list)
    assert sent == sorted([espn_id["C"], espn_id["D"]])          # only the owned offers
