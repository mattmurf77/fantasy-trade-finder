"""draft-extensions W3 M-A — ESPN pick assignment: store, seeder, routes.

Plan `docs/plans/draft-extensions/plan.md` §6 (REVISED) + the operator-decision
block; LLD §2.4 / §3.1 / §4.3; ADR-010.

This wave REVERSES a documented invariant — `draft_picks.platform` used to say
"ESPN never writes rows" — so the safety story cannot live in a comment. Every
load-bearing claim is pinned here:

  * **Containment by default (D12).** `load_draft_picks` defaults to
    platform-only, `NULL` reads as platform, and an AST test enumerates every
    call site: exactly the sanctioned ones may name `source=`. A new
    unsanctioned site fails the test rather than silently joining the union.
  * **A writer only ever deletes rows it could have written (INV-2).**
  * **No user-entered values, EVER (D13).** Every route rejects a value field
    at the edge, and every asserted row's price is byte-equal to the SHIPPED
    `pick_pool_value`, checked through `priced_pool_value` under BOTH M6b
    pricing modes.
  * **The conservation bound (INV-4).** Ownership can be redistributed, never
    created; `rounds` is clamped server-side.
  * **Contested/orphaned ⇒ unpriced by ROW FILTER (INV-5)** — never by nulling
    `pool_value`, which `_power_picks_by_owner` would silently re-derive.
  * **CAS (D16).** A stale token 409s WITH the current row; different slots
    never collide.
"""
import ast
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_taxonomy as taxonomy
import backend.database as db
import backend.feature_flags as ff
import backend.server as server
from backend.database import (
    metadata, leagues_table, league_members_table, draft_picks_table,
)
from backend.pick_values import pick_pool_value, priced_pool_value

REPO = Path(__file__).resolve().parents[2]
SERVER_PATH = REPO / "backend" / "server.py"
DATABASE_PATH = REPO / "backend" / "database.py"

LEAGUE = "1099887766554433221"          # numeric — an ESPN-shaped league id
ME = "u1"
MEMBERS = ["u1", "u2", "u3", "u4"]
NAMES = {u: f"Team {u}" for u in MEMBERS}
SEASON = 2026
TOKEN = "test-token-w3-ma"


# ---------------------------------------------------------------------------
# harness — in-memory SQLite throughout; data/trade_finder.db is never opened
# ---------------------------------------------------------------------------

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
        for uid in MEMBERS:
            conn.execute(league_members_table.insert().values(
                league_id=LEAGUE, user_id=uid, username=NAMES[uid],
                display_name=NAMES[uid], roster_data="[]"))
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
    sess = {
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


@pytest.fixture()
def flag_off():
    saved = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS}
    try:
        yield
    finally:
        ff._flags_cache = saved


def _hdr():
    return {"X-Session-Token": TOKEN, "Content-Type": "application/json"}


def _seed(client, **body):
    return client.post("/api/league/pick-assignments/order", headers=_hdr(),
                       data=json.dumps({"league_id": LEAGUE, **body}))


def _get(client):
    return client.get(f"/api/league/pick-assignments?league_id={LEAGUE}",
                      headers=_hdr())


def _put(client, pick_id, **body):
    return client.put(f"/api/league/pick-assignments/{pick_id}", headers=_hdr(),
                      data=json.dumps({"league_id": LEAGUE, **body}))


#: A slot label no member holds, so the platform grid and the asserted grid
#: do not collide on `pick_id` (whose unique key has no provenance dimension).
_PLATFORM_SLOT = "99"


def _platform_rows(league_id=LEAGUE, n=4, slot=_PLATFORM_SLOT):
    """Pre-W3-shaped rows: `source` absent entirely, exactly like every row
    already in production."""
    return [{
        "pick_id": db.make_pick_id(league_id, SEASON, r, slot),
        "league_id": league_id, "season": SEASON, "round": r,
        "owner_user_id": "u1", "owner_username": "Team u1",
        "original_roster_id": slot, "original_user_id": "u1",
        "original_username": "Team u1", "is_traded": 0,
        "pick_value": 10.0 * r, "pool_value": 100.0 * r,
        "platform": "sleeper", "synced_at": "2026-08-01T00:00:00+00:00",
    } for r in range(1, n + 1)]


# ---------------------------------------------------------------------------
# D12 — containment by default (AST + behaviour)
# ---------------------------------------------------------------------------

