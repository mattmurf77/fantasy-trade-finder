"""Independent partial/completed-week acceptance; small synthetic worlds only."""
from copy import deepcopy
from decimal import Decimal
import pytest
from backend.league_projections import provider,simulation
from backend.tests.test_league_projection_best_available import completed_world
from backend.tests.test_league_projection_native_capture import run


def test_missing_player_actual_uses_known_completed_team_total_without_inventing_player_points():
    source,cfg=completed_world(False)
    source[f'{provider.API}/league/123/matchups/3'][0]['players_points'].pop('p1')
    detail=run(source,cfg)['weeks'][0]['teams']['1']
    assert detail['actual']['lineup'][0]['player'] is None
    assert Decimal(detail['maxpf']['points'])==50
    assert detail['projection_coverage']['priced_actual_pool']==0
    assert detail['actual_score_observed'] is True
    assert Decimal(detail['modeled_actual_projection'])==5
    assert detail['projection_coverage']['fallback'] is None


def test_played_bench_is_not_usable_partial_actual_fallback_pool():
    source,cfg=completed_world()
    source[f'{provider.API}/league/123']['roster_positions']=['SUPER_FLEX','SUPER_FLEX']
    rows=source[f'{provider.API}/league/123/matchups/3']
    rows[0]['starters']=['p1','p4'];rows[1]['starters']=['p2','0']
    rows[0]['players_points'].pop('p1')
    key='https://api.sleeper.app/projections/nfl/2026/3?season_type=regular'
    source[key]=[row for row in source[key] if row['player_id']!='p4']
    detail=run(source,cfg)['weeks'][0]['teams']['1']
    assert detail['projection_coverage']['priced_actual_pool']==0
    assert detail['projection_coverage']['fallback']=='completed_team_history'
    assert detail['projection_coverage']['fallback_lanes']==['actual']
    assert Decimal(detail['modeled_actual_projection'])==Decimal('7.5')
    assert Decimal(detail['modeled_maxpf_projection'])==50


def test_current_manual_override_is_not_silently_ignored():
    source,cfg=completed_world(False)
    source[f'{provider.API}/league/123/matchups/3'][0]['custom_points']=99
    with pytest.raises(provider.Unavailable):
        run(source,cfg)


def test_duplicate_observed_completed_starter_rejected():
    source,cfg=completed_world()
    source[f'{provider.API}/league/123']['roster_positions']=['SUPER_FLEX','SUPER_FLEX']
    rows=source[f'{provider.API}/league/123/matchups/3']
    rows[0]['starters']=['p1','p1'];rows[1]['starters']=['p2','0']
    with pytest.raises(provider.Unavailable):
        run(source,cfg)


def test_partial_current_week_manual_override_stays_explicit():
    source,cfg=completed_world()
    source[f'{provider.API}/league/123']['roster_positions']=['SUPER_FLEX','SUPER_FLEX']
    rows=source[f'{provider.API}/league/123/matchups/3']
    rows[0]['starters']=['p1','p4'];rows[1]['starters']=['p2','0']
    rows[0]['custom_points']=99
    with pytest.raises(provider.Unavailable):run(source,cfg)


def test_completed_week_is_added_once_and_has_no_random_actual_result():
    source,cfg=completed_world(False)
    result=simulation.simulate(run(source,cfg),cfg)
    teams={t['roster_id']:t for t in result['teams']}
    assert teams[1]['current_record']==[1,1,0]
    assert teams[1]['expected_record']==[1,2,0]
    assert teams[2]['expected_record']==[2,1,0]
    assert teams[1]['current_maxpf']==20
    assert teams[1]['maxpf_mean']==70
    assert teams[1]['weeks'][0]['modeled_score_mean']==5
    assert teams[1]['weeks'][0]['modeled_score_sd']==0
    assert teams[1]['weeks'][0]['historical_component']==0
    assert teams[1]['weeks'][0]['maxpf_floor']['simulated_actual_variance']==0


def test_fully_finished_week_with_empty_lineups_is_still_observed():
    source,cfg=completed_world(False)
    for game in source['https://api.sleeper.app/scores/nfl/regular/2026/3']:
        game.update(status='complete',start_time=1793469600000)
        game['metadata'].update(has_started=True,is_over=True,is_in_progress=False,status='complete')
    for row in source[f'{provider.API}/league/123/matchups/3']:
        row['starters']=['0'];row['points']=0
    snapshot=run(source,cfg)
    assert all(detail['actual_score_observed'] for detail in snapshot['weeks'][0]['teams'].values())
    result=simulation.simulate(snapshot,cfg)
    assert all(team['expected_record']==[1,1,1] for team in result['teams'])
