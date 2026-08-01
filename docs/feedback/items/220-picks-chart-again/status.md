# #220 — "Picks still not present on the bar chart" (post-#200) — status

**Status: fixed (backend — Sleeper-flake wipe class closed; client verified,
no change)** · 2026-08-01 · branch `teardown-remediation` worktree

## Operator report

> "Picks still not present on the bar chart"

Filed 2026-08-01T06:23Z from `LeagueRankings` (v1.11.0, iOS) — three days
AFTER the #200 fix shipped (backend on origin/main `b41b128`, deployed).

## Honest re-root-cause — what was ruled out, with evidence

The task's three candidates were each verified WORKING before looking
deeper:

- **(a) MFL heal path** — runs. App open into a linked MFL league always
  ends in `POST /api/session/init` with the MFL league id (both client
  branches converge: `initLeagueSession`'s MFL branch builds the body from
  the backend snapshot via `/api/mfl/leagues`; the Sleeper-branch fallback
  goes through the #149/#150-guarded `/api/sleeper/rosters|league_users`
  proxies, which serve the DB snapshot for `is_linked_platform_league` ids).
  The daemon then routes numeric platform ids to `_sync_mfl_owned_picks`
  (the #200 guard) — code path confirmed live on origin/main.
- **(b) Client bar segment** — present and live in v1.11.0.
  `LeagueSummaryScreen.BarColumn` stacks `PICKS` at the base of the All
  subset (since a4ed81f, re-based by #195/5326f78); pill, legend and
  drill-in all render when `teams[].picks.value > 0`. `PICKS_COLOR`
  (`chalk.faint` #626C79) is clearly visible against the well. No client
  change needed.
- **(c) `compute_power_rankings` / `_power_picks_by_owner`** — correct.
  Reproduced empirically against the operator's REAL Lakeview league data
  (dev copy of `1312076055586050048`, 156 rows — including NULL
  `pool_value` legacy rows, which the fallback re-pricing handles): all 12
  teams carry non-zero `picks.value`. Prod's own log (08:22Z, 2026-08-01)
  shows the operator's Lakeview init syncing 192 picks and the trade job
  injecting 72 pick assets — server data healthy AFTER a successful init.

## What was ACTUALLY still broken

The #200 runbook watch item, real on the **genuine-Sleeper path**: the
session-init daemon fed `sync_draft_picks` whatever the Sleeper reads
returned —

- `_fetch_league_rosters` → `None` on any failure, daemon did `or []` →
  `sync_draft_picks(roster_ids=[])` → **REPLACE-synced the league's
  `draft_picks` to an EMPTY grid** (the exact #200 wipe, no MFL misroute
  required);
- a flaked `_fetch_sleeper_league_meta` silently shrank the grid to 3
  rounds / default season (both operator leagues are 4-round).

One bad Sleeper read on app open ⇒ no draft capital anywhere (League
Summary chart, suggestions, calculator) until the NEXT successful init
re-synced — an intermittent, self-re-arming wipe, which is exactly the
"still not present" + "healthy when inspected later" signature (picks were
present in prod by 08:22Z, two hours after the 06:23Z report; the log
buffer had rolled past the report window, so the triggering flake itself is
inferred, not captured — it is the only remaining code path that empties a
synced league's picks).

## Fix

- `backend/server.py` — the daemon's Sleeper pick-sync block is extracted
  to `_sync_sleeper_owned_picks(league_id, uid_to_name, scoring_format)`,
  which **SKIPS the sync and keeps the prior snapshot (returns `None`)**
  when the rosters or league-meta read is unavailable; a skip logs
  `owned-pick sync skipped … (keeping prior snapshot)` and the next init
  retries. (The extraction also hosts the #228 completed-draft exclusion.)
- `backend/database.py` — `sync_draft_picks` **no-ops on empty
  `roster_ids`** (returns `[]` without touching the DB): the only real
  producer of that input is an upstream fetch failure, so it must never
  mean "delete everything" (defense in depth for every caller).

## Client verification (no change shipped)

Verified in `mobile/src/screens/LeagueSummaryScreen.tsx` @ v1.11.0:
`BarColumn` includes the `PICKS` key in the All-subset stack
(`[...CORE_POSITIONS, 'PICKS']`, picks ordered last = the base), segment
value `team.picks?.value`, color `chalk.faint`; `showPicksKey` gates the
pill + legend on `teams.some(picks.value > 0) && subset === 'all'`; the
drill-in "Draft capital" section renders from `picks.items`. With the
backend no longer serving transient `picks: {count: 0}` payloads, the
existing client renders picks with no modification.

## Files

- `backend/server.py` — `_sync_sleeper_owned_picks` extraction + skip
  guard; daemon block now calls it
- `backend/database.py` — `sync_draft_picks` empty-`roster_ids` no-op (+
  `exclude_seasons`, see #228)
- `backend/tests/test_owned_picks.py` — regression tests
- `docs/runbook.md` — incident entry (#220) + operational rule
- `docs/api-reference.md` — `/api/league/picks` sync-semantics note

## Tests (`backend/tests/test_owned_picks.py`)

- `test_sync_empty_roster_ids_keeps_prior_snapshot`
- `test_daemon_step_skips_when_sleeper_rosters_unavailable`
- `test_daemon_step_skips_when_league_meta_unavailable`

## Verification

- `python3 -m pytest backend/tests -q` → **1378 passed, 1 skipped**
  (branch baseline: 1365 passed, 1 skipped).
- No mobile change → `npx tsc --noEmit` not applicable (client untouched).
