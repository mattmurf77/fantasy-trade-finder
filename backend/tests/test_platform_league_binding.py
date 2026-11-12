"""Per-user platform-league binding (docs/plans/platform-league-binding/).

Two app users who manage DIFFERENT teams in the same ESPN or MFL league both
link it. Each must keep their own "which team is mine": the second link (or a
re-sync, or the first user's re-link) may refresh the shared league facts but
must never rebind, unlist or un-verify the other user.

Flask test client + isolated in-memory SQLite + injected sessions. No network:
ESPN / MFL payloads are the recorded fixtures patched over the service
fetchers, exactly as test_espn_link_route.py / test_mfl_link_route.py do.
"""
import copy
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.espn_service as es
import backend.espn_write as espn_write
import backend.mfl_service as mfl
import backend.mfl_write as mfl_write
import backend.server as server
from backend.database import metadata

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
ESPN_FIXTURE = os.path.join(FIXTURES, "espn_league_snapshot_2026-07-11.json")
MFL_FIXTURE = os.path.join(FIXTURES, "mfl_league_snapshot_2026-07-17.json")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")

A, B, C = "100000000000000001", "200000000000000002", "300000000000000003"
ESPN_LEAGUE, MFL_LEAGUE = "987654321", "10005"
SWID = {1: "{A1111111-1111-1111-1111-111111111111}",
        2: "{B2222222-2222-2222-2222-222222222222}",
        3: "{C3333333-3333-3333-3333-333333333333}"}
FLAGS = {"espn.link", "mfl.link", "espn.send", "trade.send_in_mfl"}


def _load(path):
    with open(path) as f:
        return json.load(f)


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


@pytest.fixture()
def env(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    server._espn_reverse_xwalk_cache = None
    server._mfl_reverse_xwalk_cache = None
    c = server.app.test_client()
    xwalk = es.load_crosswalk(XWALK_FIXTURE)
    espn_payload, mfl_bundle = _load(ESPN_FIXTURE), _load(MFL_FIXTURE)
    tokens = {}
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in FLAGS), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(es, "get_crosswalk", lambda _opener=None: xwalk), \
         patch.object(es, "fetch_league",
                      lambda *a, **kw: copy.deepcopy(espn_payload)), \
         patch.object(mfl, "resolve_host", lambda *a, **kw: "www48.myfantasyleague.com"), \
         patch.object(mfl, "fetch_league_bundle",
                      lambda *a, **kw: copy.deepcopy(mfl_bundle)), \
         patch.object(mfl, "fetch_rosters",
                      lambda *a, **kw: copy.deepcopy(mfl_bundle["rosters"])):
        with server._sessions_lock:
            for uid in (A, B, C):
                tok = f"bind-tok-{uid}"
                tokens[uid] = tok
                server._sessions[tok] = {"verified": True, "user_id": uid,
                                         "active_format": "1qb_ppr",
                                         "last_active": 0.0}
        try:
            yield SimpleNamespace(c=c, engine=engine, tok=tokens)
        finally:
            with server._sessions_lock:
                for tok in tokens.values():
                    server._sessions.pop(tok, None)
            server._espn_reverse_xwalk_cache = None
            server._mfl_reverse_xwalk_cache = None


def _espn_link(env, uid, team_id):
    return env.c.post("/api/espn/link", headers=_h(env.tok[uid]), data=json.dumps(
        {"espn_league_id": ESPN_LEAGUE, "season": 2026, "team_id": team_id}))


def _espn_import(env, uid):
    return env.c.post("/api/espn/import", headers=_h(env.tok[uid]),
                      data=json.dumps({"league_id": ESPN_LEAGUE}))


def _espn_leagues(env, uid):
    r = env.c.get("/api/espn/leagues", headers=_h(env.tok[uid]))
    assert r.status_code == 200, r.get_data(as_text=True)
    return {lg["league_id"]: lg for lg in r.get_json()["leagues"]}


def _mfl_link(env, uid, fid):
    return env.c.post("/api/mfl/link", headers=_h(env.tok[uid]), data=json.dumps(
        {"mfl_league_id": MFL_LEAGUE, "year": 2026, "franchise_id": fid}))


