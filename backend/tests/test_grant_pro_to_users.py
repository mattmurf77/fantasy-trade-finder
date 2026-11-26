"""scripts/grant_pro_to_users.py — perpetual Pro for named people, after launch.

Modelled on test_grant_lifetime_pro_existing_users.py: a temporary SQLite file
with synthetic rows, and the script's HTTP call routed into the real
`POST /api/admin/entitlements/bulk-grant` through Flask's test client. Pinned:
  - the dry run writes nothing; --apply grants perpetual manual_grant pro with
    the --note; a second --apply sends nothing;
  - a person already on perpetual pro is skipped; several identifiers for one
    person (Sleeper id, username, account id, acct_*) are granted once;
  - an identifier that matches no one refuses --apply before any send (exit 2);
  - --users-file ignores blank lines and # comments;
  - --apply refuses without --note or --base-url;
  - no identifier or id reaches stdout without --verbose; the secret never does.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, insert, select

from backend import database as db
from backend import entitlements as entl

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import grant_lifetime_pro_existing_users as base  # noqa: E402
import grant_pro_to_users as script  # noqa: E402

CREATED = "2026-09-01T12:00:00+00:00"
FRIEND = "313560442465169501"             # Sleeper user, username friendly
FRIEND_NAME = "friendly"
LINKED = "313560442465169502"             # Sleeper user linked to account `linkedacct`
LINKED_NAME = "linkeduser"
LINKED_ACCT = "linkedacct"
APPLE_ACCT = "appleonly"                  # Sign in with Apple, no Sleeper
HELD = "313560442465169503"               # already on perpetual pro
OTHER = "313560442465169504"              # present but never named
SECRET = "test-cron-secret-xyz"
NOTE = "make-good for support ticket (test)"


@pytest.fixture
def engine(monkeypatch, tmp_path):
    path = tmp_path / "named.db"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    with engine.begin() as conn:
        u = db.users_table
        for uid, name in ((FRIEND, FRIEND_NAME), (LINKED, LINKED_NAME),
                          (HELD, "helduser"), (OTHER, "otheruser")):
            conn.execute(insert(u).values(sleeper_user_id=uid, username=name,
                                          created_at=CREATED))
        a = db.accounts_table
        conn.execute(insert(a).values(account_id=LINKED_ACCT, sleeper_user_id=LINKED,
                                      created_at=CREATED))
        conn.execute(insert(a).values(account_id=APPLE_ACCT, created_at=CREATED))
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
        resp = client.post(base.ROUTE, json=body, headers={"X-Cron-Secret": secret})
        return resp.status_code, resp.get_json()

    monkeypatch.setattr(base, "_post_bulk", post)
    return calls


def run(capsys, tmp_path, *args, apply=False, note=NOTE, base_url="http://test.invalid"):
    out = tmp_path / "keys.txt"
    if out.exists():
        out.unlink()
    argv = ["--allow-local", "--out", str(out), *args]
    if apply:
        argv.append("--apply")
        if base_url:
            argv += ["--base-url", base_url]
        if note:
            argv += ["--note", note]
    code = script.main(argv)
    keys = set(out.read_text().split()) if out.exists() else None
    return code, capsys.readouterr().out, keys


def rows(engine):
    with engine.connect() as conn:
        return conn.execute(select(db.entitlements_table)).fetchall()


def granted(engine):
    return [r for r in rows(engine) if r.source == "manual_grant"]


def test_dry_run_reports_and_writes_nothing(engine, http, capsys, tmp_path):
    before = len(rows(engine))
    code, out, keys = run(capsys, tmp_path, "--user", FRIEND_NAME, "--user", APPLE_ACCT,
                          "--user", HELD)
    assert code == 0
    assert keys == {FRIEND, f"acct_{APPLE_ACCT}"}
    assert http == [] and len(rows(engine)) == before
    assert out.splitlines()[0].startswith("database: sqlite;")
    assert "people found: 3; not found: 0" in out
    assert "already hold active perpetual pro (skipped): 1" in out
    assert "would grant: 2" in out and "DRY RUN" in out


def test_apply_grants_perpetual_manual_pro_with_the_note(engine, http, capsys, tmp_path):
    code, out, keys = run(capsys, tmp_path, "--user", FRIEND, "--user", APPLE_ACCT,
                          apply=True)
    assert code == 0, out
    assert "SUMMARY: sent 2; confirmed perpetual pro on read-back 2; failures 0" in out
    assert len(http) == 1 and http[0]["perpetual"] is True and http[0]["note"] == NOTE
    new = granted(engine)
    assert len(new) == 2
    for r in new:
        assert (r.entitlement, r.status, r.expires_at) == ("pro", "active", None)
        assert r.granted_by == "operator" and r.note == NOTE
    for uid in (FRIEND, f"acct_{APPLE_ACCT}"):
        view = entl.get_entitlements(uid)
        assert view["pro"] and view["expires_at"] is None
    assert not entl.get_entitlements(OTHER)["pro"]


def test_second_apply_sends_nothing(engine, http, capsys, tmp_path):
    assert run(capsys, tmp_path, "--user", FRIEND, apply=True)[0] == 0
    count = len(rows(engine))
    http.clear()
    code, out, keys = run(capsys, tmp_path, "--user", FRIEND, apply=True)
    assert code == 0
    assert keys == set() and "to grant: 0" in out and "nothing to grant" in out
    assert http == [] and len(rows(engine)) == count


def test_already_perpetual_user_is_skipped(engine, http, capsys, tmp_path):
    code, out, keys = run(capsys, tmp_path, "--user", "helduser", apply=True)
    assert code == 0 and keys == set() and http == []
    assert "already hold active perpetual pro (skipped): 1" in out
    assert not [r for r in granted(engine) if r.user_id == HELD]


def test_identifiers_for_one_person_grant_once(engine, http, capsys, tmp_path):
    code, out, keys = run(capsys, tmp_path, "--user", LINKED, "--user", LINKED_NAME,
                          "--user", LINKED_ACCT, "--user", f"acct_{LINKED_ACCT}",
                          "--user", LINKED, apply=True)
    assert code == 0, out
    assert "identifiers given: 4; people found: 1" in out
    assert keys == {f"acct_{LINKED_ACCT}"}
    assert len(http) == 1 and len(http[0]["users"]) == 1
    new = granted(engine)
    assert len(new) == 1
    assert new[0].user_id == LINKED and new[0].account_id == LINKED_ACCT
    assert "confirmed perpetual pro on read-back 1; failures 0" in out


def test_unresolvable_identifier_refuses_before_any_send(engine, http, capsys, tmp_path):
    before = len(rows(engine))
    code, out, keys = run(capsys, tmp_path, "--user", FRIEND, "--user", "no-such-user",
                          apply=True)
    assert code == 2 and "REFUSED" in out and "1 identifier(s) match no user" in out
    assert "no-such-user" not in out
    assert http == [] and keys is None and len(rows(engine)) == before


def test_dry_run_flags_an_unresolvable_identifier(engine, capsys, tmp_path):
    code, out, _keys = run(capsys, tmp_path, "--user", "no-such-user")
    assert code == 0 and "not found: 1" in out and "--apply will refuse" in out
    assert "no-such-user" not in out


def test_users_file_ignores_blank_lines_and_comments(engine, http, capsys, tmp_path):
    f = tmp_path / "people.txt"
    f.write_text(f"# friends and testers\n\n{FRIEND_NAME}   # the friend\n"
                 f"   \n#{OTHER}\n{APPLE_ACCT}\n")
    code, out, keys = run(capsys, tmp_path, "--users-file", str(f), apply=True)
    assert code == 0, out
    assert "identifiers given: 2; people found: 2; not found: 0" in out
    assert keys == {FRIEND, f"acct_{APPLE_ACCT}"}
    assert not entl.get_entitlements(OTHER)["pro"]


@pytest.mark.parametrize("missing", ["note", "base_url"])
def test_apply_refuses_without_note_or_base_url(engine, http, capsys, tmp_path, missing):
    kwargs = {missing: None}
    code, out, keys = run(capsys, tmp_path, "--user", FRIEND, apply=True, **kwargs)
    assert code == 2 and "REFUSED" in out
    assert ("--note" if missing == "note" else "--base-url") in out
    assert http == [] and keys is None and not granted(engine)


def test_blank_note_is_refused(engine, http, capsys, tmp_path):
    code, out, _keys = run(capsys, tmp_path, "--user", FRIEND, apply=True, note="   ")
    assert code == 2 and "--note" in out and http == []


def test_needs_at_least_one_user(engine, capsys, tmp_path):
    with pytest.raises(SystemExit) as e:
        script.main(["--allow-local"])
    assert e.value.code == 2


def test_nothing_identifying_on_stdout_without_verbose(engine, http, capsys, tmp_path):
    idents = (FRIEND_NAME, LINKED_ACCT, "helduser", "no-such-user")
    args = [a for i in idents for a in ("--user", i)]
    _code, dry, _ = run(capsys, tmp_path, *args)
    _code, applied, _ = run(capsys, tmp_path, *args[:-2], apply=True)
    for out in (dry, applied):
        for s in (*idents, FRIEND, LINKED, HELD, APPLE_ACCT, SECRET):
            assert s not in out
    _code, loud, _ = run(capsys, tmp_path, *args, "--verbose")
    assert FRIEND_NAME in loud and FRIEND in loud and "no-such-user: not found" in loud
    assert SECRET not in loud


def test_secret_comes_from_the_environment_only(engine, monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    code, out, _keys = run(capsys, tmp_path, "--user", FRIEND, apply=True)
    assert code == 2 and "CRON_SECRET" in out


def test_a_refused_batch_exits_nonzero(engine, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("CRON_SECRET", SECRET)
    monkeypatch.setattr(base, "_post_bulk", lambda *a, **k: (401, None))
    code, out, _keys = run(capsys, tmp_path, "--user", FRIEND, apply=True)
    assert code == 1 and "failures 1" in out and not granted(engine)


def test_local_sqlite_is_refused_without_allow_local(engine, capsys):
    code = script.main(["--user", FRIEND])
    assert code == 2 and "REFUSED" in capsys.readouterr().out
