#!/usr/bin/env python3
"""
Seed the full trade-disposition matrix for mattmurf77 in "Lakeview League (Test)",
with simple counterparties (User1..User5) so you can both (a) see an event for
EVERY outcome the other owner can take, and (b) log in as each counterparty to
drive the other side live (login enablement is a separate backend change).

Creates / ensures:
  • users User1..User5 (+ their league_members rows, with small real rosters)
  • trade_decisions: one LIKE, one PASS (your outbound swipes)
  • trade_matches covering every state, one counterparty each:
      User1  new (neither decided)        — either side can act
      User2  you accepted, awaiting them  — log in as User2 to accept/decline
      User3  they accepted, you to decide
      User4  fully accepted (both)
      User5  declined (they declined)
  • notifications for YOU covering every other-owner outcome:
      trade_match     (match formed)        ×5
      trade_accepted  (they accepted)       (User4)
      trade_declined  (they declined)       (User5)

Idempotent (clears prior seed by marker first). Local by default; prod via
  DATABASE_URL=$DATABASE_URL_PROD python3 qa/seed_test_dispositions.py
"""
import json, os, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from database import engine, metadata  # noqa: E402
from sqlalchemy import select, delete, insert, func  # noqa: E402

TD = metadata.tables["trade_decisions"]
TM = metadata.tables["trade_matches"]
NO = metadata.tables["notifications"]
PL = metadata.tables["players"]
U  = metadata.tables["users"]
LM = metadata.tables["league_members"]

LEAGUE = "test_league_lakeview"
MATT = "313560442465169408"
MARK = "fb-test-disp"          # notification metadata marker
TID = "seedfb_"               # trade_decisions marker

# counterparty test users + a small real-player roster each (give-side pool)
USERS = {
    "User1": ["7553", "9494"],   # Kyle Pitts, Marvin Mims
    "User2": ["9224", "8112"],   # Chase Brown, Drake London
    "User3": ["9481", "9504"],   # Luke Musgrave, Kayshon Boutte
    "User4": ["7090", "4017"],   # Darnell Mooney, Deshaun Watson
    "User5": ["12476", "11565"], # Devin Neal, J.J. McCarthy
}
def now(m=0): return (datetime.now(timezone.utc) - timedelta(minutes=m)).isoformat()

