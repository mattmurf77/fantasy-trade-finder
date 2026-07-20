# Config Reference

Environment variables, feature flags, and `model_config` keys. Keep in sync when adding any of the three (see [docs/CLAUDE.md](CLAUDE.md)).

---

## Environment variables

| Var | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | `backend/database.py` | Postgres connection string. Unset → SQLite at `data/trade_finder.db` |
| `ANTHROPIC_API_KEY` | `backend/smart_matchup_generator.py` | Enables Claude-assisted matchup selection; unset → algorithmic fallback |
| `FTF_FLAGS` | `backend/feature_flags.py` | JSON dict of process-level feature-flag overrides (wins over `config/features.json`) |
| `CRON_SECRET` | `backend/server.py` | Shared secret (`X-Cron-Secret` header) for all operator endpoints: `/api/cron/*`, `/api/feedback/admin/*`, `/api/admin/*` (config + engine-metrics), `/api/debug/log`, `/api/feature-flags/reload`. In a non-SQLite (prod) env these **fail closed** (503) when it's unset; in SQLite dev an unset secret disables the check. Compared with `hmac.compare_digest`. |
| `FTF_TESTER_ALLOWLIST` | `backend/experiments.py` | Comma-separated experiment unit ids (account ids and/or `device:<id>` pseudo-ids) that resolve the `is_tester_allowlist` targeting attribute to true. **Unioned with `config/tester_allowlist.json`** (JSON array, git-deployable — required in practice: Render does not apply `render.yaml` envVars to a dashboard-created service). Read on the engine's 60s cache refresh; not `model_config` because its value column is a Float. Powers operator-targeted rollouts (e.g. `onboarding_v2_rollout`). |
| `SCORING_FORMAT` | `backend/server.py` | Default scoring format override |
| `SLEEPER_TOKEN_KEY` | `backend/sleeper_write.py` | Fernet key encrypting stored Sleeper write tokens (`trade.send_in_sleeper`). Unset/invalid → the link + propose routes fail closed (503 `sleeper_unconfigured`). Generate with `cryptography.fernet.Fernet.generate_key()`; set in `secrets.local.env` + Render. |
| `FTF_TEST_MODE` | `backend/server.py` + `backend/test_support.py` | `1` → mounts the `/__test__/*` UI-test blueprint and makes `/api/trades/propose` fail closed (599). **Startup-aborts unless `FTF_SLEEPER_FIXTURES_DIR` and `FTF_PLAYERS_CACHE_FILE` are also set.** Never set in prod. See `docs/plans/mobile-testing/` |
| `FTF_SLEEPER_FIXTURES_DIR` | `backend/server.py` `_sleeper_get` | Fixture seam: serve Sleeper responses from canned JSON in this dir (path-keyed, e.g. `user/qa_standard.json`); a miss raises HTTP 599 (fail-closed, never live) |
| `FTF_SLEEPER_RECORD` | `backend/server.py` `_sleeper_get` | `1` → live calls also write scrubbed cassettes into `FTF_SLEEPER_FIXTURES_DIR`. Refuses to start with `FTF_TEST_MODE` (record is deliberately live) or a non-empty fixtures dir |
| `FTF_PLAYERS_CACHE_FILE` | `backend/server.py` | Redirects the players warm-cache path (default `data/.sleeper_players_cache.json`, shared with real dev) so test runs never clobber it |
| `FTF_DP_VALUES_FILE` | `backend/data_loader.py` | Test seam: serve the DynastyProcess values CSV from this local path instead of the live GitHub egress (identical parse path). Under `FTF_TEST_MODE=1` it is **mandatory** (the silent flat-Elo fallback would otherwise reshape the pool mid-test) |
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

### Player profiles (#17)

| Flag | Default | Gates |
|---|---|---|
| `players.profile_pages` | false | `GET /api/players/<id>/profile` (404 when off) and web player-name linkification (`playerLink` in `web/js/app.js` → `web/player.html`). The daily `POST /api/cron/value-snapshot` job that feeds the profiles runs **unflagged** — it is data retention and must collect history before the UI ships. |

