"""Migration DDL must never block a boot (fix 1 after #416's ~90 s init_db).

On Postgres `ALTER TABLE … ADD COLUMN` takes ACCESS EXCLUSIVE before it checks
whether the column exists, and CREATE INDEX IF NOT EXISTS takes SHARE before
its check, so running every listed DDL on every boot queued locks behind the
still-serving old instance. `_migrate_db` now reads the catalog (each read
under a 3 s lock_timeout) and issues only the DDL that is missing.
  * A missing column's ALTER runs under SET LOCAL lock_timeout +
    statement_timeout.
  * A missing index's CREATE runs under SET LOCAL lock_timeout only: a build
    is never cancelled.
  * If the table stays busy, the boot FAILS with MIGRATION_LOCK_BUSY (head-eng
    ruling on #427: readers need every metadata column).
docs/runbook.md § "Migration DDL never blocks boot".

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
  T-d test_missing_index_lock_busy_fails_the_boot — a missing index's CREATE
      runs under SET LOCAL lock_timeout and NO statement_timeout; persistent
      55P03 means 10 attempts, then MIGRATION_LOCK_BUSY <index> and a raise.
  T-e test_catalog_read_lock_busy_fails_the_boot — each catalog read first
      sets lock_timeout on its own connection; a lock-busy read raises
      MIGRATION_LOCK_BUSY <table>, not the empty-set fallback that would retry
      every column.

No real Postgres test: .github/workflows/ci.yml has no Postgres service.

Sabotage record (2026-10-26; each applied, observed red, reverted green):
  T-a  precheck bypassed (`if present is None or col in present` -> `if present
       is None`)                                                    -> RED
  T-b  persistent busy swallowed (`return False` instead of raising) -> RED
  T-c  the SET LOCAL lines removed                                  -> RED
  T-d  index guard given a statement_timeout                        -> RED
  T-e  lock-busy catalog read mapped to the empty-set fallback      -> RED
"""
import logging

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import OperationalError

import backend.database as db

TABLE, COLUMN = "deck_candidate_sets", "cand_pack_version"
ALTER = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} INTEGER"
INDEX_TABLE, INDEX = "players", "ix_players_position"
CREATE_INDEX = f"CREATE INDEX IF NOT EXISTS {INDEX} ON {INDEX_TABLE} (position)"
SET_LOCK = f"SET LOCAL lock_timeout = '{db._DDL_LOCK_TIMEOUT}'"
SET_STMT = f"SET LOCAL statement_timeout = '{db._DDL_STATEMENT_TIMEOUT}'"


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
    assert creates == [CREATE_INDEX]
    assert COLUMN in _columns(sqlite_engine, TABLE)


class _LockNotAvailable(Exception):
    pgcode = "55P03"


def _lock_busy(sql):
    return OperationalError(sql, {}, _LockNotAvailable("canceling statement due to lock timeout"))


@pytest.fixture
def postgres_path(sqlite_engine, monkeypatch):
    """Force the Postgres branch on the SQLite DB: every SET (session or LOCAL)
    is recorded but not sent (SQLite has no such statement), and any statement
    in `busy` raises the driver's lock_not_available."""
    _drop_column_and_index(sqlite_engine)
    monkeypatch.setattr(db, "_ddl_is_postgres", lambda: True)
    monkeypatch.setattr(db, "_DDL_RETRY_SLEEP_S", 0)
    real = db._execute_ddl
    state = {"busy": {ALTER}, "calls": []}

    def fake_execute(conn, sql):
        state["calls"].append((conn, conn.in_transaction(), sql))
        if sql.startswith("SET "):
            return
        if sql in state["busy"]:
            raise _lock_busy(sql)
        real(conn, sql)

    monkeypatch.setattr(db, "_execute_ddl", fake_execute)
    return state


def _txn_of(calls, statement):
    """The statements issued on the connection that ran `statement` (its txn)."""
    conn = next(c for c, _, sql in calls if sql == statement)
    return [(in_tx, sql) for c, in_tx, sql in calls if c is conn]


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

    postgres_path["busy"], postgres_path["calls"] = set(), []
    db._migrate_db()                         # the redeploy: table is quiet
    assert [sql for _, _, sql in postgres_path["calls"] if "ADD COLUMN" in sql] == [ALTER]
    assert COLUMN in _columns(sqlite_engine, TABLE)


def test_lock_timeout_is_set_first_in_the_same_transaction(sqlite_engine, postgres_path):
    postgres_path["busy"] = set()
    db._migrate_db()
    txn = _txn_of(postgres_path["calls"], ALTER)
    assert [sql for _, sql in txn] == [SET_LOCK, SET_STMT, ALTER]
    assert all(in_tx for in_tx, _ in txn)                          # inside its transaction
    assert db._DDL_LOCK_TIMEOUT == "3s" and db._DDL_STATEMENT_TIMEOUT == "30s"


def test_missing_index_lock_busy_fails_the_boot(sqlite_engine, postgres_path, caplog):
    postgres_path["busy"] = {CREATE_INDEX}
    with caplog.at_level(logging.ERROR, logger="backend.database"), \
            pytest.raises(RuntimeError, match=f"MIGRATION_LOCK_BUSY {INDEX}"):
        db._migrate_db()
    creates = [sql for _, _, sql in postgres_path["calls"] if sql == CREATE_INDEX]
    assert len(creates) == db._DDL_ATTEMPTS == 10
    txn = _txn_of(postgres_path["calls"], CREATE_INDEX)
    assert [sql for _, sql in txn][:2] == [SET_LOCK, CREATE_INDEX]  # lock_timeout first ...
    assert SET_STMT not in [sql for _, sql in txn]                   # ... never a statement_timeout
    assert [r.getMessage().split(":")[0] for r in caplog.records
            if "MIGRATION_LOCK_BUSY" in r.getMessage()] == [f"MIGRATION_LOCK_BUSY {INDEX}"]


def test_catalog_read_lock_busy_fails_the_boot(sqlite_engine, monkeypatch, caplog):
    db._migrate_db()
    monkeypatch.setattr(db, "_ddl_is_postgres", lambda: True)
    issued: list[str] = []
    real = db._execute_ddl

    def fake_execute(conn, sql):
        issued.append(sql)
        if not sql.startswith("SET "):
            real(conn, sql)

    monkeypatch.setattr(db, "_execute_ddl", fake_execute)
    original = Inspector.get_columns

    def get_columns(self, table_name, *args, **kwargs):
        if table_name == TABLE:
            raise _lock_busy("SELECT … pg_attribute")
        return original(self, table_name, *args, **kwargs)

    monkeypatch.setattr(Inspector, "get_columns", get_columns)
    statements = _ddl_log(sqlite_engine)
    with caplog.at_level(logging.ERROR, logger="backend.database"), \
            pytest.raises(RuntimeError, match=f"MIGRATION_LOCK_BUSY {TABLE}"):
        db._migrate_db()
    assert f"SET lock_timeout = '{db._DDL_LOCK_TIMEOUT}'" in issued   # before each catalog read
    assert [s for s in statements if "ADD COLUMN" in s.upper()] == []  # no fallback ALTERs
    assert any(r.levelno == logging.ERROR and r.getMessage().startswith(f"MIGRATION_LOCK_BUSY {TABLE}:")
               for r in caplog.records)
