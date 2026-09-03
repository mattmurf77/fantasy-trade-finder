# FB-417 — mini-PRD: the pushed anchored deck cannot start a second, unanchored search

**Date:** 2026-09-03 · **Entry point:** feedback #417 (operator, v1.16.14, screen `TradeDeck`)
**Path:** fast-track bug · **Branch:** `feat/fb417-pushed-deck-research`
**Scope block:** [scope.md](scope.md) · **Evidence timeline:** [investigation.md](investigation.md)
**Surface:** mobile only — `mobile/src/screens/TradesScreen.tsx`. No backend, no schema, no API, no flag.

## 1. Problem

The report: *"Starting a trade offer with a player selected worked for the first offer and
didn't include him for subsequent offers."* Clarified 2026-09-03: a decision was made on the
first card; the second card presented did not include the selected player.

The user's mental contract on a give-side anchored search is that **every** card in that deck
sends the player he put on the canvas. The deck stopped honoring it mid-session, while the
"Built around <name>" receipt at the top of the page still claimed it did.

## 2. Repro — from the prod event stream, not a guess

The full timeline is in [investigation.md](investigation.md). The load-bearing three rows
(operator's account, 2026-09-02 UTC):

| Time | Event | What it means |
|---|---|---|
| 22:03:06 | `calc_find_a_trade_tapped {path: fair, give_count: 1}` → `screen_viewed TradeDeck` → `find_trades_tapped {source: calculator}` | The D-171 push; the anchored sweep starts |
| **22:03:07** | **`find_trades_tapped {mode: deck}` — no `source`** | A SECOND search ~1 s later, before the first card was even viewed. Only the pushed page's own `trades.find-btn` emitted that shape |
| 22:03:12 | `trade_card_viewed {card_index: 0, …}` twice, two different `trade_id`s, **no swipe between them** | The deck re-sorted under the user: model cards took index 0 from the fair card |

The 21:28:54 and 22:04:42 sessions are the control — one `find_trades_tapped`, fair card stays,
no bug. The trigger is the second tap, not the sweep.

## 3. Root cause (pre-fix line numbers, `mobile/src/screens/TradesScreen.tsx` @ `c529abc8`)

1. **The pushed page renders an unanchored search button.** The always-mounted primary
   `trades.find-btn` ("Find a Trade") renders on the pushed deck in both arms of its ternary
   (:7185-7200 legacy `!consolidateOn`, :7390-7402 consolidated) — `canvasHost !== 'flag'` is
   the only gate and the pushed instance nulls `canvasHost`. On a fair deck `job` is null, so
   the button is enabled and reads "Find a Trade": an invitation to search, on a page reached
   by searching.
2. **Its legacy arm dispatched privately** — `track → setPinIdeaResumed(false) →
   dispatchGenerate({})` (:7195-7197): no deck reset, and (unlike `handleFindTrades` since
   #384 W6-B) no `setFairDeck(false)`. The job reads pins from the store, which the anchor
   path never writes, so the job is **unanchored**.
3. **The results merge.** The streaming effect appends the job's cards to the existing deck
   (:2137-2143). Nothing there distinguishes bases.
4. **And then outrank the fair cards.** With the fairness toggle OFF (the 2026-08-17 default)
   `sortedDeck` (:3773) sorts by `match_score` desc; fair cards carry `match_score: 0`
   (`mobile/src/utils/ideaToCard.ts`), so every model card sorts **above** them — index 0
   changes identity while the user is looking at it.
5. **The receipt outlives its deck.** `fairDeck` stays true on that path, so `inlineAnchorShown`
   (:5775) keeps saying "Built around <name>" over a deck that is now mostly the model's.
6. **Nothing blocked the tap.** `disabled` read `generateMutation.isPending || job?.status ===
   'running'`; the fair sweep is one synchronous request with **no job**, so both are false for
   the second it runs.

`handleFindTrades` (:1097) is only half-safe: it clears `fairDeck` but does **not** reset the
deck, so the same merge happens through it (the fair deck's own "Search all trades" exit and
the receipt's Clear both route there).

## 4. Requirements

**R-1 — the anchored pushed deck renders no page-level primary.**
While `isResultsPushed && fairDeck`, neither arm of `trades.find-btn` renders. Both mounts
still exist (this is a render gate, not a deletion): every other host and state renders the
button byte-identically — flag-off, the landing, team/player modes, and **model** decks on the
pushed page. Verified replacements on that page, post-change line numbers:

| Control | testID | Renders on the anchored pushed deck? |
|---|---|---|
| Receipt "Change" (:7760) | `trades.anchor-receipt.change` | Yes — `inlineAnchorShown` is `(canvasHost === 'flag' \|\| isResultsPushed) && fairDeck && !!inlineAnchor` (:5807); pops to the landing canvas that still holds the build (D-171 ruling 2) |
| Receipt "Clear" (:7786) | `trades.anchor-receipt.clear` | Yes — same gate; `onPress` is `handleSearchAllTrades` (:3670) verbatim, i.e. this IS the "search all trades" exit |
| "Back to calculator" (:8564, :8672) | `trades.deck-{summary,exhausted}.back-to-calc` | Yes — gated on `calcMergedOn` only |
| "Search all trades" (:8597, :8691) | `trades.deck-{summary,exhausted}.search-all` | Gated `fairDeck && !inlineAnchorShown` — it **stands aside while the receipt is up** (D-158: the receipt's Clear is the same action, and two copies on one screen is the same action twice). With a receipt: Clear is the exit. Without one (a push whose `anchorLabel` is null): this renders |
| Unpin-retry (:8580, :8680) | `trades.deck-{summary,exhausted}.unpin-retry` | No, by design — `!fairDeck` (#384 W5: a fair deck has no pins, the anchor rode the request body) |

So the anchored deck always has at least two live search controls and one exit; it is never
stranded. **Deliberate consequence:** `find_trades_tapped {mode: deck}` can no longer be emitted
from a pushed anchored deck — that emission was the bug.

**R-2 — a model dispatch never merges into a fair deck.**
Every path that can dispatch the model while `fairDeck` is true resets the deck first.
Implemented at the single shared entry point: `handleFindTrades` calls
`resetDeckForNewTargets()` when `fairDeck` (:1130), **before** `dispatchGenerate` (the reset
bumps `deckEpochRef` synchronously at :2893, and the dispatch's `onMutate` stamps the new
epoch — resetting after would kill the search it just started). Reset semantics: new epoch,
`deck` emptied, `deckIdx` 0, `job` null, `fairDeck` false, browse session killed — so the
receipt is gone and no fair card survives. Paths covered:

| Path | Covered by |
|---|---|
| `handleSearchAllTrades` (:3670) — the end-of-deck exit AND the receipt's Clear | Calls `handleFindTrades('deck_search_all')` |
| The legacy `!consolidateOn` CTA arm (:7251) | Re-routed: `onPress={() => handleFindTrades()}` — it can no longer drift from the consolidated arm, which already did this. Same event, same `{mode: deckMode}` shape (`handleFindTrades`'s no-`source` branch) |
| The prefs-changed strip, deck-error retry, unpin-retry | Already `handleFindTrades` |
| #186 keep-side (:3492-3493) | Already `resetDeckForNewTargets(); dispatchGenerate({});` |

**The reset does NOT clear the pin store.** `resetDeckForNewTargets` (:2890) touches deck state
only; pins are the user's targets and the next dispatch reads them out of the store. (A fair
deck has none anyway.) Pinned by assertion 8f.

**Non-fair decks are untouched:** the reset is behind `if (fairDeck)`, so a "Find more trades"
tap on a **model** deck still appends to the existing deck exactly as shipped.

**R-3 — the jobless sweep is not re-dispatchable while in flight.**
New state `fairSweepPending` (:776), armed at `runFairPackages`'s entry beside the epoch capture
(:3552) and disarmed at both of its exits **after** the `#330` epoch guard (:3584 success,
:3594 failure). `resetDeckForNewTargets` also disarms it (:2906), so a **superseded** sweep —
which must not touch the flag, and returns before both disarms — can never strand a control
disabled. Read by: both CTA arms' `disabled` (:7242, :7456) and the landing canvas cell, which
withholds its handler (:7667) because `disabled={!onFindATrade}` is that cell's own gate
(`mobile/src/components/InLeagueCalculator.tsx:1297`). No spinner added.

**R-4 — analytics: no new event.** `find_trades_tapped` keeps every shape it had. The legacy
arm's inline emitter is gone; the row it sent is now `handleFindTrades`'s no-`source` branch —
identical name, identical `{mode: deckMode}` payload, one emitter fewer (4 → 3). Hiding the CTA
on the anchored pushed deck removes the source-less `{mode}` emission **from that surface by
construction** — that emission was the defect, and no other surface changes.

**R-5 — no flag, no schema, no API.** `calc.results_push` remains the kill switch for this
whole surface; with it off, `isResultsPushed` is false and every predicate here is inert.

## 5. Out of scope

- Changing `sortedDeck`'s `match_score` ordering or giving fair cards a non-zero score — the
  ordering is correct once a deck holds one basis, which is what R-2 guarantees.
- Preventing a **double push** (two taps on the landing cell under the push posture pushing two
  `TradeDeck` instances). Not what the event stream shows (one `screen_viewed TradeDeck`), and
  the landing cell's guard here is inert under the push posture by D-171 ruling 1.
- A visible in-flight affordance for the fair sweep (spinner/progress). R-3 is a disable, not a
  new signal.
- Anything on the landing's own in-canvas browsing (`calc.canvas_results`, flag-dormant).

## 6. Guardrails honored

- **D-171 (2026-08-31, five verbatim rulings).** Ruling 2 keeps the anchor receipt on top of the
  pushed deck — this change makes the receipt's Change/Clear the page's search controls rather
  than one of three. Ruling 1 (landing = builder only) is untouched: the landing dispatches
  nothing under `resultsPushLive`. Ruling 5: ships LIT under `calc.results_push`, no new flag.
- **D-153 fork (#384 W6-B).** The fair/model fork still happens once, in
  `forkCanvasSearch`, before the push; `runFairPackages` still returns before the model gate.
  R-2 does not re-price anything — it only stops the two bases sharing one deck.
- **#330 R-10 epoch rule.** The reset's epoch bump is what makes the in-flight fair answer
  (or a superseded model job) drop on arrival; both new `fairSweepPending` disarms sit *after*
  the epoch guard for exactly that reason.
- **G-056.** No navigation verb was added or changed; `popTo` paths untouched.
- **Chalkline (ADR-004/005).** No copy, token, style or testID changed. `testid-lint` green.

## 7. Test plan

### 7.1 Structural guard (D-056 evidence)

`mobile/tests/check-results-push.js` § 8 — 18 new assertions (`8`, `8a`–`8q`; 23 printed lines), each proven red
by a named sabotage and restored green. Table in [build-notes.md](build-notes.md). Run:
`cd mobile && npm run test:results-push`.

### 7.2 Code-walk proof (post-change line numbers)

**(1) Pushed fair deck → no CTA.** `handleInlineFindATrade` (:3196) forks, then under
`resultsPushLive` pushes `TradeDeck` with `resultsPush.fairAnchor` (:3213). On the pushed
instance `isResultsPushed` is true (:846) and `canvasHost` is nulled by param presence, so
`canvasHost !== 'flag'` is true — the pre-#417 gate would render the CTA. The consumption
effect (:3161-3182) arms `fairAnchorRef`, the choke point (:3092) calls `runFairPackages`, whose
success path sets `fairDeck = true` (:3583). `findCtaHiddenForAnchoredDeck = isResultsPushed &&
fairDeck` (:5820) is then true, and both arms' gates (:7229, :7443) evaluate
`canvasHost !== 'flag' && !findCtaHiddenForAnchoredDeck` → **false**: neither Button mounts.
The receipt renders instead (`inlineAnchorShown`, :5807 → :7753).

**(2) Pushed fair deck → "Search all trades" → clean model deck.** The receipt's Clear (:7786)
presses `handleSearchAllTrades` (:3670) — `canvasResultsLive` is false on the pushed instance,
so it is the un-forked arm. It emits `deck_search_all_tapped`, then
`handleFindTrades('deck_search_all')` (:1108): `fairDeck` is true → `resetDeckForNewTargets()`
(:1130) bumps the epoch (:2893), empties `deck` (:2897), nulls `job`, sets `fairDeck` false
(:2902) and disarms `fairSweepPending` (:2906). `inlineAnchorShown` is now false → receipt
gone, and `findCtaHiddenForAnchoredDeck` false → the CTA returns for the model deck.
`dispatchGenerate({})` (:1134) runs under the new epoch, and the streaming effect (:2161-2164)
appends into an **empty** deck: model cards only. Same trace via the end-of-deck
`trades.deck-exhausted.search-all` (:8691) when no receipt is up.

**(3) Landing double-tap during the sweep → second tap ignored.** On the in-place posture
(`calc.canvas_results`, the kill-switch restore) tap 1 runs `handleInlineFindATrade` → choke
point → `runFairPackages`, which sets `fairSweepPending = true` at :3552 before its `await`.
The next render passes `onFindATrade={undefined}` (:7667), and `InLeagueCalculator:1297`
renders the cell `disabled={!onFindATrade}` with `styles.actionBtnDisabled` (:1318) and
early-returns in `onPress` (:1299). Tap 2 is inert. On arrival, :3584 (or :3594) disarms and
the cell returns. Under the **push** posture the same window is covered on the pushed page by
the CTA's `disabled` (:7242 / :7456), which is what the operator's 22:03:07 tap would have hit:
between the push and the first card, `fairDeck` is still false so the CTA renders — and
`fairSweepPending` is true, so it does nothing.

**(4) Pushed MODEL deck → "Find more trades" appends as before.** An empty canvas pushes with
`fairAnchor: null` (:3213), so the choke point takes the model arm and `fairDeck` is never set.
`findCtaHiddenForAnchoredDeck` is false → the CTA renders, labelled "Find more trades" once
`deck.length > 0 && job?.status === 'complete'` (:7235 / :7449, unchanged). Its press reaches
`handleFindTrades`, where `if (fairDeck)` is **false** → no reset → `dispatchGenerate({})`
streams the new job's cards onto the existing deck via :2160-2164. Byte-identical to shipped.

### 7.3 Manual TestFlight checklist (operator)

Build with `calc.results_push` on (its shipped default). In-league, Trades tab.

1. On the Trades landing, put **one** player on the **give** side of the canvas. Leave the
   receive side empty. Tap **Find a Trade** in the canvas action row.
2. On the deck page that opens: confirm the "Built around <name>" receipt is at the top **and
   that there is no full-width "Find a Trade" button anywhere on the page.** (Pre-fix there was
   one, under the deck.)
3. Immediately (within a second of the page opening) tap where that button used to be, twice.
   Nothing should happen — no second search, no progress strip.
4. Swipe through the whole deck. **Every** card must send the player from step 1.
5. Decide on card 1 (swipe pass or like). Confirm card 2 still sends that player — this is the
   exact regression reported.
6. Tap **Clear** on the receipt. Expect: the receipt disappears, the deck is replaced (not
   appended to) by model cards, and the "Find a Trade" / "Find more trades" button is back.
7. Tap it once. Expect a normal model search; when it completes, tap **Find more trades** and
   confirm cards are **added** to the deck (count grows, position keeps).
8. Go back to the landing (back arrow). Confirm the canvas still holds the player from step 1.
   Tap **Find a Trade** again → a fresh anchored deck, receipt present, no CTA.
9. Repeat step 1 but with the **Team** dropdown set to a specific league-mate — same
   expectations (the scope rides the push).
10. Empty the canvas entirely, tap **Find a Trade** → a model deck on the pushed page **with**
    the CTA present and working (this is the state R-1 must not touch).

Log the outcome in `living-memory/TEST_LEDGER.md`.

## 8. File ownership

| File | Change |
|---|---|
| `mobile/src/screens/TradesScreen.tsx` | R-1/R-2/R-3 — the only source file touched |
| `mobile/tests/check-results-push.js` | New § 8 (18 assertions) + one re-spec |
| `mobile/tests/check-inline-home.js`, `check-canvas-results.js`, `check-offer-prefill-330.js`, `check-analytics-297-302.js` | Declared re-specs only (see build-notes.md) |

Not touched, by instruction: `mobile/src/components/ShopOffersBody.tsx`,
`mobile/tests/check-shop-deck.js` (owned by #418).
