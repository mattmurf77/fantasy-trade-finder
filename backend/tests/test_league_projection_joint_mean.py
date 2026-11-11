"""Mean contract, joint dependence and draw-parity acceptance checks."""
import math
from copy import deepcopy
import pytest
from backend.league_projections import joint, simulation
from backend.league_projections.core import Unavailable
from backend.tests.test_league_projection_simulation import snapshot, config


@pytest.mark.parametrize('sd', [0., 1e-6, .01, 1., 20., 1e6])
@pytest.mark.parametrize('ratio', [1e-14, 1e-6, .01, .1, 1., 10., 1e6])
def test_positive_gap_solver_preserves_requested_expectation(sd,ratio):
    delta=sd*ratio if sd else ratio
    mean=joint.latent_gap_mean(delta,sd)
    assert math.isclose(joint.positive_normal_mean(mean,sd),delta,rel_tol=1e-10,abs_tol=1e-25)


def test_degenerate_infeasible_and_near_perfect_correlation():
    assert joint.latent_gap_mean(0,15) is None
    assert joint.latent_gap_mean(5,0)==5
    with pytest.raises(Unavailable):joint.latent_gap_mean(-1,2)
    with pytest.raises(Unavailable):joint.latent_gap_mean(float('nan'),2)
    with pytest.raises(Unavailable):joint.prepare(30,20,10,10,0,5,True,2)
    assert joint.prepare(30,20,10,10,0,5,False,2)['target_mean']==20
    exact=joint.prepare(20,30,10,10,1,5,True,2)
    near=joint.prepare(20,30,10,10,math.nextafter(1.,0.),5,True,2)
    assert exact['gap_sd']==0 and near['gap_sd']>0
    assert exact['analytic_realized_variance']==125
    assert exact['analytic_realized_correlation']==1


def fixture(actual=20,maximum=30):
    source=snapshot();source['weeks']=source['weeks'][:1]
    for t in source['teams']:
        t.update(actual_history=['10','30'],points_for='40',points_against='40',maxpf='40')
    for detail in source['weeks'][0]['teams'].values():
        detail['actual']['points']=str(actual);detail['maxpf']['points']=str(maximum)
    cfg=config();cfg.update(iterations=30000,residual_correlation=0)
    return source,cfg


def test_nonzero_gap_realized_mean_variance_and_correlation_match_analytic_model():
    source,cfg=fixture();result=simulation.simulate(source,cfg)
    for t in result['teams']:
        d=t['weeks'][0]['maxpf_floor']
        assert d['policy']==joint.POLICY and d['latent_maxpf_mean']<d['target_mean']==30
        assert abs(d['simulated_mean']-30)<6*d['simulated_mean_standard_error']+.005
        assert math.isclose(d['analytic_unrounded_mean'],30,abs_tol=1e-9)
        assert abs(d['simulated_maxpf_variance']/d['analytic_realized_variance']-1)<.05
        assert abs(d['simulated_correlation']-d['analytic_realized_correlation'])<.03


def test_rounding_bound_is_explicit_for_deterministic_subcent_means():
    source,cfg=fixture(20.003,20.006)
    cfg.update(iterations=100,score_sd=0)
    result=simulation.simulate(source,cfg)
    for t in result['teams']:
        d=t['weeks'][0]['maxpf_floor']
        assert abs(d['simulated_mean']-20.006)<=d['rounding_mean_error_bound']+1e-12
        assert d['analytic_realized_variance']==0
        assert d['simulated_correlation'] is None


@pytest.mark.parametrize('maximum,rho',[(20,0),(30,0),(30,1)])
def test_actual_outcomes_keep_identical_rng_path_to_unshifted_floor(monkeypatch,maximum,rho):
    source,cfg=fixture(maximum=maximum);cfg.update(iterations=2000,residual_correlation=rho)
    new=simulation.simulate(source,cfg)
    prepare=joint.prepare
    def legacy(*args):
        result=prepare(*args)
        return {**result,'construction':'legacy_floor_reference','latent_mean_shift':0}
    monkeypatch.setattr(joint,'prepare',legacy)
    old=simulation.simulate(deepcopy(source),cfg)
    for a,b in zip(new['teams'],old['teams']):
        for key in ('expected_record','final_record_distribution','playoff_probability','bye_probability'):
            assert a[key]==b[key]
        for x,y in zip(a['weeks'],b['weeks']):
            for key in ('win_probability','loss_probability','tie_probability'):
                assert x[key]==y[key]
            assert x['maxpf_floor']['simulated_actual_mean']==y['maxpf_floor']['simulated_actual_mean']


def test_diagnostic_variance_survives_large_location_small_variance():
    source,cfg=fixture(9e6,9e6+.5)
    cfg.update(iterations=10000,score_sd=.125,score_decimals=3)  # variance .015625 at a 9e6 location
    result=simulation.simulate(source,cfg)
    for t in result['teams']:
        d=t['weeks'][0]['maxpf_floor']
        assert .01<d['simulated_actual_variance']<.03
        assert .01<d['simulated_maxpf_variance']<.03
        assert abs(d['simulated_maxpf_variance']/d['analytic_realized_variance']-1)<.08
        assert d['simulated_mean_standard_error']>0


def test_large_positive_gap_does_not_cancel_analytic_variance():
    value=joint.prepare(0,1e10,.1,.2,.3,0,True,3)
    assert math.isclose(value['analytic_realized_variance'],.04,rel_tol=1e-12)
    assert math.isclose(value['analytic_realized_correlation'],.3,rel_tol=1e-12)
