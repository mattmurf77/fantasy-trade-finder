"""
demo_matchup.py — Smart Matchup Generator Demo
================================================
Run this to see Claude pick the most informative next dynasty matchup.

  cd Fantasy\ Trade\ Finder
  python -m scripts.demo_matchup

Set ANTHROPIC_API_KEY in your environment before running.
"""

import os
import sys

# Allow running from the project root: python -m scripts.demo_matchup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.smart_matchup_generator import SmartMatchupGenerator, Player, SwipeDecision


# ---------------------------------------------------------------------------
# Sample dynasty player pool (RB-heavy to keep the demo focused)
# ---------------------------------------------------------------------------

PLAYERS = [
    # Running Backs
    Player("rb_1",  "Breece Hall",       "RB", "NYJ", 23, 3),
    Player("rb_2",  "Bijan Robinson",    "RB", "ATL", 22, 2),
    Player("rb_3",  "Jahmyr Gibbs",      "RB", "DET", 22, 2),
    Player("rb_4",  "De'Von Achane",     "RB", "MIA", 23, 2),
    Player("rb_5",  "Jonathon Brooks",   "RB", "CAR", 22, 1),
    Player("rb_6",  "Kyren Williams",    "RB", "LAR", 25, 3),
    Player("rb_7",  "Isiah Pacheco",     "RB", "KC",  25, 3),
    Player("rb_8",  "Josh Jacobs",       "RB", "GB",  26, 6),
    Player("rb_9",  "Tony Pollard",      "RB", "TEN", 27, 6),
    Player("rb_10", "Derrick Henry",     "RB", "BAL", 30, 8),

    # Wide Receivers
    Player("wr_1",  "Ja'Marr Chase",     "WR", "CIN", 24, 4),
    Player("wr_2",  "CeeDee Lamb",       "WR", "DAL", 25, 5),
    Player("wr_3",  "Justin Jefferson",  "WR", "MIN", 25, 5),
    Player("wr_4",  "Malik Nabers",      "WR", "NYG", 21, 1),
    Player("wr_5",  "Rome Odunze",       "WR", "CHI", 22, 1),
    Player("wr_6",  "Puka Nacua",        "WR", "LAR", 23, 2),
]


# ---------------------------------------------------------------------------
# Simulated swipe history (a partially-ranked user)
# ---------------------------------------------------------------------------
# Imagine a user has done ~15 swipes on RBs and has a rough sense of the top tier,
# but hasn't settled the mid-tier yet.

SWIPE_HISTORY = [
    # Clear top-tier consensus
    SwipeDecision("rb_1",  "rb_10"),   # Breece > Henry (age)
    SwipeDecision("rb_2",  "rb_10"),   # Bijan > Henry
    SwipeDecision("rb_3",  "rb_10"),   # Gibbs > Henry
    SwipeDecision("rb_1",  "rb_9"),    # Breece > Pollard
    SwipeDecision("rb_2",  "rb_9"),    # Bijan > Pollard
    SwipeDecision("rb_4",  "rb_8"),    # Achane > Jacobs (age)
    SwipeDecision("rb_5",  "rb_9"),    # Brooks > Pollard (youth)
    SwipeDecision("rb_5",  "rb_10"),   # Brooks > Henry (age)
    # Mid-tier comparisons (only a few done)
    SwipeDecision("rb_1",  "rb_6"),    # Breece > Kyren
    SwipeDecision("rb_2",  "rb_7"),    # Bijan > Pacheco
    SwipeDecision("rb_3",  "rb_8"),    # Gibbs > Jacobs
    # No comparisons yet: rb_4 vs rb_6, rb_4 vs rb_7, rb_5 vs rb_6, etc.
]


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

def run_demo():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Set ANTHROPIC_API_KEY in your environment before running this demo.\n"
            "  export ANTHROPIC_API_KEY=your-key-here"
        )

    generator = SmartMatchupGenerator(api_key=api_key)

    print("=" * 62)
    print("  Fantasy Trade Finder — Smart Matchup Generator Demo")
    print("=" * 62)
    print(f"  Players loaded : {len(PLAYERS)}")
    print(f"  Swipes so far  : {len(SWIPE_HISTORY)}")
    print()

    # --- Demo 1: Next RB matchup ---
    print("📊 DEMO 1 — Next RB Matchup")
    print("-" * 62)
    p1, p2, reason = generator.generate_next_matchup(
        players=PLAYERS,
        swipe_history=SWIPE_HISTORY,
        position_filter="RB",
    )
    print(f"  ⚡ Claude picks: {p1.name} vs {p2.name}")
    print(f"  💬 Reasoning: {reason}")
    print()

    # --- Demo 2: Cold start (no history) ---
    print("📊 DEMO 2 — Cold Start (no swipe history)")
    print("-" * 62)
    p1, p2, reason = generator.generate_next_matchup(
        players=[p for p in PLAYERS if p.position == "WR"],
        swipe_history=[],
        position_filter="WR",
    )
    print(f"  ⚡ Claude picks: {p1.name} vs {p2.name}")
    print(f"  💬 Reasoning: {reason}")
    print()

    # --- Demo 3: All-position matchup ---
    print("📊 DEMO 3 — All Positions (mixed)")
    print("-" * 62)
    p1, p2, reason = generator.generate_next_matchup(
        players=PLAYERS,
        swipe_history=SWIPE_HISTORY,
    )
    print(f"  ⚡ Claude picks: {p1.name} ({p1.position}) vs {p2.name} ({p2.position})")
    print(f"  💬 Reasoning: {reason}")
    print()

    print("=" * 62)
    print("  Done! Integrate SmartMatchupGenerator into the")
    print("  Ranking Service to power the swipe feed.")
    print("=" * 62)


if __name__ == "__main__":
    run_demo()
