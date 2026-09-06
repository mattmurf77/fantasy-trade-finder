"""Shared local ranking seeder for the two preserved FantasyPros snapshots.

The wrapper CLIs in scripts/ select a fixed profile. Importing this module does
not load the application's database; main() loads it only after CLI parsing.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, insert, delete


MIN_SWIPES_PER_POS = 45
_SUFFIXES = re.compile(r"\b(jr|sr|ii|iii|iv|v|junior|senior)\b\.?$", re.IGNORECASE)


def load_profile(name: str) -> dict:
    """Load one of the two retained ranking snapshots, including its aliases."""
    if name not in {"fantasypros-2025", "fantasypros-2026"}:
        raise ValueError(f"Unknown ranking seed profile: {name}")
    return json.loads(Path(__file__).with_name(f"{name}.json").read_text())


def _normalise(name: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    name = name.lower()
    name = re.sub(r"['.`'\-]", "", name)   # remove apostrophes, dots, hyphens
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _strip_suffix(name: str) -> str:
    """Return name with trailing Jr./II/III/IV etc. removed."""
    return _SUFFIXES.sub("", name).strip()


def _resolve_alias(name: str, aliases: dict[str, str]) -> str:
    """Return canonical Sleeper name if an alias exists, else original."""
    key = _normalise(name)
    return aliases.get(key, name)


def build_name_index(conn, players_table) -> dict[str, str]:
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


def find_player_id(name: str, idx: dict[str, str], aliases: dict[str, str]) -> str | None:
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
    canonical = _resolve_alias(name, aliases)
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


def seed_user(profile, database, *, dry_run=False, clear=False):
    """Apply one profile to the supplied database, preserving the legacy CLI behavior."""
    engine = database.engine
    users_table = database.users_table
    players_table = database.players_table
    swipe_decisions_table = database.swipe_decisions_table
    user_id = profile["user_id"]
    now = datetime.now(timezone.utc).isoformat()

    with engine.begin() as conn:
        # ── Build name → player_id index ──────────────────────────────────────
        idx = build_name_index(conn, players_table)
        print(f"  Players in DB: {len(idx)}")

        # ── Clear existing data if requested ──────────────────────────────────
        if clear and not dry_run:
            deleted = conn.execute(
                delete(swipe_decisions_table).where(
                    swipe_decisions_table.c.user_id == user_id
                )
            ).rowcount
            print(f"  Cleared {deleted} existing swipe rows for {user_id}")

        # ── Upsert test user ──────────────────────────────────────────────────
        existing_user = conn.execute(
            select(users_table).where(users_table.c.sleeper_user_id == user_id)
        ).fetchone()

        if not existing_user and not dry_run:
            conn.execute(insert(users_table).values(
                sleeper_user_id = user_id,
                username        = profile["username"],
                display_name    = profile["display_name"],
                avatar          = None,
                created_at      = now,
            ))
            print(f"  Created user: {user_id}")
        elif existing_user:
            print(f"  User exists:  {user_id}")

        # ── Process each position ─────────────────────────────────────────────
        total_rows   = 0
        total_skip   = 0
        rows_to_insert: list[dict] = []

        for pos, rankings in profile["rankings"].items():
            # Sort by rank ascending (best first)
            sorted_ranks = sorted(rankings, key=lambda x: x[1])

            # Resolve player IDs
            resolved: list[tuple[str, str, int]] = []   # (name, player_id, rank)
            skipped:  list[str] = []

            for name, rank in sorted_ranks:
                pid = find_player_id(name, idx, profile["aliases"])
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
                    "user_id":          user_id,
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

        if dry_run:
            print("\n  [DRY RUN] No changes written.")
            return

        if rows_to_insert:
            conn.execute(insert(swipe_decisions_table), rows_to_insert)
            print(f"\n  ✅ Inserted {len(rows_to_insert)} swipe rows for {user_id}")
        else:
            print("\n  ⚠ Nothing to insert.")

    print("\nDone.")


def main(profile_name: str, argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without writing to DB")
    parser.add_argument("--clear", action="store_true",
                        help="Delete existing swipes for this test user first")
    args = parser.parse_args(argv)

    from backend import database

    seed_user(load_profile(profile_name), database,
              dry_run=args.dry_run, clear=args.clear)
