"""Trade-relevance engine P0 — schema layer (docs/plans/trade-relevance-engine/lld.md §3).

Sabotage-proven structural tests (house convention, LLD §7): every test names
the sabotage that must make it fail. Review checks the sabotage list, not the
green run.

Covers:
  (a) T-25 migration equivalence — a fresh `create_all()` DB and a legacy
      fixture DB carried forward by `_migrate_db()` must have IDENTICAL
      `PRAGMA table_info` for every touched table, and the two new indexes
  (b) T-25 second half — `_migrate_db()` twice is a no-op (idempotent DDL)
  (c) `uq_pass_run` really rejects a duplicate (pass_name, run_date) — the
      double-POST claim mechanism (T-2's prerequisite)
  (d) `save_deck_outcome` accepts all ten legal actions and counts-and-drops
      an illegal one

Harness pattern follows test_analytics_p0.py: file-backed SQLite (so the
schema survives across engine handles), patched into `backend.database`.
"""
import pytest
from sqlalchemy import create_engine, text
from unittest.mock import patch

import backend.database as db_module
from backend.database import (
    DECK_OUTCOME_ACTIONS,
    cron_pass_runs_table,
    metadata,
    save_deck_outcome,
)


# The P0 schema surface under test. Keep these three lists in lockstep with
# LLD §3.2/§3.3 — a column added to the Table declaration but forgotten in
# `migration_cols` is exactly what (a) is here to catch.
P0_NEW_TABLES = ["cron_pass_runs", "deck_class_stats", "deck_job_stats"]
P0_NEW_COLUMNS = [
    ("trade_decisions", "impression_id"),
    ("trade_matches",   "impression_id_a"),
    ("trade_matches",   "impression_id_b"),
    ("trade_matches",   "join_quality_b"),
    ("deck_outcomes",   "join_quality"),
    ("deck_outcomes",   "source_match_id"),
]
P0_TOUCHED_TABLES = sorted(
    set(P0_NEW_TABLES) | {t for t, _ in P0_NEW_COLUMNS}
)
P0_NEW_INDEXES = [
    ("deck_outcomes",   "ix_deck_outcomes_action"),
    ("trade_decisions", "ix_trade_decisions_impression"),
]


# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------

def _engine(path):
    return create_engine(f"sqlite:///{path}",
                         connect_args={"check_same_thread": False})


def _boot(eng):
    """Exactly what `init_db()` does at startup, minus the experiment seed."""
    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "DATABASE_URL", "sqlite:///p0-relevance"):
        metadata.create_all(eng)
        db_module._migrate_db()


def _table_info(eng, table):
    """PRAGMA table_info as a comparable structure: (name, type, notnull,
    default, pk) per column, ordered by cid."""
    with eng.connect() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA table_info('{table}')").fetchall()
    return [(r[1], (r[2] or "").upper(), r[3], r[4], r[5]) for r in rows]


def _indexes(eng, table):
    with eng.connect() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA index_list('{table}')").fetchall()
    return {r[1] for r in rows}


def _schema_dump(eng):
    with eng.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "ORDER BY type, name").fetchall()
    return [tuple(r) for r in rows]


@pytest.fixture()
def fresh_db(tmp_path):
    """A brand-new DB built by create_all() + _migrate_db()."""
    eng = _engine(tmp_path / "fresh.db")
    _boot(eng)
    return eng


@pytest.fixture()
def migrated_legacy_db(tmp_path):
    """A DB that predates the P0 diff, then booted on the NEW code.

    Built by creating today's schema and then *de-migrating* it — dropping
    the three new tables and the six new columns — which is the honest
    stand-in for "the old code created this file". Then create_all() +
    _migrate_db() run on top, exactly as a real deploy would.

    Note the DROP COLUMNs only work because the P0 indexes are declared in
    the idempotent `_migrate_db()` list rather than as `Index(...)` on the
    Table objects (SQLite refuses to drop an indexed column) — which is also
    the only mechanism that reaches EXISTING production tables.
    """
    eng = _engine(tmp_path / "legacy.db")
    metadata.create_all(eng)
    with eng.begin() as conn:
        for tbl in P0_NEW_TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
        for tbl, col in P0_NEW_COLUMNS:
            conn.execute(text(f"ALTER TABLE {tbl} DROP COLUMN {col}"))
    # Sanity: the fixture must actually be legacy, or (a) proves nothing.
    for tbl, col in P0_NEW_COLUMNS:
        assert col not in {c[0] for c in _table_info(eng, tbl)}, (
            f"legacy fixture still has {tbl}.{col}")
    _boot(eng)
    return eng


# ---------------------------------------------------------------------------
# (a) T-25 — fresh create_all() DB == migrated legacy DB
# ---------------------------------------------------------------------------