def _calls_named(tree: ast.AST, name: str):
    """(enclosing function name, keyword names) for every call to `name`."""
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def _enclosing(node):
        cur = parents.get(node)
        while cur is not None and not isinstance(
                cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cur = parents.get(cur)
        return cur.name if cur is not None else "<module>"

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        called = fn.id if isinstance(fn, ast.Name) else (
            fn.attr if isinstance(fn, ast.Attribute) else None)
        if called == name:
            out.append((_enclosing(node),
                        {k.arg for k in node.keywords if k.arg}))
    return out


#: THE seven read sites, by SYMBOL (line numbers drift; symbols do not).
#: In M-A none of them named `source=`. **W3 M-C opted all seven in, together**
#: (plan §6.4 + operator decision 4 — full engine parity), each passing
#: `source=_pick_read_source()`, which is `'platform'` (the shipped default)
#: with `picks.assign_tradeable` off and `'any'` with it on. Editing this set
#: is how an eighth site gets DECIDED rather than silently added.
_SEVEN_READ_SITES = frozenset({
    "_roster_eveners", "_user_pick_share", "_run_trade_job",
    "_trade_evaluate_impl", "get_league_picks", "_owned_pick_assets",
    "_power_picks_by_owner",
})

#: The assignment surface's own reads. These name a LITERAL provenance
#: (`PICK_SOURCE_USER`) rather than the flag-gated helper, because they are
#: the screens on which assertions are seen and fixed.
_SANCTIONED_SOURCE_CALLERS = frozenset({
    "seed_pick_grid",            # database.py — reads its own provenance only
    "_assignment_slots",         # server.py  — the assignment screen's payload
    "_assignment_grid",          # server.py  — the ESPN board's grid
    "pick_assignment_put_route", # server.py  — the prior-owner read for audit
})

#: Everything allowed to name `source=` at all: the seven engine read sites
#: plus the assignment surface. Nothing else.
_SANCTIONED_SOURCE_OPT_INS = _SEVEN_READ_SITES | _SANCTIONED_SOURCE_CALLERS


def test_w3_02_ast_only_sanctioned_call_sites_name_source():
    """D12 — the AST enumeration. Copies the shipped `test_m3_07` pattern.

    Three assertions, and each catches a different regression:
      1. a NEW site opting into asserted rows (the silent widening);
      2. one of the seven DROPPING its opt-in (asserted picks would vanish
         from that surface while still pricing everywhere else);
      3. any site left on the bare default, which after M-C means a read that
         is invisible to the flag.
    """
    seen_default, seen_source = set(), set()
    for path in (SERVER_PATH, DATABASE_PATH):
        for enclosing, kwargs in _calls_named(ast.parse(path.read_text()),
                                              "load_draft_picks"):
            (seen_source if "source" in kwargs else seen_default).add(enclosing)

    assert seen_source <= _SANCTIONED_SOURCE_OPT_INS, (
        "an unsanctioned call site opts into asserted picks: "
        f"{sorted(seen_source - _SANCTIONED_SOURCE_OPT_INS)}")
    assert _SANCTIONED_SOURCE_OPT_INS <= seen_source, (
        "a sanctioned site stopped naming source=: "
        f"{sorted(_SANCTIONED_SOURCE_OPT_INS - seen_source)}")
    assert seen_default == frozenset(), (
        "load_draft_picks call site(s) on the bare default after M-C — a read "
        "the `picks.assign_tradeable` switch cannot reach: "
        f"{sorted(seen_default)}")


def test_w3_02d_the_seven_read_sites_go_through_the_ONE_flag_helper():
    """M-C's opt-in is a helper call, never a literal.

    `source=PICK_SOURCE_ANY` hard-coded at a read site would price asserted
    picks with the kill switch OFF — the one failure the two-flag design
    exists to prevent. Every one of the seven must pass
    `_pick_read_source()`, and only the assignment surface may name a literal.
    """
    tree = ast.parse(SERVER_PATH.read_text())
    parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}

    def _enclosing(node):
        cur = parents.get(node)
        while cur is not None and not isinstance(cur, ast.FunctionDef):
            cur = parents.get(cur)
        return cur.name if cur is not None else "<module>"

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "load_draft_picks"):
            continue
        fn = _enclosing(node)
        if fn not in _SEVEN_READ_SITES:
            continue
        kw = next(k for k in node.keywords if k.arg == "source")
        assert (isinstance(kw.value, ast.Call)
                and isinstance(kw.value.func, ast.Name)
                and kw.value.func.id == "_pick_read_source"), (
            f"{fn} passes a literal source= instead of _pick_read_source() — "
            "that read would ignore the picks.assign_tradeable kill switch")


