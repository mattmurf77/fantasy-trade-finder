from datetime import datetime
from copy import deepcopy
import pytest
from backend.league_projections.timing import validate_season_schedule,normalize_week_games,classify_player_game,CoverageError


def world():
    raw=[{'game_id':'g1','home':'A','away':'B','week':1},{'game_id':'g2','home':'C','away':'D','week':2}]
    schedule=validate_season_schedule(raw,games=2,teams=4,games_per_team=1,weeks=2)
    score={'game_id':'g1','season':'2026','week':1,'season_type':'regular','sport':'nfl','status':'pre_game',
           'start_time':int(datetime.fromisoformat('2026-11-08T18:00:00+00:00').timestamp()*1000),
           'metadata':{'home_team':'A','away_team':'B','date_time':'2026-11-08T13:00:00-05:00','status':'scheduled','has_started':False,'is_in_progress':False,'is_over':False,'canceled':False}}
    player={'season':'2026','week':1,'season_type':'regular','category':'proj','game_id':'g1','team':'A','opponent':'B'}
    return schedule,score,player


def test_known_schedule_bye_is_distinct_from_missing_player_projection():
    schedule,row,player=world();games=normalize_week_games(schedule,[row],2026,1,'2026-11-08T17:00:00+00:00')
    assert classify_player_game(None,'C',schedule,games,2026,1)['bye'] is True
    assert classify_player_game(player,'A',schedule,games,2026,1)['phase']=='pregame'
    with pytest.raises(CoverageError):classify_player_game(None,'A',schedule,games,2026,1)
    assert classify_player_game(None,None,schedule,games,2026,1)['phase']=='no_known_team'


def test_canceled_scheduled_game_is_not_bye():
    schedule,row,player=world();row['metadata']['canceled']=True
    games=normalize_week_games(schedule,[row],2026,1,'2026-11-08T17:00:00+00:00')
    result=classify_player_game(player,'A',schedule,games,2026,1)
    assert result['phase']=='canceled' and result['bye'] is False

@pytest.mark.parametrize('change',[lambda r:r.update(start_time=None),lambda r:r['metadata'].update(date_time='2026-11-08'),lambda r:r['metadata'].update(date_time='2026-11-08T20:00:00+00:00')])
def test_missing_or_conflicting_exact_kickoff_not_date_guessed(change):
    schedule,row,_=world();change(row)
    with pytest.raises(CoverageError):normalize_week_games(schedule,[row],2026,1,'2026-11-08T17:00:00+00:00')


def test_past_scheduled_time_without_status_confirmation_not_pregame_or_completed():
    schedule,row,player=world();games=normalize_week_games(schedule,[row],2026,1,'2026-11-08T19:00:00+00:00')
    assert classify_player_game(player,'A',schedule,games,2026,1)['phase']=='unknown_or_delayed'


def test_projection_game_mismatch_rejected():
    schedule,row,player=world();games=normalize_week_games(schedule,[row],2026,1,'2026-11-08T17:00:00+00:00');player['game_id']='g2'
    with pytest.raises(CoverageError):classify_player_game(player,'A',schedule,games,2026,1)
