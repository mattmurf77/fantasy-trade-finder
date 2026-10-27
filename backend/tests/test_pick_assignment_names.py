"""Pick-assignment grid: a user id is never stored or served as a team name.

Scope: `docs/plans/draft-extensions/scope-pick-grid-name-fallback.md`.

A member with no `username` / `display_name` used to be named
`Team <user_id>` by `server._assignment_members`, and the PUT writer fell
back to the same string. For a non-FTF ESPN manager that is
`Team espn:{SWID}`; for a fresh sign-in, `Team acct_*` — served to every
other member of the league. Both writers now fall back to the SLOT label,
`Team <original_roster_id>`, and to `Unnamed team` when the member has no
slot yet.

Production-shape members, real routes, in-memory SQLite (the live DB is
never opened). Harness mirrors `test_pick_assignment.py`.
"""
import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine

import backend.database as db
import backend.feature_flags as ff
import backend.server as server
from backend.database import metadata, leagues_table, league_members_table

LEAGUE = "1099887766554433221"          # numeric — an ESPN-shaped league id
SEASON = 2026
TOKEN = "test-token-pick-names"

ME = "acct_caller"                       # the caller: a real, named member
NAMED = "u_named"                        # named via display_name only
SWID_MEMBER = "espn:{1A2B3C4D-SWID}"     # non-FTF ESPN manager
ACCT_MEMBER = "acct_testnameless"        # a fresh sign-in with no name
SWID = "1A2B3C4D"

#: (user_id, username, display_name) — None, "" and whitespace all mean "no name".
MEMBERS = [
    (ME,          "Dana", "Dana D"),
    (NAMED,       None,   "Riley"),
    (SWID_MEMBER, None,   "   "),
    (ACCT_MEMBER, "",     None),
]
REAL_NAMES = {ME: "Dana", NAMED: "Riley"}
NAMELESS = [SWID_MEMBER, ACCT_MEMBER]


@pytest.fixture()
def mem_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    with engine.begin() as conn:
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=LEAGUE, user_id=ME, name="Sunday Sickos",
            season=str(SEASON), platform="espn", total_rosters=len(MEMBERS)))
        for uid, username, display_name in MEMBERS:
            conn.execute(league_members_table.insert().values(
                league_id=LEAGUE, user_id=uid, username=username,
                display_name=display_name, roster_data="[]"))
    db.invalidate_pick_assignment_cache(LEAGUE)
    server._invalidate_draft_context_cache()
    yield engine
    db.invalidate_pick_assignment_cache(LEAGUE)
    server._invalidate_draft_context_cache()


class _League:
    league_id = LEAGUE
    platform = "espn"
    members = ()


@pytest.fixture()
def client(mem_db):
    server.app.config["TESTING"] = True
    sess = {"verified": True,
        "user_id": ME, "league": _League(), "players": [],
        "services": {"1qb_ppr": MagicMock()}, "service": MagicMock(),
        "trade_svc": MagicMock(), "active_format": "1qb_ppr",
        "last_active": 0.0,
    }
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        yield server.app.test_client()
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


@pytest.fixture()
def flag_on():
    saved = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "picks.assign": True,
                       "draft.room": True}
    try:
        yield
    finally:
        ff._flags_cache = saved


def _hdr():
    return {"X-Session-Token": TOKEN, "Content-Type": "application/json"}


def _seed(client, **body):
    return client.post("/api/league/pick-assignments/order", headers=_hdr(),
                       data=json.dumps({"league_id": LEAGUE, **body}))


def _slots(client):
    r = client.get(f"/api/league/pick-assignments?league_id={LEAGUE}",
                   headers=_hdr())
    assert r.status_code == 200
    return [s for season in r.get_json()["seasons"] for s in season["slots"]]


def _put(client, pick_id, **body):
    return client.put(f"/api/league/pick-assignments/{pick_id}", headers=_hdr(),
                      data=json.dumps({"league_id": LEAGUE, **body}))


def _stored_rows():
    return db.load_draft_picks(LEAGUE, source=db.PICK_SOURCE_USER,
                               include_contested=True)


