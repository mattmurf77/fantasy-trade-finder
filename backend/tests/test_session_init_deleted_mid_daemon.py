"""POST /api/session/init — the background daemon never re-creates rows an
account deletion removed.

release-lead's QA of #479: the daemon's `upsert_league` re-created a deleted
`leagues` row with platform NULL (a linked MFL/ESPN league then reads as
Sleeper, and its next init is a 503 `league_data_unavailable`), and its
`users` and `league_members` writes could re-create those rows as well.

The daemon now reads what exists at its start; those rows are only updated.
The `users` row is never inserted (the session mint writes it), and only a
Sleeper league's first init inserts: its `leagues` row, with the platform, and
the `league_members` rows of managers new since the start. The users, leagues,
both user_events, league_members and roster-history writes each hold the
account's users-row lock (`database._lock_live_user`); the first to find the
row gone (`AccountGone`) stops the daemon. A structural test pins the lock as
the first statement of its write's own transaction; the opt-in Postgres twin
(test_session_init_deleted_pg.py) runs the interleavings on real threads.

Two deletions are injected between the daemon's start read and its writes (or
later), by wrapping the daemon's own calls:

  * the caller's own account (U). In one process the user_data_lifecycle lease
    already holds a deletion until the daemon is done, so this runs only the
    deletion's DB transaction (`accounts._delete_user_data`): a deletion
    committed by another process (a rolling deploy's other container), which
    only the DB guard can stop;
  * the leaguemate who imported the league (A), through the public
    `delete_user_data`. Leases are per account, so U's daemon isn't drained.

Harness: test_session_init_sleeper_calls's (in-memory SQLite, every Sleeper
call faked, the daemon inline), with a users row for U, as the mint writes it.
"""

import ast
import pathlib

import pytest
from sqlalchemy import String, or_, select

import backend.accounts as accounts
import backend.database as db_module
import backend.roster_history as roster_history
import backend.server as server
from backend.tests import test_session_init_sleeper_calls as calls_t

LEAGUE_ID = calls_t.LEAGUE_ID
MFL = calls_t.NUMERIC_MFL_LEAGUE
ESPN = calls_t.NUMERIC_ESPN_LEAGUE
USER_ID = calls_t.USER_ID
OPP_ID = calls_t.OPP_ID
TOKEN = "budget-verified-token"   # the harness's session

pytestmark = pytest.mark.usefixtures("no_real_network")


@pytest.fixture()
def harness(monkeypatch):
    yield from calls_t.harness.__wrapped__(monkeypatch)


def _init(client, league_id):
    return calls_t._init(client, league_id)


def _league(league_id):
    with db_module.engine.connect() as conn:
        row = conn.execute(select(db_module.leagues_table).where(
            db_module.leagues_table.c.sleeper_league_id == league_id)).mappings().first()
    return dict(row) if row else None


def _user(user_id):
    with db_module.engine.connect() as conn:
        return conn.execute(select(db_module.users_table.c.sleeper_user_id).where(
            db_module.users_table.c.sleeper_user_id == user_id)).first()


def _members(league_id):
    return {m["user_id"]: m for m in db_module.load_league_members(league_id)}


# The deletion scrub's job row (#562) names the deleted ids on purpose, and is
# kept until the scrub finishes: deletion's own bookkeeping, never a row the
# daemon writes. Excluded by name, so this holds with or without #562.
_SCAN_EXCLUDED = {"deletion_scrub_jobs"}


def _rows_naming(needle):
    """Every row, in every table but _SCAN_EXCLUDED, with a text column
    containing `needle`."""
    found = []
    with db_module.engine.connect() as conn:
        for table in db_module.metadata.sorted_tables:
            if table.name in _SCAN_EXCLUDED:
                continue
            cols = [c for c in table.columns if isinstance(c.type, String)]
            if cols:
                found += [(table.name, repr(tuple(r))) for r in conn.execute(select(table).where(
                    or_(*[c.contains(needle, autoescape=True) for c in cols])))]
    return sorted(found)


