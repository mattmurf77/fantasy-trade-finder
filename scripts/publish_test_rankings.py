#!/usr/bin/env python3
"""
publish_test_rankings.py
========================
One-time script to replay swipe decisions for test users and publish
their computed Elo ratings to member_rankings.

Run from the project root:

    python scripts/publish_test_rankings.py

This fixes the trade generation "0 cards" issue caused by test users
having swipe_decisions but no member_rankings entries.
"""

import sys, os

# Ensure project root is on sys.path so `backend` imports work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from backend.data_loader import load_consensus_elo, load_consensus_values, normalise_name
from backend.ranking_service import RankingService, Player
from backend.database import (
    load_swipe_decisions,
    upsert_member_rankings,
    init_db,
)

# Import the sleeper cache loader and universal pool builder.
# Importing server triggers module-level init (Flask, demo data, etc.) — harmless.
from backend.server import _load_sleeper_cache, build_universal_pool, elo_map


LEAGUE_ID = "test_league_lakeview"
TEST_USERS = ["test_user_fp_1", "test_user_fp_2"]


def main():
    print("🔧 publish_test_rankings — building universal player pool...")

    # Initialise DB tables (no-op if already exist)
    init_db()

    # Build the same universal player pool the app uses
    cache = _load_sleeper_cache()
    if not cache:
        print("❌ Could not load Sleeper player cache. Run the app at least once first.")
        sys.exit(1)

    scoring = os.environ.get("SCORING_FORMAT", "1qb")
    dp_vals = load_consensus_values(scoring=scoring)
    players, seed_ratings = build_universal_pool(
        sleeper_cache=cache,
        dp_elo=elo_map,
        dp_vals=dp_vals,
    )
    if not players:
        print("❌ Universal pool is empty — check DP data / Sleeper cache.")
        sys.exit(1)

    print(f"   ✅ {len(players)} players in universal pool")

    for user_id in TEST_USERS:
        print(f"\n── {user_id} ──")

        # 1. Load their stored swipe decisions
        swipes = load_swipe_decisions(user_id=user_id)
        if not swipes:
            print(f"   ⚠️  No swipe decisions found — skipping")
            continue
        print(f"   📊 {len(swipes)} swipe rows in DB")

        # 2. Build a RankingService and replay swipes
        svc = RankingService(
            players=players,
            seed_ratings=seed_ratings,
        )
        replayed = svc.replay_from_db(swipes)
        print(f"   🔁 {replayed} swipes replayed into Elo engine")

        # 3. Compute rankings across all positions
        rank_set = svc.get_rankings(position=None)
        rankings_payload = [
            {"player_id": rp.player.id, "elo": rp.elo}
            for rp in rank_set.rankings
        ]
        print(f"   📈 {len(rankings_payload)} player Elo ratings computed")

        # 4. Publish to member_rankings
        upsert_member_rankings(
            user_id=user_id,
            league_id=LEAGUE_ID,
            rankings=rankings_payload,
        )
        print(f"   ✅ Published {len(rankings_payload)} ratings to member_rankings")

    print("\n🎉 Done — restart the app and try 'Find a Trade' again.")


if __name__ == "__main__":
    main()
