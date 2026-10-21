# Repo facts for the pricing memo (read-only worker, 2026-10-15)

**origin/main = `678834abfa70384367fb3cbf17d6b06ef4a7ab85`** (2026-10-14 21:31 -0400). Every path:line is on origin/main unless noted. Flag refs are `config/features.json` line:value.

## Headline facts
- **Nothing is gated today.** `_require_pro` is defined at `backend/server.py:30965-30977` but no route uses it. The only Pro gate check is `check_pro` (`backend/entitlements.py:251-265`), and that decorator is its only caller.
- **Four things the paywall sells don't exist:** a league cap, an engine-knob UI, a Pro extension overlay and ads. The paywall feature grid also sells Portfolio, which is free today (`server.py:31003-31005`).
- **Every `monetize.*` flag is false** (`config/features.json:141-148`). Only `monetize.entitlements` and `monetize.paywall` are ever read. `monetize.pro`, `season_pass`, `founder`, `affiliate`, `ads_*`, `growth.referral`, `growth.group_unlock` and `marketplace.*` are registered (`backend/feature_flags.py:260-290`) and read nowhere.
- **The "timing doc" and the IAP runbook can't be found on any ref.**

## 1. Packageable inventory
"Core" = on the path sign-in → sync → rank → suggestions → send.

- **Multi-league.** Exists, with no cap anywhere.
  - `league_limit` / `unlimited_leagues` appear only in paywall copy (`server.py:31004`; `mobile/src/screens/PaywallScreen.tsx:83`) and a taxonomy comment (`analytics_taxonomy.py:1666`).
  - The planned cap at `POST /api/session/init` (`00-platform-foundation.md:134-137`; `pro-subscription/prd.md:91-96` R3) was never built.
  - No flag. Sync is core.
- **Portfolio.** Exists (`PortfolioScreen.tsx`, `GET /api/portfolio` at `server.py:20792`). No flag.
  - The pill shows only with 2+ leagues (`TradesScreen.tsx:457`); a "See liked" button also routes there (`TradesScreen.tsx:8954-8959`).
  - Not core.
- **Engine knobs (PRD G3, `prd.md:77`):**
  - Aggression is a server-side A/B only (`trade.aggression_ab`:51 true); the client passes the variant through (`mobile/src/api/trades.ts:132-134`). No UI.
  - Lanes: `trade.lanes`:49 true. User lane pills and a fairness control already exist in TradeDnaSheet's "Fine tuning" strip (`TradeDnaSheet.tsx:63-74, 174-176`), under `trades.edit_full_sheet`:240 true. **That knob is already free.**
  - Fuzzy match (`trade.fuzzy_match`:38 true) and crown asset (`trade.crown_asset`:48 true) have no user UI.
  - Knob UI was explicitly out of scope (`iap-enablement/scope.md:35-36`).
- **Extension overlays.** The extension ships a basic tier + position-rank pill on sleeper.com (`extension/README.md`). There is no Pro tier.
  - The docstring at `server.py:30984-30986` claims a `pro` bool rides in `/api/extension/auth`, but the handler (`server.py:25792+`) has none.
- **Push and alerts.** Kinds and buckets: `backend/database.py:13931-13952`.
  - trade_matches: new_match, counter_offer, match_accepted, match_expiring, first_match, league_member_joined, league_member_unlocked_trades.
  - weekly_digest: weekly_digest, pending_review.
  - reengagement: winback_matches, winback_dormant, finish_ranking, season_start, deck_replenished.
  - Caps live at `server.py:23271-23296`. `notif.*`:180-184 are true; `trades.new_partners_alerts`:15 is false.
  - Not built: the PRD "Alerts pillar" (G5, `prd.md:79`) and the `trial_ending` push (R19, `prd.md:134-141`).
- **Win Now.** `WinNowScreen.tsx`; `trades.win_now`:5 true and `outlook.season_projections`:4. Entries at `TradesScreen.tsx:6757` and `LeagueSummaryScreen.tsx:1651`. Not core.
- **Team overhaul.** The 8 `Overhaul*Screen` files; `overhaul.enabled`:84 true (`TradesScreen.tsx:765`). It builds and sends trades, so it sits next to the core loop.
- **Trade calculator.** `TradeCalculatorScreen.tsx`; `calc.merged_layout`:95, `calc.inline_home`:97 and `calc.results_push`:101 are true.
  - Since #384 it is the Find-a-Trade landing that hands off to the deck (`screens/CLAUDE.md:26`), so it is effectively core.
  - It's on the PRD free list (`prd.md:70`).
