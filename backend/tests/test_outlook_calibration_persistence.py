"""Independent adversarial round persistence tests, synthetic SQLite only.

Authored from the frozen acceptance contract before inspecting new service outputs.
No owner engine stubs here: these tests deliberately test the durable boundary.
"""
import json
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from backend import database as db, blind_grading as bg

ROUND = 'outlook-v2-v3-1'
NOW = '2026-11-06T12:00:00+00:00'

@pytest.fixture
def engine(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    db.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(db.users_table.insert(), [dict(sleeper_user_id=uid, verified_via='sleeper', created_at=NOW)
            for uid in ('account', 'account-0', 'account-1', 'account-2')])
    monkeypatch.setattr(db, 'engine', engine)
    yield engine
    engine.dispose()

def session(sid, *, round_id=ROUND, status='open', owner='account', active=None):
    return dict(session_id=sid, user_id=owner, league_id='league', status=status,
                round_id=round_id, active_round_key=active, seed='71', created_at=NOW,
                completed_at=None, counts_json='{}', source_json='{}', error_json=None)

def card(cid, sid, pos=1, owner='account', arms=('current',)):
    return dict(card_id=cid, session_id=sid, user_id=owner, position=pos,
                arms_json=json.dumps({a:{'version': 'private-version', 'rank': pos} for a in arms}),
                trade_json=json.dumps({'partner_name':'Partner', 'give':[], 'receive':[]}),
                grade=None, skipped=0, tags_json='[]', graded_at=None, partner_user_id='partner')

def answer(cid, grade=5, skipped=False, tags=(), owner='account', now=NOW):
    return db.answer_grading_card(cid, owner, grade=grade, skipped=skipped,
                                 tags_json=json.dumps(list(tags)), now=now)

def test_round_resume_and_reports_never_relabel_old_history(engine):
    for sid, rd in [('old',None), ('new',ROUND), ('future','future-round')]:
        db.insert_grading_session(session(sid,round_id=rd),[card(sid+'-c',sid)])
    assert db.load_open_grading_session('account','league')['session_id']=='old'
    assert db.load_open_grading_session('account','league',round_id=ROUND)['session_id']=='new'
    assert [r['session_id'] for r in db.list_open_grading_sessions()]==['old']
    old_before=db.load_grading_session('old')
    assert answer('new-c')['status']=='completed'
    assert db.load_grading_session('old')==old_before
    sessions,cards=db.load_grading_report_rows(None,True)
    assert [s['session_id'] for s in sessions]==['old']
    assert [c['card_id'] for c in cards]==['old-c']
    sessions,cards=db.load_grading_report_rows(None,False,round_id=ROUND)
    assert [s['session_id'] for s in sessions]==['new']
    assert [c['card_id'] for c in cards]==['new-c']

@pytest.mark.parametrize('grade,skip,tags',[(5,False,()),(1,False,('other',)),(None,True,())])
def test_final_answer_lost_response_retry_preserves_first_feedback(engine,grade,skip,tags):
    db.insert_grading_session(session('s',active='one-active'),[card('c','s')])
    first=answer('c',grade,skip,tags)
    frozen=db.load_grading_cards('s')
    retried=answer('c',grade,skip,tags,now='2026-11-07T12:00:00+00:00')
    assert first['status']==retried['status']=='completed'
    assert retried['rejected'] is False
    assert retried['answered']==retried['total']==1
    assert db.load_grading_cards('s')==frozen
    assert db.load_grading_session('s')['active_round_key'] == 'one-active'
    changed=answer('c',4,False,())
    assert changed['rejected'] and changed['conflict']
    assert db.load_grading_cards('s')==frozen

def test_partial_answer_retry_and_foreign_ids_are_noops(engine):
    db.insert_grading_session(session('s'),[card('c1','s'),card('c2','s',2)])
    assert answer('c1')['status']=='open'
    frozen=db.load_grading_cards('s')
    assert answer('c1')['answered']==1
    assert answer('c1',grade=1)['conflict']
    assert answer('c2',owner='foreign') is None
    assert db.load_grading_session('s','foreign') is None
    assert db.load_grading_cards('s')==frozen

def test_cohort_unique_until_failure_and_remains_unique_after_completion(engine):
    db.insert_grading_session(session('s',status='building',active='round-account-league'),[])
    with pytest.raises(IntegrityError):
        db.insert_grading_session(session('duplicate',status='building',active='round-account-league'),[])
    assert db.fail_grading_session('s','{"code":"candidate_empty"}')
    db.insert_grading_session(session('retry',active='round-account-league'),[card('c','retry')])
    assert answer('c')['status']=='completed'
    with pytest.raises(IntegrityError):
        db.insert_grading_session(session('after',active='round-account-league'),[])

def test_failed_bulk_insert_rolls_back_entire_deck_and_status(engine):
    db.insert_grading_session(session('s',status='building'),[])
    with pytest.raises(IntegrityError):
        db.finish_grading_session_build('s',[card('duplicate','s',1),card('duplicate','s',2)],
                                       counts_json='{}',source_json='{"new":"payload"}')
    assert db.load_grading_session('s')['status']=='building'
    assert db.load_grading_session('s')['source_json']=='{}'
    assert db.load_grading_cards('s')==[]

def test_shared_feedback_is_one_exposure_and_two_credits(engine):
    db.insert_grading_session(session('s'),[card('c','s',arms=('current','value_core'))])
    answer('c')
    summaries,shared=bg.arm_summaries(db.load_grading_cards('s'))
    assert shared==1
    for arm in ('current','value_core'):
        assert summaries[arm]['n']==1
        assert summaries[arm]['mean']==5

def test_public_next_card_is_allowlisted_not_provenance(engine):
    db.insert_grading_session(session('s'),[card('c','s',arms=('current','value_core'))])
    value=db.load_next_grading_card('s')
    assert set(value)=={'card_id','position','trade_json'}
    assert 'private-version' not in json.dumps(value)


def test_concurrent_start_commits_one_active_cohort(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock
    from backend import outlook_calibration as oc
    eng = create_engine('sqlite:///' + str(tmp_path / 'concurrent.sqlite'),
                        connect_args={'check_same_thread': False, 'timeout': 10})
    db.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(db.users_table.insert().values(sleeper_user_id='account', verified_via='sleeper'))
    monkeypatch.setattr(db, 'engine', eng)
    original = db.load_open_grading_session
    barrier, lock, entered = Barrier(2), Lock(), [0]
    def synchronized(*args, **kwargs):
        row = original(*args, **kwargs)
        with lock:
            entered[0] += 1
            first = entered[0] <= 2
        if first:
            barrier.wait(timeout=5)
        return row
    monkeypatch.setattr(db, 'load_open_grading_session', synchronized)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: oc.start_session(
                user_id='account', league_user_id='seat', league_id='league'), range(2)))
        assert len({r['session']['session_id'] for r in results}) == 1
        with eng.connect() as conn:
            assert len(conn.execute(select(db.grading_sessions_table)).all()) == 1
    finally:
        eng.dispose()


def test_expired_worker_is_fenced_from_snapshot_publish_and_failure(engine):
    from datetime import datetime, timedelta, timezone
    from backend import outlook_calibration as oc
    now = datetime.now(timezone.utc)
    db.insert_grading_session(session('s', status='building'), [])
    assert oc._claim_lease('old', now)
    assert oc._renew_lease('old')
    assert not oc._claim_lease('other', now)
    with engine.begin() as conn:
        conn.execute(db.grading_build_leases_table.update().values(expires_at=(now - timedelta(seconds=1)).isoformat()))
    assert oc._claim_lease('new', now)
    assert not oc._renew_lease('old')
    assert not oc._save_build('s', {'secret': 'old'}, {}, 'old')
    assert not db.finish_grading_session_build('s', [card('c', 's')], counts_json='{}', source_json='{}', lease_token='old')
    assert not db.fail_grading_session('s', '{}', lease_token='old')
    assert db.load_grading_session('s')['status'] == 'building'
    assert db.load_grading_cards('s') == []
    assert db.fail_grading_session('s', '{}', lease_token='new')
