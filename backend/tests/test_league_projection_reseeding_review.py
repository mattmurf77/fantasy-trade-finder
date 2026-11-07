"""Independent capture/engine tests for later-round reseeding admission."""
from copy import deepcopy
import pytest
from backend.league_projections import provider,simulation
from backend.league_projections.core import Unavailable
from backend.tests.test_league_projection_provider import world,run
from backend.tests.test_league_projection_simulation import config
API=provider.API

@pytest.mark.parametrize('value',[False,True,'0','1',0.0,1.0,2,-1,None,[],{}])
def test_only_exact_native_integer_enum_is_accepted(value):
    source,feed=world();source[f'{API}/league/123']['settings']['playoff_seed_type']=value
    with pytest.raises(Unavailable) as exc:run(source,feed)
    assert exc.value.reason=='unsupported_playoff_reseeding_policy'

@pytest.mark.parametrize('key,value',[('divisions',2),('league_average_match',1),('best_ball',1),('playoff_round_type',1),('playoff_type',2),('start_week',2)])
def test_reseeding_never_disables_other_league_guards(key,value):
    source,feed=world();source[f'{API}/league/123']['settings'].update(playoff_seed_type=1,**{key:value})
    with pytest.raises(Unavailable):run(source,feed)


def test_manual_bracket_remains_unavailable_under_reseeding():
    source,feed=world();source[f'{API}/league/123']['settings']['playoff_seed_type']=1
    source[f'{API}/league/123']['bracket_overrides_id']='synthetic-manual'
    with pytest.raises(Unavailable) as exc:run(source,feed)
    assert exc.value.reason=='unsupported_divisions_median_bestball_or_manual_seeding'


def eight_team_world(seed_type):
    source,_=world();league=source[f'{API}/league/123']
    league['total_rosters']=8;league['settings'].update(playoff_seed_type=seed_type,playoff_week_start=4,playoff_teams=6)
    source[f'{API}/state/nfl']['week']=3
    rows=[]
    for i in range(1,9):
        odd=i%2==1
        rows.append({'roster_id':i,'league_id':'123','owner_id':'me' if i==1 else f'owner{i}','players':[f'p{i}'],'reserve':[],'taxi':[],
        'settings':{'wins':2 if odd else 0,'losses':0 if odd else 2,'ties':0,'fpts':22 if odd else 13,'fpts_against':13 if odd else 22,'ppts':24 if odd else 15}})
    source[f'{API}/league/123/rosters']=rows
    for w in (1,2):
        source[f'{API}/league/123/matchups/{w}']=[{'roster_id':i,'matchup_id':(i+1)//2,'points':(10 if i%2 else 5)+(0 if w==1 else (2 if i%2 else 3)), 'starters':[f'p{i}'],'starters_points':[(10 if i%2 else 5)+(0 if w==1 else (2 if i%2 else 3))]} for i in range(1,9)]
    source[f'{API}/league/123/matchups/3']=[{'roster_id':i,'matchup_id':(i+1)//2} for i in range(1,9)]
    source[f'{API}/players/nfl']={f'p{i}':{'fantasy_positions':['WR']} for i in range(1,9)}
    source[f'{API}/league/123/traded_picks']=[{'season':'2027','round':1,'roster_id':8,'owner_id':1}]
    class Feed:
        def weeks(self,*args):return {'source':'synthetic','captured_at':'2026-11-01T00:00:00+00:00','weeks':{'3':{f'p{i}':{'kickoff_at':'2026-11-08T18:00:00+00:00','availability':1,'stats':{'rec':i},'supported_keys':['rec']} for i in range(1,9)}}}
    return source,Feed()


def test_regular_qualification_byes_and_nonplayoff_pick_worlds_are_exactly_equal():
    outputs=[];snapshots=[]
    for value in (0,1):
        source,feed=eight_team_world(value);snap=run(source,feed);snapshots.append(snap)
        outputs.append(simulation.simulate(snap,config()))
    a,b=outputs
    assert snapshots[0]['league_revision']!=snapshots[1]['league_revision']
    assert a['snapshot_hash']!=b['snapshot_hash']
    assert a['teams']==b['teams']
    assert a['playoff_spots']==b['playoff_spots']==6
    assert a['playoff_byes']==b['playoff_byes']==2
    assert sum(t['playoff_probability'] for t in a['teams'])==pytest.approx(6)
    assert sum(t['bye_probability'] for t in a['teams'])==pytest.approx(2)
    assert sum(t['owner_expected_nonplayoff_picks'] for t in a['teams'])==pytest.approx(2)
    assert snapshots[1]['coverage']['native_playoff_seed_type']==1
    assert snapshots[1]['coverage']['postseason_rounds_simulated'] is False


def test_mid_capture_reseeding_setting_change_is_still_stale():
    source,feed=world();source[f'{API}/league/123']['settings']['playoff_seed_type']=0
    calls=0
    def fetch(url):
        nonlocal calls
        data=deepcopy(source[url])
        if url==f'{API}/league/123':
            calls+=1
            if calls==2:data['settings']['playoff_seed_type']=1
        return data
    with pytest.raises(Unavailable) as exc:
        provider.capture('123','me',config(),fetch,feed=feed,captured_at='2026-11-01T00:00:00+00:00',clock=lambda:'2026-11-01T00:00:01+00:00')
    assert exc.value.reason=='inputs_changed_during_capture'




def test_absent_native_setting_keeps_existing_default():
    source,feed=world();snap=run(source,feed)
    assert snap['coverage']['native_playoff_seed_type']==0
    assert snap['coverage']['postseason_rounds_simulated'] is False