def test_w3_02b_ast_no_unsanctioned_writer_reaches_the_store():
    """D12 — no path outside the assignment surface writes `draft_picks`."""
    sanctioned = {
        "replace_draft_picks": frozenset({
            "sync_draft_picks",           # database.py — the Sleeper grid
            "seed_pick_grid",             # database.py — W3's projection
            "_sync_mfl_owned_picks",      # server.py   — the MFL grid
        }),
        "sync_draft_picks": frozenset({"_sync_sleeper_owned_picks"}),
    }
    for name, allowed in sanctioned.items():
        callers = set()
        for path in (SERVER_PATH, DATABASE_PATH):
            for enclosing, _kw in _calls_named(ast.parse(path.read_text()), name):
                if enclosing != name:          # skip the definition's recursion
                    callers.add(enclosing)
        assert callers <= allowed, (
            f"{name} gained a caller outside the sanctioned set: "
            f"{sorted(callers - allowed)} — re-check it against INV-2")


def test_w3_02c_load_draft_picks_defaults_to_platform_only(mem_db):
    """The default IS the containment. NULL `source` reads as platform."""
    import inspect
    sig = inspect.signature(db.load_draft_picks)
    assert sig.parameters["source"].default == db.PICK_SOURCE_PLATFORM

    db.replace_draft_picks(LEAGUE, _platform_rows())
    before = db.load_draft_picks(league_id=LEAGUE)
    assert len(before) == 4
    # every pre-W3 row has source IS NULL and is selected by the default
    assert all(r["source"] is None for r in before)

    db.seed_pick_grid(league_id=LEAGUE, member_user_ids=MEMBERS,
                      user_id_to_name=NAMES, actor_user_id=ME,
                      current_season=SEASON, rounds=4)
    after = db.load_draft_picks(league_id=LEAGUE)
    assert after == before, "an asserted row leaked into the default read"


def test_w3_01_golden_byte_identity_on_every_read_site(mem_db):
    """D10 / INV-1 — with a FULL asserted grid in the DB, every read site is
    byte-identical to the same build with no assertions at all.

    The seven sites all take the platform-only default (pinned by the AST test
    above), so this exercises the default through four of them directly plus
    the shared loader they all funnel through.
    """
    db.replace_draft_picks(LEAGUE, _platform_rows())

    def _snapshot():
        return {
            "load":     json.dumps(db.load_draft_picks(league_id=LEAGUE),
                                   sort_keys=True, default=str),
            "load_own": json.dumps(db.load_draft_picks(league_id=LEAGUE,
                                                       owner_user_id="u1"),
                                   sort_keys=True, default=str),
            "share":    server._user_pick_share(ME, LEAGUE),
            "power":    json.dumps(server._power_picks_by_owner(LEAGUE, "1qb_ppr"),
                                   sort_keys=True),
            "assets":   sorted(
                (o, p.id, p.name, p.pick_value)
                for o, ps in server._owned_pick_assets(LEAGUE, "1qb_ppr").items()
                for p in ps),
        }

    before = _snapshot()
    db.seed_pick_grid(league_id=LEAGUE, member_user_ids=MEMBERS,
                      user_id_to_name=NAMES, actor_user_id=ME,
                      current_season=SEASON, rounds=4)
    assert len(db.load_draft_picks(league_id=LEAGUE, source=db.PICK_SOURCE_USER)) == \
        4 * len(MEMBERS) * 4
    assert _snapshot() == before


def test_w3_07b_seeder_skips_a_slot_the_platform_already_owns(mem_db):
    """`pick_id`'s unique key has NO provenance dimension, so one slot cannot
    hold both a platform row and an asserted one.

    Found by this suite: before the guard the seeder raised an IntegrityError
    (a 500) on any league that had platform rows. The platform wins — it is
    the authoritative reading — and the slot is SKIPPED, never overwritten.
    """
    db.replace_draft_picks(LEAGUE, _platform_rows(n=2, slot="1"))
    result = db.seed_pick_grid(
        league_id=LEAGUE, member_user_ids=MEMBERS, user_id_to_name=NAMES,
        actor_user_id=ME, current_season=SEASON, rounds=2)
    assert result["skipped"] == 2
    assert result["seeded"] == 2 * len(MEMBERS) * 4 - 2
    # the platform rows are untouched and still read as platform
    platform = db.load_draft_picks(league_id=LEAGUE)
    assert len(platform) == 2
    assert all(r["source"] is None for r in platform)


