"""Independent synthetic service tests. Stub proof/arm inputs test orchestration only;
actual owner proof and production gate parity require separate adapter tests.
"""
import json
from types import SimpleNamespace
import pytest
from sqlalchemy import select, func
from backend import accounts, blind_grading as bg, database as db, outlook_calibration as oc
from backend.tests.test_outlook_calibration_persistence import engine, session, card, answer, ROUND

class Proof:
    def __init__(self,version,valid=True): self.model_identity=('owner',version);self.valid=valid
    def matches(self,card): return self.valid
    def as_dict(self): return {'model_version':self.model_identity[1], 'private_counterparty_board':{'secret-player':9999}}

def offer(version,i,partner='partner',valid=True):
    return SimpleNamespace(target_user_id=partner,give_player_ids=('g',),receive_player_ids=(f'r{i}',),
                           owner_evaluation=Proof(version,valid))

def frozen_factory(*,sizes=(12,12),shared=3,duplicate=False,fail=None,invalid=False):
    calls=[]
    assets={i:{'name':i,'position':'WR','nfl_team':'X','age':26,'value':1000}
            for i in ['g']+[f'r{i}' for i in range(100)]}
    catalog=bg.Catalog(assets=assets,partner_names={'partner':'Partner'},
                       holdings={'seat':frozenset({'g'}),'partner':frozenset(assets)-{'g'}})
    def run(version):
        calls.append(version)
        arm=list(oc.MODEL_VERSIONS.values()).index(version)
        if fail==arm: raise RuntimeError('SECRET DATA MUST NOT LEAK')
        ids=list(range(shared))+list(range(10+arm*30,10+arm*30+max(0,sizes[arm]-shared)))
        rows=[offer(version,i,valid=not invalid) for i in ids[:sizes[arm]]]
        if duplicate and rows: rows.append(rows[0])
        return rows,{'native_count':len(rows),'final_count':len(rows)}
    frozen=SimpleNamespace(source={'common_input_hash':'frozen-common-hash'},catalog=catalog,run_arm=run)
    return frozen,calls

def build(**kwargs):
    frozen,calls=frozen_factory(**kwargs)
    captures=[]
    def capture(**scope): captures.append(scope);return frozen
    start=oc.start_session(user_id='account',league_user_id='seat',league_id='league',seed=91)
    sid=start['session']['session_id']
    oc.build_session(session_id=sid,capture=capture)
    return sid,db.load_grading_session(sid),db.load_grading_cards(sid),captures,calls

def test_same_capture_two_versions_balanced_dedup_and_stable_resume(engine):
    sid,row,cards,captures,calls=build(duplicate=True)
    assert row['status']=='open'
    assert captures==[dict(user_id='account',league_user_id='seat',league_id='league')]
    assert sorted(calls)==sorted(oc.MODEL_VERSIONS.values())
    assert len(cards)==21
    counts=json.loads(row['counts_json'])
    assert counts['shared']==3
    for version in oc.MODEL_VERSIONS.values():
        assert counts['arms'][version]['unique_inventory']==12
        assert counts['arms'][version]['duplicate_occurrences']==1
        assert counts['arms'][version]['selected']==12
    credits={'current':0,'value_core':0}
    for c in cards:
        for a in json.loads(c['arms_json']): credits[a]+=1
        assert abs(credits['current']-credits['value_core'])<=1
        payload=json.loads(c['trade_json'])
        assert set(payload)=={'partner_name','give','receive'}
        assert 'secret' not in c['trade_json']
    resumed=oc.start_session(user_id='account',league_user_id='seat',league_id='league')
    assert resumed['session']['session_id']==sid and resumed['resumed']
    oc.build_session(session_id=sid,capture=lambda **k: pytest.fail('recaptured opened cohort'))
    assert db.load_grading_cards(sid)==cards

