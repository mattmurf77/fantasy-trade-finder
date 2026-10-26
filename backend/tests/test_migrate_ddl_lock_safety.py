"""Migration DDL must never block a boot (fix 1 after #416's ~90 s init_db).

On Postgres `ALTER TABLE … ADD COLUMN` takes ACCESS EXCLUSIVE before it checks
whether the column exists, so running every listed ALTER on every boot queued
exclusive locks behind the still-serving old instance. `_migrate_db` now
inspects the schema once and only issues DDL that is missing; a missing
column's ALTER runs under SET LOCAL lock_timeout, and if the table stays busy
the boot FAILS with MIGRATION_LOCK_BUSY (head-eng ruling on #427: readers need
every metadata column). docs/runbook.md § "Migration DDL never blocks boot".

  T-a test_migrated_db_issues_no_add_column_or_create_index /
      test_only_the_missing_column_and_index_get_ddl — a SQLite file DB with
      the full schema: a second `_migrate_db()` issues no ADD COLUMN and no
      CREATE INDEX; with one column and one index dropped, exactly that ALTER
      and that CREATE INDEX run.
  T-b test_persistent_lock_busy_fails_the_boot — the Postgres path forced by
      stubbing `_ddl_is_postgres` and `_execute_ddl`: the ALTER keeps raising
      pgcode 55P03, so it is tried exactly 10 times, MIGRATION_LOCK_BUSY is
      logged at ERROR, and `_migrate_db()` raises (init_db fails the boot).
      Once the lock clears, the next call (the redeploy) adds the column.
  T-c test_lock_timeout_is_set_first_in_the_same_transaction — on that path
      SET LOCAL lock_timeout and statement_timeout precede the ALTER on the
      same connection, inside its transaction.

No real Postgres test: .github/workflows/ci.yml has no Postgres service.

Sabotage record (each applied, observed red, reverted green):
  T-a  precheck bypassed (`if present is None or col in present` -> `if present
       is None`)                                                    -> RED (2026-10-26)
  T-b  persistent busy swallowed (log, then `return False` instead of raise)
                                                                    -> RED (2026-10-27)
  T-c  the two SET LOCAL lines removed                              -> RED (2026-10-26)
"""
import logging

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import OperationalError

import backend.database as db

TABLE, COLUMN = "deck_candidate_sets", "cand_pack_version"
ALTER = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} INTEGER"
INDEX_TABLE, INDEX = "players", "ix_players_position"


@pytest.fixture
def sqlite_engine(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "migrate.sqlite3"),
                           connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    yield engine
    engine.dispose()


def _ddl_log(engine):
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _record(conn, cursor, statement, params, context, executemany):
        statements.append(" ".join(statement.split()))

    return statements


def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _drop_column_and_index(engine):
    db._migrate_db()      # fully migrated (incl. the migrate-only indexes) ...
    with engine.begin() as conn:                     # ... then lose one of each
        conn.execute(text(f"ALTER TABLE {TABLE} DROP COLUMN {COLUMN}"))
        conn.execute(text(f"DROP INDEX IF EXISTS {INDEX}"))
    assert COLUMN not in _columns(engine, TABLE)


def test_migrated_db_issues_no_add_column_or_create_index(sqlite_engine):
    db._migrate_db()                         # fully migrated from here on
    statements = _ddl_log(sqlite_engine)
    db._migrate_db()
    assert [s for s in statements if "ADD COLUMN" in s.upper()] == []
    assert [s for s in statements if s.upper().startswith("CREATE") and " INDEX " in s.upper()] == []


def test_only_the_missing_column_and_index_get_ddl(sqlite_engine):
    _drop_column_and_index(sqlite_engine)
    statements = _ddl_log(sqlite_engine)
    db._migrate_db()
    assert [s for s in statements if "ADD COLUMN" in s.upper()] == [ALTER]
    creates = [s for s in statements if s.upper().startswith("CREATE") and " INDEX " in s.upper()]
    assert creates == [f"CREATE INDEX IF NOT EXISTS {INDEX} ON {INDEX_TABLE} (position)"]
    assert COLUMN in _columns(sqlite_engine, TABLE)


class _LockNotAvailable(Exception):
    pgcode = "55P03"


@pytest.fixture
def postgres_path(sqlite_engine, monkeypatch):
    """Force the Postgres branch on the SQLite DB: SET LOCAL is recorded but
    not sent (SQLite has no such statement), and while `busy` is on the ALTER
    for COLUMN raises the driver's lock_not_available."""
    _drop_column_and_index(sqlite_engine)
    monkeypatch.setattr(db, "_ddl_is_postgres", lambda: True)
    monkeypatch.setattr(db, "_DDL_RETRY_SLEEP_S", 0)
    real = db._execute_ddl
    state = {"busy": True, "calls": []}

    def fake_execute(conn, sql):
        state["calls"].append((conn, conn.in_transaction(), sql))
        if sql.startswith("SET LOCAL"):
            return
        if state["busy"] and sql == ALTER:
            raise OperationalError(sql, {}, _LockNotAvailable("canceling statement due to lock timeout"))
        real(conn, sql)

    monkeypatch.setattr(db, "_execute_ddl", fake_execute)
    return state


def test_persistent_lock_busy_fails_the_boot(sqlite_engine, postgres_path, caplog):
    with caplog.at_level(logging.ERROR, logger="backend.database"), \
            pytest.raises(RuntimeError, match=f"MIGRATION_LOCK_BUSY {TABLE}.{COLUMN}"):
        db._migrate_db()                     # init_db (and the boot) fails
    alters = [sql for _, _, sql in postgres_path["calls"] if "ADD COLUMN" in sql]
    assert alters == [ALTER] * db._DDL_ATTEMPTS == [ALTER] * 10
    busy = [r for r in caplog.records if "MIGRATION_LOCK_BUSY" in r.getMessage()]
    assert [r.levelno for r in busy] == [logging.ERROR]
    assert busy[0].getMessage().startswith(f"MIGRATION_LOCK_BUSY {TABLE}.{COLUMN}: ")
    assert "MIGRATION_DEFERRED" not in caplog.text
    assert COLUMN not in _columns(sqlite_engine, TABLE)

    postgres_path["busy"], postgres_path["calls"] = False, []
    db._migrate_db()                         # the redeploy: table is quiet
    assert [sql for _, _, sql in postgres_path["calls"] if "ADD COLUMN" in sql] == [ALTER]
    assert COLUMN in _columns(sqlite_engine, TABLE)


def test_lock_timeout_is_set_first_in_the_same_transaction(sqlite_engine, postgres_path):
    postgres_path["busy"] = False
    db._migrate_db()
    calls = postgres_path["calls"]
    assert [sql for _, _, sql in calls] == [
        f"SET LOCAL lock_timeout = '{db._DDL_LOCK_TIMEOUT}'",
        f"SET LOCAL statement_timeout = '{db._DDL_STATEMENT_TIMEOUT}'",
        ALTER,
    ]
    assert db._DDL_LOCK_TIMEOUT == "3s" and db._DDL_STATEMENT_TIMEOUT == "30s"
    assert len({id(conn) for conn, _, _ in calls}) == 1          # one connection
    assert all(in_tx for _, in_tx, _ in calls)                    # inside its transaction
