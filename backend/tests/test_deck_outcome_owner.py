"""G3-e (legal R28.22; head-eng's routing, 2026-10-29): deck_outcomes carries
the acting user's id, and account deletion and export also match on it.

An outcome then stays reachable however its deck's evidence is stored or
pruned, so these tests build outcomes that neither the user's rows nor their
packs reach (an impression id with no row and no pack).
"""
import inspect
import re
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, insert, inspect as sa_inspect, select, text

from backend import accounts, database as db, server

UID = "g3e-owner"
OTHER = "g3e-other"
AID = "g3e-account"
ALIAS = accounts.account_user_id(AID)


@pytest.fixture
def store(monkeypatch):
    eng = create_engine("sqlite:///:memory:")
    db.metadata.create_all(eng)
    monkeypatch.setattr(db, "engine", eng)
    with eng.begin() as conn:
        conn.execute(insert(db.accounts_table).values(
            account_id=AID, sleeper_user_id=UID, created_at="2026-10-29"))
        for uid in (UID, ALIAS, OTHER):
            conn.execute(insert(db.users_table).values(sleeper_user_id=uid))
    yield eng
    eng.dispose()


def _impression(conn, impression_id, user_id):
    conn.execute(insert(db.deck_impressions_table).values(
        impression_id=impression_id, user_id=user_id, league_id="league",
        deck_job_id="job", card_index=0, propensity=1,
        served_at=datetime.now(timezone.utc).isoformat()))


def _outcome(conn, impression_id, user_id):
    return conn.execute(insert(db.deck_outcomes_table).values(
        impression_id=impression_id, action="like", user_id=user_id,
        acted_at="2026-10-29T00:00:00+00:00")).inserted_primary_key[0]


def _outcomes(eng):
    with eng.connect() as conn:
        return conn.execute(select(db.deck_outcomes_table)
                            .order_by(db.deck_outcomes_table.c.id)).mappings().all()


def test_the_write_stamps_the_acting_user(store):
    with store.begin() as conn:
        _impression(conn, "owned", UID)
    assert db.save_deck_outcome("owned", "like", acting_user_id=UID)
    # The owner check is unchanged, so the column only ever names the owner.
    assert not db.save_deck_outcome("owned", "pass", acting_user_id=OTHER)
    assert [(r["action"], r["user_id"]) for r in _outcomes(store)] == [("like", UID)]


def test_the_session_users_outcome_carries_their_id(store, monkeypatch):
    """Through _save_deck_outcome_safe, the one call idiom every route uses."""
    monkeypatch.setattr(server, "_deck_signal_v2_enabled", lambda: True)
    monkeypatch.setattr(server, "_deck_taste_enabled", lambda: False)
    monkeypatch.setattr(server, "_sessions", {"tok": {"user_id": UID, "verified": True}})
    with store.begin() as conn:
        _impression(conn, "owned", UID)
    with server.app.test_request_context("/api/x", method="POST",
                                         headers={"X-Session-Token": "tok"}):
        server._save_deck_outcome_safe("owned", "like", acting_user_id=UID)
    assert [r["user_id"] for r in _outcomes(store)] == [UID]


def test_deletion_reaches_an_outcome_only_its_owner_column_names(store):
    with store.begin() as conn:
        _impression(conn, "owned", UID)
        _outcome(conn, "owned", UID)              # the row reaches it, and the column
        _outcome(conn, "owned", None)             # pre-G3-e: the row only (no backfill)
        _outcome(conn, "gone-job:3", UID)         # no row, no pack: the column only
        _outcome(conn, "gone-job:4", ALIAS)       # an alias's, the same
        _impression(conn, "theirs", OTHER)
        kept = [_outcome(conn, "theirs", OTHER), _outcome(conn, "theirs", None),
                _outcome(conn, "gone-job:9", OTHER)]
    counts = accounts.delete_user_data(UID)
    assert [r["id"] for r in _outcomes(store)] == kept
    assert counts["deck_outcomes_deleted"] == 2           # today's path, unchanged
    assert counts["deck_outcomes_by_owner_deleted"] == 2  # what only the column reached


