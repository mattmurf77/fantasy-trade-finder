"""Best-available estimates distinguish data absence from a real numeric zero."""
from copy import deepcopy
from decimal import Decimal
import pytest
from backend.league_projections import provider, simulation
from backend.league_projections.core import Unavailable
from backend.league_projections.scoring import best_available, BEST_AVAILABLE
from backend.tests.test_league_projection_native_capture import native_world, run


FEED='https://api.sleeper.app/projections/nfl/2026/3?season_type=regular'


def world():
    source,cfg=native_world();cfg['scoring_contract']=BEST_AVAILABLE
    return source,cfg


def add_priced_teammate(source):
    """Roster 2 gains p5, a WR projected for 4 points, beside its TE p2."""
    source[f'{provider.API}/league/123/rosters'][1]['players'].append('p5')
    source[f'{provider.API}/players/nfl']['p5']={'fantasy_positions':['WR'],'position':'WR','team':'T1'}
    row=deepcopy(next(r for r in source[FEED] if r['player_id']=='p2'));row.update(player_id='p5')
    row['stats']={'gp':1,'rec':2,'rec_yd':20,'pts_std':2,'pts_half_ppr':3,'pts_ppr':4}
    source[FEED].append(row)


def drop_projection(source,pid):
    source[FEED]=[row for row in source[FEED] if row['player_id']!=pid]


def assert_missing_weekly_projections(source,cfg,lanes):
    """The run stops; completed team scoring never stands in for a projection."""
    with pytest.raises(Unavailable) as error:run(source,cfg)
    assert error.value.reason=='missing_weekly_projections'
    assert error.value.state=='incomplete_projections'
    assert error.value.details=={'week':3,'lanes':lanes}


@pytest.mark.parametrize('raw',[None,{}, {'stats':{}},{'stats':{'gp':1}}])
def test_missing_rows_and_placeholders_never_acquire_inapplicable_zero_estimates(raw):
    result=best_available(raw,{'bonus_rec_te':1,'idp_tkl_solo':1},{'idp_tkl_solo'},positions=['DB'],primary_position='DB')
    assert result['known_points_subtotal'] is None and result['stats']=={}
    assert result['projection_status']=='unpriced'


def test_explicit_zero_and_missing_negative_events_are_distinct():
    result=best_available({'stats':{'rec':0}}, {'rec':1,'fum_lost':-2}, {'rec','fum_lost'},positions=['WR'],primary_position='WR')
    assert result['known_points_subtotal']=='0'
    assert result['missing_negative_keys']==['fum_lost']
    assert result['stat_provenance']['rec']['basis']=='direct'
    assert result['stat_provenance']['fum_lost']['value'] is None
    assert result['projection_status']=='partial'


def test_direct_idp_kicker_negative_contributions_use_custom_coefficients():
    result=best_available({'stats':{'idp_tkl_solo':5,'fgm_50p':.5,'fum_lost':2}},
        {'idp_tkl_solo':1.25,'fgm_50p':6,'fum_lost':-4,'idp_blk_kick':5},
        {'idp_tkl_solo','fgm_50p','fum_lost'},positions=['DL'],primary_position='DE')
    assert Decimal(result['known_points_subtotal'])==Decimal('1.25')
    assert result['missing_keys']==['idp_blk_kick']


def test_missing_player_does_not_block_known_team_and_wholly_unpriced_team_stops_the_run():
    # A missing player beside a priced teammate: both teams keep a number.
    source,cfg=world();add_priced_teammate(source);drop_projection(source,'p2')
    snapshot=run(source,cfg);teams=snapshot['weeks'][0]['teams']
    assert Decimal(teams['1']['modeled_actual_projection'])==8
    assert Decimal(teams['2']['modeled_actual_projection'])==4  # p5 alone; not the 7.5 completed average.
    assert Decimal(teams['2']['modeled_maxpf_projection'])==4
    assert teams['2']['actual']['lineup'][0]['player']['player_id']=='p5'
    coverage=teams['2']['projection_coverage']
    assert [(p['player_id'],p['positions']) for p in coverage['unpriced_players']]==[('p2',['TE'])]
    assert coverage['estimated'] and coverage['complete'] and coverage['missing_actual_slots']==[]
    assert 'fallback' not in coverage and 'fallback_lanes' not in coverage
    assert snapshot['coverage']['estimate_status']=='complete' and snapshot['coverage']['unpriced_player_weeks']==1
    assert 'history_fallback_team_weeks' not in snapshot['coverage']
    assert simulation.simulate(snapshot,cfg)['status']=='complete'
    # The same missing player as the team's only one: no projected lineup, no forecast.
    source,cfg=world();drop_projection(source,'p2')
    assert_missing_weekly_projections(source,cfg,['actual','maxpf'])


