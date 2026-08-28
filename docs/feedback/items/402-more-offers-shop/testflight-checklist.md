# TestFlight checklist — #402/#403 "More offers = shop a player"

> **Operator, on the first build carrying branch `claude/new-feedback-71436e`
> (commits `5115265b` + `4b71f036` + `bc21ee0f` + `472f6649`).**
> Under D-056 this checklist is the ONLY runtime evidence mobile gets — every
> step names the regression it would catch. The feature ships **dark**
> (`trade.shop_asset: false`); Part A needs the flag flipped on (plus
> `trade.asset_ideas` already true) via `config/features.json` +
> `POST /api/feature-flags/reload`. Part B is run with the flag OFF.

## Part A — flag ON

1. **Entry, one give asset.** On the Trades deck, the button under the players
   you send reads **"More offers"** (not "Keep · more offers"); under the
   players you get it still reads **"Keep · more offers"**. Tap the give-side
   button on a card with ONE give asset → the shop strip opens directly
   below the card; the deck did NOT clear or regenerate. ☐
2. **Entry, several give assets.** On a card sending 2+ assets, the same tap
   opens a **"Shop which player?"** sheet listing every give-side asset
   (players and picks). Cancel closes it with no other effect; picking a row
   opens the strip for that asset. ☐
3. **The deck holds still — all three ways.** With the strip open: (a) try to
   swipe the card — it must not move; (b) the card's own Pass/Like buttons
   render dimmed and do nothing; (c) **VoiceOver on**: the card's rotor
   offers NO like/pass actions while the strip is open. Close the strip →
   all three come back. *(QA B-1 — the buttons and VoiceOver were live in
   the first build.)* ☐
4. **Modes and counts.** Strip header reads "Shopping <name>" with a ✕. Three
   chips — Tier up / Tier down / Same value — each with a live count.
   Tier up is selected on open. A zero-count mode shows named copy (e.g.
   "No tier-down offers cleared the bar") and the pointer line renders ONLY
   if another mode actually has offers. ☐
5. **The pager is honest.** Swipe horizontally through the tiles; the
   "1 / X" counter tracks exactly, X = tiles actually present. Reaching the
   end does not advance, dispose, or wrap. ☐
6. **Like = a real offer.** Tap ✓ on a tile → success toast; the same trade
   appears queued (check the counterparty flow you normally use). Tap ✓ on
   the SAME tile again → the same success copy (idempotent), not an error.
   A refusal (e.g. an untouchable involved) names the reason, never a
   generic failure. **Ruled: this like DOES move your Elo board.** ☐
7. **Dismiss + Undo, the honest version.** Tap ✕ on a tile → it leaves the
   pager, X drops, "Dismissed · Undo" toast appears. Tap **Undo** within
   5 s → the tile returns exactly where it was, counter restored. ☐
8. **Undo never lies.** Dismiss a tile, then immediately tap a different
   mode chip → the Undo toast disappears AT THAT MOMENT (the dismiss is
   committed; a dead Undo button must never linger). *(QA B-4.)* ☐
9. **Positions (Same value).** Chips show every league position EXCEPT the
   shopped player's own position; no PICK chip; hint line reads "Positions
   offered back · <POS> is where he plays — leave all clear for
   same-position swaps". Select one position → ideas re-sweep to that
   position; select none → same-position swaps return. A filtered zero
   result shows "Nothing at <positions>" with a **Clear positions** button
   that works (and shows the unfiltered count when known). ☐
10. **Shop a pick.** Open shop on a card whose give side is a draft pick →
    the strip works but NO position chips render in Same value (the engine
    ignores them for picks; dead chips would lie). ☐
11. **Context death closes the strip.** With the strip open: switch leagues →
    strip gone. Open it again, then trigger any deck regeneration (e.g.
    change the fairness toggle or run a new search) → strip gone, new deck
    swipes normally. *(QA B-2 — the first build left an orphan strip over a
    fresh deck with its swipe dead.)* ☐
12. **Shop a different player without closing.** Shop player A, select a
    position filter, close nothing; shop player B directly from a new card →
    the strip resets (Tier up, no position selection, page 1). *(QA/A-2 —
    a stale filter could become invisible and un-clearable.)* ☐

## Part B — flag OFF (flip back, reload flags)

13. **Byte-identical deck.** Both keep buttons read "Keep · more offers";
    the give-side tap pins your players and regenerates the deck exactly as
    before this build (progress state, then a re-shopped return side; the
    pin summary row appears; clearing the pin restores the prior deck). ☐
14. **No shop anywhere.** Nothing labeled "Shop", no strip, no chooser, on
    any screen. ☐

## Known-open at checklist authoring (not blockers for a dark merge)

- **B-3 (unfixed by operator selection):** within 60 s, switching position
  filters away and back can briefly resurrect a dismissed tile from cache;
  it is already permanently passed server-side. If you see it in step 9's
  flow, that is the known issue.
- **Own-position chip ruling open:** "WR swaps plus RB swaps" is not
  expressible — the shopped player's own position is never offered as a
  chip (mockup and LLD disagree; awaiting ruling).
- P-1..P-4 runtime concerns from QA reviewer B (pager/counter desync on
  last-tile undo; dismiss-vs-sweep race; doubled `shop_opened` on chooser
  entries; `calc.merged_layout` must stay ON for the ✓ to queue).
