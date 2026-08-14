"""ADR-011 — league-state history capture (#46 Wrapped, P0).

One idempotent writer behind three triggers:

  A. on-sync   — server.py hooks beside the two league_members writers
                 (session-init daemon for Sleeper; the seven platform
                 import/refresh sites for ESPN/MFL/Fleaflicker), each in
                 its OWN transaction after the membership write commits.
  B. weekly    — the daily-tick weekday >= gate, server-side fetch on all
                 four platforms (YR-8), on a daemon thread.
  C. manual    — POST /api/cron/roster-snapshot.

This module is the shared row-building half: pure-ish functions taking
their inputs as arguments (pool seed, player metadata, priced picks) so
they are unit-testable without a Flask app or the universal-pool globals.
server.py owns trigger wiring and fetch adapters; database.py owns the
precedence-aware upserts.

The value contract (ADR-011): team_value is compute_power_rankings'
consensus-basis players total — NEVER a fresh summation, or the Wrapped
chart and the Power Rankings screen would show different numbers for the
same team in the same app. That call also inherits the codebase's
written-down K/DEF decision (out-of-pool players contribute 0.0), which
`valued_player_count` then makes legible instead of invisible.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from .database import (
    contested_pick_ids,
    latest_value_snapshot_date,
    load_draft_picks,
    load_member_boards_for_league,
    load_prev_roster_hashes,
    orphaned_pick_ids,
    upsert_board_snapshots,
    upsert_roster_snapshots,
)
from .power_rankings import compute_power_rankings

log = logging.getLogger("ftf.roster_history")

# Synthetic member-id prefixes: a "user_id" carrying one of these is a
# placeholder for an unlinked manager, not an FTF account — it must never
# be stored as owner_user_id (that column is a real-account pointer,
# resolved forward at link time via restamp_roster_history_owner).
# NOTE 'flea:' — _flea_member_id's actual prefix; 'fleaflicker:' and
# 'sleeper:' cover this module's own team-key vocabulary when a team_key
# doubles as the member id for an ownerless swept team.
_SYNTHETIC_PREFIXES = ("espn:", "mfl:", "flea:", "fleaflicker:", "sleeper:")


def iso_period_key(now: datetime | None = None) -> str:
    """The weekly bucket label — '2026-W33'. Uses the ISO week-numbering
    YEAR, never .year: 2026-12-31 is 2027-W01, and a %Y-keyed label would
    sort and dedupe wrong at the boundary."""
    now = now or datetime.now(timezone.utc)
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def roster_hash(player_ids: list) -> str:
    """Set-semantics change detector: sorted ids, first 16 hex chars."""
    joined = ",".join(sorted(str(p) for p in player_ids or []))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def real_owner_or_none(member_user_id: str | None) -> str | None:
    """owner_user_id is an FTF account pointer or NULL — a synthetic
    platform id stored there would defeat the re-stamp path."""
    uid = str(member_user_id or "")
    if not uid or uid.startswith(_SYNTHETIC_PREFIXES):
        return None
    return uid


def pick_fold_for_league(league_id: str, read_source: str) -> dict:
    """C3 fold-in inputs, per member user_id:

      {uid: {"pick_ids": [...], "pick_ids_excluded": [...], "pick_source": str}}

    pick_ids is what load_draft_picks already returns — contested and
    orphaned slots are dropped by its ROW FILTER (never by nulling
    pool_value; INV-5). pick_ids_excluded is the per-owner record of what
    that filter removed: THIS team asserted these slots and we decline to
    state them as fact. Non-empty => the recap suppresses pick flow for
    the league entirely rather than rendering it partially — a confident
    wrong story is worse than no story.
    """
    out: dict[str, dict] = {}
    try:
        clean = load_draft_picks(league_id=league_id, source=read_source)
        drop = contested_pick_ids(league_id) | orphaned_pick_ids(league_id)
        raw = (load_draft_picks(league_id=league_id, source=read_source,
                                include_contested=True)
               if drop else clean)
    except Exception as e:
        log.warning("pick fold-in failed (continuing without picks): %s", e)
        return out

    clean_ids = {str(r.get("pick_id")) for r in clean}
    for r in raw:
        uid = str(r.get("owner_user_id") or "")
        if not uid:
            continue
        g = out.setdefault(uid, {"pick_ids": [], "pick_ids_excluded": [],
                                 "_sources": set()})
        pid = str(r.get("pick_id"))
        if pid in clean_ids and pid not in drop:
            g["pick_ids"].append(pid)
            g["_sources"].add(r.get("source") or "platform")
        elif pid in drop:
            g["pick_ids_excluded"].append(pid)

    for g in out.values():
        srcs = g.pop("_sources")
        g["pick_source"] = (None if not srcs
                            else "mixed" if len(srcs) > 1
                            else next(iter(srcs)))
    return out


def build_roster_snapshot_rows(
    league_id: str,
    platform: str,
    scoring_format: str,
    teams: list[dict],
    source: str,
    *,
    seed: dict[str, float],
    players_meta: dict,
    picks_by_owner: dict[str, list[dict]] | None = None,
    pick_fold: dict | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Rows for upsert_roster_snapshots, one per team.

    teams: [{team_key, team_key_quality, member_user_id, player_ids,
             starter_ids|None}] — member_user_id is the league_members id
    (real FTF id or synthetic), used for pick attribution; owner_user_id
    on the row is derived from it (synthetic => NULL).
    """
    now = now or datetime.now(timezone.utc)
    period = iso_period_key(now)
    today = now.strftime("%Y-%m-%d")
    snapshot_at = now.isoformat()
    basis_date = latest_value_snapshot_date(scoring_format, today)
    prev_hashes = load_prev_roster_hashes(league_id, scoring_format, period)

    # THE value contract: one compute_power_rankings call for the league,
    # consensus basis (board_elo=None). Keyed back by the member user_id
    # each team was submitted under (which is also what picks_by_owner is
    # keyed by), so the pick pipeline prices identically to the Power
    # Rankings screen.
    members = [{"user_id": t["member_user_id"],
                "username": t["member_user_id"],
                "display_name": t["member_user_id"],
                "player_ids": [str(p) for p in (t.get("player_ids") or [])]}
               for t in teams]
    ranked = compute_power_rankings(
        members, seed, players_meta, board_elo=None,
        picks_by_owner=picks_by_owner or {})
    by_uid = {r["user_id"]: r for r in ranked}

    rows: list[dict] = []
    for t in teams:
        uid = str(t["member_user_id"])
        ids = sorted(str(p) for p in (t.get("player_ids") or []))
        r = by_uid.get(uid)
        valued = sum(1 for p in ids if p in seed)
        # NULL, never 0, when nothing prices — a zero renders as a roster
        # wipe and is indistinguishable from a real one; a NULL renders as
        # a gap. (Rendering rule: grey when NULL or valued < 0.8 * count,
        # never interpolate.)
        team_value = (round(float(r["positions_value"]), 1)
                      if r is not None and valued > 0 else None)
        picks_value = (round(float(r["picks"]["value"]), 1)
                       if r is not None and r.get("picks") else None)
        fold = (pick_fold or {}).get(uid) or {}
        h = roster_hash(ids)
        prev = prev_hashes.get(t["team_key"])
        rows.append({
            "league_id":           str(league_id),
            "team_key":            t["team_key"],
            "team_key_quality":    t.get("team_key_quality") or "strong",
            "platform":            platform,
            "owner_user_id":       real_owner_or_none(uid),
            "scoring_format":      scoring_format,
            "period_key":          period,
            "period_kind":         "week",
            "snapshot_date":       today,
            "snapshot_at":         snapshot_at,
            "player_ids":          json.dumps(ids),
            "starter_ids":         (json.dumps([str(s) for s in t["starter_ids"]])
                                    if t.get("starter_ids") else None),
            "pick_ids":            (json.dumps(fold["pick_ids"])
                                    if fold.get("pick_ids") else None),
            "pick_ids_excluded":   (json.dumps(fold["pick_ids_excluded"])
                                    if fold.get("pick_ids_excluded") else None),
            "pick_source":         fold.get("pick_source"),
            "roster_hash":         h,
            "changed_from_prev":   (None if prev is None else int(h != prev)),
            "player_count":        len(ids),
            "valued_player_count": valued,
            "team_value":          team_value,
            "team_value_picks":    picks_value,
            "value_basis_date":    basis_date,
            "in_season":           None,   # P0: not derived (no LeagueState build)
            "source":              source,
        })
    return rows


