# Feature Scope — Monetization from day 1: the trial, the Founder price, the access gate

<!--
MANDATORY for every feature or change that adds/modifies user-visible behavior,
data collection, schema, or API surface — regardless of which pipeline the work
enters through (feedback item, NEXT.md queue, staged-work, direct ask).

Copied from docs/templates/feature-scope.md. RULE: every section is answered or
explicitly WAIVED with a reason. Silence is not a waiver. Waivers are surfaced to
the operator before build starts (§6 below, and recommendation.md decision 14).

EXPRESS LANE: not available. This change touches API contracts, feature-flag
surfaces and analytics events (CLAUDE.md "Bright line").
-->

**Date:** 2026-10-24
**Entry point:** direct ask. The operator's direction of 2026-10-24 (relayed by head-bizops → head-product →
monetization-pm): "Work with product and eng to build monetization from day 1. 30 day free trial to access the
product." Product spec: [recommendation.md](recommendation.md). UX spec: ux-lead's "Monetization UX flows"
(`docs/plans/org-bringup/reports/ux-lead.md:23-264`, cited **ux §n**).
**Builder:** engagement-eng in the **approved 4th Eng slot** from 10-28, weekends included (the client); head-eng's
server PRs #394 and #395 (drafts, under way); eng-web (web). Rows refer to [recommendation.md](recommendation.md)
§Itemization.
**Operator sign-off on waivers:** **approved 2026-10-25** (W-MON-1, W-MON-2), under "rest of PR #393" (relayed verbatim
via head-bizops → head-product): "Approve M2-M5 as recommended: trade features only locked (C2), $4.99/$24.99 Founder then $6.99/$34.99 from 2027-01-01, rest of PR #393 incl. decision 16. Name: Founding GMs. Listing line: legal's R28.8 version."
**Built to the operator's decisions of 2026-10-25** (recommendation.md header and §Decisions): A-preview, C2, the
Founding GMs prices, R1 (the route, M1: "Ok. Then we need to build it.").
**Operator ruling, 2026-10-24** (head-bizops' session, relayed by head-product, verbatim): "No to any UX reflections of a
trial countdown. So scrap the 3 days and the day 30 items". Applied throughout: trial terms (duration, end behavior,
price) and the cut-off are stated once, at the start, on the offer (3.1.2); when access ends, a gated action opens the
standard paywall (3.1.2 disclosures, Restore, a close control) on gated surfaces only. ux §2, §3's day-30 treatment and
the T-3 items are superseded.

---

## 1. Analytics scope

