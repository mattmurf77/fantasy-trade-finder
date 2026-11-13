"""Pure statistics for the Max PF moves leave-one-out backtest. Standard library only.

Nothing here reads files, the network or the clock. A *pair* is (predicted, realised).
Intervals come from resampling whole leagues with replacement (`bootstrap`).
"""
from __future__ import annotations

import math
import random


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def rankdata(values):
    """Average ranks (1-based), ties share the mean of their positions."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
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
    """Rank correlation with average ranks for ties; None when either side is constant."""
    return pearson(rankdata(list(x)), rankdata(list(y)))


def summary(pairs):
    """Calibration of predicted against realised: bias is predicted minus realised
    (positive = the prediction is too large)."""
    pairs = list(pairs)
    if not pairs:
        return {"n": 0}
    pred = [p for p, _ in pairs]
    real = [r for _, r in pairs]
    return {"n": len(pairs), "mean_predicted": mean(pred), "mean_realised": mean(real),
            "bias": mean(p - r for p, r in pairs), "mae": mean(abs(p - r) for p, r in pairs),
            "rmse": math.sqrt(mean((p - r) ** 2 for p, r in pairs)),
            "spearman": spearman(pred, real),
            "realised_over_predicted": (sum(real) / sum(pred)) if sum(pred) else None}


def bucket_of(value, edges):
    """Index of the bucket for `value`. `edges` are ascending upper bounds of
    half-open buckets; bucket 0 is exactly 0 (and below), the last is open-ended.
    edges=(2, 5) gives buckets: <=0, (0, 2], (2, 5], > 5."""
    if value <= 0:
        return 0
    for i, edge in enumerate(edges):
        if value <= edge:
            return i + 1
    return len(edges) + 1


def bucket_labels(edges):
    labels = ["0"]
    low = 0
    for edge in edges:
        labels.append(f"{low:g}-{edge:g}")
        low = edge
    labels.append(f">{low:g}")
    return labels


def calibration_table(pairs, edges):
    """Per predicted-drop bucket: count, mean predicted, mean realised, share of
    realised <= 0, share of realised < 0 (wrong sign)."""
    groups = [[] for _ in range(len(edges) + 2)]
    for p, r in pairs:
        groups[bucket_of(p, edges)].append((p, r))
    out = []
    for label, group in zip(bucket_labels(edges), groups):
        out.append({"bucket": label, "n": len(group),
                    "mean_predicted": mean(p for p, _ in group), "mean_realised": mean(r for _, r in group),
                    "share_realised_zero_or_less": mean(r <= 0 for _, r in group),
                    "share_realised_negative": mean(r < 0 for _, r in group)})
    return out


def top_k(scores, k):
    """Top k keys by score, ties broken by key (the product's order: -drop, then id)."""
    return [key for key, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def list_agreement(predicted, realised, k=5):
    """One roster's list: overlap of the top k, rank correlation over every
    player, and whether the predicted #1 is in the realised top 3."""
    pred_top, real_top = top_k(predicted, k), top_k(realised, k)
    keys = sorted(predicted)
    return {"overlap": len(set(pred_top) & set(real_top)),
            "spearman": spearman([predicted[x] for x in keys], [realised[x] for x in keys]),
            "first_in_real_top3": bool(pred_top) and pred_top[0] in top_k(realised, 3)}


def interval(values, level=.95):
    values = sorted(v for v in values if v is not None)
    if not values:
        return [None, None]
    low = values[int((1 - level) / 2 * (len(values) - 1))]
    high = values[int(math.ceil((1 + level) / 2 * (len(values) - 1)))]
    return [low, high]


def bootstrap(groups, statistic, reps=1000, seed=7):
    """Resample whole leagues with replacement. `groups` is a list of per-league
    row lists; `statistic(rows)` returns a dict of numbers (None allowed).
    Returns {key: {"value": full-data value, "ci95": [low, high]}}."""
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
