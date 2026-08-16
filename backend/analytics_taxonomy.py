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
    # #321 (2026-08-16): the connect flow's first FAILURE event — fired when
    # the server refuses (or can't judge) a captured pair at store time.
    # `reason` distinguishes wrong_account / bad_credentials / unavailable,
    # so the identity-binding rejection is measurable and the R10
    # migration's re-sign-in wave has a signal.
    "espn_connect_store_rejected",
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
    # ── P1 remediation, commit T1 — 2026-08-11 ──────────────────────────
    # Plans: docs/plans/audit-p1-remediation/{HLD-p1.md §A.2, LLD-p1-1-2.md
    # §10, LLD-p1-5.md §8}. Binding operator decisions: DECISIONS-p1.md.
    #
    # T1 is deliberately a REGISTRATION-ONLY commit and it lands BEFORE any
    # P1 client emitter, because this registry is default-deny behind a 200
    # (analytics_ingest.py counts + drops, no error signal on either side).
    # A name that arrives after its track() call is silent, unrecoverable
    # data loss with a success-shaped response.
    #
    # `share_package_created` and `invite_cta_shown` are ALSO added to
    # analytics_queries.NON_INTENT_EVENTS in this same commit — INTENT is
    # derived by SUBTRACTION, so a name registered here and nowhere else
    # ships as INTENT and step-changes DAU/WAU on the day its emitter goes
    # live. `calc_trade_shared` and `invite_cta_tapped` stay INTENT: both
    # are real user decisions.
    #
    # NOT REGISTERED HERE, ON PURPOSE — three sets of names people will
    # expect to find and must not assume are missing by accident:
    #   * `tier_board_shared` — CANCELLED by D-P1-12 (sharing of rankings /
    #     tier boards is not a product surface). Its routes are now flag-off.
    #   * `email_captured` — CANCELLED by AN-6 (operator skipped the event).
    #   * `sleeper_connect_opened/_failed/_captured/_abandoned` (P1-10) —
    #     DEFERRED, not dropped. Their naming decision AN-1 is still open
    #     with the operator, and this file is default-deny, so guessing a
    #     name here would be worse than waiting. **A T1 AMENDMENT COMMIT IS
    #     REQUIRED** for them before P1-10's client wiring ships. This file
    #     is NOT final.
    #
    # P1-1/2 — the share loop. `calc_trade_shared` is a REPAIR, not a new
    # signal: TradeCalculatorScreen.tsx has fired it since it shipped while
    # the name was absent from this set, so every envelope was dropped
    # behind a 200. There is NO historical series for it, which is also why
    # the P1 build could safely narrow its firing conditions.
    "calc_trade_shared", "share_package_created",
    # P1-5 — the promoted invite CTA. `invite_shared` is NOT re-added: P0-3
    # registered it above and T1 only EXTENDS its prop row (see
    # CLIENT_EVENT_PROPS). Re-adding a name is harmless in a set but the
    # prop-row edit is not, and the two are easy to confuse.
    "invite_cta_shown", "invite_cta_tapped",
    # ── #295/#296/#305 mock-draft family, 2026-08-13 ─────────────────────
    # Registration-ONLY commit, ordered FIRST on branch mock-draft-fix
    # (INV-11): this registry is default-deny behind a 200, so a name that
    # arrives after its track() call is silent data loss. All five are
    # CLIENT-fired (one family, one namespace — no SERVER_FIRED_EVENTS
    # sibling exists or may be added without a rename; the #292 server-side
    # bulk-clear emits nothing). `mock_completed` and `mock_create_refused`
    # are NON_INTENT — their analytics_queries.NON_INTENT_EVENTS rows land
    # in this SAME commit (the DAU-seam rule; see that file's block comment).
    # `platform` on every row is the LEAGUE platform from the session league
    # cache (the InLeagueCalculator convention), never the device platform.
    "mock_started", "mock_pick_made", "mock_completed", "mock_abandoned",
    "mock_create_refused",
    # Notification-inbox growth surface, 2026-08-13 — the bell's first
    # instrumentation of any kind. Tracking plan:
    # docs/plans/notif-inbox-growth/analytics.md.
    #
    # REGISTERED BEFORE ANY EMITTER EXISTS. This commit adds no track()
    # call anywhere; the client wiring lands two commits later. That order
    # is the whole point — a name that arrives after its track() call is
    # dropped behind a 200 and the data is unrecoverable.
    #
    # `notif_inbox_opened` and `notif_empty_state_shown` are ALSO added to
    # NON_INTENT_EVENTS in analytics_queries.py in THIS commit; see the
    # block there. `notif_row_tapped` stays INTENT — it is the one number
    # this whole batch exists to produce.
    "notif_inbox_opened", "notif_row_tapped", "notif_empty_state_shown",
    # ── Dropped-emitter backlog registration, 2026-08-13 ─────────────────
    # Tracking plan (the addendum this module's docstring demands):
    # docs/business/analytics/2026-08-13-dropped-emitter-backlog.md.
    #
    # REGISTRATION ONLY — every name below has a LIVE mobile track() call
    # that has been counted-and-dropped (dropped_unknown_type) behind a 200
    # since it shipped. This is the remainder of the 2026-08-11 sweep that
    # found 33 of 73 emitted names unregistered (G-031); most are teardown
    # S3/S4 instrumentation whose metrics have been dark since ship.
    # NO new emitter ships in this commit; prop rows below mirror what the
    # shipped emitters actually send TODAY.
    #
    # Eight of these are impression / dismissal / exposure class and land
    # in analytics_queries.NON_INTENT_EVENTS in this SAME commit (the
    # DAU-seam rule; see that file). The rest are real user decisions and
    # stay INTENT — which still moves INTENT coverage on ship day, so the
    # seam date is recorded in the addendum.
    #
    # DELIBERATELY ABSENT: `quickset_completed`. The client emitter in
    # QuickSetTiersScreen.tsx collided with the server-fired name (the
    # scoped save fires the authoritative row) — registering it here would
    # trip the import-time disjointness assert below and take the app down
    # at boot. The client emitter is REMOVED in this same commit; its
    # `onboarding` prop (was this walk an onboarding return?) is the one
    # signal that dies with it, recorded as accepted loss in the addendum.
    #
    # Interrupt arbiter + prompt surfaces (teardown S4 PRD-04,
    # flag ux.prompt_arbiter):
    "prompt_shown", "apple_banner_dismissed",
    "push_primer_shown", "push_primer_accepted", "push_primer_dismissed",
    # Help surface (teardown S4 PRD-01, flag ux.help_surface):
    "help_opened", "help_read_more_tapped",
    # Player context menu (teardown S3 PRD-02, flag ux.player_context_menu):
    "player_menu_opened",
    # Undo affordances (teardown S3 PRD-03 toast-undo family):
    "calc_clear_undone", "match_dismiss_undone", "suppression_undo_tapped",
    # Trades deck card actions + pin lifecycle:
    "deck_summary_viewed", "demo_bridge_tapped",
    "trade_asset_removed", "trade_edit_in_calculator_tapped",
    "trade_keep_side_tapped", "trade_pin_cleared",
    "trade_swap_suggest_opened", "untouchable_toggled",
    # Trios entry + session exposure (onboarding 8b retention metric):
    "trio_entry_tapped", "trio_session_started",
    # Settings:
    "notif_denied_settings_shown", "notif_denied_settings_tapped",
    "pick_pricing_mode_changed", "stud_tax_mode_changed",
    # Guided tour re-enable (Settings row; the tour family is above):
    "guide_tour_reenabled",
    # Rating prompt REQUEST (growth.rating_prompt) — the OS decides whether
    # a dialog actually appears; we can only instrument the request:
    "rating_prompt_requested",
    # ── Premium rankings import v1, 2026-08-15 ([D-058]) ─────────────────
    # Scope block (the addendum this module's docstring demands):
    # docs/plans/connected-rankings/build-v1-premium-import/scope.md §1.
    #
    # REGISTERED BEFORE ANY EMITTER SHIPS — this registry is default-deny
    # behind a 200 (analytics_ingest.py counts + drops), so a name that
    # arrives after its track() call is silent, unrecoverable data loss
    # with a success-shaped response. Both names are MOBILE-fired; the
    # backend fires neither (the server never sees the file — presets are
    # parsed client-side and arrive as the `rows` payload of
    # POST /api/rankings/import-match).
    #
    # BOTH are NON-INTENT and both land in
    # analytics_queries.NON_INTENT_EVENTS in this SAME commit — INTENT is
    # derived by SUBTRACTION, so a passive name registered here and
    # nowhere else step-changes DAU/WAU on the day its emitter ships. They
    # describe pipeline mechanics mid-flow; the INTENT event for this
    # funnel is the apply (`rankings_import_applied`, server-fired below).
    #
    #   rankings_preset_detected — a premium CSV's header signature matched
    #     a known source and the user cleared the confirmation step.
    #     `source` ∈ {dynasty_nerds, dlf} (the flag-name enum, mirrored in
    #     docs/cross-client-invariants.md); `via` ∈ {browser, file} (in-app
    #     browser capture vs file picker / "Open in FTF"); `set_confirmed`
    #     is TRUE when the user CHANGED the inferred value system/format —
    #     the addendum's `rankings_preset_confirm_changed` folded into one
    #     event rather than split across two names.
    #
    #   rankings_preset_fallback — a file arrived with no matching
    #     signature, so the generic column-mapping UI took over. `via` only:
    #     with no recognized signature there is no honest `source` to send,
    #     and guessing one would poison the enum.
    #
    # NOT registered: any event carrying a player value. Premium imports are
    # order-only; Value/Trend/PPG columns never enter FTF, analytics least
    # of all.
    "rankings_preset_detected", "rankings_preset_fallback",
    # ── Guided Onboarding v2 addendum, 2026-08-15 ───────────────────────
    # Plan: docs/plans/guided-onboarding-v2/{PRD.md,scope.md} §1;
    # event-state verdicts in DELTA-2026-08-15.md §E.
    #
    # REGISTERED BEFORE ANY EMITTER SHIPS (FR-E8 / G-031 / G-036) — the
    # registry is default-deny behind a 200, so a name that lands after
    # its track() call is silent data loss with a success-shaped response.
    # All five are mobile-only; the guide is not a web/extension surface.
    #
    # `guide_step_suppressed` is the FR-E5 measurement: `requestStep` drops
    # silently today (useGuide.ts:94), so every deferral is invisible.
    # `quickset_started` is the client-observable INTENT half of the
    # QuickSet walk — `quickset_completed` is SERVER-fired (see the
    # DELIBERATELY ABSENT note above) and can never be a client receipt.
    # `outlook_saved` / `finder_target_pinned` / `awaiting_segment_viewed`
    # are the adoption receipts the v2 beats retire against.
    #
    # NOT here, on purpose: `trade_sent` and the MFL/ESPN send-attempt rows
    # (PRD Phase 2, not built), and any client `quickset_completed`.
    #
    # `guide_step_suppressed` and `awaiting_segment_viewed` are
    # suppression / impression class and belong in
    # analytics_queries.NON_INTENT_EVENTS before their emitters ship —
    # INTENT is a deny-list, so taxonomy growth is intent-by-default and
    # admitting them would step-change DAU at the emitter's ship date.
    "guide_step_suppressed",
    "outlook_saved", "finder_target_pinned", "quickset_started",
    "awaiting_segment_viewed",
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
    # rankings_import_applied (REGISTRATION ONLY, 2026-08-15) — fired by
    # POST /api/rankings/import-apply since #232's follow-on shipped
    # (2026-08-02) while absent from this registry, i.e. written to
    # user_events but invisible to every taxonomy-driven read. Server-fired
    # because only the route knows how many submitted rows actually landed
    # on the board (`imported_count` vs `submitted_count`), and it must
    # never be client-forgeable — it is a board WRITE. INTENT by default
    # (deliberately NOT in analytics_queries.NON_INTENT_EVENTS): applying
    # an import is a deliberate ranking action, the peer of ranking_reorder
    # and tier_save. NOTE: registration is retroactive — historical rows
    # already in user_events start counting toward INTENT/DAU from this
    # commit, backwards as well as forwards. Volume is small (the flag
    # gates a rarely-used path) and every applier is already counted that
    # day by the tier_save / ranking_reorder side effects of the same
    # session, so no DAU seam is expected.
    "rankings_import_applied",
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
    # awaiting_trade_dismissed (#318, 2026-08-13 — tracking-plan addendum in
    # docs/feedback/items/311-lineup-values-nonsleeper/): the caller
    # retracted an "Awaiting them" like via POST /api/trades/awaiting/
    # dismiss. SERVER-fired because only the server knows how many like
    # rows the dismiss actually marked (`dismissed_likes`) — the client
    # fires nothing (one event, one source of truth; trade_match precedent).
    # Fired ONLY when dismissed_likes >= 1: an idempotent 0-row repeat is
    # not a fresh intent, so no phantom INTENT rows. INTENT by default —
    # deliberately NOT in analytics_queries.NON_INTENT_EVENTS (a deliberate
    # destructive user action belongs in WAT/DAU).
    # Props: partner_id (deck-invalidation target, trade_match's naming),
    # dismissed_likes (rows newly marked, int >= 1). league_id rides the
    # envelope column, never a prop. No platform prop — source 'api'.
    "awaiting_trade_dismissed",
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
    # +landing +surface (P1 T1, P1-1/2 — LLD-p1-1-2.md §10.3). MODIFIED IN
    # PLACE, never delete-and-re-add: a three-way merge that resolves to the
    # pre-existing row keeps the EVENT working and delivers every row
    # hollowed out, with no error anywhere. Pre-edit contents, verbatim:
    #     frozenset({"trade_id", "channel"})
    # `landing` has been STRIPPED since it shipped — TradesScreen.tsx has
    # sent it and analytics_ingest.py popped it silently on every row, so
    # there is no historical `landing` to reconcile with. It is a boolean:
    # TRUE when the shared artifact carried a rich landing (/s/trade/<id> or
    # /s/p/<id>), FALSE when the link ladder degraded to a bare ?ref= — i.e.
    # the rung-A hit rate as the RECIPIENT experienced it, not as the mint
    # reported it. `channel` and `surface` are both RESERVED: no client has
    # ever sent either. Registered so adding them is a client change alone.
    "trade_card_shared":     frozenset({"trade_id", "channel", "landing",
                                        "surface"}),
    "coach_mark_shown":      frozenset({"mark_key", "mark"}),
    "coach_mark_dismissed":  frozenset({"mark_key", "mark"}),
    "celebration_shown":     frozenset({"beat_key", "beat"}),
    "deck_exhausted_viewed": frozenset({"lane", "cards_seen", "deck_size"}),
    # Guided avatar tour — `step` is the script id (s0.1 … s8.1), `via` is the
    # advance mechanism (tap | cta | action | auto | timeout).
    # `spotlight` (guided-onboarding-v2, FR-E6) ∈ measured | degraded | none —
    # whether the beat's cutout resolved, fell back, or was never deictic.
    # AnalystGuide renders the same line either way today, so without this
    # prop a deictic beat pointing at nothing is indistinguishable from one
    # that landed (s7.1 is the live exhibit).
    "guide_step_shown":      frozenset({"step", "pose", "screen",
                                        "spotlight"}),
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
    # #321 — `reason` ∈ wrong_account | bad_credentials | unavailable
    # (derived from the store response: 403 + reason:"wrong_account" →
    # wrong_account; other 403 espn_bad_credentials → bad_credentials;
    # anything else → unavailable); `source`/`saw_otp` mirror the events
    # above. No cookie/credential prop exists or may be added.
    "espn_connect_store_rejected": frozenset({"reason", "source", "saw_otp"}),
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
    # EXTENDED by P1 T1 (P1-5 — LLD-p1-5.md §8). MODIFIED IN PLACE, for the
    # same reason as trade_card_shared above. Pre-edit contents, verbatim:
    #     frozenset({"league_id"})
    # `surface` ∈ league_home | matches_empty | trades_banner |
    # members_overlay | notif_empty — CLOSED, 5 values. `members_overlay` is
    # present per operator decision PR-9 (D-P1-13), which put the
    # members-overlay invite button in scope; without it that surface's rows
    # land surface-less. `notif_empty` is the bell sheet's empty state
    # (operator decision GD-1, 2026-08-13): the invite ask lives THERE and
    # never as a standing inbox row, gated at the same <50%-penetration rule
    # MatchesScreen already ships. Registered in the same commit that adds
    # the three notif_* names below, and BEFORE the client can emit it —
    # `surface` values are carried by this comment rather than enforced by
    # code (CLIENT_EVENT_PROPS constrains prop KEYS, not values), so an
    # unregistered value is not rejected, it is merely undocumented, which
    # is worse. Mirror: mobile InviteLeaguematesBanner.tsx `InviteSurface`.
    # `not_joined` / `total_mates` are int | null. NULL IS HONEST, 0 IS A
    # LIE: the Trades banner has no join counts and a stale league summary
    # can leave them unknown — never substitute 0.
    # `platform` is the LEAGUE platform (sleeper | espn | mfl | fleaflicker
    # | unknown), the same sense league_selected.platform and
    # league_view.platform carry above. It is NOT the device platform: that
    # is a user_events COLUMN derived server-side in analytics_ingest.py
    # (the NULL-`platform` incident), it is never a prop, and it must not
    # become one.
    "invite_shared":           frozenset({"league_id", "surface",
                                          "not_joined", "total_mates",
                                          "platform"}),
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
    # ── P1 remediation, commit T1 — 2026-08-11 ──────────────────────────
    # P1-1/2, the share loop (LLD-p1-1-2.md §10.2 / §10.5).
    #
    # `mode` ∈ live | demo (the type also admits `league`, which never
    # reaches the calculator's share path). `landing` is the same boolean
    # documented on trade_card_shared above. `surface` ∈ calc_live |
    # calc_in_league | trades_liked — a CLOSED enum, and OMITTED on the
    # calculator's demo lane rather than faked. `tiers` is deliberately NOT
    # a member: D-P1-12 cancelled tier-board sharing outright.
    "calc_trade_shared":     frozenset({"mode", "landing", "surface"}),
    # `outcome` ∈ ok | rate_limited | demo | failed — the rung-A SUCCESS
    # rate, and the only way to tell "nobody shares" from "sharing is
    # broken". Fired on every mint attempt that reached the server, and it
    # is dismissal-INDEPENDENT: unlike calc_trade_shared it does not wait
    # for the share sheet to resolve. That is precisely why it is a SYSTEM
    # OUTCOME and not a user action — see NON_INTENT_EVENTS in
    # analytics_queries.py. `give_n`/`receive_n` are 0–5 (server's
    # _SHARE_PACKAGE_SIDE_MAX). The client-side `skipped` state fires NO
    # event at all and is not an `outcome` value.
    "share_package_created": frozenset({"surface", "give_n", "receive_n",
                                        "outcome"}),
    # P1-5, the promoted invite CTA (LLD-p1-5.md §8). Both rows carry the
    # SAME four props as the extended invite_shared row above minus
    # `league_id`, which stays exclusive to invite_shared — see that row for
    # the closed `surface` enum, the null-not-zero rule on the counts, and
    # the league-vs-device meaning of `platform`.
    #
    # invite_cta_shown is an IMPRESSION (the card rendered; the user has not
    # chosen anything) and is NON_INTENT. invite_cta_tapped is a real
    # decision and stays INTENT.
    #
    # Known measurement caveat, recorded so the number is not over-read
    # later (D-P1-04 / HLD §H OG-12): on the Matches empty state the block
    # sits inside a region with no scroll container, so
    # invite_cta_shown{surface: matches_empty} is a MOUNT COUNTER, not a
    # true impression, until that clipping is fixed. The league_home surface
    # is unaffected and its rate is sound.
    "invite_cta_shown":      frozenset({"surface", "not_joined",
                                        "total_mates", "platform"}),
    "invite_cta_tapped":     frozenset({"surface", "not_joined",
                                        "total_mates", "platform"}),
    # ── #295/#296/#305 mock-draft family, 2026-08-13 ─────────────────────
    # `platform` (REQUIRED on all five, never null) is the LEAGUE platform
    # (sleeper | espn | mfl | fleaflicker | unknown) from the session league
    # cache — the InLeagueCalculator convention verbatim, NOT the device
    # platform (that is a user_events COLUMN; the NULL-`platform` incident).
    # `mode` ∈ cpu | manual = settings_echo.mode, the only mode truth.
    # `mock_started` props read off the server's resolved settings_echo,
    # never the setup sheet's request values. `mock_pick_made.for_own_team`
    # = the just-picked slot's roster_id vs settings_echo.user_owner_id
    # (always true in cpu mode). `mock_completed.user_picks` counts
    # my_picks.length — the user's TEAM's picks, never a `by == "user"`
    # count (in manual mode every pick is by:"user").
    # `mock_create_refused.reason` is the typed-empty reason verbatim
    # (open string).
    "mock_started":        frozenset({"platform", "teams", "rounds", "type",
                                      "order_source", "mode"}),
    "mock_pick_made":      frozenset({"platform", "mode", "round", "pick_no",
                                      "for_own_team"}),
    "mock_completed":      frozenset({"platform", "mode", "rounds", "teams",
                                      "user_picks"}),
    "mock_abandoned":      frozenset({"platform", "mode", "picks_made"}),
    "mock_create_refused": frozenset({"platform", "reason"}),
    # ── Bell inbox, 2026-08-13 ────────────────────────────────────────────
    # Tracking plan: docs/plans/notif-inbox-growth/analytics.md. MOBILE
    # ONLY — web/js/app.js has no analytics SDK (no track(), no /api/events
    # caller), so none of these three is a product-wide rate. Said here
    # because the number is easier to over-read than to re-derive.
    #
    # notif_inbox_opened — `unread_count` is read BEFORE markAllRead()
    #   runs (after, it is always 0). `row_count` is the PRE-HYDRATION row
    #   count: the server fetch is async and lands later, so this is "rows
    #   the user saw immediately", never "rows the server holds". Firing
    #   after the network settles would lose every offline open, which is
    #   why it is measured this way.
    "notif_inbox_opened":    frozenset({"unread_count", "row_count"}),
    # notif_row_tapped — fired BEFORE resolveNotificationTarget, so a tap
    #   on an unroutable kind is still recorded. That is deliberate: a row
    #   tapped that goes nowhere is exactly the referral_joined bug this
    #   batch fixes, and this event is the only way to catch the next one.
    #   `type` is the row's data.type verbatim ('' when absent).
    "notif_row_tapped":      frozenset({"type", "position", "age_hours"}),
    # notif_empty_state_shown — `not_joined`/`total_mates` are int | null,
    #   under the SAME rule as the invite rows above: NULL IS HONEST, 0 IS
    #   A LIE. The bell is global — it opens with no active league and
    #   before /api/league/summary lands, and neither case is "everyone
    #   joined". `invite_offered` is whether the penetration gate opened.
    "notif_empty_state_shown": frozenset({"not_joined", "total_mates",
                                          "invite_offered"}),
    # ── Dropped-emitter backlog registration, 2026-08-13 ─────────────────
    # Every row mirrors what the SHIPPED emitter sends today — no reserved
    # keys, no reconciliation renames (the addendum records call sites).
    # `surface` on prompt_shown is the InterruptSurface enum
    # (quickset_prompt | coach_mark | apple_banner | outlook_banner —
    # mobile useInterruptCoordinator.ts, the values are carried there).
    "prompt_shown":            frozenset({"surface"}),
    "apple_banner_dismissed":  frozenset(),
    # push_primer_shown.trigger ∈ session | want_it (usePushPriming.ts);
    # push_primer_dismissed.declines is the post-increment decline count.
    "push_primer_shown":       frozenset({"trigger"}),
    "push_primer_accepted":    frozenset(),
    "push_primer_dismissed":   frozenset({"declines"}),
    # `topic` is the HelpSheet topic key (matching | trade_pricing today).
    "help_opened":             frozenset({"topic"}),
    "help_read_more_tapped":   frozenset({"topic"}),
    # `surface` ∈ matches | matches_awaiting | trades | trios (the trios
    # mount omits `side`); `side` ∈ give | receive where present.
    "player_menu_opened":      frozenset({"surface", "side"}),
    "calc_clear_undone":       frozenset(),
    "match_dismiss_undone":    frozenset({"match_id"}),
    "suppression_undo_tapped": frozenset(),
    # sessionTally spread + deck length at summary render.
    "deck_summary_viewed":     frozenset({"passed", "liked", "proposed",
                                          "deck_size"}),
    "demo_bridge_tapped":      frozenset(),
    "trade_asset_removed":     frozenset({"side"}),
    "trade_edit_in_calculator_tapped": frozenset(),
    "trade_keep_side_tapped":  frozenset({"side"}),
    # `restored` — whether clearing the pin restored a pre-pin deck snapshot.
    "trade_pin_cleared":       frozenset({"restored"}),
    "trade_swap_suggest_opened": frozenset({"side"}),
    # `marked` is the RESULTING untouchable state (post-toggle).
    "untouchable_toggled":     frozenset({"marked"}),
    "trio_entry_tapped":       frozenset({"from"}),
    "trio_session_started":    frozenset(),
    "notif_denied_settings_shown":  frozenset(),
    "notif_denied_settings_tapped": frozenset(),
    "pick_pricing_mode_changed":    frozenset({"mode"}),
    "stud_tax_mode_changed":        frozenset({"mode"}),
    "guide_tour_reenabled":         frozenset(),
    # `version` is the app version the request fired under (StoreReview
    # once-per-version backoff key).
    "rating_prompt_requested":      frozenset({"trigger", "version"}),
    # Premium rankings import v1 ([D-058]) — see the block in
    # ALLOWED_CLIENT_EVENTS. Closed enums only; no filename, no column
    # names, no player values.
    "rankings_preset_detected":     frozenset({"source", "via",
                                               "set_confirmed"}),
    "rankings_preset_fallback":     frozenset({"via"}),
    # ── Guided Onboarding v2 addendum, 2026-08-15 ───────────────────────
    # `step` is the script id the guide asked for (same vocabulary as
    # guide_step_shown.step); `blocked_by` is the refusal reason — the
    # authoritative low-cardinality union is the client's `GuideBlockedBy`
    # type (mobile/src/state/useGuide.ts): guide_active | slot_busy | seen |
    # display_cap | invalidated | retired | degrade | v1_release_cap |
    # matched. One row per deferral episode, not per retry.
    "guide_step_suppressed":   frozenset({"step", "blocked_by"}),
    # `source` on all three is the entry point that produced the receipt
    # (guide hand-off vs. organic), so adoption can be attributed without
    # a session join: outlook_saved ∈ guide | sheet | strip;
    # awaiting_segment_viewed ∈ guide | tab | push.
    "outlook_saved":           frozenset({"source"}),
    # `side` ∈ give | receive — the targeting board half the pin landed on
    # (the same vocabulary as player_menu_opened.side).
    "finder_target_pinned":    frozenset({"side", "source"}),
    # `position` is a CORE POSITION (QB|RB|WR|TE) — the QuickSet walk being
    # started, NOT a device platform (the NULL-`platform` incident).
    "quickset_started":        frozenset({"position", "source"}),
    "awaiting_segment_viewed": frozenset({"source"}),
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
