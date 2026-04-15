"""
data_loader.py — Fantasy Trade Finder
======================================
Fetches the DynastyProcess consensus values CSV and maps each player's
dynasty trade value onto an initial Elo rating.

Source: https://github.com/dynastyprocess/data
File:   files/values-players.csv

CSV columns used:
  player      — player name (string)
  pos         — position: QB | RB | WR | TE
  value_1qb   — dynasty trade value, 0-10000 scale (1QB scoring)
  value_2qb   — dynasty trade value, 0-10000 scale (Superflex/2QB)

Elo seeding formula:
  elo = ELO_MIN + (value / VALUE_MAX) * ELO_RANGE
  → value 10000 ≈ Elo 1800  (elite dynasty asset)
  → value  5000 ≈ Elo 1500  (solid starter)
  → value     0 ≈ Elo 1200  (bench/depth)

This gives every player a cross-position baseline derived from community
consensus. User swipes personalise the rankings from there.
"""

import csv
import io
import re
import urllib.request
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VALUES_URL = (
    "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"
)

ELO_MIN   = 1200.0
ELO_MAX   = 1800.0
ELO_RANGE = ELO_MAX - ELO_MIN
VALUE_MAX = 10_000.0

# Positions we care about
VALID_POSITIONS = {"QB", "RB", "WR", "TE"}

# ---------------------------------------------------------------------------
# Name-mismatch reference table: DynastyProcess → Sleeper
# ---------------------------------------------------------------------------
# DP includes suffixes (Jr., Sr., II, III) that Sleeper strips.  This table
# maps the normalised DP name to the normalised Sleeper name so we can join
# them correctly without a lossy last-name fallback.
#
# Generated 2026-04-12 from a full cross-reference of the DP values CSV
# against the Sleeper player cache.  Validated by the user.

DP_TO_SLEEPER_NAME: dict[str, str] = {
    "aaron jones sr": "aaron jones",
    "anthony richardson sr": "anthony richardson",
    "brian robinson jr": "brian robinson",
    "brian thomas jr": "brian thomas",
    "calvin austin iii": "calvin austin",
    "cedrick wilson jr": "cedrick wilson",
    "chris brazzell ii": "chris brazzell",
    "chris godwin jr": "chris godwin",
    "chris rodriguez jr": "chris rodriguez",
    "darrell henderson jr": "darrell henderson",
    "deebo samuel sr": "deebo samuel",
    "donte thornton jr": "donte thornton",
    "efton chism iii": "efton chism",
    "erick all jr": "erick all",
    "gardner minshew ii": "gardner minshew",
    "harold fannin jr": "harold fannin",
    "henry ruggs iii": "henry ruggs",
    "james cook iii": "james cook",
    "jeff wilson jr": "jeff wilson",
    "jimmy horn jr": "jimmy horn",
    "joe milton iii": "joe milton",
    "john metchie iii": "john metchie",
    "kenneth walker iii": "kenneth walker",
    "kevin coleman jr": "kevin coleman",
    "kyle pitts sr": "kyle pitts",
    "laviska shenault jr": "laviska shenault",
    "lequint allen jr": "lequint allen",
    "lew nichols iii": "lew nichols",
    "luther burden iii": "luther burden",
    "marvin harrison jr": "marvin harrison",
    "marvin mims jr": "marvin mims",
    "mecole hardman jr": "mecole hardman",
    "michael penix jr": "michael penix",
    "michael pittman jr": "michael pittman",
    "mike washington jr": "mike washington",
    "odell beckham jr": "odell beckham",
    "ollie gordon ii": "ollie gordon",
    "omar cooper jr": "omar cooper",
    "oronde gadsden ii": "oronde gadsden",
    "patrick mahomes ii": "patrick mahomes",
    "pierre strong jr": "pierre strong",
    "rayray mccloud iii": "rayray mccloud",
    "robert henry jr": "robert henry",
    "russell gage jr": "russell gage",
    "thomas fidone ii": "thomas fidone",
    "travis etienne jr": "travis etienne",
    "trent sherfield sr": "trent sherfield",
    "tyrone tracy jr": "tyrone tracy",
    "velus jones jr": "velus jones",
    "vinny anthony ii": "vinny anthony",
}