- **Shop-a-player.** `ShopAssetScreen.tsx`; `trade.shop_asset`:68 and `trade.asset_ideas`:66 true. Not core.
- **Today's Trade.** `TodaysTradeScreen.tsx`; `trades.presentation_v2`:256 is false, so it can't be reached.
- **Draft room and mock draft.** Both live (`draft.room`:223, `draft.mock`:230). `draft.tab`:238 is false; the tab slot went to Calibration on 2026-10-02 (`docs/runbook.md:538`). Not core.
- **Usage Trends.** `UsageTrendsScreen.tsx`; `usage_trends.enabled`:109 true. Entries at `HomeHub.tsx:81` and `FreeAgentsScreen.tsx:60`. Not core.
- **Trends.** `TrendsScreen.tsx`, no flag; reached from Rank's "More ways to rank". The PRD recommends keeping it free (`prd.md:251` Q3).
- **Calibration.** `CalibrationScreen.tsx` (blind grading); `grading.blind`:278 true; its own tab (`TabNav.tsx:769-771, 910-919`).
  - "Open to every app user since 2026-10-05 (operator)" (`CalibrationScreen.tsx:27-28`).
  - It generates data, so the never-tolled rule applies.
- **Year-in-review / Wrapped.** Only data capture exists (`backend/roster_history.py`; `market.roster_history`:63 true). No recap UI or route.
  - `wrapped_viewed` is registered with no emitter (`analytics_taxonomy.py:838`).
  - The free-vs-premium call is owed before P3 (`living-memory/NEXT.md:508`; `2026-08-13-dynasty-year-in-review-plan.md:414`).
- **Team Review.** `TeamReviewScreen.tsx`; `trades.team_review`:82 true. Its beats write `league_preferences`, which reshapes the deck (adjacent to core).
- **Power rankings.** `league.power_rankings`:198 is false and web-only (`web/js/app.js:84-90, 470-476`). The mobile League rankings view (LeagueSummaryScreen) is live and unflagged; the PRD lists league summary as free (`prd.md:70`).
- **PremiumRankingsBrowser.** Entered from `RankHomeScreen.tsx:104` through the ImportRankingsSheet premium row.
  - `ranks.source.dynasty_nerds`:160 true; `ranks.source.dlf`:161 false.
  - It imports rank order only, from the user's own DN/DLF subscription (D-058). It is not an FTF-paid surface.
- **ad_free.** The entitlement value exists (`entitlements.py:41-43`) and pro implies it (:245).
  - **There are no ads anywhere:** `monetize.ads_web` / `ads_mobile`:147-148 are false and never read, and no AdMob or AdSense code exists in `web/` or `mobile/src`.
  - Affiliate is the same: an `affiliate_clicks` table (`database.py:2623`) with no route; `monetize.affiliate`:146 false.

## 2. Entitlement gates
- **Uses of `check_pro`:**
  - `entitlements.py:11` (docstring) and :251 (definition).
  - `server.py:30958-30960` (comment), :30965 (`def _require_pro`), :30974 (calls `check_pro`; 402 `pro_required`).
  - Tests: `test_entitlements.py:170-191`.
  - Applied as a decorator: **zero routes.** `@require_pro`, the foundation's name, doesn't exist.
- **Gate list on paper vs wired:**
  - Foundation §2.2 (`00-platform-foundation.md:130-137`): the core loop (rank → trades in one synced league) is never wrapped; gate lists live in each plan's LLD; the league cap is enforced at session/init.
  - PRD §4.1 (`prd.md:67-81`): G1 1 league → unlimited; G2 Portfolio; G3 knobs; G4 three-team trades (`trade.three_team`:42 false); G5 Alerts; G6 extension overlays; G7 ad-free. The free list is at `prd.md:69-71`.
  - **Wired: none.** `iap-enablement/scope.md:39-41`: "wraps zero routes and adds no gates."
- **Observe vs enforce (`entitlements.py:251-265`):**
  - `monetize.entitlements` off → allow everything.
  - Entitlements on, `monetize.paywall` off → log `ENTITLE-OBSERVE … would_block=` and allow.
  - Both on → enforce.