def test_w3_03_replace_draft_picks_never_crosses_provenance(mem_db):
    """INV-2 (VFF against the pre-W3 unconditional DELETE).

    The old body was `DELETE WHERE league_id = ?` with no provenance scope, so
    ANY platform sync wiped an entire league's assertions and the assignment
    projection wiped the platform grid. Both directions are pinned.
    """
    db.replace_draft_picks(LEAGUE, _platform_rows())
    db.seed_pick_grid(league_id=LEAGUE, member_user_ids=MEMBERS,
                      user_id_to_name=NAMES, actor_user_id=ME,
                      current_season=SEASON, rounds=2)
    asserted = len(db.load_draft_picks(league_id=LEAGUE,
                                       source=db.PICK_SOURCE_USER))
    assert asserted == 2 * len(MEMBERS) * 4

    # A platform writer replacing its own grid cannot touch an assertion.
    db.replace_draft_picks(LEAGUE, _platform_rows(n=2))
    assert len(db.load_draft_picks(league_id=LEAGUE)) == 2
    assert len(db.load_draft_picks(league_id=LEAGUE,
                                   source=db.PICK_SOURCE_USER)) == asserted

    # And the assignment projection cannot touch a platform row.
    db.replace_draft_picks(LEAGUE, [], preserve_source=db.PICK_SOURCE_USER)
    assert len(db.load_draft_picks(league_id=LEAGUE)) == 2
    assert db.load_draft_picks(league_id=LEAGUE,
                               source=db.PICK_SOURCE_USER) == []


# ---------------------------------------------------------------------------
# D13 — no user-entered values, ever
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["value", "pool_value", "pick_value", "elo"])
def test_w3_04_value_fields_are_refused_at_the_edge(client, flag_on, field):
    """D13 — a value in ANY assignment body is a loud 400, never a silent
    ignore. There is no path from a request to a price."""
    r = _seed(client, rounds=2, **{field: 999})
    assert r.status_code == 400 and r.get_json()["error"] == "values_not_accepted"

    _seed(client, rounds=2)
    pick_id = db.make_pick_id(LEAGUE, SEASON, 1, "1")
    r = _put(client, pick_id, owner_user_id="u2", **{field: 999})
    assert r.status_code == 400 and r.get_json()["error"] == "values_not_accepted"


def test_w3_05_asserted_prices_are_the_shipped_function_in_both_modes(mem_db):
    """D13 / INV-3, restated against the code that actually prices.

    M6b made the read-time price mode-dependent (`priced_pool_value`), and only
    two of the seven sites go through it — so naming the stored column alone
    would under-test the claim. Both modes are checked by name.
    """
    db.seed_pick_grid(league_id=LEAGUE, member_user_ids=MEMBERS,
                      user_id_to_name=NAMES, actor_user_id=ME,
                      current_season=SEASON, rounds=4)
    rows = db.load_draft_picks(league_id=LEAGUE, source=db.PICK_SOURCE_USER)
    assert rows
    for row in rows:
        years_out = int(row["season"]) - SEASON
        expected = pick_pool_value(int(row["round"]), years_out, "1qb_ppr")
        assert row["pool_value"] == expected
        assert row["pick_value"] == db.compute_pick_value(
            int(row["round"]), int(row["season"]), SEASON, len(MEMBERS))
        for mode in ("tier_ladder", "market_slots"):
            priced = priced_pool_value(row, scoring_format="1qb_ppr", mode=mode)
            # `market_slots` re-shapes the curve from DynastyProcess; with no
            # DP slot price available it falls back to the stored value. Either
            # way the price is a pure function of the pick's COORDINATES and
            # never of anything a user typed.
            assert priced == priced_pool_value(
                {"season": row["season"], "round": row["round"],
                 "pool_value": expected}, scoring_format="1qb_ppr", mode=mode)


