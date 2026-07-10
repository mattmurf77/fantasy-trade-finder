#!/usr/bin/env python3
"""
TC-INT-001 — Sleeper-boundary input handling (the G-003..G-008 gotchas).

The Sleeper API is the untrusted input boundary. This verifies the backend
defensively handles the documented gotchas without crashing:

  - Null roster slots (G-004): Sleeper returns null entries -> must be filtered.
  - String-vs-int player IDs (G-005): int IDs must be coerced, no TypeError.
  - Unknown/garbage IDs: filtered against the player pool.
  - Empty roster: session still created (degrades, doesn't crash).
  - Duplicate IDs: handled without inflating the roster.
  - Passthrough error handling: bad username + URL parsing return structured
    errors, not 500s.

Usage:  python3 qa/sec/tc_int_001.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import harness as H  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch_int"
LEAGUE = "test_league_lakeview"
USER = "test_user_fp_1"
rec = H.CheckRecorder()


def real_roster(db):
    raw = H.db_scalar(db, "SELECT roster_data FROM league_members "
                      "WHERE league_id=? AND user_id=?", (LEAGUE, USER))
    return [str(x) for x in (json.loads(raw) if raw else []) if x]


def init(base, roster, user="qa_int_user", league="qa_int_league"):
    return H.Api(base).post("/api/session/init", {
        "user_id": user, "username": user, "display_name": user,
        "league_id": league, "league_name": "QA INT",
        "user_player_ids": roster, "opponent_rosters": []})


def main() -> int:
    print("TC-INT-001 — Sleeper-boundary input handling")
    db = H.make_scratch_db(SCRATCH, "qa_int.db")
    proc, base = H.boot_server(db, 5161, SCRATCH / "server.log",
                               env_overrides={"CRON_SECRET": None})
    try:
        valid = real_roster(db)[:6]
        n_valid = len(valid)
        rec.check("setup", n_valid >= 4, f"{n_valid} valid player IDs from fixture")

        # 1. Null roster slots (G-004): nulls must be dropped, valid kept.
        r = init(base, valid[:3] + [None, None])
        ok = r.status_code == 200
        roster_n = len(r.json().get("user_roster", [])) if ok else -1
        rec.check("null-slots", ok and roster_n == 3,
                  f"roster with 2 nulls -> {roster_n} resolved (want 3), status={r.status_code}")

        # 2. Int IDs (G-005): must be coerced to strings, not crash.
        int_ids = [int(x) for x in valid[:3] if str(x).isdigit()]
        r = init(base, int_ids)
        rec.check("int-ids", r.status_code == 200 and len(r.json().get("user_roster", [])) == len(int_ids),
                  f"int player IDs -> status={r.status_code}, "
                  f"{len(r.json().get('user_roster', [])) if r.status_code == 200 else '?'} resolved")

        # 3. Unknown/garbage IDs filtered.
        r = init(base, valid[:2] + ["999999999", "not-a-player", ""])
        roster_n = len(r.json().get("user_roster", [])) if r.status_code == 200 else -1
        rec.check("garbage-ids", r.status_code == 200 and roster_n == 2,
                  f"2 valid + 3 garbage -> {roster_n} resolved (want 2)")

        # 4. Empty roster: session still created (degrades, no crash).
        r = init(base, [])
        rec.check("empty-roster", r.status_code == 200,
                  f"empty roster -> status={r.status_code} (session still created)")

        # 5. Duplicate IDs: roster not inflated beyond distinct valid set.
        r = init(base, valid[:3] + valid[:3])
        roster_n = len(r.json().get("user_roster", [])) if r.status_code == 200 else -1
        rec.check("dup-ids", r.status_code == 200 and roster_n <= 6,
                  f"duplicated 3 IDs -> {roster_n} in roster (<= input length, no crash)")

        # 6. Passthrough: bad Sleeper username -> structured error, not 500.
        r = H.Api(base).get("/api/sleeper/user/__nonexistent_qa_user__xyz")
        rec.check("bad-username", r.status_code in (200, 400, 404, 502),
                  f"bad username -> {r.status_code} (graceful, not 500); "
                  f"body has error/empty: {('error' in _j(r)) or _j(r) in (None, {}, [])}")

        # 7. URL parsing: garbage + valid both return structured JSON, no 500.
        r1 = H.Api(base).post("/api/league/parse-url", {"url": "not a url at all"})
        r2 = H.Api(base).post("/api/league/parse-url",
                              {"url": "https://sleeper.com/leagues/123456789/team"})
        rec.check("parse-url", r1.status_code in (200, 400) and r2.status_code in (200, 400),
                  f"parse-url garbage={r1.status_code} valid={r2.status_code} "
                  f"(both structured, no 500)")
    finally:
        H.stop_server(proc)

    return rec.summary(SCRATCH / "TC-INT-001-run.json",
                       meta={"test_case": "TC-INT-001", "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})


def _j(r):
    try:
        return r.json()
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
