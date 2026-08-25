# QA round 1 — agent A — 2026-08-24

## Summary: PASS (0 findings)

Group B (#397/#398) — s2.2 band pinned to the top of the window. All five PRD sabotage
proofs plus both self-satisfaction probes reproduced independently; solver, call site,
step declaration, and guard additions all match the Round-3 contract exactly.

## Environment

- Commit: `c8b0e224`, branch `claude/new-user-feedback-55320e`, clean tree.
- node v24.14.1 · Python 3.14.4 · fresh `npm ci`.

## Results

| Test | Result | Evidence |
|---|---|---|
| `check-guide-spotlight-tracking.js` on merged tree | PASS | "All guide-spotlight-tracking checks passed" |
| R-1: `GuideStep.band?: 'top'` | PASS | `useGuide.ts:99-101`, doc comment cites #397/#398 |
| R-2: pin branch precedes every other branch incl. null-cutout early return | PASS | `AnalystGuide.tsx:75` (param), `:82` (pin return), `:85` (early return after it) |
| R-4: call site forwards `active.band` as 5th arg | PASS | `AnalystGuide.tsx:370` |
| R-5: only `s2_2` declares `band: 'top'` | PASS | `analystScript.ts:127`; `git grep band` over the file finds no other declaration |
| R-8: CLAUDE.md row amended signature + pin clause | PASS | `mobile/src/components/CLAUDE.md:70` quotes `solveBandPlacement(cutout, bandH, winH, insets, pin?)` and the per-step pin clause |
| Sabotage 1 — drop 5th param + branch | PASS (RED as mapped) | 11n and 11o red, both `{"from":"bottom","offset":92}`; revert → green |
| Sabotage 2 — accept param, never branch | PASS (RED as mapped) | 11n/11o red, all 4-arg cases stayed green — the branch is real |
| Sabotage 3 — unconditional pin | PASS (RED as mapped) | 11d, 11e, 11f (`{"from":"top","offset":67}`), 11g, 11h, and the 11i overlap sweep red (first overlap `{"c":{"top":-40,"height":120},"bandH":80,"p":{"from":"top","offset":67}}`); 11j stayed green (67 ≮ 67) — byte-identical to the build report's record, proving the sweep executes the 4-arg path |
| Sabotage 4 — remove `band: 'top'` from s2_2 | PASS (RED as mapped) | 11p red. Self-satisfaction: `band: 'top'` moved onto the `s2_1` builder → 11p **stayed red** — binds to s2_2's own AST node |
| Sabotage 5 — call site back to 4 args | PASS (RED as mapped) | 11q red (`call args: solveBandPlacement(cutout, bandH, winH, insets)`). Self-satisfaction: decoy `active?.band` expression planted elsewhere in the file → 11q **stayed red** — walks the CallExpression's arguments |
| R-3: 4-arg path behaviorally unchanged | PASS | 11d–11h + 11i/11j sweep green on the merged tree (the mechanical proxy the PRD pins) |
| `tsc --noEmit` / testid-lint / full 78-guard sweep | PASS | all green |

Group-D disjointness confirmed on the merged file: Group B's additions live in rule 11's
block; rule 12's block is the host-list version Group D shipped — both coexist, suite green.

## Findings

None. One observation:

- **Obs-1 (informational):** the build report's sabotage-3 record (which cases red, which
  offsets, 11j's 67 ≮ 67 near-miss) reproduced exactly — the logged evidence for this
  group is trustworthy as filed.

## TestFlight checklist (operator-run) — verified as executable, refined

Feasibility pre-checks confirmed in code: `resetGuideProgress`/`V2` never clear
`firstSwipeDone` (`useOnboardingState.ts:180-229`), so the Guided-tour toggle alone cannot
re-arm s2.x — the PRD's Factory-reset path is the only route. `TestStagesScreen.tsx:189`
(`replaceOnboardingState({})`) exists; the Test-stages row is gated on
`testing.stage_users` (`TestingSection.tsx`, flag false at `features.json:181` — the
flag's own comment blesses a temporary QA-window flip + `POST /api/feature-flags/reload`).
The Guided-tour toggle lives at Settings → About (`GuideSection.tsx`, "Guided tour"
TickLabel) and is only the un-dismiss lever.

1. **Re-arm (first-run state required):** Settings → Testing → **Test stages → Factory
   reset** (clears `firstSwipeDone` + signs out), or spawn a stage user. If the Test-stages
   row is absent, flip `testing.stage_users` → true + hot-reload flags for the QA window,
   flip back after. Do NOT expect the Guided-tour toggle to re-fire s2.x — it will not.
2. Acquire tab with a deck present; s2.1 shows; tap to advance it.
3. **Expected:** s2.2 ("Swipe right to take it, left to pass…") renders **pinned at the
   top of the screen, above the mode chip strip** — ring around the trade card, Pass/Like
   row fully visible. At max Dynamic Type / the taller ram sprite, a minor graze of the
   ring's **top edge** by the band is acceptable; the bubble must never cover the card's
   content or disposition row.
4. Swipe right or left — the beat advances on the real swipe (unchanged).
5. **Regression spot-check:** "Show me around" from the calculator → n12 (trade columns)
   and n19 (deck) bubbles still sit **adjacent to their rings**; an untargeted beat still
   uses the bottom band. None moved to the top.
6. **Both mascots if practical:** `onboarding.mascot_ram` on (Fleeced) and off (The
   Analyst) — band at the top in both; the taller sprite must not push the bubble over the
   card (scroll reservation uses the measured band height).
