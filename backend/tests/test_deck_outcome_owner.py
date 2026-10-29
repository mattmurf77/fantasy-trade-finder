"""G3-e (legal R28.22; head-eng's routing, 2026-10-29): deck_outcomes carries
the acting user's id, and account deletion and export also match on it.

An outcome then stays reachable however its deck's evidence is stored or
pruned, so these tests build outcomes that neither the user's rows nor their
packs reach (an impression id with no row and no pack).
"""
import importlib.util
import inspect
import re
from pathlib import Path
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


def _pre_g3e(tmp_path):
    """A database whose deck_outcomes is the table as it was before G3-e."""
    url = f"sqlite:///{tmp_path / 'g3e.db'}"
    eng = create_engine(url)
    db.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE deck_outcomes"))
        conn.execute(text(
            "CREATE TABLE deck_outcomes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "impression_id VARCHAR NOT NULL, action VARCHAR NOT NULL, dwell_ms INTEGER, "
            "detail_expanded INTEGER, calc_opened INTEGER, acted_at VARCHAR NOT NULL)"))
        conn.execute(text(
            "CREATE INDEX ix_deck_outcomes_impression ON deck_outcomes (impression_id)"))
        conn.execute(text("INSERT INTO deck_outcomes (impression_id, action, acted_at) "
                          "VALUES ('old', 'like', '2026-10-01T00:00:00+00:00')"))
    return url, eng


def _indexes(eng):
    return {i["name"]: i["column_names"] for i in sa_inspect(eng).get_indexes("deck_outcomes")}


def test_boot_adds_the_column_never_the_index_and_no_backfill(tmp_path, monkeypatch):
    """init_db adds the column to an existing table and never builds the index
    there: a plain CREATE INDEX holds a SHARE lock that blocks every outcome
    write for its scan (release-lead, #541). A fresh DB gets it from the
    declaration."""
    url, eng = _pre_g3e(tmp_path)
    monkeypatch.setattr(db, "engine", eng)
    monkeypatch.setattr(db, "DATABASE_URL", url)
    for _ in range(2):                            # the second boot changes nothing
        db.init_db()
        assert "user_id" in {c["name"] for c in sa_inspect(eng).get_columns("deck_outcomes")}
        assert "ix_deck_outcomes_user" not in _indexes(eng)
        with eng.connect() as conn:
            assert conn.execute(text(
                "SELECT impression_id, user_id FROM deck_outcomes")).all() == [("old", None)]
    eng.dispose()
    assert {i.name for i in db.deck_outcomes_table.indexes} >= {"ix_deck_outcomes_user"}
    fresh = create_engine("sqlite://")
    db.metadata.create_all(fresh)
    assert _indexes(fresh)["ix_deck_outcomes_user"] == ["user_id"]
    fresh.dispose()


def _script():
    path = Path(__file__).resolve().parents[2] / "scripts/create_outcome_owner_index.py"
    spec = importlib.util.spec_from_file_location("create_outcome_owner_index", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


def test_the_script_builds_it_on_an_existing_table_and_check_writes_nothing(tmp_path, monkeypatch):
    script = _script()
    url, eng = _pre_g3e(tmp_path)
    monkeypatch.setattr(db, "engine", eng)
    monkeypatch.setattr(db, "DATABASE_URL", url)
    db.init_db()
    assert script.main(["--check"]) == 0 and script.state(eng) == "missing"
    assert script.main([]) == 0 and script.state(eng) == "valid"
    assert _indexes(eng)["ix_deck_outcomes_user"] == ["user_id"]
    assert script.build(eng) == "valid"           # idempotent
    eng.dispose()


def test_the_scripts_postgres_build_is_concurrent():
    """Postgres: CONCURRENTLY (no write lock) in autocommit (it can't run in a
    transaction), a lock_timeout on its brief locks, and an INVALID leftover of
    a failed build dropped concurrently before the rebuild."""
    src = inspect.getsource(_script().build)
    assert re.search(
        r'if engine\.dialect\.name == "postgresql":\n'
        r'        with engine\.connect\(\)\.execution_options\(isolation_level="AUTOCOMMIT"\) as conn:\n'
        r"            conn\.execute\(text\(f\"SET lock_timeout = '\{LOCK_TIMEOUT\}'\"\)\)\n"
        r'            if current == "invalid":\n'
        r'                conn\.execute\(text\(f"DROP INDEX CONCURRENTLY IF EXISTS \{INDEX\}"\)\)\n'
        r'            conn\.execute\(text\(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS \{INDEX\} "\n'
        r'                              "ON deck_outcomes \(user_id\)"\)\)\n', src)
    assert _script().LOCK_TIMEOUT == "5s"
    # And the boot path never builds it.
    assert "ix_deck_outcomes_user" not in inspect.getsource(db._migrate_db)


def test_three_paths_one_run(store):
    """onboarding-eng's ask for the #523/#541 resync (release-lead's QA test,
    ported): one outcome reachable only by its row, one only by a pack
    contract id (#523), one only by user_id (G3-e). Each is exported once,
    all are deleted in one run, and another user's outcome on a contract id
    past the pack's cards stays."""
    with store.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id="t3"))
        conn.execute(insert(db.users_table).values(sleeper_user_id="t30"))
        conn.execute(insert(db.deck_impressions_table).values(
            impression_id="t3-d:0", user_id="t3", league_id="lg", deck_job_id="t3-d",
            card_index=0, propensity=1.0, served_at="2026-10-28T00:00:00+00:00"))
        conn.execute(insert(db.deck_evidence_packs_table).values(
            run_id="t3-p", user_id="t3", league_id="lg", served_at="2026-10-28T00:00:00+00:00",
            pack_version=1, header_json='{"run": {}}', cards_blob=b"x", checksum="c" * 64,
            card_count=2, created_at="2026-10-28T00:00:00+00:00"))
        ids = {tag: _outcome(conn, iid, owner) for tag, iid, owner in (
            ("row", "t3-d:0", None),          # the row path only (pre-G3-e)
            ("pack", "t3-p:1", None),         # the pack path only
            ("col", "t3-gone:5", "t3"),       # the owner column only
            ("other", "t3-p:2", "t30"))}      # past card_count, another user's
    exported = accounts.export_user_data("t3")["tables"]["deck_outcomes"]
    assert [r["id"] for r in exported] == sorted(ids[t] for t in ("row", "pack", "col"))
    counts = accounts.delete_user_data("t3")
    assert [r["id"] for r in _outcomes(store)] == [ids["other"]]
    assert counts["deck_outcomes_by_owner_deleted"] == 1