@pytest.mark.parametrize('sizes,fail,invalid,code',[
    ((0,12),None,False,'comparison_too_few'),
    ((0,0),None,False,'comparison_too_few'),
    ((20,20),1,False,'comparison_failed'),
    ((20,20),None,True,'comparison_failed'),
])
def test_insufficient_error_invalid_proof_never_exposes_partial_deck(engine,sizes,fail,invalid,code):
    sid,row,cards,_,_=build(sizes=sizes,shared=0,fail=fail,invalid=invalid)
    assert row['status']=='failed' and cards==[]
    assert json.loads(row['error_json'])=={'code':code}
    assert row['active_round_key'] is None
    assert 'SECRET' not in json.dumps(bg.session_view(row))

def test_shorter_valid_arm_caps_both_without_backfill(engine):
    sid,row,cards,_,_=build(sizes=(11,30),shared=0)
    assert row['status']=='open' and len(cards)==22
    counts=json.loads(row['counts_json'])
    assert {v['selected'] for v in counts['arms'].values()}=={11}

def test_completed_round_is_never_regenerated_by_repeated_start(engine):
    sid,row,cards,_,_=build()
    for c in cards: answer(c['card_id'])
    completed=db.load_grading_session(sid)
    retry=oc.start_session(user_id='account',league_user_id='new-seat',league_id='league')
    assert retry['resumed'] and not retry['needs_build']
    assert retry['session']['session_id']==sid
    assert db.load_grading_session(sid)==completed

def test_interrupted_capture_is_failed_not_recaptured_under_old_identity(engine):
    row=session('interrupted',status='building')
    row['source_json']=json.dumps({'seat':'seat','build_stage':'captured','snapshot':{'old':'data'}})
    db.insert_grading_session(row,[])
    oc.build_session(session_id='interrupted',capture=lambda **k: pytest.fail('silent recapture'))
    assert db.load_grading_session('interrupted')['status']=='failed'
    assert json.loads(db.load_grading_session('interrupted')['error_json'])['code']=='comparison_interrupted'

def test_report_reconciles_unique_feedback_and_separates_partial_and_old(engine):
    sid,row,cards,_,_=build()
    shared=next(c for c in cards if len(json.loads(c['arms_json']))==2)
    answer(shared['card_id'])
    old=session('old',round_id=None,status='completed')
    db.insert_grading_session(old,[card('old-card','old')])
    before=db.load_grading_cards(sid)
    report=oc.report(include_open=True)
    assert report['status_counts']=={'open':1}
    assert report['partial']['answered_observations']==1
    assert report['completed']['answered_observations']==0
    for arm in report['partial']['arms'].values(): assert arm['n']==1
    assert 'secret' not in json.dumps(report) and '"account"' not in json.dumps(report)
    assert db.load_grading_cards(sid)==before

def test_export_does_not_disclose_hidden_counterparty_proof(engine):
    sid,row,cards,_,_=build()
    exported=accounts._export_grading_arms(cards[0]['arms_json'])
    assert 'private_counterparty_board' not in json.dumps(exported)
    assert 'secret-player' not in json.dumps(exported)

def test_core_build_and_feedback_write_no_organic_or_learning_tables(engine):
    protected=[t for name,t in db.metadata.tables.items() if not name.startswith('grading_')]
    def counts():
        with engine.connect() as conn:
            return {t.name:conn.execute(select(func.count()).select_from(t)).scalar() for t in protected}
    before=counts()
    sid,row,cards,_,_=build()
    answer(cards[0]['card_id'])
    oc.report(include_open=True)
    assert counts()==before

def test_participant_deletion_discards_private_replay_not_feedback(engine):
    from backend import deletion_scrub as scrub
    sid,row,cards,_,_=build()
    answer(cards[0]['card_id'])
    saved=db.load_grading_cards(sid)
    source=json.loads(row['source_json'])
    source['snapshot']['members']={'partner':{'private_board':{'WR':1900}}}
    with engine.begin() as conn:
        conn.execute(db.grading_sessions_table.update().where(db.grading_sessions_table.c.session_id==sid)
                     .values(source_json=json.dumps(source)))
        scrub._redact_grading_source(conn,{**row,'source_json':json.dumps(source)},
                                     SimpleNamespace(ids={'partner'},token='deleted-token'))
    after=json.loads(db.load_grading_session(sid)['source_json'])
    assert after['replay_invalidated']=='participant_deleted'
    assert 'snapshot' not in after and 'proofs' not in after
    assert db.load_grading_cards(sid)==saved

