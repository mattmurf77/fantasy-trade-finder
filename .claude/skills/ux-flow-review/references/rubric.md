# Rubric — where to look, what pins it, what went wrong before

> Companion to the rubric in [../SKILL.md](../SKILL.md). For each check: where the
> evidence lives in code, the `mobile/tests/check-*.js` guard that already pins it (CI runs
> every one, `.github/workflows/ci.yml:47`), and the feedback items that show the failure.
> Line numbers were verified on `origin/main` at `678834ab` (2026-10-15). They drift:
> re-open every one at the reviewed sha before citing it.

Paths below are relative to `mobile/src/` unless they start with `mobile/`, `docs/` or
`backend/`.

## 1. Entries and deep links

| Check | Where to look | Guards and precedents |
|---|---|---|
| E1 Discoverable entry | Callers: `git grep -n "navigate('<Route>'" -- mobile/src`. Tab roots and the Home hub (`components/home/HomeHub.tsx`, mounted by `screens/HomeScreen.tsx:31` under `nav.home_hub`) | #173: untouchables existed since FB-95 but nothing listed them, so a tester asked for the feature. #213: one quiet "Find a trade" link placed outside the calculator's mode branch, so every mode carries it |
| E2 Deep link | `utils/deepLinks.ts`: router v2 header :17-23 (unroutable path → `Main` + toast, intents buffered until the navigator is ready); `V2_SCREENS` :96-215; flag-gated routes stay addressable (:127-129, :179) | #246 kept `TradeDeck` registered so `app/trades/finder` still resolves after the landing changed |
| E2 Signed out, no league | `navigation/RootNav.tsx:452-457` picks `SignIn` / `LeaguePicker` / `Main`, keyed on the `no_league` sentinel. `LeagueJoin` sits on the root stack because invitees are usually signed out (`utils/deepLinks.ts:114-119`). `?ref=` and `?league=` are read in both router modes (`utils/deepLinks.ts:396-438`) | The 2026-08-09 audit (`docs/business/product/2026-08-09-mobile-ux-audit/00-master-report.md`) found invite links carrying an unread `?league=`; that has since been fixed (P0-3, unflagged) |
| E3 No orphan | Registrations in `navigation/RootNav.tsx` and `navigation/TabNav.tsx` against their callers | `Profile` (`navigation/RootNav.tsx:709`) still has no in-app caller at `678834ab`; it is reachable only through `u/:username` (`utils/deepLinks.ts:113`). The same audit's "public profiles with no entry point" |
| E4 Push and inbox taps | `resolveNotificationTarget` `utils/deepLinks.ts:329-342`; kind sets from :285 | `check-notif-glyphs.js` found two inbox kinds with a glyph and a dead tap (`utils/deepLinks.ts:288-295`) |
| E5 Three things together | `navigation/CLAUDE.md:23`, `navigation/README.md:43-51` | — |

## 2. Exits and back paths

| Check | Where to look | Guards and precedents |
|---|---|---|
| X1 Back or close | `HeaderBack` `navigation/RootNav.tsx:241-261`: the native back control is dead on iOS 26 over the `headerShown:false` Main tabs (#151), so pushes use an explicit JS control. `canGoBack()` fallback to `Main` for cold-start links (:277-299). Modal ✕ rule: `docs/design/components.md:77` | `check-settings-nav.js`. components.md:77 records that `FeedbackInbox` and `SleeperConnect` are modals without the ✕ — an open gap, not a precedent for new modals |
| X2 No loops | `rankSubScreenOptions` `navigation/TabNav.tsx:200-210` (no back, More-ways only); `screens/RankHomeScreen.tsx:119-133` (`navigate`, never `replace`); never-strand rule `navigation/CLAUDE.md:21-22` | `check-rank-nav-exit.js`. #162/#165: `replace` removed the chooser and back fell to a sibling surface. #217: two header controls for one destination at the stack root |
| X3 Landing after a terminal action | The screen's `navigate` / `popTo` / `goBack` after send, save or finish | #246: a deep-linked deck pushes over the landing; Back returns to the landing |
| X4 Push vs modal | `navigation/CLAUDE.md:20`: Settings became a push because a modal strands whatever is pushed on top of it | `check-settings-nav.js` |
| X5 Spent interstitial | `navigation/RootNav.tsx:608-615` (`LeagueJoin`, `headerShown:false`) | — |

## 3. States

Check per [state-standard.md](state-standard.md). Guards that already pin states:
`check-home-hub.js`, `check-usage-trends.js`, `check-presentation-v2.js`,
`check-win-now.js`, `check-win-now-recovery.js`, `check-swipe-failure-recovery.js`,
`check-feedback-capture.js`. Precedents: #159, #164, #189, #229, #420, #422 (each
summarised in the standard).

## 4. Interrupt budget

All in `state/useInterruptCoordinator.ts` unless noted. Flag `ux.prompt_arbiter` off
makes the slot a passthrough (:53-55).

