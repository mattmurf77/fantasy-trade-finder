# Config Reference

*Jump via the TOC — read sections, not the file.*

Environment variables, feature flags, and `model_config` keys. Keep in sync when adding any of the three (see [docs/CLAUDE.md](CLAUDE.md)).


## Table of Contents

- [Environment variables](#environment-variables)
- [Feature flags](#feature-flags)
- [Flags — 2026-04-19 sprint cohort (swipe, tiers, trades, league social, invite, mobile polish, landing, trade math)](#flags-2026-04-19-sprint-cohort-swipe-tiers-trades-league-social-invite-mobile-polish-landing-trade-math)
- [Flags — Analytics & experiments platform (ADR-007)](#flags-analytics-experiments-platform-adr-007)
- [Flags — League rankings surfaces (#14 / #300)](#flags-league-rankings-surfaces-14-300)
- [Flags — Player profiles (#17)](#flags-player-profiles-17)
- [Flags — Trade engine flags (Tier 1–2, landed — all currently **true** in `config/features.json`)](#flags-trade-engine-flags-tier-12-landed-all-currently-true-in-configfeaturesjson)
- [Flags — Trade engine flags (Tier 3, flag-gated — landing imminently, default **false**)](#flags-trade-engine-flags-tier-3-flag-gated-landing-imminently-default-false)
- [Flags — Owned draft picks in calculator + suggestions (#158/#170/#171 — ship dark)](#flags-owned-draft-picks-in-calculator-suggestions-158170171-ship-dark)
- [Flags — Directional outlook weighting (feedback #175 — ships dark)](#flags-directional-outlook-weighting-feedback-175-ships-dark)
- [Flags — Compressed-board trade generation (2026-08-15 field bug — LIVE)](#flags-compressed-board-trade-generation-2026-08-15-field-bug-live)
- [Flags — Trade generation pipeline v2 (matchmaking research — ships dark)](#flags-trade-generation-pipeline-v2-matchmaking-research-ships-dark)
- [Flags — Trade presentment rules (G6 2026-08-16 — ships ON)](#flags-trade-presentment-rules-g6-2026-08-16-ships-on)
- [Flags — Send in Sleeper (flagged beta)](#flags-send-in-sleeper-flagged-beta)
- [Flags — Account auth (account-auth plan P2 — ships dark)](#flags-account-auth-account-auth-plan-p2-ships-dark)
- [Flags — ESPN league linking (Phase 1 — ships dark)](#flags-espn-league-linking-phase-1-ships-dark)
- [Flags — Multi-platform league linking — MFL / Fleaflicker (Phase 1 — ships dark; [plan](plans/multi-platform-linking-plan-2026-07-17.md))](#flags-multi-platform-league-linking-mfl-fleaflicker-phase-1-ships-dark-plan)
- [Flags — Onboarding & conversion redesign (ships dark; [plan](plans/onboarding-conversion/plan.md) v2.1)](#flags-onboarding-conversion-redesign-ships-dark-plan-v21)
- [Flags — Monetization platform (ships dark; [foundation](plans/monetization/00-platform-foundation.md), [plan index](plans/monetization/README.md))](#flags-monetization-platform-ships-dark-foundation-plan-index)
- [Flags — App-teardown remediation (2026-07, branch `teardown-remediation` — all dark)](#flags-app-teardown-remediation-2026-07-branch-teardown-remediation-all-dark)
- [Flags — TikTok-discovery deck engine (2026-07-26)](#flags-tiktok-discovery-deck-engine-2026-07-26)
- [Flags — Rookie draft + Draft Room (2026-08-06)](#flags-rookie-draft-draft-room-2026-08-06)
- [Flags — Draft-surface extensions (2026-08-06)](#flags-draft-surface-extensions-2026-08-06)
- [Flags — QA / testing surfaces](#flags-qa-testing-surfaces)
- [Flags — Decline-reason capture (2026-08-17, ships **ON**)](#flags-decline-reason-capture-2026-08-17-ships-on)
- [Flags — API observability (2026-08-09, ships **ON**)](#flags-api-observability-2026-08-09-ships-on)
- [Flags — P0 remediation (2026-08-11 mobile UX audit)](#flags-p0-remediation-2026-08-11-mobile-ux-audit-plans)
- [Analytics events — Guided Onboarding v2 addendum (2026-08-15)](#analytics-events-guided-onboarding-v2-addendum-2026-08-15)
- [`model_config` keys](#model_config-keys)
  - [Analytics platform (P0, [ADR-007](adr/adr-007-first-party-analytics-experimentation.md))](#analytics-platform-p0-adr-007)
  - [Trios → tier calibration + variety — `ranking_service._DEFAULT_CFG`, DB-seeded](#trios-tier-calibration-variety-ranking_service_default_cfg-db-seeded)
  - [Decline-reason Elo suppression — `ranking_service._DEFAULT_CFG`](#decline-reason-elo-suppression-ranking_service_default_cfg)
  - [Board-override pins — `ranking_service._DEFAULT_CFG`, DB-seeded](#board-override-pins-ranking_service_default_cfg-db-seeded)
  - [Forced deck regeneration — `backend/server.py`, DB-seeded](#forced-deck-regeneration-backendserverpy-db-seeded)
  - [Consensus seed blend (#145/#148) — `backend/data_loader.py`, DB-seeded](#consensus-seed-blend-145148-backenddata_loaderpy-db-seeded)
  - [Trade engine v2 (Tier 1) — `trade_service._DEFAULT_CFG`](#trade-engine-v2-tier-1-trade_service_default_cfg)
  - [Tier 2 — marginal valuation + outlook blend](#tier-2-marginal-valuation-outlook-blend)
  - [Tier 2 — deck ordering, diversification, fuzzy matching](#tier-2-deck-ordering-diversification-fuzzy-matching)
  - [F3 — fatigue & durable suppression (flag `deck.fatigue`)](#f3-fatigue-durable-suppression-flag-deckfatigue)
  - [F5 — trade-taste vectors (flag `deck.taste_vectors`)](#f5-trade-taste-vectors-flag-decktaste_vectors)
  - [F7 — exploration slots & archetype audition (flag `deck.exploration`)](#f7-exploration-slots-archetype-audition-flag-deckexploration)
  - [F9 — first-session win engineering (flag `deck.first_session`)](#f9-first-session-win-engineering-flag-deckfirst_session)
  - [Suggestion telemetry & ghost holdout (flag `suggestion.telemetry`)](#suggestion-telemetry-ghost-holdout-flag-suggestiontelemetry)
  - [F6 — learned acceptance heads × V-vector (flag `deck.value_model` — **dark**)](#f6-learned-acceptance-heads-v-vector-flag-deckvalue_model-dark)
  - [Tier 3 (flag-gated, landing imminently)](#tier-3-flag-gated-landing-imminently)
  - [Trade generation pipeline v2 (flag `trade_gen.v2` — dark)](#trade-generation-pipeline-v2-flag-trade_genv2-dark-trade_service_default_cfg-consumed-by-backendtrade_gen_v2py)
  - [Trade presentment rules (flag `trade.presentment_rules`) — `trade_service._DEFAULT_CFG`, DB-seeded](#trade-presentment-rules-flag-tradepresentment_rules-trade_service_default_cfg-db-seeded)
  - [Bake-off arm A — `MODEL_A_PROFILE` + the R4 bypass (`backend/bakeoff_profiles.py`)](#bake-off-arm-a--model_a_profile--the-r4-bypass-backendbakeoff_profilespy)
  - [Outlook odds (#169) — `backend/outlook/`](#outlook-odds-169-backendoutlook)
  - [Fit-congruence signal weighting (no flag) — `trade_service._DEFAULT_CFG`, DB-seeded](#fit-congruence-signal-weighting-no-flag-trade_service_default_cfg-db-seeded)
  - [Verdict bands (backlog #6 / #27) — `trade_service._DEFAULT_CFG`](#verdict-bands-backlog-6-27-trade_service_default_cfg)
  - [Mock-draft CPU drafters (draft-extensions W2) — `mock_draft_service._DEFAULT_CFG`](#mock-draft-cpu-drafters-draft-extensions-w2-mock_draft_service_default_cfg)
- [Offline eval harness (F8, `backend/eval/` — operator tooling, unflagged)](#offline-eval-harness-f8-backendeval-operator-tooling-unflagged)

---

## Environment variables

| Var | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | `backend/database.py` | Postgres connection string. Unset → SQLite at `data/trade_finder.db` |
| `ANTHROPIC_API_KEY` | `backend/smart_matchup_generator.py` | Enables Claude-assisted matchup selection; unset → algorithmic fallback |
| `FTF_FLAGS` | `backend/feature_flags.py` | JSON dict of process-level feature-flag overrides (wins over `config/features.json`) |
| `CRON_SECRET` | `backend/server.py` | Shared secret (`X-Cron-Secret` header) for all operator endpoints: `/api/cron/*`, `/api/feedback/admin/*`, `/api/admin/*` (config + engine-metrics), `/api/debug/log`, `/api/feature-flags/reload`. In a non-SQLite (prod) env these **fail closed** (503) when it's unset; in SQLite dev an unset secret disables the check. Compared with `hmac.compare_digest`. |
| `FTF_TESTER_ALLOWLIST` | `backend/experiments.py` | Comma-separated experiment unit ids (account ids and/or `device:<id>` pseudo-ids) that resolve the `is_tester_allowlist` targeting attribute to true. **Unioned with `config/tester_allowlist.json`** (JSON array, git-deployable — required in practice: Render does not apply `render.yaml` envVars to a dashboard-created service). Read on the engine's 60s cache refresh; not `model_config` because its value column is a Float. Powers operator-targeted rollouts (e.g. `onboarding_v2_rollout`, `trades_home_inline`). `aggregate_tier_labels` rode this until its **#306/D-306-1 graduation (operator, 2026-08-16)** — `/api/league/power-rankings` now emits the aggregate labels ungated for every caller and no longer consults the experiment; the experiment record retires via the admin stop→decide lifecycle (docs/feedback/items/279-aggregate-tier-labels/status.md §runbook). |
| `SCORING_FORMAT` | `backend/server.py` | Default scoring format override |
| `FTF_OUTLOOK_STRENGTH_SOURCE` | `backend/outlook/config.py` | **#169** — selects the outlook-odds `StrengthProvider`: `auto` (default; roster-value preseason → `trailing_scores`/`blended` in-season), `roster_value`, `trailing_scores`, `blended`, `sleeper_projections` (stub), `own_model` (stub). String-valued, so it lives here rather than `model_config` (whose value column is a Float). This is the operator's swap seam: change one value to repoint the projection/points source; nothing downstream imports a concrete provider. |
| `SLEEPER_TOKEN_KEY` | `backend/sleeper_write.py` | Fernet key encrypting stored Sleeper write tokens (`trade.send_in_sleeper`). Unset/invalid → the link + propose routes fail closed (503 `sleeper_unconfigured`). Generate with `cryptography.fernet.Fernet.generate_key()`; set in `secrets.local.env` + Render. |
| `FTF_TEST_MODE` | `backend/server.py` + `backend/test_support.py` | `1` → mounts the `/__test__/*` UI-test blueprint and makes `/api/trades/propose` fail closed (599). **Startup-aborts unless `FTF_SLEEPER_FIXTURES_DIR` and `FTF_PLAYERS_CACHE_FILE` are also set.** Never set in prod. See `docs/plans/mobile-testing/` |
| `FTF_SLEEPER_FIXTURES_DIR` | `backend/server.py` `_sleeper_get` | Fixture seam: serve Sleeper responses from canned JSON in this dir (path-keyed, e.g. `user/qa_standard.json`); a miss raises HTTP 599 (fail-closed, never live) |
| `FTF_SLEEPER_RECORD` | `backend/server.py` `_sleeper_get` | `1` → live calls also write scrubbed cassettes into `FTF_SLEEPER_FIXTURES_DIR`. Refuses to start with `FTF_TEST_MODE` (record is deliberately live) or a non-empty fixtures dir |
| `FTF_PLAYERS_CACHE_FILE` | `backend/server.py` | Redirects the players warm-cache path (default `data/.sleeper_players_cache.json`, shared with real dev) so test runs never clobber it |
| `FTF_PLAYERS_REFRESH` | `backend/server.py` `_refresh_players_cache_async` | **Kill switch for the M0 player-cache refresh.** `0` → the daemon never starts (`POST /api/cron/players-refresh` still 202s with `started: false`); anything else (default) → enabled. Exists because M0 is deliberately **not** flag-gated — there is no user-visible surface to gate — so this is the only lever that stops the refresh without a code deploy. Mirrors the KTC kill-switch precedent |
| `FTF_DP_VALUES_FILE` | `backend/data_loader.py` | Test seam: serve the DynastyProcess values CSV from this local path instead of the live GitHub egress (identical parse path). Under `FTF_TEST_MODE=1` it is **mandatory** (the silent flat-Elo fallback would otherwise reshape the pool mid-test) |
| `FTF_DP_PICK_VALUES_FILE` | `backend/data_loader.py` | Test seam: serve DynastyProcess's **combined** `files/values.csv` (read only for its `pos == "PICK"` rows — the M6 draft-pick slot values) from this local path instead of the live GitHub egress. This is a **second** remote DP file, so it has its own override; under `FTF_TEST_MODE=1` it is **mandatory** and the backend startup-aborts without it (T-M6-01) |
| `FTF_ROSTER_SNAPSHOT_WEEKDAY` | `backend/server.py` (`_roster_snapshot_weekday_gate`) | ADR-011: the `daily-tick` weekday `>=` gate for the weekly roster-snapshot sweep (Writer B). Default **1** — Monday's tick is gated, Tuesday onward is eligible, and the `>=` (not `==`) shape means one missed cron run doesn't skip the week (the period's existing `'weekly'` rows cap the work at once). **`7` can never pass** (`weekday()` is 0–6): the deploy-free lever that kills only the sweep while on-sync capture keeps running. The manual route `POST /api/cron/roster-snapshot` ignores this gate by design. |
| `FTF_OBS_RETENTION_DAYS` | `backend/api_observability.py` | Retention window (days) for `api_call`/`api_request` observability rows in `user_events` (flag `obs.api_events`). Default **30**; `0` = keep forever. The purge rides `server._cleanup_loop` (5-min tick, internally throttled to one DELETE per 6 h) and runs regardless of the flag state so old rows age out even while capture is off |
| `FTF_KTC_VALUES_FILE` | `backend/data_loader.py` | Test seam: serve the KeepTradeCut dynasty-rankings **HTML** from this local path instead of the live fetch (#145). When unset under `FTF_TEST_MODE=1` (or when `FTF_DP_VALUES_FILE` is set), KTC is simply **off** — never a live egress from a hermetic run |
| `FTF_TEST_PROFILE` | `backend/test_support.py` | Fixture profile name reported by `GET /__test__/whoami` (set by the seeder's `--print-env`) |
| `FTF_ENV` / `FTF_API_BASE_URL` | `mobile/app.config.js` (build time) | `FTF_ENV=test` nulls the Sentry DSN + sets `extra.testMode`; `FTF_API_BASE_URL` overrides `extra.apiBaseUrl` (test builds → local Flask). Unset → identical to `app.json` |
| `GOOGLE_OAUTH_CLIENT_ID` | `backend/server.py` (`/api/auth/google`) | Google OAuth client id — the expected `aud` of Google ID tokens (`auth.accounts`). Unset → the route fails closed (503 `not_configured`). Apple needs no equivalent (its `aud` is the app bundle id, hardcoded in `backend/accounts.py`). |
| `EXPERIMENT_SALT_KEY` | `backend/database.py` (`_layer_salt`) | Master secret the per-layer experiment bucketing salts derive from (`HMAC(key, layer)`). **Set in Render + `secrets.local.env` before launching any experiment** (analytics-platform P3). Unset (dev/test) → a fixed deterministic salt, which keeps the UI-test seed DB reproducible but is not cryptographically secret. **Rotating it reshuffles every bucket in every layer — treat as launch-blocking-to-change once an experiment is running.** |
| `ANALYTICS_TESTER_DEVICE_IDS` | `backend/analytics_queries.py` (`_tester_device_ids`) | Optional comma-separated device-id allowlist excluded from cohort reports (operator/tester traffic). Empty by default. |
| `REVENUECAT_WEBHOOK_SECRET` | `backend/server.py` (`/api/billing/revenuecat/webhook`) | Bearer token RevenueCat sends in `Authorization` on webhooks. Prod unset → the route fails closed (503); SQLite dev unset → check disabled (same posture as `CRON_SECRET`). Set in `secrets.local.env` + Render when RevenueCat is configured. |
| `STRIPE_WEBHOOK_SECRET` | `backend/server.py` (`/api/billing/stripe/webhook`) | Stripe webhook signing secret (`whsec_…`) for `Stripe-Signature` v1 verification. Same fail-closed posture as above. |
| `APPLE_TEAM_ID` | `backend/server.py` (AASA route; SIWA revocation) | Apple Developer team ID. Overrides the in-repo default (`N5Y4N2Q49A` from `mobile/eas.json`) in the served `/.well-known/apple-app-site-association`; also part of the ES256 client secret for Sign in with Apple token revocation on account deletion. Unset → AASA serves the in-repo default; revocation is skipped with a log line (deletion never blocks). |
| `APPLE_KEY_ID` | `backend/server.py` (SIWA revocation) | Key ID of the Sign in with Apple .p8 private key. Unset → revocation skipped, logged; deletion proceeds. |
| `APPLE_PRIVATE_KEY` | `backend/server.py` (SIWA revocation) | PEM contents of the Sign in with Apple .p8 key (ES256 client secret). Store in `secrets.local.env` / Render env only. Unset → revocation skipped, logged; deletion proceeds. |

---

## Feature flags

Source of truth: `config/features.json`. Every key defaults to **false** in `backend/feature_flags.py` (`FLAG_KEYS` / `DEFAULT_FLAGS`); flipping a value in the JSON (or `FTF_FLAGS`) enables it. Reload at runtime via `POST /api/feature-flags/reload`.

Every flag is documented below. The **`features.json`** column is the value actually shipped — read it, not the registered default: several of the older keys are **true** in production, and a reader who assumes "undocumented ⇒ dark" will be wrong about a live surface.

## Flags — 2026-04-19 sprint cohort (swipe, tiers, trades, league social, invite, mobile polish, landing, trade math)

The keys under the first `_comment` block in `config/features.json` ("Feature flags for the 2026-04-19 sprint"), plus the trade-math batch. Documented 2026-08-18 — they were previously left to be read off `config/features.json` as "self-describing", which hid the four that ship **true**. Registered default for all of them is false (`backend/feature_flags.py` `DEFAULT_FLAGS`).

| Flag | `features.json` | Gates |
|---|---|---|
| `swipe.community_compare` | false | `GET /api/trio` attaches a `community_signal` block (`smart_matchup_generator.community_trio_signal`, gate at `server.py` ~6109) for the "X% agreed with your #1" toast. Consumed by web only (`web/js/app.js` ~1546, toast CSS in `web/css/styles.css`); mobile types the field but renders nothing. Off ⇒ no new keys in the trio response. |
| `swipe.qc_compliments` | **true** | Quality-control trios: `GET /api/trio` periodically substitutes a deliberately lopsided trio (`smart_matchup_generator.find_qc_trio`) and stamps `is_qc_trio` + `qc_expected_order` so the client can reward a consensus-matching ranking. Throttled to one QC trio per `QC_TRIO_INTERVAL` rankings per position via a per-session counter, and **skipped entirely under `scope="rookie"`** (the QC path builds its own pool and would leak non-rookies into a scoped trio). Consumed by `mobile/src/screens/RankScreen.tsx` (Toast "Nice call!") and `web/js/app.js` ~1560. Off ⇒ no new keys, counter never touched. |
| `swipe.gesture_audit` | **true** | Per-player info affordance on the trio screen: mobile long-press → info sheet (`RankScreen.showInfoSheet`; paired with `ux.player_context_menu` for the visible ⓘ twin), web touch-gesture handlers + info button/sheet (`web/js/app.js` ~1789). Client-only — no backend route reads it. |
| `tiers.community_diff` | false | `GET /api/tiers/community-diff` (user tier vs community tier per player). Off ⇒ the route still answers 200 with `{diffs: {}, disabled: true}` rather than 404, and `web/positional-tiers.html` gates its overlay toggle on the same flag. |
| `tiers.stability_indicator` | false | `GET /api/tiers/stability` — 30-day `elo_history` bucketing into `stable` (1 distinct tier) / `volatile` (3+); 2 tiers or <2 snapshots are omitted. Off ⇒ 200 with `{stability: {}, disabled: true}`; the badge in `web/positional-tiers.html` is gated client-side too. |
| `tiers.swipe_secondary_actions` | false | Web-only (`web/positional-tiers.html` ~3127): swipe-left/right secondary actions on tier chips (pool chip swipes into the most-recently-used tier) plus the one-shot swipe hint. No backend consumer. |
| `trades.queue_2k` | false | The 2K-style trade queue — stack trade ideas, then "Send all" opens each on Sleeper in a staggered new tab. Client-only, per-league localStorage (`web/js/app.js` ~3678; `mobile/src/screens/TradesScreen.tsx` ~824, where the store stays functional while the UI hides so hook order is stable across flag flips). No backend route. |
| `trades.new_partners_alerts` | false | "New trade partners" banner. **Two different derivations, no dedicated route:** web diffs the current top-10 `trade_id`s against a per-league localStorage snapshot on a 7-day rotation (`web/js/app.js` ~3893); mobile derives newly-tradeable leaguemates from `unlock` events on the activity feed (`mobile/src/api/league.ts` `getNewPartners`) — so on mobile it is functionally coupled to `league.activity_feed`. |
| `league.unlock_badges_per_member` | false | `GET /api/league/member-unlock-states` (per-member unlocked scoring formats). Off ⇒ `{"members": [], "flag_off": true}` — 200, not 404. |
| `league.activity_feed` | false | `GET /api/league/activity` (league event feed, `limit` clamped 1–100). Off ⇒ `{"events": [], "flag_off": true}`. Also the mobile new-partners derivation above depends on this feed. |
| `league.unlock_badges_nav_pill` | false | Web-only: the unlocked-formats pill (0/2, 1/2, 2/2) on the header League button (`web/js/app.js` ~5309). Off ⇒ pill hidden. No backend consumer. |
| `invite.k_factor_dashboard` | false | `GET /api/invite/impact` (inviter K-factor snapshot) + the invite modal's impact section (`web/js/app.js` ~5393). Off ⇒ the route returns 200 with a **zeroed** payload (`enabled: false`) so the client fails quiet, and the section stays hidden/emptied. |
| `mobile.sticky_cta` | false | **Gates nothing observable today.** `web/js/app.js` `_applyMobilePolishFlags` writes `body[data-ftf-flag-mobile-sticky-cta]`, and `web/index.html` carries the `.mobile-sticky-cta-bar` markup, but **no CSS rule in `web/css/styles.css` selects either the attribute or the class** — flipping it on changes a data attribute and nothing else. Verified 2026-08-18. |
| `mobile.thumb_zone_tables` | false | **Gates nothing observable today.** Same wiring as above (`body[data-ftf-flag-mobile-thumb-zone-tables]`); no CSS rule selects the attribute. Verified 2026-08-18. |
| `mobile.rankings_card_view` | false | **Gates nothing observable today.** Same wiring as above (`body[data-ftf-flag-mobile-rankings-card-view]`); no CSS rule selects the attribute. Verified 2026-08-18. |
| `landing.smart_start_cta` | false | Accept a Sleeper **league URL** as well as a bare username on the landing/sign-in surface: URL input goes through `/api/league/parse-url` to find a roster owner, then drops into the normal username sign-in. Client-only in both clients (`mobile/src/screens/SignInScreen.tsx` ~78; `web/js/app.js` ~1185 + the CTA block in `web/index.html`) — `server.py` ~19688 records it as "frontend only". Distinct from `landing.try_before_sync`, which is the demo-session escape and **does** gate a backend route. |
| `trade_math.qb_tax` | false | `trade_service.qb_tax_adjustment` — a composite multiplier in (0, 1] applied when one side **receives** a premium QB (seed Elo ≥ `_QB_PREMIUM_ELO`) without giving one back, in either direction. Off ⇒ returns 1.0. `model_config`: `qb_tax_rate`. |
| `trade_math.roster_clogger` | false | `trade_service.roster_clogger_adjustment` — penalizes asymmetric-count trades: `roster_spot_penalty` per extra roster spot, plus `roster_clogger_penalty` per player beyond 2 once a side reaches `roster_clogger_threshold`. Off ⇒ returns 1.0. |
| `trade_math.human_explanations` | **true** | Populates the `reasons[]` string list on trade cards (`trade_service.py` ~2176/2269/2328, serialized at ~4946; `server.py` ~10188). Off ⇒ `reasons` is emitted empty. Clients gate their rendering on the same key (`mobile/src/components/TradeCard.tsx` ~184; `web/js/app.js` ~3641), and `mobile/src/shared/types.ts` documents `reasons?` as present only under this flag. |

`trade_math.star_tax` is in this cohort too and is **false** — turned off 2026-07-17 by the trade-logic interview because it double-counted the premium now priced by `trade.crown_asset` (see that row above).

## Flags — Analytics & experiments platform (ADR-007)

| Flag | `features.json` | Gates |
|---|---|---|
| `analytics.ingest` | **true** | **Server acceptance gate for `POST /api/events`** (`backend/analytics_ingest.py` ~320, the first check in `ingest_request`, before the size cap and parse). Off ⇒ 200 `{"disposition": "disabled"}` and clients **retain** their queue and back off, so the backlog flows in on re-enable (analytics-platform LLD §2.1/§4.6) — this is deliberately not an error, and not a drop. Distinct from `analytics.client_events`, which gates client-side *emission*; both must be on for client events to land. Report darkness in `/api/admin/analytics/*` is measured from rows in window (`analytics_queries.is_dark`), never from this flag. |
| `experiments.engine` | **true** | Master gate for the P3 experiment evaluator (`backend/experiments.py`): `resolve_for_unit` (~324), `variant_for` (~349) and the event-stamp path (~392) all return empty/None when off, so the product runs exactly as if no experiment existed (analytics-platform LLD §4.3). The admin CRUD routes under `/api/admin/experiments` are **not** gated by it — an experiment can be authored and transitioned while the evaluator is dark; `web/admin/analytics.html` says so in the empty state. Assignment/targeting inputs are separate concerns: `EXPERIMENT_SALT_KEY` (bucketing) and `FTF_TESTER_ALLOWLIST` / `config/tester_allowlist.json` (targeting). |

## Flags — League rankings surfaces (#14 / #300)

| Flag | `features.json` | Gates |
|---|---|---|
| `league.power_rankings` | false | **Web surface kill switch only** (#14/#21): the "League rankings" nav link in the League Summary header and the league-card rank chips (`web/js/app.js` ~77, `web/index.html`). `GET /api/league/power-rankings` itself ships **unflagged** (open-by-design consensus aggregate — see [api-reference](api-reference.md)), and mobile's silent-fail chip is likewise unflagged. Off ⇒ the web link stays hidden; nothing server-side changes. |
| `league.pos_candidates` | **true** | **#300** — on the mobile League rankings list, when **exactly one** core position is selected: the labelled median divider (playoff-cutline pattern), the Buyer/Seller band labels (band = `round(team_count * 0.33)`; middle unlabelled, but the LINE is the direction rule), pick-tier labels replacing the raw numeric, and the auto-return when the filter changes while drilled in. Multi-position has no single median, so nothing draws. **Client-only** (`mobile/src/screens/LeagueSummaryScreen.tsx` ~599): the route's `medians` field is additive and ships **unflagged**, so a flag-on/field-absent state can't occur. Off ⇒ the list renders as it did pre-#300. |
| `league.player_trade_handoff` | **true** | **#300** drill-in half: which roster the stacked drill-in shows (the direction the median line implies) and the row actions — **Offer** on your own players (pins give), **Target** on theirs (pins receive) — which route to the trade finder and **replace** existing pins. Deliberately a separate key so the divider can ship and be evaluated without the write-side handoff. Meaningless alone (no direction without the line), so every drill-in consumer reads the **AND** of this and `league.pos_candidates`. Client-only. |

Both #300 keys were flipped **ON by operator direction on 2026-08-12, in the same change that shipped them** — they did not bake dark, and the operator waived the pre-ship simulator gate and Maestro execution, so TestFlight was the first runtime exercise of that code. Kill switch: set either key false.

## Flags — Player profiles (#17)

| Flag | Default | Gates |
|---|---|---|
| `players.profile_pages` | false | `GET /api/players/<id>/profile` (404 when off) and web player-name linkification (`playerLink` in `web/js/app.js` → `web/player.html`). The daily `POST /api/cron/value-snapshot` job that feeds the profiles runs **unflagged** — it is data retention and must collect history before the UI ships. |

## Flags — Trade engine flags (Tier 1–2, landed — all currently **true** in `config/features.json`)

| Flag | Tier | Gates |
|---|---|---|
| `trade_engine.v2` | 1 | The entire v2 scorer (`trade_service._generate_trades_v2`): single value space (`elo_to_value`), `package_value_v2`, both-sides surplus gate + harmonic-mean ranking, waiver-slot cost, confidence shrinkage, range-overlap fairness, top-K heap, consensus-basis cards. Off → legacy scorer, byte-for-byte unchanged |
| `trade.marginal_value` | 2 (2.1) | Over-replacement (marginal) valuation inside the v2 pair loop; switches the per-side gate to `min_side_surplus_marginal` |
| `trade.outlook_blend` | 2 (2.2) | Now/future age-curve blend applied to the user's value map (α from `outlook_alpha_*`). Replaces the deleted `team_outlook_multiplier`. v2-only; legacy ignores outlook. **Turned OFF 2026-07-17** (trade-logic interview, "age = tiebreak"): age is already priced into market values, so the engine no longer double-adjusts; window/age return as lane labels + narratives in phase 2 (see [plans/trade-logic-interview-2026-07-17.md](plans/trade-logic-interview-2026-07-17.md)) |
| `trade.likes_you` | 2 (2.3a) | Likes-you queue: inject/boost cards whose mirror a league-mate already liked (`server._inject_likes_you_cards`, cap 3 per deck) |
| `trade.fuzzy_match` | 2 (2.3b) | Jaccard ≥ `fuzzy_match_tau` mirror matching in `database.check_for_match`, guarded so only low-value players (`search_rank ≥ 120`) may differ |
| `trade.thompson_deck` | 2 (A5) | Thompson-sampled deck ordering: one Beta(1+likes, 2+passes) draw per card *shape* (e.g. `2x1`), bounded (0.5, 1.5) multiplier on the ordering key (`server._order_deck`) |
| `trade.deck_diversity` | 2 (A6) | League-wide diversification: penalize cards whose top receive asset saturates other members' recent decks; intra-deck cap `deck_max_per_target` |

## Flags — Trade engine flags (Tier 3, flag-gated — landing imminently, default **false**)

| Flag | Gates |
|---|---|
| `trade_engine.v3` | `backend/trade_optimizer.py` — exact per-pair package search + sweetener pass. Off → falls back to v2 (then legacy if `trade_engine.v2` is also off) |
| `trade.three_team` | 3-team cycle trades (kidney-exchange-style clearing) in `trade_optimizer.py` |
| `trade.finder_targeting` | FB-47 ([plan](plans/trade-finder-targeting.md)): `pinned_receive_players` ("I want to acquire X") + counterparty positional-fit ranking (`partner_fit` on cards, `fit_consensus_weight` / `fit_divergence_weight` composite blend). Default **false**; **enabled in `config/features.json` since 2026-07-10** (Phase C: web picker direction toggle + mobile Target-players controls; both clients gate their targeting UI on this flag and render the `partner_fit` line on cards). |
| `trades.finder_hub` | FB #156 — Trade-Finding Hub (Variant B "Launcher Hub"). When **true** the mobile Trades-tab home becomes `TradeFinderHubScreen` (Trade DNA panel + Guided/Team/Player/Calculator launcher cards); each deck mode opens the `TradeDeck` route (a re-entry of `TradesScreen`) with a lateral quick-switch bar, and Specific Team threads `opponent_user_id` into `/api/trades/generate`. When **false** `TradesScreen` stays the Trades home unchanged. **Flipped true 2026-07-25** (operator-approved, #156 finish batch — two-column player board, #174 package toggle, live pin counts, in-place team switch, #186/#190 card actions). Interaction to QA on-device: the `onboarding.trades_first` experiment arm auto-generates on the deck as the Trades home — the hub displaces that landing for enrolled devices (the operator's allowlisted device runs that arm). No backend behavior is gated by this flag — the additive `position_needs`/`position_surplus` prefs fields and the `opponent_user_id` generate scope are always live and harmless when unused. |
| `trade.need_fit` | FB-96 (feedback #96; kin of FB-47 but needs NO user input): every v2-orchestrated card (divergence, v3, consensus) gets an automatic **positional-need fit** in [0,1] from the two rosters' `analyze_roster_strengths` profiles — high when the card gives from the user's deepest position into the opponent's need AND receives at the user's thinnest position from the opponent's surplus (SF bumps the QB "loaded" bar by one). Composite ×= `1 + need_fit_weight · (need_fit − 0.5)`, applied in `_generate_trades_v2` AFTER all gates — reorders acceptable trades, never rescues gated ones; fairness/mismatch scores untouched. Cards carry `need_fit` (serialized when set). Default **false**; **enabled in `config/features.json` since 2026-07-09**. New `model_config` key: `need_fit_weight` (0.15 since the 2026-07-17 interview — "keep it a light multiplier", max ±7.5% composite swing; was 0.30, old-default DB rows are migrated on boot). |
| `trade.block_boost` | FB-147 engine hook (kin of `need_fit`): a **SOFT, acquire-side** boost. Every v2-orchestrated card (divergence, v3, consensus) whose **acquire side** (`receive_player_ids`) holds ≥1 player the **counterparty** flagged "on the block" (`database.load_trade_block`, grouped by flagging owner via `trade_service._load_on_block_by_uid`) gets composite ×= `1 + block_boost_weight`, applied in `_generate_trades_v2` AFTER all gates — reorders acceptable trades, never rescues gated ones; fairness/mismatch untouched. Give-side / the user's own flagged players are out of scope (operator chose acquire-side only). Flat bump regardless of how many acquired assets are blocked. Cards carry the in-process `block_boosted` flag; client inspectability rides #147's existing per-player `on_block` receive-row flag (no separate serialization). Depends on `sleeper.trade_block` having synced block data (else no-op). Default **true** (bounded/kill-switchable); flag off or knob 0 ⇒ composite byte-identical, nothing stamped. New `model_config` key: `block_boost_weight` (0.15, max +15% composite bump; 0 disables). |
| `trade.outlook_infer` | Backlog #1 ([plan](plans/competitor-top20/01-opponent-outlook-classifier.md)): price each opponent's side of a trade through *their* contend/rebuild α instead of the `not_sure` 0.50 default. Per opponent: declared `league_preferences.team_outlook` → `infer_team_outlook` (roster age/value/pick-share signals) → `not_sure`. Since phase 2 (2026-07-17) the flag is **decoupled into label vs value roles**: the label (declared → inferred → not_sure) is resolved whenever this flag is on and feeds `match_context.opponent_outlook`, narrative acceptance framing, and lanes; the VALUE blend of `_vo` additionally requires `trade.outlook_blend` (turned off by the interview — "age = tiebreak"). Consensus-basis cards stay market-neutral by design. Default **false**; **enabled in `config/features.json` 2026-07-17** for the label role. `model_config` keys: `infer_w_vet_share` (1.0), `infer_w_youth_share` (1.0), `infer_w_pick_share` (2.0), `infer_contender_cut` (0.08), `infer_rebuilder_cut` (-0.08). |
| `trade.preference_lists` | Backlog #2 ([plan](plans/competitor-top20/02-asset-preference-lists.md)): per-player **untouchables** (hard give-side filter — dropped from `_known_user`/`known_user` pools + sweetener candidates in all gen paths; likes-you injections whose mirror would send an untouchable are skipped too) and **targets** (survive the divergence prune + a capped composite reward). Stored in `asset_preferences`; loaded into `_run_trade_job` and passed as `untouchable_ids`/`target_ids`. Default **false**; **enabled in `config/features.json` since 2026-07-09** (feedback #95 — mobile marks untouchables via long-press on the Matches tab). New `model_config` key: `target_acquire_bonus` (0.20), capped by `pos_multiplier_cap` (2.0). |
| `trade.outlook_seed` | Backlog #8 ([plan](plans/competitor-top20/08-per-league-outlook.md)): leagues with **no declared `team_outlook`** are seeded with `infer_team_outlook` run on the *user's own* roster (`_infer_user_outlook` in `server.py`), resolved identically in the generate-route cache pre-read and the worker so the job-cache key agrees. `GET /api/league/preferences` adds `inferred_outlook` + `inferred_signals` (additive) for the one-tap confirm UI. Nothing is persisted — recomputed per request, so roster drift self-corrects. Declared rows always win. Default **false**; **enabled in `config/features.json` 2026-07-17** (phase 2 "infer + confirm"): the inferred window now powers lanes + the clients' one-tap confirm UI rather than a value blend. No new config keys (reuses #1's `infer_*`). |
| `trade.crown_asset` | Backlog #10 ([plan](plans/competitor-top20/10-key-asset-package-adjustment.md)): key-asset consolidation premium in `package_value_v2`. The top asset of a *smaller-count* side (consolidation side) is priced up by `crown_rate · (share − floor)/(1 − floor)` where `share = v_top / Σ side`. Provably **neutral on equal-count trades** (1-for-1, 2-for-2) via an `n_other` guard, so flag-off and symmetric trades are byte-identical. Closes the 1-for-1 fairness-gate watch item the FPTrack/Dynasty-Daddy way (explicit multiplier, not a hard gate). Default **false**; **enabled in `config/features.json` 2026-07-17** (trade-logic interview) as the replacement for `trade_math.star_tax` (turned off the same day — a second tier-gap penalty double-counted this premium). The premium now also scales with the crown asset's absolute value: full `crown_rate` at/above `crown_elite_value`, linearly less below ("depends on the stud"). `model_config` keys: `crown_rate` (0.12), `crown_share_floor` (0.50), `crown_elite_value` (6000). |
| `trade.lanes` | Interview phase 2 ([plan](plans/trade-logic-interview-2026-07-17.md)): stamps every v2-orchestrated card with a `lane` — `"window"` (moves the roster toward the user's declared/seeded window) or `"value"` (pure value play). Classifier `classify_lane` reuses the now/future age curves purely as LABELS on consensus values ("age = tiebreak" — scoring untouched). No window (unset/`not_sure`) → no `lane` field → clients hide the lane filter. Serialized on trade cards; joined into swipe events. Default **false**; **enabled 2026-07-17**. `model_config` key: `lane_shift_frac` (0.10). |
| `trade.fit_premium` | Interview phase 2 ("yes, flag it"): the honest exception to the #108 raw-board gate — a 1-for-1 that LOSES the user a little raw-board value is allowed when it fills a positional need (receive position in `position_needs`, give position not) and the loss ≤ `fit_premium_max_loss`. The card carries `fit_premium: {value_paid, position}`, an honest narrative lead ("you pay a little on your own board for the fit"), and a client badge. Both surplus gates still apply (marginal values usually show the gain that justifies it). Default **false**; **enabled 2026-07-17**. `model_config` key: `fit_premium_max_loss` (300). |
| `trade.aggression_ab` | Interview phase 2 ("test all three"): stable per-user opening-offer bucket — `light` / `fair` / `generous` via md5(user_id) % 3 — that reweights which ACCEPTABLE offers lead the deck: light boosts consensus-tilt-toward-user offers, generous the reverse, fair prefers balance (`composite ×= 1 ± aggression_weight · tilt`, applied after all gates). Cards carry `aggression_variant`; swipe events log it (plus `lane` and `fit_premium`) so acceptance rates can be compared per bucket. Default **false**; **enabled 2026-07-17**. `model_config` key: `aggression_weight` (0.20). |
| `calc.open_calculator` | Backlog #27 (PRD at `staged-work/backlog-21-30/prds/27-open-trade-calculator.md` — **gitignored, local-only**, so it resolves on the operator's machine and in no clone): gates the **public, no-session** open-trade-calculator compute routes `POST /api/calc/score` + `GET /api/calc/values` (both 404 when off). The static `web/calculator.html` SEO page ships **unflagged** (like `faq.html`); when the flag is off its Score button degrades to a "coming soon" state via the self-fetched `/api/feature-flags`. No new endpoint config keys — reuses the backlog #6 `verdict_*` `model_config` keys for band thresholds so the public calc and in-app trade cards agree on the same trade. Default **false**. |

## Flags — Owned draft picks in calculator + suggestions (#158/#170/#171 — ship dark)

| Flag | Default | Gates |
|---|---|---|
| `market.trade_capture` | false | Market-data readiness (PRD #43 Phase-1 data foundation / #26): capture executed Sleeper league trades — public v1 `GET /league/<id>/transactions/<week>`, legs 1–18, `type=trade` + `complete` only — into the `sleeper_trades` table during `session_init`'s background daemon (`backend/sleeper_trades_service.py`). Capture ONLY (raw payload retained, idempotent on `transaction_id`); no scoring, no aggregation, no UI. Best-effort and off the request path; Sleeper numeric league ids only. Off ⇒ no fetch, no rows. Currently **true** in `config/features.json` (data must accumulate before any observed-market feature can be built — same "start logging now" logic as #57); the flag is the kill switch. |
| `market.roster_history` | false | **ADR-011 (#46 Wrapped P0)** — weekly league-state capture into `league_roster_history` + `league_board_history`: the on-sync writers (session-init daemon last block + the seven platform import/refresh sites), the `daily-tick` weekday-gated sweep (server-side fetch, all four platforms — YR-8), and `POST /api/cron/roster-snapshot`. Gates **writes only** — `metadata.create_all` still creates the tables when off, so flipping mid-season is a behavior change, never a schema surprise. Currently **true** in `config/features.json` (capture that ships dark is capture that did not happen; the urgency is Week 1). Off ⇒ no snapshot writes anywhere, tick payload byte-identical. The env knob `FTF_ROSTER_SNAPSHOT_WEEKDAY=7` kills only the sweep half (on-sync capture keeps running) — the deploy-free lever for the worker-blocking half. |
| `market.movers` | false | **#243 "Market pulse" strip** — gates `GET /api/market/movers`: top risers/fallers by trailing-window % change of FTF community value (`player_value_history` `consensus_value` snapshots; read-only over the data #57 already accumulates, via `database.load_value_movers_window`). Off ⇒ the route 404s and the mobile `MarketPulseStrip` (League home, below Explore) renders nothing. Currently **true** in `config/features.json`; the flag is the kill switch. Empty-safe while history is thin — flipping it on before snapshots have accrued shows nothing rather than erroring. |
| `picks.owned_sync` | false | Revives the per-league owned-pick sync (`database.sync_draft_picks` on the session_init daemon for Sleeper; `server._sync_mfl_owned_picks` at MFL link/import) + normalizes MFL picks into `draft_picks` + enriches `GET /api/league/picks` with `pool_value`/`label`/`picks_supported` + the mobile In-league calculator's owned-pick rows. Off ⇒ no owned-pick rows written or surfaced (byte-identical to today; the sync was dead code since the trade-engine-v2 rebuild). ESPN leagues never write rows (`picks_supported:false`). |
| `picks.rank_year_labels` | false | **#207 (2026-08-05), currently `true`.** Serves the 12 generic pick rungs on `GET /api/rankings` + `GET /api/trio` with a **year-explicit** label ("2026 Early 1st" when the active league's rookie draft hasn't happened; "2027 Early 1st" once it has) and a `years_out`-discounted `pick_value`, resolved from the league row's cached `draft_status` (`backend/draft_status.py`). Rung ids, universal-pool membership, board Elo and rank are untouched — Option A "relabel, don't add/remove" ([item folder](feedback/items/207-rookie-draft-detection/) — `status.md` + `mfl-parity-status.md`; there is no `plan.md`). **Fail-safe:** `unknown` / never-checked reads as NOT drafted, i.e. current-year picks stay visible. Off ⇒ today's year-less `"Early 1st Round Pick"` labels and undiscounted values, byte-identical. Detection + its caching run regardless of this flag (the flag gates only what is served). |
| `trade.picks_in_pool` | false | Injects each team's owned picks (capped `picks_pool_cap`, top-N by `pool_value`) as priced `position="PICK"` pseudo-assets into the suggestion candidate pool in `_run_trade_job`, so a generated trade can send/receive a pick (#170/#171). **Data inclusion only** — the engine already prices PICK assets (`dynasty_value`); scoring/weighting is unchanged. Off ⇒ no pick ever appears in a suggestion. `model_config`: `picks_pool_cap` (6). |
| `trade.asset_ideas` | **true** | **#172/#189 follow-up** — gates `POST /api/trades/asset-ideas` (asset-centric Upgrade / Lateral / Downgrade idea groups for one pinned asset, `TradeService.generate_asset_ideas`) + the mobile grouped-ideas panel on TradesScreen (rendered when exactly ONE finder target is pinned; the deck flow is untouched). Off ⇒ the route 404s and the panel never renders. Default ON (operator ask); this flag is the kill switch. `model_config`: `asset_ideas_lateral_band` (0.10), `asset_ideas_group_cap` (6). |
| `outlook.odds` | false | **#169** — gates `GET /api/league/outlook` (playoff/championship odds pipeline, `backend/outlook/`). Off ⇒ the route 404s and nothing else changes. Source selection via `FTF_OUTLOOK_STRENGTH_SOURCE`; numeric knobs under `model_config` (`outlook_*`). `meta.beta` (`completed_weeks<6`, independent of `meta.is_preseason`) flags every payload through week 5 as low-confidence. **Dark on purpose and registered in all four touches** (this table, `backend/feature_flags.py`, `config/features.json`, `backend/tests/fixtures/flags/release.json`) at false — deliberately ABSENT from `backend/tests/fixtures/flags/all-on.json` so a flag sweep can't light an uncalibrated surface, and absent from mobile's `LAUNCHED_FLAG_DEFAULTS`. Lighting is a one-touch flip once calibration passes — procedure in [feedback/items/169-outlook-league-summary/status.md](feedback/items/169-outlook-league-summary/status.md) §Productionization. Ships-off + mirror asserted by `backend/tests/test_outlook_route_cache.py`. |

## Flags — Directional outlook weighting (feedback #175 — ships dark)

| Flag | Default | Gates |
|---|---|---|
| `trade.outlook_direction` | false | **#175** — steers the deck by the USER's resolved outlook (declared `team_outlook` → #8 seed → None), via `outlook_direction_mult` applied in `_generate_trades_v2` AFTER all gates to every v2-orchestrated card (divergence v2/v3 + consensus). Reuses the lane machinery: the card's value-weighted now-lean shift (received − given, `classify_lane`'s exact shift, on CONSENSUS values). Rebuild-side (`rebuilder`/`jets`): shift > 0 (acquiring win-now/older production) ⇒ composite `×= max(0.05, 1 − outlook_dir_penalty·shift)`; shift < 0 (acquiring future capital — younger players, picks) ⇒ `×= 1 + outlook_dir_boost·(−shift)`. Plus the **~1-year-gap rule**: primary (highest-consensus-value) give is a player and the primary return is an older player beyond `outlook_dir_age_tolerance` years, with no pick / tolerance-younger return component worth ≥ `outlook_dir_rescue_frac` of the primary give ⇒ `×= outlook_dir_age_gap_mult` (**near-exclusion by penalty, not a hard filter** — a genuinely lopsided-value win can still surface). Contend-side (`championship`/`contender`): ONLY the mild symmetric mirror `×= 1 + outlook_dir_contend_weight·shift`, no age-gap rule. `not_sure`/None ⇒ no effect. Cards carry the in-process `outlook_dir` multiplier (QA record, not serialized). Off ⇒ composites byte-identical. `model_config` keys: `outlook_dir_penalty` (3.0), `outlook_dir_boost` (1.0), `outlook_dir_contend_weight` (0.5), `outlook_dir_age_tolerance` (1.0), `outlook_dir_age_gap_mult` (0.15), `outlook_dir_rescue_frac` (0.5). |

## Flags — Compressed-board trade generation (2026-08-15 field bug — LIVE)

Both flags address one field report on the operator's real league FFV3: three of
four **boarded** leaguemates produced zero trade cards at any per-opponent budget
while mutually positive trades demonstrably existed. Two independent defects, one
flag each. Full write-up + measured before/after: `docs/plans/compressed-board-pool/scope.md`.

| Flag | Default | Gates |
|---|---|---|
| `trade.pool_calibration` | **true** (flipped by operator 2026-08-15) | The v3 candidate-pool prune (`trade_optimizer.generate_pair_trades_v3`) ranks each side's assets by the raw divergence `_vo(p) - _uv(p)` and keeps the top `v3_pool_size` (12). Because `elo_to_value` is **exponential**, an opponent board sitting uniformly lower than the user's — a floor-pinned, barely-started board (the three broken boards had median Elo 1201 against the user's shrunk board) — deflates high-Elo players far more than low-Elo ones: a stud loses thousands of value points, a bench body loses tens. Every tradeable stud therefore sorts BELOW the user's worthless bench, the pool fills with junk, and the pair yields nothing. ON ⇒ the opponent's value space is rescaled by the **geometric-mean ratio over the assets in play** (the same players priced on both boards, so no roster-strength confound; equivalent to shifting the opponent's board onto the user board's mean Elo) before differencing, making the pool **order** exactly invariant to a board-wide offset — a difference that carries zero information about which player either side prefers. **Prune ordering ONLY**: every surplus, fairness and composite number still uses each side's own raw value space, untouched. Computed from the `_uv`/`_vo` accessors, so the #1 outlook blend is included automatically. Boards already on the same scale ⇒ factor ≈ 1 ⇒ deck unchanged. OFF ⇒ pool byte-identical to today. No new `model_config` key. **Note:** raising `v3_pool_size` is *not* an equivalent mitigation — at 30 it rescues the same pairs but costs 26–102 s per pair against ~2 s at 12 (enumeration is cubic-ish in pool size on both sides). |
| `trade.divergence_fallback` | **true** (flipped by operator 2026-08-15) | `_generate_trades_v2`'s boarded/unboarded branch was `if member.has_rankings: <divergence> else: <consensus>` with **no fall-through**, so a boarded member whose divergence path returned zero cards got no consensus fallback either and vanished from the deck entirely — ranking a little made a leaguemate a *worse* trade partner than never ranking at all. ON ⇒ when the divergence path (v3 or v2) returns an empty list for a boarded member, the same `_generate_consensus_for_pair` the never-ranked path uses runs for that pair. Cards stay labeled `basis:"consensus"`, so `basis:"consensus"` on a `has_rankings=true` member is the new-but-already-instrumented combination to watch. Strictly additive: fires only on an empty result, so a member already producing cards is untouched. OFF ⇒ the zero-card cliff remains. |

**Deck-size note (both flags):** generation stops once the deck reaches
`global_target = max(30, max_per_opponent * 6)`, and boarded members are visited
**first** by design — so opponents after the break contribute nothing and
rescuing boarded members **displaces** unranked members' consensus cards.
Composition shifts toward real counterparties.

The target is a **stop-when-reached threshold, not a truncation**: the check
(`trade_service.py`, `if len(new_cards) >= global_target: break`) runs *after* an
opponent's whole batch is appended, so the deck can overshoot by up to
`max_per_opponent - 1`. The post-deploy FFV3 read returned **34** cards, not 30 —
earlier pre-deploy reads landed on exactly 30 only because every batch was a full
5 and the running total hit the threshold exactly.

## Flags — Trade generation pipeline v2 (matchmaking research — ships dark)

| Flag | Default | Gates |
|---|---|---|
| `trade_gen.v2` | false | Routes `TradeService.generate_trades` to `backend/trade_gen_v2.py`, the research-driven staged pipeline (matchmaking research item 2 — `docs/research/matchmaking/` rounds 1–2; scope block `docs/plans/matchmaking-engine/trade-gen-v2-scope.md`). Stages: divergence-driven partner + centerpiece selection (want/accept boards applied as filters, targets as priority) → bounded return-package search around each centerpiece (≤3 assets + picks per side) → hard gates IN ORDER (composition hygiene reusing #141 filler + #227 pick-churn → roster feasibility both sides → **dual-board ε-gain**: each side must gain ≥ `gen2_epsilon` on its OWN board, with a non-linear consolidation discount so junk can't stuff a package → **consensus fairness band** ±`gen2_band` as a defensibility constraint, never an objective) → rank by joint gain, tiebreak by surplus-split symmetry → empirical-Bayes **acceptance-prior** multiplier → league-level **exposure shaping** (per-counterparty cap + viable-suggestion floor — ordering only, counts logged) → **tier metadata** (`endorsed`/`featured`/`browse`) + **MESO** return-package variants + structured two-sided `rationale` on the cards. **No engine truncation** (operator decision 2026-08-16): the engine returns the FULL ranked survivor set — uncapped discovery + uncapped browsable list as a ranking-signal surface; scarcity applies only to endorsement via the `tier` field, and any list-length limits are caller-passed presentation parameters. Built dark ALONGSIDE the v2/v3 engine: OFF (default) ⇒ the module is never imported and every existing generation path is byte-identical. Divergence-only by design — unranked opponents keep the flag-off engine's consensus path. Kill switch is the flag itself (deploy-free). |

## Flags — Trade presentment rules (G6 2026-08-16 — ships ON)

| Flag | Default | Gates |
|---|---|---|
| `trade.presentment_rules` | **true** (ships ON — operator decision Q-G6-3; feedback #304 #336 #339 #340 #341, specs in [feedback/items/304-positional-need-filter/](feedback/items/304-positional-need-filter/)) | Backend-only, no client surface. ON ⇒ two new layers on the **v1 generation path** (`trade_gen.v2` carries its own gate stack): **construction rules** run inside every generator (v3 loop, v3 sweetener re-validation, v2 `_consider`, consensus `_emit`) so killed candidates refill from the enumeration — R1 `overpay_ok` (#340: raw-consensus gap ≥ `max_overpay_min_value` AND ≥ `max_overpay_frac` of the larger side kills, BOTH directions, **independent of the client fairness toggle**), R2 `pos_net_ok` (#341: per-position signed net |recv−give| ≤ `pos_net_cap` over QB/RB/WR/TE, picks uncounted), R3 `pick_gap_ok` (#339: for gap ≥ `pick_gap_min_value`, a heavier-side pick inside the two-sided band [`pick_gap_frac`·gap, gap/`pick_gap_frac`] — "the pick IS the gap" — kills; a pick far larger than the gap passes), R5 `need_gate_ok` (#304: window-scaled need gate on the primary received player, **untargeted discovery decks only** — pinned/opponent-scoped/explicit-acquire jobs bypass via a server-derived flag, never client-passable); and **eligibility**: R4 (#336) windowless awaiting-like + pending/accepted-match exclusion at `_dedup_and_sort` (streaming snapshots included) and the likes-you injector (dedup only — Q21 keeps the quality rules off that surface; the D-055 floor is its quality gate; `declined`/retracted regenerate). Never relaxed by the #189 relaxed pass. Per-job per-rule kill counters + the `presentment-tripwire` WARNING ([runbook](runbook.md)) ship with it. Per-rule deploy-free kill switches are the knobs below; this flag is the one-line group revert and R4's only switch. OFF ⇒ every generation path byte-identical to pre-G6 (pinned by test). |

## Flags — Send in Sleeper (flagged beta)

| Flag | Default | Gates |
|---|---|---|
| `trade.send_in_sleeper` | false | ⚠️ **ToS-adverse.** `POST/GET/DELETE /api/sleeper/link` + `POST /api/trades/propose` (all 404 when off) — sends trades through Sleeper's *undocumented* private write API (`propose_trade` GraphQL mutation). Requires `SLEEPER_TOKEN_KEY`. Adapter: `backend/sleeper_write.py`; token store: `sleeper_credentials`. Capture + ToS/risk (C4): [runbook](plans/sleeper-write-capture-runbook.md). |
| `trade.send_in_mfl` | false | "Send in MFL" — `POST /api/trades/propose-mfl` + the MFL branch of `POST /api/trades/validate` + the mobile send button on MFL leagues (404 / unmounted when off). Rides MFL's **documented** import API (`import?TYPE=tradeProposal`) with the #177 `MFL_USER_ID` cookie (`mfl_credentials`; requires `SLEEPER_TOKEN_KEY` for at-rest encryption). Adapter: `backend/mfl_write.py`. **Keep off until the operator live-verification checklist passes** (import response shape, wwwNN import host, pick encodings, MFL client registration): [scope block](feedback/items/177-mfl-auth-link/send-in-mfl-scope.md). |
| `espn.send` | false | ⚠️ **Undocumented ESPN write API.** "Send in ESPN" — `POST /api/trades/propose-espn` + the mobile send button on ESPN leagues (404 / P0-6 copy fallback when off). Players only; picks hard-block. Payload live-verified for football 2026-08-11 ([capture](plans/espn-send-live-capture-2026-08-11.md)); adapter `backend/espn_write.py`; cookies from `espn_credentials` (requires `SLEEPER_TOKEN_KEY`). **Deliberately ABSENT from `config/features.json` (D-026)** — do not add the key until the auth probe proves `espn_s2`+`SWID` alone authorize a server-side POST (the captures were browser-session; a CSRF/session token may be required). |

## Flags — Account auth (account-auth plan P2 — ships dark)

| Flag | Default | Gates |
|---|---|---|
| `auth.accounts` | false | Apple/Google identity anchors ([plan](plans/account-auth-plan-2026-07-11.md) §3-P2): `POST /api/auth/apple`, `POST /api/auth/google`, `GET /api/account` (all 404 when off) + the mobile Sign in with Apple button (SignInScreen) and the Settings linked-identity display. **`DELETE /api/account` is deliberately NOT gated** — in-app account deletion is App Store Guideline 5.1.1(v). Logic: `backend/accounts.py`; tables: `accounts` + `linked_identities`. Before flipping ON: complete the ASC steps in the runbook (Sign in with Apple capability) and update `web/privacy.html` to cover Apple/Google `sub` storage (plan §4 / #114). |
| `auth.email_capture` | false | Plaintext email storage on `accounts` ([spec](business/product/2026-07-17-email-capture-spec.md)). **Off (default)** = pre-spec behavior: Apple's first-auth email is SHA-256-hashed (`linked_identities.email_hash`), plaintext discarded. **On** = Apple first-auth email + the future Settings capture field store to `accounts.email` with `email_consent_at`. **Flip only in the same release as the capture UI + `web/privacy.html` update** — the policy currently states no email addresses are stored. Logic: `backend/accounts.py` (`_email_capture_enabled`, `set_account_email`, `find_or_create_account`). |
| `auth.enforce_verified_writes` | false | Account-auth P1→P3 write-gate mode ([plan](plans/account-auth-plan-2026-07-11.md) §3). **false = GRACE**: unverified sessions' mutating requests are allowed but each logs one `AUTH-GRACE` line (funnel instrumentation — see [runbook](runbook.md)). **true = P3 enforcement**: unverified writes → 403 `verification_required`. Independent of grace, a user_id with a verified controller (`users.verified_via` set) always denies unverified writes, and the hard routes (`POST /api/sleeper/link`, `POST /api/trades/propose`, `POST /api/account/reset-rankings`) always require proof. Flip to true only after the P1 verification funnel looks healthy (plan §2d: ~2–4 weeks). |

## Flags — ESPN league linking (Phase 1 — ships dark)

| Flag | Default | Gates |
|---|---|---|
| `espn.link` | false | Read-only ESPN league import via the **unofficial** v3 API ([plan](plans/espn-league-linking-plan-2026-07-11.md)): `POST /api/espn/link`, `GET /api/espn/leagues`, `POST /api/espn/import` (all 404 when off) + the mobile "Link an ESPN league" affordance (LeaguePicker + League tab re-sync). Adapter: `backend/espn_service.py` (crosswalks rosters to Sleeper ids via DynastyProcess `db_playerids.csv`, 24h-TTL in-memory cache, snapshot fallback). Private-league cookie store: `espn_credentials` (Fernet — **reuses `SLEEPER_TOKEN_KEY`**; public leagues need no auth or key). Doubles as the **kill switch**: ESPN blocking reads or an App Store objection → flip off, feature goes fully dark (imported data stays inert in the DB). Before flipping ON: run the live public-league smoke via `python3 -m backend.espn_service <league_id> [season]` (plan §5 — the fixture tests can't see endpoint churn). |
| `espn.webview_capture` | false | **Phase 1b** ([scope](plans/espn-connect-webview/scope.md)) — the mobile in-app **WebView cookie-capture** path. Gates the "Sign in to ESPN" primary button in `EspnLinkSheet`'s private-league section: it pushes `EspnConnectScreen`, which loads ESPN's own login in a WebView and reads the `espn_s2` + `SWID` cookies from the **native cookie store** (`@react-native-cookies/cookies` / WKHTTPCookieStore — `espn_s2` can be HttpOnly, so injected `document.cookie` can't see it), then feeds them back into the sheet's existing paste fields. Manual paste stays as the fallback. Also gates the League tab's re-sync recovery button (`league.espn-resync-signin`, shown on a 403 `espn_auth_required`) — the sheet's auth-error auto-expand itself is unflagged (flag off it reveals the paste fields instead). **Client-only gate** — no backend route reads it (`POST /api/espn/link` already accepts the cookies); requires `espn.link` also ON to have any effect. Ships OFF: the flag flips only after a TestFlight build carrying the new native dependency validates against a real private league. Rollback lever: flip off ⇒ the sheet renders exactly as before (manual paste only), no client update. |
| `espn.league_picker` | true | **2026-08-09** — league discovery so the user doesn't have to type a league id ([field feedback](feedback/items/espn-webview-escape/status.md): "fetch all their ESPN leagues and let them pick"). Gates `GET /api/espn/my-leagues` (404 `feature_disabled` when off) — fetches the session user's already-stored `espn_credentials` cookies' ESPN **fan profile** (`fan.api.espn.com/apis/v2/fans/{SWID}`, a separate host from the league-read API, §ESPN league linking above) and lists the football leagues it finds, via `espn_service.fetch_fan_leagues`/`_parse_fan_leagues`. **Response shape UNVERIFIED** — the endpoint is undocumented by ESPN; the parser follows the best-known community shape and degrades to an empty/partial list on drift, never a 500 — needs TestFlight confirmation against a real account. Also gates the mobile **league-SELECTION list** in `EspnLinkSheet` that replaces the league-id text input once cookies are available (`espn.webview_capture` capture or a prior paste); manual league-id entry stays the fallback path either way — public leagues need no login at all and are untouched. Requires `espn.link` also ON to have any effect. Flag off ⇒ the sheet's input step is byte-identical to today (text field only, no picker fetch). |

## Flags — Multi-platform league linking — MFL / Fleaflicker (Phase 1 — ships dark; [plan](plans/multi-platform-linking-plan-2026-07-17.md))

Both are **zero-auth** public-read imports; no credentials table, no encryption key. Rosters crosswalk to Sleeper ids through the **same** DynastyProcess `db_playerids.csv` cache as ESPN (`espn_service.get_crosswalk`, now exposing per-platform id maps). Each flag gates its own `/api/{platform}/*` routes + the mobile link option and is the vendor/App-Store **kill switch** (imported data stays inert when off).

| Flag | Default | Gates |
|---|---|---|
| `mfl.link` | false | MFL import via the **official** export API: `POST /api/mfl/link`, `GET /api/mfl/leagues`, `POST /api/mfl/import`. Adapter `backend/mfl_service.py` (crosswalk via `mfl_id`; per-league `wwwNN` host resolution; `futureDraftPicks` stored raw in `leagues.platform_future_picks`, normalized into `draft_picks` since #158 and **re-fetched on the #207 draft-status cadence** since the #207/#228 MFL parity fix). Env: optional `MFL_USER_AGENT` (registered-client UA after MFL client registration — see [plan §9](plans/multi-platform-linking-plan-2026-07-17.md)); optional `MFL_COOKIE` for the CLI private path. |
| `mfl.auth_link` | false | **#177** MFL *authenticated* linking on top of `mfl.link`'s import path: `POST /api/mfl/auth-link` (MFL login → `myleagues`) + `POST /api/mfl/auth-import` (import **all** leagues at once, private leagues included, franchise auto-bound — no choose-team step) + the mobile "Sign in with MFL" path in PlatformLinkSheet. Password is transient (one MFL login POST, never persisted/logged); only the returned `MFL_USER_ID` cookie is kept — Fernet-encrypted in `mfl_credentials` via **`SLEEPER_TOKEN_KEY`**, falling back to session-only storage when the key is absent (nothing plaintext at rest). Both routes 404 dark when off. |
| `fleaflicker.link` | false | Fleaflicker import via the **official** public JSON API: `POST /api/fleaflicker/link`, `GET /api/fleaflicker/leagues`, `POST /api/fleaflicker/discover` (email lookup), `POST /api/fleaflicker/import`. Adapter `backend/fleaflicker_service.py` (crosswalk via `sportradar_id` from roster `externalIds`). No env/keys. |

**Before flipping either ON**, run the live public-league smoke (the fixture tests can't see endpoint churn):
- MFL: `python3 -m backend.mfl_service <league_id_or_url> [year]` (host auto-resolves; e.g. `python3 -m backend.mfl_service 10005 2026` → 100% by id)
- Fleaflicker: `python3 -m backend.fleaflicker_service <league_id>` (or an email to list leagues; e.g. `python3 -m backend.fleaflicker_service 312861` → 99.7% by id)

## Flags — Onboarding & conversion redesign ([plan](plans/onboarding-conversion/plan.md) v2.1)

**Master/individual semantics:** every `onboarding.*` feature is live iff **`onboarding.v2` AND its own flag**. `onboarding.v2` false = whole redesign dark regardless of individual flags (kill switch). Individual flags allow feature-by-feature enablement/rollback. `analytics.client_events` is deliberately **outside** the master — it gates instrumentation only (tracking plan v2 §S2) and must run against the *current* flow first to capture the pre-redesign baseline.

**Open-access Phase A (2026-08-15).** The v2 flow is no longer dark. Per [business/product/2026-08-14-open-access-onboarding.md](business/product/2026-08-14-open-access-onboarding.md) §5 Phase A (operator-ratified O-1), five onboarding flags **plus** `landing.try_before_sync` flipped **true in `config/features.json`** in one release: the built flow stops being an experiment overlay and becomes the product. **The flags stay as the revert levers** — they gate client behavior, not server routes, so flipping any one back to false is a config-only rollback (`POST /api/feature-flags/reload`, no deploy). The remaining `onboarding.*` keys (`share_sheet`, `rank_routing`, `demo_bridge`, `guided_layer`, `keep_warm`) are **not** in Phase A scope and stay dark.

| Flag | Default | `features.json` | Gates |
|---|---|---|---|
| `analytics.client_events` | false | **true** (baseline capture) | `POST /api/events` ingestion (404 when off) + client event SDK emission (`mobile/src/api/events.ts`). Instrumentation only; no UX change. |
| `onboarding.v2` | false | **true** | Master kill-switch for all `onboarding.*` features below. |
| `onboarding.landing` | false | **true** (Phase A) | Item 5 — username-first landing on SignInScreen (primary username field, quiet Apple re-entry link, not-found copy, Sleeper-down demo escape). First consumer of `landing.try_before_sync`, and the reason that flag flips with it (below). |
| `onboarding.trades_first` | false | **true** (Phase A) | Item 4 — trades-first hook: pregen at auth-return, skeleton/streamed first-run deck, first-run chrome collapse, provenance chip, identity-confirm strip. |
| `onboarding.league_autoskip` | false | **true** (Phase A) | Item 6 — single-league LeaguePicker auto-skip + error fallback. |
| `onboarding.quickset_prompt` | false | **true** (Phase A) | Item 7 — inline prompt card (first pass after swipe 2, else 3 swipes) + onboarding-mode QuickSet (suppress finish-prompt, return to Trades, force deck regen, diff banner). |
| `onboarding.apple_save_moment` | false | **true** (Phase A) | Item 8 — save-moment Apple prompt (honest framing, decline policy, one auto-prompt per save-moment class), persisted-username silent re-init, session-2 non-modal banner. |
| `onboarding.share_sheet` | false | false | Item 8 rider — native share sheet on liked trade card (user-initiated; appears only after the Apple prompt resolves). **Not Phase A.** |
| `onboarding.rank_routing` | false | false | Item 9 — RankHome chooser demoted to "More ways to rank", Rank tab defaults to QuickSet, deck-exhausted state → trio entry. **Not Phase A.** |
| `onboarding.demo_bridge` | false | false | Item 10 — persistent "See this for YOUR team →" bar in demo mode + redraft "Dynasty values shown" label/segment tag. **Not Phase A.** |
| `onboarding.guided_layer` | false | false | v2.1 guided layer — swipe-gesture hint (card 1), ≤4 coach marks, celebration beats (first like / first QuickSet save). **Not Phase A** — the open-access plan §6 records that the guided script was *designed* for trades-first and that Phase A makes it correct, but §5's flip list does not name this flag, so it stays dark pending an explicit call. |
| `onboarding.keep_warm` | false | false | Item 3 — server-side keep-warm affordances for the Render cold-start cron ping. **Not Phase A** (named in the plan's §9 risk row for cold-start latency, not in the §5 flip list). |
| `onboarding.guide_v2` | false | false | **Guided Onboarding v2** ([scope](plans/guided-onboarding-v2/scope.md) §2) — gates every v2 addition to The Analyst tour: the declarative eligibility layer on `GuideStep`, the guide's membership in the interrupt arbiter, all new beats (N1, N2, N4, N5, N6.1, N8, N9) and the copy changes riding the new script fields. Under the `onboarding.v2` master like its siblings. **False = byte-identical to pre-build behavior**, which makes it the rollback lever: config-only (`POST /api/feature-flags/reload`, no deploy). **Graduation to true** is an operator decision — the TestFlight checklist passes *and* first-cohort diagnostics M1–M8 are clean. Distinct from `onboarding.guided_layer` (the v2.1 coach-mark surface, still dark) and `onboarding.guided_avatar` (the shipped v1 tour, already true). |
| `landing.try_before_sync` | false | **true** (Phase A) | Not an `onboarding.*` key and **outside** the `onboarding.v2` master, but the documented **launch pairing** for `onboarding.landing` (`config/features.json` `_comment_onboarding`): `POST /api/session/demo` checks it server-side and **404s when off** (`backend/server.py:18929`), so the v2 landing's Sleeper-down escape and demo link are dead ends without it. Flip and revert it together with `onboarding.landing`. |

## Flags — Monetization platform (ships dark; [foundation](plans/monetization/00-platform-foundation.md), [plan index](plans/monetization/README.md))

One flag per monetization strategy — each independently flippable, ALL default false. **Rollout order** (foundation §1): `monetize.entitlements` first in observe mode (logs `ENTITLE-OBSERVE`, never blocks — enforcement needs `monetize.paywall` too), then `monetize.founder` + `monetize.paywall` for the TestFlight window, `monetize.pro`/`monetize.season_pass` at launch, `growth.*` after, ads last. The manual-grant admin routes (`/api/admin/entitlements/*`) and billing webhooks are deliberately **unflagged** — operator surface + provider traffic; grants written while dark sit dormant.

| Flag | Default | Gates |
|---|---|---|
| `monetize.entitlements` | false | Master: entitlement checks become active (`entitlements.check_pro`). Off = every user implicitly pro. On without `monetize.paywall` = observe mode. |
| `monetize.paywall` | false | Purchase UI surfaces (mobile + web) AND the enforce half of `check_pro` (both flags on → 402 on gated routes). |
| `monetize.pro` | false | Pro subscription SKUs purchasable + Pro gate list ([plan](plans/monetization/pro-subscription/prd.md)). |
| `monetize.season_pass` | false | Year-labeled season SKUs ([plan](plans/monetization/season-pass/prd.md)). |
| `monetize.founder` | false | Founder Lifetime window — the flag flip IS the window open/close ([plan](plans/monetization/founder-lifetime/prd.md)). |
| `monetize.affiliate` | false | Affiliate placements + partner registry ([plan](plans/monetization/affiliate/prd.md)); per-partner enables live in the (future) `config/affiliates.json`. |
| `monetize.ads_web` | false | Web display ads ([plan](plans/monetization/ads/prd.md)). |
| `monetize.ads_mobile` | false | Mobile AdMob banner + rewarded + ATT prompt. Independent kill switch from web. |
| `growth.referral` | false | Give-get referral program (invite CTAs, reward granting). |
| `growth.group_unlock` | false | League group-unlock experiment (A/B vs per-referrer rewards). |
| `ranks.accuracy_scoring` | false | Passive board snapshots + quarterly scoring + leaderboard ([marketplace plan](../docs/business/product/2026-07-17-rankings-marketplace-plan.md) phase 1). |
| `ranks.rank_sets` | false | Publish/adopt rank sets, free only (phase 2). |
| `ranks.set_types_extended` | false | `redraft`/`bestball` set types (platform-thesis test; `dynasty`/`rookie` are unflagged launch types). |
| `ranks.import` | false (ON in features.json) | #232 follow-on (2026-08-02): paste-first rankings import — gates `POST /api/rankings/import-match` + `/import-apply` (404 while off) and the mobile chooser's "Have rankings already?" entry. Ships **true** — the key is a kill switch, not a dark launch (also baked into the mobile `LAUNCHED_FLAG_DEFAULTS`). |
| `ranks.source.dynasty_nerds` | **true** (flipped 2026-08-16, operator) | **Premium rankings import v1** ([D-058]; [scope](plans/connected-rankings/build-v1-premium-import/scope.md)): the Dynasty Nerds row in the import half sheet + its CSV preset (header signature `Rank,Player,Team,Position,Age,Exp,Value[,Trend,PPG],Pos Rank`). Off ⇒ the row is absent and the preset never runs; paste import and generic CSV upload are **not** gated by this key. The import is order-only in both states — the CSV's `Value`/`Trend`/`PPG` columns are never read or stored. **Flipped ON 2026-08-16 by operator directive** (graduation testing proceeds on TestFlight build 112; compiled client default stays false, so pre-112 builds never show the row). Kill switch: set back to false. |
| `ranks.source.dlf` | false | Same, for DLF. Additionally blocked on a **real subscriber-exported DLF fixture** to pin its (dynamic, ranker-dependent) header shape — addendum §3.4 fixture gate — so it stays off even after `dynasty_nerds` graduates. |
| `marketplace.publisher_sets` | false | Publisher IAP + subscriber account-linking (phase 3). |
| `marketplace.contributor_sales` | false | Contributor credit-priced sales (phase 4). |
| `marketplace.cash_payouts` | false | Stripe Connect cash-out rung (phase 5). |

## Flags — App-teardown remediation (2026-07, branch `teardown-remediation` — all dark)

Registered under the `_comment_teardown` block in `config/features.json`; source PRDs live in the gitignored `app-teardown-review/` (per-section `prds/` folders; see [ADR-008](adr/adr-008-teardown-remediation-wave.md)). ALL default false pending operator review; implementations land flag-gated on branch `teardown-remediation`. Deliberate unflagged exceptions (per the features.json comment): the league-prefs authz fix (security), doc/legal-copy corrections, and inert accessibility annotations (labels/roles/traits).

| Flag | Default | Gates (source PRD) |
|---|---|---|
| `ux.sheet_guard` | false | Unsaved-input protection on sheet dismiss — FeedbackSheet draft persist/confirm, EspnLinkSheet keeps step + fields across close (01/prd-01). |
| `ux.rank_tab_destination` | false | Rank tab-press navigates to the preferred/last-used rank surface instead of opening the 7-row menu; in-screen mode switcher; RankHome back header; chevron removed (01/prd-02). |
| `ux.retap_active_tab` | false | Focused-tab re-tap pops the tab's stack to root / scrolls the primary list to top on Trades, Matches, League (01/prd-05). |
| `ux.deeplink_router_v2` | false | Single deep-link route table covering every screen; push taps + share links through one path; unroutable-link home-plus-toast fallback; pre-`navigationRef.isReady()` intents buffered and replayed (01/prd-04). |
| `ux.player_context_menu` | false | One player long-press vocabulary — context menu on the player card + visible twins for gesture-only actions (untouchables, trio info sheet) (03/prd-02). |
| `ux.swipe_undo` | false | Undo for the triage loop: pass/like swipe rewind + match-dismiss take-back via a toast action slot (03/prd-03). |
| `ux.toast_v2` | false | Tone-based toast durations (errors persist long enough to read), action slot, VoiceOver announcements via `AccessibilityInfo` (04/prd-03). |
| `ux.prompt_arbiter` | false | Global one-prompt-at-a-time arbiter across instructional families (banners, coach marks, prompt cards, modals) + push-primer backoff after "Maybe later" (04/prd-04). |
| `ux.empty_state_ctas` | false | Empty states offer the action their copy names (e.g. Matches empty → "Go to Trades" instead of Refresh) (04/prd-05). |
| `ux.help_surface` | false | In-app help surface — FAQ/ranking-method content reachable from mobile + contextual ⓘ at moments of doubt (04/prd-01). |
| `ux.board_search` | false | Name search (Quick Set pattern: scroll-to + highlight) on ManualRanks and Tiers boards (07/prd-04 item 6). |
| `ux.touch_polish` | false | Touch-target & drag bundle: 44pt floors (chips, slider dots, segments, pills, compact Button), ManualRanks `activationDistance` 5→18, haptics-at-lift taxonomy (03/prd-04). |
| `ux.whats_new` | false | One versioned what's-new CoachMark per release, anchored where the headline change lives, shown-once persisted; never a modal (07/prd-04 item 5). |
| `ux.outlook_inline_default` | false | Flags-off default path fix: inline inferred-outlook confirm banner replaces the forced OutlookSheet modal on first Trades visit (04/prd-02). |
| `a11y.text_scaling` | false | Dynamic Type support — scalable type/containers, `maxFontSizeMultiplier` policy, AX-size layout adaptation (02/prd-01). |
| `a11y.reduce_motion` | false | Reduce Motion — mobile `useReducedMotion` branches (card fling, toasts, modals) + web `prefers-reduced-motion` on all animation, incl. the infinite loops (02/prd-02). |
| `visual.chalkline_cleanup` | false | Retire the legacy theme: migrate the four stragglers (FormatGate, TierStickyHeader, TierTargetChips, TileStats) to Chalkline tokens + contrast/type floors (02/prd-03, 02/prd-04). |
| `notif.tz_sync` | false | Write the client's `X-User-TZ` into `notification_prefs.tz` so quiet hours/digests deliver recipient-local (05/prd-01). |
| `notif.tap_routing_v2` | false | Notification tap routing: cold-start handling (`useLastNotificationResponse`), exact-screen landing (stop discarding `match_id`), bundle/bell routing, pre-ready buffer (05/prd-02; consumes `ux.deeplink_router_v2`). |
| `notif.denial_recovery` | false | Denied-permission recovery: `Linking.openSettings()` path at want-it moments; Settings toggles reflect real OS permission state (05/prd-03). |
| `notif.reengagement_default_off` | false | `reengagement` push bucket defaults to 0 and is separately consented — the primer's transactional consent no longer opts users into winbacks/season pushes (05/prd-04; Guideline 4.5.4). |
| `notif.honest_winbacks` | false | `winback_dormant` fires only on a real match lookup (like `winback_matches`) + lifetime stop after unanswered winbacks; primer overpromise copy removed (05/prd-04). |
| `growth.share_landing` | false | Close the share loop: mobile shares compose the `/s/trade/<id>` / `/s/tiers/...` OG landing URLs; universal links (AASA + associatedDomains) open them in-app (07/prd-01, 01/prd-03). |
| `growth.tier_board_share` | false | Gates `GET /og/tiers/<pos>/<username>.png` and `GET /s/tiers/<pos>/<username>` — both 404 while dark. **OFF is the resting state, not a dark launch:** operator decision D-P1-12 (`docs/plans/audit-p1-remediation/DECISIONS-p1.md`) rules that sharing of rankings / tier boards is not a product surface and must not be live in any form. Both routes previously shipped **unguarded** — no session, no in-app link — so any username's board was fetchable by guessing the URL. `growth.share_landing` covers the trade/package routes only and never carried these two. Do not flip without an explicit operator reversal of D-P1-12. |
| `growth.rating_prompt` | false | `StoreReview` rating prompt at demonstrated-satisfaction moments (tier save, Nth liked trade, first Sleeper send); once/version, 3/365 budget; unhappy paths keep routing to feedback (07/prd-02). |
| `account.data_export` | false | Download-my-data export (the deletion matrix as export manifest), surfaced beside Delete in Settings → Account (06/prd-02; GDPR Art. 20). |
| `account.sleeper_disconnect` | false | "Disconnect Sleeper sending" row in Settings → Account (status from `GET /api/sleeper/link`, wired to `unlinkSleeper()`) — the control the privacy policy already promises (09/prd-01, 06/prd-04). |
| `account.settings_v2` | false | Settings IA regroup to five frequency-ordered groups, Testing section gated to TestFlight builds, instant ranking-method preference apply (06/prd-04). |
| `profiles.user_toggle` | false | Per-user public-profile visibility opt-out under `profiles.public_pages` — the global flag alone never publishes a user who opted out (06/prd-04). |
| `auth.persistent_sessions` | false | Durable sessions for account-only (Apple) users — refresh-token model with server-side revocation, replacing the 4h in-memory dict (06/prd-03; the codebase's own "P3"). |
| `league.rookie_board_entry` | false | Mounts the fully-built-but-orphaned RookieDraftBoardSheet as a League Explore row during draft season (07/prd-04 item 2). |
| `league.picks_always_counted` | **true** | Kill switch for a **reversal of shipped behavior** on the mobile League rankings chart (`LeagueSummaryScreen`, route `LeagueRankings`) — feedback #293/#294. The screen shipped with the rule "picks are neither starters nor bench", so a team's draft capital counted ONLY in the All subset with no position filter and vanished the moment the user tapped Starters, Bench, or a position pill. **ON** ⇒ the team total adds the full `picks.value` in all three subsets and whenever `PICKS` is in the position filter; the neutral Picks segment, legend swatch and pill render everywhere; the first position tap auto-adds `PICKS` (lit pill, one tap to opt out); the drill-in "Draft capital" group always renders. A stated consequence: Starters + Bench deliberately no longer partition All. **OFF** ⇒ byte-identical to the shipped 1.11.0 build. **Shipped ON 2026-08-10 (v1.12.0) by operator direction** — graduated together with its `LAUNCHED_FLAG_DEFAULTS` entry in `mobile/src/state/useFeatureFlags.ts`, so the feature is visible from first paint rather than waiting on the first successful flag fetch; a server `false` still kills it on the next revalidate. Client-only — no backend behavior rides this key; `picks.value` and `pool_value` are unchanged in both states. Read ONCE and gating all fourteen expressions atomically (a partially-gated build would grow each bar while silently stretching its position segments to fill it). That graduation requirement is satisfied. |
| `rankings.cross_format_derive` | false (true in `features.json`) | **FB-191** — read-time cross-format board derivation: a member with rankings only in the OTHER scoring format gets a value-mapped (#124 math) board for reads that need this format (`/api/trade/evaluate` Mode B — the in-league calculator). Explicit rankings always win; nothing materialized; responses carry additive `*_derived` markers (the calculator's R* badge, FB-192). Off ⇒ pre-#191 consensus fallback for format-unranked members. |
| `trades.edit_full_sheet` | false (true in `features.json`) | **#257** — consolidates TradesHome's Controls Card (outlook row, trade-fairness slider, `window`/`value` lane pills, target-players block) into `TradeDnaSheet` expanded to a full-height sheet (variant C: outlook/positions/specific-players at full weight, fairness+lane demoted to a dim "Fine tuning" strip below a hairline). Client-only, `mobile/src/screens/TradesScreen.tsx` + `mobile/src/components/TradeDnaSheet.tsx`; see [docs/feedback/items/257-edit-full-sheet/status.md](feedback/items/257-edit-full-sheet/status.md). On ⇒ the Controls Card and the legacy `OutlookSheet` entry point are cut on the finder-mode landing (classic non-finder-mode home is unaffected — it has no receipt to serve as the entry point); `OutlookBiasReceipt`'s Change is the sole entry into the full sheet; player mode keeps its on-screen TRADE AWAY/TRADE FOR board. Off ⇒ `TradesScreen.tsx`/`TradeDnaSheet.tsx` render byte-identical to pre-#257. |
| `trades.intent_modes` | false (true in `features.json`) | **#172** — trade intent modes: a single-select "Consolidate / Tier up / Tier down" chip row (tap again to clear) inside the `trades.edit_full_sheet` full sheet only, its own labeled block with the primary questions, above the "Fine tuning" strip. `backend/trade_service.py`'s `generate_trades` applies the chosen `trade_intent` (`consolidate`\|`tier_up`\|`tier_down`\|null) as a POST-GENERATION filter over the already-scored deck, via `RankingService.tier_for_elo`/`ORDERED_TIERS` on each side's best (highest-tier) asset: `consolidate` = user sends more pieces than they receive AND the best incoming asset is a strictly better tier; `tier_up` = best incoming strictly better tier than best outgoing, piece counts irrelevant; `tier_down` = inverse of consolidate (user receives more pieces than they send AND the best outgoing asset is strictly better tier). `trade_intent` also gates the shared per-key job cache's freshness check (alongside `fairness_threshold`/`outlook_value`) so a changed intent always regenerates rather than serving a stale filtered deck; pinned/opponent-scoped jobs are unaffected (they already bypass that cache). A zero-candidate result is an honest empty deck — the mobile toast names the intent, reusing the existing no-fair-trades empty-state mechanism, not a new field. See [docs/feedback/items/172-trade-intents/status.md](feedback/items/172-trade-intents/status.md). Off ⇒ no chips, `trade_intent` is never read, and `/api/trades/generate` responses are byte-identical. |
| `trades.sheet_targeting` | false (true in `features.json`) | **#269** — moves specific-team targeting and a league picker INTO the `trades.edit_full_sheet` full sheet, above the primary questions, and removes `TradeFinderModeBar`'s Team and Player chips (the deck is the only Acquire-tab surface once both live in the sheet). Client-only, `mobile/src/screens/TradesScreen.tsx` + `mobile/src/components/TradeDnaSheet.tsx` + `mobile/src/components/TradeFinderModeBar.tsx`. Team targeting REUSES the pre-existing Team-mode machinery verbatim — the sheet's "Trade with" row opens the same "Pick a manager" list Modal and single-select toggle (tap the active manager again to clear) feeds the SAME `opponent_user_id` `/api/trades/generate` already reads from legacy Team mode's route params; only the source of that id moves from `route.params` to sheet-local state (`sheetOpponent`). It autosaves like the sheet's other prefs — marks the `trades.edit_full_sheet` "Preferences changed" strip via `prefsChangedSinceGenerateRef`, does not reset the deck outright. The league picker reuses the global `LeagueSwitcherSheet` component wholesale (close-sheet/open-picker/reopen-sheet, the same pattern the sheet's "Specific players" add flow already uses for `PlayerPickerModal` — iOS won't stack sibling Modals). Player mode's on-screen TRADE AWAY/TRADE FOR board and Team mode's route-param scoping code both stay in the tree, just unreachable via chips (only removed when `trades.edit_full_sheet` is also on — otherwise there'd be no sheet to move them into). See [docs/feedback/items/269-sheet-targeting/status.md](feedback/items/269-sheet-targeting/status.md). Off ⇒ `TradesScreen.tsx`, `TradeDnaSheet.tsx` and `TradeFinderModeBar.tsx` render byte-identical to today. |
| `trade.position_impact` | false (true in `features.json`) | **#169** — position-impact fold-in into the shipped `starter_impact.slots` lineup table (operator decision: build A1a's positional-rank framing, with two modifications — the tier label replaces the raw value-delta chip, and the outgoing player gets a tier label too). `backend/server.py`'s `_starter_impact()` additively prices each `slots[].before`/`after` entry with `tier` (`RankingService.tier_for_elo` over the RAW seed Elo — the identical call #277's `_evener_tier` closure already makes, reused verbatim) and `rank` (1-based positional rank within the universal pool, via `trends_service.compute_consensus_pos_ranks` with no baseline snapshot — ranks only). Both keys are gated by a single `tier_of` param bound only when the flag is on. Mobile (`mobile/src/components/InLeagueCalculator.tsx`'s `LineupImpactTable`) renders a second line under a CHANGED slot with `TierBadge` chips for both sides in place of the raw `+430`-style delta chip — the incoming player's chip sits where the delta used to, the outgoing player's chip is new — using `TierBadge`'s `posRank` slot to carry the rank movement (e.g. "4th · TE21" → "1 1st · TE4"). See [docs/feedback/items/169-position-impact/status.md](feedback/items/169-position-impact/status.md). Off ⇒ `tier_of` is never bound, `slots` carries no new keys, and the table renders the legacy numeric delta chip — byte-identical to today. |
| `trades.player_offers_calc` | false (true in `features.json`) | **#287** — single-pin find-a-trade's featured window (`FeaturedTradeWindow`, mounted from `TradesScreen.tsx` when exactly one asset is pinned) renders the pinned idea as an editable `InLeagueCalculator` instead of a read-only `TradeCard` tile — the operator's complaint: routing from a found trade to "other options for that player" landed on a tile with no add/remove/edit. Client-only, `mobile/src/components/FeaturedTradeWindow.tsx` + `mobile/src/screens/TradesScreen.tsx`. Reuses the `TradeBuildCanvas` prefill technique verbatim: `InLeagueCalculator` is remounted (keyed on the idea's `assetIdeaKey`) with `initialOpponentId`/`initialGiveIds`/`initialReceiveIds` set from the featured idea, so add/remove players, eveners, lineup impact and tier chips all work in place. The Upgrade/Lateral/Downgrade alternates list (`AssetIdeasPanel`) stays a pickable rail beneath it unchanged — picking a row swaps the calculator's prefill (remount) instead of swapping a read-only card. See [docs/feedback/items/286-player-offers-flow/status.md](feedback/items/286-player-offers-flow/status.md). Off ⇒ `FeaturedTradeWindow.tsx` renders byte-identical to today (read-only `TradeCard` + "Edit in calculator" push to `TradeCalculatorScreen`). |
| `trades_home_inline.strip` / `trades_home_inline.canvas` | absent — **not** in `config/features.json` | **#270/#272**, experiment `trades_home_inline` (layer `trades_ui`, unit `account`, targeting `is_tester_allowlist`; mirrors `aggregate_tier_labels`/`onboarding_v2_rollout`). Unlike every other row in this table, these two keys never appear as a global `config/features.json` default — they exist ONLY as a running experiment variant's `client_config.flags` overlay (`/api/feature-flags` → `configs.trades_home_inline.flags`, merged client-side by `mobile/src/api/flags.ts`), so `useFlag('trades_home_inline.strip')`/`.canvas` read false for every unit except whichever one the experiment currently assigns to that variant. `strip`: bigger (28pt) Draft/Free-agents/Manual-calc-as-button utility row (`TradeHomeUtilityRow`) + a League/"Trading with" pill strip (`TradingWithStrip`) render above the guided deck; the full `TradeDnaSheet` stays the destination for everything else, unchanged. `canvas`: same utility row + pill strip, plus a two-column hand-built trade canvas (`TradeBuildCanvas`, wraps the existing `InLeagueCalculator` wholesale) rendered ABOVE the still-intact swipe deck, fed by a suggestion rail built from the deck's own cards (tap to prefill). Both variants scoped to the guided landing only (`finderMode === 'guided'`); `canvas` additionally excludes first-run and single-pin featured mode. Client-only: `mobile/src/screens/TradesScreen.tsx` + new `mobile/src/components/{TradeHomeUtilityRow,TradingWithStrip,TradeBuildCanvas}.tsx`. See [docs/feedback/items/270-inline-trades-home/status.md](feedback/items/270-inline-trades-home/status.md). Absent from the experiment (control, or any non-allowlisted unit) ⇒ `TradesScreen.tsx` renders byte-identical to today. |

## Flags — TikTok-discovery deck engine (2026-07-26)

Registered under the `_comment_tiktok_discovery` block in `config/features.json`; source PRDs in
[docs/plans/tiktok-discovery/prds/](plans/tiktok-discovery/prds/). Built wave-by-wave, each wave's
flags flipped ON at its TestFlight ship. F8 (offline eval harness) is unflagged operator tooling.

| Flag | Default | Gates |
|---|---|---|
| `deck.signal_v2` | false | F1 impression_id logging spine: `deck_impressions`/`deck_outcomes` tables, per-card impression_id in `/api/trades/generate`, dwell/viewed capture, propensity persistence. Inert (logging only). |
| `deck.thompson_v2` | false | F2 bandit hygiene: pessimistic base-rate priors, posterior decay γ=0.995/day, viewed-only (cascade) updates, archetype×shape arms with parent warm-start. |
| `deck.fatigue` | false | F3 per-user impression discounting, decline ⇒ 30-day near-duplicate suppression (+1 retest), suppression note + undo, deck refresh (soft-layer reset). |
| `deck.session_rerank` | false | F4 client-side re-rank of remaining deck after each disposition (last-k session boost vector; peeked card/pins/wildcard never move). |
| `deck.taste_vectors` | false | F5 per-user decayed attribute-preference vectors (short τ=21d / long τ=180d) + board-derived prior, applied as a bounded multiplicative re-rank at generation (`user_taste` table, `backend/taste_service.py`; keys in the F5 model_config section below). |
| `deck.exploration` | false | F7 one labeled Wildcard slot per deck (positions 4–6), archetype audition pools, exploration propensity logging. |
| `deck.value_model` | false | F6 learned P(like)/P(propose) heads × hand-set V-vector as base ordering (`backend/value_model.py`; §F6 keys below). Gates BOTH serving and the automatic nightly refit — dark = truly inert. **Stays dark until an F8 replay win with adequate ESS (PRD gate).** |
| `deck.first_session` | false | F9 first-session win: confidence-weighted top-5 + 8–10-card clamp on a user's FIRST deck per league, the honest mid-deck adaptation moment (client), the "Built from your updated board" header on every board-refreshed deck (2026-07-26 amendment; needs `deck.signal_v2` for the previous-deck timestamp), and the `first_session_*` activation events. Off ⇒ byte-identical payloads/ordering/UI. |
| `deck.replenishment` | false | F10 deck-completion summary card + weekly post-waivers pre-generation (daily-tick hook) + 1/week preference-gated fresh-deck push. |
| `suggestion.telemetry` | false | Matchmaking item 1 (`docs/plans/matchmaking-engine/telemetry-scope.md`) — counterfactual logging on the F1 spine: stamps `policy_version` / `candidate_set_id` + `candidate_set_size` (→ new `deck_candidate_sets` table) / `assets_json` on telemetry-era `deck_impressions`; the **ghost-suggestion holdout** (~1-in-`ghost_holdout_one_in` organic deck cards per league × ISO week deterministically withheld from display, logged with `is_ghost=1`, requires `deck.signal_v2` ON to withhold at all); the **executed-trade matcher** after each `market.trade_capture` sync (→ `suggestion_trade_links.was_recommended` + ghost incrementality columns); and `GET /api/admin/suggestion-telemetry/ratio`. Off ⇒ zero withholding, zero new column stamping, zero candidate-set/link writes, byte-identical serving; the ratio route 404s. Keys in the §suggestion.telemetry section below. |

## Flags — Rookie draft + Draft Room (2026-08-06)

Registered under the `_comment_rookie_draft` block in `config/features.json`; plan/HLD/LLD in
[docs/plans/rookie-draft/](plans/rookie-draft/). All flags land OFF and flip at each milestone's
release gate. M0 (the player-cache refresh) is deliberately **not** flag-gated — its lever is the
`FTF_PLAYERS_REFRESH` env var above.

| Flag | Default | Gates |
|---|---|---|
| `ranks.rookie_subset` | false | M2 rookie scope: `?scope=rookie` on `/api/rankings` + `/api/trio`, and `scope`/`via:"rookie_*"` in the `POST /api/tiers/save` body. A **post-Elo view filter** over the ONE existing board — a rookie's Elo is identical scoped or unscoped, and a scoped tier save uses the merged-band rule (persist the scoped pids only, at exactly the values a full-band save would give them; see [ADR-009](adr/adr-009-rookie-scope-view-filter.md)). **Off ⇒ the `scope` parameter is never read** — not parsed, not validated, not logged — so flag-on and flag-off responses are byte-identical on held-constant data. Precondition for flipping it: the pre-scope snapshot + restore procedure ([runbook § Rookie-scope board restore](runbook.md)) is live. |
| `draft.room` | false | M3/M4 Draft Room. Gates `GET /api/draft/board` ([api-reference § Draft room](api-reference.md#draft-room-flag-draftroom)) **and** the mobile entry point: ON ⇒ the League tab's third Explore tile is "Rookie draft" and pushes the `DraftRoom` screen; OFF ⇒ it is today's "Rookie board" tile (`league.rookie_board_entry`), so flipping the flag off never strands a user with nothing. **Off ⇒ the route 404s `feature_disabled` before any session or league work.** |
| `picks.slot_values` | false | M6 per-slot draft-pick market prices on the Draft Room board — `order[].slot_value`, in seed-Elo space, read from DynastyProcess's `values.csv` PICK rows via `data_loader.load_pick_slot_values` (test seam `FTF_DP_PICK_VALUES_FILE` above). **A display axis only**: `GENERIC_PICK_SEEDS`, the tier ladder, the tier bands and the trade engine do not read it (engine adoption is the separate M6b repricing wave, plan O2 — see [cross-client-invariants § Draft-pick slot values](cross-client-invariants.md)). Non-12-team leagues get a within-round percentile map and the payload carries `slot_value_approx: true`; a 12-team league is exact and carries no marker. **Off ⇒ the `slot_value` key is omitted entirely** (never null) and `values.csv` is never fetched; a fetch failure with the flag on degrades identically. |
| `trade.slot_pricing` | false | **M6b** — DynastyProcess market slot values IN THE TRADE ENGINE (operator decision O2, which reverses hld KD-9 / lld §4.7). Gates the per-user `users.pick_pricing_mode` setting (`tier_ladder` **default** = today's behaviour | `market_slots`) and the `GET/PUT /api/settings/pick-pricing` route. Under `market_slots` an OWNED pick prices at `pick_values.market_pick_pool_value(season, round, scoring_format)` instead of the stored ladder `pool_value`, resolved at READ time in `server._owned_pick_assets` and `/api/trade/evaluate`. `GENERIC_PICK_SEEDS`, the tier ladder and the tier bands are byte-unchanged in BOTH modes, and `draft_picks.pool_value` (league-shared) is never rewritten. **Off ⇒ `pick_pricing_mode_for_user` returns `tier_ladder` for every user without a DB read, the settings route 404s, and pricing is byte-identical to today.** |
| `draft.live_poll` | false | M4 live polling — the Draft Room refetching **our own** `/api/draft/board` every 15 s. Three gates, all required: the flag, the screen being focused, and the app being foregrounded; polling additionally stops unless the board's own `state == "live"`. **Blurred or backgrounded is ZERO requests** (the QA pass threshold is literally zero). The manual **Refresh** control is present flag-on or flag-off, so the room is fully usable dark. Flip gate: the throwaway-league live test (plan O7) — a release gate, not a build gate. |
| `draft.mfl` | false | M5 MFL parity. Gates the **MFL binding** inside `GET /api/draft/board` — the renderer itself already ships and is fixture-tested. ON ⇒ an MFL league's board is built from `TYPE=draftResults` ([api-reference § MFL league linking](api-reference.md#mfl-league-linking)), whose pre-populated grid carries a franchise on **every** pick, made or not, so MFL's pre-draft ownership is strictly better than Sleeper's (D8); an expired MFL cookie serves the stored snapshot with `notice.mfl_reconnect` + `stale:true`, **never stale-as-live**. **Off ⇒ an MFL league gets the byte-identical `platform_unsupported` payload M3 shipped and ZERO MFL reads are attempted** — no league-row lookup, no crosswalk load, no export call. Sleeper responses are unchanged either way (D10). **Live mode is release-gated separately:** a drafting MFL league reports `state:"live"` honestly, but MFL's mid-draft update latency is UNVERIFIED — recurring refresh stays behind `draft.live_poll` until the timed probe in [build-m5](plans/rookie-draft/build-m5.md#the-live-probe) passes. Flipping `draft.mfl` on starts no poll. |
| `draft.rank_inline` | false | **draft-extensions W1** — per-player ACTIONS on the Draft Room's undrafted rows ([plan §4](plans/draft-extensions/plan.md), [lld §4.1](plans/draft-extensions/lld.md)). ON ⇒ a **long-press** plus an `accessibilityActions` custom action (the shipped `TradeCard` vocabulary — there is no visible overflow glyph anywhere in `mobile/src/`, and adding one would need a `docs/design/components.md` spec under ADR-004/005) opens the shared `PlayerContextMenu`: **Set my value** → the new `AnchorSheet` on the shipped `POST /api/anchor/save` lane (carrying `via:'draft_room'`), **Rank the rookies** (the existing bridge, now two-way via a return route), **Add to targets** (the shipped asset-pref write); the coverage nudge ("N of the top 25 have no value on your board") renders too. **HARD CONSTRAINT — the anchor lane ONLY:** nothing this flag opens may reach `save_tiers_position` or the merged-band path, pinned by AST + runtime + source tests in `backend/tests/test_draft_extensions_w1.py`. **Off ⇒ undrafted rows are the inert `View`s they are today** — no long-press handler, no a11y action, no menu, no sheet, no nudge. The per-player testIDs (`draft-room.undrafted-row.<pid>`, `.order-row.<round>-<slot>`, `.pick-row.<pick_no>`) and the four new client analytics events ship **unflagged**: the ids are inert and are what makes the flag testable at all, and the events are what makes the surface measurable (the room shipped with zero `track()` calls). |

## Flags — Draft-surface extensions (2026-08-06)

Registered under the `_comment_draft_extensions` block in `config/features.json`; plan/HLD/LLD in
[docs/plans/draft-extensions/](plans/draft-extensions/).

| Flag | Default | Gates |
|---|---|---|
| `draft.mock` | **true** | **W2** — the FTF-native mock draft: all four `/api/mock-draft` routes ([api-reference § Mock draft](api-reference.md#mock-draft-flag-draftmock)) and the mobile mock surface. Effective gating is `draft.room` **AND** `draft.mock`; it is independent of `draft.live_poll` (the mock never polls), `draft.mfl` and `picks.slot_values`. **Off ⇒ every mock route 404s `feature_disabled` before any session work, the `mock_drafts` table is never touched, and no other route's response changes.** ⚠️ **Shipped ON 2026-08-08 (`6caca35`) by operator override, not by the gate passing.** W2's calibration gate FAILED and has stayed failed through three re-runs ([mock-calibration-2026-08d.md](plans/draft-extensions/mock-calibration-2026-08d.md)) — the specified noise model cannot reproduce the reach distribution of a real rookie draft at any value in the specified grid, on the hold-out or on an independent corpus. The operator then specified CPU reach behaviour directly as a product rule (W2e round-tiered caps) and declined further validation, so `mock_draft_service.CPU_MODEL_VALIDATED` is `True` **while the recorded statistical verdict remains FAILED**. `test_w2_16_calibration_gate` asserts that verdict independently, so a change that makes the model pass turns the suite red and forces a deliberate artifact re-publish — that is the intended tripwire, not a bug. Revert by setting `CPU_MODEL_VALIDATED` back to `False`; nothing else needs to change. **2026-08-10 (#290):** the pick model is now value-aware — candidates are truncated at a locally-significant value gap and composed with the W2e round cap via `min()`, so the rule can only tighten it. |
| `picks.assign` | false | **draft-extensions W3 M-A/M-B** — user-asserted pick **ownership** ([plan §6 REVISED](plans/draft-extensions/plan.md), [ADR-010](adr/adr-010-user-asserted-pick-ownership.md), delivered contract in [build-w3-ma-mb.md](plans/draft-extensions/build-w3-ma-mb.md)). Gates the three assignment routes (`GET`/`PUT /api/league/pick-assignments`, `POST …/order`) **and** the ESPN branch of `GET /api/draft/board`, and (#328) the ESPN branch of the mock-draft create's `_mock_real_draft` resolution — the same gate as the board route, so the mock and the ESPN Draft Room can never disagree; OFF ⇒ an ESPN mock falls back to slot order, labeled `ownership_source: "none"`. **Why it exists:** ESPN has no rookie-draft concept (operator ruling), so an ESPN dynasty league's rookie draft necessarily runs off-platform and there is **no draft object to read, now or ever** — the league's own members are the only possible source of who owns which pick. **ON ⇒** the routes answer, and an ESPN board is either `notice.picks_not_assigned` on an `unavailable` payload (nothing assigned) or a real `upcoming` board built entirely from the grid with `picks: []` and **zero platform egress**. **OFF ⇒** all three routes 404 `feature_disabled` before any session work, the ESPN board is the byte-identical `platform_unsupported` payload it is today, the three new `draft_picks` provenance columns stay unwritten, and every existing read site is unchanged because `load_draft_picks` **defaults to `source='platform'`** (NULL reads as platform, so no backfill runs) — that default IS the containment. **No user-entered values, ever:** price comes only from the shipped `pick_pool_value`/`compute_pick_value` and every route 400s `values_not_accepted` on any value field, which is what buys the conservation bound (`rounds` clamped 1..`ROOKIE_MAX_ROUNDS` server-side). Asserted picks do **not** enter trade math under this flag — that is the separate `picks.assign_tradeable` kill switch (M-C, **not yet built**), deliberately two flags so pick math can be killed without destroying the rows a league typed in. Ship-by/kill-by: review 2026-11-08. |
| `picks.assign_tradeable` | false | **draft-extensions W3 M-C** — **trade-math activation** for asserted picks ([plan §6.4 + operator decision 4](plans/draft-extensions/plan.md), [ADR-010](adr/adr-010-user-asserted-pick-ownership.md), delivered contract in [build-w3-mc.md](plans/draft-extensions/build-w3-mc.md)). The **second, deliberately separate** switch: `picks.assign` owns entry, storage and the ESPN Draft Room; this one owns whether those rows **price**. Killing it never destroys the rows a league typed in. **ON ⇒** all SEVEN read sites read the platform ∪ asserted union instead of `load_draft_picks`' platform-only default — S1 `/api/league/picks` + `/api/trade/evaluate`, S2 `_power_picks_by_owner` + `_user_pick_share`, S3 `_owned_pick_assets`/`_inject_owned_picks` + the trade job's opponent pick shares, S4 `_roster_eveners` — so assigned picks behave **exactly like any other league's picks**, including generated suggestions and one-tap eveners (operator decision 4 overrides both lenses' recommendation to hold S3/S4; S1→S4 survives as a BUILD SEQUENCE, not release gates). It also flips the engine guard `_owned_picks_available` from a platform test to a data test for ESPN (all three of its conjuncts — `trade.picks_in_pool`, not-demo, platform — are preserved), makes `picks_supported` a data test (`platform != "espn" or the league has assigned rows`), and puts `source: "platform" | "user"` + `season` on every priced pick payload (the label **"Member-entered — not verified with ESPN"** and the `{leagueId, season, focusPickId}` correction link are registered in [cross-client-invariants.md](cross-client-invariants.md)). **OFF (default) ⇒** every one of those payloads is byte-identical and asserted rows reach no trade math, no power rankings and no suggestion. In BOTH states contested/orphaned slots leave the priced union by **row filter**, never by nulling `pool_value`. The §6.8 adoption / contested-rate thresholds are monitoring and rollback triggers, not ship gates. Ship-by/kill-by: review 2026-11-08. |
| `draft.manual_picks` | false | **draft-extensions W3 M-D** — **live offline pick recording** ([plan §6.5](plans/draft-extensions/plan.md), [ADR-010](adr/adr-010-user-asserted-pick-ownership.md), delivered contract in [build-w3-md.md](plans/draft-extensions/build-w3-md.md)). The **third, separate** switch: `picks.assign` owns ownership entry/storage/the room, `picks.assign_tradeable` owns whether asserted rows price, this one owns whether the app can record **what happened** during a real off-platform draft. Storage is the new `recorded_picks` table ([data-dictionary](data-dictionary.md#recorded_picks)) — never `draft_picks`, never `leagues.draft_status*`. **ON ⇒** `POST /api/league/recorded-picks` (batch, idempotent on `(league_id, season, overall)`) and its `/void` companion answer, and `GET /api/draft/board`'s ESPN branch projects live `recorded_picks` rows into `picks[]` (subtracting them from `undrafted[]`) through the SAME renderer every other platform's board uses. **OFF (default) ⇒** both routes 404 `feature_disabled` before any session work, `recorded_picks` stays unwritten, and the ESPN board reads **zero rows** from it regardless of what the table holds — the flag gates the read as well as the writes, so a row left over from a prior on/off flip can never leak into a flag-off board. Off-by-one recovery is **manual-cursor-only, no auto-shift**: a missed pick is fixed by tapping the correct slot directly, never by an "insert here and shift everything after" operation. Ship-by/kill-by: review 2026-11-08. |
| `draft.tab` | false (**ships TRUE**) | **The seasonal on/off switch for mobile's Draft tab** (operator decision 2026-08-06: *"it should literally just be set to seasonal. So a flag we turn on and off to display the tab. Right now it should be on for all."*). **The operator flips this by hand each year — it is never computed.** Client-only: no backend route reads it. **ON ⇒** the bottom bar carries the Draft tab (third: **Rank · Acquire · Draft · Matches · League**, testID `tab.draft`) and it lands on the **active league's** Draft Room. **OFF ⇒** four tabs. `DraftRoom` is reachable either way through the root stack (the League tile, the Acquire mode strip's Draft chip) and the canonical deep link `app/league/draft-room`. This **replaces** the per-league qualification predicate the tab shipped with (`draft_status == 'not_drafted' && draft_status_confidence == 'high'` over an AsyncStorage snapshot that only converged on the NEXT launch — it hid the tab from operators whose leagues genuinely qualified, on the first run after a storage-key bump). There is no chooser: with the tab always on there is nothing to choose between, and the Draft Room renders every state honestly (drafted ⇒ recap, not-drafted ⇒ upcoming, ESPN ⇒ unsupported, no league ⇒ its no-league state), so a non-drafting league lands somewhere truthful rather than somewhere empty. Read **imperatively** at TabNav's first mount (`useFeatureFlags.getState()`, never `useFlag`) so a mid-session flag revalidation cannot rewrite the navigator's route array; a flip therefore takes effect on the next launch. |

#### Ship-by / kill-by review convention (07/prd-04)

Dark flags are inventory, not archive. **Every flag dark ≥90 days gets a recorded decision at a quarterly flag review: schedule a canary via the experiments engine, or delete the code path.** "Still thinking" is not a decision — the review's exit criterion is zero flags >90 days old without one. Record the decision as a one-line ship-by/kill-by note in the flag's `features.json` comment block (or the table above). The teardown block's clock starts 2026-07-19.

## Flags — QA / testing surfaces

| Flag | Default | Gates |
|---|---|---|
| `testing.stage_users` | false | Synthetic `qa_*` stage-user spawner for onboarding QA (`backend/test_users.py`). Runtime-flagged kin of `FTF_TEST_MODE` so the operator's phone can hit a prod-shaped build. **The flag and the allowlist govern two different halves — read the next paragraph before reasoning about this one.** See [api-reference.md → Test users (QA)](api-reference.md). |

**Server access is allowlist-only; the flag gates the client row.** `_test_users_denied()` (`backend/server.py:20067`, the gate on both `POST /api/test-users` and `DELETE /api/test-users/<user_id>`) checks **only** the tester allowlist — `experiments.load_tester_allowlist()`, i.e. `FTF_TESTER_ALLOWLIST` env ∪ `config/tester_allowlist.json` — against the caller's `device:<X-Device-Id>` or session `user_id`, and 404s everyone else (no existence signal). Its docstring states the flag "is deliberately NOT consulted here": it gates only the client Settings row, and ships per-device through the experiment overlay so the global flag can stay dark (operator direction 2026-07-19).

Two consequences a reader must not get wrong:

- **Turning the flag off does NOT close the server-side surface.** An allowlisted device can still spawn and delete `qa_*` users with the flag false. The allowlist is the only thing standing between these routes and the public.
- **Turning the flag on does not expose the routes to real users.** A non-allowlisted caller gets 404 regardless of flag state.

To actually close the surface, remove the entry from the allowlist (`config/tester_allowlist.json` / `FTF_TESTER_ALLOWLIST`) — not the flag.

---

## Flags — Decline-reason capture (2026-08-17, ships **ON**)

Spec: `docs/plans/decline-reason-capture/SPEC.md`. The trade card's ✕ is replaced by three layer-1 tiles — **Value · Fit · Neither** — and tapping one *is* the pass: one gesture commits the disposition and the reason together.

| Flag | Default | Gates |
|---|---|---|
| `feedback.decline_reasons` | **true** in `config/features.json` (registered default false) | `POST /api/trades/pass-reason` (`backend/server.py`) and the `trade_pass_reasons` table it upserts. **Flag-only** — checked before any session work, with ordinary write auth (`@_gate_unverified_write` + an initialized session) behind it. **This key is the kill switch:** OFF ⇒ the route 404s `feature_disabled`, no `trade_pass_reasons` row is ever written, and `/api/trades/swipe` is **untouched by this feature** (nothing in the shipped ✓/✕ path reads this flag), so the disposition behaves byte-identically to today. Flipping it is a config edit plus `POST /api/feature-flags/reload` — no deploy. Pinned by `test_decline_reasons.py::test_flag_off_*`. |

**Scope: ALL users.** SPEC §5 proposed tester-allowlist scoping; the operator superseded that on 2026-08-17 and this ships to everyone. There is deliberately **no allowlist half anywhere in the feature** — not on the route, not on the served flag map — which is precisely what makes this key a true one-line revert: there is no second condition to reason about, and `GET /api/feature-flags` serves the same value to every caller, so the client surface and the route can never disagree about whether the feature is on.

**Rollback.** Flip to `false` and reload. The `trade_pass_reasons` rows already written are retained (they are the diagnostic's whole output); nothing reads them on any user-facing path.

**Elo consequence** rides a **separate** knob, not this flag — see [`pass_reason_elo_suppression`](#decline-reason-elo-suppression-ranking_service_default_cfg). That separation is deliberate: the ranking-math change can be reverted without taking the capture down with it, and vice versa.

---

## Flags — API observability (2026-08-09, ships **ON**)

| Flag | Default | Gates |
|---|---|---|
| `obs.api_events` | **true** in `config/features.json` (registered default false) | `backend/api_observability.py` — inbound + outbound API event capture into `user_events` as server-fired `api_call`/`api_request` rows (taxonomy: `OBS_EVENT_PROPS` in `backend/analytics_taxonomy.py`; query surface: `GET /api/admin/analytics/apihealth`). Outbound: every external egress chokepoint (Sleeper REST + GraphQL incl. the trade-block/trade-capture bypass sites, ESPN, MFL, Fleaflicker, DynastyProcess CSVs, KTC scrape, Anthropic, Expo push, Apple/Google sign-in verification). Inbound: Flask hooks recording route PATTERN/method/status/latency for `/api/*` (static assets and `/api/events` excluded). Volume policy: errors always, successes 1-in-N (`obs_success_sample_n`); retention `FTF_OBS_RETENTION_DAYS` (30 d). This key is the **kill switch**: OFF ⇒ zero event writes, zero overhead beyond a flag check, byte-identical responses. Per-service redaction rules in `docs/integrations/` are enforced structurally (key denylist + value-shape scrub + prop-spec strip). |

---

## Flags — P0 remediation (2026-08-11 mobile UX audit; [plans](plans/audit-p0-remediation/))

| Flag | Default | Gates |
|---|---|---|
| `growth.invite_join_link` | **false** | **Emitter only.** ON: `mobile/src/utils/deepLinks.ts` `buildInviteUrl` emits `/app/league/join/<league_id>?ref=<username>`. OFF (default): today's `/?league=<id>&ref=<username>`. **It never gates the reader, the route, or the claim** — the `?league=` parser, the `LeagueJoin` mobile route, the server 302 at `GET /app/league/join/<id>` and the AASA `/app/league/join/*` claim are all **unflagged** and ship ahead of it. **Why the ordering is inverted from the usual pattern:** Apple caches `/.well-known/apple-app-site-association` on its own CDN for up to ~24 h, so a build that emitted the new URL before the claim propagated would open every invite in Safari — strictly worse than the legacy URL. Parsers-first also means links shared *before* this build keep working forever. **Graduation criteria (all three):** (1) the live AASA validates externally and lists `/app/league/join/*`, (2) ≥24 h of CDN propagation has elapsed since that deploy, (3) a TestFlight build installed *after* that deploy demonstrably opens the app on a tapped `/app/league/join/…` link. Procedure: [runbook § Universal Links AASA](runbook.md#universal-links-aasa-is-cdn-cached-by-apple-feedback-239-2026-08-02). **Rollback = flip back to false**; the legacy URL is parsed forever by both clients, so nothing already in the wild breaks. `buildInviteUrl` reads the flag **imperatively** (`useFeatureFlags.getState()`) so multiple call sites cannot drift. |

**No other P0 finding added a flag.** P0-1, P0-2, P0-5, P0-6, P0-7 and P0-8/9 ship unflagged by design — for P0-1 and P0-2 a flag's OFF position would be the known bug, which is not a rollback lever worth shipping. Rollback for those is `git revert` of the named commit; the levers are enumerated per finding in each PRD's *Rollback* section.

---

## Analytics events — Guided Onboarding v2 addendum (2026-08-15)

Registered in `backend/analytics_taxonomy.py` ([scope](plans/guided-onboarding-v2/scope.md) §1; event-state verdicts in [DELTA-2026-08-15.md](plans/guided-onboarding-v2/DELTA-2026-08-15.md) §E). **Rows ship before emitters** (FR-E8): `ALLOWED_CLIENT_EVENTS` is default-deny *behind a 200* — an unregistered name is counted-and-dropped, and a registered name carrying an unregistered prop lands hollowed out. Both failures are silent, and both have happened here before (`invite_shared`, `deck_regenerated`, the NULL-`platform` incident).

Props are a **key allowlist** — the registry does not validate values, so the value unions below are the contract for emitter authors, not something the server enforces. All six are **mobile-only**; the guide is not a web or extension surface. Round-tripped by `backend/tests/test_events_api.py::test_guided_onboarding_v2_*`.

| Event | Props | Fires when |
|---|---|---|
| `guide_step_suppressed` | `step`, `blocked_by ∈ slot_busy \| ineligible \| matched \| already_seen` | `requestStep` refuses — once per deferral episode, not per retry. FR-E5: the drop is silent today (`useGuide.ts:94`), so suppression is currently unmeasurable. |
| `guide_step_shown` *(existing — allowlist **extended**)* | `step`, `pose`, `screen`, **`spotlight ∈ measured \| degraded \| none`** | Unchanged emit site. FR-E6: `AnalystGuide` renders the same line whether the cutout resolved or not, so without `spotlight` a deictic beat pointing at nothing looks identical to one that landed (`s7.1` is the live exhibit). |
| `outlook_saved` | `source ∈ guide \| sheet \| strip` | First preference write in a `TradeDnaSheet` session. |
| `finder_target_pinned` | `side ∈ give \| receive`, `source` | Targeting-board pin recorded. |
| `quickset_started` | `position ∈ QB \| RB \| WR \| TE`, `source` | `QuickSetTiers` mounted with intent (guide hand-off vs. organic). The client-observable **intent** half — `quickset_completed` is server-fired and can never be a client receipt. |
| `awaiting_segment_viewed` | `source ∈ guide \| tab \| push` | Matches "Awaiting them" segment focused. |
| `trio_session_started` *(already registered)* | *(none)* | Already landed in the 2026-08-13 dropped-emitter sweep. Its emitter (`mobile/src/screens/RankScreen.tsx:92`) sends **no props**, so the empty allowlist is the correct shape — do not "fill it in". |

**Deliberate absences.** `trade_sent` and the MFL/ESPN send-attempt rows are PRD **Phase 2** and are not registered — a name registered ahead of its emitter makes an unfired row read as a measured zero. A client `quickset_completed` must **never** be added: the server-fired name already exists, and a collision trips the import-time disjointness assert in `analytics_taxonomy.py`, taking the app down at boot.

**Intent classification (open).** `guide_step_suppressed` (a system suppression, no user action) and `awaiting_segment_viewed` (an impression) are non-intent class and belong in `analytics_queries.NON_INTENT_EVENTS` **before their emitters ship** — `INTENT_EVENTS` is derived by subtraction, so taxonomy growth is intent-by-default and admitting them would step-change DAU/WAU permanently at the emitter's ship date. The other three are real user decisions and stay intent.

---

## `model_config` keys

Two layers, both read through `trade_service._cfg` at runtime:

1. **DB-seeded keys** — `_MODEL_CONFIG_DEFAULTS` in `backend/database.py` seeds the `model_config` table (INSERT OR IGNORE on startup). Tunable live via `PUT /api/admin/config/<key>`.
2. **Code-default keys** — the trade-engine v2/Tier-2 keys below are declared only in `trade_service._DEFAULT_CFG` (and `fuzzy_match_tau` inline in `server._fuzzy_match_tau`). They are **not yet seeded into the `model_config` table**, and `database.set_config` rejects unknown keys — so until they're added to `_MODEL_CONFIG_DEFAULTS`, the admin API cannot tune them and the code defaults below are what runs.

Legacy keys (Elo K-factors, KTC curve, package weights, outlook multipliers, tier multipliers, trade-math taxes, tier-engine knobs) are documented in [glossary.md](glossary.md) and listed by `GET /api/admin/config`.

### Analytics platform (P0, [ADR-007](adr/adr-007-first-party-analytics-experimentation.md))

| Key | Default | Meaning |
|---|---|---|
| `analytics.wrapped_cutover_at` | *(stamped at first P0 boot)* | **Not a tunable** — the epoch-seconds instant of the `wrapped_events` → `user_events` writer cutover (LLD §6.4). Seeded once by `_migrate_db()` (INSERT-or-ignore; `model_config.value` is Float, hence epoch seconds rather than ISO text — `database.get_wrapped_cutover_iso()` converts). `load_league_activity()` splits its union read on it. Never edit after deploy: moving it double-counts or hides narrative rows. |
| `obs_success_sample_n` | 10 | API observability (flag `obs.api_events`, `backend/api_observability.py`): record **1-in-N successful** `api_call`/`api_request` events (deterministic per-endpoint counter; each sampled row carries `props.sample_n` so call volumes rescale honestly). **Errors are always recorded** regardless of N. `1` = record every call (full firehose — debugging only). Cached 60 s; tune live via `PUT /api/admin/config/obs_success_sample_n`. |

### Trios → tier calibration + variety — `ranking_service._DEFAULT_CFG`, DB-seeded

The trio loop rotates among three strategies (never repeating the previous one), then anti-repeat suppresses recently-seen players so the same faces don't recur. Since FB #97 the selectors also randomise *which* eligible straddlers/extremes get served (within-tier top/bottom drawn from the top/bottom two; boundary candidate/opponent from the top-two eligibles) and the within-tier cursor starts at a random tier on each service rebuild — so a fresh session no longer always opens on the elite tier's same top players.

| Key | Default | Meaning |
|---|---|---|
| `trio_boundary_rate` | 0.4 | Share of trios that **probe a value-band boundary** — a player just below a tier edge vs one just above, drawn from the FULL pool. The only comparison that moves a player across a tier. **0 = never boundary.** |
| `trio_within_tier_rate` | 0.35 | Share of trios that compare **top-vs-bottom of the SAME tier** (rotating through tiers via a cursor) to nail intra-tier order. The remainder after `boundary + within` (+ `cross_pos` post-unlock) is the legacy **tightest** near-equal ordering. Set both rates to `0` for pure-legacy behaviour. |
| `trio_cross_pos_rate` | 0.15 | #132 — share of trios that compare **same-tier players from DIFFERENT positions** (own separate tier cursor). Only served once the user's four positional interaction thresholds are all met (the trio-method trade-finder unlock); pre-unlock the lane is off regardless of this knob. Its share comes out of the tightest remainder. **0 = off.** |
| `trio_boundary_margin` | 60.0 | Elo window on each side of a tier edge to pull boundary straddlers from. |
| `trio_repeat_avoid` | 8.0 | Don't reuse a player seen in the last **N** served trios (fixes "same 2 players trio after trio"). Relaxes gracefully when a pool/tier is too small to honour it — the longest-unseen players are re-admitted first, never the whole avoid set at once. Default raised 3 → 8 (FB #97) to match the live prod tune; 3 was too short to keep the top value cluster from recurring. |

> Backend-only and **behavioural for all users** once deployed (changes which trio the Rank screen serves; Elo/value math is unchanged). Fully revertible live via `PUT /api/admin/config`. See [trios-tier-calibration-plan-2026-07-08.md](plans/trios-tier-calibration-plan-2026-07-08.md).

### Decline-reason Elo suppression — `ranking_service._DEFAULT_CFG`

| Key | Default | Meaning |
|---|---|---|
| `pass_reason_elo_suppression` | 1.0 (**ON**) | Decline-reason capture (flag `feedback.decline_reasons`, SPEC §4). Today every pass fires `record_trade_signal(winner=give, loser=receive)` — it asserts *"I value my players more than theirs"*. Once the tester says **why** they passed, that assertion holds for exactly one answer. **ON (≥0.5):** only `value_giving` ("Giving up too much") writes the pass's Elo signal. `value_getting` says the *opposite*, so writing the usual signal would invert it; every `fit_*`, every `other*` and every layer-1-only answer makes no valuation claim at all — all suppressed. Because layer-1-only always suppresses, a kept signal lands at the **layer-2 tap**, not the tile tap, and `trade_pass_reasons.elo_signal_at` makes it once-only per impression. **OFF (<0.5):** every reasoned pass writes Elo at the tile tap, exactly as today's ✕ does — the deploy-free rollback lever for the one part of this feature that touches ranking math. Read **only** on the reasoned-pass path: `/api/trades/swipe` never consults it, so unreasoned passes are unaffected in either position. Not currently in `_MODEL_CONFIG_DEFAULTS`, so it is a code default until seeded. |

> Known one-way behavior, recorded rather than fixed: an Elo signal earned by `value_giving` is **not retracted** if the tester later switches tiles — there is no negative-K correction path on this route (that machinery exists only for match dispositions, `trade_k_decline_correction`). It can never write a second time. See [data-dictionary § trade_pass_reasons](data-dictionary.md#trade_pass_reasons).

### Board-override pins — `ranking_service._DEFAULT_CFG`, DB-seeded

A tier save, Quick Rank pass, drag reorder, pick-anchor or cross-format copy
writes an Elo **override** into `users.tier_overrides`, which *pins* that
player: `_compute_elo` seeds them from the override. Originally it then skipped
every rating update, so the pin was a **freeze**; since `pin_tier_bounded`
(2026-08-18) the pin instead names the **tier** the player may move inside.
[The 2026-08-18 valuation audit](reviews/2026-08-18-valuation-age-audit.md)
found the pin composing badly with the trade layer's confidence shrinkage —
`_shrink_user_elo` weights personal Elo by `w = n/(n + shrink_pseudocount)`
where `n` is the **comparison count**, with no reference to which way the user
voted. A pinned player's Elo cannot move, so every additional comparison only
raised `w` and dragged the effective trade value further toward the pin. On the
audited board the pin sat *above* consensus, so **17 down-votes raised the
player's trade value 12.5%** — voting him down made the engine want him more.
Scale at the time of the audit: **67.8% of all 4,013 recorded comparisons had
both players pinned**, making the Elo update a no-op on both sides.

**Tier-bounded voting replaced the freeze on 2026-08-18** (operator design
call, [D-076](../living-memory/DECISIONS.md)): *"for deliberately placed
players in tiers, the voting can just rerank a player within his current set
tier. So some adjustment is expected, but nothing massive across a tier."* A
pin is now a permanent **band constraint**, not a frozen value and not
something a later swipe expires. That change **supersedes F2** — both F2 knobs
are kept and still functional, but default OFF.

Revert paths, both live via `PUT /api/admin/config`, no deploy:

| Want | Set |
|---|---|
| Phase 0 (freeze + release-on-newer-swipe) | `pin_tier_bounded=0`, `pin_unpin_on_newer_swipe=1` — byte-identical to `origin/main`, golden `backend/tests/fixtures/pin_tier_bounded_golden.json` |
| Pre-2026-08-18 (a pin freezes, and its votes still build confidence) | all four knobs `0` — golden `backend/tests/fixtures/override_pin_golden.json` |

Both goldens were **captured** by running the tests' own fixtures against the
pristine prior tree, and each carries a guard test asserting the golden still
exhibits the behaviour it is supposed to record, so the proof cannot rot.

| Key | Default | Meaning |
|---|---|---|
| `pin_tier_bounded` | 1.0 (**ON**) | **Tier-bounded voting.** The pinned Elo is read as a **tier label** (`RankingService.tier_for_elo`) and every subsequent rating update is clamped to that tier's band (`tier_bands_for` → `backend/tier_config.json`). Bands are 165–205 Elo wide, so a player genuinely re-ranks inside his tier while never crossing one. **Nothing is written anywhere** — the band is derived at Elo-compute time from the pinned value the board already stores — so all **2,735** pre-existing pins are covered with no migration, no backfill and no opt-in. Two populations stay frozen on purpose: a pin **below the lowest band** (`tier_for_elo → None`; that is `DEMOTED_ELO`/`ANCHOR_NO_VALUE_ELO` = 1100, the "unranked, pending placement" markers) has no tier to move inside, and a pin F2 has *released* is gone altogether so nothing clamps it. A pin sitting in a **gap** between two bands (e.g. 1576–1579) or **above the top band's max** widens its own clamp to `min(lo, pin)`/`max(hi, pin)`, so the clamp can never move a player who has not been voted on. Measured on prod at ship: effective comparisons **1,292 → 3,938 of 4,013 (32.2% → 98.1%)**, and **667 of 2,735 pins (24.4%)** actually move. **`0` restores the total freeze.** |
| `pin_exclude_comparisons` | 1.0 (**ON**) | **F1, narrowed by tier-bounding.** `RankingService.comparison_counts()` counts only the comparisons that actually **moved** a player's Elo. Under the freeze that excluded *every* vote on a pinned player (`n = 0`, priced at exactly the consensus seed). Under tier-bounding an in-band vote really does move him, so it counts as evidence again, and the exclusion narrows to the genuinely inert residue: a player **clamped at a band edge** with the vote still pushing him further out, and a **pin with no band**. Keeping the rule in this narrowed form rather than reverting it is what makes the value truer — a vote the tier floor swallowed would otherwise raise confidence in a number the user was trying to lower, which is the audited inversion one tier down. The map is shared by both consumers: `_shrink_user_elo` (value blending) **and** `_value_uncertainty` (`range_base/sqrt(1+n)`, the range-overlap fairness gate); confidence earned from updates that changed nothing is false precision. **`0` disables**, restoring raw counts for both consumers. |
| `pin_unpin_on_newer_swipe` | 0.0 (**OFF** — superseded) | **F2, superseded by `pin_tier_bounded`.** Shipped ON for a few hours on 2026-08-18 and then defaulted OFF: full release is no longer the model, because a pin is a durable band constraint rather than something that expires on the next swipe. Kept and still functional as the revert path to Phase 0. When it is `1`, a ranking swipe recorded **strictly after** the pin releases that player — the pin stays as his *starting* rating and only swipes newer than it apply on top — and a released player then evolves **unclamped**, because release means the pin is gone. Tier-bounding only governs pins still in force. Only **ranking** swipes trigger a release; once released, newer trade swipes do apply. Requires a stored write time; see `pin_legacy_at_epoch`. |
| `pin_legacy_at_epoch` | 0.0 (**OFF** — superseded) | **F2 legacy policy, superseded.** Only qualifies F2, and F2 is now off, so this knob is **inert** unless `pin_unpin_on_newer_swipe` is turned back on. It exists because overrides written before 2026-08-18 carry **no timestamp** (`users.tier_overrides.__override_at__` did not exist): `0` treats such a pin as permanent, `1` treats it as written at the epoch so any recorded swipe releases it. It was the lever for unfreezing the **739 of 2,735** legacy pins that had ever been voted on — a question tier-bounding now answers without any operator decision, since the band is computed from the pin itself. The timestamp **backfill** proposal in [scope-phase0.md](plans/three-model-bakeoff/scope-phase0.md) §6 is likewise moot; it is left recorded, not withdrawn. |

### Forced deck regeneration — `backend/server.py`, DB-seeded

| Key | Default | Meaning |
|---|---|---|
| `force_supersedes_running` | 1.0 (**ON**) | `POST /api/trades/generate` with `force: true` **supersedes** an already-RUNNING job for the same `(user, league, format)` key and spawns a fresh one. Before 2026-08-18 the cache-hit branch honoured `force` but the in-flight branch did not, so a forced request arriving mid-generation returned the running job verbatim — same `job_id`, same minted `trade_id`s — and the forced regeneration never happened ("The deck rebuilds around it." after a Quick Set save; it did not). The job registry has **no cancellation mechanism**, so the superseded worker runs to completion but finishes *quietly*: no further snapshot publishes (`_job_live`), no `deck_impressions` rows, and no `trades_generated` event — a deck nobody was served must leave no trace in the signal corpus. It still transitions to `complete`, so a client holding the old `job_id` polls to a terminal state as before. **`0` restores the pre-2026-08-18 silent share.** |

### Consensus seed blend (#145/#148) — `backend/data_loader.py`, DB-seeded

Both knobs shape the **baseline consensus seed values** (the DP→Elo pool seeds), applied once at pool build (`_apply_consensus_blend`, inside `_fetch_dynasty_process`). They are **not** live-hot: a change takes effect on the next boot / pool rebuild (the universal pool is built from the live DP CSV once per boot). Editable via `PUT /api/admin/config/<key>`.

| Key | Default | Meaning |
|---|---|---|
| `ktc_blend_weight` | 0.5 | #145 — weight of KeepTradeCut in the consensus seed blend. Per matched player: `value = (1 − w)·dp + w·ktc_on_dp_curve`, where KTC values are **rank-normalized onto the DP value curve** per format (so the value distribution — and hence tier occupancy / the #117 affine calibration — stays DP-shaped while KTC's ordering opinion is imported). **`0` = DP-only kill switch** (with `tep_te_uplift = 1` **and the #313 QB-cap knobs off** the seed pipeline is byte-identical to pre-#145 — pinned by `test_ktc_blend.test_blend_off_is_byte_identical`, and weight 0 never even fetches KTC). `1` = KTC ordering only. Unmatched pool players keep pure DP; unmatched KTC players are ignored (pool universe unchanged). See [runbook → KTC consensus blend](runbook.md) for the fragility + kill-switch procedure. |
| `tep_te_uplift` | 1.18 | #148 — TE value multiplier applied to **`sf_tep` TE seeds only** (after the blend). DP's `value_2qb` column is *plain* superflex with no tight-end premium, so plain-SF TE values sit ~25–30% below their 1QB analogs; a 1QB→SF-TEP board copy then demoted TEs. The uplift (calibrated 2026-07-17 so the top-8 `sf_tep` TE seeds clear their 1QB analogs at the default blend weight — KTC's own TEP effect is ≈ +11%, the rest offsets SF's non-QB compression) makes SF-TEP TEs read as *slightly upgraded*, matching the operator's expectation. `1` = off. Pinned by `test_ktc_blend.test_sf_tep_top_tes_beat_their_1qb_seed`. |
| `qb_1qb_cap_elo` | 1785 | #313 — the highest seed Elo a quarterback may reach in **`1qb_ppr` only**. 1QB QB values are compressed onto this ceiling after the KTC blend and before the Elo map (`data_loader._compress_qb_1qb_values`): identity at or below `qb_1qb_cap_knee_elo`, and above it the stretch up to the DP ceiling is squeezed monotonically onto the cap, so **the QB board's order is preserved** (a hard clamp would tie the top QBs). 1785 is the top of the `first_1` band in every format/position cell of `tier_config.json` (`firsts_2` starts at 1788), so no QB can read "2 1sts" in a 1QB league — the operator's report. **`0` or negative = kill switch**: the seed pipeline is byte-identical to pre-#313 (pinned by `test_qb_1qb_cap.test_kill_switch_is_byte_identical`). Tier bands and every client mirror are **unchanged** — the label is derived from the served Elo and follows the value. Takes effect on the next pool build/boot. |
| `qb_1qb_cap_knee_elo` | 1580 | #313 — the seed Elo below which 1QB QB values pass through **untouched**; the compression applies only above it. 1580 is the `first_1` floor (the Late-1st pick seed), so the re-pricing is confined to QBs that were already worth a first or more and the rest of the QB board is byte-identical. `0` or negative = kill switch (either knob disables the compression). |

### Trade engine v2 (Tier 1) — `trade_service._DEFAULT_CFG`

| Key | Default | Meaning |
|---|---|---|
| `elo_value_k` | 0.0050 | Steepness of the Elo→value curve `value = base · exp(k · (elo − ref))` |
| `elo_value_ref` | 1500.0 | Elo that maps to the reference value |
| `elo_value_base` | 1000.0 | Value at the reference Elo |
| `package_adj_gamma` | 1.5 | Exponent in the KTC-style per-asset contribution `v · (0.15 + 0.85 · (v/v_max)^γ)` (`package_value_v2`). **#214: this is the `heavy` (legacy) stud-tax mode's depth shape** — the default `market` mode uses the `*_market` keys below. |
| `skew_phaseout` | 0.5 | #214 market mode — the crown credit is scaled by `max(0, 1 − \|naive_skew\| / skew_phaseout)` where `naive_skew` = the sides' naive-sum gap over the SMALLER side's sum. Full credit on even trades, zero once the trade is already half-again lopsided (KTC's observed shape). ≤ 0 disables the phase-out. DB-seeded. |
| `crown_rate_market` | 0.08 | #214 market mode — crown credit per **elite** asset (value ≥ `crown_elite_value`) on EITHER side, count-independent (DynastyDealer's per-side stud-bonus shape). Lower than the legacy `crown_rate` (0.12) because every qualifying piece earns it. Kill-switch: flag `trade.crown_asset`, shared with the legacy crown. DB-seeded. |
| `package_floor_market` | 0.70 | #214 market mode — depth-discount contribution floor: `contribution(v) = v · (floor + (1−floor) · (v/own_max)^γ)` benchmarked against the package's **own best asset** (`own_max`), never the trade-wide `v_max` — a single-asset side is never depth-discounted. Fit 2026-08-05 against the T1–T6 competitor matrix (see `docs/feedback/items/214-stud-tax/build-status.md`). DB-seeded. |
| `package_adj_gamma_market` | 0.5 | #214 market mode — depth-discount exponent (same formula as `package_floor_market`). DB-seeded. |
| `package_discount_cap` | 0.35 | #214 market mode — a side's TOTAL depth discount is capped at this fraction of its naive sum (DynastyDealer's observed −22…−38% ceiling). DB-seeded. |
| `min_side_surplus` | 150.0 | Min per-side value gain (raw values) for a trade to surface |
| `min_side_surplus_marginal` | 60.0 | Replacement gate when `trade.marginal_value` is on (marginal values run smaller) |
| `user_gain_epsilon` | 0.0 | #108 user-board gain gate (value space). 1-for-1 player swaps (any basis, v2 + v3) must show receive − give ≥ ε on the user's OWN raw board (pre-shrinkage `user_elo`) — never offer the user's higher-ranked player for their lower-ranked one. Consensus-basis cards additionally require the consensus package delta (receive − give) ≥ ε on every shape. 0.0 = receive must at least tie give. Multi-asset divergence packages are exempt from the raw-board rule (the aggregate surplus gate is the compensation test). |
| `filler_min_frac` | 0.25 | #141 junk-filler gate (all package shapes: v2 pair, v3 optimizer incl. the 3.4 sweetener pass, consensus fallback). Any piece beyond a side's headliner (its best asset) must be worth ≥ this fraction of that headliner, each player priced at **max(user board, opponent board)** raw value — a filler EITHER side genuinely values survives; junk both boards value low never pads a suggestion. Headliners (the 1-for-1 core) are exempt; marginal valuation is deliberately NOT used (it collapses depth pieces by design, but "is this junk?" is a board-value judgment). On the consensus path the opponent's board is consensus. 0.25 ≈ a 277-Elo window below the headliner: on the 2026-06-13 DP snapshot a Chase-headlined side (≈8470) only accepts pieces ≥ ~2100 (≈ a mid 1st / top-65), a rank-50-headlined side (≈3250) accepts ≥ ~810 (≈ rank 115), and a rank-100-headlined side (≈1000) accepts ≥ ~250 (≈ rank 250) — so depth-for-depth trades are untouched. 0 restores pre-#141 behavior byte-identically. Unlike the other Tier-1 keys this one **is DB-seeded** (`_MODEL_CONFIG_DEFAULTS`), so it is live-tunable via `PUT /api/admin/config/filler_min_frac`. |
| `asset_floor_abs` | 450.0 | Interview 2026-07-17 ("both floors") — absolute companion to `filler_min_frac`, same code path (`filler_ok`) and same max-of-boards metric: every non-headliner piece must ALSO clear this value-space floor (~bottom of the depth tier, Elo ≈ 1350), so pure roster-clogger bodies never pad a package even when the relative bar is tiny. Headliners exempt; `filler_min_frac = 0` remains the master kill-switch for the whole gate; 0 disables just the absolute floor. DB-seeded. |
| `consolidation_raw_loss_frac` | 0.15 | Deck-eval 2026-07-17 — consolidation raw-delta sanity gate, **consensus path only** (`_generate_consensus_for_pair._emit`). On a user-give-side consolidation (more assets given than received) the **raw** consensus loss `Σgive − Σreceive` may not exceed this fraction of `Σgive`. Closes the insult-card class where the `package_adj_gamma` depth discount vaporizes a valuable second give asset while the crown premium inflates the received stud, so the adjusted delta (the #108 gate's input) flips positive and fairness scores ~0.99 on a raw −2748 consensus loss (Daniels + Odunze → Hurts). Divergence cards are untouched (their both-sides surplus gates run on real boards). 0.15 ≈ the market's ceiling on a fair consolidation premium; a 13%-loss 2-for-1 still surfaces. 0 disables (pre-fix behavior). DB-seeded. |
| `fairness_floor_divergence` | 0.55 | Interview 2026-07-17 ("loosen it") — for **divergence** cards (both members have real boards) the consensus fairness gate becomes `min(fairness_threshold, this)`: an extreme-case veto only, since the both-sides surplus gate already proves mutual gain on the boards that matter. Applies in the v2 pair generator and the v3 optimizer (including the sweetener band). Consensus-basis cards keep the full `fairness_threshold`. Fairness still weighs into the composite, so lopsided-but-mutual trades rank lower rather than vanish. DB-seeded. |
| `relaxed_fairness_threshold` | 0.55 | #189 — stage-1 fairness bar for the **relaxed fallback pass**: when a *targeted* job (pinned players and/or acquire/trade-away positions) yields ZERO cards under normal gates, generation reruns with the effective fairness threshold (caller's threshold AND `fairness_floor_divergence`) dropped to `min(caller's threshold, this)` — relaxation never tightens. Cards from the pass carry `relaxed: true` + `relaxed_reason`. No flag: the behavior only activates on otherwise-empty targeted results. The #108 `user_gain_epsilon` gate and untouchables are NEVER relaxed. DB-seeded. |
| `relaxed_surplus_floor` | 0.0 | #189 — stage-2 ("fairness_band+surplus_floor") value for `min_side_surplus` / `min_side_surplus_marginal` when stage 1 still yields nothing. 0.0 still requires NON-NEGATIVE surplus on both boards — mutual gain is floored, never inverted. DB-seeded. |
| `asset_ideas_lateral_band` | 0.10 | #172/#189 follow-up (flag `trade.asset_ideas`) — classification band for `TradeService.generate_asset_ideas`: a counterpart asset within ±this fraction of the pinned asset's consensus value is a **Lateral** 1-for-1 candidate; above the band it's an **Upgrade** target, below it a **Downgrade** piece. DB-seeded. |
| `asset_ideas_group_cap` | 6.0 | #172/#189 follow-up — max ideas returned per group (upgrade / lateral / downgrade) by `POST /api/trades/asset-ideas`, ordered by \|difference\| ascending (closest deals first). DB-seeded. |
| `mutual_gain_cap` | 1500.0 | Normalization ceiling for the harmonic-mean term in the composite score |
| `waiver_slot_cost` | 425.0 | Value cost per extra player received (FantasyCalc-derived ≈ rank-300 value) |
| `shrink_pseudocount` | 4.0 | n₀ in confidence shrinkage `w = n / (n + n₀)` toward seed Elo |
| `range_base` | 0.35 | Value half-width fraction at n=0 comparisons (range-overlap fairness) |

> **Tuning gotcha (TC-CFG-001, amended by #108):** the surplus floors (`min_side_surplus` / `min_side_surplus_marginal`) gate **divergence-basis** cards only. **Consensus-basis** cards (for opponents with no saved rankings — which dominate cold / low-coverage leagues) carry no surplus signal and are gated by **fairness plus the #108 user-gain rule** (`user_gain_epsilon`): the user's side must receive at least as much consensus package value as it gives, and a 1-for-1 must also respect the user's own raw-board ordering. (Before #108 they were gated by fairness alone, which let a card ask the user to pay up to `1 − fairness_threshold` more consensus value.) To throttle a consensus-heavy deck, tune `fairness_threshold` (per-request) or `consensus_score_scale`, not the surplus floors. And remember `trade.marginal_value` (on by default) makes `min_side_surplus_marginal` the live floor — tuning `min_side_surplus` alone is then a no-op.

### Tier 2 — marginal valuation + outlook blend

| Key | Default | Meaning |
|---|---|---|
| `bench_credit_rate` | 0.15 | FALLBACK bench credit for positions outside QB/RB/WR/TE (interview 2026-07-17 made the credit position/format-aware — see the six keys below, picked by `bench_credit_rate()` in `trade_service.py`) |
| `bench_credit_qb` | 0.10 | Bench credit for QB depth in 1QB formats (fungible) |
| `bench_credit_rb` | 0.30 | Bench credit for RB depth (near-startable insurance in every format) |
| `bench_credit_wr` | 0.30 | Bench credit for WR depth (near-startable insurance in every format) |
| `bench_credit_te` | 0.10 | Bench credit for TE depth in non-TEP formats |
| `bench_credit_qb_sf` | 0.35 | QB override in superflex — backup QBs are startable capital |
| `bench_credit_te_tep` | 0.25 | TE override in TE-premium |
| `waiver_baseline_value` | 250.0 | Replacement floor when a position has fewer than starters+1 players |
| `outlook_alpha_championship` | 1.00 | α (weight on NOW value; 1−α on FUTURE) per outlook |
| `outlook_alpha_contender` | 0.75 | |
| `outlook_alpha_not_sure` | 0.50 | Also used for outlook = None/unknown |
| `outlook_alpha_rebuilder` | 0.25 | |
| `outlook_alpha_jets` | 0.10 | |

The per-position age NOW/FUTURE curves are deliberately a code constant table (`_AGE_NOW_CURVE` / `_AGE_FUTURE_CURVE` in `trade_service.py`), not config keys — the breakpoints were calibrated as a set.

### Tier 2 — deck ordering, diversification, fuzzy matching, likes-you

| Key | Default | Meaning |
|---|---|---|
| `diversity_window_days` | 7.0 | Lookback for league-wide impression counts |
| `diversity_user_cap` | 3.0 | Top receive asset already shown to ≥ this many OTHER members → penalize |
| `diversity_penalty` | 0.6 | Ordering-key multiplier for saturated targets |
| `deck_max_per_target` | 3.0 | Intra-deck cap: cards per top receive asset (deck never shrinks below 5) |
| `fuzzy_match_tau` | 0.8 | Min Jaccard similarity per side for a fuzzy mirror match (read inline in `server._fuzzy_match_tau`) |
| `likes_you_min_user_delta` | -500.0 | **User-gain floor on the likes-you injection** ([D-055](../living-memory/DECISIONS.md)). A leaguemate's liked trade is mirrored into the user's deck only when the **viewer's** net consensus value — `sum(receive) − sum(give)` over per-player `elo_to_value`, the same arithmetic `scripts/deck_eval.py` scores decks with — is ≥ this value. Below it the like is skipped entirely: not flagged, not boosted, not synthesized, and it does **not** consume one of the 3 `_LIKES_YOU_CAP` slots, so a fairer like can still take it. The default is the ratified deck-eval materiality floor (−500): the 2026-08-15 Phase A gate found **all 8** insulting first-deck cards were likes-you injections at deck position 1–3 ([open-access-phase-a-gates.md § Gate (a)](plans/open-access-phase-a-gates.md)), and −500 removes every one of them (insult rate 1.48% → 0.00%) while keeping 54 of 66 injections. The **mechanism** is ratified; the number is tuning — raise toward 0 to cut every net-negative injection (removes 51/66), or set very negative to restore pre-D-055 behavior. Read via `server._likes_you_min_user_delta`; DB-seeded, so `PUT /api/admin/config/likes_you_min_user_delta` retunes it without a deploy |
| `thompson_prior_base_rate` | 0.59 | **F2** (flag `deck.thompson_v2`) — fallback p̂ for the pessimistic prior Beta(1, 1/p̂) when the trailing-30-day GLOBAL like rate (`load_global_like_rate`, cached 6h in `server._thompson_prior_base_rate`) has < 10 decisions or the read fails. Clamped to [0.05, 0.9]. Default = all-time global like rate 13/22 as of 2026-07-26. Read via `server._deck_cfg` |
| `thompson_decay_gamma` | 0.995 | **F2** (flag `deck.thompson_v2`) — per-day posterior decay γ: effective like/pass mass = γ^age_days, computed lazily at read time in `server._thompson_v2_arm_stats` (no cron mutates state). Clamped to [0.5, 0.99999]. Start conservative; tunable without deploy |
| `replenish_weekday` | 2.0 | **F10** (flag `deck.replenishment`) — Python `weekday()` on which the weekly replenishment pass inside `/api/cron/daily-tick` unlocks (2 = Wednesday, post-waivers). The gate is `>=`, so later days of the same ISO week self-heal a missed cron run; the `deck_replenish_log` marker keeps everything 1/week. Read via `server._deck_cfg` |

### F3 — fatigue & durable suppression (flag `deck.fatigue`)

All read via `server._deck_cfg`, consumed by the fatigue/suppression layer around `_order_deck`. The soft multiplier is the PRD's LinkedIn impression-discounting form `w1·exp(−a·impCount) + w2·exp(−b·daysSinceLastSeen)`, computed from **viewed** impressions only, clamped to `[fatigue_floor, 1.0]`, applied only to items with ≥1 viewed impression inside `fatigue_lookback_days` — recovery comes from impressions aging out of the window. A card takes the **min** across its keys (trade_hash, centerpiece, archetype), never a product. Discount-only: multipliers never exceed 1.0 and are applied after all generation gates.

| Key | Default | Meaning |
|---|---|---|
| `fatigue_w1` | 0.85 | Weight of the impression-count term |
| `fatigue_w2` | 0.15 | Weight of the recency-credit term |
| `fatigue_a` | 0.18 | Per-impression decay at item level (trade_hash / centerpiece keys) |
| `fatigue_b` | 0.10 | Per-day decay of the recency credit |
| `fatigue_arch_a` | 0.05 | Weaker per-impression decay for the archetype-level accrual |
| `fatigue_floor` | 0.25 | Soft multiplier never drops below this |
| `fatigue_lookback_days` | 30.0 | Viewed impressions older than this stop counting (the recovery window) |
| `fatigue_session_hours` | 8.0 | Deck-session window for the 2+-pass demotion |
| `fatigue_session_demotion` | 0.2 | Multiplier for a centerpiece passed ≥2× within one deck job in the session window |
| `fatigue_decline_suppress_days` | 30.0 | Hard near-duplicate suppression window after a decline / proposal-kill |
| `fatigue_decline_value_band` | 0.10 | Near-duplicate ⇔ same centerpiece + shape AND package value within ±this fraction of the declined package |
| `fatigue_retest_mult` | 0.5 | Low-exposure multiplier for the ONE post-window retest card |

### F5 — trade-taste vectors (flag `deck.taste_vectors`)

All read via `taste_service._cfg` (same live-dict pattern as `server._deck_cfg`), consumed by `backend/taste_service.py` + the taste layer around `_order_deck`. Serving math: `final = base × clamp((1 + taste_eta_long·prefMatch_long)·(1 + taste_eta_short·prefMatch_short), taste_clamp_lo, taste_clamp_hi)` with prefMatch = normalized cosine of the decayed vector against the card's attribute set (`shape:`, `arch:`, `window:`, `cpos:`, `givepos:`/`recvpos:`, `giveband:`/`recvband:`, `giveage:`/`recvage:`, `pick:`, `partner:` keys). Zero-history user ⇒ prefMatch 0 ⇒ multiplier exactly 1.0 (flag-off-identical ordering). Applied after every generation gate — reorders acceptable trades, never rescues gated ones — and composes multiplicatively with the F3 fatigue discount.

| Key | Default | Meaning |
|---|---|---|
| `taste_eta_long` | 0.2 | Long-τ prefMatch weight (η_l) |
| `taste_eta_short` | 0.3 | Short-τ prefMatch weight (η_s) |
| `taste_clamp_lo` | 0.7 | Final taste multiplier floor |
| `taste_clamp_hi` | 1.4 | Final taste multiplier ceiling |
| `taste_tau_short_days` | 21.0 | Short-interest decay τ (`w ← w·exp(−Δt/τ) + r`, lazy at read/update) |
| `taste_tau_long_days` | 180.0 | Long-interest decay τ |
| `taste_dwell_ms` | 8000.0 | `dwell_ms` ≥ this on an outcome ⇒ the long-dwell bonus applies (hesitation is interest, whatever the verdict) |
| `taste_dwell_bonus` | 0.3 | Reward added on a long dwell (base rewards: like +1, propose +6, accept +4, pass −0.5, decline −2, not_interested −4) |
| `taste_epsilon` | 0.05 | GC floor — `user_taste` rows whose decayed weights are BOTH below this are deleted on read/update; sub-ε prior attrs are never stored |
| `taste_prior_scale` | 10.0 | Board-prior ceiling ≈ the weight of this many likes (a warm start swipe volume overtakes, not a ceiling) |
| `taste_prior_shrink` | 20.0 | Per-attribute ranked-count shrinkage `n/(n+this)` on the board prior |
| `taste_prior_ref_delta` | 0.25 | Board-vs-consensus relative delta treated as "strong" (prior scales on `mean_delta/this`, clamped ±1) |

### F7 — exploration slots & archetype audition (flag `deck.exploration`)

Read via `server._deck_cfg`, consumed by the exploration layer that runs AFTER `_order_deck` in `_run_trade_job` (`_apply_exploration_slot` + `_audition_statuses`). One honestly-labeled wildcard per deck of ≥ `exploration_min_deck` cards, drawn uniformly from gate-passing candidates OUTSIDE the served deck (the engine over-generates `exploration_overgen` extra cards per opponent while the flag is on) — bottom prefMatch tercile → low-data F2 arms → uniform, plus auditioning-archetype candidates. Quality gates never relax; F3 decline suppressions still bind on the draw pool. The wildcard's logged propensity is `exploration_rate × 1/|eligible pool|` (replaces the Thompson multiplier — see `deck_impressions.propensity` in the data dictionary).

| Key | Default | Meaning |
|---|---|---|
| `exploration_rate` | 0.125 | Propensity numerator only (PRD's ≈1-in-8 slot share); slot frequency itself is 1 per eligible deck |
| `exploration_slot_position` | 5 | 1-indexed served slot for the wildcard, clamped to positions 4–6 (F4's client lock keeps it pinned) |
| `exploration_min_deck` | 8 | Decks below this many cards get no wildcard |
| `exploration_overgen` | 3 | Extra per-opponent candidates generated (on top of the flag-off 5) to form the outside-the-deck draw pool |
| `audition_min_views` | 30 | Viewed impressions (global, viewed-gated) before an auditioning archetype gets a graduate/retire verdict; also the all-time bar below which a first-seen archetype enters `test` |
| `audition_like_rate_frac` | 0.5 | Graduate when window like-rate ≥ this × the global base rate (F2's cached trailing-30d p̂) |
| `audition_retire_days` | 30 | Retirement window for a failed archetype before it re-enters `test` with a fresh counting window |

### F9 — first-session win engineering (flag `deck.first_session`)

Read via `server._deck_cfg`, consumed by the first-deck layer that runs AFTER the F7 wildcard insert and BEFORE impression logging in `_run_trade_job` (`_apply_first_session_shaping` + `_first_session_confidence_ok`). First decks only (no `deck_impressions` AND no legacy `trade_impressions` rows for the user+league): the deck clamps to `first_session_deck_max` cards (truncate only, never padded), then a stable partition floats confidence-passing cards into the first `first_session_top_k` UNLOCKED slots — the F7 wildcard's fixed slot, likes-you pins, and F3 retest cards never move (with the wildcard at slot 5 the region is positions 1–4 + 6). Reorder/truncate only — quality gates untouched, no card is ever rescued.

| Key | Default | Meaning |
|---|---|---|
| `first_session_top_k` | 5 | Confidence-weighted top region — the first this-many unlocked served slots |
| `first_session_min_margin` | 40.0 | Divergence-card bar: `mismatch_score` ≥ this |
| `first_session_min_fairness` | 0.85 | Consensus-card bar (their mismatch is 0 by construction): `fairness_score` ≥ this |
| `first_session_min_seed_elo` | 1250.0 | High-data check: EVERY asset must be consensus-seeded ≥ this (the seed map is the consensus-n signal the engine already computes; user comparison counts are ~0 on a first deck). #185-primed picks pass naturally |
| `first_session_max_side_assets` | 2 | Per-side asset cap for "simple shape" |
| `first_session_max_total_assets` | 3 | Total asset cap — defaults ⇒ 1x1 / 2x1 / 1x2 pass, 2x2/3x1+ serve later |
| `first_session_deck_max` | 10 | First decks truncate to ≤ this many cards (session-one completion — F10's moment — must be reachable) |
| `first_session_deck_min` | 8 | Documented target floor only — no padding, only the max clamps |

### Suggestion telemetry & ghost holdout (flag `suggestion.telemetry`)

Read via `suggestion_telemetry._cfg` (the `_deck_cfg` pattern — `trade_service._DEFAULT_CFG` defaults, live-tunable through `model_config` without deploy). Scope block: `docs/plans/matchmaking-engine/telemetry-scope.md`.

| Key | Default | Meaning |
|---|---|---|
| `ghost_holdout_one_in` | 10 | Ghost withholding rate: an organic deck card ghosts when `sha256("ghost\|league\|iso_week\|trade_hash") % N == 0`. **≤ 0 disables ghosting without touching the flag** — the deploy-free rollback lever. Exempt always: likes-you, wildcard, F3-retest cards; pinned/opponent-targeted decks; demo league |
| `suggestion_match_lookback_days` | 14 | Executed-trade matcher window: only suggestions served within this many days BEFORE `traded_at` are candidates |
| `suggestion_match_min_overlap` | 0.5 | Partial-match floor: matched-token share of the larger asset set (with ≥1 matched asset required on each side) |

### F6 — learned acceptance heads × V-vector (flag `deck.value_model` — **dark**)

All read via `value_model._cfg` (same live-dict pattern as `taste_service._cfg` — keys are NOT in `trade_service._DEFAULT_CFG`; set them as `model_config` rows to override the inline defaults). Consumed by `backend/value_model.py`. The V-vector is the hand-set strategy layer (PRD §2): `rank_score = P(like)·value_model_v_like + P(like)·P(propose|like)·value_model_v_propose`, read LIVE at scoring time so strategy changes need no retraining. The rank_score replaces `composite_score` as `_order_deck`'s **base ordering key only** (the F6 seam — `server._order_deck(value_scores=…)`); all gates and presentation multipliers apply on top unchanged, and `deck_impressions.base_score` keeps logging the composite. **Both serving and the automatic nightly refit (daily-tick, after the F8 eval block) are gated on `deck.value_model`** — dark means zero model reads/writes/training. Flag-independent operator tools: `python3 -m backend.value_model --refit` (train; needed BEFORE the flag flips so F8 can grade the model) and the registered `value_model` eval scorer.

| Key | Default | Meaning |
|---|---|---|
| `value_model_v_like` | 1.0 | V(like) — hand-set value of a predicted like |
| `value_model_v_propose` | 6.0 | V(propose) — hand-set value of a predicted proposal (6:1 vs like, mirroring the Elo K-ratios; utility-not-time-spent) |
| `value_model_calib_frac` | 0.2 | Trailing time-slice fraction of training rows held out for Platt calibration (clamped 0.05–0.5) |
| `value_model_l2` | 0.01 | L2 on the numeric/dense feature group (bias exempt) |
| `value_model_l2_cat` | 0.5 | L2 on one-hot features — much stronger by design: at this data volume one-hots overfit label noise (validated on the F8 synthetic fixtures), while personalized categorical taste reaches the model through the F5 prefMatch numerics |

Env var: `VALUE_MODEL_DIR` (default `data/value_model/` — inside the gitignored `/data/`) — directory for the append-only `models.jsonl` model store (latest parseable record = the served model; nightly refit is idempotent per UTC `train_date`). Tests point it at a tmp dir, F8-`EVAL_RUNS_DIR`-style.

### Tier 3 (flag-gated, landing imminently)

| Key | Default | Meaning |
|---|---|---|
| `v3_pool_size` | 12 | Candidate pool size per side for the exact per-pair search |
| `picks_pool_cap` | 6 | **#170/#171** — max owned draft picks per team injected into the suggestion candidate pool (top-N by `pool_value`) when `trade.picks_in_pool` is on. Bounds package enumeration. `0` disables injection. |
| `sweetener_band` | 0.15 | Fairness shortfall band in which a sweetener pass is attempted |
| `sweetener_max_cards` | 2 | Max sweetener-balanced cards per deck |
| `cycle_edge_min_gain` | 100.0 | Min per-edge value gain for a 3-team cycle edge |
| `cycle_min_net` | 200.0 | Min net surplus per participating team in a cycle |
| `cycle_max_results` | 3 | Max 3-team cycle cards surfaced |

### Trade generation pipeline v2 (flag `trade_gen.v2` — dark) — `trade_service._DEFAULT_CFG`, consumed by `backend/trade_gen_v2.py`

| Key | Default | Meaning |
|---|---|---|
| `gen2_epsilon` | 100.0 | Dual-board ε-gain gate: minimum own-board gain PER SIDE (value space, on consolidation-discounted packages). Extends the #108 `user_gain_epsilon` convention to BOTH sides of every generated package. 100 ≈ 5% of a generic mid-1st — between the existing marginal (60) and raw (150) surplus floors: big enough to beat board noise, small enough to keep genuinely mutual depth trades alive. |
| `gen2_band` | 0.15 | Consensus fairness band half-width: discounted consensus package values must satisfy min/max ≥ 1 − band (±15%, the research's defensibility band). A constraint, never an objective — own-board gain decides *acceptance*, this band decides *league defensibility*. |
| `gen2_consol_gamma` | 1.5 | Consolidation discount exponent γ: `contribution(v) = v · (floor + (1−floor)·(v/v_best_own)^γ)`, benchmarked against the side's OWN best asset. Single-asset sides are never discounted. |
| `gen2_consol_floor` | 0.15 | Consolidation discount floor: a near-worthless filler contributes ≈ floor·v, so junk cannot stuff a package to fairness. **1.0 restores naive additivity** (the documented KTC exploit) — the discount's kill switch. |
| `gen2_centerpiece_top_k` | 5 | Stage-1: divergence-ranked centerpieces examined per opponent. Bounds **search breadth** (which opponent assets anchor a package search), never output length — the engine returns every gate survivor. Raised 3 → 5 with the 2026-08-16 no-truncation decision: at 3, deep divergent rosters starved the browse tier of centerpiece variety; 5 keeps worst-case enumeration ≈ 9.6k combos/pair. |
| `gen2_give_pool` | 10 | Stage-2: user-side return-asset pool (ranked by `v_opp − v_user`). |
| `gen2_recv_extra_pool` | 4 | Stage-2: divergence-positive extras eligible to round out the receive side (receive = centerpiece + ≤2 extras). |
| `gen2_min_divergence` | 0.0 | Minimum own-board divergence (value space) for a centerpiece; candidates need `v_user − v_opp` strictly above this. |
| `gen2_exposure_cap` | 3 | Exposure budget — **ordering, never truncation** (operator decision 2026-08-16): max suggestions per counterparty in the shaped HEAD of the list; cap-overflow cards are demoted below the head in rank order, never dropped. |
| `gen2_exposure_floor` | 1 | Exposure floor: every counterparty with ≥1 viable (gate-surviving) suggestion gets at least this many cards in the shaped head. 0 disables the floor. |
| `gen2_featured_count` | 4 | Tier metadata: after the single `endorsed` pick, cards ranking inside this count are `featured`; every remaining survivor is `browse`. Scarcity lives in the tier field, not in list length. |
| `gen2_dedup_jaccard` | 0.6 | Batch dedup: a lower-ranked suggestion whose combined asset set overlaps a kept same-counterparty suggestion at-or-above this Jaccard is a near-duplicate. (Exact-set and same-(counterparty, centerpiece, shape-bucket) duplicates are always dropped.) |
| `gen2_meso_band` | 0.05 | MESO variants: alternate return packages must sit within ±this fraction of the base return's value **on the RECIPIENT's (counterparty's) board** — equivalence on the recipient's board, so their choice reveals shape preference, not value preference. |
| `gen2_meso_max_variants` | 3 | Max MESO variants on each pair's top card (research guidance: never exceed ~3 offers). |
| `gen2_accept_prior_strength` | 10.0 | Completion-probability hook: empirical-Bayes pseudo-observation count m in `p = (accepts + m·p0)/(responses + m)`. |
| `gen2_accept_global_prior` | 0.5 | Global acceptance prior p0 — the fallback when a manager has no accept/response history (uniform scaling, ordering unchanged). |
| `gen2_youth_age` | 25 | MESO shape vocabulary: a package is `youth_heavy` when the value-weighted mean age of its non-pick players is ≤ this. |

### Trade presentment rules (flag `trade.presentment_rules`) — `trade_service._DEFAULT_CFG`, DB-seeded

G6 2026-08-16 wave (#304 #336 #339 #340 #341). All seven are DB-seeded and
live-tunable via `PUT /api/admin/config/<key>` — each is that rule's
deploy-free kill switch (R4 has no knob; the flag is its revert). Units:
raw summed consensus value (`seed_value` per side) — the D-055 Δ currency.
Measured baselines + acceptance bands:
[feedback/items/304-positional-need-filter/prd.md §2](feedback/items/304-positional-need-filter/prd.md).

| Key | Default | Meaning |
|---|---|---|
| `max_overpay_frac` | 0.25 | R1 #340: kill when the raw consensus gap is ≥ `max_overpay_min_value` AND ≥ this fraction of the larger side — either side overpaying, independent of `fairness_threshold` (the mobile toggle can never relax it). Corpus-fit: 0.20 killed 14–18% (too hot); 0.35 left the 25–35% insult band alive; 0.25 → 8.9% and covers every corpus insult card. **≤ 0 disables R1.** |
| `max_overpay_min_value` | 500.0 | R1: absolute gap floor (D-055 materiality — also why a `fit_premium_max_loss` (300) need-fill card can never trip R1). |
| `pos_net_cap` | 1.0 | R2 #341: max \|count(recv at P) − count(give at P)\| per position over {QB, RB, WR, TE} — one signed net per position (2RB→2RB is net 0), picks uncounted, K/DEF/IDP uncounted by design. **0 disables** (the `filler_min_frac` convention). |
| `pick_gap_frac` | 0.8 | R3 #339: two-sided band — for a gap ≥ `pick_gap_min_value`, a pick on the HEAVIER side inside [frac·gap, gap/frac] kills ("the pick is the gap"); a pick far larger than the gap (stud-scaled centerpiece consolidation) passes. Same knob mirrored forms the upper bound. **0 disables.** **UNMEASURED default** — zero pick cards in the D-055 corpus and zero R3-shaped candidates in the 2026-08-16 local pick replay; this knob is the named tuning lever pending a prod-state divergence replay (NEXT.md follow-up). |
| `pick_gap_min_value` | 300.0 | R3: consensus gap floor below which the band is never evaluated. |
| `need_gate_min_value` | 500.0 | R5 #304: minimum consensus value of the primary received player before the need gate applies (sub-floor churn always passes). Untargeted discovery decks only (R-5b bypass). **≤ 0 disables the whole gate.** |
| `need_gate_upgrade_margin` | 0.0 | R5: the primary must beat the post-give incumbent (S-th best body at P on `roster − give`) by this fraction to count as a starter upgrade. 0 = any strict upgrade passes. |

### Engine quality (2026-08-18 field wave) — `backend/trade_service.py` + `backend/trade_optimizer.py`

Five independent ranking/gating fixes for the two defects diagnosed from the
live corpus (563 impressions / 8h): **picks buying fairness for free** (a pick
carries zero board divergence by construction, so it adds nothing to the
mutual-gain story, yet it raised the consensus fairness term whenever it closed
the value gap — 63% of live cards involved a pick) and **one high-divergence
asset flooding a whole deck** (Colston Loveland in 18 of 18 cards). Scope block:
[plans/engine-quality/scope.md](plans/engine-quality/scope.md).

**No feature flag by design** — each change gets its OWN knob, so the five are
independently revertible. Every key below defaults ON (today's behavior *is* the
bug) and its kill value is a deploy-free, byte-identical revert via
`PUT /api/admin/config/<key>`. These knobs change LIVE behavior for all users:
the v1 engine path (`trade_engine.v2` + `trade_engine.v3`) is what everyone is
on. `trade_gen.v2` is dark and carries its own gate stack — it is unaffected by
C1/C2/C4/C5 and sees C3 only in its pre-existing narrow form.

| Key | Default | Kill value | Meaning |
|---|---|---|---|
| `rank_div_min_frac` | 0.02 | **0** | **C1** — an asset enters the **signal core** (the sub-package the RANKING fairness term is priced on) only when the two boards disagree about it by at least this fraction of its own value. Picks sit at exactly 0 by construction, so they can never move the ranking fairness ratio: adding a zero-divergence asset to either side leaves the term bit-for-bit unchanged, for any base package. The fairness **GATE** and the card's stamped `fairness_score` still price the REAL package — a pick genuinely transfers value and can genuinely make an unfair trade fair. Degenerate cores fall back to full-package fairness: one side entirely zero-divergence is the legitimate "buy a player with a pick" shape, and consensus-basis cards have no divergence at all. Pricing on the core makes a package and its zero-divergence-padded sibling score *identically*, so C1 also owns the resulting tie in the v2 heap: on a tie, **fewer pieces wins** (the pre-existing tie-break was later-enumerated-wins, and 1-for-1s enumerate first, so the bare deal lost every tie it now makes). v3 already tie-broke toward the smaller package and needed no change. Kill value restores full-package ranking fairness AND the original tie-break. |
| `min_package_band` | 0.10 | **0** | **C2** — minimal-package preference in the pinned/targeted asset-ideas ranker (`_emit_best`). Units are **fairness**, measured from the best variant of the same search: variants within this much fairness of the best are near-equivalent deals, and among them the one with **fewer pieces** wins; a variant further out than the band still loses on fairness, so a genuinely needed sweetener is never dropped. Fixes the shape where a bare 1-for-1 at a 200-point gap LOST to the same trade plus a 180-point pick that shaved the gap to 20 — closest-to-even alone had no preference for fewer pieces, so the pick bought the slot for free. Kill value restores the original `(relaxed, |difference|, give, receive)` rank key. |
| `pick_pair_strip_frac` | 0.85 | **0** | **C3** — widened `pick_swap_ok`. Picks are paired across the two sides best-against-best by consensus value; a pair whose min/max ratio is at or above this frac is **matched** (same asset class, same price, zero divergence in BOTH directions) and is stripped before the churn gate rules on the trade, so the deal is judged on its real content. **Emptying either side ⇒ the pick swap WAS the trade ⇒ killed.** Previously only the literal 1-for-1 both-sides-pick shape was banned and pick-for-pick INSIDE a package passed by design, which let a 1st-for-1st ride along in a bigger deal contributing nothing (tester: "another example of a random 1st swap. Shouldn't happen"). Documented exemptions preserved: picks as sweeteners/headline compensation (only one side holds picks, nothing pairs) and pick **consolidation** (2 lesser picks for 1 better — best-against-best pairing puts those values outside the band, so nothing strips). Also re-validated on the v3 sweetener pass, since the sweetener can itself be a pick. Kill value — and any caller that passes no consensus value fn, which is how the dark `trade_gen.v2` path stays untouched — restores the pre-C3 narrow gate exactly. |
| `deck_headliner_cap` | 2.0 | **0** | **C4** — at most this many cards in one served deck may share a **centerpiece** (the package's highest-consensus asset). Applied in `_dedup_and_sort` AFTER the composite sort, so each headliner keeps its BEST cards, and at deck assembly rather than inside one opponent's enumeration, so it bounds the FINAL served set (streaming snapshots re-derive it from the same accumulating list, exactly like the R4 exclusion). Dedup there was exact-key only, and `mismatch` is largest for whichever asset diverges most between the two boards, so that one asset generated many distinct high-scoring packages and all of them survived — Colston Loveland in 18 of 18 cards of one live deck, 8/8 in another, MarShawn Lloyd 13/33. That made a single valuation error catastrophic instead of survivable, since mismatch is LARGEST exactly where a valuation is most wrong. The centerpiece is `trade_service.deck_centerpiece`, the same definition `deck_impressions.centerpiece_id` is written with (`server._fatigue_centerpiece` delegates to it), so the cap and the metric that measured the flooding cannot drift. Kill value drops no card and leaves the plain composite sort. |
| `mismatch_confidence_damp` | 1.0 | **0** | **C5** — scales the RANKING mismatch term by `max(0, 1 − damp × unc)`, where `unc` is the package's value-weighted mean `_value_uncertainty` (`range_base / sqrt(1 + n)`, n = the user's comparison count for that player). That uncertainty already existed but fed only the fairness gate's range-overlap test, never the ranking, so a large apparent divergence resting on a player almost nobody has ranked outranked well-sampled disagreement. At the default a never-compared package keeps 65% of its mismatch (1 − `range_base`) and a heavily-compared one keeps ~99%. The surplus **gates** are untouched — this reorders cards that already passed, it never removes one. `confidence=None` (no counts available) is a no-op at any value: no information is not the same as low confidence. Kill value ⇒ undamped. |


### Bake-off arm A — `MODEL_A_PROFILE` + the R4 bypass (`backend/bakeoff_profiles.py`)

**Not a knob — a pinned *set* of kill values.** The three-model bake-off
([plans/three-model-bakeoff/PLAN.md](plans/three-model-bakeoff/PLAN.md)) serves
trade cards from three generators side by side. Arm **A** (`baseline`) is the
engine as it behaved **before** the two waves above, and the engine was
modified *in place*, never forked — so "original" exists only as the nine knobs
in the two tables above set to their disable values. `MODEL_A_PROFILE` is that
set, pinned as a constant against reference SHA **`92c31d5`** (`20b40db^` — the
last commit before the G6 wave) and golden-tested in
`backend/tests/test_bakeoff_arm_a_golden.py`. Scope block, with the audit of
every knob included *and every knob deliberately excluded*:
[plans/three-model-bakeoff/scope-phase2.md](plans/three-model-bakeoff/scope-phase2.md).

| Item | Value |
|---|---|
| `MODEL_A_PROFILE` | `max_overpay_frac`, `pos_net_cap`, `pick_gap_frac`, `need_gate_min_value`, `rank_div_min_frac`, `min_package_band`, `pick_pair_strip_frac`, `deck_headliner_cap`, `mismatch_confidence_damp` — **all 0.0** |
| `MODEL_A_REFERENCE_SHA` | `92c31d5` |
| Entry point | `with backend.bakeoff_profiles.model_a(): …` |

**Nothing here changes any default.** The profile rides the existing
thread-local `_cfg_override` seam (#189), so it applies only to the thread
inside `model_a()`; `model_config`, the DB seed values and every ordinary trade
job are untouched. `trade_optimizer` (v3) reads `_c` from `trade_service`, so
the v3 optimizer honours the profile too.

**The R4 bypass** (`trade_service.r4_bypass()` / `r4_bypassed()`). R4 — the
#336 windowless awaiting/matched exclusion — is the one G6 rule with **no
knob**: `trade.presentment_rules` is its only switch, and that flag is global,
so flipping it would disable R4 for arms B and C and for every other user.
`r4_bypass()` is a thread-local context manager in the same style as
`_cfg_override`; inside it, the R4 exclusion set is ignored at all three sites
that consult it — `TradeService._dedup_and_sort` (streaming snapshots
included), the `trade_gen.v2` hand-off, and `server._inject_likes_you_cards_impl`.
It never bypasses `_past_decision_keys`: a trade the user already swiped on
stays gone for every arm. Outside `model_a()` the bypass is off, so production
behaviour is unchanged.

**Adding a generation knob?** `test_no_generation_knob_was_added_without_an_arm_a_decision`
pins the full `trade_service._DEFAULT_CFG` key set and fails by name when it
moves. That is deliberate: a new knob is a new way for arm A to stop being the
pre-wave engine. Add its kill value to `MODEL_A_PROFILE` and re-capture the
golden, or record in the scope block why it is excluded — then update the
inventory. Never re-capture the golden just to make a failure go away.

### Dismiss cooldown (D-067) — `backend/server.py` session_init + swipe route

| Key | Default | Meaning |
|---|---|---|
| `pass_cooldown_days` | 14.0 | **Hard** exclusion window for a dismissed suggestion (the UI's "dismiss" is the API's `decision='pass'`). A dismissed `(give, receive)` pair is filtered out of every generation for this many days, and binds **immediately** at swipe time on every service in `sess["trade_svcs"]` — not just at the next `session_init`. Distinct from the `fatigue_*` knobs above, which only demote (floored at `fatigue_floor`) and are what let dismissed cards resurface. **Likes keep their own separate 7-day window** (a like that matured into a match/awaiting is excluded windowlessly by #336's R4). **Set to `7.0` to restore the pre-fix behavior** — this knob is the deploy-free revert, which is why the fix ships without a feature flag. Scope is exact-pair by design, NOT the decline path's near-duplicate suppression (`fatigue_decline_suppress_days`): a dismiss is one cheap swipe at a generated hypothesis, a decline is backing out of a deal a league-mate agreed to. |

### Outlook odds (#169) — `backend/outlook/`

Numeric knobs for the playoff/championship-odds pipeline (gated by `outlook.odds`; string source select is the `FTF_OUTLOOK_STRENGTH_SOURCE` env var). **The roster-value→points calibration (`outlook_mean_points`/`outlook_points_per_value_sd`/`outlook_sigma_default`) is a documented heuristic, not an empirically fit model — flagged for operator tuning via the offline backtest scaffold in `test_outlook_odds.py`.**

| `pass_cooldown_start_epoch` | 1787005800.0 (2026-08-17T22:30:00Z) | **Legacy-dismiss amnesty** (D-067, operator 2026-08-17). Dismisses recorded **before** this instant are exempt from the cooldown and can be re-presented immediately: they predate decline-reason capture (D-066, backend live `2026-08-17T22:22:56Z`) and therefore carry no reason, so applying the avoidance rule to them would suppress taps the user was never given the chance to explain. Unix epoch seconds. **Scoped to dismisses only** — likes are unaffected. **0 disables the amnesty.** ⚠️ The default sits just past the BACKEND landing; the reason tiles are a MOBILE change, so users cannot produce reasoned dismisses until a build carrying them reaches testers — raise this key to that moment (one `PUT /api/admin/config` call, no deploy) if pre-build dismisses should also be amnestied. |
| Key | Default | Meaning |
|---|---|---|
| `outlook_mean_points` | 110.0 | Assumed league-average weekly fantasy score — the affine anchor for `RosterValueStrength` μ. **Heuristic.** |
| `outlook_points_per_value_sd` | 12.0 | Weekly points added per 1 SD of (cross-league) starting-lineup roster value — `RosterValueStrength` slope. **Heuristic.** |
| `outlook_sigma_default` | 25.0 | Default weekly-score standard deviation when not derived from played games. **Heuristic.** |
| `outlook_trailing_min_weeks` | 3.0 | K — minimum completed weeks before `TrailingScoresStrength` is usable and `auto` switches off roster-value (1..K-1 uses `blended`). |
| `outlook_sim_count` | 10000.0 | Monte-Carlo season simulations per request. |
| `outlook_seed` | 0.0 | Config seed XORed with `stable_hash(league_id)` for the deterministic RNG (same league+seed → identical odds). |
| `outlook_bye_multiplier_enabled` | 0.0 | Gate for the EVALUATED per-week bye-week μ multiplier (`backend/outlook/bye_multiplier.py`) — **`pipeline.py` does not read this key; it exists only as the wiring point for a future ship decision.** See [feedback/items/169-outlook-league-summary/bye-week-multiplier-2026-08-09.md](feedback/items/169-outlook-league-summary/bye-week-multiplier-2026-08-09.md) for the backtest verdict before ever flipping this. |
| `outlook_bye_multiplier_scale` | 1.0 | Linear scale from starting-lineup value-fraction-on-bye to the μ multiplier haircut (`mu_multipliers()`). **Heuristic, unshipped.** |

### Fit-congruence signal weighting (no flag) — `trade_service._DEFAULT_CFG`, DB-seeded

Deck swipes feed personal Elo through `RankingService.record_trade_signal` at `trade_k_like` / `trade_k_pass`. Those K-factors treat every swipe as a pure valuation statement, and the flat half-K pass discount was the only acknowledgment that **"don't want" ≠ "don't value"** — a rebuilder passing a fairly-priced vet was sinking that vet on their board for a *window* reason.

These two keys scale that K by how **surprising** the swipe is given the user's window. The congruence test reuses the existing lane machinery verbatim: `trade_service.signed_lane_shift()` — the value-weighted mean now/future lean of what changes hands (received counts +, given counts −), signed by the user's resolved window direction (declared `team_outlook` → #8 roster seed → none), on CONSENSUS values — against the same `lane_shift_frac` (0.10) threshold `classify_lane` uses. The signed shift is stamped on every v2-orchestrated card at generation (`TradeCard.lane_shift`, in-process only, never serialized) because the swipe route holds neither the resolved outlook nor a consensus value fn. `lane` itself is **not** sufficient: its `"value"` bucket collapses window-neutral and strongly anti-window cards, and the anti-window swipe is the signal this weights hardest.

| Key | Default | Meaning |
|---|---|---|
| `fit_k_explained_mult` | 0.4 | **Fit-explained** — the window already predicted the swipe: a *like* on a window-congruent card (`lane_shift ≥ lane_shift_frac`), or a *pass* on an anti-window one (`lane_shift ≤ −lane_shift_frac`). Discounted: it is a weaker valuation statement than it looks. **Setting this to 1.0 is the kill switch** — with `fit_k_defying_mult` at its 1.0 default the engine is byte-identical to pre-feature behavior, deploy-free via `PUT /api/admin/config/fit_k_explained_mult`. There is deliberately **no feature flag**. |
| `fit_k_defying_mult` | 1.0 | **Fit-defying** — the swipe contradicts the window: a *pass* on a window-congruent card, or a *like* on an anti-window one (the rebuilder who wants the vet anyway — the strongest board signal the deck produces). Full baseline K. **Deliberately not boosted above 1.0** without data to justify it; raising it is a live experiment, not a default. |

Neutral cases weight at exactly 1.0 and are byte-identical to pre-feature behavior: no window direction (unset / `not_sure`), `|lane_shift| < lane_shift_frac`, no consensus value on the table, and FB-46 client-echo card reconstructions (which carry no stamped shift). The multiplier is applied to **both** the in-memory `record_trade_signal(fit_mult=…)` call and the persisted `save_trade_swipes` `k_factor` — `_compute_elo` replays the DB rows, so the two must carry the same K. Out of scope by design: `record_disposition_signal` (match accept/decline are deliberate decisions, not deck reflexes) and bad-trade flags.

### Verdict bands (backlog #6 / #27) — `trade_service._DEFAULT_CFG`

| Key | Default | Meaning |
|---|---|---|
| `verdict_fair_max_gap_pct` | 0.08 | `classify_verdict` band cut: gap ≤ this (as a fraction of the larger side) → `fair` |
| `verdict_lopsided_min_gap_pct` | 0.20 | `classify_verdict` band cut: gap ≥ this → `lopsided`; else `slight` |

These were introduced by backlog #6 (verdict banner) and are **vendored into `_DEFAULT_CFG` by backlog #27** (open calculator) when #6 is not yet integrated — the public `/api/calc/score` calls `classify_verdict`, so it shares the exact band thresholds in-app trade cards use. If #6 lands first, the keys already exist and #27's copy is a harmless duplicate to drop on merge.

### Mock-draft CPU drafters (draft-extensions W2) — `mock_draft_service._DEFAULT_CFG`

Read through `mock_draft_service._c`, which overlays `database.get_config()` on the module defaults. **Deliberately NOT seeded into `_MODEL_CONFIG_DEFAULTS`:** these belong to a feature whose calibration gate is closed, so the code default is the single source until an operator inserts a row. All three values are snapshotted into `mock_drafts.settings.noise` at create, so retuning them can never change an in-flight mock.

| Key | Default | Meaning |
|---|---|---|
| `mock_max_reach_slots` | 3.0 | Structural cap on how many consensus rank slots a positional **need** can pull a player up: `need_bonus ≤ outlook_alpha(persona) × severity × this`. A **product cap, not a fitted parameter** — fitting it alongside the noise is unidentifiable at the corpus sizes available. **W2e narrowed its role to the need term only:** it is no longer any part of the support bound on a reach (that is the round-tiered policy below), and the round cap dominates it because the need term is scored over the already-truncated candidate set. |
| `mock_bpa_prob` | 0.10 | First of the **two** fitted parameters of the W2b mixture (re-fitted in W2d on the interleaved fit block; W2c's was 0.20, W2b's 0.50): the probability that a CPU pick is the strict board pick (`argmin(rank − need_bonus)`, no idiosyncrasy). The complement takes the reach branch below. |
| `mock_reach_decay` | 0.70 | Second fitted parameter (unmoved by the W2d re-fit; W2b's was 0.95): the reach branch's per-slot survival ratio — reaching one slot further is `this` times as likely, i.e. `P(reach = d) ∝ this ᵈ`, truncated at the round's reach cap. Implemented as a per-candidate `Gumbel(0, −1/ln(this))` draw, which by the Gumbel-max identity makes the reach depth exactly geometric. |

⚠️ **The two defaults above are the recorded W2d fit, but the model is NOT validated — and W2e moved the support bound underneath them without re-fitting.** They were fitted when a single global candidate window truncated every reach at 11.5 slots; since W2e that truncation is the round-tiered policy below. `CPU_MODEL_VALIDATED` is `True` by operator override while the statistical verdict remains FAILED, so **a deliberate re-fit + re-gate is owed before either value means anything.** Read [mock-calibration-2026-08d.md](plans/draft-extensions/mock-calibration-2026-08d.md) — especially §6, on why the residual localised in the support bound — and [build-w2e.md](plans/draft-extensions/build-w2e.md) before touching either key.

#### The round-tiered reach policy (W2e) — product policy, not a tuning constant

How deep, and how often, a CPU drafter may deviate from the consensus board. **The operator's rule, verbatim:** *"For the first round, I expect no more than reaching 3 picks (and no more than 3 times a round). For the second round 5 picks (and only 2 times a round). For the third and fourth 15 picks (limit of 5 times a round)."*

| Round | Max reach (consensus slots) | Max reaching picks per round, **league-wide** |
|---|---|---|
| 1 | 3 | 3 |
| 2 | 5 | 2 |
| 3, 4, and every later round | 15 | 5 |

Held in `mock_draft_service` as `MOCK_REACH_CAP_BY_ROUND` / `MOCK_REACH_CAP_LATE` and `MOCK_REACH_BUDGET_BY_ROUND` / `MOCK_REACH_BUDGET_LATE`, read through `round_reach_cap(round)` / `round_reach_budget(round)`.

**It is deliberately NOT a `model_config` key and NOT operator-tunable at runtime**, even though it sits beside three keys that are. It is the model's *support bound*: a row in `model_config` could silently invalidate the calibration verdict the gate records, and a support bound that moves without a re-gate is exactly the failure amendment 2 exists to prevent. Changing either table is a **product decision that requires a re-gate**.

Semantics, as implemented:

- **Reach** — a pick whose 0-based position in the remaining consensus pool is ≥ 1, i.e. it passed over at least one better-valued available player. A pick at best-player-available is never a reach.
- **The cap truncates** the candidate set for that round, so the geometric reach law is truncated at the round's cap. A CPU can never reach further than its round's cap, at any parameter.
- **The budget is per round and shared across every CPU team** (not per team). Once a round has spent it, every remaining CPU pick in that round is **strict best-available — the need term included**, because that is what "strict best available" means. It is consumed in pick order and re-derived from the persisted picks on resume, so a replayed mock spends it identically and `INV-10` (same seed ⇒ byte-identical draft) still holds.
- **The user is outside it.** A human's own reach neither consumes the budget nor is constrained by it; the policy describes how the bots draft.

The CPU **candidate window** `K` (`mock_draft_service.MOCK_CANDIDATE_WINDOW`) is *not* a `model_config` key either, and since W2e it is a **performance bound only** — the width of the pool head a CPU scans, so the scan is `O(K)` rather than `O(pool)`. W2d found that at `K = 12` it was doubling as the *binding* support bound ([08d §6](plans/draft-extensions/mock-calibration-2026-08d.md)); W2e replaced it in that role with the round tier above and widened it **12 → 24**, comfortably clear of the deepest round cap (15, needing 16 candidates), so it never binds the distribution at any round. Pinned by `test_w2_04b_the_candidate_window_is_never_the_binding_constraint`.

The persona weight itself is **not** a new key — it is `outlook_alpha(persona_outlook)`, the existing `outlook_alpha_*` map above, reused verbatim.

---

## Offline eval harness (F8, `backend/eval/` — operator tooling, unflagged)

No feature flag and no `model_config` keys: the harness is a read-only CLI/library (`python3 -m backend.eval.replay`) that never touches product behavior. Its knobs are env vars (all optional), read at import/call time:

| Var | Used by | Purpose |
|---|---|---|
| `EVAL_ESS_MIN` | `backend/eval/replay.py` | Effective-sample-size gate (default **100**). Any replay run whose Kish ESS falls below it has its verdict labeled `UNRELIABLE` — the numbers are still printed, never silently capped. Rationale: at ESS≈100 a 95% CI on a ~10–20% like-rate already spans ±6–8pp, wider than any plausible ranking effect. CLI `--ess-min` overrides per run. |
| `EVAL_BOOTSTRAP` | `backend/eval/replay.py` | Cluster-bootstrap resample count for CIs (default **1000**; clusters = deck jobs). CLI `--bootstrap` overrides. |
| `EVAL_RUNS_DIR` | `backend/eval/persistence.py` | Directory for the append-only `runs.jsonl` run records. Default `data/eval_runs/` (inside the already-gitignored `/data/`). Tests point it at a tmp dir. |

Fixed estimator constants (in `backend/eval/replay.py`, changed only by code review because they change what the numbers mean): propensity-tilt clip bounds `TILT_MIN=0.5` / `TILT_MAX=2.0` (clip **count** is reported on every run), exposure-curve floor `EXPOSURE_FLOOR=0.02`, Laplace `+1/+2` smoothing on the served→viewed curve.
