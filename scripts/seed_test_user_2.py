#!/usr/bin/env python3
"""
seed_test_user_2.py — Seeds test user 2 (FantasyPros dynasty rankings, April 2026)
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
"""

import os
import sys
import argparse
import re
from datetime import datetime, timezone

# ── path setup ───────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sqlalchemy import select, insert, delete, text
from backend.database import engine, users_table, swipe_decisions_table, players_table

# ── test user ─────────────────────────────────────────────────────────────────
TEST_USER_ID  = "test_user_fp_2"
TEST_USERNAME = "fp_ranker_2"
TEST_DISPLAY  = "FP Ranker 2"

# ── FantasyPros dynasty rankings snapshot (April 2026) ───────────────────────
# Format: (player_name, overall_dynasty_rank)   lower rank = better
# Source: FantasyPros dynasty overall rankings captured 4/12/2026

QB_RANKINGS = [
    ("Drake Maye",        31),
    ("Josh Allen",        32),
    ("Caleb Williams",    51),
    ("Jayden Daniels",    52),
    ("Jalen Hurts",       62),
    ("Patrick Mahomes",   70),
    ("Jaxson Dart",       71),
    ("Lamar Jackson",     72),
    ("Joe Burrow",        73),
    ("Justin Herbert",    77),
    ("Brock Purdy",       87),
    ("Baker Mayfield",    88),
    ("Trevor Lawrence",   89),
    ("Jordan Love",       93),
    ("Jared Goff",        94),
    ("Bo Nix",            95),
    ("Fernando Mendoza", 118),
    ("Dak Prescott",     129),
    ("Kyler Murray",     130),
    ("Cam Ward",         131),
    ("Sam Darnold",      132),
    ("Ty Simpson",       139),
    ("Malik Willis",     169),
    ("Daniel Jones",     170),
    ("C.J. Stroud",      171),
    ("Tyler Shough",     196),
    ("J.J. McCarthy",    197),
    ("Michael Penix",    198),
    ("Bryce Young",      203),
    ("Tua Tagovailoa",   204),
    ("Shedeur Sanders",  206),
    ("Matthew Stafford", 208),
    ("Aaron Rodgers",    209),
]

RB_RANKINGS = [
    ("Bijan Robinson",        1),
    ("Jahmyr Gibbs",          5),
    ("De'Von Achane",         6),
    ("Jeremiyah Love",       11),
    ("Omarion Hampton",      13),
    ("Ashton Jeanty",        14),
    ("Jonathan Taylor",      18),
    ("TreVeyon Henderson",   19),
    ("Breece Hall",          21),
    ("Quinshon Judkins",     24),
    ("James Cook",           27),
    ("Christian McCaffrey",  39),
    ("Bucky Irving",         40),
    ("Kyren Williams",       46),   # RB 14 — ranked ahead of Barkley by this ranker
    ("Saquon Barkley",       47),
    ("Kenneth Walker",       48),
    ("Javonte Williams",     49),
    ("Josh Jacobs",          56),
    ("Travis Etienne",       64),
    ("Cam Skattebo",         65),
    ("Chase Brown",          74),
    ("Jonah Coleman",        79),
    ("Jadarian Price",       80),
    ("RJ Harvey",            81),
    ("Mike Washington",      96),
    ("D'Andre Swift",        97),
    ("Kyle Monangai",       105),
    ("Rico Dowdle",         109),
    ("Bhayshul Tuten",      114),
    ("Derrick Henry",       116),
    ("David Montgomery",    123),
    ("Tyjae Spears",        124),
    ("Trey Benson",         136),
    ("Jaylen Warren",       137),
    ("J.K. Dobbins",        142),
    ("Alvin Kamara",        143),
    ("Tyler Allgeier",      146),
    ("Woody Marks",         147),
    ("Zach Charbonnet",     148),
    ("Braelon Allen",       149),
    ("Tony Pollard",        150),
    ("Chuba Hubbard",       151),
    ("Blake Corum",         155),
    ("Jonathon Brooks",     156),
    ("Kaleb Johnson",       157),
    ("Brian Robinson",      159),
    ("Rhamondre Stevenson", 160),
    ("Devin Neal",          161),
    ("Tyrone Tracy",        168),
    ("Aaron Jones",         177),
    ("Jordan Mason",        178),
    ("Brashard Smith",      179),
    ("Emmett Johnson",      180),
    ("Isiah Pacheco",       183),
]

