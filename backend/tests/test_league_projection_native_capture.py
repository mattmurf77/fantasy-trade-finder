from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import pytest
from backend.league_projections.provider import API,capture
from backend.league_projections.simulation import simulate
from backend.league_projections.core import Unavailable
from backend.tests.test_league_projection_provider import world
from backend.tests.test_league_projection_simulation import config


def native_world():
 source,_=world();league=source[f'{API}/league/123'];league['settings']['playoff_week_start']=4
 league['roster_positions']=['SUPER_FLEX']
 league['scoring_settings']={'pass_yd':.04,'pass_td':4,'pass_int':-2,'rush_yd':.1,'rush_td':6,'rec':1,'rec_yd':.1,'rec_td':6,'bonus_rec_te':.5,'pts_allow_0':10,'fgm':3}
 source[f'{API}/state/nfl']['week']=3
 source[f'{API}/league/123/matchups/2']=deepcopy(source[f'{API}/league/123/matchups/1'])
 for row in source[f'{API}/league/123/matchups/2']:row.update(points=5 if row['roster_id']==1 else 10,starters_points=[5 if row['roster_id']==1 else 10])
 source[f'{API}/league/123/matchups/3']=[{'roster_id':i,'matchup_id':1} for i in (1,2)]
 for row in source[f'{API}/league/123/rosters']:row['settings'].update(wins=1,losses=1,fpts=15,fpts_against=15,ppts=20)
 source[f'{API}/players/nfl']={f'p{i}':{'fantasy_positions':[pos],'position':pos,'team':f'T{i-1}'} for i,pos in ((1,'QB'),(2,'TE'))}
 schedule=[{'game_id':f'w{w}g{j}','week':w,'home':f'T{2*j}','away':f'T{2*j+1}'} for w in range(1,18) for j in range(16)]
 scores=[{'game_id':f'w3g{j}','season':'2026','week':3,'season_type':'regular','sport':'nfl','status':'pre_game','start_time':int(datetime.fromisoformat('2026-11-15T18:00:00+00:00').timestamp()*1000),'metadata':{'home_team':f'T{2*j}','away_team':f'T{2*j+1}','status':'scheduled','has_started':False,'is_in_progress':False,'is_over':False,'canceled':False}} for j in range(16)]
 rows=[{'player_id':f'p{i}','season':'2026','week':3,'season_type':'regular','category':'proj','company':'rotowire','game_id':'w3g0','team':f'T{i-1}','opponent':f'T{2-i}', 'stats':stats} for i,stats in ((1,{'gp':1,'pass_att':20,'pass_yd':100,'pass_td':1,'pts_std':8,'pts_half_ppr':8,'pts_ppr':8}),(2,{'gp':1,'rec':3,'rec_yd':30,'pts_std':3,'pts_half_ppr':4.5,'pts_ppr':6}))]
 source.update({'https://api.sleeper.app/schedule/nfl/regular/2026':schedule,'https://api.sleeper.app/scores/nfl/regular/2026/3':scores,'https://api.sleeper.app/projections/nfl/2026/3?season_type=regular':rows})
 cfg=config();cfg.update(scoring_contract='sleeper_sparse_offense_v1',availability_scenario='conditional_provider_forecast')
 return source,cfg

def run(source,cfg):return capture('123','me',cfg,lambda url:deepcopy(source[url]),captured_at='2026-11-01T00:00:00+00:00',clock=lambda:'2026-11-01T00:00:01+00:00')


def test_actual_native_feed_capture_and_joint_engine_support_mixed_tep_scoring():
 source,cfg=native_world();snapshot=run(source,cfg)
 detail=snapshot['weeks'][0]['teams']
 assert Decimal(detail['1']['actual']['points'])==Decimal('8')
 assert Decimal(detail['2']['actual']['points'])==Decimal('7.5')
 assert snapshot['coverage']['model_assumed_player_fields']>0
 assert set(snapshot['coverage']['inactive_slot_coefficients'])=={'pts_allow_0','fgm'}
 assert all(entry['input']['scoring_contract']=='sleeper_sparse_offense_v1' for entry in snapshot['player_week_inputs'])
 result=simulate(snapshot,cfg)
 assert result['status']=='complete' and sum(t['playoff_probability'] for t in result['teams'])==1


@pytest.mark.parametrize('mutation',[lambda s:s['https://api.sleeper.app/projections/nfl/2026/3?season_type=regular'].pop(),lambda s:s[f'{API}/league/123']['roster_positions'].append('K'),lambda s:s[f'{API}/league/123']['scoring_settings'].update(idp_def_td=6)])
def test_actual_capture_never_silently_drops_missing_rows_active_kicker_or_rare_idp(mutation):
 source,cfg=native_world();mutation(source)
 with pytest.raises(Unavailable):run(source,cfg)
