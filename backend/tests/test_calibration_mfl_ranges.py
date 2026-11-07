"""Native ranges are exact legal alternatives, never an unrestricted FLEX guess."""
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace as N
import pytest
from backend.calibration_native_lineup import templates,choose,demands,NativeRules
from backend.calibration_provider_capture import parse_mfl,_mfl_native_ranges
from backend import calibration_fixed_lineup as fixed
from backend.trade_roster import Asset,Team,Context
from backend.blind_grading import GradingError
from backend.tests.test_calibration_provider_parsers import mfl_raw,xwalk

OFF=(('QB',1,2),('RB',2,3),('TE',2,3),('WR',2,4))
DEF=(('CB',2,3),('DE',2,3),('DT',1,3),('LB',2,4),('S',2,3))

def native_raw():
    raw=mfl_raw();league=raw['league']['league']
    league.update(rosterSize='45',injuredReserve='7',taxiSquad='7')
    league['starters']={'count':'20','iop_starters':'9','idp_starters':'11',
        'position':[{'name':p,'limit':f'{lo}-{hi}'} for p,lo,hi in OFF+DEF]}
    for i,pos in enumerate(('DT','DE','LB','CB','S'),10):
        raw['players']['players']['player'].append({'id':str(i),'name':f'Synthetic {pos}','position':pos})
        raw['rosters']['rosters']['franchise'][0]['player'].append({'id':str(i),'status':'ROSTER'})
    return raw


def test_native_20_start_shape_has_exact_partition_families_and_unpriced_fixed_holdings(xwalk):
    snap=parse_mfl(native_raw(),league_id='123',user_id='me',franchise_id='0001',xwalk=xwalk)
    assert len(templates(snap.native_bounds,9))==7
    assert len(templates(snap.fixed_bounds,11))==12
    assert len(snap.slots)==20 and snap.capacity==45
    assert {r['position'] for r in snap.fixed_metadata.values()}=={'DT','DE','LB','CB','S'}
    assert len(snap.rosters[0]['players'])==6
    assert not set(snap.fixed_metadata)&set(snap.positions)

@pytest.mark.parametrize('changes',[{'iop_starters':'10'},{'idp_starters':None},{'count':'21'}])
def test_native_partition_is_required_not_inferred(changes):
    raw=native_raw()['league']['league'];raw['starters'].update(changes)
    with pytest.raises(GradingError):_mfl_native_ranges(raw)


def test_global_cross_domain_variable_counts_do_not_become_fixed_partition():
    raw={'starters':{'count':'2','position':[{'name':'WR','limit':'0-2'},{'name':'K','limit':'0-2'}]}}
    from backend.calibration_provider_capture import _mfl_slots
    with pytest.raises(GradingError):_mfl_slots(raw)


def test_exact_family_refuses_third_qb_formation_and_preserves_native_subset_depth():
    assets=[Asset(f'{p}{i}',frozenset({p}),100) for p,n in [('QB',3),('RB',2),('WR',2),('TE',2)] for i in range(n)]
    selected=choose(OFF,9,assets)
    assert sum(p is not None for p in selected)==8 # unrestricted SF would incorrectly fill9
    assert Counter(next(a for a in assets if a.id==p).positions.__iter__().__next__() for p in selected if p)['QB']==2
    assert demands(OFF,9)['RB+TE+WR'][1]==7


def test_optional_slot_assignment_and_native_depth_change_are_joint():
    bounds=(('QB',0,1),('WR',1,2));rules=NativeRules(('WR','WR'),'observed',5,native_bounds=bounds)
    assets={p:Asset(p,frozenset({pos}),v) for p,pos,v in [('q','QB',500),('w1','WR',100),('w2','WR',90),('w3','WR',80),('other','WR',100)]}
    ctx=Context('a',{'a':Team('a',('q','w1','w2','w3')),'b':Team('b',('other',))},assets,rules)
    card=N(target_user_id='b',give_player_ids=['q'],receive_player_ids=['other'])
    result=ctx.card(card)
    before=result['teams']['a']['before'];after=result['teams']['a']['after']
    assert [r['slot'] for r in before['lineup']]==['QB','WR']
    assert [r['slot'] for r in after['lineup']]==['WR','WR']
    assert before['starter_value']==600 and after['starter_value']==200
    assert 'QB' not in before['coverage'] # minQB0 does not invent a backup obligation
    assert result['teams']['a']['outlook_utility']['components']['lineup_dynasty_proxy']['before']==600


def test_native_fixed_partition_preserves_ir_capacity_and_refuses_fixed_legs(xwalk):
    snap=parse_mfl(native_raw(),league_id='123',user_id='me',franchise_id='0001',xwalk=xwalk)
    ctx=snap.roster_context(viewer_id='me',league=N(members=[]),players={},consensus_value=lambda _:0,
        startable=lambda *_:False,player_metadata=snap.fixed_metadata,availability_fresh=True,viewer_roster=snap.rosters[0]['players'])
    proof=fixed.prepare(ctx,snap.fixed_metadata,fixed_bounds=snap.fixed_bounds)
    assert len(ctx.rules.slots)==9 and ctx.rules.native_bounds==OFF
    assert len(proof['teams']['me']['fixed_ids'])==5
    assert proof['teams']['me']['active_count']==5
    assert not any(r['player_id'] for r in proof['teams']['me']['known_available_assignment']) # health unknown
    with pytest.raises(GradingError):fixed.validate_legs([N(give_player_ids=['mfl-fixed:10'],receive_player_ids=['b'])],proof,ctx)


def test_private_fixed_proof_labels_representative_templates_and_retains_both_bound_families(xwalk):
    snap=parse_mfl(native_raw(),league_id='123',user_id='me',franchise_id='0001',xwalk=xwalk)
    ctx=snap.roster_context(viewer_id='me',league=N(members=[N(user_id='mfl:123.f0002',roster=['b'])]),players={},consensus_value=lambda _:0,
        startable=lambda *_:False,player_metadata=snap.fixed_metadata,availability_fresh=True,viewer_roster=snap.rosters[0]['players'])
    proof=fixed.prepare(ctx,snap.fixed_metadata,fixed_bounds=snap.fixed_bounds)
    card=N(target_user_id='mfl:123.f0002',roster_evaluation={})
    fixed.annotate([card],proof,'me')
    saved=card.roster_evaluation['fixed_lineup']
    assert saved['native_fixed_bounds']==list(DEF)
    assert saved['native_offensive_bounds']==list(OFF)
    assert saved['slots_role']=='representative_templates_not_complete_native_rules'