- **`monetize.pro` is never consulted.** That contradicts `foundation.md:23` ("Pro gate list active"). The planned TestFlight-window flip of `monetize.paywall` (foundation:38-40) would enforce any gated route at that moment, before Pro launches.
- `GET /api/me/entitlements` reports `enforcing = monetize.entitlements` (`server.py:30989`), so it says true even in observe mode.
- **Flags** (consumer in parentheses):
  - `monetize.entitlements`:141 false — master switch, observe → enforce (`entitlements.py:257`).
  - `monetize.paywall`:142 false — all purchase UI and the tip jar (`server.py:31050`; `PaywallScreen.tsx:111`; `TipJarScreen.tsx:50`; `SettingsScreen.tsx:111`; `SettingsHubScreen.tsx:95`).
  - `monetize.pro`:143, `season_pass`:144, `founder`:145, `affiliate`:146, `ads_web`:147, `ads_mobile`:148 — false, never read.
  - `growth.referral`:149, `growth.group_unlock`:150 — false, never read.
  - `growth.share_landing`:185 true; `growth.rating_prompt`:186 true.
  - `growth.tier_board_share`:188 false; `growth.invite_join_link`:190 false (it only changes the emitted URL).
  - `invite.k_factor_dashboard`:20 false.
  - `marketplace.*`:154-156 and `ranks.accuracy_scoring` / `rank_sets` / `set_types_extended`:151-153 — false, never read.
- **Grant sources (`entitlements.py:47-51`):**
  - Billing: apple_iap, stripe, founder_iap, season_pass_iap, trial.
  - Also valid: promo_referral, promo_group_unlock, manual_grant, rankset_purchase.
- **Actual writers:**
  - `manual_grant` via `/api/admin/entitlements/grant` and `/bulk-grant` (`server.py:31075-31127`; revoke :31130; list :31139), behind X-Cron-Secret.
  - The webhook projector (`entitlements.py:534-557`): founder SKUs → founder_iap; season and rookie pass SKUs → season_pass_iap; anything else → apple_iap; stripe when the rail is Stripe.
  - `ftf_tip_*` grants nothing (:363-371).
  - **Nothing ever writes promo_referral, promo_group_unlock, rankset_purchase or trial.**
- Webhook routes: `server.py:31149` (RevenueCat) and :31182 (Stripe). Both return 503 when their secret is unset.

## 3. Prior operator rulings on pricing
- **Pro price:** $4.99/mo and $34.99/yr (`prd.md:100-101`). Served at `server.py:31009-31015`; annual is the hero ("best_value", $2.92/mo equivalent).
- **Trials:**
  - PRD original: monthly none, annual 14 days.
  - 2026-08-28e (operator): monthly 3 days.
  - **2026-08-29 (operator): monthly 14 days, annual 30 days** (`CHANGELOG.md:519-521`; checklist :28). Code matches (`server.py:31011, 31014`).
  - Trials are store-managed only (`server.py:31060-31064`).
- **Founder Lifetime:** D8 band $99–119, $119 recommended, cap 100, optional $119/$99 A/B (`founder-lifetime/prd.md:11-12, 29-33, 212, 219`; `lld.md:24`; `monetization/README.md:18`).
  - **No operator ruling on the point price is recorded.**
  - The planned Stripe-rail TestFlight window (founder `prd.md:192`; foundation:244) **conflicts with** `scope.md:40-41`: "Founder Lifetime is a pre-order of the shipped app… never an in-beta unlock."
- **Season Pass and Rookie Pass** (`season-pass/prd.md:75-79`): Season Pass $19.99 (early-bird $14.99); Rookie Pass ~$9.99; upgrade $7.99; returning buyer ~$14.99. All recommendations (:196-207).
- **Tip jar:** `ftf_tip_199/499/999` at $1.99/$4.99/$9.99, operator request 2026-08-28 (`server.py:31017-31025`; `CHANGELOG.md:523-525`). Grants nothing.
- **SKU ids (Q-034):** resolved 2026-08-28 in favour of the `ftf_*` names (`OPEN_QUESTIONS.md:388-390`).
- **Ads and affiliate:** recommendations only. There is no monetization D-entry in DECISIONS.md. ADR-016 covers RevenueCat with server-side truth.
- **Timing doc: NOT FOUND** on any ref or on disk.
  - The best paraphrase is `origin/claude/new-user-feedback-06dabd:living-memory/HANDOFF.md:195`: "nothing is tolled today, honoring §7/§11: no data-generating action gated ever".
  - **§7 and §11 can't be quoted.**
