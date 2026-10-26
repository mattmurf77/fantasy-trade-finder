"""S0 roster fingerprint (rfp1) and values snapshot id (vsn1), contract v0.4.

Pins the canonical forms (§2, §6): what moves the ids and what must not; the
pick row set being exactly the engine's (`load_draft_picks` with
`pick_source`, contested/orphaned filter included); the draft state; the
player-id filter; co-owners; the §3 status table; that vsn1 survives a
simulated restart; and the on_roster_change call contract. In-memory SQLite
only, with `database.engine` patched (load_draft_picks and
is_linked_platform_league read through it).
"""
import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, insert, update

import backend.database as db_module
from backend import roster_snapshot as rs
from backend.database import (draft_picks_table, league_members_table, league_roster_state_table,
                              leagues_table, metadata)
from backend.ranking_service import Player

LEAGUE = "L1"
NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
PLATFORM, ANY = "platform", "any"


def _iso(seconds_ago):
    return (NOW - timedelta(seconds=seconds_ago)).isoformat()


def _engine(monkeypatch, *, tables=None):
    eng = create_engine("sqlite:///:memory:")
    metadata.create_all(eng, tables=tables)
    monkeypatch.setattr(db_module, "engine", eng)
    return eng


@pytest.fixture()
def engine(monkeypatch):
    rs._seed_memo.clear()
    with db_module._CONTESTED_LOCK:
        db_module._CONTESTED_CACHE.clear()
    return _engine(monkeypatch)


def _member(conn, user_id, roster, *, league=LEAGUE, name=None, updated_at=None):
    conn.execute(insert(league_members_table).values(
        league_id=league, user_id=user_id, username=name or user_id,
        display_name=name or user_id, roster_data=json.dumps(roster),
        updated_at=updated_at or _iso(60)))


def _pick(conn, pick_id, owner, *, league=LEAGUE, season=2027, rnd=1, orig="1",
          pool_value=10.0, source=None):
    conn.execute(insert(draft_picks_table).values(
        pick_id=pick_id, league_id=league, season=season, round=rnd,
        owner_user_id=owner, owner_username=f"name-{owner}", original_roster_id=orig,
        pick_value=50.0, pool_value=pool_value, platform="sleeper", source=source,
        synced_at="2026-10-20T00:00:00+00:00"))


def _seed(conn, *, reverse=False):
    rows = [("u1", ["10", "11"]), ("u2", ["20", "21"])]
    for uid, roster in (reversed(rows) if reverse else rows):
        _member(conn, uid, list(reversed(roster)) if reverse else roster)
    picks = [("L1_2027_1_1", "u1", "1"), ("L1_2027_1_2", "u2", "2")]
    for pid, owner, orig in (reversed(picks) if reverse else picks):
        _pick(conn, pid, owner, orig=orig)


def _snap(engine, league=LEAGUE, pick_source=PLATFORM, **kw):
    with engine.connect() as conn:
        return rs.roster_snapshot(conn, league, pick_source=pick_source, now=NOW, **kw)


def _fp(engine, league=LEAGUE, pick_source=PLATFORM):
    return _snap(engine, league, pick_source).fp


# ── rfp1: canonical form ─────────────────────────────────────────────────────

