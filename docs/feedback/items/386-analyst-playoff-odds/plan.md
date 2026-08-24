# #386 / #391 — Analyst pop-up broken while the playoff odds section is expanded

**Date:** 2026-08-24 · **Group:** D (planner) · **Items:** #386 (bug, v1.16.2), #391 (bug, v1.16.2) — lowest ID owns the folder
**Screen (FAB route):** `LeagueRankings` = `mobile/src/screens/LeagueSummaryScreen.tsx` (League tab root; `mobile/src/navigation/TabNav.tsx:509`)

## 1. The surface, exactly

- **Analyst pop-up** = the `AnalystGuide` overlay (`mobile/src/components/AnalystGuide.tsx`), mounted once in `RootNav`. The only tour beat on this screen is **n5** (`mobile/src/components/analystScript.ts:346-354`): `screen: 'LeagueRankings'`, `target: 'league-summary.pos-pills'`, pose `point`, advance `action`. Live today: `onboarding.v2`, `onboarding.guided_avatar`, and `onboarding.guide_v2` are all `true` in `config/features.json`, so the v2 engine path is the shipping path.
- **Target** = the position-filter pills, registered at `LeagueSummaryScreen.tsx:961` (`registerGuideTarget('league-summary.pos-pills', posPillsRef)`) and rendered inside the chart card at `LeagueSummaryScreen.tsx:1671-1679`.
- **Playoff odds / projection section** = the #169 season-outlook layer (flag `outlook.odds`, LIT 2026-08-19, D-094), mounted at `LeagueSummaryScreen.tsx:1566-1572` — **above** the chart card that holds the pos-pills. `OutlookStripAndSection` (`:2823-2871`) renders the one-line strip always, plus `SeasonOutlookSection` (a full seed-ordered standings list, several hundred pt tall) **only while `expanded`**. Expanded state is per-user/per-league, hydrated asynchronously from AsyncStorage (`mobile/src/state/outlookStrip.ts:36-64`), and toggled by tapping the strip (`:2849-2857`).

## 2. How the bubble/ring position is computed (file:line trace)

1. When beat n5 activates, the target is measured **once** via `measureGuideTarget` (`mobile/src/state/guideTargets.ts:19-40`) — `measureInWindow`, i.e. **absolute window coordinates**. Under `guide_v2` the engine owns that measurement and the overlay reads `spotlightFrame` (`AnalystGuide.tsx:100-107,163`).
2. The overlay re-measures **only** when a host announces movement: `subscribeGuideTargetsMoved` → `remeasure` (`AnalystGuide.tsx:165-209`), plus the two keyboard events. Hosts announce via `notifyGuideTargetsMoved()` (`guideTargets.ts:58-60`).
3. `LeagueSummaryScreen` announces from exactly one place: `onScroll` on its page ScrollView (`LeagueSummaryScreen.tsx:1497`). **Nothing announces on a layout change.**
4. The ring (`cutout`, `AnalystGuide.tsx:342-355`) and scrim are drawn at the cached frame; the avatar+bubble band is placed **adjacent to that cutout** by `solveBandPlacement` (`AnalystGuide.tsx:70-90`), side latched per step, offset live (`:357-385`).

## 3. Root cause

**The outlook section changes the page's layout without a scroll, and this screen only notifies the guide on scroll.** Three concrete triggers, all the same class:

- **Hydration:** the strip's expanded state arrives from AsyncStorage a tick after mount (`outlookStrip.ts:36-64`); for a user who left the projection expanded (the operator did), `SeasonOutlookSection` mounts after first paint.
- **Query resolution:** `OutlookStripAndSection` swaps the loading shell for strip + section when `GET /api/league/outlook` resolves (`LeagueSummaryScreen.tsx:2834-2870`) — while expanded, that mounts the full standings list.
- **Manual toggle:** tapping the strip mid-beat mounts/unmounts the section (`:2849-2857`); the scrim wrapper is `pointerEvents="none"` (`AnalystGuide.tsx:395`), so the strip stays tappable while the bubble is up.

Each shifts everything below the outlook layer — including `league-summary.pos-pills` — down (or up) by the section's height. The cached window frame is now stale; no `notifyGuideTargetsMoved` fires; the ring, scrim cutout, and adjacent band all render at the **pre-shift** y.

