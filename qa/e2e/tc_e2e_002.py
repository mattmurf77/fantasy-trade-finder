#!/usr/bin/env python3
"""
TC-E2E-002 — Restart resilience (in-memory session + trade-job loss).

Sessions and trade-generation jobs live in process memory, so a Render redeploy
mid-flight drops them. This verifies the loss is GRACEFUL (clean 401/404, never
a hang) and that the FB-46 card-context echo makes swiping restart-proof:

  1. Pre-restart: session_init + generate a deck (capture token, job_id, cards).
  2. Restart the server against the SAME DB (memory wiped, data intact).
  3. Old session token -> 401 on a session-gated route (not a 500/hang).
  4. Polling the old job_id (with a fresh session) -> 404 (job evicted), no hang.
  5. Re-init yields a working session; persisted rankings/data survive.
  6. FB-46: swiping a card from the PRE-restart deck (whose in-memory entry is
     gone) succeeds via the echoed give/receive context — decision persists.

Usage:  python3 qa/e2e/tc_e2e_002.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import harness as H  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch"
USER = "test_user_fp_1"
LEAGUE = "test_league_lakeview"
rec = H.CheckRecorder()


def roster(db, league, user):
    raw = H.db_scalar(db, "SELECT roster_data FROM league_members "
                      "WHERE league_id=? AND user_id=?", (league, user))
    return [str(x) for x in (json.loads(raw) if raw else []) if x]


def init(base, db):
    r = H.Api(base).post("/api/session/init", {
        "user_id": USER, "username": USER, "display_name": USER,
        "league_id": LEAGUE, "league_name": "QA Restart",
        "user_player_ids": roster(db, LEAGUE, USER), "opponent_rosters": []})
    return (r.json().get("token", ""), r.status_code) if r.status_code == 200 else ("", r.status_code)


def card_ids(card, side):
    return [str(p["id"]) for p in card.get(side, [])]


def generate(api):
    r = api.post("/api/trades/generate", {"league_id": LEAGUE})
    snap = r.json()
    jid = snap.get("job_id", "")
    t0 = time.monotonic()
    while snap.get("status") not in ("complete", "error") and time.monotonic() - t0 < 40:
        time.sleep(0.6)
        snap = api.get(f"/api/trades/status?job_id={jid}").json()
    return jid, (snap.get("cards") or [])


def main() -> int:
    print("TC-E2E-002 — restart resilience")
    db = H.make_scratch_db(SCRATCH, "qa_restart.db")

    print("\nPRE-RESTART — session + generate")
    proc, base = H.boot_server(db, 5131, SCRATCH / "server_pre.log",
                               env_overrides={"CRON_SECRET": None})
    old_token, code = init(base, db)
    rec.check("pre:session", bool(old_token), f"session_init -> {code}")
    api = H.Api(base, token=old_token)
    old_job, cards = generate(api)
    rec.check("pre:deck", len(cards) > 0, f"job {old_job[:8]} -> {len(cards)} cards")
    # Pick a fresh 1-for-1 card to swipe AFTER the restart.
    target_card = next((c for c in cards
                        if len(card_ids(c, "give")) == 1 and len(card_ids(c, "receive")) == 1),
                       cards[0] if cards else None)
    swipes_before = H.db_scalar(db, "SELECT COUNT(*) FROM trade_decisions WHERE user_id=?", (USER,))

    print("\n>>> RESTART (terminate + boot fresh process, same DB) <<<")
    H.stop_server(proc)
    proc, base = H.boot_server(db, 5132, SCRATCH / "server_post.log",
                               env_overrides={"CRON_SECRET": None})
    try:
        # 3. Old token must be cleanly rejected (sessions are in-memory).
        r = H.Api(base, token=old_token).get("/api/rankings?position=RB")
        rec.check("post:old-token-401", r.status_code == 401,
                  f"stale session token -> {r.status_code} (want 401, graceful)")

        # 4. Old job_id gone -> 404 via a fresh session (no hang).
        new_token, code = init(base, db)
        rec.check("post:reinit", bool(new_token), f"re-init after restart -> {code}")
        api2 = H.Api(base, token=new_token)
        t0 = time.monotonic()
        r = api2.get(f"/api/trades/status?job_id={old_job}")
        elapsed = time.monotonic() - t0
        rec.check("post:old-job-404", r.status_code == 404 and elapsed < 5,
                  f"stale job_id -> {r.status_code} in {elapsed:.2f}s (want 404, no hang)")

        # 5. Persisted data survived the restart.
        ranks = H.db_scalar(db, "SELECT COUNT(*) FROM member_rankings WHERE user_id=?", (USER,))
        rec.check("post:data-survived", ranks and ranks > 0,
                  f"member_rankings rows for user survived restart: {ranks}")

        # 6. FB-46: swipe a PRE-restart card via echoed context (its in-memory
        #    deck entry is gone) — must reconstruct + record, not error.
        if target_card:
            give, recv = card_ids(target_card, "give"), card_ids(target_card, "receive")
            r = api2.post("/api/trades/swipe", {
                "trade_id": target_card["trade_id"], "decision": "pass",
                "give_player_ids": give, "receive_player_ids": recv,
                "target_user_id": str(target_card["target_user_id"]),
                "target_username": target_card.get("target_username", ""),
                "league_id": LEAGUE})
            rec.check("post:fb46-swipe", r.status_code == 200,
                      f"swipe pre-restart card via echo -> {r.status_code} "
                      f"{r.text[:120] if r.status_code != 200 else '(reconstructed)'}")
            swipes_after = H.db_scalar(db, "SELECT COUNT(*) FROM trade_decisions WHERE user_id=?",
                                       (USER,))
            rec.check("post:fb46-persisted", (swipes_after or 0) - (swipes_before or 0) >= 1,
                      f"trade_decisions +{(swipes_after or 0) - (swipes_before or 0)} after restart swipe")

        # 7. New session is fully functional (generate works again).
        new_job, new_cards = generate(api2)
        rec.check("post:generate-works", len(new_cards) > 0,
                  f"post-restart generation -> {len(new_cards)} cards (new job {new_job[:8]})")
    finally:
        H.stop_server(proc)

    return rec.summary(SCRATCH / "TC-E2E-002-run.json",
                       meta={"test_case": "TC-E2E-002", "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})


if __name__ == "__main__":
    sys.exit(main())