def test_export_has_each_owned_outcome_once_in_id_order(store):
    with store.begin() as conn:
        _impression(conn, "owned", UID)
        orphan = _outcome(conn, "gone-job:3", UID)    # the column only, and the lowest id
        both = _outcome(conn, "owned", UID)           # reached both ways: exported once
        legacy = _outcome(conn, "owned", None)        # the row only
        alias = _outcome(conn, "gone-job:4", ALIAS)
        _impression(conn, "theirs", OTHER)
        _outcome(conn, "theirs", OTHER)
        _outcome(conn, "gone-job:9", OTHER)
    exported = accounts.export_user_data(UID)["tables"]["deck_outcomes"]
    assert [r["id"] for r in exported] == [orphan, both, legacy, alias]
    assert [r["user_id"] for r in exported] == [UID, UID, None, ALIAS]


def test_migration_adds_the_column_and_index_without_backfill(tmp_path, monkeypatch, capsys):
    url = f"sqlite:///{tmp_path / 'g3e.db'}"
    eng = create_engine(url)
    db.metadata.create_all(eng)
    with eng.begin() as conn:                     # the table as it was before G3-e
        conn.execute(text("DROP TABLE deck_outcomes"))
        conn.execute(text(
            "CREATE TABLE deck_outcomes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "impression_id VARCHAR NOT NULL, action VARCHAR NOT NULL, dwell_ms INTEGER, "
            "detail_expanded INTEGER, calc_opened INTEGER, acted_at VARCHAR NOT NULL)"))
        conn.execute(text(
            "CREATE INDEX ix_deck_outcomes_impression ON deck_outcomes (impression_id)"))
        conn.execute(text("INSERT INTO deck_outcomes (impression_id, action, acted_at) "
                          "VALUES ('old', 'like', '2026-10-01T00:00:00+00:00')"))
    monkeypatch.setattr(db, "engine", eng)
    monkeypatch.setattr(db, "DATABASE_URL", url)
    for _ in range(2):                            # the second run changes nothing
        db._migrate_db()
        insp = sa_inspect(eng)
        assert "user_id" in {c["name"] for c in insp.get_columns("deck_outcomes")}
        indexes = {i["name"]: i["column_names"] for i in insp.get_indexes("deck_outcomes")}
        assert indexes["ix_deck_outcomes_user"] == ["user_id"]
        with eng.connect() as conn:
            assert conn.execute(text(
                "SELECT impression_id, user_id FROM deck_outcomes")).all() == [("old", None)]
    assert "ix_deck_outcomes_user not built" not in capsys.readouterr().out
    eng.dispose()
    # A fresh database (create_all) gets the index from the metadata.
    assert {i.name for i in db.deck_outcomes_table.indexes} >= {"ix_deck_outcomes_user"}


def test_the_index_build_is_bounded_on_postgres():
    """A plain CREATE INDEX holds off outcome writes for its scan: on Postgres
    it waits at most 5 s for its lock and runs at most 60 s, in the same
    transaction as the build (SET LOCAL), and a failure is caught."""
    src = inspect.getsource(db._migrate_db)
    assert re.search(
        r"    try:\n"
        r"        with engine\.begin\(\) as conn:\n"
        r"            if conn\.dialect\.name == \"postgresql\":\n"
        r"                conn\.execute\(text\(\"SET LOCAL lock_timeout = '5s'\"\)\)\n"
        r"                conn\.execute\(text\(\"SET LOCAL statement_timeout = '60s'\"\)\)\n"
        r"            conn\.execute\(text\(\n"
        r"                \"CREATE INDEX IF NOT EXISTS ix_deck_outcomes_user ON deck_outcomes \(user_id\)\"\)\)\n"
        r"    except Exception as e:\n", src)
    # After the column's ALTER TABLE, which the index needs.
    assert (src.index('("deck_outcomes",      "user_id",                   "VARCHAR")')
            < src.index("ALTER TABLE {table} ADD COLUMN")
            < src.index("CREATE INDEX IF NOT EXISTS ix_deck_outcomes_user"))
