# Settings IA — hub page + second-level pages

> **Status:** active, not built · 2026-08-18
> **Entry point:** direct operator ask ("review the entire settings page live in prod, write a plan
> to re-organize the page into a set of grouped settings with a top level page and second level
> pages. Move it from a half sheet to actual page")
> **Scope block:** [`scope.md`](scope.md) — the mandatory feature gate for this work.

---

## Table of contents

- [1. What is live in prod today](#1-what-is-live-in-prod-today)
- [2. What is wrong with it](#2-what-is-wrong-with-it)
- [3. Target IA](#3-target-ia)
- [4. Row-by-row migration map](#4-row-by-row-migration-map)
- [5. Half sheet → real page](#5-half-sheet--real-page)
- [6. Data loading model](#6-data-loading-model)
- [7. Build phases](#7-build-phases)
- [8. Flag, deep links, analytics, testIDs](#8-flag-deep-links-analytics-testids)
- [9. Evidence plan (D-056)](#9-evidence-plan-d-056)
- [10. Docs to update](#10-docs-to-update)
- [11. Risks and open questions](#11-risks-and-open-questions)
- [12. Non-goals](#12-non-goals)

---

## 1. What is live in prod today

### How this was verified

The iOS app is TestFlight-only (v1.13.2) and D-056 retired the simulator, so there is no way to
drive the live app from this session. What was actually checked:

1. **Live prod feature-flag state** — `GET https://fantasy-trade-finder.onrender.com/api/feature-flags`
   (172 flags), read on 2026-08-18. Flags are what decide which rows render, so this is the real
   determinant of the live page.
2. **The shipped source** — `mobile/src/screens/SettingsScreen.tsx` (1,712 lines) at HEAD, confirmed
   byte-identical to `origin/main` (`git diff origin/main -- mobile/src/screens/SettingsScreen.tsx`
   is empty), i.e. this is the version in the TestFlight build.
3. **Registration and presentation** — [RootNav.tsx:510-529](../../../mobile/src/navigation/RootNav.tsx:510).

What was **not** done: no on-device pass, no screenshots. Section 9 turns that into an operator
TestFlight checklist rather than pretending it happened.

### Prod flag state that shapes the page (2026-08-18)

| Flag | Prod | Effect on Settings |
|---|---|---|
| `account.settings_v2` | **true** | v2 IA is the live layout; the legacy branch is dead code in prod |
| `trade.slot_pricing` | **true** | Pick-pricing segmented control renders |
| `ux.help_surface` | **true** | Help & FAQ row renders |
| `account.data_export` | **true** | Download my data renders |
| `account.sleeper_disconnect` | **true** | Sleeper sending row renders |
| `notif.denial_recovery` | **true** | Denied-permission banner can render |
| `onboarding.guided_avatar` | **true** | Guided tour section renders |
| `espn.link` / `mfl.link` / `mfl.auth_link` | **true** | ESPN + MFL link/disconnect rows render |
| `auth.accounts` | **true** | Identity rows + Link Apple render |
| `fleaflicker.link` | false | MFL row reads "Link an MFL league" (not "MFL or Fleaflicker") |
| `profiles.user_toggle` | **false** | Public-profile toggle is **dark in prod** |
| `testing.stage_users` | false | Testing section hidden in release builds |

### Live inventory — one screen, 7 section headers, ~25 controls

Composed at [SettingsScreen.tsx:1477-1553](../../../mobile/src/screens/SettingsScreen.tsx:1477):

| # | Section | Contents (prod flags) | Source |
|---|---|---|---|
| 1 | **Leagues** | one tappable row per league (only when >1); Connect card (help text + text input + Connect button); "Link an ESPN league"; "Link an MFL league" | [:767](../../../mobile/src/screens/SettingsScreen.tsx:767), [:811](../../../mobile/src/screens/SettingsScreen.tsx:811), [:836](../../../mobile/src/screens/SettingsScreen.tsx:836) |
| 2 | **Ranking** | `SteerSlider` (quickset / trio / anchor / tiers / manual) + hint | [:885](../../../mobile/src/screens/SettingsScreen.tsx:885) |
| 3 | **Trade values** | Stud tax segmented (Market / Heavy / Off) + desc; Pick pricing segmented (Tier ladder / Market) + desc | [:912](../../../mobile/src/screens/SettingsScreen.tsx:912), [:959](../../../mobile/src/screens/SettingsScreen.tsx:959) |
| 4 | **Guided tour** | "The Analyst" toggle | [:995](../../../mobile/src/screens/SettingsScreen.tsx:995) |
| 5 | **Notifications** | denied banner (conditional) + Trade matches / Weekly digest / Stay in the game toggles + Pause overnight toggle + Time zone value row + "Detected from this device" footnote | [:1021](../../../mobile/src/screens/SettingsScreen.tsx:1021), [:1043](../../../mobile/src/screens/SettingsScreen.tsx:1043), [:1066](../../../mobile/src/screens/SettingsScreen.tsx:1066) |
| 6 | **Account** | identity rows (Apple/Google); Link Apple card; Sleeper `@username`; account-only link form; Verification value row + explainer; Verify account; Disconnect Sleeper sending; Disconnect ESPN account; Disconnect MFL sign-in; ~~Public profile~~ (dark); Download my data; **Delete account** | [:1255](../../../mobile/src/screens/SettingsScreen.tsx:1255) and [:1126](../../../mobile/src/screens/SettingsScreen.tsx:1126)–[:1243](../../../mobile/src/screens/SettingsScreen.tsx:1243) |
| 7 | **About** | Help & FAQ; Privacy Policy; Terms of Use | [:1416](../../../mobile/src/screens/SettingsScreen.tsx:1416) |
| — | *Testing* | hidden in prod (`__DEV__ \|\| testing.stage_users`) | [:1086](../../../mobile/src/screens/SettingsScreen.tsx:1086) |
| 8 | **Sign out** | destructive text row | [:1461](../../../mobile/src/screens/SettingsScreen.tsx:1461) |

Entered from the gear in the global TopBar ([TopBar.tsx:392-407](../../../mobile/src/components/TopBar.tsx:392))
and from Portfolio ([PortfolioScreen.tsx:67](../../../mobile/src/screens/PortfolioScreen.tsx:67)).

---

## 2. What is wrong with it

Ordered by how much the reorganization actually buys.

**F1 — Everything is one scroll, including the two most destructive actions.** Delete account and
Sign out sit at the bottom of ~25 controls with no landmarks between them and the top. The #243
scroll audit already reached this conclusion from the other direction and called it "expected for a
long settings list" ([league-misc-surfaces.md §5](../../feedback/items/243-scroll-audit/league-misc-surfaces.md)) —
correct as a *density* verdict, which is why the fix is structural, not a whitespace trim.

**F2 — Platform connections are split across two sections that never mention each other.** "Link an
ESPN league" lives under **Leagues**; "Disconnect ESPN account" lives under **Account**, ~15 rows
away. Same for MFL. A user who wants to un-link ESPN has no reason to look in Account.

**F3 — Account is doing four unrelated jobs.** Identity (who you signed in as), security
(verification), platform credentials (three disconnects), and data rights (export + delete) are one
undifferentiated list of hairline rows. The destructive action is visually a peer of "Sleeper
sending: Not connected".

**F4 — The whole screen blocks on the notifications query.**
[SettingsScreen.tsx:750](../../../mobile/src/screens/SettingsScreen.tsx:750) returns a full-screen
spinner while `prefsQuery.isLoading`. Opening Settings to switch leagues waits on
`GET /api/notifications/prefs`. Six `useQuery` calls plus two `useEffect` fetches (stud tax, pick
pricing) fire on every open, for a page where a user typically touches one control.

**F5 — The modal presentation forces a navigation hack.**
[SettingsScreen.tsx:227-234](../../../mobile/src/screens/SettingsScreen.tsx:227):

```ts
const navigateFromSettings = (route, params) => {
  if (settingsV2) { navigation.goBack?.(); navigation.navigate?.(route, params); }
  else { navigation.navigate?.(route, params); }
};
```

Every outbound link (Verify account → SleeperConnect, Link ESPN → LeaguePicker, Test feedback →
FeedbackInbox) dismisses Settings first, because pushing onto a modal stack strands the user. The
cost: back from SleeperConnect lands on the tabs, not on Settings. This exists *only* because
Settings is a modal.

**F6 — Modal presentation also costs the feedback surface.** SettingsScreen mounts no `FeedbackFAB`
(count: 0). That is legal today — #188 exempts modals/sheets — so Settings is one of the few
surfaces where a tester cannot file feedback in place.

**F7 — No version/build row.** `grep -i version` on SettingsScreen returns nothing. A shipping app's
About section should state the build; support triage needs it.

**F8 — Sub-page-worthy content has no sub-page.** "Trade values" (stud tax + pick pricing) changes
how every trade in the app is priced and gets one unlabelled segmented row inline. "Ranking" changes
where a whole tab opens. Both deserve room for the explanation they currently compress into a
`body-sm` line.

---

## 3. Target IA

### Top level — `Settings` (hub)

A pushed page. Identity block, then grouped nav rows with **state previews**. **Sign out is not on
the hub** — operator decision 2026-08-18; it lives on the Account page (see below).

```
┌ Settings ───────────────────────────────── ‹ back ┐
│                                                    │
│  @mattmurphy                        Verified ✓     │   ← identity block, taps → Account
│                                                    │
│  LEAGUES                                           │   ← TickLabel group banner
│  Leagues                                        ›  │
│    Dynasty Warlords + 2 more · Sleeper, ESPN       │
│                                                    │
│  HOW THE APP WORKS                                 │
│  Ranking                                        ›  │
│    Opens on Tiers                                  │
│  Trade values                                   ›  │
│                                                    │
│  ALERTS                                            │
│  Notifications                                  ›  │
│    2 of 3 on · Quiet hours 10p–8a                  │
│                                                    │
│  ACCOUNT                                           │
│  Account & data                                 ›  │
│    Apple · Verified · Sign out                     │
│                                                    │
│  ABOUT                                             │
│  Help & about                                   ›  │
│    FAQ, privacy, terms · v1.14.0                   │
│                                                    │
│  [Testing]                                      ›  │   ← dev/tester builds only
│                                                    │
└────────────────────────────────────────────────────┘
```

Six rows (five in release builds + Testing), each ≥44pt. Fits one screen with no scroll on a
393×852 device — the first time Settings has.

**Why previews matter.** A hub without them trades one scroll for N taps and is a net loss. The
subtitle answers the question the user came to ask ("are notifications on?", "which stud tax am I
on?") without a drill-in. Preview data must be free — see §6.

### Second level — five pages (+ Testing)

| Route | Title | Owns |
|---|---|---|
| `SettingsLeagues` | Leagues | Switch league · Connect a league · Link ESPN · Link MFL · **all three platform disconnects** |
| `SettingsRanking` | Ranking | Rank-home `SteerSlider` + the "your suggestions are only as good as your rankings" explainer, given room |
| `SettingsTradeValues` | Trade values | Stud tax · Pick pricing, each with a real explanation of what it changes |
| `SettingsNotifications` | Notifications | Denied banner · 3 delivery toggles · Quiet hours · Time zone |
| `SettingsAccount` | Account & data | Identities · Link Apple · Sleeper identity · Verification + Verify CTA · **Sign out** · Public profile (when flagged on) · Download my data · **Delete account** |
| `SettingsAbout` | Help & about | The Analyst toggle · Help & FAQ · Privacy · Terms · **Version + build (new)** |
| `SettingsTesting` | Testing | Test feedback · Test stages — registered unconditionally, entry row gated (`__DEV__ \|\| testing.stage_users`), per the RootNav convention |

**Three grouping calls worth stating explicitly:**

1. **Ranking and Trade values stay separate pages** even though each is small. They answer different
   questions ("where does the Rank tab open" vs "how is a trade priced"), and merging them
   reproduces the undifferentiated-list problem at smaller scale. The hub groups them visually under
   one `HOW THE APP WORKS` banner, which is where the affinity belongs.
2. **All platform disconnects move to Leagues** (fixes F2). A platform connection is one thing —
   link it and unlink it in one place. Account keeps *identity* (Apple/Google/Sleeper), not
   *credentials for other services*.
3. **The Analyst goes to Help & about**, not to its own group. It is the in-app help system; it
   belongs beside the FAQ link.
4. **Sign out moves to the Account page** (operator decision, 2026-08-18). It becomes a two-tap trip
   from the gear instead of one, which is the iOS convention and keeps the hub purely navigational.
   **Placement within the page matters:** Sign out sits directly under the identity/verification
   block — the session it terminates — and **Delete account stays last**, after Download my data.
   Putting the two destructive controls at opposite ends of the page is deliberate; stacking them
   adjacent invites a mis-tap on the irreversible one. Flip this at build time if you want Sign out
   at the very bottom, but do not let the two end up neighbours.

---

## 4. Row-by-row migration map

Nothing is dropped. Every row below exists in prod today; the "new" marks are additions.

| Today's row | Today's section | Goes to | Notes |
|---|---|---|---|
| League rows (switch) | Leagues | `SettingsLeagues` | unchanged behavior |
| Connect league card | Leagues | `SettingsLeagues` | unchanged |
| Link an ESPN league | Leagues | `SettingsLeagues` | still routes to `LeaguePicker {espnLink:true}` |
| Link an MFL league | Leagues | `SettingsLeagues` | unchanged |
| Disconnect Sleeper sending | **Account** | `SettingsLeagues` | **moved** (F2) |
| Disconnect ESPN account | **Account** | `SettingsLeagues` | **moved** (F2) |
| Disconnect MFL sign-in | **Account** | `SettingsLeagues` | **moved** (F2) |
| `SteerSlider` + hint | Ranking | `SettingsRanking` | unchanged; keeps the v2 immediate-apply reroute |
| Stud tax segmented | Trade values | `SettingsTradeValues` | unchanged |
| Pick pricing segmented | Trade values | `SettingsTradeValues` | unchanged |
| The Analyst toggle | Guided tour | `SettingsAbout` | **moved** |
| Denied-permission banner | Notifications | `SettingsNotifications` | unchanged |
| Trade matches / Weekly digest / Stay in the game | Notifications | `SettingsNotifications` | unchanged |
| Pause overnight | Notifications (v2-folded) | `SettingsNotifications` | unchanged |
| Time zone + footnote | Notifications | `SettingsNotifications` | unchanged |
| Demo session row | Account | `SettingsAccount` | unchanged |
| Identity rows (Apple/Google) | Account | `SettingsAccount` | also feeds the hub identity block |
| Link Apple card | Account | `SettingsAccount` | unchanged |
| Sleeper `@username` | Account | `SettingsAccount` | unchanged |
| `LinkSleeperForm` (account-only) | Account | `SettingsAccount` | unchanged; keeps `navigation.replace('LeaguePicker')` |
| Verification row + explainer | Account | `SettingsAccount` | also feeds the hub identity block |
| Verify account | Account | `SettingsAccount` | now a real push — back returns to Account (F5) |
| Public profile toggle | Account | `SettingsAccount` | dark in prod; carried, still flag-gated |
| Download my data | Account | `SettingsAccount` | unchanged |
| Delete account | Account | `SettingsAccount` | stays **last** on its page, isolated from Sign out |
| Help & FAQ | About | `SettingsAbout` | unchanged |
| Privacy Policy / Terms of Use | About | `SettingsAbout` | unchanged |
| Test feedback / Test stages | Testing | `SettingsTesting` | hub row gated as today |
| Sign out | — | `SettingsAccount` | **moved** (operator decision) — under the identity block, not adjacent to Delete account. Two taps from the gear instead of one. |
| — | — | `SettingsAbout` | **new:** Version + build from `expo-constants` (F7) |
| — | — | every page | **new:** `FeedbackFAB activeScreen="<RouteName>" aboveTabBar={false}` (F6, #188) |

---

## 5. Half sheet → real page

### The change

[RootNav.tsx:510-529](../../../mobile/src/navigation/RootNav.tsx:510) currently registers Settings with
`presentation: 'modal'` (iOS page-sheet — the card that stops short of the top, i.e. the "half
sheet") plus a `HeaderClose` ✕ added by feedback #130 because swipe-dismiss was undiscoverable.

Replace with a standard push:

- drop `presentation: 'modal'` (default card push);
- swap `headerRight: HeaderClose` for `headerLeft: HeaderBack` with `headerBackVisible: false` —
  the existing #151 pattern at [RootNav.tsx:168](../../../mobile/src/navigation/RootNav.tsx:168),
  required because the native back control goes dead on iOS 26 when the previous screen runs
  `headerShown: false` (react-native-screens#3294), which `Main` does;
- register the five/six second-level screens the same way.

### What it fixes for free

- **F5 disappears.** `navigateFromSettings` collapses to a plain `navigation.navigate(...)`. Back
  from SleeperConnect returns to `SettingsAccount`. Delete the `settingsV2` branch in that helper.
- **F6 becomes possible.** Pushed pages are not exempt from #188 — each settings page mounts its own
  `FeedbackFAB`.
- **Deep links get somewhere to land.** `settings/notifications` can open a real page with a real
  back stack, instead of a modal with no parent.
- **The ✕ goes away.** #130 was a workaround for a presentation we are removing; a back chevron is
  the discoverable control it was reaching for.

### What to watch

- **Gesture regression.** Users on 1.13.2 dismiss Settings by swiping down. A pushed page swipes
  *right*. This is a learned-gesture change — the TestFlight checklist (§9) covers it explicitly.
- **Tab bar.** Root-stack pushes cover the tabs, same as today's modal. No change in what is
  visible; verify anyway on the first build.
- **`navigation.replace('SignIn')`** in the sign-out handler and `replace('LeaguePicker')` in the
  account-only link flow are stack operations that behave differently from a modal root. Both need a
  code-walk in the build phase, and both are on the checklist.
- **#130 stays in the record.** The ✕ was a real fix for a real complaint; the plan removes the
  *presentation*, not the finding. Note it in `DECISIONS.md` so nobody re-adds a modal later citing
  #130.

---

## 6. Data loading model

The split is also the fix for F4.

**Hub fetches nothing on the network.** Previews come from data already in memory:

| Hub row | Preview source | Cost |
|---|---|---|
| Leagues | `useSession(s => s.leagues)` + active league | free (store) |
| Ranking | `useSession(s => s.rankingMethodPref)` | free (store) |
| Trade values | **none — no preview.** Stud tax and pick pricing are fetched by bare effects with no React Query key, so nothing is free to read on a cold open. Printing the code default as the user's setting is the exact lie this rule forbids. Row is title + chevron only. |
| Notifications | `['notif-prefs']` from the React Query cache **if already resident**, else no subtitle | free |
| Account & data | `useSession(s => s.user)` + `['account']` cache if resident | free |
| Help & about | `Constants.expoConfig.version` | free |

Rule: **a subtitle that is not known for free is not rendered.** A stale or wrong preview is worse
than none — it is a setting screen lying about a setting.

**Each second-level page owns its own queries**, which is a straight lift of today's blocks:

| Page | Queries |
|---|---|
| `SettingsLeagues` | `['sleeper-link']`, `['espn-link']`, `['mfl-link']` |
| `SettingsRanking` | none |
| `SettingsTradeValues` | `getStudTaxMode()`, `getPickPricingMode()` |
| `SettingsNotifications` | `['notif-prefs']` |
| `SettingsAccount` | `['account']`, `['profile-visibility']` |
| `SettingsAbout` | none |

Net effect: opening Settings goes from 6 queries + 2 fetches to **zero**, and the full-screen
`prefsQuery.isLoading` gate ([:750](../../../mobile/src/screens/SettingsScreen.tsx:750)) moves to the
Notifications page where blocking on notification prefs is honest. Per-page loading states stay
in-place (skeleton rows, not a full-screen spinner) so a slow link-status query never blanks a page.

---

## 7. Build phases

Each phase is independently mergeable and leaves the app shippable.

**Phase 0 — extract the section blocks (no behavior change).**
Move the nine section blocks out of `SettingsScreen.tsx` into
`mobile/src/screens/settings/sections/*.tsx`, each owning its own queries and handlers. Keep the
existing v2 screen composing them in the current order. `tsc --noEmit` green, testIDs unchanged.
This is the load-bearing phase — a 1,712-line component with all state hoisted to the top is why
this refactor looks expensive; it stops being expensive once the blocks are standalone.

**Phase 1 — presentation.** Flip `Settings` from `presentation: 'modal'` to a push, swap
`HeaderClose` → `HeaderBack`, simplify `navigateFromSettings`, mount `FeedbackFAB`. Ships behind
`account.settings_hub` (default **off**) so the modal remains the release path until Phase 3.

**Phase 2 — pages.** Add `SettingsLeagues` / `SettingsRanking` / `SettingsTradeValues` /
`SettingsNotifications` / `SettingsAccount` / `SettingsAbout` / `SettingsTesting`, each composed from
Phase 0 blocks. Move the three disconnect rows to Leagues; move The Analyst to About; add the version
row.

**Phase 3 — the hub.** New `SettingsHubScreen`: identity block, grouped nav rows with previews, Sign
out. `Settings` route becomes the hub when `account.settings_hub` is on and the flat v2 list when it
is off — same single-flag pattern as `account.settings_v2` at
[SettingsScreen.tsx:1477](../../../mobile/src/screens/SettingsScreen.tsx:1477).

**Phase 4 — graduate and clean up.** After one TestFlight round with the flag on: default the flag
true, then delete the legacy branch **and** the `account.settings_v2` legacy branch, which has been
dead in prod since `settings_v2` shipped true. Retire both flags from `config/features.json`,
`backend/feature_flags.py`, and `docs/config-reference.md`.

**Nav-row component.** The hub row (title + preview subtitle + chevron) is a new construction. It is
close to the existing `linkRow` at [SettingsScreen.tsx:1638](../../../mobile/src/screens/SettingsScreen.tsx:1638)
but adds a value-preview line. It needs a spec row in
[`docs/design/components.md`](../../design/components.md) § Navigation before it ships — Chalkline rules
(ADR-004/005): hairline rows on `--ink-0`, `label` title, `body-sm` chalk-dim preview, ice only for
action affordances, no emoji, no new radii.

---

## 8. Flag, deep links, analytics, testIDs

**Flag.** `account.settings_hub`, default `false`. Graduation: one operator TestFlight pass against
the §9 checklist with no P0. Registered in `config/features.json` + `backend/feature_flags.py`
`FLAG_KEYS` + `docs/config-reference.md`.

**Deep links.** `ux.deeplink_router_v2` is **true** in prod;
[deepLinks.ts:99](../../../mobile/src/utils/deepLinks.ts:99) maps `Settings: 'settings'`. Add:

```
SettingsLeagues:       'settings/leagues'
SettingsRanking:       'settings/ranking'
SettingsTradeValues:   'settings/trade-values'
SettingsNotifications: 'settings/notifications'
SettingsAccount:       'settings/account'
SettingsAbout:         'settings/about'
```

`settings` keeps resolving to the hub, so every existing link and the TopBar gear are unaffected.
The legacy 5-route map at [RootNav.tsx:352-361](../../../mobile/src/navigation/RootNav.tsx:352) needs no
change — it keeps `Settings: 'settings'` and the flag-off path is the flat list anyway.

**Analytics — no new events needed.** RootNav already emits `screen_viewed {screen, prev_screen, tab}`
on every route change ([RootNav.tsx:395](../../../mobile/src/navigation/RootNav.tsx:395)), and
`analytics_taxonomy.py` puts no allowlist on the `screen` value. So "which settings groups do people
open, and which do they never find" is answered for free by `screen_viewed` with
`screen=SettingsAccount` etc. Confirm `screen_viewed` is in `NON_INTENT_EVENTS` (it is, as an
app-lifecycle event) so the new screens do not inflate intent metrics.

**testIDs.** Every existing `settings.*` testID moves with its row unchanged — `settings.link-espn`,
`settings.link-platform`, `settings.sleeper-disconnect`, `settings.espn-disconnect`,
`settings.mfl-disconnect`, `settings.export-data`, `settings.help-faq`, `settings.test-stages`,
`settings.guided-tour-toggle`, `settings.stud-tax.*`, `settings.pick-pricing.*`,
`settings.link-apple-btn`, `settings.notif-denied-banner`. New: `settings.hub.<group>` per hub row,
`settings.hub.identity`, and `settings.account.sign-out` (Sign out has no testID today). `settings.close-btn` is **deleted** with the modal
— grep the tree before removing it. `mobile/scripts/testid-lint.sh` gates this in CI.

---

## 9. Evidence plan (D-056)

D-056 retired Maestro and the simulator: no flows, no `screens/` captures. Note that
`docs/templates/feature-scope.md` § 3 still asks for a Maestro delta and a capture delta — that
section is stale under D-056 and is answered here with the replacement evidence instead.

**Structural checks** (`mobile/tests/check-*.js`, `npm run`-able, matching the 22 existing ones):

1. `check-settings-ia.js` — every row in the §4 migration map appears in exactly one page module;
   nothing is orphaned or duplicated. This is the check that catches a lost setting.
2. `check-settings-nav.js` — `Settings` and all second-level routes register **without**
   `presentation: 'modal'`; each has a `HeaderBack`; each page module mounts `FeedbackFAB`.
3. `check-settings-testids.js` — the full inventory in §8 still resolves; `settings.close-btn` is
   gone everywhere.

**Code-walk proof** (file:line-cited, written into the build doc): the destructive paths and the
stack operations — `confirmDeleteAccount`, sign-out `navigation.replace('SignIn')`, account-only
`navigation.replace('LeaguePicker')`, and the three `confirmDisconnect*` handlers — traced through
the new stack to show each still lands where it did as a modal.

**Operator TestFlight checklist** (the only runtime evidence mobile gets — specific enough to catch
a regression):

1. Gear → Settings **pushes from the right**, fills the screen to the top, back chevron top-left.
   Swipe-right dismisses; swipe-down does **not** (expected change).
2. Hub fits without scrolling; every row shows a preview line, or no line at all — never a wrong one.
3. Notifications page: flip Weekly digest off, back to hub, hub preview drops by one (e.g. "2 of 3 on" → "1 of 3 on").
4. Account → Verify account → SleeperConnect → back lands on **Account**, not on the tabs (F5).
5. Leagues page shows the ESPN/MFL disconnect rows; disconnect ESPN, confirm the row disappears and
   Send-in-ESPN is gated again.
6. Delete account still shows its confirm alert and is the last row on Account.
7. Sign out lives on **Account & data**, under the identity block and well clear of Delete account;
    it returns to SignIn with no stranded settings screen behind it.
8. FeedbackFAB is tappable on every settings page and files against the right `activeScreen`.
9. Deep link `.../settings/notifications` opens the Notifications page with a working back to the hub.
10. About shows the version matching the TestFlight build number.

**Pre-ship gate.** CI green (`pytest backend/tests`, `tsc --noEmit`, `testid-lint.sh`); the three
structural checks run and logged in `living-memory/TEST_LEDGER.md`; `FTF_SKIP_SIM_GATE=1` per the
standing D-056 posture, noting the evidence actually run.

---

## 10. Docs to update

| Doc | What |
|---|---|
| [`docs/design/components.md`](../../design/components.md) § Navigation | **New:** settings hub nav row (title + preview + chevron) spec; **amend** § Sheets/modals, which currently names Settings as the example modal-screen with a header close |
| [`docs/config-reference.md`](../../config-reference.md) | `account.settings_hub` added; `account.settings_v2` marked for retirement in Phase 4 |
| [`living-memory/LLD.md`](../../../living-memory/LLD.md) | settings route naming + the per-page query-ownership convention |
| [`mobile/src/navigation/CLAUDE.md`](../../../mobile/src/navigation/CLAUDE.md) | route list gains the settings sub-routes; Settings moves out of the modal list |
| [`mobile/src/screens/CLAUDE.md`](../../../mobile/src/screens/CLAUDE.md) | new `screens/settings/` subtree |
| [`living-memory/DECISIONS.md`](../../../living-memory/DECISIONS.md) | new D-: modal → push, and why #130's ✕ is removed rather than reverted |
| [`docs/api-reference.md`](../../api-reference.md) | **n/a** — no route added, renamed, or contract-changed |
| [`docs/architecture.md`](../../architecture.md) / [`living-memory/HLD.md`](../../../living-memory/HLD.md) | **n/a** — client-side IA only, no module wiring change |
| [`docs/glossary.md`](../../glossary.md) | **n/a** — no new domain term |

---

## 11. Risks and open questions

| # | Risk | Mitigation |
|---|---|---|
| R1 | A hub is more taps for users who knew where a setting was | Previews (§3) answer the common read without a drill-in; flag-gated with a one-round TestFlight comparison before graduating |
| R2 | Swipe-down-to-dismiss is a learned gesture on 1.13.2 | Explicit checklist item; back chevron is the discoverable replacement #130 was reaching for |
| R3 | A row is silently lost in the split (1,712 lines, conditional rendering everywhere) | `check-settings-ia.js` asserts the §4 map exactly; the map is the contract |
| R4 | Phase 0 touches the whole file and collides with concurrent sessions | Branch from a fresh `origin/main`; Phase 0 is mechanical and merges first |
| R5 | Hub previews go stale after an edit on a sub-page | Previews read from the same React Query cache / session store the sub-pages mutate; invalidation already exists per key |

**Operator decisions — resolved 2026-08-18. These bind the build.**

1. **Sign out lives on the Account page**, not the hub. Overrides the plan's original
   one-tap-from-gear recommendation; matches iOS convention and keeps the hub purely navigational.
   Placement within the page is specced in §3 (under identity, never adjacent to Delete account).
2. **Ranking and Trade values stay two pages**, grouped under one `HOW THE APP WORKS` hub banner.
3. **`account.settings_v2` is retired in Phase 4**, in the same wave — its legacy branch has been
   dead in prod since it shipped, and deleting it shrinks what the split has to carry.

No open questions remain. Anything new goes to `living-memory/OPEN_QUESTIONS.md`.

---

## 12. Non-goals

- No native inset-grouped list styling. ADR-008 already rejected that trade explicitly; this is
  Chalkline hairline rows throughout.
- No new settings. The only additions are the version row and the FeedbackFAB mounts.
- No changes to what any setting *does* — stud tax, pick pricing, rank-home routing, notification
  prefs, and every disconnect behave exactly as they do in 1.13.2.
- No web or extension work. Settings is a mobile surface; `web/` has no equivalent page.
- No collapse-by-default sections. The #243 audit is right that hiding settings a user came to find
  is a regression; grouping is not hiding when the hub previews state.
