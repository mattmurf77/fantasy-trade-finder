#!/usr/bin/env python3
"""
create_test_league.py — Create a test league for UAT

Creates a test league by cloning all members from the real Lakeview League,
but REPLACING two real teams with test user credentials:

  - 454869184224948224 (DrByron34) → test_user_fp_1 / fp_ranker_1 / "FP Ranker 1"
  - 694249360803848192 (sauter)    → test_user_fp_2 / fp_ranker_2 / "FP Ranker 2"

The test users inherit the replaced teams' actual Sleeper roster player IDs.
All other 10 teams (including mattmurf77) remain exactly as-is.

Usage:
    cd "<project root>"
    python3 scripts/create_test_league.py [--dry-run] [--clear]

Flags:
    --dry-run   Print plan without writing to DB
    --clear     Delete the test league and re-create it fresh
"""

import os, sys, json, argparse
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sqlalchemy import text, select, insert, delete
from backend.database import (
    engine, leagues_table, league_members_table
)

# ── Config ────────────────────────────────────────────────────────────────────

SOURCE_LEAGUE_ID = "1312076055586050048"   # The real Lakeview League to clone
TEST_LEAGUE_ID   = "test_league_lakeview"
TEST_LEAGUE_NAME = "Lakeview League (Test)"

# Teams to replace: real_user_id → (test_user_id, test_username, test_display)
REPLACE_TEAMS = {
    "454869184224948224": ("test_user_fp_1", "fp_ranker_1", "FP Ranker 1"),
    "694249360803848192": ("test_user_fp_2", "fp_ranker_2", "FP Ranker 2"),
}

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--clear",   action="store_true",
                        help="Delete existing test league before re-creating")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).isoformat()

    with engine.begin() as conn:

        # ── Load source league members ────────────────────────────────────────
        src_members = conn.execute(
            text("SELECT user_id, username, display_name, roster_data "
                 "FROM league_members WHERE league_id=:lid ORDER BY username"),
            {"lid": SOURCE_LEAGUE_ID}
        ).fetchall()

        if not src_members:
            print(f"  ❌ Source league {SOURCE_LEAGUE_ID!r} not found. Aborting.")
            return

        print(f"\n  Source league: {SOURCE_LEAGUE_ID}")
        print(f"  Members to process: {len(src_members)}")

        # Build the final member list: replace targeted teams with test users
        final_members = []  # list of (user_id, username, display_name, roster_json)
        for row in src_members:
            uid, uname, display, roster_json = row
            if uid in REPLACE_TEAMS:
                test_uid, test_uname, test_display = REPLACE_TEAMS[uid]
                print(f"  Replacing {uname!r} ({uid}) → {test_uname!r} ({test_uid})")
                final_members.append((test_uid, test_uname, test_display, roster_json))
            else:
                final_members.append((uid, uname, display, roster_json))

        print(f"\n  Final member count: {len(final_members)}")

        # ── Dry run summary ───────────────────────────────────────────────────
        if args.dry_run:
            print(f"\n  Would create league: {TEST_LEAGUE_NAME!r}  id={TEST_LEAGUE_ID!r}")
            print(f"  Members:")
            for uid, uname, display, roster_json in final_members:
                roster = json.loads(roster_json) if roster_json else []
                print(f"    {uid}  {uname}  ({len(roster)} players)")
            print("\n  [DRY RUN] No changes written.")
            return

        # ── Clear if requested ────────────────────────────────────────────────
        if args.clear:
            conn.execute(delete(league_members_table).where(
                league_members_table.c.league_id == TEST_LEAGUE_ID))
            conn.execute(delete(leagues_table).where(
                leagues_table.c.sleeper_league_id == TEST_LEAGUE_ID))
            print(f"\n  Cleared existing test league {TEST_LEAGUE_ID!r}")

        # ── Insert leagues row (use first test user as the "owner" row) ───────
        test_uid_1, test_uname_1, test_display_1 = REPLACE_TEAMS["454869184224948224"]
        # Build opponent_data from the final members
        opponent_data = []
        for uid, uname, display, roster_json in final_members:
            roster = json.loads(roster_json) if roster_json else []
            opponent_data.append({
                "user_id":    uid,
                "username":   uname or uid,
                "player_ids": roster,
            })

        # Find test user 1's roster
        test_roster_1 = []
        for uid, uname, display, roster_json in final_members:
            if uid == test_uid_1:
                test_roster_1 = json.loads(roster_json) if roster_json else []
                break

        existing_league = conn.execute(
            text("SELECT 1 FROM leagues WHERE sleeper_league_id=:lid AND user_id=:uid"),
            {"lid": TEST_LEAGUE_ID, "uid": test_uid_1}
        ).fetchone()

        if existing_league:
            conn.execute(
                text("""UPDATE leagues SET name=:name, season=:season,
                         roster_data=:rd, opponent_data=:od, updated_at=:now
                         WHERE sleeper_league_id=:lid AND user_id=:uid"""),
                {"name": TEST_LEAGUE_NAME, "season": "2026",
                 "rd": json.dumps(test_roster_1), "od": json.dumps(opponent_data),
                 "now": now, "lid": TEST_LEAGUE_ID, "uid": test_uid_1}
            )
            print(f"\n  Updated existing leagues row for {test_uid_1}")
        else:
            conn.execute(insert(leagues_table).values(
                sleeper_league_id = TEST_LEAGUE_ID,
                user_id           = test_uid_1,
                name              = TEST_LEAGUE_NAME,
                season            = "2026",
                roster_data       = json.dumps(test_roster_1),
                opponent_data     = json.dumps(opponent_data),
                created_at        = now,
                updated_at        = now,
            ))
            print(f"\n  Created leagues row for {test_uid_1}")

        # ── Insert/update league_members ──────────────────────────────────────
        members_written = 0
        for uid, uname, display, roster_json in final_members:
            existing = conn.execute(
                text("SELECT 1 FROM league_members WHERE league_id=:lid AND user_id=:uid"),
                {"lid": TEST_LEAGUE_ID, "uid": uid}
            ).fetchone()
            if existing:
                conn.execute(
                    text("""UPDATE league_members SET username=:un, display_name=:dn,
                             roster_data=:rd, updated_at=:now
                             WHERE league_id=:lid AND user_id=:uid"""),
                    {"un": uname, "dn": display, "rd": roster_json,
                     "now": now, "lid": TEST_LEAGUE_ID, "uid": uid}
                )
            else:
                conn.execute(insert(league_members_table).values(
                    league_id    = TEST_LEAGUE_ID,
                    user_id      = uid,
                    username     = uname,
                    display_name = display,
                    roster_data  = roster_json,
                    updated_at   = now,
                ))
            members_written += 1

        print(f"  League members written: {members_written}")
        print(f"\n  ✅ Test league {TEST_LEAGUE_ID!r} ready.")
        print(f"\n  To use for UAT:")
        for real_uid, (test_uid, test_uname, test_display) in REPLACE_TEAMS.items():
            print(f"    Login as: {test_uname}  (replaces real team {real_uid})")
        print(f"    League:   {TEST_LEAGUE_NAME}")

    print("\nDone.")


if __name__ == "__main__":
    main()
