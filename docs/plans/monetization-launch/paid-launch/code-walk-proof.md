# Code-walk proof — paid launch (enforcement ON)

**Date:** 2026-11-21
**Scope block:** [scope.md](scope.md)
**Branch:** `feat/paid-launch`. Line numbers are as of this branch's head. They are citations, not contracts, so re-derive them with `git grep -n` if the files move. Mobile paths are relative to `mobile/src/`.

**Why this exists:** D-056 retired the simulator. This document is the written, file:line-cited trace that
stands in for runtime captures. It walks every mobile entry point that leads to a gated route. It assumes
the server **enforces** (`entitlements.is_enforcing()` true) and that the client has `monetize.paywall` on (prod
already does, G-076).

**Verified by running vs inferred by reading:**

- **Verified by running:** the backend paywall suites (658 passed), the allowlist test, `tsc`, testid-lint, all 196 `check-*.js` and the sabotages.
- **Inferred by reading:** every runtime UI sequence below, such as an Alert stacking on a modal or what is on screen after a dismiss. Nothing here ran on a device.

- [1. Readiness verdict](#1-readiness-verdict)
- [2. The six user states, server-side](#2-the-six-user-states-server-side)
- [3. Entry points](#3-entry-points)
- [4. After the paywall closes](#4-after-the-paywall-closes)
- [5. Before the tap](#5-before-the-tap)
- [6. Requirement (a): no Pro content without the server](#6-requirement-a-no-pro-content-without-the-server)

## 1. Readiness verdict

**Launchable as paid once enforcement is on: yes,** with one condition. The mobile binary that is live when
the knob goes to 1 must contain this branch, or the user-visible roughness in §3 rows S1–S3, Q1 and Sh1 ships with it.

- **Server.** Every Pro feature is enforced server-side (`backend/paywall_gate.py:82-118`, 32 gated rules). The allowlist test fails CI on any unclassified Flask rule (`backend/tests/test_paywall_gate_allowlist.py:23`) and pins the gated set exactly (`:50`).
- **Client.** The router opens the paywall, or the VerifySheet, on every user-initiated gated call (`api/client.ts:392-416`, `state/usePaywallGate.ts:252-274`).
- **What was missing:**
  - Clean fail states on the launch surfaces. The Send buttons and the calculator queue showed a failure alert or toast on top of the paywall; Shop and the ideas panel showed a generic error or a false empty state behind it. This branch closes those.
  - Store and provider evidence, which is not code (runbook §A, §C).
- **Not done:**
  - A visible lock before the tap: not built, and why is in §5.
  - Auto-resume after a purchase for first searches and sends: not built, see §4.
  - Several cut-candidate surfaces fail safe but read poorly (Overhaul, Today's Trade, Win Now's blank line, the standing-offer sheet). See the "fails safe" rows.

## 2. The six user states, server-side

The routing is the same for every entry point. The server decides, and the client maps the answer the same
way everywhere. All of these assume a mobile `X-Device` (`paywall_gate.py:498`).

| State | Deck routes (`DECK_ROUTES`, `:74`) | Every other gated route | Client opens |
|---|---|---|---|
| **Never-entitled, verified** | first page of the first deck free (`_preview`, `:548-576`), then 402 `preview_used` | 402 `never_trialed` (`:509`, `_reason` `:531`) | Paywall `source:gate` (`usePaywallGate.ts:268-270`) |
| **Trialing** (an active `pro` row from the intro offer) | through (`:504`) | through | nothing |
| **Paid** | through | through | nothing |
| **Lapsed** (held `pro` before, not now) | 402 `trial_expired` if every ledger event was TRIAL, else `lapsed` (`_held_pro` `:652-674`) | same | Paywall |
| **Unverified (non-demo)** | if the route wears the verified gate: through to the route's own 403 `verification_required`, else 402 `verify_required`. No entitlement or preview read (`:500-503`; R28.14) | same | VerifySheet (`client.ts:365-372`; `openPaywall` → `openVerify`, `usePaywallGate.ts:148`) |
| **Demo** (server demo session) | through, exempt (`:496`) | treated as unverified | VerifySheet, Apple "new sign-in" variant (`isUnverifiedSession` counts demo, `usePaywallGate.ts:86-89`; `verifyPathFor` `:73-80`) |

- **Status-blind.** Routing reads only the signal, `session_verified` and `isDemo` (`usePaywallGate.ts:27-31`), so an unverified session's answer cannot reveal subscriber status.
- **Client pre-checks.** The Send pre-check and Win Now's `findLocked` read `useEntitlements.enforcing` and `pro`. They are skipped until `enforcing` is known (`state/useEntitlements.ts:85` defaults false, not persisted), and then the server's 402 is the backstop.

## 3. Entry points

Each row gives the surface, what the user sees before the tap, what the tap does, whether the prompt
opens, whether it names the action, and what is left on screen. "Names the action" means the paywall
headline (`copy/monetization.ts:245-251`): `kind:'send'` → "Sending trades needs a subscription.",
`kind:'find'` → "Finding trades needs a subscription.", and `preview_end` → "There's a full deck behind this
page." Every variant lists what Pro includes (`mon.pay.value` and `b1`–`b4`, `screens/PaywallScreen.tsx:695-705`)
and what stays free (`mon.lock.free`, `:707`).

### Launch surfaces

| # | Entry point | Before tap | On tap (non-subscriber) | Prompt? Names it? | Left on screen after dismiss |
|---|---|---|---|---|---|
| D1 | **Acquire tab, Find a trade** (`screens/TradesScreen.tsx:1530`) → `generateTrades`, user-initiated (`:2399-2401`) | the normal button | never-entitled: the first page is served (the preview). Otherwise 402 | Paywall, `find`. Named. | `onError` checks `isProRequired` first (`:2487`), no toast; a pushed deck pops to the landing (`:2508`); classic host: the idle "Find a Trade" card |
| D2 | **Swipe past the free page**: next-page prefetch, background (`api/trades.ts:513`) | cards | 402 on the next page → `noteDeckGateEnd` (`TradesScreen.tsx:5617`) | No auto-open (background, D2). The **preview end card** (`components/TradeDeckStates.tsx:166-191`: "That's the first page." + `mon.lock.find` + See plans / Continue) | the end card stays; See plans → `openPaywall({source:'preview_end'})` (`TradesScreen.tsx:5640-5647`) |
| D3 | **Like/Pass a card** (`TradesScreen.tsx:2945`ff) → `/api/trades/swipe` | cards | inside the preview window: allowed (`paywall_gate.py:571-573`); outside it: 402 | Paywall, `find` | the card rewinds; no "Swipe didn't save" toast (`TradesScreen.tsx:3073`) |
| D4 | **Pass-reason sheet** → `/api/trades/pass-reason` (`api/declineReasons.ts:105`) | sheet | 402 only outside the window | Paywall | errors swallowed (`declineReasons.ts:122-126`), no error UI |
| C1 | **Calculator, Find a trade** (`screens/TradeCalculatorScreen.tsx:816-856` → hand-off → `TradesScreen.tsx:3771-3843`); with a give side → `/fair-packages` (`:4062`), else `/generate` (`:4093`); user-initiated on arrival | the normal button | fair sweep: 402 for every non-subscriber (not a deck route, so no preview). Model: as D1 | Paywall, `find`. Named. | the fair catch checks `isProRequired` first (`:4565`), `fairPending` clears (`finally`), and a pushed empty deck pops |
| C2 | **Calculator ✓ "Queue this trade for the other manager"** → `/api/trades/queue` (`utils/queueCalcTrade.ts`) | the ✓ cell | 402 | Paywall, `send`. Named. | **was:** the error toast "Couldn't queue that. Try again." **now:** no toast (`queueCalcTrade.ts:86`, `if (gated)`); the cell unlocks in `.finally` |
| S1 | **Send in Sleeper** on the deck card (`TradesScreen.tsx:10341`), the calculator (`components/InLeagueCalculator.tsx:1532`), Shop (`components/ShopOffersBody.tsx:1047`) and Matches (`components/TradeCard.tsx:1220`, `:1242`) | the normal button | **pre-check first** (`SendInSleeperButton.tsx:486-488` → `sendPreCheck` `:72-88`): verified and not pro → Paywall before the confirm; unverified/demo → VerifySheet, then re-check and resume to the confirm | Paywall, `send`. Named. | the button is idle. If the pre-check was skipped (entitlements not loaded yet), the server's 402 → paywall. **was:** "Couldn't send. Something went wrong sending to Sleeper." on top; **now:** nothing more (`:308`) |
| S2 | **Send in MFL** (rendered by the router, `SendInSleeperButton.tsx:493-507`) | the button | pre-check (`SendInMflButton.tsx:340`) | Paywall, `send` | **was:** "Couldn't send" on top; **now:** silent gate branch (`:166`), second after outcome-unknown (pinned first by `check-send-timeout` D) |
| S3 | **Send in ESPN** (cut candidate, polished anyway: same component family) | the button | pre-check (`SendInEspnButton.tsx:377`) | Paywall, `send` | same fix (`:205`) |
| Sh1 | **Shop a player / More offers** (`screens/ShopAssetScreen.tsx` → `ShopOffersBody`, `ideasQuery` user-initiated, `:391-418`) | the More offers tap | 402 on mount | Paywall, `find`. Named. | **was:** "Couldn't sweep the league" + Try again (a loop back into the paywall), and a second paywall from the `retry: 1` retry. **now:** `PaywallGateNotice` (`mon.lock.find` + See plans / Continue, `ShopOffersBody.tsx:868-878`); no retry on a 402 (`state/queryClient.ts:27`) |
| P1 | **Single-pin ideas panel** (one pin from League rankings Offer/Target, Usage Trends Trade, or a manual pin), `assetIdeasQuery` (`TradesScreen.tsx:2122-2141`) | pinning | 402 | Paywall, `find` (the query is user-initiated) | **was:** the false empty "No defensible packages found…". **now:** the notice (`components/AssetIdeasPanel.tsx`, `gated && !groups`; host `TradesScreen.tsx:8119`) |
| H1 | **League rankings Offer/Target** (`screens/LeagueSummaryScreen.tsx:1436-1446`), **Usage Trends Trade** (`screens/UsageTrendsScreen.tsx:397-404`), **Team Review "Find my trades"** (`screens/TeamReviewScreen.tsx:406-410`): `autoRun` hand-offs | the row/tile tap | arrival runs `dispatchGenerate({})`, user-initiated (`TradesScreen.tsx:3933-3948`): as D1. A single pin also fires P1 | Paywall, `find`. Named. | as D1 / P1 |
| M1 | **Matches** (`screens/MatchesScreen.tsx`) | the list is free and viewable (`GET /api/trades/matches/all`, `paywall_gate.py:361`); Dismiss is free (`:360`) | the only action that reaches a gated route is **Send** (S1–S3). There is no mobile accept/disposition caller (`api/trades.ts:929-932`) | Paywall, `send` | as S1 |
| HM | **Home tiles** (`components/home/HomeHub.tsx:181,189,491`) | tiles | navigate to Trades only, with no gated call | — | — |

### Surfaces that fail safe (cut candidates; not polished)

| # | Entry point | What a non-subscriber gets | Roughness left |
|---|---|---|---|
| W1 | **Win Now** (`trades.win_now` **on**): `screens/WinNowScreen.tsx:169` | `findLocked` (`:157-166`) opens the Paywall (`find`) before the search; a 402 maps to a blank line (`actionErrorCopy` `:59-61`) | After a dismiss, no on-screen line says why. Entries at `TradesScreen.tsx:8285` and `LeagueSummaryScreen.tsx:1849` |
| O1 | **Team Overhaul** (`overhaul.enabled` **off**): only entry `components/OverhaulEntryCard.tsx` via `TradesScreen.tsx:8297` | unreachable at launch. If turned on: every call is user-initiated, so the Paywall opens | the screens render raw "(pro_required)" or a bare "Try again" (e.g. `OverhaulOutlookScreen.tsx:160`, `OverhaulSummaryScreen.tsx:206`). **Polish before enabling.** |
| SO1 | **Standing offer** (`components/StandingOfferSheet.tsx`) | background post (`:252`); on a gate answer the sheet hides, then Paywall/Verify opens after the Modal is gone (`:268-273`) | the sheet's choices are lost |
| T1 | **Today's Trade / Browse All** (`trades.presentation_v2` **off**): `hooks/usePresentationDeck.ts:83-85` | dark | if enabled: the raw "pro_required" text, and the background mount opens nothing. **Fix before enabling.** |
| CR1 | **Canvas-results landing** (`calc.canvas_results` **off**) | dark | if enabled: the 402 branches never clear `browseSession`, so "Looking for trades…" spins forever (`TradesScreen.tsx:9802-9833`). **Fix before enabling.** |
| R1 | **Automatic re-search** after `inputs_changed`, background (`:2396`, `:2498-2504`) | the 402 ends the deck. With an emptied deck the end card can't render (`pagedWithCards`, `:4919`), so a pushed deck pops silently | rare, because it needs a mid-deck input change after the preview is spent. The next tap gets the paywall |
| A1 | **First-run auto-start**, background (`:2916-2935`) | a never-entitled user gets the preview page (the server serves it on `/generate` whatever the client flag). A lapsed user gets 402 → the idle "Find a Trade" card | no cue until the tap, and the tap opens the Paywall |
| HP1 | **Held pass flush** (`ux.swipe_undo`), about 5 s after the swipe (`:7243-7260`) | only outside the preview window | the paywall can open after the user has moved on |

**Client mirror check:** `_isGatedPath` (`api/client.ts:346-352`) matches every server `GATED` rule and no free one (`standing-offer/revoke`, `matches/<id>/dismiss`, `liked` and `validate` are excluded by the `$` anchor). It only decides whether a 403 opens the sheet; a 402 is classified whatever the path (`:365`).

## 4. After the paywall closes

- **Dismiss ("Not now" / ✕).** `PaywallScreen.tsx:193-196` goes back to the screen the user was on. Nothing re-opens on its own (D4; one paywall at a time, `usePaywallGate.ts:152`; no retry of a 402 query, `queryClient.ts:27`). The deck keeps the preview end card. Shop and the panel keep the notice with See plans. Send buttons are idle.
- **Purchase.**
  - `onPurchase` notes CustomerInfo optimistically, awaits `refreshEntitlements()`, then dismisses, or shows the Founding GMs welcome inside the club window (`PaywallScreen.tsx:390-404`).
  - **The deck's page path resumes by itself:** `useEffect([payEntitled]) → resumeDeckPages()` (`TradesScreen.tsx:5636-5638`) re-kicks the next page, the revalidation or the re-search.
  - **Everything else needs a fresh tap:** a first Find a trade, a calculator hand-off (consumed once, `:3773`), and Send. **Shop and the ideas panel do resume:** each refetches its sweep when `pro` turns true while its notice shows (`ShopOffersBody.tsx`, the `entitled` effect; `TradesScreen.tsx`, the `payEntitled && assetIdeasQuery.isError` effect; `check-paid-launch` 7a).
  - **Sends are never re-sent, by design (D18).** The user taps Send, sees the confirm and sends.
  - No UI line says "tap again". This is waiver W4: it needs a ux/copy call, and an auto-resume of a search would land a deck on a user who may have moved on.
- **Restore.** As purchase, but the paywall closes after "Welcome back…" (`:446-448`). The same resume rules apply.
- **Verify** (unverified sessions). A non-send call is re-sent once and the server decides (`client.ts:407-416`). The Send pre-check resumes to the confirm (`SendInSleeperButton.tsx:77-80`). The deck end card resumes the pages (`TradesScreen.tsx:5642`). The new notice's Continue passes `onVerified` → refetch (`ShopOffersBody.tsx:876`).

## 5. Before the tap

There is no lock or "Pro" mark on any entry point today, and this branch adds none (scope W3). What a user does get:

- the paywall at the moment of a gated action, naming the action;
- the Send pre-check opening it before any confirm;
- the deck's end card;
- the new in-place notice on Shop and the ideas panel.

`SubscriptionSection.tsx:45`'s "`enforcing` gates the LOCK UI only" refers to these gate surfaces. No lock UI was ever built. Building one needs:

1. a glyph (none in `components/chalkline/Icon.tsx`);
2. approved copy;
3. legal's read against R28.8 #5;
4. a rule for Find a trade, which is free for one page.

## 6. Requirement (a): no Pro content without the server

- **Server.** Every Pro feature's routes are `GATED`, and new routes cannot slip through (the allowlist test). The deck preview is the only free Pro content, and it is capped server-side (`paywall_gate.py:548-576`, served and recorded by `/generate` and `/status`).
- **Device-held first page** (`state/devicePageStore.ts`). The background refresh can't claim the preview (the server answers 409 `prewarm_requires_tap`, which discards, `:326`). A 402 keeps any held page (`:322-329`).
  - The render path refuses held cards when `payEnforcing && !payEntitled` (`TradesScreen.tsx:4078`).
  - **Residual window:** `enforcing` isn't persisted, so on a cold start before `/api/me/entitlements` answers, a page held at most `DEVICE_PAGE_MAX_AGE_S` = 300 s (`utils/devicePage.ts:20`) can render. That page was validated while the user was entitled. Its first action is still gated server-side, and its revalidation (user-initiated, `TradesScreen.tsx:5227`) opens the paywall.
  - Accepted: at most one 5-minute-old page, for a user who lapsed within those 5 minutes.
- **The 72 h offline grace** (`useEntitlements.ts:42`) affects only client UI pre-checks. The server still answers 402.
- **The persisted query cache** holds no deck data (`App.tsx:76`: rankings, progress, matches, tiers-status, liked-trades). `liked-trades` and `matches` are free reads.
- **Background calls whose 402 opens nothing:**
  - D2 shows the end card.
  - A1, R1 and HP1 are covered above.
  - Device prewarm leaves nothing visible.
  - Shop's background dismiss swipe (`ShopOffersBody.tsx:575-582`) refetches, which opens the gate through the user-initiated sweep and now shows the notice.
  - No launch surface is left blank because its only call is background.
