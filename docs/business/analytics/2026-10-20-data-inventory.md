# Data inventory for the privacy policy and App Store privacy labels (M7)

## 1. Purpose and status

- **What this is.** A factual inventory of every data element FTF holds about a person, so that `web/privacy.html` and the App Store privacy labels can be checked against it. Launch item M7; decision P12 (labels follow the tracking plan).
- **What this is not.** It is not the policy, not policy wording, and not legal advice. Wording goes to `legal-lead` (via `head-bizops`); the pages go to `onboarding-pm`.
- **Baseline.** Code as of `origin/main` `678834ab` (2026-10-20). Prod counts are from five read-only, count-only queries run 2026-10-20 06:23–06:24 UTC (§2, last column). No values, ids or user rows were read.
- **Marking.** Anything about Apple's label rules is **assumed (general knowledge, unverified)**. Line numbers are at `678834ab`.
- **Scope.** iOS app (`mobile/`), web app (`web/`), extension (`extension/`), backend (`backend/`). `backend/database.py` defines 94 tables. Tables with no person data (`players`, `model_config`, `player_value_history`, the experiment and prepared-trade machinery) are left out, except where a column names a user.
- **Terms.** "Linked" means the row carries the user's working key (`sleeper_user_id` or `acct_*`) or joins to it through `identity_links`. "None in code" means no purge exists, so the data is kept until account deletion.

## 2. Data collected

One row per element. Citations are `file:line`, with `database.py` implied for a bare `:line` in "Where stored". "Prod" is a non-null or row count, never a value.

### 2.1 Identifiers and account

| # | Element | Where stored | Source | Linked? | Purpose | Shared with | Retention | Export / delete | Prod (2026-10-20) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Sleeper user id (the app's working key) | `users.sleeper_user_id` (`database.py:449`); the key column on most tables | Platform API (Sleeper `GET /user/{username}`, `sleeper.md:39`) | Yes, it is the key | App functionality | Sleeper (lookups, trade writes); Sentry user tag (`useSession.ts:394`); RevenueCat `appUserID` once keyed (`purchases.ts:125-140`) | None in code | Export `users` (`accounts.py:944`); delete (matrix `accounts.py:583-628`) | `users` 22 rows |
| 2 | Sleeper username, display name, avatar | `users.username/display_name/avatar` (`:450-452`); copies in `sessions` (`:2502`), `app_feedback.username` (`:1691`), `bad_trade_flags.username` (`:1739`) | User-entered (username) and platform API | Yes | App functionality | Sleeper; Expo push text shown to *other* users (row 11) | None in code | Export; delete (feedback `username` set to NULL, `accounts.py:893-899`) | Not checked separately |
| 3 | FTF account id | `accounts.account_id` (`:2466`); `acct_*` working key | Derived (opaque hex) | Yes | App functionality | RevenueCat aliases, once purchases are on | None in code | Export (`accounts.py:1046`); delete (`:901-915`) | `accounts` 5 |
| 4 | Apple/Google `sub` and provider name | `linked_identities.provider_subject/provider` (`:2481-2482`) | Platform (Apple identity token) | Yes, via `account_id` | App functionality, security | Apple: JWKS verification; token revoke at deletion (`accounts.py:1081-1099`, `:1174`) | None in code | Export; delete | `linked_identities` 5 |
| 5 | Email hash (SHA-256) | `linked_identities.email_hash` (`:2483`); `hash_email` (`accounts.py:236-240`) | Derived from the email Apple shares | Yes | Support lookups (comment `:2461-2463`) | None | None in code | Export; delete | 5 of 5 non-null |
| 6 | Raw email | `accounts.email`, `email_source`, `email_consent_at` (`:2471-2475`) | Would be Apple or user | Yes | None today | None | n/a | Export; delete | **0 of 5 non-null.** Writer gated by `auth.email_capture` = false (`features.json:93`; `accounts.py:251-259, 277-278, 304`). Capture reverted in `65c63479`. **Not collected.** |
| 7 | ESPN member id (SWID); MFL login handle | `espn_credentials.swid` (`:2415`, plaintext by design); `mfl_credentials.mfl_username` (`:2441`) | User sign-in (WebView or form) | Yes | App functionality | ESPN, MFL | Until disconnect or deletion (`database.py:13549`, `:13643`) | Export (secret columns omitted, `accounts.py:969-970`); delete | `espn_credentials` 2, `mfl_credentials` 2 |

