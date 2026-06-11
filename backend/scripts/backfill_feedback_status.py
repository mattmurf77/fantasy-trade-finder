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
    16: "shipped",      # select-marking — operator confirmed shipped (2026-06-10)
    17: "shipped",      # batch D (League)
    18: "shipped",      # batch B
    19: "shipped",      # QC-trio throttle — operator set 1/100 (2026-06-10); backend-only, live at backfill time
    20: "shipped",      # batch B
    # ── Probes ───────────────────────────────────────────────────────
    21: "declined",     # Claude probe
    25: "declined",     # Claude probe
    # ── June 8-9 batch (ids 22-44) ───────────────────────────────────
    22: "shipped",      # tiers drag rebuild (#84, in TestFlight build 14)
    23: "shipped",      # drag coord-space fix
    24: "shipped",      # slow initial load → perf waves + Render Starter dyno
    26: "shipped",      # rookies link removed (#83)
    27: "shipped",      # tile movement while dragging — operator confirmed (2026-06-10)
    28: "new",          # bottom-nav affordance icon
    29: "shipped",      # full tile shift while dragging — operator confirmed (2026-06-10)
    30: "shipped",      # operator closed (2026-06-10) — reference note, target UX achieved
    31: "shipped",      # trends as rank-place deltas (trends_service rank deltas)
    32: "shipped",      # multi-select rework — operator confirmed (2026-06-10)
    33: "shipped",      # injury tags removed (#83)
    34: "shipped",      # check/X buttons under trade tile (TradesScreen)
    35: "shipped",      # match accept failure → FB-01 disposition fix
    36: "shipped",
    37: "planned",      # league tiles → route to trade records (idea, see SEVERITY_MAP)
    38: "planned",      # joined-the-app overlay rework (idea, see SEVERITY_MAP)
    39: "planned",      # leaderboard streak/total toggle
    40: "shipped",      # operator closed (2026-06-10) — OverallRanks/ManualRanks question resolved
    41: "shipped",      # league team count (#82)
    42: "planned",      # merge joined-summary into header tile
    43: "shipped",      # drag/multiselect — operator confirmed working (2026-06-10)
    44: "shipped",      # multi-select bulk-move fix (#85)
    # ── June 10 batch (ids 45-48) ────────────────────────────────────
    45: "fixed",        # session resume — fixed 2026-06-10, ships next build
    46: "fixed",        # swipe didn't save — fixed 2026-06-10
    47: "planned",      # standalone needs-based trade finder (NEXT.md)
    48: "fixed",        # portfolio season double-count — fixed 2026-06-10
}

# id → severity reclassification (operator decisions, 2026-06-10).
# Sent in the same PUT as the status when both exist.
SEVERITY_MAP: dict[int, str] = {
    37: "idea",         # filed as bug; really a navigation feature request
    38: "idea",         # filed as bug; really an overlay/UX redesign request
    47: "idea",         # filed as bug; self-described feature idea
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
    all_ids = sorted(set(STATUS_MAP) | set(SEVERITY_MAP))
    for fid in all_ids:
        payload: dict = {}
        if fid in STATUS_MAP:
            payload["status"] = STATUS_MAP[fid]
        if fid in SEVERITY_MAP:
            payload["severity"] = SEVERITY_MAP[fid]
        status = payload.get("status", "(unchanged)")
        if args.dry_run:
            print(f"would set {fid} -> {payload}")
            continue
        req = urllib.request.Request(
            f"{args.base}/api/feedback/admin/{fid}/status",
            data=json.dumps(payload).encode(),
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
    print(f"\ndone: {ok} ok, {failed} failed, {len(all_ids)} total")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