def _mfl_import(env, uid):
    return env.c.post("/api/mfl/import", headers=_h(env.tok[uid]),
                      data=json.dumps({"league_id": MFL_LEAGUE}))


def _mfl_leagues(env, uid):
    r = env.c.get("/api/mfl/leagues", headers=_h(env.tok[uid]))
    assert r.status_code == 200, r.get_data(as_text=True)
    return {lg["league_id"]: lg for lg in r.get_json()["leagues"]}


def _mine(lg, uid):
    """What the mobile client does (api/espn.ts buildEspnSessionInitBody,
    api/platformLink.ts): `mine` is the member row whose user_id is me."""
    mine = [m for m in lg["members"] if m["user_id"] == uid]
    assert len(mine) == 1, f"{uid} has {len(mine)} member rows"
    return mine[0]


def _espn_roster(team_id):
    """The Sleeper-space roster the importer stores for an ESPN team."""
    payload = _load(ESPN_FIXTURE)
    league = es.parse_league(payload)
    return es.map_rosters(league["teams"], es.get_crosswalk())["rosters"][team_id]


def _mfl_roster(fid):
    parsed = mfl.parse_bundle(_load(MFL_FIXTURE))
    return mfl.map_franchises(parsed, es.get_crosswalk())["rosters"][fid]


def _assert_espn_view(env, uid, team_id):
    lg = _espn_leagues(env, uid).get(ESPN_LEAGUE)
    assert lg is not None, f"ESPN league vanished from {uid}'s league list"
    assert lg["my_team_id"] == team_id
    assert _mine(lg, uid)["player_ids"] == _espn_roster(team_id)


def _assert_mfl_view(env, uid, fid):
    lg = _mfl_leagues(env, uid).get(MFL_LEAGUE)
    assert lg is not None, f"MFL league vanished from {uid}'s league list"
    assert lg["my_team"] == fid
    assert _mine(lg, uid)["player_ids"] == _mfl_roster(fid)


# ===========================================================================
# Phase 1 — reproduction: two users, one ESPN league
# ===========================================================================

def test_espn_second_link_keeps_first_users_team(env):
    assert _espn_link(env, A, 1).status_code == 200
    assert _espn_link(env, B, 2).status_code == 200
    _assert_espn_view(env, A, 1)
    _assert_espn_view(env, B, 2)


def test_espn_reverse_order(env):
    assert _espn_link(env, B, 2).status_code == 200
    assert _espn_link(env, A, 1).status_code == 200
    _assert_espn_view(env, A, 1)
    _assert_espn_view(env, B, 2)


def test_espn_first_user_relink_after_second_keeps_both(env):
    _espn_link(env, A, 1)
    _espn_link(env, B, 2)
    assert _espn_link(env, A, 1).status_code == 200
    _assert_espn_view(env, A, 1)
    _assert_espn_view(env, B, 2)


def test_espn_resync_by_either_user_keeps_both(env):
    _espn_link(env, A, 1)
    _espn_link(env, B, 2)
    r = _espn_import(env, A)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["my_team_id"] == 1
    r = _espn_import(env, B)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["my_team_id"] == 2
    _assert_espn_view(env, A, 1)
    _assert_espn_view(env, B, 2)


def test_espn_each_user_sees_the_other_as_a_real_member(env):
    """League-mates using the app together: in A's view, B's team carries B's
    real id (so matching/notifications can reach B) and vice versa."""
    _espn_link(env, A, 1)
    _espn_link(env, B, 2)
    ids_a = {m["user_id"] for m in _espn_leagues(env, A)[ESPN_LEAGUE]["members"]}
    ids_b = {m["user_id"] for m in _espn_leagues(env, B)[ESPN_LEAGUE]["members"]}
    assert {A, B} <= ids_a and {A, B} <= ids_b
    assert len(ids_a) == len(ids_b) == 3


def test_espn_same_user_relinks_to_another_team(env):
    _espn_link(env, A, 1)
    _espn_link(env, B, 2)
    assert _espn_link(env, A, 3).status_code == 200
    _assert_espn_view(env, A, 3)
    _assert_espn_view(env, B, 2)
    with env.engine.connect() as conn:
        uids = [m.user_id for m in conn.execute(
            select(db_module.league_members_table)).fetchall()]
    assert sorted(uids).count(A) == 1 and len(uids) == 3