This also explains "**playoff odds section broken**" (#386) without any render error: with the section expanded, the stale cutout hole + ice ring sit where the pos-pills *used to be* — i.e. punched across the middle of the expanded playoff odds section, with the rest of it dimmed by scrim. The section itself isn't crashing; it's wearing the misplaced spotlight. And #391 is the control case: **minimized**, the strip and loading shell are the same one-line height, layout matches the measurement, so the box lands correctly. No build-agent instrumentation needed unless TestFlight QA contradicts this reading; if it does, the thing to instrument is the measured frame vs. actual pos-pills y at beat-show time (log `guide_step_shown.spotlight` alongside a fresh `measureGuideTarget` result).

This exact defect class was already found and fixed on the calculator — #384 device report 1: "scroll is not the only way a target moves." `TradeCalculatorScreen.tsx:670-676` wires `onLayout` **and** `onContentSizeChange` to `notifyGuideTargetsMoved` on its page ScrollView. `LeagueSummaryScreen` never received the same treatment.

## 4. Fix

**Chosen (smallest, precedented):** add the two announcement props to `LeagueSummaryScreen`'s page ScrollView (`:1491-1498`), mirroring `TradeCalculatorScreen.tsx:675-676`:

```
onLayout={notifyGuideTargetsMoved}
onContentSizeChange={notifyGuideTargetsMoved}
```

Two lines plus a short comment citing #386. Covers all three triggers (hydration, query resolution, manual toggle) because each changes the ScrollView's content size. Cost when no tour is active: `notifyGuideTargetsMoved` walks an empty listener set (`guideTargets.ts:44-60`) — a no-op. Works identically for both mascots: the fix is in measurement notification, upstream of the `AnalystAvatar` switch (`onboarding.mascot_ram`).

**Alternatives considered:**
- `onLayout` on the outlook layer only (wrap `:1566-1572` in a View): narrower, but misses every *other* async grower on this page (chart data landing, draft-capital section, drill-in) and adds a wrapper node. Rejected — the ScrollView props are strictly broader at the same cost.
- Re-measure on an interval / on every frame inside `AnalystGuide`: touches shared overlay internals (Group B territory), adds ongoing cost for all screens. Rejected.
- Reset `scrolledForRef` so a large post-shift delta re-runs scroll-into-view (`AnalystGuide.tsx:122,223-249`): would improve the residual case where the expanded section pushes the pills below the fold, but it's overlay-internal, re-entrancy-sensitive (test rule 13 pins the once-per-step guard), and the B1 degrade posture (ring drops offscreen, bubble stays) is acceptable. Not needed for this fix; note for Group B if they're already in that file.

## 5. File ownership

| File | Change |
|---|---|
| `mobile/src/screens/LeagueSummaryScreen.tsx` | +2 props on the ScrollView (`:1491`) + comment |
| `mobile/tests/check-guide-spotlight-tracking.js` | Extend rule 12 (`:1138-1170`) from calculator-only to also assert `LeagueSummaryScreen`'s wired ScrollView carries `onLayout` + `onContentSizeChange` referencing the notifier |
| `docs/feedback/items/386-analyst-playoff-odds/` | this plan + status/QA output |
| `living-memory/TEST_LEDGER.md`, `living-memory/CHANGELOG.md` | at ship time |

**Group overlap:** none on source. This plan deliberately touches **no** shared analyst files — `AnalystGuide.tsx`, `state/useGuide.ts`, `state/guideTargets.ts`, `components/analyst/*` are read-only dependencies here; Group B may edit them freely. One coordination point: if Group B also edits `mobile/tests/check-guide-spotlight-tracking.js`, merge order matters — the rule-12 extension is additive and small, so rebase is trivial.

## 6. Evidence plan (D-056)

1. **Structural guard (sabotage-provable):** the rule-12 extension above. Sabotage: delete either prop from `LeagueSummaryScreen`'s ScrollView → red; delete from the calculator → still red (existing behavior preserved).
2. **Code-walk proof:** the §2-§4 trace, re-cited against the landed diff — specifically that the same ScrollView carrying `onScroll={notifyGuideTargetsMoved}` (`:1497`) now also announces from both layout callbacks, and that `AnalystGuide.tsx:165-209` re-measures on that notification and re-derives cutout + band placement (`:342-385`).
3. **Operator TestFlight checklist:**
   - Precondition: an account with beat n5 still armed (hasn't applied a league position filter; `maxDisplayCount: 2` not exhausted) in a Sleeper league with ≥3 ranked members.
   - a) With the playoff projection **expanded** (persisted from a prior visit), open League tab → wait for the Analyst bubble: the ring must sit on the position pills, the bubble adjacent to it, and the playoff odds section must look normal (dimmed by scrim only, no hole punched through it).
   - b) While the bubble is up, tap the "Season outlook" strip to collapse and re-expand: the ring must follow the pills each time.
   - c) Repeat (a) with the projection **minimized** — still correct (regression check for #391's good case).
   - d) Scroll the list while the bubble is up — ring tracks (existing behavior, must not regress).

## 7. Risks

- **Same latent class elsewhere:** `TradesScreen` registers six guide targets (`:3243-3248`) and announces on scroll only — its content also grows after first paint (cards stream in, banners mount). Out of scope for this fix (Group A/B surface, different repro), but the build agent should log it; extending test rule 12 to a host list makes adding it later mechanical.
- **Notification frequency:** `onContentSizeChange` fires on every content growth (drill-in open/close, chart load). Re-measure is rAF-coalesced in the overlay (`AnalystGuide.tsx:171-191`) and a no-op with no active step — no perf concern, matches the calculator's shipped behavior since 2026-08-22.
- **Residual:** if the expanded section pushes the pills fully below the fold *after* the step's one scroll-into-view already ran, the ring degrades offscreen (scrim dropped, bubble stays) per B1 — honest, not broken; the checklist's step (b) exercises it.
