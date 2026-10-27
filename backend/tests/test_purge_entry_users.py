"""scripts/purge_entry_users.py — the one-time purge of orphaned ESPN/MFL entry users.

Legal R28.12 row 2 and R28.16; head-eng 2026-10-26; onboarding-eng 2026-10-26.
A temporary SQLite file only (synthetic rows). Pinned here:
  - head-eng's target filter: unverified + created before the cutoff, or no
    users row at all; verified, after-cutoff and no-created_at ids are skipped
    and counted, never touched;
  - dry run changes nothing; --execute refuses a stale --expect, removes every
    target's key-column rows through accounts.delete_user_data (credentials and
    the MFL pick-grid owner included) and anonymizes the shared trade match;
  - --verify fails before, passes after, and fails on a credential left on a
    skipped entry user;
  - no id ever reaches stdout or the log, a DB error included (hide_parameters
    engines plus a type-only top-level handler);
  - every mode prints the DB identity first and refuses local SQLite without
    --allow-local; read modes run on the read-only engine;
  - discovery covers every user-id column delete_user_data filters on (its SQL
    is captured; a new column the script doesn't discover fails here).
"""
import os
import re
import sys

import pytest
from sqlalchemy import Float, Integer, LargeBinary, create_engine, event, insert, select

from backend import accounts, database as db

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import purge_entry_users as purge  # noqa: E402

CUTOFF = "2026-10-26T00:00:00Z"
BEFORE, AFTER = "2026-09-01T12:00:00+00:00", "2026-10-27T09:00:00+00:00"
SWID = "{3C0FFEE0-AAAA-BBBB-CCCC-DDDDEEEEFFFF}"
ESPN = f"entry:espn:{SWID}"                       # target: users row, unverified, before
MFL = "entry:mfl:61408.f0003"                     # target: users row, unverified, before
ORPHAN = "entry:espn:4242.t4"                     # target: no users row
VERIFIED = "entry:mfl:61408.f0007"                # skipped: verified_via set
LATE = "entry:espn:{0BADF00D-1111-2222-3333-444455556666}"   # skipped: after the cutoff
UNDATED = "entry:espn:7777.t1"                    # skipped: no created_at
SLEEPER = "313560442465169408"                    # untouched
ACCT = "acct_mfl-signin-proof"                    # untouched
ALL_IDS = (ESPN, MFL, ORPHAN, VERIFIED, LATE, UNDATED, SLEEPER, ACCT)


def seed(conn, table, marker, **values):
    """Fill required columns with a synthetic marker; scenarios set join keys."""
    row = {}
    for col in table.columns:
        if col.name in values or col.nullable or col.default is not None or col.server_default is not None:
            continue
        if col.primary_key and isinstance(col.type, Integer):
            continue
        row[col.name] = (1 if isinstance(col.type, (Integer, Float))
                         else b"x" if isinstance(col.type, LargeBinary) else "x-" + marker)
    row.update(values)
    conn.execute(insert(table).values(**row))


def _import_rows(conn, uid, n, platform, league):
    """What an entry session left behind: sign-in, session, board, import."""
    seed(conn, db.identity_links_table, f"link{n}", sleeper_user_id=uid, device_id=f"dev-{n}")
    seed(conn, db.sessions_table, f"sess{n}", token_hash=f"tok-{n}", user_id=uid)
    seed(conn, db.member_rankings_table, f"rank{n}", user_id=uid, league_id=league)
    seed(conn, db.swipe_decisions_table, f"swipe{n}", user_id=uid)
    seed(conn, db.trade_decisions_table, f"td{n}", user_id=uid, league_id=league)
    seed(conn, db.leagues_table, f"lg{n}", sleeper_league_id=league, user_id=uid, platform=platform)
    seed(conn, db.league_members_table, f"lm{n}", league_id=league, user_id=uid)
    seed(conn, db.league_members_table, f"lm{n}b", league_id=league, user_id=f"{platform}:{league}.other")
    seed(conn, db.trade_matches_table, f"tm{n}", league_id=league, user_a_id=uid, user_b_id=SLEEPER,
         user_b_decision="like")


