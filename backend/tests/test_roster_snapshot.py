"""S0 roster fingerprint (rfp1) and values snapshot id (vsn1).

Pins the canonical forms in scope-eng-200ms §6.1 (and models-eng's final vsn1):
what moves the ids, what must not, co-owners, the prefixes, and that vsn1
survives a simulated restart. In-memory SQLite only.
"""
import hashlib
import json

import pytest
from sqlalchemy import create_engine, insert, update

from backend import roster_snapshot as rs
from backend.database import (draft_picks_table, league_members_table, league_roster_state_table,
                              metadata)
from backend.ranking_service import Player

LEAGUE = "L1"


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    metadata.create_all(eng)
    rs._seed_memo.clear()
    return eng


def _member(conn, user_id, roster, *, league=LEAGUE, name=None):
    conn.execute(insert(league_members_table).values(
        league_id=league, user_id=user_id, username=name or user_id,
        display_name=name or user_id, roster_data=json.dumps(roster),
        updated_at="2026-10-20T00:00:00+00:00"))


def _pick(conn, pick_id, owner, *, league=LEAGUE, season=2027, rnd=1, orig="1", pool_value=10.0):
    conn.execute(insert(draft_picks_table).values(
        pick_id=pick_id, league_id=league, season=season, round=rnd,
        owner_user_id=owner, owner_username=f"name-{owner}", original_roster_id=orig,
        pick_value=50.0, pool_value=pool_value, platform="sleeper",
        synced_at="2026-10-20T00:00:00+00:00"))


def _seed(conn, *, reverse=False):
    rows = [("u1", ["10", "11"]), ("u2", ["20", "21"])]
    for uid, roster in (reversed(rows) if reverse else rows):
        _member(conn, uid, list(reversed(roster)) if reverse else roster)
    picks = [("L1_2027_1_1", "u1", "1"), ("L1_2027_1_2", "u2", "2")]
    for pid, owner, orig in (reversed(picks) if reverse else picks):
        _pick(conn, pid, owner, orig=orig)


def _fp(engine, league=LEAGUE):
    with engine.connect() as conn:
        return rs.roster_snapshot(conn, league).fp


