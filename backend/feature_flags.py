"""
feature_flags.py — single source of truth for feature flags.

Every feature shipped in the 2026-04-19 parallel sprint is gated behind a
flag defined here. Defaults are all False so new code ships dark; a
deployer flips a key in config/features.json (or via the FTF_FLAGS env
var) to turn the feature on in production.

Usage
-----
    from .feature_flags import FLAGS, is_enabled

    if FLAGS.swipe_community_compare:
        ...

    if is_enabled("swipe.community_compare"):
        ...

Both work; the attribute form is handy inside routes, the string form is
handy when the flag key comes from request data.

Flag naming
-----------
Dotted group.feature keys inside JSON / API; snake_case_group_feature
inside the Flags dataclass. The `_key_to_attr` helper converts between
them automatically — never hand-maintain a second mapping.

The `GET /api/feature-flags` endpoint serves the dotted map to the
frontend so `window.FTF_FLAGS["swipe.community_compare"]` just works.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Flag declarations
# ---------------------------------------------------------------------------

# Every key here MUST be listed in `DEFAULT_FLAGS` below with a default.
# The agent prompts reference these literal strings; do not rename lightly.
FLAG_KEYS: tuple[str, ...] = (
    # Swipe UX (Agent A1)
    "swipe.community_compare",
    "swipe.qc_compliments",
    "swipe.gesture_audit",
    # Positional tiers (Agent A2)
    "tiers.community_diff",
    "tiers.stability_indicator",
    "tiers.swipe_secondary_actions",
    # Trade UI (Agent A3)
    "trades.queue_2k",
    "trades.new_partners_alerts",
    # FB #156 — Trade-Finding Hub (Variant B launcher hub). When ON the Trades
    # tab home becomes the mode launcher (Guided / Team / Player / Calculator)
    # + Trade DNA panel; OFF keeps today's TradesScreen deck as the home.
    "trades.finder_hub",
    # League social (Agent A4)
    "league.unlock_badges_per_member",
    "league.activity_feed",
    "league.unlock_badges_nav_pill",
    # Invite virality (Agent A5)
    "invite.k_factor_dashboard",
    # Mobile polish (Agent A6)
    "mobile.sticky_cta",
    "mobile.thumb_zone_tables",
    "mobile.rankings_card_view",
    # New surfaces (Agent A7)
    "profiles.public_pages",
    "landing.smart_start_cta",
    "landing.try_before_sync",
    # Player profiles (#17)
    "players.profile_pages",
    # Trade math (Agent A8)
    "trade_math.qb_tax",
    "trade_math.star_tax",
    "trade_math.roster_clogger",
    "trade_math.human_explanations",
    # Trade engine v2 — Tier 1 scorer rebuild (docs/plans/trade-engine-tier1-fixes.md)
    "trade_engine.v2",
    # Trade engine Tier 2 (docs/plans/trade-engine-tier2-models.md)
    "trade.marginal_value",   # 2.1 over-replacement valuation (trade_service.py)
    "trade.outlook_blend",    # 2.2 now/future valuation blend (trade_service.py)
    "trade.likes_you",        # 2.3a likes-you queue (server.py)
    "trade.fuzzy_match",      # 2.3b fuzzy mirror matching (database.py)
    "trade.thompson_deck",    # A5 Thompson-sampled deck ordering (server.py)
    "trade.deck_diversity",   # A6 league-wide deck diversification (server.py)
    # Trade engine Tier 3 (docs/plans/trade-engine-tier3-rebuild.md)
    "trade_engine.v3",        # exact per-pair package construction + sweeteners
    "trade.three_team",       # 3-team cycle generation (no client surface yet)
    # FB-47 finder targeting (docs/plans/trade-finder-targeting.md)
    "trade.finder_targeting", # pinned-receive + counterparty positional fit
    # FB-96 — automatic positional-need fit (feedback #96; kin of FB-47)
    "trade.need_fit",         # boost swaps that cross-fill positional needs
    # Backlog #1 — opponent outlook inference (docs/plans/competitor-top20/01-*)
    "trade.outlook_infer",    # price opponents with their inferred/declared α
    # Backlog #2 — asset preference lists (docs/plans/competitor-top20/02-*)
    "trade.preference_lists", # untouchables (give-side filter) + targets (reward)
    # Backlog #8 — seed unset-league outlook from the user's own roster (01's classifier)
    "trade.outlook_seed",
    # Backlog #10 — crown-asset package premium (docs/plans/competitor-top20/10-*)
    "trade.crown_asset",
    # Trade-logic interview phase 2 (docs/plans/trade-logic-interview-2026-07-17.md)
    "trade.lanes",           # stamp cards window_move/value_move from the user's window
    "trade.fit_premium",     # surface flagged need-fill cards that pay a small raw-value premium
    "trade.aggression_ab",   # A/B opening-offer aggression buckets (light/fair/generous)
    # "Send in Sleeper" — undocumented Sleeper write API (FLAGGED-BETA / ToS-adverse)
    "trade.send_in_sleeper",  # docs/plans/sleeper-write-capture-runbook.md
    # "Send in MFL" — MFL's DOCUMENTED import API (import?TYPE=tradeProposal),
    # the sanctioned-API inverse of the Sleeper path. Gates POST
    # /api/trades/propose-mfl + the MFL branch of /api/trades/validate + the
    # mobile send button on MFL leagues. Default OFF until the operator runs
    # the live-verification checklist (import response shape, wwwNN host,
    # pick-asset encodings) — see
    # docs/feedback/items/177-mfl-auth-link/send-in-mfl-scope.md.
    "trade.send_in_mfl",      # backend/mfl_write.py
    # "Send in ESPN" — ESPN's undocumented lm-api-writes transactions
    # endpoint, live-verified for football 2026-08-11
    # (docs/plans/espn-send-live-capture-2026-08-11.md). Gates POST
    # /api/trades/propose-espn + the mobile send button on ESPN leagues.
    # D-026: OFF and deliberately ABSENT from config/features.json until the
    # auth probe clears (it is NOT proven that espn_s2 + SWID alone authorize
    # a server-side POST — a CSRF/session token may be required).
    "espn.send",              # backend/espn_write.py
    # FB-147 — import Sleeper trade-block flags (public GraphQL read) and tag
    # involved players on trade cards. Gates BOTH the session_init sync and
    # the `on_block` card serialization; off = payloads byte-identical to
    # pre-147. backend/trade_block_service.py
    "sleeper.trade_block",
    # FB-147 engine hook — SOFT, acquire-side trade-block boost. A card whose
    # ACQUIRE side holds a player the counterparty flagged "on the block" gets
    # a bounded composite bump (knob block_boost_weight). Applied AFTER all
    # gates — reorders acceptable trades, never rescues a gated one (mirrors
    # trade.need_fit). Default ON (bounded/kill-switchable); off or knob 0 ⇒
    # composite byte-identical. backend/trade_service.py
    "trade.block_boost",
    # Account-auth P2 — Apple/Google identity anchors (docs/plans/account-auth-plan-2026-07-11.md)
    # Gates the sign-in surface (/api/auth/apple, /api/auth/google,
    # GET /api/account + mobile Sign in with Apple UI). DELETE /api/account
    # is deliberately NOT gated — App Store 5.1.1(v) in-app deletion.
    "auth.accounts",
    # Account-auth P1/P3 — write-gate enforcement (plan §3-P1/P3).
    # False (default) = GRACE: unverified writes allowed but logged
    # (AUTH-GRACE lines; see docs/runbook.md). True = P3: unverified writes
    # → 403 verification_required. Hard-verified routes (POST
    # /api/sleeper/link, POST /api/trades/propose) ignore this flag and
    # always require proof.
    "auth.enforce_verified_writes",
    # Email capture (docs/business/product/2026-07-17-email-capture-spec.md).
    # False (default) = pre-spec behavior: Apple email is hashed, plaintext
    # discarded. Flip ONLY in the same release as the capture UI + the
    # privacy-policy update — the policy currently says "no email addresses".
    "auth.email_capture",
    # ESPN league linking Phase 1 — read-only import of ESPN leagues via the
    # unofficial v3 API (docs/plans/espn-league-linking-plan-2026-07-11.md).
    # Gates /api/espn/* routes + the mobile link affordance. Also the kill
    # switch if ESPN blocks reads or Apple objects (plan §4/§6).
    "espn.link",
    # ESPN league linking Phase 1b — in-app WebView cookie capture. Gates the
    # mobile "Sign in to ESPN" primary path in EspnLinkSheet (captures
    # espn_s2 + SWID from the native cookie store; manual paste stays as the
    # fallback). No backend routes: POST /api/espn/link already accepts the
    # cookies. Requires `espn.link` on to have any effect. Default OFF until a
    # TestFlight build with the native cookie dependency validates against a
    # real private league (docs/plans/espn-connect-webview/scope.md).
    "espn.webview_capture",
    # ESPN league linking — "my leagues" picker (2026-08-09, field feedback:
    # "can't we fetch all their ESPN leagues and let them pick, instead of
    # asking for a league ID?"). Gates GET /api/espn/my-leagues (fetches the
    # session user's STORED ESPN cookies' fan profile, fan.api.espn.com,
    # UNVERIFIED response shape — see espn_service.fetch_fan_leagues) AND the
    # mobile league-SELECTION list in EspnLinkSheet that replaces the
    # league-id text input once cookies are available. Manual league-id
    # entry (public leagues need no login at all) stays the fallback path
    # either way. Requires `espn.link` on to have any effect (same as
    # `espn.webview_capture`). OFF ⇒ /api/espn/my-leagues 404s
    # `feature_disabled` and the sheet's input step is byte-identical to
    # today (text field only).
    "espn.league_picker",
    # Multi-platform league linking Phase 1 — read-only import of MFL /
    # Fleaflicker leagues via their official public APIs
    # (docs/plans/multi-platform-linking-plan-2026-07-17.md). Each gates its
    # own /api/{platform}/* routes + the mobile link option; both default OFF
    # and are the kill switch if the vendor changes or Apple objects.
    "mfl.link",           # MFL: public zero-auth import; futureDraftPicks stored (not engine-wired)
    # #177 — MFL authenticated linking: POST /api/mfl/auth-link (MFL login →
    # myleagues) + /api/mfl/auth-import (import ALL leagues at once, private
    # leagues included, franchise auto-detected). Password used transiently,
    # never stored; only the MFL session cookie is kept (Fernet-encrypted via
    # SLEEPER_TOKEN_KEY, session-only when the key is absent). Default OFF.
    "mfl.auth_link",
    "fleaflicker.link",   # Fleaflicker: public zero-auth import via sportradar_id crosswalk
    # ── Onboarding & conversion redesign (docs/plans/onboarding-conversion/plan.md v2.1) ──
    # Semantics: each onboarding.* feature is live iff `onboarding.v2` (the
    # master kill-switch) AND its own flag are both true. Clients enforce the
    # AND via the shared helper (mobile: state/flags onboardingEnabled();
    # backend: onboarding_enabled() in server.py). All ship dark; enable
    # individually once the item is QA'd. `analytics.client_events` is
    # deliberately OUTSIDE the master — it gates instrumentation (tracking
    # plan v2 §S2), which must run against the CURRENT flow to capture the
    # pre-redesign baseline.
    "analytics.client_events",     # CLIENT emission gate only: SDKs track/flush while
                                   # true (P1 split — server acceptance moved to
                                   # analytics.ingest; analytics-platform LLD §2.1)
    "analytics.ingest",            # SERVER acceptance gate for POST /api/events.
                                   # Off → 200 {"disposition":"disabled"}; P1+ clients
                                   # retain their queue and back off (LLD §2.1/§4.6)
    "experiments.engine",          # P3 experiment evaluator master gate. Off →
                                   # resolve_for_unit/variant_for/stamp_for_event
                                   # return empty/None, so the product runs exactly
                                   # as if no experiment existed (analytics-platform LLD §4.3)
    "onboarding.v2",               # master kill-switch for every onboarding.* below
    "onboarding.landing",          # item 5 — username-first landing (also first consumer of landing.try_before_sync)
    "onboarding.trades_first",     # item 4 — trades-first hook screen (pregen at auth-return, skeleton deck, chrome collapse, provenance chip, identity strip)
    "onboarding.league_autoskip",  # item 6 — single-league LeaguePicker auto-skip + fallback
    "onboarding.quickset_prompt",  # item 7 — inline prompt card + onboarding-mode QuickSet (return to Trades, regen, diff banner)
    "onboarding.apple_save_moment",# item 8 — save-moment Apple prompt, decline policy, silent re-init, session-2 banner
    "onboarding.share_sheet",      # item 8 rider — native share sheet on liked card (user-initiated only)
    "onboarding.rank_routing",     # item 9 — chooser demotion, Rank tab → QuickSet default, deck-exhausted → trio entry
    "onboarding.demo_bridge",      # item 10 — demo→real bar + redraft label/segment tag
    "onboarding.guided_layer",     # v2.1 — swipe hint, coach marks (≤4), celebration beats
    "onboarding.guided_avatar",    # The Analyst guided tour (guided-avatar-script.md) — supersedes guided_layer surfaces when on
    "onboarding.keep_warm",        # item 3 — server-side keep-warm affordances (cron ping target)
    # Guided Onboarding v2 (docs/plans/guided-onboarding-v2/scope.md §2) —
    # gates every v2 addition to The Analyst tour: the declarative
    # eligibility layer, arbiter membership, the new beats, and the copy
    # riding the new script fields. Under the `onboarding.v2` master like
    # its siblings. FALSE = byte-identical to pre-build behavior, so it is
    # the config-only rollback lever. NOT `guided_layer` (v2.1 coach marks,
    # still dark) and NOT `guided_avatar` (the v1 tour, already true).
    "onboarding.guide_v2",
    # ── Monetization platform (docs/plans/monetization/00-platform-foundation.md §1) ──
    # One flag per monetization strategy; everything ships dark. Rollout
    # order per foundation §1: monetize.entitlements ON in observe mode
    # first (logs ENTITLE-OBSERVE, never blocks — enforcement starts only
    # when the flag is on AND a paywall exists), then founder+paywall,
    # then pro/season_pass at launch, growth.* after, ads last.
    # Admin manual-grant routes are deliberately NOT flag-gated (operator
    # surface, X-Cron-Secret guarded); grants written while flags are off
    # sit dormant until enforcement flips.
    "monetize.entitlements",       # master switch: entitlement checks enforce (off = all users implicitly pro)
    "monetize.paywall",            # purchase UI surfaces (mobile + web)
    "monetize.pro",                # Pro subscription SKUs + gate list (docs/plans/monetization/pro-subscription/)
    "monetize.season_pass",        # year-labeled season SKUs (docs/plans/monetization/season-pass/)
    "monetize.founder",            # Founder Lifetime offer window (docs/plans/monetization/founder-lifetime/)
    "monetize.affiliate",          # affiliate placements + partner registry (docs/plans/monetization/affiliate/)
    "monetize.ads_web",            # web display ads (docs/plans/monetization/ads/)
    "monetize.ads_mobile",         # mobile AdMob banner+rewarded + ATT prompt
    "growth.referral",             # give-get referral program (invite CTAs + reward granting)
    "growth.group_unlock",         # league group-unlock experiment
    # ── Rankings marketplace (docs/business/product/2026-07-17-rankings-marketplace-plan.md) ──
    "ranks.accuracy_scoring",      # passive snapshot + scoring cron + leaderboard (phase 1)
    "ranks.rank_sets",             # publish/adopt rank sets, free only (phase 2)
    "ranks.set_types_extended",    # redraft/bestball set types (platform-thesis test)
    # ── #232 follow-on — paste-first rankings import (2026-08-02) ──
    # Gates POST /api/rankings/import-match + /import-apply and the mobile
    # "Have rankings already?" chooser entry. Ships ON in features.json —
    # this key is a kill switch, not a dark launch.
    "ranks.import",                # paste-a-table rankings import v1
    # ── Premium rankings import v1 (2026-08-15, [D-058]) ──────────────
    # docs/plans/connected-rankings/build-v1-premium-import/scope.md §2.
    # One key per premium source row in the import half sheet; BOTH DARK.
    # Off = the row is absent and that source's CSV preset never runs;
    # paste + generic CSV upload are deliberately NOT gated by these.
    # Order-only in both states — a premium CSV's Value/Trend/PPG columns
    # are never read or stored (addendum §3.2 R14).
    "ranks.source.dynasty_nerds",  # Dynasty Nerds premium CSV preset + sheet row
    "ranks.source.dlf",            # DLF preset — also gated on a real fixture (§3.4)
    "marketplace.publisher_sets",  # publisher IAP + subscriber linking (phase 3)
    "marketplace.contributor_sales", # contributor credit-priced sales (phase 4)
    "marketplace.cash_payouts",    # Stripe Connect cash-out rung (phase 5)
    # ── 2026-07-19 app-teardown remediation (branch teardown-remediation) ──
    # PRDs live in gitignored app-teardown-review/. All default OFF; the
    # matching keys are pre-registered (dark) in config/features.json.
    # Unflagged-by-design exceptions: league-prefs authz fix (security),
    # first_match/new_match dedup, AASA route (inert without the mobile
    # entitlement), Apple token revocation on deletion.
    "ux.sheet_guard",
    "ux.rank_tab_destination",
    "ux.retap_active_tab",
    "ux.deeplink_router_v2",
    "ux.player_context_menu",
    "ux.swipe_undo",
    "ux.toast_v2",
    "ux.prompt_arbiter",
    "ux.empty_state_ctas",
    "ux.help_surface",
    "ux.board_search",
    "ux.touch_polish",
    "ux.whats_new",
    "ux.outlook_inline_default",
    "a11y.text_scaling",
    "a11y.reduce_motion",
    "visual.chalkline_cleanup",
    "notif.tz_sync",               # 05-01: adopt device X-User-TZ into notification_prefs.tz
    "notif.tap_routing_v2",
    "notif.denial_recovery",
    "notif.reengagement_default_off",  # 05-04a: reengagement bucket defaults 0 w/o stored pref
    "notif.honest_winbacks",       # 05-04b: winback_dormant truthful copy + lifetime stop
    "growth.share_landing",
    "growth.rating_prompt",
    # ── Tier-board sharing — OFF, and meant to stay off ─────────────────
    # P1 audit remediation, operator decision D-P1-12
    # (docs/plans/audit-p1-remediation/DECISIONS-p1.md): "sharing of
    # rankings must not be live in any form." Sharing a tier board is not
    # a product surface. Gates GET /og/tiers/<pos>/<username>.png and
    # GET /s/tiers/<pos>/<username>; both 404 while dark, matching how the
    # package routes close behind growth.share_landing. Those two routes
    # shipped with NO guard at all — sessionless, no in-app link required,
    # so any username's board was fetchable by guessing the URL. Default
    # False here AND false in config/features.json: two independent OFFs.
    # Do not flip without an explicit operator reversal of D-P1-12.
    "growth.tier_board_share",
    # P0-3 (2026-08-09 mobile UX audit) — EMITTER ONLY. On: buildInviteUrl
    # emits /app/league/join/<id>?ref=<u>. Off (default): today's
    # /?league=<id>&ref=<u>, byte-identical. Never gates the ?league= reader,
    # the LeagueJoin route, the AASA claim or the 302 — those are additive and
    # must be live BEFORE any new-format link exists. Graduation: AASA
    # validated live + >=24h CDN propagation + a post-deploy install proves a
    # tapped link opens the app (docs/runbook.md § AASA).
    "growth.invite_join_link",
    "account.data_export",       # 06-02: GET /api/account/export JSON archive
    "account.sleeper_disconnect",
    "account.settings_v2",
    # Settings hub IA — a top-level Settings hub page plus second-level
    # pages (Leagues, Ranking, Trade values, Notifications, Account & data,
    # Help & about), replacing the single flat modal list. Default OFF.
    # Graduation: one operator TestFlight pass. Rollback is PARTIAL — the
    # sheet->page flip is on the route, outside this flag (D-089).
    "account.settings_hub",
    "profiles.user_toggle",
    "auth.persistent_sessions",
    "league.rookie_board_entry",
    # #14 League power rankings — WEB surface kill-switch only (nav link +
    # league-card rank chips in web/js/app.js). The routes themselves ship
    # unflagged (open-by-design consensus aggregates, docs/api-reference.md)
    # and mobile's silent-fail chip is likewise unflagged.
    "league.power_rankings",
    # #293/#294 — mobile LeagueRankings chart counts a team's draft-pick value
    # in EVERY subset (All/Starters/Bench) and under every position filter.
    # Kill switch for a reversal of shipped behavior; OFF (default) = the
    # pre-#293 rule where picks count only in All with no filter. Client-only:
    # no backend behavior rides this key.
    "league.picks_always_counted",
    # #300 — League rankings positional trade candidates
    # (docs/feedback/items/300-league-rankings-trade-candidates/).
    # league.pos_candidates: the median divider on the League rankings list
    # when EXACTLY ONE core position is selected — the labelled cutline plus
    # the Buyer/Seller band emphasis and the stacked-roster drill-in. OFF
    # (default) = the list renders exactly as it does today. Client-only
    # today: the route's `medians` field is additive and ships UNFLAGGED
    # (see the note in league_power_rankings_route) so the client never has
    # to reason about a flag-on/field-absent state.
    "league.pos_candidates",
    # league.player_trade_handoff: the drill-in's row actions ("Offer" on
    # your own players, "Target" on theirs) that pin the asset and route to
    # the trade finder, replacing existing pins. OFF (default) = rows carry
    # no action. Separate key from pos_candidates so the divider can ship
    # without the write-side handoff.
    "league.player_trade_handoff",
    # ── QA / testing surfaces ──
    # Kin of FTF_TEST_MODE, but runtime-flagged (not env-gated) so the
    # operator's phone can exercise a prod-shaped build. Every consumer must
    # ALSO require the tester allowlist (experiments.load_tester_allowlist)
    # so the flag being on never exposes the surface to real users.
    "testing.stage_users",   # POST/DELETE /api/test-users — synthetic stage-user
                             # spawner for onboarding QA (backend/test_users.py)
    # ── #158/#170/#171 — owned draft picks in calculator + suggestions ──
    # picks.owned_sync: revive sync_draft_picks on the league-sync path
    # (session_init daemon for Sleeper; link/import for MFL) + normalize MFL
    # picks + enrich GET /api/league/picks with pool_value/label + the
    # In-league calculator's owned-pick rows. Off ⇒ no owned-pick rows written
    # or shown (byte-identical today).
    "picks.owned_sync",
    # #207 — picks.rank_year_labels: serve the 12 generic pick rungs with a
    # YEAR-EXPLICIT label ("2026 Early 1st" pre-draft, "2027 Early 1st" once
    # the active league's rookie draft is detected as complete) and a
    # years_out-discounted pick_value, on /api/rankings + /api/trio only.
    # Rung ids, pool membership and board Elo are untouched. Off ⇒ today's
    # year-less "Early 1st Round Pick" labels, byte-identical.
    "picks.rank_year_labels",
    # #355 — picks.league_horizon: build a Sleeper league's pristine pick grid
    # over the classes the league REALLY carries (three consecutive rookie
    # classes anchored to the first UNDRAFTED class, per
    # `draft_status.pick_horizon`) instead of a fixed `current_season + 3`.
    # The old constant over-reached by exactly one class for every pre-draft
    # league, so 12.8% of served cards offered a 2029 pick that does not exist
    # — an offer the user cannot execute. Off ⇒ `sync_draft_picks` takes the
    # historical `seasons_ahead` window and the grid is byte-identical to
    # today. WRITE-side only: no read path, route or payload shape changes,
    # and the next replace-sync repairs (or, flag off, restores) the rows
    # either way.
    "picks.league_horizon",
    # D-090 — picks.slot_labels: label an OWNED pick by the slot it actually
    # occupies once its league's CURRENT-season draft order is known, so a
    # card reads "2026 1.08" instead of "2026 1st". Display only: no price,
    # no seed, no tier band and no stored `pool_value` moves in either state
    # (the slot is not a pricing input — see the D-090 note in
    # backend/pick_slots.py and Q-023). Resolution is season-stamped, so a
    # future year keeps its round ordinal, and it fails soft — an unset,
    # unknown or unsupported order yields the generic label. Off ⇒ every
    # owned-pick label is the pre-D-090 string, BYTE-IDENTICAL, at all five
    # sites that build one.
    "picks.slot_labels",
    # ── Market-data readiness (PRD #43 Phase-1 data foundation / #26) ────
    # market.trade_capture: capture executed Sleeper league trades (public
    # v1 /league/<id>/transactions/<week>, type=trade + complete) into the
    # sleeper_trades table during session_init's background daemon
    # (backend/sleeper_trades_service.py). Capture ONLY — raw payload
    # retained, no scoring/aggregation/UI. Off ⇒ no fetch, no rows.
    "market.trade_capture",
    # market.roster_history (ADR-011, #46 Wrapped P0): weekly league-state
    # snapshots into league_roster_history + league_board_history — the
    # ownership-side twin of the value snapshots. Gates the WRITES at every
    # call site (on-sync hooks, the daily-tick sweep, the manual cron
    # route), never the tables' creation, so flipping it mid-season is a
    # behavior change and not a schema surprise. Default ON at merge, like
    # its three sibling capture flags in the same daemon — capture that
    # ships dark is capture that did not happen, and the urgency argument
    # is about days. D-P1-07 does not bar it (that decision is about read
    # routes with external references; this gates a write with none). The
    # env knob FTF_ROSTER_SNAPSHOT_WEEKDAY=7 kills only the sweep half.
    "market.roster_history",
    # market.movers: GET /api/market/movers (#243 "Market pulse" strip) —
    # top risers/fallers by trailing-window % change of FTF community value
    # (player_value_history consensus_value snapshots, the data #57 /
    # market.trade_capture already accumulate). Read-only, no new writes.
    # Off ⇒ the route 404s and the mobile strip renders nothing.
    "market.movers",
    # trade.picks_in_pool: inject each team's owned picks (capped picks_pool_cap)
    # as priced PICK pseudo-assets into the suggestion candidate pool so a card
    # can send/receive a pick (#170/#171). DATA inclusion only — scoring
    # unchanged. Off ⇒ no pick ever appears in a suggestion.
    "trade.picks_in_pool",
    # ── #172/#189 follow-up — asset-centric trade ideas ──────────────────
    # POST /api/trades/asset-ideas: when the user pins exactly ONE asset in
    # the finder targeting flow, return Upgrade / Lateral / Downgrade idea
    # groups swept from every league-mate's roster + owned picks (consensus
    # basis, TradeService.generate_asset_ideas). Off ⇒ the route 404s and
    # the mobile grouped-ideas panel never renders. Default ON in
    # config/features.json (operator ask); this flag is the kill switch.
    "trade.asset_ideas",
    # ── Feedback #175 — directional outlook weighting ────────────────────
    # When the user's resolved outlook is rebuild-side (rebuilder/jets),
    # cards acquiring win-now/older production are strongly penalized and
    # cards acquiring future capital (younger players, picks) are boosted;
    # an unrescued older-primary return past ~1 year is near-excluded.
    # Contend-side gets only the mild mirror. Off ⇒ composites byte-identical.
    "trade.outlook_direction",
    # ── #191 — cross-format board derivation (read-time auto-sync) ───────
    # When a member has rankings in one scoring format and none in the
    # other, reads that need the missing format (trade/evaluate Mode B —
    # the in-league calculator) derive it on the fly via the #124 value-
    # rank mapping (same math as /api/tiers/copy-from-format). Read-time
    # only — nothing is materialized, explicit rankings always win, and
    # responses mark derived boards (opponent_board_derived etc.). Off ⇒
    # unranked-in-this-format members degrade to consensus as before.
    "rankings.cross_format_derive",
    # ── TikTok-discovery deck engine (docs/plans/tiktok-discovery/) ────────
    # All pre-registered dark in config/features.json (2026-07-26); flipped
    # ON per-wave at each TestFlight ship. Only deck.signal_v2 (F1) has code
    # behind it so far — the rest are reserved for waves F2–F8 (without a
    # FLAG_KEYS entry the JSON loader would ignore/typo-warn on them and
    # test_entitlements' features-json-keys-known guard fails).
    #
    # F1 — signal foundation (prds/F1-signal-foundation.md). When ON, each
    # completed trade-generation job writes one deck_impressions row per card
    # (frozen features + Thompson propensity + served position), the generate
    # /status card payloads carry `impression_id`, and the decision/event
    # routes append deck_outcomes rows keyed by it. OFF (default) ⇒ zero new
    # rows, byte-identical payloads, old-client behavior everywhere.
    "deck.signal_v2",
    "deck.thompson_v2",     # F2 — v2 deck sampler: pessimistic priors, decay, viewed-gated counts, lane×shape arms
    "deck.fatigue",         # F3 — per-user fatigue multipliers, 30d decline suppression + retest, deck refresh/undo
    "deck.session_rerank",  # F4 — reserved (no consumer yet)
    "deck.taste_vectors",   # F5 — taste vectors: per-user decayed attr prefs (short/long τ) + board prior, bounded re-rank
    "deck.exploration",     # F7 — wildcard slot (1/deck ≥8, positions 4–6, honest label) + archetype audition pools + exploration propensity logging
    "deck.value_model",     # F6 — learned P(like)/P(propose) heads × V-vector base ordering + nightly refit; DARK until an F8 replay win
    "deck.first_session",   # F9 — first-session win: confidence-weighted first-5 + size clamp on FIRST decks, board-refreshed deck header, adaptation moment
    "deck.replenishment",   # reserved (no consumer yet)
    # ── Matchmaking research item 1 — suggestion telemetry / counterfactual
    # logging (docs/plans/matchmaking-engine/telemetry-scope.md). When ON
    # (and deck.signal_v2 ON — the F1 spine carries the rows): telemetry-era
    # deck_impressions additionally stamp policy_version / candidate_set_id
    # + size (joined to deck_candidate_sets) / assets_json; ~1-in-N organic
    # deck cards (model_config ghost_holdout_one_in, default 10) are
    # deterministically WITHHELD from display per league×ISO-week and logged
    # with is_ghost=1 (never rendered — ghost-ads incrementality); executed
    # Sleeper trades get matched to logged suggestions after each
    # market.trade_capture sync (suggestion_trade_links.was_recommended) and
    # GET /api/admin/suggestion-telemetry/ratio serves the per-league
    # endorsement ratio. OFF (default) ⇒ no withholding, no new columns
    # stamped, no candidate-set/link writes, ratio route 404s —
    # byte-identical serving.
    "suggestion.telemetry",
    # ── #169 — League "outlook odds" (playoff/championship-odds pipeline) ──
    # Gates GET /api/league/outlook (backend/outlook/). Off (default) ⇒ the
    # route 404s and nothing else changes. Componentized behind swappable
    # Protocol providers; the projection/points source is config-selected via
    # FTF_OUTLOOK_STRENGTH_SOURCE. Preseason payloads are flagged beta.
    "outlook.odds",
    # #357 — with-trade playoff-odds delta on evaluate + deck cards.
    # Independent of `outlook.odds`: that one gates the STANDALONE League
    # Summary surface, this one gates the per-trade DELTA. Either may be on
    # without the other, and each is its own kill switch.
    "outlook.trade_impact",
    # #357/#358/#359 — the six-beat Team Review flow (client surface in the
    # Trades tab, hence the `trades.*` namespace; `trade.*` is the engine).
    "trades.team_review",
    # #365 — the net first-round-pick term inside `infer_team_outlook`
    # ("number of 1sts owned vs traded away"). NAMED `trade.*` ON PURPOSE:
    # this one lives in the ENGINE's classifier, whose verdict feeds
    # outlook_alpha for trade_gen_v2, the mock draft and the outlook seed.
    # OFF (default) ⇒ the kwarg is accepted and IGNORED, so
    # `infer_team_outlook` is byte-identical for every caller (INV-365) and
    # the Team Review route never even reads the pick ledger. ON ⇒ the term
    # applies ONLY where a ledger is supplied, and today only the Team Review
    # route supplies one — so lighting this moves the WINDOW BEAT and no deck
    # (INV-365b). Knobs: `infer_w_net_firsts` (0.10),
    # `infer_net_firsts_cap` (1.0); either at 0 neutralises the term without
    # changing the payload shape.
    "trade.outlook_net_firsts",
    # #371 — let the simulated PLAYOFF BAND drive the Team Review window
    # instead of the roster heuristic. `trades.*` because it composes in the
    # route and changes no engine value: `infer_team_outlook` still runs, and
    # its verdict still ships as `window.roster_inferred` whichever path wins.
    # Sleeper-only by construction (backend/outlook/league_state.py registers
    # the other platforms as NotImplemented stubs) and REFUSED in preseason,
    # `completed_weeks == 0` being the odds engine's weakest window (D-094).
    # OFF (default) ⇒ `window` carries none of the source/odds keys and the
    # payload is byte-identical.
    "trades.window_from_odds",
    # #372 — the COMPOSITE window model. Third operator report on this
    # surface: age alone is too simple, incorporate starter dynasty value and
    # playoff likelihood, and make age a lighter driver. `trade.*` for the
    # same reason as `trade.outlook_net_firsts`: it re-weights the ENGINE's
    # classifier, whose verdict feeds outlook_alpha.
    # OFF (default) ⇒ the two new kwargs are accepted and IGNORED, so
    # `infer_team_outlook` is byte-identical for every caller (INV-372) and
    # the route builds no starter signal at all. ON ⇒ the re-weighting applies
    # ONLY where an APPLIED starter signal is supplied, and today only the
    # Team Review route supplies one — so lighting this moves the WINDOW BEAT
    # and no deck (INV-372b). It also SUPERSEDES `trades.window_from_odds`'s
    # replacement behaviour when both are on: the playoff band becomes a
    # weighted term inside the score instead of overwriting the verdict, and
    # counting the same signal twice is what that precedence exists to stop.
    # Knobs: `infer_composite_w_*` (vet 0.40 / youth 0.40 / pick 2.00 /
    # starter 0.60 / playoff 0.40); starter and playoff at 0 neutralise the
    # new terms without changing the payload shape.
    "trade.outlook_composite",
    # ── Rookie draft (docs/plans/rookie-draft/) ────────────────────────────
    # M2 — `?scope=rookie` on /api/rankings + /api/trio, and `scope` in the
    # /api/tiers/save body. A POST-Elo VIEW filter over the ONE existing board:
    # scoped Elo == unscoped Elo for every rookie, and a scoped tier save uses
    # the merged-band rule (persist the scoped pids only, at exactly the values
    # a full-band save would give them).
    # OFF (default) ⇒ the `scope` parameter is NEVER READ — not parsed, not
    # validated, not logged — so flag-on and flag-off responses are
    # byte-identical on held-constant data (plan D4).
    "ranks.rookie_subset",
    # M3/M4 — the Draft Room. Gates GET /api/draft/board (read-only,
    # backend/draft_board_service.py) AND the mobile entry point: with the
    # flag ON the League tab's Explore tile becomes "Rookie draft" and
    # pushes the DraftRoom screen; OFF it is today's "Rookie board" tile
    # (league.rookie_board_entry), so no user is ever stranded.
    # OFF (default) ⇒ the route 404s `feature_disabled` before any session
    # or league work, and nothing else in the app changes.
    "draft.room",
    # M4 — client-side live polling of OUR /api/draft/board (never the
    # platform). 15 s interval, and ONLY while the screen is focused, the
    # app is in the foreground, and the board's own `state` is "live";
    # blurred or backgrounded is ZERO requests. Separate from `draft.room`
    # so the room can ship on manual Refresh alone while the throwaway-
    # league live test (plan O7) is still the release gate for polling.
    # OFF (default) ⇒ no recurring fetch anywhere; the manual Refresh
    # control is always present either way.
    "draft.live_poll",
    # M5 — MFL parity on the Draft Room. Gates the MFL BINDING inside
    # GET /api/draft/board only (the renderer already exists and is tested):
    # ON, an MFL league's board is built from TYPE=draftResults, whose
    # pre-populated grid carries a franchise on every unmade pick.
    # OFF (default) ⇒ an MFL league gets the same honest
    # `platform_unsupported` payload M3 shipped, byte-identical, and ZERO
    # MFL reads are attempted — no league-row lookup, no crosswalk load, no
    # export call. Sleeper responses are unaffected either way (D10).
    # Live mode is release-gated separately: a drafting MFL league reports
    # state:"live" honestly, but MFL's mid-draft update latency is
    # UNVERIFIED, so recurring refresh stays behind `draft.live_poll` until
    # the timed probe in docs/plans/rookie-draft/build-m5.md passes.
    "draft.mfl",
    # M6 — per-slot draft-pick market prices on the Draft Room board, read
    # from DynastyProcess's SECOND file (files/values.csv PICK rows) via
    # data_loader.load_pick_slot_values and served in seed-Elo space on
    # `order[]` entries — a DISPLAY axis only. GENERIC_PICK_SEEDS, the tier
    # ladder, the tier bands and the trade engine do NOT read it (engine
    # adoption is the separate M6b repricing wave, plan O2). Non-12-team
    # leagues get a percentile map and the payload carries
    # `slot_value_approx: true` (plan O3).
    # OFF (default) ⇒ the `slot_value` key is OMITTED ENTIRELY from every
    # order entry (never null), no `slot_value_approx` key, and values.csv is
    # never fetched. A fetch failure with the flag ON degrades the same way.
    "picks.slot_values",
    # M6b — DynastyProcess market slot values IN THE TRADE ENGINE (plan
    # operator decision O2, which reverses hld KD-9 / lld §4.7). Gates the
    # per-user `pick_pricing_mode` setting ('tier_ladder' default |
    # 'market_slots'): the /api/settings/pick-pricing route and the mode
    # resolution in trade_service.pick_pricing_mode_for_user.
    # OFF (default) ⇒ pick_pricing_mode_for_user returns 'tier_ladder' for
    # EVERY user without reading the DB, /api/settings/pick-pricing 404s, and
    # every owned pick prices at its stored `draft_picks.pool_value` exactly
    # as today. `GENERIC_PICK_SEEDS`, the tier ladder and the tier bands are
    # byte-unchanged in BOTH modes — this flag reprices owned picks only.
    "trade.slot_pricing",
    # draft-extensions W1 — per-player ACTIONS on the Draft Room's undrafted
    # rows (docs/plans/draft-extensions/plan.md §4, lld §4.1). ON ⇒ a
    # long-press (plus the `accessibilityActions` custom action, the shipped
    # TradeCard vocabulary) on an undrafted row opens the shared
    # PlayerContextMenu with Set my value → an anchor sheet on the SHIPPED
    # POST /api/anchor/save lane, Rank the rookies (the existing bridge, now
    # two-way), and Add to targets; the coverage nudge renders too.
    # HARD CONSTRAINT: the anchor lane ONLY — no surface this flag opens may
    # reach save_tiers_position or the merged-band path (AST + runtime
    # tests in backend/tests/test_draft_extensions_w1.py).
    # OFF (default) ⇒ undrafted rows are the inert Views they are today: no
    # long-press handler, no a11y action, no menu, no sheet, no nudge. The
    # per-player testIDs ship UNFLAGGED (they are inert, and they are what
    # makes the flag testable at all).
    "draft.rank_inline",
    # draft-extensions W2 — the FTF-native mock draft. Gates all four
    # /api/mock-draft routes; effective gating is `draft.room` AND
    # `draft.mock`. Independent of `draft.live_poll` (the mock never polls),
    # `draft.mfl` and `picks.slot_values`.
    # When OFF ⇒ every mock route 404s `feature_disabled` before any session
    # work, the `mock_drafts` table is never read or written, and no other
    # route's response changes.
    # STATUS: **ON since W2e** (`config/features.json`), so this surface is lit
    # in production and changes to the engine ship visible on merge. The
    # earlier note here said the flag "stays OFF" because W2's calibration gate
    # failed on 2026-08-06 — that is no longer the state of the world. W2e
    # replaced the single global reach cap with the operator's round-tiered
    # policy and the operator accepted THAT rule as the definition of "bots
    # draft plausibly", so `mock_draft_service.CPU_MODEL_VALIDATED` is now True
    # (see its comment, and docs/plans/draft-extensions/mock-calibration-2026-08d.md).
    # The typed-empty `{"empty": true, "reason": "cpu_model_unvalidated"}`
    # contract still exists and is what the create route would answer if
    # `CPU_MODEL_VALIDATED` were flipped back to False.
    "draft.mock",
    # draft-extensions W3 M-A/M-B (ADR-010) — ESPN pick assignment. Gates the
    # three assignment routes (GET/PUT /api/league/pick-assignments,
    # POST …/order) AND the ESPN branch of GET /api/draft/board.
    # OFF (default) ⇒ all three routes 404 `feature_disabled` before any
    # session work; `GET /api/draft/board` for an ESPN league returns the
    # byte-identical `platform_unsupported` payload it returns today; the
    # three new `draft_picks` provenance columns stay unwritten; and every
    # existing read site is unchanged because `load_draft_picks` defaults to
    # `source='platform'` (NULL reads as platform, so no backfill runs).
    # This flag does NOT let asserted picks into trade math — that is the
    # separate M-C kill switch, deliberately, so pick math can be turned off
    # without destroying the rows a league typed in.
    "picks.assign",
    # draft-extensions W3 M-C (ADR-010) — TRADE-MATH ACTIVATION for asserted
    # picks. The second, deliberately separate switch: `picks.assign` owns
    # entry/storage/the room, this one owns whether those rows PRICE. Killing
    # it never destroys the 48-192 rows a league typed in.
    # ON  ⇒ all SEVEN read sites read `source='any'` instead of the
    #       platform-only default (S1 /api/league/picks + /api/trade/evaluate,
    #       S2 _power_picks_by_owner + _user_pick_share, S3 _owned_pick_assets
    #       /_inject_owned_picks + the trade job's opponent pick shares,
    #       S4 _roster_eveners) — full engine parity, operator decision 4;
    #       `_owned_picks_available` stops excluding ESPN leagues that have
    #       assignments; `picks_supported` becomes a data test; and every
    #       priced pick payload carries `source: "platform" | "user"`.
    # OFF (default) ⇒ every one of those sites takes `load_draft_picks`'
    #       platform-only default and every payload is byte-identical, so
    #       asserted rows reach no trade math, no power rankings and no
    #       suggestion. Contested/orphaned slots are withheld from the priced
    #       union by ROW FILTER in either state (never by nulling pool_value —
    #       `_power_picks_by_owner` re-derives a price from a NULL).
    "picks.assign_tradeable",
    # draft-extensions W3 M-D (ADR-010) — LIVE OFFLINE PICK RECORDING. A
    # THIRD, separate flag: `picks.assign` owns ownership entry/storage/the
    # room, `picks.assign_tradeable` owns whether asserted rows PRICE, this
    # one owns whether the app can record WHAT HAPPENED during a real
    # off-platform draft. Storage is the new `recorded_picks` table — never
    # `draft_picks`, never `leagues.draft_status*`.
    # ON  ⇒ POST /api/league/recorded-picks (batch, idempotent on
    #       (league_id, season, overall)) and its /void companion answer,
    #       and GET /api/draft/board's ESPN branch projects live
    #       `recorded_picks` rows into `picks[]` (subtracting them from
    #       `undrafted[]`) through the SAME renderer every other platform
    #       uses.
    # OFF (default) ⇒ both routes 404 `feature_disabled` before any session
    #       work, `recorded_picks` stays unwritten, and the ESPN board reads
    #       zero rows from it regardless of what (if anything) the table
    #       holds — so the board payload is byte-identical to the M-B/M-C
    #       shape (`picks: []`, no drafted subtraction).
    "draft.manual_picks",
    # THE SEASONAL ON/OFF SWITCH FOR THE DRAFT TAB (operator decision,
    # 2026-08-06: "it should literally just be set to seasonal — a flag we
    # turn on and off to display the tab"). Client-only: no route reads it.
    # ON  ⇒ mobile's bottom bar carries the Draft tab (third: Rank · Acquire
    #        · Draft · Matches · League), landing on the ACTIVE league's
    #        Draft Room.
    # OFF ⇒ four tabs. `DraftRoom` stays reachable through the root stack
    #        (the League tile, the Acquire mode strip's Draft chip) and the
    #        canonical deep link `app/league/draft-room` either way.
    # This REPLACES the per-league qualification predicate the tab shipped
    # with (`draft_status == 'not_drafted' && confidence == 'high'` over an
    # AsyncStorage snapshot). That predicate hid the tab from operators whose
    # leagues genuinely qualified, because the snapshot only converged on the
    # NEXT launch. The Draft Room renders every state honestly (drafted ⇒
    # recap, not-drafted ⇒ upcoming, ESPN ⇒ unsupported, no league ⇒ its
    # no-league state), so an always-on tab always lands somewhere truthful.
    # The operator flips this by hand each year — it is not computed.
    "draft.tab",
    # #257 — consolidate TradesHome's Controls Card (outlook row, trade-
    # fairness slider, lane pills, target-players block) into TradeDnaSheet
    # expanded to a full-height sheet (variant C: the three real questions —
    # outlook, positions, specific players — at full weight, fairness + lane
    # demoted to a dim "Fine tuning" strip below a hairline). Client-only: no
    # route reads it. ON ⇒ TradesScreen drops the Controls Card, the legacy
    # OutlookSheet entry point, and TradeDnaSheet's half-sheet DNA-only body
    # in favor of the full sheet reached from OutlookBiasReceipt (the sole
    # entry point); player mode keeps its on-screen TRADE AWAY/TRADE FOR
    # board (the sheet does not absorb it). OFF (default) ⇒ TradesScreen.tsx
    # and TradeDnaSheet.tsx render byte-identical to today.
    "trades.edit_full_sheet",
    # #172 - trade intent modes. A single-select "Consolidate / Tier up /
    # Tier down" chip row in the #257 full sheet lets the user declare the
    # SHAPE of trade they want; the backend applies it as a post-generation
    # filter in trade_service.generate_trades (see the #172 comment block
    # above TradeService). Gates BOTH the chip UI (full sheet only - the
    # flag-off legacy card never gets chips) and the server-side filter.
    # OFF => trade_intent is never read, so responses (and the mobile UI)
    # are byte-identical to today.
    "trades.intent_modes",
    # #269 — specific-team targeting + a league picker MOVE INTO the #257
    # full sheet (both live "with the primary questions", above the demoted
    # "Fine tuning" strip); the mode-bar's Team and Player chips are removed
    # (Player's on-screen board and Team's route-param scoping machinery
    # both stay in the tree — only the chips that reach them go away).
    # Client-only: no route reads it. ON => TradeFinderModeBar renders
    # Guided/Calc/Free agents (+ Draft) only, and the full sheet gains a
    # League row + a single-select "Trade with" team block that feeds the
    # SAME `opponent_user_id` the legacy Team mode already sent to
    # /api/trades/generate. OFF => TradesScreen.tsx, TradeDnaSheet.tsx and
    # TradeFinderModeBar.tsx render byte-identical to today.
    "trades.sheet_targeting",
    # #169 — position-impact fold-in (operator decision, A1a + two
    # modifications; docs/feedback/items/169-position-impact/status.md).
    # POST /api/trade/evaluate Mode B's `starter_impact.slots[].before/after`
    # entries gain additive `tier` (RankingService.tier_for_elo over the RAW
    # seed Elo — the SAME call #277's `_evener_tier` closure already makes)
    # and `rank` (1-based positional rank within the universal pool, via
    # trends_service.compute_consensus_pos_ranks). Mobile's LineupImpactTable
    # (InLeagueCalculator.tsx) uses both on a changed slot to swap the raw
    # value-delta chip for a tier chip on the incoming player AND a matching
    # chip on the outgoing player (TierBadge's `posRank` slot carries the
    # rank movement, e.g. "4th · TE21" -> "1 1st · TE4"). OFF (default) =>
    # `tier_of` is never bound, so `slots` carries no new keys and the
    # table renders the legacy numeric delta chip, byte-identical to today.
    "trade.position_impact",
    # ── #287 — player-offers surface becomes an editable calculator ──────
    # Client-only; no route reads it. Single-pin find-a-trade's featured
    # window (FeaturedTradeWindow, mounted from TradesScreen when exactly
    # one asset is pinned) currently renders the pinned idea as a READ-ONLY
    # TradeCard — the operator's complaint: routing from a found trade to
    # "other options for that player" lands on a tile you can't edit. ON =
    # the window renders the idea as an editable InLeagueCalculator instead
    # (the TradeBuildCanvas prefill technique: initialOpponentId/
    # initialGiveIds/initialReceiveIds, remounted per idea via its
    # assetIdeaKey) so add/remove/eveners/lineup-impact all work in place;
    # the Upgrade/Lateral/Downgrade alternates list (AssetIdeasPanel) stays
    # a pickable rail beneath it. OFF (default) = FeaturedTradeWindow.tsx
    # renders byte-identical to today.
    "trades.player_offers_calc",
    # ── API observability (operator-directed, 2026-08-09) ────────────────
    # backend/api_observability.py: inbound (/api/* Flask hooks) + outbound
    # (every external egress chokepoint) API event capture into user_events
    # as server-fired `api_call`/`api_request` rows, with error-always +
    # success-sampled volume policy and a 30d retention purge. Ships ON in
    # config/features.json — this key is the kill switch. OFF ⇒ zero event
    # writes, zero overhead beyond the flag check, byte-identical responses
    # (the hooks/wrappers no-op before doing any work).
    "obs.api_events",
    # ── Compressed-board trade generation (field bug, 2026-08-15) ─────────
    # docs/plans/compressed-board-pool/scope.md. Both keys address the same
    # field report: three of four boarded leaguemates in the operator's real
    # league (FFV3) produced ZERO trade cards at any budget while mutually
    # positive trades demonstrably existed.
    #
    # trade.pool_calibration — trade_optimizer's candidate-pool prune ranks
    # assets by the raw divergence `_vo - _uv`. elo_to_value is exponential,
    # so an opponent board that sits uniformly LOWER than the user's (a
    # floor-pinned, barely-started board: those three had median Elo ~1220
    # against the consensus 1347) deflates high-Elo players far more than
    # low-Elo ones, and every tradeable stud sorts to the BOTTOM of the key.
    # ON = the opponent's board is shifted onto the user board's mean before
    # differencing, making the pool ORDER invariant to a board-wide scale
    # offset that carries no preference information. Pool ordering only —
    # surplus/fairness math keeps each side's own raw value space. OFF
    # (default) = the pool is byte-identical to today.
    "trade.pool_calibration",
    # trade.divergence_fallback — a member WITH rankings whose divergence
    # path yields zero cards currently gets no consensus fallback either
    # (the branch is if/else, not fall-through), so they vanish from the
    # deck entirely: ranking a little makes you a WORSE trade partner than
    # never ranking at all. ON = the consensus generator runs for a boarded
    # member when the divergence path returns nothing, so no counterparty is
    # ever silently dropped. Cards stay labeled basis="consensus". OFF
    # (default) = boarded members keep the zero-card cliff.
    "trade.divergence_fallback",
    # trade_gen.v2 — matchmaking-research staged generation pipeline
    # (backend/trade_gen_v2.py): divergence-driven partner+centerpiece
    # selection → bounded return-package search → feasibility /
    # dual-board-ε / consensus-band gates in order → joint-gain ranking →
    # acceptance-prior multiplier → exposure cap+floor shaping → MESO
    # variants + two-sided rationale. Built DARK alongside the v2/v3
    # engine; OFF (default) = the module is never imported and every
    # existing generation path is byte-identical.
    "trade_gen.v2",
    # ── Trade presentment rules — G6, 2026-08-16 feedback wave ───────────
    # (#304 #336 #339 #340 #341; specs + kill-rate bands in
    # docs/feedback/items/304-positional-need-filter/). Backend-only, no
    # client surface. ON ⇒ four construction/eligibility layers on the v1
    # generation path (trade_gen.v2 carries its own gate stack):
    #   R1 #340 — absolute overpay ceiling on raw consensus sums, both
    #     sides, independent of the client fairness toggle;
    #   R2 #341 — per-position signed net cap (|recv−give| per position
    #     over QB/RB/WR/TE; picks uncounted);
    #   R3 #339 — "the pick IS the gap" two-sided band on the heavier side;
    #   R5 #304 — window-scaled need gate on the primary received player,
    #     UNTARGETED discovery decks only (pinned/opponent-scoped/explicit-
    #     acquire jobs bypass, derived server-side — R-5b);
    # plus R4 #336 — windowless awaiting-like/pending-accepted-match
    # exclusion at dedup + the likes-you injector (likes-you stays exempt
    # from R1/R2/R3/R5 per Q21 — the D-055 user-gain floor is its quality
    # gate). Per-job per-rule kill counters + the `presentment-tripwire`
    # WARNING ship with the flag. Each rule dies live via its model_config
    # knob (max_overpay_*, pos_net_cap, pick_gap_*, need_gate_*); the flag
    # is the group revert and R4's only switch. OFF ⇒ every generation
    # path is byte-identical to pre-G6 (enforced by test).
    "trade.presentment_rules",
    # ── Decline-reason capture — 2026-08-17, ships ON for ALL users ───────
    # docs/plans/decline-reason-capture/SPEC.md. ON = the trade card's ✕ is
    # replaced by three layer-1 tiles (Value · Fit · Neither); tapping one IS
    # the pass, and POST /api/trades/pass-reason accepts the progressive
    # writes. OFF = that route 404s `feature_disabled` before any session
    # work, no trade_pass_reasons row is ever written, and /api/trades/swipe
    # is untouched (nothing in the shipped ✓/✕ path reads this key), so the
    # disposition row behaves byte-identically.
    #
    # SPEC §5 proposed tester-allowlist scoping; the operator SUPERSEDED that
    # on 2026-08-17 — this ships to everyone. There is deliberately no
    # allowlist half anywhere in the feature: this key is the whole switch,
    # which is what makes it a true one-line kill switch (flip + POST
    # /api/feature-flags/reload, no deploy).
    #
    # The Elo consequence rides a SEPARATE model_config knob
    # (pass_reason_elo_suppression), not this flag, so ranking math can be
    # reverted without taking the capture down with it.
    "feedback.decline_reasons",
    # ── Three-model bake-off — docs/plans/three-model-bakeoff/PLAN.md ─────
    # Scope block: docs/plans/three-model-bakeoff/scope-phase3.md. ON = one
    # organic trade job fans out into THREE generations run sequentially on
    # the existing daemon thread — arm `baseline` (the live engine under the
    # pinned MODEL_A_PROFILE + the arm-A R4 bypass), arm `current` (live
    # defaults), arm `gen_v2` (backend/trade_gen_v2.py called directly,
    # regardless of `trade_gen.v2`, which gates the NORMAL serving path and
    # stays FALSE) — merged by team-draft interleaving, with every served
    # card attributed on deck_impressions.model_arm / .arm_rank and one
    # bakeoff_runs row per job. Also zeroes the trade-swipe K factors
    # (PLAN.md §3.4 Channel 1) so arms cannot teach the shared board between
    # decks; ranking votes (elo_k) stay live.
    #
    # Serving is knob-controlled INSIDE the flag: model_config
    # bakeoff_serve_interleaved 0 (default) = Phase-4 dark validation — all
    # three arms generate and log, only arm `current` is served, the
    # presentation stack runs untouched; 1 = Phase-5 interleaved serving,
    # where the post-generation re-rankers (F2/F3/F5/F6/F7/F9 + A6
    # diversity) are BYPASSED for that deck so nothing reorders the
    # interleaver's output (PLAN.md §3.4 Channel 2).
    #
    # OFF (default) ⇒ no fan-out, no interleave, no new columns stamped, no
    # bakeoff_runs row, swipe K factors untouched — byte-identical serving.
    "trade.bakeoff",
    # ── Trade-suggestion presentation v2 (docs/plans/trade-presentation-v2/) ──
    # CLIENT-ONLY. No route reads this key; it is registered here so the
    # features-json-keys-known guard accepts it and so /api/flags serves it
    # to mobile. ON ⇒ the Acquire tab's mode strip gains a leading "Today"
    # chip that opens the additive TodaysTrade / TradeBrowseAll screens (one
    # endorsed hero + a small Featured tier + an uncapped ranked browse
    # list). OFF (default) ⇒ no chip, no entry point, and TradesScreen /
    # TradeFinderModeBar / TradeHomeUtilityRow render byte-identical to
    # today. The existing deck is never modified either way.
    "trades.presentation_v2",
    # ── #366 — position-relative tier bands (docs/feedback/items/366-tier-ladder) ──
    # ON ⇒ trade_service.analyze_roster_strengths bands each player by his rank
    # WITHIN HIS POSITION instead of by three absolute dynasty-value cuts, and
    # mirrors every `bench` count onto a `replacement` key (alias, not a fourth
    # bin — `bench` is retained so pre-#366 clients still parse). The absolute
    # cuts are a disguised OVERALL-search_rank cut, which is why "elite" admits
    # 33 RBs and 7 TEs today; the report asked for that logic to be reviewed.
    #
    # THIS IS NOT A DISPLAY FLAG. `analyze_roster_strengths` also produces
    # `position_needs` / `position_surplus`, consumed by trade_gen_v2 (:930,
    # :980) and trade_service (:3413, :3440, :4096, :4172, :4259) — flipping it
    # ON CHANGES EVERY DECK FOR EVERY USER. Graduation wants a deck-quality
    # read (scripts/deck_eval.py) on real leagues first, not an eyeball.
    #
    # OFF (default) ⇒ `_bin_player`'s three absolute cuts run unchanged and the
    # profile dict is byte-identical to pre-#366 — pinned by
    # backend/tests/test_position_tiers.py, which is the whole reason this is a
    # flag rather than an edit.
    "trade.position_tiers",
    # ── #366 — the RB Handcuff tag ────────────────────────────────────────────
    # ON ⇒ the roster profile gains `handcuff_rb`: how many of the roster's RBs
    # are the RB2 on their NFL depth chart (`depth_chart_position == "RB"` AND
    # `depth_chart_order == 2`). This rides Sleeper's OWN depth chart, already
    # ingested (database.py:970-971, :8769-8770, re-synced every 24h) and
    # already hydrated onto every pooled Player (server.py:1580-1581) — it is
    # NOT the "second-highest-valued RB on the team" approximation that
    # plan-remaining.md §2 proposed and rightly warned against (D-121).
    #
    # Deliberately SEPARATE from `trade.position_tiers`: this key is purely
    # additive and no engine path reads it, so a deck regression must be
    # revertible without also taking down a harmless label.
    #
    # OFF (default) ⇒ the key is ABSENT from the profile (never 0, never null)
    # and no depth_chart_* attribute is read at all.
    "trade.rb_handcuff",
)

DEFAULT_FLAGS: dict[str, bool] = {key: False for key in FLAG_KEYS}


def _key_to_attr(key: str) -> str:
    """Convert a dotted flag key to a Python attribute name.

    >>> _key_to_attr("swipe.community_compare")
    'swipe_community_compare'
    >>> _key_to_attr("trade_math.qb_tax")
    'trade_math_qb_tax'
    """
    return key.replace(".", "_").replace("-", "_")


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config" / "features.json"

_flags_lock = threading.Lock()
_flags_cache: dict[str, bool] | None = None


def _load_from_json(path: Path) -> dict[str, bool]:
    """Load overrides from a JSON file. Returns empty dict on any failure."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except Exception as e:
        print(f"[feature_flags] could not parse {path}: {e}")
        return {}
    if not isinstance(raw, dict):
        return {}
    # Only keep keys we know about — typos shouldn't silently create flags.
    clean: dict[str, bool] = {}
    for k, v in raw.items():
        if k in DEFAULT_FLAGS:
            clean[k] = bool(v)
        else:
            print(f"[feature_flags] ignoring unknown key {k!r} in {path.name}")
    return clean