def test_w3_06_conservation_bound_and_the_rounds_clamp(mem_db):
    """INV-4 / KD-4 — ownership redistributes value; it never creates it, and
    `rounds` (the only inflation lever) is clamped in the STORE, not just the
    route."""
    db.seed_pick_grid(league_id=LEAGUE, member_user_ids=MEMBERS,
                      user_id_to_name=NAMES, actor_user_id=ME,
                      current_season=SEASON, rounds=4)
    rows = db.load_draft_picks(league_id=LEAGUE, source=db.PICK_SOURCE_USER)
    pristine_total = round(sum(r["pool_value"] for r in rows), 4)

    # Reassign every slot to one owner — the worst-case redistribution.
    for r in rows:
        db.assign_draft_pick(LEAGUE, r["pick_id"], "u2", "Team u2", ME,
                             r["assigned_at"])
    after = db.load_draft_picks(league_id=LEAGUE, source=db.PICK_SOURCE_USER)
    assert round(sum(r["pool_value"] for r in after), 4) == pristine_total
    assert {r["owner_user_id"] for r in after} == {"u2"}

    # The clamp lives in seed_pick_grid itself, so no caller can widen it.
    db.seed_pick_grid(league_id=LEAGUE, member_user_ids=MEMBERS,
                      user_id_to_name=NAMES, actor_user_id=ME,
                      current_season=SEASON, rounds=99, reseed=True)
    maxr = max(int(r["round"]) for r in
               db.load_draft_picks(league_id=LEAGUE, source=db.PICK_SOURCE_USER))
    from backend.draft_status import ROOKIE_MAX_ROUNDS
    assert maxr == ROOKIE_MAX_ROUNDS == 8


def test_w3_06b_route_refuses_rounds_out_of_range(client, flag_on):
    for bad in (0, -1, 9, 100, "many"):
        r = _seed(client, rounds=bad)
        assert r.status_code == 400
        assert r.get_json()["error"] == "rounds_out_of_range"
        assert r.get_json()["max"] == 8


# ---------------------------------------------------------------------------
# D14 — pristine-seed correctness + orphans
# ---------------------------------------------------------------------------

def test_w3_07_pristine_seed_is_correct_and_idempotent(client, flag_on, mem_db):
    """D14 — exactly `rounds x teams x 4` slots, each owned by its ORIGINAL
    team, and a re-seed preserves every edit verbatim.

    The pristine default is the whole reason a ~192-slot board is tractable: a
    league with three trades leaves 189 slots untouched.
    """
    r = _seed(client, rounds=4)
    assert r.status_code == 200
    body = _get(client).get_json()

    assert [s["season"] for s in body["seasons"]] == [SEASON + i for i in range(4)]
    slots = [s for season in body["seasons"] for s in season["slots"]]
    assert len(slots) == 4 * len(MEMBERS) * 4 == body["progress"]["total"]
    assert all(s["owner_user_id"] == s["original_user_id"] for s in slots)
    assert all(s["is_traded"] is False for s in slots)
    assert body["progress"]["traded"] == 0
    assert body["seeded"] is True

    # Edit one slot, then re-seed: the edit survives byte-for-byte.
    target = slots[0]
    assert _put(client, target["pick_id"], owner_user_id="u3",
                if_assigned_at=target["assigned_at"]).status_code == 200
    edited = next(s for s in
                  (x for season in _get(client).get_json()["seasons"]
                   for x in season["slots"])
                  if s["pick_id"] == target["pick_id"])
    assert edited["owner_user_id"] == "u3" and edited["is_traded"] is True

    assert _seed(client, rounds=4).status_code == 200
    again = _get(client).get_json()
    still = next(s for season in again["seasons"] for s in season["slots"]
                 if s["pick_id"] == target["pick_id"])
    assert still == edited
    assert again["progress"]["traded"] == 1


