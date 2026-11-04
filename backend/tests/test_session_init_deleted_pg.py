"""Session init's users-row guard on a real Postgres, real threads (opt-in).

The essentials of release-lead's #587 QA (Postgres 18.3), kept so the
interleavings SQLite can't show stay pinned. U is the caller, O a leaguemate.

  (a) a deletion of U that starts while the daemon holds the lock mid-write
      waits for it, and the daemon's next guarded write stops at AccountGone;
  (b) a deletion of U that commits first: the daemon's first lock stops it;
  (d2) O deleted just before the Sleeper members replace's DELETE: the replace
      takes the rows still there from DELETE … RETURNING, so O's row stays gone;
  (d5) O, the importer of a linked league, deleted while the update-only
      members write holds O's row: the deletion waits, then deletes it;
  (d1) the known limit (write_session_init_members' docstring): O deleted
      after the replace's DELETE locked O's row waits, and can't see the row
      re-inserted for O, which survives. Public Sleeper membership. Pinned as
      it is, so a change to it is a decision.

Opt-in, like test_fa_move_pg_race.py (#578): set
FTF_SESSION_INIT_TEST_POSTGRES_URL to a disposable, socket-only local Postgres,
e.g. postgresql+psycopg2://postgres@/postgres?host=/private/tmp/sinitpg&port=55492
Skipped otherwise. Each test runs in its own schema, dropped afterwards. The
harness is test_session_init_sleeper_calls's (every Sleeper call faked), on
that Postgres. U's own deletion runs only the deletion's DB transaction
(`accounts._delete_user_data`): another process's deletion, which the
in-process lease can't hold.
"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

import backend.accounts as accounts
import backend.database as db_module
from backend.tests import test_session_init_deleted_mid_daemon as sq
from backend.tests import test_session_init_sleeper_calls as calls_t

PG_URL = os.environ.get("FTF_SESSION_INIT_TEST_POSTGRES_URL")
USER_ID, OPP_ID, LEAGUE_ID, MFL = sq.USER_ID, sq.OPP_ID, sq.LEAGUE_ID, sq.MFL
_RealThread = threading.Thread    # the harness swaps threading.Thread for its inline daemon

pytestmark = pytest.mark.usefixtures("no_real_network")


@pytest.fixture()
def pg(monkeypatch):
    if not PG_URL:
        pytest.skip("FTF_SESSION_INIT_TEST_POSTGRES_URL not set (disposable local Postgres)")
    url = make_url(PG_URL)
    # Only a disposable socket-only Postgres under /private/tmp: never a network host.
    assert url.drivername == "postgresql+psycopg2" and not url.host
    assert str(url.query.get("host", "")).startswith("/private/tmp/")
    schema = "sinit_" + uuid.uuid4().hex[:12]
    controller = create_engine(url, isolation_level="AUTOCOMMIT")
    with controller.connect() as conn:
        conn.execute(CreateSchema(schema))
    engine = create_engine(url, connect_args={"options": "-csearch_path=" + schema})
    # The league and member upserts pick their SQL by DATABASE_URL.
    monkeypatch.setattr(db_module, "DATABASE_URL", "postgresql://session-init-test")
    monkeypatch.setattr(calls_t, "create_engine", lambda *a, **kw: engine)
    gen = calls_t.harness.__wrapped__(monkeypatch)
    client, _calls = next(gen)
    pauses = []
    try:
        yield client, controller, pauses
    finally:
        for p in pauses:
            p.release.set()
            event.remove(engine, p.event_name, p.fn)
        try:
            next(gen)
        except StopIteration:
            pass
        engine.dispose()
        with controller.connect() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        controller.dispose()


class _Pause:
    """Hold thread `thread` just before the nth statement matching `pattern`
    (after it, with when="after"), until `release` is set."""

    def __init__(self, pauses, pattern, *, thread, nth=1, when="before"):
        self.rx, self.thread, self.nth, self.seen = re.compile(pattern, re.I), thread, nth, 0
        self.paused, self.release = threading.Event(), threading.Event()
        self.event_name = "before_cursor_execute" if when == "before" else "after_cursor_execute"
        event.listen(db_module.engine, self.event_name, self.fn)
        pauses.append(self)

    def fn(self, conn, cursor, statement, *a):
        if threading.current_thread().name == self.thread and self.rx.search(statement):
            self.seen += 1
            if self.seen == self.nth:
                self.paused.set()
                assert self.release.wait(60)


class _Runner(_RealThread):
    def __init__(self, name, fn):
        super().__init__(name=name, daemon=True)
        self.fn, self.result, self.exc = fn, None, None

    def run(self):
        try:
            self.result = self.fn()
        except BaseException as exc:  # noqa: BLE001
            self.exc = exc


def _blocked(controller, timeout=5.0):
    """True once some backend of this database waits on a row lock."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with controller.connect() as conn:
            if conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE "
                                 "datname = current_database() AND wait_event_type = 'Lock'")
                            ).scalar():
                return True
        time.sleep(0.05)
    return False