def test_espn_resync_does_not_unverify_first_users_credential(env):
    """Cookie leagues: A's re-sync after B's link used to hold A's SWID to
    B's team (the #321 R3b check against the overwritten binding), null A's
    verified_at and 403 wrong_account."""
    now = datetime.now(timezone.utc).isoformat()
    for uid, team in ((A, 1), (B, 2)):
        db_module.upsert_espn_credential(
            uid, SWID[team], server._sleeper_write.encrypt_token(f"s2-{uid}"),
            verified_at=now)
    assert _espn_link(env, A, 1).get_json()["auth"] == "cookie"
    assert _espn_link(env, B, 2).get_json()["auth"] == "cookie"
    r = _espn_import(env, A)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["my_team_id"] == 1
    assert db_module.get_espn_credential(A)["verified_at"] == now
    assert db_module.get_espn_credential(B)["verified_at"] == now
    assert db_module.get_espn_credential(A)["swid"] == SWID[1]


def test_espn_unbound_user_fails_closed(env):
    """C never linked: the league is not C's, C cannot re-sync it, and C is
    never handed anyone else's team."""
    _espn_link(env, A, 1)
    assert ESPN_LEAGUE not in _espn_leagues(env, C)
    r = _espn_import(env, C)
    assert r.status_code in (403, 404, 409)
    _assert_espn_view(env, A, 1)


# ===========================================================================
# Phase 1 — reproduction: two users, one MFL league
# ===========================================================================

def test_mfl_second_link_keeps_first_users_team(env):
    assert _mfl_link(env, A, "0001").status_code == 200
    assert _mfl_link(env, B, "0002").status_code == 200
    _assert_mfl_view(env, A, "0001")
    _assert_mfl_view(env, B, "0002")


def test_mfl_reverse_order_and_relink(env):
    _mfl_link(env, B, "0002")
    _mfl_link(env, A, "0001")
    assert _mfl_link(env, B, "0002").status_code == 200
    _assert_mfl_view(env, A, "0001")
    _assert_mfl_view(env, B, "0002")


def test_mfl_resync_by_either_user_keeps_both(env):
    _mfl_link(env, A, "0001")
    _mfl_link(env, B, "0002")
    r = _mfl_import(env, A)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["my_team_id"] == "0001"
    r = _mfl_import(env, B)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["my_team_id"] == "0002"
    _assert_mfl_view(env, A, "0001")
    _assert_mfl_view(env, B, "0002")


def test_mfl_authed_import_keeps_other_users_team(env):
    """The #177 sign-in import path (_mfl_import_league_authed) is a third
    writer of the same rows."""
    _mfl_link(env, A, "0001")
    with patch.object(server, "is_enabled", lambda k: k in FLAGS):
        server._mfl_import_league_authed(B, MFL_LEAGUE, 2026, None, "cookie-b", "0002")
    _assert_mfl_view(env, A, "0001")
    _assert_mfl_view(env, B, "0002")


def test_mfl_unbound_user_fails_closed(env):
    _mfl_link(env, A, "0001")
    assert MFL_LEAGUE not in _mfl_leagues(env, C)
    assert _mfl_import(env, C).status_code in (403, 404, 409)
    _assert_mfl_view(env, A, "0001")


# ===========================================================================
# Phase 1 — sends use the SENDER's own binding and credential
# ===========================================================================

def _espn_seed_two_linkers(first, second):
    """Both users linked via the real link writer, in the given order."""
    teams = {A: 1, B: 2}
    for uid in (first, second):
        db_module.upsert_espn_league(
            league_id=ESPN_LEAGUE, user_id=uid, name="Recorded Shape Dynasty",
            espn_season=2026, espn_auth="cookie", espn_my_team_id=teams[uid],
            total_rosters=3)
        db_module.upsert_espn_credential(
            uid, SWID[teams[uid]], server._sleeper_write.encrypt_token(f"s2-{uid}"),
            verified_at=datetime.now(timezone.utc).isoformat())


