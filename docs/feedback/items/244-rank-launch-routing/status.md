# #244 — Rank-tab launch routing by quick-tiers completion

**Status:** built 2026-08-05 · branch `teardown-remediation` · mobile-only (no backend change)

Operator ask: the screen you land on when you log in should follow quick-tiers
progress — no quick tiers yet → Quick Set; some positions done → Quick Set at
the next unset position; all positions done → Trios.

## Routing table (Rank stack `initialRouteName` / `initialParams`, decided once at first mount)

| State at launch | Destination | Data source |
|---|---|---|
| Explicit `rankingMethodPref` stored (`trio`/`anchor`/`tiers`/`manual`) | That surface (`PREF_ROUTE`, unchanged) | `useSession.rankingMethodPref` (AsyncStorage `ftf_rank_method_pref`, hydrated in `bootstrap()`) |
| Explicit pref `'quickset'` | QuickSetTiers, **starting at the next unset position** (QB if all done) | pref + completion union (below) |
| No pref, **zero** positions complete | QuickSetTiers at QB (ladder start) — byte-identical to the #122 default | completion union (below) |
| No pref, **partial** (1–3 positions complete) | QuickSetTiers, auto-positioned at the **next unset position** in QB→RB→WR→TE order | completion union (below) |
| No pref, **all four** positions complete | **Trios** (`RankScreen`) | completion union (below) |

**Completion union** (`mobile/src/state/quicksetProgress.ts` → `nextQuicksetPosition()`):
a position counts as complete when it is in **either**

1. `useOnboardingState.quicksetCompletedPositions` — the persisted "finished a
   Quick Set walk" record QuickSetTiersScreen writes on every walk finish
   (updates instantly, so on-device progress routes right on the very next
   launch), **or**
2. the device-cached snapshot of `GET /api/tiers/status` `saved` (positions
   with saved tiers for the active format — server truth, existing endpoint,
   **no backend field added**; also what makes reinstalls / second devices /
   Tiers-board-built boards converge). Format-tagged: a snapshot cached under
   a different scoring format is ignored rather than misapplied.

## Async / stale handling (matches how the pref itself works)

- The decision is **synchronous at first mount** from pre-hydrated state: the
  App.tsx boot gate (INIT-01 legs) now includes `hydrateQuicksetProgress()`
  (local AsyncStorage read, ms-fast) alongside `bootstrap()` and onboarding
  hydration — so routing never races defaults and never flashes a wrong
  screen.
- The server snapshot refreshes **fire-and-forget after `revalidateSession`**
  (`refreshQuicksetProgress()`); a stale cache converges on the NEXT launch.
  There is deliberately no mid-session `navigation.replace` — same
  "applies next launch" contract as `initialRouteName`/`rankingMethodPref`.
- Worst-case staleness: fresh install of an all-done account lands on Quick
  Set once (optimistic default), then Trios from the next launch onward.

## Pref interaction (operator rule vs. chooser pref)

- An **explicit** `rankingMethodPref` chosen in the RankHome chooser (or the
  Settings slider) always wins on destination — the completion automation
  only fills the no-pref gap. This includes explicit `'quickset'`: an
  all-done user who *chose* Quick Set still lands there (at QB), per the
  "explicit pref wins" ruling; only the next-unset **starting position** is
  applied to the quickset path in both pref states (it changes where the walk
  starts, not which screen shows).
- `initialParams` fill only missing keys: the Tiers header
  (`navigate('QuickSetTiers', { position })`) and the guide's next-position
  prompt keep their explicit positions; the Rank menu / chooser / launch
  routing inherit the next-unset start.

## Known limits (accepted, documented)

- Both stores are **device-scoped and survive sign-out**, exactly like
  `ftf_rank_method_pref` — a different user on the same device inherits one
  optimistic launch, then the refresh converges the cache.
- `quicksetCompletedPositions` is format-agnostic (it drives the onboarding
  provenance chip and was reused, not re-scoped); the server snapshot is the
  format-aware half of the union.

## Files

- `mobile/src/state/quicksetProgress.ts` — new: cache + `nextQuicksetPosition()`
- `mobile/src/navigation/TabNav.tsx` — `RankStackNav` launch decision + QuickSetTiers `initialParams` (routing only; **no tab definitions/labels touched** — another agent owns a tab rename in this file, overlap noted)
- `mobile/App.tsx` — boot-gate hydration leg + post-revalidate refresh
- Docs: `mobile/src/navigation/CLAUDE.md`, `mobile/src/screens/CLAUDE.md` (QuickSetTiers/RankScreen rows), `mobile/src/state/CLAUDE.md`

## Verification

- `npx tsc --noEmit` clean (worktree mobile).
- Backend untouched → pytest gate not applicable (no route/schema change;
  `/api/tiers/status` reused as-is, `docs/api-reference.md` unchanged).
