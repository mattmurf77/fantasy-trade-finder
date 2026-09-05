"""Synthetic-only regression coverage for the current account-deletion schema."""
import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import Float, Integer, create_engine, event, insert, select

from backend import accounts, database as db

UID = "synthetic-owner"
OTHER = "synthetic-counterparty"
AID = "synthetic-account"
ALIAS = accounts.account_user_id(AID)


@pytest.fixture
def engine(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    with engine.begin() as conn:
        conn.execute(insert(db.accounts_table).values(
            account_id=AID, sleeper_user_id=UID, created_at="2026-09-04"))
        for uid in (UID, ALIAS, OTHER):
            conn.execute(insert(db.users_table).values(sleeper_user_id=uid))
    yield engine
    engine.dispose()


def seed(conn, table, marker, **values):
    """Supply synthetic required fields; scenarios explicitly set join keys."""
    row = {}
    for col in table.columns:
        if col.name in values or col.nullable or col.default is not None or col.server_default is not None:
            continue
        if col.primary_key and isinstance(col.type, Integer):
            continue
        row[col.name] = 1 if isinstance(col.type, (Integer, Float)) else marker
    row.update(values)
    conn.execute(insert(table).values(**row))


def rows(engine, table):
    with engine.connect() as conn:
        return conn.execute(select(table)).mappings().all()


@pytest.mark.parametrize("table_name", accounts._ADDITIONAL_PRIVATE_TABLES)
def test_new_private_rows_and_aliases_removed_counterparty_kept(engine, table_name):
    table = getattr(db, table_name + "_table")
    with engine.begin() as conn:
        for uid in (UID, ALIAS, OTHER):
            seed(conn, table, uid, user_id=uid)
    accounts.delete_user_data(UID)
    assert [r["user_id"] for r in rows(engine, table)] == [OTHER]


def test_encrypted_credentials_billing_and_all_sessions_removed(engine):
    ciphertext = Fernet(Fernet.generate_key()).encrypt(b"synthetic-session-secret").decode()
    with engine.begin() as conn:
        for uid in (UID, ALIAS, OTHER):
            aid = AID if uid != OTHER else "other-account"
            for table, col in ((db.sleeper_credentials_table, "token_encrypted"),
                               (db.espn_credentials_table, "espn_s2_encrypted"),
                               (db.mfl_credentials_table, "cookie_encrypted")):
                seed(conn, table, uid, user_id=uid, **{col: ciphertext})
            seed(conn, db.sessions_table, uid, user_id=uid, account_id=aid)
            seed(conn, db.entitlements_table, uid, user_id=uid, account_id=aid)
            seed(conn, db.subscription_events_table, uid, user_id=uid, account_id=aid,
                 payload=json.dumps({"app_user_id": uid, "secret": "synthetic"}))
        # Stale differently-keyed rows still belong to the same account.
        seed(conn, db.sessions_table, "old-session", user_id="old-key", account_id=AID)
        seed(conn, db.mfl_credentials_table, "old-credential", user_id="old-key")
        seed(conn, db.subscription_events_table, "old-billing", user_id="old-key", account_id=AID)
    accounts.delete_user_data(UID)
    for table in (db.sleeper_credentials_table, db.espn_credentials_table,
                  db.mfl_credentials_table, db.sessions_table, db.entitlements_table,
                  db.subscription_events_table):
        assert [r["user_id"] for r in rows(engine, table)] == [OTHER]
    assert not rows(engine, db.accounts_table)
    assert [r["sleeper_user_id"] for r in rows(engine, db.users_table)] == [OTHER]


def test_shared_device_deletes_anonymous_history_preserves_other_identity(engine):
    with engine.begin() as conn:
        for uid, aid in ((UID, AID), (OTHER, "other-account"), (None, None)):
            seed(conn, db.identity_links_table, "device", device_id="shared-device",
                 sleeper_user_id=uid, account_id=aid)
        for uid in (UID, ALIAS, OTHER, "device:shared-device", "device:unrelated"):
            seed(conn, db.user_events_table, uid, user_id=uid, device_id="shared-device")
            seed(conn, db.experiment_assignments_table, uid, unit_id=uid)
    accounts.delete_user_data(UID)
    assert {r["user_id"] for r in rows(engine, db.user_events_table)} == {OTHER, "device:unrelated"}
    assert {r["unit_id"] for r in rows(engine, db.experiment_assignments_table)} == {OTHER, "device:unrelated"}
    assert [r["sleeper_user_id"] for r in rows(engine, db.identity_links_table)] == [OTHER]


def test_outcomes_follow_impressions_shared_trade_record_retained(engine):
    with engine.begin() as conn:
        for uid in (UID, ALIAS, OTHER):
            seed(conn, db.deck_impressions_table, uid, user_id=uid, impression_id=uid)
            seed(conn, db.deck_outcomes_table, uid, impression_id=uid)
        seed(conn, db.suggestion_trade_links_table, UID,
             matched_impression_id=UID, ghost_impression_id=ALIAS)
    accounts.delete_user_data(UID)
    assert [r["impression_id"] for r in rows(engine, db.deck_outcomes_table)] == [OTHER]
    link = rows(engine, db.suggestion_trade_links_table)[0]
    assert link["matched_impression_id"] is None
    assert link["ghost_impression_id"] is None


def test_late_failure_rolls_back_deleted_credentials_and_sessions(engine):
    with engine.begin() as conn:
        seed(conn, db.sessions_table, UID, user_id=UID, account_id=AID)
        seed(conn, db.espn_credentials_table, UID, user_id=UID)

    def fail_users_delete(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM users"):
            raise RuntimeError("synthetic late database failure")

    event.listen(engine, "before_cursor_execute", fail_users_delete)
    try:
        with pytest.raises(RuntimeError, match="synthetic late"):
            accounts.delete_user_data(UID)
    finally:
        event.remove(engine, "before_cursor_execute", fail_users_delete)
    assert len(rows(engine, db.sessions_table)) == 1
    assert len(rows(engine, db.espn_credentials_table)) == 1
    assert len(rows(engine, db.users_table)) == 3


def test_published_rankings_and_other_adoptions_survive_without_author(engine):
    with engine.begin() as conn:
        for rid, visibility in ((1, "private"), (2, "published")):
            seed(conn, db.rank_sets_table, str(rid), id=rid, owner_user_id=UID,
                 visibility=visibility, title="Identifying title", description="Author bio")
            seed(conn, db.rank_set_entries_table, str(rid), rank_set_id=rid)
        seed(conn, db.rank_set_adoptions_table, OTHER, rank_set_id=2, user_id=OTHER)
    accounts.delete_user_data(UID)
    rank_set = rows(engine, db.rank_sets_table)[0]
    assert rank_set["id"] == 2
    assert rank_set["owner_user_id"] == accounts.DELETED_USER_PLACEHOLDER
    assert rank_set["description"] is None
    assert [r["rank_set_id"] for r in rows(engine, db.rank_set_entries_table)] == [2]
    assert [r["user_id"] for r in rows(engine, db.rank_set_adoptions_table)] == [OTHER]


def test_referral_counterparties_and_public_league_grids_are_preserved(engine):
    with engine.begin() as conn:
        seed(conn, db.referrals_table, "sent", referrer_user_id=UID, referred_user_id=OTHER)
        seed(conn, db.referrals_table, "alias-sent", referrer_user_id=ALIAS, referred_user_id=OTHER)
        seed(conn, db.referrals_table, "received", referrer_user_id=OTHER, referred_user_id=UID)
        seed(conn, db.draft_picks_table, "public", owner_user_id=UID, assigned_by=UID)
        seed(conn, db.shared_packages_table, "share", user_id=UID)
        seed(conn, db.trade_block_table, "block", user_id=UID)
        seed(conn, db.league_roster_history_table, "weak", owner_user_id=UID, team_key_quality="weak")
        seed(conn, db.league_roster_history_table, "strong", owner_user_id=UID, team_key_quality="strong")
    accounts.delete_user_data(UID)
    refs = rows(engine, db.referrals_table)
    assert len(refs) == 3
    assert sum(r["referred_user_id"] == OTHER for r in refs) == 2
    assert sum(r["referrer_user_id"] == OTHER for r in refs) == 1
    assert all(r["referrer_user_id"] not in {UID, ALIAS} for r in refs)
    # Public ownership is intentionally retained; private attribution removed.
    pick = rows(engine, db.draft_picks_table)[0]
    assert pick["owner_user_id"] == UID
    assert pick["assigned_by"] is None
    assert rows(engine, db.shared_packages_table)[0]["user_id"] == accounts.DELETED_USER_PLACEHOLDER
    assert rows(engine, db.trade_block_table)[0]["user_id"] is None
    history = rows(engine, db.league_roster_history_table)
    assert len(history) == 1 and history[0]["owner_user_id"] is None


def test_route_evicts_bound_alias_and_account_sessions(engine, monkeypatch):
    from backend import server
    sessions = {
        "synthetic-delete-token": {"user_id": UID, "account_id": AID, "verified": True},
        "synthetic-alias-token": {"user_id": ALIAS},
        "synthetic-stale-token": {"user_id": "old-key", "account_id": AID},
        "synthetic-other-token": {"user_id": OTHER},
    }
    monkeypatch.setattr(server, "touch_user_activity", lambda *a, **kw: None)
    monkeypatch.setattr(accounts, "has_apple_identity", lambda *a, **kw: False)
    with server._sessions_lock:
        server._sessions.update(sessions)
    try:
        response = server.app.test_client().delete(
            "/api/account", headers={"X-Session-Token": "synthetic-delete-token"})
        assert response.status_code == 200, response.get_json()
        with server._sessions_lock:
            assert set(sessions) & server._sessions.keys() == {"synthetic-other-token"}
    finally:
        with server._sessions_lock:
            for token in sessions:
                server._sessions.pop(token, None)


def test_export_includes_alias_private_rows_and_omits_credentials(engine):
    with engine.begin() as conn:
        for uid in (UID, ALIAS, OTHER):
            seed(conn, db.user_taste_table, uid, user_id=uid)
            seed(conn, db.espn_credentials_table, uid, user_id=uid,
                 espn_s2_encrypted='PRIVATE_ESPN_CIPHERTEXT')
            seed(conn, db.mfl_credentials_table, uid, user_id=uid,
                 cookie_encrypted='PRIVATE_MFL_CIPHERTEXT')
            seed(conn, db.user_events_table, uid, user_id=uid,
                 session_id='LEGACY_BEARER_VALUE')
            seed(conn, db.app_feedback_table, uid, user_id=uid, text='private note ' + uid)
    archive = accounts.export_user_data(UID)
    assert archive['export_version'] == 2
    assert {r['user_id'] for r in archive['tables']['user_taste']} == {UID, ALIAS}
    assert {r['user_id'] for r in archive['tables']['espn_credentials']} == {UID, ALIAS}
    exported = json.dumps(archive)
    assert 'PRIVATE_ESPN_CIPHERTEXT' not in exported
    assert 'PRIVATE_MFL_CIPHERTEXT' not in exported
    assert 'LEGACY_BEARER_VALUE' not in exported
    assert 'private note ' + OTHER not in exported
    accounts.delete_user_data(UID)
    feedback = rows(engine, db.app_feedback_table)
    assert [r['text'] for r in feedback if r['user_id'] == OTHER] == ['private note ' + OTHER]
    assert all(r['text'] == '[Removed following account deletion]' for r in feedback if r['user_id'] is None)
