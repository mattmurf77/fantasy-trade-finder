# #121 Anchors resume failure — status

**Covered feedback IDs:** #121, #125 (bugs, duplicate root cause), #128 (bug), #133 (polish)
**Branch:** `trade-engine-v2` · **Owner:** mattmurf77 · **Status:** built + sim-verified, in review

## Items

| ID | Report | Resolution |
|---|---|---|
| #121 | "resuming into the app and landing on the anchors page, the page fails to load" | Fixed — pool query self-heals via `useRecoverOnResume` |
| #125 | "Doesn't load players right away … player fetch call doesn't happen on app resume" | Same root cause as #121; same fix |
| #128 | Error state says "pull back and retry" but pull-to-refresh doesn't work | Fixed — plain-English copy, real pull-to-refresh, Retry button |
| #133 | "Anchors should have the option to set anchors per position or all positions" | Added — All/QB/RB/WR/TE scope pills filtering the wizard queue |

## Root cause (#121/#125)

Server sessions are in-memory and die on every Render deploy/restart (FB-45).
On cold launch and foreground resume, `App.tsx` fires
`useSession.revalidateSession()` to re-handshake and mint a fresh token — but
that takes seconds, and `PickAnchorScreen`'s pool query
(`['anchor-pool', format]`, `staleTime: Infinity`) fires immediately with the
**orphaned token still in secure-store**. The backend 401s, the client clears
the token, TanStack retries once (401 again), and the query lands in error
state. From there nothing ever recovers:

- `staleTime: Infinity` (intentional — a mid-wizard refetch would shuffle the
  queue under the user's thumbs) means no background revalidation;
- `refetchOnWindowFocus` is `false` app-wide (`state/queryClient.ts`); only
  `['progress']` opts in;
- the screen stays mounted in the Rank stack, so there is no remount-refetch;
- nothing invalidates `['anchor-pool']` when revalidation succeeds moments
  later.

So the user resumes into a permanently stuck "Could not load" screen — which
also had no working recovery affordance (#128: plain `View`, nothing to pull,
nothing to tap).

**Other screens share the race** (any query in flight during the
revalidation window 401s once), but they recover on the next
mount/stale-refetch because their `staleTime` is finite. The anchors screen
was uniquely stuck. If resume flakiness is seen elsewhere ("seen similar
behavior with other pages at first"), the new `useRecoverOnResume` hook is
generic — wire it to that screen's query.

## Fixes

1. **`mobile/src/hooks/useRecoverOnResume.ts` (new)** — refetches an errored
   query on two signals, both no-ops otherwise:
   - *Session restore:* `revalidateSession()` ends with
     `set({ hasToken: true })`; zustand notifies subscribers on every `set`
     even when the value is unchanged, so the hook refetches exactly when the
     fresh token lands (this is what heals the 401 race).
   - *Foreground resume:* covers non-auth failures (network blip, server
     hiccup) where no token change ever fires.
2. **`PickAnchorScreen`** wires `useRecoverOnResume(poolQuery)`.
3. **#128** — error/empty state is now a `ScrollView` with a `RefreshControl`
   (pull-to-refresh actually exists and works), a **Retry** button, and copy
   "Couldn't load your players. Pull down to refresh, or tap Retry."
4. **#133** — scope pills above the wizard (PositionTabs construction per
   `docs/design/components.md`: hairline segmented group, active = ink-3 fill +
   2px underline in the position's color, ice for ALL). Verified the wizard
   previously served one value-descending queue across all positions; the
   pills filter that queue client-side (`ALL` preserves the original
   behavior). Scope is session-only by design (module-level mirror survives
   remounts, resets on next launch). Progress counter and the "All anchored"
   card are scope-aware; **Start over** in a position scope re-opens only that
   position's players.

No backend or API-layer changes; `/api/rankings` + `/api/anchor/save` are
untouched, `getAnchorPool` already sends `X-Scoring-Format` (#112).

## Files

- `mobile/src/hooks/useRecoverOnResume.ts` (new)
- `mobile/src/screens/PickAnchorScreen.tsx`
- `mobile/src/hooks/CLAUDE.md`, `mobile/src/screens/CLAUDE.md` (doc rows)

## Verification

- `cd mobile && npx tsc --noEmit` — clean.
- Release sim build via `mobile/scripts/sim-build.sh` (localhost API base),
  fixture backend `standard` profile (qa_standard / QA Standard League)
  seeded via `backend/tests/fixtures/seed_ui_test_db.py`, driven on the
  FTF-iOS18 simulator with Maestro.
- Evidence: see `screenshots/` in this folder (filled in below).

### Runs

_TBD — filled after sim runs._