@pytest.fixture
def engine(monkeypatch, tmp_path):
    # A file, not :memory:, because the script opens its own engines on this
    # database's URL; ro_engine is the read-only (mode=ro) view, as in prod.
    path = tmp_path / "purge.db"
    engine = create_engine(f"sqlite:///{path}")
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "ro_engine", create_engine(
        f"sqlite:///file:{path}?mode=ro&uri=true", connect_args={"uri": True}))
    with engine.begin() as conn:
        users = db.users_table
        conn.execute(insert(users).values(sleeper_user_id=ESPN, created_at=BEFORE))
        conn.execute(insert(users).values(sleeper_user_id=MFL, created_at=BEFORE))
        conn.execute(insert(users).values(sleeper_user_id=VERIFIED, created_at=BEFORE,
                                          verified_via="mfl_login"))
        conn.execute(insert(users).values(sleeper_user_id=LATE, created_at=AFTER))
        conn.execute(insert(users).values(sleeper_user_id=UNDATED, created_at=None))
        conn.execute(insert(users).values(sleeper_user_id=SLEEPER, created_at=BEFORE,
                                          verified_via="sleeper"))
        conn.execute(insert(users).values(sleeper_user_id=ACCT, created_at=BEFORE,
                                          verified_via="mfl_login"))
        conn.execute(insert(db.accounts_table).values(account_id=ACCT[len("acct_"):],
                                                      created_at=BEFORE))
        _import_rows(conn, ESPN, 1, "espn", "10101")
        # release-lead's case: a verified Fleeced user also belongs to 10101.
        seed(conn, db.league_members_table, "lm-shared", league_id="10101", user_id=SLEEPER)
        seed(conn, db.recorded_picks_table, "rp", league_id="10101", season=2027, round=1, slot=1,
             overall=1, picking_team_id=ESPN, recorded_by=SLEEPER)
        seed(conn, db.espn_credentials_table, "espn", user_id=ESPN, swid=SWID)
        _import_rows(conn, MFL, 2, "mfl", "61408")
        seed(conn, db.mfl_credentials_table, "mfl", user_id=MFL, mfl_username="someone")
        seed(conn, db.draft_picks_table, "pk-own", pick_id="61408_2027_1_0003", league_id="61408",
             platform="mfl", owner_user_id=MFL, original_user_id=MFL)
        seed(conn, db.draft_picks_table, "pk-other", pick_id="61408_2027_1_0004", league_id="61408",
             platform="mfl", owner_user_id="mfl:61408.f0004", original_user_id="mfl:61408.f0004")
        seed(conn, db.member_rankings_table, "orphan", user_id=ORPHAN, league_id="4242")
        for n, uid in enumerate((VERIFIED, LATE, UNDATED, SLEEPER, ACCT), start=10):
            seed(conn, db.member_rankings_table, f"keep{n}", user_id=uid, league_id="keep")
            seed(conn, db.swipe_decisions_table, f"keep{n}", user_id=uid)
    yield engine
    engine.dispose()


def snapshot(engine):
    with engine.connect() as conn:
        return {t.name: sorted(map(repr, conn.execute(select(t)).all()))
                for t in db.metadata.sorted_tables}


def rows_naming(engine, ids):
    """(table.column, value) for every key column holding one of `ids`."""
    hits = []
    with engine.connect() as conn:
        for attr, col in purge.key_columns():
            tbl = getattr(db, attr)
            for v in conn.execute(select(tbl.c[col]).where(tbl.c[col].in_(list(ids)))).scalars():
                hits.append((f"{tbl.name}.{col}", v))
    return hits


def run(capsys, *args):
    code = purge.main(["--cutoff", CUTOFF, "--allow-local", *args])
    return code, capsys.readouterr().out


def test_dry_run_counts_and_changes_nothing(engine, capsys):
    before = snapshot(engine)
    code, out = run(capsys)
    assert code == 0
    assert "targets: 3 (unverified, created before the cutoff: 2; orphans with no users row: 1)" in out
    assert "skipped (verified or after cutoff): 2 (verified: 1; created at or after the cutoff: 1)" in out
    assert "skipped (no usable created_at): 1" in out
    assert "espn_credentials.user_id: 1" in out and "mfl_credentials.user_id: 1" in out
    assert "draft_picks.owner_user_id: 1" in out
    assert "recorded_picks.picking_team_id: 1" in out
    assert ("  python3 scripts/purge_entry_users.py --cutoff 2026-10-26T00:00:00Z "
            "--execute --expect 3") in out
    assert snapshot(engine) == before