def test_t25_fresh_and_migrated_schemas_are_identical(fresh_db,
                                                      migrated_legacy_db):
    """SABOTAGE: drop any of the six entries from `migration_cols` in
    `_migrate_db()` (while leaving its `Column(...)` on the Table), or
    misspell a column type there — the legacy DB then lacks the column, or
    has a different one, and the PRAGMA comparison diverges."""
    for tbl in P0_TOUCHED_TABLES:
        fresh = _table_info(fresh_db, tbl)
        legacy = _table_info(migrated_legacy_db, tbl)
        assert fresh, f"{tbl} missing from the fresh DB entirely"
        assert fresh == legacy, (
            f"{tbl}: fresh create_all() schema != migrated legacy schema\n"
            f"  fresh : {fresh}\n  legacy: {legacy}")


def test_t25_new_columns_and_tables_present_on_both_paths(
        fresh_db, migrated_legacy_db):
    """SABOTAGE: delete a new `Column(...)` from a Table declaration (so
    create_all() stops emitting it), or drop a new Table from the module —
    the presence assertion fails on the path that lost it."""
    for eng, label in ((fresh_db, "fresh"), (migrated_legacy_db, "migrated")):
        for tbl in P0_NEW_TABLES:
            assert _table_info(eng, tbl), f"{label}: table {tbl} not created"
        for tbl, col in P0_NEW_COLUMNS:
            names = {c[0] for c in _table_info(eng, tbl)}
            assert col in names, f"{label}: {tbl}.{col} missing"


def test_t25_new_indexes_exist_on_both_paths(fresh_db, migrated_legacy_db):
    """SABOTAGE: remove either entry from the idempotent CREATE INDEX list
    in `_migrate_db()` — production tables (which create_all() never
    re-indexes) silently lose the index the P0-4 aggregation scan needs."""
    for eng, label in ((fresh_db, "fresh"), (migrated_legacy_db, "migrated")):
        for tbl, idx in P0_NEW_INDEXES:
            assert idx in _indexes(eng, tbl), f"{label}: {idx} missing on {tbl}"


def test_t25_new_columns_are_nullable_no_notnull_alter(fresh_db):
    """SABOTAGE: declare any added column `nullable=False` — SQLite forbids
    ADD COLUMN NOT NULL without a constant default, so the ALTER would fail
    silently in the swallow-all try/except and the two paths would diverge.
    Pinning notnull=0 catches the intent before the divergence does."""
    for tbl, col in P0_NEW_COLUMNS:
        info = {c[0]: c for c in _table_info(fresh_db, tbl)}
        assert info[col][2] == 0, f"{tbl}.{col} is NOT NULL — illegal ALTER"
        assert info[col][3] is None, f"{tbl}.{col} carries a default"


# ---------------------------------------------------------------------------
# (b) T-25 second half — migration idempotence
# ---------------------------------------------------------------------------

def test_migrate_db_twice_is_a_no_op(tmp_path):
    """SABOTAGE: use a non-idempotent DDL form — `CREATE INDEX` without
    `IF NOT EXISTS`, or an ALTER outside the per-statement transaction — and
    the second run either raises or leaves a different sqlite_master."""
    eng = _engine(tmp_path / "twice.db")
    _boot(eng)
    dump1 = _schema_dump(eng)
    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "DATABASE_URL", "sqlite:///p0-relevance"):
        db_module._migrate_db()
    dump2 = _schema_dump(eng)
    assert dump1 == dump2, "second _migrate_db() run changed the schema"


def test_p0_config_keys_seeded_once_with_expected_defaults(tmp_path):
    """SABOTAGE: seed `cron.pass_disabled.*` (inverted-polarity fail-safe —
    absent MUST mean the pass runs, LLD §2.4), or change a default value
    without updating docs/config-reference.md."""
    eng = _engine(tmp_path / "cfg.db")
    _boot(eng)
    with eng.connect() as conn:
        rows = dict(conn.exec_driver_sql(
            "SELECT key, value FROM model_config").fetchall())
    assert rows["class_demotion_floor"] == 0.5
    assert rows["class_demotion_min_views"] == 200.0
    assert rows["dedup_overlap_tau"] == 0.75
    assert not [k for k in rows if k.startswith("cron.pass_disabled")], (
        "cron.pass_disabled.* must stay UNSEEDED — absent means the pass runs")


# ---------------------------------------------------------------------------
# (c) uq_pass_run — the double-POST claim mechanism
# ---------------------------------------------------------------------------

