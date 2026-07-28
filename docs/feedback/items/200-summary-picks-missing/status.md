# #200 — Draft picks missing from League Summary — status

**Status: fixed (backend root cause; client had no bug)** · 2026-07-27 ·
branch `teardown-remediation` worktree

## Operator report

> "Draft picks are missing from league summary"

Filed 2026-07-28T01:07Z from `LeagueRankings` (v1.11.0, iOS).

## Root cause — (c) the payload's `team.picks` went missing, but NOT in power_rankings

The task's three candidates were each ruled out where they pointed:

- (a) **Picks segment in the vertical bars** — present since the League
  Analyzer rewrite (a4ed81f) and correctly re-based by #195 (5326f78):
  `LeagueSummaryScreen.BarColumn` renders the neutral `PICKS` segment at the
  stack base in the All subset.
- (b) **Drill-in "Draft capital" section** — present in the inline-roster
  rewrite (All subset, `league-summary.roster-picks`), as is the Picks
  filter pill (`showPicksKey`) and legend entry.
- (c) **`compute_power_rankings` / the route** — both serialize `picks`
  correctly (13 pre-existing tests); prod data for the Sleeper leagues was
  healthy.

The actual regression sat one layer deeper. The operator's active league at
feedback time (prod `user_events`) was **62846 — "The Dependables League",
an MFL league** linked via #177. Prod `leagues.platform_future_picks` holds
its raw pick list (9 KB), but prod `draft_picks` had **zero rows** for it:

**Session-init's #158 owned-pick sync daemon gated the Sleeper grid rebuild
on `str(league_id).isdigit()` alone.** MFL native ids are numeric too (the
established #149/#150 misroute class — the proxies already guard with
`is_linked_platform_league`, this daemon didn't). For an MFL id the Sleeper
traded-picks/rosters fetches return nothing, so
`sync_draft_picks(roster_ids=[], …)` REPLACE-synced the league's
`draft_picks` to an **empty grid — deleting the picks `_sync_mfl_owned_picks`
normalized at link time**. Every app open into the league re-wiped them.
`/api/league/power-rankings` then served `picks: {count: 0, value: 0}` for
every team, and the client — behaving exactly as designed for a league
without draft capital — hid the Picks pill, the bar segment, the legend
entry, and the Draft capital section. Nothing to "restore" client-side.

## Fix

`backend/server.py` session-init daemon: the pick-sync step now
discriminates with `is_linked_platform_league(league_id)` —

- platform-linked numeric ids **skip the Sleeper grid sync** (the clobber
  can't happen) and **re-run `_sync_mfl_owned_picks(league_id)`** instead:
  no network (reads the stored `platform_future_picks`), ESPN/Fleaflicker
  rows have no MFL row and return 0 (no fabrication), and previously
  clobbered leagues **self-heal on their next session init** — no manual
  prod data repair needed (league 62846 recovers the next time the operator
  opens it).
- genuine Sleeper ids run the existing grid+overlay sync unchanged.

`backend/power_rankings.py` and `mobile/src/screens/LeagueSummaryScreen.tsx`
required no changes (verified end-to-end: `_power_picks_by_owner` resolves
all owners against `league_members` for the affected league once rows
exist; the chart/pill/drill-in render paths were all live).

## Files

- `backend/server.py` — session-init pick-sync platform guard (+ comment)
- `backend/tests/test_owned_picks.py` — 2 new tests
- `docs/runbook.md` — incident entry (diagnosis pattern + watch item for the
  other `isdigit()`-gated daemons, which fail soft today)

## Tests (`backend/tests/test_owned_picks.py`, 14 total — 2 new)

- `test_numeric_mfl_id_detected_as_platform_league` — a numeric MFL id
  passes `isdigit()` (the old gate's blind spot) but is caught by
  `is_linked_platform_league`.
- `test_mfl_renormalization_restores_clobbered_picks` — normalize → clobber
  (the pre-fix daemon's empty replace-sync) → re-normalize restores both
  rows with `platform="mfl"` and priced `pool_value`.

## Verification

- `python3 -m pytest backend/tests -q` → **1352 passed, 1 skipped**
  (branch baseline before this change: 1346 passed, 1 skipped).
- `cd mobile && npx tsc --noEmit` → clean (exit 0; no client change beyond
  the #198 panel copy).