def _delete_at(monkeypatch, point, delete):
    """Run `delete()` once: as the daemon's thread starts, after the request
    read the league and before the daemon's first read ("before_start"), or
    inside the daemon just after the named call returns. Returns a list that
    holds, once it ran, the rows naming each deleted id at that moment."""
    ran = []

    def run():
        delete()
        ran.append({uid: _rows_naming(uid) for uid in (USER_ID, OPP_ID)})

    if point == "before_start":
        inline = server.threading.Thread          # the harness's inline daemon

        class _DeleteFirst(inline):
            def start(self):
                if self.name == "session-init-bg-writes" and not ran:
                    run()
                super().start()

        monkeypatch.setattr(server.threading, "Thread", _DeleteFirst)
        return ran
    name = {"start": "league_row_and_member_ids", "user": "upsert_user",
            "league": "upsert_league", "events": "record_event",
            "members": "write_session_init_members"}[point]
    real = getattr(server, name)

    def hooked(*a, **kw):
        out = real(*a, **kw)
        if not ran and (point != "events" or "league_synced" in a):
            run()
        return out

    monkeypatch.setattr(server, name, hooked)
    return ran


def _seed_league(league_id, importer):
    """The league's row (Sleeper: created here; MFL/ESPN: the harness's) owned
    by `importer`, and both managers' league_members rows."""
    with db_module.engine.begin() as conn:
        if league_id == LEAGUE_ID:
            conn.execute(db_module.leagues_table.insert().values(
                sleeper_league_id=LEAGUE_ID, user_id=importer, name="Bush League",
                platform="sleeper"))
        else:
            conn.execute(db_module.leagues_table.update().where(
                db_module.leagues_table.c.sleeper_league_id == league_id).values(user_id=importer))
    if league_id == LEAGUE_ID:
        db_module.upsert_league_members(LEAGUE_ID, [
            {"user_id": USER_ID, "username": "Me", "player_ids": ["p1"]},
            {"user_id": OPP_ID, "username": "Opp", "player_ids": ["p2"]}])


# ---------------------------------------------------------------------------
# The caller's own account, deleted mid-daemon (another process's deletion)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("point", ["before_start", "start", "user", "league", "events"])
@pytest.mark.parametrize("league", ["sleeper_first_init", "sleeper_reinit", "mfl", "espn"])
def test_own_deletion_mid_daemon_is_never_undone(harness, monkeypatch, league, point):
    client, _calls = harness
    league_id = {"sleeper_first_init": LEAGUE_ID, "sleeper_reinit": LEAGUE_ID,
                 "mfl": MFL, "espn": ESPN}[league]
    if league == "sleeper_reinit":
        _seed_league(LEAGUE_ID, USER_ID)
    ran = _delete_at(monkeypatch, point, lambda: accounts._delete_user_data(USER_ID))

    assert _init(client, league_id).status_code == 200
    assert ran, "the deletion never ran inside the daemon"

    after_delete = ran[0][USER_ID]
    assert after_delete == []                      # the deletion removed every row naming U
    assert _user(USER_ID) is None
    assert _league(league_id) is None
    assert USER_ID not in _members(league_id)
    # Nothing the daemon wrote after the deletion names U, in any table: no
    # users/leagues/league_members row, no user_events row, nothing else.
    assert _rows_naming(USER_ID) == after_delete
    assert _rows_naming(db_module.analytics_session_id(TOKEN)) == []


@pytest.mark.parametrize("league", ["sleeper_first_init", "sleeper_reinit"])
def test_own_deletion_after_the_members_write(harness, monkeypatch, league):
    """The league syncs that follow the members write: the roster-history
    snapshot (league_roster_history, league_board_history) holds the lock as
    well, so it writes nothing naming U (release-lead's #587 QA, g). The
    owned-pick sync does write U's Sleeper draft_picks again: public Sleeper
    data, which the deletion matrix keeps."""
    client, _calls = harness
    if league == "sleeper_reinit":
        _seed_league(LEAGUE_ID, USER_ID)
    ran = _delete_at(monkeypatch, "members", lambda: accounts._delete_user_data(USER_ID))

    assert _init(client, LEAGUE_ID).status_code == 200
    assert ran and ran[0][USER_ID] == []

    assert _user(USER_ID) is None and _league(LEAGUE_ID) is None
    assert USER_ID not in _members(LEAGUE_ID)
    left = _rows_naming(USER_ID)
    assert {t for t, _r in left} <= {"draft_picks"}, left


