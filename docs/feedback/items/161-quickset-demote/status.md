# FB-161 — unselected players drop on Quick Set save

- **Type:** behavior fix · **Status:** built 2026-07-25 (branch `teardown-remediation` worktree)
- **Screen:** QuickSetTiersScreen · **Backend:** `/api/tiers/save` + `RankingService.apply_tiers`
- **Sibling:** FB-159 (empty-save-as-skip CTA) — its PRD explicitly carves this out; the two rules compose: **skip ≠ demote, only explicit saves demote.**

## Semantics decision (documented rule)

When a Quick Set tier is **explicitly saved** (≥1 player selected), every
player who was **visible in that step's grid** and **unselected**, whose
current tier is **the saved tier or a higher one**, is demoted to
**unranked/pending** — pinned below every band — NOT to an arbitrarily deeper
tier. Rationale: an explicit save is the statement "these are my ⟨tier⟩
players"; anyone passed over must not silently keep a stale ≥⟨tier⟩ label
(the tester's Jameson Williams case). Boundary rules:

- **Skip never demotes.** Skipping a step (or saving with nothing picked —
  FB-159's empty-save-as-skip) sends no `demoted_pids`.
- **Clear-only saves never demote** (deselect-everything on a revisited tier
  restores the consensus suggestion, today's behavior).
- Players **claimed by an earlier tier this run** aren't in the grid → never
  demoted. Lower-tier players get their own steps later in the walk.
- A player deselected on a revisited tier during an explicit save is sent in
  BOTH `cleared_pids` (legacy bookkeeping) and `demoted_pids` — **demote
  wins** server-side (a bare clear would snap them back into the tier off
  their consensus seed, the reported bug in miniature). A tier assignment in
  the same save wins over a demotion.
- Demoted players can be re-placed at any later step/run; the demotion is an
  ordinary Elo override (`users.tier_overrides`), so every existing surface
  (Tiers board pool, anchors, trios) can rescue them.

## Mechanics

- Client (`QuickSetTiersScreen.onSave`): computes `demoted` =
  grid-visible ∧ unselected ∧ `tierForElo(elo) ∈ {saved tier or higher}`;
  sends it as the new optional `demoted_pids` field on `/api/tiers/save`
  (`saveTiers` in `mobile/src/api/rankings.ts`).
- Backend (`RankingService.apply_tiers`): pins each valid demoted pid to
  `DEMOTED_ELO = 1100.0` — below the waivers floor (1150) in every
  format/position cell, the same Elo the anchor wizard's "no value" answer
  uses — applied after clears, before tier writes (precedence above).
  TiersScreen and other `/api/tiers/save` callers never send the field →
  byte-identical behavior for them; old clients unaffected (field optional).

## Tests

`backend/tests/test_quickset_demote.py`:
- `test_demoted_pid_reads_unranked`
- `test_demotion_wins_over_clear_for_same_pid`
- `test_tier_assignment_wins_over_demotion_in_same_save`
- `test_unknown_pids_ignored`
- `test_no_demoted_pids_is_todays_behavior`

## Files

- `mobile/src/screens/QuickSetTiersScreen.tsx`, `mobile/src/api/rankings.ts`
- `backend/ranking_service.py` (`DEMOTED_ELO`, `apply_tiers`), `backend/server.py` (`/api/tiers/save`)
- `docs/api-reference.md` (contract)
