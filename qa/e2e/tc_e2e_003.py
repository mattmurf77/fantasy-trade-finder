#!/usr/bin/env python3
"""
TC-E2E-003 — Superflex (sf_tep) format path + format isolation.

The dual-format design keeps 1qb_ppr and sf_tep as fully independent rank sets.
This exercises the sf_tep branch end-to-end (via the X-Scoring-Format header)
and proves ranking in one format does NOT pollute the other:

  1. session_init builds both format services.
  2. Rank a trio under sf_tep -> swipe_decisions rows carry scoring_format='sf_tep'.
  3. The 1qb_ppr swipe/ranking counts are UNCHANGED (isolation).
  4. member_rankings gain an sf_tep partition for the user.
  5. Trade generation under sf_tep returns valid cards (sf_tep value space).
  6. The two formats can hold DIFFERENT Elo for the same player.

Usage:  python3 qa/e2e/tc_e2e_003.py
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
SF = {"X-Scoring-Format": "sf_tep"}
rec = H.CheckRecorder()


def roster(db):
    raw = H.db_scalar(db, "SELECT roster_data FROM league_members "
                      "WHERE league_id=? AND user_id=?", (LEAGUE, USER))
    return [str(x) for x in (json.loads(raw) if raw else []) if x]


def main() -> int:
    print("TC-E2E-003 — superflex (sf_tep) format path + isolation")
    db = H.make_scratch_db(SCRATCH, "qa_sf.db")
    proc, base = H.boot_server(db, 5141, SCRATCH / "server.log",
                               env_overrides={"CRON_SECRET": None})
    try:
        # 1. session_init.
        r = H.Api(base).post("/api/session/init", {
            "user_id": USER, "username": USER, "display_name": USER,
            "league_id": LEAGUE, "league_name": "QA SF",
            "user_player_ids": roster(db), "opponent_rosters": []})
        rec.check("init", r.status_code == 200, f"session_init -> {r.status_code}")
        api = H.Api(base, token=r.json().get("token", ""))

        def count(fmt):
            return H.db_scalar(db, "SELECT COUNT(*) FROM swipe_decisions WHERE user_id=? "
                               "AND decision_type='rank' AND scoring_format=?", (USER, fmt)) or 0

        sf_before, ppr_before = count("sf_tep"), count("1qb_ppr")
        mr_sf_before = H.db_scalar(db, "SELECT COUNT(*) FROM member_rankings WHERE user_id=? "
                                   "AND scoring_format='sf_tep'", (USER,)) or 0

        # 2-3. Rank 3 trios under sf_tep (header-scoped).
        ranked_ok = 0
        for _ in range(3):
            t = api.get("/api/trio?position=QB", headers=SF)   # QB matters in SF
            if t.status_code != 200:
                continue
            trio = t.json()
            ids = [trio[k]["id"] for k in ("player_a", "player_b", "player_c")]
            rk = api.post("/api/rank3", {"ranked": ids}, headers=SF)
            if rk.status_code == 200:
                ranked_ok += 1
        rec.check("sf-rank", ranked_ok == 3, f"{ranked_ok}/3 sf_tep trios ranked")

        sf_after, ppr_after = count("sf_tep"), count("1qb_ppr")
        rec.check("sf-rows-written", sf_after - sf_before == 9,
                  f"sf_tep rank rows +{sf_after - sf_before} (3 trios x 3 pairwise = 9)")
        rec.check("ppr-isolation", ppr_after == ppr_before,
                  f"1qb_ppr rank rows unchanged ({ppr_before} -> {ppr_after}) — formats isolated")

        # 4. member_rankings sf_tep partition.
        mr_sf_after = H.db_scalar(db, "SELECT COUNT(*) FROM member_rankings WHERE user_id=? "
                                  "AND scoring_format='sf_tep'", (USER,)) or 0
        rec.check("sf-member-rankings", mr_sf_after > mr_sf_before,
                  f"sf_tep member_rankings {mr_sf_before} -> {mr_sf_after}")

        # 5. Trade generation under sf_tep.
        g = api.post("/api/trades/generate", {"league_id": LEAGUE}, headers=SF)
        snap = g.json()
        jid = snap.get("job_id", "")
        t0 = time.monotonic()
        while snap.get("status") not in ("complete", "error") and time.monotonic() - t0 < 40:
            time.sleep(0.6)
            snap = api.get(f"/api/trades/status?job_id={jid}", headers=SF).json()
        cards = snap.get("cards") or []
        rec.check("sf-generate", snap.get("status") == "complete" and len(cards) > 0,
                  f"sf_tep generation -> {snap.get('status')} {len(cards)} cards")
        if cards:
            my = set(roster(db))
            bad = [c for c in cards
                   if not {str(p["id"]) for p in c.get("give", [])} <= my
                   or not (0 <= float(c.get("fairness_score", -1)) <= 1)]
            rec.check("sf-cards-valid", not bad,
                      f"{len(bad)} invalid sf_tep cards (roster/fairness)")

        # 6. Same player can hold different Elo across formats.
        rows = H.db_query(db, "SELECT scoring_format, elo FROM member_rankings WHERE user_id=? "
                          "AND player_id=(SELECT player_id FROM member_rankings WHERE user_id=? "
                          "AND scoring_format='sf_tep' LIMIT 1) ORDER BY scoring_format",
                          (USER, USER))
        fmts = {f: e for f, e in rows}
        rec.check("dual-format-independent", "sf_tep" in fmts,
                  f"per-format Elo present: {sorted(fmts)}"
                  + (f" (1qb={fmts.get('1qb_ppr'):.0f} sf={fmts.get('sf_tep'):.0f})"
                     if "1qb_ppr" in fmts and "sf_tep" in fmts else ""))
    finally:
        H.stop_server(proc)

    return rec.summary(SCRATCH / "TC-E2E-003-run.json",
                       meta={"test_case": "TC-E2E-003", "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})


if __name__ == "__main__":
    sys.exit(main())
