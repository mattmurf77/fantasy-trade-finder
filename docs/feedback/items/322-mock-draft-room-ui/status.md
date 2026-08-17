# FB-322 — group canonical folder

- **Status:** built 2026-08-16 · **Phase:** 2 (build) — awaiting wave integration + operator TestFlight checklist (PRD §5.5)
- **Group:** G2 — Mock draft room UI (canonical: #322-#327)
- **Batch plan:** [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md)
- **Base:** `origin/main` @ `d3fe3ac` (v1.13.4); built on G3's completed build @ `08eb04b` per PRD §3 serialization (G3 first, G2 rebased on its regions)
- **Branch:** `feat/fb322-draftui`

## Build summary (2026-08-16)

All 16 PRD requirements landed:

- **#322/#325** — single fixed-height ascending ticker via pure `tickerWindow` (`mobile/src/utils/tickerWindow.ts`): defensive ascending sort, `slice(-8)`, `firstNewIndex` highlight boundary. R-4 consequence stands: manual mode always reads "Just picked" with no new-pick tint (`sinceUserPick` untouched by design).
- **#323** — additive `picks[].tier` from `state_payload()` via `RankingService.tier_for_elo` (consensus-always, basis-independent, null ⇒ no badge); `MockPick` typed (`tier`, `consensus_rank`, `consensus_delta`, `valued`); chips render position + `TierBadge`, never client-derived.
- **#324** — 3-per-row equal-width `flexBasis` chip grid; wrap, no nested scrollable anywhere (one ScrollView in the screen, pinned).
- **#326** — `MockTeamSheet` modal (`mobile/src/components/draft/MockTeamSheet.tsx`): Roster (shared power-rankings read, `is_you` team, grouped by position) + "Drafted in this mock" (position + tier); "Your team" ice link on the clock card; position filter row; both filter and search reset on `pick_no` advance.
- **#327** — pool search via pure `filterPool` (`mobile/src/utils/mockPool.ts`), search scoped to the filter subset; `keyboardShouldPersistTaps="handled"`.
- **Analytics (R-15, operator-approved):** `mock_team_sheet_opened` / `mock_pool_filtered` / `mock_pool_searched` registered in `backend/analytics_taxonomy.py` (names + props maps) in the same change as the emitters.

## Verification (D-056 — no Maestro/simulator)

- Backend: `test_mock_draft.py` (122, incl. new T-P1..T-P4) + G3's `test_mock_pick_ownership.py` + `test_analytics_p0.py` — **162 passed**. Each T-P sabotage proven red → reverted → green.
- Mobile: new `mobile/tests/check-mock-g2-ui.js` (76 checks: T-U1/T-U2 transpile-and-call + T-S1..T-S10 structural) — all pass; **14 named sabotages proven red → green**. Four existing mock suites + G3's `check-mock-ownership-caption.js` green; `testid-lint.sh` OK; `tsc --noEmit` clean.
- Runtime proof: operator TestFlight checklist T-F1..T-F10 (PRD §5.5) — pending, at ship.

One PRD deviation, recorded: R-10's "grouping keys on the caller's league identity via `myOwnerId`" is implemented as the power-rankings payload's own `is_you` row — the server's rendering of the same ADR-012 league identity, and the standing consumer convention for this exact payload (LeagueSummaryScreen); `myOwnerId` would have required an extra league-rosters read the sheet doesn't need.

## Reported

> The just picked order section should be shown the other way.. 1.01 at the top and descending from there. [Operator: #322+#325 are ONE section — fixed height, earliest at top, earliest scroll off as picks land.]
