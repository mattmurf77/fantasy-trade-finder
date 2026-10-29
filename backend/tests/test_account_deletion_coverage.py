"""Synthetic-only regression coverage for the current account-deletion schema."""
import inspect
import io
import json
import re
import tokenize

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import Float, Integer, LargeBinary, create_engine, event, insert, select

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
        row[col.name] = (1 if isinstance(col.type, (Integer, Float))
                         else marker.encode() if isinstance(col.type, LargeBinary) else marker)
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


def test_proposals_preserve_other_owners_history_without_deleted_board(engine):
    """Counterparty sends survive; identity and private valuation do not."""
    with engine.begin() as conn:
        for target in (UID, ALIAS, "unrelated-counterparty"):
            seed(conn, db.trade_proposals_table, target, user_id=OTHER,
                 target_user_id=target, give_asset_ids='["player-a"]',
                 receive_asset_ids='["player-b"]', provider="sleeper",
                 valuation_json=json.dumps({"private_board": target}))
    accounts.delete_user_data(UID)
    proposals = rows(engine, db.trade_proposals_table)
    assert len(proposals) == 3
    for proposal in proposals:
        assert proposal["user_id"] == OTHER
        assert proposal["give_asset_ids"] == '["player-a"]'
        assert proposal["receive_asset_ids"] == '["player-b"]'
        assert proposal["provider"] == "sleeper"
        if proposal["proposal_event_id"] in {UID, ALIAS}:
            assert proposal["target_user_id"] is None
            assert proposal["valuation_json"] is None
        else:
            assert proposal["target_user_id"] == "unrelated-counterparty"
            assert json.loads(proposal["valuation_json"]) == {
                "private_board": "unrelated-counterparty"}


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
    monkeypatch.setattr(accounts, "apple_identity_subjects", lambda *a, **kw: set())
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
            seed(conn, db.trade_proposals_table, uid, user_id=uid,
                 valuation_json=json.dumps({"private_board": uid}))
            seed(conn, db.trade_policy_shadow_table, uid, user_id=uid)
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
    for table_name in ("trade_proposals", "trade_policy_shadow"):
        assert {r['user_id'] for r in archive['tables'][table_name]} == {UID, ALIAS}
    assert {json.loads(r['valuation_json'])['private_board']
            for r in archive['tables']['trade_proposals']} == {UID, ALIAS}
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


@pytest.mark.parametrize("name", ["win_now_jobs", "win_now_scenarios", "win_now_decisions"])
def test_win_now_private_data_exports_and_deletes_all_account_aliases(engine, name):
    table = getattr(db, name + "_table")
    with engine.begin() as conn:
        for uid in (UID, ALIAS, OTHER):
            seed(conn, table, uid, user_id=uid)
    archive = accounts.export_user_data(UID)
    assert {row["user_id"] for row in archive["tables"][name]} == {UID, ALIAS}
    counts = accounts.delete_user_data(UID)
    assert counts[name + "_deleted"] == 2
    assert [row["user_id"] for row in rows(engine, table)] == [OTHER]


def _pick(conn, pick_id, platform, owner, original, assigned_by=None):
    seed(conn, db.draft_picks_table, pick_id, pick_id=pick_id, league_id=f"{platform}-league",
         platform=platform, owner_user_id=owner, original_user_id=original,
         owner_username="Team " + pick_id, original_username="Team " + pick_id,
         assigned_by=assigned_by)


def _picks(engine):
    return {r["pick_id"]: r for r in rows(engine, db.draft_picks_table)}