def test_missing_custom_events_yield_partial_contributions_not_league_refusal():
    source,cfg=world();source[f'{provider.API}/league/123']['scoring_settings'].update(idp_blk_kick=6,st_ff=-2)
    snapshot=run(source,cfg)
    assert snapshot['coverage']['estimated'] and snapshot['coverage']['partial_player_weeks']==2
    detail=snapshot['weeks'][0]['teams']['1']
    assert Decimal(detail['actual']['points'])==8
    assert detail['projection_coverage']['partial_players'][0]['missing_negative_keys']==['st_ff']
    assert simulation.simulate(snapshot,cfg)['status']=='complete'


def test_unknown_nfl_team_is_unpriced_not_a_bye_or_confirmed_zero():
    source,cfg=world();source[f'{provider.API}/players/nfl']['p2']['team']=None
    # Alone on the roster the player is unknown, so the run stops: a bye or a
    # confirmed zero would have produced a zero-point lineup instead.
    assert_missing_weekly_projections(source,cfg,['actual','maxpf'])
    add_priced_teammate(source)
    snapshot=run(source,cfg);detail=snapshot['weeks'][0]['teams']['2']
    assert detail['projection_coverage']['unpriced_players'][0]['reason']=='unknown_nfl_team'
    assert detail['projection_coverage']['unpriced_players'][0]['positions']==['TE']
    assert not any(p['reason']=='bye' for p in detail['exclusions'])
    assert [r['player']['player_id'] for r in detail['actual']['lineup']]==['p5']
    assert Decimal(detail['modeled_actual_projection'])==4


def test_empty_successful_feed_stops_the_run_without_a_history_number_and_transport_error_propagates(monkeypatch):
    source,cfg=world();key='https://api.sleeper.app/projections/nfl/2026/3?season_type=regular';source[key]=[]
    original=provider.SleeperExperimentalFeed.weeks;states=[]
    def weeks(self,*args):
        result=original(self,*args);states.append(result['coverage']['weekly_feed_states']);return result
    monkeypatch.setattr(provider.SleeperExperimentalFeed,'weeks',weeks)
    # The empty response is still told apart from an outage, but it no longer
    # yields a forecast built from completed team scoring.
    assert_missing_weekly_projections(source,cfg,['actual','maxpf'])
    assert states==[{'3':'empty_response'}]
    def fetch(url):
        if url==key:raise TimeoutError('synthetic outage')
        return deepcopy(source[url])
    with pytest.raises(TimeoutError):
        provider.capture('123','me',cfg,fetch,captured_at='2026-11-01T00:00:00+00:00',clock=lambda:'2026-11-01T00:00:01+00:00')


def test_missing_taxi_forecast_does_not_invent_actual_lineup_projection():
    source,cfg=world();rosters=source[f'{provider.API}/league/123/rosters']
    rosters[1]['taxi']=['p2'];source['https://api.sleeper.app/projections/nfl/2026/3?season_type=regular'].pop()
    # Only the Max PF lane is missing: a taxi player is no part of the actual
    # lineup, so the actual lane is neither reported missing nor invented.
    assert_missing_weekly_projections(source,cfg,['maxpf'])
    # With a priced active player, the unprojected taxi player changes nothing
    # in the actual lineup and leaves no actual slot missing.
    source,cfg=world();add_priced_teammate(source);drop_projection(source,'p5')
    source[f'{provider.API}/league/123/rosters'][1]['taxi']=['p5']
    detail=run(source,cfg)['weeks'][0]['teams']['2']
    assert Decimal(detail['modeled_actual_projection'])==Decimal('7.5')
    assert detail['projection_coverage']['complete'] and detail['projection_coverage']['missing_actual_slots']==[]
    assert [p['player_id'] for p in detail['projection_coverage']['unpriced_players']]==['p5']
    assert not detail['projection_coverage']['unpriced_players'][0]['actual_eligible']