def _assert_no_id(name, all_ids):
    """`name` is a real string and carries no member id, no id prefix, no SWID."""
    assert isinstance(name, str) and name.strip(), repr(name)
    for uid in all_ids:
        assert uid not in name, f"{name!r} contains user id {uid!r}"
    for frag in ("espn:", "acct_", SWID):
        assert frag not in name, f"{name!r} contains {frag!r}"


_ALL_IDS = [m[0] for m in MEMBERS]


def _assign(client, slot, owner):
    """PUT one slot to `owner` with its CAS token; return the stored row."""
    r = _put(client, slot["pick_id"], owner_user_id=owner,
             if_assigned_at=slot["assigned_at"])
    assert r.status_code == 200, r.get_json()
    return next(x for x in _stored_rows() if x["pick_id"] == slot["pick_id"])


# ---------------------------------------------------------------------------
# T1 — the seeder (order route -> seed_pick_grid's own slot fallback)
# ---------------------------------------------------------------------------

def test_t1_seeded_grid_never_names_a_team_by_user_id(client, flag_on, mem_db):
    assert _seed(client, rounds=2).status_code == 200

    stored = _stored_rows()
    served = _slots(client)
    assert stored and len(served) == len(stored)
    for row in [*stored, *served]:
        _assert_no_id(row["owner_username"], _ALL_IDS)
        _assert_no_id(row["original_username"], _ALL_IDS)

    for row in stored:
        if row["original_user_id"] in NAMELESS:
            label = f"Team {row['original_roster_id']}"
            assert row["owner_username"] == label
            assert row["original_username"] == label
    assert {r["original_user_id"] for r in stored} >= set(NAMELESS)


# ---------------------------------------------------------------------------
# T2 — PUT to a nameless member who already has slots -> Team <their slot>
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("owner", NAMELESS)
def test_t2_put_to_nameless_member_stores_their_slot_label(
        client, flag_on, mem_db, owner):
    assert _seed(client, rounds=1).status_code == 200
    slots = _slots(client)
    their_slot = next(s["original_roster_id"] for s in slots
                      if s["original_user_id"] == owner)
    target = next(s for s in slots if s["original_user_id"] == ME)

    row = _assign(client, target, owner)
    assert row["owner_user_id"] == owner
    assert row["owner_username"] == f"Team {their_slot}"
    _assert_no_id(row["owner_username"], _ALL_IDS)


# ---------------------------------------------------------------------------
# T3 — PUT to a nameless member added AFTER seeding (no slot) -> Unnamed team
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("late", ["espn:{9F8E7D6C-LATE}", "acct_latecomer"])
def test_t3_put_to_slotless_nameless_member_stores_unnamed_team(
        client, flag_on, mem_db, late):
    assert _seed(client, rounds=1).status_code == 200
    with mem_db.begin() as conn:
        conn.execute(league_members_table.insert().values(
            league_id=LEAGUE, user_id=late, username=None,
            display_name="  ", roster_data="[]"))
    target = next(s for s in _slots(client) if s["original_user_id"] == ME)
    assert not any(r["original_user_id"] == late for r in _stored_rows())

    row = _assign(client, target, late)
    assert row["owner_user_id"] == late
    assert row["owner_username"] == "Unnamed team"
    _assert_no_id(row["owner_username"], [*_ALL_IDS, late])


# ---------------------------------------------------------------------------
# T4 — regression: a named member keeps their real name on both paths
# ---------------------------------------------------------------------------

def test_t4_named_members_keep_their_real_names(client, flag_on, mem_db):
    assert _seed(client, rounds=1).status_code == 200
    stored = _stored_rows()
    for uid, name in REAL_NAMES.items():
        mine = [r for r in stored if r["original_user_id"] == uid]
        assert mine
        assert all(r["owner_username"] == name for r in mine)
        assert all(r["original_username"] == name for r in mine)

    # PUT path: a nameless member's slot handed to a named member.
    target = next(s for s in _slots(client)
                  if s["original_user_id"] == SWID_MEMBER)
    row = _assign(client, target, NAMED)
    assert row["owner_username"] == "Riley"
