"""analytics_stats.py — verify the hand-rolled special functions + tests match
scipy to 1e-9 against committed golden vectors (backend/tests/fixtures/
stats_golden.json, regenerated offline by backend/tools/gen_stats_golden.py).
scipy is NOT a runtime dependency — these fixtures ARE the oracle.
"""
import json
import os

import pytest

import backend.analytics_stats as s

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "stats_golden.json")
with open(_FIX) as f:
    G = json.load(f)

TOL = 1e-9


@pytest.mark.parametrize("x,exp", G["norm_cdf"])
def test_norm_cdf(x, exp):
    assert abs(s.norm_cdf(x) - exp) < TOL


@pytest.mark.parametrize("p,exp", G["norm_ppf"])
def test_norm_ppf(p, exp):
    assert abs(s.norm_ppf(p) - exp) < 1e-8   # Acklam+Halley: ~1e-14, budget 1e-8


@pytest.mark.parametrize("a,b,x,exp", G["betainc"])
def test_betainc(a, b, x, exp):
    assert abs(s.betainc(a, b, x) - exp) < TOL


@pytest.mark.parametrize("sp,x,exp", G["gammainc_lower"])
def test_gammainc_lower(sp, x, exp):
    assert abs(s.gammainc_lower(sp, x) - exp) < TOL


@pytest.mark.parametrize("x,k,exp", G["chi2_sf"])
def test_chi2_sf(x, k, exp):
    assert abs(s.chi2_sf(x, k) - exp) < TOL


@pytest.mark.parametrize("t,df,exp", G["t_sf_two_sided"])
def test_t_two_sided(t, df, exp):
    assert abs(s.t_sf_two_sided(t, df) - exp) < TOL


@pytest.mark.parametrize("x1,n1,x2,n2,z,p", G["two_proportion_z"])
def test_two_proportion_z(x1, n1, x2, n2, z, p):
    r = s.two_proportion_z(x1, n1, x2, n2)
    assert abs(r["z"] - z) < TOL and abs(r["p_value"] - p) < TOL


@pytest.mark.parametrize("m1,v1,n1,m2,v2,n2,t,df,p", G["welch_t"])
def test_welch_t(m1, v1, n1, m2, v2, n2, t, df, p):
    r = s.welch_t(m1, v1, n1, m2, v2, n2)
    assert abs(r["t"] - t) < TOL and abs(r["df"] - df) < TOL and abs(r["p_value"] - p) < TOL


@pytest.mark.parametrize("obs,w,chi2,df,p", G["srm"])
def test_srm(obs, w, chi2, df, p):
    r = s.srm_check(obs, w)
    assert abs(r["chi2"] - chi2) < TOL and abs(r["p_value"] - p) < TOL


def test_srm_red_banner_on_gross_mismatch():
    # 600/400 vs intended 50/50 with n=1000 → χ²=40 → p≪.001 → red.
    r = s.srm_check([600, 400], [5000, 5000])
    assert r["red"] is True
    # Balanced split → not red.
    assert s.srm_check([505, 495], [5000, 5000])["red"] is False


def test_design_calculator_beta_honesty():
    # 5-pt lift on 30% baseline at 40 eligible/week is deeply underpowered.
    d = s.design_calculator(0.30, 0.05, 2, 40)
    assert d["n_per_arm"] > 1000
    assert d["predicted_weeks"] > 26
    assert d["underpowered"] is True
    assert "UNDERPOWERED" in d["banner"]
    # A coarse metric with lots of traffic is fine.
    d2 = s.design_calculator(0.30, 0.10, 2, 2000)
    assert d2["underpowered"] is False


def test_bonferroni():
    assert s.bonferroni(0.05, 3) == pytest.approx(0.05 / 3)
    assert s.bonferroni(0.05, 1) == 0.05   # max(m,1)


def test_no_scipy_import():
    # The shipped module must not import scipy/numpy (cold-start + RSS budget).
    import backend.analytics_stats as mod
    src = open(mod.__file__).read()
    assert "import scipy" not in src and "import numpy" not in src
