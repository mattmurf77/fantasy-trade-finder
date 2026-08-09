# Config Reference

*Jump via the TOC — read sections, not the file.*

Environment variables, feature flags, and `model_config` keys. Keep in sync when adding any of the three (see [docs/CLAUDE.md](CLAUDE.md)).


## Table of Contents

- [Environment variables](#environment-variables)
- [Feature flags](#feature-flags)
- [Flags — Player profiles (#17)](#flags-player-profiles-17)
- [Flags — Trade engine flags (Tier 1–2, landed — all currently **true** in `config/features.json`)](#flags-trade-engine-flags-tier-12-landed-all-currently-true-in-configfeaturesjson)
- [Flags — Trade engine flags (Tier 3, flag-gated — landing imminently, default **false**)](#flags-trade-engine-flags-tier-3-flag-gated-landing-imminently-default-false)
- [Flags — Owned draft picks in calculator + suggestions (#158/#170/#171 — ship dark)](#flags-owned-draft-picks-in-calculator-suggestions-158170171-ship-dark)
- [Flags — Directional outlook weighting (feedback #175 — ships dark)](#flags-directional-outlook-weighting-feedback-175-ships-dark)
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
- [Flags — API observability (2026-08-09, ships **ON**)](#flags-api-observability-2026-08-09-ships-on)
- [`model_config` keys](#model_config-keys)
  - [Analytics platform (P0, [ADR-007](adr/adr-007-first-party-analytics-experimentation.md))](#analytics-platform-p0-adr-007)
  - [Trios → tier calibration + variety — `ranking_service._DEFAULT_CFG`, DB-seeded](#trios-tier-calibration-variety-ranking_service_default_cfg-db-seeded)
  - [Consensus seed blend (#145/#148) — `backend/data_loader.py`, DB-seeded](#consensus-seed-blend-145148-backenddata_loaderpy-db-seeded)
  - [Trade engine v2 (Tier 1) — `trade_service._DEFAULT_CFG`](#trade-engine-v2-tier-1-trade_service_default_cfg)
  - [Tier 2 — marginal valuation + outlook blend](#tier-2-marginal-valuation-outlook-blend)
  - [Tier 2 — deck ordering, diversification, fuzzy matching](#tier-2-deck-ordering-diversification-fuzzy-matching)
  - [F3 — fatigue & durable suppression (flag `deck.fatigue`)](#f3-fatigue-durable-suppression-flag-deckfatigue)
  - [F5 — trade-taste vectors (flag `deck.taste_vectors`)](#f5-trade-taste-vectors-flag-decktaste_vectors)
  - [F7 — exploration slots & archetype audition (flag `deck.exploration`)](#f7-exploration-slots-archetype-audition-flag-deckexploration)
  - [F9 — first-session win engineering (flag `deck.first_session`)](#f9-first-session-win-engineering-flag-deckfirst_session)
  - [F6 — learned acceptance heads × V-vector (flag `deck.value_model` — **dark**)](#f6-learned-acceptance-heads-v-vector-flag-deckvalue_model-dark)
  - [Tier 3 (flag-gated, landing imminently)](#tier-3-flag-gated-landing-imminently)
  - [Outlook odds (#169) — `backend/outlook/`](#outlook-odds-169-backendoutlook)
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
| `FTF_TESTER_ALLOWLIST` | `backend/experiments.py` | Comma-separated experiment unit ids (account ids and/or `device:<id>` pseudo-ids) that resolve the `is_tester_allowlist` targeting attribute to true. **Unioned with `config/tester_allowlist.json`** (JSON array, git-deployable — required in practice: Render does not apply `render.yaml` envVars to a dashboard-created service). Read on the engine's 60s cache refresh; not `model_config` because its value column is a Float. Powers operator-targeted rollouts (e.g. `onboarding_v2_rollout`, `aggregate_tier_labels`, `trades_home_inline`). |
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

Pre-existing flags (sprint UX + trade-math): see `config/features.json` directly — they are self-describing (`swipe.*`, `tiers.*`, `trades.*`, `league.*`, `invite.*`, `mobile.*`, `profiles.*`, `landing.*`, `trade_math.*`).

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
| `calc.open_calculator` | Backlog #27 ([prd](../staged-work/backlog-21-30/prds/27-open-trade-calculator.md)): gates the **public, no-session** open-trade-calculator compute routes `POST /api/calc/score` + `GET /api/calc/values` (both 404 when off). The static `web/calculator.html` SEO page ships **unflagged** (like `faq.html`); when the flag is off its Score button degrades to a "coming soon" state via the self-fetched `/api/feature-flags`. No new endpoint config keys — reuses the backlog #6 `verdict_*` `model_config` keys for band thresholds so the public calc and in-app trade cards agree on the same trade. Default **false**. |

## Flags — Owned draft picks in calculator + suggestions (#158/#170/#171 — ship dark)

| Flag | Default | Gates |
|---|---|---|
| `market.trade_capture` | false | Market-data readiness (PRD #43 Phase-1 data foundation / #26): capture executed Sleeper league trades — public v1 `GET /league/<id>/transactions/<week>`, legs 1–18, `type=trade` + `complete` only — into the `sleeper_trades` table during `session_init`'s background daemon (`backend/sleeper_trades_service.py`). Capture ONLY (raw payload retained, idempotent on `transaction_id`); no scoring, no aggregation, no UI. Best-effort and off the request path; Sleeper numeric league ids only. Off ⇒ no fetch, no rows. Currently **true** in `config/features.json` (data must accumulate before any observed-market feature can be built — same "start logging now" logic as #57); the flag is the kill switch. |
| `market.movers` | false | **#243 "Market pulse" strip** — gates `GET /api/market/movers`: top risers/fallers by trailing-window % change of FTF community value (`player_value_history` `consensus_value` snapshots; read-only over the data #57 already accumulates, via `database.load_value_movers_window`). Off ⇒ the route 404s and the mobile `MarketPulseStrip` (League home, below Explore) renders nothing. Currently **true** in `config/features.json`; the flag is the kill switch. Empty-safe while history is thin — flipping it on before snapshots have accrued shows nothing rather than erroring. |
| `picks.owned_sync` | false | Revives the per-league owned-pick sync (`database.sync_draft_picks` on the session_init daemon for Sleeper; `server._sync_mfl_owned_picks` at MFL link/import) + normalizes MFL picks into `draft_picks` + enriches `GET /api/league/picks` with `pool_value`/`label`/`picks_supported` + the mobile In-league calculator's owned-pick rows. Off ⇒ no owned-pick rows written or surfaced (byte-identical to today; the sync was dead code since the trade-engine-v2 rebuild). ESPN leagues never write rows (`picks_supported:false`). |
| `picks.rank_year_labels` | false | **#207 (2026-08-05), currently `true`.** Serves the 12 generic pick rungs on `GET /api/rankings` + `GET /api/trio` with a **year-explicit** label ("2026 Early 1st" when the active league's rookie draft hasn't happened; "2027 Early 1st" once it has) and a `years_out`-discounted `pick_value`, resolved from the league row's cached `draft_status` (`backend/draft_status.py`). Rung ids, universal-pool membership, board Elo and rank are untouched — Option A "relabel, don't add/remove" ([plan](feedback/items/207-rookie-draft-detection/plan.md)). **Fail-safe:** `unknown` / never-checked reads as NOT drafted, i.e. current-year picks stay visible. Off ⇒ today's year-less `"Early 1st Round Pick"` labels and undiscounted values, byte-identical. Detection + its caching run regardless of this flag (the flag gates only what is served). |
| `trade.picks_in_pool` | false | Injects each team's owned picks (capped `picks_pool_cap`, top-N by `pool_value`) as priced `position="PICK"` pseudo-assets into the suggestion candidate pool in `_run_trade_job`, so a generated trade can send/receive a pick (#170/#171). **Data inclusion only** — the engine already prices PICK assets (`dynasty_value`); scoring/weighting is unchanged. Off ⇒ no pick ever appears in a suggestion. `model_config`: `picks_pool_cap` (6). |
| `trade.asset_ideas` | **true** | **#172/#189 follow-up** — gates `POST /api/trades/asset-ideas` (asset-centric Upgrade / Lateral / Downgrade idea groups for one pinned asset, `TradeService.generate_asset_ideas`) + the mobile grouped-ideas panel on TradesScreen (rendered when exactly ONE finder target is pinned; the deck flow is untouched). Off ⇒ the route 404s and the panel never renders. Default ON (operator ask); this flag is the kill switch. `model_config`: `asset_ideas_lateral_band` (0.10), `asset_ideas_group_cap` (6). |
| `outlook.odds` | false | **#169** — gates `GET /api/league/outlook` (playoff/championship odds pipeline, `backend/outlook/`). Off ⇒ the route 404s and nothing else changes. Source selection via `FTF_OUTLOOK_STRENGTH_SOURCE`; numeric knobs under `model_config` (`outlook_*`). Preseason payloads are flagged `beta`. |

## Flags — Directional outlook weighting (feedback #175 — ships dark)

| Flag | Default | Gates |
|---|---|---|
| `trade.outlook_direction` | false | **#175** — steers the deck by the USER's resolved outlook (declared `team_outlook` → #8 seed → None), via `outlook_direction_mult` applied in `_generate_trades_v2` AFTER all gates to every v2-orchestrated card (divergence v2/v3 + consensus). Reuses the lane machinery: the card's value-weighted now-lean shift (received − given, `classify_lane`'s exact shift, on CONSENSUS values). Rebuild-side (`rebuilder`/`jets`): shift > 0 (acquiring win-now/older production) ⇒ composite `×= max(0.05, 1 − outlook_dir_penalty·shift)`; shift < 0 (acquiring future capital — younger players, picks) ⇒ `×= 1 + outlook_dir_boost·(−shift)`. Plus the **~1-year-gap rule**: primary (highest-consensus-value) give is a player and the primary return is an older player beyond `outlook_dir_age_tolerance` years, with no pick / tolerance-younger return component worth ≥ `outlook_dir_rescue_frac` of the primary give ⇒ `×= outlook_dir_age_gap_mult` (**near-exclusion by penalty, not a hard filter** — a genuinely lopsided-value win can still surface). Contend-side (`championship`/`contender`): ONLY the mild symmetric mirror `×= 1 + outlook_dir_contend_weight·shift`, no age-gap rule. `not_sure`/None ⇒ no effect. Cards carry the in-process `outlook_dir` multiplier (QA record, not serialized). Off ⇒ composites byte-identical. `model_config` keys: `outlook_dir_penalty` (3.0), `outlook_dir_boost` (1.0), `outlook_dir_contend_weight` (0.5), `outlook_dir_age_tolerance` (1.0), `outlook_dir_age_gap_mult` (0.15), `outlook_dir_rescue_frac` (0.5). |

## Flags — Send in Sleeper (flagged beta)

| Flag | Default | Gates |
|---|---|---|
| `trade.send_in_sleeper` | false | ⚠️ **ToS-adverse.** `POST/GET/DELETE /api/sleeper/link` + `POST /api/trades/propose` (all 404 when off) — sends trades through Sleeper's *undocumented* private write API (`propose_trade` GraphQL mutation). Requires `SLEEPER_TOKEN_KEY`. Adapter: `backend/sleeper_write.py`; token store: `sleeper_credentials`. Capture + ToS/risk (C4): [runbook](plans/sleeper-write-capture-runbook.md). |

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

## Flags — Onboarding & conversion redesign (ships dark; [plan](plans/onboarding-conversion/plan.md) v2.1)

**Master/individual semantics:** every `onboarding.*` feature is live iff **`onboarding.v2` AND its own flag**. `onboarding.v2` false = whole redesign dark regardless of individual flags (kill switch). Individual flags allow feature-by-feature enablement/rollback. `analytics.client_events` is deliberately **outside** the master — it gates instrumentation only (tracking plan v2 §S2) and must run against the *current* flow first to capture the pre-redesign baseline.

| Flag | Default | Gates |
|---|---|---|
| `analytics.client_events` | false (true in `features.json` — baseline capture) | `POST /api/events` ingestion (404 when off) + client event SDK emission (`mobile/src/api/events.ts`). Instrumentation only; no UX change. |
| `onboarding.v2` | false | Master kill-switch for all `onboarding.*` features below. |
| `onboarding.landing` | false | Item 5 — username-first landing on SignInScreen (primary username field, quiet Apple re-entry link, not-found copy, Sleeper-down demo escape). First consumer of `landing.try_before_sync`. |
| `onboarding.trades_first` | false | Item 4 — trades-first hook: pregen at auth-return, skeleton/streamed first-run deck, first-run chrome collapse, provenance chip, identity-confirm strip. |
| `onboarding.league_autoskip` | false | Item 6 — single-league LeaguePicker auto-skip + error fallback. |
| `onboarding.quickset_prompt` | false | Item 7 — inline prompt card (first pass after swipe 2, else 3 swipes) + onboarding-mode QuickSet (suppress finish-prompt, return to Trades, force deck regen, diff banner). |
| `onboarding.apple_save_moment` | false | Item 8 — save-moment Apple prompt (honest framing, decline policy, one auto-prompt per save-moment class), persisted-username silent re-init, session-2 non-modal banner. |
| `onboarding.share_sheet` | false | Item 8 rider — native share sheet on liked trade card (user-initiated; appears only after the Apple prompt resolves). |
| `onboarding.rank_routing` | false | Item 9 — RankHome chooser demoted to "More ways to rank", Rank tab defaults to QuickSet, deck-exhausted state → trio entry. |
| `onboarding.demo_bridge` | false | Item 10 — persistent "See this for YOUR team →" bar in demo mode + redraft "Dynasty values shown" label/segment tag. |
| `onboarding.guided_layer` | false | v2.1 guided layer — swipe-gesture hint (card 1), ≤4 coach marks, celebration beats (first like / first QuickSet save). |
| `onboarding.keep_warm` | false | Item 3 — server-side keep-warm affordances for the Render cold-start cron ping. |

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
| `growth.rating_prompt` | false | `StoreReview` rating prompt at demonstrated-satisfaction moments (tier save, Nth liked trade, first Sleeper send); once/version, 3/365 budget; unhappy paths keep routing to feedback (07/prd-02). |
| `account.data_export` | false | Download-my-data export (the deletion matrix as export manifest), surfaced beside Delete in Settings → Account (06/prd-02; GDPR Art. 20). |
| `account.sleeper_disconnect` | false | "Disconnect Sleeper sending" row in Settings → Account (status from `GET /api/sleeper/link`, wired to `unlinkSleeper()`) — the control the privacy policy already promises (09/prd-01, 06/prd-04). |
| `account.settings_v2` | false | Settings IA regroup to five frequency-ordered groups, Testing section gated to TestFlight builds, instant ranking-method preference apply (06/prd-04). |
| `profiles.user_toggle` | false | Per-user public-profile visibility opt-out under `profiles.public_pages` — the global flag alone never publishes a user who opted out (06/prd-04). |
| `auth.persistent_sessions` | false | Durable sessions for account-only (Apple) users — refresh-token model with server-side revocation, replacing the 4h in-memory dict (06/prd-03; the codebase's own "P3"). |
| `league.rookie_board_entry` | false | Mounts the fully-built-but-orphaned RookieDraftBoardSheet as a League Explore row during draft season (07/prd-04 item 2). |
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
| `draft.mock` | false | **W2** — the FTF-native mock draft: all four `/api/mock-draft` routes ([api-reference § Mock draft](api-reference.md#mock-draft-flag-draftmock)) and the mobile mock surface. Effective gating is `draft.room` **AND** `draft.mock`; it is independent of `draft.live_poll` (the mock never polls), `draft.mfl` and `picks.slot_values`. **Off ⇒ every mock route 404s `feature_disabled` before any session work, the `mock_drafts` table is never touched, and no other route's response changes.** ⚠️ **This flag stays OFF beyond the usual lands-dark convention.** W2's calibration gate FAILED and has stayed failed through three re-runs ([mock-calibration-2026-08d.md](plans/draft-extensions/mock-calibration-2026-08d.md)) — the specified noise model cannot reproduce the reach distribution of a real rookie draft at any value in the specified grid, on the hold-out or on an independent corpus — so the plan's W2 abort criterion **cut the CPU-bot mock**. `mock_draft_service.CPU_MODEL_VALIDATED` is `False`, and with the flag ON the create route answers the typed-empty `{empty:true, reason:"cpu_model_unvalidated"}` rather than serving unvalidated bots. Flipping it on is not a release decision until that gate is re-run green against a re-specced model. |
| `picks.assign` | false | **draft-extensions W3 M-A/M-B** — user-asserted pick **ownership** ([plan §6 REVISED](plans/draft-extensions/plan.md), [ADR-010](adr/adr-010-user-asserted-pick-ownership.md), delivered contract in [build-w3-ma-mb.md](plans/draft-extensions/build-w3-ma-mb.md)). Gates the three assignment routes (`GET`/`PUT /api/league/pick-assignments`, `POST …/order`) **and** the ESPN branch of `GET /api/draft/board`. **Why it exists:** ESPN has no rookie-draft concept (operator ruling), so an ESPN dynasty league's rookie draft necessarily runs off-platform and there is **no draft object to read, now or ever** — the league's own members are the only possible source of who owns which pick. **ON ⇒** the routes answer, and an ESPN board is either `notice.picks_not_assigned` on an `unavailable` payload (nothing assigned) or a real `upcoming` board built entirely from the grid with `picks: []` and **zero platform egress**. **OFF ⇒** all three routes 404 `feature_disabled` before any session work, the ESPN board is the byte-identical `platform_unsupported` payload it is today, the three new `draft_picks` provenance columns stay unwritten, and every existing read site is unchanged because `load_draft_picks` **defaults to `source='platform'`** (NULL reads as platform, so no backfill runs) — that default IS the containment. **No user-entered values, ever:** price comes only from the shipped `pick_pool_value`/`compute_pick_value` and every route 400s `values_not_accepted` on any value field, which is what buys the conservation bound (`rounds` clamped 1..`ROOKIE_MAX_ROUNDS` server-side). Asserted picks do **not** enter trade math under this flag — that is the separate `picks.assign_tradeable` kill switch (M-C, **not yet built**), deliberately two flags so pick math can be killed without destroying the rows a league typed in. Ship-by/kill-by: review 2026-11-08. |
| `picks.assign_tradeable` | false | **draft-extensions W3 M-C** — **trade-math activation** for asserted picks ([plan §6.4 + operator decision 4](plans/draft-extensions/plan.md), [ADR-010](adr/adr-010-user-asserted-pick-ownership.md), delivered contract in [build-w3-mc.md](plans/draft-extensions/build-w3-mc.md)). The **second, deliberately separate** switch: `picks.assign` owns entry, storage and the ESPN Draft Room; this one owns whether those rows **price**. Killing it never destroys the rows a league typed in. **ON ⇒** all SEVEN read sites read the platform ∪ asserted union instead of `load_draft_picks`' platform-only default — S1 `/api/league/picks` + `/api/trade/evaluate`, S2 `_power_picks_by_owner` + `_user_pick_share`, S3 `_owned_pick_assets`/`_inject_owned_picks` + the trade job's opponent pick shares, S4 `_roster_eveners` — so assigned picks behave **exactly like any other league's picks**, including generated suggestions and one-tap eveners (operator decision 4 overrides both lenses' recommendation to hold S3/S4; S1→S4 survives as a BUILD SEQUENCE, not release gates). It also flips the engine guard `_owned_picks_available` from a platform test to a data test for ESPN (all three of its conjuncts — `trade.picks_in_pool`, not-demo, platform — are preserved), makes `picks_supported` a data test (`platform != "espn" or the league has assigned rows`), and puts `source: "platform" | "user"` + `season` on every priced pick payload (the label **"Member-entered — not verified with ESPN"** and the `{leagueId, season, focusPickId}` correction link are registered in [cross-client-invariants.md](cross-client-invariants.md)). **OFF (default) ⇒** every one of those payloads is byte-identical and asserted rows reach no trade math, no power rankings and no suggestion. In BOTH states contested/orphaned slots leave the priced union by **row filter**, never by nulling `pool_value`. The §6.8 adoption / contested-rate thresholds are monitoring and rollback triggers, not ship gates. Ship-by/kill-by: review 2026-11-08. |
| `draft.manual_picks` | false | **draft-extensions W3 M-D** — **live offline pick recording** ([plan §6.5](plans/draft-extensions/plan.md), [ADR-010](adr/adr-010-user-asserted-pick-ownership.md), delivered contract in [build-w3-md.md](plans/draft-extensions/build-w3-md.md)). The **third, separate** switch: `picks.assign` owns ownership entry/storage/the room, `picks.assign_tradeable` owns whether asserted rows price, this one owns whether the app can record **what happened** during a real off-platform draft. Storage is the new `recorded_picks` table ([data-dictionary](data-dictionary.md#recorded_picks)) — never `draft_picks`, never `leagues.draft_status*`. **ON ⇒** `POST /api/league/recorded-picks` (batch, idempotent on `(league_id, season, overall)`) and its `/void` companion answer, and `GET /api/draft/board`'s ESPN branch projects live `recorded_picks` rows into `picks[]` (subtracting them from `undrafted[]`) through the SAME renderer every other platform's board uses. **OFF (default) ⇒** both routes 404 `feature_disabled` before any session work, `recorded_picks` stays unwritten, and the ESPN board reads **zero rows** from it regardless of what the table holds — the flag gates the read as well as the writes, so a row left over from a prior on/off flip can never leak into a flag-off board. Off-by-one recovery is **manual-cursor-only, no auto-shift**: a missed pick is fixed by tapping the correct slot directly, never by an "insert here and shift everything after" operation. Ship-by/kill-by: review 2026-11-08. |
| `draft.tab` | false (**ships TRUE**) | **The seasonal on/off switch for mobile's Draft tab** (operator decision 2026-08-06: *"it should literally just be set to seasonal. So a flag we turn on and off to display the tab. Right now it should be on for all."*). **The operator flips this by hand each year — it is never computed.** Client-only: no backend route reads it. **ON ⇒** the bottom bar carries the Draft tab (third: **Rank · Acquire · Draft · Matches · League**, testID `tab.draft`) and it lands on the **active league's** Draft Room. **OFF ⇒** four tabs. `DraftRoom` is reachable either way through the root stack (the League tile, the Acquire mode strip's Draft chip) and the canonical deep link `app/league/draft-room`. This **replaces** the per-league qualification predicate the tab shipped with (`draft_status == 'not_drafted' && draft_status_confidence == 'high'` over an AsyncStorage snapshot that only converged on the NEXT launch — it hid the tab from operators whose leagues genuinely qualified, on the first run after a storage-key bump). There is no chooser: with the tab always on there is nothing to choose between, and the Draft Room renders every state honestly (drafted ⇒ recap, not-drafted ⇒ upcoming, ESPN ⇒ unsupported, no league ⇒ its no-league state), so a non-drafting league lands somewhere truthful rather than somewhere empty. Read **imperatively** at TabNav's first mount (`useFeatureFlags.getState()`, never `useFlag`) so a mid-session flag revalidation cannot rewrite the navigator's route array; a flip therefore takes effect on the next launch. |

#### Ship-by / kill-by review convention (07/prd-04)

Dark flags are inventory, not archive. **Every flag dark ≥90 days gets a recorded decision at a quarterly flag review: schedule a canary via the experiments engine, or delete the code path.** "Still thinking" is not a decision — the review's exit criterion is zero flags >90 days old without one. Record the decision as a one-line ship-by/kill-by note in the flag's `features.json` comment block (or the table above). The teardown block's clock starts 2026-07-19.

## Flags — QA / testing surfaces

| Flag | Default | Gates |
|---|---|---|
| `testing.stage_users` | false | `POST`/`DELETE /api/test-users` (`backend/test_users.py`) — synthetic `qa_*` stage-user spawner for onboarding QA. Runtime-flagged kin of `FTF_TEST_MODE` so the operator's phone can hit a prod-shaped build. The flag alone is **not sufficient**: callers must also be on the tester allowlist (`experiments.load_tester_allowlist()` — `FTF_TESTER_ALLOWLIST` env ∪ `config/tester_allowlist.json`), so flipping it on never exposes the surface to real users. Flip only during onboarding QA windows. See [api-reference.md → Test users (QA)](api-reference.md). |

---

## Flags — API observability (2026-08-09, ships **ON**)

| Flag | Default | Gates |
|---|---|---|
| `obs.api_events` | **true** in `config/features.json` (registered default false) | `backend/api_observability.py` — inbound + outbound API event capture into `user_events` as server-fired `api_call`/`api_request` rows (taxonomy: `OBS_EVENT_PROPS` in `backend/analytics_taxonomy.py`; query surface: `GET /api/admin/analytics/apihealth`). Outbound: every external egress chokepoint (Sleeper REST + GraphQL incl. the trade-block/trade-capture bypass sites, ESPN, MFL, Fleaflicker, DynastyProcess CSVs, KTC scrape, Anthropic, Expo push, Apple/Google sign-in verification). Inbound: Flask hooks recording route PATTERN/method/status/latency for `/api/*` (static assets and `/api/events` excluded). Volume policy: errors always, successes 1-in-N (`obs_success_sample_n`); retention `FTF_OBS_RETENTION_DAYS` (30 d). This key is the **kill switch**: OFF ⇒ zero event writes, zero overhead beyond a flag check, byte-identical responses. Per-service redaction rules in `docs/integrations/` are enforced structurally (key denylist + value-shape scrub + prop-spec strip). |

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

### Consensus seed blend (#145/#148) — `backend/data_loader.py`, DB-seeded

Both knobs shape the **baseline consensus seed values** (the DP→Elo pool seeds), applied once at pool build (`_apply_consensus_blend`, inside `_fetch_dynasty_process`). They are **not** live-hot: a change takes effect on the next boot / pool rebuild (the universal pool is built from the live DP CSV once per boot). Editable via `PUT /api/admin/config/<key>`.

| Key | Default | Meaning |
|---|---|---|
| `ktc_blend_weight` | 0.5 | #145 — weight of KeepTradeCut in the consensus seed blend. Per matched player: `value = (1 − w)·dp + w·ktc_on_dp_curve`, where KTC values are **rank-normalized onto the DP value curve** per format (so the value distribution — and hence tier occupancy / the #117 affine calibration — stays DP-shaped while KTC's ordering opinion is imported). **`0` = DP-only kill switch** (with `tep_te_uplift = 1` the seed pipeline is byte-identical to pre-#145 — pinned by `test_ktc_blend.test_blend_off_is_byte_identical`, and weight 0 never even fetches KTC). `1` = KTC ordering only. Unmatched pool players keep pure DP; unmatched KTC players are ignored (pool universe unchanged). See [runbook → KTC consensus blend](runbook.md) for the fragility + kill-switch procedure. |
| `tep_te_uplift` | 1.18 | #148 — TE value multiplier applied to **`sf_tep` TE seeds only** (after the blend). DP's `value_2qb` column is *plain* superflex with no tight-end premium, so plain-SF TE values sit ~25–30% below their 1QB analogs; a 1QB→SF-TEP board copy then demoted TEs. The uplift (calibrated 2026-07-17 so the top-8 `sf_tep` TE seeds clear their 1QB analogs at the default blend weight — KTC's own TEP effect is ≈ +11%, the rest offsets SF's non-QB compression) makes SF-TEP TEs read as *slightly upgraded*, matching the operator's expectation. `1` = off. Pinned by `test_ktc_blend.test_sf_tep_top_tes_beat_their_1qb_seed`. |

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

### Tier 2 — deck ordering, diversification, fuzzy matching

| Key | Default | Meaning |
|---|---|---|
| `diversity_window_days` | 7.0 | Lookback for league-wide impression counts |
| `diversity_user_cap` | 3.0 | Top receive asset already shown to ≥ this many OTHER members → penalize |
| `diversity_penalty` | 0.6 | Ordering-key multiplier for saturated targets |
| `deck_max_per_target` | 3.0 | Intra-deck cap: cards per top receive asset (deck never shrinks below 5) |
| `fuzzy_match_tau` | 0.8 | Min Jaccard similarity per side for a fuzzy mirror match (read inline in `server._fuzzy_match_tau`) |
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

### Outlook odds (#169) — `backend/outlook/`

Numeric knobs for the playoff/championship-odds pipeline (gated by `outlook.odds`; string source select is the `FTF_OUTLOOK_STRENGTH_SOURCE` env var). **The roster-value→points calibration (`outlook_mean_points`/`outlook_points_per_value_sd`/`outlook_sigma_default`) is a documented heuristic, not an empirically fit model — flagged for operator tuning via the offline backtest scaffold in `test_outlook_odds.py`.**

| Key | Default | Meaning |
|---|---|---|
| `outlook_mean_points` | 110.0 | Assumed league-average weekly fantasy score — the affine anchor for `RosterValueStrength` μ. **Heuristic.** |
| `outlook_points_per_value_sd` | 12.0 | Weekly points added per 1 SD of (cross-league) starting-lineup roster value — `RosterValueStrength` slope. **Heuristic.** |
| `outlook_sigma_default` | 25.0 | Default weekly-score standard deviation when not derived from played games. **Heuristic.** |
| `outlook_trailing_min_weeks` | 3.0 | K — minimum completed weeks before `TrailingScoresStrength` is usable and `auto` switches off roster-value (1..K-1 uses `blended`). |
| `outlook_sim_count` | 10000.0 | Monte-Carlo season simulations per request. |
| `outlook_seed` | 0.0 | Config seed XORed with `stable_hash(league_id)` for the deterministic RNG (same league+seed → identical odds). |

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

⚠️ **The two defaults above are the recorded W2d fit, but the model is NOT validated — and W2e moved the support bound underneath them without re-fitting.** They were fitted when a single global candidate window truncated every reach at 11.5 slots; since W2e that truncation is the round-tiered policy below. `CPU_MODEL_VALIDATED` is `False`, the CPU-bot mock stays cut, and **a deliberate re-fit + re-gate is owed before either value means anything.** Read [mock-calibration-2026-08d.md](plans/draft-extensions/mock-calibration-2026-08d.md) — especially §6, on why the residual localised in the support bound — and [build-w2e.md](plans/draft-extensions/build-w2e.md) before touching either key.

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
