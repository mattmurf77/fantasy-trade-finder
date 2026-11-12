"""Best-available estimates distinguish data absence from a real numeric zero.

Player who changed NFL teams (Sleeper metadata has the new team; the weekly
feed row still carries the old one):
- test_team_changed_player_is_unpriced_and_stale_row_scores_nothing: capture
  succeeds, the player is unpriced as `player_team_changed`, timed by the new
  team's game, and the stale row's stats reach no lineup; a teammate whose
  teams agree is priced as before.
- test_team_changed_player_alone_for_a_slot_is_filled_from_free_agents: the
  slot only he could fill takes the best projected free agent (model v6); the
  league estimate stays complete.
- test_team_changed_player_on_new_team_bye_is_a_bye: a verified bye, not
  unpriced and not an error.
- test_strict_contract_still_refuses_a_team_changed_player.

Free-agent fill (model v6, operator rule 2026-11-11), through the real weekly
feed adapter:
- test_empty_rb_slot_takes_the_best_projected_free_agent_rb: the production
  case (only eligible rostered RB has an empty feed row) is filled, complete,
  and the outlook suggestion is no longer withheld; the same free agent may
  fill slots on different teams; Max PF uses the same fill and never drops
  below the lineup total; coverage records slot, player and points.
- test_free_agent_on_bye_or_not_pregame_is_not_used.
- test_feed_never_offers_a_rostered_player_as_a_free_agent (players, taxi,
  reserve of every team).
- test_free_agent_never_displaces_a_rostered_starter.
- test_two_open_slots_take_two_free_agents_in_the_best_assignment.
- test_a_played_starter_with_no_score_is_not_filled_and_stays_incomplete.
"""
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


def test_missing_player_does_not_block_known_team_and_wholly_unpriced_team_is_zero_filled():
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
    # The same missing player as the team's only one. The feed is populated
    # (p1 is projected), so the slot is filled from free agents; this feed
    # has none, so it scores a known zero instead of stopping the run (v6).
    source,cfg=world();drop_projection(source,'p2')
    snapshot=run(source,cfg);detail=snapshot['weeks'][0]['teams']['2']
    assert Decimal(detail['modeled_actual_projection'])==Decimal(detail['modeled_maxpf_projection'])==0
    assert detail['projection_coverage']['zero_filled_slots']==['SUPER_FLEX'] and detail['projection_coverage']['complete']
    assert snapshot['coverage']['estimate_status']=='complete' and snapshot['coverage']['zero_filled_slots']==1


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
    # Alone on the roster he has no game; the feed is otherwise populated, so
    # the slot is a known zero with no free agent projected (v6), not a stop.
    detail=run(source,cfg)['weeks'][0]['teams']['2']
    assert Decimal(detail['modeled_actual_projection'])==0 and detail['projection_coverage']['zero_filled_slots']==['SUPER_FLEX']
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
    # A taxi player is no part of the actual lineup. With the feed otherwise
    # populated, his empty Max PF slot is filled (here: zero, no free agent)
    # rather than stopping the run (v6).
    detail=run(source,cfg)['weeks'][0]['teams']['2']
    assert detail['projection_coverage']['maxpf_zero_filled_slots']==['SUPER_FLEX']
    assert detail['projection_coverage']['missing_maxpf_slots']==[] and Decimal(detail['modeled_maxpf_projection'])==0
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


# ── A player who changed NFL teams: the stale feed row is not his projection ──

def change_team(source,pid='p2',new='T2',stale_stats=None):
    """Metadata moves `pid` to `new`; his feed row keeps the old team and game."""
    source[f'{provider.API}/players/nfl'][pid]['team']=new
    row=next(r for r in source[FEED] if r['player_id']==pid)
    assert row['team']!=new
    if stale_stats is not None:row['stats']=stale_stats


HUGE={'gp':1,'rec':100,'rec_yd':1000,'pts_std':200,'pts_half_ppr':250,'pts_ppr':300}


