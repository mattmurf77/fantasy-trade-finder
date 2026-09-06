#!/usr/bin/env python3
"""seed_test_user.py — Seeds test user 1 (FantasyPros dynasty rankings, April 2025)
into the Fumble AI database as synthetic pairwise swipe decisions.

The rankings are converted into swipe decisions that, when replayed by
RankingService.replay_from_db(), produce ELO scores matching the intended order.

Usage:
    cd "<project root>"
    python scripts/seed_test_user.py [--dry-run] [--clear]

Flags:
    --dry-run   Print matches and swipe count without writing to DB
    --clear     Delete existing swipe data for this test user before seeding

Compatibility entry point; shared implementation and named data live in fixtures/.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.fixtures.seed_rankings import main


if __name__ == "__main__":
    main('fantasypros-2025')
