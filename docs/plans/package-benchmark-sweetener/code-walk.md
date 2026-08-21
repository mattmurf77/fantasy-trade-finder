# Code-walk proof — benchmark threading + sweetener reach

**Date:** 2026-08-21 · branch `fix/package-benchmark-sweetener`
**What this proves:** (A) every consumer of the market-mode package math
receives the trade-wide benchmark, with no callsite left on stale
assumptions; (B) the gap-sweetener pass reaches exactly the three v1 paths
and cannot run post-draft; (C) both changes are byte-identical no-ops at
their kill values, which is what arm A's pin rests on.

Line numbers are as of this branch's tip.

## A. The benchmark fix — where `v_max` comes from, callsite by callsite

The single changed function: `_package_value_market`
(`backend/trade_service.py` — see the `bench` block):

```python
bench = own_max
if (len(values) > 1 and v_max is not None and v_max > own_max
        and _c("package_bench_trade_wide") > 0):
    bench = v_max
    floor = _c("package_floor_cross")
```

Four conditions, each load-bearing:

- `len(values) > 1` — a single-asset side is never depth-discounted
  (the documented #214 invariant survives; every 1-for-1 fairness ratio
  is untouched).
- `v_max > own_max` — a side that holds the trade's best asset keeps the
  original own-max math (`bench == own_max`, `floor` untouched), so the
  consolidating stud+filler side prices exactly as before.
- `package_bench_trade_wide > 0` — the kill value restores the pre-fix
  expression byte-for-byte (`bench = own_max`, market floor), pinned by
  `test_package_benchmark.py::test_kill_value_is_byte_identical_to_pre_fix_math`.
- `v_max is not None` — belt-and-braces for any direct caller of the
  private function (there are none outside `package_value_v2`).

`package_value_v2` passes its existing `v_max` parameter through
(`return _package_value_market(values, other_values, v_max)`). The claim
that `v_max` is ALREADY the trade-wide max at every callsite, verified:

| Caller | v_max construction | Trade-wide? |
|---|---|---|
| `trade_service.rank_fairness` (C1 ranking) | `max(gvals + rvals)` over the signal cores | yes |
| `TradeService.generate_asset_ideas._eval` | `max(gvals + rvals)` | yes |
| `_generate_trades_v2` aggression re-price loop | `max(gvals + rvals)` | yes |
| `_generate_for_pair_v2._fairness` (A4 gate) | `max(gvals + rvals)` | yes |
| `_generate_for_pair_v2._pair_surpluses` (user side) | `u_max = max(uvals_give + uvals_recv)` — both sides in the USER's value space | yes (per board) |
| `_generate_for_pair_v2._pair_surpluses` (opp side) | `o_max = max(ovals_give + ovals_recv)` — both sides in the OPPONENT's space | yes (per board) |
| `_generate_consensus_for_pair._emit` + `_gap_gates_ok` | `max(gvals + rvals)` | yes |
| `trade_optimizer._consensus_packages` | `max(gvals + rvals)` | yes |
| `trade_optimizer._fairness_v3` | `max(gvals + rvals)` | yes |
| `trade_optimizer.generate_pair_trades_v3._surpluses` | `u_max` / `o_max`, both sides per board | yes (per board) |
| `trade_gen_fit._surplus` (fit arm, K-wrappers) | `v_max = max(rvals + gvals)` (`backend/trade_gen_fit.py:640-649`), calling `ts.package_value_v2` through the module namespace | yes — **the fit arm inherits the fix automatically**, verified not assumed |
| `trade_gen_v2` (arm C) | its own `consolidated_value` (own-best benchmark, `gen2_consol_*` knobs) for gating/scoring; `_consensus_packages` only for the DISPLAYED `give_value`/`receive_value` | arm C's displayed values inherit; its internal gate math is its own, unchanged |
| `server._evaluate_adjustments` (calculator breakdown) | `max(gvals + rvals)`; derives depth/crown rows by calling `package_value_v2` with/without `n_other` — no math duplicated, so the displayed decomposition tracks the fix automatically | yes |

The "market mode ignores `v_max`" note in the old docstring was the ONLY
place the parameter was dropped; no caller had stopped passing it, so the
threading is a one-line change with no callsite edits.

## B. The gap sweetener — where it runs, and why it cannot run post-draft

One shared helper: `trade_optimizer.close_value_gap` (module-level, next to
its prior art `_try_sweeten`, exported in `__all__`). Three hook sites, all
INSIDE per-pair generation:

1. **v3** — `generate_pair_trades_v3`, after the 3.4 fairness-band
   sweetener pass, over the pair's finished cards. Path gates re-earned via
   `_gap_extra_ok`: `filler_ok`, `pick_swap_ok`, `presentment_ok_fn`,
   `_gap_ok`, both `_surpluses ≥ MIN_SIDE`; the helper itself re-checks
   gap, fairness band and 3.2 lineup feasibility. Collision guard: a
   sweetened id-set that equals a sibling card's is skipped.
2. **v2 divergence** — `_generate_for_pair_v2`, in the final card loop over
   `ranked[:max_cards]`. The surplus/composite math needed for re-scoring
   was extracted byte-identically into `_pair_surpluses` / `_composite_v2`
   (both used by `_consider`, so organic scoring is unchanged — the full
   suite plus the arm-A/challenger/engine-quality goldens pin that).
3. **consensus** — `_generate_consensus_for_pair._emit`, after the fairness
   gate and before card construction, with `_gap_gates_ok` re-earning the
   consensus stack (sign test under one-way mode, `consolidation_raw_loss_frac`,
   `user_gain_ok_1for1`, `pick_swap_ok`, `filler_ok`, presentment).
   `scoring_format` is threaded from `_generate_trades_v2` for the
   feasibility check (new keyword, default `"1qb_ppr"`).

**Interleave-safe by construction:** all three sites execute inside
`TradeService.generate_trades` / `generate_pair_trades_v3`, i.e. inside the
arm's own generation call, under whatever `_cfg_override` overlay the
bake-off runner has entered on that thread. The interleaver
(`bakeoff_runner`) only ever merges the returned lists; no post-draft code
was touched, so deck positions cannot be disturbed and arm attribution is
inherited from the generating arm.

**Richer-side selection:** `rv > gv` (user receives more) ⇒ equalizer comes
OFF the user's roster onto the give side; `gv > rv` ⇒ off the opponent's
roster onto the receive side. Candidates sorted ascending by consensus
value; the first that passes every check is the smallest sufficient
equalizer. Untouchables never leave the user's roster; not-interested
players are never sweetened INTO the user — same exclusions as
`_try_sweeten` (#2, #163).

**Attribution:** the card gets `gap_sweetener = {player_id, side,
gap_before, gap_after}`; `server.py` serializes it on the card payload only
when present (the `sweetener` convention) and stamps it into
`features_json` on EVERY impression row, null when absent (the fit-arm
uniform-key precedent — inside the one Text column, so the executemany
first-row-keys trap cannot drop it).

## C. Kill values

- `package_bench_trade_wide ≤ 0` ⇒ `bench = own_max`, market floor — the
  exact pre-fix expression (test-pinned, four shapes).
- `sweetener_gap_threshold ≤ 0` ⇒ every hook site's `if GAP_THR > 0` guard
  short-circuits before any work; generators return their pre-sweetener
  output byte-for-byte (test-pinned per path).
- Both are pinned at 0.0 in `MODEL_A_PROFILE`, which is why the arm-A
  golden passes UN-recaptured (10/10) — the baseline did not move.
