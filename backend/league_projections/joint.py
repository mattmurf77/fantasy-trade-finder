"""Mean-preserving positive-gap normal policy; not an accuracy calibration.

The actual score remains Gaussian. A shifted correlated latent Max PF score is
floored at actual while preserving the requested *unrounded* Max PF mean.
"""
import math
from .core import Unavailable

POLICY = "mean_preserving_positive_gap_v1"


def positive_normal_mean(mean, sd):
    if sd == 0:
        return max(0., mean)
    a = mean / sd
    return sd * (math.exp(-a * a / 2) / math.sqrt(2 * math.pi) + a * .5 * math.erfc(-a / math.sqrt(2)))


def latent_gap_mean(delta, sd):
    """Solve once per team/week; zero target has no finite Gaussian solution."""
    if not all(math.isfinite(v) for v in (delta, sd)) or min(delta, sd) < 0:
        raise Unavailable("infeasible_maxpf_mean_or_scale")
    if delta == 0:
        return None
    if sd == 0:
        return delta
    ratio = delta / sd
    low, high = -1., max(1., ratio)
    while positive_normal_mean(low, 1.) > ratio:
        low *= 2
    for _ in range(160):
        middle = low + (high - low) / 2
        if middle in (low, high):
            break
        if positive_normal_mean(middle, 1.) < ratio:
            low = middle
        else:
            high = middle
    return sd * (low + (high - low) / 2)


def _correlation(covariance, variance_a, variance_m):
    if variance_a <= 0 or variance_m <= 0:
        return None
    return max(-1., min(1., covariance / math.sqrt(variance_a * variance_m)))


def prepare(actual_mean, maxpf_mean, actual_sd, latent_maxpf_sd, rho, strength_sd, dominance, score_decimals):
    if not all(math.isfinite(v) for v in (actual_mean, maxpf_mean, actual_sd, latent_maxpf_sd, rho, strength_sd)) or min(actual_sd, latent_maxpf_sd, strength_sd) < 0 or not -1 <= rho <= 1:
        raise Unavailable("invalid_joint_distribution")
    variance_a = actual_sd ** 2 + strength_sd ** 2
    variance_latent = latent_maxpf_sd ** 2 + strength_sd ** 2
    latent_covariance = rho * actual_sd * latent_maxpf_sd + strength_sd ** 2
    gap_sd = math.hypot(actual_sd - latent_maxpf_sd, math.sqrt(2 * actual_sd * latent_maxpf_sd * (1 - rho)))
    delta = maxpf_mean - actual_mean
    result = {"policy": POLICY if dominance else "unconstrained_joint_normal_v1", "construction": "unconstrained",
              "target_mean": maxpf_mean, "target_gap": delta, "gap_sd": gap_sd,
              "latent_gap_mean": delta, "latent_maxpf_mean": maxpf_mean, "latent_mean_shift": 0.,
              "configured_actual_variance": variance_a, "configured_latent_maxpf_variance": variance_latent,
              "configured_residual_correlation": rho,
              "configured_latent_total_correlation": _correlation(latent_covariance, variance_a, variance_latent),
              "analytic_realized_variance": variance_latent,
              "analytic_realized_correlation": _correlation(latent_covariance, variance_a, variance_latent),
              "analytic_unrounded_mean": maxpf_mean, "rounding_mean_error_bound": .5 * 10 ** -score_decimals,
              "mean_solver_error": 0., "floating_gap_tolerance": 0.}
    if not dominance:
        return result
    # Almost-sure dominance cannot have a smaller target mean.
    if delta < 0:
        raise Unavailable("maxpf_target_below_actual_mean", details={"target_gap": delta})
    gap_mean = latent_gap_mean(delta, gap_sd)
    result.update(target_gap=delta, latent_gap_mean=gap_mean)
    if gap_mean is None:
        result.update(construction="actual_equals_maxpf", latent_maxpf_mean=None, latent_mean_shift=None,
                      analytic_unrounded_mean=actual_mean, analytic_realized_variance=variance_a,
                      analytic_realized_correlation=1. if variance_a else None,
                      mean_solver_error=actual_mean - maxpf_mean)
        return result
    result.update(construction="deterministic_gap" if gap_sd == 0 else "positive_normal_gap",
                  latent_maxpf_mean=actual_mean + gap_mean, latent_mean_shift=gap_mean - delta)
    probability = 1. if gap_sd == 0 else .5 * math.erfc(-gap_mean / gap_sd / math.sqrt(2))
    expected_gap = positive_normal_mean(gap_mean, gap_sd)
    if gap_sd == 0:
        variance_gap = 0.
    else:
        # Algebraically centered rectified-normal variance; avoid subtracting
        # two gap_mean² terms when the positive gap dwarfs its uncertainty.
        a = gap_mean / gap_sd
        density = math.exp(-.5 * a * a) / math.sqrt(2 * math.pi)
        survival = .5 * math.erfc(a / math.sqrt(2))
        variance_gap = gap_sd ** 2 * max(0., probability - density ** 2
                       + a * density * (1 - 2 * probability) + a * a * probability * survival)
    covariance_actual_gap = (rho * actual_sd * latent_maxpf_sd - actual_sd ** 2) * probability
    variance_m = max(0., variance_a + variance_gap + 2 * covariance_actual_gap)
    result.update(analytic_unrounded_mean=actual_mean + expected_gap,
                  mean_solver_error=actual_mean + expected_gap - maxpf_mean,
                  analytic_realized_variance=variance_m,
                  analytic_realized_correlation=_correlation(variance_a + covariance_actual_gap, variance_a, variance_m))
    return result
