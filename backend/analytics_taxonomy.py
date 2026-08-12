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
    # ── P0 remediation batch, 2026-08-11 ────────────────────────────────
    # Plans: docs/plans/audit-p0-remediation/{hld,lld-p0-7,plan-p0-7}.md.
    # Tracking-plan addendum (the precondition this module's docstring
    # demands): docs/business/analytics/2026-08-11-p0-7-addendum.md.
    #
    # REGISTERED BEFORE ANY EMITTER SHIPS. This registry is default-deny
    # behind a 200 (analytics_ingest.py counts + drops), so a name that
    # lands after its track() call is a silent data loss with a
    # success-shaped response. Four instances of exactly that already
    # exist in this tree: the NULL-`platform` incident, `invite_shared`
    # and `deck_regenerated` (both below), and `celebration_fired` (a
    # typo the CLIENT fixes by rename — no alias here).
    #
    # `tab_selected`, `league_view`, `experiment_exposed` and
    # `quickset_abandoned` are ALSO added to
    # analytics_queries.NON_INTENT_EVENTS — INTENT is a deny-list, so
    # without that these impression-class names would step-change DAU/WAU
    # on ship day and break every retention series at that seam.
    #
    # P0-7 — navigation + League surfaces (mobile only; web and the
    # extension fire none of these).
    "tab_selected",
    "league_view", "league_basis_changed", "league_subset_changed",
    "league_team_opened", "league_home_action_tapped",
    # P0-7 — Send in Sleeper. The ATTEMPT and the FAILURE are client-only
    # signals: a tap that never reaches the server, a network/timeout
    # error, and the pre-identity refusals (feature_disabled, no_user,
    # test_mode_propose_disabled) the server cannot attribute to a user.
    # The SUCCESS is server-fired — see SERVER_FIRED_EVENTS below.
    "sleeper_send_attempted", "sleeper_send_failed",
    # P0-3 — the invite loop. `invite_shared` is NOT new: it has been
    # fired by InviteLeaguematesBanner.tsx since it shipped and dropped
    # on the floor every time, which is why "the invite loop converts
    # zero" has never actually been measurable. Registering it is a bug
    # fix, not an addition.
    "invite_shared", "invite_link_opened", "invite_league_pinned",
    "invite_pin_failed",
    # P0-7 §6 F1 — exposure, not assignment. `experiment_exposed` is
    # already in FUNNEL_CRITICAL (below) and in the mobile SDK's mirror
    # (events.ts) but was NEVER in this allowlist, so anything that fired
    # it was dropped: a live instance of this file's own trap.
    # backend/experiments.py uses assignment as an exposure proxy and
    # reports the dilution; every A/B read is diluted until this lands.
    "experiment_exposed",
    # P0-7 §6 F3/F4 — the Quick Set per-rung drop-off curve. quickset_
    # completed is server-fired PER COMPLETED POSITION, so a user who does
    # three rungs of QB and quits is invisible today. quickset_step_
    # advanced stays INTENT (it is real ranking intent); quickset_
    # abandoned is an outcome/impression signal and is NON_INTENT.
    "quickset_step_advanced", "quickset_abandoned",
    # P0-8/9 D-4 (approved fold-in) — the post-Quick-Set deck reveal
    # counter. Fired by TradesScreen.tsx's diff-banner effect since it
    # shipped and dropped every time, so the S5 reveal — the number the
    # trades-first hypothesis turns on — has never been readable in
    # production. Registration only: the emitter already exists.
    "deck_regenerated",
    # League Summary outlook strip (#169 frame E, scope.md §1a; flag
    # `outlook.odds`) — the collapsed-strip expand/collapse toggle. NOT
    # funnel-critical; zero volume until the flag lights (specced now
    # because the operator rejected the analytics waiver 2026-08-11).
    "outlook_strip_toggled",
    # ── Feedback #297 / #299 / #302, 2026-08-11 ──────────────────────────
    # Tracking plan (the addendum this module's docstring demands):
    # docs/feedback/items/297-lineup-impact-single-pin/analytics.md.
    # The operator REJECTED both build agents' analytics waivers.
    #
    # Only TWO names are added, and both are also listed in
    # analytics_queries.NON_INTENT_EVENTS in this same commit — INTENT is
    # derived by SUBTRACTION, so a name added here and nowhere else
    # step-changes DAU/WAU with no error and no log.
    #
    #   lineup_impact_unavailable — #297. The honest-empty "Starting
    #     lineup" row rendered by the in-league calculator when the server
    #     omits `starter_impact`. An IMPRESSION the server cannot see: the
    #     server knows it omitted the field, it does not know the client
    #     reached the both-sides-populated state that renders the row.
    #
    #   league_team_closed — #299/#302. The EXIT half of the League team
    #     drill-in. The ENTER half is `league_team_opened` (P0-7, above) and
    #     is NOT duplicated: this event deliberately does not re-register a
    #     "focused" name. #302's entire claim is that the drill-in now HAS
    #     exits; `via` is the only way to learn which one users find.
    "lineup_impact_unavailable",
    "league_team_closed",
    # ── Feedback #300, 2026-08-12 ───────────────────────────────────────
    # Tracking plan (the addendum this module's docstring demands):
    # docs/feedback/items/300-league-rankings-trade-candidates/analytics.md.
    # The operator flipped `league.pos_candidates` +
    # `league.player_trade_handoff` ON at ship (d207b03) AND waived the
    # simulator gate and the Maestro run, so these two events are the only
    # evidence that will ever exist that the feature works in the wild.
    #
    # Exactly ONE of the two is also listed in
    # analytics_queries.NON_INTENT_EVENTS, in this same commit — INTENT is
    # derived by SUBTRACTION, so a passive name added here and nowhere else
    # step-changes DAU/WAU with no error and no log.
    #
    #   league_pos_candidates_viewed — the EXPOSURE half, and NON_INTENT.
    #     Fires when the user reaches the single-position candidate view
    #     (the exact `candidatePos` memo the divider's own render gate
    #     reads). Without it, a zero on the action below is unreadable:
    #     nobody found the feature vs nobody wanted it. There is no
    #     existing event to hang this on — `league_view` fires ONCE per
    #     mount, before any pill is tapped; `league_subset_changed` fires
    #     on the All/Starters/Bench control only (a position-pill tap
    #     emits nothing today, anywhere); and `league_team_opened` fires
    #     only for users who already acted, which is the population whose
    #     absence is the thing being measured.
    #
    #   league_candidate_pinned — the ACTION half, and INTENT. The Offer /
    #     Target row action: pins give/receive through useFinderTargets and
    #     routes to the trade finder. This is the feature's conversion
    #     moment and the one number worth reading.
    "league_pos_candidates_viewed",
    "league_candidate_pinned",
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
    # P0-7 — the north-star SEND leg. analytics_queries reserved this and
    # its two client siblings in WAT_DARK on 2026-07-17 and nothing ever
    # fired them; the same commit as this one moves all three to WAT_LIVE.
    # FUNNEL_STAGES stage 8 and FEATURE_VERTICALS["send_in_sleeper"]
    # already reference this exact string and light up on their own.
    # SERVER-fired because POST /api/trades/propose is the only place the
    # send is KNOWN to have landed in Sleeper — a client-forgeable success
    # would sit in WAT and funnel stage 8 next to server-authoritative
    # trade_ratified. NOT added to database._EVENT_TO_USER_COL: bumping
    # last_trade_proposed_at would change notification gating, which is
    # out of scope for an instrumentation item (hld.md S-34).
    "sleeper_send_succeeded",
    # trade_sent (2026-08-11, operator-approved taxonomy addition — tracking
    # plan v2 addendum 2026-08-11, rescoped at the MFL merge the same day):
    # a CONFIRMED outbound send into a real NON-SLEEPER platform league.
    # Fired server-side on the success paths of POST /api/trades/propose-mfl
    # and POST /api/trades/propose-espn ONLY — never on validation or
    # hard-block failures (e.g. mfl_asset_unmapped, espn_pick_unsupported,
    # espn_asset_unmapped). Deliberately NOT fired on the Sleeper path:
    # Sleeper's confirmed send is `sleeper_send_succeeded` (P0-7, above),
    # and firing both for one real send would double-count funnel stage 8.
    # Cross-platform send counts = sleeper_send_succeeded ∪ trade_sent.
    # Props (the NULL-`platform` incident is why `platform` is mandatory
    # and non-null):
    #   platform      'mfl' | 'espn' (2026-08-11, Send-in-ESPN) — REQUIRED,
    #                 never null ('sleeper' never appears; future non-Sleeper
    #                 send platforms extend this enum)
    #   give_count    assets offered (players + side-attributed picks)
    #   receive_count assets requested (players + side-attributed picks)
    #   outcome       platform-confirmed status string ('proposed')
    # league_id rides the envelope column, not props. No player ids/PII.
    "trade_sent",
    # trade_responded (2026-08-11, trade-lifecycle follow-up to trade_sent —
    # tracking plan v2 addendum 2026-08-11): a CONFIRMED response to a
    # pending platform trade. Fired server-side on the success path of
    # POST /api/trades/respond-mfl only (no Sleeper respond route exists) —
    # never on validation, auth, or write failures. Props (same discipline
    # as trade_sent; `platform` mandatory and non-null):
    #   platform  'mfl'  — REQUIRED, never null
    #   response  accept | reject | revoke — the action the user requested
    #   outcome   platform-confirmed result ('accepted'|'rejected'|'revoked')
    # league_id rides the envelope column. No trade contents/ids/PII.
    "trade_responded",
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
    # #298 (2026-08-11) — TWO shipped entries widened, no new event name.
    # Called out loudly because this file is claimed by four branches this
    # week: both edits are pure ADDITIONS to an existing frozenset, no key
    # removed, no neighbouring block reformatted.
    #
    # `source` is a BUG FIX, not a feature: TradesScreen.handleFindTrades
    # (:768) has been sending it since #257 and the empty registry above
    # popped it on every row — the live twin of `trade_card_shared`'s
    # `landing`. Values in flight today: prefs_changed_strip,
    # deck_error_retry, absent.
    # `mode` ∈ single_pin | deck is #298's discriminator. Before the fix a
    # pinned surface could not fire this event AT ALL (the CTA was gated
    # out), so a non-zero find_trades_tapped{mode:single_pin} count IS the
    # regression fix's telemetry.
    "find_trades_tapped":   frozenset({"source", "mode"}),
    # `mode` mirrors find_trades_tapped's — the OUTCOME half of the pair. A
    # find_trades_tapped{mode:single_pin} with no following
    # trade_card_viewed{mode:single_pin} is #298 reappearing: a deck
    # generated with nowhere to render and no disposition path. Still fired
    # from TradesScreen.tsx:2380 — #169 moved the Pass/Like CONTROLS into
    # TradeCard.tsx, it did not move this emitter.
    "trade_card_viewed":    frozenset({"trade_id", "card_index", "lane",
                                       "dwell_ms", "ms_since_open",
                                       "cold_start", "mode"}),
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
    # ── P0 remediation batch, 2026-08-11 ────────────────────────────────
    # NOTE `platform` on league_view is the LEAGUE platform (sleeper /
    # espn / mfl / fleaflicker), matching league_selected's precedent
    # above. It is NOT the device platform — that is a user_events COLUMN
    # derived server-side in analytics_ingest.py from the batch body /
    # X-Device headers (the NULL-`platform` incident). No event in this
    # block carries a device-platform prop, and the prop-stripping test in
    # test_events_api.py pins that.
    "tab_selected":            frozenset({"tab", "from_tab", "refocus",
                                          "intercepted"}),
    "league_view":             frozenset({"surface", "state", "platform",
                                          "team_count", "basis", "subset",
                                          "starters_available",
                                          "outlook_shown", "is_tab_root"}),
    "league_basis_changed":    frozenset({"basis", "from", "boards_differ",
                                          "team_focused"}),
    "league_subset_changed":   frozenset({"subset", "from", "source",
                                          "filter_count", "picks_stripped"}),
    # `is_self` is deliberately ABSENT (hld.md S-33): session-user ↔
    # PowerRankedTeam.user_id identity was never proven, and a guessed
    # prop is worse than a missing one. Adding it later is a one-line
    # taxonomy change plus one client line — do that only with the
    # identity proven.
    "league_team_opened":      frozenset({"via", "rank", "basis", "subset",
                                          "filter_count"}),
    "league_home_action_tapped": frozenset({"action"}),
    # `surface` ∈ deck | match | awaiting | calculator — the four
    # SendInSleeperButton mounts (P0-6 SEND_SURFACES; 'awaiting' is the
    # Matches non-match send row, NOT 'suggested').
    "sleeper_send_attempted":  frozenset({"surface", "give_n", "receive_n",
                                          "from_deck", "has_target"}),
    # `error_code` is a CLOSED enum: the 12 server codes of
    # /api/trades/propose plus network | timeout | unknown. 15 values,
    # forever. `kind` is SleeperWriteError.kind, present only on
    # sleeper_rejected / sleeper_write_failed.
    "sleeper_send_failed":     frozenset({"surface", "error_code", "status",
                                          "kind", "give_n", "receive_n",
                                          "from_deck"}),
    # P0-3 invite loop. `league_id` is a Sleeper/platform league id, not a
    # person; no user identifier rides in any of these four. `auth_state`
    # ∈ signed_out | authed_member | authed_non_member | account_only —
    # the fourth value is the HLD S-17 account-only case (lld-p0-3 D-8);
    # values are not constrained by this registry, so it is the addendum
    # that carries the enum.
    "invite_shared":           frozenset({"league_id"}),
    "invite_link_opened":      frozenset({"league_id", "has_ref", "format",
                                          "auth_state"}),
    "invite_league_pinned":    frozenset({"league_id", "source",
                                          "ms_since_open"}),
    "invite_pin_failed":       frozenset({"league_id", "reason"}),
    # `unit` (account|device) is registered but NOT emitted today: the
    # client cannot derive it — GET /api/feature-flags returns the merged
    # experiments/configs maps without the unit_type that
    # experiments.resolve_for_unit knew server-side. Registered now so
    # adding it later is a server change alone, never a taxonomy change.
    # `key` is the flag key whose first consumption triggered the
    # exposure, which is what makes an exposure auditable back to a
    # surface.
    "experiment_exposed":      frozenset({"experiment", "variant", "unit",
                                          "key"}),
    "quickset_step_advanced":  frozenset({"position", "tier_index",
                                          "tier_count", "seeded_accepted",
                                          "picked_n", "via", "ms"}),
    "quickset_abandoned":      frozenset({"position", "tier_index",
                                          "tiers_done", "ms", "reason"}),
    # P0-8/9 D-4 — the two props the shipped TradesScreen emitter already
    # sends: the Quick Set position that forced the regeneration and the
    # count of cards that were not in the pre-Quick-Set deck.
    "deck_regenerated":        frozenset({"position", "new_trades"}),
    # Outlook strip (#169 frame E) — `expanded` is the RESULTING state.
    "outlook_strip_toggled":  frozenset({"league_id", "expanded"}),
    # ── Feedback #297, 2026-08-11 ───────────────────────────────────────
    # `platform` is the LEAGUE platform (sleeper | espn | mfl |
    # fleaflicker | unknown), read from the session's cached league list —
    # the SAME sense league_selected.platform and league_view.platform
    # carry above. It is NOT the device platform: that is a user_events
    # COLUMN derived server-side in analytics_ingest.py (the NULL-
    # `platform` incident), it is never a prop, and it must not become one.
    #
    # 'unknown' is a REAL value, not a placeholder: the calculator can be
    # reached for a league that is not in the session's cached list (deep
    # link, cold start before the switcher hydrates).
    #
    # There is deliberately NO `reason` prop. The client's only honest
    # split of "why is starter_impact absent" would be
    # `platform == 'sleeper'`, i.e. a pure function of the prop above —
    # two encodings of one fact, which is the two-sources-of-truth bug this
    # surface's history (#208/#248/#293) is a catalog of. The finer split
    # (no_slot_template vs roster_missing) is knowable ONLY server-side and
    # is recorded as deliberately-not-instrumented in the tracking plan.
    "lineup_impact_unavailable": frozenset({"platform"}),
    # ── Feedback #299 / #302, 2026-08-11 ────────────────────────────────
    # The EXIT half of the League drill-in. `league_team_opened` (P0-7,
    # above) is the enter half and is reused unchanged — there is no
    # parallel "focused" name.
    #
    # `via` is a CLOSED enum of the five ways focus can end, one per
    # control that calls the screen's single close helper:
    #   header_back   — #302's fixed stack-header "‹ All teams" (tab root)
    #   in_card_link  — the #243 in-card link (legacy root-stack push only;
    #                   mutually exclusive with header_back on screen)
    #   hardware_back — RESERVED, no emitter. #302's Android BackHandler was
    #     built and withdrawn before ship (iOS-only release, unverifiable on
    #     Android); the name is kept so re-enabling is one effect, not a
    #     taxonomy migration. Pinned both ways by check-analytics-297-302.js.
    #   tab_retap     — #302's re-tap of the already-active League tab
    #   refocus       — opened a DIFFERENT team without leaving the panel
    # A `league_team_opened` with no `league_team_closed` before the next
    # screen_left is the sixth case — abandoned by navigating away. It is
    # measured by ABSENCE on purpose: an unmount-cleanup emitter would
    # double-fire on React strict-mode remounts and invent dwell.
    #
    # `dwell_ms` terminates the focus interval the way screen_left
    # terminates screen_viewed. `rank` is the rank AT OPEN (carried in the
    # focus ref), so it joins to league_team_opened.rank even when the user
    # changes basis mid-focus. Bounded small integers; no league id, no
    # member id, no team name.
    "league_team_closed":     frozenset({"via", "dwell_ms", "rank"}),
    # ── Feedback #300, 2026-08-12 ───────────────────────────────────────
    # `position` is a CORE POSITION (QB | RB | WR | TE) — the single
    # position the ranked list is filtered to. It is NOT a device platform
    # and NOT a roster slot; the divider exists only for the four core
    # positions the server publishes a median for.
    #
    # `divider` is the render OUTCOME, three closed values, each read
    # straight off the memo the render itself reads — never re-derived:
    #   shown     — the line drew (`cutAfter` non-null)
    #   no_median — `medians[position]` absent from the payload: an old
    #               server, or the position missing from the object. The
    #               ops signal that the rollout is incomplete, and the
    #               reason this is a three-valued prop rather than a
    #               shown-only impression event.
    #   no_split  — a median arrived but marks no boundary (every team on
    #               one side, or a list too short to split), so the client
    #               deliberately draws nothing.
    "league_pos_candidates_viewed": frozenset({"position", "divider"}),
    # The conversion moment. `verb` ∈ offer | target is the user's action;
    # `side` ∈ above | below is the TAPPED TEAM's side of the median line.
    #
    # THE TWO ARE NOT REDUNDANT, and the reason is the mirror. The primary
    # roster's verb is fixed by the side (above ⇒ target theirs, below ⇒
    # offer yours), but the drill-in also stacks the MIRROR roster, whose
    # rows carry the OPPOSITE verb. So all four combinations occur, and
    # `mirror = (verb == 'target') == (side == 'below')` — i.e. the user
    # acted against the direction the line chose for them. That rate is
    # the direct test of the feature's central bet and it is unreadable
    # from either prop alone.
    #
    # `rank` is the tapped team's 1-based ON-SCREEN rank at the moment of
    # the pin (the same `selectedIdx` the drill-in header prints), so it
    # is coherent with `side` even if the user changed basis mid-focus —
    # which is also why it can differ from the `league_team_opened.rank`
    # that preceded it. Bounded small integer; no league id, no member id,
    # no team name, no player id.
    #
    # There is deliberately NO `band` prop (Buyer / Seller). Those labels
    # drive no behaviour by operator ruling, and the band is a pure
    # function of `rank` and `league_view.team_count` on the same mount.
    # See the tracking plan's deliberately-not-instrumented section.
    "league_candidate_pinned": frozenset({"verb", "position", "rank", "side"}),
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
