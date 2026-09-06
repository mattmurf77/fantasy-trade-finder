#!/usr/bin/env python3
"""seed_test_user_2.py — Seeds test user 2 (FantasyPros dynasty rankings, April 2026)
into the Fumble AI database as synthetic pairwise swipe decisions.

Notable ranking differences from Ranker 1:
  - C.J. Stroud dropped to QB 25 (was top-10)
  - Kyren Williams ranked ahead of Saquon Barkley
  - Tyler Warren at TE 3 (higher than consensus)
  - Travis Kelce at TE 24 (much lower than consensus)
  - Mark Andrews at TE 13

Usage:
    cd "<project root>"
    python scripts/seed_test_user_2.py [--dry-run] [--clear]

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
    main('fantasypros-2026')
