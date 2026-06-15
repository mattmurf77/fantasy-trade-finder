"""Concurrency probe for TC-DB-002. Runs against DATABASE_URL (a scratch copy).

Exercises the DB write paths under thread concurrency and emits JSON. Reused by
tc_db_002.py which interprets the results.
"""
import json
import sys
import threading

import backend.database as db
from sqlalchemy import text


def _count(sql, args=None):
    with db.engine.connect() as c:
        return c.execute(text(sql), args or {}).scalar()


def concurrent_member_rankings():
    """8 threads upsert the SAME (user,league,fmt) snapshot concurrently.
    upsert is a delete+insert replace — the final row count must equal the
    snapshot size (no accumulation, no partial state), and nothing should raise."""
    U, L = "qa_cc_u", "qa_cc_lg"
    snap = [{"player_id": str(p), "elo": 1500.0 + p} for p in range(20)]
    errors = []

    def w():
        try:
            db.upsert_member_rankings(U, L, snap, "1qb_ppr")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=w) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    final = _count("SELECT COUNT(*) FROM member_rankings WHERE user_id=:u AND league_id=:l",
                   {"u": U, "l": L})
    return {"errors": errors, "final_rows": final, "expected": len(snap)}


def concurrent_trade_decisions():
    """16 threads each persist a DISTINCT trade decision — none lost, none raised."""
    U, L = "qa_cc_u2", "qa_cc_lg2"
    errors = []

    def w(i):
        try:
            db.save_trade_decision(U, L, f"trade_{i}", [str(i)], [str(i + 100)],
                                   "like" if i % 2 else "pass")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=w, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    final = _count("SELECT COUNT(*) FROM trade_decisions WHERE user_id=:u", {"u": U})
    return {"errors": errors, "final_rows": final, "expected": 16}


def concurrent_ranking_swipes():
    """8 threads persist ranking swipes concurrently — exercises the swipe_decisions
    insert path + WAL under write contention. No 'database is locked'."""
    U = "qa_cc_u3"
    errors = []

    def w(i):
        try:
            db.save_ranking_swipes(U, [f"p{i}a", f"p{i}b", f"p{i}c"], scoring_format="1qb_ppr")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=w, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 8 threads x 3 pairwise = 24 swipe rows.
    final = _count("SELECT COUNT(*) FROM swipe_decisions WHERE user_id=:u AND decision_type='rank'",
                   {"u": U})
    return {"errors": errors, "final_rows": final, "expected": 24}


def match_recency_bound():
    """check_for_match must ignore likes older than 90 days."""
    L, A, B = "qa_rec_lg", "qa_rec_a", "qa_rec_b"
    # B likes [give=p1]->[recv=p2]; A's mirror is give=p2 recv=p1.
    db.save_trade_decision(B, L, "t_old", ["p1"], ["p2"], "like")
    fresh = db.check_for_match(current_user_id=A, league_id=L, target_user_id=B,
                               give_player_ids=["p2"], receive_player_ids=["p1"])
    # Age B's like to 100 days old, then it must drop out of the window.
    with db.engine.begin() as conn:
        conn.execute(text(
            "UPDATE trade_decisions SET created_at = :old WHERE user_id=:u AND trade_id='t_old'"),
            {"old": "2026-01-01T00:00:00+00:00", "u": B})  # >90d before 2026-06-11
    stale = db.check_for_match(current_user_id=A, league_id=L, target_user_id=B,
                               give_player_ids=["p2"], receive_player_ids=["p1"])
    return {"fresh_matches": bool(fresh), "stale_matches": bool(stale)}


def main():
    db.init_db()
    print(json.dumps({
        "member_rankings": concurrent_member_rankings(),
        "trade_decisions": concurrent_trade_decisions(),
        "ranking_swipes": concurrent_ranking_swipes(),
        "recency": match_recency_bound(),
    }))


if __name__ == "__main__":
    main()
