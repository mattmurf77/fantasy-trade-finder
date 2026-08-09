# #286 — Balanced upgrade/lateral/downgrade alternates; player-offers flow becomes an editable calc

**Status:** in-progress · 2026-08-09 · branch `worktree-agent-a481844ff0482699e` · flag `trades.player_offers_calc`

Also covers **#287** and **#288** (multi-ID fix, lowest ID per
`docs/feedback/items/README.md`) — all three are one commit against the same
flow: the path from a found trade card to "other options for that player".

Operator reports (verbatim):

> #286: "When I hit more trades the alt trade options are only trade down ideas."

> #287: "Routing from a found trade to other options for that same player
> should have the same trade calc experience. The player specific offers
> page I'm brought to is the older tile design where I can't edit any
> players. Let's keep the calc UI consistent."

> #288: "add a back button to the newly routed page so I can go back to the
> original offer suggestion. Or present the player to easily x out in the ui
> presentment (outside of change link)."

## The flow, as shipped

Tapping **"Keep · more offers"** on a found trade card's give or receive side
(`TradeCard.tsx`'s `keepSlot`, `TradesScreen.handleKeepSide`) pins that
side's player(s) into `useFinderTargets` and regenerates. When exactly one
asset ends up pinned, `TradesScreen`'s `singlePin` derivation activates
**single-pin featured mode**: the swipe deck hides, the Controls Card
collapses to a one-line pin summary, and two things mount instead —

- `FeaturedTradeWindow` — the best Upgrade/Lateral/Downgrade idea from
  `POST /api/trades/asset-ideas`, rendered as a full trade card ("Featured
  trade").
- `AssetIdeasPanel` — the grouped "More trades for `<pin>`" list beneath it;
  tapping a row swaps a different idea into the window.

This is also the surface the hub's "Specific Player" card and the player-mode
TRADE AWAY/TRADE FOR board land on — anywhere exactly one asset gets pinned.

## #286 — root cause and fix

**Root cause:** `TradeService.generate_asset_ideas`
(`backend/trade_service.py`) classifies each candidate deal into
Upgrade/Lateral/Downgrade around the pin's consensus value
(`asset_ideas_lateral_band`), and each group is capped independently
(`asset_ideas_group_cap`) — so the final selection step was never crowding
one class out for another. The skew traces one level deeper, to package
pricing:

- The test suite (`backend/tests/test_asset_ideas.py`) pins
  `stud_tax_override("heavy")` — the pre-#214 legacy package-value math —
  because that's what the tests were originally authored against.
- **Production defaults to `'market'` mode** (`stud_tax_mode_for_user`),
  which prices a multi-piece package differently: the depth-discount
  benchmarks against the package's OWN best asset (not a trade-wide max),
  and the "crown" premium that lets one pricier single asset outweigh
  several lesser pieces only fires when the received single asset clears
  `crown_elite_value` (≈6000 — an ultra-elite absolute threshold most pinned
  players never approach).
- Net effect: for a typical (non-elite) Upgrade candidate, there is a real
  but narrow `give_value` window between "still underpaying" (fails the
  fairness floor) and "now overpaying" (fails the never-relaxed #108
  `user_gain_epsilon` gate). The give-direction Upgrade branch and the
  receive-direction Tier-UP branch each tried only **one** extra sweetener
  piece at a time — a blunt instrument that often can't land inside that
  window even when the roster holds pieces that COULD, combined. The
  Downgrade branch, by contrast, already searches 2–3-piece combinations
  (`combinations(down, r)` for `r in (2, 3)`) across a pooled candidate set,
  so it reliably finds a passing package. Zero test coverage existed for
  this asymmetry under the production-default mode — `test_asset_ideas.py`
  only ever exercised `'heavy'`.
- This was reproduced directly (not just theorized): a small `TradeService`
  fixture run under `stud_tax_override("market")` returns `upgrade: []`
  while `lateral`/`downgrade` populate, for both `direction="give"` and
  `direction="receive"` — matching "only trade down ideas" exactly.

**Fix (surgical, `backend/trade_service.py`,
`_generate_asset_ideas_impl`):** widened the give-direction Upgrade branch
and the receive-direction Tier-UP branch to also search 2-sweetener
combinations (`combinations(sweeteners[:_POOL], 2)`), bounded to the same
`_POOL` cap the Downgrade branch already uses — the identical combinatorial
breadth Downgrade gets, not a relaxed gate. No change to `package_value_v2`,
the shared valuation engine, or any never-relaxed gate; blast radius is
contained to asset-ideas classification. Unflagged (bug fix).

**Test:** `backend/tests/test_asset_ideas.py` gained
`test_give_direction_balanced_mix_under_market_mode`,
`test_give_direction_upgrade_needs_paired_sweetener` (regression guard
proving the paired search is load-bearing — no single sweetener in the
fixture clears the window alone) and
`test_receive_direction_balanced_mix_under_market_mode`, all running under
the **production-default `'market'` mode** (not the file's `'heavy'`
override) — each constructs a pool with genuine candidates in all three
classes and asserts the returned mix isn't single-class.

## #287 — player-offers surface becomes an editable calc

**Fix:** `FeaturedTradeWindow.tsx` gained an optional `calc?: { userId }`
prop. When set, it renders the featured idea as an
**`InLeagueCalculator`** — the same reuse the `TradeBuildCanvas` prefill
technique already shipped (`docs/feedback/items/270-inline-trades-home/`):
remounted per idea via a `key={assetIdeaKey(idea)}`, with
`initialOpponentId`/`initialGiveIds`/`initialReceiveIds` set from the idea
— instead of the read-only `TradeCard`. `InLeagueCalculator` "owns all state
after mount," so a new idea needs a fresh instance, not a prop update
(identical to how the deck's own "Edit in calculator" hand-off and
`TradeBuildCanvas`'s suggestion rail work). Add/remove players, eveners,
lineup impact and tier chips all work in place.

`TradesScreen.tsx` passes `calc={playerOffersCalcOn ? { userId } : undefined}`.
`AssetIdeasPanel` (the Upgrade/Lateral/Downgrade rail) is unchanged — it's
already a pickable list; picking a row still swaps the featured idea, which
now remounts the calculator instead of swapping a read-only card. No second
calculator implementation — this is the SAME `InLeagueCalculator` the pushed
`TradeCalculatorScreen` and `TradeBuildCanvas` already mount.

**Flag:** `trades.player_offers_calc`, 4-touch, **ships ON**:
`backend/feature_flags.py`, `config/features.json`,
`backend/tests/fixtures/flags/release.json`, `docs/config-reference.md`.
Off ⇒ `FeaturedTradeWindow.tsx` renders byte-identical to today (read-only
`TradeCard` + the `onEditInCalculator` push to `TradeCalculatorScreen`).

## #288 — back / clear-pin affordance

**Navigation shape:** entering single-pin mode is an **in-place state
transition**, not a screen push — there's no route to pop back to. The
existing `FeaturedTradeWindow.onBack` chip ("‹ Previous trade") already
covers swapping BETWEEN ideas within one pin's history; it does not unpin or
leave single-pin mode. Before this fix there was no way out of single-pin
mode at all short of expanding "Edit" and manually removing the pin from the
TRADE AWAY/TRADE FOR board (the "change link" the operator's second option
explicitly called out as insufficient).

**My call:** built the **X on the pinned player chip**
(`trades.pin-summary.clear`, always visible in the collapsed pin-summary
row) as the primary affordance — it's honest about the actual navigation
shape and never dead-ends. On top of that, since `handleKeepSide` (the
literal "found trade card → other options for that player" entry point the
ticket names) wipes `deck`/`deckIdx`/`job` via `resetDeckForNewTargets`
before regenerating, clearing the pin from THAT entry point restores the
**exact original deck position and card** — `preSinglePinSnapshotRef`
captures `{deck, deckIdx, job}` immediately before the pin is set, only when
entering from a clean (unpinned) deck, and `handleClearPin` restores it.
Pins entered any other way (the player-mode target board, the DNA sheet's
"Specific players" add) have no snapshot to restore — clearing still unpins
and leaves the ordinary empty-deck state, where "Find a Trade" is always the
recovery path, so the user is never stranded either way. This single X
satisfies both halves of the ticket ("and/or") without two separate
controls.

**Scope:** #288 rides the existing pin-summary/single-pin machinery, not the
new #287 calc presentation — it's a fix to a pre-existing gap (no way out of
single-pin mode), not new UI introduced by #287. **Unflagged.**

## Gates

- `python3 -m pytest backend/tests -q` — **2075 passed, 1 skipped** (baseline
  2072 passed / 1 skipped + 3 new `test_asset_ideas.py` tests). No
  regressions.
- `cd mobile && npx tsc --noEmit` — clean (via the documented node_modules
  symlink from `.claude/worktrees/agent-a16b8c9e20f110454/mobile/node_modules`,
  removed after).
- `mobile/scripts/testid-lint.sh` — `testid-lint OK`.

## Files touched

- `backend/trade_service.py` — #286 fix (paired-sweetener search, both
  directions).
- `backend/tests/test_asset_ideas.py` — #286 balanced-mix tests under
  production-default `'market'` mode.
- `backend/feature_flags.py`, `config/features.json`,
  `backend/tests/fixtures/flags/release.json`,
  `docs/config-reference.md` — `trades.player_offers_calc` 4-touch.
- `mobile/src/components/FeaturedTradeWindow.tsx` — #287 `calc` prop.
- `mobile/src/screens/TradesScreen.tsx` — #287 flag wiring; #288 deck
  snapshot + `handleClearPin` + pin-summary X button.