def _load_from_env() -> dict[str, bool]:
    """Load overrides from the FTF_FLAGS env var — JSON-encoded dict."""
    raw = os.environ.get("FTF_FLAGS", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[feature_flags] could not parse FTF_FLAGS env var: {e}")
        return {}
    if not isinstance(parsed, dict):
        return {}
    clean: dict[str, bool] = {}
    for k, v in parsed.items():
        if k in DEFAULT_FLAGS:
            clean[k] = bool(v)
    return clean


def _compute_flags() -> dict[str, bool]:
    """Merge defaults + json file + env var into the effective flag map.

    Precedence (later wins): defaults → config/features.json → FTF_FLAGS env
    """
    merged = dict(DEFAULT_FLAGS)
    merged.update(_load_from_json(_CONFIG_PATH))
    merged.update(_load_from_env())
    return merged


def flags_dict() -> dict[str, bool]:
    """Return the current effective flag map (dotted keys → bool).

    Cached — call `reload()` to force a re-read after editing the JSON file.
    """
    global _flags_cache
    if _flags_cache is None:
        with _flags_lock:
            if _flags_cache is None:
                _flags_cache = _compute_flags()
    return dict(_flags_cache)


def reload() -> dict[str, bool]:
    """Force re-read of config/env. Useful for runtime config swaps."""
    global _flags_cache
    with _flags_lock:
        _flags_cache = _compute_flags()
    return dict(_flags_cache)


def is_enabled(key: str) -> bool:
    """Return True if `key` is enabled. Unknown keys return False."""
    return bool(flags_dict().get(key, False))


# ---------------------------------------------------------------------------
# Dataclass access — `FLAGS.swipe_community_compare` and friends
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _FlagsSnapshot:
    """Immutable snapshot of the flag map. Built lazily via `FLAGS`."""
    # Populated dynamically below via setattr; declared here for type hints.

    def __getattr__(self, name: str) -> bool:
        # Fall back for flags declared only in DEFAULT_FLAGS — useful so
        # agents don't have to also edit this class when adding new flags.
        # Convert attr → dotted key via reverse of _key_to_attr: any
        # single underscore preserved, the first underscore (at a group
        # boundary) becomes a dot.
        for key in DEFAULT_FLAGS:
            if _key_to_attr(key) == name:
                return is_enabled(key)
        raise AttributeError(f"No such feature flag: {name!r}")


class _FlagsProxy:
    """Live proxy — every attribute access hits the current flag map.

    Avoids the 'snapshot stale after reload()' gotcha that would bite
    agents stashing `FLAGS.whatever` at module-import time.
    """
    def __getattr__(self, name: str) -> bool:
        for key in DEFAULT_FLAGS:
            if _key_to_attr(key) == name:
                return is_enabled(key)
        raise AttributeError(f"No such feature flag: {name!r}")

    def __getitem__(self, key: str) -> bool:
        return is_enabled(key)

    def __repr__(self) -> str:
        enabled = [k for k, v in flags_dict().items() if v]
        return f"<FLAGS enabled={enabled!r}>"


FLAGS = _FlagsProxy()
