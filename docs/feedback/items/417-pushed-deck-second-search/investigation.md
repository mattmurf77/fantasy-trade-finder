# FB-417 — investigation (2026-09-03)

**Report (operator, v1.16.14, screen TradeDeck):** "Starting a trade offer with a player
selected worked for the first offer and didn't include him for subsequent offers."
Clarified 2026-09-03: a decision was made on the first card; the second card presented did
not include the selected player.

## What the prod event stream shows (operator's account, 2026-09-02 UTC)

| Time | Event | Meaning |
|---|---|---|
| 22:03:06 | `calc_asset_added {side: give}` → `calc_find_a_trade_tapped {path: fair, give_count: 1, has_partner: false}` | Player 12514 on the canvas give side; Find a Trade forks to the fair sweep |
| 22:03:06 | `screen_viewed TradeDeck` · `find_trades_tapped {source: calculator}` | D-171 push; `runFairPackages` (TradesScreen.tsx:3528) dispatches the anchored sweep |
| **22:03:07** | **`find_trades_tapped {mode: deck}` — no `source`** | A SECOND search: the pushed page's own primary `trades.find-btn` (TradesScreen.tsx:7195 legacy arm, or :7400 via `handleFindTrades()`). Only those two emitters produce `{mode}` with no source. It fired ~1 s after the push, before the first fair card was even viewed |
| 22:03:07 | `trade_card_viewed {card_index: 0, trade_id: fairpk_bd69…}` | The fair deck lands; card 0 is anchored on 12514 |
| 22:03:12 | `trade_card_viewed {card_index: 0, trade_id: 8965c77f}` then `{card_index: 0, trade_id: b23268e4}` | Model cards stream in and take index 0 **without any swipe** — the deck re-sorted under the user |
| 22:03:17 | `trades_generated {count: 59}` | The unanchored model job the second dispatch kicked (started ~22:03:07) |
| 22:03:19 | `match_swiped pass b23268e4 give [12514]` | The "first offer" the operator decided on — a MODEL card that happened to give 12514 |
| 22:03:22 | `trade_card_viewed {card_index: 1, trade_id: afdd5509}` · 22:03:36 `match_swiped pass afdd5509 give [8112]` | The "second offer": Drake London, not 12514 |
| 22:04:06 | `feedback_submitted {screen: TradeDeck}` | This report |

Control: the 21:28:54 session (same flow, `has_partner: true`) and the 22:04:42 retry show
ONE `find_trades_tapped` and the fair card stays — no duplicate dispatch, no bug.

## Mechanism (code)

1. The pushed `TradeDeck` instance renders the always-mounted primary `trades.find-btn`
   labelled "Find a Trade" (`canvasHost !== 'flag'`, TradesScreen.tsx:7185-7200 and
   :7390-7402). On a fair deck `job` is null, so it is enabled and reads "Find a Trade" —
   an invitation to tap on a page that just searched. Whether the 22:03:07 tap was a second
   deliberate tap or a double-tap that landed on the pushed page's button at the landing
   button's position, the outcome is the same.
2. Its legacy arm (:7195) does `track → setPinIdeaResumed(false) → dispatchGenerate({})`
   with NO deck reset and NO `setFairDeck(false)`; the model job reads pins from the store
   (:1857), which the anchor path never writes, so the job is unanchored.
3. The streaming effect (:2137) APPENDS the job's cards to the existing fair deck. With the
   fairness toggle OFF (the 2026-08-17 default), `sortedDeck` (:3773) sorts by
   `match_score` desc; fair cards carry `match_score: 0` (utils/ideaToCard.ts) so every
   model card sorts ABOVE them and index 0 changes identity while the user is looking —
   exactly the two `card_index: 0` events at 22:03:12.
4. `fairDeck` stays true, so the "Built around <name>" receipt (`inlineAnchorShown`,
   :5775) keeps describing a deck that is now mostly the model's.
5. Nothing disables the button while the fair sweep is in flight: `disabled` reads
   `generateMutation.isPending || job?.status === 'running'` and the fair sweep sets
   neither.

## Recommended fix (mobile only, TradesScreen.tsx) — pending operator go

- On the pushed results deck (`isResultsPushed`) the primary `trades.find-btn` does not
  render while the deck is a fair deck: the receipt's Change/Clear and the end-of-deck
  exits ("Search all trades", "Back to calculator") are the search controls there.
- Any model dispatch from a fair deck goes through `handleFindTrades` semantics
  (`resetDeckForNewTargets` + `setFairDeck(false)`), so anchored and unanchored cards can
  never share a deck and the receipt cannot outlive it. Route the :7195 legacy arm through
  it.
- Track the fair sweep's in-flight state and include it in the CTA's `disabled`
  (double-tap guard).
- Guard: extend `mobile/tests/check-results-push.js` (sabotage-proven) for the three
  points above.