def _finish(*runners):
    for r in runners:
        r.join(60)
        assert not r.is_alive()
        assert r.exc is None, r.exc


def _nothing_names_the_caller(league_id):
    assert sq._user(USER_ID) is None and sq._league(league_id) is None
    assert USER_ID not in sq._members(league_id)
    assert sq._rows_naming(USER_ID) == []
    assert sq._rows_naming(db_module.analytics_session_id(sq.TOKEN)) == []


@pytest.mark.parametrize("league", ["sleeper_reinit", "sleeper_first_init", "mfl"])
def test_a_deletion_waits_for_the_locked_write_then_the_daemon_stops(pg, league):
    client, controller, pauses = pg
    league_id = MFL if league == "mfl" else LEAGUE_ID
    if league == "sleeper_reinit":
        sq._seed_league(LEAGUE_ID, USER_ID)
    p = _Pause(pauses, r"^\s*(UPDATE leagues SET|INSERT INTO leagues)", thread="init")
    init = _Runner("init", lambda: sq._init(client, league_id))
    init.start()
    assert p.paused.wait(30)
    deletion = _Runner("delete", lambda: accounts._delete_user_data(USER_ID))
    deletion.start()
    assert _blocked(controller), "the deletion didn't wait: the lock isn't held at the write"
    p.release.set()
    _finish(init, deletion)
    assert init.result.status_code == 200
    _nothing_names_the_caller(league_id)


@pytest.mark.parametrize("league", ["sleeper_reinit", "mfl"])
def test_b_a_deletion_that_commits_first_stops_the_daemon_at_its_first_lock(pg, league):
    client, controller, pauses = pg
    league_id = MFL if league == "mfl" else LEAGUE_ID
    if league == "sleeper_reinit":
        sq._seed_league(LEAGUE_ID, USER_ID)
    p = _Pause(pauses, r"FOR KEY SHARE", thread="init")
    init = _Runner("init", lambda: sq._init(client, league_id))
    init.start()
    assert p.paused.wait(30)
    deletion = _Runner("delete", lambda: accounts._delete_user_data(USER_ID))
    deletion.start()
    deletion.join(15)
    assert not deletion.is_alive(), "the deletion waited on a daemon that holds nothing yet"
    p.release.set()
    _finish(init, deletion)
    _nothing_names_the_caller(league_id)


def test_d2_a_leaguemate_deleted_just_before_the_replace_stays_deleted(pg):
    client, controller, pauses = pg
    sq._seed_league(LEAGUE_ID, USER_ID)
    db_module.upsert_user(OPP_ID)
    p = _Pause(pauses, r"^\s*DELETE FROM league_members", thread="init")
    init = _Runner("init", lambda: sq._init(client, LEAGUE_ID))
    init.start()
    assert p.paused.wait(30)
    gone = _Runner("delete-opp", lambda: accounts.delete_user_data(OPP_ID))
    gone.start()
    gone.join(15)
    assert not gone.is_alive()
    assert OPP_ID not in sq._members(LEAGUE_ID)
    p.release.set()
    _finish(init, gone)
    assert set(sq._members(LEAGUE_ID)) == {USER_ID}


def test_d5_the_importers_deletion_follows_the_update_only_members_write(pg):
    client, controller, pauses = pg
    db_module.upsert_user(OPP_ID)
    sq._seed_league(MFL, OPP_ID)
    p = _Pause(pauses, r"^\s*UPDATE league_members SET", thread="init", nth=2, when="after")
    init = _Runner("init", lambda: sq._init(client, MFL))
    init.start()
    assert p.paused.wait(30)                 # both member rows updated, uncommitted
    gone = _Runner("delete-opp", lambda: accounts.delete_user_data(OPP_ID))
    gone.start()
    assert _blocked(controller)              # on O's updated row
    p.release.set()
    _finish(init, gone)
    assert OPP_ID not in sq._members(MFL) and sq._league(MFL) is None
    assert sq._rows_naming(OPP_ID) == []


def test_d1_known_limit_a_leaguemate_deleted_after_the_replace_locked_their_row(pg):
    client, controller, pauses = pg
    sq._seed_league(LEAGUE_ID, USER_ID)
    db_module.upsert_user(OPP_ID)
    p = _Pause(pauses, r"^\s*INSERT INTO league_members", thread="init")
    init = _Runner("init", lambda: sq._init(client, LEAGUE_ID))
    init.start()
    assert p.paused.wait(30)                 # after the DELETE, before the INSERT
    gone = _Runner("delete-opp", lambda: accounts.delete_user_data(OPP_ID))
    gone.start()
    assert _blocked(controller)              # on O's row, which the replace deleted
    p.release.set()
    _finish(init, gone)                      # no deadlock: everyone completes
    assert sq._user(OPP_ID) is None
    assert OPP_ID in sq._members(LEAGUE_ID)  # the known limit: the re-inserted row survives
