"""Independent high-precision base expectation and observed-floor simulation checks."""
from copy import deepcopy
import math
import pytest
from backend.league_projections import joint,simulation,provider
from backend.tests.test_league_projection_simulation import snapshot,config
from backend.tests.test_league_projection_best_available import completed_world
from backend.tests.test_league_projection_native_capture import run


# Frozen independent 70-digit mpmath oracle values; no new dependency.
ORACLE = {(0, 1, 0): 0.3989422804014327, (10, 3, 0): 10.000336233656904, (0, 3, 10): 10.000336233656904, (-10, 3, -5): -4.940520344985828, (1000000.0, 0.001, 1000000.0): 1000000.0003989423, (1000000.0, 0.001, 1000000.003): 1000000.0030003821, (1000000.0, 0.001, -1000000.0): 1000000.0, (-1000000.0, 0.001, 1000000.0): 1000000.0, (0, 0, -1): 0, (0, 0, 1): 1, (0, 0, 0): 0, (1e-07, 1e-06, 2e-07): 5.509353312047147e-07}
def expectation(mu,sigma,floor):
    return ORACLE[(mu,sigma,floor)]


@pytest.mark.parametrize('mu,sd,floor',[(0,1,0),(10,3,0),(0,3,10),(-10,3,-5),
    (1e6,.001,1e6),(1e6,.001,1e6+.003),(1e6,.001,-1e6),(-1e6,.001,1e6),
    (0,0,-1),(0,0,1),(0,0,0),(1e-7,1e-6,2e-7)])
@pytest.mark.parametrize('rho',[-1,0,1])
def test_floor_base_mean_matches_independent_high_precision_expectation(mu,sd,floor,rho):
    p=joint.prepare_observed_floor(mu,mu,sd,sd,rho,0,floor,True,2)
    oracle=expectation(mu,sd,floor)
    assert p['base_mean']==pytest.approx(oracle,rel=2e-13,abs=1e-10)
    assert p['target_mean']==pytest.approx(max(mu,oracle),rel=2e-13,abs=1e-10)
    assert p['target_adjustment']==pytest.approx(p['target_mean']-mu)
    assert p['analytic_realized_variance'] is None
    assert p['analytic_realized_correlation'] is None


@pytest.mark.parametrize('rho',[-1,0,1])
@pytest.mark.parametrize('target_extra',[0,30])
def test_compound_floor_mean_and_actual_rng_paths(rho,target_extra):
    data=snapshot();data['weeks']=data['weeks'][:1]
    cfg=config();cfg.update(iterations=2000,residual_correlation=rho)
    for week in data['weeks']:
        for team in week['teams'].values():
            team['maxpf']['points']=str(100+target_extra)
    before=simulation.simulate(data,cfg)
    after_data=deepcopy(data)
    for team in after_data['weeks'][0]['teams'].values():team['observed_maxpf_floor']='60'
    after=simulation.simulate(after_data,cfg)
    for old,new in zip(before['teams'],after['teams']):
        assert old['expected_record']==new['expected_record']
        assert old['final_record_distribution']==new['final_record_distribution']
        assert old['playoff_probability']==new['playoff_probability']
        a,b=old['weeks'][0]['maxpf_floor'],new['weeks'][0]['maxpf_floor']
        assert a['simulated_actual_mean']==b['simulated_actual_mean']
        assert a['simulated_actual_variance']==b['simulated_actual_variance']
        assert b['simulated_mean'] >= 60
        assert abs(b['simulated_mean']-b['target_mean'])<=6*b['simulated_mean_standard_error']+.006
        assert new['maxpf_quantiles']['0.1']>=110 # historical50 + achieved floor60
        conditioning=new['weeks'][0]['observed_mean_conditioning']
        assert conditioning['conditioned_target']==b['target_mean']
        assert conditioning['target_adjustment']==pytest.approx(b['target_adjustment'])


def test_completed_bench_full_assignment_establishes_floor_before_starters_finish():
    source,cfg=completed_world();source[f'{provider.API}/league/123/matchups/3'][0]['starters']=['p4']
    data=run(source,cfg);detail=data['weeks'][0]['teams']['1']
    assert detail['actual_score_observed'] is False
    assert Decimal(detail['observed_maxpf_floor'])==50
    result=simulation.simulate(data,cfg)['teams'][0]
    assert result['maxpf_quantiles']['0.1']>=70
    assert result['weeks'][0]['observed_mean_conditioning']['target_adjustment']>0


from decimal import Decimal
@pytest.mark.parametrize('empty,expected',[('fill_available',None),('allow','50')])
def test_partial_known_pool_is_floor_only_if_empty_slots_explicitly_allowed(empty,expected):
    source,cfg=completed_world();cfg['empty_slots']=empty
    source[f'{provider.API}/league/123']['roster_positions']=['SUPER_FLEX','RB']
    rows=source[f'{provider.API}/league/123/matchups/3']
    rows[0]['starters']=['p4','0'];rows[1]['starters']=['p2','0']
    detail=run(source,cfg)['weeks'][0]['teams']['1']
    assert detail['observed_maxpf_floor']==expected
