#!/usr/bin/env python3
"""One-off: backfill lifecycle statuses for feedback ids 1-48 (2026-06-10).

Statuses per the triage in docs/feedback/inbox.md. Hits the deployed
PUT /api/feedback/admin/<id>/status endpoint, so run AFTER the status
feature is deployed. Reads CRON_SECRET from secrets.local.env (project
root) unless --secret is passed.

Usage:
    python3 backend/scripts/backfill_feedback_status.py            # against prod
    python3 backend/scripts/backfill_feedback_status.py --base http://localhost:5000
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

PROD_BASE = "https://fantasy-trade-finder.onrender.com"
SECRETS_FILE = Path(__file__).resolve().parents[2] / "secrets.local.env"

# id → status. Vocabulary: new|planned|in_progress|fixed|shipped|declined.
# Sources: docs/feedback/inbox.md triage + PR/commit history (#82-#85,
# feedback batches A-D, FB-01 disposition fix, FB-45/46/48 fixes).
# Items left out default to 'new' (= "Received") server-side and need no row.
STATUS_MAP: dict[int, str] = {
    # ── May batch (ids 3-20) ─────────────────────────────────────────
    3:  "shipped",      # liked-trades awaiting view → awaiting-trades shipped
    4:  "shipped",      # fairness slider → on/off toggle (TradesScreen)
    5:  "shipped",      # equal-trades button removed with #4 redesign
    6:  "shipped",      # 100%-match display → match_score scaling + v2 engine
    7:  "shipped",      # batch A (Matches fixes)
    8:  "shipped",
    9:  "shipped",
    10: "shipped",
    11: "shipped",      # batch C (portfolio exposure double-count, May variant)
    12: "shipped",      # perf-optimization waves (INIT-*)
    13: "shipped",      # batch B (Trios fixes)
    14: "shipped",      # tiers drop-zone visuals (#84 gap-shift)
    15: "shipped",      # long-press multi-select (superseded by #32 rework ask)
    16: "in_progress",  # select-marking — #32 (June) says still not right
    17: "shipped",      # batch D (League)
    18: "shipped",      # batch B
    19: "new",          # "obvious trio" threshold — needs operator number
    20: "shipped",      # batch B
    # ── Probes ───────────────────────────────────────────────────────
    21: "declined",     # Claude probe
    25: "declined",     # Claude probe
    # ── June 8-9 batch (ids 22-44) ───────────────────────────────────
    22: "shipped",      # tiers drag rebuild (#84, in TestFlight build 14)
    23: "shipped",      # drag coord-space fix
    24: "shipped",      # slow initial load → perf waves + Render Starter dyno
    26: "shipped",      # rookies link removed (#83)
    27: "planned",      # background-tile movement still too subtle (post-#84)
    28: "new",          # bottom-nav affordance icon
    29: "planned",      # full tile shift while dragging (with #27)
    30: "new",          # praise/reference: ManualRanks drag is the target UX
    31: "shipped",      # trends as rank-place deltas (trends_service rank deltas)
    32: "planned",      # multi-select rework spec (arrows, no long-press)
    33: "shipped",      # injury tags removed (#83)
    34: "shipped",      # check/X buttons under trade tile (TradesScreen)
    35: "shipped",      # match accept failure → FB-01 disposition fix
    36: "shipped",
    37: "planned",      # league tiles → route to trade records
    38: "planned",      # joined-the-app overlay rework
    39: "planned",      # leaderboard streak/total toggle
    40: "new",          # OverallRanks vs ManualRanks duplication question
    41: "shipped",      # league team count (#82)
    42: "planned",      # merge joined-summary into header tile
    43: "in_progress",  # drag/multiselect re-broken + stray × button (post-#84/#85 verify)
    44: "shipped",      # multi-select bulk-move fix (#85)
    # ── June 10 batch (ids 45-48) ────────────────────────────────────
    45: "fixed",        # session resume — fixed 2026-06-10, ships next build
    46: "fixed",        # swipe didn't save — fixed 2026-06-10
    47: "planned",      # standalone needs-based trade finder (NEXT.md)
    48: "fixed",        # portfolio season double-count — fixed 2026-06-10
}


def read_secret() -> str | None:
    if not SECRETS_FILE.exists():
        return None
    for line in SECRETS_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("CRON_SECRET=") :
            val = line.split("=", 1)[1].strip()
            return val or None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=PROD_BASE)
    ap.add_argument("--secret", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    secret = args.secret or read_secret()
    if not secret and not args.dry_run:
        print("No CRON_SECRET — pass --secret or fill secrets.local.env")
        return 1

    ok = failed = 0
    for fid, status in sorted(STATUS_MAP.items()):
        if args.dry_run:
            print(f"would set {fid} -> {status}")
            continue
        req = urllib.request.Request(
            f"{args.base}/api/feedback/admin/{fid}/status",
            data=json.dumps({"status": status}).encode(),
            headers={"Content-Type": "application/json", "X-Cron-Secret": secret},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(f"{fid} -> {status}  [{resp.status}]")
                ok += 1
        except urllib.error.HTTPError as e:
            print(f"{fid} -> {status}  FAILED [{e.code}] {e.read().decode()[:120]}")
            failed += 1
        except Exception as e:
            print(f"{fid} -> {status}  FAILED {e}")
            failed += 1
    print(f"\ndone: {ok} ok, {failed} failed, {len(STATUS_MAP)} total")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