@pytest.mark.parametrize("order", [(A, B), (B, A)])
def test_espn_send_uses_senders_team_and_cookie(env, order):
    _espn_seed_two_linkers(*order)
    give_a, give_b = _espn_roster(1)[0], _espn_roster(2)[0]
    for sender, my_team, their_team, give, recv in (
            (A, 1, 2, give_a, give_b), (B, 2, 1, give_b, give_a)):
        fake = MagicMock(return_value={"transaction_id": "t", "status": "PENDING",
                                       "raw": {}})
        with patch.object(espn_write, "propose_trade", fake):
            r = env.c.post("/api/trades/propose-espn", headers=_h(env.tok[sender]),
                           data=json.dumps({"league_id": ESPN_LEAGUE,
                                            "their_team_id": their_team,
                                            "give_player_ids": [give],
                                            "receive_player_ids": [recv]}))
        assert r.status_code == 200, (sender, r.get_data(as_text=True))
        (espn_s2, swid, req), _ = fake.call_args
        assert req.my_team_id == my_team, f"{sender} sent as team {req.my_team_id}"
        assert espn_s2 == f"s2-{sender}" and swid == SWID[my_team]


def test_espn_send_counterparty_by_real_member_id(env):
    """In A's view B's team carries B's real id; sending to it must resolve to
    B's team, never to A's own."""
    _espn_seed_two_linkers(A, B)
    fake = MagicMock(return_value={"transaction_id": "t", "status": "PENDING", "raw": {}})
    with patch.object(espn_write, "propose_trade", fake):
        r = env.c.post("/api/trades/propose-espn", headers=_h(env.tok[A]),
                       data=json.dumps({"league_id": ESPN_LEAGUE, "their_user_id": B,
                                        "give_player_ids": [_espn_roster(1)[0]],
                                        "receive_player_ids": [_espn_roster(2)[0]]}))
    assert r.status_code == 200, r.get_data(as_text=True)
    (_, _, req), _ = fake.call_args
    assert (req.my_team_id, req.their_team_id) == (1, 2)


def test_espn_send_by_unbound_user_refused(env):
    _espn_seed_two_linkers(A, B)
    db_module.upsert_espn_credential(
        C, SWID[3], server._sleeper_write.encrypt_token("s2-c"),
        verified_at=datetime.now(timezone.utc).isoformat())
    fake = MagicMock()
    with patch.object(espn_write, "propose_trade", fake):
        r = env.c.post("/api/trades/propose-espn", headers=_h(env.tok[C]),
                       data=json.dumps({"league_id": ESPN_LEAGUE, "their_team_id": 1,
                                        "give_player_ids": [_espn_roster(3)[0]],
                                        "receive_player_ids": [_espn_roster(1)[0]]}))
    assert r.status_code == 404 and r.get_json()["error"] == "espn_not_linked"
    fake.assert_not_called()


def _mfl_seed_two_linkers(first, second):
    teams = {A: "0001", B: "0002"}
    for uid in (first, second):
        db_module.upsert_platform_league(
            league_id=MFL_LEAGUE, user_id=uid, name="MFL", platform="mfl",
            season=2026, auth="cookie", my_team=teams[uid], total_rosters=3,
            host="www48.myfantasyleague.com", future_picks=[])
        db_module.upsert_mfl_credential(
            uid, f"mfl-{uid}", server._sleeper_write.encrypt_token(f"MFL_USER_ID={uid}"),
            2026)


@pytest.mark.parametrize("order", [(A, B), (B, A)])
def test_mfl_send_uses_senders_franchise_and_cookie(env, order):
    _mfl_seed_two_linkers(*order)
    give_a, give_b = _mfl_roster("0001")[0], _mfl_roster("0002")[0]
    for sender, their_fid, give, recv in ((A, "0002", give_a, give_b),
                                          (B, "0001", give_b, give_a)):
        fake = MagicMock(return_value={"status": "OK", "raw": "<status>OK</status>"})
        with patch.object(mfl_write, "propose_trade", fake):
            r = env.c.post("/api/trades/propose-mfl", headers=_h(env.tok[sender]),
                           data=json.dumps({"league_id": MFL_LEAGUE,
                                            "their_franchise_id": their_fid,
                                            "give_player_ids": [give],
                                            "receive_player_ids": [recv]}))
        assert r.status_code == 200, (sender, r.get_data(as_text=True))
        (cookie, _host, _year, req), _ = fake.call_args
        assert cookie == f"MFL_USER_ID={sender}"
        assert req.offered_to == their_fid