def test_queue_bounded_and_disabled_flag_leaves_pending_immutable(engine,monkeypatch):
    ids=[]
    for i in range(3):
        ids.append(oc.start_session(user_id=f'account-{i}',league_user_id='seat',league_id='league')['session']['session_id'])
    frozen,_=frozen_factory()
    monkeypatch.setattr(oc,'enabled',lambda:True)
    result=oc.drain_queue(capture=lambda **k:frozen,max_jobs=1)
    assert result['processed']==1
    assert sorted(db.load_grading_session(s)['status'] for s in ids)==['building','building','open']
    snapshot=[db.load_grading_session(s) for s in ids]
    monkeypatch.setattr(oc,'enabled',lambda:False)
    result=oc.drain_queue(capture=lambda **k:pytest.fail('built while disabled'),max_jobs=100)
    assert result['processed']==0
    assert [db.load_grading_session(s) for s in ids]==snapshot


@pytest.fixture(autouse=True)
def captured_snapshot_is_current(monkeypatch):
    # Orchestration fixtures omit real provider/input identities; adapter tests
    # exercise the real freshness contract separately.
    from backend import outlook_calibration_adapter as adapter
    monkeypatch.setattr(adapter, "is_current", lambda *a, **kw: True)


def test_stale_unanswered_snapshot_retires_without_mutating_cards(engine, monkeypatch):
    from backend import outlook_calibration_adapter as adapter
    sid, row, cards, _, _ = build()
    monkeypatch.setattr(adapter, 'is_current', lambda *a, **kw: False)
    replacement = oc.start_session(user_id='account', league_user_id='seat', league_id='league')
    assert replacement['session']['session_id'] != sid
    assert replacement['session']['status'] == 'building'
    assert db.load_grading_session(sid)['status'] == 'failed'
    assert json.loads(db.load_grading_session(sid)['error_json'])['code'] == 'comparison_stale'
    assert db.load_grading_cards(sid) == cards


def test_started_snapshot_remains_frozen_after_known_input_change(engine, monkeypatch):
    from backend import outlook_calibration_adapter as adapter
    sid, row, cards, _, _ = build()
    answer(cards[0]['card_id'])
    before = db.load_grading_session(sid)
    monkeypatch.setattr(adapter, 'is_current', lambda *a, **kw: pytest.fail('started exercise revalidated'))
    assert oc.start_session(user_id='account', league_user_id='seat', league_id='league')['session']['session_id'] == sid
    assert db.load_grading_session(sid) == before


def test_capture_resolves_previously_unobserved_coowner_seat(engine):
    frozen, _ = frozen_factory()
    frozen.source['league_user_id'] = 'seat'
    queued = oc.start_session(user_id='account', league_user_id=None, league_id='league')
    sid = queued['session']['session_id']
    oc.build_session(session_id=sid, capture=lambda **kwargs: frozen)
    row = db.load_grading_session(sid)
    assert row['status'] == 'open'
    assert json.loads(row['source_json'])['seat'] == 'seat'


@pytest.mark.parametrize('n', [1, 2, 9])
def test_small_valid_inventory_keeps_equal_quality_sample_with_honest_denominators(engine, n):
    sid, row, cards, _, _ = build(sizes=(n, 20), shared=0)
    assert row['status'] == 'open'
    counts = json.loads(row['counts_json'])
    assert len(cards) == 2 * n and counts['sample_size_status'] == 'limited'
    assert {a['selected'] for a in counts['arms'].values()} == {n}