def test_platform_pick_grid_owner_ids_anonymized_sleeper_grid_untouched(engine):
    """MFL/ESPN grids hold the importer's Fleeced id; Sleeper grids keep public ids."""
    gone = accounts.DELETED_USER_PLACEHOLDER
    with engine.begin() as conn:
        _pick(conn, "mfl-own", "mfl", UID, UID)            # the importer's own pick
        _pick(conn, "mfl-alias", "mfl", ALIAS, ALIAS)      # the bound acct_ alias
        _pick(conn, "mfl-traded-in", "mfl", UID, OTHER)    # OTHER's pick, now UID's
        _pick(conn, "mfl-traded-out", "mfl", OTHER, UID)   # UID's pick, now OTHER's
        _pick(conn, "mfl-other", "mfl", OTHER, OTHER)      # another owner on the same grid
        _pick(conn, "espn-own", "espn", UID, UID)
        _pick(conn, "sleeper-own", "sleeper", UID, UID)    # public Sleeper ids: kept
        _pick(conn, "legacy-own", None, UID, UID)          # pre-#158 row, no platform: kept
    counts = accounts.delete_user_data(UID)
    picks = _picks(engine)
    owners = lambda pid: (picks[pid]["owner_user_id"], picks[pid]["original_user_id"])  # noqa: E731
    assert owners("mfl-own") == (gone, gone)
    assert owners("mfl-alias") == (gone, gone)
    assert owners("mfl-traded-in") == (gone, OTHER)
    assert owners("mfl-traded-out") == (OTHER, gone)
    assert owners("mfl-other") == (OTHER, OTHER)
    assert owners("espn-own") == (gone, gone)
    assert owners("sleeper-own") == (UID, UID)
    assert owners("legacy-own") == (UID, UID)
    # Rows are kept (other members rely on the grid); only the ids change.
    assert len(picks) == 8
    assert counts["draft_picks_owner_anonymized"] == 5


@pytest.mark.parametrize("deleted", ["acct_mfl-signin", "entry:mfl:61408.f0003"])
def test_platform_only_users_pick_rows_anonymized_on_the_mfl_grid(engine, deleted):
    """A proof-based MFL sign-in (acct_*) and an old entry user own picks by Fleeced id."""
    gone = accounts.DELETED_USER_PLACEHOLDER
    with engine.begin() as conn:
        if deleted.startswith(accounts.ACCOUNT_USER_PREFIX):
            conn.execute(insert(db.accounts_table).values(
                account_id=deleted[len(accounts.ACCOUNT_USER_PREFIX):], created_at="2026-10-27"))
        conn.execute(insert(db.users_table).values(sleeper_user_id=deleted))
        _pick(conn, "mine", "mfl", deleted, deleted)
        _pick(conn, "theirs", "mfl", OTHER, OTHER)
        _pick(conn, "placeholder", "mfl", "mfl:61408.f0004", "mfl:61408.f0004")
        _pick(conn, "sleeper", "sleeper", OTHER, OTHER)
    counts = accounts.delete_user_data(deleted)
    picks = _picks(engine)
    assert (picks["mine"]["owner_user_id"], picks["mine"]["original_user_id"]) == (gone, gone)
    assert (picks["theirs"]["owner_user_id"], picks["theirs"]["original_user_id"]) == (OTHER, OTHER)
    assert picks["placeholder"]["owner_user_id"] == "mfl:61408.f0004"
    assert picks["sleeper"]["owner_user_id"] == OTHER
    assert counts["draft_picks_owner_anonymized"] == 1


def test_platform_pick_grid_names_follow_the_anonymized_ids(engine):
    """A kept platform row named the person too: each scrubbed side becomes "Team <slot>"."""
    gone = accounts.DELETED_USER_PLACEHOLDER
    with engine.begin() as conn:
        def pick(pick_id, league, owner, original, slot, platform="mfl"):
            seed(conn, db.draft_picks_table, pick_id, pick_id=pick_id, league_id=league,
                 platform=platform, owner_user_id=owner, owner_username="Name of " + owner,
                 original_user_id=original, original_username="Name of " + original,
                 original_roster_id=slot)
        pick("own", "L1", UID, UID, "0003")             # UID's own pick; UID's slot is 0003
        pick("in", "L1", UID, OTHER, "0005")            # OTHER's pick, now UID's
        pick("out", "L1", OTHER, UID, "0003")           # UID's pick, now OTHER's
        pick("alias-in", "L1", ALIAS, OTHER, "0006")    # the bound alias is the same person
        pick("orphan-in", "L2", UID, OTHER, "0001")     # no own pick in L2: slot unknown
        pick("alias-own", "L3", ALIAS, ALIAS, "0009")   # the slot comes from the alias's pick
        pick("in-L3", "L3", UID, OTHER, "0002")
        pick("two-a", "L4", UID, UID, "0001")           # two slots in one league:
        pick("two-b", "L4", ALIAS, ALIAS, "0002")       # a traded-in pick can't tell which,
        pick("in-L4", "L4", UID, OTHER, "0003")         # but an own pick still can
        pick("espn-own", "E1", UID, UID, "2", platform="espn")
        pick("sleeper", "S1", UID, UID, "4", platform="sleeper")
    accounts.delete_user_data(UID)
    picks = _picks(engine)
    names = lambda pid: (picks[pid]["owner_username"], picks[pid]["original_username"])  # noqa: E731
    assert names("own") == ("Team 0003", "Team 0003")
    assert names("in") == ("Team 0003", "Name of " + OTHER)
    assert names("out") == ("Name of " + OTHER, "Team 0003")
    assert names("alias-in") == ("Team 0003", "Name of " + OTHER)
    assert names("orphan-in") == (gone, "Name of " + OTHER)
    assert names("in-L3") == ("Team 0009", "Name of " + OTHER)
    assert names("two-a") == ("Team 0001", "Team 0001")
    assert names("two-b") == ("Team 0002", "Team 0002")
    assert names("in-L4") == (gone, "Name of " + OTHER)
    assert names("espn-own") == ("Team 2", "Team 2")
    assert names("sleeper") == ("Name of " + UID, "Name of " + UID)    # public Sleeper data
    for pid, r in picks.items():
        if pid != "sleeper":
            text = json.dumps(r, default=str)
            assert UID not in text and ALIAS not in text, pid


