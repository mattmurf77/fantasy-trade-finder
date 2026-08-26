# Reconciliation log — #386/#391 (Group D)

> Dual-agent record: Round 1 = planner investigation → author deltas; Round 2 = critic pass over prd.md / scope.md / status.md. Verdict at the end of each round.

## Round 1 (2026-08-24) — plan → PRD

- Planner's root cause, fix choice (2 ScrollView props, calculator precedent), file ownership, and guard-extension approach adopted unchanged into prd.md R-1…R-6.
- Author corrected two plan citations: n5 is `analystScript.ts:345-353` (plan said 346-354); calculator precedent props are exactly `:675-676` with the scroll lambda at `:666-669`. **Critic re-verified both against the tree in Round 2 — both corrections are right** (O-5).

## Round 2 (2026-08-24) — critic objections

### O-1 — BLOCKING: TestFlight checklist step 1 cannot reproduce the defect (self-satisfying step)

PRD §5c step 1 says: expand the projection, "leave the tab (state persists), then return so the expanded section mounts after first paint." That premise is false:

- Bottom-tab screens stay mounted on blur — `TabNav.tsx` sets no `unmountOnBlur` / `freezeOnBlur` / `detachInactiveScreens` (grep over the file: zero hits). Returning to the League tab does **not** remount `LeagueSummaryScreen`, so the outlook section is already laid out when the tester returns.
- n5 is re-requested on **every qualifying focus** (`LeagueSummaryScreen.tsx:995-1003`, `useFocusEffect` → `requestGuideStep(GUIDE.n5())`), so the re-focus activation measures the pills against **settled** layout — correct placement even with the bug present.
- The strip's expanded-state hydration runs once per mount keyed on `userId` (`outlookStrip.ts:36-64`), and the outlook query data is already cached on re-focus — neither shifts layout on return.

Consequence: pre-fix, step 2's expected result **passes** — the step can never catch a recurrence of the reported failure (the mount race is the operator's actual repro; steps 3-4's mid-beat toggle covers only the toggle trigger). **Required change:** step 1 must be a cold start — expand the projection, **force-quit the app, relaunch**, navigate to the League tab, and let the outlook section land after the bubble measures (rankings resolve first from the persisted query cache, so the race is real on first tab focus). Step 5's control case should use the same cold-start shape for symmetry (it passes either way, so that half is non-blocking).

### O-2 — BLOCKING: the re-arm path may be unable to arm n5 at all

PRD §5c precondition: "re-arm via Settings → About → The Analyst toggle (calls `enableTour()`/`resetGuideProgress()`)." Two defects:

1. **Wrong function under the live flags.** `onboarding.guide_v2` is on, so `enableTour()` calls `resetGuideProgressV2()`, not `resetGuideProgress()` (`useGuide.ts:520-522`). The difference is load-bearing: V2 keeps `guideSeen` + display counts for steps in `guideRetired`, and **never clears `guideReceipts`** — "a step whose retirement receipt already fired … is therefore still refused by `requestStep` on replay" (`useOnboardingState.ts:194-224`, FR-E10 by design).
2. **n5 retires permanently on one `league_filter_applied` receipt** (`analystScript.ts:351`; recorded at `LeagueSummaryScreen.tsx:1009-1014`). If the operator has ever applied a single-position filter on this screen — likely, given heavy testing of this surface — **no toggle cycle can ever re-arm n5 on that install**, and the whole checklist is unrunnable as written.

**Required change:** the precondition must (a) name `resetGuideProgressV2` semantics honestly, (b) add a feasibility check ("if the bubble does not appear on a qualifying cold visit, the beat is receipt-retired on this install"), and (c) give a working fallback — sign in as a different/fresh Sleeper user (per-user onboarding state), noting that `testing.stage_users` is currently **false**, so the TestStages synthetic-user reset is not available without a deliberate flag flip.

### O-3 — NON-BLOCKING: toggle location/label imprecision

`account.settings_hub` is **true**, so the live surface is Settings hub → "Help & about" (`SettingsAboutScreen`) → the **"Guided tour"** toggle (`settings/sections/GuideSection.tsx:51-63`); the flag-off flat-list copy is `SettingsScreen.tsx:915-933`. The PRD's "The Analyst toggle" is not the on-screen label. Name the label and, ideally, both flag paths.

### O-4 — NON-BLOCKING: rule-12 sabotage argument verified — holds, one cosmetic nit