def test_team_changed_player_is_unpriced_and_stale_row_scores_nothing():
    source,cfg=world();add_priced_teammate(source);change_team(source,stale_stats=HUGE)
    snapshot=run(source,cfg);teams=snapshot['weeks'][0]['teams'];detail=teams['2']
    assert [(p['player_id'],p['reason']) for p in detail['projection_coverage']['unpriced_players']]==[('p2','player_team_changed')]
    # p5 (teams agree) starts; the stale 300-point row reaches neither lane.
    assert [r['player']['player_id'] for r in detail['actual']['lineup']]==['p5']
    assert Decimal(detail['modeled_actual_projection'])==Decimal(detail['modeled_maxpf_projection'])==4
    assert detail['projection_coverage']['complete'] and detail['projection_coverage']['missing_actual_slots']==[]
    assert snapshot['coverage']['estimate_status']=='complete'
    # Timed by the new team's game, carrying none of the stale row.
    p2=next(p['input'] for p in snapshot['player_week_inputs'] if p['player_id']=='p2')
    assert p2['game_id']=='w3g1' and p2['stats']=={} and p2['projection_status']=='unpriced'
    # Player whose teams agree is unaffected.
    assert Decimal(teams['1']['modeled_actual_projection'])==8
    assert teams['1']['projection_coverage']['unpriced_players']==[]


def test_team_changed_player_alone_for_a_slot_is_filled_from_free_agents():
    source,cfg=world();add_priced_teammate(source);change_team(source,stale_stats=HUGE)
    source[f'{provider.API}/league/123']['roster_positions']=['SUPER_FLEX','TE']
    add_free_agent(source,'fte','TE','T6',rec=2)
    snapshot=run(source,cfg);detail=snapshot['weeks'][0]['teams']['2']
    # He is simply not used; his TE slot takes the free agent like any other.
    assert detail['projection_coverage']['complete'] is True and detail['projection_coverage']['missing_actual_slots']==[]
    assert [(f['slot'],f['player_id']) for f in detail['projection_coverage']['free_agent_fills']]==[('TE','fte')]
    assert Decimal(detail['modeled_actual_projection'])==4+Decimal(detail['projection_coverage']['free_agent_fills'][0]['points'])
    assert snapshot['coverage']['estimate_status']=='complete'
    assert snapshot['weeks'][0]['teams']['1']['projection_coverage']['complete'] is True


def test_team_changed_player_on_new_team_bye_is_a_bye():
    source,cfg=world();change_team(source,stale_stats=HUGE)
    # T2 (and T3) do not play week 3: their game moves to week 18.
    schedule=source['https://api.sleeper.app/schedule/nfl/regular/2026']
    next(g for g in schedule if g['game_id']=='w3g1')['week']=18
    scores=source['https://api.sleeper.app/scores/nfl/regular/2026/3']
    scores[:]=[g for g in scores if g['game_id']!='w3g1']
    snapshot=run(source,cfg);detail=snapshot['weeks'][0]['teams']['2']
    assert {'player_id':'p2','reason':'bye'} in detail['exclusions']
    assert detail['projection_coverage']['unpriced_players']==[]
    assert Decimal(detail['modeled_actual_projection'])==0
    assert detail['projection_coverage']['complete'] and snapshot['coverage']['estimate_status']=='complete'
    # The stored row is an ordinary verified bye, not an unpriced row.
    p2=next(p['input'] for p in snapshot['player_week_inputs'] if p['player_id']=='p2')
    assert p2['availability']==0 and p2['availability_basis']=='verified_schedule_bye'
    assert 'projection_status' not in p2 and 'coverage_reason' not in p2


def test_strict_contract_still_refuses_a_team_changed_player():
    source,cfg=native_world();change_team(source)
    assert cfg['scoring_contract']!=BEST_AVAILABLE
    with pytest.raises(Unavailable) as error:run(source,cfg)
    assert error.value.reason=='player_team_changed'


# ── Free-agent fill (model v6) ──────────────────────────────────────────────

CUTS=(.15,.75)


def add_free_agent(source,pid,pos,team,**stats):
    """A player on no roster, projected for `team`'s week-3 game."""
    j=int(team[1:])//2;home,away=f'T{2*j}',f'T{2*j+1}'
    source[f'{provider.API}/players/nfl'][pid]={'fantasy_positions':[pos],'position':pos,'team':team,'full_name':pid.upper()}
    source[FEED].append({'player_id':pid,'season':'2026','week':3,'season_type':'regular','category':'proj','company':'rotowire',
                         'game_id':f'w3g{j}','team':team,'opponent':away if team==home else home,'stats':{'gp':1,**stats}})


