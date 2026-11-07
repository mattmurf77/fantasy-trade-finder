"""Disjoint fixed holdings preserve legality, capacity and both-arm proof identity."""
import copy
from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from backend import calibration_fixed_lineup as fixed
from backend.blind_grading import GradingError
from backend.trade_roster import Asset, Context, Rules, Team, evaluate


def world(slots=('RB','K'), capacity=3):
    ctx = Context('a', {'a':Team('a', ('sell','bench','ka')),
        'b':Team('b', ('buy','backup','kb'))}, {
        pid: Asset(pid, frozenset({'RB'}), 100) for pid in ('sell','bench','buy','backup')},
        Rules(tuple(slots), 'observed', capacity))
    metadata = {pid:{'player_id':pid,'fantasy_positions':['K'],'active':True} for pid in ('ka','kb')}
    return ctx, metadata


def check(ctx, give=('sell',), receive=('buy',)):
    return evaluate(viewer=ctx.teams['a'], partner=ctx.teams['b'],
        give=give,receive=receive,assets=ctx.assets,rules=ctx.rules)


def test_fixed_asset_stays_capacity_only_and_proof_has_full_slots():
    ctx,metadata=world()
    # Named sabotage control: omitting the projection reproduces the original
    # all-cards unsupported-lineup failure before any price/quality judgment.
    assert 'unsupported_or_missing_lineup' in check(ctx)['unknowns']
    proof=fixed.prepare(ctx,metadata)
    assert ctx.rules.slots==('RB',) and ctx.rules.capacity==3
    assert proof['original_slots']==['RB','K']
    assert proof['teams']['a']['known_available_assignment']==[{'slot':'K','player_id':'ka'}]
    asset=ctx.assets['ka']
    assert not asset.positions and not asset.startable and not asset.available and asset.value==0
    result=check(ctx);assert result['eligible']
    assert result['teams']['a']['before']['active_count']==3
    card=N(target_user_id='b',roster_evaluation=result)
    fixed.annotate([card],proof,'a')
    assert result['fixed_lineup']['fixed_market_values']=='unknown_not_zero'


@pytest.mark.parametrize('slots,capacity', [
    (['QB','RB','RB','WR','WR','TE','FLEX','K','DL','DL','LB','LB','DB','DB','IDP_FLEX'],36),
    (['QB','RB','RB','WR','WR','TE','FLEX','FLEX','DEF'],19)])
def test_observed_league_shapes_preserve_complete_capacity(slots,capacity):
    ctx,metadata=world(slots,capacity)
    proof=fixed.prepare(ctx,metadata)
    assert proof['original_slots']==slots
    assert ctx.rules.capacity==capacity
    assert len(ctx.rules.slots)+len(proof['fixed_slots'])==len(slots)
    assert check(ctx)['eligible']  # existing identical deficits never worsen


def test_fixed_active_and_reserve_costs_in_quantity_unbalanced_trade():
    ctx,metadata=world();fixed.prepare(ctx,metadata)
    ctx.assets['extra']=Asset('extra',frozenset({'WR'}),50)
    ctx.teams['b']=replace(ctx.teams['b'],roster=ctx.teams['b'].roster+('extra',))
    assert 'cuts_required' in check(ctx,receive=('buy','extra'))['teams']['a']['blockers']
    ctx.teams['a']=replace(ctx.teams['a'],inactive=frozenset({'ka'}))
    assert 'cuts_required' not in check(ctx,receive=('buy','extra'))['teams']['a']['blockers']


def test_fixed_matching_is_exact_for_overlapping_defensive_slots():
    candidates={'dual':frozenset({'DL','LB'}),'dl':frozenset({'DL'}),'db':frozenset({'DB'})}
    result=fixed._matching(('DL','LB','IDP_FLEX'),candidates)
    assert len({r['player_id'] for r in result if r['player_id']})==3
    assert result[1]['player_id']=='dual'


@pytest.mark.parametrize('positions',[['WR','DB'],['RB','K'],['WR','CB']])
def test_cross_domain_eligibility_never_projected_away(positions):
    ctx,metadata=world();metadata['ka']['fantasy_positions']=positions
    with pytest.raises(GradingError,match='provider_cross_domain_eligibility'):fixed.prepare(ctx,metadata)


@pytest.mark.parametrize('row',[{}, {'fantasy_positions':['OTHER']},
    {'fantasy_positions':['K'],'player_id':'mismatched'}])
