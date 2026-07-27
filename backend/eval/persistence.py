"""F8 — run persistence: append-only JSON-lines under data/eval_runs/.

Why files, not a table: F8 cannot touch backend/database.py this wave
(file ownership), the writer is a single-operator CLI/cron (no concurrency
to referee), and JSON-lines records are greppable, diffable, and
zero-migration. `/data/` is already gitignored (repo .gitignore line 8),
so data/eval_runs/ ships nothing. If eval runs ever need SQL joins, a
later wave can lift runs.jsonl into an eval_runs table verbatim — every
record carries a schema_version for that migration.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUNS_DIR = os.environ.get(
    "EVAL_RUNS_DIR", os.path.join(_REPO_ROOT, "data", "eval_runs"))
RUNS_FILE = "runs.jsonl"
SCHEMA_VERSION = 1


def runs_path() -> str:
    # Env re-read at call time so tests can point at a tmp dir.
    base = os.environ.get("EVAL_RUNS_DIR", RUNS_DIR)
    return os.path.join(base, RUNS_FILE)


def run_record(run, baseline, extra: dict | None = None) -> dict:
    """Serialize an EvalRun (+ its verdicts vs baseline) into one JSON-able
    record."""
    from backend.eval.replay import verdict  # local import — no cycle at module load
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": uuid.uuid4().hex,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "run_date": datetime.now(timezone.utc).date().isoformat(),
        "scorer": run.scorer,
        "baseline": baseline.scorer,
        "eval_start": run.eval_start,
        "ess_min": run.ess_min,
        "n_total": run.n_total,
        "n_included": run.n_included,
        "excluded": dict(run.excluded),
        "tilt_clipped": run.tilt_clipped,
        "metrics": {
            name: {
                "n": m.n, "ess": m.ess, "observed": m.observed,
                "ips": m.ips, "snips": m.snips,
                "ci": [m.ci_low, m.ci_high],
                "ips_ci": [m.ips_ci_low, m.ips_ci_high],
                "verdict": verdict(run, baseline, name),
            }
            for name, m in run.metrics.items()
        },
        **(extra or {}),
    }


def append_run(record: dict) -> str:
    path = runs_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def load_runs() -> list[dict]:
    path = runs_path()
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue   # torn write — skip, never crash the harness
    return records
