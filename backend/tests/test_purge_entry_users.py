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
import json
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
LATE = "entry:espn:{0BADF00D-1111-2222-3333-444455556666}"   # skipped: a proven sign-in after the cutoff
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
        conn.execute(insert(users).values(sleeper_user_id=LATE, created_at=AFTER,
                                          verified_via="espn_login"))
        conn.execute(insert(users).values(sleeper_user_id=SLEEPER, created_at=BEFORE,
                                          verified_via="sleeper"))
        conn.execute(insert(users).values(sleeper_user_id=ACCT, created_at=BEFORE,
                                          verified_via="mfl_login"))
        conn.execute(insert(db.accounts_table).values(account_id=ACCT[len("acct_"):],
                                                      created_at=BEFORE))
        _import_rows(conn, ESPN, 1, "espn", "10101")
        # A verified Fleeced user also belongs to 10101 (release-lead's case).
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
        for n, uid in enumerate((VERIFIED, LATE, SLEEPER, ACCT), start=10):
            seed(conn, db.member_rankings_table, f"keep{n}", user_id=uid, league_id="keep")
            seed(conn, db.swipe_decisions_table, f"keep{n}", user_id=uid)
    yield engine
    engine.dispose()


def add_undated(engine):
    """An unverified entry user with no usable created_at: the purge skips it,
    and --verify (g) (legal R28.16 part 1) fails on it. Not in the default
    fixture, so the other tests' clean verify stays clean."""
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=UNDATED, created_at=None))
        seed(conn, db.member_rankings_table, "undated", user_id=UNDATED, league_id="keep")
        seed(conn, db.swipe_decisions_table, "undated", user_id=UNDATED)


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
    # The runbook passes --expect-db in every mode (--execute requires it); a
    # test's own --expect-db comes later and wins.
    code = purge.main(["--cutoff", CUTOFF, "--allow-local",
                       "--expect-db", purge._db_name(db.engine.url), *args])
    return code, capsys.readouterr().out


def test_dry_run_counts_and_changes_nothing(engine, capsys):
    add_undated(engine)
    before = snapshot(engine)
    code, out = run(capsys)
    assert code == 0
    assert "targets: 3 (unverified, created before the cutoff: 2; orphans with no users row: 1)" in out
    assert "skipped (verified or after cutoff): 2 (verified: 2; created at or after the cutoff: 0)" in out
    assert "unverified created after cutoff: 0" in out and "STOP" not in out
    assert "skipped (no usable created_at): 1" in out
    assert "espn_credentials.user_id: 1" in out and "mfl_credentials.user_id: 1" in out
    assert "draft_picks.owner_user_id: 1" in out
    assert "recorded_picks.picking_team_id: 1" in out
    assert ("  python3 scripts/purge_entry_users.py --cutoff 2026-10-26T00:00:00Z "
            "--execute --expect 3") in out
    assert snapshot(engine) == before


def test_dry_run_counts_credential_rows_on_skipped_entry_users(engine, capsys):
    """Legal R28.17 A1: the verified users' rows are what the flag deletes;
    rows on other skipped users are never deleted here. Counts only."""
    add_undated(engine)
    with engine.begin() as conn:
        seed(conn, db.mfl_credentials_table, "verified", user_id=VERIFIED, mfl_username="a")
        seed(conn, db.espn_credentials_table, "undated", user_id=UNDATED, swid="{UNDATED}")
    before = snapshot(engine)
    code, out = run(capsys)
    assert code == 0
    assert ("credential rows on verified entry users (--delete-verified-credentials removes them; "
            "legal R28.17 A1): 1 (mfl_credentials.user_id 1)") in out
    assert ("credential rows on other skipped entry users (never deleted here; --verify (b) fails "
            "on any): 1 (espn_credentials.user_id 1)") in out
    assert ("--execute --expect 3 --expect-db purge.db --delete-verified-credentials 1") in out
    for secret in (VERIFIED, UNDATED, "{UNDATED}", "61408", "7777"):
        assert secret not in out, secret
    assert snapshot(engine) == before