### 2.2 Device, session and push

| # | Element | Where stored | Source | Linked? | Purpose | Shared with | Retention | Export / delete | Prod (2026-10-20) |
|---|---|---|---|---|---|---|---|---|---|
| 8 | Install device id (`dev_` + UUID) | `user_events.device_id` (`:2154`); `identity_links.device_id` (`:2178`) | Device: iOS SecureStore (`client.ts:120`), web `localStorage` (`web/js/events.js:14`), extension storage (`extension/background.js:148`) | Yes after sign-in (`identity_links`, written via `auth.ts:46-48`); before that `user_id = 'device:<id>'` | Analytics | None | None in code | Device rows and links deleted (`accounts.py:747-762`); exported (`:1059-1063`). Stays on the device (policy §6) | 19,544 of 35,085 events; 1,211 pre-auth rows; `identity_links` 13 |
| 9 | Analytics session id | `user_events.session_id` (`:2147`), stored as a salted SHA-256 (`database.py:4376-4386`) | Device, then hashed | Yes | Analytics | None | None in code | Omitted from export (`accounts.py:961`); deleted with events | 22,351 non-null |
| 10 | Auth sessions | `sessions.token_hash` (SHA-256, `:2503`), plus user id, account id, `verified_via` | Derived | Yes | Security, app functionality | None | 90-day rolling idle purge (`server.py:2337`; `database.py:14748`) | Export without `token_hash` (`accounts.py:1053`); delete (`:741-745`) | `sessions` 6 |
| 11 | Push token and platform | `device_tokens.device_token/platform` (`:2299-2300`) | Device (Expo) | Yes | App functionality (notifications) | Expo relay, then APNs/FCM (`server.py:23299`). Push text can name other users and leagues (`server.py:16262`, `:16270`, `:20583`, `:22709`) | **Only account deletion removes it** (`accounts.py:853`). No sign-out path; Expo rejections not pruned (`expo-push.md:45`) | Export omits the token (`accounts.py:957`); delete | `device_tokens` 4 |
| 12 | Time zone (IANA) | `notification_prefs.tz` (`:2330`); `users.last_rank_tz` (`:489`) from `X-User-TZ` (`server.py:2905`) | Device | Yes | App functionality (quiet hours, streaks) | None | None in code | Export; delete | 2 and 7 non-null |
| 13 | Coarse country (ISO alpha-2) | `user_events.country` (`:2159`), from `CF-IPCountry` / `X-Country-Code` header, never the IP (`analytics_ingest.py:379-384`) | Derived from a CDN header | Yes (row's user id) | Analytics | None | None in code | With `user_events` | **19,473 of 35,085 non-null; 351 of 1,033 in the last 7 days** (all client-ingested rows) |
| 14 | Device snapshot (type, OS version, app version) | `user_events.device_type/os_version/app_version` (`:2148-2150`); `users.last_device_*` (`:478-480`); `app_feedback` (`:1695-1698`) | Device headers (`client.ts:30-37`) | Yes | Analytics, diagnostics | Sentry (row 23) | None in code | Export; delete | ~29,000 non-null |
| 15 | Event envelope: `client_ts`, `platform`, `screen`, experiment variants | `user_events` (`:2155-2158`); `experiment_assignments` (`:2260-2266`, `experiments.engine` on, `features.json:123`) | Device, derived | Yes | Analytics, product personalization (experiments) | None | None in code | Export (`accounts.py:1064-1067`); delete (`:763-766`) | `client_ts` 19,529; `experiments` 86; assignments 6 |

### 2.3 Platform credentials

| # | Element | Where stored | Source | Linked? | Purpose | Shared with | Retention | Export / delete | Prod (2026-10-20) |
|---|---|---|---|---|---|---|---|---|---|
| 16 | Sleeper session JWT (full-account credential) | `sleeper_credentials.token_encrypted` (Fernet, `:2377`), `expires_at` | Platform (captured from Sleeper's own login WebView, `sleeper.md:76`) | Yes | App functionality (ownership proof, trade proposals) | Sleeper (sent on GraphQL writes) | Until disconnect or deletion. **No expiry sweep** (per-user delete only, `database.py:13462`) | Export omits ciphertext (`accounts.py:963`); delete (`:858`) | 1 row |
| 17 | ESPN `espn_s2` cookie; MFL session cookie | `espn_credentials.espn_s2_encrypted` (`:2416`); `mfl_credentials.cookie_encrypted` (`:2442`). The MFL password is forwarded to MFL once and never stored (`mfl.md:88-104`) | User sign-in | Yes | App functionality | ESPN; MFL (password and cookie) | Same as row 16 | Same as row 16 | 2 and 2 |

### 2.4 League data, rankings, trades and user content

| # | Element | Where stored | Source | Linked? | Purpose | Shared with | Retention | Export / delete | Prod (2026-10-20) |
|---|---|---|---|---|---|---|---|---|---|
| 18 | **Other managers:** platform ids, usernames, display names, rosters, trade-block flags, executed trades | `league_members` (`:625-634`); `leagues.opponent_data` (`:527`); `trade_block.user_id` (`:648`); `sleeper_trades.raw`, the full Sleeper payload (`:675`); `league_roster_history.owner_user_id` (`:1934`) | Platform API (public league reads) | Linked to the *leaguemate's* id, not the app user | App functionality | None outward | Trade block and members re-synced; `sleeper_trades` append-only, none | Own `league_members` row deleted; references anonymized (`accounts.py:810-822`); `sleeper_trades` is not user-keyed and is kept | `league_members` 231; `sleeper_trades` 616; `trade_block` 125 |
| 19 | Rankings and rating history | `swipe_decisions` (`:584`), `member_rankings` (`:683`), `elo_history` (`:1793`), `users.tiers_saved/tier_overrides` (`:458-460`), `user_player_skips` (`:1775`) | User-entered, derived | Yes | App functionality, product personalization | Leaguemates' trade engines and an aggregate contrarian score (policy §3). Anthropic receives player names plus this user's Elo numbers, with no ids (`anthropic.md:39-46`): **not linked** | Indefinite by design (policy §5); none in code | Export; delete | `member_rankings` 12,277 |
| 20 | Trade decisions and deck behavior | `trade_decisions` (`:596`), `trade_matches` (`:728`), `deck_impressions` (`:928`), `user_taste` (`:1319`), `trade_proposals` (`:809`) | User-entered, derived | Yes | App functionality, product personalization | Sleeper, ESPN or MFL when the user sends a proposal | None in code | Delete own rows; `trade_matches` anonymized (matrix `accounts.py:604-606`) | Not checked |
| 21 | Free text outside feedback | `trade_pass_reasons.free_text` (`:1412`); `bad_trade_flags.reason` (`:1759`) | User-entered | Yes | Product quality | None (never an event prop, `analytics_taxonomy.py:1505`) | None in code | Export; delete (`accounts.py:652-658`) | 29 and 0 non-null |
| 22 | Feedback and web contact form | `app_feedback.text/screen/severity` plus device fields (`:1687-1704`). `web/contact.html:142,158` posts here and asks for the Sleeper username (`:86`) | User-entered | Yes when signed in | App functionality (support), product | None | Kept as a product record; none in code | Export (`accounts.py:968`). On delete, user id and username set to NULL and text replaced (`:893-899`). Anonymous web rows are not matched | 431 rows, 427 with a user id |

### 2.5 Usage events and diagnostics

| # | Element | Where stored | Source | Linked? | Purpose | Shared with | Retention | Export / delete | Prod (2026-10-20) |
|---|---|---|---|---|---|---|---|---|---|
| 23 | Crash and performance data | Not in our DB. Sentry SDK (`sentry.ts:72-97`; DSN set, `app.json:65`): user-id tag only, `sendDefaultPii: false` (`:97`), 20% traces (`:88`) | Device | Yes (user id tag) | Diagnostics | Sentry | Sentry's own retention (not in code) | Not covered; tag cleared on sign-out | Not checked (third party) |
| 24 | Usage events, client-fired | `user_events` via `POST /api/events`: 164 allowlisted types (`analytics_taxonomy.py:38`), per-event prop allowlist (`:916`). Scrub drops `token`/`password`/`email` keys and redacts email, bearer, JWT and 16+ digit values (`analytics_ingest.py:155-210`) | Device | Yes | Analytics, product personalization | None | None in code | Export; delete (`accounts.py:755-757`) | 35,085 events in total |
| 25 | Usage events, server-fired | `record_event` (`database.py:4389`), 44 `SERVER_FIRED_EVENTS` (`analytics_taxonomy.py:736`). Props are written as passed, with no scrub. Legacy `wrapped_events` (`:2106`) is read-only | Derived | Yes | Analytics, notification gating | None | None in code | Export; delete | `wrapped_events` 1,409 |
| 26 | Client diagnostics: `client_error`, `api_request_failed` | `user_events`; `message` capped at 200 chars after the scrub (`analytics_ingest.py:186`, `:209`); `route` normalized (`analytics_taxonomy.py:922-930`) | Device | Yes | Diagnostics | None | None in code | As row 24 | `client_error` 0 rows |
| 27 | Server diagnostics: `api_call`, `api_request` | `user_events` with `user_id = 'system:api'`. **`props.user` holds the session user or account id** (`api_observability.py:33-36`, `:374`; `analytics_taxonomy.py:1750-1753`) | Derived | Yes, via `props.user` | Diagnostics | None | 30 days (`FTF_OBS_RETENTION_DAYS` default, `api_observability.py:402-433`) | **Not exported, not deleted:** deletion matches the `user_id` column only (`accounts.py:755`) | `api_request` 1,876 rows, 1,133 with `props.user`; 0 rows older than 31 days |

### 2.6 Purchases, referral and attribution

| # | Element | Where stored | Source | Linked? | Purpose | Shared with | Retention | Export / delete | Prod (2026-10-20) |
|---|---|---|---|---|---|---|---|---|---|
| 28 | Purchases and entitlements | `entitlements` (`:2547`); `subscription_events.payload`, raw and never trimmed (`:2587`), from the RevenueCat and Stripe webhooks (`server.py:31149-31209`). The SDK is inert without `EXPO_PUBLIC_REVENUECAT_IOS_KEY` (`purchases.ts:51`) | Platform (store or billing provider) | Yes | App functionality (access) | RevenueCat (SDK and webhook), Apple; Stripe (webhook only; no checkout route in code) | None in code | Export without `payload` (`accounts.py:1053-1054`); delete (`:741-745`) | 0 and 0 rows; every `monetize.*` flag false (`features.json:141-148`) |
| 29 | Referral: `invited_by` | `users.invited_by` (`:462`): the referrer's username as typed, set on first insert (`database.py:5127-5156`; `server.py:22185`) | User link | Yes (two people) | App functionality (referral notification) | None | None in code | Export. On delete it is cleared only where it equals a deleted user's **id** (`accounts.py:814`), but it stores a **username**: a code gap | 0 non-null |
| 30 | Referral ledger and notices | `referrals` (`:2598-2620`); the `referral_joined` bell row stores `new_username` (`server.py:22656-22667`) | Derived | Yes | App functionality, growth analytics | None | None in code | Export without `invite_token` (`accounts.py:1043-1044`); both sides anonymized (`:829-840`) | `referrals` 0; `growth.referral` false (`features.json:149`) |
| 31 | Share links, affiliate clicks | `shared_packages.user_id` (`:2525-2531`); `affiliate_clicks` (`:2623`) | Derived | Yes | App functionality, monetization | Affiliates get a `subid` only (flag off, `features.json:146`) | Share links kept indefinitely (comment `:2520`) | Anonymized (`accounts.py:811-813`) | 5 and 0 |

**Not found in code:** IP address or user-agent storage (no `remote_addr`, `X-Forwarded-For` or user-agent reads in `backend/*.py`), precise location, contacts, photos, health, search queries (no free-text search prop in `CLIENT_EVENT_PROPS`), advertising identifiers. Render's own request logs are outside the code (policy §4).

## 3. Mapping to Apple's App Privacy categories (assumed)

Everything in this section is **assumed (general knowledge, unverified)** about Apple's taxonomy. The facts in it come from §2.

| Apple category | FTF elements (§2 row) | Linked to user | Used for tracking | Purposes |
|---|---|---|---|---|
| Identifiers: User ID | Sleeper id, username and display name (1, 2), account id (3), Apple `sub` (4), ESPN SWID and MFL handle (7) | Yes | No | App Functionality, Analytics |
| Identifiers: Device ID | Install id (8); Expo push token (11) is a likely fit | Yes | No | Analytics, App Functionality |
| Location: Coarse Location | Country code (13), populated in prod. Time zone (12) may count | Yes | No | Analytics (country), App Functionality (time zone) |
| Contact Info: Email Address | Raw email not collected (6). A SHA-256 hash is stored (5): see Q3 | Yes (hash) | No | App Functionality (support lookup) |
| User Content: Customer Support | Feedback and contact text (22) | Yes | No | App Functionality |
| User Content: Other User Content | Rankings, tiers (19); pass free text, flags (21); trade likes (20) | Yes | No | App Functionality, Product Personalization |
| Usage Data: Product Interaction | Usage events (24, 25), trade and deck behavior (20) | Yes | No | Analytics, Product Personalization, App Functionality |
| Diagnostics: Crash, Performance, Other | Sentry (23); `api_request_failed`, `client_error` (26); `api_request` (27); device snapshot (14) | Yes | No | App Functionality, Analytics |
| Purchases: Purchase History | Entitlements and ledger (28): **0 rows, flags off**. Becomes collected when monetization ships | Yes | No | App Functionality |
| Other Data | Encrypted platform credentials (16, 17); no closer category | Yes | No | App Functionality |

- **Look not collected:** Contact Info (name, phone, address), Health and Fitness, Financial Info (stores take payment), Precise Location, Sensitive Info, Contacts, Emails or Text Messages, Photos or Videos, Audio, Gameplay Content (fantasy rosters read as league data, not game content; see Q8), Browsing History, Search History, Advertising Data, Surroundings, Body.
- **Tracking.** The code supports "not used to track". There are no ad or attribution SDKs in `mobile/package.json` (third-party SDKs: Sentry `:129`, RevenueCat `:152`, NetInfo `:124`, Apple auth, Expo notifications). There is no ATT or IDFA dependency. No IP is stored. Policy §2 says no data is sold. This holds while `monetize.ads_web`, `monetize.ads_mobile` and `monetize.affiliate` stay off (`features.json:146-148`).
- **Other managers' data (18)** is collected *about* people who may never use the app. Labels describe the user's own data, so this is a policy question, not a label one (assumed). See Q8.

## 4. Mismatches with `web/privacy.html`

Ordered by risk. The quotes are from the policy at `678834ab`.

1. **Country is populated, but the policy says it is empty.**
   - Policy: "this field is empty today" (`privacy.html:132`).
   - Code: `user_events.country` is stamped from `CF-IPCountry` or `X-Country-Code` (`analytics_ingest.py:379-384`). Server-fired events never set it.
   - Prod: 19,473 of 35,085 rows, close to every row with a device id (19,544), and 351 of the last 7 days' 1,033. So a CDN header is reaching the app. `runbook.md:684` places Cloudflare at Render's edge; which header it is has not been verified.
   - `docs/data-dictionary.md:1445` makes the same stale claim.
2. **Push-token retention.**
   - Policy: tokens are kept "until you sign out on that device, disable notifications" (`:220`).
   - Code: only account deletion removes a token (`accounts.py:853`). A re-register can overwrite one (`database.py:13330`). Expo rejections are not pruned (`expo-push.md:45`).
3. **Deletion leaves some rows behind.**
   - Policy: deletion removes "activity and usage events" (`:233`).
   - Code: `api_request` rows keep the user's id in `props.user` under `user_id = 'system:api'`. Deletion matches the `user_id` column only (`accounts.py:755`), so these rows survive until the 30-day purge. They are also missing from the export (row 27).
   - Prod: 1,133 such rows today.
   - Code: a deleted referrer's username also survives in invitees' `users.invited_by` (row 29). Prod: 0 rows today.
4. **The third-party list is incomplete** (§4, `:203-212`).
   - Missing: ESPN and MFL, which receive the user's cookies (MFL also receives the password once, `mfl.md:88-104`). They appear only in §1 and §2 (`:167-168`, `:187`).
   - Missing: Apple (identity verification and token revoke, `accounts.py:1081-1099`, `:1174`).
   - Missing: RevenueCat (SDK and webhook, once keyed; row 28).
   - Not needed but could be named: KeepTradeCut and nflverse, which are inbound reads that send no user data (`integrations/README.md`).
5. **"Sleeper username only" (`:85-86`)** contradicts the policy's own Apple paragraph (`:95-100`). It also omits ESPN and MFL sign-in (`verified_via`, `database.py:491-497`; `features.json:91,110,117-118`).
6. **ESPN and MFL identifiers are plaintext.** The policy says they "retain encrypted authentication cookies or tokens" (`:167-168`). That is true of the secrets, but the ESPN member id (`database.py:2415`) and the MFL handle (`:2441`) are stored in plaintext and not named as collected.
7. **Credential expiry.** The policy says tokens are kept until "the token expires" (`:221`). No sweep deletes expired rows; they stay until disconnect or deletion (row 16).
8. **Device id storage.** The policy says "stored in your device's secure storage" (`:123-124`). That is true on iOS. Web uses `localStorage` (`events.js:14`) and the extension uses extension storage (`background.js:148`).
9. **Time zone.** The policy mentions it only for quiet hours (`:147`). `users.last_rank_tz` also stores it, for streaks (row 12).
10. **Dormant email capability.** The policy says "When account email collection is enabled" (`:99-100`). The flag is off, the feature was reverted (`65c63479`), and prod has 0 rows. It is accurate as conditional text; whether to keep it is legal's call.
11. **Push content names other users** (`server.py:16262`, `:22709`). This is covered by "notification content" (`:208`), noted for completeness.

**Policy matches code:** the Sentry id-only tag and no default PII (`:178-181`); Anthropic receiving no ids (`:198`); the event PII scrub (`:119-120`); export exclusions (`:248-249`); feedback anonymization on deletion (`:239-240`); first-party-only analytics (`:190`).

## 5. Upcoming deltas that change the inventory

- **Referral loop** (PR #348 plan; PR #350 events addendum, `2026-10-15-referral-loop-events.md` on `docs/referral-loop-events`). Behind the new `growth.referral_ledger` and `growth.join_landing` (both off).
  - Adds a ledger of who invited whom, linked to both accounts.
  - Adds four server events owned by the referrer (`invite_landing_opened`, `invite_landing_cta`, `referral_attributed`, `referral_activated`) and `signup.attribution` / `attribution_miss`.
  - A landing open stores a **non-user's** coarse `device_class`, with no user agent or IP (grant C4).
  - `invite_id` is an opaque public share id. There is no invitee id in props (C2) and no usernames (C9).
  - Label effect (assumed): more Identifiers and Product Interaction; possibly the "Developer's Advertising or Marketing" purpose. The addendum already flags a privacy delta for `onboarding-pm`.
- **P18 UTMs.** Four params (`utm_source`, `utm_medium`, `utm_campaign`, `utm_content`), closed vocabularies, values matching `^[a-z0-9_]{1,40}$`. They become `utm_*` props and `signup.first_utm_*` once the capture is built (deferred). First-party only, and they describe the campaign, not the person. Purpose may add "Developer's Advertising or Marketing" (assumed).
- **`network_type`** (PR #339 PRD, `prd.md:196`, `:238-241` on `plan/trade-time-to-suggestion`). `wifi|cellular|offline|unknown` as a prop on `trade_first_card_shown` and `trade_first_card_failed` only, plus a `search_id`. It is not an envelope column (R4 refused). Diagnostics or Performance Data. NetInfo is already a dependency.
- **Monetization on** (`monetize.*`, `features.json:141-148`).
  - RevenueCat receives the working key and purchase data from the SDK once `EXPO_PUBLIC_REVENUECAT_IOS_KEY` is baked into an EAS build (Q6).
  - `subscription_events.payload` stores webhook bodies verbatim. RevenueCat events carry aliases, including anonymous ids. Stripe events can carry customer contact and billing fields (assumed); no checkout route exists today.
  - Purchase History becomes collected.
  - Turning on `monetize.affiliate` or the ads flags reopens the tracking answer.
- **Email capture re-enabled** (`auth.email_capture`): Contact Info → Email Address, and a policy change.
- **Public profiles** (`profiles.public_pages`, `profiles.user_toggle`, both off): a disclosure change, not new collection.

## 6. Open questions for `legal-lead` and the operator

- **Q1 (operator).** The label answers live only in App Store Connect. The operator needs to read out the current answers (categories, linked, tracking, purposes) so they can be diffed against §3.
- **Q2 (operator, legal).** Country (§4.1): keep it, and update the policy plus a Coarse Location label? Or drop it at ingest? Eng should confirm which header supplies it.
- **Q3 (legal).** Does a SHA-256 hash of the Apple-shared email count as collecting "Email Address" (5 of 5 identities have one)?
- **Q4 (legal, eng).** Should deletion purge `api_request` rows by `props.user`, or should the policy disclose the 30-day tail (§4.3)? Should export include them?
- **Q5 (eng).** Fix or disclose these: the `invited_by` deletion gap (row 29), push-token retention versus the policy (§4.2), and the missing expired-credential sweep (§4.7).
- **Q6 (operator).** Is `EXPO_PUBLIC_REVENUECAT_IOS_KEY` set on the production EAS profile of the current TestFlight build? If it is, RevenueCat already receives the user id. This can't be read from tracked files.
- **Q7 (operator).** Is IP storage turned off in Sentry's project settings? `sendDefaultPii: false` is client-side; whether Sentry's server stores IPs is unverified (assumed).
- **Q8 (legal).** Is the disclosure enough for data about other managers (row 18): their handles, rosters, executed trades (`sleeper_trades.raw`), and push text naming them? How should rosters be classed for labels (Other User Content vs. Gameplay Content)?
- **Q9 (legal).** Does Render's request log (IP addresses, outside our code) need a label answer?
- **Q10 (legal).** Web contact-form rows sent without sign-in (row 22) are not matched by account deletion. Do they need a manual-handling note in the policy?
- **Could not classify with confidence:** the push token (Device ID vs. Other Data), time zone (Coarse Location or not), encrypted credentials (Other Data), and fantasy rosters (Q8).