def test_execute_refuses_a_stale_expect(engine, capsys):
    before = snapshot(engine)
    code, out = run(capsys, "--execute", "--expect", "4")
    assert code == 2 and "REFUSED" in out
    assert snapshot(engine) == before


def test_execute_removes_targets_everywhere_and_keeps_everyone_else(engine, capsys):
    keep_ids = (VERIFIED, LATE, UNDATED, SLEEPER, ACCT)
    kept_before = sorted(rows_naming(engine, keep_ids))
    code, out = run(capsys, "--execute", "--expect", "3")
    assert code == 0, out
    assert "targets: 3; deleted: 3; failed: 0" in out
    # Every key column, credentials and the MFL grid owner included.
    assert rows_naming(engine, (ESPN, MFL, ORPHAN)) == []
    with engine.connect() as conn:
        assert conn.execute(select(db.espn_credentials_table)).all() == []
        assert conn.execute(select(db.mfl_credentials_table)).all() == []
        picks = {r.pick_id: r for r in conn.execute(select(db.draft_picks_table))}
        matches = conn.execute(select(db.trade_matches_table)).all()
        members = {r.user_id for r in conn.execute(select(db.league_members_table))}
        leagues = {r.sleeper_league_id: r.user_id for r in conn.execute(select(db.leagues_table))}
        recorded = conn.execute(select(db.recorded_picks_table)).one()
    assert (recorded.picking_team_id, recorded.recorded_by) == (accounts.DELETED_USER_PLACEHOLDER, SLEEPER)
    # 10101 is shared with a live member: kept, importer anonymized. 61408 is solo: gone.
    assert leagues == {"10101": accounts.DELETED_USER_PLACEHOLDER}
    assert picks["61408_2027_1_0003"].owner_user_id == accounts.DELETED_USER_PLACEHOLDER
    assert picks["61408_2027_1_0004"].owner_user_id == "mfl:61408.f0004"
    # The shared match is anonymized on the entry side; the counterparty's
    # side, decision included, is intact.
    assert len(matches) == 2
    assert all(m.user_a_id == accounts.DELETED_USER_PLACEHOLDER for m in matches)
    assert all(m.user_b_id == SLEEPER and m.user_b_decision == "like" for m in matches)
    assert {"espn:10101.other", "mfl:61408.other"} <= members
    # Skipped entry users and ordinary users are untouched.
    assert sorted(rows_naming(engine, keep_ids)) == kept_before


def test_verify_fails_before_and_passes_after(engine, capsys):
    code, out = run(capsys, "--verify")
    assert code == 1
    assert "(a) target ids remaining in key columns: 3 -> FAIL" in out
    assert "(b) credential rows on any entry: id: espn_credentials.user_id 1, mfl_credentials.user_id 1 -> FAIL" in out
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    code, out = run(capsys, "--verify")
    assert code == 0, out
    assert "-> OK" in out and "FAIL" not in out


def test_verify_fails_on_a_credential_left_on_a_skipped_entry_user(engine, capsys):
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    with engine.begin() as conn:
        seed(conn, db.espn_credentials_table, "late", user_id=LATE, swid="{LATE}")
    code, out = run(capsys, "--verify")
    assert code == 1
    assert "(a) target ids remaining in key columns: 0 -> OK" in out
    assert "espn_credentials.user_id 1" in out and "-> FAIL" in out
    assert "on a SKIPPED entry user (verified, after the cutoff or no created_at): 1" in out


def test_info_counts_never_fail_verify(engine, capsys):
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    with engine.begin() as conn:
        seed(conn, db.standing_offers_table, "so", user_id=SLEEPER, league_id="61408",
             player_id="p1", round=1, team_user_ids=f'["{LATE}"]')
        seed(conn, db.overhaul_offers_table, "ovh", offer_id="ovh_1", overhaul_id="ovh_x", revision=1,
             package_hash="h", counterparty_user_id=VERIFIED, give_ids_json="[]",
             receive_ids_json="[]", card_json="{}", created_at=BEFORE)
        # Another user's event naming an entry id (pick_assignment_changed.new_owner).
        seed(conn, db.user_events_table, "ev", user_id=SLEEPER, event_type="pick_assignment_changed",
             props=f'{{"actor": "{SLEEPER}", "new_owner": "{LATE}"}}')
    code, out = run(capsys, "--verify")
    assert code == 0, out
    assert "standing_offers.team_user_ids 1" in out
    assert "user_events.props 1" in out
    assert "known general deletion gap, privacy §6 'not yet'): " in out
    assert "overhaul_offers.counterparty_user_id 1" in out


