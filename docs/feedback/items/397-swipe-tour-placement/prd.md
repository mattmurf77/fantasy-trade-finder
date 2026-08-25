# FB-397/#398 — Mini-PRD: pin the swipe-coaching beat's bubble to the top of the screen

**Date:** 2026-08-24 · **Author:** Group B author agent · fast-track bug path (mobile-only)
**Plan:** [plan.md](plan.md) (all file:line claims re-verified 2026-08-24; one drift — see §6 note on guard case IDs)

## 1. Repro (operator, v1.16.3 build 129)

1. Reach the beat on a **first-run state** — a fresh install, or Settings → Testing → Test stages → **Factory reset** (`TestStagesScreen.tsx:186–189` → `replaceOnboardingState({})`, which clears `firstSwipeDone`). The Guided-tour toggle alone does NOT re-arm s2.x: `resetGuideProgress`/`V2` never clear `firstSwipeDone` (`useOnboardingState.ts:180–192, 209–229`), and both s2.1 and s2.2 are gated on first-run state (`TradesScreen.tsx:3293, :3316`). (Live toggle mount: `settings/sections/GuideSection.tsx:54` inside Settings → About; `SettingsScreen.tsx:924` is the flag-off flat list.)
2. Acquire tab with a deck present; s2.1 shows and is tap-advanced.
3. Beat **s2.2** ("Swipe right to take it, left to pass. Every swipe teaches me.", `analystScript.ts:123–127`, target `trades.card-body`) appears with its ring around the whole deck card — and the Fleeced bubble lands either **mid-screen squeezed above the card** or in the **bottom band at `bottom: 92`, covering the card's Pass/Like disposition row**, depending on device height and Dynamic Type. #397 asked for bottom; **#398 supersedes: top of the screen, above the trade chip strip.**

## 2. Root cause

Placement is the pure adjacency solver `solveBandPlacement(cutout, bandH, winH, insets)` (`AnalystGuide.tsx:70–90`): above the ring if the band clears `insets.top + BAND_EDGE`, else below, else the legacy bottom band (`BAND_BOTTOM = 92`, line 44). s2.2's ring is the **entire deck card** (~500–600 pt on an 844 pt window): "below" never fits, "above" is marginal, so the answer band-flips per device between mid-screen and the bottom-band fallback over Pass/Like. Guard case **11f** (`mobile/tests/check-guide-spotlight-tracking.js:1046–1052`) pins tall-ring → bottom-band as correct *generic* behavior, so the fix must be a **per-step opt-in**, not a solver-default change.

## 3. Requirements

