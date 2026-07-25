# Status — #175 directional outlook weighting

**State:** built + tested, DARK (`trade.outlook_direction` = false everywhere).
Branch: isolated worktree branch off `teardown-remediation` (see commit
referencing #175). Not merged, not deployed.

## What was built

- `backend/trade_service.py`
  - `outlook_direction_mult(give_ids, recv_ids, players, outlook, value_of)`
    (+ `_primary_asset` helper), placed with the lane machinery it reuses.
    Directional shift term + the ~1-year-gap rule; consensus values, same
    rationale as `classify_lane` (the card's shape, not either private
    board).
  - Applied in `_generate_trades_v2`'s per-opponent post-gate block (after
    the FB-147 block boost, before lane stamping) — covers divergence v2,
    v3 optimizer, and consensus cards uniformly, AFTER all gates: it
    reorders acceptable trades and never rescues gated ones. The legacy
    pre-v2 path is production-dead (`trade_engine.v2` true) and untouched.
  - New in-process `TradeCard.outlook_dir` field (applied multiplier, QA
    record only — never serialized).
- Flag `trade.outlook_direction` registered in `backend/feature_flags.py`,
  `config/features.json` (false), `backend/tests/fixtures/flags/release.json`
  (false).
- `model_config` seeds in `backend/database.py` + `_DEFAULT_CFG`.

## Knobs (model_config, all live-tunable)

| Key | Default | Meaning |
|---|---|---|
| `outlook_dir_penalty` | 3.0 | Rebuild-side weight on a positive (win-now-acquiring) shift: `×= max(0.05, 1 − w·shift)` |
| `outlook_dir_boost` | 1.0 | Rebuild-side weight on a negative (future-capital) shift: `×= 1 + w·(−shift)` |
| `outlook_dir_contend_weight` | 0.5 | Contend-side mild symmetric mirror: `×= 1 + w·shift` |
| `outlook_dir_age_tolerance` | 1.0 | Years an older primary return may exceed the primary give before the gap rule fires |
| `outlook_dir_age_gap_mult` | 0.15 | Near-exclusion multiplier for unrescued older-primary returns (rebuild-side only) |
| `outlook_dir_rescue_frac` | 0.5 | Min fraction of the primary give's consensus value a pick/younger component needs to rescue |

Typical magnitudes at defaults (WR curves): a 24yo give → 30yo return
1-for-1 lands at ×≈0.05 (shift 0.34 + gap crush); → 22yo return ×≈1.04;
→ pick return ×≈1.08; → 25yo return ×≈0.87 (inside tolerance, mild only).

## Decisions (and why)

- **Penalty, not filter**, for the 1-year rule — per the spec's lean: a
  genuinely lopsided-value win can still surface above the crush.
- **Consensus values** for shift + primaries — matches `classify_lane`
  ("the card's shape, not either member's private board") and keeps the
  term independent of board noise.
- **"Primary" = single highest-consensus-value asset per side.** Pragmatic;
  documented in code. The feedback's "same/similar tier of value" clause is
  not a separate gate: fairness-gated cards already make primaries
  comparable, and the penalty-not-filter choice covers the lopsided case.
- **No age-gap rule when a primary is a PICK or an age is missing** — the
  rule can't judge; the shift term still applies (giving a pick for a vet
  is already heavily shift-penalized for a rebuilder).
- No new ADR: this reuses the existing lane machinery and the established
  post-gate bounded-multiplier pattern (need_fit / block_boost); nothing
  architecturally novel.

## How to validate

1. Flip `trade.outlook_direction` to true in `config/features.json`.
2. In a league whose outlook is `rebuilder` (declared or #8-seeded),
   regenerate TradesHome suggestions: pick/younger returns should lead;
   cards returning an older player for a younger give should sink hard
   unless the return carries a comparable pick/younger piece.
3. Set outlook to `not_sure` → deck ordering identical to flag-off.
4. Tests: `python3 -m pytest backend/tests/test_outlook_direction.py -q`
   (15 tests); full suite 1013 passed, 1 skipped (baseline 998 + 15 new).