def snapshot_league_rosters(
    league_id: str,
    platform: str,
    scoring_format: str,
    teams: list[dict],
    source: str,
    *,
    seed: dict[str, float],
    players_meta: dict,
    picks_by_owner: dict[str, list[dict]] | None = None,
    pick_read_source: str = "platform",
    now: datetime | None = None,
) -> dict:
    """Build + upsert one league's roster snapshot. Returns the upsert
    counters. Raises nothing to the caller beyond what upsert raises —
    trigger sites wrap with their own try/except (continuing) per the
    house daemon pattern."""
    if not teams:
        return {"inserted": 0, "updated": 0,
                "skipped_precedence": 0, "skipped_unchanged": 0}
    fold = pick_fold_for_league(league_id, pick_read_source)
    rows = build_roster_snapshot_rows(
        league_id, platform, scoring_format, teams, source,
        seed=seed, players_meta=players_meta, picks_by_owner=picks_by_owner,
        pick_fold=fold, now=now)
    return upsert_roster_snapshots(rows)


def snapshot_league_boards(league_id: str, source: str,
                           now: datetime | None = None) -> dict:
    """C5/C6 — one complete-board snapshot per (member, format) for the
    period, from member_rankings (local read, no platform call, identical
    on every trigger). board_updated_at carries member_rankings.updated_at
    so one observation re-snapshotted five times never reads as five."""
    now = now or datetime.now(timezone.utc)
    period = iso_period_key(now)
    boards = load_member_boards_for_league(league_id)
    rows = [{
        "user_id":          b["user_id"],
        "league_id":        str(league_id),
        "scoring_format":   b["scoring_format"],
        "period_key":       period,
        "snapshot_date":    now.strftime("%Y-%m-%d"),
        "snapshot_at":      now.isoformat(),
        "elos":             json.dumps(b["elos"]),
        "player_count":     len(b["elos"]),
        "board_updated_at": b.get("board_updated_at"),
        "source":           source,
    } for b in boards if b.get("elos")]
    return upsert_board_snapshots(rows)
