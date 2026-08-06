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
    "account.data_export",         # 06-02: GET /api/account/export JSON archive
    "account.sleeper_disconnect",
    "account.settings_v2",
    "profiles.user_toggle",
    "auth.persistent_sessions",
    "league.rookie_board_entry",
    # #14 League power rankings — WEB surface kill-switch only (nav link +
    # league-card rank chips in web/js/app.js). The routes themselves ship
    # unflagged (open-by-design consensus aggregates, docs/api-reference.md)
    # and mobile's silent-fail chip is likewise unflagged.
    "league.power_rankings",
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
    # ── Market-data readiness (PRD #43 Phase-1 data foundation / #26) ────
    # market.trade_capture: capture executed Sleeper league trades (public
    # v1 /league/<id>/transactions/<week>, type=trade + complete) into the
    # sleeper_trades table during session_init's background daemon
    # (backend/sleeper_trades_service.py). Capture ONLY — raw payload
    # retained, no scoring/aggregation/UI. Off ⇒ no fetch, no rows.
    "market.trade_capture",
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
    # ── #169 — League "outlook odds" (playoff/championship-odds pipeline) ──
    # Gates GET /api/league/outlook (backend/outlook/). Off (default) ⇒ the
    # route 404s and nothing else changes. Componentized behind swappable
    # Protocol providers; the projection/points source is config-selected via
    # FTF_OUTLOOK_STRENGTH_SOURCE. Preseason payloads are flagged beta.
    "outlook.odds",
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
    # draft-extensions W2 — the FTF-native mock draft. Gates all four
    # /api/mock-draft routes; effective gating is `draft.room` AND
    # `draft.mock`. Independent of `draft.live_poll` (the mock never polls),
    # `draft.mfl` and `picks.slot_values`.
    # OFF (default) ⇒ every mock route 404s `feature_disabled` before any
    # session work, the `mock_drafts` table is never read or written, and no
    # other route's response changes.
    # NOTE: this flag stays OFF beyond the usual "lands dark" convention. W2's
    # calibration gate FAILED on 2026-08-06 (mock_draft_service.CPU_MODEL_VALIDATED
    # is False; see docs/plans/draft-extensions/mock-calibration-2026-08.md),
    # so the plan's abort criterion cut the CPU-bot mock. With the flag ON the
    # create route answers the typed-empty `{"empty": true, "reason":
    # "cpu_model_unvalidated"}` rather than serving unvalidated bots.
    "draft.mock",
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