| Check | Where to look | Guards and precedents |
|---|---|---|
| I1 One surface | Surface union and `SURFACE_PRIORITY` :57-71; `useInterruptSlot` :148-205; call order is the tiebreak (:145-146). Exemplar: `screens/TradesScreen.tsx:4215-4253` claims quickset prompt → coach mark → apple banner → outlook banner | `check-tour-suppression.js` executes the real store |
| I2 Root modals defer | `isInterruptBusy` :107-115; `components/PushPrimingModal.tsx:37-49`; `components/AppleSaveMomentSheet.tsx:40-44` | — |
| I3 Tour hold | Hold rules :33-55; refusal inside `claim` :96; `useMutedDuringTour` :117-135 for notices that never claim. One begin and one end site: `utils/calcTour.ts:512` and :216 (`utils/CLAUDE.md:37`: a leaked hold mutes every interstitial for the session) | `check-tour-suppression.js`, `check-calc-tour.js` |
| I4 Measured | `prompt_shown` and `prompt_deferred` with `blocked_by` :164-187; both classified non-intent in `backend/analytics_queries.py` (:232, :347) | Route new surface ids to `analytics-lead` |
| I5 First value | First run = `onboarding.trades_first` live and no swipe yet (`navigation/TabNav.tsx:728-739`; `state/useOnboardingState.ts:18`). The guide claims synchronously, ahead of screen effects (`state/useGuide.ts:474-478`) | `check-guide-script.js`, `check-guide-spotlight-tracking.js`; #397/#398 |
| I6 No preemption | :13-17 and `claim` :90-99. Coach marks are inline, never modal, never stacked; callers own the claim (`components/CoachMark.tsx:6-10`; the `coach_mark` claim is `screens/TradesScreen.tsx:4228-4234`) | — |

Cross-screen hand-offs that trigger a surface on arrival (for example a forced deck
regeneration after a rank walk) go through `state/onboardingBus.ts` (:1-8); check that the
arriving screen still claims a slot for anything it shows.

## 5. #188 FeedbackFAB

| Check | Where to look | Guards and precedents |
|---|---|---|
| F1 Root-stack push mounts one | Mount pattern `components/FeedbackFAB.tsx:60-66`; exemplars `screens/FreeAgentsScreen.tsx:222`, `screens/WinNowScreen.tsx:251` | `check-settings-nav.js` (each settings page), `check-usage-trends.js` (one FAB) |
| F2 Tab-stack mounts none | Global mount `navigation/RootNav.tsx:628-633`; tab-stack comments `navigation/TabNav.tsx:500-516`; the tab copy of `DraftRoom` suppresses its FAB with `inTabs` (`navigation/README.md:41`) | #196/#197 double FAB |
| F3 Pinned bottom bar | Reporter rules `components/FeedbackFAB.tsx:23-54` (focused only, 0 on blur, max not sum); exemplar `screens/TiersScreen.tsx:768-770` | — |
| F4 Exempt | `screens/TipJarScreen.tsx:36`, `screens/PaywallScreen.tsx:51` | — |

## 6. Seams

Read both sides, then trace each error the other side can raise to what this side shows.
Seam ownership between areas: decision P6 in `docs/plans/org-bringup/reports/head-product.md`.

| Seam | Sides | Errors that must surface here | Guards and precedents |
|---|---|---|---|
| Connect | Platforms × onboarding | `LeaguePicker` opens the ESPN or MFL sheet from a param (`navigation/RootNav.tsx:585-607`). `verification_required` → `ApiError.isVerificationRequired` (`api/client.ts:187-197`) → one central listener (:219-229, :637-646) → `VerifyAccountBanner` (`navigation/RootNav.tsx:624-626`). `espn_auth_required` → `isEspnAuthRequired` (`api/client.ts:198-209`) | `check-espn-nav-policy.js` (ESPN Connect WebView gate), `check-espn-wrong-account.js`, `check-landing-platform-options.js`; #130, #131 |
| Send to league | Trade card or calculator × platform write | `components/SendInSleeperButton.tsx`, `SendInEspnButton.tsx`, `SendInMflButton.tsx`: one button per platform, never a write to the wrong one | `check-send-button-platform.js`; #303 |
| Win Now and overhaul | League or trades × models | Unavailable reasons named in full (`backend/win_now_service.py:53` leads "Win Now can't model this league yet."); loading that ends | `check-win-now.js`, `check-win-now-recovery.js`, `check-team-overhaul.js`; #420, #422 |
| Share and invite | Growth × engagement | `handleDeepLink` `utils/deepLinks.ts:387-438`; `LeagueJoin` | `check-invite-social-proof.js`; the 2026-08-09 audit |

## 7. Placement and discoverability

| Check | Precedents |
|---|---|
| P1 Next to what it acts on | #251: "Recommended to even it" moved directly under the trade window. #303: Send moved above the verdict |
| P2 Reachable without scrolling | #243: the RankMenu sheet grew taller than the screen with no cap or scroll, so its top was unreachable (`docs/feedback/items/243-scroll-audit/rank-surfaces.md`). #379 (planned): an in-page minimised row replaces the top-row Filters button. #397/#398 (built): the tour bubble pinned to the top of the screen for the one step that covered the card |
| P3 Consistent with siblings | Compare the sibling screens' control and position; the control's own spec is `docs/design/components.md` (`design-lead`) |
| P4 Label and state cue | Verb labels; a check glyph, not colour alone, carries state (`mobile/tests/check-avoid-positions.js` header) — visual questions go to `design-lead` |
| P5 Traceable decision | #412: "More offers" moved because of a QA agent's compensating placement, not an operator ruling, and a tester reported it as a regression |