def unprojected_rb(source,roster_index=1,pid='r2',team='T1'):
    """A rostered RB whose feed row is empty: `no_usable_projection_contribution`."""
    source[f'{provider.API}/league/123/rosters'][roster_index]['players'].append(pid)
    source[f'{provider.API}/players/nfl'][pid]={'fantasy_positions':['RB'],'position':'RB','team':team}
    row=deepcopy(next(r for r in source[FEED] if r['player_id']=='p2'));row.update(player_id=pid,stats={})
    source[FEED].append(row)


def test_empty_rb_slot_takes_the_best_projected_free_agent_rb():
    from backend.league_projections import recommendation
    source,cfg=world();source[f'{provider.API}/league/123']['roster_positions']=['SUPER_FLEX','RB']
    unprojected_rb(source)
    add_free_agent(source,'fa_lo','RB','T4',rush_yd=50);add_free_agent(source,'fa_hi','RB','T6',rush_yd=80)
    snapshot=run(source,cfg);detail=snapshot['weeks'][0]['teams']['2'];coverage=detail['projection_coverage']
    assert [(p['player_id'],p['reason']) for p in coverage['unpriced_players']]==[('r2','no_usable_projection_contribution')]
    assert coverage['free_agent_fills']==[{'slot_index':1,'slot':'RB','player_id':'fa_hi','name':'FA_HI','points':'8.0','estimate_status':'partial'}]
    assert coverage['zero_filled_slots']==[] and coverage['complete'] and coverage['missing_actual_slots']==[]
    assert Decimal(detail['modeled_actual_projection'])==Decimal('15.5')
    # The same free agent fills team 1's open RB slot too (no league scarcity).
    assert [f['player_id'] for f in snapshot['weeks'][0]['teams']['1']['projection_coverage']['free_agent_fills']]==['fa_hi']
    # Max PF: the same fill, never below the lineup total.
    assert [(f['slot'],f['player_id']) for f in coverage['maxpf_free_agent_fills']]==[('RB','fa_hi')]
    for team in snapshot['weeks'][0]['teams'].values():
        assert Decimal(team['modeled_maxpf_projection'])>=Decimal(team['modeled_actual_projection'])
    league=snapshot['coverage']
    assert league['estimate_status']=='complete' and league['incomplete_team_weeks']==0 and league['missing_lineup_slots']==0
    assert (league['fa_filled_slots'],league['zero_filled_slots'],league['maxpf_fa_filled_slots'],league['maxpf_zero_filled_slots'])==(2,0,2,0)
    # The used free-agent row is a recorded input (hash, kickoff guard).
    assert [e['player_id'] for e in snapshot['player_week_inputs'] if e.get('free_agent')]==['fa_hi']
    result=simulation.simulate(snapshot,cfg)
    assert result['coverage']['estimate_status']=='complete'
    assert recommendation.build('current',result,None,CUTS)['status']=='available'


def test_free_agent_on_bye_or_not_pregame_is_not_used():
    source,cfg=world();source[f'{provider.API}/league/123']['roster_positions']=['SUPER_FLEX','RB']
    add_free_agent(source,'fa_lo','RB','T4',rush_yd=50)
    add_free_agent(source,'fa_bye','RB','T10',rush_yd=900)
    add_free_agent(source,'fa_live','RB','T12',rush_yd=900)
    add_free_agent(source,'fa_done','RB','T14',rush_yd=900)
    # T10/T11 move to week 18 (a bye); T12's game is live; T14's is over.
    next(g for g in source['https://api.sleeper.app/schedule/nfl/regular/2026'] if g['game_id']=='w3g5')['week']=18
    scores=source['https://api.sleeper.app/scores/nfl/regular/2026/3'];scores[:]=[g for g in scores if g['game_id']!='w3g5']
    live=next(g for g in scores if g['game_id']=='w3g6');live['status']='in_progress';live['metadata'].update(has_started=True,is_in_progress=True)
    done=next(g for g in scores if g['game_id']=='w3g7');done['status']='complete';done['start_time']=1793469600000
    done['metadata'].update(has_started=True,is_over=True,status='complete')
    snapshot=run(source,cfg)
    for team in snapshot['weeks'][0]['teams'].values():
        assert [f['player_id'] for f in team['projection_coverage']['free_agent_fills']]==['fa_lo']