WR_RANKINGS = [
    ("Jaxon Smith-Njigba",   2),
    ("Ja'Marr Chase",        3),
    ("Puka Nacua",           4),
    ("CeeDee Lamb",          7),
    ("Justin Jefferson",    10),
    ("Amon-Ra St. Brown",   12),
    ("Malik Nabers",        15),
    ("Drake London",        16),
    ("Tetairoa McMillan",   17),
    ("Garrett Wilson",      20),
    ("Carnell Tate",        22),
    ("Nico Collins",        23),
    ("Ladd McConkey",       25),
    ("Makai Lemon",         26),
    ("Rome Odunze",         28),
    ("George Pickens",      29),
    ("Emeka Egbuka",        30),
    ("Rashee Rice",         33),
    ("Chris Olave",         34),
    ("Marvin Harrison",     35),
    ("Brian Thomas",        36),
    ("Jordyn Tyson",        37),
    ("Zay Flowers",         41),
    ("Luther Burden III",   44),
    ("Jaylen Waddle",       45),
    ("Tee Higgins",         50),
    ("DeVonta Smith",       53),
    ("A.J. Brown",          55),
    ("Denzel Boston",       59),
    ("Omar Cooper",         60),
    ("Jordan Addison",      63),
    ("Jameson Williams",    67),
    ("Ricky Pearsall",      69),
    ("Christian Watson",    76),
    ("Michael Wilson",      78),
    ("KC Concepcion",       86),
    ("DK Metcalf",          87),
    ("Ja'Kobi Lane",        90),
    ("DJ Moore",            91),
    ("Chris Godwin",        92),
    ("Alec Pierce",         98),
    ("Michael Pittman",     99),
    ("Davante Adams",      100),
    ("Germie Bernard",     101),
    ("Malachi Fields",     102),
    ("Chris Brazzell",     106),
    ("Rashid Shaheed",     107),
    ("Quentin Johnston",   108),
    ("Matthew Golden",     110),
    ("Xavier Worthy",      111),
    ("Terry McLaurin",     112),
    ("Jayden Higgins",     113),
    ("Courtland Sutton",   115),
    ("Romeo Doubs",        117),
    ("Troy Franklin",      119),
]

TE_RANKINGS = [
    ("Brock Bowers",       8),
    ("Trey McBride",       9),
    ("Tyler Warren",      38),
    ("Colston Loveland",  54),
    ("Tucker Kraft",      57),
    ("Harold Fannin Jr.", 58),
    ("Sam LaPorta",       61),
    ("Kyle Pitts",        66),
    ("Kenyon Sadiq",      68),
    ("Oronde Gadsden II", 75),
    ("Eli Stowers",       83),
    ("Jake Ferguson",     84),
    ("Mark Andrews",      85),
    ("Mason Taylor",     103),
    ("Dalton Kincaid",   104),
    ("George Kittle",    127),
    ("Isaiah Likely",    128),
    ("David Njoku",      145),
    ("Max Klare",        160),
    ("T.J. Hockenson",   163),
    ("Dallas Goedert",   181),
    ("Michael Trigg",    185),
    ("Jonnu Smith",      186),
    ("Travis Kelce",     187),
    ("Evan Engram",      193),
    ("Gunnar Helm",      223),
    ("Hunter Henry",     227),
    ("Cade Otton",       229),
    ("Theo Johnson",     230),
    ("Juwan Johnson",    231),
    ("Elijah Arroyo",    239),
    ("AJ Barner",        240),
    ("Terrance Ferguson",241),
]

ALL_POSITIONS = [
    ("QB", QB_RANKINGS),
    ("RB", RB_RANKINGS),
    ("WR", WR_RANKINGS),
    ("TE", TE_RANKINGS),
]

# ── name normalisation ────────────────────────────────────────────────────────

_SUFFIXES = re.compile(
    r"\b(jr|sr|ii|iii|iv|v|junior|senior)\b\.?$", re.IGNORECASE
)