def test_execute_deletes_verified_users_credential_rows_only_with_the_flag(engine, capsys):
    """Legal R28.17 A1: only those rows go; the account, its entitlement and
    everything else stay, so one execute + verify passes R28.16's two parts."""
    with engine.begin() as conn:
        seed(conn, db.mfl_credentials_table, "verified", user_id=VERIFIED, mfl_username="a")
        seed(conn, db.entitlements_table, "verified", user_id=VERIFIED)
        seed(conn, db.sessions_table, "verified", token_hash="tok-verified", user_id=VERIFIED)
    kept = sorted(r for r in rows_naming(engine, (VERIFIED,)) if not r[0].endswith("credentials.user_id"))
    assert ("entitlements.user_id", VERIFIED) in kept and ("users.sleeper_user_id", VERIFIED) in kept
    before = snapshot(engine)
    for flag in ((), ("--delete-verified-credentials", "0"), ("--delete-verified-credentials", "2")):
        code, out = run(capsys, "--execute", "--expect", "3", *flag)
        assert code == 2 and "REFUSED. --delete-verified-credentials" in out, flag
        assert snapshot(engine) == before            # refused before anything changed
    code, out = run(capsys, "--execute", "--expect", "3", "--delete-verified-credentials", "1")
    assert code == 0, out
    assert ("verified entry users' credential rows deleted (accounts kept): 1; "
            "mfl_credentials 1") in out
    with engine.connect() as conn:
        assert conn.execute(select(db.mfl_credentials_table)).all() == []
        assert conn.execute(select(db.espn_credentials_table)).all() == []
    assert sorted(rows_naming(engine, (VERIFIED,))) == kept
    code, out = run(capsys, "--verify")
    assert code == 0, out
    assert "(g) entry users without verified_via (legal R28.16 part 1): 0 -> OK" in out


def _creds(engine):
    with engine.connect() as conn:
        return sorted([r.user_id for r in conn.execute(select(db.espn_credentials_table))]
                      + [r.user_id for r in conn.execute(select(db.mfl_credentials_table))])


def test_the_flag_deletes_only_verified_entry_users_rows(engine, capsys):
    """release-lead #452 r5 P2-1: rows on an unverified entry user and on
    non-entry users sit next to the verified one, and stay."""
    add_undated(engine)
    with engine.begin() as conn:
        seed(conn, db.mfl_credentials_table, "verified", user_id=VERIFIED, mfl_username="a")
        seed(conn, db.espn_credentials_table, "undated", user_id=UNDATED, swid="{UNDATED}")
        seed(conn, db.mfl_credentials_table, "sleeper", user_id=SLEEPER, mfl_username="b")
        seed(conn, db.espn_credentials_table, "acct", user_id=ACCT, swid="{ACCT}")
    code, out = run(capsys, "--execute", "--expect", "3", "--delete-verified-credentials", "1")
    assert code == 0, out
    assert _creds(engine) == sorted([UNDATED, SLEEPER, ACCT])


def _seed_verified_credential(engine):
    with engine.begin() as conn:
        seed(conn, db.mfl_credentials_table, "verified", user_id=VERIFIED, mfl_username="a")


def test_a_failed_target_skips_the_credential_step(engine, capsys, monkeypatch):
    """release-lead #452 r5 P1-1 (1): no credential delete after a failed target."""
    _seed_verified_credential(engine)
    real = accounts.delete_user_data
    monkeypatch.setattr(accounts, "delete_user_data",
                        lambda uid, *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
                        if uid == MFL else real(uid, *a, **k))
    code, out = run(capsys, "--execute", "--expect", "3", "--delete-verified-credentials", "1")
    assert code == 1
    assert "targets: 3; deleted: 2; failed: 1" in out
    assert "verified entry users' credential rows: SKIPPED, 1 kept, because a target failed." in out
    assert VERIFIED in _creds(engine)


