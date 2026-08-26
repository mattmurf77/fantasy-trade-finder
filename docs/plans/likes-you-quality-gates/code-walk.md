# Code-walk proof — likes-you quality gates (D-096)

D-056 evidence artefact. Line numbers are `fix/likes-you-quality-gates`.
Companion: [`scope.md`](scope.md), [`testflight-checklist.md`](testflight-checklist.md),
[`backend/tests/test_likes_you_gates.py`](../../../backend/tests/test_likes_you_gates.py).

## What has to be true

1. Every likes-you injection is gated in the SAME units the user's value bar renders.
2. `likes_you_gate_level = 0` restores pre-D-096 behaviour exactly, with no deploy.
3. R1 never kills a card in which the *viewer* is the one being overpaid.
4. A gated card costs no cap slot, and an existing generated card is never deleted.
5. Nothing outside the injector changes — no route, no schema, no generator.

## Trace

**Entry.** `server.py:5582` — `_run_trade_job` calls `_inject_likes_you_cards` after
every generator has returned and after the exploration split, guarded (`:5577-5580`) by
`_likes_you_enabled()`, non-demo league, no pinned give/receive, no targeted opponent.
Unchanged by D-096. This is the **normal serving path**, not a bake-off arm: the same
call serves arms A/B/C alike, which is why arm A is not pinned to level 0
(`docs/plans/three-model-bakeoff/scope-phase2.md` § Excluded).

**Stud-tax pin.** `server.py:3050-3060` — `_inject_likes_you_cards` resolves the deck
owner's stud-tax mode and wraps the whole impl in `stud_tax_override(_mode)`. Unchanged,
and now load-bearing for the gate too: `package_value_v2` branches on that thread-local,
so the floor is evaluated in the same mode the card's bar values are computed in.
(Requirement 1.)

**Knob reads, once per deck.** `server.py:3122-3125`:
```
gate_level     = _likes_you_gate_level()      # -> :2912, clamps to [0, 2]
min_user_delta = _likes_you_min_user_delta()  # -> :2929, legacy raw floor, level 0 only
min_user_gain  = _likes_you_min_user_gain()   # -> :2940, package floor, levels >= 1
seed_value     = _likes_you_seed_value(...)   # -> :2966, pid -> elo_to_value(seed)
```
All four route through `_likes_you_cfg` (`:2900`), which reads `trade_service._cfg` inside
a `try/except` returning the inline default — a missing model_config row or an import
problem can never break deck generation. `_likes_you_gate_level` clamps with
`max(0, min(2, int(...)))`, so a garbage row degrades to a valid level rather than raising.
(Requirement 2, safety half. Pinned by `test_gate_level_clamps_garbage`,
`test_knob_defaults_are_the_shipped_values`.)

**Gate placement.** `server.py:3196-3209`, inside the per-like loop, positioned **after**
every pre-existing filter (roster actionability `:3138-3141`, untouchables `:3145`,
not-interested `:3149`, `seen_keys` `:3154`, `_past_decision_keys` `:3158`, R4 exclusion
`:3170-3181`) and **before** the existing/synthesize split at `:3211`. So the gates apply
to both branches: a below-floor like neither flags-and-boosts an existing card nor
synthesizes a new one.

**Level 0 — the exact revert.** `:3196-3200`:
```
if gate_level <= 0:
    if _likes_you_user_delta(my_give, my_recv, seed_map) < min_user_delta:
        continue
```
`_likes_you_user_delta` (`:2951`) is byte-identical to its pre-D-096 body, and
`min_user_delta` still defaults to −500.0 (`trade_service._DEFAULT_CFG:405`, deliberately
untouched). At level 0 the `else` branch never runs, so `_gv`/`_rv` stay `None` and the
synthesize branch recomputes them at `:3228-3230` exactly as the old code did at the same
point. (Requirement 2. Pinned by `test_level_zero_is_byte_identical_to_legacy` and by the
whole re-pinned D-055 block in `test_trade_match_flow.py:345-455`, which now runs at
level 0 via `_inject_floor_deck`.)

