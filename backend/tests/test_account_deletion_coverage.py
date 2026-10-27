"""Synthetic-only regression coverage for the current account-deletion schema."""
import json

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
