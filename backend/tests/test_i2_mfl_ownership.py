"""I-2 (2/4): MFL send-time player + pick ownership revalidation, plus R3.

PRD: docs/plans/trade-time-to-suggestion/prd.md §5.3 I-2 (platforms-pm R1–R5:
"MFL also checks picks, from `futureDraftPicks`") and AC-6a. Stacked on I-2 PR 1
(#411), whose platform-neutral `_ownership_refusal` / `_roster_read_failed_copy`
this reuses.

`_mfl_propose_core` serves POST /api/trades/propose-mfl AND the team-overhaul
send, which calls the same core. Before any provider write it now checks:

  * players against MFL's live `rosters` export (after the Sleeper→MFL
    crosswalk): give on the caller's franchise, receive on the counterparty's
  * FTF picks against MFL's live `futureDraftPicks` export: the current owner
    must be the offering side. The stored snapshot stays the existence check
    (422 `mfl_asset_unmapped`, unchanged)
  * a moved asset → 422 `asset_not_owned` / `counterparty_asset_not_owned`,
    with the give side reported first, players and picks together
  * a failed read (either export) → 502 `mfl_unavailable`, `kind: "network"`
    (R3). Both fetchers turn any MflError into `{}`, so a missing top-level
    key is the failure signal. `mfl_unavailable` (the core's existing
    read-failure 502) rather than `mfl_write_failed`, because SendInMflButton
    shows the latter as "MFL rejected the request".

No network: the two fetchers (or `_fetch_one` under the real fetchers) are
stubbed and `mfl_write.propose_trade` is a mock.
"""
import http.client
import json
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import insert

import backend.database as db_module
import backend.mfl_service as mfl_service
import backend.mfl_write as mfl_write
import backend.server as server
from backend import overhaul_api
from backend import overhaul_store as store
from backend.tests import test_mfl_propose_route as mfl_t
from backend.tests import test_overhaul_api as ovh_t

LEAGUE, MY_FID, THEIR_FID = mfl_t.LEAGUE, mfl_t.MY_FID, mfl_t.THEIR_FID
THEIR_MEMBER = mfl_t.THEIR_MEMBER
GIVE, RECV = mfl_t.SLEEPER_GIVE, mfl_t.SLEEPER_RECV           # Sleeper-space ids
MFL_GIVE, MFL_RECV = mfl_t.MFL_GIVE, mfl_t.MFL_RECV
GIVE2, MFL_GIVE2 = "4881", "13593"                             # a second give player
MY_PICK, THEIR_PICK = mfl_t.MY_PICK, mfl_t.THEIR_PICK
_h = mfl_t._h

TAIL = ", so nothing was sent. Find a new trade."
R3_COPY = ("Couldn’t confirm rosters with MFL right now, so nothing was sent. "
           "Try again in a moment.")

REAL_FETCH_ROSTERS = mfl_service.fetch_rosters
REAL_FETCH_PICKS = mfl_service.fetch_future_draft_picks


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setitem(mfl_t._FAKE_XWALK.by_mfl_sleeper, MFL_GIVE2, GIVE2)
    yield from mfl_t.client.__wrapped__(monkeypatch)


def _rosters(mine=(MFL_GIVE, MFL_GIVE2), theirs=(MFL_RECV,), *, drop=None):
    fr = [{"id": MY_FID, "player": [{"id": p} for p in mine]},
          {"id": THEIR_FID, "player": [{"id": p} for p in theirs]}]
    return {"rosters": {"franchise": [f for f in fr if f["id"] != drop]}}


def _picks(my_2027_1st_owner=MY_FID, their_2028_2nd_owner=THEIR_FID):
    return {"futureDraftPicks": {"franchise": [
        {"id": my_2027_1st_owner, "futureDraftPick": [
            {"year": "2027", "round": "1", "originalPickFor": THEIR_FID}]},
        {"id": their_2028_2nd_owner, "futureDraftPick": [
            {"year": "2028", "round": "2", "originalPickFor": THEIR_FID}]},
    ]}}