def test_no_id_reaches_stdout_or_the_log(engine, capsys, caplog):
    caplog.set_level("DEBUG")
    outputs = []
    for args in ((), ("--verify",), ("--execute", "--expect", "3"), ("--verify",)):
        outputs.append(run(capsys, *args)[1])
    text = "\n".join(outputs) + "\n" + caplog.text
    for secret in (*ALL_IDS, SWID, "61408", "10101", "4242", "7777", "someone"):
        assert secret not in text, f"output names {secret!r}"


def test_guard_refuses_anything_but_an_entry_id(engine, capsys, monkeypatch):
    for bad in (SLEEPER, ACCT, "", None, "ENTRY:espn:x", " entry:espn:x"):
        with pytest.raises(ValueError):
            purge._guard(bad)
    real = purge.discover

    def poisoned(cutoff):
        found = real(cutoff)
        found["targets"] = found["targets"] | {SLEEPER}
        return found
    monkeypatch.setattr(purge, "discover", poisoned)
    before = snapshot(engine)
    code = purge.main(["--cutoff", CUTOFF, "--allow-local", "--execute", "--expect", "4"])
    assert code == 3 and "ERROR (ValueError)" in capsys.readouterr().err
    assert snapshot(engine) == before        # refused before deleting anyone


IDENTITY = "database: sqlite; host: ***; name: purge.db"


def test_every_mode_prints_the_db_identity_first(engine, capsys):
    for args in ((), ("--execute", "--expect", "3"), ("--verify",)):
        assert run(capsys, *args)[1].splitlines()[0] == IDENTITY


@pytest.mark.parametrize("args", [(), ("--verify",), ("--execute", "--expect", "3")])
def test_a_local_sqlite_database_is_refused_without_allow_local(engine, capsys, args):
    before = snapshot(engine)
    code = purge.main(["--cutoff", CUTOFF, *args])
    out = capsys.readouterr().out
    assert code == 2
    assert out.splitlines()[0] == IDENTITY
    assert "REFUSED. That is a local SQLite database" in out
    assert "targets" not in out              # refused before discovery
    assert snapshot(engine) == before


def test_the_identity_names_the_database_never_its_credentials():
    from sqlalchemy.engine import make_url
    url = make_url("postgresql://fleeced_user:s3cret-pw@dpg-abc123-a.oregon-postgres.render.com"
                   ":5432/ftf_prod")
    assert purge._identity(url) == "database: postgresql; host: dpg-abc123-a; name: ftf_prod"
    assert purge._identity(make_url("postgresql://u:p@10.0.0.7/ftf")) == \
        "database: postgresql; host: ***; name: ftf"


def test_a_db_error_mid_discovery_prints_no_id(engine, capsys, caplog, monkeypatch):
    """The users lookup binds every discovered entry id; the driver fails it."""
    import sqlite3
    dialect = type(engine.dialect)
    real = dialect.do_execute

    def failing(self, cursor, statement, parameters, context=None):
        if "users.sleeper_user_id IN" in statement:
            raise sqlite3.OperationalError("database is locked")
        return real(self, cursor, statement, parameters, context)
    monkeypatch.setattr(dialect, "do_execute", failing)
    caplog.set_level("DEBUG")
    before = snapshot(engine)
    for args in ((), ("--verify",), ("--execute", "--expect", "3")):
        code = purge.main(["--cutoff", CUTOFF, "--allow-local", *args])
        captured = capsys.readouterr()
        assert code == 3
        assert "ERROR (OperationalError)" in captured.err
        for secret in ("entry:", SWID, "61408", "10101", "4242"):
            assert secret not in captured.out + captured.err + caplog.text, secret
    assert snapshot(engine) == before


