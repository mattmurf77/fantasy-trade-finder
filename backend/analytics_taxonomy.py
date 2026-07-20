"""
analytics_taxonomy.py — single source of truth for analytics event names.

Analytics platform P0 (docs/plans/analytics-platform/lld.md §1.1/§6.4b; HLD
§2.2). Three registries live here:

  ALLOWED_CLIENT_EVENTS — the client-fired allowlist enforced by
      POST /api/events (moved out of server.py at P0; server.py imports it).
      New client event types require a tracking-plan addendum first
      (default-deny; unknown types are counted + dropped, never 4xx'd).

  SERVER_FIRED_EVENTS — every event name the backend itself writes via
      database.record_event(). These are server-authoritative: rows carry
      event_id=NULL forever (LLD §6.2) and clients may NEVER submit them
      through /api/events.

  FUNNEL_CRITICAL — client events the SDK queue must retain under overflow
      (drop-last policy, LLD §3.4). Hand-mirrored into each client SDK port
      and copy-checked by eng-qa until OQ-5 promotes it to generated JSON.

Import-time invariant: the client and server namespaces are disjoint. A
collision would let a client forge a server-authoritative row (or make
reports double-count), so the module refuses to import on one.
"""

from __future__ import annotations

# Server-side registries that already encode server-authoritative names.
from .database import _EVENT_TO_USER_COL, _RANK_STREAK_EVENTS

# ---------------------------------------------------------------------------
# Client-fired allowlist (enforced by POST /api/events)
# ---------------------------------------------------------------------------
# Event names + envelope are a cross-client contract — see
# docs/cross-client-invariants.md and the tracking plan
# (docs/business/analytics/2026-07-17-tracking-plan-v2.md).

ALLOWED_CLIENT_EVENTS: frozenset[str] = frozenset({
    # Lifecycle / navigation
    "app_opened", "app_backgrounded", "screen_viewed", "client_error",
    # Observability addendum (tracking plan v2, 2026-07-19): universal API-
    # failure signal from the client wrapper + explicit screen-exit so dwell
    # time has a real terminator instead of a next-screen_viewed inference.
    "api_request_failed", "screen_left",
    # Pre-auth funnel
    "signin_attempted", "signin_succeeded", "signin_failed",
    "league_selected", "demo_entered",
    # Ranking
    "rank_method_selected",
    # Trades
    "find_trades_tapped", "trade_card_viewed", "trade_flagged",
    "match_opened",
    # Engagement
    "push_opened",
    # Onboarding & conversion plan (docs/plans/onboarding-conversion/plan.md)
    "apple_prompt_shown", "apple_prompt_accepted", "apple_prompt_declined",
    "apple_prompt_dismissed",
    "quickset_prompt_shown", "quickset_prompt_accepted",
    "quickset_prompt_snoozed",
    "trade_card_shared",
    "coach_mark_shown", "coach_mark_dismissed",
    "celebration_shown", "deck_exhausted_viewed",
    # Guided avatar tour (docs/plans/onboarding-conversion/guided-avatar-script.md §6)
    "guide_step_shown", "guide_step_advanced", "guide_step_skipped",
    "guide_tour_dismissed", "guide_tour_completed",
})

# ---------------------------------------------------------------------------
# Server-fired taxonomy (record_event call sites; event_id is always NULL)
# ---------------------------------------------------------------------------

SERVER_FIRED_EVENTS: frozenset[str] = frozenset({
    # Session
    "signup", "login", "logout", "app_open",
    # Ranking
    "trio_swipe", "tier_save", "ranking_complete_first_time",
    "ranking_method_changed", "ranking_reorder", "anchor_answered",
    "quickset_completed", "quickrank_completed", "swipe",
    # Trades
    "trade_proposed", "match_swiped", "match_viewed", "match_dismissed",
    "trade_accepted", "trade_declined", "trade_ratified", "counter_sent",
    "trade_match", "trades_generated", "calc_trade_evaluated",
    # Engagement / misc
    "push_sent", "notif_pref_changed", "league_synced", "wrapped_viewed",
    "feedback_submitted", "asset_pref_added", "asset_pref_removed",
})

# ---------------------------------------------------------------------------
# Funnel-critical client events (SDK overflow retention, LLD §3.4)
# ---------------------------------------------------------------------------

FUNNEL_CRITICAL: frozenset[str] = frozenset({
    "app_opened_first",
    "signin_attempted",
    "signin_succeeded",
    "experiment_exposed",
})

# ---------------------------------------------------------------------------
# Per-event client prop allowlist (ingest step 7, LLD §4.1 — unknown props
# are STRIPPED + counted, the event itself is still accepted)
# ---------------------------------------------------------------------------
# Union of the tracking-plan "Key props" columns (tracking plan v2 §S3 +
# addendum) and the props the shipped mobile client actually fires today —
# the two have drifted (e.g. the client sends coach_mark `mark` where the
# plan says `mark_key`, apple_prompt `trigger` vs `trigger_moment`).
# Stripping live props would silently destroy data, so both spellings are
# legal until a tracking-plan addendum reconciles them. New props require a
# tracking-plan PR first (default-deny).
#
# Props the SERVER stamps after stripping (`seq` from the envelope,
# `ts_suspect` from the client_ts clamp) never pass through this filter and
# deliberately do not appear here.

