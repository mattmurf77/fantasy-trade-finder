# Feature Scope — Three-model bake-off, Phase 2: pin arm A

**Date:** 2026-08-18
**Entry point:** [docs/plans/three-model-bakeoff/PLAN.md](PLAN.md) §7 Phase 2 (direct ask)
**Builder:** backend build agent, branch `feat/bakeoff-arm-a`
**Operator sign-off on waivers:** not needed — the two waivers below (§1, §3) are
"backend-only, nothing user-visible, no surface to instrument"

---

## 0. What this phase is

Arm A of the bake-off is **not a code branch**. The 2026-08-16 G6 presentment
wave (`20b40db`) and the 2026-08-18 engine-quality wave (`60cbe11`) modified
the trade engine **in place**, so "the original engine" survives only as a set
of knob kill-values plus one flag bypass. This phase turns that set into a
named, documented constant and proves it, so the bake-off's baseline arm
cannot silently drift into meaninglessness.

Ships: a profile constant, a thread-local bypass, and tests. **Nothing
user-visible, no route change, no serving change, no schema change.** Phase 3
(the runner, `feat/bakeoff-runner`) consumes what this phase produces.

### Reference SHA

**`92c31d5`** — `review: P0 remediation verified against main`. It is
`20b40db^` on `git log --first-parent main`, i.e. the last commit before the
G6 wave landed. Carried in code as
`backend/bakeoff_profiles.MODEL_A_REFERENCE_SHA`.

### Public surface Phase 3 imports

| Import | What it is |
|---|---|
| `from backend.bakeoff_profiles import model_a` | **The one supported entry point.** Context manager applying the profile *and* the R4 bypass together |
| `from backend.bakeoff_profiles import MODEL_A_PROFILE` | The pinned knob dict, if the runner needs to log/report it |
| `from backend.bakeoff_profiles import MODEL_A_REFERENCE_SHA` | For `bakeoff_runs` provenance |
| `from backend.trade_service import r4_bypass, r4_bypassed` | The bypass primitives, if the runner needs them apart from `model_a()` |

Using `_cfg_override(MODEL_A_PROFILE)` **without** `r4_bypass()` produces a
silently wrong arm A — R4 is the one G6 rule with no knob. `model_a()` exists
so that mistake is not available.

## 0.1 `MODEL_A_PROFILE` — the audit

Method: `git diff 92c31d5..origin/main -- backend/database.py backend/trade_service.py`
over the `model_config` seed rows and `trade_service._DEFAULT_CFG`, plus
`docs/plans/engine-quality/scope.md` and
`docs/feedback/items/304-positional-need-filter/`. Fourteen keys were added in
that range and two (`gen2_g6_net_position_cap`, `gen2_pick_band_frac`) were
removed. No pre-existing knob's default was re-tuned.

**Included — ten keys, every post-reference-SHA v1-generation knob:**

| Knob | Wave | Rule | Disable value verified at |
|---|---|---|---|
| `max_overpay_frac` | G6 | R1 #340 overpay ceiling | `trade_service.overpay_ok` — `frac <= 0` returns True |
| `pos_net_cap` | G6 | R2 #341 per-position net cap | `pos_net_ok` — `cap <= 0` returns True |
| `pick_gap_frac` | G6 | R3 #339 pick-is-the-gap band | `pick_gap_ok` — `frac <= 0` returns True |
| `need_gate_min_value` | G6 | R5 #304 need gate | `need_gate_ok` — `floor <= 0` returns True |
| `rank_div_min_frac` | engine-quality | C1 divergence-gated ranking fairness | `<= 0` ⇒ fairness unchanged |
| `min_package_band` | engine-quality | C2 minimal-package preference | `0` ⇒ closest-gap-wins |
| `pick_pair_strip_frac` | engine-quality | C3 matched-pick-pair strip | `<= 0` ⇒ literal 1-for-1 ban only |
| `deck_headliner_cap` | engine-quality | C4 headliner diversity cap | `0` ⇒ uncapped |
| `deck_give_headliner_cap` | give-headliner cap, 2026-08-19 | C4b give-side headliner cap | `0` ⇒ uncapped |
| `mismatch_confidence_damp` | engine-quality | C5 confidence damping | `<= 0` ⇒ undamped |

**Excluded — each with its reason** (per the mission's requirement that every
exclusion be justified):

> **2026-08-19 (D-095).** The landability challenger was briefed as "the new
> arm A" and is deliberately **not** one: it ships as a fourth arm,
> `challenger`, with its own `MODEL_CHALLENGER_PROFILE`. `MODEL_A_PROFILE`,
> `model_a()` and the arm-A golden's captured deck are unchanged by that work
> — arm A is the bake-off's only fixed point, and overwriting it makes every
> comparison unfalsifiable (D-075). The five knobs the challenger introduced
> are excluded below, and the first row is the reason why in detail.