def test_canonical_form_and_prefix(engine):
    with engine.begin() as conn:
        _seed(conn)
    expected = json.dumps({
        "v": 1,
        "members": [["u1", ["10", "11"]], ["u2", ["20", "21"]]],
        "picks": [["L1_2027_1_1", 2027, 1, "1", "u1"], ["L1_2027_1_2", 2027, 1, "2", "u2"]],
        "draft": {},
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    fp = _fp(engine)
    assert fp == "rfp1:" + hashlib.sha256(expected.encode()).hexdigest()[:32]
    assert fp.startswith("rfp1:") and len(fp) == len("rfp1:") + 32


def test_row_and_roster_order_do_not_matter(engine):
    other = create_engine("sqlite:///:memory:")
    metadata.create_all(other)
    with engine.begin() as conn:
        _seed(conn)
    with other.begin() as conn:
        _seed(conn, reverse=True)
    assert _fp(engine) == _fp(other)


def test_names_timestamps_and_values_do_not_move_the_fp(engine):
    with engine.begin() as conn:
        _seed(conn)
    before = _fp(engine)
    with engine.begin() as conn:
        conn.execute(update(league_members_table).values(
            username="renamed", display_name="Renamed Team", updated_at="2030-01-01"))
        conn.execute(update(draft_picks_table).values(
            owner_username="renamed", pick_value=1.0, pool_value=99.0, synced_at="2030-01-01"))
    assert _fp(engine) == before


@pytest.mark.parametrize("change", ["move_player", "move_pick", "add_member", "add_player"])
def test_ownership_changes_move_the_fp(engine, change):
    with engine.begin() as conn:
        _seed(conn)
    before = _fp(engine)
    with engine.begin() as conn:
        if change == "move_player":
            conn.execute(update(league_members_table)
                         .where(league_members_table.c.user_id == "u1")
                         .values(roster_data=json.dumps(["10"])))
            conn.execute(update(league_members_table)
                         .where(league_members_table.c.user_id == "u2")
                         .values(roster_data=json.dumps(["11", "20", "21"])))
        elif change == "move_pick":
            conn.execute(update(draft_picks_table)
                         .where(draft_picks_table.c.pick_id == "L1_2027_1_1")
                         .values(owner_user_id="u2"))
        elif change == "add_member":
            _member(conn, "u3", [])
        else:
            conn.execute(update(league_members_table)
                         .where(league_members_table.c.user_id == "u1")
                         .values(roster_data=json.dumps(["10", "11", "12"])))
    assert _fp(engine) != before


def test_other_leagues_rows_are_ignored(engine):
    with engine.begin() as conn:
        _seed(conn)
    before = _fp(engine)
    with engine.begin() as conn:
        _member(conn, "u9", ["99"], league="L2")
        _pick(conn, "L2_2027_1_1", "u9", league="L2")
    assert _fp(engine) == before


def test_asset_owner_players_picks_and_co_owners(engine):
    with engine.begin() as conn:
        _seed(conn)
        # Two rows holding the same roster (co-owners) share its assets.
        _member(conn, "u1b", ["10", "11"])
    with engine.connect() as conn:
        snap = rs.roster_snapshot(conn, LEAGUE)
    assert snap.asset_owner["10"] == frozenset({"u1", "u1b"})
    assert snap.asset_owner["20"] == frozenset({"u2"})
    assert snap.asset_owner["L1_2027_1_1"] == frozenset({"u1"})
    assert snap.asset_owner["L1_2027_1_2"] == frozenset({"u2"})
    assert "99" not in snap.asset_owner


def test_status_missing_unknown_and_refresh_record(engine):
    with engine.connect() as conn:
        empty = rs.roster_snapshot(conn, LEAGUE)
    assert (empty.status, empty.refreshed_at) == ("missing", None)
    with engine.begin() as conn:
        _seed(conn)
    with engine.connect() as conn:
        snap = rs.roster_snapshot(conn, LEAGUE)
    assert (snap.status, snap.refreshed_at) == ("unknown", None)

    # The table absent (a DB from before #378): still `unknown`, never `missing`.
    bare = create_engine("sqlite:///:memory:")
    metadata.create_all(bare, tables=[t for t in metadata.sorted_tables
                                      if t.name != "league_roster_state"])
    with bare.begin() as conn:
        _seed(conn)
    with bare.connect() as conn:
        snap = rs.roster_snapshot(conn, LEAGUE)
    assert (snap.status, snap.refreshed_at) == ("unknown", None)

    # platforms-eng's table (#378) with a row is read (checked once per engine).
    fresh = create_engine("sqlite:///:memory:")
    metadata.create_all(fresh)
    with fresh.begin() as conn:
        _seed(conn)
        conn.execute(insert(league_roster_state_table).values(
            league_id="L1", refreshed_at="2026-10-20T12:00:00+00:00", status="fresh",
            updated_at="2026-10-20T12:00:05+00:00"))
    with fresh.connect() as conn:
        snap = rs.roster_snapshot(conn, LEAGUE)
    assert (snap.status, snap.refreshed_at) == ("fresh", "2026-10-20T12:00:00+00:00")
    assert snap.fp == _fp(engine)   # the refresh record is not a fingerprint input


# ── vsn1 ─────────────────────────────────────────────────────────────────────

def _pool(elo=1600.0, age=24):
    players = [Player(id="10", name="A", position="RB", team="X", age=age),
               Player(id="20", name="B", position="WR", team="Y", age=27)]
    return {"players": players, "seed": {"20": 1500.5, "10": elo}}


def _vsn(engine, pool, *, league=LEAGUE, generation=1, fmt="1qb_ppr"):
    with engine.connect() as conn:
        return rs.values_snapshot_id(conn, fmt, league, pool, generation=generation)


def test_vsn_canonical_form(engine):
    with engine.begin() as conn:
        _seed(conn)
    expected = json.dumps({
        "v": 1, "fmt": "1qb_ppr",
        "seed": [["10", 1600.0, 24], ["20", 1500.5, 27]],
        "picks": [["L1_2027_1_1", 10.0], ["L1_2027_1_2", 10.0]],
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    vsn = _vsn(engine, _pool())
    assert vsn == "vsn1:" + hashlib.sha256(expected.encode()).hexdigest()[:32]
    assert vsn.startswith("vsn1:") and len(vsn) == len("vsn1:") + 32


def test_vsn_stable_across_a_simulated_restart(engine):
    with engine.begin() as conn:
        _seed(conn)
    before = _vsn(engine, _pool(), generation=7)
    rs._seed_memo.clear()                        # a new process: empty memo...
    assert _vsn(engine, _pool(), generation=1) == before   # ...and a reset generation


def test_vsn_memo_follows_generation_and_seed_object(engine):
    with engine.begin() as conn:
        _seed(conn)
    pool = _pool()
    first = _vsn(engine, pool, generation=3)
    # A rebuilt pool (new seed map) is recomputed even before the generation bump.
    assert _vsn(engine, _pool(elo=1700.0), generation=3) != first
    assert _vsn(engine, _pool(), generation=4) == first


@pytest.mark.parametrize("change", ["seed_elo", "age", "pick_pool_value"])
def test_vsn_changes_on_value_inputs(engine, change):
    with engine.begin() as conn:
        _seed(conn)
    before = _vsn(engine, _pool())
    pool = _pool()
    if change == "seed_elo":
        pool = _pool(elo=1601.0)
    elif change == "age":
        pool = _pool(age=25)
    else:
        with engine.begin() as conn:
            conn.execute(update(draft_picks_table)
                         .where(draft_picks_table.c.pick_id == "L1_2027_1_1")
                         .values(pool_value=11.5))
    assert _vsn(engine, pool, generation=2) != before


def test_vsn_differs_between_leagues_with_different_picks(engine):
    with engine.begin() as conn:
        _seed(conn)
        _pick(conn, "L2_2027_1_1", "u9", league="L2", pool_value=3.0)
    assert _vsn(engine, _pool(), league="L1") != _vsn(engine, _pool(), league="L2")


def test_vsn_ignores_roster_and_names(engine):
    with engine.begin() as conn:
        _seed(conn)
    before = _vsn(engine, _pool())
    with engine.begin() as conn:
        conn.execute(update(league_members_table).values(roster_data="[]", display_name="x"))
        conn.execute(update(draft_picks_table).values(owner_user_id="u2", owner_username="x"))
    assert _vsn(engine, _pool()) == before


def test_snapshot_ids_matches_the_standalone_functions(engine):
    with engine.begin() as conn:
        _seed(conn)
    with engine.connect() as conn:
        snap, vsn = rs.snapshot_ids(conn, "1qb_ppr", LEAGUE, _pool(), generation=1)
        assert snap == rs.roster_snapshot(conn, LEAGUE)
        assert vsn == rs.values_snapshot_id(conn, "1qb_ppr", LEAGUE, _pool())


# ── on_roster_change registry ────────────────────────────────────────────────

def test_on_roster_change_notifies_handlers(monkeypatch):
    calls = []
    monkeypatch.setattr(rs, "_roster_change_handlers", [])

    def boom(*args):
        raise RuntimeError("handler failure")

    def record(*args):
        calls.append(args)

    rs.register_roster_change_handler(boom)
    rs.register_roster_change_handler(record)
    rs.register_roster_change_handler(record)    # idempotent
    rs.on_roster_change("L1", "rfp1:old", "rfp1:new")
    rs.on_roster_change("L1", "rfp1:same", "rfp1:same")
    assert calls == [("L1", "rfp1:old", "rfp1:new")]
