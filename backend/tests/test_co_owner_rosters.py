"""Sleeper co-owned rosters — regression suite.

Pins the 2026-08-15 finding: FTF matched rosters on ``owner_id`` alone and
never read Sleeper's ``co_owners``, so a co-manager's league resolved to no
team AND — because the opponent filter was ``owner_id != user_id`` — their own
roster was posted back as a leaguemate for the engine to trade against.

Fixture: ``fixtures/sleeper/co-owned-league/`` — the real Bush League
(1338231586314780672) roster/owner ids, roster_id 3 co-owned by
313560442465169408, with synthetic player lists.

Design under test (docs/plans/sleeper-co-owner-rosters/scope.md §0.3):

  a roster is yours iff  user_id == owner_id  OR  user_id in co_owners

and a co-owner is an ALIAS of that roster's primary ``owner_id`` — the
canonical LEAGUE identity — while their own Sleeper id stays their ACCOUNT
identity. The two are the same string for a sole owner, so every assertion
here has a sole-owner twin proving the old behavior is byte-identical.
"""
import json
import pathlib
from unittest.mock import MagicMock

import pytest

import backend.server as server
from backend.draft_board_service import _order_from
from backend.sleeper_roster import (
    canonical_owner_id,
    co_owner_ids,
    find_user_roster,
    owns_roster,
)


FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "sleeper" / "co-owned-league"

LEAGUE_ID = "1338231586314780672"
CO_OWNER = "313560442465169408"       # co-owns roster 3; owns nothing
PRIMARY = "460238423161040896"        # roster 3's owner_id
SOLE_OWNER = "733459678624915456"     # roster 1 — the control
STRANGER = "999999999999999999"       # in no roster at all


@pytest.fixture(scope="module")
def rosters():
    return json.loads((FIXTURES / "rosters.json").read_text())


# ===========================================================================
# The predicate — backend/sleeper_roster.py
# ===========================================================================

def test_fixture_shape_is_the_reported_case(rosters):
    """Guard the fixture itself: if this drifts, every test below lies."""
    assert len(rosters) == 12
    co_owned = [r for r in rosters if r["co_owners"]]
    assert len(co_owned) == 1
    assert co_owned[0]["roster_id"] == 3
    assert co_owned[0]["owner_id"] == PRIMARY
    assert co_owned[0]["co_owners"] == [CO_OWNER]
    # Every other roster carries an explicit null, which is what Sleeper sends.
    assert all(r["co_owners"] is None for r in rosters if r["roster_id"] != 3)


def test_owns_roster_matches_the_primary_owner(rosters):
    assert owns_roster(rosters[0], SOLE_OWNER) is True


def test_owns_roster_matches_a_co_owner(rosters):
    """THE bug. Before co-owner support this was False and the league died."""
    roster3 = rosters[2]
    assert owns_roster(roster3, CO_OWNER) is True
    assert owns_roster(roster3, PRIMARY) is True      # primary still matches


def test_owns_roster_rejects_a_stranger(rosters):
    assert owns_roster(rosters[2], STRANGER) is False


def test_owns_roster_rejects_an_empty_user_id(rosters):
    """An ownerless roster (owner_id null after a manager leaves) must not
    resolve to a caller with no id — `str(None) == str(None)` would."""
    ownerless = {"roster_id": 99, "owner_id": None, "co_owners": None}
    assert owns_roster(ownerless, None) is False
    assert owns_roster(ownerless, "") is False


@pytest.mark.parametrize("raw", [None, [], "not-a-list", 0, {"a": 1}])
def test_co_owner_ids_tolerates_every_absent_shape(raw):
    assert co_owner_ids({"owner_id": "x", "co_owners": raw}) == []


def test_co_owner_ids_tolerates_the_key_being_absent():
    """The shape the hermetic sim harness emits: `seed_ui_test_db.py` builds
    roster cassettes with no `co_owners` key at all, so every Maestro flow
    runs the sole-owner branch. `.get()` must not become a KeyError."""
    assert co_owner_ids({"owner_id": "x", "roster_id": 1}) == []
    assert owns_roster({"owner_id": "x", "roster_id": 1}, "x") is True
    assert owns_roster({"owner_id": "x", "roster_id": 1}, "y") is False


def test_co_owner_ids_coerces_to_str():
    """Nothing guarantees the wire type stays string; owner_id is compared
    str-wise everywhere else for the same reason."""
    assert co_owner_ids({"co_owners": [123, "456", None, ""]}) == ["123", "456"]