- **R-1 — Step contract.** `GuideStep` (interface at `useGuide.ts:81`) gains one optional field `band?: 'top'` — "pin the avatar band to the top of the window instead of adjacency placement (#397/#398)". Inert wherever absent; no other values.
- **R-2 — Solver pin.** `solveBandPlacement` gains an optional 5th parameter `pin?: 'top'`. With `pin === 'top'` it returns `{ from: 'top', offset: insets.top + BAND_EDGE }` **before any other branch** — including the null-cutout / unmeasured-band early return, so a degraded or not-yet-measured s2.2 still honors the ask.
- **R-3 — 4-arg path behaviorally unchanged, pinned by 11d–11j.** With `pin` undefined the solver's behavior is sampled-behavior-equivalent to today's: guard cases 11d–11h and the 11i/11j invariant sweep (`check-guide-spotlight-tracking.js:1022–1095`) execute the 4-arg path and must pass unchanged (this is the mechanical proxy — not a byte-level guarantee). No other beat moves.
- **R-4 — Call site.** The overlay's single solver call (`AnalystGuide.tsx:363`) passes `active.band` as the 5th argument. Latch (370–380), entry spring (298–314), scroll-into-view (223–249), and `bandPending` (385) are untouched — with a constant solved placement the side-latch merge degenerates to a no-op.
- **R-5 — Declaration.** The `s2_2` builder (`analystScript.ts:123–127`) declares `band: 'top'`. No other step declares it.
- **R-6 — Rendered result.** s2.2's bubble renders anchored at the top of the window (`atTop` branch, `AnalystGuide.tsx:435`, `top: place.offset`), above the mode chip strip, ring on the trade card, with the card's Pass/Like row fully visible. The existing scroll-into-view reservation `insets.top + BAND_EDGE + bandH + BAND_GAP` (`AnalystGuide.tsx:231, 240`) is exactly the pinned band's span, so the card is pulled clear whenever the ScrollView has range — zero new code.
- **R-7 — Both mascots.** The pin holds under `onboarding.mascot_ram` on (Fleeced, taller sprite) and off (The Analyst): the offset is inset-derived, the band grows downward, and the scroll reservation uses the *measured* `bandH`, so clearance self-adjusts.
- **R-8 — Doc row.** The `AnalystGuide` row in `mobile/src/components/CLAUDE.md` gains one clause: adjacency, with a per-step `band: 'top'` pin (#397/#398) — AND the row's quoted signature (`:70`, `solveBandPlacement(cutout, bandH, winH, insets)`) is amended to include the 5th `pin` param so it doesn't half-describe the function it names.

Every R-n maps to at least one mechanical criterion in §6.

## 4. Out of scope

- **No solver rewrite** — no change to the adjacency ordering, constants, or tall-ring fallback for the generic path.
- **No other beat moves** — only s2.2 declares the pin; n12 (`calc.trade-columns`), n19–n24, untargeted beats, and degraded beats keep today's placement.
- **Guard 11f semantics untouched** — tall-ring → bottom band remains the pinned generic answer.
- **`mobile/src/screens/TradesScreen.tsx` is READ-ONLY** — request site (3312–3318), advance site (`advanceGuideIfActive('s2.2')`, ~4335), and target registration (3221, 3243) all stay as-is. Group A owns that file this wave.
- No schema, route, flag, or analytics change.

## 5. File ownership / coordination

**This group edits:** `mobile/src/state/useGuide.ts` · `mobile/src/components/AnalystGuide.tsx` · `mobile/src/components/analystScript.ts` · `mobile/tests/check-guide-spotlight-tracking.js` · `mobile/src/components/CLAUDE.md` · this folder.

**Coordination points:**
- `TradesScreen.tsx` — Group A's file; if Group A moves the s2.2 request site or the chip strip, re-verify plan §1 line numbers. We read, never write.
- `mobile/tests/check-guide-spotlight-tracking.js` — **also extended by Group D**. Note: the file's rule numbering already runs 11a–11m, 12a, 13a–f, 14a–f, and a "rule 12" already exists (12a, calculator ScrollView movement). Our additions land inside rule 11's solver block as **11n/11o** (see §6 drift note). Orchestrator must serialize the two groups' edits to this file and confirm Group D's case IDs don't collide with 11n/11o.

## 6. D-056 test plan

> **Drift vs plan.md:** the plan named the new guard cases 11i/11j, but those IDs already exist (the overlap/inset invariant sweep, lines 1084–1095). Rule 11's last case is 11m. The new cases are therefore **11n** and **11o**.

### (a) Structural guard — extend `mobile/tests/check-guide-spotlight-tracking.js` (`npm run test:guide-spotlight-tracking`)

Group-D disjointness (verified): Group B's additions live entirely inside rule 11's block (executable cases in the lifted-solver region ~`:1022–1096`, structural 11p/11q alongside 11k–11m, block ends `:1136`); Group D extends rule 12/12a's host list, a separate block at `:1138–1172`. Disjoint, adjacent regions — textual conflict only if rule 12's header is restructured, which neither group does.

The guard already lifts `solveBandPlacement` out of the TSX via the TS AST and **runs** it (lines 1002–1012), so pin behavior is provable by execution, not shape-matching.

| Case | Assertion | Verifies |
|---|---|---|
| **11n** | `solve({top:80, height:700}, 180, 844, INSETS, 'top')` → `{from:'top', offset: INSETS.top + EDGE}` — the exact tall-ring input 11f bottom-bands, now pinned | R-2 |
| **11o** | `solve(null, 0, 844, INSETS, 'top')` → the same pin — a degraded/unmeasured s2.2 still honors the ask (pin precedes the early return) | R-2 |
| **11p** (structural) | `analystScript.ts`'s `s2_2` builder's returned object literal carries property `band` with string literal `'top'` — located via the TS AST on the builder's arrow function, not a text grep (a comment or another builder must not satisfy it) | R-5 |
| **11q** (structural) | `AnalystGuide.tsx` passes a 5th argument referencing `active.band` **inside the `solveBandPlacement` CallExpression itself** (the assertion walks the call's arguments — a bare `active.band` token elsewhere in the file must not satisfy it) | R-4 |
| existing 11d–11h + 11i/11j sweep | run the 4-arg path unchanged and must stay green | R-3 |

**Sabotage proofs — each must turn the guard red, then be reverted:**
1. **Drop the 5th parameter** from `solveBandPlacement`'s signature → 11n/11o red (the lifted function ignores the extra arg and answers bottom-band). *Self-satisfaction check:* with the real code in place, 11n's input run through the **4-arg** call still returns `{from:'bottom'}` (that is 11f) — proving 11n passes because of the pin, not because the solver started answering top for tall rings.
2. **Ignore `pin` inside the solver** (accept the param, never branch on it) → 11n/11o red. *Self-satisfaction:* same as above — 11f green + 11n green can only coexist if the branch is real.
3. **Make the pin unconditional** (always return the top pin) → 11f red **and** the 11i overlap sweep red (a ring near the top would sit under the band). *Self-satisfaction:* confirms the sweep genuinely exercises the 4-arg path — if it silently passed a 5-arg pin, this sabotage would stay green.
4. **Remove `band: 'top'` from `s2_2`** → 11p red. *Self-satisfaction:* temporarily add `band: 'top'` to a *different* builder (e.g. `s2_1`) with s2_2's removed — 11p must stay red, proving the assertion binds to s2_2 specifically.
5. **Revert the call site to 4 args** → 11q red. *Self-satisfaction:* 11q must reference the *solver call*, not merely find the token `active.band` anywhere in the file.

### (b) Code-walk proof (written into status.md at build time)

Trace, file:line-cited against the built code: s2.1 seen → chain effect requests s2.2 (`TradesScreen.tsx:3312–3318`) → `requestStep` activates with `band:'top'` → guide_v2 measured frame for `trades.card-body` (`deckWrapRef`, registration `TradesScreen.tsx:3243`) → overlay computes `solveBandPlacement(cutout, bandH, winH, insets, active.band)` → pin branch returns `{from:'top', offset: insets.top + BAND_EDGE}` → latch stores the constant (`AnalystGuide.tsx:370–380`) → `atTop` renders `{top: place.offset}` (line 435) → scroll-into-view reserves `insets.top + BAND_EDGE + bandH + BAND_GAP` of headroom (lines 231, 240), pulling the card below the band → first real swipe calls `advanceGuideIfActive('s2.2')` (`TradesScreen.tsx:~4335`), unchanged.

### (c) Operator TestFlight checklist

1. **Re-arm (first-run state required):** the Guided-tour toggle alone CANNOT re-fire s2.x — `resetGuideProgress`/`V2` never clear `firstSwipeDone` (`useOnboardingState.ts:180–192, 209–229`), and s2.1/s2.2 are first-run-gated (`TradesScreen.tsx:3293, :3316`). Use Settings → Testing → **Test stages → Factory reset** (`TestStagesScreen.tsx:186–189` → `replaceOnboardingState({})` + sign-out, which resets `firstSwipeDone`), or spawn a stage user (`:229`). **Feasibility branch:** the Test-stages row is gated on `testing.stage_users` (`TestingSection.tsx:46`) — `false` in `config/features.json:181` but delivered per-device via the experiment overlay; if the row is absent on the device, flip `testing.stage_users` → `true` + `POST /api/feature-flags/reload` for the QA window (the flag's own comment blesses this; server allowlist still gates the spawn route), and flip back after. The Guided-tour toggle (`settings/sections/GuideSection.tsx:54`, Settings → About) is only the un-dismiss lever if "Skip the tour" was previously hit.
2. Go to the **Acquire** tab with a deck present; let s2.1 show and tap to advance it.
3. **Expected:** s2.2 ("Swipe right to take it, left to pass…") renders **pinned at the top of the screen, above the mode chip strip** — ring around the trade card, the card's **Pass/Like row fully visible**; at maximum Dynamic Type / the taller ram sprite, at most a minor graze of the ring's **top edge** by the band is acceptable — the bubble must never overlap the card's content or disposition row.
4. Swipe right or left — the beat advances on the real swipe (unchanged behavior).
5. **Regression spot-check:** run "Show me around" from the calculator; confirm **n12** (trade columns) and **n19** (deck) bubbles still sit **adjacent to their rings**, and an untargeted beat (e.g. s2.1) still uses the bottom band — none of them moved to the top.
6. **Both mascots if reachable:** with `onboarding.mascot_ram` on (Fleeced — the operator's device) and, if practical, off (The Analyst): in both cases the s2.2 band sits at the top and the taller Fleeced sprite does not push the bubble over the card (the scroll reservation uses the measured band height).

**Gates:** `npx tsc --noEmit` · `npm run test:guide-spotlight-tracking` (with sabotage proofs logged) · `bash mobile/scripts/testid-lint.sh` (no testID changes expected) · results in `living-memory/TEST_LEDGER.md`.
