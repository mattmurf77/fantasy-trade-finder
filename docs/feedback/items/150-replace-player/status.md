# Status — 150-replace-player

```project-status
{
  "status": "shipped",
  "updated": "2026-07-25",
  "summary": "Status — #150 Replace-player (swap) button not working",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: shipped 2026-07-25 — platform-routing proxy fix `52be577` (#149/#150) — CHANGELOG 2026-07-25. Prior row preserved at ../../../reviews/2026/2026-09-06-project-status-migration/feedback-index.md."
}
```

## Historical notes

The material below is retained evidence. Its former status wording does not override the record above.

# Status — #150 Replace-player (swap) button not working

**2026-07-25 — fixed on worktree branch `worktree-agent-ae33eec5a00d24264` (worktree agent).**

Verbatim: "Replace player button also not working" (TradesHome, v1.9.0 —
filed in the same session as #149, on an ESPN league).

## Root cause — SAME as #149

The swap sheet (feedback #86) opens fine; its candidate list
(`swapCandidates` in `mobile/src/screens/TradesScreen.tsx`) is built from
the same `rosterByOwner` map as the #149 target picker:
`rosterByOwner.get(side === 'give' ? userId : opponent_user_id)`. For an
ESPN league `GET /api/sleeper/rosters/<numeric espn id>` was misrouted to
Sleeper (404), so `rosterByOwner` was empty and the sheet showed zero
candidates — "not working". No separate tap-handler, sheet, or repricing
bug found; the handler wiring and `handleSwapPick` path are intact.

Not reproducible as a Sleeper-league bug from code inspection: Sleeper
leagues resolve `rosterByOwner` normally through the same query.

## Fix

The #149 backend fix (serve platform-imported leagues from the DB in the
`/api/sleeper/rosters|league_users` proxies) restores the candidate pool.
No code change specific to #150. Details + tests:
`../149-espn-trade-away/status.md`.

## Verification

- Covered by the #149 regression tests (rosters proxy returns the imported
  membership snapshot, including counterparties' synthetic `espn:` ids —
  the receive-side swap keys on `opponent_user_id`, which is such an id).
- Full backend suite **1016 passed, 1 skipped**; `npx tsc --noEmit` clean.
