"""analytics_stats.py — the experiment statistics engine (analytics platform
P3, LLD §4.5 / FR-42–46). PURE functions: no Flask, no DB, no scipy/numpy
imports (stdlib `math` only), so it is trivially unit-testable to 1e-9 against
scipy-generated golden vectors (backend/tests/fixtures/stats_golden.json,
regenerated offline by tools/gen_stats_golden.py — scipy never ships).

Why hand-rolled (OQ-10, decided): the N6 anti-hand-rolling principle targets
statistical *design* wrongness (mSPRT) that no unit test can catch. These are
the opposite — pure float→float special functions with independently generated
truth tables. scipy+numpy would cost seconds of cold start and ~150 MB RSS on
Render's 512 MB instance for four functions we can verify exactly.

Design-time: power/duration calculator with the mandatory beta-honesty banner.
Read-time: two-proportion z / Welch's t (p99-winsorized upstream), 95% CIs,
Bonferroni, χ² SRM. Fixed-horizon only; mSPRT deferred to v2 (N6/OQ-8).
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Special functions (stdlib math only)
# ---------------------------------------------------------------------------

_SQRT2 = math.sqrt(2.0)


def norm_cdf(x: float) -> float:
    """Standard normal CDF Φ(x) via the stdlib error function."""
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


# Acklam's inverse-normal rational approximation, |abs err| < 1.15e-9 after one
# Halley refinement (which uses norm_cdf + the pdf).
_A = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
      1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
_B = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
      6.680131188771972e+01, -1.328068155288572e+01)
_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
      -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
      3.754408661907416e+00)
_PLOW = 0.02425
_PHIGH = 1.0 - _PLOW


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (quantile). p in (0,1)."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    if p < _PLOW:
        q = math.sqrt(-2.0 * math.log(p))
        x = (((((_C[0]*q+_C[1])*q+_C[2])*q+_C[3])*q+_C[4])*q+_C[5]) / \
            ((((_D[0]*q+_D[1])*q+_D[2])*q+_D[3])*q+1.0)
    elif p <= _PHIGH:
        q = p - 0.5
        r = q*q
        x = (((((_A[0]*r+_A[1])*r+_A[2])*r+_A[3])*r+_A[4])*r+_A[5])*q / \
            (((((_B[0]*r+_B[1])*r+_B[2])*r+_B[3])*r+_B[4])*r+1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        x = -(((((_C[0]*q+_C[1])*q+_C[2])*q+_C[3])*q+_C[4])*q+_C[5]) / \
            ((((_D[0]*q+_D[1])*q+_D[2])*q+_D[3])*q+1.0)
    # One Halley step against the true CDF for full double precision.
    e = norm_cdf(x) - p
    u = e * math.sqrt(2.0 * math.pi) * math.exp(x*x / 2.0)
    x = x - u / (1.0 + x*u/2.0)
    return x


_MAXIT = 200
_EPS = 1e-12
_FPMIN = 1e-300


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (Lentz), Numerical Recipes."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, _MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < _EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a,b) ∈ [0,1]. The Student-t / F CDF core."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _gamma_series(s: float, x: float) -> float:
    """Lower regularized incomplete gamma P(s,x) via series (x < s+1)."""
    if x <= 0.0:
        return 0.0
    ap = s
    term = 1.0 / s
    total = term
    for _ in range(_MAXIT):
        ap += 1.0
        term *= x / ap
        total += term
        if abs(term) < abs(total) * _EPS:
            break
    return total * math.exp(-x + s * math.log(x) - math.lgamma(s))


def _gamma_cf(s: float, x: float) -> float:
    """Upper regularized incomplete gamma Q(s,x) via continued fraction (x ≥ s+1)."""
    b = x + 1.0 - s
    c = 1.0 / _FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, _MAXIT + 1):
        an = -i * (i - s)
        b += 2.0
        d = an * d + b
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = b + an / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < _EPS:
            break
    return math.exp(-x + s * math.log(x) - math.lgamma(s)) * h


def gammainc_lower(s: float, x: float) -> float:
    """Lower regularized incomplete gamma P(s,x) = γ(s,x)/Γ(s) ∈ [0,1]."""
    if x <= 0.0 or s <= 0.0:
        return 0.0
    if x < s + 1.0:
        return _gamma_series(s, x)
    return 1.0 - _gamma_cf(s, x)


def chi2_sf(x: float, k: int) -> float:
    """χ² survival function P(X > x) for k degrees of freedom."""
    if x <= 0.0:
        return 1.0
    return 1.0 - gammainc_lower(k / 2.0, x / 2.0)


def t_sf_two_sided(t: float, df: float) -> float:
    """Two-sided p-value for a Student-t statistic: P(|T| > |t|)."""
    if df <= 0.0:
        return float("nan")
    x = df / (df + t * t)
    return betainc(df / 2.0, 0.5, x)   # == regularized I_x(df/2, 1/2)


# ---------------------------------------------------------------------------
# Read-time tests
# ---------------------------------------------------------------------------

def two_proportion_z(x1: int, n1: int, x2: int, n2: int, alpha: float = 0.05):
    """Two-proportion z-test. Pooled p for the z statistic; UNpooled SE for the
    CI on the absolute lift (p2 − p1). Returns a dict with z, two-sided p, the
    lift and its 95% CI, and per-arm rates."""
    if n1 <= 0 or n2 <= 0:
        return {"error": "empty_arm"}
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se_pool = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se_pool if se_pool > 0 else 0.0
    p_value = 2.0 * (1.0 - norm_cdf(abs(z)))
    se_unpooled = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    zc = norm_ppf(1 - alpha / 2)
    lift = p2 - p1
    return {
        "test": "two_proportion_z",
        "p1": p1, "p2": p2, "z": z, "p_value": p_value,
        "lift_abs": lift,
        "lift_rel": (lift / p1) if p1 > 0 else None,
        "ci95": [lift - zc * se_unpooled, lift + zc * se_unpooled],
    }


def welch_t(mean1: float, var1: float, n1: int,
            mean2: float, var2: float, n2: int, alpha: float = 0.05):
    """Welch's unequal-variance t-test on continuous (p99-winsorized upstream)
    values. Returns t, Welch–Satterthwaite df, two-sided p, mean diff + CI."""
    if n1 < 2 or n2 < 2:
        return {"error": "insufficient_n"}
    s1, s2 = var1 / n1, var2 / n2
    se = math.sqrt(s1 + s2)
    if se == 0:
        return {"error": "zero_variance"}
    t = (mean2 - mean1) / se
    df = (s1 + s2) ** 2 / (s1 ** 2 / (n1 - 1) + s2 ** 2 / (n2 - 1))
    p_value = t_sf_two_sided(t, df)
    # t critical via the inverse of the two-sided tail: approximate with the
    # normal z for the CI half-width when df is large; for small df we bisect.
    tc = _t_ppf_two_sided(1 - alpha, df)
    diff = mean2 - mean1
    return {"test": "welch_t", "t": t, "df": df, "p_value": p_value,
            "mean_diff": diff, "ci95": [diff - tc * se, diff + tc * se]}


def _t_ppf_two_sided(conf: float, df: float) -> float:
    """Critical t for a two-sided interval at confidence `conf` (e.g. 0.95),
    by bisection on t_sf_two_sided (monotone in t)."""
    target = 1.0 - conf   # desired two-sided tail
    lo, hi = 0.0, 100.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if t_sf_two_sided(mid, df) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def srm_check(observed: list[int], weights_bp: list[int], p_crit: float = 0.001):
    """Sample-ratio-mismatch χ² over arms. `weights_bp` are the intended
    allocation in basis points (sum 10000). Returns χ², df, p, and whether it
    trips the red banner (p < p_crit → suppress the verdict)."""
    total = sum(observed)
    wsum = sum(weights_bp)
    if total <= 0 or wsum <= 0 or len(observed) != len(weights_bp):
        return {"chi2": None, "df": None, "p_value": None, "red": False}
    chi2 = 0.0
    for obs, w in zip(observed, weights_bp):
        exp = total * (w / wsum)
        if exp > 0:
            chi2 += (obs - exp) ** 2 / exp
    df = len(observed) - 1
    p = chi2_sf(chi2, df) if df > 0 else 1.0
    return {"chi2": chi2, "df": df, "p_value": p, "red": p < p_crit}


def bonferroni(alpha: float, m: int) -> float:
    """Bonferroni-adjusted α for m comparisons (arms−1 or primary-eligible
    metrics, whichever the caller passes)."""
    return alpha / max(m, 1)


# ---------------------------------------------------------------------------
# Design-time power / duration (FR-42)
# ---------------------------------------------------------------------------

def power_n_per_arm(p_baseline: float, mde: float,
                    alpha: float = 0.05, power: float = 0.80) -> int:
    """Per-arm sample size for a two-proportion test to detect an ABSOLUTE
    effect `mde` on a baseline rate `p_baseline`. n = 2·(z_{1−α/2}+z_{1−β})²·
    p̄(1−p̄) / mde² with p̄ = the average of the two arms' assumed rates."""
    if mde <= 0 or not (0 < p_baseline < 1):
        return 0
    p2 = min(max(p_baseline + mde, 1e-6), 1 - 1e-6)
    p_bar = (p_baseline + p2) / 2
    z = norm_ppf(1 - alpha / 2) + norm_ppf(power)
    n = 2.0 * z * z * p_bar * (1 - p_bar) / (mde * mde)
    return int(math.ceil(n))


