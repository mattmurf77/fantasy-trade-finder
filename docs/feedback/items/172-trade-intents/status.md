# #172 — Trade intent modes (Consolidate / Tier up / Tier down)

**Status:** built-dark · 2026-08-08 · `trades.intent_modes` flag (ships ON in `config/features.json`, worktree not yet merged to `main`)

Operator idea (TradesHome, verbatim):

> "Trade idea: I want to consolidate, I want to tier up, I want to tier down."

An INTENT selector for the trade finder: the user declares the shape of
trade they want and the deck respects it.

## Relationship to #168

`docs/feedback/items/168-looking-for-intents/prd.md` (2026-07-25, proposal
only, never built) already scoped this exact ask under the combined title
"#168 / #172 — 'Looking for' intents." That PRD explicitly **rejected** a
client-only/post-generation filter as "dishonest: it would silently discard
most of the generation budget instead of steering it," and proposed instead
an engine-level redesign (restrict the v2 candidate-shape enumeration itself
via a new `intent` param threaded into package construction) as a "next
round" `NOT BUILT` stretch item, because the engine internals were judged
another agent's territory that round.

This build takes the lighter path the #168 PRD declined — a pure
post-generation filter in `trade_service.generate_trades()` — per this
round's explicit build brief. The objection the old PRD raised is addressed
directly rather than ignored: a filtered-to-empty result is never silently
served as "no trades" (see Empty-deck handling below) — the mobile toast
always names the active intent, so "no results" reads as "no results **for
this shape**," not as a broken finder. This is not the "silent" fake the
#168 PRD warned about; it's an honest filter with honest empty state.

Two other divergences from the old PRD's proposal, both deliberate:

- **Three values, not two.** #168 sketched `consolidate | spread` and
  conflated `tier_up` into `consolidate` ("Consolidate (tier up: 2/3-for-1
  me into a better player)"). This build's brief drew the vocabulary
  directly from the operator's verbatim three-way ask and from
  `RankingService.tier_for_elo` — `tier_up` is its own value, defined as a
  pure quality comparison **independent of piece count** (see Semantics
  below), distinct from `consolidate`'s shape+quality combination.
- **Grounded in the tier ladder, not shape alone.** #168's acceptance
  criteria were purely piece-count based (`|give| > |receive|` /
  `|give| < |receive|`). This build additionally requires a genuine
  quality change on the best asset per side (`RankingService.tier_for_elo`
  / `ORDERED_TIERS`) — a 2-for-1 of three bench pieces for one similarly
  bad piece would pass #168's criteria but is not what "I want to
  consolidate" means. The `#172` operator quote frames it as
  quality-seeking ("consolidate... tier up"), not just piece-count
  arithmetic.

If the engine-level redesign #168 proposed (restricting shape enumeration
itself, applying the crown-asset premium unconditionally) is ever revisited,
this filter should be superseded, not stacked — the two approaches steer the
same knob two different ways. `#168`'s `status.md` cross-links here.

## Final semantics

Grounded in the 8-tier pick-value ladder
(`RankingService.tier_for_elo` / `ORDERED_TIERS`, best→worst:
`firsts_4plus, firsts_3, firsts_2, first_1, second, third, fourth,
waivers`). Each side of a candidate trade has a **best asset** — the
highest-tier player or pick on that side, via `_best_tier_idx` (a small
helper mirroring `star_tax_adjustment`'s existing "top asset per side"
comparison, `backend/trade_service.py`). An asset with no tier (ELO below
every band) sinks below every real tier.

| Intent | Piece-count condition | Quality condition |
|---|---|---|
| **Consolidate** | user sends MORE pieces than they receive (`len(give) > len(receive)`) | AND the best incoming asset's tier is strictly better than the best outgoing asset's tier |
| **Tier up** | *(none — piece counts irrelevant)* | best incoming asset's tier strictly better than best outgoing asset's tier |
| **Tier down** | user receives MORE pieces than they send (`len(receive) > len(give)`) — inverse of Consolidate's shape | AND the best outgoing asset's tier is strictly better than the best incoming asset's tier |