def test_w3_08_orphaned_owners_surface_and_are_unpriced_never_dropped(
        client, flag_on, mem_db):
    """D14 — an owner id that is no longer a `league_members` row (a SWID
    rotation on re-import, or a manager who left) becomes a RE-ASSIGN row.

    Never silently dropped: a dropped slot is value that vanishes with no
    explanation, and there is no platform that will ever contradict the grid.
    """
    _seed(client, rounds=1)
    pick_id = db.make_pick_id(LEAGUE, SEASON, 1, "1")
    with db.engine.begin() as conn:
        conn.execute(draft_picks_table.update()
                     .where(draft_picks_table.c.pick_id == pick_id)
                     .values(owner_user_id="ghost_swid"))
    db.invalidate_pick_assignment_cache(LEAGUE)

    slots = [s for season in _get(client).get_json()["seasons"]
             for s in season["slots"]]
    orphan = next(s for s in slots if s["pick_id"] == pick_id)
    assert orphan["orphaned"] is True
    assert orphan["owner_user_id"] == "ghost_swid"      # visible, not dropped

    # …and excluded from any read that could reach a price.
    priced = db.load_draft_picks(league_id=LEAGUE, source=db.PICK_SOURCE_ANY)
    assert pick_id not in {r["pick_id"] for r in priced}
    # INV-5 — the exclusion is a ROW FILTER. The stored price is untouched, so
    # nothing downstream can re-derive it (see the contested test below).
    still = db.load_draft_picks(league_id=LEAGUE, source=db.PICK_SOURCE_USER,
                                include_contested=True)
    assert next(r for r in still if r["pick_id"] == pick_id)["pool_value"] is not None


def test_w3_34_contested_is_excluded_by_row_filter_not_by_nulling(
        client, flag_on, mem_db):
    """INV-5, stated as the failure it prevents.

    `_power_picks_by_owner` RE-DERIVES a price when `pool_value` is NULL. So
    the naive "unprice it by nulling the column" implementation would price
    the very row the rule exists to withhold. The test asserts both halves:
    the real filter removes the row, and nulling demonstrably does not.
    """
    _seed(client, rounds=1)
    pick_id = db.make_pick_id(LEAGUE, SEASON, 1, "1")
    slots = [s for season in _get(client).get_json()["seasons"]
             for s in season["slots"]]
    token = next(s for s in slots if s["pick_id"] == pick_id)["assigned_at"]

    # Two DIFFERENT actors assign the SAME slot to two DIFFERENT owners.
    assert _put(client, pick_id, owner_user_id="u2",
                if_assigned_at=token).status_code == 200
    fresh = next(s for season in _get(client).get_json()["seasons"]
                 for s in season["slots"] if s["pick_id"] == pick_id)
    db.assign_draft_pick(LEAGUE, pick_id, "u3", "Team u3", "u4",
                         fresh["assigned_at"])
    db.record_event("u4", "pick_assignment_changed", league_id=LEAGUE, props={
        "pick_id": pick_id, "actor": "u4", "new_owner": "u3"})
    db.invalidate_pick_assignment_cache(LEAGUE)

    assert pick_id in db.contested_pick_ids(LEAGUE)
    assert pick_id not in {
        r["pick_id"] for r in
        db.load_draft_picks(league_id=LEAGUE, source=db.PICK_SOURCE_ANY)}
    # …but it is VISIBLE on the screen where someone fixes it.
    shown = next(s for season in _get(client).get_json()["seasons"]
                 for s in season["slots"] if s["pick_id"] == pick_id)
    assert shown["contested"] is True

    # The forbidden implementation, demonstrated failing.
    with db.engine.begin() as conn:
        conn.execute(draft_picks_table.update()
                     .where(draft_picks_table.c.pick_id == pick_id)
                     .values(source=None, pool_value=None))
    powered = server._power_picks_by_owner(LEAGUE, "1qb_ppr")
    assert any(item["value"] > 0
               for items in powered.values() for item in items), (
        "nulling pool_value does NOT unprice a row — _power_picks_by_owner "
        "re-derives it, which is why INV-5 mandates a row filter")


# ---------------------------------------------------------------------------
# D16 — concurrency
# ---------------------------------------------------------------------------

def test_w3_09_cas_stale_token_409s_with_the_current_row(client, flag_on, mem_db):
    _seed(client, rounds=1)
    pick_id = db.make_pick_id(LEAGUE, SEASON, 1, "1")
    slots = [s for season in _get(client).get_json()["seasons"]
             for s in season["slots"]]
    stale = next(s for s in slots if s["pick_id"] == pick_id)["assigned_at"]

    assert _put(client, pick_id, owner_user_id="u2",
                if_assigned_at=stale).status_code == 200

    r = _put(client, pick_id, owner_user_id="u4", if_assigned_at=stale)
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "stale_assignment"
    # The WHOLE current row rides the 409 so the conflict UI needs no second
    # request ("Dana changed this 4 minutes ago — keep theirs, or use yours?").
    assert body["current"]["pick_id"] == pick_id
    assert body["current"]["owner_user_id"] == "u2"
    assert body["current"]["assigned_at"] != stale