def test_canonical_form_and_prefix(engine):
    with engine.begin() as conn:
        _seed(conn)
    expected = json.dumps({
        "v": 1,
        "members": [["u1", ["10", "11"]], ["u2", ["20", "21"]]],
        "picks": [["L1_2027_1_1", 2027, 1, "1", "u1", "platform"],
                  ["L1_2027_1_2", 2027, 1, "2", "u2", "platform"]],
        "draft": {"drafted": False},
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    fp = _fp(engine)
    assert fp == "rfp1:" + hashlib.sha256(expected.encode()).hexdigest()[:32]
    assert fp.startswith("rfp1:") and len(fp) == len("rfp1:") + 32


def test_row_and_roster_order_do_not_matter(engine, monkeypatch):
    with engine.begin() as conn:
        _seed(conn)
    first = _fp(engine)
    other = _engine(monkeypatch)
    with other.begin() as conn:
        _seed(conn, reverse=True)
    assert _fp(other) == first


def test_bad_player_ids_are_filtered(engine, monkeypatch):
    """G-004: None, "" and "None" are never assets, and never fingerprint inputs."""
    with engine.begin() as conn:
        _seed(conn)
    clean = _fp(engine)
    other = _engine(monkeypatch)
    with other.begin() as conn:
        _seed(conn)
        conn.execute(update(league_members_table).where(league_members_table.c.user_id == "u1")
                     .values(roster_data=json.dumps(["10", None, "", "None", "11"])))
    snap = _snap(other)
    assert snap.fp == clean
    assert not {"", "None"} & set(snap.asset_owner)


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


@pytest.mark.parametrize("change", ["move_player", "move_pick", "add_member", "add_player",
                                    "null_pick_owner"])
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
        elif change == "add_player":
            conn.execute(update(league_members_table)
                         .where(league_members_table.c.user_id == "u1")
                         .values(roster_data=json.dumps(["10", "11", "12"])))
        else:   # a NULL owner stays in the canonical form, as null
            conn.execute(update(draft_picks_table)
                         .where(draft_picks_table.c.pick_id == "L1_2027_1_1")
                         .values(owner_user_id=None))
    assert _fp(engine) != before


@pytest.mark.parametrize("status, moves", [("drafted", True), ("not_drafted", False),
                                           ("unknown", False), (None, False)])
def test_draft_state_is_normalized(engine, status, moves):
    with engine.begin() as conn:
        _seed(conn)
        conn.execute(insert(leagues_table).values(sleeper_league_id=LEAGUE, user_id="u1",
                                                  draft_status=None))
    before = _fp(engine)
    with engine.begin() as conn:
        conn.execute(update(leagues_table).values(draft_status=status))
    assert (_fp(engine) != before) is moves


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
        _member(conn, "u1b", ["10", "11"])      # two rows holding one roster share its assets
    snap = _snap(engine)
    assert snap.asset_owner["10"] == frozenset({"u1", "u1b"})
    assert snap.asset_owner["20"] == frozenset({"u2"})
    assert snap.asset_owner["L1_2027_1_1"] == frozenset({"u1"})
    assert snap.asset_owner["L1_2027_1_2"] == frozenset({"u2"})
    assert "99" not in snap.asset_owner


# ── picks: exactly the engine's row set ──────────────────────────────────────

def test_pick_rows_follow_pick_source_and_carry_their_source(engine):
    """`platform` reads platform rows only; `any` adds asserted (`user`) rows."""
    with engine.begin() as conn:
        _seed(conn)
        _pick(conn, "L1_2028_1_1", "u1", season=2028, source="user")
    platform, any_ = _snap(engine, pick_source=PLATFORM), _snap(engine, pick_source=ANY)
    assert "L1_2028_1_1" not in platform.asset_owner
    assert any_.asset_owner["L1_2028_1_1"] == frozenset({"u1"})
    assert platform.fp != any_.fp
    with engine.begin() as conn:     # the same row platform-sourced: the source moves the fp
        conn.execute(update(draft_picks_table)
                     .where(draft_picks_table.c.pick_id == "L1_2028_1_1").values(source=None))
    assert _fp(engine, pick_source=ANY) != any_.fp


def test_contested_and_orphaned_rows_are_filtered_like_the_engine(engine, monkeypatch):
    """The filter is load_draft_picks' own (database._excluded_pick_ids)."""
    with engine.begin() as conn:
        _seed(conn)
        _pick(conn, "L1_2028_1_1", "u1", season=2028, source="user")
        _pick(conn, "L1_2028_1_2", "u2", season=2028, source="user")
    before = _snap(engine, pick_source=ANY)
    monkeypatch.setattr(db_module, "_excluded_pick_ids",
                        lambda lid: (frozenset({"L1_2028_1_1"}), frozenset({"L1_2028_1_2"})))
    after = _snap(engine, pick_source=ANY)
    assert {"L1_2028_1_1", "L1_2028_1_2"} <= set(before.asset_owner)
    assert not {"L1_2028_1_1", "L1_2028_1_2"} & set(after.asset_owner)
    assert after.fp != before.fp
    assert {pick["pick_id"] for pick in db_module.load_draft_picks(LEAGUE, source=ANY)} == \
        {pid for pid in after.asset_owner if pid.startswith("L1_")}


# ── §3 status table ──────────────────────────────────────────────────────────

def _state(conn, *, status, refreshed_at, error=None, league=LEAGUE):
    conn.execute(insert(league_roster_state_table).values(
        league_id=league, status=status, refreshed_at=refreshed_at, last_error_code=error,
        updated_at=_iso(0)))


def test_status_missing_without_member_rows(engine):
    with engine.begin() as conn:
        _pick(conn, "L1_2027_1_1", "u1")
    snap = _snap(engine)
    assert (snap.status, snap.refreshed_at, snap.age_s) == ("missing", None, None)


def test_status_unknown_for_sleeper_without_a_state_row_or_table(engine, monkeypatch):
    with engine.begin() as conn:
        _seed(conn)
    snap = _snap(engine)
    assert (snap.status, snap.refreshed_at, snap.linked) == ("unknown", None, False)
    assert snap.age_s == 60.0                     # the newest league_members.updated_at
    bare = _engine(monkeypatch, tables=[t for t in metadata.sorted_tables
                                        if t.name != "league_roster_state"])
    with bare.begin() as conn:
        _seed(conn)
    assert _snap(bare).status == "unknown"


@pytest.mark.parametrize("stored, refreshed, error, status, age", [
    ("fresh", 30, None, "fresh", 30.0),
    ("stale", 600, "http_5xx", "stale", 600.0),
    ("stale", None, "http_5xx", "stale", 60.0),   # NULL refreshed_at: age from the newest row
    ("stale", 600, "write_failed", "unknown", 600.0),   # C-e: a failed session write
])
def test_status_from_the_sleeper_state_row(engine, stored, refreshed, error, status, age):
    with engine.begin() as conn:
        _seed(conn)
        _state(conn, status=stored, refreshed_at=None if refreshed is None else _iso(refreshed),
               error=error)
    snap = _snap(engine)
    assert (snap.status, snap.age_s, snap.linked) == (status, age, False)
    assert snap.refreshed_at == (None if refreshed is None else _iso(refreshed))


@pytest.mark.parametrize("newest_age, status", [(3600, "fresh"), (90000, "stale")])
def test_status_for_a_linked_platform_by_import_age(engine, newest_age, status):
    with engine.begin() as conn:
        conn.execute(insert(leagues_table).values(sleeper_league_id=LEAGUE, user_id="u1",
                                                  platform="espn"))
        _member(conn, "u1", ["10"], updated_at=_iso(newest_age + 500))
        _member(conn, "u2", ["20"], updated_at=_iso(newest_age))
    snap = _snap(engine, import_fresh_s=86400)
    assert (snap.status, snap.linked, snap.age_s) == (status, True, float(newest_age))
    assert snap.refreshed_at == _iso(newest_age)


def test_a_missing_table_is_rechecked_not_cached(monkeypatch):
    """release-lead #367: only "the table exists" is cached."""
    bare = _engine(monkeypatch, tables=[t for t in metadata.sorted_tables
                                        if t.name != "league_roster_state"])
    with bare.begin() as conn:
        _seed(conn)
    assert _snap(bare).status == "unknown"
    league_roster_state_table.create(bare)
    with bare.begin() as conn:
        _state(conn, status="fresh", refreshed_at=_iso(10))
    assert _snap(bare).status == "fresh"


# ── vsn1 ─────────────────────────────────────────────────────────────────────

def _pool(elo=1600.0, age=24):
    players = [Player(id="10", name="A", position="RB", team="X", age=age),
               Player(id="20", name="B", position="WR", team="Y", age=27)]
    return {"players": players, "seed": {"20": 1500.5, "10": elo}}


def _vsn(engine, pool, *, league=LEAGUE, generation=1, fmt="1qb_ppr", pick_source=PLATFORM):
    with engine.connect() as conn:
        return rs.values_snapshot_id(conn, fmt, league, pool, pick_source=pick_source,
                                     generation=generation)


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
    rs._seed_memo.clear()                                   # a new process: empty memo...
    assert _vsn(engine, _pool(), generation=1) == before    # ...and a reset generation


def test_vsn_memo_follows_generation_and_seed_object(engine):
    with engine.begin() as conn:
        _seed(conn)
    first = _vsn(engine, _pool(), generation=3)
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


def test_vsn_reads_the_engine_pick_rows(engine):
    with engine.begin() as conn:
        _seed(conn)
        _pick(conn, "L1_2028_1_1", "u1", season=2028, source="user", pool_value=4.0)
    assert _vsn(engine, _pool(), pick_source=PLATFORM) != _vsn(engine, _pool(), pick_source=ANY)


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
        ids = rs.snapshot_ids(conn, "1qb_ppr", LEAGUE, _pool(), pick_source=ANY, generation=1)
        assert ids == (rs.roster_snapshot(conn, LEAGUE, pick_source=ANY).fp,
                       rs.values_snapshot_id(conn, "1qb_ppr", LEAGUE, _pool(), pick_source=ANY))


def test_seed_memo_is_consistent_under_threads():
    """E1 (#367): the memo is guarded; concurrent readers agree. (No DB: an
    in-memory SQLite database is per thread.)"""
    rs._seed_memo.clear()
    pool, picks, results, errors = _pool(), [{"pick_id": "L1_2027_1_1", "pool_value": 10.0}], [], []

    def run():
        try:
            for generation in range(20):
                results.append(rs._values_snapshot_id("1qb_ppr", pool, picks, generation % 3))
        except Exception as exc:     # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(set(results)) == 1


# ── on_roster_change registry (A3) ───────────────────────────────────────────

def test_on_roster_change_call_contract(monkeypatch):
    calls = []
    monkeypatch.setattr(rs, "_roster_change_handlers", [])

    def boom(*args):
        raise RuntimeError("handler failure")

    def record(*args):
        calls.append(args)

    rs.register_roster_change_handler(boom)
    rs.register_roster_change_handler(record)
    rs.register_roster_change_handler(record)              # registration dedupes
    rs.on_roster_change("L1", None, "rfp1:first")          # a league's first stamp
    rs.on_roster_change("L1", "rfp1:first", "rfp1:next")   # boom is caught; record still runs
    rs.on_roster_change("L1", "rfp1:same", "rfp1:same")    # equal fps: no call
    assert calls == [("L1", None, "rfp1:first"), ("L1", "rfp1:first", "rfp1:next")]
