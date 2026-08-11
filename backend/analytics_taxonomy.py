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
    # TikTok-discovery deck engine (docs/plans/tiktok-discovery/). The F1
    # /api/events outcome scan reads deck_card_viewed / swipe_undone BEFORE
    # taxonomy filtering (server-side deck_outcomes are independent of this
    # allowlist); registering them here additionally lands the analytics
    # rows F8's offline-eval harness reads. deck_reranked is F4 telemetry.
    "deck_card_viewed", "swipe_undone", "deck_reranked",
    # F9 (deck.first_session) — activation instrumentation. Client-fired
    # only on the user's first deck for a league (server-marked
    # `first_deck` job field) while the flag is on: first_session_like =
    # position of the session's FIRST like; first_session_deck_completed =
    # session-one deck completion; first_session_adaptation_shown = the
    # honest mid-deck adaptation moment rendered.
    "first_session_like", "first_session_deck_completed",
    "first_session_adaptation_shown",
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
    # Draft Room per-player actions (draft-extensions W1, lld §2.2 / §4.1;
    # tracking-plan addendum docs/business/analytics/2026-08-06-draft-room-
    # w1-addendum.md). The Draft Room shipped with ZERO track() calls — D0's
    # first deliverable is that the bridge row and the new row actions are
    # measurable at all. NOTE: the anchor WRITE itself stays server-fired
    # (`anchor_answered`, now carrying `via`); these four are the client-side
    # intent/exposure signals the server cannot see.
    "draft_room_row_menu_opened", "draft_room_action_taken",
    "draft_room_coverage_nudge_shown", "draft_room_rank_rookies_tapped",
    # ESPN Connect WebView cookie capture (Phase 1b, flag
    # `espn.webview_capture`; scope docs/plans/espn-connect-webview/scope.md).
    # Client-only intent/exposure signals for the in-app ESPN login →
    # native-cookie-store capture flow. `espn_connect_captured` /
    # `_abandoned` carry `saw_otp` so we can measure how often the Disney SSO
    # one-time-code step gates the flow. The cookies themselves are NEVER an
    # event property — nothing but the two credential strings leaves the
    # WebView, and they go to POST /api/espn/link, not analytics.
    "espn_connect_opened", "espn_connect_otp_step",
    "espn_connect_captured", "espn_connect_abandoned",
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
    # trade_sent (2026-08-11, operator-approved taxonomy addition — tracking
    # plan v2 addendum 2026-08-11): a CONFIRMED outbound send into a real
    # platform league. Fired server-side on the success path of BOTH
    # POST /api/trades/propose (Sleeper) and POST /api/trades/propose-mfl —
    # never on validation or hard-block failures (e.g. mfl_asset_unmapped).
    # Props (spec'd once for both platforms; the NULL-`platform` incident is
    # why `platform` is mandatory and non-null):
    #   platform      'sleeper' | 'mfl'  — REQUIRED, never null
    #   give_count    assets offered (players + side-attributed picks)
    #   receive_count assets requested (players + side-attributed picks)
    #   pick_count    Sleeper only — its draft_picks list is not
    #                 side-attributed, so picks ride this separate count
    #   outcome       platform-confirmed status string ('proposed')
    # league_id rides the envelope column, not props. No player ids/PII.
    "trade_sent",
    # Engagement / misc
    "push_sent", "notif_pref_changed", "league_synced", "wrapped_viewed",
    "feedback_submitted", "asset_pref_added", "asset_pref_removed",
    # API observability (flag obs.api_events, backend/api_observability.py) —
    # server-fired capture of outbound external HTTP calls (api_call) and
    # inbound /api/* requests (api_request). Rows carry user_id="system:api"
    # (never a real user) and are NON_INTENT in analytics_queries so they can
    # never leak into DAU/retention. Property specs: OBS_EVENT_PROPS below —
    # enforced by api_observability._scrub_props (unknown props stripped,
    # credential-shaped keys/values redacted).
    "api_call", "api_request",
    # draft-extensions W3 M-A (ADR-010) — the pick-assignment AUDIT TRAIL.
    # `user_events` IS the audit trail for asserted pick ownership: it is what
    # `database.contested_pick_ids` derives disagreement from, and what
    # docs/runbook.md's recovery procedure reconstructs a league's grid from.
    # It must therefore stay SERVER-FIRED and must NEVER appear in
    # ALLOWED_CLIENT_EVENTS — a client-forgeable audit row is a forgeable
    # audit trail, and the import-time disjointness assert below would raise
    # (taking the app down at boot) if someone added it to both.
    "pick_assignment_changed",
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
    # `bg` (2026-08-05): true when the request spanned a foreground exit, so
    # its wall-clock duration is meaningless (prod showed several routes
    # sharing one 992310ms / 3906711ms value — the device slept mid-request).
    # `ms` is OMITTED entirely on untrustworthy samples, so latency analysis
    # filters on "ms present", and `bg` explains why a sample is missing.
    "api_request_failed": frozenset({"route", "method", "status", "ms",
                                     "timeout", "bg"}),
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
    # TikTok-discovery deck engine (F1 viewed/undo joins + F4 rerank moves)
    "deck_card_viewed":     frozenset({"impression_id", "trade_id", "card_index"}),
    "swipe_undone":         frozenset({"trade_id", "impression_id"}),
    "deck_reranked":        frozenset({"moved", "moves"}),
    # F9 — `position` is the 1-based disposition ordinal within the first
    # session (the swipe at which the first like landed); `variant` is
    # 'rerank' (deck.session_rerank on — the deck literally re-ranks) or
    # 'descriptive' (the honest fallback); `attribute` is the dominant
    # liked attribute key (client-local sessionRerank key space).
    "first_session_like":            frozenset({"position", "trade_id",
                                                "impression_id"}),
    "first_session_deck_completed":  frozenset({"deck_size", "dispositions",
                                                "liked"}),
    "first_session_adaptation_shown": frozenset({"variant", "attribute",
                                                 "likes"}),
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
    # Draft Room W1 — `surface` is the host ('draft_room'); `valued` mirrors
    # the payload's `undrafted[].valued` (false = the row has no consensus
    # value, which is exactly the row the anchor action exists for); `rank`
    # is the row's cross-position undrafted rank, not a list index.
    # `action` ∈ set_value | rank_rookies | add_target. `window` is the
    # coverage nudge's fixed top-N (25). `state` is the board state the
    # bridge row was tapped from; `from` is the host surface.
    "draft_room_row_menu_opened":      frozenset({"surface", "player_id",
                                                  "valued", "rank"}),
    "draft_room_action_taken":         frozenset({"action", "player_id",
                                                  "valued"}),
    "draft_room_coverage_nudge_shown": frozenset({"unvalued_count", "window"}),
    "draft_room_rank_rookies_tapped":  frozenset({"state", "from"}),
    # ESPN Connect WebView (Phase 1b) — `source` is the entry point
    # ('link_sheet'); `saw_otp` records whether the Disney SSO one-time-code
    # step appeared before the outcome. No cookie/credential prop exists or
    # may be added.
    "espn_connect_opened":    frozenset({"source"}),
    "espn_connect_otp_step":  frozenset(),
    "espn_connect_captured":  frozenset({"saw_otp"}),
    "espn_connect_abandoned": frozenset({"saw_otp"}),
}


