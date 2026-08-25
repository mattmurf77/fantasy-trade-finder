# FB-386 + FB-391 — analyst pop-up / playoff odds broken (Group D canonical)
- **Status:** built 2026-08-24 — awaiting QA + operator TestFlight checklist ([prd.md](prd.md) §5c)
- **Covered:** #386 (bug), #391 (context: analyst box positions correctly when playoff projection is minimized)
- **Path:** fast-track bug, full gates
- Batch plan: [346-quickset-tier-drop/plan.md](../346-quickset-tier-drop/plan.md)
- Plan (root cause + fix choice): [plan.md](plan.md)
- PRD (fix contract R-1…R-6 + D-056 test plan): [prd.md](prd.md)
- Scope block: [scope.md](scope.md)

On LeagueRankings (1.16.2) the analyst pop-up renders broken when the playoff
odds section is expanded; correct when minimized (#391). Note `outlook.odds`
was lit 2026-08-19 (D-094) — this surface is young.

---

## Build report (Group D build agent, 2026-08-24)

**Branch:** `feat/fb386-guide-layout-notify-mobile`, cut from `8576910e`
("merge Group B build: s2.2 band pinned to top (#397/#398)") on
`claude/new-user-feedback-55320e`.

**Diff (3 files, source diff is the screen only — R-4):**

| File | Change |
|---|---|
| `mobile/src/screens/LeagueSummaryScreen.tsx` | +8 lines on the page ScrollView (now `:1491-1506`): `onLayout={notifyGuideTargetsMoved}` + `onContentSizeChange={notifyGuideTargetsMoved}` (`:1504-1505`) with the #386 constraint comment (`:1498-1503`). Existing `onScroll` (`:1497`) and `scrollEventThrottle={16}` (`:1506`) untouched (R-5) |
| `mobile/tests/check-guide-spotlight-tracking.js` | Rule 12 (`:1226-1263`) extended from the hardcoded calculator to `GROWING_HOSTS_REL = [TradeCalculatorScreen.tsx, LeagueSummaryScreen.tsx]`; 12a/12b messages parameterized per host (`12a — ${rel}'s page ScrollView…`, detail prefixed with the host path). Rule 11's block untouched — Group B's 11n/11o/11p/11q byte-identical and green |
| `mobile/src/screens/CLAUDE.md` | One clause appended to the `LeagueSummaryScreen` row: the ScrollView announces from `onScroll` **and** `onLayout`/`onContentSizeChange`, props pinned by rule 12 — so the next editor doesn't strip them as unused |

**Gates (all on the committed tree):**
- `npm ci` clean; `npx tsc --noEmit` clean.
- `node tests/check-guide-spotlight-tracking.js` → 92 PASS / 0 FAIL, exit 0 —
  including Group B's `11n`/`11o`/`11p`/`11q` and the four new rule-12 lines
  (`12b — src/screens/{TradeCalculatorScreen.tsx:663,LeagueSummaryScreen.tsx:1491}
  also announces from {onLayout,onContentSizeChange}`).
- `bash scripts/testid-lint.sh` → `testid-lint OK`.

**Sabotage evidence (PRD §5a; each performed on the working tree, then
reverted via `git checkout --`; guard exit code shown):**

1. **(a) delete `onContentSizeChange` from LeagueSummaryScreen** → exit 1, one FAIL:
   `FAIL  12b — src/screens/LeagueSummaryScreen.tsx:1491 also announces from onContentSizeChange: src/screens/LeagueSummaryScreen.tsx: content that grows under a settled scroll offset moves every target below it and fires no scroll event`
   → revert → exit 0.
2. **(b) delete `onLayout`** → exit 1, symmetric FAIL (`…also announces from onLayout: …`) → revert (held for c).
3. **(c) not-self-satisfying proof — additionally delete `onScroll`** → exit 1 via the loud 12a branch, host named:
   `FAIL  12a — src/screens/LeagueSummaryScreen.tsx's page ScrollView announces movement: no wired onScroll found`
   (plus rule 9's independent `FAIL 9b — src/screens/LeagueSummaryScreen.tsx calls the notifier from an onScroll handler`, as the critic predicted in O-4). A host dropped from parsing cannot green the suite. → full revert → exit 0.
4. **(d) symmetric calculator check — delete `onContentSizeChange` from TradeCalculatorScreen** → exit 1:
   `FAIL  12b — src/screens/TradeCalculatorScreen.tsx:663 also announces from onContentSizeChange: src/screens/TradeCalculatorScreen.tsx: content that grows under a settled scroll offset moves every target below it and fires no scroll event`
   → revert → exit 0. Existing coverage preserved (R-5/R-6).

Assertions run against the real files by relative path (`parse(rel)` from the
suite's `ROOT = mobile/`), never fixtures — the sabotage edits were made to
the shipped source itself.

**Contract check:** R-2 — no guide-state read added; `git diff` shows no new
import (the `notifyGuideTargetsMoved` import pre-exists at `:51`) and the
props are unconditional. R-3 — `git grep mascot_ram` on the screen: 0 hits.
R-4 — `git diff --name-only 8576910e..HEAD` = exactly the three files above;
no `AnalystGuide.tsx`, `useGuide.ts`, `guideTargets.ts`, `components/analyst/`.

## Code-walk proof (PRD §5b, cited against the landed diff)

1. **Activation + first measure.** Beat n5 (`analystScript.ts:348-353` — id/target
   `league-summary.pos-pills`, screen `LeagueRankings`, `retireAfter` at `:353`)
   activates; the engine measures the target via `measureGuideTarget`
   (`guideTargets.ts:19-40`): `measureInWindow` → **absolute window coordinates**,
   250 ms timeout → null (`:28`). The overlay holds the resolved frame
   (`AnalystGuide.tsx:170` — `frame = guideV2 ? engineFrame : localFrame`).
2. **The shift, now announced.** The outlook layer renders inside the page
   ScrollView (`LeagueSummaryScreen.tsx:1574-1580`); `OutlookStripAndSection`
   changes its rendered height on AsyncStorage hydration (`state/outlookStrip.ts`
   `useOutlookStripExpanded`, once per mount keyed on userId), on outlook-query
   resolution (`:2840-2849` — loading shell → strip/section swap), and on the
   manual strip toggle (`:2856-2865` — `onToggle` flips `expanded`). Each
   changes the ScrollView's layout or content size, so RN fires the **new**
   props `onLayout={notifyGuideTargetsMoved}` / `onContentSizeChange={notifyGuideTargetsMoved}`
   (`:1504-1505`, this diff) — the same seam the existing `onScroll` uses (`:1497`).
3. **Re-measure → cutout → band.** `notifyGuideTargetsMoved` walks the listener
   set (`guideTargets.ts:58-60`); the overlay subscribed `remeasure` from its
   tracking effect (`AnalystGuide.tsx:172-199`, subscribe at `:199`), which
   coalesces to one `measureGuideTarget` per animation frame with a pending
   flag so a one-shot shift is never dropped (`:178-198`). The fresh frame
   re-derives the cutout (`:349`) and the band follows via
   `solveBandPlacement(cutout, bandH, winH, insets, active.band)` (`:370`,
   solver at `:70-90`). The ring lands on the pills' post-shift position — no
   hole punched through the expanded odds section.
4. **No-op with no tour (R-2).** With no overlay mounted nothing has subscribed:
   `notifyGuideTargetsMoved` iterates an **empty Set** (`guideTargets.ts:51-60`,
   comment at `:44-48` pins this posture) — no measurement, no guide-state
   read on the screen. The diff adds no conditional and no new import.
5. **Mascot-independent (R-3).** The change is upstream of the avatar renderer:
   nothing in the diff or the notification path reads `onboarding.mascot_ram`;
   the re-measure feeds the frame store, identical for The Analyst and the ram.

**Handed to the operator:** TestFlight checklist prd.md §5c (7 steps, cold-start
repro, feasibility probe for the receipt-retired case, fresh-account fallback).
