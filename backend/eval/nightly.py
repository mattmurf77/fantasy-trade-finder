"""F8 — nightly re-run of every registered candidate scorer.

`run_all()` grades each registered scorer (except the logged-order
identity) on the trailing window vs the production baseline, appends run
records to data/eval_runs/runs.jsonl, and returns a summary + markdown
report. Idempotent per (UTC run_date, scorer, window_days): a re-invoked
daily tick finds the existing records and skips — same convention as the
F10 replenish log.

The server.py cron hook is a HANDOFF this wave (F7 owns server.py); the
designed snippet lives in feedback-workspace/tiktok-discovery/build/W4-F8.md
and in docs/runbook.md §"Offline eval harness". Until wired, run manually:

    python3 -m backend.eval.nightly
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.eval.data import load_decks
from backend.eval.persistence import append_run, load_runs, run_record
from backend.eval.replay import (
    DEFAULT_BOOTSTRAP,
    DEFAULT_ESS_MIN,
    evaluate,
    render_report,
)
from backend.eval.scorers import get_scorer, registered_names

DEFAULT_WINDOW_DAYS = 30
_SKIP = {"logged"}   # identity policy — self-check tool, not a candidate


def run_all(
    window_days: int = DEFAULT_WINDOW_DAYS,
    *,
    engine=None,
    db_url: str | None = None,
    ess_min: float = DEFAULT_ESS_MIN,
    bootstrap: int = DEFAULT_BOOTSTRAP,
    seed: int = 0,
    baseline_name: str = "production",
) -> dict:
    """Returns {"ran": int, "skipped": int, "errors": int, "report": str,
    "summary": str}. Never raises for a single scorer's failure — the
    failure is recorded (status=error) and counted, runbook-style."""
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    since = (now - timedelta(days=window_days)).isoformat()

    done = {
        (r.get("run_date"), r.get("scorer"), r.get("window_days"))
        for r in load_runs()
    }

    decks = load_decks(engine=engine, db_url=db_url, since=since)
    stats = {"ran": 0, "skipped": 0, "errors": 0, "report": "", "summary": ""}
    if not decks:
        stats["summary"] = f"no impressions in trailing {window_days}d — nothing to grade"
        return stats

    baseline = evaluate(get_scorer(baseline_name), decks,
                        ess_min=ess_min, bootstrap=bootstrap, seed=seed)
    runs = [baseline]
    for name in registered_names():
        if name in _SKIP or name == baseline_name:
            continue
        if (today, name, window_days) in done:
            stats["skipped"] += 1
            continue
        try:
            run = evaluate(get_scorer(name, seed=seed), decks,
                           ess_min=ess_min, bootstrap=bootstrap, seed=seed)
        except Exception as e:
            stats["errors"] += 1
            append_run({
                "schema_version": 1, "run_date": today, "scorer": name,
                "window_days": window_days, "status": "error", "error": str(e),
                "recorded_at": now.isoformat(),
            })
            continue
        runs.append(run)
        append_run(run_record(run, baseline,
                              extra={"window_days": window_days,
                                     "source": "nightly", "seed": seed}))
        stats["ran"] += 1

    # Baseline record too (once/day) so the trailing series is complete.
    if (today, baseline_name, window_days) not in done:
        append_run(run_record(baseline, baseline,
                              extra={"window_days": window_days,
                                     "source": "nightly", "seed": seed}))

    stats["report"] = render_report(runs, baseline)
    verdict_bits = []
    for run in runs[1:]:
        from backend.eval.replay import verdict
        verdict_bits.append(f"{run.scorer}:{verdict(run, baseline, 'like')}")
    stats["summary"] = (
        f"graded {stats['ran']} scorer(s) on {len(decks)} decks "
        f"(trailing {window_days}d); {' '.join(verdict_bits) or 'nothing new'}")
    return stats


if __name__ == "__main__":
    result = run_all()
    print(result["summary"])
    if result["report"]:
        print()
        print(result["report"])