def test_full_inventory_counts_but_only_bounded_selected_proofs_expand(engine, monkeypatch):
    import weakref
    expansions, prior_refs = [], []
    original = Proof.as_dict
    monkeypatch.setattr(Proof, 'as_dict', lambda self: (expansions.append(self.model_identity), original(self))[1])
    frozen, _ = frozen_factory(sizes=(30, 30), shared=0)
    native = frozen.run_arm
    class NativeCard:
        pass
    def run(version):
        # The next full generation must not overlap the previous native deck.
        assert not any(ref() is not None for ref in prior_refs)
        cards, diagnostics = native(version)
        wrapped = []
        for c in cards:
            obj = NativeCard()
            obj.__dict__.update(c.__dict__)
            wrapped.append(obj)
        prior_refs[:] = [weakref.ref(c) for c in wrapped]
        return wrapped, diagnostics
    frozen.run_arm = run
    sid = oc.start_session(user_id='account', league_user_id='seat', league_id='league')['session']['session_id']
    oc.build_session(session_id=sid, capture=lambda **kw: frozen)
    row = db.load_grading_session(sid)
    assert row['status'] == 'open'
    assert len(expansions) == 2 * oc.PER_ARM
    counts = json.loads(row['counts_json'])
    assert {a['unique_inventory'] for a in counts['arms'].values()} == {30}
    assert {a['selected'] for a in counts['arms'].values()} == {20}
    assert not any(ref() is not None for ref in prior_refs)


def test_first_exposure_pins_snapshot_even_before_any_answer(engine, monkeypatch):
    from backend import outlook_calibration_adapter as adapter
    monkeypatch.setattr(oc, 'enabled', lambda: True)
    sid, row, cards, _, _ = build()
    first = bg.next_card(user_id='account', session_id=sid)
    assert not first['done']
    assert db.load_grading_session(sid)['first_exposed_at'] is not None
    monkeypatch.setattr(adapter, 'is_current', lambda *a, **kw: pytest.fail('visible exercise replaced'))
    assert oc.current_session(user_id='account', league_id='league')['session']['session_id'] == sid
    assert bg.next_card(user_id='account', session_id=sid) == first
    assert not db.retire_grading_session(sid, '{}')


def test_direct_next_rejects_stale_unexposed_and_paused_ready(engine, monkeypatch):
    from backend import outlook_calibration_adapter as adapter
    sid, row, cards, _, _ = build()
    monkeypatch.setattr(oc, 'enabled', lambda: False)
    with pytest.raises(bg.GradingError) as exc:
        bg.next_card(user_id='account', session_id=sid)
    assert exc.value.code == 'round_paused'
    assert db.load_grading_session(sid)['first_exposed_at'] is None
    monkeypatch.setattr(oc, 'enabled', lambda: True)
    monkeypatch.setattr(oc, 'kick_worker', lambda: None)
    monkeypatch.setattr(adapter, 'is_current', lambda *a, **kw: False)
    with pytest.raises(bg.GradingError) as exc:
        bg.next_card(user_id='account', session_id=sid)
    assert exc.value.code == 'comparison_not_ready'
    assert db.load_grading_session(sid)['status'] == 'failed'
    assert db.load_grading_cards(sid) == cards


def test_worker_continues_after_bounded_batch_but_never_spins_on_foreign_lease(monkeypatch):
    launched = []
    monkeypatch.setattr(oc, 'enabled', lambda: True)
    monkeypatch.setattr(oc, '_pending_work', lambda: True)
    monkeypatch.setattr(oc, '_launch_worker_locked', lambda: launched.append(True))
    monkeypatch.setattr(oc, 'drain_queue', lambda: {'processed': 100})
    oc._worker_main()
    assert launched == [True]
    monkeypatch.setattr(oc, 'drain_queue', lambda: {'busy': True})
    oc._worker_main()
    assert launched == [True]


def test_readiness_counts_latest_connected_attempt_not_historical_failures(engine, monkeypatch):
    with engine.begin() as conn:
        conn.execute(db.users_table.update().where(db.users_table.c.sleeper_user_id == 'account').values(verified_via='sleeper'))
        conn.execute(db.leagues_table.insert(), [
            {'sleeper_league_id': 'league', 'user_id': 'account'},
            {'sleeper_league_id': 'not-queued', 'user_id': 'account'}])
    old = session('old-failed', status='failed')
    old['created_at'] = '2026-01-01T00:00:00+00:00'
    db.insert_grading_session(old, [])
    sid, row, cards, _, _ = build()
    report = oc.report(include_open=True)
    assert report['status_counts'] == {'failed': 1, 'open': 1}
    assert report['readiness_counts'] == {'ready': 1, 'not_queued': 1}
    assert report['partial']['sessions'] == 0
    monkeypatch.setattr(oc, 'enabled', lambda: True)
    bg.next_card(user_id='account', session_id=sid)
    report = oc.report(include_open=True)
    assert report['readiness_counts'] == {'started': 1, 'not_queued': 1}
    assert report['partial']['sessions'] == 1
    assert report['partial']['distinct_accounts'] == 1
    assert report['partial']['distinct_graders'] == 0
    answer(cards[0]['card_id'])
    assert oc.report(include_open=True)['partial']['distinct_graders'] == 1