def test_unknown_fixed_asset_stays_unresolved(row):
    ctx,metadata=world();metadata['ka']=row
    fixed.prepare(ctx,metadata)
    result=check(ctx)
    assert not result['eligible']
    assert 'unresolved_roster_asset' in result['teams']['a']['unknowns']


def test_missing_fixed_availability_reports_uncertainty_but_unchanged_delta():
    ctx,metadata=world();metadata['ka'].pop('active')
    proof=fixed.prepare(ctx,metadata)
    assert proof['teams']['a']['unknown_availability_ids']==['ka']
    assert proof['teams']['a']['known_available_assignment']==[{'slot':'K','player_id':None}]
    assert check(ctx)['eligible']  # no assertion that whole lineup is filled


def test_duplicate_holdings_remain_rejected():
    ctx,metadata=world();ctx.teams['a']=replace(ctx.teams['a'],roster=('sell','bench','ka','ka'))
    fixed.prepare(ctx,metadata)
    assert 'duplicate_roster_asset' in check(ctx)['teams']['a']['unknowns']


@pytest.mark.parametrize('side',['give_player_ids','receive_player_ids'])
def test_fixed_leg_never_enters_either_side(side):
    ctx,metadata=world();proof=fixed.prepare(ctx,metadata)
    card=N(give_player_ids=['sell'],receive_player_ids=['buy']);setattr(card,side,['ka'])
    with pytest.raises(GradingError,match='comparison_fixed_asset_exchange'):fixed.validate_legs([card],proof)


def test_future_cut_plan_refuses_even_if_offer_legs_are_offensive():
    ctx,metadata=world();proof=fixed.prepare(ctx,metadata)
    with pytest.raises(GradingError,match='comparison_cut_plan_unsupported'):
        fixed.validate_legs([N(give_player_ids=['sell'],receive_player_ids=['buy'],cuts=['ka'])],proof)


def test_custom_slot_refuses_before_generating_deck():
    ctx,metadata=world(('RB','CUSTOM'))
    with pytest.raises(GradingError,match='provider_lineup_unsupported'):fixed.prepare(ctx,metadata)


from backend.tests.test_outlook_calibration_adapter import captured
from backend.tests.test_owner_generator_routes import harness,owner_harness,ME,LEAGUE


def test_real_pair_keeps_fixed_ids_outside_generation(captured,monkeypatch):
    from backend import outlook_calibration_adapter as adapter, session_input,server
    old=session_input.resolve_session_input
    metadata=copy.deepcopy(server._load_sleeper_cache())
    def resolve(*args,**kwargs):
        result=old(*args,**kwargs)
        kwargs['raw']['meta']['roster_positions'] += ['K','DL','LB','DB','IDP_FLEX']
        for i,row in enumerate(kwargs['raw']['rosters']):
            for pos in ('K','DL','LB','DB'):
                pid=f'fixed-{i}-{pos}'
                row['players'].append(pid)
                metadata[pid]={'player_id':pid,'fantasy_positions':[pos],'active':True}
            # Raw roster is authoritative for both fixed holdings and capacity.
        return result
    monkeypatch.setattr(session_input,'resolve_session_input',resolve)
    monkeypatch.setattr(server,'_load_sleeper_cache',lambda:metadata)
    frozen=adapter.capture(user_id=ME,league_user_id=ME,league_id=LEAGUE)
    ids=set(frozen.source['fixed_lineup']['assets']);assert ids
    assert not ids & frozen.owner_context['players'].keys()
    for version in adapter.VERSIONS:
        cards,diag=frozen.run_arm(version);assert cards
        for card in cards:
            assert not ids & set(card.give_player_ids+card.receive_player_ids)
            assert card.owner_evaluation.matches(card) and card.roster_evaluation['eligible']
            assert card.roster_evaluation['fixed_lineup']['fixed_slots']==['K','DL','LB','DB','IDP_FLEX']


def test_fixed_holding_cannot_belong_to_two_teams():
    ctx,metadata=world();ctx.teams['b']=replace(ctx.teams['b'],roster=('buy','backup','ka'))
    with pytest.raises(GradingError,match='provider_roster_identity_ambiguous'):fixed.prepare(ctx,metadata)


def test_unknown_nonoffensive_traded_asset_is_not_accepted():
    ctx,metadata=world();proof=fixed.prepare(ctx,metadata)
    ctx.assets['unknown']=Asset('unknown',frozenset({'UNKNOWN'}),100)
    with pytest.raises(GradingError,match='comparison_nonoffensive_exchange'):
        fixed.validate_legs([N(give_player_ids=['unknown'],receive_player_ids=['buy'])],proof,ctx)
