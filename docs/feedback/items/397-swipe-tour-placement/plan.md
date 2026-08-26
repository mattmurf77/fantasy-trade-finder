# #397/#398 — Pin the swipe-coaching beat's bubble to the top of the screen

**Date:** 2026-08-24 · **Group B planner** · fast-track bug path (mobile-only)

## The feedback

- **#397** (bug, v1.16.3, mattmurf77, TradesHome): "Fleeced swipe right/left onboarding step needs to be lowered to the bottom of the screen."
- **#398** (same, minutes later): "Actually best spot is top of the screen above the trade chip section."

**#398 supersedes #397.** The operative ask: the swipe-coaching bubble renders at the **top of the screen, above the trade chip section** (the mode chip strip — `TradeHomeUtilityRow` / `TradeFinderModeBar` inside `modeBarWrap`, the first child of TradesScreen's main ScrollView, `mobile/src/screens/TradesScreen.tsx:5045–5122`).

## 1 · Beat location (file:line trace)

The beat is **`s2.2`** — the v1 swipe-coaching step, *not* one of the #384 calc-tour beats (those are n10–n24; the deck half n19–n24 has no swipe beat — `mobile/src/utils/calcTour.ts:58–64`). "Fleeced" is the mascot name because `onboarding.mascot_ram` is live on the operator's device (CHANGELOG 2026-08-24).

| What | Where |
|---|---|
| Step definition — `id: 's2.2'`, `pose: 'point'`, `advance: 'action'`, `target: 'trades.card-body'`, line "Swipe right to take it, left to pass. Every swipe teaches me." | `mobile/src/components/analystScript.ts:123–127` |
| Request site — chained after s2.1, first session, deck present, no swipe yet | `mobile/src/screens/TradesScreen.tsx:3315–3318` |
| Advance — the real first swipe calls `advanceGuideIfActive('s2.2')` | `mobile/src/screens/TradesScreen.tsx:4341` |
| Target registration — `trades.card-body` → `deckWrapRef`, the wrapper around the whole deck card | `mobile/src/screens/TradesScreen.tsx:3221, 3243`; rendered at `6292–6297` |
| Overlay host — measures the target, solves band placement, renders avatar+bubble | `mobile/src/components/AnalystGuide.tsx` (mounted once in `RootNav`) |

s2.2 also survives verbatim in the onboarding-tour-merge spine ("First cards … s2.2 (swipe teach, action)", `docs/plans/onboarding-tour-merge/plan.md:66`), so fixing its placement is not throwaway work and contradicts neither D-158 nor Wave A/B0.

## 2 · Root cause — what places the bubble today

Placement is the adjacency solver `solveBandPlacement(cutout, bandH, winH, insets)` (`mobile/src/components/AnalystGuide.tsx:70–90`, W7 fix, 2026-08-22k):

1. **Above** the ring if the whole band clears `insets.top + BAND_EDGE` (line 81–82);
2. else **below** the ring if it fits above the bottom inset (line 87–88);
3. else the legacy **bottom band** `{from:'bottom', offset: BAND_BOTTOM=92}` (lines 44, 89).

s2.2's ring is the **entire deck card** — a cutout ~500–600 pt tall on an 844 pt window. For a ring that tall:

- "below" always fails (card bottom + band never fits above the bottom inset);
- "above" is *marginal*: the card top sits ~230 pt down (TopBar + chip strip + outlook receipt), the band is ~130–200 pt tall depending on Dynamic Type and the mascot sprite, so the branch flips per device/text-size between (a) the band squeezed directly above the card — mid-screen, over the receipt/strip rows — and (b) the bottom-band fallback at `bottom: 92`, floating over the card's Pass/Like disposition row.

Neither outcome is what the operator wants, and the flip between them is device-dependent — which is itself part of the bug. Guard `check-guide-spotlight-tracking.js` case **11f** (`mobile/tests/check-guide-spotlight-tracking.js:1046–1053`) pins the tall-ring → bottom-band fallback as correct *generic* behavior, so the fix must not change the solver's default answers — it must be a **per-step override**.

