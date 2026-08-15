"""B8 — the nightly propensity-drift check (LLD §4.13, HLD §2.3/§5.3, PRD R10).

THE CONTRACT IT POLICES (HLD §2.3): any change to serving order must either be
deterministic given the logged `features_json`, or contribute its factor to the
logged `propensity`. A layer that is neither does not ship. Nothing in code
review can prove that stayed true six months from now, so this pass proves it
nightly from the data itself:

    final_score  ==  base × propensity × Π(frozen multipliers)      (±1%)

where `base` is the impression's `base_score` unless the F6 model replaced the
base ordering key, in which case the applied value is frozen as
`features_json.base_key`; and the frozen multipliers are exactly the keys in
`FROZEN_MULTIPLIER_KEYS` that the serve-time capture wrote. An absent
multiplier key means "that layer did not run" and reads as the neutral 1.0 —
the same no-signal-anchor convention the rest of `features_json` uses.

If someone adds a reorder layer and forgets to log its factor, the identity
breaks for every card that layer touched and this pass goes red the next
night. That is the entire point (R4): the tripwire fires on the CODE that
wasn't written (the logging), not on the code that was.

Consequences of a violation, per LLD §4.13:
  • >`MAX_VIOLATION_RATE` of the sample violating ⇒ the pass records `error`
    (it raises; `registry.run_ledger` writes the ledger row),
  • …and writes an `untrusted-<date>` marker file next to the F8 eval runs.
    The marker is the durable artifact: the D4 promotion counter reads it to
    skip a poisoned night, long after the log line has rotated away.

Rows deliberately NOT sampled:
  • non-`fs2` rows — they predate the freeze and carry no multipliers to check
    (checking them would flag every pre-B8 impression as a violation),
  • F7 wildcard rows — their `propensity` is the exploration draw probability
    (`rate × 1/|pool|`), not an ordering multiplier; the card was inserted at a
    fixed slot AFTER ordering and its key never went through the stack, so the
    identity does not apply to it by construction.

No Flask imports (D12).
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone

__all__ = [
    "FROZEN_MULTIPLIER_KEYS", "FEATURE_SET", "TOLERANCE_FRAC",
    "MAX_VIOLATION_RATE", "DEFAULT_SAMPLE", "markers_dir", "marker_path",
    "check_drift", "run",
]

log = logging.getLogger(__name__)

# The multiplier keys the serve-time capture may freeze (LLD §3.6). Order is
# irrelevant to the product; the tuple is the whitelist, so a stray numeric key
# in features_json can never be mistaken for an ordering factor.
# `class_demotion` is B6's and is simply absent until B6 lands — handled by the
# same absent-⇒-1.0 rule as every other layer that didn't run.
FROZEN_MULTIPLIER_KEYS = (
    "fatigue_mult", "taste_mult", "diversity_mult", "class_demotion",
)

FEATURE_SET        = "fs2"
TOLERANCE_FRAC     = 0.01    # |Δ| ≤ 1% of max(|final|, FLOOR)
FLOOR              = 1e-6
MAX_VIOLATION_RATE = 0.02    # >2% of the sample ⇒ untrusted night
DEFAULT_SAMPLE     = 200
# Rows read per night before the fs2 filter. The filter cannot go in SQL
# without substring-matching JSON, which would silently change meaning the day
# json.dumps' separators change; a bounded scan is honest and cheap.
SCAN_MULTIPLIER    = 10


# ---------------------------------------------------------------------------
# The marker (LLD §4.13)
# ---------------------------------------------------------------------------

def markers_dir() -> str:
    """`data/eval_runs/`, the F8 run directory — env-overridable at CALL time
    (the `eval.persistence` idiom) so tests can point at a tmp dir."""
    from ...eval import persistence          # noqa: WPS433 — late, cycle-free
    return os.environ.get("EVAL_RUNS_DIR", persistence.RUNS_DIR)


def marker_path(date_str: str) -> str:
    return os.path.join(markers_dir(), f"untrusted-{date_str}")


def _write_marker(date_str: str, payload: dict) -> str | None:
    path = marker_path(date_str)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        return path
    except OSError as e:
        # A marker we could not write is worse than useless if it also kills
        # the error signal, so log loudly and let the raise below still happen.
        log.error("drift_check: could not write untrusted marker %s: %s",
                  path, e)
        return None


# ---------------------------------------------------------------------------
# The identity
# ---------------------------------------------------------------------------

def expected_final(base_score: float, propensity: float, features: dict) -> float:
    """base × propensity × Π(frozen multipliers). Absent key ⇒ 1.0."""
    base = features.get("base_key")
    if not isinstance(base, (int, float)) or isinstance(base, bool):
        base = base_score
    out = float(base) * float(propensity)
    for k in FROZEN_MULTIPLIER_KEYS:
        v = features.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out *= float(v)
    return out


def _violates(final: float, expected: float) -> bool:
    if not (math.isfinite(final) and math.isfinite(expected)):
        return True
    return abs(final - expected) > TOLERANCE_FRAC * max(abs(final), FLOOR)


# ---------------------------------------------------------------------------
# The sample
# ---------------------------------------------------------------------------

def _sample_rows(day: str, limit: int) -> list:
    from sqlalchemy import select
    from ... import database as db

    # `served_at` is an ISO-8601 UTC string, so a half-open [day, day+1)
    # string range is an exact day filter and stays index-friendly.
    nxt = (datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
           + timedelta(days=1)).strftime("%Y-%m-%d")
    t = db.deck_impressions_table
    with db.engine.connect() as conn:
        return list(conn.execute(
            select(t.c.impression_id, t.c.features_json, t.c.propensity,
                   t.c.base_score, t.c.final_score, t.c.deck_job_id)
            .where(t.c.served_at >= day, t.c.served_at < nxt)
            .order_by(t.c.served_at, t.c.impression_id)
            .limit(max(1, limit * SCAN_MULTIPLIER))
        ))


def check_drift(*, day: str, sample_limit: int = DEFAULT_SAMPLE) -> dict:
    """Read-only: sample `day`'s fs2 impressions and score the identity.

    Returns the report dict; writes nothing. `run()` owns the marker and the
    raise, so this half stays trivially testable.
    """
    rows = _sample_rows(day, sample_limit)
    sampled = 0
    skipped_wildcard = 0
    skipped_non_fs2 = 0
    unparsable = 0
    violations: list[dict] = []

    for r in rows:
        if sampled >= sample_limit:
            break
        try:
            features = json.loads(r.features_json) if r.features_json else {}
        except (TypeError, ValueError):
            unparsable += 1
            continue
        if not isinstance(features, dict):
            unparsable += 1
            continue
        if features.get("feature_set") != FEATURE_SET:
            skipped_non_fs2 += 1
            continue
        if features.get("wildcard"):
            skipped_wildcard += 1
            continue

        sampled += 1
        final = float(r.final_score if r.final_score is not None else 0.0)
        expected = expected_final(
            float(r.base_score if r.base_score is not None else 0.0),
            float(r.propensity if r.propensity is not None else 1.0),
            features,
        )
        if _violates(final, expected):
            violations.append({
                "impression_id": r.impression_id,
                "deck_job_id":   r.deck_job_id,
                "final_score":   final,
                "expected":      expected,
            })

    rate = (len(violations) / sampled) if sampled else 0.0
    return {
        "day":              day,
        "scanned":          len(rows),
        "sampled":          sampled,
        "violations":       len(violations),
        "violation_rate":   rate,
        "untrusted":        rate > MAX_VIOLATION_RATE,
        "skipped_non_fs2":  skipped_non_fs2,
        "skipped_wildcard": skipped_wildcard,
        "unparsable":       unparsable,
        # Bounded: the first few are all an operator needs to find the layer.
        "examples":         violations[:5],
    }


# ---------------------------------------------------------------------------
# The pass body
# ---------------------------------------------------------------------------

def run(ctx) -> dict:
    """PassSpec fn. Checks YESTERDAY (today's impressions are still arriving).

    On an untrusted night: write the marker FIRST, then raise so the ledger
    records `error`. Order matters — the marker is what a later promotion
    counter reads, and a raise that happened before the write would leave the
    poisoned night looking clean to everything except the ledger.
    """
    day = (ctx.now - timedelta(days=1)).strftime("%Y-%m-%d")
    report = check_drift(day=day)
    report["items"] = report["sampled"]

    if not report["untrusted"]:
        if report["violations"]:
            log.warning("drift_check %s: %d/%d violations (%.2f%%) — under the "
                        "%.0f%% bar, night stays trusted", day,
                        report["violations"], report["sampled"],
                        100 * report["violation_rate"], 100 * MAX_VIOLATION_RATE)
        return report

    report["marker"] = _write_marker(day, report)
    raise RuntimeError(
        f"propensity drift on {day}: {report['violations']}/{report['sampled']} "
        f"impressions ({100 * report['violation_rate']:.1f}%) do not satisfy "
        f"final = base × propensity × Πmultipliers. An ordering layer is "
        f"applying a factor it does not log (HLD §2.3). Marker: "
        f"{report.get('marker')}"
    )


def yesterday(now: datetime | None = None) -> str:
    """Helper for callers/tests that want the same day string `run` uses."""
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=1)).strftime("%Y-%m-%d")