def test_uq_pass_run_rejects_duplicate_pass_and_date(fresh_db):
    """SABOTAGE: drop the `UniqueConstraint("pass_name","run_date")` from
    `cron_pass_runs_table` — the second claim then succeeds, two workers
    both believe they own the pass, and every pass body runs twice on a
    Render retry (T-2's whole failure mode)."""
    row = dict(pass_name="flag_agg", run_date="2026-08-14", status="running",
               started_at="2026-08-14T02:00:00+00:00", attempt=1)
    with fresh_db.begin() as conn:
        conn.execute(cron_pass_runs_table.insert().values(**row))
    with pytest.raises(Exception):
        with fresh_db.begin() as conn:
            conn.execute(cron_pass_runs_table.insert().values(**row))
    # A different date for the same pass, and a different pass on the same
    # date, are both legal — the constraint is on the PAIR.
    with fresh_db.begin() as conn:
        conn.execute(cron_pass_runs_table.insert().values(
            **{**row, "run_date": "2026-08-15"}))
        conn.execute(cron_pass_runs_table.insert().values(
            **{**row, "pass_name": "dedup"}))
    with fresh_db.connect() as conn:
        n = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM cron_pass_runs").scalar()
    assert n == 3


def test_uq_class_stat_rejects_duplicate_class_day(fresh_db):
    """SABOTAGE: drop `uq_class_stat` — the nightly aggregation pass then
    appends a second row for a class it already computed today, and the
    "latest stat_date is live" read becomes ambiguous."""
    row = dict(archetype="window", shape_bucket="2x1", value_band="3000",
               exposures=250, flags=12, flag_rate_shrunk=0.05, demotion=0.9,
               computed_at="2026-08-14T02:00:00+00:00", stat_date="2026-08-14")
    with fresh_db.begin() as conn:
        conn.execute(db_module.deck_class_stats_table.insert().values(**row))
    with pytest.raises(Exception):
        with fresh_db.begin() as conn:
            conn.execute(db_module.deck_class_stats_table.insert().values(**row))


# ---------------------------------------------------------------------------
# (d) DECK_OUTCOME_ACTIONS — the widened enum, counted-and-dropped rejection
# ---------------------------------------------------------------------------

def test_deck_outcome_actions_is_the_ten_label_set():
    """SABOTAGE: drop one of the four D2 disposition labels from
    `DECK_OUTCOME_ACTIONS` — the disposition writer's rows are then silently
    dropped and the whole D2 label loop reports zero."""
    assert DECK_OUTCOME_ACTIONS == frozenset({
        "viewed", "like", "pass", "not_interested", "propose", "undo",
        "accepted", "declined", "accepted_by_partner", "declined_by_partner",
    })


def test_save_deck_outcome_accepts_all_ten_actions(fresh_db):
    """SABOTAGE: leave the old inline six-tuple in `save_deck_outcome`
    instead of reading DECK_OUTCOME_ACTIONS — the four disposition labels
    are rejected and no row lands."""
    with patch.object(db_module, "engine", fresh_db):
        for action in sorted(DECK_OUTCOME_ACTIONS):
            save_deck_outcome(f"imp_{action}", action)
    with fresh_db.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT action FROM deck_outcomes ORDER BY action").fetchall()
    assert [r[0] for r in rows] == sorted(DECK_OUTCOME_ACTIONS)


def test_save_deck_outcome_raises_on_an_illegal_action(fresh_db):
    """SABOTAGE: remove the enum guard (accept any string) — 'clicked' then
    writes a junk label row, which is the taxonomy hole this guard exists to
    close.

    The guard RAISES rather than dropping, deliberately. save_deck_outcome is
    a low-level writer whose only production caller
    (server._save_deck_outcome_safe) already wraps it in try/except + log, so
    the always-200 contract is held one layer up and a raise never reaches a
    client. Raising is what catches a mistyped action string in dev and CI —
    P0-3 adds four new labels, and a silent drop would surface only as an
    inexplicably low join rate weeks later. Client-supplied junk never gets
    here: the caller validates impression ownership first."""
    with patch.object(db_module, "engine", fresh_db):
        save_deck_outcome("imp_ok", "propose")
        for bad in ("clicked", ""):
            with pytest.raises(ValueError):
                save_deck_outcome("imp_bad", bad)
    with fresh_db.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT impression_id, action FROM deck_outcomes").fetchall()
    assert [tuple(r) for r in rows] == [("imp_ok", "propose")]


def test_disposition_columns_default_null_on_swipe_rows(fresh_db):
    """SABOTAGE: give `join_quality` / `source_match_id` a non-NULL default
    — swipe-time rows would then claim a join provenance they don't have,
    and the exact-join-rate metric (M2) would read as 100% by construction."""
    with patch.object(db_module, "engine", fresh_db):
        save_deck_outcome("imp_swipe", "like")
    with fresh_db.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT join_quality, source_match_id FROM deck_outcomes"
        ).fetchone()
    assert row == (None, None)
