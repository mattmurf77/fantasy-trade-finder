from copy import deepcopy
import pytest
from backend.league_projections.provider import capture,API
from backend.league_projections.core import Unavailable
from backend.tests.test_league_projection_simulation import config


def world():
    league={'league_id':'123','name':'Synthetic','sport':'nfl','season_type':'regular','season':'2026','total_rosters':2,'settings':{'playoff_week_start':3,'playoff_teams':1},'roster_positions':['WR'],'scoring_settings':{'rec':1}}
    rosters=[{'roster_id':i,'league_id':'123','owner_id':'me' if i==1 else 'other','players':[f'p{i}'],'reserve':[],'taxi':[],
        'settings':{'wins':1 if i==1 else 0,'losses':0 if i==1 else 1,'ties':0,'fpts':10 if i==1 else 5,'fpts_against':5 if i==1 else 10,'ppts':10 if i==1 else 5}} for i in (1,2)]
    history=[{'roster_id':i,'matchup_id':1,'points':10 if i==1 else 5,'starters':[f'p{i}'],'starters_points':[10 if i==1 else 5]} for i in (1,2)]
    source={f'{API}/state/nfl':{'season':'2026','season_type':'regular','week':2},f'{API}/league/123':league,f'{API}/league/123/rosters':rosters,
            f'{API}/league/123/matchups/1':history,f'{API}/league/123/matchups/2':[{'roster_id':i,'matchup_id':1} for i in (1,2)],
            f'{API}/players/nfl':{f'p{i}':{'fantasy_positions':['WR']} for i in (1,2)},f'{API}/league/123/traded_picks':[]}
    class Feed:
        def weeks(self,season,weeks,player_ids):
            return {'source':'synthetic','captured_at':'2026-11-01T00:00:00+00:00','weeks':{'2':{f'p{i}':{'kickoff_at':'2026-11-08T18:00:00+00:00','availability':1,'stats':{'rec':10 if i==1 else 5},'supported_keys':['rec']} for i in (1,2)}}}
    return source,Feed()

def run(source,feed):return capture('123','me',config(),lambda url:deepcopy(source[url]),feed=feed,captured_at='2026-11-01T00:00:00+00:00',clock=lambda:'2026-11-01T00:00:01+00:00')

def test_complete_synthetic_provider_snapshot_preserves_official_totals():
    source,feed=world();result=run(source,feed)
    assert [t['points_for'] for t in result['teams']]==['10','5']
    assert [t['maxpf'] for t in result['teams']]==['10','5']
    assert result['weeks'][0]['games']==[[1,2]]


def test_mismatched_raw_league_identity_is_not_relabeled_as_requested_league():
    source,feed=world();source[f'{API}/league/123']['league_id']='456'
    with pytest.raises(Unavailable):run(source,feed)


def test_incomplete_declared_roster_count_is_not_silently_accepted():
    source,feed=world();source[f'{API}/league/123']['total_rosters']=3
    with pytest.raises(Unavailable):run(source,feed)


def test_incomplete_stat_is_not_zero_filled():
    source,feed=world();source[f'{API}/league/123']['scoring_settings']['rec_yd']=.1
    with pytest.raises(Unavailable) as error:run(source,feed)
    assert error.value.reason=='unsupported_scoring'


def test_missing_occupied_idp_history_cannot_silently_bias_bye_replacement_mean():
    source,_=world()
    source[f'{API}/state/nfl']['week']=3
    source[f'{API}/league/123']['settings']['playoff_week_start']=4
    source[f'{API}/league/123']['roster_positions']=['DL']
    source[f'{API}/players/nfl']={f'p{i}':{'fantasy_positions':['DL']} for i in (1,2)}
    source[f'{API}/league/123/matchups/2']=deepcopy(source[f'{API}/league/123/matchups/1'])
    for row in source[f'{API}/league/123/matchups/2']:row.pop('starters_points')
    source[f'{API}/league/123/matchups/3']=[{'roster_id':i,'matchup_id':1} for i in (1,2)]
    for row in source[f'{API}/league/123/rosters']:
        for key in ('wins','losses','fpts','fpts_against','ppts'):row['settings'][key]*=2
    class ByeFeed:
        def weeks(self,*args):return {'source':'synthetic','captured_at':'2026-11-01T00:00:00+00:00','weeks':{'3':{f'p{i}':{'bye':True,'bye_evidence':'synthetic authoritative schedule'} for i in (1,2)}}}
    with pytest.raises(Unavailable):run(source,ByeFeed())