def test_w3_09b_blind_overwrite_of_an_assigned_row_is_never_allowed(
        client, flag_on, mem_db):
    _seed(client, rounds=1)
    pick_id = db.make_pick_id(LEAGUE, SEASON, 1, "1")
    r = _put(client, pick_id, owner_user_id="u2")      # no if_assigned_at
    assert r.status_code == 409
    assert r.get_json()["error"] == "stale_assignment"


def test_w3_09c_different_slots_both_succeed(client, flag_on, mem_db):
    _seed(client, rounds=2)
    slots = {s["pick_id"]: s for season in _get(client).get_json()["seasons"]
             for s in season["slots"]}
    a = db.make_pick_id(LEAGUE, SEASON, 1, "1")
    b = db.make_pick_id(LEAGUE, SEASON, 2, "2")
    assert _put(client, a, owner_user_id="u2",
                if_assigned_at=slots[a]["assigned_at"]).status_code == 200
    assert _put(client, b, owner_user_id="u3",
                if_assigned_at=slots[b]["assigned_at"]).status_code == 200


def test_w3_09d_unknown_pick_and_non_member_owner(client, flag_on, mem_db):
    _seed(client, rounds=1)
    r = _put(client, "not_a_pick", owner_user_id="u2")
    assert r.status_code == 404 and r.get_json()["error"] == "pick_not_found"
    pick_id = db.make_pick_id(LEAGUE, SEASON, 1, "1")
    r = _put(client, pick_id, owner_user_id="somebody_else")
    assert r.status_code == 400
    assert r.get_json()["error"] == "owner_not_in_league"


def test_w3_11_every_write_emits_the_audit_event(client, flag_on, mem_db):
    """D16 — `user_events` IS the audit trail (contested derives from it and
    the runbook reconstructs a grid from it), so a write without an event is a
    silent, unrecoverable change."""
    _seed(client, rounds=1)
    pick_id = db.make_pick_id(LEAGUE, SEASON, 1, "1")
    slots = {s["pick_id"]: s for season in _get(client).get_json()["seasons"]
             for s in season["slots"]}
    with patch.object(server, "record_event") as rec:
        assert _put(client, pick_id, owner_user_id="u2",
                    if_assigned_at=slots[pick_id]["assigned_at"]
                    ).status_code == 200
    assert rec.call_count == 1
    args, kwargs = rec.call_args
    assert args == (ME, "pick_assignment_changed")
    assert kwargs["league_id"] == LEAGUE
    assert set(kwargs["props"]) == {"pick_id", "season", "round",
                                    "original_team", "old_owner",
                                    "new_owner", "actor"}
    assert kwargs["props"]["old_owner"] == "u1"
    assert kwargs["props"]["new_owner"] == "u2"
    assert kwargs["props"]["actor"] == ME


def test_w3_11b_the_audit_event_is_server_fired_and_not_client_forgeable():
    """A client-forgeable audit row is a forgeable audit trail — and the
    taxonomy's import-time disjointness assert would take the app down at boot
    if the name were registered in both namespaces."""
    assert "pick_assignment_changed" in taxonomy.SERVER_FIRED_EVENTS
    assert "pick_assignment_changed" not in taxonomy.ALLOWED_CLIENT_EVENTS
    taxonomy._assert_namespaces_disjoint(taxonomy.ALLOWED_CLIENT_EVENTS,
                                         taxonomy.SERVER_FIRED_EVENTS)


def test_w3_12_o9_survives_no_path_writes_the_draft_status_columns(
        client, flag_on, mem_db):
    """INV-7, pinned BEHAVIORALLY rather than by source-text identity."""
    def _verdict():
        with db.engine.connect() as conn:
            row = conn.execute(select(
                leagues_table.c.draft_status,
                leagues_table.c.draft_status_confidence,
                leagues_table.c.draft_status_checked_at)
                .where(leagues_table.c.sleeper_league_id == LEAGUE)).fetchone()
        return tuple(row)

    before = _verdict()
    _seed(client, rounds=2)
    pick_id = db.make_pick_id(LEAGUE, SEASON, 1, "1")
    slots = {s["pick_id"]: s for season in _get(client).get_json()["seasons"]
             for s in season["slots"]}
    _put(client, pick_id, owner_user_id="u2",
         if_assigned_at=slots[pick_id]["assigned_at"])
    assert _verdict() == before