def test_find_user_roster_resolves_the_co_owned_team(rosters):
    hit = find_user_roster(rosters, CO_OWNER)
    assert hit is not None
    assert hit["roster_id"] == 3
    # The players are globally unique per roster — this is the assertion that
    # the RIGHT roster came back, not merely a roster.
    assert hit["players"] == ["p3_1", "p3_2", "p3_3"]


def test_find_user_roster_returns_none_for_a_stranger(rosters):
    assert find_user_roster(rosters, STRANGER) is None


def test_canonical_owner_id_aliases_a_co_owner_to_the_primary(rosters):
    assert canonical_owner_id(rosters, CO_OWNER) == PRIMARY


def test_canonical_owner_id_is_identity_for_a_sole_owner(rosters):
    """The sole-owner twin: nothing changes for the 99% case."""
    assert canonical_owner_id(rosters, SOLE_OWNER) == SOLE_OWNER


def test_canonical_owner_id_falls_back_when_there_is_no_roster(rosters):
    """No roster here, or a failed rosters fetch — return the caller's own id
    rather than an empty string, so downstream keying stays well-formed."""
    assert canonical_owner_id(rosters, STRANGER) == STRANGER
    assert canonical_owner_id(None, CO_OWNER) == CO_OWNER
    assert canonical_owner_id([], CO_OWNER) == CO_OWNER


# ===========================================================================
# Session identity — server._league_user_id
# ===========================================================================

def test_league_user_id_prefers_the_league_identity():
    sess = {"user_id": CO_OWNER, "league_user_id": PRIMARY}
    assert server._league_user_id(sess) == PRIMARY


def test_league_user_id_falls_back_for_a_pre_existing_session():
    """Sessions minted before the key existed must keep working — this is what
    lets every call site swap user_id -> _league_user_id safely."""
    assert server._league_user_id({"user_id": SOLE_OWNER}) == SOLE_OWNER


# ===========================================================================
# Send in Sleeper — server._roster_id_for_owner
# ===========================================================================

def test_roster_id_for_owner_resolves_a_co_owner(rosters):
    """Sleeper grants co-owners full control, so a co-owner proposing a trade
    proposes it as that roster. This returned None before, and the send failed."""
    assert server._roster_id_for_owner(rosters, CO_OWNER) == 3


def test_roster_id_for_owner_unchanged_for_a_sole_owner(rosters):
    assert server._roster_id_for_owner(rosters, SOLE_OWNER) == 1


def test_roster_id_for_owner_none_for_a_stranger(rosters):
    assert server._roster_id_for_owner(rosters, STRANGER) is None
    assert server._roster_id_for_owner(rosters, "") is None
    assert server._roster_id_for_owner([], CO_OWNER) is None


# ===========================================================================
# Mock draft owner set — server._mock_owner_ids / _mock_rosters
#
# INV-6 refuses a create whose user_owner_id isn't in the resolved order. The
# session's league.members are keyed on each roster's owner_id, so a co-owner
# passing their ACCOUNT id was refused `user_not_in_draft`.
# ===========================================================================

def _mock_session(user_id, league_user_id):
    members = [MagicMock(user_id=PRIMARY, roster=["p3_1"]),
               MagicMock(user_id=SOLE_OWNER, roster=["p1_1"])]
    return {"user_id": user_id,
            "league_user_id": league_user_id,
            "league": MagicMock(members=members),
            "user_roster": ["p3_1", "p3_2"]}


def test_mock_owner_ids_does_not_add_a_phantom_owner_for_a_co_owner():
    """The caller joins as the roster they co-own — 2 owners, not 3."""
    owners = server._mock_owner_ids(_mock_session(CO_OWNER, PRIMARY))
    assert owners == [PRIMARY, SOLE_OWNER]
    assert CO_OWNER not in owners


def test_mock_rosters_keys_the_caller_by_league_identity():
    """_mock_owner_ids and _mock_rosters are keyed together — a roster filed
    under an id no owner holds is invisible to the engine."""
    rosters_map = server._mock_rosters(_mock_session(CO_OWNER, PRIMARY))
    assert set(rosters_map) == {PRIMARY, SOLE_OWNER}
    # The session roster is authoritative for the caller and wins the merge.
    assert rosters_map[PRIMARY] == ["p3_1", "p3_2"]


def test_mock_owner_ids_unchanged_for_a_sole_owner():
    sess = _mock_session(SOLE_OWNER, SOLE_OWNER)
    assert server._mock_owner_ids(sess) == [PRIMARY, SOLE_OWNER]
    assert server._mock_rosters(sess)[SOLE_OWNER] == ["p3_1", "p3_2"]


