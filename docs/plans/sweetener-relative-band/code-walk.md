# Code-walk proof — gap-sweetener relative band + best-effort fallback (`sweetener_gap_frac`, `sweetener_best_effort`)

**Date:** 2026-09-02 · **Branch:** `claude/sweetener-relative-band` (forked from `origin/main` @ `e16bb487`) · **Scope:** [scope.md](scope.md) · **Measurement:** [results.md](results.md)

Line numbers are the branch tip's files. Every claim below is either a cited line or a test in `backend/tests/test_sweetener_relative_band.py` (named in brackets; the pin test lives in `test_bakeoff_arm_a_golden.py`).

## 1. Both knobs are read at CALL time, through `_c`, inside the helper

| Step | Where | What |
|---|---|---|
| declared | `trade_service.py:530` / `:542` | `"sweetener_gap_frac": 0.0` and `"sweetener_best_effort": 0.0` in `_DEFAULT_CFG`, directly after `sweetener_gap_threshold` (`:516`), each with the house comment block |
| seeded | `backend/database.py:2446-2447` | `_MODEL_CONFIG_DEFAULTS` rows — the boot migration at `:3187` inserts every tuple with `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING`, and `set_config` (`:4433`) raises for a key with no row, so without these seeds `PUT /api/admin/config/<key>` would 404. [`test_defaults_registered_in_both_stores_and_arm_dispositions`] pins both stores at 0.0 |
| read | `trade_optimizer.py:918` `frac = _c("sweetener_gap_frac")` and `:924` `best_effort = _c("sweetener_best_effort") >= 1.0` | the third and sixth statements of `close_value_gap` (`:843`), executed on every call, never at import, never via `_ts._cfg.get` (D-098 / G-058 cause 3 — the `SHAPE_D` comment at `trade_optimizer.py:279-289` is the canonical explanation). `_c` is imported from `trade_service` at `:57-61` — it already was, for the sibling knobs |
| `_c` honours the overlay | `trade_service.py:1282-1288` | `_c` consults `_cfg_local.map` first, then `_cfg`, then `_DEFAULT_CFG` — so a `_cfg_override` (`:1273`) on the calling thread shadows the process-global row. [`test_knobs_are_read_at_call_time_through_the_overlay`]: a global live triple under `_cfg_override({frac: 0, best: 0})` is the knob-0 result; overlaying only one key leaves the other live |

Sabotage S5 (results.md § Sabotages) hoists the reads to `_DEFAULT_CFG[...]` and the overlay test goes red.

## 2. The knob-0 identity is structural, for BOTH knobs

```
917  thr_eff = gap_threshold
918  frac = _c("sweetener_gap_frac")
919  if frac > 0:
920      thr_eff = max(gap_threshold, frac * max(gv, rv))
921  gap_before = abs(gv - rv)
922  if gap_before <= thr_eff:
923      return None
924  best_effort = _c("sweetener_best_effort") >= 1.0
...
953      closes = n_gap <= thr_eff
954      if not closes:
955          if not best_effort:
956              continue                          # too small to close it
```

* **frac ≤ 0:** `thr_eff` IS the `gap_threshold` argument (`:917`, the `if` at `:919` is skipped — deliberately `frac > 0`, not `max(…, 0 × H)`, so a caller passing a non-positive threshold is also unchanged). The guard at `:922` is then the old `abs(gv − rv) <= gap_threshold`, and requirement (a) at `:953` is the old `abs(n_gv − n_rv) > gap_threshold`.
* **best_effort off:** a non-closing candidate takes `continue` at `:956` before any gate is evaluated — exactly the old `# too small to close it` branch, same position in the loop, so the gates run for the same candidates in the same order. `best` (`:943`) is never assigned; the function falls through to `return None` at `:979-980`, as before.
* The first closing candidate still returns immediately (`:974-976`), so "cheapest sufficient" is unchanged. The only visible difference at knob 0 is the tuple's 8th field, `False`, which every caller unpacks and ignores when false (§5).