def test_export_of_draft_picks_is_unchanged_by_the_pick_grid_anonymization(engine):
    """Export still keys draft_picks on assigned_by only, never on grid ownership."""
    with engine.begin() as conn:
        _pick(conn, "owned", "mfl", UID, UID)                       # owned, not assigned
        _pick(conn, "assigned", "espn", OTHER, OTHER, assigned_by=UID)
        _pick(conn, "alias-assigned", "mfl", OTHER, OTHER, assigned_by=ALIAS)
    archive = accounts.export_user_data(UID)
    assert {r["pick_id"] for r in archive["tables"]["draft_picks"]} == {"assigned", "alias-assigned"}


# #452 D2: recorded_picks has no platform column, so picking_team_id is
# anonymized only where it is a Fleeced-minted id (entry:*, acct_*).
def _recorded(conn, overall, picking_team_id):
    seed(conn, db.recorded_picks_table, f"rp{overall}", league_id="espn-league", season=2027,
         round=1, slot=overall, overall=overall, picking_team_id=picking_team_id,
         player_id=f"p{overall}", recorded_by=OTHER, recorded_at="2026-10-26T00:00:00Z")


def _recorded_teams(engine):
    return {r["overall"]: r["picking_team_id"] for r in rows(engine, db.recorded_picks_table)}


@pytest.mark.parametrize("deleted", [
    "entry:espn:{5EED0000-AAAA-BBBB-CCCC-DDDDEEEEFFFF}", "entry:mfl:61408.f0003", "acct_espn-signin"])
def test_recorded_pick_team_ids_anonymized_where_fleeced_minted(engine, deleted):
    with engine.begin() as conn:
        if deleted.startswith(accounts.ACCOUNT_USER_PREFIX):
            conn.execute(insert(db.accounts_table).values(
                account_id=deleted[len(accounts.ACCOUNT_USER_PREFIX):], created_at="2026-10-26"))
        conn.execute(insert(db.users_table).values(sleeper_user_id=deleted))
        _recorded(conn, 1, deleted)
        _recorded(conn, 2, OTHER)
        _recorded(conn, 3, "espn:{SOMEONE-ELSE}")
        _recorded(conn, 4, None)
    counts = accounts.delete_user_data(deleted)
    assert _recorded_teams(engine) == {
        1: accounts.DELETED_USER_PLACEHOLDER, 2: OTHER, 3: "espn:{SOMEONE-ELSE}", 4: None}
    assert counts["recorded_picks_picking_team_id_anonymized"] == 1


def test_recorded_pick_sleeper_team_ids_stay_and_the_bound_alias_goes(engine):
    with engine.begin() as conn:
        _recorded(conn, 1, UID)       # a public Sleeper id: kept, as on Sleeper grids
        _recorded(conn, 2, ALIAS)     # the bound acct_ alias: Fleeced-minted
        _recorded(conn, 3, OTHER)
    counts = accounts.delete_user_data(UID)
    assert _recorded_teams(engine) == {1: UID, 2: accounts.DELETED_USER_PLACEHOLDER, 3: OTHER}
    assert counts["recorded_picks_picking_team_id_anonymized"] == 1


