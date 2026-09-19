# #228 — Hide a season's picks once that rookie draft has occurred — status

**Status: built (backend — Sleeper sync exclusion; MFL degrades,
documented)** · 2026-08-01 · branch `teardown-remediation` worktree

## Operator report

> "Draft picks should not be present for that year if a league rookie
> draft has already occurred (for example 2026 picks are shown in trades
> for lakeview but that draft already happened."

Filed 2026-08-01T06:37Z from `TradeDeck` (v1.11.0, iOS). Verified live:
Sleeper `GET /v1/league/1312076055586050048/drafts` (Lakeview) →
`{status: "complete", season: "2026"}`, while the pick sync still built
the full 2026..2029 grid (192 picks incl. 48 non-existent 2026 ones). The
operator's other league (FFv3 `1312140920132497408`) is `pre_draft` for
2026 — its 2026 picks are legitimately still tradable assets.

## Behavior

During the session-init pick sync for Sleeper leagues
(`server._sync_sleeper_owned_picks`), the league's drafts are fetched
best-effort (`GET /v1/league/<id>/drafts`, new `_fetch_sleeper_drafts`,
fail-soft → `[]`). When a draft with `status == "complete"` matches the
league's CURRENT season, that season is passed to
`sync_draft_picks(exclude_seasons={...})`, which drops it from both the
pristine grid AND the traded-picks overlay. Rules:

- **Future seasons are always included** — only the current season is ever
  excluded, and only on a `complete` draft (`pre_draft`/`drafting` keep
  today's behavior).
- **Flaked drafts read excludes nothing** — degrade to current behavior,
  never guess.
- **Stale rows self-clean:** the sync is replace-style (delete league rows
  → insert fresh), so previously synced current-season rows disappear on
  the league's next session init (verified by test). No manual repair.
- **Downstream fixed for free:** trade suggestions (`_owned_pick_assets` ←
  `load_draft_picks`), the calculator pick lists and `/api/league/picks`
  all read `draft_picks`, so post-draft current-year picks vanish from all
  of them at once.

**MFL — ~~documented degradation~~ CLOSED 2026-08-05.** The MFL bundle's
`futureDraftPicks` export drops a draft's picks once that draft has been
held (executed picks become rostered players), but the engine read the copy
stored at link/import time (`leagues.platform_future_picks`), so a league
linked BEFORE its MFL draft kept the stale year until the next re-import
(`POST /api/mfl/import` or re-link). The claim that "the bundle carries no
cheap draft-status export" was **wrong**: #207 found and verified
`TYPE=draftResults` (zero-auth), and the parity follow-up closed the seam —
see [../207-rookie-draft-detection/mfl-parity-status.md](../207-rookie-draft-detection/mfl-parity-status.md).

MFL now gets both halves:
1. **Snapshot refresh** — `server._refresh_mfl_future_picks` re-fetches
   `TYPE=futureDraftPicks` (also zero-auth, verified live) on #207's
   draft-status refresh cadence. No re-import required, no new cron.
2. **Verdict-gated exclusion** — `server._sync_mfl_owned_picks` drops the
   CURRENT season's picks when the league's cached `draft_status` is
   positively `drafted`. Same **write-path layer** as this item's Sleeper
   rule (`_sync_sleeper_owned_picks`), same fail-safe direction
   (`not_drafted`/`unknown`/never-checked exclude nothing), same
   self-cleaning replace-sync.

**This item's Sleeper behavior is unchanged** — `_sync_sleeper_owned_picks`
still reads its own live `GET /v1/league/<id>/drafts`, not the cached #207
verdict (pinned by
`test_owned_picks.py::test_cached_verdict_does_not_leak_into_the_sleeper_sync`).

**Out of scope:** feedback #207 (add pre-draft rookie PICKS to rank sets)
is a separate idea — deliberately not built here.

## Files

- `backend/server.py` — `_fetch_sleeper_drafts`; completed-draft exclusion
  in `_sync_sleeper_owned_picks`
- `backend/database.py` — `sync_draft_picks(exclude_seasons=…)` (grid +
  traded overlay)
- `backend/tests/test_owned_picks.py` — regression tests
- `docs/api-reference.md` — `/api/league/picks` sync-semantics note

## Tests (`backend/tests/test_owned_picks.py`)

- `test_sync_excludes_completed_draft_season` — excluded season absent
  from grid AND overlay; future-season trades still apply.
- `test_replace_sync_cleans_stale_current_season_rows` — pre-draft rows
  are cleaned by the first post-draft sync.
- `test_daemon_step_excludes_current_season_when_draft_complete` — end-to-
  end through `_sync_sleeper_owned_picks` with a `complete` drafts fixture.
- `test_daemon_step_no_exclusion_when_draft_pending_or_flaked` —
  `pre_draft` status and a flaked drafts read both keep current-season
  picks.

## Verification

- `python3 -m pytest backend/tests -q` → **1378 passed, 1 skipped**
  (branch baseline: 1365 passed, 1 skipped).