- [x] **(a) New events specced.** analytics-lead grants the pair (`analytics_taxonomy.py` + `NON_INTENT_EVENTS`) to the
  emitting eng, in the emitter's commit, through head-product → head-eng
  (`origin/skill/an-data-architect:.claude/skills/an-data-architect/references/registration.md` §1). Server events
  start at the deploy, so these register before the 11-06 binary.

  | Event | Properties | Fires when | Client | Class |
  |---|---|---|---|---|
  | `paywall_gate_hit` (**new**, server-fired) | `gate`: `preview_used` \| `never_trialed` \| `trial_expired` \| `lapsed` \| `verify_required`. `route_family` (props only; never in the 402 body): `deck` \| `send` \| `matches` \| `calculator` \| `shop` \| `overhaul` \| `win_now` \| `other` (closed enums, kept in the row's comment) | The global gate returns 402 `pro_required`. **`gate=verify_required` carries no status** (it fires for every unverified session, subscriber or not). **Capped:** the first per (user, `gate`, `route_family`) per UTC day; read as distinct users, never as a row count | server | **NON_INTENT** (a system response to an intent the existing events already count) |
  | `entitlement_granted` (**register only**; the emitter ships at `entitlements.py:302`) | `entitlement`, `source`, `expires_at`, verbatim from the shipped call | `entitlements.grant()` inserts a row (purchase projection, manual or comp grant) | server | **INTENT**, no NON_INTENT row (#347 5h). analytics-lead confirms, given that manual grants fire it for the recipient |
  | `paywall_viewed` (**shipped; enum widening only**) | `source` gains `first_opinion` \| `left_deck` \| `gate` \| `settings` (it keeps `unknown`). No push or club values (the ruling). `platform` unchanged (the config variant) | The paywall mounts. `first_opinion` / `left_deck` are ux §1's two triggers; `gate` is the standard paywall opened from a gated surface | mobile | NON_INTENT (unchanged). The widening edits the row comment and the addendum, not the registry (registration.md §3) |

  - **Gate enum semantics:** `preview_used` = never held `pro`, and the preview page is spent. `trial_expired` = held
    `pro` only through an intro trial that ended unconverted. `lapsed` = held a paid period, now expired or refunded.
    `never_trialed` = never held `pro`, and the action is outside the preview (a send before any opinion), or the
    preview knob is 0. **`lapsed` is added to the lead's three:** a churned payer isn't `trial_expired`.
    **`verify_required` is status-blind** (legal R28.9 row 4, a MUST before launch, `docs/plans/org-bringup/leads/legal-lead.md:1677`): it is the
    gate for **every** unverified session (not verified, not demo) at a gated action, whatever the account's
    subscription. For unverified sessions it **replaces** `preview_used`, `never_trialed`, `trial_expired` and
    `lapsed`, so an unverified session never learns its status. **On the deck, generate, swipe and propose routes the
    existing account check answers first (P53):** `_verified_read_denial` (`backend/server.py:2787` on `origin/main` `db7425d4`, plus its decorator) returns 403 `verification_required`, identical
    for every account, before any paywall logic; the 402 `verify_required` is the status-blind backstop.
    analytics-lead is granting the event now.
  - **Not added, on purpose:**
    - `paywall_shown` (it duplicates `paywall_viewed`; this overrides head-eng's and ux-lead's proposals);
    - client `trial_started`, `purchase_*` duplicates, `declined`, `trial_expired*`.
    - Trial start, conversion and cancellation are **ledger queries** on `subscription_events` (RevenueCat
      INITIAL_PURCHASE `period_type=TRIAL`, the first RENEWAL, CANCELLATION) plus `entitlements`.
    - A decline is a `paywall_viewed` with no `paywall_purchase_initiated` in the session, or `paywall_purchase_failed
      {user_cancelled: true}` for Apple's sheet.
  - **The offer as an interrupt surface:** if the coordinator emits `prompt_shown{surface}` for every surface, the
    offer's surface id widens that enum. analytics-lead decides whether `paywall_viewed` alone is the impression (Product
    prefers it: no double count).
  - **The welcome moment** (ux §4.1) is a screen, counted by the existing `screen_viewed{screen}`.
  - **No device `platform` prop on any row** (registration.md §4).
  - **Follow-through:** the taxonomy addendum (analytics-lead). No `docs/data-dictionary.md` change: `user_events` is
    unchanged.
- [x] **(b) Existing events cover the rest:**
  - `paywall_purchase_initiated` / `_completed` / `_failed` and `paywall_restore` (`analytics_taxonomy.py:704-706`,
    `:1690-1694`) answer offer → purchase and Restore health.
  - FUNNEL_STAGES stage 7 (`analytics_queries.py:415`) answers "did the invitee activate before the offer" (FR-17).
  - WAT (`WAT_LIVE`, `analytics_queries.py:53-55`) feeds K1.
  - The invitee funnel cut (ux §5) is a query over these, not new events.
- [ ] (c) Waived: n/a. Celebration-moment events beyond the above are W-MON-1.

## 2. Schema & flag scope

- **New or changed tables and columns: none expected.** **head-eng to confirm** the storage for:
  - the **per-user "preview used" record** (P49, platforms-eng): user-initiated deck pages served since enforcement
    start; cron-built decks never count. If platforms-eng stores it in a new column or table, that's a
    data-dictionary row plus a migration entry;
  - **`founder`** (and the gate's `trial_expired` / `lapsed` split): derived from `subscription_events.payload`
    (`entitlements.py:421`), or stored in the existing `entitlements.metadata` JSON column. No `in_trial` / `will_renew`:
    nothing after the offer reflects trial time (the ruling).

  If either needs a column: a `docs/data-dictionary.md` row plus a reviewed migration entry, and this line is amended
  before build. Existing drift to fix while there (onboarding-pm): the data dictionary says entitlements rows are never
  deleted, but account deletion hard-deletes them.
- **Feature flags (existing; no new flag).** All default `false` in `config/features.json:141-145`. `FTF_FLAGS`
  overrides them in prod, so every flip goes through the effective mechanism (release-lead), on the operator's word.

  | Flag | Role (head-eng's rule, #394) | Flip | Graduation |
  |---|---|---|---|
  | `monetize.entitlements` | Resolution on; without enforce = observe mode (`ENTITLE-OBSERVE … would_block`) | ON at the server-gate deploy (~11-04) | Remove after 8 weeks of enforcement with K0–K3 clear [A] |
  | `monetize.paywall` | Purchase UI (the paywall, Settings › Subscription) **and** an enforce leg | ON when enforcement starts (review, ~11-09) | Same |
  | `monetize.pro` | **Retired:** deliberately not read (#394) | Stays OFF | Remove with the others |
  | `monetize.founder`, `monetize.season_pass` | Unused: no Founder or Season Pass SKU | Stay OFF | — |

  **Enforce = `entitlements.is_enforcing()` = `monetize.entitlements` ∧ `monetize.paywall` ∧ model_config
  `paywall_enforce_enabled` = 1** (the rule head-eng's #394, a draft, implements). `docs/config-reference.md` and
  `backend/feature_flags.py` `FLAG_KEYS` get the new semantics; the flag keys don't change.
- **New `model_config` keys** (deploy-free; `docs/config-reference.md`):
  - **`paywall_enforce_enabled`** (int 0/1, default **0**): **the ship-the-knob kill.** 0 means no request is ever
    blocked, whatever the flags say. A gate misfire locks every user out, so the rollback can't need a deploy.
  - **`paywall_web_enforce_enabled`** (int 0/1, default **0**): web enforcement, on top of `is_enforcing()`. A request
    without the native app's `X-Device` counts as web (#395). **head-product ruled the web stays ungated until 11-18;**
    it flips on 11-18 once `IOS_INSTALL_URL` resolves, on the operator's word.
  - **`paywall_preview_pages`** (int, **= 1**, decided: head-eng 10-25, Product's P49): the free deck pages for a
    never-entitled user, i.e. the first page of the first deck, served through E2 paging, with a per-user "preview
    used" record. #395's `PREVIEW_PAGES = 0` is known and fixed: **platforms-eng builds the allowance and merges it by
    11-06.** engagement-eng builds the end card and the offer trigger with knob = 1 as primary. **A 0 fallback (the
    offer at the first trade action) would be a Product decision, with copy rewrites.**
  - **The club window is server config,** not a knob: `closes_at` in `/api/paywall/config` must equal App Store
    Connect's scheduled price-change date, so it moves only with a reviewed deploy.
- **New env vars: none.** Existing key names only, values never in docs or chat:
  - `EXPO_PUBLIC_REVENUECAT_IOS_KEY` (EAS production, baked in at build, by ~11-07);
  - `REVENUECAT_WEBHOOK_SECRET` (Render and `secrets.local.env`; the webhook 503s without it).
- **API surface** (`docs/api-reference.md`). No new routes:
  1. **The global gate:** every route the classification table marks `gated` returns
     `402 {"error": "pro_required", "gate": "<enum>"}`, for a non-entitled user, while enforcing (web only once
     `paywall_web_enforce_enabled` is on). The enum is `preview_used | never_trialed | trial_expired | lapsed |
     verify_required`. **P47 as amended by legal R28.9 row 4** (`docs/plans/org-bringup/leads/legal-lead.md:1677`; Product's calls, head-product):
     - Pro counts only on verified or demo sessions.
     - **Unverified sessions get no free page (P53).** The account check `_verified_read_denial` (`backend/server.py:2787` on `origin/main` `db7425d4`, plus its decorator) returns
       403 `verification_required` to every unverified session on the deck, generate, swipe and propose routes. It
       runs before the paywall, is identical for every account, and passes only verified sessions and
       `_synthetic_demo_session`. So the verify sheet comes at the **first trade action**. **The client opens the same
       verify sheet for the 403 `verification_required` and the 402 `verify_required`.** The 402 stays as the second
       line of defence on gated routes: status-blind, unchanged, subscriber or not.
     - **Nothing differs by subscription status for an unverified session:** the 402 body is identical,
       `/api/me/entitlements` stays blank, and there's no timing or content tell (the gate decides an unverified
       session before any entitlement read).
     - **After verifying (P53),** the action is retried and the server decides: an entitled account continues (a Send
       returns to its confirmation, never sent without a tap); a not-entitled account gets what any verified account
       gets, **the free page if it hasn't been used, otherwise the standard paywall**.
     - **The client** keys the verify screen off `useSession.verification.session_verified`, never off a subscription
       signal, and shows no subscription surface (status, Restore, club lines) to an unverified session.
     - **The verify sheet (P53–P55; `docs/plans/org-bringup/reports/ux-lead.md` §3, amended; CTA strings cited, not
       copied):** a **Sleeper** session gets Verify with Sleeper **only**; Sign in with Apple is **removed** for it,
       because it switches accounts. **Any other unverified session** gets an honest line plus Apple's own Sign in with
       Apple button as a **new sign-in** ("reconnect your league in Settings"); **nothing carries over.** There's **no
       MFL path.** The ESPN/MFL sign-in buttons go off now via `landing.platform_options`: **an operator decision
       already taken** (release-lead flips it on the operator's word; nothing is flipped here).
     - **Copy (legal-approved, unchanged):** `mon.verify.title` "Verify this session first"; `mon.verify.body` "To use
       or start a subscription, verify this session first. Signing in confirms the account is yours."
     - One `before_request` hook reads a **per-route** table (`gated` | `free` | `never_gate`), not prefixes:
       `/api/league/*` and `/api/trades/*` mix families. The table follows recommendation §(c).
     - **Gated:** `/api/trades/generate`, `GET /api/trades` and `/status` beyond the preview page; `/swipe` and
       `/pass-reason` beyond it; `/propose`, `/propose-espn`, `/propose-mfl`, `/respond-mfl` and `/queue` (always);
       `/fair-packages`, `/asset-ideas`, `/standing-offer`; `/matches/<id>/disposition`; `/api/overhauls*`;
       **the four `/api/win-now/*` routes** (`/search`, `/evaluate`, `/jobs/<id>`, `/scenarios/<id>/decision`; #395,
       P52); Today's Trade.
     - **Never gated:** `/api/admin/*`, `/api/cron/*`, `/api/billing/*` (secret-guarded, provider or operator traffic).
     - **Two "demos", no conflict:** the **try-before-sync session** (`_synthetic_demo_session`) is **exempt** from the
       gate (head-eng coded it; moot while `try_before_sync` is off). The **App Review demo accounts** (one entitled,
       one never entitled) **stay gated**, so the reviewer sees the real gate.
     - **Everything else is `free`.** That includes `DELETE /api/account`, `/api/account/export`, `/api/me/entitlements`,
       `/api/paywall/config`, `/api/feature-flags`, `/api/events`, `/api/session/*`, `/api/auth/*`, `/api/sleeper/link`,
       `/api/extension/*`, every rank write, `/api/trade/evaluate`, `GET /api/trades/matches[/all]`, `/api/invite/*`,
       `/api/profile/*`, and **P48** (Product-confirmed against ux-lead's classification; #395 keeps them free):
       `POST /api/trades/validate`, `POST /api/trades/standing-offer/revoke`, `POST /api/trades/matches/<id>/dismiss`,
       `GET /api/trades/liked`; and **`GET /api/league/season-projections`** (the "Season projections & Win Now"
       standings; P52).
     - **The client source for engagement-eng** is ux-lead's classification with its "Decide" column decided by Product
       (`docs/plans/org-bringup/reports/ux-lead.md:495`): the calculator's value comparison FREE (its deck suggestions
       and sends gated); viewing Matches FREE (dismiss free; swipe, accept, send gated); Draft Room FREE; Calibration FREE.
     - `load_member_rankings` (`database.py:9281-9380`) is **not** filtered by entitlement.
  2. **`GET /api/me/entitlements`:**
     - `enforcing` becomes `is_enforcing()` (5b; today it reads one flag, `server.py:31168`);
     - it adds `founder` (bool) only, for the Settings status line, the Home mark and the kept-price line;
     - **for an unverified session it blanks every subscription field** (`pro`, `ad_free`, `sources`, `expires_at`,
       `founder`): byte-identical whether or not the user_id holds Pro.
  3. **`GET /api/paywall/config`** (`server.py:31209-31251`):
     - `club: {name, closes_at, open}`;
     - `products[].trial_period: "1 month"`, which replaces the client-built "`trial_days` days free" string
       (`PaywallScreen.tsx:173-175`);
     - `display_price` at the founder price while `open`, the standard price after;
     - a truthful `pages` grid (5c: the delivered gated features only; `engine_knobs`, `extension_overlays`, `ad_free`
       dropped);
     - `tips: []` at launch;
     - **`dismissible` stays `true`**: no non-dismissible mode. When access ends, a gated action opens this standard
       paywall; there is no bespoke gated state (the ruling);
     - the offer is **the one place** the trial terms and `club.closes_at` are shown (3.1.2; the ruling);
     - `trial_eligible` stays a per-SKU claim, while the client's "free" copy keys off RevenueCat's intro eligibility
       (ux rule 0.3).
  4. **The webhook projector:**
     - 5f: sandbox events are projected with `expires_at = min(payload, now + 24 h)`, tagged sandbox, never perpetual
       (head-eng's corrected fix);
     - 5d: a guard that refuses a perpetual grant for any non-founder product.

## 3. Evidence scope

<!-- D-056 (2026-08-15) retired Maestro and the simulator ENTIRELY. -->

- **§Maestro delta: n/a, retired by D-056.** No flow authoring, no flow execution, no `screens/` captures.
- [x] **Structural guard: `mobile/tests/check-paywall-gate.js`** (dependency-free; `npm run test:paywall-gate` in
  `mobile/package.json`). It pins:
  1. `pro_required` handling in `mobile/src/api/client.ts` opens the standard paywall (in the deck, the kept page's end
     card, whose one button opens it) **only for user-initiated calls**. A background call never opens it (ux §3).
  2. The always-reachable screens contain no gate check: SignIn, LeaguePicker, LeagueJoin, the connect screens, the
     Settings pages, `AccountDataSection` (Delete and Export), `AboutSection` (Privacy and Terms), the FeedbackFAB and
     inbox, and Rank / Calibration.
  3. **Restore** renders on the standard paywall and in Settings › Subscription.
  4. The "free" trial copy reads RevenueCat eligibility, not `config.trial_eligible`. The string "days free" is gone,
     and no user-facing string says "30 days".
  5. The offer's surface id sits in `SURFACE_PRIORITY` directly after `guide_step` (`useInterruptCoordinator.ts:65-71`).
  6. **No trial-time copy** (the ruling): a string scan of the paywall, welcome, Home, deck and Settings sources fails on
     a countdown, days-left or ends-soon phrase, or a trial-end date outside the offer.
  7. The tip row is hidden at launch. Update `check-tipjar.js` to match.
  8. The plan-title fallbacks read exactly `Fleeced Pro Monthly` / `Fleeced Pro Annual`, plain space, no dash
     (`PaywallScreen.tsx:73-74` still has the em-dash form; engagement-eng's D14,
     `docs/plans/org-bringup/leads/engagement-eng-paywall.md:47`, lands before the binary).
- [x] **Unit tests** (backend pytest; targeted locally, the full suite in GitHub CI per the throttle rule):
  - `backend/tests/test_paywall_gate.py` **(the gate matrix).** Cross every combination of:
    - the flags × the knob (0/1);
    - user state: never-entitled before and after the preview; in trial; paid; trial expired; lapsed; manual grant;
      sandbox-capped; **unverified sessions, on a subscriber and a non-subscriber account**; a never-entitled account
      (the App Review demo's case: gated); the try-before-sync session (exempt: never 402 or 403);
    - client: native (`X-Device`) vs web, × `paywall_web_enforce_enabled` (0/1);
    - route class, including the four P48 routes and `GET /api/league/season-projections` (always free) and the four
      `/api/win-now/*` routes (gated; P52).

    Expect 200 or 402, with the exact `gate` value. Also: **`paywall_preview_pages` = 1 → page 1 served, page 2 → 402
    `preview_used`** (an unverified session never reaches page 1: 403 `verification_required` from the account
    check); cron-built decks never consume the preview; a send in preview → `never_trialed`; **an unverified session
    gets 403 `verification_required` on the deck, generate, swipe and propose routes before any paywall logic, and 402
    `verify_required` on the other gated routes, never another value; after verifying, an unused free page is served**;
    knob 0 → never 402; web knob 0 → no web 402; the 402 body carries no route family.
  - `backend/tests/test_paywall_gate_allowlist.py` **(completeness).** Iterate `app.url_map`, and fail on any rule
    missing from the classification table. A pinned list must stay non-gated (`DELETE /api/account`, export,
    entitlements, paywall config, feature flags, events, session, auth, billing, admin, cron, and the four P48 routes).
    **Sabotage, each one red:**
    - delete a table row;
    - mark `DELETE /api/account` gated;
    - add an entitlement filter to `load_member_rankings`.
  - **`backend/tests/test_paywall_gate_status_blind.py` (new; legal R28.9 row 4, P53).** Two unverified sessions, one
    whose user_id holds Pro and one that doesn't. **At the deck** both get byte-identical 403 `verification_required`
    from the account check, before any paywall logic. **On a gated non-deck route (the 402 backstop)** both get
    byte-identical 402 `verify_required`. `/api/me/entitlements` is byte-identical and blank for both, and the gate
    path reads no entitlement before deciding (a spy on `get_entitlements`, the mechanical proxy for a timing tell).
    **Sabotage:** branch the unverified case on `pro` → red.
  - `backend/tests/test_member_rankings_ungated.py`: a lapsed leaguemate's board still loads, and the payer's card
    `basis` is `two_board` (`trade_policy.py:94-96`).
  - `backend/tests/test_entitlements_sandbox_cap.py`: 5f's 24 h cap and 5d's perpetual guard, with sabotage.
  - `backend/tests/test_paywall_config.py` (extend): the club block open and closed around `closes_at`, `trial_period`
    "1 month", the founder vs standard `display_price`, the truthful grid, `tips: []`, `dismissible: true`.
  - `backend/tests/test_me_entitlements.py` (extend): `enforcing` = `is_enforcing()` across flags × knob (5b), with
    `monetize.pro` ignored; `founder` from fixture ledger payloads; for unverified sessions, every subscription field
    blank and the body identical whether or not the user_id holds Pro.
  - The analytics registration: `entitlement_granted` ∈ `SERVER_FIRED_EVENTS` and ∉ `NON_INTENT_EVENTS`;
    `paywall_gate_hit` in both; the daily cap.
- [ ] **Code-walk proof (written by the builder, file:line cited, linked here before merge).** Required traces:
  1. **The invitee:** LeagueJoin → SignIn → session init (free) → the first page → a swipe → the FR-17 activation
     helper fires → **then** the offer (ux §1, §5 B6).
  2. **The purchase:** the offer → Apple's sheet → RevenueCat webhook → `_project` (`entitlements.py:507`) →
     `/api/me/entitlements` → the deck resumes on the same card.
  3. **Delete while gated:** Settings › Account → `AccountDataSection` → `DELETE /api/account` (`server.py:28133`) is
     never-gated.
  4. **The kill:** knob 0 → the hook returns early, before any entitlement read.
  5. **A lapsed leaguemate's board** in `load_member_rankings` → a `two_board` card for the payer.
  6. **Web:** a 402 → the "continue on iPhone" state; sign-in, settings, legal and delete reachable.
- [x] **Manual TestFlight checklist** (sandbox build; the operator runs it, and app-manager folds it into its
  checklist). **20 steps.** T1–T8 are **8 of ux-lead's 10** (M1–M5 and M8–M10, `reports/ux-lead.md:205-229`), cited, not
  rewritten. M6 (the days-28–30 Home line) and M7 (the post-trial in-place gated state) are removed: the operator ruling
  of 2026-10-24 supersedes them. T9–T20 are added, with no duplicates; T13–T14 follow ux-lead's addendum V1–V6
  (amended). **Every never-entitled check runs on a fresh account** (`docs/plans/org-bringup/leads/app-manager-monetization-setup.md`
  §8). **App Review demo B (never entitled) is reserved for App Review:** it is never used for testing and stays pristine.
  1. **T1 (ux M1)** [fresh, verified, never-entitled account; an unverified one gets the verify sheet instead, T13] Onboard → first deck → Like one card. **Expect:** the offer appears only after the
     swipe settles, and shows price, renewal, Restore, Privacy and Terms.
  2. **T2 (ux M2)** Start the free month. **Expect:** Apple's sheet → the welcome → back to the same card.
  3. **T3 (ux M3, as adjusted by the ruling)** [fresh, verified, never-entitled account] Not now. **Expect:** you keep swiping the current page;
     its end card's button opens the standard paywall; a new Find a trade opens the standard paywall; Rank works.
  4. **T4 (ux M4)** [an Apple ID that used the intro] **Expect:** no "free" anywhere; the price and Subscribe.
  5. **T5 (ux M5)** Restore on the paywall and in Settings. **Expect:** both work; "nothing found" reads honestly.
  6. **T6 (ux M8)** [gated] Rank, Settings, Delete (with the subscription note), Export, Privacy, Terms, Help,
     Feedback. **Expect:** all work.
  7. **T7 (ux M9)** [invitee] #386 → install → re-tap → sign in → first deck → first Like. **Expect:** the inviter's
     activation row arrives before the offer, and the offer shows the invite line.
  8. **T8 (ux M10)** [VoiceOver] The offer, the welcome, the deck end card. **Expect:** focus goes title → body →
     primary → secondary, and the close control is reachable.
  9. **T9 (access ends)** [sandbox trial expired, or lapsed] Try every gated entry point (Home tile, League ×2, a Matches
     accept, Usage Trends Trade, Summary Offer/Target, the calculator's Find a trade, Send). **Expect:** each opens the
     standard paywall (price, renewal, Restore, Privacy, Terms, a close control); closing it returns you to where you
     were; nothing appeared on its own when access ended.
  10. **T10** [gated] The free surfaces: the calculator's value comparison, existing Matches (view only), Draft Room,
      Calibration, Trends, League standings. **Expect:** all work, with no 402 and no paywall. **Sub-step (league-pm,
      P52), for a non-subscriber:** League Summary → "Season projections & Win Now" → the standings load with no
      paywall; "Find Win Now trades" → the standard paywall; closing it returns to the standings.
  11. **T11 (kill)** release-lead sets `paywall_enforce_enabled` = 0, on the operator's word. **Expect:** the gated
      account gets a full deck on the next Find a trade. Back to 1 → gated actions open the standard paywall again.
  12. **T12 (gated re-entry)** From a second account, Like a package that mirrors the gated account's. **Expect:** the
      existing push's tap lands on Matches (viewable); accepting opens the standard paywall.
  13. **T13 (status-blind verify; ux addendum V1, V2, V6, amended)** [two unverified Sleeper-username sessions: the
      entitled Demo A and a fresh never-entitled account; never demo B] Tap Find a trade; open Settings › Subscription.
      **Expect, for both:** no deck; the identical "Verify this session first" sheet at once (the 403 from the account
      check), with Verify with Sleeper and Cancel only, no Sign in with Apple; Settings shows one identical row;
      nothing on or around them differs (compare side by side).
  14. **T14 (after verifying; ux addendum V3–V5, amended)** Verify each T13 session. **Expect:** the subscriber's
      action continues (a Send returns to its confirmation, nothing sent until you tap); the fresh non-subscriber gets
      **the free page** (unused), with the offer after its first opinion; an account whose free page is used gets the
      standard paywall; a different Sleeper login shows the wrong-account message.
  15. **T15 (a fresh never-entitled account, standing in for App Review demo B)** Gated like any user (only the
      try-before-sync session is exempt): preview → offer → sandbox purchase. **Expect:** entitled within one refresh, and the sandbox grant expires ≤ 24 h
      later (5f).
  16. **T16 (App Review demo A, entitled)** Manual grant. **Expect:** no offer, a full deck; Settings shows the plan.
  17. **T17 (terms once; titles)** **Expect:** "1 month", never "30 days"; the trial terms (duration, end behavior,
      price) and the cut-off appear once, on the offer; the plan titles read exactly `Fleeced Pro Monthly` / `Fleeced
      Pro Annual`, matching App Store Connect step 2g; the Terms and Privacy links open.
  18. **T18 (the ruling)** Walk Home, the deck, Matches, League, the welcome and Settings › Subscription, during the trial
      and after it. **Expect:** no countdown, days-left or ends-soon text on any surface, including Settings; Settings ›
      Subscription shows status, plan, Manage and Restore only.
  19. **T19 (web)** [gated account on web] Before the 11-18 flip: **Expect** no web 402. After
      `paywall_web_enforce_enabled` = 1: a **verified** session gets the first deck, then "continue on iPhone"; an
      **unverified** one gets the web verify screen (ux addendum V7). Rank, Settings, Delete and legal reachable; no
      purchase UI.
  20. **T20 (extension)** [gated account] Sign in to the extension. **Expect:** the rankings overlay loads, with no 402.
- [ ] **WAIVED:** n/a. Every row above is answered. W-MON-2 (§6) covers the one behavior that can't be exercised
  before launch.
- **`testID`s added** (proposed names; they must pass `mobile/scripts/testid-lint.sh`): `paywall-offer-cta`,
  `paywall-offer-not-now`, `paywall-restore` (existing), `deck-end-paywall-cta`, `settings-subscription-row`,
  `settings-subscription-restore`, `settings-subscription-manage`, `founder-welcome-back`.
- **§Simulator-gate tier: n/a, retired by D-056.** There's no tier to declare and no `qa/sim-runs/last-sim-run.json`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** (at build) | The 402 contract (`pro_required` + `gate`) on every gated route; `/api/me/entitlements` (`enforcing`, `founder`); `/api/paywall/config` (`club`, `trial_period`, the grid, `tips`) |
| `living-memory/LLD.md` | **updated** | A convention shift: one `before_request` per-route classification gate replaces per-route `@require_pro`; a new route must be classified (CI-enforced). "The server never mints trials" stays true. The `paywall_preview_pages` allowance and its per-user "preview used" record |
| `docs/architecture.md` | **updated** | A cross-cutting gate in the request pipeline. The billing ledger → entitlements → gate data flow |
| `living-memory/HLD.md` | **updated** | Monetization becomes live access control across iOS, web and the extension: a major flow |
| `docs/cross-client-invariants.md` | **updated** | § "Monetization SKU ids…" (`:1204`): the 402 `gate` enum (with the status-blind `verify_required`); the `paywall_viewed.source` enum; `ftf_pro_monthly` / `ftf_pro_annual` at founder $4.99 / $24.99 → standard $6.99 / $34.99; `trial_period` "1 month"; `club` field names; tips not served at launch |
| `docs/glossary.md` | **updated** | Founding GMs (the operator's name, decided 2026-10-25), the preview, the standard paywall on gated surfaces, the preserved price |
| ADR or `DECISIONS.md` entry | **updated** | **A new ADR** (next free number; ADR-025 is the packing draft) **plus a D-entry** (D-209 on main today; grep first), written by head-eng. It overturns foundation §2.2 "never wrap the core loop" (`00-platform-foundation.md:131-134`) and the `_require_pro` docstring (`server.py:31144-31146`) on the operator's direction; the 2026-08-14 never-gated list; never-tolled for swipes (BL-001); the August trial ruling. It records price preservation as the Founder mechanism, and C2's rule |
| `docs/data-dictionary.md` | **n/a** unless head-eng's storage needs a column (§2). Fix the entitlements-deletion drift while there |
| `docs/config-reference.md` | **updated** | `paywall_enforce_enabled`, `paywall_web_enforce_enabled`, `paywall_preview_pages`; the `monetize.*` semantics (`:438-448`), with `monetize.pro` marked retired; the `FTF_FLAGS` note |
| `docs/integrations/revenuecat.md` | **new** | RevenueCat is an external service with no file today: the intro-eligibility check, the webhook, the sandbox cap, and the safe-to-log / must-redact split |
| `docs/runbook.md` | **updated** | The kill: `paywall_enforce_enabled` → 0, on the operator's word, and how to verify it |
| Terms alignment (`web/terms.html`, #373 @ `d866706b`; P50) | **aligned** (checked by the lead) | §14.8 matches this scope: $4.99/$24.99 for subscribing by 2026-12-31; $6.99/$34.99 for new subscribers from 2027-01-01; "won't go up for as long as your subscription stays active on that plan" = keep-current-price; legal's lapse wording; §14.3's "1-month" trial. It also matches `docs/plans/org-bringup/leads/app-manager-monetization-setup.md` steps 2d, 2e and 3a–3c. **Dependency:** "Starting a free trial counts as subscribing" holds only if both increases start after Dec 31 has ended in every US zone: **scheduled 2027-01-02, starting 04:00 UTC = Jan 1, 11 pm ET** (operator 2026-10-28, "Yes, Jan 2"; Apple's start-times table puts a 2027-01-01 change at Dec 31, 11 pm ET). Legal-lead is rewording §14.8's "From January 1, 2027" to match. §14.8 names no plans. **ASC step 2g display names:** `Fleeced Pro Monthly` (`ftf_pro_monthly`), `Fleeced Pro Annual` (`ftf_pro_annual`), plain space, no dash (marketing §9.4 `mon.pay.plan.*`, D-h, legal R28.8 "match exactly"); proposed group `Fleeced Pro`; marketing-lead writes the descriptions via head-bizops |

## 5. Ship gate declaration

<!-- The simulator-gate tier matrix is RETIRED (D-056, 2026-08-15). -->

- **CI green:** `backend-tests`, plus `mobile-typecheck` (which also runs the `check-*.js` suites), plus
  `maestro-testid-lint`, all passing on the pushed sha. Push with `FTF_SKIP_SIM_GATE=1` (the D-056 standing posture),
  noting the evidence above.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the pytest files, `check-paywall-gate.js`, and
  the code-walk proof.
- **TestFlight verification:** T1–T20 are run by the operator on the 11-07 build, with the outcome logged in TEST_LEDGER
  **before the 11-10 submission**. The update-1 moments (the Home mark, the kept-price line) get T18 again on that build.
- **Order:**
  - the server registration and gate deploy (enforcement off) **before** the 11-06 binary;
  - **the preview precondition (P49), in release-lead's flip checklist, before `paywall_enforce_enabled` = 1:**
    `paywall_preview_pages` = 1 confirmed, page 1 served, then 402 on page 2;
  - enforcement on (flags plus knob) for review, on the operator's word;
  - `paywall_web_enforce_enabled` on 11-18, once `IOS_INSTALL_URL` resolves, on the operator's word;
  - the R1 checkpoint 11-03: if the client gate isn't CI-green, it comes out of the binary, and the route is R3.
- **Express lane declared by the operator?** **No**, and not eligible: API contracts, flag surfaces and analytics events
  are touched (the CLAUDE.md bright line).

## 6. Waivers (APPROVED by the operator, 2026-10-25, under "rest of PR #393")

- **W-MON-1: celebration-moment analytics.**
  - **What's waived:** events beyond `paywall_viewed`, `screen_viewed` and the ledger for the update-1 moments (the Home
    mark and the kept-price line).
  - **Why:** head-product's ask (f) is names only. ux-lead and design-lead's moment specs go to analytics-lead for
    grants before the update-1 build.
  - **Risk:** none for the 11-06 binary.
- **W-MON-2: price preservation at the cut-off can't be exercised before launch.**
  - **What's waived:** sandbox can't run a scheduled App Store Connect price change, and the 2027-01-02 change happens
    after launch. So runtime proof that trialists and subscribers keep the founder price is waived.
  - **Mitigation:**
    - the operator verifies the scheduled change, with "keep current price", in App Store Connect at setup (noted in
      TEST_LEDGER);
    - release-lead reads the first post-cut-off new subscription's price and a renewing founder's price from the ledger
      in the first week of January;
    - legal-lead's wording ("while subscribed, on your plan") bounds the promise.
