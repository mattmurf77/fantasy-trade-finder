"""scripts/grant_lifetime_pro_existing_users.py — lifetime Pro for existing users.

Operator decision 2026-11-22 (turn-on runbook A6 / B5a). A temporary SQLite
file with synthetic rows; the script's HTTP call is routed into the real
`POST /api/admin/entitlements/bulk-grant` through Flask's test client, so the
rows are written by the route the operator's run uses. Pinned here:
  - one grant per person: a Sleeper user, an Apple-only account (acct_*), and
    a Sleeper user linked to an account (plus its legacy acct_ users row);
    synthetic ids and acct_ keys with no account are skipped;
  - the dry run writes nothing and lists the would-grant keys in --out;
  - --apply grants perpetual manual_grant pro (granted_by operator, the note);
    a second --apply grants nothing; a user already on perpetual pro is skipped;
  - --exclude keeps demo B unentitled; an exclude that resolves to no one is a
    hard error before anything is sent;
  - --created-before skips later accounts; a refused batch exits 1;
  - no id reaches stdout without --verbose; CRON_SECRET only from the env.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, func, insert, select

from backend import database as db
from backend import entitlements as entl

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import grant_lifetime_pro_existing_users as script  # noqa: E402

BEFORE, AFTER = "2026-09-01T12:00:00+00:00", "2026-11-25T09:00:00+00:00"
CUT = "2026-11-23T00:00:00Z"
SLEEPER = "313560442465169401"            # Sleeper-only user
LINKED = "313560442465169402"             # Sleeper user linked to account `linked`
LINKED_ACCT = "linked"
APPLE_ACCT = "appleonly"                  # Sign in with Apple, no Sleeper
APPLE = f"acct_{APPLE_ACCT}"
HELD = "313560442465169403"               # already on perpetual pro
DEMO_B = "313560442465169409"             # App Review demo B, username demob
LATE = "313560442465169404"               # created after CUT
SECRET = "test-cron-secret"
EXPECTED = {SLEEPER, LINKED, APPLE, LATE}


@pytest.fixture
def engine(monkeypatch, tmp_path):
    path = tmp_path / "grant.db"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    with engine.begin() as conn:
        u = db.users_table
        for uid, created in ((SLEEPER, BEFORE), (LINKED, BEFORE), (HELD, BEFORE),
                             (LATE, AFTER), (f"acct_{LINKED_ACCT}", BEFORE),
                             ("demo_user_abc", BEFORE), ("qa_tp_313560442465169401", BEFORE),
                             ("acct_gone", BEFORE)):
            conn.execute(insert(u).values(sleeper_user_id=uid, created_at=created))
        conn.execute(insert(u).values(sleeper_user_id=DEMO_B, username="demob",
                                      created_at=BEFORE))
        a = db.accounts_table
        conn.execute(insert(a).values(account_id=LINKED_ACCT, sleeper_user_id=LINKED,
                                      created_at=BEFORE))
        conn.execute(insert(a).values(account_id=APPLE_ACCT, created_at=BEFORE))
    entl.grant(HELD, "pro", source="founder_iap", product_id="ftf_founder")
    yield engine


@pytest.fixture
def http(monkeypatch, engine):
    """Route the script's POST into the real bulk-grant route."""
    import backend.server as server
    monkeypatch.setattr(server, "_CRON_SECRET", SECRET)
    monkeypatch.setenv("CRON_SECRET", SECRET)
    client = server.app.test_client()
    calls = []

    def post(base_url, secret, body, timeout=120):
        calls.append(body)
        resp = client.post(script.ROUTE, json=body, headers={"X-Cron-Secret": secret})
        return resp.status_code, resp.get_json()

    monkeypatch.setattr(script, "_post_bulk", post)
    return calls


def run(capsys, tmp_path, *args, apply=False):
    out = tmp_path / "keys.txt"
    argv = ["--allow-local", "--out", str(out), "--exclude", "demob", *args]
    if apply:
        argv += ["--apply", "--base-url", "http://test.invalid"]
    code = script.main(argv)
    keys = set(out.read_text().split()) if out.exists() else None
    return code, capsys.readouterr().out, keys