def test_read_modes_use_the_read_only_engine_and_every_engine_hides_parameters(
        engine, capsys, monkeypatch):
    originals = (db.engine, db.ro_engine)
    rw_url, ro_url = str(db.engine.url), str(db.ro_engine.url)
    seen, real = {}, purge.discover

    def spy(cutoff):
        with db.engine.connect() as conn:
            try:
                conn.exec_driver_sql("SELECT ? FROM no_such_table", (ESPN,))
            except Exception as e:  # noqa: BLE001 - its rendering is the point
                rendered = str(e)
            try:
                conn.exec_driver_sql("DELETE FROM swipe_decisions WHERE 0")
                writable = True
            except Exception:  # noqa: BLE001
                writable = False
        seen[mode] = (str(db.engine.url), str(db.ro_engine.url), writable,
                      db.ro_engine.hide_parameters, rendered)
        return real(cutoff)
    monkeypatch.setattr(purge, "discover", spy)
    for mode, args in (("dry", ()), ("execute", ("--execute", "--expect", "3")),
                       ("verify", ("--verify",))):
        run(capsys, *args)
        assert (db.engine, db.ro_engine) == originals          # restored after the run
    assert seen["dry"][:4] == (ro_url, ro_url, False, True)
    assert seen["verify"][:4] == (ro_url, ro_url, False, True)
    assert seen["execute"][:4] == (rw_url, ro_url, True, True)
    for *_rest, rendered in seen.values():
        assert ESPN not in rendered and "hide_parameters=True" in rendered


def test_postgres_engines_hide_parameters_and_reads_are_read_only(monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy.engine import make_url
    made = []
    monkeypatch.setattr(purge, "create_engine", lambda url, **kw: made.append(kw))
    source = SimpleNamespace(url=make_url("postgresql://u:p@dpg-x-a.example/ftf"))
    purge._hidden_engine(source, read_only=True)
    purge._hidden_engine(source, read_only=False)
    assert [kw["hide_parameters"] for kw in made] == [True, True]
    assert [kw["connect_args"] for kw in made] == [
        {"options": "-c default_transaction_read_only=on"}, {}]


# delete_user_data filters on these columns, but they are not user ids: they
# are reached through an id the purge already discovers (account, device,
# impression, rank set, inventory, and the leagues a deleted user imported or
# belongs to, for the shared-league check).
NOT_USER_KEYS = {
    ("leagues", "sleeper_league_id"), ("league_members", "league_id"),
    ("accounts", "account_id"), ("linked_identities", "account_id"),
    ("sessions", "account_id"), ("entitlements", "account_id"),
    ("subscription_events", "account_id"), ("identity_links", "account_id"),
    ("identity_links", "device_id"), ("deck_outcomes", "impression_id"),
    ("suggestion_trade_links", "matched_impression_id"),
    ("suggestion_trade_links", "ghost_impression_id"),
    ("rank_set_entries", "rank_set_id"), ("rank_set_adoptions", "rank_set_id"),
    ("rank_sets", "id"), ("prepared_trade_manifests_v2", "inventory_id"),
}


def test_discovery_covers_every_user_column_delete_user_data_filters_on(engine):
    """Fails when _delete_user_data gains a user-id column the purge doesn't discover."""
    statements = []
    event.listen(engine, "before_cursor_execute",
                 lambda conn, cur, stmt, params, ctx, many: statements.append(stmt))
    accounts.delete_user_data(ESPN)
    filtered = {(t, c) for s in statements
                for t, c in re.findall(r"\b([a-z_0-9]+)\.([a-z_0-9]+) IN \(", s)}
    assert filtered, "captured no SQL"
    discovered = {(getattr(db, attr).name, col) for attr, col in purge.key_columns()}
    missing = sorted(filtered - discovered - NOT_USER_KEYS)
    assert not missing, f"delete_user_data filters on {missing}; add them to DELETION_ONLY_KEYS"
    # Every table it deletes from or rewrites is one the purge can see into.
    written = {t for s in statements for t in re.findall(r"^(?:DELETE FROM|UPDATE) ([a-z_0-9]+)", s)}
    reachable = {t for t, _ in discovered | NOT_USER_KEYS} | {"prepared_trade_sweeps"}
    assert written <= reachable, sorted(written - reachable)