def test_policy_excluded_reserve_needs_no_unused_projection_but_remains_visible():
    source,feed=world()
    source[f'{API}/league/123/rosters'][0]['players'].append('reserve')
    source[f'{API}/league/123/rosters'][0]['reserve']=['reserve']
    source[f'{API}/players/nfl']['reserve']={'fantasy_positions':['WR']}
    cfg=config();cfg['ir_maxpf']='exclude'
    result=capture('123','me',cfg,lambda url:deepcopy(source[url]),feed=feed,captured_at='2026-11-01T00:00:00+00:00',clock=lambda:'2026-11-01T00:00:01+00:00')
    assert 'reserve' in result['teams'][0]['roster']['reserve']
    assert any(p['player_id']=='reserve' for p in result['weeks'][0]['teams']['1']['exclusions'])


def test_capture_crossing_kickoff_rejects_unlocked_pregame_snapshot():
    source,feed=world()
    with pytest.raises(Unavailable) as error:
        capture('123','me',config(),lambda url:deepcopy(source[url]),feed=feed,
                captured_at='2026-11-08T17:59:59+00:00',clock=lambda:'2026-11-08T18:00:01+00:00')
    assert error.value.reason=='game_started_during_capture'


def test_idp_mean_counts_occupied_zero_and_hypothetical_never_enters_maxpf():
    source,_=world();source[f'{API}/league/123']['roster_positions']=['DL']
    source[f'{API}/players/nfl']={f'p{i}':{'fantasy_positions':['DL']} for i in (1,2)}
    for i,row in enumerate(source[f'{API}/league/123/matchups/1']):row.update(points=0 if i==0 else 10,starters_points=[0 if i==0 else 10])
    for i,row in enumerate(source[f'{API}/league/123/rosters']):
        row['settings'].update(wins=0 if i==0 else 1,losses=1 if i==0 else 0,fpts=0 if i==0 else 10,fpts_against=10 if i==0 else 0,ppts=0 if i==0 else 10)
    class ByeFeed:
        def weeks(self,*args):return {'source':'synthetic','captured_at':'2026-11-01T00:00:00+00:00','weeks':{'2':{f'p{i}':{'bye':True,'bye_evidence':'verified synthetic schedule'} for i in (1,2)}}}
    result=run(source,ByeFeed())
    for detail in result['weeks'][0]['teams'].values():
        assert detail['replacement_means']['DL']=='5'
        assert detail['actual']['points']=='5'
        assert detail['maxpf']['points']=='0'
        assert detail['maxpf_dominates_actual'] is False
    assert [t['maxpf'] for t in result['teams']]==['0','10']


def test_removed_coowner_cannot_borrow_canonical_owner_seat():
    source,feed=world()
    with pytest.raises(PermissionError):
        capture('123','me',config(),lambda url:deepcopy(source[url]),feed=feed,viewer_user_id='removed',
                captured_at='2026-11-01T00:00:00+00:00',clock=lambda:'2026-11-01T00:00:01+00:00')
    source[f'{API}/league/123/rosters'][0]['co_owners']=['current']
    result=capture('123','me',config(),lambda url:deepcopy(source[url]),feed=feed,viewer_user_id='current',
                captured_at='2026-11-01T00:00:00+00:00',clock=lambda:'2026-11-01T00:00:01+00:00')
    assert result['league_id']=='123'
