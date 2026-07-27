"""F8 — replay/IPS evaluator over the F1 propensity logs + operator CLI.

    python3 -m backend.eval.replay --db data/trade_finder.db --scorer base_score
    python3 -m backend.eval.replay --db data/trade_finder.db --self-check

Estimand: the expected like-rate (and propose-rate) among VIEWED cards if
decks had been ordered by a candidate scorer instead of the logged policy.

Estimator — exposure-weighted IPS with a propensity tilt (all modeling
choices explicit; this is an approximate slate OPE, honest about it):

  For each logged deck the candidate scorer re-scores the same cards from
  their frozen features and produces a counterfactual rank. Position drives
  exposure: e(k) = P(viewed | served at position k), estimated empirically
  from the loaded log (Laplace-smoothed, floored — the floor and smoothing
  are printed, never silent). Per included impression:

      w_i = [ e(rank_candidate(i)) / e(rank_logged(i)) ]          exposure shift
            × clip( p̄_deck / p_i , TILT_MIN, TILT_MAX )           propensity tilt

  The tilt uses F1's logged propensity (the Thompson sort-key multiplier
  actually applied, or F7's exploration propensity): cards that reached
  their logged rank on a lucky draw (p_i > deck mean) are down-weighted,
  first-order-correcting the stochastic component of the logged ordering.
  The multiplier is NOT a true probability — the tilt is a documented
  approximation, clipped to [TILT_MIN, TILT_MAX] with the clip COUNT
  reported on every run (no silent caps).

      V_IPS   = (1/N) Σ w_i r_i
      V_SNIPS = Σ w_i r_i / Σ w_i          (self-normalized; primary)
      ESS     = (Σ w)² / Σ w²              (Kish effective sample size)

  CIs: cluster bootstrap over DECK JOBS (impressions within a deck are
  correlated), percentile 95%. Verdict vs the production baseline is
  labeled UNRELIABLE whenever ESS < ess_min — the number is still printed,
  the label just refuses to bless it.

Self-consistency (--self-check): replaying the logged order gives
rank_candidate = rank_logged ⇒ exposure ratio 1 for every card, so SNIPS
collapses to a tilt-weighted observed rate; with deterministic serving
(p=1) it equals the observed rate exactly. The check asserts the observed
rate falls inside the replayed 95% CI, per metric.

Time-ordered protocol: --eval-start YYYY-MM-DD splits by served_at; the
harness fits trainable scorers ONLY on pre-split decks and scores ONLY
post-split decks (backend.eval.data.split_decks). A fit-capable scorer
without --eval-start is refused. There is no shuffled-CV API on purpose.

Exclusions (counted per reason and printed — never silently dropped):
  null_propensity  propensity NULL/≤0/non-finite (defensive; column is NOT NULL)
  never_viewed     no `viewed` outcome — served ≠ seen; the label would be
                   fabricated (the F2 cascade rule: unseen is not a negative)
  undo_reversed    an `undo` outcome exists — the disposition was retracted
  bad_features     features_json missing/unparseable — scorer can't score it
  scorer_error     scorer raised on any card in the deck — whole deck out
                   (a partial deck can't be ranked consistently)
Excluded cards still occupy candidate-rank positions when scoreable (the
counterfactual deck still contains them); unscoreable cards sink to the
bottom of the candidate order.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from dataclasses import dataclass, field

from backend.eval.data import (
    LoggedDeck,
    card_dict,
    load_decks,
    split_decks,
)
from backend.eval.scorers import get_scorer, registered_names

# Defaults — env-overridable (documented in docs/config-reference.md §F8).
DEFAULT_ESS_MIN = float(os.environ.get("EVAL_ESS_MIN", "100"))
DEFAULT_BOOTSTRAP = int(os.environ.get("EVAL_BOOTSTRAP", "1000"))
TILT_MIN = 0.5
TILT_MAX = 2.0
EXPOSURE_FLOOR = 0.02
METRICS = ("like", "propose")

EXCLUSION_REASONS = (
    "null_propensity", "never_viewed", "undo_reversed",
    "bad_features", "scorer_error",
)


@dataclass
class MetricEstimate:
    metric: str
    n: int                 # included impressions
    observed: float | None # logged policy's realized rate on the included set
    ips: float | None
    snips: float | None
    ess: float
    ci_low: float | None   # 95% cluster-bootstrap CI on SNIPS
    ci_high: float | None
    ips_ci_low: float | None = None
    ips_ci_high: float | None = None


@dataclass
class EvalRun:
    scorer: str
    n_total: int                     # impressions loaded into the eval window
    n_included: int
    excluded: dict = field(default_factory=dict)   # reason -> count
    tilt_clipped: int = 0            # propensity tilts hit TILT_MIN/TILT_MAX
    exposure_positions: int = 0      # positions with an estimated e(k)
    metrics: dict = field(default_factory=dict)    # metric -> MetricEstimate
    eval_start: str | None = None
    ess_min: float = DEFAULT_ESS_MIN

    @property
    def unreliable(self) -> bool:
        return any(m.ess < self.ess_min for m in self.metrics.values())


# ---------------------------------------------------------------------------
# Exposure curve
# ---------------------------------------------------------------------------

def exposure_curve(decks: list[LoggedDeck]) -> dict[int, float]:
    """e(k) = P(viewed | served at position k), Laplace(+1/+2)-smoothed,
    floored at EXPOSURE_FLOOR. Positions never observed fall back to the
    floor at lookup time (exposure_at)."""
    served: dict[int, int] = {}
    viewed: dict[int, int] = {}
    for deck in decks:
        for c in deck.cards:
            served[c.card_index] = served.get(c.card_index, 0) + 1
            if c.viewed:
                viewed[c.card_index] = viewed.get(c.card_index, 0) + 1
    return {
        k: max((viewed.get(k, 0) + 1) / (served[k] + 2), EXPOSURE_FLOOR)
        for k in served
    }


def exposure_at(curve: dict[int, float], k: int) -> float:
    return curve.get(k, EXPOSURE_FLOOR)


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def _candidate_ranks(scorer, deck: LoggedDeck) -> dict[str, int]:
    """Counterfactual rank per impression_id under `scorer`. Cards without
    parseable features sink to the bottom (they still occupy slots). Any
    scorer exception propagates — the caller excludes the whole deck as
    scorer_error (a partially-scored deck can't be ranked consistently)."""
    scored: list[tuple[float, int, str]] = []
    for c in deck.cards:
        if c.features is None:
            key = (float("-inf"), c.card_index, c.impression_id)
        else:
            s = scorer.score(card_dict(c))
            if s is None or (isinstance(s, float) and not math.isfinite(s)):
                raise ValueError(
                    f"scorer returned non-finite score for {c.impression_id}")
            key = (float(s), c.card_index, c.impression_id)
        scored.append(key)
    # Higher score first; ties broken by logged position (stable: replaying
    # the logged scorer reproduces the served order exactly).
    scored.sort(key=lambda t: (-t[0], t[1]))
    return {imp_id: rank for rank, (_s, _ci, imp_id) in enumerate(scored)}


def _reward(card, metric: str) -> float:
    if metric == "like":
        return 1.0 if card.liked else 0.0
    if metric == "propose":
        return 1.0 if card.proposed else 0.0
    raise ValueError(f"unknown metric {metric!r}")


def _fit_rows(decks: list[LoggedDeck]) -> list[dict]:
    return [
        {
            "card": card_dict(c),
            "viewed": c.viewed,
            "liked": c.liked,
            "proposed": c.proposed,
            "dwell_ms": c.dwell_ms,
        }
        for d in decks for c in d.cards
    ]


def evaluate(
    scorer,
    decks: list[LoggedDeck],
    *,
    eval_start: str | None = None,
    ess_min: float = DEFAULT_ESS_MIN,
    bootstrap: int = DEFAULT_BOOTSTRAP,
    seed: int = 0,
    curve: dict[int, float] | None = None,
) -> EvalRun:
    """Replay `decks` under `scorer`. Enforces the time-ordered protocol:
    a fit-capable scorer requires eval_start, is fitted on pre-split decks
    only, and is evaluated on post-split decks only."""
    fit_capable = hasattr(scorer, "fit")
    if fit_capable and not eval_start:
        raise ValueError(
            f"scorer {scorer.name!r} has fit(); --eval-start is required so the "
            "harness can enforce the time-ordered train/eval split "
            "(shuffled CV on sequential logs is refused by design)")

    if eval_start:
        train_decks, eval_decks = split_decks(decks, eval_start)
        if fit_capable:
            scorer.fit(_fit_rows(train_decks))
    else:
        eval_decks = decks

    # Exposure curve from the FULL loaded log (it describes the logged
    # policy's view behavior, not the candidate) unless caller supplied one.
    curve = curve if curve is not None else exposure_curve(decks)

    run = EvalRun(
        scorer=getattr(scorer, "name", scorer.__class__.__name__),
        n_total=sum(len(d.cards) for d in eval_decks),
        n_included=0,
        excluded={r: 0 for r in EXCLUSION_REASONS},
        exposure_positions=len(curve),
        eval_start=eval_start,
        ess_min=ess_min,
    )

    # weights/rewards per deck (bootstrap clusters)
    clusters: list[dict] = []   # {"w": [...], "r_like": [...], "r_propose": [...]}
    for deck in eval_decks:
        try:
            ranks = _candidate_ranks(scorer, deck)
        except Exception:
            run.excluded["scorer_error"] += len(deck.cards)
            continue
        valid_p = [c.propensity for c in deck.cards
                   if c.propensity is not None and c.propensity > 0
                   and math.isfinite(c.propensity)]
        p_bar = (sum(valid_p) / len(valid_p)) if valid_p else 1.0
        cluster = {"w": [], "r_like": [], "r_propose": []}
        for c in deck.cards:
            if (c.propensity is None or not math.isfinite(c.propensity)
                    or c.propensity <= 0):
                run.excluded["null_propensity"] += 1
                continue
            if not c.viewed:
                run.excluded["never_viewed"] += 1
                continue
            if c.undone:
                run.excluded["undo_reversed"] += 1
                continue
            if c.features is None:
                run.excluded["bad_features"] += 1
                continue
            tilt = p_bar / c.propensity
            if tilt < TILT_MIN or tilt > TILT_MAX:
                run.tilt_clipped += 1
                tilt = min(max(tilt, TILT_MIN), TILT_MAX)
            w = (exposure_at(curve, ranks[c.impression_id])
                 / exposure_at(curve, c.card_index)) * tilt
            cluster["w"].append(w)
            cluster["r_like"].append(_reward(c, "like"))
            cluster["r_propose"].append(_reward(c, "propose"))
        if cluster["w"]:
            clusters.append(cluster)

    weights = [w for cl in clusters for w in cl["w"]]
    run.n_included = len(weights)

    rng = random.Random(seed)
    for metric in METRICS:
        rkey = f"r_{metric}"
        rewards = [r for cl in clusters for r in cl[rkey]]
        run.metrics[metric] = _estimate(
            metric, weights, rewards, clusters, rkey, bootstrap, rng)
    return run


def _point_estimates(weights, rewards):
    n = len(weights)
    if n == 0:
        return None, None, None, 0.0
    sw = sum(weights)
    swr = sum(w * r for w, r in zip(weights, rewards))
    sw2 = sum(w * w for w in weights)
    observed = sum(rewards) / n
    ips = swr / n
    snips = (swr / sw) if sw > 0 else None
    ess = (sw * sw / sw2) if sw2 > 0 else 0.0
    return observed, ips, snips, ess


def _estimate(metric, weights, rewards, clusters, rkey, bootstrap, rng):
    observed, ips, snips, ess = _point_estimates(weights, rewards)
    est = MetricEstimate(
        metric=metric, n=len(weights), observed=observed,
        ips=ips, snips=snips, ess=ess, ci_low=None, ci_high=None,
    )
    if not clusters or snips is None or bootstrap <= 0:
        return est
    snips_samples, ips_samples = [], []
    k = len(clusters)
    for _ in range(bootstrap):
        ws, rs = [], []
        for _ in range(k):
            cl = clusters[rng.randrange(k)]
            ws.extend(cl["w"])
            rs.extend(cl[rkey])
        sw = sum(ws)
        if sw <= 0:
            continue
        swr = sum(w * r for w, r in zip(ws, rs))
        snips_samples.append(swr / sw)
        ips_samples.append(swr / len(ws))
    if snips_samples:
        est.ci_low, est.ci_high = _percentile_ci(snips_samples)
        est.ips_ci_low, est.ips_ci_high = _percentile_ci(ips_samples)
    return est


def _percentile_ci(samples: list[float], alpha: float = 0.05):
    s = sorted(samples)
    lo = s[max(0, int(math.floor(alpha / 2 * len(s))))]
    hi = s[min(len(s) - 1, int(math.ceil((1 - alpha / 2) * len(s))) - 1)]
    return lo, hi


# ---------------------------------------------------------------------------
# Verdicts + self-check
# ---------------------------------------------------------------------------

def verdict(run: EvalRun, baseline: EvalRun, metric: str = "like") -> str:
    """UNRELIABLE below the ESS gate (per PRD: labeled, never silently
    capped); else WIN/LOSS when the candidate's 95% CI clears the baseline
    point estimate, FLAT otherwise."""
    m = run.metrics.get(metric)
    b = baseline.metrics.get(metric)
    if m is None or m.snips is None or m.ess < run.ess_min:
        return "UNRELIABLE"
    if b is None or b.snips is None:
        return "NO-BASELINE"
    if m.ci_low is not None and m.ci_low > b.snips:
        return "WIN"
    if m.ci_high is not None and m.ci_high < b.snips:
        return "LOSS"
    return "FLAT"


def self_check(
    decks: list[LoggedDeck],
    *,
    ess_min: float = DEFAULT_ESS_MIN,
    bootstrap: int = DEFAULT_BOOTSTRAP,
    seed: int = 0,
) -> tuple[bool, EvalRun]:
    """Replay the logged policy against its own logs: SNIPS must contain
    the observed rate within the bootstrap 95% CI, per metric (skipping
    degenerate metrics with no CI). Returns (passed, run)."""
    run = evaluate(get_scorer("logged"), decks,
                   ess_min=ess_min, bootstrap=bootstrap, seed=seed)
    passed = True
    for m in run.metrics.values():
        if m.n == 0 or m.snips is None or m.ci_low is None:
            continue
        if not (m.ci_low - 1e-12 <= m.observed <= m.ci_high + 1e-12):
            passed = False
    return passed, run


# ---------------------------------------------------------------------------
# Operator report
# ---------------------------------------------------------------------------

def _fmt(v, pct=False):
    if v is None:
        return "—"
    return f"{v * 100:.2f}%" if pct else f"{v:.4f}"


def render_report(runs: list[EvalRun], baseline: EvalRun) -> str:
    """Markdown operator report: scorer vs baseline, IPS/SNIPS, CI, ESS,
    verdict — plus the exclusion accounting (nothing dropped silently)."""
    lines = [
        "| scorer | metric | N | ESS | observed | IPS | SNIPS | 95% CI (SNIPS) | vs production | verdict |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for run in runs:
        for metric in METRICS:
            m = run.metrics[metric]
            b = baseline.metrics[metric]
            delta = (None if (m.snips is None or b.snips is None)
                     else m.snips - b.snips)
            ci = ("—" if m.ci_low is None
                  else f"[{_fmt(m.ci_low, True)}, {_fmt(m.ci_high, True)}]")
            lines.append(
                f"| {run.scorer} | {metric} | {m.n} | {m.ess:.1f} "
                f"| {_fmt(m.observed, True)} | {_fmt(m.ips, True)} "
                f"| {_fmt(m.snips, True)} | {ci} "
                f"| {'—' if delta is None else f'{delta * 100:+.2f}pp'} "
                f"| {verdict(run, baseline, metric)} |"
            )
    lines.append("")
    lines.append("Exclusion accounting (impressions in eval window, per scorer):")
    for run in runs:
        excl = ", ".join(f"{k}={v}" for k, v in run.excluded.items() if v)
        lines.append(
            f"- {run.scorer}: total={run.n_total} included={run.n_included} "
            f"excluded[{excl or 'none'}] tilt_clipped={run.tilt_clipped} "
            f"(bounds [{TILT_MIN}, {TILT_MAX}])"
        )
        total_accounted = run.n_included + sum(run.excluded.values())
        if total_accounted != run.n_total:
            lines.append(
                f"  WARNING: accounting mismatch — {total_accounted} accounted "
                f"vs {run.n_total} loaded")
    lines.append("")
    lines.append(
        f"ESS gate: {baseline.ess_min:.0f} (verdicts below it are UNRELIABLE; "
        f"exposure curve floor {EXPOSURE_FLOOR}, Laplace +1/+2 smoothing).")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python3 -m backend.eval.replay",
        description="F8 offline replay/IPS evaluator over the F1 impression spine.",
    )
    ap.add_argument("--db", help="SQLite path (or SQLAlchemy URL) to read; "
                                 "default = backend.database engine (data/trade_finder.db)")
    ap.add_argument("--scorer", action="append", default=[],
                    help=f"candidate scorer(s) to grade; registered: {registered_names()}")
    ap.add_argument("--baseline", default="production",
                    help="baseline scorer (default: production)")
    ap.add_argument("--self-check", action="store_true",
                    help="replay the logged policy; fail (exit 1) unless the "
                         "observed rate falls inside the replayed 95%% CI")
    ap.add_argument("--eval-start", help="ISO date/datetime — fit on decks before, "
                                         "evaluate on decks at/after (time-ordered protocol)")
    ap.add_argument("--since", help="only load impressions served at/after this ISO timestamp")
    ap.add_argument("--until", help="only load impressions served before this ISO timestamp")
    ap.add_argument("--user", help="restrict to one user_id")
    ap.add_argument("--league", help="restrict to one league_id")
    ap.add_argument("--ess-min", type=float, default=DEFAULT_ESS_MIN,
                    help=f"ESS gate for UNRELIABLE labeling (default {DEFAULT_ESS_MIN:g}; "
                         "env EVAL_ESS_MIN)")
    ap.add_argument("--bootstrap", type=int, default=DEFAULT_BOOTSTRAP,
                    help=f"bootstrap resamples (default {DEFAULT_BOOTSTRAP}; env EVAL_BOOTSTRAP)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-persist", action="store_true",
                    help="skip appending the run record to data/eval_runs/")
    args = ap.parse_args(argv)

    db_url = None
    if args.db:
        db_url = args.db if "://" in args.db else f"sqlite:///{args.db}"

    decks = load_decks(db_url=db_url, since=args.since, until=args.until,
                       user_id=args.user, league_id=args.league)
    n_imps = sum(len(d.cards) for d in decks)
    print(f"Loaded {len(decks)} decks / {n_imps} impressions"
          + (f" from {args.db}" if args.db else " from default DB"))
    if not decks:
        print("Nothing to evaluate.")
        return 0

    if args.self_check:
        ok, run = self_check(decks, ess_min=args.ess_min,
                             bootstrap=args.bootstrap, seed=args.seed)
        print(render_report([run], run))
        for m in run.metrics.values():
            print(f"self-check {m.metric}: observed={_fmt(m.observed, True)} "
                  f"snips={_fmt(m.snips, True)} "
                  f"ci=[{_fmt(m.ci_low, True)}, {_fmt(m.ci_high, True)}]")
        print(f"SELF-CHECK {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1

    scorer_names = args.scorer or ["base_score", "random"]
    baseline = evaluate(get_scorer(args.baseline), decks,
                        eval_start=args.eval_start, ess_min=args.ess_min,
                        bootstrap=args.bootstrap, seed=args.seed)
    runs = [baseline]
    for name in scorer_names:
        if name == args.baseline:
            continue
        runs.append(evaluate(get_scorer(name, seed=args.seed), decks,
                             eval_start=args.eval_start, ess_min=args.ess_min,
                             bootstrap=args.bootstrap, seed=args.seed))
    report = render_report(runs, baseline)
    print(report)

    if not args.no_persist:
        from backend.eval.persistence import append_run, run_record
        path = None
        for run in runs:
            path = append_run(run_record(run, baseline, extra={
                "db": args.db, "since": args.since, "until": args.until,
                "seed": args.seed, "bootstrap": args.bootstrap,
            }))
        print(f"Run records appended to {path} (runs.jsonl)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