CLIENT_EVENT_PROPS: dict[str, frozenset[str]] = {
    # Lifecycle / navigation
    "app_opened":        frozenset({"launch_type", "from_push", "push_kind"}),
    "app_backgrounded":  frozenset({"session_ms", "screens_viewed"}),
    "screen_viewed":     frozenset({"screen", "prev_screen", "tab"}),
    "client_error":      frozenset({"screen", "error_kind", "message", "fatal"}),
    # route is NORMALIZED client-side (query stripped, id runs → ':id') so
    # cardinality stays bounded and no user identifiers ride in props.
    "api_request_failed": frozenset({"route", "method", "status", "ms", "timeout"}),
    "screen_left":        frozenset({"screen", "dwell_ms", "reason"}),
    # Pre-auth funnel
    "signin_attempted":  frozenset({"method", "has_league_url"}),
    "signin_succeeded":  frozenset({"method"}),
    "signin_failed":     frozenset({"method", "error_code"}),
    "league_selected":   frozenset({"league_index", "league_count", "platform",
                                    "auto", "league_type"}),
    "demo_entered":      frozenset({"source"}),
    # Ranking
    "rank_method_selected": frozenset({"method", "is_first_time"}),
    # Trades
    "find_trades_tapped":   frozenset(),
    "trade_card_viewed":    frozenset({"trade_id", "card_index", "lane",
                                       "dwell_ms", "ms_since_open",
                                       "cold_start"}),
    "trade_flagged":        frozenset({"reason", "trade_id"}),
    "match_opened":         frozenset({"match_id"}),
    # Engagement
    "push_opened":          frozenset({"kind", "dedup_key"}),
    # Onboarding & conversion plan (docs/plans/onboarding-conversion/plan.md)
    "apple_prompt_shown":     frozenset({"trigger_moment", "trigger"}),
    "apple_prompt_accepted":  frozenset({"trigger_moment", "trigger"}),
    "apple_prompt_declined":  frozenset({"trigger_moment", "trigger"}),
    "apple_prompt_dismissed": frozenset({"trigger_moment", "trigger"}),
    "quickset_prompt_shown":    frozenset({"screen", "position", "show_count"}),
    "quickset_prompt_accepted": frozenset({"screen", "position", "via"}),
    "quickset_prompt_snoozed":  frozenset({"screen", "position", "retired"}),
    "trade_card_shared":     frozenset({"trade_id", "channel"}),
    "coach_mark_shown":      frozenset({"mark_key", "mark"}),
    "coach_mark_dismissed":  frozenset({"mark_key", "mark"}),
    "celebration_shown":     frozenset({"beat_key", "beat"}),
    "deck_exhausted_viewed": frozenset({"lane", "cards_seen", "deck_size"}),
    # Guided avatar tour — `step` is the script id (s0.1 … s8.1), `via` is the
    # advance mechanism (tap | cta | action | auto | timeout).
    "guide_step_shown":      frozenset({"step", "pose", "screen"}),
    "guide_step_advanced":   frozenset({"step", "via"}),
    "guide_step_skipped":    frozenset({"step"}),
    "guide_tour_dismissed":  frozenset({"at_step"}),
    "guide_tour_completed":  frozenset({"steps_seen"}),
}


def _assert_namespaces_disjoint(client: frozenset[str],
                                server: frozenset[str]) -> None:
    """Raise if any client event name collides with a server-authoritative
    name. Called at import time; also called directly by tests with synthetic
    collisions."""
    collisions = client & server
    if collisions:
        raise ValueError(
            "analytics_taxonomy: client event name(s) collide with "
            f"server-authoritative names: {sorted(collisions)!r} — rename "
            "the client event (server-fired rows are event_id=NULL and must "
            "never be client-forgeable)."
        )


# Server-authoritative = the explicit taxonomy plus everything the denorm /
# streak maps in database.py know about (belt and braces — those maps are
# where new server event wiring lands first).
_SERVER_AUTHORITATIVE: frozenset[str] = (
    SERVER_FIRED_EVENTS
    | frozenset(_EVENT_TO_USER_COL)
    | frozenset(_RANK_STREAK_EVENTS)
)

_assert_namespaces_disjoint(ALLOWED_CLIENT_EVENTS, _SERVER_AUTHORITATIVE)

# Every allowlisted client event must carry a prop registry entry (possibly
# empty) — a missing entry would silently strip every prop of a newly
# allowlisted event. Enforced at import so the two registries can't drift.
_missing_props = ALLOWED_CLIENT_EVENTS - frozenset(CLIENT_EVENT_PROPS)
if _missing_props:
    raise ValueError(
        "analytics_taxonomy: allowlisted client event(s) missing a "
        f"CLIENT_EVENT_PROPS entry: {sorted(_missing_props)!r}"
    )