def test_malformed_source_identity_and_numeric_values_still_fail():
    source,cfg=world();key='https://api.sleeper.app/projections/nfl/2026/3?season_type=regular'
    source[key][0]['season']='2025'
    with pytest.raises(Unavailable):run(source,cfg)
    source,cfg=world();source[key][0]['stats']['pass_yd']=float('nan')
    with pytest.raises((Unavailable,ValueError)):run(source,cfg)


def test_available_zero_is_used_even_when_history_is_positive():
    source,cfg=world();key='https://api.sleeper.app/projections/nfl/2026/3?season_type=regular'
    source[key][1]['stats']={'gp':1,'rec':0,'rec_yd':0,'pts_std':0,'pts_half_ppr':0,'pts_ppr':0}
    detail=run(source,cfg)['weeks'][0]['teams']['2']
    assert detail['modeled_actual_projection']=='0.00'
    assert detail['projection_coverage']['complete'] and detail['projection_coverage']['missing_actual_slots']==[]
    assert detail['projection_coverage']['unpriced_players']==[]
    assert detail['projection_coverage']['priced_actual_pool']==1


def completed_world(include_future_bench=True):
    source,cfg=world();key='https://api.sleeper.app/projections/nfl/2026/3?season_type=regular'
    scores=source['https://api.sleeper.app/scores/nfl/regular/2026/3']
    scores[0]['status']='complete';scores[0]['start_time']=1793469600000  # Oct31 18:00UTC
    scores[0]['metadata'].update(has_started=True,is_over=True,status='complete')
    rosters=source[f'{provider.API}/league/123/rosters']
    rosters[0]['players']=['p1','p3']+(['p4'] if include_future_bench else [])
    source[f'{provider.API}/players/nfl']['p3']={'fantasy_positions':['QB'],'position':'QB','team':'T0'}
    extra=deepcopy(source[key][0]);extra.update(player_id='p3');extra['stats']['pass_yd']=10000 # Prematch projection must never be used.
    source[key].append(extra)
    if include_future_bench:
        source[f'{provider.API}/players/nfl']['p4']={'fantasy_positions':['QB'],'position':'QB','team':'T2'}
        extra=deepcopy(source[key][0]);extra.update(player_id='p4',team='T2',opponent='T3',game_id='w3g1')
        extra['stats']={'gp':1,'pass_yd':2500,'pts_std':100,'pts_half_ppr':100,'pts_ppr':100}
        source[key].append(extra)
    source[f'{provider.API}/league/123/matchups/3']=[
        {'roster_id':1,'matchup_id':1,'players':rosters[0]['players'],'starters':['p1'],'players_points':{'p1':5,'p3':50},'points':5},
        {'roster_id':2,'matchup_id':1,'players':['p2'],'starters':['p2'],'players_points':{'p2':7.5},'points':7.5}]
    return source,cfg


def test_completed_starter_is_locked_and_played_bench_remains_maxpf_eligible():
    source,cfg=completed_world(False);snapshot=run(source,cfg);detail=snapshot['weeks'][0]['teams']['1']
    assert Decimal(detail['actual']['points'])==5
    assert detail['actual']['lineup'][0]['player']['player_id']=='p1'
    assert detail['actual']['lineup'][0]['player']['locked_actual']
    assert Decimal(detail['maxpf']['points'])==50
    assert detail['maxpf']['lineup'][0]['player']['player_id']=='p3'
    assert snapshot['completed_weeks']==2 and snapshot['teams'][0]['points_for']=='15'
    actual=next(p['input'] for p in snapshot['player_week_inputs'] if p['player_id']=='p1')
    assert actual['actual_points']=='5' and actual['points_source']=='sleeper_matchup_players_points'
    assert 'pass_yd' not in actual['stats']


