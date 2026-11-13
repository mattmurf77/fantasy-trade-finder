"""Pure statistics for the score-spread study. Standard library only.

Nothing here reads files, the network or the clock. A *game* is a tuple
``(d, ba, bb, y)``: ``d`` is team a's projection minus team b's, ``ba`` and
``bb`` are the two teams' spread *bases* and ``y`` is 1 if team a won, else 0.
A model with scale ``s`` gives team a the win probability
``Phi(d / (s * sqrt(ba + bb)))``. With both bases 1 the scale is the product's
flat weekly SD; with bases equal to a lineup's summed player variances the
scale is a multiplier on the independent-player spread.
"""
from __future__ import annotations

import math

BUCKET_EDGES = (5, 10, 15, 20, 25)
BUCKET_LABELS = ("<5", "5-10", "10-15", "15-20", "20-25", "25+")


def phi(z):
    """Standard normal CDF."""
    return .5 * math.erfc(-z / math.sqrt(2))


def bucket(points, edges=BUCKET_EDGES):
    """Index of the projected-points bucket (values below the first edge, negatives included, are 0)."""
    for i, edge in enumerate(edges):
        if points < edge:
            return i
    return len(edges)


def win_probability(game, scale):
    d, ba, bb, _ = game
    spread = scale * math.sqrt(ba + bb)
    if spread <= 0:
        return 1. if d > 0 else 0. if d < 0 else .5
    return phi(d / spread)


def log_likelihood(games, scale):
    total = 0.
    for game in games:
        p = min(1 - 1e-12, max(1e-12, win_probability(game, scale)))
        total += math.log(p) if game[3] else math.log(1 - p)
    return total


def fit_scale(games, low, high, tol=1e-3):
    """Scale in [low, high] maximizing the head-to-head log likelihood (golden section on log scale).

    The likelihood of a probit model in 1/scale is concave, so it is unimodal in scale.
    """
    if not games:
        raise ValueError("no games")
    a, b = math.log(low), math.log(high)
    g = (math.sqrt(5) - 1) / 2
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = log_likelihood(games, math.exp(c)), log_likelihood(games, math.exp(d))
    while b - a > tol:
        if fc > fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = log_likelihood(games, math.exp(c))
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = log_likelihood(games, math.exp(d))
    return math.exp((a + b) / 2)


def wilson(wins, n, z=1.959964):
    if not n:
        return [None, None]
    p = wins / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [centre - half, centre + half]


def reliability(games, scale, bins=5):
    """Favourite-side reliability: model probability bands of width 0.1 from 0.5 up."""
    table = [[0, 0, 0.] for _ in range(bins)]
    for game in games:
        p = win_probability(game, scale)
        q, won = (p, game[3]) if p >= .5 else (1 - p, 1 - game[3])
        k = min(bins - 1, int((q - .5) * 10))
        table[k][0] += 1
        table[k][1] += won
        table[k][2] += q
    out = []
    for k, (n, w, q) in enumerate(table):
        if n:
            out.append({"model_says": [round(.5 + k / 10, 1), round(.6 + k / 10, 1)], "games": n,
                        "mean_model_probability": q / n, "favourite_won": w / n, "wilson_95": wilson(w, n)})
    return out


def moments(n, total, squares):
    """Mean, SD about the mean (n-1) and root mean square from running sums."""
    if n < 2:
        return {"n": n}
    mean = total / n
    var = max(0., (squares - n * mean * mean) / (n - 1))
    return {"n": n, "mean": mean, "sd": math.sqrt(var), "rmse": math.sqrt(squares / n)}


def variance_components(groups):
    """Unbalanced one-way random-effects split from (n, sum, sum of squares) per group.

    Returns the within-group variance (noise around a group's own mean), the
    between-group variance (how much group means truly differ: a persistent
    bias) and the between share. Groups with n < 2 are ignored.
    """
    groups = [g for g in groups if g[0] >= 2]
    k = len(groups)
    if k < 2:
        return None
    big_n = sum(g[0] for g in groups)
    grand = sum(g[1] for g in groups) / big_n
    ssw = sum(s2 - s * s / n for n, s, s2 in groups)
    ssb = sum(n * (s / n - grand) ** 2 for n, s, _ in groups)
    msw, msb = ssw / (big_n - k), ssb / (k - 1)
    n0 = (big_n - sum(n * n for n, _, _ in groups) / big_n) / (k - 1)
    between = (msb - msw) / n0
    total = msw + max(0., between)
    return {"groups": k, "observations": big_n, "within_var": msw, "between_var": between,
            "between_share": max(0., between) / total if total else None}


def implied_correlation(team_var, player_vars):
    """Average pairwise correlation that turns independent player variances into the team variance.

    team_var = sum(v) + rho * sum_{i != j} sqrt(v_i v_j), solved for rho.
    """
    sds = [math.sqrt(v) for v in player_vars]
    cross = sum(sds) ** 2 - sum(player_vars)
    return (team_var - sum(player_vars)) / cross if cross > 0 else None


def correlation(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else None


def interval(values, level=.95):
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return [None, None]
    lo = ordered[int((1 - level) / 2 * (len(ordered) - 1))]
    hi = ordered[int((1 - (1 - level) / 2) * (len(ordered) - 1))]
    return [lo, hi]


def window_moments(windows):
    """Running sums (count, step sums, step cross-products) of equal-length error sequences; they add across groups."""
    k = len(windows[0]) if windows else 0
    sums, cross = [0.] * k, [[0.] * k for _ in range(k)]
    for w in windows:
        for i in range(k):
            sums[i] += w[i]
            row = cross[i]
            for j in range(k):
                row[j] += w[i] * w[j]
    return len(windows), sums, cross


def add_moments(parts):
    n, sums, cross = 0, None, None
    for pn, ps, pc in parts:
        if sums is None:
            sums, cross = [0.] * len(ps), [[0.] * len(ps) for _ in ps]
        n += pn
        for i in range(len(ps)):
            sums[i] += ps[i]
            for j in range(len(ps)):
                cross[i][j] += pc[i][j]
    return n, sums, cross


def window_stats_from_moments(n, sums, cross):
    """Covariance structure of equal-length error sequences (one per team and forecast origin).

    Returns the variance at each step, the step-by-step covariance matrix, the mean
    off-diagonal covariance, and the variance of the window sum over the sum of the
    step variances (1 = independent steps; above 1 = misses persist).
    """
    if n < 2:
        return {"windows": n}
    k = len(sums)
    cov = [[(cross[i][j] - sums[i] * sums[j] / n) / (n - 1) for j in range(k)] for i in range(k)]
    variances = [cov[i][i] for i in range(k)]
    off = [cov[i][j] for i in range(k) for j in range(k) if i != j]
    total = sum(sum(row) for row in cov)
    return {"windows": n, "steps": k, "variance_by_step": variances, "covariance": cov,
            "mean_offdiagonal_covariance": sum(off) / len(off) if off else 0.,
            "sum_variance_ratio": total / sum(variances)}


def window_stats(windows):
    return window_stats_from_moments(*window_moments(windows))
