# #236 — Trade DNA edits autosave on selection

- **Reported by:** mattmurf77 (severity: polish, screen: TradesHome)
- **Ask:** "Trade dna edits should save automatically upon user selection rather than waiting on the user hitting 'done'"
- **Status:** Done (2026-08-02), branch `teardown-remediation` (worktree)

## Root cause of the old behavior

The #212 in-place DNA editor on `mobile/src/screens/TradeFinderHubScreen.tsx`
was deliberately built as a staged draft: taps only mutated local state
(`draftOutlook` / `draftChasing` / `draftShopping`), and the single
`POST /api/league/preferences` (the `saveOutlook` mutation) fired inside
`handleDnaDone` — gated on `dnaTouched` so an idle expand/collapse never
invalidated the backend's cached deck. Consequence: closing the editor any
other way (or assuming taps stuck) silently dropped edits until Done was
pressed.

## The change (mobile only; no backend/API change)

- **Autosave per tap:** `pickOutlook` and `toggleDnaPos` now compute the
  next full preference payload up front and call `queueDnaSave`, which
  POSTs immediately via the existing `saveOutlook` mutation. Coalescing:
  one request in flight at a time (`dnaInFlight`/`dnaDesired` refs); taps
  landing mid-flight collapse into a single trailing save of the latest
  full payload, so requests can't complete out of order and the last
  write wins. Re-tapping the already-selected outlook is a no-op (no POST).
- **Cache sync per edit:** each successful save runs the mutation's
  existing `onSuccess` — `invalidateQueries(['league-prefs', leagueId])` —
  exactly what the old Done handler did, so the collapsed summary,
  `OutlookBiasReceipt`, and TradesScreen's prefs consumers stay in sync.
  The mid-edit reseed guard (`dnaEditing && dnaTouched`) keeps the
  refetch from clobbering the open editor.
- **Failure handling (existing pattern):** on a failed save, queued edits
  are dropped, drafts revert to the last-saved prefs from the
  `['league-prefs']` cache, and the existing inline `dnaError` line
  ("Could not save preferences" / server message) renders — same error
  surface #212 used.
- **Done is a pure collapse:** `handleDnaDone` no longer POSTs; the
  button keeps its label/testID (`dna.done`) but drops the
  `isPending` spinner/disable since collapsing never waits on a save.
  An untouched expand/collapse still fires zero POSTs (the "a look never
  invalidates the cached deck" guarantee is preserved — only taps save).
- Doc sync: `mobile/src/screens/CLAUDE.md` TradeFinderHubScreen row
  updated with the #236 note.

All existing testIDs (`dna.edit`, `dna.done`, `dna.outlook.*`,
`dna.chase.*`, `dna.shop.*`, `finder-hub.dna.untouchables`, …) are
unchanged; no visual styling changes beyond removing the Done spinner
state.

## Verification

- `cd mobile && npx tsc --noEmit` — passes clean (exit 0).
- Code-path review: every editor mutation path (`pickOutlook`, both
  branches of `toggleDnaPos`) ends in `queueDnaSave` with the exact
  arrays just rendered; `handleDnaDone` and `openDnaEdit` contain no
  mutation calls; `saveOutlook` is invoked only from `flushDnaSave`.
- Coalescing logic traced: `flushDnaSave` early-returns while in flight,
  `finally` re-flushes if a newer desired payload arrived, and the error
  path clears the queue before reverting — no retry loop, no stuck flag.
