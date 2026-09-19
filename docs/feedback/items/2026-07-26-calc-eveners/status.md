# Calculator eveners — "Recommended to even it" (DynastyGM teardown parity)

- **Source:** `docs/business/product/2026-07-26-dynastygm-app-teardown.md` — Trades tab / Team Calc: "RECOMMENDED" evener rows with + buttons when a trade is uneven (gap 7 in the FTF-vs-DynastyGM list). Operator-approved replication for FTF's calculator.
- **Status:** BUILT + verified 2026-07-26 (branch `teardown-remediation`, isolated worktree). Not flag-gated — additive server field + client rows that only render when the server sends candidates; old servers/clients degrade silently.

## What shipped

### Backend — additive `eveners` on `POST /api/trade/evaluate` (`backend/server.py`)

Present only on an uneven two-sided read (`favors` ≠ `even`, `gap.add_to` set). Eveners belong to the side `gap.add_to` points at — the WINNING side (receives more) adds to what it gives: `add_to='give'` → the caller's roster, `'receive'` → the opponent's.

- **Mode B** (`_roster_eveners`): candidates = that owner's `league_members` roster players (universal-pool priced via the route's `seed_value`) + their owned picks from the #158 `draft_picks` store (`pool_value`; label via `_owned_pick_label`, `position: "PICK"`, `is_pick: true`). Window 0.4×–1.5× of `gap.value`, closest-to-gap first, cap 3. Assets already in the trade are excluded. The roster owner's untouchables (`asset_preferences`, keyed per user+league — so knowable for caller AND counterparty) are never recommended.
- **Stretch (2-piece package):** at most ONE combo row appended after the singles — pairwise scan over the top-15 sub-gap assets from the same pool; combined (additive) value must land in the same window; closest wins. Shape `{id: "a+b", ids: [a, b], name: "X + Y", position: "PKG", value: sum, is_package: true}`. Value is additive, not package-shrunk — the client re-evaluates on add, so the verdict stays server-authoritative.
- **Mode A** (rosterless open calculator): one-element list containing the `gap.pick_equivalent` generic pick (`generic_pick_*` — a real `/api/trade/values` pool id the client can add; never fabricated). `[]` when the gap has no single-pick equivalent or the pick already rides in the trade.
- Build failures log + omit the field; they never fail the route. No engine changes.

### Client (mobile)

- `mobile/src/api/calc.ts` — `CalcEvener` type + `eveners?` on `CalcEvaluation`.
- `mobile/src/components/EvenerRows.tsx` — NEW shared rows component (spec in `docs/design/components.md` → Meters & progress). testIDs `calc.evener.<id>` / `calc.evener-add.<id>`. Chalkline: ink-1 rows, ice-bordered + button (ice = action), PositionChip (`PICK`/`PKG`), honest empty (renders nothing without candidates).
- `mobile/src/components/InLeagueCalculator.tsx` — renders EvenerRows under the two-board verdict; + adds to the `gap.add_to` side (dupe-guarded) and the debounced evaluate re-run refreshes/clears rows. Coexists with the #78/#88 confirmed balance suggestions (left untouched).
- `mobile/src/components/ConsensusVerdictCard.tsx` — optional `onAddEvener` prop; rows render inside the card ("add to Side A/B"). `mobile/src/screens/TradeCalculatorScreen.tsx` — minimal wiring only (passes the handler in live mode).

## Verification

- `python3 -m pytest backend/tests -q` → **1194 passed, 1 skipped** (evaluate file alone: 23 passed).
- New tests in `backend/tests/test_trade_evaluate.py`: caller-side sourcing + window/cap/order + caller-untouchable exclusion + 2-piece combo (`test_mode_b_eveners_from_callers_roster_when_caller_wins`), owned-pick inclusion/label (`test_mode_b_eveners_include_owned_picks`), opponent-side sourcing (`test_mode_b_eveners_from_opponents_roster_when_opponent_wins`), absent-on-even (`test_mode_b_eveners_absent_on_even_trade`), in-trade exclusion (`test_mode_b_eveners_exclude_players_already_in_trade`), Mode A generic pick (`test_mode_a_evener_is_the_gap_generic_pick`), Mode A empty beyond ladder (`test_mode_a_eveners_empty_when_gap_beyond_pick_ladder`), Mode A absent even/one-sided (`test_mode_a_eveners_absent_when_even_or_one_sided`).
- `cd mobile && npx tsc --noEmit` → clean.

## Notes / follow-ups

- Counterparty untouchables ARE knowable (asset prefs are stored server-side per user+league), so they're respected on both sides — not just the caller's.
- The package row's `value` is the additive sum, not `package_value_v2`-shrunk; the post-add server re-evaluation is the source of truth. If the shrink gap ever misleads, price combos through `_consensus_packages` server-side.
- Mode B eveners are consensus-priced (like `gap` itself); a divergence-basis variant (pick eveners the OPPONENT'S board values highly) is a possible v2.
- Demo league (`league_demo`): loaders return no picks; roster eveners work only if demo `league_members` rows exist — degrades to no rows.