Proof: [`test_helper_knob0_is_byte_identical_to_origin_main`] compares nine `close_value_gap` results (the first seven fields — the whole tuple on the capture tree) against literals captured on a `git archive origin/main` tree; [`test_v3_deck_knob0_is_byte_identical_to_origin_main`] does the same for 30 engine-quality v3 cards plus the gap-sweetener v3 fixture, `gap_sweetener` dicts included. The branch capture `cmp`'d byte-identical to the main capture. [`test_the_goldens_are_not_vacuous`] shows both row sets move at the live triple.

## 3. The best-effort branch, and the three rules it keeps

```
957          # Best-effort partial: strictly narrower, same richer side, and
958          # only worth gating if it beats the tightest partial so far.
959          if n_gap >= gap_before or (n_rv > n_gv) != user_richer:
960              continue
961          if best is not None and n_gap >= best[0]:
962              continue
963      ratio = min(n_gv, n_rv) / max(n_gv, n_rv)
964      if ratio < fairness_threshold:            # fell out of the band
965          continue
966-972  lineup feasibility on BOTH rosters (unchanged)
973      if extra_ok_fn is not None and not extra_ok_fn(new_give, new_recv): continue
974-976  if closes: return (..., round(ratio, 3), False)
977-978  best = (n_gap, s_pid, side, new_give, new_recv, n_gv, n_rv, round(ratio, 3))
981-982  return s_pid, side, new_give, new_recv, n_gv, n_rv, ratio, True
```

1. **Strict reduction** (`:959`, first clause). Under the live trade-wide benchmark a cheap piece can WIDEN the packaged gap — adding any second piece to London's side re-benchmarks London against CeeDee at `package_floor_cross` 0.4 (`trade_service.py:1697-1700`), a −275 hit, so 450 nets +118 and 600 +49 on the #414 card. Such a piece is never attached even with the #141 gate off — [`test_best_effort_never_widens_the_gap`].
2. **Richer side unchanged** (`:959`, second clause). A flipped candidate still above the trigger has turned the user's overpay into the partner's; it can pass R1 (a 3,200 piece flips the #414 card to |gap| 1,063.6 at raw ratio 0.237 < 0.25) and fairness (0.871). It is refused; the 900 partial (1,288.8) wins — [`test_best_effort_never_flips_the_richer_side`]. A flip that lands UNDER the trigger is a full close, as it always was. Sabotage S3 drops this clause and the test goes red.
3. **Tightest, not cheapest** (`:961`, `:977`). Candidates arrive cheapest-first; a partial that leaves a larger gap than the best so far is skipped before the gates (cost only — the gates have no side effects except the presentment kill counters, which are diagnostics). The final `best` is the minimum post-add |gap| among gate-passing partials — [`test_qa_regression_best_effort_attaches_the_tightest`] (1,480 → 1,534.5 beats 1,200 → 1,708.3). Sabotage S2 inverts the comparison and the test goes red.

Every gate a full close must pass — the ratio bar (`:964`), both lineups (`:966-972`), the caller's `extra_ok_fn` (`:973`: junk filler, pick-swap, presentment R1/R2/R3/R5, surplus/Elo-gap gates, arm C's band and ε-gain) — is evaluated for a partial in the same order, verbatim. A full close found after a partial still returns immediately (`:974`), so best-effort never displaces a real close.

## 4. The effective trigger, and why 0.12

`thr_eff = max(threshold, frac × max(gv, rv))` — a floor plus a band, never a replacement. At the proposed triple: the #414 card (H = 7,328.8) triggers at 879.5; a 5,000-value 1x1 at 750 (the floor wins below H = 6,250); a 10,000 package at 1,200. The band cannot go *lower* than the floor, so the rows the operator agreed to (a late 1st = 1,539 in 2026-08-21) are relaxed only by the deliberate PUT to 750. [`test_frac_raises_the_trigger_above_the_floor`]: frac 0.20 (→ 1,465.8 > 1,396) leaves the card alone; 0.12 fires; frac 0.12 under a 1,539 floor is inert (879.5 < 1,539). [`test_414_full_close_when_the_bench_holds_a_closer`] is a full close only because the band lifted 750 → 879.5 (the 1,500 piece lands at 772.1) — sabotage S1 replaces the `max` with `gap_threshold` and both tests go red.

## 5. Every caller, and the `partial` stamp path