def test_the_credential_step_rolls_back_unless_exactly_m_rows_go(engine, capsys, monkeypatch):
    """release-lead #452 r5 P1-1 (4) and P2-2: a verified holder's row added
    after the count makes the write match 2, not 1, so nothing is deleted."""
    _seed_verified_credential(engine)
    real = accounts.delete_user_data
    added = []

    def deletion_then_a_new_row(uid, *a, **k):
        counts = real(uid, *a, **k)
        if not added:
            added.append(1)
            with engine.begin() as conn:
                seed(conn, db.espn_credentials_table, "late", user_id=LATE, swid="{LATE}")
        return counts
    monkeypatch.setattr(accounts, "delete_user_data", deletion_then_a_new_row)
    code, out = run(capsys, "--execute", "--expect", "3", "--delete-verified-credentials", "1")
    assert code == 1
    assert "targets: 3; deleted: 3; failed: 0" in out          # the purge's summary first
    assert out.index("purge_entry_users: EXECUTE.") < out.index("ROLLED BACK")
    assert ("verified entry users' credential rows: ROLLED BACK, nothing deleted: 2 matched at "
            "the write, not 1.") in out
    assert _creds(engine) == sorted([VERIFIED, LATE])


def test_a_credential_step_error_prints_its_type_only_and_deletes_nothing(engine, capsys, monkeypatch):
    """release-lead #452 r5 P1-1 (2), (3): the summary is printed first; the
    error shows its type only, never an id; the transaction rolls back."""
    _seed_verified_credential(engine)
    real_delete = purge.delete
    calls = []

    def second_delete_fails(table):
        calls.append(table.name)
        if len(calls) > 1:
            raise RuntimeError(f"boom {VERIFIED}")
        return real_delete(table)
    monkeypatch.setattr(purge, "delete", second_delete_fails)
    code, out = run(capsys, "--execute", "--expect", "3", "--delete-verified-credentials", "1")
    assert code == 1
    assert out.index("purge_entry_users: EXECUTE.") < out.index("FAILED (RuntimeError)")
    assert ("verified entry users' credential rows: FAILED (RuntimeError), rolled back, nothing "
            "deleted.") in out
    assert VERIFIED not in out and "boom" not in out
    assert VERIFIED in _creds(engine)


def test_verify_b_counts_entry_rows_case_sensitively(engine, capsys):
    """SQLite's LIKE ignores case; an "ENTRY:" id is not an entry user."""
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    with engine.begin() as conn:
        seed(conn, db.espn_credentials_table, "upper", user_id="ENTRY:espn:1.t1", swid="{UP}")
    code, out = run(capsys, "--verify")
    assert code == 0, out
    assert ("(b) credential rows on any entry: id: espn_credentials.user_id 0, "
            "mfl_credentials.user_id 0 -> OK") in out


def test_a_blank_verified_via_is_not_a_verification(engine, capsys):
    blank = "entry:mfl:61408.f0011"
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=blank, created_at=BEFORE,
                                                   verified_via=" "))
    code, out = run(capsys)
    assert "targets: 4 (unverified, created before the cutoff: 3;" in out


def test_delete_verified_credentials_only_goes_with_execute(engine, capsys):
    with pytest.raises(SystemExit):
        run(capsys, "--delete-verified-credentials", "1")
    with pytest.raises(SystemExit):
        run(capsys, "--verify", "--delete-verified-credentials", "1")


def test_verify_g_fails_on_an_unverified_entry_user_left(engine, capsys):
    """Legal R28.16 part 1: zero entry users without verified_via. The purge
    skips an undated one, so only (g) catches it."""
    add_undated(engine)
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    code, out = run(capsys, "--verify")
    assert code == 1
    assert "(a) target ids remaining in key columns: 0 -> OK" in out
    assert "(g) entry users without verified_via (legal R28.16 part 1): 1 -> FAIL" in out
    assert out.count("-> FAIL") == 1


def test_execute_refuses_a_stale_expect(engine, capsys):
    before = snapshot(engine)
    code, out = run(capsys, "--execute", "--expect", "4")
    assert code == 2 and "REFUSED" in out
    assert snapshot(engine) == before