def test_own_deletion_between_the_board_read_and_its_write(harness, monkeypatch):
    """The board snapshot reads every member's board (member_rankings), then
    writes league_board_history, a private table, under the caller's lock.
    The caller deleted between the read and the write leaves no board row
    (release-lead's #587 QA, round 3)."""
    client, _calls = harness
    with db_module.engine.begin() as conn:
        conn.execute(db_module.member_rankings_table.insert().values(
            user_id=USER_ID, league_id=LEAGUE_ID, player_id="p1", elo=1550.0,
            updated_at="2026-11-03T00:00:00+00:00", scoring_format="1qb_ppr"))
    real, read = roster_history.load_member_boards_for_league, []

    def read_then_delete(league_id):
        boards = real(league_id)
        read.append(boards)
        accounts._delete_user_data(USER_ID)
        return boards

    monkeypatch.setattr(roster_history, "load_member_boards_for_league", read_then_delete)

    assert _init(client, LEAGUE_ID).status_code == 200

    assert [b["user_id"] for b in read[0]] == [USER_ID]   # the write had a board to write
    t = db_module.league_board_history_table
    with db_module.engine.connect() as conn:
        assert conn.execute(select(t)).first() is None
    left = _rows_naming(USER_ID)
    assert {t for t, _r in left} <= {"draft_picks"}, left


def test_the_first_write_to_find_the_account_gone_stops_the_daemon(harness, monkeypatch):
    """record_event re-raises AccountGone under require_user, so a deletion
    just before the first event ends the daemon there: no second event, no
    members write, no roster history, no Sleeper call past the request's."""
    client, calls = harness
    _seed_league(LEAGUE_ID, USER_ID)
    tried = []
    for name in ("record_event", "write_session_init_members", "_sleeper_roster_history_on_sync"):
        real = getattr(server, name)
        monkeypatch.setattr(server, name, lambda *a, _n=name, _real=real, **kw: (
            tried.append(_n), _real(*a, **kw))[1])
    ran = _delete_at(monkeypatch, "league", lambda: accounts._delete_user_data(USER_ID))

    assert _init(client, LEAGUE_ID).status_code == 200
    assert ran

    assert tried == ["record_event"]
    assert set(calls) == {"meta", "users", "rosters"}   # the request's read, nothing after


def test_without_a_users_row_the_daemon_writes_nothing(harness, monkeypatch):
    """The daemon never inserts the users row: none at all (the account is
    gone, or its mint's write failed) means nothing to anchor a write on."""
    client, _calls = harness
    with db_module.engine.begin() as conn:
        conn.execute(db_module.users_table.delete())
    deferred, inline = [], server.threading.Thread

    class _AfterTheResponse(inline):
        def start(self):
            if self.name == "session-init-bg-writes":
                deferred.append(self.run)
                return
            super().start()

    monkeypatch.setattr(server.threading, "Thread", _AfterTheResponse)
    assert _init(client, LEAGUE_ID).status_code == 200
    before = _rows_naming(USER_ID)   # the request's own writes (its durable session)

    deferred.pop()()

    assert _user(USER_ID) is None
    assert _league(LEAGUE_ID) is None
    assert _members(LEAGUE_ID) == {}
    assert _rows_naming(USER_ID) == before


# ---------------------------------------------------------------------------
# The leaguemate who imported the league, deleted mid-daemon (same process)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("point", ["before_start", "start"])
@pytest.mark.parametrize("league_id", [MFL, ESPN, LEAGUE_ID])
def test_the_importers_deletion_mid_daemon_is_not_undone(harness, monkeypatch, league_id, point):
    client, _calls = harness
    db_module.upsert_user(OPP_ID)
    _seed_league(league_id, OPP_ID)
    ran = _delete_at(monkeypatch, point, lambda: accounts.delete_user_data(OPP_ID))

    assert _init(client, league_id).status_code == 200
    assert ran, "the deletion never ran inside the daemon"

    assert _user(OPP_ID) is None
    members = _members(league_id)
    assert members[USER_ID]["updated_at"]          # the caller's own row is still written
    if league_id == LEAGUE_ID and point == "before_start":
        # The daemon found neither row, so to it this is a Sleeper league's
        # first init: both are built from Sleeper's public read, as the next
        # init would build them (the deletion matrix: "recreated from
        # Sleeper's public API by any member's next session_init"). The league
        # is the caller's now, and never has a NULL platform.
        row = _league(LEAGUE_ID)
        assert (row["user_id"], row["platform"]) == (USER_ID, "sleeper")
        assert members[OPP_ID]["player_ids"] == ["p2"]
        return
    # The rows it found are only updated: deleted since, they stay deleted,
    # so a linked league never comes back with a NULL platform.
    assert OPP_ID not in members
    assert _league(league_id) is None
    if league_id != LEAGUE_ID:
        # No Sleeper sync runs for a linked league whose row has gone (its
        # roster history would carry the importer's id again): nothing names A.
        assert _rows_naming(OPP_ID) == ran[0][OPP_ID] == []


# ---------------------------------------------------------------------------
# Normal inits still create and update
# ---------------------------------------------------------------------------

