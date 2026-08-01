# #222 — "First round picks should not be listed in free agents section" — status

**Status: fixed (backend)** · 2026-08-01 · branch `teardown-remediation`
worktree

## Operator report

> "First round picks should not be listed in free agents section"

Filed 2026-08-01T06:25Z from `FreeAgents` (v1.11.0, iOS).

## Root cause — generic pool picks masquerade as positional players

The FA pool is the active format's universal pool minus every rostered
player, filtered to `FA_POSITIONS = ("QB","RB","WR","TE")` — a filter whose
comment claimed "PICK pseudo-players … are never free agents". That held
for OWNED-pick pseudo-players (position `"PICK"`, and they never enter the
universal pool anyway), but NOT for the pool's **generic picks**: to mix
draft capital into the trio ranking tabs, `build_universal_pool` assigns
them a REAL position per round (`_PICK_POS = {1:"RB", 2:"WR", 3:"TE",
4:"QB"}`) with `team = "PICK"`. Generic picks are never rostered, so
"Early/Mid/Late 1st Round Pick" (seed Elo 1720/1650/1580 — top-RB money)
surfaced at the top of the RB free-agent list in every league. (The
`_inject_owned_picks` suggestion-engine injection was investigated and is
NOT the leak path: injected owned picks live in the per-session trade
service and job dicts, not in the `_get_universal_pool` list the FA route
reads, and their ids never reach `pool_players`.)

## Fix

- `backend/trade_service.py` — new shared `is_pick_asset(p)`: True for
  position `"PICK"` (owned-pick pseudo-players) OR team `"PICK"` (generic
  pool picks, any position). Also used by the #227 gate.
- `backend/free_agent_service.py` — `compute_free_agents` excludes pick
  assets from the ranked FA pool explicitly; `compute_drop_candidates`
  skips them too (belt-and-braces — pick ids can't appear in
  `user_roster`, but the claim sheet must never offer "drop a pick").

Response shape unchanged; rows that were never legitimate simply disappear.

## Files

- `backend/trade_service.py` — `is_pick_asset`
- `backend/free_agent_service.py` — exclusion in `compute_free_agents` +
  `compute_drop_candidates`, corrected header comment
- `backend/tests/test_free_agents.py` — regression test
- `docs/api-reference.md` — `/api/league/free-agents` row note

## Tests (`backend/tests/test_free_agents.py`)

- `test_generic_pool_picks_are_not_free_agents` — a league pool with
  synced-in generic picks (`generic_pick_1_early` as RB, `generic_pick_2_mid`
  as WR, both team `"PICK"`, both unrostered) never lists a pick in FA
  results, while real players still surface.
- (pre-existing `test_pick_pseudo_players_are_not_free_agents` continues to
  pin the position-`"PICK"` case.)

## Verification

- `python3 -m pytest backend/tests -q` → **1378 passed, 1 skipped**
  (branch baseline: 1365 passed, 1 skipped).