### Trade engine flags (Tier 1–2, landed — all currently **true** in `config/features.json`)

| Flag | Tier | Gates |
|---|---|---|
| `trade_engine.v2` | 1 | The entire v2 scorer (`trade_service._generate_trades_v2`): single value space (`elo_to_value`), `package_value_v2`, both-sides surplus gate + harmonic-mean ranking, waiver-slot cost, confidence shrinkage, range-overlap fairness, top-K heap, consensus-basis cards. Off → legacy scorer, byte-for-byte unchanged |
| `trade.marginal_value` | 2 (2.1) | Over-replacement (marginal) valuation inside the v2 pair loop; switches the per-side gate to `min_side_surplus_marginal` |
| `trade.outlook_blend` | 2 (2.2) | Now/future age-curve blend applied to the user's value map (α from `outlook_alpha_*`). Replaces the deleted `team_outlook_multiplier`. v2-only; legacy ignores outlook. **Turned OFF 2026-07-17** (trade-logic interview, "age = tiebreak"): age is already priced into market values, so the engine no longer double-adjusts; window/age return as lane labels + narratives in phase 2 (see [plans/trade-logic-interview-2026-07-17.md](plans/trade-logic-interview-2026-07-17.md)) |
| `trade.likes_you` | 2 (2.3a) | Likes-you queue: inject/boost cards whose mirror a league-mate already liked (`server._inject_likes_you_cards`, cap 3 per deck) |
| `trade.fuzzy_match` | 2 (2.3b) | Jaccard ≥ `fuzzy_match_tau` mirror matching in `database.check_for_match`, guarded so only low-value players (`search_rank ≥ 120`) may differ |
| `trade.thompson_deck` | 2 (A5) | Thompson-sampled deck ordering: one Beta(1+likes, 2+passes) draw per card *shape* (e.g. `2x1`), bounded (0.5, 1.5) multiplier on the ordering key (`server._order_deck`) |
| `trade.deck_diversity` | 2 (A6) | League-wide diversification: penalize cards whose top receive asset saturates other members' recent decks; intra-deck cap `deck_max_per_target` |

### Trade engine flags (Tier 3, flag-gated — landing imminently, default **false**)

| Flag | Gates |
|---|---|
| `trade_engine.v3` | `backend/trade_optimizer.py` — exact per-pair package search + sweetener pass. Off → falls back to v2 (then legacy if `trade_engine.v2` is also off) |
| `trade.three_team` | 3-team cycle trades (kidney-exchange-style clearing) in `trade_optimizer.py` |
| `trade.finder_targeting` | FB-47 ([plan](plans/trade-finder-targeting.md)): `pinned_receive_players` ("I want to acquire X") + counterparty positional-fit ranking (`partner_fit` on cards, `fit_consensus_weight` / `fit_divergence_weight` composite blend). Default **false**; **enabled in `config/features.json` since 2026-07-10** (Phase C: web picker direction toggle + mobile Target-players controls; both clients gate their targeting UI on this flag and render the `partner_fit` line on cards). |
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

### Send in Sleeper (flagged beta)

| Flag | Default | Gates |
|---|---|---|
| `trade.send_in_sleeper` | false | ⚠️ **ToS-adverse.** `POST/GET/DELETE /api/sleeper/link` + `POST /api/trades/propose` (all 404 when off) — sends trades through Sleeper's *undocumented* private write API (`propose_trade` GraphQL mutation). Requires `SLEEPER_TOKEN_KEY`. Adapter: `backend/sleeper_write.py`; token store: `sleeper_credentials`. Capture + ToS/risk (C4): [runbook](plans/sleeper-write-capture-runbook.md). |

### Account auth (account-auth plan P2 — ships dark)