`git grep -n "close_value_gap(" -- backend` (non-test): four call sites, all guarded by their path's `GAP_THR = _c("sweetener_gap_threshold") > 0` read:

| Path | `GAP_THR` read | call | unpack | stamp | notes |
|---|---|---|---|---|---|
| v3 optimizer (boarded partner, `trade_engine.v3`) | `trade_optimizer.py:710` | `:728` | `:739` | `:772` `card.gap_sweetener["partial"] = True` | `fairness_threshold` already loosened to `min(caller, fairness_floor_divergence)` at `:302-303` before any gate — inherited verbatim |
| v2 pair generator (boarded partner, v3 off) | `trade_service.py:6957` | `:6979` | `:6990` | `:7001` | same loosened bar; `_gap_extra_ok` at `:6959-6970` |
| consensus generator (no partner board — the path that served #414) | `trade_service.py:7201` | `:7305` (`_close_gap`) | `:7327` | `:7336` | caller's full threshold; pools narrowed via `give_candidates` / `recv_candidates` (`:7322-7323`), `_gap_gates_ok` at `:7204` |
| arm C (`trade_gen_v2`, bake-off) | `trade_gen_v2.py:589` | `:740` | `:797` | `:804` | `fairness_threshold=0.0` (`:746`) — the helper's ratio gate is inert; arm C's own band and ε-gain live in `_gap_gates_ok` (`:591-625`) and are re-run on partials like any other `extra_ok_fn` |

Every caller stamps the same shape: `{"player_id", "side", "gap_before", "gap_after"}` plus `"partial": True` **only** when the 8th field is true — a full close's dict is byte-identical to today's ([`test_v3_deck_knob0_is_byte_identical_to_origin_main`] includes the sweetened 3-for-1's dict). The collision guards (`card_keys` / `_picked_keys` / `seen`) are untouched, so a partial that would duplicate a sibling card is dropped exactly as a full close would be.

Stamp-path tests: [`test_consensus_path_stamps_partial_on_the_414_card`], [`test_v3_path_stamps_partial_and_full_closes_distinctly`], [`test_v2_divergence_path_stamps_partial`]. Arm C emits nothing on the unit fixtures; its partials are read off the harness `C_gen_v2` rows (results.md).

## 6. Which overlays reach the reads

All overlays enter through `_cfg_override` (`trade_service.py:1273`), which `_c` honours on the calling thread:

| Overlay | Entered at | Names the knobs? | Effect |
|---|---|---|---|
| `MODEL_A_PROFILE` (arm A) | `bakeoff_profiles.py:153` `model_a()`, from `bakeoff_runner.py:1538` | **yes — both pinned 0.0** (`:147-148`) | arm A keeps the all-or-nothing closer at the absolute trigger whatever prod sets. **Reachability, stated plainly:** the same profile pins `sweetener_gap_threshold` 0.0 (`:105`), and every caller in §5 guards `GAP_THR > 0`, so on an arm-A thread `close_value_gap` is never entered and the two reads never happen today. The pins are defence in depth for the day that pin is lifted, and [`test_sweetener_band_pins_are_load_bearing`] proves them in that state: the overlay minus the threshold pin, live triple in the row, the #414 card with a 450/600/900 bench under arm A's own-max package math (`package_bench_trade_wide` pinned 0 → the 900 piece closes to 833, over the 750 floor, under the band's 879.5) — unsweetened with the pins, sweetened without them, and the full overlay unmoved. Sabotage S4 removes a pin and it goes red. Harness: every `A_baseline` row is identical across V0–V4 |
| `MODEL_CHALLENGER_PROFILE` (arm D) | `bakeoff_profiles.py:232` `model_challenger()`, from `bakeoff_runner.py:1550` | **no** | arm D inherits all three live rows — it is the live engine under an overlay (D-095) and is serving (G-064); its `consensus_both_ways` 1.0 means the consensus path can put the equalizer on the RECEIVE side there, which the helper already handles (`side = "receive"`) |
| #189 relaxed pass | `trade_service.py:5045` `_relaxed_targeted_pass` | **no** (`fairness_floor_divergence`, `min_side_surplus*` only) | the relaxed re-run sweetens with the same triple the normal pass used, at its own lower fairness bar |
| arm B (`current`) | no overlay | — | reads the prod rows directly |

Also checked: `backend/trade_gen_fit.py` (arm `fit`) never calls `close_value_gap`; `bakeoff_runner.py` never mentions either key.

## 7. The wire payload — where `partial` goes

| Surface | Where | Carries `partial`? |
|---|---|---|
| deck-outcome corpus (`deck_impressions.features_json`) | `server.py:4524` `"gap_sweetener": getattr(card, "gap_sweetener", None)` — the key is present on EVERY row (null when unsweetened; comment at `:4519-4523`) | **yes, automatically** — the whole dict is serialized inside `features_json`, so `partial` rides along with no schema or logging change; `SELECT … WHERE features_json->'gap_sweetener'->>'partial' = 'true'` splits the corpus |
| card JSON to clients | `server.py:11755` `trade_card_to_dict` → `:11818-11820` `if gap_sweetener: out["gap_sweetener"] = gap_sweetener` | **yes, automatically** — the dict is emitted whole when present. No client reads it: `git grep -n gap_sweetener -- mobile web extension` is empty, so the mobile/web payload gains an optional key nobody consumes (the value bar shows the sweetened values as it does for a full close) |
| whole-object dumps | none exist in `backend/` (no `asdict` / `__dict__` of a `TradeCard`) | — |

So: no client change, no analytics change, one additive key inside a dict two surfaces already emit whole.

## 8. The package math the brief's arithmetic missed (qualifies "900 closes it to ≤ 879")

The brief expected a 900 equalizer to close the #414 gap to ≤ 879 — the naive-sum picture (5,932.8 + 900 = 6,832.8 vs 7,328.9 → 496). `close_value_gap` measures the gap with `_consensus_packages` (`trade_optimizer.py:108`) = `package_value_v2` (`trade_service.py:1569`) in 'market' mode → `_package_value_market` (`:1654`), and under the live knobs that function does three things to a 1x1 that gains a second piece:

1. **The single richer asset earns the crown credit** (`:1706-1717`, `crown_elite_value` 6,000, `crown_rate_market` 0.08, phased out by naive skew): CeeDee's seed 6,965.6 packages to the served **7,328.9**. The prod card's give/receive values are packaged values — the unit fixture inverts the seed (`_CEEDEE = 6965.6`) to reproduce them exactly.
2. **The side without the trade's best asset is benchmarked trade-wide** once it has ≥ 2 pieces (`:1697-1700`, `package_bench_trade_wide` 1.0, `package_floor_cross` 0.4, `package_adj_gamma_market` 0.5): London himself drops 5,932.8 → 5,658 (−275) the moment he has a partner.
3. **The added piece is depth-discounted against CeeDee**, not against London: 900 → 554, 1,200 → 779.

Net on the packaged gap: 900 → **−107** (1,288.8), 1,200 → **−337** (1,058.9), 1,500 → −624 (772.1, the first full close under 879.5). So with the 450/600/900/1,200 bench the card is a best-effort **partial**, which is exactly what the second knob exists for; a user who has a ≥ 1,500 piece gets a full close. This is a property of the 2026-08-21 benchmark fix, not of this change, and it is why the sweetened share in results.md is mostly partials at the triple — and why "adding a player to make it more fair" moves the bar less than the player's face value suggests. Flagged for the lead as a finding, not fixed here.

## 9. Not proven here, for the lead

* No prod replay: the harness leagues are synthetic; the `414_1x1` league plants the operator's two prices into the 12-team fixture but the surrounding benches are the fixture's, not mattmurf77's. Whether the London/CeeDee card closes fully or partially in prod depends on his bench (≥ ~1,500 of consensus value in one WR-or-flex piece → full).
* Arm C's partial stamp is exercised only by the harness (`C_gen_v2` rows), not by a unit fixture.
* No global parity test between `_DEFAULT_CFG` and `_MODEL_CONFIG_DEFAULTS` exists; this change pins its own keys, as every predecessor did.
* The fairness bar the divergence paths hand the helper is `min(caller, fairness_floor_divergence)` (`trade_optimizer.py:302`); a partial on those paths can therefore sit at a point ratio the consensus path would refuse. Pre-existing, inherited, and stated in the fuzz test rather than hidden.