| Key | Added | Why arm A does not set it |
|---|---|---|
| `max_overpay_min_value` | G6 | **Inert companion.** `overpay_ok` returns True at `max_overpay_frac <= 0` before reading it. Pinning it would imply it matters. |
| `pick_gap_min_value` | G6 | Inert companion of `pick_gap_frac`, same reason. |
| `need_gate_upgrade_margin` | G6 | Inert companion of `need_gate_min_value`, same reason. |
| `pass_cooldown_days` | D-067, 2026-08-17 | **Not generation logic.** It sets how long a *dismissed* trade stays excluded (was hard-coded 7 days, now 14). The exclusion set is built once per job in `server.py`, upstream of every arm, from the user's own swipe history. Differing here would make arm A re-serve trades the user explicitly dismissed — a user-facing harm, and a confound (arms would differ in "which of your dismissals do I respect", not in generation). All three arms share one past-decision set. |
| `pass_cooldown_start_epoch` | D-067 | Same — the amnesty cutoff for the same shared exclusion set. |
| `force_supersedes_running` | 2026-08-18 | **Not generation logic.** Job-cache/route semantics of `POST /api/trades/generate` (`force: true` superseding an in-flight job). Does not enter any generator. |
| `pin_exclude_comparisons` | Phase 0 (F1) | **Board computation, and deliberately live.** PLAN.md §3.4 "What must NOT be frozen": Phase 0's unpinning stays on for all three arms, or the bake-off measures which model best mines a frozen board. |
| `pin_unpin_on_newer_swipe` | Phase 0 (F2) | Same. |
| `pin_legacy_at_epoch` | Phase 0 (F2) | Same. |
| `likes_you_gate_level`, `likes_you_min_user_gain` | D-096, 2026-08-19 | **Not generation logic — serving-layer post-process, and a live user-facing fix.** Both are read only by `server._inject_likes_you_cards_impl`, which runs in `_run_trade_job` AFTER every generator has returned, on the deck all three arms share; no generator reads them. Same class as `pass_cooldown_days` above. Pinning arm A to level 0 would make arm A the only arm still serving cards whose value bar shows the user paying (115 of 198 served likes-you impressions, worst -5,571 — `docs/plans/likes-you-quality-gates/scope.md`), which is a user-facing harm and a confound: the arms would differ in "do I show you insulting mirrored likes", not in generation. The arm-A golden is unaffected — `_deck()` calls the generators directly and never reaches the injector — and was re-run green with this change. |
| `pick_year_decay_r1` … `_r4` | D-079, 2026-08-19 | **Asset valuation, not generation logic — and deliberately live for all three arms.** These four set how much a draft pick's value decays per season it is in the future (`pick_values.year_decay`, consumed by `pick_pool_value` / `discount_pick_value` / `compute_pick_value`). They price an ASSET; they do not decide which package to build out of priced assets. Pinning arm A to the pre-D-079 uniform 0.85 would make a 2029 1st worth 1300.1 to arm A and 2117.0 to arms B/C, so any deck difference would confound generation policy with a repricing — exactly what PLAN.md §3.4 forbids for the board itself. Same class as `elo_value_k` / `ktc_k` / `ktc_blend_weight`, which are likewise unpinned: the value space is shared ground the arms compete on, not a variable under test. The arm-A golden is unaffected (its fixture deck reprices identically) and was re-run green at the time of the change. |
| `infer_w_net_firsts`, `infer_net_firsts_cap` | #365, [D-110](../../../living-memory/DECISIONS.md), 2026-08-20 | **Cannot reach generation — the strongest exclusion on this page.** They weight the net first-round-pick term inside `infer_team_outlook`, whose verdict DOES feed generation via `outlook_alpha`. But the term is gated on BOTH the `trade.outlook_net_firsts` flag AND a caller supplying `first_round_ledger`, and the only caller that supplies one is `GET /api/league/team-review`. `trade_gen_v2.py:986`, `trade_service.py:4381`, the mock draft (`server.py:14013`) and the outlook seed (`server.py:5320`) all still pass four positional arguments, so no arm can observe either knob at any flag setting (INV-365b, pinned by `test_flag_on_without_a_ledger_is_still_the_golden`). Pinning a kill value in `MODEL_A_PROFILE` would imply they matter to a deck; they provably do not. The arm-A golden is unaffected and was re-run green with this change. If the ledger is ever plumbed into a generator, that change owns re-deciding this row. |
| `gen2_*` (all) | pre-dates / arm C | `trade_gen_v2` is **arm C**. Arm A must not touch its knobs. |
| `bakeoff_serve_interleaved` | Phase 3, 2026-08-18 | **Not generation logic — it is the bake-off's own orchestration.** Read only by `bakeoff_runner._cfg`, never by any generator: it selects Phase-4 dark validation vs Phase-5 interleaved serving, which is a decision about the merged deck, made after all three arms have already run. Setting it per-arm would be meaningless. |
| `bakeoff_deck_limit` | Phase 3, 2026-08-18 | Same — a cap on the INTERLEAVED deck, applied by the team-draft merge after generation. No arm can see it. |
| `user_elo_shrink`, `consensus_both_ways`, `consensus_fairness_floor` | D-095, landability challenger (arm D), 2026-08-19 | **Their defaults ARE the pre-wave engine — pinning a kill value would CHANGE arm A, not preserve it.** This is the one exclusion on this page that runs the opposite way to all the others. Every other row is "a knob post-dating the reference SHA, disabled so arm A behaves as it did"; these three are knobs whose *live default* is the pre-wave behaviour and whose *non-default* value is a proposal about the future. `user_elo_shrink` = 1.0 is the confidence blend the engine has always done; `consensus_both_ways` = 0.0 is the `rv >= gv` sign test it has always applied; `consensus_fairness_floor` = 0.0 is "use whatever threshold the caller passed". Setting any of them to the challenger value in `MODEL_A_PROFILE` would make arm A skip shrinkage and emit both directions of an even trade — behaviour the pre-G6 engine never had, silently rewriting the baseline that every bake-off comparison is measured against. They belong to `bakeoff_profiles.MODEL_CHALLENGER_PROFILE` and nowhere else ([landability-challenger PRD](../landability-challenger/PRD.md) N1, A2). All three are pinned in `_PINNED_KNOBS` as usual, so the inventory guard still fires if a fourth appears. |
| `bakeoff_include_challenger`, `bakeoff_include_gen_v2` | D-095, 2026-08-19 | Same class as `bakeoff_include_baseline` below — **arm roster, not generation.** Read only by `bakeoff_runner.arm_roster()`, before any arm runs; an arm cannot observe which other arms are on the roster. |
| `bakeoff_group_size`, `bakeoff_group_value_slots`, `bakeoff_fill_policy`, `bakeoff_lane_reallocate`, `bakeoff_include_baseline` | composition, 2026-08-18 / D-086 2026-08-19 | Same class — **deck composition, not generation.** All five are read only by `bakeoff_runner`, after every arm has finished producing its ranked list, and they decide how those lists are narrowed, quota'd and merged. An arm cannot observe them, so a per-arm value would be meaningless. `bakeoff_lane_reallocate` in particular only ever moves a SLOT between lanes inside one already-generated group; it cannot change, add or remove a card any arm proposed. |
| `fit_r5_mode` | fit challenger PR-F1, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_junk_floor` | fit challenger PR-F1, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_score_scale` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_score_even` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_w_board` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_w_div` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_w_cons` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_pool_consensus` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_pool_div_seed` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_pool_div_opp` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_pool_cap` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_max_packages_per_pair` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_expand_from` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_min_them` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `fit_min_aggregate` | fit challenger PR-F2, 2026-08-20 | Generation knob for `trade_gen_fit`, a module arm A never imports; no effect on MODEL_A_PROFILE output. |
| `bakeoff_include_fit` | fit challenger PR-F3, 2026-08-20 | Arm roster / serving bit, not generation — read only by `bakeoff_runner` before or after any arm runs; an arm cannot observe it. |
| `bakeoff_serve_fit` | fit challenger PR-F3, 2026-08-20 | Arm roster / serving bit, not generation — read only by `bakeoff_runner` before or after any arm runs; an arm cannot observe it. |
| `package_bench_trade_wide` | benchmark fix, 2026-08-21 | **Generation logic post-dating the reference SHA → INCLUDED in `MODEL_A_PROFILE` at its kill value 0.0.** The pre-wave engine benchmarked package depth against each side's own best asset; at ≤ 0 that math is byte-identical (proven by `test_package_benchmark.py::test_kill_value_is_byte_identical_to_pre_fix_math`), so the golden did NOT need re-capturing — verified 10/10 green with the pin. |
| `package_floor_cross` | benchmark fix, 2026-08-21 | **Inert companion.** `_package_value_market` never reads it while `package_bench_trade_wide` ≤ 0 (arm A's pin) — same rule as `max_overpay_min_value`. Pinning it would imply it matters to arm A. |
| `sweetener_gap_threshold` | gap auto-sweetener, 2026-08-21 | **Generation logic post-dating the reference SHA → INCLUDED in `MODEL_A_PROFILE` at its kill value 0.0.** At ≤ 0 the gap-sweetener pass is skipped entirely and every generator is byte-identical to its pre-sweetener self; the pre-wave engine had no sweetener. |

> **2026-08-21 — the 25 `breaker_*` keys.** The counterparty breaker
> ([LLD](../counterparty-breaker/LLD.md) §4) adds an **evaluation layer**, not a
> generator: `backend/trade_breaker.py` is imported by no generator and no ranker, runs
> after the deck-mutation stack has completed, and mutates only a new card attribute. No
> arm can observe one of these knobs at any value, so pinning a kill value in
> `MODEL_A_PROFILE` would imply they matter to a deck; they provably do not. This is the
> same shape of exclusion as the `fit_*` rows above, one layer later in the pipeline. The
> one knob the breaker also reads, `waiver_slot_cost`, is an **existing engine
> registration** reused as-is (`_SHARED_ENGINE_KNOB_KEYS`, LLD §1.1) — it is not one of
> the 25 and its disposition is unchanged by this feature.

| Key | Added | Why arm A does not set it |
|---|---|---|
| `breaker_ms_budget` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_budget_checkpoint_frac` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_degraded_share_max` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_min_severity` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_max_repeat_frac` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_shadow_run` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_outlook_haircut_legacy` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_outlook_narrate_margin` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_board_div_min` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_board_min_divergent` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_value_scale` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_crunch_scale` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_floor_fit_outlook` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_floor_fit_new_weakness` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_floor_fit_duplicate` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_floor_value_giving` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_floor_value_giving_consensus` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_floor_other_player_keep` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_floor_roster_crunch` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_narrate_fit_outlook` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_narrate_fit_new_weakness` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_narrate_fit_duplicate` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_narrate_value_giving` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_narrate_other_player_keep` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |
| `breaker_narrate_roster_crunch` | counterparty breaker, 2026-08-21 | Evaluation-layer knob for `backend/trade_breaker.py`, a module no generator or ranker imports; it runs after the deck-mutation stack completes and mutates only a new card attribute; no effect on MODEL_A_PROFILE output. |