def test_execute_removes_targets_everywhere_and_keeps_everyone_else(engine, capsys):
    keep_ids = (VERIFIED, LATE, SLEEPER, ACCT)
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
    # Every league a purged entry user imported is deleted, shared or not
    # (main's behaviour; #452 D1 was reverted): a remaining member re-links it
    # and owns the new row, so linker-gated routes keep working.
    assert leagues == {}
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
    # LATE is verified, so the dry run's command removes it (legal R28.17 A1).
    assert "on a verified entry user: 1. Dry-run again" in out
    code, out = run(capsys)
    assert "--execute --expect 0 --expect-db purge.db --delete-verified-credentials 1" in out
    assert run(capsys, "--execute", "--expect", "0", "--delete-verified-credentials", "1")[0] == 0
    code, out = run(capsys, "--verify")
    assert code == 0, out


def test_an_id_minted_after_the_cutoff_stops_the_dry_run_and_fails_verify(engine, capsys):
    """A live entry session (flag still on, or no restart) mints users after the cutoff."""
    minted = "entry:mfl:61408.f0009"
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=minted, created_at=AFTER))
        seed(conn, db.sessions_table, "minted", token_hash="tok-minted", user_id=minted)
    code, out = run(capsys)
    assert code == 0 and "targets: 3" in out
    assert "unverified created after cutoff: 1" in out
    assert "STOP: unverified entry users were created at or after the cutoff" in out
    assert "--execute --expect" not in out          # no command to copy
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    with engine.begin() as conn:                    # a purged id, re-created
        conn.execute(insert(db.users_table).values(sleeper_user_id=ESPN, created_at=AFTER))
    code, out = run(capsys, "--verify")
    assert code == 1
    assert "(a) target ids remaining in key columns: 0 -> OK" in out
    assert ("(c) unverified entry users created after the cutoff: 2. The flag or restart "
            "wasn't done; investigate before re-running. -> FAIL") in out


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
    add_undated(engine)
    with engine.begin() as conn:
        seed(conn, db.mfl_credentials_table, "verified", user_id=VERIFIED, mfl_username="someone2")
    caplog.set_level("DEBUG")
    outputs = []
    for args in ((), ("--verify",),
                 ("--execute", "--expect", "3", "--delete-verified-credentials", "1"), ("--verify",)):
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
    code, out = run(capsys, "--execute", "--expect", "4")
    assert code == 2 and "REFUSED. A target, or an alias its deletion would also remove" in out
    assert snapshot(engine) == before        # refused before deleting anyone


@pytest.mark.parametrize("alias", ["bound-account", "session-working-key"])
def test_guard_refuses_a_target_whose_deletion_scope_reaches_a_non_entry_id(
        engine, capsys, alias):
    """delete_user_data(id) also deletes the aliases _user_data_scope resolves."""
    with engine.begin() as conn:
        conn.execute(insert(db.accounts_table).values(
            account_id="acct-on-entry", sleeper_user_id=MFL, created_at=BEFORE))
        if alias == "session-working-key":
            seed(conn, db.sessions_table, "wk", token_hash="tok-wk", user_id=SLEEPER,
                 account_id="acct-on-entry")
    before = snapshot(engine)
    code, out = run(capsys, "--execute", "--expect", "3")
    assert code == 2 and "REFUSED. A target, or an alias" in out
    assert snapshot(engine) == before        # refused before deleting anyone


def test_the_scope_is_rechecked_right_before_each_deletion(engine, capsys, monkeypatch):
    real, calls = accounts.delete_user_data, []

    def bind_the_last_target_on_first_call(uid, *a, **kw):
        if not calls:                         # a bind lands mid-run on a later target
            with engine.begin() as conn:
                conn.execute(insert(db.accounts_table).values(
                    account_id="late-bind", sleeper_user_id=MFL, created_at=AFTER))
        calls.append(uid)
        return real(uid, *a, **kw)
    monkeypatch.setattr(accounts, "delete_user_data", bind_the_last_target_on_first_call)
    code, out = run(capsys, "--execute", "--expect", "3")
    assert code == 1 and "targets: 3; deleted: 2; failed: 1" in out
    assert MFL not in calls and rows_naming(engine, (MFL,))   # never deleted