- **IAP runbook (`iap-enablement-runbook-2026-08-27.md`): NOT FOUND.** It is cited as authored on the `app-launch-scorecard` worktree, but no such branch or worktree exists.
- **Open-access onboarding doc (`docs/business/product/2026-08-14-open-access-onboarding.md`):**
  - "Never gated again: the deck, Find-a-Trade, matches, the calculator, sends, every tab" (:285).
  - The ranking lock was "a toll FTF charged before showing value" (:207-208).
  - The milestone gates only the board label, publishing to the league, and board-only features (:280-284).
  - Boards are never aggregated into an FTF consensus product (:200-205).
  - "user base is 3–5" (:155).

## 4. PFO guardrails
- `.claude/skills/pm-pfo/SKILL.md`:
  - The loop is sign in → sync → rank trios → values → suggestions (:10-15).
  - Watch anything that "slows, clutters, or gates the primary function" (:42-43).
  - Paywall or free-limit proposals must argue their case to PFO (:85-86).
  - The default answer to any added step before the first suggestion is no (:93-95).
- `pm-monetization` SKILL.md:78: don't gate the core loop before retention data exists.
- `docs/business/context.md:61-71`: funnel v2 and the WAT north star; paid conversion is stage 10, "unspecced".
- Never-gated rulings: foundation:131-133; `prd.md:41-42, 69-71`; `scope.md:39-41`; open-access :285.
- **No DECISIONS.md entry on the free list.** The only operator "free" act: Calibration opened to all users on 2026-10-05.

## 5. Paywall as built
- **Entry points:** only the "Fleeced Pro" and "Support Fleeced" rows on both settings surfaces (`SettingsScreen.tsx:1060-1092`; `settings/SettingsHubScreen.tsx:290-306`), hidden while `monetize.paywall` is off.
  - The routes are registered unconditionally (`RootNav.tsx:745-755`).
  - The screen guards itself twice: on the local flag, and on the server's `enabled:false`.
  - TipJar is behind the same flag; its copy says a tip "unlocks nothing".
- **`_PAYWALL_PAGES` (`server.py:30999-31007`):**
  - `value_recap`: "Your league has trades waiting", reusing `matches_preview`.
  - `feature_grid`: unlimited_leagues, portfolio, engine_knobs, extension_overlays, ad_free (copy at `PaywallScreen.tsx:82-87`).
  - `plans`.
  - The client has lifetime and season plan labels (:75-76), but the config serves only monthly and annual.
- **`GET /api/paywall/config` (`server.py:31030-31072`):** needs a session. Flag off → `{"enabled":false}`. Flag on → platform, pages, products, `trial_eligible:true`, `dismissible:true`, tips.
- **July plan vs today:**
  - PRD R5 put a soft multi-page paywall at the end of onboarding, after 2–3 real trades (`prd.md:107-110`).
  - R6 added 402 touchpoints (league cap, Portfolio, knobs) plus the Settings row (:111-112).
  - **Today only the Settings row exists.**

## 6. Analytics
- The five `paywall_*` events are registered (`analytics_taxonomy.py:704-706`; props :1690-1694) and classified NON_INTENT (`analytics_queries.py:376-380`).
- **`entitlement_granted` is fired** (`entitlements.py:302`) **but NOT registered** in SERVER_FIRED_EVENTS, and not in NON_INTENT, so it counts as intent. This is a registration gap.
- PRD events that are not registered: paywall_advanced, paywall_dismissed, trial_started, subscription_cancelled, cancel_intent, pro_gate_hit, knob_changed, invite_created, invite_clicked, referral_activated, referral_rewarded, share_card_shared.
- **Funnel-v2 keys a placement could use (`analytics_queries.py:406-417`):**
  - League synced: `league_synced` is server-fired (`server.py:22636-22642`); the stage itself uses the client event `league_selected`.
  - Board usable: `ranking_complete_first_time`.
  - First suggestion: `trades_generated` and client `trade_card_viewed`.
  - Later stages: `trade_proposed` / `match_swiped`; then `trade_ratified` / `sleeper_send_succeeded`.