# #452 QA P2: OTHER users' pick_assignment_changed events (the pick grid's audit
# trail) name owners and actors. A deleted Fleeced-minted id there becomes the
# placeholder; public Sleeper ids stay, as on Sleeper grids.
def _assignment_event(conn, marker, actor, old_owner, new_owner):
    seed(conn, db.user_events_table, marker, user_id=actor, event_type="pick_assignment_changed",
         league_id="espn-league", props=json.dumps({
             "pick_id": marker, "actor": actor, "old_owner": old_owner, "new_owner": new_owner}))


def _assignment_props(engine):
    return {json.loads(r["props"])["pick_id"]: json.loads(r["props"])
            for r in rows(engine, db.user_events_table) if r["event_type"] == "pick_assignment_changed"}


@pytest.mark.parametrize("deleted", ["entry:espn:{5EED0000-AAAA-BBBB-CCCC-DDDDEEEEFFFF}",
                                     "entry:mfl:61408.f0003", "acct_espn-signin"])
def test_pick_assignment_events_anonymize_a_deleted_fleeced_minted_id(engine, deleted):
    with engine.begin() as conn:
        if deleted.startswith(accounts.ACCOUNT_USER_PREFIX):
            conn.execute(insert(db.accounts_table).values(
                account_id=deleted[len(accounts.ACCOUNT_USER_PREFIX):], created_at="2026-10-26"))
        conn.execute(insert(db.users_table).values(sleeper_user_id=deleted))
        _assignment_event(conn, "new", OTHER, OTHER, deleted)        # OTHER gave the pick to them
        _assignment_event(conn, "old", OTHER, deleted, OTHER)        # and took it back
        _assignment_event(conn, "none", OTHER, OTHER, "synthetic-third")
    counts = accounts.delete_user_data(deleted)
    props = _assignment_props(engine)
    placeholder = accounts.DELETED_USER_PLACEHOLDER
    assert (props["new"]["new_owner"], props["new"]["actor"]) == (placeholder, OTHER)
    assert (props["old"]["old_owner"], props["old"]["new_owner"]) == (placeholder, OTHER)
    assert props["none"] == {"pick_id": "none", "actor": OTHER, "old_owner": OTHER,
                             "new_owner": "synthetic-third"}
    assert counts["pick_assignment_events_anonymized"] == 2
    assert deleted not in json.dumps(list(props.values()))


def test_pick_assignment_events_keep_a_public_sleeper_id(engine):
    with engine.begin() as conn:
        _assignment_event(conn, "sleeper", OTHER, OTHER, UID)    # UID is a public Sleeper-style id
        _assignment_event(conn, "alias", OTHER, OTHER, ALIAS)    # the bound acct_ alias is minted
    counts = accounts.delete_user_data(UID)
    props = _assignment_props(engine)
    assert props["sleeper"]["new_owner"] == UID
    assert props["alias"]["new_owner"] == accounts.DELETED_USER_PLACEHOLDER
    assert counts["pick_assignment_events_anonymized"] == 1


def test_pick_assignment_scrub_rewrites_an_actor_and_skips_other_event_types(engine):
    deleted = "entry:mfl:61408.f0003"
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=deleted))
        # OTHER's event in which the deleted user is the recorded actor
        seed(conn, db.user_events_table, "actor", user_id=OTHER, event_type="pick_assignment_changed",
             props=json.dumps({"pick_id": "actor", "actor": deleted, "new_owner": OTHER}))
        # another event type that happens to name them: not the audit trail, untouched
        seed(conn, db.user_events_table, "other", user_id=OTHER, event_type="trade_proposed",
             props=json.dumps({"new_owner": deleted}))
        # a malformed audit row must not abort the deletion
        seed(conn, db.user_events_table, "bad", user_id=OTHER, event_type="pick_assignment_changed",
             props=json.dumps([deleted]))
    counts = accounts.delete_user_data(deleted)
    by_type = {}
    for r in rows(engine, db.user_events_table):
        by_type.setdefault(r["event_type"], []).append(json.loads(r["props"]))
    assert {"pick_id": "actor", "actor": accounts.DELETED_USER_PLACEHOLDER,
            "new_owner": OTHER} in by_type["pick_assignment_changed"]
    assert [deleted] in by_type["pick_assignment_changed"]          # malformed: left alone
    assert by_type["trade_proposed"] == [{"new_owner": deleted}]
    assert counts["pick_assignment_events_anonymized"] == 1