# ---------------------------------------------------------------------------
# API-observability server event prop specs (api_call / api_request).
# Enforced at write time by api_observability._scrub_props — a prop key not
# listed here is STRIPPED before storage (same default-deny posture as
# CLIENT_EVENT_PROPS; the NULL-`platform` incident is why specs exist).
# Per-service safe-context props follow docs/integrations/ instrumentation
# guidance: booleans/counts/enums only, never credential values.
# ---------------------------------------------------------------------------

OBS_EVENT_PROPS: dict[str, frozenset[str]] = {
    # One outbound HTTP call. `endpoint` is a route-template CLASS (e.g.
    # "league.rosters", "graphql.propose_trade", "export.rosters") — never a
    # raw URL. `error_kind` is the service's closed error enum (EspnError /
    # MflError / FleaflickerError / SleeperWriteError .kind). `sample_n` is
    # present on sampled success rows only (rescale: Σ sample_n + errors).
    "api_call": frozenset({
        "service", "endpoint", "method", "status", "ok", "ms",
        "response_bytes", "error_class", "error_kind", "retry", "fallback",
        "sample_n",
        # per-service safe context (docs/integrations/ §instrumentation)
        "league_id", "season", "host", "auth_mode",       # espn/mfl/sleeper
        "s2_encoded", "swid_braced",                       # espn cookie SHAPE booleans
        "week", "rows", "format",                          # sleeper sweeps / DP row counts
        "input_tokens", "output_tokens", "prompt_class",   # anthropic cost visibility
        "candidate_count",                                 # anthropic prompt size class
        "batch_size", "kind",                              # expo push
    }),
    # One inbound request to our own /api/* surface. `route` is the Flask
    # url_rule PATTERN ("/api/sleeper/rosters/<league_id>") — never the raw
    # path, so no user identifiers ride in the event. `user` is the resolved
    # session user/account id when authenticated (diagnosis only — the row's
    # user_id column stays "system:api"). `error_code` is the JSON `error`
    # field of a 4xx/5xx payload (closed enums like "feature_disabled").
    "api_request": frozenset({
        "route", "method", "status", "ok", "ms", "response_bytes",
        "error_code", "error_class", "user", "sample_n",
    }),
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