## 7. Referral infra today
- **`referral_joined`** is an in-app bell notification, not an Expo push. It fires once, on a new user's first session_init with `invited_by` (`server.py:22648-22675`). Unflagged.
- Attribution: `users.invited_by` (`database.py:462`).
- The **`referrals` table** (`database.py:2598-2618`) has no writer.
- **Invite UI:**
  - InviteLeaguematesBanner (`TradesScreen.tsx:7052`); InviteLeaguematesCard (`LeagueScreen.tsx:603`).
  - The URL is `/?league=&ref=`, or `/app/league/join/<id>` when the flag is on.
  - LeagueJoinScreen sits behind `growth.invite_join_link`.
- **Events:** invite_shared, invite_link_opened, invite_league_pinned, invite_cta_shown / tapped.
- **No code grants promo_referral or promo_group_unlock.**

## 8. Cost and scale
- **Render memo (`docs/business/finance/2026-07-17-render-paid-tier-memo.md`):** the free tier cold-starts in 30–60 s. Options: keep-warm cron ($0) or Starter at ~$7/mo (the memo's assumption). It recommends Starter; the operator decision is pending.
- **`render.yaml`:** web `plan: free` (:14); DB `basic-256mb` (:6, upgraded in the dashboard 2026-07-26); three crons with no plan key. GOTCHAS.md:261 says blueprint crons are billable. **The actual dashboard plans are unverified.**
- **DB storage:**
  - 2026-09-15: the DB was suspended at 98.3% disk. Disk was grown 1 → 5 GB (+$1.20/mo at $0.30/GB-month, irreversible) (`db-storage-reduction/status.md:5-6`; `release.md:3`).
  - After compaction: 1,051,078,660 B used of 5,246,714,000 B (20.03%), 45.76% RAM (`release.md:50-51`). DB allocation fell 895 → 539 MB. Runway ≈350k records, about 380 generation runs.
  - ADR-011:115 projects ~470 MB at 1,000 leagues.
  - Not on origin/main: the uncommitted `plan/db-storage-budget/requirements.md` (2026-10-15) records the operator ruling out any further disk increase, and a ~28 MB INSERT OOM on 2026-09-07.
- **Anthropic:** optional matchup selection on `claude-sonnet-4-6` (`smart_matchup_generator.py:23, 59`), on when `ANTHROPIC_API_KEY` is set. D-005's "~$0.001 with Haiku" is stale. **No spend is recorded.**
- **Users:** no WAU/MAU/WAT is measured anywhere.

| Date | Count | Source |
|---|---|---|
| 2026-08-05 | 16 users, 3,346 events | `analytics/2026-08-05-trade-impact…:14` |
| 2026-08-09 | 16 users, 7 leagues, one non-test user with a real board | `ux-audit/05-appendix.md:47` |
| 2026-08-12 to 08-14 | "3–5 users" | `open-access:155` |
| ~2026-08-20 | ~10 testers | `negative-results-memory/PRD.md:27-28` |
| 2026-08-29 | 92 `trade_proposed` from 6 users since 08-21 | `trade-disposition-review.md:91` |

## 9. Stale docs
- `docs/plans/README.md:85` is false: the flags exist, and the code exists (`entitlements.py`, tables at `database.py:2547-2618`, routes at `server.py:30947-31190`, PaywallScreen and TipJarScreen, `react-native-purchases` ^10.8.1).
- `monetization/README.md`: :6 ("nothing built yet"), :35 ("docs-only thread"), :16 (14-day trial).
- `pro-subscription/prd.md:100-101` and R18 (:117-119) are superseded by the 14/30-day ruling. `scope.md:26-27` (3-day monthly) is too.
- `sandbox-test-checklist.md:100` contradicts its own P2.
- `season-pass/lld.md:103` still anchors Founder at $79.
- `docs/business/context.md:20-23, :34, :27` are stale (no payment SDK; analytics dark; v1.6.0).
- Comments that don't match code:
  - `server.py:30984-30986`: the extension `pro` bool doesn't exist.
  - `analytics_taxonomy.py:700`: `entitlement_granted` isn't registered.
  - `TabNav.tsx:766-767`: says `grading.blind` "ships false", but it's true.
  - foundation:23 and :130-137: the enforcement description doesn't match the code.
- The invite URL `ftf.app/join/<invite_token>` is not the shipped format.

## 10. Rankings marketplace
- Plan status: "PLAN… PRD/HLD/LLD follow on green-light"; the monetization README calls it a Phase-2 candidate.
- Schema only: `rank_sets`, `rank_set_entries`, `rank_set_adoptions`, `accuracy_scores` (`database.py:2648-2704`). No routes, no UI.
- All its flags are false and never read.
