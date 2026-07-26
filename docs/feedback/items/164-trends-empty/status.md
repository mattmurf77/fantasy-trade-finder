# #164 — Trends screen empty despite rankings

**Status:** Built (this worktree, branch `teardown-remediation`).

**Tester report:** "Feel like I have enough rankings for this? But no
population."

## Root cause (confirmed, not the suspected format bug)

The Risers/Fallers sections of Trends read from the `elo_history` table via
`GET /api/trends/risers-fallers` → `load_elo_history()`. That table had
**exactly one writer**: the trio-swipe route (`/api/rank3`,
`backend/server.py` ~line 2917).

Every other ranking flow mutates the user's board WITHOUT writing history:
- `/api/tiers/save` — Quick Set / Tiers (Quick Set is the DEFAULT ranking
  flow since #122, so this is the common path)
- `/api/rankings/reorder` — Quick Rank + manual board
- `/api/anchor/save` — Pick Anchor wizard

A user who ranked exclusively through those flows (i.e. most users under the
current default) had `has_history: false` forever → the mobile screen showed
"Keep ranking to see trends here." no matter how much they ranked. Exactly
the tester's experience.

Ruled out: format scoping (`load_elo_history` filters by the same
`_active_format` the write uses; snapshots carry the format they were written
under) and threshold logic (`has_history` is simply `bool(rows)` — there were
zero rows to threshold).

The third Trends section (consensus gap) has its own leaguemate-baseline
requirement (`has_baseline`, ≥ leaguemate rankings) with honest copy already —
unchanged.

## Fix

**Backend** (`backend/server.py`): new best-effort helper
`_record_trends_snapshot(service, user_id, league, fmt, changed_pids)` —
mirrors the rank3 snapshot block (write only the players the submission
changed; failures log-and-continue, never block the save). Called from:
- `save_tiers_route` — assigned pids **+ `cleared_pids`** (a clear reverts the
  player's ELO; that movement belongs in history too)
- `save_anchor_route` — the anchored `player_id`
- `reorder_rankings` — `ordered_ids`

**Mobile** (`mobile/src/screens/TrendsScreen.tsx`): the no-history empty state
now says what the data needs instead of a bare nudge:
"No ranking history yet — it records each time you rank or adjust players, in
any flow. Movement shows here across a 30-day window." (Users whose history
starts today legitimately see "No risers in this window" until something
moves — that copy is accurate and unchanged.)

Note: existing rows written by trio swipes are untouched; history for
quickset-only users starts accruing from their first save after this deploys
(no backfill is possible — the old values were never recorded).

## Tests (`backend/tests/test_trends_history_writers.py`, 6 new)

- `test_tiers_save_writes_elo_history` — rows for every assigned pid with
  user/league/format stamped
- `test_tiers_save_records_cleared_pids` — cleared player lands in history
- `test_reorder_writes_elo_history`
- `test_anchor_save_writes_elo_history` — snapshot carries the POST-anchor ELO
- `test_trends_populates_for_quickset_only_user` — end-to-end regression for
  the tester report: tiers/save → later ELO move → `/api/trends/risers-fallers`
  returns `has_history: true` + the player as a riser
- `test_snapshot_failure_never_blocks_save` — history write failure → 200

## Verification

- `python3 -m pytest backend/tests -q` → **1089 passed, 1 skipped** (baseline
  1083 + 6 new).
- `cd mobile && npx tsc --noEmit` — clean.

## Files

- `backend/server.py` (helper + 3 call sites)
- `backend/tests/test_trends_history_writers.py` (new)
- `mobile/src/screens/TrendsScreen.tsx` (empty-state copy)
- `docs/api-reference.md` (risers-fallers row notes the new writers)