def test_a_first_init_creates_the_rows_with_the_platform(harness):
    client, _calls = harness
    assert _league(LEAGUE_ID) is None and _members(LEAGUE_ID) == {}

    assert _init(client, LEAGUE_ID).status_code == 200

    row = _league(LEAGUE_ID)
    assert (row["user_id"], row["platform"]) == (USER_ID, "sleeper")
    assert set(_members(LEAGUE_ID)) == {USER_ID, OPP_ID}
    assert _user(USER_ID) is not None


def test_a_reinit_updates_the_rows(harness, monkeypatch):
    client, _calls = harness
    assert _init(client, LEAGUE_ID).status_code == 200
    created = _league(LEAGUE_ID)

    monkeypatch.setattr(calls_t, "LEAGUE_META", {**calls_t.LEAGUE_META, "name": "Renamed"})
    monkeypatch.setattr(calls_t, "ROSTERS", [
        calls_t.ROSTERS[0], {**calls_t.ROSTERS[1], "players": ["p2", "p3"]}])
    assert _init(client, LEAGUE_ID).status_code == 200

    row = _league(LEAGUE_ID)
    assert row["name"] == "Renamed"
    assert (row["user_id"], row["platform"], row["created_at"]) == (
        USER_ID, "sleeper", created["created_at"])
    assert _members(LEAGUE_ID)[OPP_ID]["player_ids"] == ["p2", "p3"]


@pytest.mark.parametrize("league_id, platform", [(MFL, "mfl"), (ESPN, "espn")])
def test_a_linked_league_keeps_its_platform(harness, league_id, platform):
    client, _calls = harness
    with db_module.engine.begin() as conn:
        conn.execute(db_module.league_members_table.update().where(
            db_module.league_members_table.c.league_id == league_id).values(updated_at=None))

    assert _init(client, league_id).status_code == 200

    assert _league(league_id)["platform"] == platform
    members = _members(league_id)
    assert set(members) == {USER_ID, OPP_ID}
    assert all(m["updated_at"] for m in members.values())   # updated, not re-inserted


# ---------------------------------------------------------------------------
# Where the lock sits (structural; the behavior tests above can't tell)
# ---------------------------------------------------------------------------

# Every database.py writer that takes the users-row lock. A writer added to
# or dropped from this set fails the test until it's listed here.
_GUARDED_WRITERS = {"upsert_user", "upsert_league", "record_event", "write_session_init_members",
                    "upsert_roster_snapshots", "upsert_board_snapshots"}


def _called(func):
    return getattr(func, "id", None) or getattr(func, "attr", None)


def _opening_lock(with_node):
    """The `_lock_live_user` call that opens this `with` block, directly or as
    the first statement of a leading `if` (`if require_user:`), or None."""
    first = with_node.body[0]
    if isinstance(first, ast.If) and not first.orelse:
        first = first.body[0]
    if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
            and _called(first.value.func) == "_lock_live_user"):
        return first.value
    return None


_WRITE_FUNCS = {"insert", "update", "delete", "dialect_insert", "pg_insert"}


def _table_aliases(fn):
    """Local names bound to a table in `fn`: `t = league_members_table`."""
    return {n.targets[0].id: n.value.id for n in ast.walk(fn)
            if isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Name)
            and n.value.id.endswith("_table")}


def _kind(statement, aliases):
    """("write" | "read" | None, tables) for what a `conn.execute(...)` runs:
    insert/update/delete (function or `table.update()` form) or a select."""
    resolve = lambda name: aliases.get(name, name)   # noqa: E731
    e = statement
    while isinstance(e, ast.Call):
        f = e.func
        if isinstance(f, ast.Name):
            if f.id in _WRITE_FUNCS and e.args and isinstance(e.args[0], ast.Name):
                return "write", {resolve(e.args[0].id)}
            if f.id == "select":
                return "read", {resolve(n.value.id) if isinstance(n, ast.Attribute) else resolve(n.id)
                                for a in e.args for n in ast.walk(a)
                                if (isinstance(n, ast.Attribute) and n.attr == "c"
                                    and isinstance(n.value, ast.Name))
                                or (isinstance(n, ast.Name) and resolve(n.id).endswith("_table"))}
            return None, set()
        if not isinstance(f, ast.Attribute):
            break
        if f.attr in ("insert", "update", "delete") and isinstance(f.value, ast.Name):
            return "write", {resolve(f.value.id)}
        e = f.value
    return None, set()