# ===========================================================================
# Draft order — draft_board_service._order_from
#
# `roster_by_user` carries co-owner ALIASES (draft_order may key a co-managed
# team by either id); `user_by_roster` stays owner-primary, because it fills
# the one public owner id on every entry.
# ===========================================================================

def _detail(draft_order):
    return {"settings": {"rounds": 1, "teams": 12}, "type": "linear",
            "draft_order": draft_order}


def test_draft_order_keyed_by_a_co_owner_resolves_the_roster(rosters):
    order, confidence = _order_from(
        _detail({CO_OWNER: 1}), [], rosters, [], 2026)
    assert confidence == "assigned"
    slot1 = next(e for e in order if e["slot"] == 1)
    # Resolved to roster 3 — and reported under the PRIMARY owner, never the
    # co-owner, so a team's public id doesn't vary with who co-manages it.
    assert slot1["owner_user_id"] == PRIMARY
    assert slot1["original_user_id"] == PRIMARY


def test_draft_order_keyed_by_the_primary_owner_still_wins(rosters):
    order, _ = _order_from(_detail({PRIMARY: 1}), [], rosters, [], 2026)
    slot1 = next(e for e in order if e["slot"] == 1)
    assert slot1["owner_user_id"] == PRIMARY


def test_draft_order_sole_owner_unchanged(rosters):
    order, _ = _order_from(_detail({SOLE_OWNER: 4}), [], rosters, [], 2026)
    slot4 = next(e for e in order if e["slot"] == 4)
    assert slot4["owner_user_id"] == SOLE_OWNER


# ===========================================================================
# session_init end-to-end — the league_members write
#
# This is the assertion that a naive client-only fix would fail: league_members
# is a league-SHARED table, so a co-owned roster must land on ONE row keyed by
# its primary owner. Keyed on the caller instead, a 12-team league accumulates
# 13 rows with one roster duplicated, and session_init's own DB-member merge
# then hands the trade engine a phantom copy of the caller's team.
# ===========================================================================

@pytest.fixture()
def init_client(monkeypatch, rosters):
    """A session_init harness whose background daemon runs INLINE, so the
    league_members write is observable from the test body."""
    from backend.ranking_service import Player

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    pool = [Player(f"p{i}_{n}", f"P{i}{n}", "RB", "AAA", 25, 1)
            for i in range(1, 13) for n in (1, 2, 3)]
    seed = {p.id: 1500.0 for p in pool}
    fake_pools = {"1qb_ppr": {"players": pool, "seed": seed},
                  "sf_tep":  {"players": pool, "seed": seed}}
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format", fake_pools)
    monkeypatch.setattr(server, "g_universal_players", pool)
    monkeypatch.setattr(server, "_kickoff_trade_job", MagicMock())
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta", lambda lid: None)

    from backend import database as db, accounts
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(accounts, "get_user_profile", lambda uid: None)
    def sleeper_get(url):
        if url.endswith("/rosters"):
            return rosters
        if url.endswith("/users"):
            return [{"user_id": r["owner_id"], "display_name": f"Manager {r['roster_id']}"}
                    for r in rosters]
        return {"name": "Bush League"}
    monkeypatch.setattr(server, "_sleeper_get", sleeper_get)
    # Authentication is established before selecting a league. Each test
    # client chooses which proven identity to exercise via the header.
    sessions = {uid: {"user_id": uid, "verified": True, "verified_via": "sleeper"}
                for uid in (CO_OWNER, SOLE_OWNER)}
    monkeypatch.setattr(server, "_get_session", lambda token: sessions.get(token))
    server._sessions.update(sessions)

    captured: dict = {}

    def _capture(league_id, members):
        captured["league_id"] = league_id
        captured["members"] = members

    monkeypatch.setattr(server, "upsert_league_members", _capture)
    # Everything else the daemon touches is best-effort and already wrapped in
    # try/except upstream; neuter the writes so the test needs no live DB or
    # network. Anything NOT neutered here fails soft and is logged, exactly as
    # in production.
    for name in ("upsert_user", "upsert_league", "record_event",
                 "load_league_member_unlock_states", "is_linked_platform_league"):
        monkeypatch.setattr(server, name, MagicMock(return_value=[]))
    monkeypatch.setattr(server, "user_exists", lambda uid: True)

    real_thread = server.threading.Thread

    class _InlineBgThread(real_thread):
        """Run the bg-writes daemon synchronously. The session-init-rank pool
        workers must still thread for real or fut.result() deadlocks."""
        def start(self):
            if self.name == "session-init-bg-writes":
                self.run()
                return
            super().start()

    monkeypatch.setattr(server.threading, "Thread", _InlineBgThread)
    yield client, captured
    for token in sessions:
        server._sessions.pop(token, None)
    engine.dispose()