- Structure confirmed: rule 12 today is `if (!scroller) { fail('12a …') } else { assert onLayout + onContentSizeChange }` (`check-guide-spotlight-tracking.js:1149-1169`) — the host-list extension keeps the loud-fail branch, so a host silently dropped from parsing cannot green the suite. Deleting `onScroll` also trips rules 9b/10c independently — still red either way.
- `referencesIdentifier` (`:189-191`) matches any identifier text under the initializer, so it already accepts **both** wiring shapes — the calculator's arrow body (`:666-669`) and the league screen's bare `onScroll={notifyGuideTargetsMoved}` (`:1497`); rule 9 passes on the latter today, which proves it. §5a's locator caution is satisfied with no locator change.
- The sabotage **is** provable on the LeagueSummaryScreen host (not just the calculator it copies), provided the extension asserts per host — which PRD §3 R-6 / §5a pins.
- Nit: the current 12a/12b message strings say "the calculator page" — the extension must parameterize the messages per host. Cosmetic.

### O-5 — NON-BLOCKING: author corrections and scope claims verified

- n5 = `analystScript.ts:345-353` ✓ (id/target at `:346-347`, `retireAfter` at `:351`). Calculator props `:675-676`, lambda `:666-669` ✓.
- scope.md analytics claim accurate: `guide_step_shown` registered at `backend/analytics_taxonomy.py:78` with props `{step, pose, screen, spotlight}` at `:895-896`; no re-measure/targets-moved event exists in the taxonomy ✓ — no new emitter warranted.
- scope.md §5's claim that CI runs the check suites is **true**: `.github/workflows/ci.yml:42-47` runs `for f in tests/check-*.js; do node "$f" || exit 1; done` under mobile-typecheck. Aside (not this item's docs): root `CLAUDE.md`'s "the `mobile/tests/check-*.js` structural suites … gate nothing yet" line is stale.
- `league.pos_candidates` is true — n5's content gate can pass in prod.

### O-6 — NON-BLOCKING: contract and invariants clean

R-1…R-6 admit no divergent implementations the pass-criteria table wouldn't catch; R-2 pins the no-op-without-tour posture and forbids wrapping the calls in guide-state reads. `docs/cross-client-invariants.md` surfaces untouched (no band threshold, color, or enum moves; no worked example to recompute). No provisional orchestrator arbitrations appear in the PRD.

## Round 2 verdict

**NOT-READY** — two blocking objections, both confined to PRD §5c (the TestFlight checklist, the only runtime evidence this fix gets): O-1 (step 1 cannot reproduce the defect; needs cold-start repro) and O-2 (re-arm precondition may be impossible on a receipt-retired install; needs feasibility check + fresh-account fallback and the correct `resetGuideProgressV2` citation). The fix contract, guard extension, scope block, and analytics posture are sound as written.

## Round 3 (2026-08-24) — resolutions (applied by the orchestrator; the Author agent was repeatedly killed by a server-side 529 outage after Round 2, with no Round-3 edits landed)

- **O-1 (BLOCKING) — RESOLVED.** §5c step 1 rewritten as a cold start: expand → force-quit → relaunch → League tab, with the why (tab switches never remount; n5 re-requests on every focus against settled layout; the mount race needs rankings-from-cache first, outlook landing after the bubble measures). Step 5 given the same cold-start shape for symmetry.
- **O-2 (BLOCKING) — RESOLVED.** Precondition rewritten: names `resetGuideProgressV2` semantics honestly (receipts never cleared, FR-E10), documents n5's permanent retirement on one `league_filter_applied` receipt, adds the feasibility check (no bubble on a qualifying cold visit ⇒ receipt-retired install), and the fallback (fresh/different Sleeper user; `testing.stage_users` false so TestStages unavailable without a flag flip). If neither path works, steps 1–5 degrade to the §5b code-walk proof and TEST_LEDGER must record that — no pass-by-vacuity.
- **O-3 (NON-BLOCKING) — RESOLVED.** Toggle path corrected to Settings hub → Help & about → "Guided tour" (`GuideSection.tsx:51-63`), flat-list copy cited for the flag-off path.
- **O-4 (NON-BLOCKING) — ALREADY IN PRD.** §5a already requires per-host parameterization of the 12a/12b message strings (prd.md §5a, "message strings" paragraph); no further change.

**O-2 feasibility answer:** there IS a workable operator path (fresh Sleeper account) even on a receipt-retired install; on the operator's primary account feasibility is unknowable from code — hence the checklist's explicit feasibility probe and the recorded-degrade rule.

## Round 3 verdict

READY — both blocking objections resolved in place; fix contract, guard plan, scope block untouched (per the critic's own finding that they were sound).