def _send(client, give, receive, *, rosters=None, picks=None):
    """POST /api/trades/propose-mfl with the live exports patched. `rosters`
    / `picks` are export bodies or callables standing in for the fetchers.
    Returns (response, propose_trade mock, fetch_rosters mock, picks mock)."""
    c, token = client
    fake = MagicMock(return_value={"status": "OK", "raw": ""})
    fr = rosters if callable(rosters) else MagicMock(return_value=rosters or _rosters())
    fp = picks if callable(picks) else MagicMock(return_value=picks or _picks())
    with patch.object(mfl_write, "propose_trade", fake), \
         patch.object(mfl_service, "fetch_rosters", fr), \
         patch.object(mfl_service, "fetch_future_draft_picks", fp):
        r = c.post("/api/trades/propose-mfl", headers=_h(token), data=json.dumps({
            "league_id": LEAGUE, "their_user_id": THEIR_MEMBER,
            "give_player_ids": give, "receive_player_ids": receive}))
    return r, fake, fr, fp


def _name(pid, full_name):
    with db_module.engine.begin() as conn:
        conn.execute(insert(db_module.players_table).values(player_id=pid, full_name=full_name))


def _their_team(name):
    db_module.upsert_league_members(LEAGUE, [{"user_id": THEIR_MEMBER, "username": name,
                                              "display_name": name, "player_ids": []}])


def _pick_row(pick_id, season, rnd, owner_fid, orig_fid, orig_name):
    with db_module.engine.begin() as conn:
        conn.execute(insert(db_module.draft_picks_table).values(
            pick_id=pick_id, league_id=LEAGUE, season=season, round=rnd,
            owner_user_id=f"mfl:{LEAGUE}.f{owner_fid}", original_roster_id=orig_fid,
            original_user_id=f"mfl:{LEAGUE}.f{orig_fid}", original_username=orig_name,
            is_traded=int(owner_fid != orig_fid), platform="mfl"))


def _no_raw_ids(body):
    assert body["assets"]
    assert not any(a in body["message"] for a in body["assets"]), body["message"]
    assert "FP_" not in body["message"]
    assert body["detail"] == body["message"]


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

def test_moved_give_player_refuses_before_the_provider(client):
    _name(GIVE, "Christian McCaffrey")
    r, fake, fr, fp = _send(client, [GIVE], [RECV], rosters=_rosters(mine=(MFL_GIVE2,)))
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "asset_not_owned" and body["assets"] == [GIVE]
    assert body["message"] == "Christian McCaffrey is no longer on your roster" + TAIL
    _no_raw_ids(body)
    fake.assert_not_called()
    fr.assert_called_once()
    fp.assert_not_called()                         # player-only send: no picks read


def test_moved_receive_player_names_the_team(client):
    _name(RECV, "Jaylen Waddle")
    _their_team("Dolphins Den")
    r, fake, _, _ = _send(client, [GIVE], [RECV], rosters=_rosters(theirs=()))
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "counterparty_asset_not_owned" and body["assets"] == [RECV]
    assert body["message"] == "Jaylen Waddle is no longer on Dolphins Den’s roster" + TAIL
    _no_raw_ids(body)
    fake.assert_not_called()


def test_unnamed_moved_players_are_counted_never_shown_by_id(client):
    r, fake, _, _ = _send(client, [GIVE, GIVE2], [RECV], rosters=_rosters(mine=()))
    body = r.get_json()
    assert r.status_code == 422 and body["assets"] == [GIVE, GIVE2]
    assert body["message"] == "2 players in this trade are no longer on your roster" + TAIL
    _no_raw_ids(body)
    fake.assert_not_called()


# ---------------------------------------------------------------------------
# Picks (live futureDraftPicks owner)
# ---------------------------------------------------------------------------

def test_moved_give_pick_refuses_with_its_label(client):
    _their_team("Dolphins Den")
    _pick_row(MY_PICK, 2027, 1, MY_FID, THEIR_FID, "Dolphins Den")
    r, fake, fr, fp = _send(client, [GIVE, MY_PICK], [RECV],
                            picks=_picks(my_2027_1st_owner="0007"))
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "asset_not_owned" and body["assets"] == [MY_PICK]
    assert body["message"] == "2027 1st (from Dolphins Den) is no longer on your roster" + TAIL
    _no_raw_ids(body)
    fake.assert_not_called()
    fp.assert_called_once()


def test_moved_receive_pick_refuses_with_its_label(client):
    _their_team("Dolphins Den")
    _pick_row(THEIR_PICK, 2028, 2, THEIR_FID, THEIR_FID, "Dolphins Den")
    r, fake, _, _ = _send(client, [GIVE], [RECV, THEIR_PICK],
                          picks=_picks(their_2028_2nd_owner="0009"))
    assert r.status_code == 422, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "counterparty_asset_not_owned" and body["assets"] == [THEIR_PICK]
    assert body["message"] == "2028 2nd is no longer on Dolphins Den’s roster" + TAIL
    _no_raw_ids(body)
    fake.assert_not_called()