# #452 QA round 3: leagues.pick_assignment_settings.order lists every member,
# including on a row ANOTHER user imported. A deleted Fleeced-minted id there
# becomes the placeholder in place; public Sleeper ids stay.
def _assignment_league(conn, league_id, importer, settings):
    seed(conn, db.leagues_table, league_id, sleeper_league_id=league_id, user_id=importer,
         pick_assignment_settings=json.dumps(settings) if not isinstance(settings, str) else settings)


def _orders(engine):
    return {r["sleeper_league_id"]: r["pick_assignment_settings"] for r in rows(engine, db.leagues_table)}


def test_pick_assignment_order_on_another_importers_row_is_anonymized_in_place(engine):
    deleted = "entry:espn:{5EED0000-AAAA-BBBB-CCCC-DDDDEEEEFFFF}"
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=deleted))
        _assignment_league(conn, "shared", OTHER, {"rounds": 4, "order": [OTHER, deleted, "third"]})
        _assignment_league(conn, "sleeper", OTHER, {"order": [OTHER, UID]})
        _assignment_league(conn, "list", OTHER, f'["{deleted}"]')            # not a dict
        _assignment_league(conn, "noorder", OTHER, {"order": f"{deleted}"})  # order not a list
    counts = accounts.delete_user_data(deleted)
    orders = _orders(engine)
    assert json.loads(orders["shared"]) == {
        "rounds": 4, "order": [OTHER, accounts.DELETED_USER_PLACEHOLDER, "third"]}
    assert json.loads(orders["sleeper"]) == {"order": [OTHER, UID]}
    assert orders["list"] == f'["{deleted}"]' and json.loads(orders["noorder"]) == {"order": deleted}
    assert counts["pick_assignment_order_anonymized"] == 1


def test_pick_assignment_order_keeps_a_public_sleeper_id_and_anonymizes_the_alias(engine):
    with engine.begin() as conn:
        _assignment_league(conn, "lg", OTHER, {"order": [UID, ALIAS, OTHER]})
    counts = accounts.delete_user_data(UID)
    assert json.loads(_orders(engine)["lg"])["order"] == [UID, accounts.DELETED_USER_PLACEHOLDER, OTHER]
    assert counts["pick_assignment_order_anonymized"] == 1


# ── Team overhaul (keys the owner as account_user_id, the rest by overhaul_id) ──

OVERHAUL_CHILDREN = (db.overhaul_offers_table, db.overhaul_roadmaps_table,
                     db.overhaul_attempts_table, db.overhaul_reservations_table)
OWNER_ESPN_MEMBER = "espn:{0WNE0000-AAAA-BBBB-CCCC-DDDDEEEEFFFF}"   # the owner's own ESPN member id
OWNER_NAME = "owner-display-name"
PLACEHOLDER = accounts.DELETED_USER_PLACEHOLDER


def _overhaul(conn, overhaul_id, account_user_id, league_user_id):
    seed(conn, db.overhauls_table, overhaul_id, overhaul_id=overhaul_id,
         account_user_id=account_user_id, league_user_id=league_user_id)


def _children(conn, overhaul_id, *, offer_id=None):
    seed(conn, db.overhaul_offers_table, overhaul_id, overhaul_id=overhaul_id,
         offer_id=offer_id or "of-" + overhaul_id, package_hash="h-" + overhaul_id)
    seed(conn, db.overhaul_roadmaps_table, overhaul_id, overhaul_id=overhaul_id)
    seed(conn, db.overhaul_attempts_table, overhaul_id, overhaul_id=overhaul_id,
         attempt_id="at-" + overhaul_id, batch_id="b-" + overhaul_id)
    seed(conn, db.overhaul_reservations_table, overhaul_id, overhaul_id=overhaul_id)


