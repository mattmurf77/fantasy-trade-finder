# #227 — "1:1 trades for draft picks should never be a suggestion" — status

**Status: fixed (backend — shared generation gate)** · 2026-08-01 · branch
`teardown-remediation` worktree

## Operator report

> "1 : 1 trades for draft picks should never be a suggestion."

Filed 2026-08-01T06:36Z from `TradeDeck` (v1.11.0, iOS).

## Root cause — zero-divergence assets pass the relaxed gates

Owned picks are injected with the SAME bridged Elo on every board
(`_pick_asset_elos` primes seed, user and member maps identically — picks
aren't matchup-rankable, so divergence on a pick is zero by construction).
A 1-for-1 pick-for-pick swap therefore has zero surplus on both sides:

- normal divergence passes gate it out (`min_side_surplus` 150 > 0), but
  the **#189 relaxed pass's `fairness_band+surplus_floor` stage drops the
  both-sides surplus minimum to 0.0** — a zero-surplus swap of two
  similar-value picks then passes everything (fairness ≈ 1.0, the #108
  1-for-1 gate sees equal values, the filler gate exempts 1-for-1s);
- the **consensus fallback** (unranked opponents — the common case) never
  had a surplus gate at all: any pick pair with `receive − give ≥
  user_gain_epsilon` and passing fairness emitted.

Result: cards like "your 2027 2nd for their 2027 2nd" — pointless churn.

## Fix — narrow, documented gate in the shared path

`backend/trade_service.py` — new `pick_swap_ok(give_ids, recv_ids,
players)`: rejects a card iff it is **1-for-1 AND both sides are pick
assets** (`is_pick_asset`: position `"PICK"` or team `"PICK"`). Enforced at
all three generation sites so v2/v3/consensus (and therefore the #189
relaxed pass, which re-runs them) all obey:

- v2 pair path (`_generate_for_pair_v2._consider`)
- v3 optimizer (`trade_optimizer.generate_pair_trades_v3` enumeration —
  gated BEFORE near-miss collection, so the 3.4 sweetener pass can never
  rescue the shape)
- consensus fallback (`_generate_consensus_for_pair._emit`)

**Documented scope decisions:**

- **1-for-1 pick-for-pick: banned outright** (the operator's ask).
- **pick + player for pick (and any mixed package): allowed** — picks as
  sweeteners or headline compensation are real trades.
- **pure pick-for-pick 2-for-1 consolidations: allowed** — two lesser
  picks for a better one changes asset SHAPE, which has genuine utility
  even at ~equal value (and dynasty managers make exactly this trade); the
  gate stays narrow rather than banning all-pick packages.
- **`POST /api/trades/asset-ideas` is deliberately NOT gated** — a pinned
  PICK's Lateral group is 1-for-1 pick swaps BY DESIGN (#198: PICK pins
  keep pure value bands). That surface is user-requested exploration of a
  specific asset, not an unsolicited suggestion.
- The legacy (pre-v2) engine path is unchanged (`trade_engine.v2` has been
  ON in prod throughout; the legacy path predates pick injection).
- 3-team cycles (`trade.three_team`, OFF) unchanged — out of scope.

No new flag/knob: the gate is a correctness rule (like #108), not taste.

## Files

- `backend/trade_service.py` — `is_pick_asset` + `pick_swap_ok`; gate
  calls in `_consider` (v2) and `_emit` (consensus)
- `backend/trade_optimizer.py` — gate call in the v3 enumeration cluster
  (+ import)
- `backend/tests/test_pick_swap_gate.py` — new file
- `docs/api-reference.md` — `/api/trades/generate` row note

## Tests (`backend/tests/test_pick_swap_gate.py`, 5)

- `test_is_pick_asset_detection`, `test_pick_swap_ok_truth_table` — helper
  semantics incl. the allowed shapes (pick-for-player, pick+player
  packages, 2-for-1 pick consolidation).
- `test_v2_pick_for_pick_1for1_never_emitted`,
  `test_v3_pick_for_pick_1for1_never_emitted`,
  `test_consensus_pick_for_pick_1for1_never_emitted` — engine-path tests
  reproducing the leak shape (equal-value picks, `min_side_surplus` pinned
  to 0 to emulate the #189 relaxed stage; consensus via a pinned receive
  pick), asserting the card is gone — and each fixture proves its own
  validity by monkeypatching the gate open and asserting the degenerate
  card DOES appear (pre-#227 behavior).

## Verification

- `python3 -m pytest backend/tests -q` → **1378 passed, 1 skipped**
  (branch baseline: 1365 passed, 1 skipped).
