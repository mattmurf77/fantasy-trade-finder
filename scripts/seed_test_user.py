#!/usr/bin/env python3
"""
seed_test_user.py — Seeds test user 1 (FantasyPros dynasty rankings, April 2025)
into the Fumble AI database as synthetic pairwise swipe decisions.

The rankings are converted into swipe decisions that, when replayed by
RankingService.replay_from_db(), produce ELO scores matching the intended order.

Usage:
    cd "<project root>"
    python scripts/seed_test_user.py [--dry-run] [--clear]

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
TEST_USER_ID  = "test_user_fp_1"
TEST_USERNAME = "fp_ranker_1"
TEST_DISPLAY  = "FP Ranker 1"

# ── FantasyPros dynasty rankings snapshot (April 2025) ───────────────────────
# Format: (player_name, overall_dynasty_rank)   lower rank = better
# Source: FantasyPros dynasty overall rankings captured 4/6/2025

QB_RANKINGS = [
    ("Drake Maye",        17),
    ("Josh Allen",        19),
    ("Jayden Daniels",    22),
    ("Caleb Williams",    25),
    ("Justin Herbert",    29),
    ("Patrick Mahomes",   35),
    ("Joe Burrow",        36),
    ("Jaxson Dart",       38),
    ("Trevor Lawrence",   40),
    ("Brock Purdy",       42),
    ("Lamar Jackson",     46),
    ("Jordan Love",       48),
    ("Bo Nix",            50),
    ("Jalen Hurts",       52),
    ("Fernando Mendoza",  61),
    ("Cam Ward",          67),
    ("Dak Prescott",      69),
    ("Jared Goff",        71),
    ("Baker Mayfield",    72),
    ("C.J. Stroud",       80),
    ("Malik Willis",      82),
    ("Sam Darnold",       83),
    ("Tyler Shough",      86),
    ("Bryce Young",       96),
    ("Matthew Stafford", 106),
    ("Daniel Jones",     108),
    ("Kyler Murray",     112),
    ("Michael Penix",    114),
    ("J.J. McCarthy",    116),
    ("Ty Simpson",       142),
    ("Shedeur Sanders",  144),
    ("Tua Tagovailoa",   149),
]

RB_RANKINGS = [
    ("Bijan Robinson",         1),
    ("Jahmyr Gibbs",           4),
    ("De'Von Achane",          8),
    ("Ashton Jeanty",         10),
    ("Jeremiyah Love",        14),
    ("Omarion Hampton",       21),
    ("Breece Hall",           26),
    ("Kenneth Walker",        27),
    ("Jonathan Taylor",       28),
    ("James Cook",            30),
    ("Quinshon Judkins",      32),
    ("TreVeyon Henderson",    39),
    ("Javonte Williams",      53),
    ("Christian McCaffrey",   54),
    ("Saquon Barkley",        57),
    ("Josh Jacobs",           58),
    ("Travis Etienne",        60),
    ("Cam Skattebo",          65),
    ("Kyren Williams",        66),
    ("Bucky Irving",          75),
    ("Chase Brown",           91),
    ("David Montgomery",     104),
    ("D'Andre Swift",        105),
    ("Mike Washington",      111),
    ("Jadarian Price",       113),
    ("Jonah Coleman",        115),
    ("J.K. Dobbins",         129),
    ("Jonathon Brooks",      136),
    ("Derrick Henry",        140),
    ("Bhayshul Tuten",       143),
    ("RJ Harvey",            145),
    ("Rico Dowdle",          146),
    ("Tyjae Spears",         147),
    ("Kyle Monangai",        150),
    ("Rhamondre Stevenson",  151),
    ("Emmett Johnson",       152),
    ("Jaylen Warren",        154),
    ("Tyrone Tracy",         158),
    ("Demond Claiborne",     159),
    ("Adam Randall",         162),
    ("Chris Rodriguez",      171),
    ("Jaylen Wright",        172),
    ("Le'Veon Moss",         173),
    ("Blake Corum",          175),
    ("Tyler Allgeier",       176),
    ("Dylan Sampson",        177),
    ("Trey Benson",          178),
    ("Jacory Croskey-Merritt", 179),
    ("Woody Marks",          180),
    ("Kenneth Gainwell",     184),
    ("Kaleb Johnson",        186),
    ("Tony Pollard",         187),
]

WR_RANKINGS = [
    ("Jaxon Smith-Njigba",   2),
    ("Ja'Marr Chase",        3),
    ("Puka Nacua",           5),
    ("Malik Nabers",         6),
    ("Justin Jefferson",    11),
    ("CeeDee Lamb",         12),
    ("Amon-Ra St. Brown",   13),
    ("Drake London",        15),
    ("Tetairoa McMillan",   16),
    ("Garrett Wilson",      18),
    ("George Pickens",      20),
    ("Emeka Egbuka",        23),
    ("Chris Olave",         31),
    ("Rome Odunze",         33),
    ("Carnell Tate",        37),
    ("Ladd McConkey",       41),
    ("Brian Thomas",        43),
    ("Rashee Rice",         44),
    ("Marvin Harrison",     45),
    ("Nico Collins",        51),
    ("Jaylen Waddle",       55),
    ("Tee Higgins",         56),
    ("Makai Lemon",         63),
    ("A.J. Brown",          68),
    ("Zay Flowers",         70),
    ("Jameson Williams",    74),
    ("Jordyn Tyson",        76),
    ("Alec Pierce",         77),
    ("Ricky Pearsall",      78),
    ("Luther Burden III",   79),
    ("DJ Moore",            84),
    ("DeVonta Smith",       88),
    ("Jordan Addison",      89),
    ("Christian Watson",    90),
    ("Wan'Dale Robinson",   92),
    ("Romeo Doubs",         93),
    ("KC Concepcion",       94),
    ("Omar Cooper",         95),
    ("Jayden Reed",         97),
    ("Jayden Higgins",      98),
    ("Michael Wilson",      99),
    ("Denzel Boston",      100),
    ("Travis Hunter",      102),
    ("Michael Pittman",    107),
    ("Ted Hurst",          110),
    ("Chris Bell",         117),
    ("Chris Brazzell",     118),
    ("Matthew Golden",     122),
    ("Terry McLaurin",     124),
    ("DK Metcalf",         125),
    ("Davante Adams",      126),
    ("Deebo Samuel",       127),
    ("Jerry Jeudy",        130),
    ("Jauan Jennings",     132),
]

TE_RANKINGS = [
    ("Brock Bowers",       7),
    ("Trey McBride",       9),
    ("Colston Loveland",  24),
    ("Tyler Warren",      34),
    ("Kyle Pitts",        49),
    ("Harold Fannin Jr.", 62),
    ("Tucker Kraft",      73),
    ("Oronde Gadsden II", 81),
    ("Sam LaPorta",       85),
    ("Dalton Kincaid",    87),
    ("Mason Taylor",     103),
    ("Kenyon Sadiq",     109),
    ("Dallas Goedert",   119),
    ("Jake Ferguson",    120),
    ("Terrance Ferguson",123),
    ("T.J. Hockenson",   128),
    ("Isaiah Likely",    148),
    ("Eli Stowers",      157),
    ("Max Klare",        161),
    ("Michael Trigg",    167),
    ("Mark Andrews",     182),
    ("AJ Barner",        183),
    ("David Njoku",      195),
    ("George Kittle",    196),
    ("Juwan Johnson",    197),
    ("Elijah Arroyo",    210),
    ("Cade Otton",       214),
    ("Hunter Henry",     236),
    ("Gunnar Helm",      237),
    ("Evan Engram",      238),
    ("Brenton Strange",  246),
    ("Dalton Schultz",   247),
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

# Common Sleeper name aliases — (our_name_normalised, sleeper_full_name)
_ALIASES = {
    "amon ra st brown":   "Amon-Ra St. Brown",
    "aj brown":           "A.J. Brown",
    "dk metcalf":         "DK Metcalf",
    "dj moore":           "DJ Moore",
    "cj stroud":          "C.J. Stroud",
    "jj mccarthy":        "J.J. McCarthy",
    "tj hockenson":       "T.J. Hockenson",
    "jk dobbins":         "J.K. Dobbins",
    "devon achane":       "De'Von Achane",
    "jamarr chase":       "Ja'Marr Chase",
    "jaxon smithnjigba":  "Jaxon Smith-Njigba",
    "luther burden iii":  "Luther Burden III",
    "wandale robinson":   "Wan'Dale Robinson",
    "harold fannin jr":   "Harold Fannin Jr.",
    "oronde gadsden ii":  "Oronde Gadsden II",
    "jacory croskey merritt": "Jacory Croskey-Merritt",
    "rj harvey":          "RJ Harvey",
    "aj barner":          "AJ Barner",
    "kc concepcion":      "KC Concepcion",
}

def _resolve_alias(name: str) -> str:
    """Return canonical Sleeper name if an alias exists, else original."""
    key = _normalise(name)
    return _ALIASES.get(key, name)

# ── player lookup ─────────────────────────────────────────────────────────────

def build_name_index(conn) -> dict[str, str]:
    """
    Returns {normalised_full_name → player_id} for all players in the DB.
    Also adds a {normalised_last_name → player_id} fallback for unique last names.
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
