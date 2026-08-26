# QA round 1 — agent B — 2026-08-24

## Summary: PASS (1 finding)

Group B — #397/#398 s2.2 band pinned to the top. All five PRD sabotage proofs
plus both self-satisfaction bind checks reproduced independently: 7/7 RED as
specified, including the exact 11j prediction. Contract R-1…R-8 verified in
the merged code. One minor citation-path finding in the checklist.

## Environment

- Commit: `c8b0e224`; tree clean after QA (all sabotages reverted).
- node v24.14.1 · Python 3.14.4 · fresh `npm ci`
- Guard: `node tests/check-guide-spotlight-tracking.js` (rule 11 block, cases 11n–11q)

## Results

| Test | Result |
|---|---|
| Batch gates (npm ci / tsc / testid-lint / 78-guard sweep / full pytest / empty web diff) | PASS — see Group A findings file for numbers |
| Guard baseline (incl. 11d–11h, 11i/11j sweep, 11n/11o/11p/11q) | PASS, exit 0 |
| Sabotage 1: drop 5th param + pin branch → 11n/11o red | PASS — RED exactly {11n, 11o} |
| Sabotage 1 self-satisfaction: 11f (4-arg twin of 11n's input) green in baseline — 11n passes because of the pin, not a solver default change | PASS (baseline 11f green) |
| Sabotage 2: accept param, never branch → 11n/11o red; 4-arg cases stay green | PASS — RED exactly {11n, 11o} |
| Sabotage 3: unconditional pin → 11d/11e/11f/11g/11h + 11i sweep red, **11j stays green** | PASS — RED exactly {11d,11e,11f,11g,11h,11i}; 11j green as the PRD predicted (67 ≮ 67) |
| Sabotage 4: remove `band: 'top'` from s2_2 → 11p red | PASS — RED {11p} |
| Sabotage 4 bind check: `band: 'top'` moved to the s2_1 builder → 11p **stays red** | PASS — RED {11p} (binds to s2_2's AST node) |
| Sabotage 5: call site reverted to 4 args → 11q red | PASS — RED {11q} |
| Sabotage 5 bind check: 4-arg call + decoy `active.band` token planted elsewhere → 11q **stays red** | PASS — RED {11q} (walks the CallExpression's own arguments) |
| R-1: `GuideStep.band?: 'top'` (`useGuide.ts:101`) | VERIFIED |
| R-2: pin branch first, before the null-cutout early return (`AnalystGuide.tsx:75` param, `:82` branch, `:85` early return) | VERIFIED |
| R-3: 4-arg adjacency body unchanged; 11d–11j execute it green | VERIFIED (mechanical proxy, per the reconciliation N-1 caveat) |
| R-4: call site `solveBandPlacement(cutout, bandH, winH, insets, active.band)` (`:370`) | VERIFIED |
| R-5: exactly one `band: 'top'` in `analystScript.ts` (`:127`, the s2_2 builder) | VERIFIED (`grep -c` = 1) |
| R-6: `atTop` renders `{ top: place.offset }` (`AnalystGuide.tsx:442`); scroll-into-view reserves `insets.top + BAND_EDGE + bandH + BAND_GAP` | VERIFIED |
| R-7: offset is inset-derived; reservation uses measured `bandH` — mascot-agnostic by construction | VERIFIED (code-walk; runtime is the operator's checklist) |
| R-8: `mobile/src/components/CLAUDE.md:70` quotes `solveBandPlacement(cutout, bandH, winH, insets, pin?)` + the per-step pin clause | VERIFIED |
| Group D disjointness: Group B's diff (`d42b2a68`) is rule-11-block-only; rule 12 extended separately by Group D (`25e4f2d5`); both green in one file | VERIFIED |
| TradesScreen READ-ONLY: `d42b2a68` touches useGuide.ts, AnalystGuide.tsx, analystScript.ts, the guard, CLAUDE.md — no TradesScreen | VERIFIED |

## Findings

**F-1 · minor · Checklist/PRD path citations for the settings files drop the
`screens/` segment.**
- Repro: prd.md §1 step 1 and §6c step 1 cite
  `settings/sections/GuideSection.tsx:54` and `TestingSection.tsx:46`; the
  real paths are `mobile/src/screens/settings/sections/GuideSection.tsx`
  (the "Guided tour" toggle renders at :51–63) and
  `mobile/src/screens/settings/sections/TestingSection.tsx:46`
  (`useFlag('testing.stage_users')`).
- Expected (PRD-ref §6c): cites resolve as written. Actual: the files exist
  and the line numbers are right, but the path as written doesn't resolve —
  trivial to the operator (they navigate the UI, not the repo), relevant to a
  future editor following the cite.
- Evidence: `find mobile/src -name GuideSection.tsx` →
  `mobile/src/screens/settings/sections/GuideSection.tsx`.

Verified non-issues hunted: `replaceOnboardingState({})` in
`TestStagesScreen.tsx:186–189` does clear `firstSwipeDone` (full defaults
replace) and neither `resetGuideProgress` nor `resetGuideProgressV2` touches
it — the B-1 re-arm analysis holds in the merged code. `testing.stage_users`
false at `config/features.json:181` with the flag comment blessing the QA-window
flip, exactly as §6c step 1's feasibility branch states.

## TestFlight checklist (operator-run)

Executable as written (with F-1's path note irrelevant at runtime). Verified
version:

1. **Re-arm (first-run state required):** the Guided-tour toggle alone cannot
   re-fire s2.x (`resetGuideProgress`/`V2` never clear `firstSwipeDone`; s2.1
   and s2.2 are first-run-gated). Use Settings → Testing → **Test stages →
   Factory reset** (clears onboarding state + signs out) or spawn a stage
   user. If the Test-stages row is absent: flip `testing.stage_users` → true
   + `POST /api/feature-flags/reload` for the QA window, flip back after. The
   "Guided tour" toggle (Settings → Help & about) is only the un-dismiss
   lever if "Skip the tour" was previously hit.
2. Acquire tab with a deck present; let s2.1 show and tap to advance it.
3. **Expected:** s2.2 ("Swipe right to take it, left to pass…") renders
   **pinned at the top of the screen, above the mode chip strip** — ring
   around the trade card, the card's **Pass/Like row fully visible**; at max
   Dynamic Type / the taller ram sprite, at most a minor graze of the ring's
   top edge is acceptable — the bubble must never overlap the card's content
   or disposition row.
4. Swipe right or left — the beat advances on the real swipe (unchanged).
5. **Regression spot-check:** "Show me around" from the calculator; confirm
   n12 (trade columns) and n19 (deck) bubbles still sit adjacent to their
   rings, and an untargeted beat (e.g. s2.1) still uses the bottom band.
6. **Both mascots if reachable** (`onboarding.mascot_ram` on = Fleeced, off =
   The Analyst): in both cases the s2.2 band sits at the top and the taller
   sprite does not push the bubble over the card.
