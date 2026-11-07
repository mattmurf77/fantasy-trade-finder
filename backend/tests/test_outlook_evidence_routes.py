"""Independent v2/v3 prepared-inventory currentness and rollout checks."""
import copy,json
import pytest
from backend import database as db,server,trade_service as ts,bakeoff_runner as bo
from backend.tests.test_owner_generator_routes import harness,owner_harness,rows,context_for,ME,LEAGUE,TOKEN
from backend.tests.test_owner_only_routes import exclusive,large_exclusive
from backend.tests.test_prepared_trade_runtime import prepared,adopt

FLAG='owner_outlook_evidence_enabled'

@pytest.fixture(params=[0.,1.])
def before_version(large_exclusive,request):
    ts._cfg[FLAG]=request.param
    return request.param

@pytest.fixture
def transition_prepared(before_version,prepared):
    return before_version,prepared

def test_prepared_rejects_version_change_both_directions(transition_prepared,monkeypatch):
    before,fixture=transition_prepared
    expected='owner-v2-bilateral-3' if before else 'owner-v2-bilateral-2'
    assert bo.owner_version()==expected
    original=copy.deepcopy(fixture[1]['prepared_bundle'])
    ts._cfg[FLAG]=1.-before
    handled,job=adopt(fixture,monkeypatch)
    assert not handled and not job['cards']
    assert not rows(fixture[0][1],db.deck_impressions_table)
    assert fixture[1]['prepared_bundle']==original

def test_prepared_same_version_adopts_and_preserves_proof(transition_prepared,monkeypatch):
    before,fixture=transition_prepared
    handled,job=adopt(fixture,monkeypatch)
    assert handled and job['status']=='complete'
    assert job['cards']
    version='owner-v2-bilateral-3' if before else 'owner-v2-bilateral-2'
    assert {c['generator_version'] for c in job['cards']}=={version}

def test_default_off_dark_hash_and_proof_identity(owner_harness):
    assert ts._DEFAULT_CFG[FLAG]==0.
    ts._cfg.update(owner_bilateral_enabled=1.,owner_bilateral_revision_enabled=1.)
    ts._cfg[FLAG]=0.
    context=context_for(owner_harness)
    original=server._owner_selected_assignment(context,'fair_packages',serve=True)['request_hash']
    context['config'].pop(FLAG,None)
    assert server._owner_selected_assignment(context,'fair_packages',serve=True)['request_hash']==original
    signature=server._trade_safety_signature()
    ts._cfg[FLAG]=1.
    assert server._trade_safety_signature()!=signature
    context['config'][FLAG]=1.
    assert bo.owner_version(context['config'])=='owner-v2-bilateral-3'
    assert server._owner_selected_assignment(context,'fair_packages',serve=True)['request_hash']!=original

def test_old_cards_not_relabelled_current_either_way(owner_harness):
    ts._cfg.update(owner_bilateral_enabled=1.,owner_bilateral_revision_enabled=1.)
    for enabled in [0.,1.]:
        ts._cfg[FLAG]=enabled;context=context_for(owner_harness)
        cards,_=bo.owner_generator(context['config'])(**context)
        assert cards
        assert server._owner_cards_valid(cards,context)
        snapshots=[c.owner_evaluation.snapshot_json for c in cards]
        context['config'][FLAG]=1.-enabled
        assert server._owner_cards_valid(cards,context)==[]
        assert [c.owner_evaluation.snapshot_json for c in cards]==snapshots


def test_explicit_age_channel_is_hashed_once_and_projected_per_offer(owner_harness):
    from backend.trade_input_evidence import PoolInputEvidence
    from backend.trade_gen_outlook_evidence import INPUT_VERSION
    ts._cfg.update(owner_bilateral_enabled=1.,owner_bilateral_revision_enabled=1.,
                   owner_outlook_evidence_enabled=1.)
    context=context_for(owner_harness)
    assert context['input_evidence']['schema_version']==INPUT_VERSION
    assignment=server._owner_selected_assignment(context,'fair_packages',serve=True)
    assert 'input_evidence' not in assignment['input']
    assert assignment['input_evidence']['used_in_model'] is True
    original=assignment['request_hash']
    any_id=next(iter(context['players']))
    context['input_evidence']['age'][any_id]['age']=29
    assert server._owner_selected_assignment(context,'fair_packages',serve=True)['request_hash']!=original
    cards,_=bo.owner_generator(context['config'])(**context)
    assert cards
    for card in cards:
        captured=server._owner_request_snapshot(assignment,card)
        exact=set(card.give_player_ids+card.receive_player_ids)
        assert set(captured['input_evidence']['age'])==exact
        assert 'input_evidence' not in captured['input']
        assert set(card.owner_evaluation.as_dict()['input_evidence']['age'])==exact


def test_v3_selected_route_serves_new_identity_without_private_fields(owner_harness):
    from backend.tests.test_owner_generator_routes import post
    ts._cfg.update(owner_bilateral_enabled=1.,owner_bilateral_revision_enabled=1.,
                   owner_outlook_evidence_enabled=1.,bakeoff_owner_only=1.)
    client,engine,*_=owner_harness
    response=post(client)
    assert response.status_code==200 and response.json['ideas']
    assert {card['generator_version'] for card in response.json['ideas']}=={'owner-v2-bilateral-3'}
    for private in ('window_evidence','qb_roster_context','input_evidence','counterparty_preference'):
        assert private not in json.dumps(response.json)
    impressions=rows(engine,db.deck_impressions_table)
    assert {json.loads(row['valuation_json'])['generator_version'] for row in impressions}=={'owner-v2-bilateral-3'}
