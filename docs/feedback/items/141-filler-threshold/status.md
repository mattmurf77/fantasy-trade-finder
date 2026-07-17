# #141 — Junk-filler threshold on suggested trades

**Owner report (mattmurf77, TradesHome):** suggestions pad both sides with
low-value players; wanted a value threshold for adding a player to a
suggestion, considering both teams' valuations via the max across them.

**Status: DONE** — 2026-07-17, branch `trade-engine-v2`.

## Mechanism found

Fillers enter packages in four places, none of which had any per-piece
value floor:

1. **v2 pair loop** (`trade_service._generate_for_pair_v2`): 2-for-1,
   1-for-2 and 3-for-2 shapes are built from `combinations()` over the
   divergence candidate pools — any rostered junk with mild divergence
   could ride along as the 2nd/3rd piece.
2. **v3 optimizer** (`trade_optimizer.generate_pair_trades_v3`): exact
   enumeration of give×receive subsets (1–3 each) over the top-12
   divergence pools — same exposure, more shapes.
3. **v3 sweetener pass** (`_try_sweeten`): explicitly picks the
   **cheapest-consensus** rosterable player to close a fairness near-miss
   — the single biggest junk injector by construction.
4. **Consensus fallback** (`_generate_consensus_for_pair`): 2-for-1 give
   pairs from the full user roster.

## Design

New gate `trade_service.filler_ok(give, recv, user_val, opp_val)`,
applied at candidate entry in **all four** paths:

- For each side with 2+ assets, every piece except the side's headliner
  (best asset) must satisfy `value ≥ filler_min_frac × headliner value`.
- Per-player metric is **max(user board, opponent board)** raw value —
  the owner's max rule: a piece either side genuinely values is a
  legitimate filler; only players BOTH boards call junk are gated.
- **Fraction of the side's headliner**, not an absolute Elo/value floor:
  the value scale spans ~250 → ~8500 (affine DP recalibration, #117), so
  any absolute floor is either toothless for elite-headlined trades or
  kills legitimate depth-for-depth trades. A fraction scales with the
  trade: big trades demand real pieces, small trades stay untouched.
- Headliners / the 1-for-1 core are exempt; the gate only removes cards
  (added after #108, before the surplus/fairness math) — it never rescues
  or weakens the fairness, user-gain or need-fit gates.
- Raw board values, not marginal: marginal valuation collapses depth by
  design; "does this look like junk?" is a board-value judgment.
- Consensus path: the opponent has no board, so consensus stands in for
  their arm of the max rule (user's raw board supplies the other arm).

## Knob + default

`filler_min_frac` = **0.25** — in `trade_service._DEFAULT_CFG` **and**
DB-seeded via `database._MODEL_CONFIG_DEFAULTS` (live-tunable through
`PUT /api/admin/config/filler_min_frac`). `0` restores pre-#141 behavior
byte-identically. No feature flag: the knob is its own kill switch.

0.25 ≈ a 277-Elo window below the headliner. On the real 2026-06-13 DP
snapshot (`player_value_history`, 1qb):

| Side headliner | Value | Filler bar (×0.25) | ≈ rank cutoff |
|---|---|---|---|
| Ja'Marr Chase (rank 1) | 8470 | ~2120 | top ~65 (≈ a mid 1st) |
| Jalen Hurts (rank 50) | 3251 | ~813 | ~rank 115 |
| Davante Adams (rank 100) | 1013 | ~253 | ~rank 250 |

So rank-200 junk (~312) can never pad a package headlined by anything
better than ~rank 110, while depth-for-depth trades are untouched.

## Before / after example

User gives **[WR1-caliber G1, junk J]** for **[R]** (J ≈ Elo 1220 ≈ value
247 on both boards; G1's max-board value 1822):

- **Before:** surfaces — surpluses ~1279/~948 ≥ 60/150, consensus ratio
  0.678, #108 exempt (multi-asset). Junk rode along.
- **After:** dark (247 < 0.25 × 1822 = 456). The clean [G1] → [R] core
  still surfaces. If the opponent's board prices J at Elo 1620 (~1822),
  the padded card surfaces again — max rule.
- **Sweeteners:** the cheapest-first pick now skips any candidate below
  the bar and lands on the first meaningful piece instead.

## Files

- `backend/trade_service.py` — `filler_min_frac` default + `filler_ok`
  helper + gates in `_consider` (v2) and `_emit` (consensus)
- `backend/trade_optimizer.py` — gate in the v3 enumeration + the
  sweetener pass (`filler_ok_fn`)
- `backend/database.py` — `_MODEL_CONFIG_DEFAULTS` row (additive)
- `backend/tests/test_filler_threshold.py` — 8 tests: helper semantics,
  v2 / v3 / consensus exclusion with knob=0 leak repros, max-rule
  survival, sweetener bar, knob=0 byte-identity vs a bypassed gate
- `docs/config-reference.md` — knob row

## Test results

`python3 -m pytest backend/tests/ -q` → **617 passed** (609 pre-existing
incl. fairness-gate golden, #108 user-gain, need-fit, optimizer suites —
all green — plus 8 new).

## Ownership transfer (2026-07-17)

Per operator direction, all trade-engine work moved to the dedicated
trade-logic thread. That thread's in-tree edits already build on the #141
filler gate (bench_credit_rate, consolidation retunes, need_fit 0.30->0.15
reference it), so the gate was NOT reverted — reverting would break their
in-flight work. The engine files (trade_service.py, trade_optimizer.py,
database.py engine rows, test_filler_threshold.py, the config-reference
knob row) are EXCLUDED from this batch's ship commit and belong to the
trade-logic thread's own commit/ship cadence. #141's feedback status
remains in_progress under that thread's ownership.