def _db_calls(node, conn):
    """Calls that use the transaction, in source order: `conn.execute(...)`,
    `conn.exec_driver_sql(...)`, or any call handed `conn`."""
    calls = [c for c in ast.walk(node) if isinstance(c, ast.Call) and (
        (isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name)
         and c.func.value.id == conn and c.func.attr in ("execute", "exec_driver_sql"))
        or any(isinstance(a, ast.Name) and a.id == conn for a in c.args))]
    return sorted(calls, key=lambda c: (c.lineno, c.col_offset))


def _first_after_lock_is_the_write(w, call, aliases):
    """The block's first use of `conn` after the lock writes, or reads a table
    the same block writes (an upsert's own existence check). Anything else
    sits between the lock and the write."""
    conn = w.items[0].optional_vars.id
    lead = w.body[0]
    rest = (lead.body[1:] if isinstance(lead, ast.If) else []) + w.body[1:]
    written = set()
    for c in _db_calls(w, conn):
        kind, tables = _kind(c.args[0], aliases) if c.args else (None, set())
        if kind == "write" and _called(c.func) == "execute":
            written |= tables
    for statement in rest:
        calls = _db_calls(statement, conn)
        if calls:
            first = calls[0]
            if _called(first.func) != "execute":
                return False
            kind, tables = _kind(first.args[0], aliases)
            return kind == "write" or (kind == "read" and bool(tables) and tables <= written)
    return False


def test_every_users_row_lock_opens_the_transaction_that_writes():
    """`_lock_live_user(conn, …)` must be the first statement inside the
    `with <engine>.begin() as conn:` block that also makes the write, and on
    that block's own `conn`. After a write it locks too late; alone in its own
    transaction it's released before the write. The block's next use of
    `conn` must be the write (or the upsert's read of the table it writes),
    so nothing unrelated runs under the lock first. On SQLite, run one at a
    time, none of this shows (release-lead's #587 QA), so this reads the
    source."""
    tree = ast.parse(pathlib.Path(db_module.__file__).read_text())
    guarded, bad = set(), []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or fn.name == "_lock_live_user":
            continue
        locks = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and _called(n.func) == "_lock_live_user"]
        if not locks:
            continue
        guarded.add(fn.name)
        opened_by = {id(_opening_lock(w)): w for w in ast.walk(fn) if isinstance(w, ast.With)}
        aliases = _table_aliases(fn)
        for call in locks:
            w = opened_by.get(id(call))
            item = w.items[0] if w is not None and len(w.items) == 1 else None
            ok = (item is not None
                  and isinstance(item.context_expr, ast.Call)
                  and _called(item.context_expr.func) == "begin"
                  and isinstance(item.optional_vars, ast.Name)
                  and isinstance(call.args[0], ast.Name)
                  and call.args[0].id == item.optional_vars.id
                  and len(w.body) > 1)                  # the write is in the same block
            if not ok:
                bad.append(f"{fn.name} (database.py:{call.lineno}): not opening its write's block")
            elif not _first_after_lock_is_the_write(w, call, aliases):
                bad.append(f"{fn.name} (database.py:{call.lineno}): its next statement isn't the write")
    assert not bad, f"users-row lock out of place: {bad}"
    assert guarded == _GUARDED_WRITERS


def test_the_lock_runs_on_the_transaction_it_is_handed():
    """`_lock_live_user` runs its SELECT … FOR KEY SHARE (and SQLite's BEGIN
    IMMEDIATE) on the `conn` it's passed: never on `engine` or a connection of
    its own, which would hold the lock outside the writer's transaction."""
    tree = ast.parse(pathlib.Path(db_module.__file__).read_text())
    fn = next(f for f in ast.walk(tree)
              if isinstance(f, ast.FunctionDef) and f.name == "_lock_live_user")
    conn = fn.args.args[0].arg
    uses = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            and c.func.attr in ("execute", "exec_driver_sql", "connect", "begin", "raw_connection")]
    assert uses and all(isinstance(c.func.value, ast.Name) and c.func.value.id == conn
                        and c.func.attr in ("execute", "exec_driver_sql") for c in uses), \
        [ast.unparse(c.func) for c in uses]
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == "engine"]
    key_share = [c for c in uses if c.func.attr == "execute" and any(
        isinstance(n, ast.Call) and _called(n.func) == "with_for_update"
        and {k.arg: getattr(k.value, "value", None) for k in n.keywords}
        == {"read": True, "key_share": True}
        for n in ast.walk(c))]
    assert key_share, "no SELECT … FOR KEY SHARE run on the passed conn"
