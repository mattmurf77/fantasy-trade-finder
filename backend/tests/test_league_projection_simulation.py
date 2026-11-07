from copy import deepcopy
import math
import pytest
from backend.league_projections.simulation import simulate
from backend.league_projections.core import Unavailable


def config(**extra):
    return dict(seeding='record_pf_higher_pa_random',draft_tie='random_exact_ties',ir_maxpf='include',reserve_activation='exclude_current_reserve',empty_slots='fill_available',maxpf_variance='actual_history_proxy',iterations=1000,seed=730,historical_weight=.6,persistent_sd=5,residual_correlation=.5,**extra)

def snapshot():
    return {'playoff_spots':2,'playoff_byes':1,'completed_weeks':2,'source':'synthetic','captured_at':'2026-11-01T00:00:00+00:00',
      'teams':[{'roster_id':i,'name':f'Team{i}','wins':1,'losses':1,'ties':0,'points_for':'30','points_against':'30','maxpf':'50','actual_history':['10','20'],'maxpf_history':[]} for i in range(1,5)],
      'weeks':[{'week':week,'games':pairs,'teams':{str(i):{'actual':{'points':str(i*4)},'maxpf':{'points':str(i*6)},'maxpf_dominates_actual':True} for i in range(1,5)}} for week,pairs in [(3,[[1,2],[3,4]]),(4,[[1,3],[2,4]])]],
      'pick_ownership':[{'season':2027,'round':1,'original_roster_id':3,'owner_roster_id':1},{'season':2027,'round':1,'original_roster_id':4,'owner_roster_id':1}]}


def test_shared_world_probability_record_and_owner_invariants():
    source=snapshot();result=simulate(source,config());teams=result['teams']
    assert math.isclose(sum(t['playoff_probability'] for t in teams),2)
    assert math.isclose(sum(t['bye_probability'] for t in teams),1)
    assert math.isclose(sum(t['expected_record'][0]+t['expected_record'][2]/2 for t in teams),8)
    for k in range(2):assert math.isclose(sum(t['pick_probabilities'][k] for t in teams),1)
    for t in teams:
        assert math.isclose(sum(t['pick_probabilities']),t['nonplayoff_probability'])
        assert math.isclose(sum(t['expected_record']),4)
        for w in t['weeks']:assert math.isclose(sum(w[k] for k in ('win_probability','tie_probability','loss_probability')),1)
        if t['nonplayoff_samples']>=100:assert math.isclose(sum(t['conditional_pick_probabilities']),1)
        else:assert t['conditional_expected_pick'] is None
    assert math.isclose(sum(t['owner_expected_nonplayoff_picks'] for t in teams),2)
    assert teams[2]['owner_expected_nonplayoff_picks']==teams[3]['owner_expected_nonplayoff_picks']==0
    assert teams[0]['owner_expected_nonplayoff_picks']>=teams[0]['owner_probability_at_least_one']
    assert source==snapshot()
    assert result==simulate(source,config())


def test_no_remaining_weeks_uses_official_totals_and_conditioning_threshold():
    source=snapshot();source['weeks']=[]
    cfg=config();cfg['iterations']=100;cfg['min_pick_samples']=101
    result=simulate(source,cfg)
    assert all(t['maxpf_mean']==50 and t['conditional_expected_pick'] is None for t in result['teams'])
    assert all(t['expected_record']==[1,1,0] for t in result['teams'])


def test_no_nonplayoff_teams_has_empty_pick_distribution():
    source=snapshot();source['playoff_spots']=4;source['playoff_byes']=0
    result=simulate(source,config())
    assert all(t['pick_probabilities']==[] and t['nonplayoff_probability']==0 and t['conditional_expected_pick'] is None for t in result['teams'])


