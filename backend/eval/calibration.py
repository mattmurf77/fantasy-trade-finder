"""F8 — calibration module: reliability tables by predicted-probability
decile for probability-emitting scorers (the F6 consumer).

A scorer that implements `predict_proba(card) -> float in [0,1]` can be
checked here: bin its predictions into fixed-width deciles, compare the
mean predicted probability against the observed outcome rate per bin, and
summarize with ECE (expected calibration error, bin-weight-averaged |gap|).

Inclusion mirrors replay.py: viewed, not undo-reversed, valid propensity,
parseable features — calibration is about labels, and only viewed cards
have honest labels (the F2 cascade rule).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.eval.data import LoggedDeck, card_dict

N_BINS = 10


@dataclass
class ReliabilityRow:
    bin_index: int          # 0..N_BINS-1
    lo: float               # [lo, hi) — last bin closed at 1.0
    hi: float
    n: int
    mean_predicted: float | None
    observed_rate: float | None
    gap: float | None       # observed - predicted


def reliability_table(
    pairs: list[tuple[float, float]], n_bins: int = N_BINS,
) -> list[ReliabilityRow]:
    """pairs = [(predicted_prob, outcome 0/1), ...] → one row per fixed-width
    bin (empty bins kept, with None stats, so the table is always complete).
    Predictions outside [0,1] raise — a probability scorer emitting them is
    broken and must not be silently binned."""
    bins: list[list[tuple[float, float]]] = [[] for _ in range(n_bins)]
    for p, y in pairs:
        if p is None or not math.isfinite(p) or p < 0.0 or p > 1.0:
            raise ValueError(f"predict_proba emitted a non-probability: {p!r}")
        idx = min(int(p * n_bins), n_bins - 1)   # 1.0 → last bin
        bins[idx].append((p, float(y)))
    rows = []
    for i, bucket in enumerate(bins):
        n = len(bucket)
        mean_p = (sum(p for p, _ in bucket) / n) if n else None
        obs = (sum(y for _, y in bucket) / n) if n else None
        rows.append(ReliabilityRow(
            bin_index=i, lo=i / n_bins, hi=(i + 1) / n_bins,
            n=n, mean_predicted=mean_p, observed_rate=obs,
            gap=(obs - mean_p) if n else None,
        ))
    return rows


def ece(rows: list[ReliabilityRow]) -> float | None:
    """Expected calibration error: Σ (n_bin/N)·|gap|. None on empty input."""
    total = sum(r.n for r in rows)
    if total == 0:
        return None
    return sum((r.n / total) * abs(r.gap) for r in rows if r.n) or 0.0


def calibration_pairs(
    scorer, decks: list[LoggedDeck], metric: str = "like",
) -> tuple[list[tuple[float, float]], dict]:
    """Collect (predicted, outcome) pairs for a probability-emitting scorer
    over the included impressions. Returns (pairs, excluded_counts) — same
    exclusion reasons and precedence as replay.py, printed by callers."""
    if not hasattr(scorer, "predict_proba"):
        raise ValueError(
            f"scorer {getattr(scorer, 'name', scorer)!r} has no predict_proba(); "
            "calibration applies only to probability-emitting scorers")
    excluded = {"null_propensity": 0, "never_viewed": 0,
                "undo_reversed": 0, "bad_features": 0, "scorer_error": 0}
    pairs: list[tuple[float, float]] = []
    for deck in decks:
        for c in deck.cards:
            if (c.propensity is None or not math.isfinite(c.propensity)
                    or c.propensity <= 0):
                excluded["null_propensity"] += 1
                continue
            if not c.viewed:
                excluded["never_viewed"] += 1
                continue
            if c.undone:
                excluded["undo_reversed"] += 1
                continue
            if c.features is None:
                excluded["bad_features"] += 1
                continue
            try:
                p = float(scorer.predict_proba(card_dict(c)))
            except Exception:
                excluded["scorer_error"] += 1
                continue
            y = 1.0 if ((metric == "like" and c.liked)
                        or (metric == "propose" and c.proposed)) else 0.0
            pairs.append((p, y))
    return pairs, excluded


def render_markdown(rows: list[ReliabilityRow]) -> str:
    lines = [
        "| decile | range | n | mean predicted | observed | gap |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        fmt = lambda v: "—" if v is None else f"{v * 100:.2f}%"
        lines.append(
            f"| {r.bin_index + 1} | [{r.lo:.1f}, {r.hi:.1f}) | {r.n} "
            f"| {fmt(r.mean_predicted)} | {fmt(r.observed_rate)} | {fmt(r.gap)} |")
    e = ece(rows)
    lines.append("")
    lines.append(f"ECE: {'—' if e is None else f'{e * 100:.2f}pp'}")
    return "\n".join(lines)
