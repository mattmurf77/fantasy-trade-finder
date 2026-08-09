# #265 — Mutual-match member threshold off by one on League home

**Status:** built · 2026-08-08 · branch `worktree-agent-a5c5a806d0d32845e`

## Report

Operator: "Only one additional league member should be needed to get
mutual matches (league home for Newton says two more needed)."

## Root cause

`LeagueProgressModule`'s unlock sentence ("`X more ranked leaguemates
unlocks mutual matches`") was driven by `MATCH_UNLOCK_MATES = 2` in
`mobile/src/components/LeagueProgressModule.tsx`. That constant was
**mock-anchored, not backend-anchored** — per the #229 status doc
(`docs/feedback/items/229-empty-states-progress/status.md`), it was
deliberately set to 2 so it would equal the *unrelated*
`/api/league/contrarian` leaderboard threshold (you + 2 ranked = 3 ranked
members total).

The actual mutual-match generation logic doesn't need 2 other ranked
members — it needs one. `backend/trade_service.py`'s `generate_trades`
builds its opponent pool as:

```python
eligible = [
    m for m in league.members
    if m.user_id != user_id and m.elo_ratings
]
```

A single opponent with stored rankings (`elo_ratings` truthy) is eligible,
and `_generate_for_pair` runs per opponent independently — trade cards
(and therefore `matches_mutual` counts, surfaced via `/api/league/summary`)
can be produced from just one ranked leaguemate. The League-home copy was
requiring a threshold from a different feature (leaderboards/contrarian
ranks) before telling the user mutual matches were reachable.

`rankedMates` (passed into the component as `coverage.ranked`, from
`backend/database.py get_ranking_coverage`) already correctly excludes the
viewing user — so this was purely a wrong threshold constant, not a
miscounted base.

## Fix

- `mobile/src/utils/leagueUnlocks.ts` (new): pure module exporting
  `MATCH_UNLOCK_MATES = 1` and `matchesUnlockRemaining(rankedMates)`.
  Extracted out of the component (rather than just changing the constant
  inline) so the boundary math is unit-testable under plain node, matching
  the existing `utils/feedbackBadge.ts` / `utils/sessionRerank.ts` idiom.
- `mobile/src/components/LeagueProgressModule.tsx`: imports
  `matchesUnlockRemaining` instead of computing `remaining` inline against
  the local constant; comment block corrected to point at the new module
  and explicitly warn against re-conflating the mutual-match threshold with
  the contrarian/leaderboards one (root cause of this bug).
- Singular/plural copy (`remaining === 1 ? '' : 's'`) was already correct
  and untouched — with the corrected threshold it now reads "**1** more
  ranked leaguemate unlocks mutual matches" at the boundary instead of "2
  more ranked leaguemate**s**".
- The populated state (`remaining === 0` → unlock sentence hidden
  entirely) is untouched; only the threshold that feeds it changed.

## Test

`mobile/tests/check-league-unlocks.js` (new, `npm run test:league-unlocks`)
transpiles and runs the real `leagueUnlocks.ts` module under plain node,
pinning:
- `MATCH_UNLOCK_MATES === 1`
- user alone (0 ranked leaguemates) → `matchesUnlockRemaining(0) === 1`
  ("1 more ranked leaguemate" needed)
- user + 1 ranked leaguemate → `matchesUnlockRemaining(1) === 0` (matches
  available; `LeagueProgressModule`'s `remaining > 0` guard hides the
  sentence)
- above threshold stays clamped at 0, never negative

## Scope check

Grepped `web/` and `extension/` for the same unlock copy — the web client's
only "N more ranked leaguemates" string
(`web/js/app.js:5732`, contrarian leaderboard empty state) is correctly
tied to the real 3-ranked-members `/api/league/contrarian` threshold and is
untouched. This bug was mobile-only.

## Verification

- `python3 -m pytest backend/tests -q` → **2041 passed, 1 skipped**
  (matches baseline; backend untouched).
- `cd mobile && npx tsc --noEmit` → clean (via the standard node_modules
  symlink from `.claude/worktrees/agent-a16b8c9e20f110454/mobile/`, removed
  after).
- `node mobile/tests/check-league-unlocks.js` → all 4 checks pass.
- Re-ran the existing mobile structural checks
  (`check-feedback-badge.js`, `check-session-rerank.js`,
  `check-mock-mode-marker.js`, `check-member-entered-marker.js`,
  `check-espn-cookies.js`) — all still pass (no regressions from the
  import change).

## Gates

Express-track bug fix (single off-by-one threshold constant, no schema/API/
flag-surface/analytics-event change) — full scope-block/Maestro-delta
process not invoked; sim gate not required for this change class. Backend
and mobile automated gates both green (above).
