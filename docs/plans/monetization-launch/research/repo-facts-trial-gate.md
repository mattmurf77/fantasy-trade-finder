# Repo facts for the trial gate (read-only worker, 2026-10-24)

**origin/main = `3d752296de31d7fc845cfe0379d187fbd91d97ef`** (2026-10-24, #377). `S` = `backend/server.py`. Code cites are origin/main unless a branch is named.

Read alongside:
- `docs/plans/org-bringup/monetization-day1-feasibility.md` (head-eng, 10-24): the Eng costs.
- `docs/plans/org-bringup/reports/onboarding-pm.md` §1–3: account states and the trial seed.

## 1. The network effect in code

- **Leaguemate boards.**
  - Each user's board is published to `member_rankings` (`database.py:683-717`) and republished on every ranking write:
    - rank3 `S:10232-10252`, tiers `S:11858-11877`, anchor `S:12057`;
    - reorder `S:12447`, import `S:12645`, explicit publish `S:20985`.
  - The trade job loads every leaguemate via `load_member_rankings` (`database.py:9281-9380`), with `has_rankings` and confidence maps (`S:7816-7853`).
  - `_shrink_user_elo` (`trade_service.py:1878-1934`) shrinks only the viewer's board toward consensus.
- **The served engine:** `owner_v2_bilateral` (`trade_gen_bilateral.py:20`).
  - A partner's board decides which players each side wants; terms are priced at consensus.
  - A member with no board gets `consensus_fallback` (`:83`).
  - Card `basis` is `two_board`, `one_board` or `consensus` (`trade_policy.py:94-96`, `:559-603`).
- **Inactive or gated leaguemates.**
  - **No activity, session, staleness or entitlement filter exists.** `load_member_rankings` selects every row except the viewer's (`database.py:9333-9345`).
  - Nothing prunes `member_rankings`; only account delete or reset removes a board (`database.py:5697-5720`).
  - So **a gated user's last board keeps powering paying leaguemates' two-board cards, frozen.** If the gate filtered gated users out of the load, payers would fall back to one-board or consensus cards.
- **Mutual matches need both users active.**
  - A match is created only when `POST /api/trades/swipe` `like` (`S:16094`) finds the counterparty's own earlier like on the mirrored package (`find_mirror_like`, `S:16300-16345`; `database.py:9532`, "BOTH swiped like" `:719-728`).
  - Routes: `/api/trades/matches` (`S:19896`), `/all`, `/dismiss`, `/disposition`.
  - **A gated leaguemate can't swipe, so new matches with them stop**, and pending ones stall.
  - Pushes to gated users (`trade_match`; `league_member_unlocked_trades` `S:10651-10697`) land them on the paywall.
- **Sends: the recipient needs no FTF account.** `POST /api/trades/propose` writes a Sleeper proposal with the sender's token (`sleeper_write.py:1-30`; route `S:19582-19640`); also `/propose-mfl` `S:32628` and `/propose-espn` `S:33141`.

## 2. The referral loop for launch

- **Launch MUST:** `launch-readiness-product.md:138-174`; the slice is in `launch-plan-1118.md:27, 68-81, 166-179`.
  - Binary pieces B1–B6 (engagement-eng, by 11-06), B3 and B7 (onboarding-eng).
  - Server and web by 11-16: L1/D-1 is the join landing plus install CTA (#386); L7 is mint, attribution, activation and FR-18 (#390).
  - **The launch plan has no monetization, paywall or trial text.**
- **The PRD is on branch `origin/plan/referral-loop`** (PR #348): `docs/plans/referral-loop/prd.md`. v1 is reward-free (§196-199); rewards are "paid entitlement time" in Phase 3 (`:1399-1400`). **It says nothing on how a paywall or trial meets the invitee.**
- **The invitee path:**
  1. The link: `?league=&ref=` (`deepLinks.ts:400-430`) or `app/league/join/:leagueId` (`deepLinks.ts:119`, `growth.invite_join_link` currently false).
  2. `LeagueJoinScreen.tsx:50-111` (`invite_link_opened` `:77`) goes to SignIn (inviter banner, `SignInScreen.tsx:223-255`).
  3. Session init stores `invited_by` on INSERT (`S:22757-22770`) and pushes `referral_joined` (`S:22820-22840`).
  4. LeaguePicker auto-pins the invited league (`LeaguePickerScreen.tsx:266-282`), then the Trades deck.
- **"Activated"** (PRD FR-17, `prd.md:887-920`, proposed): the invitee's first `trade_proposed` or `match_swiped` within 14 days of `joined_at` (FUNNEL_STAGES stage 7, `analytics_queries.py:415`). `trades_generated` never counts.
  - **So an invitee must see a deck and swipe a card to activate.** Ranking isn't required, and the cold-start format gate doesn't block an unranked user (`TradesScreen.tsx:1568-1571`).
  - Unverified: whether the served engine returns cards to a user with no board.
- **Baseline:** 0 invite opens; `invited_by` set on 0 rows (`reports/analytics-lead.md:900-915`).

## 3. The gate surface

- **Tabs** (`TabNav.tsx`): Home `:819`, Rank `:830`, Trades `:871`, Calibration `:912` (or Draft `:937`), Matches `:958`, League `:979`.
- **(A) Must stay reachable after the trial.**
  - Screens: SignIn, LeaguePicker, LeagueJoin, Sleeper/EspnConnect, Settings plus its seven pages, Profile, Paywall, FeedbackInbox/FAB.
  - **Delete:** `DELETE /api/account` `S:28133` (the launch plan's `:27977` cite is stale); row `AccountDataSection.tsx:239-250` in SettingsAccount.
  - **Export:** `GET /api/account/export` `S:28101`; "Download my data" `AccountDataSection.tsx:208-219` (`account.data_export` true).
  - **Privacy and Terms:** `AboutSection.tsx:82-94`; `/privacy` `S:12715`, `/terms` `S:12721`.
  - **Restore Purchases is reachable only on `PaywallScreen.tsx:391-394`**, and the Paywall only from the Settings Pro row, gated on `monetize.paywall`.
- **(B) Data-generating input:** Trios, Anchors, Tiers, QuickSetTiers, QuickRank, ManualRanks, RookieRanks, Calibration, PickAssignment, RecordPicks. Board publishing is implicit in every rank write.
- **(C) Trade outputs:** TradesHome/Deck, TodaysTrade, TradeBrowseAll, Portfolio, TeamReview, Overhaul*, TradeCalculator, Matches, WinNow, ShopAsset, Receipts, plus the Send buttons.
- **(D) Read-only content:** Home, RankHome, Trends, LeagueRankings, LeagueHome, LeagueSummary, Standings, FreeAgents, UsageTrends, DraftRoom, MockDraft, PremiumRankingsBrowser.
- **Backend route families** (206 routes in S, plus `/api/overhauls` ×14 and `/api/win-now` ×4):
  - **A:** `/api/session` `:22319`, `/api/auth` `:27826`, `/api/sleeper/link` `:19408`, `/api/entry` `:26030`, `/api/espn` `:28525`, `/api/mfl` `:31514`, `/api/fleaflicker` `:33443`, `/api/feature-flags` `:26469`, `/api/account` `:27874`, `/api/me/entitlements` `:31159`, `/api/paywall` `:31209`, `/api/billing` `:31328`, `/api/feedback` `:11192`, `/api/events` `:11394`, `/api/notifications` `:23274`, `/.well-known`, `/app/league/join`, `/s`, `/og`.
  - **Never gate (secret-guarded):** `/api/admin`, `/api/cron`.
  - **B:** `/api/rank3` `:10182`, `/api/trio` `:9858`, `/api/tiers` `:10933`, `/api/anchor` `:11987`, `/api/rankings` `:10330`, `/api/ranking-method`, `/api/progress`, `/api/scoring`, `/api/grading` `:27313`, `/api/league/preferences` `:21148`.
  - **C:** `/api/trades` (26 routes; generate `:14750`, swipe `:16094`, queue `:16548`, propose `:19582`), `/api/trade` `:12904` and `/evaluate`, `/api/portfolio`, `/api/share`, `/api/league/team-review`, overhauls, win-now.
  - **D:** `/api/league` (summary, power-rankings, free-agents…), `/api/players`, `/api/trends`, `/api/usage-trends`, `/api/market`, `/api/draft`, `/api/mock-draft`, `/api/rookies`, `/api/leaderboard`, `/api/profile`, `/api/invite`.
  - **`/api/league/*` mixes B, C and D, so a pure prefix gate can't be clean.**

## 4. Trial clock and gating primitives

- **`entitlements` table** (`database.py:2547-2574`): user_id (working key), account_id, entitlement, source, product_id, status, starts_at, expires_at (NULL means perpetual), granted_by, note, metadata.
- **Sources:** `trial` is in `_BILLING_SOURCES` (`entitlements.py:47`).
- **`grant()`** (`:272-308`): not idempotent; `duration_days` beats `expires_at`; fires `entitlement_granted`.
- **`check_pro()`** (`:251-269`): entitlements OFF → allow; ON + paywall OFF → observe; both ON → enforce.
- **`_require_pro`** (`S:31144-31156`) wraps nothing and returns 402 `pro_required`. Its docstring says "Never wrap the core loop".
- **`/api/me/entitlements`** (`S:31159-31169`) returns `{pro, ad_free, sources, expires_at, enforcing}`. `useEntitlements` (`mobile/src/state/useEntitlements.ts`) uses the server as truth, with a 72 h grace; RevenueCat can only raise it.
- **First-sign-in timestamps are unreliable:**
  - `users.created_at` is re-inserted as "now" by `migrate_board_data` (`accounts.py:563`);
  - `users.signup_at` is sparse;
  - `verified_at` is overwritten on every verify;
  - `accounts.created_at` is NOT NULL.
- **An app-managed trial would be an entitlements row with no schema change,** with these caveats:
  - TRANSFER/rekey paths can move trial rows;
  - the paywall config says "the server never mints trials";
  - account delete removes entitlements, so delete-and-recreate resets the trial;
  - it needs a once-per-person check.
- **Identity.**
  - The working key is a Sleeper id or `acct_<id>`; entry ids are `entry:espn:…` / `entry:<mfl>`. Entitlements resolve on user_id OR account_id (`entitlements.py:195-223`).
  - **Username-only Sleeper users have no account row and a memory-only session, and anyone can claim a username** (incident `2026-10-17-kevinlake-league-select.md`). onboarding-pm rejects username-only and unverified entry identities as trial starters (`reports/onboarding-pm.md:38-46`).
  - There are 2 entry accounts all-time.

## 5. Paywall config on main

- **`_PAYWALL_PRODUCTS`** (`S:31188-31193`): monthly $4.99 with `trial_days` **14**; annual $34.99 ($2.92/mo) with `trial_days` **30**, hero, best_value.
  - History: #231 set 3 days (2026-08-28); #243 set 14/30 (2026-08-29).
  - **The feasibility doc's "3-day" is stale.**
  - **The actual App Store Connect intro offer is unverified.**
- **`_PAYWALL_PAGES`:** value_recap, then feature_grid [unlimited_leagues, portfolio, engine_knobs, extension_overlays, ad_free], then plans.
- **`/api/paywall/config`** (`S:31209-31251`): `{"enabled":false}` when off. When on, `trial_eligible: True` and `dismissible: True` are hard-coded.
- **PaywallScreen:**
  - Close renders iff `dismissible !== false` (`:158, :274-281`), so a non-dismissible mode is a config value plus the gate.
  - Trial copy is `"${trial_days} days free, then ${price}"` from the **server**, not StoreKit (`:166-176`). The CTA reads "Start free trial" (`:383`).
- **TipJar:** dark; tips grant nothing.
- **`_product_mapping`** (`entitlements.py:374-381`):
  - `ftf_founder*` / `founder_lifetime*` → founder_iap (**perpetual**);
  - `ftf_season_pass*`, `ftf_rookie_pass*`, `season_pass_*` → season_pass_iap;
  - everything else → apple_iap.

## 6. PR #347's eight fixes: none is on main

- **5a:** `monetize.pro` is never read.
- **5b:** `enforcing` reads one flag (`S:31168`).
- **5c:** the grid still sells non-existent features (`S:31182-31183`).
- **5d:** non-renewing → perpetual (`entitlements.py:378-380, 535, 556`).
- **5e:** no Founder cap.
- **5f:** no sandbox/environment check (`S:31328-31358`; `entitlements.py:390-575`).
- **5g:** no league cap.
- **5h:** `entitlement_granted` isn't in `SERVER_FIRED_EVENTS` (`analytics_taxonomy.py:736-887`).

## 7. Web and extension

- **Web sign-in:** Sleeper username, ESPN/MFL entry, demo, and optional extension verification. **There's no Apple sign-in on web**, so `acct_`-only users can't use it. `js/app.js` calls about 60 routes, including trades/generate, swipe, matches, rank3, league/*.
- **The extension** calls `/api/extension/auth`, `/api/sleeper/link`, `/api/extension/rankings`, `/api/feature-flags` and `/api/events`. **The auth response has no `pro` field** (`S:26018-26027`), contrary to head-eng's doc.
- **A server-side gate covers both** (same session token).
  - **But no client handles 402 or `pro_required`**: not `mobile/src/api/client.ts`, not `web/js/app.js`, not `extension/*`.
  - **So web and the extension each need 402 handling**, or gated calls just fail.
- **There's no Stripe checkout or web purchase page;** only the Stripe webhook (`S:31361`).

## 8. TestFlight users

- **There's no TestFlight vs App Store signal in code:** one EAS profile builds both, and `X-App-Version` is the marketing version.
- `FTF_TESTER_ALLOWLIST` (`render.yaml:33-34`) and `config/tester_allowlist.json` hold 2 ids (the operator's).
- Synthetic users: `qa_*`, `test_user_fp_*`, `demo_*`.
- **Counts:** analytics-lead W3, 2026-10-20 (`reports/analytics-lead.md:888-911`):
  - WAU by week: W36 7, W37 9, W38 7, W39 3, W40 3, W41 8, W42 8.
  - MAU: Sep 9, Oct-to-date 8.
  - 4 new accounts in 12 weeks.
- **onboarding-pm's cohort count queries Q1–Q5** (cutoff 11-18) are drafted, not run.
- **Comp routes** (X-Cron-Secret): `POST /api/admin/entitlements/grant` `S:31254`, `/bulk-grant` `S:31280`, revoke, list.

## 9. Analytics

- **The registration rules are on branch `origin/skill/an-data-architect`** (PR #334), `references/registration.md`:
  - granted as a pair, in the emitter's commit;
  - names follow `<feature>_<object>_<past verb>`, with no duplicates of shipped names;
  - INTENT by default; impressions, echoes and terminators are NON_INTENT;
  - server events start at the deploy.
- **Existing events:** the `paywall_*` five (NON_INTENT; emitted at `PaywallScreen.tsx:192-243` and `TipJarScreen.tsx:107-118`).
- **Missing:** `trial_started`, `access_gate_hit`, `pro_gate_hit`, `trial_expired*`, `paywall_shown`.
- **head-eng proposes `paywall_shown`, which would duplicate `paywall_viewed`.** analytics-lead prefers the ledger as conversion truth, plus one NON_INTENT gate-hit event.

## 10. Timeline and capacity

- **Dates:** 11-06 binary feature-complete (`launch-plan-1118.md:19`); 11-10 submission; 11-18 launch.
- **There are three Eng slots to 11-06, not two** (`:103`):
  - Slot 1, trades-eng: M2.
  - Slot 2, onboarding-eng, to about 11-03.
  - Slot 3: engagement-eng (O8, B1/B2/B4–B6) to about 11-02, then platforms-eng 11-03 to 11-05.
- **Free time:** about 1 day of buffer (`:164`; `program-tracker.md:83`).
- **head-eng:** A fits 11-06 only with a 4th slot from about 10-28; otherwise the gate ships about 11-28 (`monetization-day1-feasibility.md:57-63`).
- **After 11-06 (2 slots):** packing 11-06 to 11-09, LEG-S6 11-10 to 11-11, L1 + L7 11-11 to 11-15 (`:232-236`).
- **No monetization appears in the launch plan or queue.** `program-tracker.md:183-185` says "No RevenueCat key in the production build, so no purchases at launch".

## Drift against main

1. The feasibility doc says monthly has a 3-day trial; main says 14.
2. The extension's `pro` bool doesn't exist.
3. The `DELETE /api/account` cite is now `:28133`.
4. The matches route is `/api/trades/matches`.
5. There are 3 Eng slots to 11-06, not 2.
