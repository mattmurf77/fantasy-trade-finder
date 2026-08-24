# PRD — #386/#391: Analyst pop-up misplaced while the playoff odds section is expanded

**Date:** 2026-08-24 · **Group:** D (author) · **Path:** fast-track bug, full gates
**Screen:** `LeagueRankings` (League tab root) = `mobile/src/screens/LeagueSummaryScreen.tsx`
**Plan:** [plan.md](plan.md) (Planner investigation, every file:line claim re-verified 2026-08-24 by the author — two one-line citation drifts noted in §7, nothing material)

## 1. Repro

1. Sleeper league, ≥3 ranked members, guide beat **n5** armed (`analystScript.ts:345-353` — target `league-summary.pos-pills`, screen `LeagueRankings`).
2. On a prior visit, expand the "Season outlook" playoff projection (flag `outlook.odds`, on) and leave — expanded state persists per user/league (`mobile/src/state/outlookStrip.ts`).
3. Open the League tab. The outlook section mounts a tick after first paint (AsyncStorage hydration + `GET /api/league/outlook` resolution), pushing the chart card — and the position pills — down by several hundred pt.
4. The Analyst bubble appears: the spotlight ring, scrim cutout, and avatar+bubble band render at the pills' **pre-shift** position — a hole punched across the middle of the expanded playoff odds section (#386's "playoff odds section broken"). With the projection minimized the strip and loading shell are the same one-line height, so everything lands correctly (#391, the control case).

## 2. Root cause (verified)

The spotlight caches an absolute window frame: `measureGuideTarget` uses `measureInWindow` (`mobile/src/state/guideTargets.ts:19-40`) and the overlay re-measures only when a host announces movement (`subscribeGuideTargetsMoved` → `remeasure`, `mobile/src/components/AnalystGuide.tsx:165-209`) or on the two keyboard events. `LeagueSummaryScreen` announces from exactly one place — `onScroll={notifyGuideTargetsMoved}` on its page ScrollView (`LeagueSummaryScreen.tsx:1497`). **Nothing announces on a layout change**, and the outlook layer (`:1566-1572`, section mount/unmount in `OutlookStripAndSection`, `:2823-2871`) changes layout without a scroll via three triggers: AsyncStorage hydration, outlook-query resolution (`:2834-2841`), and the manual strip toggle (`:2849-2857` — the strip stays tappable mid-beat because the scrim wrapper is `pointerEvents="none"`, `AnalystGuide.tsx:395`).

The same defect class was fixed on the calculator in #384 (report 1): `TradeCalculatorScreen.tsx:675-676` wires `onLayout` and `onContentSizeChange` to `notifyGuideTargetsMoved` on its page ScrollView. `LeagueSummaryScreen` never received the same treatment.

## 3. Fix contract

- **R-1** — `LeagueSummaryScreen`'s page ScrollView (the one already carrying `onScroll={notifyGuideTargetsMoved}` at `:1491-1498`) additionally carries `onLayout={notifyGuideTargetsMoved}` and `onContentSizeChange={notifyGuideTargetsMoved}`, with a short comment citing #386, mirroring the `TradeCalculatorScreen.tsx:675-676` precedent. This covers all three triggers — each changes the ScrollView's content size or layout.
- **R-2** — **No-op when no tour is active.** The fix adds no conditional logic: `notifyGuideTargetsMoved` walks an empty listener `Set` when no overlay step is up (`guideTargets.ts:42-60`). The build must not wrap the calls in any guide-state read.
- **R-3** — **Mascot-agnostic.** No mascot-conditional code: the change is in measurement notification, upstream of the `AnalystAvatar` renderer switch (`onboarding.mascot_ram`). Identical behavior for The Analyst and the ram.
- **R-4** — **Shared analyst files untouched.** `AnalystGuide.tsx`, `state/useGuide.ts`, `state/guideTargets.ts`, `components/analyst/*` are not modified (Group B may own them this wave). Source diff is `LeagueSummaryScreen.tsx` only.
- **R-5** — **Existing announcements preserved.** `onScroll={notifyGuideTargetsMoved}` (`:1497`) and `scrollEventThrottle={16}` (`:1498`) remain; the calculator's props are untouched.
- **R-6** — **Structural guard extended.** `mobile/tests/check-guide-spotlight-tracking.js` rule 12 asserts the wired ScrollView in **both** hosts (`TradeCalculatorScreen.tsx` and `LeagueSummaryScreen.tsx`) carries both layout callbacks referencing the notifier — see §5a.

### R-n → mechanical pass criteria

| Req | Pass criterion |
|---|---|
| R-1 | Rule-12 assertions for `LeagueSummaryScreen.tsx` green (`npm run test:guide-spotlight-tracking`); code-walk §5b cites the landed lines |
| R-2 | Code-walk §5b traces the empty-set no-op; `git diff` shows no guide-state import/read added to the screen beyond the existing `notifyGuideTargetsMoved` import (`:51`) |
| R-3 | `git grep mascot_ram mobile/src/screens/LeagueSummaryScreen.tsx` → no hits in the diff |
| R-4 | `git diff --name-only` contains no `AnalystGuide.tsx`, `useGuide.ts`, `guideTargets.ts`, `components/analyst/` |
| R-5 | Existing rule-12 calculator assertions still green; `onScroll` assertion (12a-equivalent) green for both hosts |
| R-6 | Sabotage run (§5a) turns the suite red; restore turns it green |

## 4. Out of scope

- **`TradesScreen` latent class — explicitly OUT, flagged as follow-up.** It registers six guide targets (`TradesScreen.tsx:3243-3248`, plus `trades.package-toggle` at `:7173`) and its content also grows after first paint, but it announces on scroll only. Different repro, Group A/B surface this wave. Follow-up: add it to the rule-12 host list and wire the same two props in a later item.
- Any change to overlay internals — including resetting `scrolledForRef` so a large post-shift delta re-runs scroll-into-view (`AnalystGuide.tsx:122,223-249`). The B1 degrade posture (ring drops offscreen, bubble stays) is accepted; noted for Group B.
- Any change to the outlook section itself, its persistence, or its flags.

## 5. Test plan (D-056 — no Maestro, no simulator)

### (a) Structural guard extension

Extend rule 12 of `mobile/tests/check-guide-spotlight-tracking.js` (today `:1138-1170`, calculator-only) from a single hardcoded file to a **host list**: `['src/screens/TradeCalculatorScreen.tsx', 'src/screens/LeagueSummaryScreen.tsx']`. For each host, keep the existing two-stage posture:

1. Locate the ScrollView whose `onScroll` references `notifyGuideTargetsMoved`; **if none is found, `fail(...)` loudly** (the existing 12a posture) — never skip the host.
2. Assert `onLayout` and `onContentSizeChange` attributes exist and reference `notifyGuideTargetsMoved` (the existing 12b loop). Note the locator (`referencesIdentifier`) must accept both wiring shapes already in the tree: the calculator's arrow-body call (`:666-669`) and the league screen's bare identifier (`:1497`).

**Sabotage that must turn it red:** delete `onContentSizeChange={notifyGuideTargetsMoved}` (or `onLayout=…`) from `LeagueSummaryScreen.tsx`'s ScrollView → `npm run test:guide-spotlight-tracking` exits non-zero. Symmetric check: delete one from the calculator → still red (existing coverage preserved).

The current 12a/12b message strings hardcode "the calculator page" — the extension must parameterize the assertion messages per host, so a red run names the file that actually failed.

**Not self-satisfying:** two properties, both demonstrated in the build agent's ledger note. (i) The guard cannot pass by failing to find the host — step 1's `fail` branch fires when `onScroll` wiring is absent, so a host silently dropped from parsing cannot green the suite (prove it by additionally deleting the `onScroll` prop in the sabotage copy → still red, with the 12a message). (ii) The assertions run against the real files by relative path, not fixtures — the sabotage is performed on the working tree (then reverted), never on a copy the guard doesn't read.

### (b) Code-walk proof outline (build agent writes the full trace against the landed diff)

1. Beat n5 activates on `LeagueRankings` → engine measures `league-summary.pos-pills` once via `measureGuideTarget` (`guideTargets.ts:19-40`, absolute window coords); overlay reads the frame (`AnalystGuide.tsx:100-107,163`).
2. Outlook section mounts/toggles (`LeagueSummaryScreen.tsx:1566-1572`, `:2834-2841`, `:2849-2857`) → the page ScrollView's `onLayout`/`onContentSizeChange` fire → **new**: both call `notifyGuideTargetsMoved` (cite landed lines) — same seam as the existing `onScroll` at `:1497`.
3. Overlay's subscription re-measures, rAF-coalesced (`AnalystGuide.tsx:165-209`, coalescing `:171-191`) → fresh frame → cutout re-derived (`:342-355`) → band offset follows via `solveBandPlacement` (`:70-90`, side latched / offset live `:357-385`).
4. No-tour cost: `notifyGuideTargetsMoved` iterates an empty `Set` (`guideTargets.ts:51-60`) — no overlay mounted, no listener, no measurement. Mascot path: the fix sits upstream of `AnalystAvatar`; no branch reads `onboarding.mascot_ram`.

### (c) Operator TestFlight checklist

Precondition: Sleeper league with ≥3 ranked members; `outlook.odds` on (it is). Beat n5 must be armed — if already consumed/dismissed, re-arm via the Settings hub → **Help & about → "Guided tour"** toggle off→on (`settings/sections/GuideSection.tsx:51-63`; with `account.settings_hub` off, the flat-list copy at `SettingsScreen.tsx:915-933`). Under the live flags (`onboarding.guide_v2` on) the toggle calls `enableTour()` → `resetGuideProgressV2()` (`useGuide.ts:520-522`), which **never clears `guideReceipts`** (`useOnboardingState.ts:194-224`, FR-E10 by design) — and n5 retires permanently on one `league_filter_applied` receipt (`analystScript.ts:351`, recorded at `LeagueSummaryScreen.tsx:1009-1014`).

**Feasibility check first:** after the toggle cycle, make a qualifying cold visit to the League tab. If the bubble does not appear, the beat is receipt-retired on this install — the operator has applied a position filter at some point — and no toggle cycle can re-arm it. **Fallback:** sign in as a different/fresh Sleeper user (onboarding state is per-user). `testing.stage_users` is currently **false**, so the TestStages synthetic-user reset is not available without a deliberate flag flip. If neither path is workable, steps 1–5 degrade to the code-walk proof (§5b) and this must be recorded as such in TEST_LEDGER — do not run the steps against an unarmed beat and report them passed.

There is no "Show me around" link on this screen (that re-entry is calculator-only) — n5 fires on visiting the League tab with the beat armed and content gates passing.

1. Open the League tab; tap the "Season outlook" strip to **expand** the playoff projection. **Force-quit the app and relaunch**, then navigate to the League tab (a tab switch does NOT remount the screen — `TabNav` sets no `unmountOnBlur`, and n5 re-requests on every focus against settled layout, so only a cold start reproduces the mount race: rankings resolve first from the persisted query cache, then the expanded outlook section lands after the bubble measures).
2. Wait for the Analyst bubble ("Filter one position…"). **Expected:** the ice ring + scrim cutout sit exactly on the position-filter pills; the avatar+bubble band is adjacent to the ring; the expanded playoff odds section looks normal — dimmed by scrim only, **no hole punched through it**.
3. While the bubble is up, tap the "Season outlook" strip to **collapse**. **Expected:** the pills shift up and the ring + band follow them immediately.
4. Tap the strip to **re-expand** while the tour is still open. **Expected:** ring + band follow the pills back down; if the pills land below the fold, acceptable degrade is ring offscreen with the bubble staying (B1) — never a ring parked mid-section.
5. Re-arm the beat (toggle off→on), **minimize** the projection, then force-quit and relaunch to the League tab (same cold-start shape as step 1, for symmetry). **Expected:** ring + band on the pills, exactly as today (#391 control case — no regression).
6. With the bubble up, scroll the page. **Expected:** ring tracks the pills (existing behavior, must not regress).
7. If the tester device has the ram mascot experiment (`onboarding.mascot_ram`): repeat steps 1–4 once — identical expectations.

## 6. File ownership / coordination

| File | Change | Owner |
|---|---|---|
| `mobile/src/screens/LeagueSummaryScreen.tsx` | +2 props + comment on the ScrollView at `:1491` | Group D |
| `mobile/tests/check-guide-spotlight-tracking.js` | Rule-12 host-list extension | Group D — **shared-file coordination point with Group B**: if Group B also edits this guard, merge order matters; the extension is additive and small, rebase-trivial |

## 7. Planner-claim verification notes

All plan.md file:line claims re-verified against the tree at `ff153a0`. Two one-line drifts, neither material: n5 is `analystScript.ts:345-353` (plan: 346-354); the calculator precedent's props are exactly `:675-676` with the scroll lambda at `:666-669` (plan's "670-676" spans the comment block). Flags confirmed live: `outlook.odds`, `onboarding.v2`, `onboarding.guided_avatar`, `onboarding.guide_v2` all true; `onboarding.mascot_ram` false (experiment-targeted).
