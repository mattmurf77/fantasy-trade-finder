#!/usr/bin/env python3
"""bench_s0_serve.py — S0's added serve latency (release-lead #367 QA, P3).

Seeds one realistic league in a throwaway SQLite file: 12 teams x 25 players,
a full pick grid (4 seasons x 4 rounds x 12 teams = 192 picks), and a fresh
`league_roster_state` row (within the roster bound, so no floor kick). Then
times `_trade_job_public_view` on a 30-card page with `trade_i1_mode` --mode (1,
the shipped default under option B, or 2) against 0, alternating per serve, after a warm-up. Prints p50/p95 for each mode and
for the added time per serve, plus the SQL statements per serve.

SQLite only: on Postgres each added statement is also a network round trip.

Usage (repo root):  python3 scripts/bench_s0_serve.py [--serves 300] [--mode 1|2]
No network and no real DB: DATABASE_URL points at a temp file before import.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "backend" / "tests" / "fixtures"
TMP = tempfile.mkdtemp(prefix="s0bench-")
os.environ["DATABASE_URL"] = f"sqlite:///{TMP}/s0bench.db"
# Hermetic value seams (the tests' fixtures): no DynastyProcess or KTC egress at import.
os.environ.setdefault("FTF_DP_VALUES_FILE", str(FIXTURES / "dp-values-history" / "values-2025-12-11.csv"))
os.environ.setdefault("FTF_DP_PICK_VALUES_FILE", str(FIXTURES / "dp_values_picks_2026-08-06.csv"))
os.environ.setdefault("FTF_KTC_VALUES_FILE", str(FIXTURES / "ktc_rankings_snapshot_2026-07-17.html"))
sys.path.insert(0, str(REPO))

from sqlalchemy import event, insert  # noqa: E402

import backend.database as db  # noqa: E402
import backend.server as server  # noqa: E402
from backend import trade_service as ts  # noqa: E402

LID = "1338231586314780001"
TEAMS, PER_TEAM, SEASONS, ROUNDS = 12, 25, (2026, 2027, 2028, 2029), 4


def seed() -> None:
    db.metadata.create_all(db.engine)
    now = datetime.now(timezone.utc).isoformat()
    with db.engine.begin() as conn:
        conn.execute(insert(db.leagues_table).values(
            sleeper_league_id=LID, user_id="u0", name="Bench", draft_status="not_drafted"))
        for t in range(TEAMS):
            conn.execute(insert(db.league_members_table).values(
                league_id=LID, user_id=f"u{t}", username=f"team{t}", display_name=f"team{t}",
                roster_data=json.dumps([str(t * 100 + i) for i in range(PER_TEAM)]),
                updated_at=now))
        for season in SEASONS:
            for rnd in range(1, ROUNDS + 1):
                for orig in range(1, TEAMS + 1):
                    conn.execute(insert(db.draft_picks_table).values(
                        pick_id=f"{LID}_{season}_{rnd}_{orig}", league_id=LID, season=season,
                        round=rnd, owner_user_id=f"u{orig - 1}", original_roster_id=str(orig),
                        pool_value=1000.0 - rnd * 100 - orig))
        conn.execute(insert(db.league_roster_state_table).values(
            league_id=LID, status="fresh", refreshed_at=now, updated_at=now))


def page() -> dict:
    cards = []
    for k in range(30):
        opp = 1 + k % (TEAMS - 1)
        give = [str(k % PER_TEAM)]
        receive = [str(opp * 100 + k % PER_TEAM)]
        if k % 5 == 0:                       # some pick-bearing cards
            give.append(f"{LID}_2027_2_1")
            receive.append(f"{LID}_2028_1_{opp + 1}")
        cards.append({"trade_id": f"t{k}", "league_id": LID, "target_user_id": f"u{opp}",
                      "target_username": f"team{opp}", "decision": None,
                      "give": [{"id": a} for a in give], "receive": [{"id": a} for a in receive]})
    return {"job_id": "bench-job", "key": ("u0", LID, "1qb_ppr"), "status": "complete",
            "opponents_done": TEAMS - 1, "opponents_total": TEAMS - 1, "cards": cards,
            "error": None, "league_user_id": "u0"}


def serve(job: dict, mode: float) -> float:
    ts._cfg["trade_i1_mode"] = mode
    start = time.perf_counter()
    out = server._trade_job_public_view(dict(job, cards=list(job["cards"])))
    elapsed = (time.perf_counter() - start) * 1000
    assert len(out["cards"]) == 30, out.get("error")
    return elapsed


def statements(job: dict, mode: float) -> int:
    count = [0]

    def tally(*_args):
        count[0] += 1

    event.listen(db.engine, "before_cursor_execute", tally)
    try:
        serve(job, mode)
    finally:
        event.remove(db.engine, "before_cursor_execute", tally)
    return count[0]


def pct(values, q):
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--serves", type=int, default=300)
    parser.add_argument("--mode", type=float, choices=(1.0, 2.0), default=1.0)
    args = parser.parse_args()
    server.log.setLevel("WARNING")           # the [i1] serve line is INFO
    seed()
    job = page()
    for _ in range(30):                      # warm-up: imports, memos, the table marker
        serve(job, args.mode)
        serve(job, 0.0)
    off, on = [], []
    for _ in range(args.serves):
        off.append(serve(job, 0.0))
        on.append(serve(job, args.mode))
    added = [b - a for a, b in zip(off, on)]
    reads_off, reads_on = statements(job, 0.0), statements(job, args.mode)
    print(f"serves={args.serves} cards=30 teams={TEAMS}x{PER_TEAM} picks="
          f"{len(SEASONS) * ROUNDS * TEAMS} (SQLite file)")
    label = f"mode {args.mode:.0f}"
    for name, values in (("mode 0", off), (label, on), ("added", added)):
        print(f"{name:7} p50={pct(values, 50):6.2f} ms  p95={pct(values, 95):6.2f} ms")
    print(f"SQL statements per serve: mode 0={reads_off} {label}={reads_on} "
          f"added={reads_on - reads_off}")

    # /generate's cache-hit path also reads the fingerprints before the job
    # lock (the pool here is unbuilt, so vsn1's seed part is empty; in prod
    # it's memoized per pool generation).
    ts._cfg["trade_i1_mode"] = args.mode
    fp_times, fp_reads = [], [0]
    for _ in range(args.serves):
        start = time.perf_counter()
        server._trade_current_fingerprints(LID, "1qb_ppr")
        fp_times.append((time.perf_counter() - start) * 1000)
    event.listen(db.engine, "before_cursor_execute", lambda *_a: fp_reads.__setitem__(0, fp_reads[0] + 1))
    server._trade_current_fingerprints(LID, "1qb_ppr")
    print(f"fingerprint read (/generate cache hit): p50={pct(fp_times, 50):.2f} ms  "
          f"p95={pct(fp_times, 95):.2f} ms  statements={fp_reads[0]}")


if __name__ == "__main__":
    main()
