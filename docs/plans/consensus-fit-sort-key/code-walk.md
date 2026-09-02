# Code-walk proof — consensus roster-fit sort key (`consensus_fit_weight`)

**Date:** 2026-09-02 · **Branch:** `claude/consensus-fit-sort-key` (forked from `origin/main` @ `ce3f443c`) · **Scope:** [scope.md](scope.md) · **Measurement:** [results.md](results.md)

Line numbers are the branch tip's `backend/trade_service.py` unless another file is named. Every claim below is either a cited line or a test in `backend/tests/test_consensus_fit_sort_key.py` (named in brackets).

## 1. The knob is read at CALL time, through `_c`, inside the generator

| Step | Where | What |
|---|---|---|
| declared | `trade_service.py:1029` | `"consensus_fit_weight": 0.0` in `_DEFAULT_CFG`, with the comment block in the house style of the D-095 consensus knobs directly above it |
| seeded | `backend/database.py` (`_MODEL_CONFIG_DEFAULTS`, the row after `consensus_score_scale`) | `("consensus_fit_weight", 0.0, "…")` — the boot migration at `database.py:3185` inserts every tuple with `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING`, and `database.set_config` (`:4431`) raises for a key with no row, so without this seed `PUT /api/admin/config/consensus_fit_weight` would 404. [`test_default_registered_in_both_stores`] pins the two stores at the same default |
| read | `trade_service.py:7115` | `_w_fit = _c("consensus_fit_weight")` — the first statement of the sort-key block, executed on every call of `_generate_consensus_for_pair`, never at import, never via `_ts._cfg.get` (D-098 / G-058 cause 3; the `SHAPE_D` comment in `trade_optimizer.py:279-289` is the canonical explanation) |
| `_c` honours the overlay | `trade_service.py:1256-1262` | `_c` consults `_cfg_local.map` first, then `_cfg`, then `_DEFAULT_CFG` — so a `_cfg_override` on the calling thread shadows the process-global row. [`test_knob_is_read_at_call_time_through_the_overlay`]: a global 0.5 under `_cfg_override({knob: 0.0})` yields the knob-0 deck |

Sabotage S4 (results.md § Sabotages) hoists the read to `_DEFAULT_CFG[...]` and the call-time test goes red.

## 2. The `w = 0` identity is structural, not numerical

```
7118  def _fit_sort_key(pool, sign):
7119      if _w_fit <= 0:
7120          return seed_value          # ← the historical key object itself
...
7144  recv_pool.sort(key=_fit_sort_key(recv_pool, -1.0), reverse=True)
...
7153  _give_key = _fit_sort_key(give_pool, +1.0)
7154  give_pool.sort(key=lambda p: (_pos(p) in shed_positions, _give_key(p)),
7155                 reverse=True)
```

At `w ≤ 0` the factory returns `seed_value` — the same callable the two sorts used on `origin/main` (`recv_pool.sort(key=seed_value, …)` and `(_pos(p) in shed_positions, seed_value(p))`). No replacement level is computed, `_fit_norm` stays empty, and Python's sort is stable, so the pool orders are byte-identical — not "equal to within rounding", identical. The stamp at `:7330` is guarded by `if _w_fit > 0`, so the knob-0 `TradeCard` carries `consensus_fit is None` (its dataclass default, `:4329`).

Proof: [`test_knob0_is_byte_identical_to_origin_main`] and [`test_mirror_knob0_is_byte_identical_to_origin_main`] compare emitted rows (give, receive, target, composite, fairness, give_value, receive_value — in **emitted order**) against literals captured by running the same file on a `git archive origin/main` tree, where the knob does not exist. [`test_the_mirror_golden_is_not_vacuous`] shows the mirror fixture DOES move at `w = 0.5`, so the identity is a claim about the default, not a fixture that cannot move. [`test_knob0_never_stamps`] covers the stamp. Sabotages S2 (drop the shed primary key) and S3 (stamp unconditionally) each turn a golden red.

## 3. The blend, and why the sign test cannot move

```
7121  u_repl = replacement_levels(user_roster, seed_value, players, scoring_format)
7123  o_repl = replacement_levels(opponent.roster, seed_value, players, scoring_format)
7127  for p in pool:
7129      if is_pick_asset(players.get(p)): raw[p] = 0.0; continue
7134      raw[p] = sign * (marginal_value(p, seed_value, o_repl, …)
7137                       - marginal_value(p, seed_value, u_repl, …))
7139  m = max(|raw|) ; _fit_norm[p] = raw[p] / m  (0.0 when m == 0)
7142  return lambda p: seed_value(p) * (1.0 + _w_fit * _fit_norm[p])
```

