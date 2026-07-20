"""
test_users.py — synthetic stage-user spawner for onboarding QA.

Operator-only surface (routes in server.py: POST/DELETE /api/test-users,
gated on the `testing.stage_users` flag AND the tester allowlist —
experiments.load_tester_allowlist). Mints `qa_*` users that bypass Sleeper
entirely and ride the demo-league machinery, pre-seeded to a chosen adoption
stage so the onboarding flow (docs/plans/onboarding-conversion/plan.md +
guided-avatar-script.md) can be QA'd repeatably without touching real
Sleeper users.

Stages (cumulative):
  fresh       — users row only; client starts from onboarding defaults
  activated   — fresh + client_state says first swipes happened (client-only)
  board_owner — activated + a persisted WR QuickSet board (same storage as
                /api/tiers/save: users.tier_overrides + tiers_saved +
                ranking_method='quickset')
  converted   — board_owner + users.verified_at/verified_via='apple' stamps
                (verification only — NO accounts row; deep account flows
                like restore/deletion are not simulated)
  power       — converted + boards for all four positions + completed tour

`client_state` is the ftf_onboarding_state dict the MOBILE CLIENT should
adopt verbatim for the stage — swipe counts, guide progress etc. are client
state, so the server returns them for the client to apply rather than
persisting them.

qa_* user_ids are excluded from analytics cohort reports via
analytics_queries.device_exclusion (same choke point as demo_ ids).
"""

from __future__ import annotations

from sqlalchemy import delete as _sa_delete

from . import database as db
from .accounts import mark_user_verified
from .database import (
    DEFAULT_SCORING,
    save_tier_overrides,
    save_tiers_position,
    set_ranking_method,
)

# Spawnable stages, in adoption order.
STAGES: tuple[str, ...] = (
    "fresh", "activated", "board_owner", "converted", "power")

# Which positions get a pre-seeded QuickSet board, per stage.
BOARD_POSITIONS: dict[str, tuple[str, ...]] = {
    "board_owner": ("WR",),
    "converted":   ("WR",),
    "power":       ("QB", "RB", "WR", "TE"),
}

# Stages that carry the users-row verification stamps (mirrors what the
# Apple bind writes via accounts.mark_user_verified — verification only).
VERIFIED_STAGES: frozenset[str] = frozenset({"converted", "power"})

# Max players placed per position board (demo pools are smaller — WR has 10).
_BOARD_SIZE = 12

# Board shape: consecutive tier bands, top-down (tier names are the
# tier_config.json band keys — see ranking_service.ORDERED_TIERS). Top 2
# players → firsts_2, next 4 → first_1, next 3 → second, rest → third.
_TIER_SHAPE: tuple[tuple[str, int], ...] = (
    ("firsts_2", 2),
    ("first_1",  4),
    ("second",   3),
    ("third",    _BOARD_SIZE),   # remainder
)


# ---------------------------------------------------------------------------
# client_state — the ftf_onboarding_state the client adopts per stage
# ---------------------------------------------------------------------------

def client_state_for(stage: str) -> dict:
    """Return the onboarding client-state dict for `stage` (plain data —
    the mobile client applies it verbatim). Stages are cumulative."""
    state: dict = {}
    if stage == "fresh":
        return state
    state.update({"firstSwipeDone": True, "totalSwipes": 5, "sessionCount": 1})
    if stage == "activated":
        return state
    state.update({
        "quicksetCompletedPositions": ["WR"],
        "quicksetPromptShows": 1,
        "guideSeen": {"s0.1": True, "s0.2": True, "s1.1": True, "s2.1": True,
                      "s2.2": True, "s2.3": True, "s3.1": True, "s4.1": True},
    })
    if stage == "board_owner":
        return state
    state["applePromptShownFor"] = {"like": True, "quickset_save": True}
    state["celebrationsShown"] = {"first_like": True, "first_quickset_save": True}
    state["guideSeen"].update({"s6.1": True, "s6.2": True})
    if stage == "converted":
        return state
    # power
    state["quicksetCompletedPositions"] = ["QB", "RB", "WR", "TE"]
    state["guideTourCompleted"] = True
    state["guideSeen"]["s8.1"] = True
    return state


# ---------------------------------------------------------------------------
# Server-side stage seeding
# ---------------------------------------------------------------------------

def build_quickset_tiers(players: list, seed_ratings: dict,
                         position: str) -> dict[str, list[str]]:
    """Top-N `position` players from the pool by seed Elo, bucketed into the
    _TIER_SHAPE bands — the tiers dict shape /api/tiers/save takes."""
    pool = sorted(
        (p for p in players if p.position == position),
        key=lambda p: seed_ratings.get(p.id, 1500),
        reverse=True,
    )[:_BOARD_SIZE]
    tiers: dict[str, list[str]] = {}
    i = 0
    for tier_name, size in _TIER_SHAPE:
        chunk = pool[i:i + size]
        if chunk:
            tiers[tier_name] = [p.id for p in chunk]
        i += size
    return tiers


def seed_stage(user_id: str, stage: str, service, players: list,
               seed_ratings: dict,
               scoring_format: str = DEFAULT_SCORING) -> list[str]:
    """Persist the server-side artifacts for `stage` (users row must already
    exist). `service` is the session's live RankingService for
    `scoring_format` — boards are applied to it in memory AND persisted via
    the exact same calls /api/tiers/save uses (apply_tiers →
    save_tier_overrides → save_tiers_position + ranking_method='quickset'),
    so the session-replay path picks the board up naturally.

    Returns human-readable notes about what was (and wasn't) simulated.
    """
    notes: list[str] = []
    positions = BOARD_POSITIONS.get(stage, ())
    for pos in positions:
        tiers = build_quickset_tiers(players, seed_ratings, pos)
        service.apply_tiers(position=pos, tiers=tiers,
                            scoring_format=scoring_format,
                            cleared_pids=None)
        save_tiers_position(user_id, pos, scoring_format=scoring_format)
    if positions:
        save_tier_overrides(user_id, service._elo_overrides,
                            scoring_format=scoring_format)
        set_ranking_method(user_id, "quickset")
        notes.append(
            f"seeded quickset boards for {'/'.join(positions)} ({scoring_format})")
    if stage in VERIFIED_STAGES:
        mark_user_verified(user_id, "apple")
        notes.append(
            "verification stamped on the users row only (verified_at + "
            "verified_via='apple'); no accounts row — deep account flows "
            "(restore, in-app deletion) are not simulated")
    return notes


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------

def delete_test_user(user_id: str) -> dict[str, int]:
    """Delete every persisted row for a qa_* user (users + swipe_decisions +
    member_rankings — the tables the spawn/session paths write). The caller
    (route) enforces the qa_ prefix and evicts live sessions."""
    counts: dict[str, int] = {}
    with db.engine.begin() as conn:
        for name, tbl, col in (
            ("swipe_decisions", db.swipe_decisions_table,
             db.swipe_decisions_table.c.user_id),
            ("member_rankings", db.member_rankings_table,
             db.member_rankings_table.c.user_id),
            ("users", db.users_table, db.users_table.c.sleeper_user_id),
        ):
            res = conn.execute(_sa_delete(tbl).where(col == user_id))
            counts[name] = res.rowcount or 0
    return counts