def test_feed_never_offers_a_rostered_player_as_a_free_agent(monkeypatch):
    source,cfg=world();source[f'{provider.API}/league/123']['roster_positions']=['SUPER_FLEX','RB']
    rosters=source[f'{provider.API}/league/123/rosters']
    # Team 1 carries a projected RB on taxi and one on reserve; team 2 one more
    # on its bench behind nobody. None is a free agent for anyone.
    for pid,team,key,owner in (('tx','T8','taxi',0),('rs','T10','reserve',0)):
        add_free_agent(source,pid,'RB',team,rush_yd=600);rosters[owner][key]=[pid]
    add_free_agent(source,'fa_lo','RB','T4',rush_yd=50)
    original=provider.SleeperExperimentalFeed.weeks;seen=[]
    def weeks(self,*args):
        result=original(self,*args);seen.append(set(result['free_agents']['3']));return result
    monkeypatch.setattr(provider.SleeperExperimentalFeed,'weeks',weeks)
    snapshot=run(source,cfg)
    assert seen==[{'fa_lo'}]
    for team in snapshot['weeks'][0]['teams'].values():
        assert [f['player_id'] for f in team['projection_coverage']['free_agent_fills']]==['fa_lo']


def test_free_agent_never_displaces_a_rostered_starter():
    source,cfg=world();source[f'{provider.API}/league/123']['roster_positions']=['SUPER_FLEX','RB']
    unprojected_rb(source);source[FEED][-1]['stats']={'gp':1,'rush_yd':10}  # r2 projects 1 point
    add_free_agent(source,'fa_hi','RB','T6',rush_yd=80)
    detail=run(source,cfg)['weeks'][0]['teams']['2']
    assert [r['player']['player_id'] for r in detail['actual']['lineup']]==['p2','r2']
    assert [r['player']['player_id'] for r in detail['maxpf']['lineup']]==['p2','r2']
    assert detail['projection_coverage']['free_agent_fills']==[]==detail['projection_coverage']['maxpf_free_agent_fills']
    assert Decimal(detail['modeled_actual_projection'])==Decimal('8.5')


def test_two_open_slots_take_two_free_agents_in_the_best_assignment():
    # Flex listed first: filling it with the best RB would leave RB empty.
    source,cfg=world();source[f'{provider.API}/league/123']['roster_positions']=['SUPER_FLEX','WRRB_FLEX','RB']
    add_free_agent(source,'rb_a','RB','T4',rush_yd=100);add_free_agent(source,'wr_b','WR','T6',rec_yd=90)
    detail=run(source,cfg)['weeks'][0]['teams']['2']
    assert {(f['slot'],f['player_id']) for f in detail['projection_coverage']['free_agent_fills']}=={('WRRB_FLEX','wr_b'),('RB','rb_a')}
    assert Decimal(detail['modeled_actual_projection'])==Decimal('7.5')+10+9


def test_a_played_starter_with_no_score_is_not_filled_and_stays_incomplete():
    # Week in progress: p1 played (no score recorded), p4 is still to play.
    source,cfg=completed_world();source[f'{provider.API}/league/123']['roster_positions']=['SUPER_FLEX','SUPER_FLEX']
    rows=source[f'{provider.API}/league/123/matchups/3'];rows[0]['starters']=['p1','p4'];rows[1]['starters']=['p2','0']
    rows[0]['players_points'].pop('p1')
    add_free_agent(source,'fqb','QB','T4',pass_yd=250)
    snapshot=run(source,cfg);mine,theirs=(snapshot['weeks'][0]['teams'][rid] for rid in ('1','2'))
    # The locked slot is a fact: neither filled nor zero, and still unknown.
    assert mine['actual']['lineup'][0]['player'] is None and mine['projection_coverage']['free_agent_fills']==[]
    assert mine['projection_coverage']['zero_filled_slots']==[]
    assert mine['projection_coverage']['missing_actual_slots']==['SUPER_FLEX']
    assert snapshot['coverage']['estimate_status']=='incomplete' and snapshot['coverage']['incomplete_team_weeks']==1
    # An open (unlocked) starter slot in the same week is filled as usual.
    assert [f['player_id'] for f in theirs['projection_coverage']['free_agent_fills']]==['fqb']