* `replacement_levels` (`:3078`) and `marginal_value` (`:3142`) are the Tier-2 helpers `trade_optimizer.py:355-365` already uses; here both replacement maps are built from the rosters at `seed_value` because no partner board exists on this path. `sign = +1` on the give side (positive = worth more in the partner's lineup), `−1` on the receive side, so a positive `_fit_norm` always means "this asset moves to where it is worth more" on either side, and the card stamp (mean over both sides, `:7331-7332`) reads the same way.
* The blend touches **only the two `sort(key=…)` calls**. `_emit` (`:7195-7333`) is unchanged from `:7131-7262` on main: `package_value_v2` on both sides, `rv − gv ≥ user_gain_epsilon` (`:7227`), `consolidation_raw_loss_frac`, `user_gain_ok_1for1`, `pick_swap_ok`, `filler_ok`, the G6 hook, the fairness ratio, the gap sweetener. A reorder cannot admit a combo the gates would have rejected. [`test_sign_test_still_holds_on_every_card`] checks `receive_value − give_value ≥ ε` on every emitted card at `w ∈ {0, 0.25, 0.5, 1}` in both profile modes; [`test_knob_half_set_of_cards_is_the_same_as_knob0_uncapped`] shows the uncapped SET is unchanged and only the ORDER differs.
* The give side keeps `pos ∈ shed_positions` as the primary key (`:7154`), so "give from the positions the partner needs first" still outranks the blend.

## 4. Pick neutrality

`:7129-7131`: `is_pick_asset(players.get(p))` (`:2140`, the canonical test — `position == "PICK"` or `team == "PICK"`, so the universal pool's generic rungs with a fake position are caught too) short-circuits to `raw = 0.0`. `marginal_value` would in fact return the raw value for a position outside `_STARTER_NEED` (`:3163-3164`), which makes the asymmetry `v − v = 0` anyway, but the explicit branch means a pick priced through a rung with a fake `RB` position cannot pick up an RB replacement level by accident. A pool of picks therefore sorts on `seed_value × (1 + 0)` at every `w` — [`test_picks_keep_their_relative_order`]; an all-picks card stamps `0.0`; an all-zero-fit pool takes the `m == 0` guard at `:7140-7141` — [`test_all_zero_fit_pool_is_guarded`].

## 5. Every caller of `_generate_consensus_for_pair`, and which overlays reach it

`git grep -n "_generate_consensus_for_pair(" -- backend` (non-test): exactly two call sites, both in `_generate_trades_v2`, both splatting the same `_consensus_kw` dict built at `:6182`:

| Call site | Condition | Path share |
|---|---|---|
| `trade_service.py:6282` | `else` branch of `if member.has_rankings and member.elo_ratings:` (`:6207`) — the never-ranked partner | the 84.5% path |
| `trade_service.py:6280` | `if not cards and FLAGS.trade_divergence_fallback:` inside the boarded branch — the 2026-08-15 zero-card fall-through | additive, boarded partner whose divergence path returned nothing |

Neither passes a per-call config; both read the thread's `_cfg` / overlay through `_c`. The overlays that can be active on the calling thread, all via `_cfg_override` (`:1247`):

| Overlay | Entered at | Names the knob? | Effect on this change |
|---|---|---|---|
| `MODEL_A_PROFILE` (arm A) | `bakeoff_profiles.py:148` `model_a()`, called from `bakeoff_runner.py:1538` | **yes — pinned `0.0`** | arm A keeps the value sort whatever prod sets; verified by the harness (`A_baseline` rows are byte-identical at every `w`, results.md) and by the arm-A golden staying green un-recaptured |
| `MODEL_CHALLENGER_PROFILE` (arm D) | `bakeoff_profiles.py:234` `model_challenger()`, from `bakeoff_runner.py:1550` | **no** | arm D inherits the live row — it is the live engine under an overlay (D-095) and a partner-fit ranker is exactly the design question its PRD §4 left open, so inheriting the prod sort is the consistent choice. No reason found to pin it; stated in `scope-phase2.md` |
| #189 relaxed pass | `trade_service.py:5069`, overrides at `:5057-5064` | **no** (`fairness_floor_divergence`, `min_side_surplus*` only) | the relaxed re-run sorts with the same `w` the normal pass used |
| arm B (`current`) | no overlay | — | reads the prod row directly |

Also checked: `backend/trade_gen_v2.py` (arm C) and `backend/trade_gen_fit.py` (arm `fit`) never call `_generate_consensus_for_pair` (grep above), so the knob cannot reach them; `bakeoff_runner.py` never mentions the key. Tests that call the generator directly (`test_bakeoff_challenger.py:168/170`, `test_finder_targeting.py:375`, `test_presentment_rules.py`, `test_gap_sweetener.py`) run at the default and stay green — [results.md § Suite].

## 6. The server view path for the new stamp

`card.consensus_fit` is set at `:7332` only while `w > 0`. Downstream:

| Surface | Where | Reads it? |
|---|---|---|
| card JSON to clients | `server.py:11755` `trade_card_to_dict` — every optional attribute is emitted by name (`need_fit` at `:11846-11848`, `partner_fit` at `:11842`, …) | **no** — the function never reads `consensus_fit`; the wire payload is unchanged at every `w` |
| deck-outcome corpus | `server.py:4378` `_log_deck_signal_impressions`, `features` dict at `:4498-4529` with `"need_fit": getattr(card, "need_fit", None)` etc. | **no** — keys are named; `features_json` is unchanged at every `w`. Adding `"consensus_fit": getattr(card, "consensus_fit", None)` there is the one-line follow-up if the lead wants the corpus to carry it; it would then be a null on every non-consensus row and on every row while `w = 0`, which is the same key-always-present discipline `gap_sweetener` uses (comment at `:4519-4524`) |
| whole-object dumps | `git grep -n "asdict\|\.__dict__\|vars(c" -- backend/*.py backend/server.py` | none exist — no path serializes a `TradeCard` wholesale, so a new `None`-default field is invisible everywhere |

So: no client change, no analytics change, no JSON change at any `w`. The stamp is an in-process/QA record, exactly like `outlook_dir` / `lane_shift` (`:4343-4359`).

## 7. What the sort key can and cannot change — the "ranking" premise, qualified

The brief's premise was that "the sort key IS the ranking; the composite never reorders anything". Half of that is right and the harness shows which half:

* **Right:** the emit loops (`:7335-7366`) take the first `max_cards` combos that clear the gates in pool order, so under the per-opponent cap (prod: `exploration_base_per_opp` 5 + `exploration_overgen` 3 = 8, `server.py:6117-6121`) the pool sort decides **which** consensus cards exist for a pairing.
* **Qualified:** `_generate_trades_v2` then does `cards = sorted(cards, key=lambda c: c.composite_score, reverse=True)` at `:4951` before the deck caps, and `get_pending_trades` sorts by composite again at `:7379`. Within a pairing, consensus composite is `fairness × tier_mult × consensus_score_scale` (`:7305-7306`), so the **served order** of whatever was emitted is by fairness × tier, not by pool order. The knob therefore moves the deck only when it changes the emitted **set** — i.e. when the first `max_cards` passing combos differ.
* **Where the set changes** (probe in results.md § Per-pair probe): uncapped, the emitted order changes in nearly every pairing and the set changes in some (the gap-sweetener's `seen` dedupe is order-dependent). At cap 5/8, the first passing combos all share the top receive asset and the top few gives; the blend rarely reorders those when the receive pool is already **need-filtered** (`:7098` restricts it to `need_positions`) and the give pool is already **shed-keyed**. It reorders them decisively when the viewer has **no** need position — then `recv_pool` is the partner's whole roster and a value sort leads with the partner's single most valuable asset regardless of fit (the mirror's 1700 QB into a roster that already starts one), while `w > 0` leads with the partner's surplus. That is half of the 12-team fixture (`u1/u4/u6/u7/u8/u9/u11` have `position_needs == []`) and every prod roster with a legal startable lineup.

## 8. Not proven here, for the lead

* No prod replay: the harness leagues are synthetic (snake-drafted, DP values rescaled). The deck-level numbers in results.md bound disruption and show the effect on the no-need viewer; they are not a like-rate prediction.
* No global parity test between `_DEFAULT_CFG` and `_MODEL_CONFIG_DEFAULTS` exists in the repo — each feature pins its own keys (`test_age_pref.py:95`, `test_pass_cooldown.py:212`, `test_model_config_log.py:233`). This change pins its own; the gap (a knob added to one store and not the other passes CI until someone PUTs it) is real and not this change's to fix.
* `features_json` does not carry the stamp (§6). If the flip is to be measured by "did fit-sorted cards get liked more", the split has to come from `basis == "consensus"` × `give_positions`/`receive_positions`, which the corpus already has, or the one-line follow-up above.
