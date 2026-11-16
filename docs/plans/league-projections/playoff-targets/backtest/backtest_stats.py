"""Pure statistics for the Playoff targets backtest. Standard library only.

Nothing here reads files, the network or the clock. A *pair* is (predicted,
realised). Intervals come from resampling whole league-seasons with
replacement (`bootstrap`).
"""
from __future__ import annotations

import math
import random


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def sd(values):
    values = list(values)
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def rankdata(values):
    """Average ranks (1-based); ties share the mean of their positions."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def pearson(x, y):
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if not sxx or not syy:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sxx * syy)


def spearman(x, y):
    """Rank correlation with average ranks; None when either side is constant."""
    return pearson(rankdata(list(x)), rankdata(list(y)))


def summary(pairs):
    """Predicted against realised. Bias is predicted minus realised (positive =
    the shown number is too large)."""
    pairs = list(pairs)
    if not pairs:
        return {"n": 0}
    pred = [p for p, _ in pairs]
    real = [r for _, r in pairs]
    return {"n": len(pairs), "mean_predicted": mean(pred), "mean_realised": mean(real),
            "bias": mean(p - r for p, r in pairs), "mae": mean(abs(p - r) for p, r in pairs),
            "spearman": spearman(pred, real),
            "realised_over_predicted": (sum(real) / sum(pred)) if sum(pred) else None,
            "share_realised_zero_or_less": mean(r <= 0 for r in real)}


def bin_labels(edges):
    labels = [f"<{edges[0]:g}"]
    for low, high in zip(edges, edges[1:]):
        labels.append(f"{low:g}-{high:g}")
    labels.append(f">={edges[-1]:g}")
    return labels


def bin_of(value, edges):
    """Half-open bins: (-inf, e0), [e0, e1), ..., [e_last, inf)."""
    for i, edge in enumerate(edges):
        if value < edge:
            return i
    return len(edges)


def binned(rows, key, edges):
    """[(label, rows in that bin of row[key])] for every bin, empty ones included."""
    groups = [[] for _ in range(len(edges) + 1)]
    for r in rows:
        groups[bin_of(r[key], edges)].append(r)
    return list(zip(bin_labels(edges), groups))


def brier(pairs):
    """Mean squared difference of a forecast probability and the outcome (0/1)."""
    return mean((p - o) ** 2 for p, o in pairs)


def brier_climatology(outcomes):
    """Brier score of always forecasting the sample's own base rate."""
    outcomes = list(outcomes)
    if not outcomes:
        return None
    m = sum(outcomes) / len(outcomes)
    return mean((o - m) ** 2 for o in outcomes)


def interval(values, level=.95):
    values = sorted(v for v in values if v is not None)
    if not values:
        return [None, None]
    low = values[int((1 - level) / 2 * (len(values) - 1))]
    high = values[int(math.ceil((1 + level) / 2 * (len(values) - 1)))]
    return [low, high]


def bootstrap(groups, statistic, reps=1000, seed=7):
    """Resample whole groups (league-seasons) with replacement. `groups` is a
    list of per-group row lists; `statistic(rows)` returns a dict of numbers
    (None allowed). Returns {key: {"value": full-data value, "ci95": [low, high]}}."""
    full = statistic([row for group in groups for row in group])
    rng = random.Random(seed)
    draws = {key: [] for key, value in full.items() if isinstance(value, (int, float)) or value is None}
    for _ in range(reps):
        rows = []
        for _ in groups:
            rows.extend(groups[rng.randrange(len(groups))])
        result = statistic(rows)
        for key in draws:
            draws[key].append(result.get(key))
    return {key: {"value": full[key], "ci95": interval(draws[key]) if key in draws else None} for key in full}
