# Feature Scope — The automatic re-search on `inputs_changed`

**Date:** 2026-10-28
**Entry point:** release-lead's #470 QA P2-1 follow-up for the 11-06 binary; analytics-lead's grant of option (a) (2026-10-28, cc head-eng and head-product); head-eng: "build when the answer comes"
**Builder:** trades-eng
**Operator sign-off on waivers:** not needed (no waivers)

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** Per analytics-lead's grant, no event, value or taxonomy row is added. Their conditions are pinned in `mobile/tests/check-trade-first-card-events.js` §10:
  - **no R1** (`find_trades_tapped`): the re-search is not a tap;
  - **no new search_id:** the open trace's while the first card hasn't shown (R2 then fires once, on the rebuilt deck's first card, timed from the original tap); otherwise none, so there's no orphan R2 or R2b;
  - **no R2b `error`:** a recovered `inputs_changed` never sets deckFailure;
  - **at most one per search;** a failed re-search or a second `inputs_changed` shows the error card, and Try again stays R1 `deck_error_retry`.
  - Server side, unchanged: `trades_generated` fires once for the rebuilt deck. It carries no search_id; the /generate response echoes the id sent, if any, for the client's trace.
  - A future auto re-search rate would be its own NON_INTENT event; it isn't needed for 11-06.

## 2. Schema & flag scope

- **New/changed tables or columns:** none.
- **New/changed feature flags:** none. It's client behavior on an existing server error. Rollback is a binary; the server's `inputs_changed` itself is unchanged.
- **New env vars / `model_config` keys:** none.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-trade-first-card-events.js` §10 (10a–10k).
  - **Executed** against `utils/tradePages.ts`'s rules and the real `state/tradeSearchTrace.ts`, analytics-lead's four cases:
    - (i) after R2: no R1/R2/R2b, no search_id;
    - (ii) before the first card: the open id, one R2, no R2b;
    - (iii) a failed re-search → the error card, then one R1 `deck_error_retry`;
    - (iv) no second re-search.
  - **By shape:** the job-error mirror returns before deckFailure, the re-search goes through `dispatchGenerate` with the open id or none and never a tap path, the deck end hides the error while recovering, and Try again stays a tap.
  - **Updated:** the dispatch-site census counts (8 routed sites: `check-canvas-results` 12a, `check-inline-home` 7f, `check-results-push` 4f, `check-offer-prefill-330` S-2) and `check-trade-pages` 5a's shape.
- [x] **Unit tests:** none (mobile only; the rules are executed in the check above).
- [x] **Code-walk proof** (`mobile/src/screens/TradesScreen.tsx` on this branch):
  1. A paged or legacy response for a revoked deck lands with `status: 'error'`, `error: 'inputs_changed'`. The job-error mirror (`useEffect` on `job?.status, job?.error`) reads `autoResearchOnJobError('idle', 'inputs_changed') === 'pending'`, sets the ref and returns before `setDeckFailure`. So the R2b effect (`if (deckFailure) failDeckSearch('error')`) never runs.
  2. At render, `deckEnd` is `'pending'` (offline: `'offline'`), never `'error'`, while `autoResearchHidesError` holds: an `inputs_changed` not yet re-searched, or the re-search itself in flight (`generateMutation.variables.research`, not any dispatch). The slot renders nothing, or the Offline card, never `DeckMoreErrorCard`.
  3. Once `rawTopCard` is null (no card left), the effect beside `deckEnd` sets `'used'` and calls `dispatchGenerate({repeat: true}, undefined, {searchId})`. `searchId` is `autoResearchSearchId(deckSearchRef.current?.id, isSearchOpen)`: the open trace's id, or null.
  4. `dispatchGenerate` with `research`:
     - skips `claimPendingSearch` and leaves the ref at `'used'`; no dispatch resets it any more;
     - sets `deckSearchRef` to that id or null;
     - mutates with `searchId: research.searchId ?? undefined, research: true`. `generateTrades(request, { searchId })` always sends `page: 1`, plus `search_id` only when there is one, so the rebuilt deck is paged (#525 QA P2-1).
     - **The budget resets only when a non-research dispatch's answer lands** (`onSuccess`: `autoResearchAfterAnswer`). A Try again whose request fails leaves the revoked job and `'used'`, so the error card stays: no endless empty slot (#525 QA P1-1).
  5. The new job's first card: `checkFirstCardShown` reports R2 for `deckSearchRef.current?.id`. That's the open id (one R2), or nothing when the trace had settled. While the trace is open, the re-search's answer replaces the first response (`noteFirstResponse(..., { replace: !!vars.research })`), so R2's `job_id`, `serve_source` and `freshness_state` name the rebuilt deck, not the revoked one (analytics-lead). Every other response stays first-wins, and a settled trace never changes.
  6. If the re-search's POST fails, `onError` sets deckFailure as today. If its job errors again, the mirror reads `'fail'` (state `'used'`) and sets deckFailure, so the error card and its Try again (a real tap, R1 `deck_error_retry`) return.
- [x] **Manual TestFlight checklist** (two devices on one account, or one device plus web).
  - **Setup:** the timing readout needs `testing.timing_readout`, which ships dark, so ask release-lead to enable it for the test account.
  - **Safety:**
    - the ranking edit changes only the operator's own FTF board, so put the player back afterwards (or use a test account);
    - never tap Send or Propose;
    - don't use a Sleeper roster move: it changes a real league, and since #481 it revokes only the refresher's own deck.
  - **Which decks:** after the page-store flip, only pinned, Specific Team and intent decks pass the error through. So use a pinned-player search.
  - **How the path triggers:** device A requests pages only while fewer than 50 cards are unseen, so a deck is fully paged within seconds of its first card. The input change must therefore land while A's deck is still building.
  1. Device A: Trades → pin a player (the give side) → Find a Trade, on a cold search (one not run recently). As soon as the first card shows, go to step 2.
  2. Device B, right away: Rankings → move one player, so the input change revokes A's deck while it's still building.
  3. Device A: swipe to the last held card. **Expect:** no "Couldn't load more trades." card. A fresh deck appears in place within a few seconds, and Like/Pass work on its first card. The readout shows **no new tap** (its last tap is still step 1's). **If you see the end card ("That's every trade…"), the change landed after the deck was complete and it didn't trigger: redo from step 1.**
  4. Repeat steps 1–2, then on device B make a second ranking move while A swipes the rebuilt deck. **Expect:** at its end, "Couldn't load more trades." shows (one automatic re-search per search). Its Try again starts a new search (a new tap in the readout), and the rebuilt deck pages normally (more cards load as you swipe).
  5. Device A: Find a Trade (pinned, cold), then **immediately**, before the first card, do step 2. **Expect:** the first card still appears with no error card, and the readout's time for that search covers the whole wait from the tap.
  6. Device A: as in steps 1–2, but turn on airplane mode just before the last held card. **Expect:** the Offline card (never "Couldn't load more trades.") while offline. Back online, the fresh deck appears, or the error card shows if the re-search fails.
  7. Put the moved players back on device B (the safety note above).
- `testID`s: none added (testid-lint OK).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route or contract change; the client may omit `search_id`, as the contract already allows |
| `living-memory/LLD.md` | updated | the deck paging client rules: the automatic re-search |
| `docs/architecture.md` | n/a | no wiring change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant (web has no paged deck) |
| `docs/glossary.md` | n/a | no new term |
| ADR or `DECISIONS.md` entry | n/a | analytics-lead's grant and head-eng's ruling are the decision record |
| `mobile/tests/README.md` | updated | the `check-trade-first-card-events` row |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (with the `check-*.js` suites) + `maestro-testid-lint`.
- **Evidence recorded:** the `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** §3's checklist, by the operator on the 11-06 build. Outcome logged in TEST_LEDGER.
- **Express lane:** no; full gates.