def test_unlabeled_moved_pick_is_counted_never_shown_by_id(client):
    # No draft_picks row, so no label: the count fallback, never the pick id.
    # It says "pick", not "player" (I-2 follow-up; placeholder copy).
    r, fake, _, _ = _send(client, [GIVE], [RECV, THEIR_PICK],
                          picks=_picks(their_2028_2nd_owner="0009"))
    body = r.get_json()
    assert r.status_code == 422 and body["assets"] == [THEIR_PICK]
    assert body["message"] == (
        "A pick in this trade is no longer on the other manager’s roster" + TAIL)
    _no_raw_ids(body)
    fake.assert_not_called()


def test_unnamed_moved_player_and_pick_are_counted_as_assets(client):
    # Both moved, neither has a name on file: "assets", not "players" or "picks"
    # (I-2 follow-up; placeholder copy). Give side, players and picks together.
    r, fake, _, _ = _send(client, [GIVE, MY_PICK], [RECV],
                          rosters=_rosters(mine=(MFL_GIVE2,)),
                          picks=_picks(my_2027_1st_owner="0007"))
    body = r.get_json()
    assert r.status_code == 422 and set(body["assets"]) == {GIVE, MY_PICK}
    assert body["message"] == "2 assets in this trade are no longer on your roster" + TAIL
    _no_raw_ids(body)
    fake.assert_not_called()


def test_pick_dropped_from_the_live_export_counts_as_moved(client):
    # MFL drops a season's picks once that draft is held: nobody owns it live.
    gone = {"futureDraftPicks": {"franchise": [{"id": THEIR_FID, "futureDraftPick": [
        {"year": "2028", "round": "2", "originalPickFor": THEIR_FID}]}]}}
    r, fake, _, _ = _send(client, [GIVE, MY_PICK], [RECV], picks=gone)
    assert r.status_code == 422 and r.get_json()["error"] == "asset_not_owned"
    fake.assert_not_called()


def test_give_side_is_reported_first_across_players_and_picks(client):
    r, fake, _, _ = _send(client, [GIVE, MY_PICK], [RECV],
                          rosters=_rosters(theirs=()), picks=_picks(my_2027_1st_owner="0007"))
    body = r.get_json()
    assert r.status_code == 422
    assert body["error"] == "asset_not_owned" and body["assets"] == [MY_PICK]
    fake.assert_not_called()


# ---------------------------------------------------------------------------
# Everything owned → the provider
# ---------------------------------------------------------------------------

def test_everything_owned_reaches_the_provider(client):
    r, fake, fr, fp = _send(client, [GIVE, MY_PICK], [RECV, THEIR_PICK])
    assert r.status_code == 200, r.get_data(as_text=True)
    (_, _, _, req), _ = fake.call_args
    assert req.will_give_up == [MFL_GIVE, f"FP_{THEIR_FID}_2027_1"]
    assert req.will_receive == [MFL_RECV, f"FP_{THEIR_FID}_2028_2"]
    fr.assert_called_once()
    fp.assert_called_once()


# ---------------------------------------------------------------------------
# R3: a failed read blocks the send; a successful read without my franchise
# keeps the existing code
# ---------------------------------------------------------------------------

def _mfl_down(*a, **k):
    raise mfl_service.MflError("MFL HTTP 503", kind="http")


@pytest.mark.parametrize("which", ["rosters", "picks"])
@pytest.mark.parametrize("failure", ["mfl_error", "non_export_body"])
def test_failed_live_read_blocks_with_readable_502(client, which, failure):
    """Runs the REAL best-effort fetchers over a failing `_fetch_one`, so the
    `{}` they degrade to is what the core sees."""
    one = (MagicMock(side_effect=_mfl_down) if failure == "mfl_error"
           else MagicMock(return_value={"error": {"$t": "League is private"}}))
    ok_rosters, ok_picks = MagicMock(return_value=_rosters()), MagicMock(return_value=_picks())
    with patch.object(mfl_service, "_fetch_one", one):
        r, fake, _, _ = _send(
            client, [GIVE, MY_PICK], [RECV],
            rosters=REAL_FETCH_ROSTERS if which == "rosters" else ok_rosters,
            picks=REAL_FETCH_PICKS if which == "picks" else ok_picks)
    assert r.status_code == 502, r.get_data(as_text=True)
    assert r.get_json() == {"error": "mfl_unavailable", "kind": "network",
                            "message": R3_COPY, "detail": R3_COPY}
    one.assert_called_once()
    fake.assert_not_called()


