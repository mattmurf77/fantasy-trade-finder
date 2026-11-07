from decimal import Decimal
import random
import pytest
from backend.league_projections.core import optimize,idp_bye_fill,SLOTS,Unavailable


def oracle(slots,players,empty_policy):
    best=None
    def visit(i,used,total,occupied):
        nonlocal best
        if i==len(slots):
            key=(occupied,total) if empty_policy=='fill_available' else (total,)
            if best is None or key>best:best=key
            return
        visit(i+1,used,total,occupied)
        for j,p in enumerate(players):
            if j not in used and set(p['positions'])&SLOTS[slots[i]]:
                points=Decimal(str(p.get('slot_points',{}).get(slots[i],p['points'])))
                visit(i+1,used|{j},total+points,occupied+1)
    visit(0,set(),Decimal(0),0)
    return best

@pytest.mark.parametrize('policy',['allow','fill_available'])
def test_small_dual_position_negative_assignments_match_exhaustive_oracle(policy):
    rng=random.Random(713)
    for case in range(100):
        slots=rng.choices(['RB','WR','FLEX','SUPER_FLEX','DL','DB','IDP_FLEX'],k=rng.randint(1,4))
        players=[{'player_id':str(i),'positions':rng.sample(['QB','RB','WR','TE','DL','LB','DB'],rng.randint(1,2)),'points':str(rng.randint(-15,25)/2)} for i in range(rng.randint(0,6))]
        actual=optimize(slots,players,empty_policy=policy)
        key=(len(slots)-len(actual['gaps']),Decimal(actual['points'])) if policy=='fill_available' else (Decimal(actual['points']),)
        assert key==oracle(slots,players,policy),(case,slots,players,actual)
        ids=[row['player']['player_id'] for row in actual['lineup'] if row['player']]
        assert len(set(ids))==len(ids)
        assert all(set(row['player']['positions'])&SLOTS[row['slot']] for row in actual['lineup'] if row['player'])

def test_slot_specific_negative_points_obey_explicit_fill_available_policy():
    player={'player_id':'virtual','positions':['DL'],'points':'0','slot_points':{'DL':'-100'}}
    actual=optimize(['DL'],[player],empty_policy='fill_available')
    assert actual['gaps']==[]
    assert Decimal(actual['points'])==-100

def test_negative_idp_bye_average_not_silently_dropped_under_fill_policy():
    actual=idp_bye_fill(['DL'],[],[{'player_id':'bye','positions':['DL']}],{'DL':'-5'},empty_policy='fill_available')
    assert actual['gaps']==[]
    assert Decimal(actual['points'])==-5

def test_locked_actual_and_bench_are_not_retroactively_reoptimized():
    players=[{'player_id':'locked','positions':['WR'],'points':'20','actual_points':'-2'},
             {'player_id':'bench','positions':['WR'],'points':'40','actual_points':'40'},
             {'player_id':'future','positions':['WR'],'points':'10'}]
    actual=optimize(['WR','FLEX'],players,empty_policy='fill_available',locked={0:'locked'},locked_bench=['bench'])
    assert [r['player']['player_id'] for r in actual['lineup']]==['locked','future']
    assert Decimal(actual['points'])==8
    hindsight=optimize(['WR','FLEX'],players,empty_policy='fill_available',locked={0:'locked'},locked_bench=['bench'],hindsight=True)
    assert 'bench' in [r['player']['player_id'] for r in hindsight['lineup']]


def test_idp_bye_counterfactual_can_reassign_healthy_dual_position_cover():
    healthy=[{'player_id':'healthy','positions':['DL','DB'],'points':'10'}]
    result=idp_bye_fill(['DL','DB'],healthy,[{'player_id':'bye-dl','positions':['DL']}],{'DL':'5','DB':'7'},empty_policy='fill_available')
    assert result['gaps']==[]
    assert [r['player']['player_id'] for r in result['lineup']]==['hypothetical:bye-dl','healthy']


def test_optional_empty_negative_healthy_idp_cannot_unlock_higher_fa_upgrade():
    healthy=[{'player_id':'healthy','positions':['DL'],'points':'-1'}]
    result=idp_bye_fill(['DL'],healthy,[{'player_id':'bye-dl','positions':['DL']}],{'DL':'10'},empty_policy='allow')
    assert not any(r['player'] and r['player'].get('hypothetical') for r in result['lineup'])


def test_unrelated_dl_bye_cannot_fill_injury_only_db_gap():
    result=idp_bye_fill(['DL','DB'],[],[{'player_id':'bye-dl','positions':['DL']}],{'DL':'5','DB':'7'},empty_policy='fill_available')
    assert result['lineup'][0]['player']['hypothetical']
    assert result['lineup'][1]['player'] is None


def test_healthy_cover_prevents_high_average_virtual_upgrade():
    result=idp_bye_fill(['DL'],[{'player_id':'healthy','positions':['DL'],'points':'1'}],[{'player_id':'bye-dl','positions':['DL']}],{'DL':'100'},empty_policy='fill_available')
    assert result['lineup'][0]['player']['player_id']=='healthy'


def test_hindsight_uses_realized_points_instead_of_obsolete_pregame_projection():
    players=[{'player_id':'pregame-favorite','positions':['WR'],'points':'30','actual_points':'-5'},
             {'player_id':'bench-winner','positions':['WR'],'points':'1','actual_points':'20'}]
    result=optimize(['WR'],players,empty_policy='fill_available',hindsight=True)
    assert result['lineup'][0]['player']['player_id']=='bench-winner'
    assert Decimal(result['points'])==20
