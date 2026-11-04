"""Pick-assignment grid: a user id is never stored or served as a team name.

Scope: `docs/plans/draft-extensions/scope-pick-grid-name-fallback.md`.

A member with no `username` / `display_name` used to be named
`Team <user_id>` by `server._assignment_members`, and the PUT writer fell
back to the same string. For a non-FTF ESPN manager that is
`Team espn:{SWID}`; for a fresh sign-in, `Team acct_*` — served to every
other member of the league. Both writers now fall back to the SLOT label,
`Team <original_roster_id>`, and to `Unnamed team` when the member has no
slot yet.

T5-T9 (#497 QA P2): rows stored BEFORE the fix keep `Team <user id>` or a
blank name, and no write path repairs them, so every client-facing reader
heals them at read time through `database.pick_team_name`. Those tests write
the pre-fix shapes straight into `draft_picks` and read them back.

Production-shape members, real routes, in-memory SQLite (the live DB is
never opened). Harness mirrors `test_pick_assignment.py`.
"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, update

import backend.blind_grading as bg
import backend.database as db
import backend.feature_flags as ff
import backend.server as server
from backend.database import (metadata, leagues_table, league_members_table,
                              draft_picks_table)

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


# ---------------------------------------------------------------------------
# T5-T9 — rows stored BEFORE #497 are healed on every client-facing read
# ---------------------------------------------------------------------------

LEGACY_SWID = f"Team {SWID_MEMBER}"      # the pre-fix id fallback
BLANK = "   "                            # the pre-fix whitespace-only name


def _write_legacy(engine):
    """Seed a 1-round grid, then write the pre-fix shapes straight into
    `draft_picks`, bypassing every writer. Returns `{user_id: slot}`.

      * SWID's own rows: both names `Team espn:{…}`; its SEASON pick is
        traded to ME (so a trade label reads "from Team espn:{…}").
      * ACCT's own rows: both names whitespace; its SEASON+1 pick is traded
        to NAMED.
      * ME's SEASON pick traded to SWID, NAMED's SEASON pick traded to ACCT,
        each with the pre-fix owner name.
    """
    slot = {r["original_user_id"]: r["original_roster_id"] for r in _stored_rows()}
    t = draft_picks_table

    def _set(orig, season=None, **values):
        where = (t.c.league_id == LEAGUE) & (t.c.original_user_id == orig)
        if season is not None:
            where &= t.c.season == season
        with engine.begin() as conn:
            conn.execute(update(t).where(where).values(**values))

    _set(SWID_MEMBER, owner_username=LEGACY_SWID, original_username=LEGACY_SWID)
    _set(ACCT_MEMBER, owner_username=BLANK, original_username=BLANK)
    _set(SWID_MEMBER, SEASON, owner_user_id=ME, owner_username="Dana", is_traded=1)
    _set(ACCT_MEMBER, SEASON + 1, owner_user_id=NAMED, owner_username="Riley",
         is_traded=1)
    _set(ME, SEASON, owner_user_id=SWID_MEMBER, owner_username=LEGACY_SWID,
         is_traded=1)
    _set(NAMED, SEASON, owner_user_id=ACCT_MEMBER, owner_username=BLANK,
         is_traded=1)
    db.invalidate_pick_assignment_cache(LEAGUE)
    return slot


def _expected(row, slot):
    """`(original, owner)` a client must see for a `_write_legacy` row."""
    def name(uid):
        return f"Team {slot[uid]}" if uid in NAMELESS else REAL_NAMES[uid]
    return name(row["original_user_id"]), name(row["owner_user_id"])


def _assert_served(rows, slot):
    for s in rows:
        _assert_no_id(s["original_username"], _ALL_IDS)
        _assert_no_id(s["owner_username"], _ALL_IDS)
        assert (s["original_username"], s["owner_username"]) == _expected(s, slot), s


@pytest.fixture()
def tradeable_on(flag_on):
    ff._flags_cache = {**ff._flags_cache, "picks.assign_tradeable": True,
                       "trade.picks_in_pool": True}


def test_t5_get_heals_pre_fix_names_on_both_sides(client, flag_on, mem_db):
    assert _seed(client, rounds=1).status_code == 200
    slot = _write_legacy(mem_db)

    served = _slots(client)
    assert len(served) == 16
    _assert_served(served, slot)

    # Read-time only: the stored rows still hold the pre-fix shapes.
    stored = {r["original_user_id"]: r for r in _stored_rows()
              if r["season"] == SEASON + 3}
    assert stored[SWID_MEMBER]["original_username"] == LEGACY_SWID
    assert stored[ACCT_MEMBER]["owner_username"] == BLANK


def test_t6_put_responses_are_healed(client, flag_on, mem_db):
    assert _seed(client, rounds=1).status_code == 200
    slot = _write_legacy(mem_db)
    slots = {(s["original_user_id"], s["season"]): s for s in _slots(client)}

    # 409: the conflict row is the whole current row, healed.
    stale = slots[(ACCT_MEMBER, SEASON + 2)]
    r = _put(client, stale["pick_id"], owner_user_id=NAMED,
             if_assigned_at="1999-01-01T00:00:00+00:00")
    assert r.status_code == 409
    _assert_served([r.get_json()["current"]], slot)

    # 200: a PUT rewrites only owner_username, so the original side it serves
    # is the guard's, and the stored original keeps the pre-fix id.
    target = slots[(SWID_MEMBER, SEASON + 1)]
    r = _put(client, target["pick_id"], owner_user_id=NAMED,
             if_assigned_at=target["assigned_at"])
    assert r.status_code == 200
    body = r.get_json()["slot"]
    assert body["owner_username"] == "Riley"
    assert body["original_username"] == f"Team {slot[SWID_MEMBER]}"
    stored = next(x for x in _stored_rows() if x["pick_id"] == target["pick_id"])
    assert stored["original_username"] == LEGACY_SWID


def test_t7_draft_room_grid_is_healed(client, flag_on, mem_db):
    assert _seed(client, rounds=1).status_code == 200
    slot = _write_legacy(mem_db)

    body = client.get(f"/api/draft/board?league_id={LEAGUE}",
                      headers=_hdr()).get_json()
    order = body["order"]
    assert len(order) == len(MEMBERS)
    _assert_served(order, slot)


@pytest.fixture()
def traded_legacy(client, tradeable_on, mem_db):
    """`(slot, want)`: the pre-fix grid, and the "(from …)" suffix each of
    the two traded-away legacy picks must carry on a trade label."""
    assert _seed(client, rounds=1).status_code == 200
    slot = _write_legacy(mem_db)
    want = {db.make_pick_id(LEAGUE, SEASON, 1, slot[SWID_MEMBER]):
            f"(from Team {slot[SWID_MEMBER]})",
            db.make_pick_id(LEAGUE, SEASON + 1, 1, slot[ACCT_MEMBER]):
            f"(from Team {slot[ACCT_MEMBER]})"}
    return slot, want


def _check_labels(labels, want):
    for pid, suffix in want.items():
        assert labels[pid].endswith(suffix), labels[pid]
        _assert_no_id(labels[pid], _ALL_IDS)


def test_t8a_calculator_pick_labels_and_names_are_healed(client, traded_legacy):
    """`/api/league/picks`: the label, and the raw name fields it spreads."""
    slot, want = traded_legacy
    picks = client.get(f"/api/league/picks?league_id={LEAGUE}",
                       headers=_hdr()).get_json()["all_picks"]
    assert len(picks) == 16
    _check_labels({p["pick_id"]: p["label"] for p in picks}, want)
    _assert_served(picks, slot)


def test_t8b_generated_suggestion_pick_labels_are_healed(traded_legacy):
    """The engine's pick assets, which name a pick on a trade card."""
    _, want = traded_legacy
    _check_labels({p.id: p.name for ps in server._owned_pick_assets(LEAGUE).values()
                   for p in ps}, want)


