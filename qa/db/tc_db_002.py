#!/usr/bin/env python3
"""
TC-DB-002 — DB concurrency, write integrity, and recency bounds.

Runs the concurrency probe against a SCRATCH copy (live DB untouched):
  - Concurrent member_rankings upserts -> atomic replace (final == snapshot,
    no accumulation), no exceptions, no SQLite lock errors.
  - Concurrent distinct trade decisions -> none lost.
  - Concurrent ranking swipes -> all pairwise rows persisted (WAL holds under
    write contention).
  - check_for_match honors the 90-day recency window.

Usage:  python3 qa/db/tc_db_002.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import harness as H  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch"
rec = H.CheckRecorder()


def main() -> int:
    print("TC-DB-002 — DB concurrency + write integrity + recency")
    db = H.make_scratch_db(SCRATCH, "qa_db2.db")
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "PYTHONPATH": str(H.ROOT)}
    env.pop("CRON_SECRET", None)
    proc = subprocess.run([sys.executable, "qa/db/_concurrency_probe.py"],
                          cwd=H.ROOT, env=env, capture_output=True, text=True, timeout=120)
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        res = json.loads(line)
    except Exception:
        rec.check("probe-ran", False, f"probe failed: {proc.stderr[-400:]}")
        return rec.summary()

    mr = res["member_rankings"]
    rec.check("cc-member-rankings-atomic", not mr["errors"] and mr["final_rows"] == mr["expected"],
              f"8 concurrent upserts -> {mr['final_rows']} rows (want {mr['expected']}, atomic replace), "
              f"errors={mr['errors']}")

    td = res["trade_decisions"]
    rec.check("cc-trade-decisions-no-loss", not td["errors"] and td["final_rows"] == td["expected"],
              f"16 concurrent distinct decisions -> {td['final_rows']} persisted (want {td['expected']}), "
              f"errors={td['errors']}")

    rs = res["ranking_swipes"]
    rec.check("cc-ranking-swipes-wal", not rs["errors"] and rs["final_rows"] == rs["expected"],
              f"8 concurrent rankings -> {rs['final_rows']} swipe rows (want {rs['expected']}), "
              f"errors={rs['errors']} (no 'database is locked')")

    rcy = res["recency"]
    rec.check("recency-fresh-matches", rcy["fresh_matches"] is True,
              f"a fresh mirror like matches: {rcy['fresh_matches']}")
    rec.check("recency-stale-excluded", rcy["stale_matches"] is False,
              f"a >90-day-old like is excluded from matching: stale_matches={rcy['stale_matches']}")

    return rec.summary(SCRATCH / "TC-DB-002-run.json",
                       meta={"test_case": "TC-DB-002", "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})


if __name__ == "__main__":
    sys.exit(main())