def test_future_bench_not_locked_and_completed_player_not_double_used():
    source,cfg=completed_world();detail=run(source,cfg)['weeks'][0]['teams']['1']
    assert Decimal(detail['actual']['points'])==5
    assert Decimal(detail['maxpf']['points'])==100
    assert detail['maxpf']['lineup'][0]['player']['player_id']=='p4'
    assert len({r['player']['player_id'] for r in detail['actual']['lineup'] if r['player']})==1


def test_missing_completed_actual_is_unpriced_and_lock_not_replaced_by_bench():
    source,cfg=completed_world();source[f'{provider.API}/league/123/matchups/3'][0]['players_points'].pop('p1')
    detail=run(source,cfg)['weeks'][0]['teams']['1']
    assert detail['actual']['lineup'][0]['player'] is None
    assert detail['actual']['lineup'][0]['unpriced_locked_player']['player_id']=='p1'
    assert detail['projection_coverage']['missing_locked_actuals'][0]['reason']=='missing_completed_actual'


def test_already_completed_starter_is_not_retroactively_removed_by_current_reserve():
    source,cfg=completed_world(False);cfg['ir_maxpf']='exclude'
    source[f'{provider.API}/league/123/rosters'][0]['reserve']=['p1']
    detail=run(source,cfg)['weeks'][0]['teams']['1']
    assert detail['actual']['lineup'][0]['player']['player_id']=='p1'
    assert Decimal(detail['actual']['points'])==5


def test_started_live_game_still_refuses_pregame_forecast():
    source,cfg=world();game=source['https://api.sleeper.app/scores/nfl/regular/2026/3'][0]
    game['status']='in_progress';game['metadata'].update(has_started=True,is_in_progress=True)
    with pytest.raises(Unavailable):run(source,cfg)


def test_fully_completed_lineup_is_observed_once_not_randomized_or_double_counted():
    source,cfg=completed_world(False);snapshot=run(source,cfg)
    assert snapshot['completed_weeks']==2
    result=simulation.simulate(snapshot,cfg)
    teams={t['roster_id']:t for t in result['teams']}
    assert teams[1]['expected_record']==[1,2,0] and teams[2]['expected_record']==[2,1,0]
    assert teams[1]['weeks'][0]['modeled_score_mean']==5
    assert teams[1]['weeks'][0]['modeled_score_sd']==0
    assert teams[1]['weeks'][0]['score_distribution']=='observed_completed_lineup'
    assert teams[1]['maxpf_mean']==70  # Official historical20 + observed current50.
    assert teams[1]['current_points_for']==15


def test_observed_maxpf_floor_conditions_remaining_unknown_bench_distribution():
    source,cfg=completed_world();key='https://api.sleeper.app/projections/nfl/2026/3?season_type=regular'
    # The future bench forecast is below already observed bench50.
    source[key][-1]['stats']={'gp':1,'pass_yd':250,'pts_std':10,'pts_half_ppr':10,'pts_ppr':10}
    result=simulation.simulate(run(source,cfg),cfg)
    detail=result['teams'][0]['weeks'][0]
    assert detail['modeled_score_mean']==5 and detail['modeled_score_sd']==0
    assert detail['observed_mean_conditioning']['known_maxpf_floor']==50
    assert detail['maxpf_floor']['target_mean']>=50
    assert detail['maxpf_floor']['simulated_mean']>=50


def test_empty_or_unpriced_lineup_is_not_declared_fully_observed():
    # Nothing priced at all: no snapshot, so nothing can be declared observed.
    source,cfg=world();source[FEED]=[]
    assert_missing_weekly_projections(source,cfg,['actual','maxpf'])
    # One unpriced player beside a priced teammate: a projection, not an observation.
    source,cfg=world();add_priced_teammate(source);drop_projection(source,'p2')
    snapshot=run(source,cfg)
    assert all(not t['actual_score_observed'] and not t['maxpf_score_observed'] for t in snapshot['weeks'][0]['teams'].values())


