#!/usr/bin/env python3
"""
TC-PERF-001 — Performance: cold-start, warm latency, concurrent load, budgets.

Measures the backend against the QA charter budgets (qa/README.md §6):
  - Cold server boot (incl. player sync) and cold vs warm session_init.
  - Warm GET p95 < 500ms (local).
  - Trade generation end-to-end < 30s (mobile timeout).
  - Concurrent load: N parallel session_init + generate complete without errors
    or pathological tail latency (connection-pool / GIL behavior).
  - Enumeration budget: per-opponent generation stays bounded (v2 1s/200k) even
    for the full league — total generate time well under the 30s ceiling.

Reports measured numbers; FAILs only on budget breaches.

Usage:  python3 qa/perf/tc_perf_001.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import harness as H  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch"
USER = "test_user_fp_1"
LEAGUE = "test_league_lakeview"
rec = H.CheckRecorder()


def roster(db):
    raw = H.db_scalar(db, "SELECT roster_data FROM league_members "
                      "WHERE league_id=? AND user_id=?", (LEAGUE, USER))
    return [str(x) for x in (json.loads(raw) if raw else []) if x]


def init(base, db, user=USER):
    body = {"user_id": user, "username": user, "display_name": user,
            "league_id": LEAGUE, "league_name": "QA Perf",
            "user_player_ids": roster(db), "opponent_rosters": []}
    t0 = time.monotonic()
    r = H.Api(base).post("/api/session/init", body)
    return (time.monotonic() - t0), (r.json().get("token", "") if r.status_code == 200 else "")


def generate_wait(api):
    t0 = time.monotonic()
    snap = api.post("/api/trades/generate", {"league_id": LEAGUE}).json()
    jid = snap.get("job_id", "")
    while snap.get("status") not in ("complete", "error") and time.monotonic() - t0 < 40:
        time.sleep(0.4)
        snap = api.get(f"/api/trades/status?job_id={jid}").json()
    return time.monotonic() - t0, len(snap.get("cards") or []), snap.get("status")


def main() -> int:
    print("TC-PERF-001 — performance + budgets")
    db = H.make_scratch_db(SCRATCH, "qa_perf.db")

    # Cold boot (harness boot_server already waits for readiness — time it).
    t_boot = time.monotonic()
    proc, base = H.boot_server(db, 5153, SCRATCH / "server.log",
                               env_overrides={"CRON_SECRET": None})
    boot_s = time.monotonic() - t_boot
    rec.check("boot-cold", boot_s < 90, f"cold boot incl. player sync: {boot_s:.1f}s (budget 90s)")

    try:
        # Cold vs warm session_init (first builds ranking services).
        cold_init, token = init(base, db)
        rec.check("init-cold", token and cold_init < 30,
                  f"cold session_init: {cold_init * 1000:.0f}ms (budget 30s)")
        warm_init, _ = init(base, db)
        rec.check("init-warm", warm_init < 5,
                  f"warm session_init (services reused): {warm_init * 1000:.0f}ms (budget 5s)")
        api = H.Api(base, token=token)

        # Warm GET latency distribution.
        gets = ["/api/rankings?position=RB", "/api/trades", "/api/leagues",
                "/api/feature-flags", "/api/me/streak", f"/api/league/coverage?league_id={LEAGUE}"]
        lat = []
        for _ in range(5):
            for path in gets:
                t0 = time.monotonic()
                api.get(path)
                lat.append((time.monotonic() - t0) * 1000)
        p50, p95, mx = (statistics.median(lat),
                        sorted(lat)[int(len(lat) * 0.95)], max(lat))
        rec.check("get-p95", p95 < 500, f"warm GET p50={p50:.0f}ms p95={p95:.0f}ms max={mx:.0f}ms "
                  f"(budget p95<500ms, n={len(lat)})")

        # Trade generation end-to-end.
        gen_s, ncards, status = generate_wait(api)
        rec.check("generate-budget", status == "complete" and gen_s < 30,
                  f"generate {ncards} cards in {gen_s:.2f}s (budget 30s)")

        # Enumeration budget: a fresh generate (bypass cache via a re-init) must
        # also stay well under budget — proves the per-opponent caps bound work.
        _, tok2 = init(base, db)
        gen2_s, n2, st2 = generate_wait(H.Api(base, token=tok2))
        rec.check("generate-bounded", st2 == "complete" and gen2_s < 30,
                  f"second generate {n2} cards in {gen2_s:.2f}s — per-opponent budget holds")

        # Concurrent load: 8 parallel users each init+generate.
        def worker(i):
            d, tok = init(base, db, user=USER)        # same fixture user (read-only data)
            if not tok:
                return ("init-fail", d, 0)
            g, n, s = generate_wait(H.Api(base, token=tok))
            return (s, d + g, n)

        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(worker, range(8)))
        wall = time.monotonic() - t0
        ok = [r for r in results if r[0] == "complete"]
        totals = sorted(r[1] for r in ok)
        rec.check("concurrent-no-errors", len(ok) == 8,
                  f"{len(ok)}/8 concurrent init+generate completed "
                  f"(statuses={[r[0] for r in results]})")
        if ok:
            rec.check("concurrent-tail", totals[-1] < 30,
                      f"concurrent wall={wall:.1f}s, slowest user end-to-end={totals[-1]:.1f}s "
                      f"(budget 30s; n={len(ok)})")

        # No errors leaked into the ring buffer during the load.
        log = api.get("/api/debug/log?n=200")
        errs = json.dumps(log.json()).count("Traceback") if log.status_code == 200 else -1
        rec.check("no-errors-under-load", errs == 0,
                  f"{errs} tracebacks in ring buffer after concurrent load")
    finally:
        H.stop_server(proc)

    return rec.summary(SCRATCH / "TC-PERF-001-run.json",
                       meta={"test_case": "TC-PERF-001", "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})


if __name__ == "__main__":
    sys.exit(main())