## 3 · Chosen fix — an opt-in per-step pin, threaded through the pure solver

Three small edits, all mobile:

1. **`mobile/src/state/useGuide.ts`** — add one optional field to `GuideStep` (the interface at ~line 80):
   `band?: 'top'` — "pin the avatar band to the top of the window instead of adjacency placement (#397/#398)". Inert everywhere it is absent.
2. **`mobile/src/components/AnalystGuide.tsx`** — give `solveBandPlacement` an optional 5th parameter `pin?: 'top'` and a head branch: `if (pin === 'top') return { from: 'top', offset: insets.top + BAND_EDGE }`. The call site (line 363) passes `active.band`. Everything else — latch (370–380), entry spring (298–314), scroll-into-view (223–249), `bandPending` (385) — is untouched: with a constant solved placement the side-latch merge is a no-op by construction.
3. **`mobile/src/components/analystScript.ts`** — `s2_2` declares `band: 'top'` (line ~125).

Why this lands "above the trade chip section": at `insets.top + BAND_EDGE` the band overlays the scrim-dimmed TopBar region, above the chip strip; the ring stays on the card. The existing scroll-into-view already reserves `insets.top + BAND_EDGE + bandH + BAND_GAP` of headroom above a targeted frame (`AnalystGuide.tsx:231, 240`), which is *exactly* the span the pinned band occupies — so whenever the ScrollView has range, the card is pulled fully clear of the bubble with zero new code.

Also update the `AnalystGuide` row in `mobile/src/components/CLAUDE.md` (one clause: adjacency, with a per-step `band:'top'` pin). No route, schema, flag, or analytics change → `docs/api-reference.md` etc. n/a.

### W7/W8 fragility check (what must not regress)

- **Entry spring vs unmounted band (W8):** the spring stays keyed on the band rendering (`spotlightPending`), JS-driven — untouched; guards 14a–f keep passing.
- **`transitionEnd` auto-start (W8 second pass):** calculator-side, calc-tour beats only — untouched.
- **Band offset live / side latched (W8):** with the pin the solver returns a constant, so latch-vs-solved merging degenerates safely; non-pinned beats behave byte-identically.
- **4-arg solver behavior:** byte-identical — guards 11d–11h and the overlap/inset sweep (1067+) run with `pin` undefined and pass unchanged.
- **Other tall-ring beats (e.g. n12 `calc.trade-columns`):** unaffected — the pin is declared per step, and only s2.2 declares it.

## 4 · Alternatives rejected

- **Change the solver's tall-ring fallback globally** (bottom band → top band): moves every untargeted step and every tall-ring beat (n12, degraded beats); guard 11f/11g pins the current fallback as correct; blast radius far beyond the ask.
- **Retarget s2.2 at the chip strip or a smaller child of the card:** the ring must stay on the thing being swiped; a chip-strip ring teaches the wrong control.
- **Screen-side placement (TradesScreen measures the chip strip and positions the bubble):** placement is the overlay's job; and TradesScreen is Group A's surface this batch — editing it here creates an avoidable merge collision.
- **Heuristic in the solver ("ring taller than X ⇒ top"):** silently re-sites future beats; the per-step field keeps intent in the script data where copy/placement decisions already live.

## 5 · File ownership (Group A serialization)

**This fix edits:**
- `mobile/src/state/useGuide.ts` (type only, +1 optional field)
- `mobile/src/components/AnalystGuide.tsx` (solver param + call site)
- `mobile/src/components/analystScript.ts` (s2_2 declaration)
- `mobile/tests/check-guide-spotlight-tracking.js` (new assertions)
- `mobile/src/components/CLAUDE.md` (map row clause)
- this folder (plan/status)

**Deliberately NOT edited:** `mobile/src/screens/TradesScreen.tsx` — the request site, target registration, and advance site all stay as-is.