**R4 (#336 windowless awaiting/matched exclusion) has no knob** — the
`trade.presentment_rules` flag is its only switch, and flipping that flag
would disable R4 for arms B and C and for every other user of the process.
Hence the thread-local bypass (§2 below), which PLAN.md §3.3 predicted as the
one code change G6 forces.

---

## 1. Analytics scope

- **(c) WAIVED — no analytics needed because:** this phase adds no user-visible
  surface and emits nothing. Arm attribution (`deck_impressions.model_arm`,
  `arm_rank`, `bakeoff_runs`) is Phase 3's scope, specced in PLAN.md §5.

## 2. Schema & flag scope

- New/changed tables or columns: **none.**
- New/changed feature flags: **none.** Deliberate: arm A must be reachable
  *without* flipping `trade.presentment_rules`, because that flag is global and
  arms B/C need R4 on. The bypass is thread-local instead.
- New env vars / `model_config` keys: **none.** `MODEL_A_PROFILE` reuses the
  existing keys through the existing `_cfg_override` thread-local seam; nothing
  is added to `model_config`, and the DB defaults are untouched, so arms B and C
  and every ordinary job are byte-identical to before this branch.
- Deploy-free rollback lever: not applicable — nothing is on. The new code is
  inert until a caller enters `model_a()`, and the only caller today is the test
  suite.

## 3. Evidence scope

- **Structural guard (`mobile/tests/check-*.js`):** WAIVED — backend-only, no
  mobile surface.
- **Unit tests:** `backend/tests/test_bakeoff_arm_a_golden.py` — 10 tests:

  | Test | Proves |
  |---|---|
  | `test_arm_a_reproduces_the_pre_wave_deck` | The golden. Arm A's deck == output captured at `92c31d5`, byte for byte |
  | `test_arm_a_reproduces_the_pre_wave_asset_ideas` | Same on the second generation surface (`generate_asset_ideas`), which is the only place C2 runs |
  | `test_arm_a_is_flag_independent` | The profile alone carries arm A — toggling `trade.presentment_rules` does not change arm A's deck |
  | `test_current_defaults_differ_from_the_golden` | **Non-vacuity.** Arm B (live defaults) on the same fixture does NOT match the golden (30 cards → 8) |
  | `test_every_pinned_rule_actually_bites_on_this_fixture` | **Per-rule non-vacuity.** Arm B records kills for R1/R2/R3/R5; C1, C4, C5 each move the deck alone; C2 moves the ideas alone |
  | `test_pick_pair_strip_kill_value_is_load_bearing` | C3 at its own gate (`pick_swap_ok`) — see the known gap below |
  | `test_r4_bypass_restores_a_card_the_flag_would_exclude` | R4: given an exclusion key for a golden card, arm B drops it (`R4` count 1), arm A keeps it (count 0) |
  | `test_r4_bypass_is_thread_local` | A concurrent sibling thread still sees R4 on |
  | `test_no_generation_knob_was_added_without_an_arm_a_decision` | **Drift alarm.** The 189-key `_DEFAULT_CFG` inventory is pinned; any added or removed knob fails with the key named |
  | `test_model_a_profile_only_names_real_knobs` | A renamed/deleted knob cannot leave the profile silently disabling nothing |

- **Code-walk proof** — how the fixture is made immune to board-computation
  drift, which is the whole design problem. Everything between `92c31d5` and
  today that changes generation *inputs* (Phase 0's pin fix, tier-bounded
  voting on `feat/tier-bounded-pins`, premium import) would make a naive
  end-to-end golden differ for reasons unrelated to the two waves. So the
  fixture supplies **every input as a literal** and calls the generator
  directly:
  - `_USER_ASSETS` / `_OPP_ASSETS` / `_OPP_BOARD` — literal `(position, seed
    elo, user elo)` tables and literal opponent boards;
  - `_generate()` passes `seed_elo=`, `user_elo=`, `user_roster=`,
    `confidence=`, `outlook=`, `fairness_threshold=` explicitly to
    `TradeService.generate_trades`;
  - no DB read, no `ranking_service` call, no fixture file, no
    `comparison_counts`, no pin resolution — none of the machinery Phase 0 or
    tier-bounded voting touches is on the path.

  The comparison therefore isolates **generation logic**. The corollary is
  stated in the test docstring: changing the fixture invalidates the pin and
  requires a re-capture (procedure is in the module docstring).

- **Manual TestFlight checklist:** WAIVED — nothing ships to a client. The new
  code paths are unreachable in production until Phase 3 wires a caller behind
  flag `trade.bakeoff` (default OFF).
- `testID`s added/renamed: none.

### Known gap, recorded rather than papered over

`pick_pair_strip_frac` (C3) is the one profile entry the **deck** fixture
cannot exercise: C3 only kills when stripping matched pick pairs empties a
side, and no such shape survives the other gates on this league (the shapes
that would produce it are killed by R3 first). Manufacturing one would mean
contorting the fixture into a league that does not resemble a real one, which
would make the golden brittle for no gain. Instead
`test_pick_pair_strip_kill_value_is_load_bearing` asserts C3 at its own gate
(`trade_service.pick_swap_ok`), and byte-identity of C3's kill value is already
pinned independently by `backend/tests/test_engine_quality_golden.py` against
`90fb19a`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed, removed, or contract-changed. R4's behaviour on every existing route is unchanged: the bypass is off unless a caller enters `model_a()`, and no route does |
| `living-memory/LLD.md` | n/a | No schema/route/invariant convention shifted. The bypass reuses the existing `_cfg_override` thread-local convention rather than introducing one |
| `docs/architecture.md` | n/a | No module wiring or data-flow change. `bakeoff_profiles` is a leaf module imported by nothing in the serving path; Phase 3's runner is the architecture change and updates this doc |
| `living-memory/HLD.md` | n/a | Same — arm A is a config profile, not a new component |
| `docs/cross-client-invariants.md` | n/a | No shared constant, enum, or colour. `MODEL_A_PROFILE` is backend-only and no client reads it |
| `docs/glossary.md` | **updated** | "Arm A / baseline", "MODEL_A_PROFILE", "R4 bypass" |
| `docs/config-reference.md` | **updated** | New § "Bake-off arm A — `MODEL_A_PROFILE` + the R4 bypass", under the trade presentment rules section |
| ADR / `DECISIONS.md` | **updated** | D-069: arm A is pinned as a constant + golden, and the knob inventory is pinned too |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` — full suite run on this branch after
  rebase onto `origin/main`; `tsc --noEmit` and `testid-lint` unaffected (no
  mobile files touched).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **Simulator gate:** D-056 standing posture — `FTF_SKIP_SIM_GATE=1`; no
  simulator evidence exists or is claimed. Backend-only change.
- **TestFlight verification:** none written (see §3 waiver).
- Express lane declared by the operator? **No** — full gates.