**Levels ≥ 1 — the unit fix.** `:3201-3206`:
```
_gv, _rv, _delta = _likes_you_package_delta(my_give, my_recv, seed_value)
if _delta < min_user_gain:
    continue
```
`_likes_you_package_delta` (`:2974`) calls `trade_optimizer._consensus_packages` — the
same function the calculator and the pre-D-096 synthesize branch used — and returns
`(gv, rv, rv - gv)`. `min_user_gain` defaults to 0.0 == `user_gain_epsilon`
(`trade_service._DEFAULT_CFG:220`), pinned equal by
`test_floor_default_equals_user_gain_epsilon`.

**The gate and the bar cannot disagree.** `:3228-3230` now reads:
```
if _gv is None or _rv is None:
    _gv, _rv, _ = _likes_you_package_delta(my_give, my_recv, seed_value)
```
and `:3244-3245` stamps `give_value = round(_gv, 1)`, `receive_value = round(_rv, 1)` onto
the card. At any level ≥ 1 those are the *same objects* the floor compared, not a
recomputation — there is no second call that could drift. (Requirement 1. Pinned by
`test_synthesized_card_bar_matches_the_gated_number`.)

**Level 2 — presentment.** `:3207-3209` calls `_likes_you_presentment_ok` (`:2997`):
```
g = sum(seed_value(p) for p in give_ids)
r = sum(seed_value(p) for p in recv_ids)
if g > r and not _trade_service_mod.overpay_ok(give_ids, recv_ids, seed_value):
    return False
return _trade_service_mod.filler_ok(give_ids, recv_ids, seed_value, seed_value)
```
`overpay_ok` and `filler_ok` are **imported through the module alias, never redefined** —
`trade_service.py:1668` and `:1527` are untouched by this branch (`git diff` on
`trade_service.py` is the `_DEFAULT_CFG` block only). The `g > r` guard is the whole
directional rule: when the viewer receives at least as much raw value as they give, R1 is
not consulted. (Requirement 3. Pinned by `test_directional_r1_kills_a_viewer_overpay`,
`test_directional_r1_spares_a_viewer_windfall`, `test_level_one_applies_the_floor_but_not_presentment`.)

**No cap slot consumed.** Every gate exits with `continue`, which is *before* the two
`injected += 1` sites (`:3215` existing-card branch, `:3249` synthesize branch) and before
`new_cards.append`. The `injected >= _LIKES_YOU_CAP` break is at `:3127`. So three
insulting likes ahead of three good ones cannot starve the deck.
(Requirement 4a. Pinned by `test_gate_failure_consumes_no_cap_slot`.)

**Existing cards are never deleted.** The `continue` skips only the
`existing.likes_you = True` / `existing.composite_score = boost_score` assignment at
`:3213-3214`. The card object is still a member of `cards`, and the return at `:3253`
sorts `new_cards + cards`. A gated existing card therefore keeps its organic composite and
falls to its organic position — the "deck holes are the rejected shape" rule from
`living-memory/LLD.md` § Presentment rules. (Requirement 4b. Pinned by
`test_gated_out_existing_card_keeps_its_organic_position`.)

**Blast radius.** `git diff --stat` against `origin/main` touches, in shipped code, only
`backend/server.py` (the helpers `:2900-3046` and the loop `:3122-3230`) and
`backend/trade_service.py` (`_DEFAULT_CFG`, two added keys, no logic). No route signature,
no table, no flag, no generator, no mobile/web/extension file. (Requirement 5.)

## Sabotage results

Each mutation applied to `backend/server.py`, suite run, then reverted; every one produced
red on exactly the assertion that should catch it.

| Sabotage | Result |
|---|---|
| Floor compared against the **raw** delta again (undo the unit fix) | 2 failed — `test_floor_is_measured_in_bar_units`, `test_gated_out_existing_card_keeps_its_organic_position` |
| Directional guard `g > r` removed (blanket R1) | 4 failed — incl. `test_directional_r1_spares_a_viewer_windfall`, `test_level_one_applies_the_floor_but_not_presentment` |
| `if gate_level <= 0:` → `if False:` (level 0 stops reverting) | 4 failed — `test_level_zero_is_byte_identical_to_legacy` + all three re-pinned D-055 floor tests |
| `filler_ok` call replaced with `return True` | 1 failed — `test_presentment_runs_filler_ok` |
| **Reverted** | 49 passed (`test_likes_you_gates` + `test_trade_match_flow` + `test_bakeoff_arm_a_golden`) |