@pytest.mark.parametrize("bad", [
    "2026-10-26", "2026-W43-1", "2026-W43-1T00:00:00Z", "2026-299T00:00:00Z",
    "2026-10-26T00:00:00", "2026-10-26T00:00Z", "2026-10-26 00:00:00Z",
    "2026-10-26T00:00:00+0000", "2026-13-01T00:00:00Z", "2099-01-01T00:00:00Z", "yesterday"])
def test_cutoff_must_be_a_full_past_datetime_with_a_timezone(engine, capsys, bad):
    before = snapshot(engine)
    with pytest.raises(SystemExit) as exit_:
        purge.main(["--cutoff", bad, "--allow-local", "--execute", "--expect", "3"])
    assert exit_.value.code == 2 and "--cutoff" in capsys.readouterr().err
    assert snapshot(engine) == before


def test_cutoff_accepts_z_offsets_and_fractions():
    from datetime import datetime, timezone
    utc = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)
    assert purge._parse_cutoff("2026-10-26T14:00:00Z") == utc
    assert purge._parse_cutoff("2026-10-26T10:00:00-04:00") == utc
    assert purge._parse_cutoff("2026-10-26T14:00:00.000001+00:00") == utc.replace(microsecond=1)


def test_options_are_never_abbreviated(engine, capsys):
    before = snapshot(engine)
    for args in (["--exec", "--expect", "3", "--allow-local"],
                 ["--execute", "--exp", "3", "--allow-local"],
                 ["--execute", "--expect", "3", "--allow"]):
        with pytest.raises(SystemExit) as exit_:
            purge.main(["--cutoff", CUTOFF, *args])
        assert exit_.value.code == 2
    assert snapshot(engine) == before


def test_created_at_equal_to_the_cutoff_is_after_and_a_microsecond_before_is_a_target(engine):
    at, just_before = "entry:mfl:9.f0001", "entry:mfl:9.f0002"
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=at,
                                                   created_at="2026-10-26T00:00:00+00:00"))
        conn.execute(insert(db.users_table).values(sleeper_user_id=just_before,
                                                   created_at="2026-10-25T23:59:59.999999+00:00"))
        for uid in (at, just_before):
            seed(conn, db.member_rankings_table, uid, user_id=uid, league_id="9")
    found = purge.discover(purge._parse_cutoff(CUTOFF))
    assert at in found["skipped_after_cutoff"] and at not in found["targets"]
    assert just_before in found["targets"]


def test_the_printed_execute_command_keeps_the_cutoff_microseconds_in_utc(engine, capsys):
    code = purge.main(["--cutoff", "2026-10-25T20:00:00.000001-04:00", "--allow-local"])
    out = capsys.readouterr().out
    assert code == 0
    assert ("  python3 scripts/purge_entry_users.py --cutoff 2026-10-26T00:00:00.000001Z "
            "--execute --expect 3") in out


IDENTITY = "database: sqlite; host: ***; name: purge.db"


def test_every_mode_prints_the_db_identity_first(engine, capsys):
    for args in ((), ("--execute", "--expect", "3"), ("--verify",)):
        assert run(capsys, *args)[1].splitlines()[0] == IDENTITY