def test_missing_history_requires_explicit_variance_prior():
    source=snapshot();source['completed_weeks']=0
    for t in source['teams']:
        t.update(wins=0,losses=0,ties=0,points_for='0',points_against='0',maxpf='0',actual_history=[])
    with pytest.raises(Unavailable) as err:simulate(source,config())
    assert err.value.reason=='short_history_variance_prior_required'
    for t in source['teams']:t['projection_weekly_sd']=10
    result=simulate(source,config())
    assert result['status']=='complete' and all(t['current_ppg'] is None for t in result['teams'])


def test_reconstructed_maxpf_history_does_not_replace_authoritative_aggregate():
    source=snapshot()
    for t in source['teams']:t['maxpf_history']=['20','29']  # Known reconstruction discrepancy; aggregate50 authoritative.
    cfg=config();cfg['maxpf_variance']='reconstructed_history'
    result=simulate(source,cfg)
    assert all(t['current_maxpf']==50 for t in result['teams'])
    assert any('reconstruct' in w.lower() for w in result['warnings'])


def test_finished_season_does_not_require_variance_priors_for_no_future_draws():
    source=snapshot();source['completed_weeks']=1;source['weeks']=[]
    for i,t in enumerate(source['teams']):
        t.update(wins=1 if i%2==0 else 0,losses=0 if i%2==0 else 1,ties=0,actual_history=['10'],points_for='10',points_against='10',maxpf='15',maxpf_history=[])
    result=simulate(source,config())
    assert result['status']=='complete'
    assert all(t['maxpf_mean']==15 and t['weeks']==[] for t in result['teams'])


def test_draft_membership_uses_actual_playoffs_before_maxpf_ranking_and_exact_pick_season():
    source=snapshot()
    for t in source['teams']:
        t.update(actual_history=['0','0'],points_for='0',points_against='0',maxpf='0')
    source['weeks']=[{'week':3,'games':[[1,3],[2,4]],'teams':{str(i):{'actual':{'points':str(a)},'maxpf':{'points':str(m)},'maxpf_dominates_actual':False} for i,a,m in [(1,100,1),(2,90,2),(3,-5,10),(4,-10,20)]}}]
    source['pick_ownership']=[{'season':2027,'round':1,'original_roster_id':3,'owner_roster_id':1},{'season':2028,'round':1,'original_roster_id':4,'owner_roster_id':1},{'season':2027,'round':2,'original_roster_id':4,'owner_roster_id':2}]
    cfg=config();cfg.update(historical_weight=0,persistent_sd=0,iterations=100)
    teams=simulate(source,cfg)['teams']
    assert [t['playoff_probability'] for t in teams]==[1,1,0,0]
    assert [t['pick_probabilities'] for t in teams]==[[0,0],[0,0],[1,0],[0,1]]
    assert [t['pick_owner_roster_id'] for t in teams]==[1,2,1,4]
    assert [t['owner_expected_nonplayoff_picks'] for t in teams]==[1,0,0,1]
    assert teams[2]['weeks'][0]['modeled_score_mean']==-5
    assert teams[3]['weeks'][0]['modeled_score_mean']==-10


def test_zero_gap_preserves_mean_and_actual_distribution_without_floor_uplift():
    source=snapshot();source['weeks']=source['weeks'][:1]
    for t in source['teams']:
        t.update(actual_history=['10','30'], points_for='40', points_against='40', maxpf='40')
    for detail in source['weeks'][0]['teams'].values():
        detail['actual']['points']='20';detail['maxpf']['points']='20'
    cfg=config();cfg.update(iterations=30000,persistent_sd=0,residual_correlation=0,historical_weight=0)
    result=simulate(source,cfg)
    for t in result['teams']:
        d=t['weeks'][0]['maxpf_floor']
        assert d['construction']=='actual_equals_maxpf'
        assert d['latent_maxpf_mean'] is None
        assert d['simulated_mean']==d['simulated_actual_mean']
        assert d['mean_uplift']==0 and d['frequency']==0
        assert math.isclose(d['simulated_correlation'],1,abs_tol=1e-10)
        assert abs(d['simulated_mean']-20)<6*d['simulated_mean_standard_error']
        assert math.isclose(t['maxpf_mean'],40+d['simulated_mean'],abs_tol=1e-9)