@pytest.mark.parametrize('phase',['capture','arm'])
def test_account_disappearing_during_build_fences_new_private_material(engine,phase):
    with engine.begin() as conn:
        exists=conn.execute(select(db.users_table.c.sleeper_user_id).where(
            db.users_table.c.sleeper_user_id=='account')).scalar()
        if not exists:conn.execute(db.users_table.insert().values(sleeper_user_id='account',verified_via='sleeper'))
    frozen,_=frozen_factory()
    frozen.source['private_input_marker']='must-not-persist-after-deletion'
    def remove():
        with engine.begin() as conn:
            conn.execute(db.users_table.delete().where(db.users_table.c.sleeper_user_id=='account'))
    if phase=='arm':
        original=frozen.run_arm
        def run(version):
            remove()
            return original(version)
        frozen.run_arm=run
    def capture(**scope):
        if phase=='capture':remove()
        return frozen
    sid=oc.start_session(user_id='account',league_user_id='seat',league_id='league')['session']['session_id']
    try:oc.build_session(session_id=sid,capture=capture)
    except db.AccountGone:pass
    assert db.load_grading_cards(sid)==[]
    row=db.load_grading_session(sid)
    if phase=='capture' and row is not None:
        assert 'must-not-persist-after-deletion' not in row['source_json']

@pytest.mark.parametrize('recreate',[False,True])
def test_private_participant_deleted_before_snapshot_write_is_not_revived(engine,recreate):
    from backend.tests.test_outlook_calibration_persistence import NOW
    original_stamp='2026-01-01T00:00:00+00:00'
    with engine.begin() as conn:
        conn.execute(db.users_table.insert().values(sleeper_user_id='partner',verified_via='sleeper',
            created_at=original_stamp,verified_at=original_stamp))
    frozen,_=frozen_factory()
    frozen.source.update(registered_participants=['account','partner'],
        registered_participant_revisions={'account':NOW,'partner':original_stamp},
        private_partner_marker='erased-private-board-must-not-reappear')
    def capture(**scope):
        # The registry was captured before the board read. Deletion/scrub may
        # finish while provider/board capture is still in flight.
        with engine.begin() as conn:
            conn.execute(db.users_table.delete().where(db.users_table.c.sleeper_user_id=='partner'))
            if recreate:
                conn.execute(db.users_table.insert().values(sleeper_user_id='partner',verified_via='sleeper',
                    created_at='2026-11-06T13:00:00+00:00',verified_at='2026-11-06T13:00:00+00:00'))
        return frozen
    sid=oc.start_session(user_id='account',league_user_id='seat',league_id='league')['session']['session_id']
    try:oc.build_session(session_id=sid,capture=capture)
    except db.AccountGone:pass
    assert db.load_grading_cards(sid)==[]
    row=db.load_grading_session(sid)
    if row is not None:assert 'erased-private-board-must-not-reappear' not in row['source_json']


def test_registered_participant_incarnations_allow_unchanged_private_capture(engine):
    from backend.tests.test_outlook_calibration_persistence import NOW
    with engine.begin() as conn:
        conn.execute(db.users_table.insert().values(sleeper_user_id='partner', verified_via='sleeper', created_at=NOW))
    frozen, _ = frozen_factory()
    frozen.source.update(registered_participants=['account', 'partner'],
        registered_participant_revisions={'account': NOW, 'partner': NOW})
    sid = oc.start_session(user_id='account', league_user_id='seat', league_id='league')['session']['session_id']
    oc.build_session(session_id=sid, capture=lambda **kw: frozen)
    assert db.load_grading_session(sid)['status'] == 'open'
    assert len(db.load_grading_cards(sid)) == 21
