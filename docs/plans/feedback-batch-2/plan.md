# Plan: Feedback Batch 2 (June 2026 TestFlight feedback)

**Thread slug:** `feedback-batch-2`
**Started:** 2026-06-08
**Trigger:** New in-app TestFlight feedback (ids #24, #26–#42) + recurring older items.

## Scope — 12 feedback ids → 7 features

| Feature | Feedback ids | Surface | Agent | Risk |
|---------|-------------|---------|-------|------|
| **FB-01** Matches disposition fix + logging | #35, #36 (←#8) | backend | A (subagent) | med — recurring bug |
| **FB-02** Tiers interaction overhaul (drag engine + multi-select) | #27, #29, #32 (←#14,#15,#16,#22) | mobile | B (subagent) | **high** |
| **FB-03** Ranks consolidation + nav affordance | #40, #28 (←#18) | mobile | C (subagent) | med |
| **FB-04** Trends as rank deltas | #31 | mobile + backend | D (subagent) | med |
| **FB-05** TradesHome ✓/✗ disposition buttons | #34 | mobile | E (subagent) | low |
| **FB-06** League team-count fix | #41 | mobile/backend | F (subagent) | low |
| **FB-07** Trios tile cleanup (remove rookies link + injury tags) | #26 (←#20), #33 | mobile | primary (self) | low |

Per-feature PRDs in [`prd/`](./prd/). Each = title, requirement, user story, acceptance criteria.

## Locked decisions (from user, 2026-06-08)

- **FB-02 multi-select move semantics:** selected players **collapse into a
  contiguous block** and move together toward the destination on each arrow tap
  (standard reorder). NOT shift-each-independently.
- **FB-02 multi-select trigger:** **remove the long-press**; multi-select is
  entered ONLY via the "Select" button; selected tiles get a **lighter-blue
  full-tile fill**; up/down arrows move the (collapsed) selection.
- **FB-02 drag feel:** **adopt the ManualRanks drag engine** (the
  `react-native-draggable-flatlist` mechanism) in Tiers so the "make room"
  animation matches ManualRanks exactly. Must preserve cross-tier moves + the
  PR #60 screen-Y drop-coordinate fix.
- **FB-03:** **remove OverallRanks** entirely; **rename ManualRanks →
  "Overall Ranks"** (the editable drag screen survives under that name).
- **FB-01:** **investigate from code + add structured logging**; harden the
  disposition route; ship logging so the next repro captures the real error.

## Investigation seed (FB-01)

`disposition_trade_match` (`backend/server.py:3374`) reads `sess["service"]`,
`sess["league"]`, `sess["players"]` unconditionally and applies ELO to the
**active-league** service even for **cross-league** matches. Likely failure
points: (a) a match accepted while the active session is a different league →
the match's players aren't in `sess["service"]`/`g_players` pool →
`record_disposition_signal` mis-applies or raises; (b) `record_match_disposition`
(`backend/database.py`) error path. Mobile surfaces ANY non-2xx as
"Action failed". Fix = wrap the handler so the real exception+traceback is
logged, null-guard the session reads, and resolve the correct league/service
for the match's own league_id.

## Orchestration

- Each subagent runs in **worktree isolation** (own branch), so even shared
  files (server.py touched by FB-01 + possibly FB-04) merge cleanly. Primary
  owns review + one PR per feature + sequential merge + final regression.
- **File-ownership guardrails** (avoid clobber even with isolation):
  - FB-02 owns `mobile/src/screens/TiersScreen.tsx` (+ may add a shared drag
    component). READS `ManualRanksScreen.tsx`; does NOT edit it or `PlayerCard.tsx`.
  - FB-03 owns nav (`TabNav.tsx`, `RootNav.tsx`), deletes `OverallRanksScreen.tsx`,
    renames labels in `ManualRanksScreen.tsx`. Does NOT touch TiersScreen.
  - FB-04 owns `TrendsScreen.tsx` + `trends_service.py` (+ trends route if
    needed). FB-01 owns the disposition route in `server.py` + `database.py`.
    Different server.py regions — isolation handles the merge.
  - FB-05 owns `TradesScreen.tsx`. FB-06 owns the league team-count source
    (`LeagueScreen.tsx` and/or the league-summary backend).
  - FB-07 (primary): `RankScreen.tsx` + `PlayerCard.tsx` (injury prop).
- **Invariants:** anything touching ELO math / tier bands / per-format
  independence → byte-for-byte safe (FB-01 only adjusts WHERE signals apply, not
  the math). FB-02 must preserve the PR #60 coord fix + cross-tier drops.

## Verification (per feature + final)
- Mobile: `cd mobile && npx tsc --noEmit`.
- Backend: `python3 -m pytest backend/tests/ -q` (currently 41 passing) + add
  targeted tests for FB-01 (disposition) and FB-04 (rank-delta) where feasible.
- One PR per feature; review each diff before merge; squash-merge to main via gh.

## HLD/LLD impact
- Screen inventory changes (remove OverallRanks; rename ManualRanks) → update
  `living-memory/LLD.md` screen list + `mobile/src/screens/CLAUDE.md`.
- Tiers adopting the shared drag engine → note in `living-memory/LLD.md`.

## Linked
- Feedback source: backend `app_feedback` table (`GET /api/feedback/admin`).
- Prior feedback wave: PRs #48–#60. Perf waves: #66 (W1), #67–#73 (W2).