def test_w3_13_membership_is_asserted_server_side(client, flag_on, mem_db):
    """A body `user_id` is IGNORED — the actor is always the session user."""
    _seed(client, rounds=1)
    pick_id = db.make_pick_id(LEAGUE, SEASON, 1, "1")
    slots = {s["pick_id"]: s for season in _get(client).get_json()["seasons"]
             for s in season["slots"]}
    with patch.object(server, "record_event") as rec:
        _put(client, pick_id, owner_user_id="u2", user_id="somebody_else",
             if_assigned_at=slots[pick_id]["assigned_at"])
    assert rec.call_args[0][0] == ME
    assert rec.call_args.kwargs["props"]["actor"] == ME

    with db.engine.begin() as conn:
        conn.execute(league_members_table.delete()
                     .where(league_members_table.c.user_id == ME))
    db.invalidate_pick_assignment_cache(LEAGUE)
    assert _get(client).status_code == 403
    assert _put(client, pick_id, owner_user_id="u2").status_code == 403
    assert _seed(client, rounds=1).status_code == 403


# ---------------------------------------------------------------------------
# INV-8 — one pick_id construction
# ---------------------------------------------------------------------------

def test_w3_10_pick_id_has_exactly_one_construction():
    """Every producer emits identical ids for identical inputs. The format was
    three duplicated f-strings before W3; the assignment store would have made
    a fourth."""
    assert db.make_pick_id("L", 2026, 1, "3") == "L_2026_1_3"
    assert db.make_pick_id("L", 2026, "1", "3") == "L_2026_1_3"   # unpadded
    # No raw construction survives in either module.
    for path in (SERVER_PATH, DATABASE_PATH):
        src = path.read_text()
        for shape in ('_{season}_{rnd}_', '_{yr}_{rnd}_', '_{season}_{round_}_'):
            assert shape not in src, f"{path.name} still builds a pick_id by hand"


def test_w3_10b_the_seeder_and_the_sleeper_sync_agree(mem_db):
    rows = db.sync_draft_picks(
        league_id="sleeper_twin", roster_ids=[1], traded_picks=[],
        roster_id_to_user={"1": "u1"}, user_id_to_name={"u1": "A"},
        current_season=SEASON, rounds=1, seasons_ahead=0)
    assert rows[0]["pick_id"] == db.make_pick_id("sleeper_twin", SEASON, 1, "1")


# ---------------------------------------------------------------------------
# D10 — flag off
# ---------------------------------------------------------------------------

def test_w3_flag_off_404s_every_assignment_route(client, flag_off, mem_db):
    assert _get(client).status_code == 404
    assert _get(client).get_json()["error"] == "feature_disabled"
    assert _seed(client, rounds=4).status_code == 404
    assert _put(client, "anything", owner_user_id="u2").status_code == 404


def test_w3_flag_off_writes_nothing(client, flag_off, mem_db):
    _seed(client, rounds=4)
    assert db.load_draft_picks(league_id=LEAGUE,
                               source=db.PICK_SOURCE_ANY) == []


# ---------------------------------------------------------------------------
# Numbering: the linear/snake toggle and the order permutation
# ---------------------------------------------------------------------------

def test_order_type_and_order_change_numbering_and_never_ownership(
        client, flag_on, mem_db):
    """The execution lens's finding, pinned: the toggle is safe at any time."""
    _seed(client, rounds=2)
    before = {s["pick_id"]: s["owner_user_id"]
              for season in _get(client).get_json()["seasons"]
              for s in season["slots"]}

    r = _seed(client, order_type="snake", order=list(reversed(MEMBERS)))
    assert r.status_code == 200
    assert r.get_json()["settings"]["order_type"] == "snake"
    assert r.get_json()["settings"]["order"] == list(reversed(MEMBERS))

    after = {s["pick_id"]: s["owner_user_id"]
             for season in _get(client).get_json()["seasons"]
             for s in season["slots"]}
    assert after == before


def test_bad_order_and_bad_order_type_are_refused(client, flag_on, mem_db):
    r = _seed(client, order=["u1", "u2"])
    assert r.status_code == 400 and r.get_json()["error"] == "bad_order"
    r = _seed(client, order_type="serpentine")
    assert r.status_code == 400 and r.get_json()["error"] == "bad_order_type"
