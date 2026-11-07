"""Prospective independent extension controls, separate from reseeding acceptance."""
from copy import deepcopy
import pytest
from backend.league_projections import provider,simulation
from backend.league_projections.core import Unavailable
from backend.tests.test_league_projection_provider import world,run
from backend.tests.test_league_projection_simulation import config
from backend.tests import test_league_projection_reseeding_review as fixture
API=provider.API

@pytest.mark.parametrize('seed_type',[0,1])
@pytest.mark.parametrize('lower_type',[0,1])
def test_both_postseason_choices_leave_regular_and_maxpf_scenario_numbers_exact(seed_type,lower_type):
    source,feed=fixture.eight_team_world(0);source[f'{API}/league/123']['settings']['playoff_type']=0
    baseline=simulation.simulate(run(source,feed),config())
    source[f'{API}/league/123']['settings'].update(playoff_seed_type=seed_type,playoff_type=lower_type)
    snapshot=run(source,feed);result=simulation.simulate(snapshot,config())
    assert result['teams']==baseline['teams']
    assert result['playoff_spots']==6 and result['playoff_byes']==2
    assert result['draft_sort']=='projected_maxpf_mean'
    assert sum(t['owner_expected_nonplayoff_picks'] for t in result['teams'])==pytest.approx(2)
    assert snapshot['coverage']['native_playoff_type']==lower_type
    assert snapshot['coverage']['postseason_rounds_simulated'] is False
    assert any('Max PF' in w and 'draft' in w.lower() and 'assum' in w.lower() for w in result['warnings'])
    assert any('consolation' in w.lower() and ('not' in w.lower() or 'rather' in w.lower()) for w in result['warnings'])

@pytest.mark.parametrize('value',[False,True,'0','1',0.0,1.0,None,-1,2,[],{}])
def test_only_exact_lower_bracket_enum_admitted(value):
    source,feed=world();source[f'{API}/league/123']['settings'].update(playoff_seed_type=1,playoff_type=value)
    with pytest.raises(Unavailable) as exc:run(source,feed)
    assert 'playoff' in exc.value.reason or 'bracket' in exc.value.reason

@pytest.mark.parametrize('key,value',[('divisions',1),('league_average_match',1),('best_ball',1),('playoff_round_type',1),('start_week',2)])
def test_lower_bracket_acceptance_preserves_separate_policy_refusals(key,value):
    source,feed=world();source[f'{API}/league/123']['settings'].update(playoff_seed_type=1,playoff_type=1,**{key:value})
    with pytest.raises(Unavailable):run(source,feed)


def test_manual_override_still_refuses_both_native_options():
    source,feed=world();source[f'{API}/league/123']['settings'].update(playoff_seed_type=1,playoff_type=1)
    source[f'{API}/league/123']['bracket_overrides_id']='synthetic-override'
    with pytest.raises(Unavailable) as exc:run(source,feed)
    assert 'manual' in exc.value.reason


def test_lower_bracket_change_during_capture_is_stale():
    source,feed=world();source[f'{API}/league/123']['settings']['playoff_type']=0;calls=0
    def fetch(url):
        nonlocal calls
        data=deepcopy(source[url])
        if url==f'{API}/league/123':
            calls+=1
            if calls==2:data['settings']['playoff_type']=1
        return data
    with pytest.raises(Unavailable) as exc:
        provider.capture('123','me',config(),fetch,feed=feed,captured_at='2026-11-01T00:00:00+00:00',clock=lambda:'2026-11-01T00:00:01+00:00')
    assert exc.value.reason=='inputs_changed_during_capture'


def test_absent_lower_bracket_uses_native_default_zero():
    source,feed=world();snap=run(source,feed)
    assert snap['coverage']['native_playoff_type']==0
    assert snap['coverage']['postseason_rounds_simulated'] is False