def test_mfl_send_counterparty_by_real_member_id(env):
    _mfl_seed_two_linkers(A, B)
    fake = MagicMock(return_value={"status": "OK", "raw": "<status>OK</status>"})
    with patch.object(mfl_write, "propose_trade", fake):
        r = env.c.post("/api/trades/propose-mfl", headers=_h(env.tok[B]),
                       data=json.dumps({"league_id": MFL_LEAGUE, "their_user_id": A,
                                        "give_player_ids": [_mfl_roster("0002")[0]],
                                        "receive_player_ids": [_mfl_roster("0001")[0]]}))
    assert r.status_code == 200, r.get_data(as_text=True)
    (cookie, _h2, _y, req), _ = fake.call_args
    assert cookie == f"MFL_USER_ID={B}" and req.offered_to == "0001"


def test_mfl_send_by_unbound_user_refused(env):
    _mfl_seed_two_linkers(A, B)
    db_module.upsert_mfl_credential(
        C, "mfl-c", server._sleeper_write.encrypt_token("MFL_USER_ID=c"), 2026)
    fake = MagicMock()
    with patch.object(mfl_write, "propose_trade", fake):
        r = env.c.post("/api/trades/propose-mfl", headers=_h(env.tok[C]),
                       data=json.dumps({"league_id": MFL_LEAGUE,
                                        "their_franchise_id": "0001",
                                        "give_player_ids": [_mfl_roster("0003")[0]],
                                        "receive_player_ids": [_mfl_roster("0001")[0]]}))
    assert r.status_code == 404 and r.get_json()["error"] == "mfl_not_linked"
    fake.assert_not_called()


def test_overhaul_fresh_rosters_are_the_viewers_own(env):
    """The server-side fresh roster read (team overhaul) labels the VIEWER's
    team with the viewer's id — for the second linker too."""
    _mfl_seed_two_linkers(A, B)
    for uid, fid in ((A, "0001"), (B, "0002")):
        sess = server._sessions[env.tok[uid]]
        rosters = server._overhaul_platform_rosters(sess, MFL_LEAGUE, "mfl")
        assert rosters is not None, uid
        mine = [r for r in rosters if r["owner_id"] == uid]
        assert [r["roster_id"] for r in mine] == [fid]


# ===========================================================================
# Phase 1 — unlink isolation (credential disconnect, account deletion)
# ===========================================================================

def test_credential_disconnect_touches_only_the_caller(env):
    _espn_seed_two_linkers(A, B)
    _mfl_seed_two_linkers(A, B)
    with patch.object(server, "is_enabled", lambda k: k in FLAGS | {"mfl.auth_link"}):
        assert env.c.delete("/api/espn/link", headers=_h(env.tok[A])).status_code == 200
        assert env.c.delete("/api/mfl/auth-link", headers=_h(env.tok[A])).status_code == 200
    assert db_module.get_espn_credential(A) is None
    assert db_module.get_mfl_credential(A) is None
    assert db_module.get_espn_credential(B)["swid"] == SWID[2]
    assert db_module.get_mfl_credential(B) is not None
    assert db_module.get_espn_league(ESPN_LEAGUE) is not None
    assert db_module.get_platform_league(MFL_LEAGUE, "mfl") is not None


def test_account_deletion_keeps_other_users_league_and_binding(env):
    from backend import accounts
    _espn_link(env, A, 1)
    _espn_link(env, B, 2)
    _mfl_link(env, A, "0001")
    _mfl_link(env, B, "0002")
    with env.engine.begin() as conn:
        for uid in (A, B):
            conn.execute(insert(db_module.users_table).values(sleeper_user_id=uid))
    accounts.delete_user_data(A)
    _assert_espn_view(env, B, 2)
    _assert_mfl_view(env, B, "0002")
    assert ESPN_LEAGUE not in _espn_leagues(env, A)
    assert MFL_LEAGUE not in _mfl_leagues(env, A)


