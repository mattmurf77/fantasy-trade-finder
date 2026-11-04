"""F8 — calibration module: reliability tables by predicted-probability
decile for probability-emitting scorers (the F6 consumer).

A scorer that implements `predict_proba(card) -> float in [0,1]` can be
checked here: bin its predictions into fixed-width deciles, compare the
mean predicted probability against the observed outcome rate per bin, and
summarize with ECE (expected calibration error, bin-weight-averaged |gap|).

Inclusion mirrors replay.py: viewed, not undo-reversed, valid propensity,
scorer inputs present (features_json or the compact block) — calibration
is about labels, and only viewed cards have honest labels (the F2 cascade
rule). Unlike replay there are no ranks here, so a card with neither is
excluded on its own as bad_features rather than taking its deck out, and
a card from a partial run (evidence_tier 'partial_run') is excluded on
its own as partial_run. Every card of a deck the loader excluded
(LoggedDeck.exclusion: calibration_refresh, pack_integrity,
withdrawal_conflict, in_flight, incomplete_deck, no_delivery_evidence,
partner_redacted) is excluded under that reason. A partner_redacted deck
holds a card whose blended scores the deletion scrub nulled, which a scorer
would read as 0 (models-lead addendum J1); a calibration read reports the
excluded share of its window (data.partner_redacted_share), and above
data.PARTNER_REDACTED_GATE_PCT % one used for a gate goes to models-lead
before it's used. calibration_refresh is checked first, ahead of
partial_run, as in replay: the deck was never shown in Trades. A recorded
never-delivered withdrawal was removed by the loader, so it is no card
here and is never counted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.eval.data import CALIBRATION_REFRESH, PARTIAL_RUN_TIER, LoggedDeck, card_dict

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
    over the included impressions. Returns (pairs, excluded_counts) — the
    per-card reasons and precedence of replay.py, with per-card
    bad_features and partial_run where replay excludes the whole deck;
    printed by callers."""
    if not hasattr(scorer, "predict_proba"):
        raise ValueError(
            f"scorer {getattr(scorer, 'name', scorer)!r} has no predict_proba(); "
            "calibration applies only to probability-emitting scorers")
    excluded = {"calibration_refresh": 0,
                "partial_run": 0, "in_flight": 0, "pack_integrity": 0,
                "withdrawal_conflict": 0, "incomplete_deck": 0,
                "no_delivery_evidence": 0, "partner_redacted": 0,
                "null_propensity": 0, "never_viewed": 0,
                "undo_reversed": 0, "bad_features": 0, "scorer_error": 0}
    pairs: list[tuple[float, float]] = []
    for deck in decks:
        for c in deck.cards:
            if deck.exclusion == CALIBRATION_REFRESH:
                excluded[CALIBRATION_REFRESH] += 1
                continue
            if c.evidence_tier == PARTIAL_RUN_TIER:
                excluded["partial_run"] += 1
                continue
            if deck.exclusion is not None:
                excluded[deck.exclusion] += 1
                continue
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
            if c.features is None and c.features_compact is None:
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
