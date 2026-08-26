# QA round 1 — agent A — 2026-08-24

## Summary: PASS (0 findings)

Group A (#376/#379/#394) — minimized "Outlook & filters" row on TradesHome. Every PRD
mechanical criterion re-proven independently on the merged tree; the full 12-case sabotage
matrix reproduced from scratch (not trusted from the build report). No contract deviation
found.

## Environment

- Commit: `c8b0e224` ("merge Group F mobile: QuickSet client stops sending demoted_pids…"),
  branch `claude/new-user-feedback-55320e`, clean tree before and after QA.
- node v24.14.1 · Python 3.14.4 · fresh `npm ci` (real `node_modules` dir, no symlink).

## Results

| Test | Result | Evidence |
|---|---|---|
| Guard `check-finder-conditions-reachable.js` on merged tree | PASS | 6 passed, 0 failed |
| Sabotage S1a — delete the row entirely | PASS (RED as mapped) | assertions 1, 2, 3 red; revert → 6/6 green |
| Sabotage S1b — delete container id, keep `.change` | PASS (RED as mapped) | assertion 1 red (2, 3 also fire — boundary anchor works) |
| Sabotage S2a — prepend `homeInlineVariant !== 'control' && ` | PASS (RED as mapped) | assertion 2 red, alias named in output |
| Sabotage S2b — append `&& showInlineHome` | PASS (RED as mapped) | assertion 2 red |
| Sabotage S2c — append `&& presentationV2On` | PASS (RED as mapped) | assertion 2 red |
| Sabotage S2d — drop `!firstRun` | PASS (RED as mapped) | assertion 2 red |
| Sabotage S2e — gate via intermediate variable | PASS (RED as mapped) | assertion 2 red (`row condition is \`outlookFallbackGate\``) |
| Sabotage S3 — row into `{!consolidateOn ? (` branch | PASS (RED as mapped) | assertion 3 red (assertion 2 co-fires) |
| Sabotage S4 — `setDnaSheetOpen(true)` → `setOutlookOpen(true)` in row span | PASS (RED as mapped) | assertion 4 red, span-scoped (5 other `setDnaSheetOpen(true)` sites did not self-satisfy) |
| Sabotage S5a — re-add `onConditions` pass in TradesScreen | PASS (RED as mapped) | assertion 5 red |
| Sabotage S5b — re-add `trades.home-utility.conditions` button | PASS (RED as mapped) | assertion 5 red |
| Sabotage S6 — drop `hideTeamAndPlayer={sheetTargetingOn && consolidateOn}` | PASS (RED as mapped) | assertion 6 red |
| R-1 code-walk (gate, siblings, value map) | PASS | verified — see below |
| R-2 removal proof | PASS | `git grep onConditions\|home-utility.conditions mobile/src/` → 0 code hits (one comment reference in CLAUDE.md/TradeHomeUtilityRow doc text only) |
| R-3/R-4/R-5 (complement predicate, no variant/flag read) | PASS | gate at `TradesScreen.tsx:5155` is the exact whitelist; wrapper gate `:5127` reads only `finderMode`; no `outlookDirectionOn`/`showInlineHome` in `:5155-5201` |
| R-6 untouched surfaces | PASS | `git diff ff153a0..c8b0e224 -- InLeagueCalculator.tsx OutlookBiasReceipt.tsx` empty; `TradingWithStrip` and prefs-changed strip regions intact; `check-trades-banner-region.js` green in the 78-suite sweep |
| R-7 no interrupt slot | PASS | no `useInterruptSlot` in the row's span |
| `npx tsc --noEmit` / testid-lint / full 78-guard sweep | PASS | all green |

Code-walk spot verification (merged line numbers): `consolidateOn = fullSheetOn && !!finderMode`
(`TradesScreen.tsx:731`); `outlookReceiptShown` predicate `:1047-1053` (receipt's own
`outlookReceiptCovers`); `firstRun` latch `:433-440`; row `:5155-5200`; Change →
`haptics.selection(); setDnaSheetOpen(true)` `:5170-5173`; `OUTLOOK_FALLBACK_LABEL`
`:7446-7452` carries the receipt's LEAN names verbatim (checked against
`OutlookBiasReceipt.tsx:34-39`) plus `not_sure` → "Not sure"; null → "Not set" at the call
site `:5159-5163`. testIDs `trades.outlook-fallback`/`.change`/`.details` all present;
`mobile/src/screens/CLAUDE.md` and `components/CLAUDE.md` rows updated as the PRD §7 required.