@pytest.mark.parametrize("args", [(), ("--verify",), ("--execute", "--expect", "3")])
def test_a_local_sqlite_database_is_refused_without_allow_local(engine, capsys, args):
    before = snapshot(engine)
    if "--execute" in args:
        args = (*args, "--expect-db", purge._db_name(engine.url))
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
    for args in ((), ("--verify",), ("--execute", "--expect", "3",
                                     "--expect-db", purge._db_name(engine.url))):
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
# impression, rank set, inventory).
NOT_USER_KEYS = {
    ("accounts", "account_id"), ("linked_identities", "account_id"),
    ("sessions", "account_id"), ("entitlements", "account_id"),
    ("subscription_events", "account_id"), ("identity_links", "account_id"),
    ("identity_links", "device_id"), ("deck_outcomes", "impression_id"),
    ("suggestion_trade_links", "matched_impression_id"),
    ("suggestion_trade_links", "ghost_impression_id"),
    ("rank_set_entries", "rank_set_id"), ("rank_set_adoptions", "rank_set_id"),
    ("rank_sets", "id"), ("prepared_trade_manifests_v2", "inventory_id"),
    # = comparisons against fixed enum values, not ids.
    ("rank_sets", "visibility"), ("league_roster_history", "team_key_quality"),
    ("prepared_trade_participants", "subject_kind"),
    # the pick audit-trail scrub selects its events by type (#452 QA round 2);
    # the ids it rewrites live in props, which (d) checks.
    ("user_events", "event_type"),
}


def test_discovery_covers_every_user_column_delete_user_data_filters_on(engine):
    """Fails when _delete_user_data gains a user-id column the purge doesn't discover."""
    statements = []
    event.listen(engine, "before_cursor_execute",
                 lambda conn, cur, stmt, params, ctx, many: statements.append(stmt))
    accounts.delete_user_data(ESPN)
    # IN lists and = comparisons (e.g. accounts.sleeper_user_id = ?): both
    # can filter on a user id.
    filtered = {(t, c) for s in statements
                for t, c in re.findall(r"\b([a-z_0-9]+)\.([a-z_0-9]+) (?:IN \(|= )", s)}
    assert filtered, "captured no SQL"
    discovered = {(getattr(db, attr).name, col) for attr, col in purge.key_columns()}
    missing = sorted(filtered - discovered - NOT_USER_KEYS)
    assert not missing, f"delete_user_data filters on {missing}; add them to DELETION_ONLY_KEYS"
    # Every table it deletes from or rewrites is one the purge can see into.
    written = {t for s in statements for t in re.findall(r"^(?:DELETE FROM|UPDATE) ([a-z_0-9]+)", s)}
    reachable = {t for t, _ in discovered | NOT_USER_KEYS} | {"prepared_trade_sweeps"}
    assert written <= reachable, sorted(written - reachable)


# ── #452 QA round 2 ────────────────────────────────────────────────────────

def _assignment_event(conn, marker, new_owner):
    seed(conn, db.user_events_table, marker, user_id=SLEEPER, event_type="pick_assignment_changed",
         props=f'{{"pick_id": "{marker}", "actor": "{SLEEPER}", "new_owner": "{new_owner}"}}')


def test_execute_anonymizes_targets_in_the_pick_audit_trail_and_verify_d_passes(engine, capsys):
    with engine.begin() as conn:
        _assignment_event(conn, "to-espn", ESPN)        # a target, named in another user's event
        _assignment_event(conn, "to-kept", VERIFIED)    # a skipped (kept) entry user may remain
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    with engine.connect() as conn:
        text = " ".join(conn.execute(select(db.user_events_table.c.props).where(
            db.user_events_table.c.event_type == "pick_assignment_changed")).scalars())
    assert ESPN not in text and accounts.DELETED_USER_PLACEHOLDER in text and VERIFIED in text
    code, out = run(capsys, "--verify")
    assert code == 0, out
    assert "(d) pick_assignment_changed events naming a removed entry id: 0 -> OK" in out


def test_verify_d_fails_on_a_removed_entry_id_left_in_the_pick_audit_trail(engine, capsys):
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    with engine.begin() as conn:
        _assignment_event(conn, "stale", ESPN)          # written after the deletion, e.g. a replay
    code, out = run(capsys, "--verify")
    assert code == 1
    assert "(d) pick_assignment_changed events naming a removed entry id: 1 -> FAIL" in out
    assert ESPN not in out and SWID not in out


def test_verify_e_fails_on_an_empty_or_wrong_database(engine, capsys, monkeypatch):
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    monkeypatch.setattr(purge, "_users_count", lambda found: 0)
    code, out = run(capsys, "--verify")
    assert code == 1 and "(e) users rows in this database: 0 -> FAIL (empty or wrong database)" in out
    monkeypatch.setattr(purge, "_users_count", lambda found: None)
    code, out = run(capsys, "--verify")
    assert code == 1 and "(e) users rows in this database: table missing -> FAIL" in out


