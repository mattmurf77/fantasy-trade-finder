#!/usr/bin/env python3
"""
Profile /api/session/init with real Sleeper data.

Usage (from repo root):
    python3 backend/profile_session_init.py

What this measures:
  - Total session_init wall time (cold: ranking services built from scratch)
  - Total session_init wall time (warm: same user, token reused — services skipped)
  - Per-phase breakdown via cProfile (top 25 functions by cumulative time)
  - Explicit per-phase probes for the 5 key phases

Feeds the INIT-08-backend decision: is there enough time outside the
ranking-service build to justify a deferred TradeService construction?
"""

import cProfile
import io
import json
import os
import pstats
import sys
import time
import urllib.request

# Ensure repo root is on sys.path so `import backend.server` works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Config ────────────────────────────────────────────────────────────
USER_ID   = "313560442465169408"   # mattmurf77
LEAGUE_ID = "1181674778942836736"  # Fantasy Football Version 3 (1QB)
SERVER_URL = "http://127.0.0.1:5000"
USE_HTTP   = "--http" in sys.argv   # default: Flask test client (faster, no server needed)

# ── Sleeper fetch ─────────────────────────────────────────────────────
def _sleeper(path: str):
    req = urllib.request.Request(
        f"https://api.sleeper.app/v1/{path}",
        headers={"User-Agent": "FTF-profiler/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


print("=" * 60)
print("FTF session_init profiler")
print("=" * 60)

print("\n[1/3] Fetching Sleeper league data …", flush=True)
t0 = time.perf_counter()
rosters = _sleeper(f"league/{LEAGUE_ID}/rosters")
users   = _sleeper(f"league/{LEAGUE_ID}/users")
sleeper_ms = (time.perf_counter() - t0) * 1000
print(f"      done in {sleeper_ms:.0f} ms  "
      f"({len(rosters)} rosters, {len(users)} users)")

user_map  = {u["user_id"]: (u.get("display_name") or u.get("username") or u["user_id"])
             for u in users}
my_roster = next((r for r in rosters if r.get("owner_id") == USER_ID), None)
my_ids    = [str(p) for p in (my_roster.get("players") or [])] if my_roster else []
opps      = [
    {
        "user_id":    r["owner_id"],
        "username":   user_map.get(r["owner_id"], r["owner_id"]),
        "player_ids": [str(p) for p in (r.get("players") or [])],
    }
    for r in rosters
    if r.get("owner_id") and r["owner_id"] != USER_ID
]
print(f"      My roster: {len(my_ids)} players | Opponents: {len(opps)}")

body = {
    "user_id":         USER_ID,
    "league_id":       LEAGUE_ID,
    "league_name":     "Fantasy Football Version 3",
    "user_player_ids": my_ids,
    "opponent_rosters": opps,
    "username":        "mattmurf77",
    "display_name":    "mattmurf77",
}

# ── Import Flask app ──────────────────────────────────────────────────
print("\n[2/3] Importing backend (module init + DB connect) …", flush=True)
t0 = time.perf_counter()
from backend.server import app  # noqa: E402
import_ms = (time.perf_counter() - t0) * 1000
print(f"      done in {import_ms:.0f} ms")

client = app.test_client()

# ── Warm Sleeper cache (prerequisite — not part of session_init cost) ──
print("\n[3/3] Warming Sleeper player cache …", flush=True)
t0 = time.perf_counter()
warm_resp = client.get("/api/sleeper/players/warm")
warm_ms = (time.perf_counter() - t0) * 1000
warm_data = warm_resp.get_json() or {}
print(f"      status={warm_resp.status_code}  "
      f"count={warm_data.get('count', '?')}  "
      f"took {warm_ms:.0f} ms")
if warm_resp.status_code != 200:
    print("ERROR: could not warm player cache. Aborting.")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────
# COLD RUN — ranking services built from scratch (first session for user)
# ─────────────────────────────────────────────────────────────────────
print("\n" + "─" * 60)
print("COLD RUN  (no existing session — ranking services built fresh)")
print("─" * 60)

pr_cold = cProfile.Profile()
pr_cold.enable()
t_cold_start = time.perf_counter()

resp_cold = client.post(
    "/api/session/init",
    data=json.dumps(body),
    content_type="application/json",
)

cold_ms = (time.perf_counter() - t_cold_start) * 1000
pr_cold.disable()

print(f"  status = {resp_cold.status_code}")
print(f"  total  = {cold_ms:.0f} ms")

if resp_cold.status_code != 200:
    print("  ERROR body:", resp_cold.get_data(as_text=True)[:500])
    sys.exit(1)

cold_token = (resp_cold.get_json() or {}).get("token", "")

# ─────────────────────────────────────────────────────────────────────
# WARM RUN — same user, existing token (ranking services reused)
# ─────────────────────────────────────────────────────────────────────
print("\n" + "─" * 60)
print("WARM RUN  (same token — ranking services reused, only TradeService rebuilt)")
print("─" * 60)

pr_warm = cProfile.Profile()
pr_warm.enable()
t_warm_start = time.perf_counter()

resp_warm = client.post(
    "/api/session/init",
    data=json.dumps(body),
    content_type="application/json",
    headers={"X-Session-Token": cold_token},
)

warm_run_ms = (time.perf_counter() - t_warm_start) * 1000
pr_warm.disable()

print(f"  status = {resp_warm.status_code}")
print(f"  total  = {warm_run_ms:.0f} ms")

# ─────────────────────────────────────────────────────────────────────
# DELTA — what ranking-service build actually costs
# ─────────────────────────────────────────────────────────────────────
rank_build_ms = cold_ms - warm_run_ms
trade_pct = (warm_run_ms / cold_ms * 100) if cold_ms else 0
rank_pct  = (rank_build_ms / cold_ms * 100) if cold_ms else 0

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  Cold (ranking build + trade svc): {cold_ms:7.0f} ms  (100%)")
print(f"  Warm (trade svc + DB reads only): {warm_run_ms:7.0f} ms  ({trade_pct:.0f}%)")
print(f"  → Ranking-service build cost:     {rank_build_ms:7.0f} ms  ({rank_pct:.0f}%)")
print()
print("  INIT-08-backend feasibility:")
if warm_run_ms < 500:
    print(f"  ✅ After deferring trade-svc build, cold response ≈ {warm_run_ms:.0f} ms")
    print("     Deferring TradeService to first /api/trades/generate is worth it.")
elif warm_run_ms < 1500:
    print(f"  🟡 Warm path is {warm_run_ms:.0f} ms — meaningful but not dramatic win.")
    print("     Consider deferring only if trade gen is rarely triggered immediately.")
else:
    print(f"  🔴 Warm path still {warm_run_ms:.0f} ms — bottleneck is elsewhere.")
    print("     Profile cold run below to identify the real hot spot.")

# ─────────────────────────────────────────────────────────────────────
# cProfile reports
# ─────────────────────────────────────────────────────────────────────
for label, pr in [("COLD", pr_cold), ("WARM", pr_warm)]:
    print(f"\n{'=' * 60}")
    print(f"cProfile — {label} RUN  (top 25 by cumulative time)")
    print("=" * 60)
    buf = io.StringIO()
    ps  = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
    ps.print_stats(25)
    # Filter out low-signal stdlib noise — keep only lines from our modules
    lines = buf.getvalue().splitlines()
    for line in lines:
        # Print header lines + any line mentioning our code or a useful time
        if (not line.strip()
                or line.startswith(" ")
                or "function calls" in line
                or "Ordered by" in line
                or "ncalls" in line):
            print(line)
        elif any(kw in line for kw in ("backend/", "session_init", "trade_service",
                                        "ranking_service", "database", "data_loader",
                                        "replay", "build_service", "TradeService",
                                        "RankingService", "load_swipe", "load_tier",
                                        "load_trade", "load_league", "_biased_elo",
                                        "_ensure_universal", "_get_universal")):
            print(line)
