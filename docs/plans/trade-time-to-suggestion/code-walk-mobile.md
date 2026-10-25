# Code walk: the 200 ms path's mobile pieces (#363)

> D-056 evidence for #363: pass A (paging), M (time-to-suggestion events), C (device-held first page). No
> simulator. Keyed by **symbol, not line number**, so it stays true as files move; the structural guards pin each
> claim, and CI runs every `mobile/tests/check-*.js`. Requirements: PRD #339 (`prd.md`, AC-L1 to AC-L8, U1–U5);
> eng scope v1.3 (`plan/trades-200ms-eng-scope`). Written 2026-10-25 by trades-eng.

## Contents

- [1. Paging and the deck (pass A)](#1-paging-and-the-deck-pass-a)
- [2. Time-to-suggestion events and the readout (M)](#2-time-to-suggestion-events-and-the-readout-m)
- [3. The device-held first page (C)](#3-the-device-held-first-page-c)
- [4. TestFlight checklist](#4-testflight-checklist)

## 1. Paging and the deck (pass A)

- **Request** (`api/trades.ts`): opt-in `page=1` on `/generate`, then `cursor` (and P2's `deck`) on `/status`. A
  response without `cursor` is today's cumulative snapshot, handled as before.
- **Merge** (`utils/tradePages.ts` `mergeDeckPage`):
  - the fronted card and every card before it never move, change or disappear (AC-9);
  - an append page goes behind everything held, deduped by `deckCardKey` (`trade_hash`);
  - only a whole-deck response (`isWholeDeck`: `replace`, or a rebased page spanning a finished deck) replaces
    what's behind the front, and a fronted card it lacks is **withdrawn in place** (`WithdrawnTradeCard`).
- **Never runs dry** (U3 / AC-L4):
  - `wantsNextPage` prefetches at the served `prefetch_remaining` (fallback `PREFETCH_REMAINING_FALLBACK` = 50);
  - `needsBackoff` / `pageRetryDelayMs` / `nextRetryAttempt` retry silently;
  - there is no "Finding more" state anywhere.
- **End of deck** (P30): `deckFullyDelivered` / `deckEndState` end a paged deck only on `pool_exhausted`, with nothing
  in flight. `DeckEndCard` carries the P30 copy and two actions, and its tally is suppressed at 0 · 0 · 0 (P36).
- **"Updating"** (`DeckUpdatingLabel`) is information only. It never disables Like or Pass (U2).
- **Screen** (`TradesScreen.tsx`): `applyPage`, `fetchNextPage`, `dispatchGenerate`.
- **Guards:** `check-trade-pages`, `check-trade-buffer`, `check-trade-inplace-reveal`, `check-no-finding-more`,
  `check-withdraw-in-place`.

## 2. Time-to-suggestion events and the readout (M)

- **One trace per tap** (`state/tradeSearchTrace.ts`). `beginTradeSearch` is the only R1 (`find_trades_tapped`)
  emitter. At the tap it:
  - mints `search_id`;
  - stamps `performance.now()` (never Date);
  - decides `launch_state` and caches `network_type`;
  - starts the 10 s timeout.
  The dispatch claims the id: `claimPendingSearch` / `claimSearch`, or `dropPendingSearch` if no search runs.
- **Tap sites:**

  | Control | `source` |
  |---|---|
  | `utils/canvasSearch` (`calc_find_a_trade_tapped` carries the same `search_id`) | `calculator` |
  | `LeagueSummaryScreen` | `league_offer` / `league_target` |
  | `UsageTrendsScreen` (dropped if the league switch fails) | `usage_trends` |
  | `TeamReviewScreen` (only with a scoped partner) | `team_review` |
  | `TradesScreen.handleFindTrades` | the in-deck sources, `end_card_adjust`, `deep_link` |

- **R2 at T1** (`TradesScreen.checkFirstCardShown` → `reportFirstCardShown`). It fires only when:
  - the fronted card is one this search delivered;
  - Like and Pass are enabled;
  - the card is ≥ 50% visible in window coordinates.
  It reports on the next frame.
- **R2b** (`failFirstCard`) covers empty, error, abandoned (blur, unmount, the app leaving `active`, or a newer tap),
  and the 10 s timeout. R2 and R2b share `settled`, so exactly one fires per `search_id`.
- **`deck_buffer_empty`** (`reportDeckBufferEmpty`) fires once per search. Settled traces past the 20 newest are
  pruned.
- **Server:**
  - `analytics_taxonomy` holds the exact prop rows; R1 stays INTENT, and R2/R2b/`deck_buffer_empty` are in
    `analytics_queries.NON_INTENT_EVENTS`;
  - `analytics_ingest._HEX_ID_PROPS` lets `search_id`/`job_id`/`deck_id` skip the digit-run scrub, but only when
    they're id-shaped.
- **Readout:** `components/TimingReadoutRow` (null unless `testing.timing_readout`). It reads `utils/tapTiming`
  (memory only), and onboarding-eng mounts it in Settings › Testing.
- **Guards and tests:** `check-trade-first-card-events`, `check-timing-readout`,
  `backend/tests/test_time_to_suggestion_events.py`, `test_analytics_taxonomy_384.py`.

## 3. The device-held first page (C)

- **Rules** (`utils/devicePage.ts`):
  - **storage:** per account, league and format (`devicePageKey`), only for the organic default scope
    (`devicePageScope`). A page is kept only from a complete, non-updating P2 response (`storableResponse`,
    `devicePageFrom`), with at most `DEVICE_PAGE_MAX_CARDS` = 30 cards.
  - **when it's used:** if it's within `DEVICE_PAGE_MAX_AGE_S` = 300 (`devicePageUsable`; a cross-client
    invariant).
  - **refresh:** at most every `DEVICE_PAGE_REFRESH_MIN_S` = 60 (`refreshDue`).
- **Store** (`state/devicePageStore.ts`):
  - a synchronous in-memory read for the tap (`readDevicePage`), persisted to AsyncStorage;
  - `refreshDevicePage` runs on Trades focus and foreground, sends no `search_id`, never offline, and drops a stale
    answer after a discard;
  - `clearDevicePages` bumps the discard epoch, which `hydrateDevicePages` respects.
- **Tap** (`TradesScreen.pushWithFirstPage`): a usable page renders at once, with no request, timer or await.
  `serve_source` is `device`.
- **Revalidation** (`revalidateDevicePage`):
  - it is the tap's own request, with the same `search_id`, capped at `DEVICE_REVALIDATE_MAX_MS`;
  - its answer goes through `applyPage(…, {revalidation: true})` → `mergeRevalidation`, a whole-deck merge, so an
    absent fronted card is withdrawn in place;
  - `deckUpdating` shows only while it runs;
  - on failure, `DeckRefreshFailedLine` shows with Retry (spoken: "Retry refreshing trades").
- **Swipes:** `advance()` removes the acted-on card (`removeDeviceCard`), so it never returns on the next tap.
- **Discard:**
  - the `api/client.ts` write listener (`isRankingWritePath`) fires on the user's rankings/preference writes;
  - `useSession` clears on `setUser` to another account, on `signOut` (which includes deletion), and on
    `startDemoSession` over another account.
- **Gate:** C is inert unless the served `trade.first_page_store` flag is on.
- **Guard:** `check-device-first-page` executes the util and the store with stubbed storage and network, and pins
  the screen, client and session wiring.

## 4. TestFlight checklist

**C (flag `trade.first_page_store` on):**
1. **Warm tap within 5 min:** open the Trades landing, wait 3 s, then tap Find a trade.
   - **Expect:** the first card instantly, with no skeleton; "Updating" briefly, then gone; Like and Pass work
     throughout; R2 `serve_source: device`.
2. **Tap after 6 min**, with no refocus. **Expect:** the normal network path, and no device "Updating".
3. **Airplane mode with a page under 5 min old.** **Expect:** cards at once, plus the refresh-failed line with
   Retry; airplane mode off clears it.
4. **Airplane mode with no page.** **Expect:** the Offline card at once; reconnecting fills the cards in place.
5. **Roster move from another device**, then tap on A within 5 min. **Expect:** the moved player's card turns into
   "This trade is no longer available." / Next trade within about 1 s.
6. **Sign out, then sign in as another account.** **Expect:** no card from the first account; the first tap takes
   the network path.
7. **Re-rank** (a trio or a tier save), then tap. **Expect:** no instant device card; the deck reflects the new
   ranks.
8. **Pass two cards, go back, re-tap.** **Expect:** the passed cards never reappear.
9. **Flag off.** **Expect:** identical to pass A.

**M:** turn on `testing.timing_readout` for the test device (`timing_readout_rollout`), tap Find a trade, and check
that Settings › Testing shows the last `ms_from_tap` with its network and launch state.

**AC-L1 itself** (p95 ≤ 200 ms, the scripted two-device session) is app-manager's device checklist (OA-6, 11-07 to
11-09; `docs/plans/org-bringup/leads/app-manager-200ms-checklist.md` in the org's working folder).