# DP players with no valid Sleeper counterpart — exclude from the pool
DP_EXCLUDED: set[str] = {
    "bam knight",
    "barion brown",
    "dallen bentley",
    "frank gore jr",
    "terion stewart",
    "tyren montgomery",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_consensus_elo(
    scoring: str = "1qb",          # "1qb" or "2qb" (superflex)
    fallback_elo: float = 1500.0,  # rating for players not found in the data
    timeout: int = 10,
) -> dict[str, float]:
    """
    Fetch DynastyProcess values and return a dict of:
        { normalised_player_name: initial_elo_rating }

    Keys are normalised (lowercase, alphanumeric only) so they can be
    matched against your player pool with `normalise_name()`.

    Returns an empty dict (falls back to flat 1500) if the fetch fails.
    """
    elo_map, _ = _fetch_dynasty_process(scoring=scoring, timeout=timeout)
    return elo_map


def load_consensus_values(
    scoring: str = "1qb",
    timeout: int = 10,
) -> dict[str, float]:
    """
    Fetch DynastyProcess values and return a dict of:
        { normalised_player_name: raw_dynasty_value (0-10000) }

    Only includes players with value > 0.
    Used to determine which Sleeper players should be in the universal
    ranking pool (any player with a positive dynasty trade value).
    """
    _, value_map = _fetch_dynasty_process(scoring=scoring, timeout=timeout)
    return value_map


def _fetch_dynasty_process(
    scoring: str = "1qb",
    timeout: int = 10,
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Internal: fetch DynastyProcess CSV and return both:
        (elo_map, value_map)
    where:
        elo_map   = { normalised_name: initial_elo }
        value_map = { normalised_name: raw_value }  (only for value > 0)
    """
    value_col = f"value_{scoring}"

    try:
        req = urllib.request.Request(
            VALUES_URL,
            headers={"User-Agent": "FantasyTradeFinder/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as e:
        print(f"⚠️  DynastyProcess fetch failed ({e}) — using flat Elo baseline")
        return {}, {}

    elo_map: dict[str, float] = {}
    value_map: dict[str, float] = {}

    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        pos = (row.get("pos") or "").strip().upper()
        if pos not in VALID_POSITIONS:
            continue

        name_raw = (row.get("player") or "").strip()
        if not name_raw:
            continue

        value_str = (row.get(value_col) or "0").strip()
        try:
            value = float(value_str)
        except ValueError:
            value = 0.0

        elo = ELO_MIN + (min(value, VALUE_MAX) / VALUE_MAX) * ELO_RANGE
        normed = normalise_name(name_raw)

        # Skip DP players with no valid Sleeper counterpart
        if normed in DP_EXCLUDED:
            continue

        # Translate DP name to Sleeper name via reference table
        lookup_key = DP_TO_SLEEPER_NAME.get(normed, normed)

        elo_map[lookup_key] = round(elo, 1)
        if value > 0:
            value_map[lookup_key] = value

    print(f"✅ Loaded {len(elo_map)} player values from DynastyProcess "
          f"({len(value_map)} with value > 0)")
    return elo_map, value_map


def seed_elo_for_players(
    players,                        # list[Player]
    elo_map: dict[str, float],
    fallback_elo: float = 1500.0,
) -> dict[str, float]:
    """
    Match your Player objects against the DynastyProcess elo_map and
    return a dict of { player.id: initial_elo }.

    Matching is by exact normalised name only.  The DP_TO_SLEEPER_NAME
    reference table (applied in _fetch_dynasty_process) has already
    translated DP names into Sleeper names, so no fuzzy fallback is needed.

    Unmatched players receive fallback_elo (1500 by default).
    """
    seeded: dict[str, float] = {}
    unmatched: list[str] = []

    for player in players:
        key = normalise_name(player.name)

        if key in elo_map:
            seeded[player.id] = elo_map[key]
        else:
            seeded[player.id] = fallback_elo
            unmatched.append(player.name)

    if unmatched:
        print(f"ℹ️  {len(unmatched)} players unmatched in consensus data "
              f"(using {fallback_elo} Elo): {', '.join(unmatched[:5])}"
              + (" …" if len(unmatched) > 5 else ""))

    return seeded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalise_name(name: str) -> str:
    """Lowercase, remove punctuation/accents, collapse whitespace."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", "", name)   # strip punctuation
    name = re.sub(r"\s+", " ", name).strip()
    return name