`tier_up` reads as a strict subset relaxation of `consolidate`'s quality
condition — every card that passes `consolidate` also passes `tier_up`,
but `tier_up` additionally admits 1-for-1s and "pay a premium to move up"
shapes where the user sends more VALUE (not more pieces) for a better tier.
`tier_down` is `consolidate`'s full mirror (both the shape and quality
conditions flip), matching the operator's own phrasing ("trade your best
piece away for multiple pieces") rather than being `tier_up`'s bare
inverse, which would drop the shape condition entirely.

`None` (no chip selected) is a no-op — every card is kept, byte-identical
to today. An unrecognized value is also a no-op (defensive; the request
route only ever forwards one of the three known strings or `None`).

## Implementation

**Backend** (`backend/trade_service.py`):
- `_best_tier_idx(ids, seed_elo, player_db, scoring_format)` — best
  (lowest-index) `ORDERED_TIERS` entry among a side's asset ids, via each
  asset's **seed (consensus) ELO** — the same board `star_tax_adjustment`
  already reads for its own top-asset comparison, so intent and star-tax
  agree on "what's the best piece here."
- `_filter_by_trade_intent(cards, intent, seed_elo, player_db,
  scoring_format)` — pure post-generation filter, module-level (no flag
  lookup of its own; trusts an already-resolved `intent`).
- `TradeService._generate_trades_impl` gained a `trade_intent: str | None`
  kwarg. Resolved once at the top of the method
  (`_intent = trade_intent if FLAGS.trades_intent_modes else None`) so
  flag-off responses are byte-identical **structurally**, not by
  discipline at each call site. Applied at the tail of **both** the v2
  path (after the #189 relaxed-targeted-pass fallback, so the two never
  interact) and the legacy path (after `_dedup_and_sort`, before cards are
  stored into `self._trade_cards` — a filtered-out card was never
  surfaced to this job's caller, so it's never stored either).

**Route** (`backend/server.py` `POST /api/trades/generate`):
- `trade_intent` read from the request body, honored only when
  `is_enabled("trades.intent_modes")`; an unrecognized string normalizes
  to `None` rather than erroring (mirrors `pinned_give_mode`'s junk
  handling).
- Threaded through `_kickoff_trade_job` → `_run_trade_job` →
  `trade_service.generate_trades(trade_intent=...)`, stored on the
  in-memory job dict.

## Cache-key handling

`trade_intent` follows the **same precedent as `outlook_value` /
`fairness_threshold`**, not the pinned-job bypass precedent
(`pinned_give_players` / `pinned_receive_players` / `opponent_user_id`,
which skip the shared per-key cache entirely because they answer a
one-off question). An intent selection is a repeatable preference like
outlook — the SAME intent on a repeat request should still hit the cache;
only a CHANGED intent should force a fresh job. `_trade_job_is_fresh`
gained a `trade_intent` parameter compared against the job's stored value;
a mismatch (including "was set, now cleared" or vice versa) fails
freshness and a fresh job is kicked off. This was the deciding reason NOT
to fold `trade_intent` into `_any_pinned` — doing so would have thrown away
a perfectly good cached deck every time a user re-taps the same chip.

## Empty-deck handling