def _normalise(name: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    name = name.lower()
    name = re.sub(r"['.`'\-]", "", name)   # remove apostrophes, dots, hyphens
    name = re.sub(r"\s+", " ", name).strip()
    return name

def _strip_suffix(name: str) -> str:
    """Return name with trailing Jr./II/III/IV etc. removed."""
    return _SUFFIXES.sub("", name).strip()

# Common Sleeper name aliases — (our_name_normalised → sleeper_full_name)
_ALIASES = {
    "amon ra st brown":      "Amon-Ra St. Brown",
    "aj brown":              "A.J. Brown",
    "dk metcalf":            "DK Metcalf",
    "dj moore":              "DJ Moore",
    "cj stroud":             "C.J. Stroud",
    "jj mccarthy":           "J.J. McCarthy",
    "tj hockenson":          "T.J. Hockenson",
    "jk dobbins":            "J.K. Dobbins",
    "devon achane":          "De'Von Achane",
    "jamarr chase":          "Ja'Marr Chase",
    "jaxon smithnjigba":     "Jaxon Smith-Njigba",
    "luther burden iii":     "Luther Burden III",
    "harold fannin jr":      "Harold Fannin Jr.",
    "oronde gadsden ii":     "Oronde Gadsden II",
    "rj harvey":             "RJ Harvey",
    "aj barner":             "AJ Barner",
    "kc concepcion":         "KC Concepcion",
    "jakobi lane":           "Ja'Kobi Lane",
}

def _resolve_alias(name: str) -> str:
    """Return canonical Sleeper name if an alias exists, else original."""
    key = _normalise(name)
    return _ALIASES.get(key, name)

# ── player lookup ─────────────────────────────────────────────────────────────

def build_name_index(conn) -> dict[str, str]:
    """
    Returns {normalised_full_name → player_id} for all players in the DB.
    """
    rows = conn.execute(
        select(players_table.c.player_id, players_table.c.full_name)
    ).fetchall()

    idx: dict[str, str] = {}
    for pid, full_name in rows:
        if full_name:
            idx[_normalise(full_name)] = pid

    return idx

def find_player_id(name: str, idx: dict[str, str]) -> str | None:
    """
    Try progressively looser matches:
      1. Direct normalised match
      2. Alias lookup
      3. Suffix-stripped match  (e.g. "Luther Burden III" → "Luther Burden")
      4. Last-name + first-initial fallback
    """
    # 1. Direct normalised match
    key = _normalise(name)
    if key in idx:
        return idx[key]

    # 2. Alias lookup
    canonical = _resolve_alias(name)
    key2 = _normalise(canonical)
    if key2 in idx:
        return idx[key2]

    # 3. Suffix-stripped match (handles Jr. / II / III stored without suffix in Sleeper)
    stripped = _strip_suffix(_normalise(name))
    if stripped and stripped != key and stripped in idx:
        return idx[stripped]

    # 4. Last-name + first-initial match
    parts = name.split()
    if len(parts) >= 2:
        last  = _normalise(parts[-1])
        first = _normalise(parts[0])[0]   # first initial
        for full_key, pid in idx.items():
            fk_parts = full_key.split()
            if fk_parts and fk_parts[-1] == last and fk_parts[0].startswith(first):
                return pid

    return None

# ── swipe generation ──────────────────────────────────────────────────────────
# Each group of 3 consecutive (winner, loser) pairs = 1 "interaction" when
# replayed by RankingService.replay_from_db() (it divides swipe count by 3).
# We need ≥ 10 interactions = ≥ 30 swipe rows per position.
# Target: 45 rows (15 interactions) per position for comfortable headroom.

MIN_SWIPES_PER_POS = 45   # → 15 interactions

def generate_swipes(ordered_ids: list[str]) -> list[tuple[str, str]]:
    """
    Generate (winner_id, loser_id) pairs from a best→worst ordered list.

    Strategy:
      Pass 1 — step 1:  adjacent pairs  (0,1), (1,2), (2,3) ...
      Pass 2 — step 2:  skip-one pairs  (0,2), (2,4), (4,6) ...
      Pass 3 — step 4:  long-range      (0,4), (4,8), (8,12) ...
      Pass 4 — step 8:  very long range (0,8), (8,16) ...

    Stops after we have enough rows.  The ordering encodes who wins each pair.
    """
    n = len(ordered_ids)
    pairs: list[tuple[str, str]] = []

    for step in [1, 2, 4, 8, 16]:
        for i in range(0, n - step):
            pairs.append((ordered_ids[i], ordered_ids[i + step]))
        if len(pairs) >= MIN_SWIPES_PER_POS:
            break

    # Round down to nearest multiple of 3 so interaction count is an integer
    keep = (len(pairs) // 3) * 3
    return pairs[:keep]

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without writing to DB")
    parser.add_argument("--clear", action="store_true",
                        help="Delete existing swipes for this test user first")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).isoformat()

    with engine.begin() as conn:
        # ── Build name → player_id index ──────────────────────────────────────
        idx = build_name_index(conn)
        print(f"  Players in DB: {len(idx)}")

        # ── Clear existing data if requested ──────────────────────────────────
        if args.clear and not args.dry_run:
            deleted = conn.execute(
                delete(swipe_decisions_table).where(
                    swipe_decisions_table.c.user_id == TEST_USER_ID
                )
            ).rowcount
            print(f"  Cleared {deleted} existing swipe rows for {TEST_USER_ID}")

        # ── Upsert test user ──────────────────────────────────────────────────
        existing_user = conn.execute(
            select(users_table).where(users_table.c.sleeper_user_id == TEST_USER_ID)
        ).fetchone()

        if not existing_user and not args.dry_run:
            conn.execute(insert(users_table).values(
                sleeper_user_id = TEST_USER_ID,
                username        = TEST_USERNAME,
                display_name    = TEST_DISPLAY,
                avatar          = None,
                created_at      = now,
            ))
            print(f"  Created user: {TEST_USER_ID}")
        elif existing_user:
            print(f"  User exists:  {TEST_USER_ID}")

        # ── Process each position ─────────────────────────────────────────────
        total_rows   = 0
        total_skip   = 0
        rows_to_insert: list[dict] = []

        for pos, rankings in ALL_POSITIONS:
            # Sort by rank ascending (best first)
            sorted_ranks = sorted(rankings, key=lambda x: x[1])

            # Resolve player IDs
            resolved: list[tuple[str, str, int]] = []   # (name, player_id, rank)
            skipped:  list[str] = []

            for name, rank in sorted_ranks:
                pid = find_player_id(name, idx)
                if pid:
                    resolved.append((name, pid, rank))
                else:
                    skipped.append(name)

            print(f"\n  {pos}: {len(resolved)} matched, {len(skipped)} not found")
            if skipped:
                print(f"       Skipped: {', '.join(skipped)}")

            if len(resolved) < 3:
                print(f"       ⚠ Too few players matched — skipping {pos}")
                continue

            # Generate swipes from ordered IDs
            ordered_ids = [pid for _, pid, _ in resolved]
            swipes = generate_swipes(ordered_ids)

            interactions = len(swipes) // 3
            print(f"       Swipe rows: {len(swipes)} → {interactions} interactions")

            # Build DB rows
            for winner_id, loser_id in swipes:
                rows_to_insert.append({
                    "user_id":          TEST_USER_ID,
                    "winner_player_id": winner_id,
                    "loser_player_id":  loser_id,
                    "decision_type":    "rank",
                    "k_factor":         32.0,
                    "created_at":       now,
                })

            total_rows += len(swipes)
            total_skip += len(skipped)

        # ── Write to DB ───────────────────────────────────────────────────────
        print(f"\n  Total swipe rows to insert: {total_rows}")
        print(f"  Total players skipped:      {total_skip}")

        if args.dry_run:
            print("\n  [DRY RUN] No changes written.")
            return

        if rows_to_insert:
            conn.execute(insert(swipe_decisions_table), rows_to_insert)
            print(f"\n  ✅ Inserted {len(rows_to_insert)} swipe rows for {TEST_USER_ID}")
        else:
            print("\n  ⚠ Nothing to insert.")

    print("\nDone.")


if __name__ == "__main__":
    main()