def test_t8c_matches_pick_labels_are_healed(traded_legacy):
    """The Matches overlay, which selects its own columns."""
    _, want = traded_legacy
    _check_labels(server._pick_labels_by_id(list(want)), want)


def test_t8d_calibration_pick_labels_are_healed(traded_legacy):
    """Calibration's catalog (blind_grading never imports server)."""
    _, want = traded_legacy
    _, _, catalog = bg._league_inputs(LEAGUE, ME, datetime.now(timezone.utc))
    _check_labels({pid: catalog.assets[pid]["name"] for pid in want}, want)


@pytest.mark.parametrize("kept", ["Riley's Rejects", "Team Rocket", "slot"],
                         ids=["real-name", "team-rocket", "team-slot"])
def test_t9_good_stored_names_pass_through(client, flag_on, mem_db,
                                           monkeypatch, kept):
    """A name that is not blank and not `Team <that user id>` is served
    verbatim. The fallback is swapped for a sentinel, so a pass-through and a
    heal that happens to produce the same string cannot be confused."""
    assert _seed(client, rounds=1).status_code == 200
    slot = _write_legacy(mem_db)
    if kept == "slot":
        kept = f"Team {slot[SWID_MEMBER]}"
    with mem_db.begin() as conn:
        conn.execute(update(draft_picks_table)
                     .where(draft_picks_table.c.original_user_id == SWID_MEMBER)
                     .values(original_username=kept, owner_username=kept))
    monkeypatch.setattr(db, "pick_slot_team_name", lambda rows, uid: "HEALED")

    served = _slots(client)
    swid = [s for s in served if s["original_user_id"] == SWID_MEMBER]
    assert swid and all(s["original_username"] == kept for s in swid)
    assert all(s["owner_username"] == kept for s in swid
               if s["owner_user_id"] == SWID_MEMBER)
    # The sentinel is live: the whitespace rows still heal through it.
    acct = [s for s in served if s["original_user_id"] == ACCT_MEMBER]
    assert acct and all(s["original_username"] == "HEALED" for s in acct)
