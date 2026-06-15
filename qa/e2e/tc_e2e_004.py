#!/usr/bin/env python3
"""
TC-E2E-004 — Cross-league flow: matches/all, awaiting, portfolio, and the
cross-league DISPOSITION branch (accept a match from a league other than the
session's active one — the path that skips in-memory Elo apply and relies on
persistence to replay into the correct league's service).

  1. matches/all returns matches across ALL the user's leagues.
  2. awaiting returns one-sided likes (cross-league).
  3. portfolio returns cross-league exposure.
  4. Create a fresh match in league A; switch session to league B; disposition
     the league-A match -> 200, decision recorded, no crash, status correct.

Uses the multi-league fixture user 313560442465169408 (mattmurf77).

Usage:  python3 qa/e2e/tc_e2e_004.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import harness as H  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch4"
MULTI_USER = "313560442465169408"           # in test_league_lakeview + 3 others
LEAGUE_A = "test_league_lakeview"           # has rankings + a counterparty
LEAGUE_B = "1101407304802574336"            # a different league the user owns
PARTNER = "test_user_fp_1"
rec = H.CheckRecorder()


def roster(db, league, user):
    raw = H.db_scalar(db, "SELECT roster_data FROM league_members "
                      "WHERE league_id=? AND user_id=?", (league, user))
    return [str(x) for x in (json.loads(raw) if raw else []) if x]


def init(base, db, user, league):
    return H.Api(base).post("/api/session/init", {
        "user_id": user, "username": user, "display_name": user,
        "league_id": league, "league_name": f"QA {league[:6]}",
        "user_player_ids": roster(db, league, user), "opponent_rosters": []}).json().get("token", "")


def card_ids(c, side):
    return [str(p["id"]) for p in c.get(side, [])]


def generate(api, league):
    snap = api.post("/api/trades/generate", {"league_id": league}).json()
    jid = snap.get("job_id", "")
    t0 = time.monotonic()
    while snap.get("status") not in ("complete", "error") and time.monotonic() - t0 < 40:
        time.sleep(0.5)
        snap = api.get(f"/api/trades/status?job_id={jid}").json()
    return snap.get("cards") or []


def main() -> int:
    print("TC-E2E-004 — cross-league flow")
    db = H.make_scratch_db(SCRATCH, "qa_x.db")
    proc, base = H.boot_server(db, 5191, SCRATCH / "server.log",
                               env_overrides={"CRON_SECRET": None})
    try:
        # Session in league A.
        tok_a = init(base, db, MULTI_USER, LEAGUE_A)
        rec.check("init-A", bool(tok_a), "session_init user in league A")
        api_a = H.Api(base, tok_a)

        # 1. matches/all spans leagues (fixture has 4 matches in league A).
        r = api_a.get("/api/trades/matches/all")
        all_matches = r.json() if r.status_code == 200 else []
        leagues_seen = {m.get("league_id") for m in all_matches} if isinstance(all_matches, list) else set()
        rec.check("matches-all", r.status_code == 200 and len(all_matches) >= 1,
                  f"matches/all -> {len(all_matches) if isinstance(all_matches, list) else '?'} matches "
                  f"across leagues {sorted(x for x in leagues_seen if x)}")

        # 2. awaiting (one-sided likes; may be empty — must be a clean array).
        r = api_a.get("/api/trades/awaiting")
        rec.check("awaiting", r.status_code == 200 and isinstance(r.json(), list),
                  f"awaiting -> {r.status_code}, array len={len(r.json()) if r.status_code == 200 else '?'}")

        # 3. portfolio cross-league.
        r = api_a.get(f"/api/portfolio?league_ids={LEAGUE_A},{LEAGUE_B}")
        rec.check("portfolio", r.status_code == 200,
                  f"portfolio (2 leagues) -> {r.status_code}")

        # 4. Cross-league disposition. First create a FRESH match in league A:
        #    partner likes a card targeting MULTI_USER, MULTI_USER likes mirror.
        tok_p = init(base, db, PARTNER, LEAGUE_A)
        api_p = H.Api(base, tok_p)
        cards = generate(api_p, LEAGUE_A)
        # partner's card whose target is MULTI_USER, 1-for-1, not already matched.
        existing = {(frozenset(json.loads(g)), frozenset(json.loads(r2)))
                    for g, r2 in H.db_query(db, "SELECT user_a_give, user_a_receive "
                                            "FROM trade_matches WHERE league_id=?", (LEAGUE_A,))}
        existing |= {(b, a) for a, b in existing}
        card = next((c for c in cards
                     if str(c.get("target_user_id")) == MULTI_USER
                     and len(card_ids(c, "give")) == 1 and len(card_ids(c, "receive")) == 1
                     and (frozenset(card_ids(c, "give")), frozenset(card_ids(c, "receive"))) not in existing),
                    None)
        if not rec.check("fresh-card", card is not None,
                         f"partner has a fresh 1-for-1 card targeting the multi-league user "
                         f"(deck={len(cards)})"):
            return rec.summary(SCRATCH / "TC-E2E-004-run.json", meta={"test_case": "TC-E2E-004"})
        give, recv = card_ids(card, "give"), card_ids(card, "receive")
        before_m = H.db_scalar(db, "SELECT COUNT(*) FROM trade_matches WHERE league_id=?", (LEAGUE_A,))
        api_p.post("/api/trades/swipe", {
            "trade_id": card["trade_id"], "decision": "like",
            "give_player_ids": give, "receive_player_ids": recv,
            "target_user_id": MULTI_USER, "target_username": MULTI_USER, "league_id": LEAGUE_A})
        # MULTI_USER likes the mirror (in league A). The match may be created by
        # EITHER swipe depending on prior likes in the fixture — what matters is
        # a fresh pending match now exists for this user in league A.
        api_a.post("/api/trades/swipe", {
            "trade_id": "qa-x-mirror", "decision": "like",
            "give_player_ids": recv, "receive_player_ids": give,
            "target_user_id": PARTNER, "target_username": PARTNER, "league_id": LEAGUE_A})
        after_m = H.db_scalar(db, "SELECT COUNT(*) FROM trade_matches WHERE league_id=?", (LEAGUE_A,))
        # Newest pending match in league A where MULTI_USER hasn't decided yet.
        row = H.db_query(db, "SELECT id, user_a_id, user_b_id, user_a_decision, user_b_decision "
                         "FROM trade_matches WHERE league_id=? AND status='pending' ORDER BY id DESC",
                         (LEAGUE_A,))
        match_id, my_side = None, None
        for mid, ua, ub, uad, ubd in row:
            if ua == MULTI_USER and not uad:
                match_id, my_side = mid, "a"; break
            if ub == MULTI_USER and not ubd:
                match_id, my_side = mid, "b"; break
        rec.check("match-created", after_m - before_m == 1 and match_id is not None,
                  f"fresh match created in league A: id={match_id} (multi-user is side {my_side}, undecided)")

        if match_id:
            # Switch MULTI_USER's session to league B, then disposition the
            # league-A match -> CROSS-LEAGUE path.
            tok_b = init(base, db, MULTI_USER, LEAGUE_B)
            api_b = H.Api(base, tok_b)
            r = api_b.post(f"/api/trades/matches/{match_id}/disposition", {"decision": "accept"})
            rec.check("xleague-dispo-200", r.status_code == 200,
                      f"cross-league accept (session on B, match in A) -> {r.status_code} "
                      f"{r.text[:120] if r.status_code != 200 else ''}")
            # The disposition must be recorded for the match's own league, and the
            # Elo signal persisted (replays into league A's service on next init).
            col = "user_a_decision" if my_side == "a" else "user_b_decision"
            dec = H.db_scalar(db, f"SELECT {col} FROM trade_matches WHERE id=?", (match_id,))
            rec.check("xleague-recorded", dec == "accept",
                      f"{col} persisted on the league-A match: {dec!r}")
            disp_swipes = H.db_scalar(db, "SELECT COUNT(*) FROM swipe_decisions "
                                      "WHERE decision_type='disposition' AND user_id=?", (MULTI_USER,))
            rec.check("xleague-elo-persisted", (disp_swipes or 0) >= 1,
                      f"disposition Elo signal persisted for replay: {disp_swipes} rows")
    finally:
        H.stop_server(proc)

    return rec.summary(SCRATCH / "TC-E2E-004-run.json",
                       meta={"test_case": "TC-E2E-004", "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})


if __name__ == "__main__":
    sys.exit(main())