## Findings

None blocking or major. Two observations, neither a PRD violation:

- **Obs-1 (informational):** `OUTLOOK_FALLBACK_LABEL[prefsQuery.data.team_outlook]` has no
  fallback for an out-of-vocabulary `team_outlook` value — it would render
  "Outlook & filters · undefined". The server enum is exactly the five mapped values, so
  this is unreachable today; noting for the Wave B0 rewrite that deletes the row anyway.
- **Obs-2 (informational):** the code comment above the details line says "≤2-row budget"
  while the render is `numberOfLines={1}` — this matches PRD §4 ("one dim ellipsized bodySm
  line"); the PRD's R-1 sentence ("same ≤2-row budget as the receipt's #315 contract") is
  the looser phrasing. No behavior gap.

## TestFlight checklist (operator-run) — verified as executable, minor wording refinements

All referenced surfaces confirmed to exist at the cited locations: flags
`trades.finder_hub`/`edit_full_sheet`/`sheet_targeting` true, `trade.outlook_direction`
false, `calc.merged_layout` true (`config/features.json:11,60,84,213,217`); `TestStages`
route registered (`RootNav.tsx:886`); `config/tester_allowlist.json` present; #333
dropdowns real (`InLeagueCalculator.tsx:788,805`).

1. **Strip variant (your device), outlook declared:** Acquire tab — below the icon utility
   row (Today/Draft/Free agents/Manual calc), an "Outlook & filters · <your outlook>" line
   renders — e.g. "· Contending", never blank, never "Not set".
2. The icon row has **no Filters button**; every remaining button still navigates
   (Draft / Free agents / Manual calc, plus Today / Track record if your build shows them).
3. Tap **Change** (the ice text at the row's right — the row body itself is not tappable;
   that is by design) → the full sheet opens: outlook chips, Shopping/Chasing, trade-idea
   lane, fairness, League + Trading-with targeting, untouchables, intent.
4. Change any preference, close the sheet → "Preferences changed — tap to refresh" strip
   appears; tap it → deck regenerates; the row reflects the new outlook/summary.
5. **Undeclared state** (fresh account that has never declared an outlook — there is no
   clear-outlook affordance): the line reads "Not set"; Change opens the same sheet; the
   "Set your team's outlook" banner may also appear (it can be deferred behind
   quickset/coach-mark/apple prompts — that is slot arbitration, not a bug). Bonus: save
   Chasing/Shopping positions *without* picking an outlook → the line reads **"Not sure"**
   (never "Not_sure", never "Not set").
6. **Control variant** — use a fresh stage account (Settings → Testing → Test stages; the
   row is gated on `testing.stage_users`, currently false in `features.json:181` —
   flip + `POST /api/feature-flags/reload` for the QA window if absent, flip back after).
   A stage account is off the tester allowlist, so `trades_home_inline` assigns no variant
   → control. **Expected: the chip mode bar renders instead of the icon row — correct for
   this cohort, not a bug.** The same "Outlook & filters" line renders below the mode bar
   and Change opens the full sheet. Fallback: any non-allowlisted tester account
   (e.g. jonbonjourvi).
7. **First-run** (fresh stage user): the minimized row is absent (by design, A1); the
   outlook banner is the entry; after the first swipe + a remount (leave and reopen the
   tab is not enough — kill/relaunch to be sure of a fresh mount) the row appears.