# ===========================================================================
# Co-owned team: two app accounts bound to the SAME team (one person with two
# app accounts, or two co-managers). One member row per team; each sees it as
# theirs; nobody else is touched.
# ===========================================================================

def test_two_accounts_on_one_team_share_one_member_row(env):
    _espn_link(env, A, 1)
    _espn_link(env, B, 2)
    assert _espn_link(env, C, 1).status_code == 200
    _assert_espn_view(env, A, 1)
    _assert_espn_view(env, B, 2)
    _assert_espn_view(env, C, 1)
    with env.engine.connect() as conn:
        uids = sorted(m.user_id for m in conn.execute(
            select(db_module.league_members_table)).fetchall())
    assert len(uids) == 3 and uids.count(A) == 1 and C not in uids


# ===========================================================================
# Backfill — derive pre-existing bindings from evidence that still holds
# ===========================================================================

def _legacy_league(conn, lid, platform, user_id, team, members):
    """A leagues row + members exactly as the pre-binding writers left them."""
    conn.execute(insert(db_module.leagues_table).values(
        sleeper_league_id=lid, user_id=user_id, name=lid, platform=platform,
        espn_my_team_id=team if platform == "espn" else None,
        platform_my_team=str(team) if platform != "espn" and team is not None else None))
    for uid in members:
        conn.execute(insert(db_module.league_members_table).values(
            league_id=lid, user_id=uid, username=uid, display_name=uid,
            roster_data="[]"))


def _bindings(engine):
    with engine.connect() as conn:
        return {(r.user_id, r.league_id): (r.platform, r.team_id, r.source)
                for r in conn.execute(select(db_module.platform_league_bindings_table))}


@pytest.fixture()
def bare_db():
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with patch.object(db_module, "engine", engine):
        yield engine


def test_backfill_derives_intact_and_never_guesses(bare_db):
    with bare_db.begin() as conn:
        # intact single linker (ESPN + MFL)
        _legacy_league(conn, "1", "espn", A, 4, [A, "espn:{S1}", "espn:{S2}"])
        _legacy_league(conn, "2", "mfl", A, "0003", [A, "mfl:2.f0001", "mfl:2.f0002"])
        # overwritten: A linked first, B last → row user A, team = B's, one
        # real member (B): B's binding is the derivable one; A gets none.
        _legacy_league(conn, "3", "espn", A, 7, [B, "espn:{S1}", "espn:{S3}"])
        # no app-user member at all (the last linker's account was deleted)
        _legacy_league(conn, "4", "mfl", A, "0001", ["mfl:4.f0001", "mfl:4.f0002"])
        # two app-user members (not reachable by the legacy writers; never guessed)
        _legacy_league(conn, "5", "espn", A, 1, [A, B])
        # no team column (a row the importers never bound)
        _legacy_league(conn, "6", "mfl", A, None, [A])
        # ESPN: the candidate's own SWID labels ANOTHER team → the pair is wrong
        _legacy_league(conn, "7", "espn", C, 2, [C, "espn:{C3333333-3333-3333-3333-333333333333}"])
        conn.execute(insert(db_module.espn_credentials_table).values(
            user_id=C, swid=SWID[3], espn_s2_encrypted="x", created_at="t", updated_at="t"))
        # Sleeper league: out of scope
        conn.execute(insert(db_module.leagues_table).values(
            sleeper_league_id="8", user_id=A, platform="sleeper"))
        conn.execute(insert(db_module.league_members_table).values(
            league_id="8", user_id=A, roster_data="[]"))
    counts = db_module.backfill_platform_league_bindings()
    assert _bindings(bare_db) == {
        (A, "1"): ("espn", "4", "backfill"),
        (A, "2"): ("mfl", "0003", "backfill"),
        (B, "3"): ("espn", "7", "backfill"),
    }
    assert counts == {"considered": 7, "bound": 3, "has_binding": 0, "no_team": 1,
                      "not_exactly_one_member": 2, "swid_conflict": 1}