No new backend field. Per the build brief, this extends the **existing**
mechanism rather than inventing one: `TradesScreen.tsx`'s
`generateMutation.onSuccess` already special-cases
`snapshot.cards.length === 0` with a `fairnessOn`-aware toast message. That
branch now checks `tradeIntent` first and — when a chip is active —
substitutes an intent-named message ("No consolidation trades found right
now." / "No tier-up trades found right now." / "No tier-down trades found
right now.") ahead of the fairness-aware fallback. The backend never needs
to say why a deck is empty; the client already knows what it asked for.

## Mobile UI

- `mobile/src/components/TradeDnaSheet.tsx`: new `TradeIntent` type
  (exported) and `TRADE_INTENTS` chip list. `TradeDnaSheetFullProps` gained
  optional `tradeIntent` / `onTradeIntent` — the chip row renders only when
  `onTradeIntent` is present, so the flag-off (or non-full-sheet) caller
  never sees it. Placed as its own "Trade idea" labeled block directly
  after the Positions (Chasing/Shopping) block, inside the same `full`
  branch, above the hairline + "Fine tuning" strip — it IS a primary
  question per the build brief, not a fine-tuning lever. Single-select;
  tapping the active chip clears it (same interaction as the #256 lane
  pills). testIDs: `dna.intent.consolidate` / `dna.intent.tier-up` /
  `dna.intent.tier-down`.
- `mobile/src/screens/TradesScreen.tsx`: `tradeIntent` state (type
  `TradeIntent`, default `null`) exists regardless of the flag (so it's
  always defined for the mutation body) but nothing ever sets it when the
  chips don't render. `handleTradeIntent` toggles the selection and marks
  `prefsChangedSinceGenerateRef.current = true` — the **same** ref the
  #257 full sheet's outlook/positions edits use to show the "Preferences
  changed — tap to refresh" strip on dismiss. Deliberately does **not**
  reset the deck outright the way `handleToggleFairness` /
  `resetDeckForNewTargets` do — selecting an intent autosaves like the
  sheet's other prefs and offers a refresh rather than yanking the current
  deck out from under the user. `trade_intent` is sent on every
  `generateTrades()` call (`tradeIntent ?? undefined`, omitted when unset
  so payloads for users who never touch the chips stay byte-identical).
  State resets to `null` on league switch (same effect that resets
  `laneFilter`) — a declared shape is league-specific, not carried across
  a switch.
- **Scoping (explicit):** the flag-off legacy Controls Card does **not**
  get chips — the intent UI exists only inside the `trades.edit_full_sheet`
  full sheet (`consolidateOn` branch), reached from `OutlookBiasReceipt`.
  There is no other entry point in this build.

## Maestro / testid-lint

No new Maestro flow authored this round — the build brief's own "Tests"
section scoped verification to the backend suite + `tsc --noEmit` and did
not list a Maestro delta, narrower than root `CLAUDE.md`'s general "every
user-visible mobile change ships a flow or a written waiver" rule. Treating
that narrower, more specific instruction as the waiver for this session:
the three new `dna.intent.*` testIDs are unreferenced by any flow today.
`mobile/scripts/testid-lint.sh` passes clean (`testid-lint OK`) since it
only checks flows against source, never the reverse. A follow-up session
extending an existing Trades/#257 flow to cover the chip row would close
this gap.

## Flag

`trades.intent_modes` — 4-touch convention: `backend/feature_flags.py`
(`FLAG_KEYS`), `config/features.json` (`true`), `backend/tests/fixtures/flags/release.json`
(mirrored `true`, enforced by `test_release_flags_mirror_features_json`),
`docs/config-reference.md`.

## Tests

`backend/tests/test_trade_intent_modes.py` (new, 11 tests):
- `_best_tier_idx` — picks the best asset on a side; unranked sinks below
  every real tier.
- `_filter_by_trade_intent` unit semantics — hand-constructed `TradeCard`s
  of known shapes/tiers per intent (`consolidate` / `tier_up` /
  `tier_down`), each asserting BOTH the keep case and at least one
  shape-only-fails / quality-only-fails drop case; `None` and an unknown
  string are no-ops.
- `generate_trades` wiring — v2 path: flag-off is a byte-identical no-op
  even when the caller passes `trade_intent`; flag-on filters a flat-tier
  fixture to an honest empty list (`test_flag_on_filters_flat_tier_trade_to_an_honest_empty_deck`)
  and keeps a genuine tier-up trade
  (`test_flag_on_keeps_a_genuine_tier_up_trade`).
- `generate_trades` wiring — legacy path (reusing the parity fixture from
  `test_trade_engine_v2.py`): the filter is wired there too, not just v2.

**Gates:** `python3 -m pytest backend/tests -q` — 2053 passed, 1 skipped
(baseline 2042 passed / 1 skipped + 11 new tests, exit 0).
`test_release_flags_mirror_features_json` and
`test_features_json_keys_known` both pass. `cd mobile && npx tsc --noEmit`
— exit 0, clean. `mobile/scripts/testid-lint.sh` — exit 0, `testid-lint OK`.