def _named_offer(conn, offer_id, counterparty, decision):
    """An offer in OTHER's overhaul, built on the owner's private data."""
    card = {"offer_id": offer_id, "target_user_id": counterparty, "target_username": OWNER_NAME,
            "give": [{"id": "p1"}], "receive": [{"id": "p2"}], "fairness_score": 0.9,
            "mismatch_score": 7.0, "composite_score": 7.0,
            "model_arm": "owner_v2_bilateral", "selection_coverage": "full", "basis": "divergence",
            "reasons": ["Other manager’s preferences are unknown; fit uses market and team context."],
            "likes_you": True,
            "match_context": {"owner_benefits": ["outlook"], "counterparty_benefits": ["need"],
                              "counterparty_preference_evidence": "known",
                              "opponent_outlook": "rebuilder",
                              "support_kind": "interpretable_support_not_probability"}}
    evidence = {"viewer": {"benefits": ["outlook"]}, "counterparty": {"outgoing_personal": 1234},
                "assets": [{"id": "p2", "counterparty_personal": 1500}], "preference_priority": 2}
    seed(conn, db.overhaul_offers_table, offer_id, overhaul_id="ovh-other", offer_id=offer_id,
         package_hash="sha1-" + offer_id, counterparty_user_id=counterparty,
         counterparty_username=OWNER_NAME, card_json=json.dumps(card),
         evidence_json=json.dumps(evidence), decision=decision)


def test_overhauls_deleted_and_offers_naming_the_owner_scrubbed(engine):
    with engine.begin() as conn:
        _overhaul(conn, "ovh-own", UID, UID)
        _overhaul(conn, "ovh-alias", ALIAS, OWNER_ESPN_MEMBER)
        _overhaul(conn, "ovh-other", OTHER, OTHER)
        for oid in ("ovh-own", "ovh-alias"):
            _children(conn, oid)
        _children(conn, "ovh-other", offer_id="of-unrelated")
        _named_offer(conn, "of-sleeper", UID, "pass")
        _named_offer(conn, "of-espn", OWNER_ESPN_MEMBER, "undecided")
        _named_offer(conn, "of-liked", UID, "like")
        seed(conn, db.overhaul_attempts_table, "sent", overhaul_id="ovh-other",
             attempt_id="at-sent", batch_id="b-sent", offer_id="of-sleeper")
        conn.execute(db.overhaul_roadmaps_table.update().where(
            db.overhaul_roadmaps_table.c.overhaul_id == "ovh-other").values(
            summary_json=json.dumps({"counterparties": [UID, "unrelated", OWNER_ESPN_MEMBER],
                                     "score": 3})))
    before = {r["offer_id"]: dict(r) for r in rows(engine, db.overhaul_offers_table)}
    counts = accounts.delete_user_data(UID)

    assert [r["overhaul_id"] for r in rows(engine, db.overhauls_table)] == ["ovh-other"]
    for tbl in OVERHAUL_CHILDREN:
        assert {r["overhaul_id"] for r in rows(engine, tbl)} == {"ovh-other"}, tbl.name
    assert counts["overhauls_deleted"] == 2
    assert counts["overhaul_offers_counterparty_anonymized"] == 3
    offers = {r["offer_id"]: dict(r) for r in rows(engine, db.overhaul_offers_table)}
    assert offers["of-unrelated"] == before["of-unrelated"]
    for oid in ("of-sleeper", "of-espn", "of-liked"):
        offer = offers[oid]
        assert offer["counterparty_user_id"] == PLACEHOLDER
        assert offer["counterparty_username"] == PLACEHOLDER
        assert offer["evidence_json"] is None
        assert offer["decision"] == before[oid]["decision"]
        assert json.loads(offer["card_json"]) == {
            "offer_id": oid, "target_user_id": PLACEHOLDER, "target_username": PLACEHOLDER,
            "give": [{"id": "p1"}], "receive": [{"id": "p2"}], "fairness_score": 0.9,
            # legal's blended-scalar test: surplus_margin (mismatch_score) is
            # nulled on every card of the partner, and composite_score, its
            # copy on the owner arms, with it.
            "mismatch_score": None, "composite_score": None,
            "model_arm": "owner_v2_bilateral", "selection_coverage": "full", "basis": "divergence",
            "match_context": {"owner_benefits": ["outlook"],
                              "support_kind": "interpretable_support_not_probability"}}
    # A passed offer keeps the hash that stops it coming back; an undecided one
    # gets a fresh one, so regeneration can't revive the scrubbed row.
    assert offers["of-sleeper"]["package_hash"] == "sha1-of-sleeper"
    assert offers["of-liked"]["package_hash"] == "sha1-of-liked"
    assert offers["of-espn"]["package_hash"].startswith("redacted_")
    # A liked or undecided offer is retired the native way: stale is never sent
    # (the placeholder resolves to no roster), and a refresh rebuilds it.
    assert {oid: offers[oid]["availability"] for oid in ("of-sleeper", "of-espn", "of-liked")} == {
        "of-sleeper": "fresh", "of-espn": "stale", "of-liked": "stale"}
    assert {r["attempt_id"] for r in rows(engine, db.overhaul_attempts_table)} == {"at-ovh-other", "at-sent"}
    summary = json.loads(rows(engine, db.overhaul_roadmaps_table)[0]["summary_json"])
    assert summary == {"counterparties": [PLACEHOLDER, "unrelated", PLACEHOLDER], "score": 3}
    assert counts["overhaul_roadmaps_counterparty_anonymized"] == 1
    # Nothing that names the owner is left in any overhaul table.
    residue = json.dumps([dict(r) for t in (db.overhauls_table, *OVERHAUL_CHILDREN)
                          for r in rows(engine, t)], default=str)
    for marker in (UID, ALIAS, OWNER_ESPN_MEMBER, OWNER_NAME, "sha1-of-espn", "1234", "1500"):
        assert marker not in residue, marker