def test_backfill_is_idempotent_and_never_overwrites_a_link(bare_db):
    with bare_db.begin() as conn:
        _legacy_league(conn, "1", "espn", A, 4, [A, "espn:{S1}"])
        _legacy_league(conn, "2", "mfl", A, "0003", [A])
    first = db_module.backfill_platform_league_bindings()
    snap = _bindings(bare_db)
    second = db_module.backfill_platform_league_bindings()
    assert _bindings(bare_db) == snap and first["bound"] == 2 and second["bound"] == 0
    assert second["has_binding"] == 2
    # A link that landed first (deploy overlap) is never replaced.
    with bare_db.begin() as conn:
        _legacy_league(conn, "9", "espn", A, 4, [A])
        db_module._upsert_platform_binding(conn, A, "9", "espn", 2)
    db_module.backfill_platform_league_bindings()
    assert _bindings(bare_db)[(A, "9")] == ("espn", "2", "link")


def test_backfill_leaves_leagues_and_members_untouched(bare_db):
    with bare_db.begin() as conn:
        _legacy_league(conn, "1", "espn", A, 4, [A, "espn:{S1}"])
        _legacy_league(conn, "3", "espn", A, 7, [B, "espn:{S1}"])
    def dump():
        with bare_db.connect() as conn:
            return ([tuple(r) for r in conn.execute(select(db_module.leagues_table))],
                    [tuple(r) for r in conn.execute(select(db_module.league_members_table))])
    before = dump()
    db_module.backfill_platform_league_bindings()
    assert dump() == before


def test_overwritten_first_user_is_asked_to_relink_not_guessed(bare_db):
    """Production state after the bug: the first linker A has no derivable
    binding — the league is not A's until A re-links; B keeps theirs."""
    with bare_db.begin() as conn:
        _legacy_league(conn, "3", "espn", A, 7, [B, "espn:{S1}"])
    db_module.backfill_platform_league_bindings()
    assert db_module.load_espn_leagues_for_user(A) == []
    assert db_module.get_platform_binding(A, "3") is None
    [lg] = db_module.load_espn_leagues_for_user(B)
    assert lg["my_team_id"] == 7


def test_backfill_runs_from_migrate_db(bare_db):
    with bare_db.begin() as conn:
        _legacy_league(conn, "1", "espn", A, 4, [A])
    db_module._migrate_db()
    db_module._migrate_db()
    assert _bindings(bare_db) == {(A, "1"): ("espn", "4", "backfill")}


