# FB-397 + FB-398 — swipe tour step placement (Group B canonical)
- **Status:** built 2026-08-24 — awaiting QA/merge; operator TestFlight checklist pending (prd.md §6c)
- **Covered:** #397 (superseded), #398 (operative: top of screen, above the trade chip section)
- **Path:** fast-track bug, full gates
- **Docs:** [plan.md](plan.md) (planner investigation) · [prd.md](prd.md) (mini-PRD + D-056 test plan) · [reconciliation-log.md](reconciliation-log.md) (Round-3 resolutions are contract)
- **Branch:** `feat/fb397-swipe-tour-mobile` (based on ec6edd97, the wave's Phase-1 spec commit)
- Batch plan: [346-quickset-tier-drop/plan.md](../346-quickset-tier-drop/plan.md)

The Fleeced swipe right/left onboarding beat (s2.2) band-flipped mid-screen /
bottom-band because its ring is the whole deck card; the fix is an opt-in
per-step pin that anchors the avatar band to the top of the window. In plain
terms: the bubble now always sits at the top of the screen for this one step,
and every other step places exactly as before.

## Build report

### Files touched (all owned per prd.md §5)

| File | Change | R |
|---|---|---|
| `mobile/src/state/useGuide.ts` | `GuideStep` gains optional `band?: 'top'` (:99–101) | R-1 |
| `mobile/src/components/AnalystGuide.tsx` | `solveBandPlacement` gains 5th param `pin?: 'top'` (:75); pin branch before every other branch incl. the null-cutout early return (:82); call site forwards `active.band` (:370) | R-2, R-4 |
| `mobile/src/components/analystScript.ts` | `s2_2` builder declares `band: 'top'` (:127); no other step declares it | R-5 |
| `mobile/tests/check-guide-spotlight-tracking.js` | rule-11 block only: executable 11n/11o after the 11i/11j sweep (:1099–1120), structural 11p/11q after 11m (:1160–1215). Rule 12's block (calculator movement, Group D) is byte-untouched | §6a |
| `mobile/src/components/CLAUDE.md` | `AnalystGuide` row (:70): quoted signature amended to `solveBandPlacement(cutout, bandH, winH, insets, pin?)` + the per-step pin clause | R-8 |

### Verification evidence (D-056, static only)

- `npm ci` fresh in `mobile/` (no symlinked node_modules).
- `npx tsc --noEmit` — clean.
- `node tests/check-guide-spotlight-tracking.js` — all checks pass, including
  the unchanged 4-arg cases 11d–11h and the 11i/11j invariant sweep (R-3's
  mechanical proxy) and the new 11n/11o/11p/11q.
- `bash scripts/testid-lint.sh` — OK (no testID changes).

**Sabotage proofs (prd.md §6a) — each applied, run RED, reverted, run green:**

1. **Drop the 5th param + branch** (full R-2 revert) → RED `11n` and `11o`,
   both with `{"from":"bottom","offset":92}` — the lifted function ignored the
   extra arg and answered bottom-band. *Self-satisfaction:* with real code in
   place, 11f (the 4-arg twin of 11n's input) still answers bottom — 11n
   passes because of the pin, not a solver-default change.
2. **Accept the param, never branch on it** → RED `11n`/`11o`, same evidence;
   all 4-arg cases stayed green — 11f green + 11n green can only coexist if
   the branch is real.
3. **Unconditional pin** (always return top) → RED `11d`, `11e`, `11f`
   (`{"from":"top","offset":67}`), `11g`, `11h`, and the `11i` overlap sweep
   (first overlap `{"c":{"top":-40,"height":120},"bandH":80,"p":{"from":"top","offset":67}}`);
   `11j` correctly stayed green (67 ≮ 67, exactly as the PRD predicted) —
   proving the sweep genuinely exercises the 4-arg path.
4. **Remove `band: 'top'` from s2_2** → RED `11p` ("no `band` property on the
   s2_2 builder's returned object literal"). *Self-satisfaction:* with
   `band: 'top'` temporarily moved to the `s2_1` builder instead, `11p`
   stayed RED — the assertion binds to s2_2's own AST node.
5. **Revert the call site to 4 args** → RED `11q` ("call args:
   `solveBandPlacement(cutout, bandH, winH, insets)`"). *Self-satisfaction:*
   with a decoy `active.band` expression planted elsewhere in the file and
   the call still 4-arg, `11q` stayed RED — it walks the CallExpression's
   own arguments, not file text.

### PRD deviations

None in the contract. One note: the worktree was cut at `cce3895f` (main tip,
which lacks ec6edd97); the branch was re-based onto `ec6edd97` before building
so the signed-off Phase-1 specs are the actual base. `cce3895f` is a
docs-only recovery-ledger commit not present on this branch; no code overlap.

## Code-walk proof (prd.md §6b, cited against the landed diff)

1. **Request.** s2.1 advances → the chain effect requests s2.2
   (`mobile/src/screens/TradesScreen.tsx:3312–3318`, first-run-gated at
   :3316, READ-ONLY this wave). `requestStep` activates the step built by
   `s2_2` (`analystScript.ts:124–129`), which now carries `band: 'top'`
   (:127) — typed by `GuideStep.band?: 'top'` (`useGuide.ts:99–101`).
2. **Measure.** guide_v2 resolves the measured frame for `trades.card-body`
   (registration `TradesScreen.tsx:3243`, unchanged).
3. **Solve.** The overlay's single solver call passes the step's pin:
   `solveBandPlacement(cutout, bandH, winH, insets, active.band)`
   (`AnalystGuide.tsx:370`). Inside the solver the pin branch is FIRST
   (:82): `if (pin === 'top') return { from: 'top', offset: insets.top + BAND_EDGE };`
   — before the null-cutout / unmeasured-band early return (:85), so a
   degraded or not-yet-measured s2.2 still pins (guard 11o executes exactly
   this). With `pin` undefined, lines 84–97 are the pre-change adjacency
   body verbatim (guard 11d–11j execute it).
4. **Latch.** The latch (`AnalystGuide.tsx:377–387`) stores the solved
   placement per step; with a constant solved value the side-latch merge
   (:386–387) degenerates to a no-op — untouched code, W7/W8 fixes intact
   (entry spring keyed on band render :305–321, scroll-into-view :230–256,
   `bandPending` :392).
5. **Render.** `atTop` is true (`from: 'top'`), so the band renders
   `{ top: place.offset }` (`AnalystGuide.tsx:442`) — top of the window,
   above the mode chip strip; ring stays on the card; nothing new captures
   touches (the band subtree is unchanged, so the draggable deck keeps its
   gestures).
6. **Clearance.** Scroll-into-view already reserves
   `insets.top + BAND_EDGE + bandH + BAND_GAP` of headroom
   (`AnalystGuide.tsx:238, 247`) — exactly the pinned band's span, measured
   `bandH` included, so both mascot sprites self-adjust (R-7); zero new code.
7. **Advance.** First real swipe calls `advanceGuideIfActive('s2.2')`
   (`TradesScreen.tsx:~4335`), unchanged.

## Coordination (standing)

- `TradesScreen.tsx` READ-ONLY (Group A owns it this wave) — honored; not in the diff.
- `check-guide-spotlight-tracking.js` also extended by Group D in rule 12's
  block (header now at :1216 after our rule-11 insertions; content
  byte-identical). Case IDs 11n–11q claimed by this group.