def main():
    print(f"DB: {engine.url}")
    with engine.begin() as c:
        names = dict(c.execute(select(PL.c.player_id, PL.c.full_name)).all())
        nm = lambda p: names.get(p, p)

        # ---- ensure User1..User5 exist (users + league_members) ----------
        for uid, roster in USERS.items():
            has_user = c.execute(select(func.count()).select_from(U)
                                 .where(U.c.sleeper_user_id == uid)).scalar()
            if not has_user:
                c.execute(insert(U).values(sleeper_user_id=uid, username=uid,
                                           display_name=uid, created_at=now()))
            has_member = c.execute(select(func.count()).select_from(LM)
                                   .where((LM.c.league_id == LEAGUE) & (LM.c.user_id == uid))).scalar()
            if not has_member:
                c.execute(insert(LM).values(league_id=LEAGUE, user_id=uid, username=uid,
                                            display_name=uid, roster_data=json.dumps(roster),
                                            updated_at=now()))

        # ---- idempotency: clear prior seed -------------------------------
        c.execute(delete(TD).where(TD.c.trade_id.like(TID + "%")))
        c.execute(delete(NO).where((NO.c.user_id == MATT) & (NO.c.metadata_json.like("%" + MARK + "%"))))
        # clear our matches: the new User1..5 set AND the prior seed's real-name
        # counterparties (so re-running supersedes the earlier vs-SwaggyJ0 seed).
        _OLD = ["852254555294019584", "852263741075611648", "852266560109293568"]
        c.execute(delete(TM).where((TM.c.league_id == LEAGUE) & (TM.c.user_b_id == MATT)
                                   & (TM.c.user_a_id.in_(list(USERS) + _OLD))))

        # ---- your outbound swipes ----------------------------------------
        c.execute(insert(TD), [
            dict(user_id=MATT, league_id=LEAGUE, trade_id=TID + "like1",
                 give_player_ids=json.dumps(["12470"]), receive_player_ids=json.dumps(["9494"]),
                 decision="like", created_at=now(120)),
            dict(user_id=MATT, league_id=LEAGUE, trade_id=TID + "pass1",
                 give_player_ids=json.dumps(["11439"]), receive_player_ids=json.dumps(["4017"]),
                 decision="pass", created_at=now(118)),
        ])

        # ---- matches: user_a = counterparty, user_b = Matt ---------------
        # user_a_give = they give = YOU RECEIVE ; user_a_receive = YOU GIVE
        MATCHES = [
            # (counterparty, they_give, you_give, status, their_dec, your_dec, mins, label)
            ("User1", "7553", "11559", "pending",  None,     None,     45, "new — neither decided"),
            ("User2", "9224", "9508",  "pending",  None,     "accept", 90, "you accepted, awaiting them"),
            ("User3", "9481", "12470", "pending",  "accept", None,     25, "they accepted, you to decide"),
            ("User4", "7090", "9501",  "accepted", "accept", "accept", 200, "fully accepted"),
            ("User5", "12476","11439", "declined", "decline","accept", 220, "they declined"),
        ]
        created = []
        for cp, they_give, you_give, status, their, your, mins, label in MATCHES:
            res = c.execute(insert(TM).values(
                league_id=LEAGUE, user_a_id=cp, user_b_id=MATT,
                user_a_give=json.dumps([they_give]), user_a_receive=json.dumps([you_give]),
                matched_at=now(mins), status=status,
                user_a_decision=their, user_b_decision=your,
                user_a_decided_at=now(mins-5) if their else None,
                user_b_decided_at=now(mins-3) if your else None,
            ))
            mid = res.inserted_primary_key[0]
            you_get, you_send = nm(they_give), nm(you_give)
            base = {"match_id": mid, "partner_username": cp, "league_name": "Lakeview League (Test)",
                    "give": [you_send], "receive": [you_get], "seed_marker": MARK}

            # (1) match-formed event — every match
            c.execute(insert(NO).values(
                user_id=MATT, type="trade_match",
                title=f"🤝 New trade match with {cp} in Lakeview League (Test)!",
                body=f"New trade match with {cp}! {you_send} for {you_get}",
                metadata_json=json.dumps(base),
                is_read=0 if status == "pending" else 1, created_at=now(mins)))

            # (2) other-owner OUTCOME event — accepted / declined
            outcome = None
            if status == "accepted":
                outcome = ("trade_accepted", "✅", "accepted")
            elif status == "declined":
                outcome = ("trade_declined", "❌", "declined")
            if outcome:
                t, emoji, verb = outcome
                c.execute(insert(NO).values(
                    user_id=MATT, type=t,
                    title=f"{emoji} {cp} {verb} your trade in Lakeview League (Test)",
                    body=f"{emoji} {cp} {verb} your trade: {you_send} for {you_get}",
                    metadata_json=json.dumps(base),
                    is_read=0, created_at=now(mins-2)))
            created.append((mid, cp, label, you_send, you_get, status))

    print("\nCounterparties ensured: " + ", ".join(USERS))
    print("Swipes: LIKE (Riley Leonard→Marvin Mims), PASS (Jaleel McLaughlin→Deshaun Watson)")
    print("Matches + events for YOU (every other-owner outcome covered):")
    for mid, cp, label, g, r, st in created:
        print(f"  • #{mid:<4} vs {cp:<6} [{label:<30}] you give {g} / get {r}  (status={st})")
    print("  notifications: trade_match ×5, trade_accepted ×1 (User4), trade_declined ×1 (User5)")
    print("Done. Idempotent — re-run to reset.")

if __name__ == "__main__":
    main()
