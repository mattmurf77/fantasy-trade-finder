"""Later-round reseeding cannot alter regular-season qualification estimates."""
from copy import deepcopy
import pytest
from backend.league_projections.core import Unavailable
from backend.league_projections.simulation import simulate
from backend.tests.test_league_projection_provider import world,run,API
from backend.tests.test_league_projection_simulation import config


def test_native_bracket_and_reseed_modes_have_identical_regular_season_outputs():
    source,feed=world()
    source[f'{API}/league/123']['settings']['playoff_seed_type']=0
    fixed=run(source,feed)
    source[f'{API}/league/123']['settings']['playoff_seed_type']=1
    reseeded=run(source,feed)
    assert fixed['league_revision']!=reseeded['league_revision']
    assert fixed['coverage']['native_playoff_seed_type']==0
    assert reseeded['coverage']['native_playoff_seed_type']==1
    assert reseeded['coverage']['postseason_rounds_simulated'] is False
    a,b=deepcopy(fixed),deepcopy(reseeded)
    for value in (a,b):
        value.pop('league_revision')
        value['coverage'].pop('native_playoff_seed_type')
    assert a==b
    x,y=simulate(fixed,config()),simulate(reseeded,config())
    assert x['teams']==y['teams']
    assert x['playoff_spots']==y['playoff_spots']
    assert x['snapshot_hash']!=y['snapshot_hash']


def test_missing_native_setting_retains_default_zero():
    source,feed=world()
    assert run(source,feed)['coverage']['native_playoff_seed_type']==0


@pytest.mark.parametrize('value',[True,False,None,'0','1',0.0,1.0,-1,2,[],{}])
def test_unknown_or_malformed_native_modes_refuse(value):
    source,feed=world();source[f'{API}/league/123']['settings']['playoff_seed_type']=value
    with pytest.raises(Unavailable) as exc:run(source,feed)
    assert exc.value.reason=='unsupported_playoff_reseeding_policy'


@pytest.mark.parametrize('setting',['divisions','league_average_match','best_ball','bracket_overrides_id'])
def test_reseeding_admission_preserves_other_rule_guards(setting):
    source,feed=world();league=source[f'{API}/league/123']
    league['settings']['playoff_seed_type']=1
    if setting=='bracket_overrides_id':league[setting]='synthetic-override'
    else:league['settings'][setting]=1
    with pytest.raises(Unavailable) as exc:run(source,feed)
    assert exc.value.reason=='unsupported_divisions_median_bestball_or_manual_seeding'