def test_a_minted_id_in_other_overhauls_snapshots_and_recovery_becomes_the_placeholder(engine):
    """ESPN/MFL grids can key a snapshot's rosters, and name a recovery pick's
    holder, by the importer's Fleeced-minted id: that names the person, so it
    goes (as in draft_picks). Platform ids stay."""
    deleted = "entry:espn:{5EED0000-AAAA-BBBB-CCCC-DDDDEEEEFFFF}"
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id=deleted))
        _overhaul(conn, "ovh-espn", OTHER, OTHER)
        _overhaul(conn, "ovh-sleeper", OTHER, OTHER)
        ovh = db.overhauls_table
        conn.execute(ovh.update().where(ovh.c.overhaul_id == "ovh-espn").values(
            snapshot_json=json.dumps({"season": 2026, "my_roster_id": 3,
                                      "rosters": {OTHER: ["p1"], deleted: ["p2", "pk_1"], UID: ["p3"]}}),
            recovery_json=json.dumps({"state": "missing_with_known_holder", "pick_id": "pk_1",
                                      "holder_user_id": deleted, "holder_username": "Their Team"})))
        conn.execute(ovh.update().where(ovh.c.overhaul_id == "ovh-sleeper").values(
            snapshot_json=json.dumps({"rosters": {OTHER: ["p1"], UID: ["p3"]}}),
            recovery_json=json.dumps({"holder_user_id": UID, "holder_username": "pub"})))
    before = {r["overhaul_id"]: dict(r) for r in rows(engine, db.overhauls_table)}
    counts = accounts.delete_user_data(deleted)
    after = {r["overhaul_id"]: dict(r) for r in rows(engine, db.overhauls_table)}
    assert json.loads(after["ovh-espn"]["snapshot_json"]) == {
        "season": 2026, "my_roster_id": 3,
        "rosters": {OTHER: ["p1"], UID: ["p3"], PLACEHOLDER: ["p2", "pk_1"]}}
    assert json.loads(after["ovh-espn"]["recovery_json"]) == {
        "state": "missing_with_known_holder", "pick_id": "pk_1",
        "holder_user_id": PLACEHOLDER, "holder_username": PLACEHOLDER}
    assert after["ovh-sleeper"] == before["ovh-sleeper"]
    assert counts["overhaul_snapshots_anonymized"] == 1
    # Deleting the Sleeper-keyed user leaves their public Sleeper id in others'
    # snapshots (platform data, as on Sleeper pick grids).
    assert accounts.delete_user_data(UID)["overhaul_snapshots_anonymized"] == 0
    assert {r["overhaul_id"]: dict(r) for r in rows(engine, db.overhauls_table)}["ovh-sleeper"] \
        == before["ovh-sleeper"]