def test_expect_db_refuses_a_different_database_in_every_mode(engine, capsys):
    name = purge._db_name(db.engine.url)
    for args in ((), ("--verify",), ("--execute", "--expect", "3")):
        before = snapshot(engine)
        code, out = run(capsys, "--expect-db", "fleeced-prod", *args)
        assert code == 2 and "REFUSED. The database name doesn't match --expect-db" in out
        assert snapshot(engine) == before
    assert run(capsys, "--expect-db", name)[0] == 0


def test_a_failing_target_prints_only_the_error_type(engine, capsys, monkeypatch):
    def boom(uid, *a, **k):
        raise RuntimeError(f"cannot delete {uid} ({SWID})")
    monkeypatch.setattr(accounts, "delete_user_data", boom)
    code, out = run(capsys, "--execute", "--expect", "3")
    err = capsys.readouterr().err
    assert code == 1
    assert out.count("a target failed (RuntimeError); continuing") == 3
    for secret in (ESPN, MFL, ORPHAN, SWID, "cannot delete"):
        assert secret not in out + err


# ── #452 QA round 3 ────────────────────────────────────────────────────────

def test_execute_anonymizes_a_target_in_another_importers_assignment_order(engine, capsys):
    with engine.begin() as conn:
        seed(conn, db.leagues_table, "own", sleeper_league_id="20202", user_id=SLEEPER,
             pick_assignment_settings=f'{{"order": ["{SLEEPER}", "{ESPN}", "{VERIFIED}"]}}')
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    with engine.connect() as conn:
        raw = conn.execute(select(db.leagues_table.c.pick_assignment_settings).where(
            db.leagues_table.c.sleeper_league_id == "20202")).scalar()
    assert json.loads(raw)["order"] == [SLEEPER, accounts.DELETED_USER_PLACEHOLDER, VERIFIED]
    code, out = run(capsys, "--verify")
    assert code == 0, out
    assert "(f) league pick-assignment orders naming a removed entry id: 0 -> OK" in out


def test_verify_f_fails_on_a_removed_entry_id_left_in_an_assignment_order(engine, capsys):
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    with engine.begin() as conn:
        seed(conn, db.leagues_table, "stale", sleeper_league_id="30303", user_id=SLEEPER,
             pick_assignment_settings=f'{{"order": ["{SLEEPER}", "{MFL}"]}}')
    code, out = run(capsys, "--verify")
    assert code == 1
    assert "(f) league pick-assignment orders naming a removed entry id: 1 -> FAIL" in out
    assert MFL not in out


@pytest.mark.parametrize("field", ["old_owner", "actor"])
def test_verify_d_reads_every_audit_field(engine, capsys, field):
    assert run(capsys, "--execute", "--expect", "3")[0] == 0
    with engine.begin() as conn:
        seed(conn, db.user_events_table, f"ev-{field}", user_id=SLEEPER,
             event_type="pick_assignment_changed",
             props=json.dumps({"pick_id": "x", "new_owner": SLEEPER, field: ESPN}))
    code, out = run(capsys, "--verify")
    assert code == 1 and "(d) pick_assignment_changed events naming a removed entry id: 1 -> FAIL" in out


def test_the_printed_execute_command_carries_expect_db(engine, capsys):
    code, out = run(capsys)
    assert code == 0
    assert f"--execute --expect 3 --expect-db {purge._db_name(db.engine.url)}" in out


def test_execute_requires_expect_db(engine, capsys):
    before = snapshot(engine)
    with pytest.raises(SystemExit) as exc:
        purge.main(["--cutoff", CUTOFF, "--allow-local", "--execute", "--expect", "3"])
    assert exc.value.code == 2
    assert "--execute needs --expect-db" in capsys.readouterr().err
    assert snapshot(engine) == before
