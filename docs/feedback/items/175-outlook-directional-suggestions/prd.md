# PRD — Feedback #175: directional outlook weighting

**Feedback (operator-filed, severity bug, screen TradesHome), verbatim:**

> "The users outlook should heavily weight the trade suggestions to then
> acquiring a younger player or a pick for the player they are giving away.
> It's rare that a rebuilder would move a younger player for an older player
> (outside of maybe a 1 year gap)"

Standing trade philosophy (2026-07-17 interview): roster fit first; age =
tiebreak; two-lane windows (contend vs rebuild). The lane machinery
(`_LANE_SIGN`, `_now_lean`, `classify_lane`) already describes a card's
now/future shape but only LABELS cards — it never steers generation or
scoring. #175 asks for steering.

## Requirements

New flag `trade.outlook_direction`, default **false** (ships dark), registered
alongside `trade.outlook_blend` in `config/features.json`,
`backend/feature_flags.py`, and `backend/tests/fixtures/flags/release.json`.

When ON and the user's resolved outlook is rebuild-side (`rebuilder`/`jets`):

1. **Directional age-flow scoring.** Reuse the lane machinery: compute the
   value-weighted now-lean shift of each candidate card from the USER's
   perspective (received − given, exactly `classify_lane`'s shift, on
   consensus values). Positive shift (acquiring win-now/older production) ⇒
   strong composite penalty; negative shift (acquiring future capital:
   younger players, picks) ⇒ boost. Magnitudes config-tunable via
   `model_config` (`outlook_dir_penalty`, `outlook_dir_boost`).
2. **The ~1-year-gap rule.** When the user gives a player and the primary
   return asset is an OLDER player, the card is heavily penalized
   (near-excluded) — UNLESS the age gap is within `outlook_dir_age_tolerance`
   (default 1.0 years) or the return includes a pick or a younger player as a
   comparable-value component (`outlook_dir_rescue_frac` of the primary
   give's value). "Primary asset" = highest-consensus-value asset on a side.
   Implemented as a large penalty (`outlook_dir_age_gap_mult`), NOT a hard
   filter, so a genuinely lopsided-value win can still surface.
3. **Contend-side mirror** (`championship`/`contender`): ONLY the mild
   scoring term (`outlook_dir_contend_weight`, positive shift boosted,
   negative penalized). No age-gap rule — contenders legitimately buy older
   players. `not_sure`/None outlook ⇒ no directional effect at all.
4. **All engines that feed TradesHome**: v2 divergence, v3 optimizer, and
   consensus cards. (All flow through the `_generate_trades_v2` post-gate
   loop; the legacy pre-v2 path is dead in production — `trade_engine.v2` is
   true — and is not touched.)
5. **Composition with `trade.picks_in_pool` (#170)**: pool-injected PICK
   pseudo-assets have negative `_now_lean`, so a pick return naturally
   satisfies the rebuild direction — verified by test.

## Acceptance criteria (all in `backend/tests/test_outlook_direction.py`)

- Flag off ⇒ generation output unchanged (byte-identical composites, nothing
  stamped).
- Rebuilder: older-player return penalized below an otherwise-equal
  younger-player return; pick return ranks above an older-player return at
  comparable value.
- Older-by-≤1yr return is NOT hard-penalized (mild shift term only).
- Contender mirror is mild (bounded band, no age-gap crush).
- `not_sure`/None ⇒ zero effect.
- Full backend suite passes.
