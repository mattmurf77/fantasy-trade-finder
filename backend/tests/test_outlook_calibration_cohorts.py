"""Independent all-user/all-connected-league enumeration cases. No customer data."""
import json
import pytest
from sqlalchemy import select
from backend import database as db, outlook_calibration as oc, blind_grading as bg
from backend.tests.test_outlook_calibration_persistence import engine, NOW

def seed(engine):
    with engine.begin() as conn:
        conn.execute(db.users_table.insert(),[
            {'sleeper_user_id':u,'verified_via':'sleeper' if u!='unverified' else None}
            for u in ('importer','second-member','roster-only','no-league','unverified')])
        conn.execute(db.leagues_table.insert(),[
            {'sleeper_league_id':l,'user_id':'importer','platform':'sleeper'} for l in ('L1','L2')])
        conn.execute(db.league_members_table.insert(),[
            {'league_id':'L1','user_id':u,'roster_data':'[]'}
            for u in ('importer','second-member','roster-only')])
        # session_init writes this authenticated user's successful connection;
        # no ranking, preference, deck, grading or overhaul was ever used.
        conn.execute(db.user_events_table.insert().values(user_id='second-member',event_type='league_synced',
            league_id='L1',occurred_at=NOW,source='api'))

def test_connected_second_member_without_any_trade_use_is_not_omitted(engine):
    seed(engine)
    targets,coverage=oc.connected_targets()
    pairs={(t['user_id'],t['league_id']) for t in targets}
    assert ('second-member','L1') in pairs
    assert {('importer','L1'),('importer','L2')}<=pairs
    assert not any(u in {'roster-only','no-league','unverified'} for u,l in pairs)

def test_pregeneration_is_bounded_idempotent_and_rejects_unconnected_targets(engine,monkeypatch):
    seed(engine)
    monkeypatch.setattr(oc,'enabled',lambda:True)
    initial=oc.pregenerate(limit=1)
    assert initial['batch_pairs']==1 and initial['remaining_pairs']>=1
    with engine.connect() as conn:
        rows=list(conn.execute(select(db.grading_sessions_table)).mappings())
    retry=oc.pregenerate(limit=1)
    with engine.connect() as conn:
        assert list(conn.execute(select(db.grading_sessions_table)).mappings())==rows
    with pytest.raises(bg.GradingError) as err:
        oc.pregenerate(targets=[{'user_id':'roster-only','league_id':'L1','league_user_id':'importer'}])
    assert err.value.code=='unconnected_target'

def test_pregeneration_ignores_caller_supplied_seat_override(engine,monkeypatch):
    seed(engine)
    monkeypatch.setattr(oc,'enabled',lambda:True)
    oc.pregenerate(targets=[{'user_id':'importer','league_id':'L1','league_user_id':'victim'}])
    with engine.connect() as conn:
        row=conn.execute(select(db.grading_sessions_table)).mappings().one()
    assert json.loads(row['source_json'])['seat'] is None  # provider resolves the authorized seat


def test_prepare_switch_queues_before_public_round_exposure(engine, monkeypatch):
    from backend import feature_flags as flags
    seed(engine)
    monkeypatch.setattr(flags, '_flags_cache', {**flags.DEFAULT_FLAGS, 'grading.outlook_prepare': True})
    assert oc.build_enabled() and not oc.enabled()
    result = oc.pregenerate(limit=1)
    assert result['batch_pairs'] == 1
    with engine.connect() as conn:
        queued = conn.execute(select(db.grading_sessions_table)).mappings().one()
    assert queued['status'] == 'building'
    flags._flags_cache['grading.outlook_prepare'] = False
    assert not oc.build_enabled()
    with pytest.raises(bg.GradingError) as exc:
        oc.pregenerate(limit=1)
    assert exc.value.code == 'round_disabled'


def test_deleted_account_between_enumeration_and_enqueue_cannot_recreate_private_rows(engine,monkeypatch):
    seed(engine)
    monkeypatch.setattr(oc,'build_enabled',lambda:True)
    original=oc.connected_targets
    def stale_enumerator():
        targets,coverage=original()
        targets=[t for t in targets if t['user_id']=='importer']
        with engine.begin() as conn:
            conn.execute(db.users_table.delete().where(db.users_table.c.sleeper_user_id=='importer'))
        return targets,coverage
    monkeypatch.setattr(oc,'connected_targets',stale_enumerator)
    try:
        oc.pregenerate(limit=1)
    except db.AccountGone:
        pass
    with engine.connect() as conn:
        recreated=conn.execute(select(db.grading_sessions_table).where(
            db.grading_sessions_table.c.user_id=='importer')).mappings().all()
    assert recreated==[]
