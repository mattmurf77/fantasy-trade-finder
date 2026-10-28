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
  - Server side, unchanged: `trades_generated` fires once for the rebuilt deck, echoing the id sent, if any.
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
  2. At render, `deckEnd` is `'pending'`, not `'error'`, while `autoResearchHidesError` holds. The slot renders nothing, never `DeckMoreErrorCard`.
  3. Once `rawTopCard` is null (no card left), the effect beside `deckEnd` sets `'used'` and calls `dispatchGenerate({repeat: true}, undefined, {searchId})`. `searchId` is `autoResearchSearchId(deckSearchRef.current?.id, isSearchOpen)`: the open trace's id, or null.
  4. `dispatchGenerate` with `research`:
     - skips `claimPendingSearch` and keeps the ref at `'used'`;
     - sets `deckSearchRef` to that id or null;
     - mutates with `searchId: research.searchId ?? undefined`, so `generateTrades` sends no `search_id` when it's null.
  5. The new job's first card: `checkFirstCardShown` reports R2 for `deckSearchRef.current?.id`. That's the open id (one R2), or nothing when the trace had settled.
  6. If the re-search's POST fails, `onError` sets deckFailure as today. If its job errors again, the mirror reads `'fail'` (state `'used'`) and sets deckFailure, so the error card and its Try again (a real tap, R1 `deck_error_retry`) return.
- [x] **Manual TestFlight checklist** (two devices on one account, or one device plus web; the timing readout on):
  1. Device A: Trades → Find a Trade. Wait for the first card; swipe until about 5 cards are left.
  2. Device B: change one ranking (Rankings tab: move a player), so the input change revokes A's deck.
  3. Device A: keep swiping to the last held card. **Expect:** no "Couldn't load more trades." card. A fresh deck appears in place within a few seconds, and Like/Pass work on its first card. The timing readout shows **no new tap** (its last tap is still step 1's).
  4. Repeat step 2 on device B while A swipes the rebuilt deck to its end. **Expect:** this time the "Couldn't load more trades." card shows (one auto re-search per search), and its Try again starts a new search (a new tap in the readout).
  5. Device A: Find a Trade, then **immediately** (before the first card) repeat step 2 on device B. **Expect:** the first card still appears, with no error card. The readout's time for that search covers the whole wait from the tap.
  6. Device A offline at step 3 (airplane mode as the last card is reached). **Expect:** no error card while offline (the slot stays empty while the re-search waits for the network); back online, the fresh deck appears, or the error card shows if the re-search fails.
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