def test_rollover_already_in_official_history_is_not_counted_again():
    source,cfg=completed_world(False)
    source[f'{provider.API}/state/nfl']['week']=4
    rosters=source[f'{provider.API}/league/123/rosters']
    rosters[0]['settings'].update(wins=1,losses=2,fpts=20,fpts_decimal=0,fpts_against=22,fpts_against_decimal=50,ppts=70)
    rosters[1]['settings'].update(wins=2,losses=1,fpts=22,fpts_decimal=50,fpts_against=20,fpts_against_decimal=0,ppts=27,ppts_decimal=50)
    source[f'{provider.API}/league/123/matchups/3'][0]['starters_points']=[5]
    source[f'{provider.API}/league/123/matchups/3'][1]['starters_points']=[7.5]
    snapshot=run(source,cfg);result=simulation.simulate(snapshot,cfg)
    assert snapshot['completed_weeks']==3 and snapshot['weeks']==[]
    assert result['teams'][0]['expected_record']==[1,2,0]
    assert result['teams'][0]['maxpf_mean']==70
    assert result['teams'][0]['current_points_for']==20


def test_partial_current_week_manual_override_remains_unsupported():
    source,cfg=completed_world();source[f'{provider.API}/league/123/matchups/3'][0]['custom_points']=99
    with pytest.raises(Unavailable,match='manual_score_adjustment_requires_policy'):run(source,cfg)


def test_completed_bench_floor_also_conditions_future_actual_starters():
    source,cfg=completed_world()
    source[f'{provider.API}/league/123/matchups/3'][0]['starters']=['p4']
    source[f'{provider.API}/league/123/matchups/3'][0]['points']=0
    snapshot=run(source,cfg);detail=snapshot['weeks'][0]['teams']['1']
    assert not detail['actual_score_observed'] and Decimal(detail['observed_maxpf_floor'])==50
    result=simulation.simulate(snapshot,cfg);w=result['teams'][0]['weeks'][0]
    assert w['maxpf_floor']['policy']=='mean_preserving_observed_floor_gap_v1'
    assert w['observed_mean_conditioning']['conditioned_target']>=50
    assert w['maxpf_floor']['simulated_mean']>=50
    assert w['maxpf_floor']['analytic_realized_variance'] is None
    assert w['maxpf_floor']['analytic_realized_correlation'] is None
    assert w['modeled_score_sd']>0


def test_full_week_completion_not_empty_lineup_alone_establishes_observed_zero():
    source,cfg=world()
    for game in source['https://api.sleeper.app/scores/nfl/regular/2026/3']:
        game['status']='complete';game['start_time']=1793469600000
        game['metadata'].update(has_started=True,is_over=True,status='complete')
    for row in source[f'{provider.API}/league/123/matchups/3']:
        row.update(starters=['0'],players_points={},points=0)
    # The finished week fixes the actual score even with no player scores; only
    # the unrecorded bench leaves the Max PF lane without a number.
    assert_missing_weekly_projections(source,cfg,['maxpf'])
    for row in source[f'{provider.API}/league/123/matchups/3']:
        row['players_points']={f"p{row['roster_id']}":4}
    result=simulation.simulate(run(source,cfg),cfg)
    assert all(t['expected_record']==[1,1,1] for t in result['teams'])
    assert all(t['maxpf_mean']==24 for t in result['teams'])  # Official 20 + the recorded bench 4.
    assert all(t['weeks'][0]['actual_score_observed'] and t['weeks'][0]['modeled_score_sd']==0 for t in result['teams'])


def test_observed_floor_expectation_accounts_for_actual_upper_tail():
    from backend.league_projections import joint
    p=joint.prepare_observed_floor(40,45,20,15,.3,5,50,True,2)
    expected=50+joint.positive_normal_mean(-10,(20**2+5**2)**.5)
    assert p['base_mean']==expected and p['target_mean']==expected
    assert p['latent_gap_mean'] is None
    q=joint.prepare_observed_floor(40,80,20,15,.3,5,50,True,2)
    assert abs(q['analytic_unrounded_mean']-80)<1e-9
    assert q['target_adjustment']==0
