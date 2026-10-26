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
- **The kill switch** (`model_config` `trade_paged_responses = 0`, PR #400): the server then ignores `page`/`cursor`
  and answers with the legacy cumulative body. Verified in code that a response with no `cursor` takes the
  pre-paging path:
  - `normalizeJobSnapshot` adds no paging field and no `from_page` stamp (`check-trade-pages` 1d);
  - `isPagedEnvelope(job)` is false, so `wantsNextPage` never fetches (4b) and the legacy cumulative poller runs
    (its `if (isPagedEnvelope(job)) return;` guard, 5d);
  - `orderedDeck` keeps today's sort (no `from_page` card), and `adoptablePage` refuses the landing's page 1, so
    the pushed deck runs its own search (it joins the same job server-side);
  - the device page keeps nothing (`storableResponse` needs a `cursor` and a `deck_id`), so C never renders;
  - **mid-deck** (release-lead's QA of #400): a legacy answer to a deck that was paging goes through
    `applyPage` → `tradePages.nextDeckJob`, which drops every paging field (`PAGING_FIELDS`) instead of
    carrying `prev`'s `cursor` forward. The deck is then un-paged: `fetchNextPage` stops retrying
    (`isPagedEnvelope(next) && needsBackoff(…)`), `wantsNextPage` is false, the legacy poller (keyed on
    `job?.cursor === undefined` too) takes over the same job, and the deck's device page is discarded. A legacy
    answer to a device deck's revalidation replaces the held cards behind the front with the cumulative ones
    (whole-deck merge), adopts the response's job and continues on the legacy path. `check-trade-pages` 6a–6d
    execute `nextDeckJob` and the screen's own `applyPage` with a paged deck and a legacy answer.
  What the lever does **not** revert: the route's `animation: 'none'` (U1), D13's removed buttons, and the
  Offline card for a search paused at the tap (it keys on `generateMutation.isPending`, not on paging). The
  paged-only states don't render on a legacy deck: withdraw in place, the 3a/3b cards past the last card, and
  **the P30 end card** (`showDeckEndCard = pagedWithCards && …`). A legacy deck ends as before, on F10's "Deck
  done" summary (`summaryVisible = !pagedWithCards && …`, flag `deck.replenishment`) or the classic exhausted
  state.
- **Named gate misses** (#339 item 12, ux-lead F-5; S0 contract v0.4 §3b; `utils/gateMiss.ts`):
  - S0's check error with no cards (`status: "error"`, `error: "roster_check_unavailable"`) maps to
    `deckFailure.kind === 'roster_check'` and `GateErrorCard` ("Couldn't confirm current rosters", one line,
    Retry as `deck_error_retry`), never the generic "server may still be waking up";
  - S0's withhold (`wait_reason: "roster_check"` on a building response, parsed by `api/trades.ts`, cleared by
    the next response that lacks it via `nextDeckJob` or the legacy poller) shows `GateWaitCard` in place of
    "Looking for trades…" while the deck has no card; after `FIRST_CARD_TIMEOUT_MS` (R2b's 10 s) with still no
    card it falls through to `GateErrorCard`. Cards arriving end it normally. Its Retry (`handleGateRetry`) also
    restarts the wait: a non-force repeat gets the SAME running job back, so the retry bumps `gateRetrySeq`, a
    dep of the fall-through effect, rather than waiting for a new `job_id`. Copy keys `trades.gate.*` are
    placeholders for marketing-lead; none says "Searching…", "Finding more" or a time. Absent fields mean
    today's behavior. Guard: `check-gate-miss`.
- **Guards:** `check-trade-pages`, `check-trade-buffer`, `check-trade-inplace-reveal`, `check-no-finding-more`,
  `check-withdraw-in-place`, `check-gate-miss`.

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
  (memory only): `ms_from_tap · network_type · launch_state · serve_source`, the last for display only (it shows
  `device` for a device-held first card; no event changes). It is to be mounted by onboarding-eng (#360) in
  Settings › Testing; until that lands, nothing shows it.
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
- **Which key a deck writes** (release-lead P1-a): the deck's own write-back (the device page effect) runs only
  while the screen's `deviceKey` equals `deckKeyRef`, the key the deck was validated under. It is bound at
  adoption (the landing's key rides the handoff) and at a model answer (`ctx.deviceKey`, stamped by that
  dispatch's own `onMutate` next to its epoch — a format switch bumps no epoch, so a shared ref would let an
  older answer bind a newer dispatch's key; `check-device-first-page` 3j runs that ordering). The league reset
  and a format change unbind it (`deckKeyRef`/`validatedAtRef`, and the
  scope on a league switch), so a league or format switch never writes the old deck under the new key.
  `check-device-first-page` 3h runs the screen's own effect bodies through a league switch and then a format
  switch.
- **Discard time** (release-lead P2-a): every discard stamps when (device clock: all pages, or the key), and
  `saveDevicePage` refuses cards validated before it, so a deck that predates a re-rank can't write its cards
  back on its next swipe (2j). A deck's own unkeepable answer stamps its own validation time, so it never bars
  the same deck.
- **Discard:**
  - the `api/client.ts` write listener (`discardsDevicePages`) fires on the user's rankings/preference writes and
    on a scoring-format switch (`/api/scoring/switch`: a page refreshed during it could hold the other format's
    cards);
  - `useSession` clears on `setUser` to another account, on `signOut` (which includes deletion), and on
    `startDemoSession` over another account.
- **Gate:** C is inert unless the served `trade.first_page_store` flag is on.
- **Guard:** `check-device-first-page` executes the util and the store with stubbed storage and network, and pins
  the screen, client and session wiring.

## 4. TestFlight checklist

Pass A and M ship live for everyone; C is gated. Run A on any build with this PR. Each step names what the operator
sees; "deck" is the pushed results deck (Acquire → Find a trade).

**Seeing which path served a card.** The operator can't see R2. Two ways:
- the Testing readout (`testing.timing_readout` on for the device, delivered per device through the experiment
  overlay; config-reference) shows `<ms> ms · <network> · <launch> · <serve_source>` for the last tap. **It is
  visible only once onboarding-eng mounts the row (#360)** in Settings › Testing;
- without it, use airplane mode: only a device-held page shows cards with no network (C step 3).

**A — paging and the deck (live for everyone):**
1. **The U1 hold.** On the Acquire landing, tap Find a trade with an empty canvas. **Expect:** the tap control
   stays pressed, then the deck appears in place (no slide-in push animation) with a complete first card, within
   about 600 ms of the tap. If the server is slower, the deck appears at about 600 ms in its honest wait state,
   never later.
2. **E2 paging, a long deck.** Swipe 40+ cards at a normal pace. **Expect:** the deck never runs dry and never
   shows "Finding more" or any "Looking for trades" card mid-deck; a card you've seen never moves, reappears or
   reorders; no card repeats.
3. **D13.** On a deck with cards, and on the P30 end card: **Expect:** no "Find a Trade" or "Find more trades"
   button anywhere on the deck.
4. **The P30 end card.** Swipe a deck to its true end (a small league, or a pinned search with few results).
   **Expect:** "You've seen every trade for now." / "New ideas show up as rosters and values change.", one tally
   line "N passed · N liked · N proposed", and two buttons: "Adjust your search" (primary) and "Back to Home"
   (secondary; only with the Home tab). Cards that arrive later never replace the end card under your thumb.
   The tally is hidden at 0 · 0 · 0 (P36), but an operator can't reach that state on purpose (every swipe, and
   the Bad trade flag, counts); `check-no-finding-more` 4d pins it instead.
5. **Withdraw in place on an E2 `replace`.** **Use a test league you control on Sleeper, never a real one.**
   Early in a deck from a large league (pages are still loading), trade away on Sleeper a player in the fronted
   card's give side, then let FTF see it (open FTF on a second
   device, or background and foreground this one) while the card stays fronted. **Expect:** at the next page
   fetch, the card keeps its slot and shows "This trade is no longer available." with Next trade; Like/Pass are
   gone on it; Next moves on. Nothing slides in by itself.
6. **Offline mid-deck (3a).** Go to airplane mode and swipe past every card already on the phone. **Expect:**
   "You're offline. More trades load when you're back online." with Retry, in the card slot; airplane off fills
   the deck in place.
7. **Error mid-deck (3b).** With the API host blocked but the phone online (a router or VPN rule, or a proxy
   map to a dead host), swipe past the held cards. **Expect:** "Couldn't load more trades." with Try again, in the card slot; Back
   still works.
8. **R1 tap sites each land on a deck:** League Summary → a row's **Offer** and a row's **Target**; Usage Trends →
   a player's **Trade**; Team Review → **Find my trades** with a scoped partner; the deep link
   `dtf://app/trades/finder` (from Notes or Safari). **Expect:** each opens a deck that fills with cards; none
   hangs on "Looking for trades".
9. **League switch, then format switch.** Find a trade in league A and swipe a few. Switch to league B (League
   picker), then Find a trade. Then switch the scoring format (1QB ↔ SF) and Find a trade again. **Expect:** no
   card from league A ever shows in league B, and no card from the other format after the format switch,
   including the first card of the first tap. With C on, step C9 gives the observable proxy for this
   (release-lead P1-a).
10. **Named gate misses (#339 item 12; reachable once S0, #367, deploys).** Prod keeps
    `trade_gate_miss_mode` = 0 until 1.22.0 is distributed, so **force each state for your test league only**
    with S0's admin hook (release-lead or the operator runs it; it needs `CRON_SECRET`). **The hook applies to every
    member of that league, so use a league whose members are all operator test accounts:**
    `POST /api/admin/trades/gate-miss-test` `{"league_id": "<test league>", "kind": "check_error", "ttl_s": 600}`
    for the error, and `"kind": "withhold"` for the wait. `DELETE` with `{"league_id": …}` clears it, and it
    expires by itself after `ttl_s` (≤ 900). With `check_error` set, tap Find a trade. **Expect:** "Couldn't
    confirm current rosters" / "We couldn't check rosters with your league's platform. Try again." with
    **Retry** in the card slot, never "Search failed … waking up"; Retry starts a new search; Back works. While
    S0 is withholding cards for the check, **expect** "Checking current rosters with your league's platform…"
    in place of "Looking for trades…" (no seconds, no "Searching…"); if no card arrives within about 10 s it
    turns into the error above with Retry; if cards arrive, the deck shows them normally. (`withhold` keeps
    withholding until the hook expires or is cleared, so expect the 10 s fall-through to the error, then Retry
    restarts the wait.) **Always `DELETE` the hook when done.** Copy is placeholder (`trades.gate.*`, head-bizops
    due ~10-28).
11. **Known behavior to log (P2-b):** on the first ~10 s of a cold search, note any card that turns into "This
    trade is no longer available." right after appearing. E2's `replace` can withdraw a fronted card that a later
    server layer dropped; log how often, don't file it as a bug.

**A, lever off** (`model_config` `trade_paged_responses = 0`, PR #400; release-lead writes it, then
`reload_config`):
1. **A cold search still shows cards.** **Expect:** the deck appears with no push animation, in its wait state
   (the landing's page 1 is no longer adopted), then fills.
2. **The deck keeps filling** by the legacy poll. **Expect:** no "Finding more"; cards stream in as before.
3. **The end:** **Expect:** the pre-paging end — F10's "Deck done" summary (tally, "Fresh ideas land every
   week.", See liked / Done) after at least one pass or like, else the classic exhausted state. **Not** the P30
   card: P30 is paged-only in code (§1).
4. **C** (if its gate is on): no device card ever renders; the readout never says `device`.
5. **Flip back to 1** (`reload_config`): the next search pages again (steps A1–A2 behave as above).
6. **Mid-deck flip.** With the knob at 1, open a deck and swipe until a few pages have loaded (20+ cards). Set the
   knob to 0 (`reload_config`) and keep swiping to the end. **Expect:** no stuck "Updating", no "Couldn't load
   more trades" or Offline card, no repeated cards; the deck keeps filling while the job builds and finishes on
   the legacy end ("Deck done" or the classic exhausted state, step 3). Then flip back to 1.

**C — the device-held first page.** **Gate:** #367–#369 deployed and `trade.first_page_store` on; until then C is
inert and these steps don't apply.
1. **Warm tap within 5 min:** open the Acquire landing, wait 3 s, leave and come back or wait, then tap Find a
   trade within 5 min. **Expect:** the first card instantly (no wait card); "Updating" in the deck header
   briefly, then gone; Like and Pass work throughout; the readout (if mounted) ends in `device`.
2. **Tap after 6 min** on the landing with no refocus or foreground. **Expect:** the normal path (step A1); the
   readout says `page`, `cached`, `joined` or `fresh`, never `device`.
3. **Airplane mode with a page under 5 min old:** **Expect:** cards at once, plus "Couldn't refresh. These trades
   may be out of date." with Retry under the card; airplane off clears it after a brief "Updating".
4. **Airplane mode with no page** (just signed in, or older than 5 min): **Expect:** the Offline card at once in
   the card slot; reconnecting fills the cards in place.
5. **Roster move from another device**, then tap on A within 5 min: **Expect:** the moved player's card turns into
   "This trade is no longer available." / Next trade within about 1 s.
6. **Sign out, then sign in as another account:** **Expect:** no card from the first account; the first tap
   takes the normal path.
7. **Re-rank** (a trio or a tier save), then tap — also: open a deck, re-rank in another tab, come back, swipe one
   card, return to the landing and tap. **Expect:** no instant device card either way; the deck reflects the new
   ranks (release-lead P2-a).
8. **Pass two cards, go back, re-tap within 5 min:** **Expect:** the passed cards never reappear.
9. **League or format switch, the observable proxy** (release-lead P1-a). In format X, open the Acquire
   landing and a deck, so a device page for X is held. Switch the scoring format to Y (one you haven't searched
   in the last 5 min), **turn on airplane mode**, then go to the Acquire landing and tap Find a trade.
   **Expect:** the Offline card at once, **never instant cards**: instant cards here would be a device page
   written under Y from X's deck. Repeat with a league switch (league A → league B, B not searched in the
   last 5 min) instead of the format switch.
10. **Flag off:** **Expect:** identical to A.

**M:** **waits on #360** (onboarding-eng's mount of the readout row in Settings › Testing); until it lands there is
nothing to see. Then, with `testing.timing_readout` on for the device, tap Find a trade and check that Settings ›
Testing shows the last `ms_from_tap` with its network, launch state and serve source.

**AC-L1 itself** (p95 ≤ 200 ms, the scripted two-device session) is app-manager's device checklist (OA-6, 11-07 to
11-09; `docs/plans/org-bringup/leads/app-manager-200ms-checklist.md` in the org's working folder).