@pytest.mark.parametrize("which", ["rosters", "picks"])
def test_dead_cookie_on_the_ownership_read_routes_to_sign_in(client, which):
    """P2-2: a private league's export 401/403s on a dead cookie. That is the
    sign-in expiring, not R3's flake: the same 409 `mfl_auth_expired` the write
    path returns (credential dropped, so the client re-prompts sign-in), never
    the "Try again in a moment" 502. Runs the REAL fetchers over `_fetch_one`."""
    assert db_module.get_mfl_credential(mfl_t.USER) is not None
    one = MagicMock(side_effect=mfl_service.MflAuthError())
    ok_rosters, ok_picks = MagicMock(return_value=_rosters()), MagicMock(return_value=_picks())
    with patch.object(mfl_service, "_fetch_one", one):
        r, fake, _, _ = _send(
            client, [GIVE, MY_PICK], [RECV],
            rosters=REAL_FETCH_ROSTERS if which == "rosters" else ok_rosters,
            picks=REAL_FETCH_PICKS if which == "picks" else ok_picks)
    assert r.status_code == 409, r.get_data(as_text=True)
    body = r.get_json()
    assert body["error"] == "mfl_auth_expired"
    assert body["message"] == "Your MFL sign-in expired — sign in again."
    fake.assert_not_called()
    assert db_module.get_mfl_credential(mfl_t.USER) is None     # dropped, as on the write path


TRANSPORT_ERRORS = [
    lambda: socket.timeout("timed out"),
    lambda: ConnectionResetError(104, "Connection reset by peer"),
    lambda: http.client.IncompleteRead(b"{\"rosters\""),
    lambda: http.client.BadStatusLine("garbage"),
]


@pytest.mark.parametrize("which", ["rosters", "picks"])
@pytest.mark.parametrize("exc", TRANSPORT_ERRORS,
                         ids=["timeout", "conn_reset", "incomplete_read", "bad_status_line"])
def test_transport_error_on_the_ownership_read_is_a_readable_502(client, which, exc):
    """P2-1: `_fetch_one` wraps only HTTPError / URLError / bad JSON, so these
    escape the REAL fetchers. The core turns them into R3's 502, never a 500."""
    one = MagicMock(side_effect=exc())
    ok_rosters, ok_picks = MagicMock(return_value=_rosters()), MagicMock(return_value=_picks())
    with patch.object(mfl_service, "_fetch_one", one):
        r, fake, _, _ = _send(
            client, [GIVE, MY_PICK], [RECV],
            rosters=REAL_FETCH_ROSTERS if which == "rosters" else ok_rosters,
            picks=REAL_FETCH_PICKS if which == "picks" else ok_picks)
    assert r.status_code == 502, r.get_data(as_text=True)
    assert r.get_json() == {"error": "mfl_unavailable", "kind": "network",
                            "message": R3_COPY, "detail": R3_COPY}
    fake.assert_not_called()


def test_other_callers_still_degrade_a_dead_cookie_to_empty():
    """The fetchers' default contract is unchanged: without `raise_auth` an
    MflAuthError is still `{}` (validate, the owned-pick refresher)."""
    with patch.object(mfl_service, "_fetch_one", MagicMock(side_effect=mfl_service.MflAuthError())):
        assert REAL_FETCH_ROSTERS(LEAGUE, 2026, "h") == {}
        assert REAL_FETCH_PICKS(LEAGUE, 2026, "h") == {}


def test_successful_rosters_read_without_my_franchise_keeps_its_code(client):
    r, fake, _, _ = _send(client, [GIVE], [RECV], rosters=_rosters(drop=MY_FID))
    assert r.status_code == 409 and r.get_json()["error"] == "mfl_franchise_unknown"
    fake.assert_not_called()


# ---------------------------------------------------------------------------
# Through the team-overhaul send: send_core → the REAL _mfl_propose_core
# ---------------------------------------------------------------------------

def _syn(fid):
    return f"mfl:{LEAGUE}.f{fid}"


CP = {"o1": "0002", "o2": "0003", "o3": "0004", "o4": "0005", "o5": "0006"}