**Overlap risk with Group A (finder filters / outlook entry on the same TradesScreen/tour surface):** `TradesScreen.tsx` (we read it, don't touch it — but if Group A moves the s2.2 request site or the chip strip, re-verify §1 line numbers), and potentially `analystScript.ts` / `useGuide.ts` if Group A touches outlook beats (n2a/n2b/n11). Orchestrator should serialize any Group A change to those two files against this one.

## 6 · Evidence plan (D-056)

**Structural guard** (extend `mobile/tests/check-guide-spotlight-tracking.js`, which already lifts and *runs* the solver — sabotage-provable):
- new case **11i**: `solve({top:80,height:700}, 180, 844, INSETS, 'top')` → `{from:'top', offset: INSETS.top + BAND_EDGE}` (the tall-ring case that used to bottom-band);
- new case **11j**: `solve(null, 0, 844, INSETS, 'top')` → same pin (a degraded/unmeasured s2.2 still honors the ask);
- existing 11d–11h prove the 4-arg path is unchanged;
- structural: `analystScript.ts`'s `s2_2` builder declares `band: 'top'`, and `AnalystGuide`'s solver call site passes `active.band`.
- Sabotage proofs: remove `band:'top'` from s2_2 → red; delete the pin branch → red; make the pin unconditional → 11f red.

**Code-walk proof** (in this folder's status doc at build time): trace s2.1-seen → chain effect (`TradesScreen.tsx:3315–3318`) → `requestStep` → v2 measured frame → `solveBandPlacement(cutout, bandH, winH, insets, 'top')` → `atTop` render at `top: insets.top + BAND_EDGE` (`AnalystGuide.tsx:435`), with the scroll-into-view reservation keeping the card below the band.

**Gates:** `npx tsc --noEmit`; `npm run` guard suite incl. the extended spotlight guard; `bash mobile/scripts/testid-lint.sh` (no testID changes expected).

**Operator TestFlight checklist:**
1. Settings → About → toggle "Guided tour" off, then on (this runs `resetGuideProgressV2`, `useGuide.ts:521–522`, re-arming s2.2).
2. Go to the Acquire tab with a deck present; let s2.1 show and advance it.
3. **s2.2 ("Swipe right to take it, left to pass…") renders pinned at the top of the screen, above the mode chip strip** — ring around the trade card, card's Pass/Like row fully visible, bubble nowhere over the card.
4. Swipe right or left — the beat advances on the real swipe (unchanged).
5. Regression spot-check: run "Show me around" from the calculator; confirm n12 (canvas) and n19 (deck ✕) bubbles still sit adjacent to their rings, and the sign-in username beat still shows avatar+bubble (W8 spring).

## 7 · Risks

- **Shared code path:** every targeted beat flows through `solveBandPlacement` — mitigated by the opt-in 5th param defaulting to undefined; the invariant sweep in the guard runs the 4-arg path untouched.
- **Small windows / max Dynamic Type:** if the ScrollView is already at offset 0 and the reserved headroom exceeds the card's natural top, the pinned band can graze the ring's top edge. Worst case is a few points of overlap with the ring border — strictly better than today's bubble over the Pass/Like row.
- **TopBar occlusion:** while s2.2 is up, the band covers the (scrim-dimmed) TopBar controls. Same class of occlusion as today's bottom band over the card; the beat is escapable (per-step ✕, skip-tour, swipe-away).
- **Tour-merge Waves A/B (D-158):** s2.2 rides into the merged spine as data; the pin travels with it. If Wave B0 reshapes the TradesHome top region (canvas above the deck), the pin still reads "top of window" and stays correct by construction.
- **Mascot band height:** Fleeced's sprite can be taller than the Analyst (`components/analyst/CLAUDE.md`); a top-anchored band grows downward, and the scroll reservation uses the *measured* `bandH`, so the clearance math self-adjusts.
