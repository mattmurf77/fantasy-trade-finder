"""Drain the Receipts grading backlog (docs/plans/receipts/PLAN.md P1).

The daily job grades one batch per run, which is right for steady state and
far too slow for launch day: every telemetry-era impression whose 14/28/56-day
window has already elapsed is gradeable the moment the feature ships. This
script loops `receipts_service.run_grading` until the backlog is drained.

TERMINATION — one rule, so there is no second rule to get wrong. The loop
stops after **two consecutive zero-work runs**, where zero-work means zero
TERMINAL rows written (graded + ungradeable both 0). A run that writes 500
`ungradeable` rows is PROGRESS and the loop continues: those rows are the
disclosure denominator, not failure. Impressions still waiting on a future
snapshot are retry-pending, they are the daily job's business, and they are
excluded from the queue predicate entirely — so they can neither stall this
loop nor spin it.

The script calls the SAME function the cron endpoint and the daily-tick guard
call — three triggers, one idempotent writer (HLD D-9). It never inserts
directly, never edits a row, and cannot produce a duplicate: the unique
constraint plus insert-or-ignore mean a re-run after a crash simply resumes.

Grading is a no-op unless BOTH the `receipts.grading` flag is on and the env
kill switch `FTF_RECEIPTS_GRADE` is not "0"; the script says so and exits
rather than looping silently.

    python3 scripts/receipts_backfill.py --dry-run
    python3 scripts/receipts_backfill.py
    python3 scripts/receipts_backfill.py --batch 1000 --max-runs 200
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import database as db                     # noqa: E402
from backend import receipts_service as rs             # noqa: E402


def _backlog() -> dict:
    """Per-window resolvable backlog at the current grader version."""
    cfg = db.get_config()
    today = rs._utc_today()
    min_serve = db.receipts_min_served_date()
    if not min_serve:
        return {"total": 0, "by_window": {}, "first_served": None}
    _, per_window = rs._serve_date_sets(cfg, today, min_serve)
    by_window = {
        str(w): db.count_receipts_queue(w, rs.GRADER_VERSION, per_window[w])
        for w in rs.WINDOWS_DAYS
    }
    return {"total": sum(by_window.values()), "by_window": by_window,
            "first_served": min_serve}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=int, default=None,
                    help="rows per run (default: model_config "
                         "receipts_grade_batch, 500)")
    ap.add_argument("--max-runs", type=int, default=100,
                    help="hard ceiling on loop iterations (safety rail)")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="seconds between runs")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the backlog and the flag state; write "
                         "nothing")
    args = ap.parse_args()

    db.init_db()

    backlog = _backlog()
    print(f"grader_version   : {rs.GRADER_VERSION}")
    print(f"taxonomy_version : {rs.TAXONOMY_VERSION}")
    print(f"first served     : {backlog['first_served']}")
    print(f"resolvable now   : {backlog['total']} "
          f"({json.dumps(backlog['by_window'])})")
    print(f"grading enabled  : {rs.grading_enabled()}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    if not rs.grading_enabled():
        print("\nreceipts.grading is OFF (or FTF_RECEIPTS_GRADE=0) — the "
              "grader would no-op on every run. Enable the flag first:\n"
              "  config/features.json -> \"receipts.grading\": true\n"
              "  POST /api/feature-flags/reload")
        return 1

    zero_streak = 0
    totals = {"graded": 0, "ungradeable": 0, "runs": 0}
    for i in range(1, max(1, args.max_runs) + 1):
        result = rs.run_grading(trigger="backfill", batch=args.batch)
        if result.get("skipped"):
            print(f"run {i}: skipped ({result['skipped']})")
            return 1
        graded = int(result.get("graded") or 0)
        ungradeable = int(result.get("ungradeable") or 0)
        terminal = graded + ungradeable
        totals["graded"] += graded
        totals["ungradeable"] += ungradeable
        totals["runs"] += 1
        print(f"run {i}: {graded} graded, {ungradeable} ungradeable, "
              f"{result.get('errors', 0)} errors, "
              f"{result.get('remaining_resolvable')} resolvable left "
              f"({result.get('duration_ms')} ms) "
              f"{json.dumps(result.get('reason_counts') or {})}")
        zero_streak = zero_streak + 1 if terminal == 0 else 0
        if zero_streak >= 2:
            print("\ntwo consecutive zero-work runs — backlog drained.")
            break
        if args.sleep:
            time.sleep(args.sleep)
    else:
        print(f"\nstopped at the --max-runs ceiling ({args.max_runs}); "
              "re-run to continue.")

    after = _backlog()
    print(f"\nTOTAL: {totals['runs']} runs, {totals['graded']} graded, "
          f"{totals['ungradeable']} ungradeable, "
          f"{after['total']} resolvable rows remaining "
          f"({json.dumps(after['by_window'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
