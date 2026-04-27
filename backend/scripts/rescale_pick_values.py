"""One-shot backfill: recompute pick_value for every draft pick using the
actual league size (instead of the hardcoded 12-team baseline).

Idempotent — safe to re-run. League size is derived from the count of
distinct original_roster_id values per league in draft_picks_table.

Usage:
    python -m backend.scripts.rescale_pick_values [--dry-run] [--current-season 2026]
"""
from __future__ import annotations

import argparse
from collections import defaultdict

from sqlalchemy import select, update

from backend.database import (
    compute_pick_value,
    draft_picks_table,
    engine,
)


def rescale(current_season: int, dry_run: bool) -> None:
    with engine.begin() as conn:
        rows = conn.execute(
            select(
                draft_picks_table.c.id,
                draft_picks_table.c.league_id,
                draft_picks_table.c.season,
                draft_picks_table.c.round,
                draft_picks_table.c.original_roster_id,
                draft_picks_table.c.pick_value,
            )
        ).fetchall()

        league_size: dict[str, set[str]] = defaultdict(set)
        for r in rows:
            if r.original_roster_id:
                league_size[r.league_id].add(r.original_roster_id)

        updated = 0
        for r in rows:
            size = len(league_size.get(r.league_id, set())) or 12
            new_value = compute_pick_value(r.round, r.season, current_season, size)
            if new_value == r.pick_value:
                continue
            updated += 1
            if not dry_run:
                conn.execute(
                    update(draft_picks_table)
                    .where(draft_picks_table.c.id == r.id)
                    .values(pick_value=new_value)
                )

        action = "would update" if dry_run else "updated"
        print(f"{action} {updated} of {len(rows)} pick rows across {len(league_size)} leagues")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--current-season", type=int, default=2026)
    args = parser.parse_args()
    rescale(args.current_season, args.dry_run)
