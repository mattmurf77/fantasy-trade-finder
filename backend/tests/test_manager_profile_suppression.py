"""Manager-profile suppression after account deletion (Q-040, D-282).

`market.manager_profiles` rebuilds one profile per roster owner from public
league history on every league-mate's sync, so deleting a person's rows is not
enough: the deletion also records a keyed hash of their league identity in
`manager_profile_suppressions`, and the capture writes no row for it.

Pins, offline (test_manager_profiles' fixture league + fake transactions
opener, in-memory SQLite):

  * a league-mate's capture after the deletion writes every other owner's row
    and none for the deleted one; the sweep path (`sync_league_trades`) too
  * the suppression row holds no raw id in any column, is keyed by the server
    secret, and only ids that can be roster owners are suppressed (a minted
    account alias is not)
  * a username-only re-signup (an unverified users row) leaves the suppression;
    the first verification of the new account clears it and the next capture
    writes the row again; a call with no users row clears nothing
  * the suppression is written in the deletion's transaction: a deletion that
    rolls back leaves none
  * the table is never exported and is registered as kept-with-reason
"""

import hashlib

import pytest
from sqlalchemy import create_engine, event, insert, select

import backend.accounts as accounts
import backend.database as db_module
import backend.sleeper_trades_service as svc
from backend.tests import test_manager_profiles as mp_t

LEAGUE, ROSTERS, META, NOW = mp_t.LEAGUE, mp_t.ROSTERS, mp_t.META, mp_t.NOW
U1, U2, U3 = mp_t.U1, mp_t.U2, mp_t.U3      # U1 is the league-mate who syncs
AID = "synthetic-account-u2"                # U2's Apple account
SUPP = db_module.manager_profile_suppressions_table


@pytest.fixture()
def engine(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_SALT_KEY", raising=False)
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db_module.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    with eng.begin() as conn:
        for uid in (U1, U2):
            conn.execute(insert(db_module.users_table).values(
                sleeper_user_id=uid, verified_via="sleeper"))
        conn.execute(insert(db_module.accounts_table).values(
            account_id=AID, sleeper_user_id=U2, created_at="2026-11-01"))
    mp_t._sync(mp_t._Opener(), live_user=U1)    # the league's first sweep
    assert _owners() == [U1, U2, U3]
    yield eng
    eng.dispose()


def _owners():
    return [r["owner_id"] for r in db_module.load_manager_profiles(LEAGUE)]


def _capture(live_user=U1):
    return svc.capture_manager_profiles(LEAGUE, rosters=ROSTERS, league_meta=META,
                                        players_fn=mp_t._players_fn, now=NOW,
                                        live_user=live_user)


def _suppressions(eng):
    with eng.connect() as conn:
        return [dict(r) for r in conn.execute(select(SUPP)).mappings()]


def test_a_league_mates_capture_skips_the_deleted_owner(engine):
    accounts.delete_user_data(U2)
    assert _owners() == [U1, U3]               # the deletion removed U2's row

    assert _capture() == 2                     # U1's daemon rebuilds the league
    assert _owners() == [U1, U3]
    mp_t._sync(mp_t._Opener(), live_user=U1)   # and the sweep path that calls it
    assert _owners() == [U1, U3]


def test_the_suppression_row_holds_no_raw_id(engine):
    accounts.delete_user_data(U2)
    rows = _suppressions(engine)
    assert len(rows) == 1                      # U2 only: the account alias can't own a roster
    assert set(rows[0]) == {"id_hmac", "created_at"}
    alias = accounts.account_user_id(AID)
    for value in rows[0].values():
        for raw in (U2, alias, AID):
            assert raw not in str(value)
    # Keyed: not a bare hash of the id, and it moves with the server secret.
    assert rows[0]["id_hmac"] != hashlib.sha256(U2.encode()).hexdigest()
    assert rows[0]["id_hmac"] == db_module.manager_profile_suppression_hash(U2)


def test_the_hash_is_keyed_by_the_server_secret(monkeypatch):
    monkeypatch.setenv("EXPERIMENT_SALT_KEY", "synthetic-key-a")
    a = db_module.manager_profile_suppression_hash(U2)
    monkeypatch.setenv("EXPERIMENT_SALT_KEY", "synthetic-key-b")
    assert db_module.manager_profile_suppression_hash(U2) != a
    monkeypatch.setenv("EXPERIMENT_SALT_KEY", "synthetic-key-a")
    assert db_module.manager_profile_suppression_hash(U2) == a


def test_only_a_verified_new_account_clears_the_suppression(engine):
    accounts.delete_user_data(U2)

    # Anyone can type a Sleeper username: the unverified users row it makes
    # is not a new account, and a lookup of the id clears nothing.
    db_module.upsert_user(U2, username="u2")
    accounts.get_user_verified_via(U2)
    _capture()
    assert _owners() == [U1, U3]
    assert len(_suppressions(engine)) == 1

    accounts.mark_user_verified(U2, "sleeper")  # the person proves the id: new account
    assert _suppressions(engine) == []
    _capture()
    assert _owners() == [U1, U2, U3]


def test_verifying_with_no_users_row_or_again_clears_nothing(engine):
    accounts.delete_user_data(U2)
    accounts.mark_user_verified(U2, "sleeper")  # no users row: nothing to verify
    assert len(_suppressions(engine)) == 1

    with engine.begin() as conn:               # an already-verified row
        conn.execute(insert(db_module.users_table).values(
            sleeper_user_id=U2, verified_via="apple"))
    accounts.mark_user_verified(U2, "sleeper")
    assert len(_suppressions(engine)) == 1


def test_a_deletion_that_rolls_back_leaves_no_suppression(engine):
    def fail_users_delete(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM users"):
            raise RuntimeError("synthetic late database failure")

    event.listen(engine, "before_cursor_execute", fail_users_delete)
    try:
        with pytest.raises(RuntimeError, match="synthetic late"):
            accounts.delete_user_data(U2)
    finally:
        event.remove(engine, "before_cursor_execute", fail_users_delete)
    assert _suppressions(engine) == []
    assert _owners() == [U1, U2, U3]


def test_the_table_is_never_exported_and_kept_with_a_reason():
    assert "manager_profile_suppressions" in accounts._KEPT_WITH_REASON
    assert all(entry[0] != "manager_profile_suppressions" for entry in accounts._EXPORT_TABLES)
    assert all(entry[1] != "manager_profile_suppressions_table"
               for entry in accounts._EXPORT_TABLES)