def test_binding_ddl_and_backfill_insert_compile_for_postgres():
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable
    t = db_module.platform_league_bindings_table
    ddl = str(CreateTable(t).compile(dialect=postgresql.dialect()))
    assert "PRIMARY KEY (user_id, league_id)" in ddl
    for ix in t.indexes:
        str(CreateIndex(ix).compile(dialect=postgresql.dialect()))
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(t).values(user_id="u", league_id="l", platform="espn", team_id="1",
                               source="backfill", created_at="t", updated_at="t")
    sql = str(stmt.on_conflict_do_nothing(index_elements=["user_id", "league_id"])
              .compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (user_id, league_id) DO NOTHING" in sql
    up = pg_insert(t).values(user_id="u", league_id="l", platform="espn", team_id="1",
                             source="link", created_at="t", updated_at="t")
    sql = str(up.on_conflict_do_update(index_elements=["user_id", "league_id"],
                                       set_={"team_id": up.excluded.team_id})
              .compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (user_id, league_id) DO UPDATE" in sql


# ===========================================================================
# Sleeper is untouched: its snapshot writer never relabels and never reads
# the binding table.
# ===========================================================================

def test_sleeper_member_snapshot_is_never_relabelled(bare_db):
    with bare_db.begin() as conn:   # even a (nonsensical) binding on the id
        db_module._upsert_platform_binding(conn, C, "555", "espn", 1)
    members = [{"user_id": A, "username": "a", "player_ids": ["1"]},
               {"user_id": B, "username": "b", "player_ids": ["2"]}]
    assert db_module.replace_league_members_snapshot("555", members)
    with bare_db.connect() as conn:
        uids = sorted(r.user_id for r in conn.execute(
            select(db_module.league_members_table)))
    assert uids == sorted([A, B])


def test_platform_free_agent_moves_do_not_exist():
    """Free-agent moves are Sleeper-only (server._FA_MOVE_FLAGS); an ESPN /
    MFL move would need the SENDER's binding exactly like a trade send. If
    this fails, a platform move was added: route its team through
    get_platform_binding and extend the send tests above."""
    assert set(server._FA_MOVE_FLAGS) == {"sleeper"}
    with patch.object(server, "is_enabled", lambda k: True):
        assert not server._fa_move_live("espn") and not server._fa_move_live("mfl")


# ===========================================================================
# Seam: every "my team" reader goes through the per-user accessor
# ===========================================================================

def test_binding_columns_have_one_reader():
    """The legacy leagues.espn_my_team_id / platform_my_team columns hold the
    LAST linker's team. Nothing may read them as anyone's binding: only the
    two link writers (as keyword arguments), the backfill and the schema
    mention them. Readers use database.get_platform_binding (my team) or
    database.platform_bound_teams (every bound team)."""
    import ast
    import pathlib
    cols = {"espn_my_team_id", "platform_my_team"}
    root = pathlib.Path(__file__).resolve().parents[1]
    allowed = {
        "database.py": {"<module>", "_migrate_db", "upsert_espn_league",
                        "upsert_platform_league", "backfill_platform_league_bindings"},
        # Fed binding-derived values by prepared_trade_runtime.cohort_rows
        # (a pure, dependency-injected module).
        "prepared_trade_runtime.py": {"cohort_rows"},
        "prepared_trade_cohort.py": {"discover_targets", "read_league_source"},
        # Founders-only calibration capture: provenance keys + live
        # provider re-verification (league_seat_changed). Known residual —
        # docs/plans/platform-league-binding/design.md § Not switched.
        "calibration_provider_capture.py": {"<module>", "capture_linked"},
    }
    writer_calls = {"upsert_espn_league", "upsert_platform_league"}
    bad = []
    for path in sorted(root.rglob("*.py")):
        if "tests" in path.relative_to(root).parts:
            continue
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text())
        ok_kw = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                if fn in writer_calls:
                    ok_kw.update(id(k) for k in node.keywords)

        def visit(node, fn):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = node.name
            hit = ((isinstance(node, ast.Constant) and node.value in cols)
                   or (isinstance(node, ast.keyword) and node.arg in cols
                       and id(node) not in ok_kw)
                   or (isinstance(node, ast.Attribute) and node.attr in cols))
            if hit and fn not in allowed.get(rel, set()):
                bad.append(f"{rel}:{getattr(node, 'lineno', '?')} in {fn}")
            for child in ast.iter_child_nodes(node):
                visit(child, fn)
        visit(tree, "<module>")
    assert not bad, "legacy binding column read outside the accessor: " + ", ".join(bad)


def test_binding_table_has_few_writers():
    """Only database.py writes bindings; accounts.py reads them for the
    deletion hand-over; prepared_trade_runtime.py reads them into the cohort."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    users = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.py")
                   if "tests" not in p.relative_to(root).parts
                   and "platform_league_bindings_table" in p.read_text())
    assert users == ["accounts.py", "database.py", "prepared_trade_runtime.py"]


def test_backfill_loses_the_race_to_a_concurrent_link(bare_db):
    """A link committed between the backfill's read and its insert (deploy
    overlap) wins: the insert is ON CONFLICT DO NOTHING."""
    from sqlalchemy import event
    with bare_db.begin() as conn:
        _legacy_league(conn, "1", "espn", A, 4, [A])
    fired = []

    def _link_lands_first(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO PLATFORM_LEAGUE_BINDINGS") \
                and not fired:
            fired.append(1)
            cursor.execute(
                "INSERT INTO platform_league_bindings (user_id, league_id, platform, "
                "team_id, source, created_at, updated_at) VALUES "
                "(?, '1', 'espn', '2', 'link', 't', 't')", (A,))
    event.listen(bare_db, "before_cursor_execute", _link_lands_first)
    try:
        counts = db_module.backfill_platform_league_bindings()
    finally:
        event.remove(bare_db, "before_cursor_execute", _link_lands_first)
    assert fired and counts["bound"] == 0
    assert _bindings(bare_db) == {(A, "1"): ("espn", "2", "link")}