def design_calculator(p_baseline: float, mde: float, arms: int,
                      eligible_per_week: float,
                      alpha: float = 0.05, power: float = 0.80) -> dict:
    """The self-service design tool (FR-42): required n/arm, predicted weeks at
    current eligible traffic, MDE achievable in 2/4/8 weeks, and the mandatory
    beta-honesty banner. `underpowered` when the horizon exceeds 26 weeks —
    launch then requires an explicit override."""
    n_arm = power_n_per_arm(p_baseline, mde, alpha, power)
    per_week = max(eligible_per_week, 1e-9)
    predicted_weeks = (n_arm * arms) / per_week if n_arm else None

    def mde_in_weeks(w):
        n_avail = (per_week * w) / arms   # per-arm n available in w weeks
        if n_avail < 2:
            return None
        z = norm_ppf(1 - alpha / 2) + norm_ppf(power)
        p_bar = p_baseline
        # invert n = 2 z² p̄(1−p̄)/mde²  →  mde = sqrt(2 z² p̄(1−p̄)/n)
        return math.sqrt(2.0 * z * z * p_bar * (1 - p_bar) / n_avail)

    underpowered = predicted_weeks is not None and predicted_weeks > 26
    banner = (
        f"At {eligible_per_week:.0f} eligible units/week, detecting an MDE of "
        f"{mde:.3f} on a {p_baseline:.3f} baseline needs ~{n_arm:,}/arm "
        f"(~{predicted_weeks:.0f} weeks). "
        + ("UNDERPOWERED at beta scale — consider a bigger swing, a coarser "
           "metric, or ship-and-watch; launching requires an explicit "
           "override." if underpowered else "Within a reasonable horizon.")
    )
    return {
        "n_per_arm": n_arm,
        "arms": arms,
        "eligible_per_week": eligible_per_week,
        "predicted_weeks": predicted_weeks,
        "mde_at": {"2w": mde_in_weeks(2), "4w": mde_in_weeks(4), "8w": mde_in_weeks(8)},
        "underpowered": underpowered,
        "banner": banner,
    }