def _init_body(rosters, user_id):
    """Build the payload the way the clients now do: resolve by owner-or-
    co-owner, exclude own roster by roster_id, declare the league identity."""
    mine = find_user_roster(rosters, user_id)
    return json.dumps({
        "user_id": user_id,
        "league_id": LEAGUE_ID,
        "league_name": "Bush League",
        "user_player_ids": list(mine["players"]),
        "opponent_rosters": [
            {"user_id": r["owner_id"], "username": f"Team {r['roster_id']}",
             "player_ids": list(r["players"])}
            for r in rosters if r["roster_id"] != mine["roster_id"]
        ],
        "league_user_id": canonical_owner_id(rosters, user_id),
        "league_display_name": "Manager 3",
    })


def test_session_init_co_owner_gets_their_roster(init_client, rosters):
    client, _ = init_client
    res = client.post("/api/session/init", data=_init_body(rosters, CO_OWNER),
                      headers={"X-Session-Token": CO_OWNER},
                      content_type="application/json")
    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert body["ok"] is True
    # The whole point: a non-empty roster, and it is roster 3's. (The response
    # serializes players, so compare ids.)
    assert sorted(p["id"] for p in body["user_roster"]) == ["p3_1", "p3_2", "p3_3"]
    assert body["opponents"] == 11


def test_session_init_co_owner_writes_one_row_per_roster(init_client, rosters):
    """No phantom 13th team, and the caller's row is keyed on the PRIMARY
    owner so a leaguemate's sync lands on the same row."""
    client, captured = init_client
    client.post("/api/session/init", data=_init_body(rosters, CO_OWNER),
                      headers={"X-Session-Token": CO_OWNER},
                content_type="application/json")

    members = captured["members"]
    assert captured["league_id"] == LEAGUE_ID
    assert len(members) == 12
    ids = [m["user_id"] for m in members]
    assert len(set(ids)) == 12
    assert CO_OWNER not in ids                       # the account id keys nothing
    assert PRIMARY in ids                            # the league identity does

    mine = next(m for m in members if m["user_id"] == PRIMARY)
    assert mine["player_ids"] == ["p3_1", "p3_2", "p3_3"]
    # Labeled with the roster owner's name, not the caller's — this row is
    # what every OTHER member sees for that team.
    assert mine["username"] == "Manager 3"


def test_session_init_sole_owner_is_unchanged(init_client, rosters):
    """The byte-identical twin: a sole owner's payload is keyed exactly as it
    was before co-owner support existed."""
    client, captured = init_client
    res = client.post("/api/session/init", data=_init_body(rosters, SOLE_OWNER),
                      headers={"X-Session-Token": SOLE_OWNER},
                      content_type="application/json")
    assert res.status_code == 200
    assert sorted(p["id"] for p in res.get_json()["user_roster"]) == [
        "p1_1", "p1_2", "p1_3"]

    members = captured["members"]
    assert len(members) == 12
    assert members[0]["user_id"] == SOLE_OWNER
    assert members[0]["player_ids"] == ["p1_1", "p1_2", "p1_3"]


def test_session_init_without_league_user_id_defaults_to_the_caller(init_client):
    """An OLD client that omits the new fields must behave exactly as before —
    this is what makes the API field additive rather than a contract break."""
    client, captured = init_client
    res = client.post("/api/session/init", content_type="application/json",
                      headers={"X-Session-Token": SOLE_OWNER},
                      data=json.dumps({
                          "user_id": SOLE_OWNER,
                          "league_id": LEAGUE_ID,
                          "league_name": "Bush League",
                          "user_player_ids": ["p1_1"],
                          "opponent_rosters": [
                              {"user_id": PRIMARY, "username": "Team 3",
                               "player_ids": ["p3_1"]},
                          ],
                      }))
    assert res.status_code == 200
    assert captured["members"][0]["user_id"] == SOLE_OWNER


def test_session_init_stores_the_league_identity_on_the_session(init_client, rosters):
    """Every league-scoped read (is_you, free agents, mock draft) resolves
    through sess['league_user_id'], so it has to survive the request."""
    client, _ = init_client
    res = client.post("/api/session/init", data=_init_body(rosters, CO_OWNER),
                      headers={"X-Session-Token": CO_OWNER},
                      content_type="application/json")
    token = res.get_json()["token"]
    with server._sessions_lock:
        sess = server._sessions[token]
    assert sess["user_id"] == CO_OWNER            # account identity preserved
    assert server._league_user_id(sess) == PRIMARY
