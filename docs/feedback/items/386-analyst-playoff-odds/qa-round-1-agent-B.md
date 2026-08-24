# QA round 1 — agent B — 2026-08-24

## Summary: PASS (1 finding)

Group D — #386/#391 LeagueSummaryScreen layout-change guide notifications.
All four PRD/build-report sabotages reproduced independently — RED with the
per-host parameterized messages, including the not-self-satisfying probe
(dropping `onScroll` trips the loud 12a branch AND rule 9b, exactly as the
critic predicted in O-4). Contract R-1…R-6 verified. One minor citation-path
finding shared with Group B.

## Environment

- Commit: `c8b0e224`; tree clean after QA.
- node v24.14.1 · Python 3.14.4 · fresh `npm ci`
- Guard: `node tests/check-guide-spotlight-tracking.js` (rule 12 host list)

## Results

| Test | Result |
|---|---|
| Batch gates (npm ci / tsc / testid-lint / 78-guard sweep / full pytest / empty web diff) | PASS |
| Guard baseline (rule 12 over both hosts + Group B's 11n–11q in the same file) | PASS, exit 0 |
| Sabotage (a): delete `onContentSizeChange` from LeagueSummaryScreen → red | PASS — RED, `12b — src/screens/LeagueSummaryScreen.tsx:1491 also announces from onContentSizeChange` |
| Sabotage (b): delete `onLayout` → red | PASS — RED, symmetric 12b onLayout message, host named |
| Sabotage (c): additionally delete `onScroll` (parse-drop probe) → still red via loud branch | PASS — RED, `12a — src/screens/LeagueSummaryScreen.tsx's page ScrollView announces movement: no wired onScroll found` **plus** rule 9's independent `9b` failure — a host dropped from parsing cannot green the suite |
| Sabotage (d): symmetric calculator check — delete `onContentSizeChange` from TradeCalculatorScreen → red | PASS — RED, 12b with the calculator host named (existing coverage preserved) |
| All reverts | PASS — exit 0 after each |
| R-1: both props on the page ScrollView (`LeagueSummaryScreen.tsx:1504-1505`) with the #386 comment (`:1498-1503`), mirroring the `TradeCalculatorScreen` precedent | VERIFIED |
| R-2: no conditional, no new import — `notifyGuideTargetsMoved` import pre-exists at `:51`; `guideTargets.ts:51-60` walks an empty Set with no tour up (comment at `:44-48` pins the posture) | VERIFIED |
| R-3: `grep -c mascot_ram LeagueSummaryScreen.tsx` → 0 | VERIFIED |
| R-4: Group D's commit `25e4f2d5` touches exactly LeagueSummaryScreen.tsx, the guard, and `screens/CLAUDE.md` — no `AnalystGuide.tsx`, `useGuide.ts`, `guideTargets.ts`, `components/analyst/` | VERIFIED |
| R-5: `onScroll={notifyGuideTargetsMoved}` (`:1497`) + `scrollEventThrottle={16}` (`:1506`) intact; calculator props untouched by this commit | VERIFIED |
| R-6: rule 12 iterates `GROWING_HOSTS_REL = [TradeCalculatorScreen.tsx, LeagueSummaryScreen.tsx]` (guard `:1233-1237`); assertions run against the real files by relative path | VERIFIED |
| Code-walk spot-checks: n5 = `analystScript.ts:348-353` (target `league-summary.pos-pills`, `retireAfter: leagueFilterApplied` at `:353`); receipt recorded at `LeagueSummaryScreen.tsx:~1012`; `enableTour()` → `resetGuideProgressV2()` when guide_v2 active (`useGuide.ts:523-524`); overlay re-measure subscription + `solveBandPlacement(..., active.band)` at `AnalystGuide.tsx:370` | VERIFIED |
| Checklist preconditions: `outlook.odds` true (`config/features.json:69`); `testing.stage_users` false (`:181`) as the checklist states | VERIFIED |

## Findings

**F-1 · minor · Checklist path citations drop the `screens/` segment.**
- Repro: prd.md §5c cites `settings/sections/GuideSection.tsx:51-63` and the
  reconciliation cites the same shape; the real path is
  `mobile/src/screens/settings/sections/GuideSection.tsx` (toggle at :51–63 —
  line numbers correct). Same class as Group B's citation.
- Expected (PRD-ref §5c): cite resolves as written. Actual: file exists, line
  range right, path prefix wrong. No runtime impact on the operator.
- Evidence: `find mobile/src -name GuideSection.tsx`.

Verified non-issue hunted: the PRD's build-report line numbers for the outlook
triggers (`:2840-2849`, `:2856-2865`) drifted a few lines from the PRD §2
originals (`:2834-2841`, `:2849-2857`) because this diff added 8 lines above
them — the build report already re-cited them correctly; both structures exist.

## TestFlight checklist (operator-run)

Executable as written, including the honest feasibility probe. Verified
version:

Precondition: Sleeper league with ≥3 ranked members; `outlook.odds` on (it
is). Beat n5 must be armed — the "Guided tour" toggle (Settings → Help &
about) un-dismisses but never clears receipts, and **n5 retires permanently
on one `league_filter_applied` receipt**. Feasibility check first: after a
toggle cycle, make a qualifying cold visit to the League tab; if the bubble
does not appear, the beat is receipt-retired on this install — fall back to a
different/fresh Sleeper user (onboarding state is per-user;
`testing.stage_users` is false, so the TestStages reset needs a deliberate
flag flip). If neither path works, steps 1–5 degrade to the §5b code-walk and
TEST_LEDGER must record that — never run the steps against an unarmed beat
and report them passed.

1. League tab → expand the "Season outlook" projection. **Force-quit and
   relaunch**, then navigate to the League tab (a tab switch does NOT remount
   the screen; only a cold start reproduces the mount race).
2. Wait for the Analyst bubble ("Filter one position…"). **Expected:** ring +
   scrim cutout sit exactly on the position-filter pills; the expanded
   playoff odds section is dimmed by scrim only — **no hole punched through
   it**.
3. While the bubble is up, tap the strip to **collapse**. Expected: pills
   shift up; ring + band follow immediately.
4. Re-expand while the tour is open. Expected: ring + band follow back down;
   acceptable degrade if the pills fall below the fold: ring offscreen,
   bubble stays (B1) — never a ring parked mid-section.
5. Re-arm, **minimize** the projection, force-quit + relaunch to the League
   tab. Expected: ring + band on the pills (#391 control case — no
   regression).
6. With the bubble up, scroll the page. Expected: ring tracks the pills
   (existing behavior, must not regress).
7. If the device has `onboarding.mascot_ram`: repeat steps 1–4 once —
   identical expectations.