def test_export_carries_own_overhauls_without_private_evidence(engine):
    with engine.begin() as conn:
        _overhaul(conn, "ovh-own", UID, UID)
        _overhaul(conn, "ovh-other", OTHER, OTHER)
        _children(conn, "ovh-other")
        _children(conn, "ovh-own")
        conn.execute(db.overhaul_offers_table.update().where(
            db.overhaul_offers_table.c.overhaul_id == "ovh-own").values(
            counterparty_user_id=OTHER, evidence_json=json.dumps({"counterparty": {"x": 1}}),
            card_json=json.dumps({"target_user_id": OTHER, "reasons": ["r"],
                                  "match_context": {"owner_benefits": ["a"],
                                                    "counterparty_benefits": ["b"]}})))
    tables = accounts.export_user_data(UID)["tables"]
    assert [r["overhaul_id"] for r in tables["overhauls"]] == ["ovh-own"]
    for tbl in OVERHAUL_CHILDREN:
        assert [r["overhaul_id"] for r in tables[tbl.name]] == ["ovh-own"], tbl.name
    offer = tables["overhaul_offers"][0]
    assert "evidence_json" not in offer
    assert json.loads(offer["card_json"]) == {"target_user_id": OTHER,
                                              "match_context": {"owner_benefits": ["a"]}}


def _code_without_comments(source):
    return " ".join(t.string for t in tokenize.generate_tokens(io.StringIO(source).readline)
                    if t.type != tokenize.COMMENT)


def test_every_table_with_a_user_id_column_is_handled_in_accounts():
    """The overhaul gap: a table keyed by any *user_id* column that accounts.py
    never names in code (comments stripped) escapes deletion and export alike.
    Name it there: delete it, anonymize it, or keep it with a reason."""
    code = _code_without_comments(inspect.getsource(accounts))
    unnamed = [t.name for t in db.metadata.sorted_tables
               if any("user_id" in c.name for c in t.columns)
               and not re.search(rf"\b{t.name}_table\b|[\"']{t.name}[\"']", code)]
    assert unnamed == []


# ── Legal R28.22 d2: overhauls whose owner account no longer exists ──────────

def test_orphaned_overhauls_are_deleted_and_live_owners_kept(engine):
    with engine.begin() as conn:
        _overhaul(conn, "ovh-orphan", "deleted-before-the-fix", "deleted-before-the-fix")
        _overhaul(conn, "ovh-entry-orphan", "entry:mfl:61408.f0003", "mfl:61408.f0003")
        _overhaul(conn, "ovh-live", UID, UID)                              # a users row
        _overhaul(conn, "ovh-session-only", "session-only", "session-only")  # a durable session
        seed(conn, db.sessions_table, "session-only", user_id="session-only")
        for oid in ("ovh-orphan", "ovh-entry-orphan", "ovh-live", "ovh-session-only"):
            _children(conn, oid)
    assert accounts.delete_orphaned_overhauls() == 2
    kept = {"ovh-live", "ovh-session-only"}
    assert {r["overhaul_id"] for r in rows(engine, db.overhauls_table)} == kept
    for tbl in OVERHAUL_CHILDREN:
        assert {r["overhaul_id"] for r in rows(engine, tbl)} == kept, tbl.name
    assert accounts.delete_orphaned_overhauls() == 0                     # idempotent


def test_the_orphan_sweep_runs_once_per_process_and_logs_only_a_count(monkeypatch, caplog):
    from backend import server
    calls = []
    monkeypatch.setattr(server, "_orphaned_overhauls_swept", False)

    def fail_then_count():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("db down")
        return 3
    monkeypatch.setattr(accounts, "delete_orphaned_overhauls", fail_then_count)
    with caplog.at_level("INFO"):
        for _ in range(3):
            server._sweep_orphaned_overhauls_once()
    assert len(calls) == 2                       # a failure retries; a success ends it
    assert "Deleted 3 overhaul(s) whose owner account no longer exists" in caplog.text


def test_the_cleanup_loop_runs_the_orphan_sweep():
    from backend import server
    loop = _code_without_comments(inspect.getsource(server._cleanup_loop))
    assert "_sweep_orphaned_overhauls_once ( )" in loop