| Flag | Default | Gates |
|---|---|---|
| `auth.accounts` | false | Apple/Google identity anchors ([plan](plans/account-auth-plan-2026-07-11.md) §3-P2): `POST /api/auth/apple`, `POST /api/auth/google`, `GET /api/account` (all 404 when off) + the mobile Sign in with Apple button (SignInScreen) and the Settings linked-identity display. **`DELETE /api/account` is deliberately NOT gated** — in-app account deletion is App Store Guideline 5.1.1(v). Logic: `backend/accounts.py`; tables: `accounts` + `linked_identities`. Before flipping ON: complete the ASC steps in the runbook (Sign in with Apple capability) and update `web/privacy.html` to cover Apple/Google `sub` storage (plan §4 / #114). |
| `auth.email_capture` | false | Plaintext email storage on `accounts` ([spec](business/product/2026-07-17-email-capture-spec.md)). **Off (default)** = pre-spec behavior: Apple's first-auth email is SHA-256-hashed (`linked_identities.email_hash`), plaintext discarded. **On** = Apple first-auth email + the future Settings capture field store to `accounts.email` with `email_consent_at`. **Flip only in the same release as the capture UI + `web/privacy.html` update** — the policy currently states no email addresses are stored. Logic: `backend/accounts.py` (`_email_capture_enabled`, `set_account_email`, `find_or_create_account`). |
| `auth.enforce_verified_writes` | false | Account-auth P1→P3 write-gate mode ([plan](plans/account-auth-plan-2026-07-11.md) §3). **false = GRACE**: unverified sessions' mutating requests are allowed but each logs one `AUTH-GRACE` line (funnel instrumentation — see [runbook](runbook.md)). **true = P3 enforcement**: unverified writes → 403 `verification_required`. Independent of grace, a user_id with a verified controller (`users.verified_via` set) always denies unverified writes, and the hard routes (`POST /api/sleeper/link`, `POST /api/trades/propose`, `POST /api/account/reset-rankings`) always require proof. Flip to true only after the P1 verification funnel looks healthy (plan §2d: ~2–4 weeks). |

### ESPN league linking (Phase 1 — ships dark)

| Flag | Default | Gates |
|---|---|---|
| `espn.link` | false | Read-only ESPN league import via the **unofficial** v3 API ([plan](plans/espn-league-linking-plan-2026-07-11.md)): `POST /api/espn/link`, `GET /api/espn/leagues`, `POST /api/espn/import` (all 404 when off) + the mobile "Link an ESPN league" affordance (LeaguePicker + League tab re-sync). Adapter: `backend/espn_service.py` (crosswalks rosters to Sleeper ids via DynastyProcess `db_playerids.csv`, 24h-TTL in-memory cache, snapshot fallback). Private-league cookie store: `espn_credentials` (Fernet — **reuses `SLEEPER_TOKEN_KEY`**; public leagues need no auth or key). Doubles as the **kill switch**: ESPN blocking reads or an App Store objection → flip off, feature goes fully dark (imported data stays inert in the DB). Before flipping ON: run the live public-league smoke via `python3 -m backend.espn_service <league_id> [season]` (plan §5 — the fixture tests can't see endpoint churn). |

### Multi-platform league linking — MFL / Fleaflicker (Phase 1 — ships dark; [plan](plans/multi-platform-linking-plan-2026-07-17.md))

Both are **zero-auth** public-read imports; no credentials table, no encryption key. Rosters crosswalk to Sleeper ids through the **same** DynastyProcess `db_playerids.csv` cache as ESPN (`espn_service.get_crosswalk`, now exposing per-platform id maps). Each flag gates its own `/api/{platform}/*` routes + the mobile link option and is the vendor/App-Store **kill switch** (imported data stays inert when off).

| Flag | Default | Gates |
|---|---|---|
| `mfl.link` | false | MFL import via the **official** export API: `POST /api/mfl/link`, `GET /api/mfl/leagues`, `POST /api/mfl/import`. Adapter `backend/mfl_service.py` (crosswalk via `mfl_id`; per-league `wwwNN` host resolution; `futureDraftPicks` stored raw in `leagues.platform_future_picks`, **not** engine-wired). Env: optional `MFL_USER_AGENT` (registered-client UA after MFL client registration — see [plan §9](plans/multi-platform-linking-plan-2026-07-17.md)); optional `MFL_COOKIE` for the CLI private path. |
| `fleaflicker.link` | false | Fleaflicker import via the **official** public JSON API: `POST /api/fleaflicker/link`, `GET /api/fleaflicker/leagues`, `POST /api/fleaflicker/discover` (email lookup), `POST /api/fleaflicker/import`. Adapter `backend/fleaflicker_service.py` (crosswalk via `sportradar_id` from roster `externalIds`). No env/keys. |

**Before flipping either ON**, run the live public-league smoke (the fixture tests can't see endpoint churn):
- MFL: `python3 -m backend.mfl_service <league_id_or_url> [year]` (host auto-resolves; e.g. `python3 -m backend.mfl_service 10005 2026` → 100% by id)
- Fleaflicker: `python3 -m backend.fleaflicker_service <league_id>` (or an email to list leagues; e.g. `python3 -m backend.fleaflicker_service 312861` → 99.7% by id)

### Onboarding & conversion redesign (ships dark; [plan](plans/onboarding-conversion/plan.md) v2.1)

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

### Monetization platform (ships dark; [foundation](plans/monetization/00-platform-foundation.md), [plan index](plans/monetization/README.md))

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
| `marketplace.publisher_sets` | false | Publisher IAP + subscriber account-linking (phase 3). |
| `marketplace.contributor_sales` | false | Contributor credit-priced sales (phase 4). |
| `marketplace.cash_payouts` | false | Stripe Connect cash-out rung (phase 5). |

### App-teardown remediation (2026-07, branch `teardown-remediation` — all dark)

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

#### Ship-by / kill-by review convention (07/prd-04)

Dark flags are inventory, not archive. **Every flag dark ≥90 days gets a recorded decision at a quarterly flag review: schedule a canary via the experiments engine, or delete the code path.** "Still thinking" is not a decision — the review's exit criterion is zero flags >90 days old without one. Record the decision as a one-line ship-by/kill-by note in the flag's `features.json` comment block (or the table above). The teardown block's clock starts 2026-07-19.

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
| `package_adj_gamma` | 1.5 | Exponent in the KTC-style per-asset contribution `v · (0.15 + 0.85 · (v/v_max)^γ)` (`package_value_v2`) |
| `min_side_surplus` | 150.0 | Min per-side value gain (raw values) for a trade to surface |
| `min_side_surplus_marginal` | 60.0 | Replacement gate when `trade.marginal_value` is on (marginal values run smaller) |
| `user_gain_epsilon` | 0.0 | #108 user-board gain gate (value space). 1-for-1 player swaps (any basis, v2 + v3) must show receive − give ≥ ε on the user's OWN raw board (pre-shrinkage `user_elo`) — never offer the user's higher-ranked player for their lower-ranked one. Consensus-basis cards additionally require the consensus package delta (receive − give) ≥ ε on every shape. 0.0 = receive must at least tie give. Multi-asset divergence packages are exempt from the raw-board rule (the aggregate surplus gate is the compensation test). |
| `filler_min_frac` | 0.25 | #141 junk-filler gate (all package shapes: v2 pair, v3 optimizer incl. the 3.4 sweetener pass, consensus fallback). Any piece beyond a side's headliner (its best asset) must be worth ≥ this fraction of that headliner, each player priced at **max(user board, opponent board)** raw value — a filler EITHER side genuinely values survives; junk both boards value low never pads a suggestion. Headliners (the 1-for-1 core) are exempt; marginal valuation is deliberately NOT used (it collapses depth pieces by design, but "is this junk?" is a board-value judgment). On the consensus path the opponent's board is consensus. 0.25 ≈ a 277-Elo window below the headliner: on the 2026-06-13 DP snapshot a Chase-headlined side (≈8470) only accepts pieces ≥ ~2100 (≈ a mid 1st / top-65), a rank-50-headlined side (≈3250) accepts ≥ ~810 (≈ rank 115), and a rank-100-headlined side (≈1000) accepts ≥ ~250 (≈ rank 250) — so depth-for-depth trades are untouched. 0 restores pre-#141 behavior byte-identically. Unlike the other Tier-1 keys this one **is DB-seeded** (`_MODEL_CONFIG_DEFAULTS`), so it is live-tunable via `PUT /api/admin/config/filler_min_frac`. |
| `asset_floor_abs` | 450.0 | Interview 2026-07-17 ("both floors") — absolute companion to `filler_min_frac`, same code path (`filler_ok`) and same max-of-boards metric: every non-headliner piece must ALSO clear this value-space floor (~bottom of the depth tier, Elo ≈ 1350), so pure roster-clogger bodies never pad a package even when the relative bar is tiny. Headliners exempt; `filler_min_frac = 0` remains the master kill-switch for the whole gate; 0 disables just the absolute floor. DB-seeded. |
| `consolidation_raw_loss_frac` | 0.15 | Deck-eval 2026-07-17 — consolidation raw-delta sanity gate, **consensus path only** (`_generate_consensus_for_pair._emit`). On a user-give-side consolidation (more assets given than received) the **raw** consensus loss `Σgive − Σreceive` may not exceed this fraction of `Σgive`. Closes the insult-card class where the `package_adj_gamma` depth discount vaporizes a valuable second give asset while the crown premium inflates the received stud, so the adjusted delta (the #108 gate's input) flips positive and fairness scores ~0.99 on a raw −2748 consensus loss (Daniels + Odunze → Hurts). Divergence cards are untouched (their both-sides surplus gates run on real boards). 0.15 ≈ the market's ceiling on a fair consolidation premium; a 13%-loss 2-for-1 still surfaces. 0 disables (pre-fix behavior). DB-seeded. |
| `fairness_floor_divergence` | 0.55 | Interview 2026-07-17 ("loosen it") — for **divergence** cards (both members have real boards) the consensus fairness gate becomes `min(fairness_threshold, this)`: an extreme-case veto only, since the both-sides surplus gate already proves mutual gain on the boards that matter. Applies in the v2 pair generator and the v3 optimizer (including the sweetener band). Consensus-basis cards keep the full `fairness_threshold`. Fairness still weighs into the composite, so lopsided-but-mutual trades rank lower rather than vanish. DB-seeded. |
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

### Tier 3 (flag-gated, landing imminently)

| Key | Default | Meaning |
|---|---|---|
| `v3_pool_size` | 12 | Candidate pool size per side for the exact per-pair search |
| `sweetener_band` | 0.15 | Fairness shortfall band in which a sweetener pass is attempted |
| `sweetener_max_cards` | 2 | Max sweetener-balanced cards per deck |
| `cycle_edge_min_gain` | 100.0 | Min per-edge value gain for a 3-team cycle edge |
| `cycle_min_net` | 200.0 | Min net surplus per participating team in a cycle |
| `cycle_max_results` | 3 | Max 3-team cycle cards surfaced |

### Verdict bands (backlog #6 / #27) — `trade_service._DEFAULT_CFG`

| Key | Default | Meaning |
|---|---|---|
| `verdict_fair_max_gap_pct` | 0.08 | `classify_verdict` band cut: gap ≤ this (as a fraction of the larger side) → `fair` |
| `verdict_lopsided_min_gap_pct` | 0.20 | `classify_verdict` band cut: gap ≥ this → `lopsided`; else `slight` |

These were introduced by backlog #6 (verdict banner) and are **vendored into `_DEFAULT_CFG` by backlog #27** (open calculator) when #6 is not yet integrated — the public `/api/calc/score` calls `classify_verdict`, so it shares the exact band thresholds in-app trade cards use. If #6 lands first, the keys already exist and #27's copy is a harmless duplicate to drop on merge.
