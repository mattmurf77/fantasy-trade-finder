# QA round 1 — agent A — 2026-08-24

## Summary: PASS (0 findings)

Group D (#386/#391) — LeagueSummaryScreen announces layout changes to the guide. All four
sabotage cases reproduced independently (including the 12a loud-fail not-self-satisfying
proof and the symmetric calculator check); R-2/R-3/R-4/R-5 contract checks verified on the
merged tree.

## Environment

- Commit: `c8b0e224`, branch `claude/new-user-feedback-55320e`, clean tree.
- node v24.14.1 · Python 3.14.4 · fresh `npm ci`.

## Results

| Test | Result | Evidence |
|---|---|---|
| `check-guide-spotlight-tracking.js` on merged tree | PASS | all checks pass, incl. rule-12 host-list lines for both hosts |
| R-1: both props on the page ScrollView | PASS | `LeagueSummaryScreen.tsx:1504-1505` (`onLayout`/`onContentSizeChange` → `notifyGuideTargetsMoved`), #386 comment `:1498-1503` |
| R-5: existing announcements preserved | PASS | `onScroll` `:1497`, `scrollEventThrottle={16}` `:1506`; calculator props intact at `TradeCalculatorScreen.tsx:675-676` |
| Sabotage (a) — delete `onContentSizeChange` from LeagueSummaryScreen | PASS (RED as mapped) | `FAIL 12b — src/screens/LeagueSummaryScreen.tsx:1491 also announces from onContentSizeChange…`, exit 1; revert → green |
| Sabotage (b) — delete `onLayout` | PASS (RED as mapped) | symmetric 12b FAIL naming `onLayout` |
| Sabotage (c) — additionally delete `onScroll` | PASS (RED as mapped) | loud `FAIL 12a — …'s page ScrollView announces movement: no wired onScroll found`, host named, **plus** rule 9's independent `FAIL 9b` — exactly the co-fire the reconciliation's O-4 predicted. A host dropped from parsing cannot green the suite |
| Sabotage (d) — delete `onContentSizeChange` from TradeCalculatorScreen | PASS (RED as mapped) | 12b FAIL naming the calculator host — existing coverage preserved |
| R-2: no guide-state conditional added | PASS | props are unconditional; `notifyGuideTargetsMoved` import pre-exists; no new guide-state read in the screen's wave diff |
| R-3: mascot-agnostic | PASS | `git grep mascot_ram mobile/src/screens/LeagueSummaryScreen.tsx` → 0 hits |
| R-4: shared analyst files untouched by this group | PASS | wave diff on `guideTargets.ts` / `components/analyst/` empty; `AnalystGuide.tsx`/`useGuide.ts` changes are Group B's own (rule-11 pin), not Group D's |
| Assertions run against real files by relative path | PASS | sabotages were performed on the working tree and detected — no fixture indirection |
| `tsc --noEmit` / testid-lint / full 78-guard sweep | PASS | all green |

## Findings

None. One observation:

- **Obs-1 (informational):** the build report's sabotage transcript (exact FAIL strings,
  the 9b co-fire in case c) reproduced verbatim — the logged evidence for this group is
  trustworthy as filed.

## TestFlight checklist (operator-run) — verified as executable, refined

Code-side references confirmed: `outlook.odds` true (`features.json:69`); the Guided-tour
toggle is the "Guided tour" TickLabel in `settings/sections/GuideSection.tsx`, mounted
under Settings → Help & about (`account.settings_hub` true); `testing.stage_users` false
(`features.json:181`), so the TestStages reset needs a deliberate QA-window flag flip;
n5 retires permanently on one `league_filter_applied` receipt — the feasibility probe is
load-bearing, not boilerplate.

Precondition: Sleeper league with ≥3 ranked members; beat n5 armed. Re-arm attempt:
Settings → Help & about → "Guided tour" toggle off→on (un-dismiss only — it never clears
receipts). **Feasibility probe first:** cold-visit the League tab; if no bubble appears,
the beat is receipt-retired on this install (you have applied a position filter at some
point) — no toggle cycle can re-arm it. Fallback: a different/fresh Sleeper account
(onboarding state is per-user), or flip `testing.stage_users` for the window. If neither
path works, record steps 1–5 as degraded-to-code-walk in TEST_LEDGER — do not run them
against an unarmed beat and report a pass.

1. League tab → expand the "Season outlook" projection. **Force-quit and relaunch**, then
   open the League tab (a tab switch never remounts the screen; only a cold start
   reproduces the mount race).
2. When the Analyst bubble appears ("Filter one position…"): **expected** — ring + scrim
   cutout sit exactly on the position pills; the expanded playoff odds section is dimmed
   by scrim only, **no hole punched through it**.
3. While the bubble is up, collapse the outlook strip. Expected: pills shift up, ring +
   band follow immediately.
4. Re-expand while the tour is open. Expected: ring + band follow back down; if the pills
   drop below the fold, ring-offscreen-with-bubble-staying is the accepted degrade — never
   a ring parked mid-section.
5. Re-arm, **minimize** the projection, force-quit + relaunch to the League tab. Expected:
   ring + band on the pills exactly as before (#391 control — no regression).
6. With the bubble up, scroll the page. Expected: ring tracks the pills (existing
   behavior, must not regress).
7. If the device has the ram mascot experiment: repeat 1–4 once — identical expectations.