@pytest.fixture()
def overhaul(monkeypatch):
    """test_overhaul_api's harness on an MFL league, with its fake MFL core
    swapped for the real one. Counterparties are synthetic MFL member ids
    (the core parses the franchise out of them) and the league id is numeric.
    The overhaul's own roster read keeps the old rosters, so its receipt
    passes and only the core's live read sees the move."""
    real_install = overhaul_api.install

    def install(app, **kw):
        kw["mfl_propose"] = server._mfl_propose_core
        return real_install(app, **kw)

    monkeypatch.setattr(overhaul_api, "install", install)
    monkeypatch.setattr(ovh_t, "LEAGUE", LEAGUE)
    monkeypatch.setattr(ovh_t._League, "league_id", LEAGUE)
    monkeypatch.setattr(ovh_t, "OPPONENTS", {_syn(CP[o]): r for o, r in ovh_t.OPPONENTS.items()})
    players = ["A", "B", "C", "D", "E", "F", "X1", "X2", "X3", "X4", "X5"]
    mfl_id = {p: str(20000 + i) for i, p in enumerate(players)}
    monkeypatch.setattr(server, "_shared_crosswalk",
                        lambda: SimpleNamespace(by_mfl_sleeper={m: p for p, m in mfl_id.items()}))
    monkeypatch.setattr(server, "_mfl_reverse_xwalk_cache", None)
    monkeypatch.setattr(server, "_mfl_cookie_for", lambda sess, uid: "MFL_USER_ID=abc")
    fake = MagicMock(return_value={"status": "OK", "raw": ""})
    monkeypatch.setattr(mfl_write, "propose_trade", fake)
    live = {}
    monkeypatch.setattr(mfl_service, "fetch_rosters",
                        lambda league_id, year, host, cookie=None, **kw: live["rosters"])
    world = ovh_t.World()
    world.platform = "mfl"
    world.script = {k: [(g, r, _syn(CP[cp])) for g, r, cp in v] for k, v in world.script.items()}
    for c in ovh_t.api.__wrapped__(world):
        db_module.upsert_platform_league(
            league_id=LEAGUE, user_id=ovh_t.USER, name="QA MFL", platform="mfl",
            season=2026, auth="cookie", my_team="0001", total_rosters=6,
            host="www76.myfantasyleague.com", future_picks=[])
        db_module.upsert_league_members(LEAGUE, [{"user_id": _syn("0004"), "username": "Third Team",
                                                  "display_name": "Third Team", "player_ids": []}])
        yield c, world, live, fake, mfl_id


def test_overhaul_send_inherits_the_mfl_refusal(overhaul):
    c, world, live, fake, mfl_id = overhaul
    oid, rm, prep = ovh_t._tie_then_prepare(c, world)
    # Between prepare and send: A leaves my live roster, X3 leaves o3's (f0004).
    fid_of = {ovh_t.USER: "0001", **{_syn(f): f for f in CP.values()}}
    franchises = []
    for owner, roster in world.rosters.items():
        keep = [p for p in roster if p not in ("A", "X3")]
        franchises.append({"id": fid_of[owner], "player": [{"id": mfl_id[p]} for p in keep]})
    live["rosters"] = {"rosters": {"franchise": franchises}}
    r = c.post(f"/api/overhauls/{oid}/send", headers=ovh_t._h(), json={
        "prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"],
        "version": rm["version"], "idempotency_key": "i2-mfl"})
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
    sent = sorted(call[0][3].will_give_up[0] for call in fake.call_args_list)
    assert sent == sorted([mfl_id["C"], mfl_id["D"]])          # only the owned offers


def test_overhaul_transport_error_fails_each_offer_readably_and_frees_reservations(overhaul, monkeypatch):
    """P2-1 through the overhaul send: a reset on the live rosters read used to
    escape the core, so each attempt went `outcome_unknown` with its
    reservation held. Now each is `send_failed` with the R3 copy and the
    packages are released."""
    c, world, live, fake, mfl_id = overhaul
    oid, rm, prep = ovh_t._tie_then_prepare(c, world)

    def reset(*a, **kw):
        raise ConnectionResetError(104, "Connection reset by peer")

    monkeypatch.setattr(mfl_service, "fetch_rosters", reset)
    r = c.post(f"/api/overhauls/{oid}/send", headers=ovh_t._h(), json={
        "prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"],
        "version": rm["version"], "idempotency_key": "i2-mfl-reset"})
    assert r.status_code == 200, r.get_json()
    attempts = r.get_json()["attempts"]
    assert [a["state"] for a in attempts] == ["send_failed"] * 5      # never outcome_unknown
    assert {a["error"]["code"] for a in attempts} == {"mfl_unavailable"}
    assert {a["error"]["message"] for a in attempts} == {R3_COPY}
    assert store.active_reservations(LEAGUE, ovh_t.USER) == []        # nothing held
    fake.assert_not_called()