def rows(engine):
    with engine.connect() as conn:
        return conn.execute(select(db.entitlements_table)).fetchall()


def test_dry_run_lists_one_key_per_person_and_writes_nothing(engine, capsys, tmp_path):
    before = len(rows(engine))
    code, out, keys = run(capsys, tmp_path)
    assert code == 0
    assert keys == EXPECTED
    assert len(rows(engine)) == before
    assert "would grant: 4" in out and "DRY RUN" in out
    assert "already hold active perpetual pro: 1" in out
    assert "acct_ keys with no account 1" in out
    for uid in (SLEEPER, LINKED, APPLE, DEMO_B, HELD):
        assert uid not in out


def test_apply_grants_perpetual_pro_once_per_person(engine, http, capsys, tmp_path):
    code, out, keys = run(capsys, tmp_path, apply=True)
    assert code == 0, out
    assert keys == EXPECTED
    assert "confirmed perpetual pro on read-back 4; failures 0" in out
    new = [r for r in rows(engine) if r.source == "manual_grant"]
    assert len(new) == 4                                   # linked person: one row
    for r in new:
        assert (r.entitlement, r.status, r.expires_at) == ("pro", "active", None)
        assert r.granted_by == "operator" and r.note == script.NOTE
    linked = [r for r in new if r.user_id == LINKED]
    assert len(linked) == 1 and linked[0].account_id == LINKED_ACCT
    for uid in (SLEEPER, LINKED, APPLE, f"acct_{LINKED_ACCT}", LATE):
        view = entl.get_entitlements(uid)
        assert view["pro"] and view["expires_at"] is None
    assert not entl.get_entitlements(DEMO_B)["pro"]       # excluded
    assert not [r for r in rows(engine) if r.user_id == HELD and r.source == "manual_grant"]
    for uid in (SLEEPER, LINKED, APPLE):
        assert uid not in out


def test_second_apply_grants_nothing(engine, http, capsys, tmp_path):
    assert run(capsys, tmp_path, apply=True)[0] == 0
    count = len(rows(engine))
    http.clear()
    code, out, keys = run(capsys, tmp_path, apply=True)
    assert code == 0
    assert keys == set() and "to grant: 0" in out and "nothing to grant" in out
    assert http == [] and len(rows(engine)) == count


def test_unresolvable_exclude_is_a_hard_error(engine, http, capsys, tmp_path):
    before = len(rows(engine))
    code, out, keys = run(capsys, tmp_path, "--exclude", "no-such-user", apply=True)
    assert code == 2 and "REFUSED" in out and "1 --exclude identifier(s)" in out
    assert "no-such-user" not in out
    assert http == [] and keys is None and len(rows(engine)) == before


def test_exclude_by_account_id_covers_the_linked_sleeper_id(engine, capsys, tmp_path):
    code, _out, keys = run(capsys, tmp_path, "--exclude", LINKED_ACCT)
    assert code == 0 and keys == EXPECTED - {LINKED}


def test_created_before_skips_later_accounts(engine, capsys, tmp_path):
    code, out, keys = run(capsys, tmp_path, "--created-before", CUT)
    assert code == 0 and keys == EXPECTED - {LATE}
    assert "created on/after --created-before 1" in out


def test_a_refused_batch_exits_nonzero(engine, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("CRON_SECRET", SECRET)
    monkeypatch.setattr(script, "_post_bulk", lambda *a, **k: (401, None))
    code, out, _keys = run(capsys, tmp_path, apply=True)
    assert code == 1 and "failures 4" in out
    assert not [r for r in rows(engine) if r.source == "manual_grant"]


def test_apply_needs_the_secret_in_the_environment(engine, monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    code, out, _keys = run(capsys, tmp_path, apply=True)
    assert code == 2 and "CRON_SECRET" in out


def test_local_sqlite_is_refused_without_allow_local(engine, capsys, tmp_path):
    code = script.main(["--out", str(tmp_path / "k.txt")])
    assert code == 2 and "REFUSED" in capsys.readouterr().out
