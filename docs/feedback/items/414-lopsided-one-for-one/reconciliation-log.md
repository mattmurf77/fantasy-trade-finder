# Reconciliation log — G-414, Phase 1 round 2 (Author incorporation of the Planner's round-1 critique)

> Input: [review-round-1.md](review-round-1.md) (Planner, 2026-09-02, against the round-1 `lld-delta.md` / `prd.md` / `scope.md`).
> Every cite in the critique was re-verified against the worktree (HEAD `48f40de5`) before incorporation.
> **Outcome: 11 objections incorporated, 0 rebutted, 0 for arbitration.** Both blocking fixes landed.
> **Mini-round (build-time gaps, §6): 3 gaps, all incorporated per orchestrator ruling; decision relabelled D-176 → D-173 (unshipped parallel build; see D-175).**
> One cite in the critique is corrected below (objection 2's crown-branch line) — a cite slip, not a
> substantive disagreement.

## Table of contents

- [1. Objections](#1-objections)
- [2. Rulings on the Author's six open questions](#2-rulings-on-the-authors-six-open-questions)
- [3. Corrections to the critique's own cites](#3-corrections-to-the-critiques-own-cites)
- [4. Test-delta recount](#4-test-delta-recount)
- [5. Deviations from the plan, final list](#5-deviations-from-the-plan-final-list)
- [6. Mini-round (build-time gaps)](#6-mini-round-build-time-gaps)

---

## 1. Objections

| # | Objection (short) | Blocking | Outcome | Where it landed |
|---|---|---|---|---|
| 1 | Acceptance fixture X1 = 1600 sits 5.2 units under the consensus `user_gain_epsilon` edge; legal window flags-off is [1497.4, ≈1606] | **Y** | **Incorporated.** X1 → **1550** (flags-off `[G, X1]` gv 6815.3 / rv 6862.0, gap 46.7; prod rv 7302.5, gap 487.2). Three validity pre-asserts added: (a) `[G, X2]` gap > eff; (b) X1 ≥ 0.25 × G and ≥ 450; (c) `[G, X1]` gv < rv. Rule restated: a pre-assert failure moves X1/X2 inside the window, never `eff`. | prd.md §4 (fixture, "Why 1550", pre-asserts, arithmetic table), §6.1 T-1, T-4a; scope.md §3 |
| 2 | Arithmetic table assumed crown OFF; prod has `trade.crown_asset: true` | N | **Incorporated.** Table now has a flags-OFF column (test truth, `_isolate` uses `DEFAULT_FLAGS`) **and** a prod (crown ON) column with hand-computed rv 7251.0 / 7365.5 / 7302.5 / 7278.5 and eff 725.1; the critique's tool-run numbers for `[G, 1550]` / `[G, 600]` agree to ±0.1. Noted that the prod bare gap is 1261.5 (17.4 %), not the plan's raw 872.5. | prd.md §4 |
| 3 | S-5 "or instead of and" is wrong-but-inert (`eff = min(0, …) = 0` ⇒ nothing closes ⇒ T-5 still green) | N | **Incorporated.** Replaced by **S-5′ "threshold ≤ 0 means unset"**: `gap_close_target` returning `frac × max` when `gap_threshold <= 0` **and** an `or` guard — sweetens under arm A's pin, T-5 goes red. The retired S-5 is kept in the row as the explanation of why it was retired. | prd.md §6.1 T-5 |
| 4 | S-7b (mid-loop `cards.remove`) does not go red at `max_cards=2` — the skipped element is the sibling, which needs no processing | N | **Incorporated.** The v3 T-7 fixture is extended with a **second organic card after the bare in `cards`** (a second opponent asset `R2` whose 1×1 sits in the frac window and is closable by an X2-sized piece) and asserts **it** is sweetened; a mid-loop removal skips it. The row explains why plain `max_cards=2` would not have gone red. | prd.md §6.1 T-7; lld-delta.md §4.1 (fixture note) |
| 5 | Checklist step 4 offered a direct DB row update as a lever; `_cfg` reloads only at start (`server.py:449`) and inside `PUT /api/admin/config/<key>` (`:18577-18601`, reload at `:18600`) | **Y** | **Incorporated.** Step 4 is pinned to `PUT /api/admin/config/sweetener_gap_frac`, header `X-Cron-Secret: $CRON_SECRET` (`_require_cron_auth` `:20943`), body `{"value": 0, "source": "testflight-414"}` then `{"value": 0.10, …}`; notes the `model_config_changes` row; the direct-DB alternative is **dropped** with the reason stated. The lever surface is also recorded in lld-delta §1 (new "Live change" row) and scope.md §2. | prd.md §6.4 step 4; lld-delta.md §1; scope.md §2, §3 |
| 6 | C1 pin has 0.48 pp of margin, undocumented (bare `uA→oB` 0.9048 ⇒ 9.52 %); below 0.0952 the pick becomes an equalizer under `_ORTHOGONAL_GATES_OPEN` and the test goes red | N | **Incorporated.** PRD §1 states the 0.48 pp margin and the mechanism; config-reference row gains the verbatim tuning gotcha; D-173 (unshipped parallel build; see D-175) gains a Consequences line (4); lld-delta §1 gains a "Tuning floor" row; scope.md §2 and §4 carry it. | prd.md §1, §7, §9; lld-delta.md §1; scope.md §2, §4 |
| 7 | T-3 is tautological (tuple equality with the default call — both resolve `gap_frac=0.0`) | N | **Incorporated.** T-3 now asserts the **literal** expected results per case with an explicit `gap_frac=0.0` (X1 tuple; `None` for gap-500, unclosable, untouchable, `extra_ok_fn=False`, `give_candidates=["X2"]`; `"X1"` for the full-roster pools call). The row records why the equality form would not go red. | prd.md §6.1 T-3 |
| 8 | Consensus collision branch under-explained: 1×1s enumerate first (`:7265-7279`), so the only reachable sibling-first case is two bares closing to the same combo — a builder could conclude the branch is dead | N | **Incorporated.** lld-delta §4.3 names the enumeration order with cites and the one reachable shape (`[A]→[R]` closed with `B`, then `[B]→[R]` closed with `A`), states "the branch is not dead — do not omit it", and carries the outcome-level invariant. PRD R-A2.7 mirrors it. | lld-delta.md §4.3, §7; prd.md §2 R-A2.7 |
| 9 | "D-173 (unshipped parallel build; see D-175) in id order" — the entry block is newest-first (D-171 `:1046`, D-170 `:1065` … D-153 `:1471`) | N | **Incorporated.** "Insert directly **above** `## D-171` at `:1046`; index row after `:522`." | prd.md §7, §9; scope.md §4 |
| 10 | T-2's "candidate leaving gap 1600 is rejected" proves S-2 only if the residual is also ≤ 0.10 × 20000 | N | **Incorporated.** Constraint stated: residual gap in **`(1539, 2000]`** — the only residual that separates the correct `min` from the sabotage. | prd.md §6.1 T-2 |
| 11 | No explicit test of the consensus epsilon window on viewer-favoured cards | N | **Incorporated.** New **T-4a-ov** `test_consensus_epsilon_window_serves_the_overshoot_bare`: equalizer at 1700 (flags-off gv 6941.0 > rv 6862.0) — helper accepts (asserted directly), consensus arm serves bare, deck non-empty; sabotage S-ov (`extra_ok_fn=None` at the site, or drop the epsilon line). Noted that in prod the crown credit keeps `gv < rv` at 1700, so this is a flags-off test, not a prod observation. Also added as acceptance criterion §4-5 and known-limit §5. | prd.md §4, §5, §6.1 T-4a-ov; lld-delta.md §7 |

**Verified-and-not-objected items** in the critique (helper contract, master-switch order, pre-check parity, R-C precedence and renderers, D-143 statement, `test_shape_knob.py` / arm-C / arm-A golden safety) are accepted as-is; the T-10 residual-risk note (`test_bakeoff_challenger.py`, `_v2_cards(max_per_opponent=3)`) is folded into PRD T-10 with the instruction to run the suite at the new default before writing new tests.

## 2. Rulings on the Author's six open questions

| Q | Ruling | What changed |
|---|---|---|
| 1 Consensus collision ordering | Accept the asymmetry; specify the invariant at the outcome level (*at most one card per balanced key; no bare surviving beside its balanced key*); do **not** pre-populate `seen`; T-7 asserts keys only | lld-delta §4.3 rewritten around the invariant and the one reachable case; §7 gains the invariant bullet; PRD R-A2.7 + §4-4 "key-level facts only"; D-173 (unshipped parallel build; see D-175) consequence (2) |
| 2 v3 post-loop drop | Accept "pair −1 per collision", **no backfill** (`scored` `:647-657` would need the diversity walk re-entered; the deck is F7-over-generated and globally ranked at `trade_service.py:6449`; per-pair count is a budget, not a cap — D-154) | lld-delta §4.1 "No backfill" paragraph; PRD R-A2.7 v3 bullet; D-173 (unshipped parallel build; see D-175) consequence (1) |
| 3 gen_v2 no collision rule | Confirmed, with the argument that a closable bare never reaches `_dedup_batch` as bare and an unclosable bare with an organic balanced sibling cannot occur (or is a different sibling at Jaccard 0.5) | lld-delta §4.4 rewritten with the cites (`:737-802`, `:802`, `:857-882`, `:863-867`, `:657-706`, `:591-628`); PRD T-4a arm-C outcome assertion "no surviving card for R is bare with gap > eff"; D-173 (unshipped parallel build; see D-175) consequence (3) |
| 4 Shape drift | Watched, not gated — a helper shape gate would contradict the shipped 3×1 pin (`test_gap_sweetener.py:326-337`); **pre-register a +5 pp absolute 3×1 tripwire** in TEST_LEDGER (builder reports before merge, operator decides, no auto-block); `test_shape_knob.py` cannot detect it | PRD §6.2, §4-7; scope.md §3, §5; D-173 (unshipped parallel build; see D-175) consequence (5) |
| 5 Consensus epsilon window | Explicit test required | T-4a-ov (objection 11) |
| 6 Lever surface | `PUT /api/admin/config/<key>` **only** | Objection 5 |

## 3. Corrections to the critique's own cites

| Critique says | Verified | Used in the specs |
|---|---|---|
| Objection 2: "`package_value_v2` crown branch `trade_service.py:1605-1610`" | `:1605-1610` is inside the docstring / legacy **'heavy'** branch (`FLAGS.trade_crown_asset and n_other is not None` at `:1616`). The **market** crown credit that prod actually runs is `_package_value_market` at **`:1689-1700`** (`if FLAGS.trade_crown_asset and other_values:`). The numbers in the objection are unaffected — they were computed by running the code. | `:1689-1700` |
| Ruling 4: "`test_gap_sweetener.py:325` already asserts a 3×1 … (`:321-330`)" | The 3×1 assertion `sorted(c.give_player_ids) == ["G1", "G2", "X1"]` is at **`:336`** inside `test_v3_gap_card_is_sweetened_at_default` (`:326-337`); `:321-330` spans the end of the `_v3_cards` call and the test's opening lines. | `:326-337` |

Neither changes any conclusion.

## 4. Test-delta recount

Round 1 said "10 pytest items" (T-1…T-10). Round 2:

| Item | Functions | Node ids | Named sabotage |
|---|---|---|---|
| T-1 helper frac trigger (X1 = 1550, 3 pre-asserts, frac-0 half) | 1 | 1 | S-1 |
| T-2 never loosens (residual in `(1539, 2000]`) | 1 | 1 | S-2 |
| T-3 default-kwarg byte-identity (literal results, parametrised × 6) | 1 | 6 | S-3 |
| T-4a per-arm sweetened at default (v2, consensus, v3, arm C — arm C adds the outcome assertion) | 4 | 4 | S-4a |
| T-4b per-arm frac-0 brings the bare back | 4 | 4 | S-4b |
| **T-4a-ov** consensus epsilon-window overshoot served bare (NEW) | 1 | 1 | S-ov |
| T-5 master switch beats frac (+ `MODEL_A_PROFILE` absence) | 1 | 1 | S-5′ (S-5 retired) |
| T-6 untouchable never balances; deck never empties | 1 | 1 | S-6 |
| T-7 sibling beats bare (v3 with a second closable card after the bare; v2 divergence) — key-level | 2 | 2 | S-7a, S-7b |
| T-8 payload precedence | 1 | 1 | S-8a, S-8b |
| T-9 seed/default parity | 1 | 1 | S-9 |
| **New file total** | **19** | **24** | **12** (S-8a/b counted as one) |
| T-10 regression — existing suite, unedited (baseline 4483 passed / 1 skipped, TEST_LEDGER 2026-08-31); run at the new default first | 0 new | — | S-10 |

Net: **+1 test function (T-4a-ov), +6 node ids from T-3's parametrisation being made explicit, one sabotage replaced (S-5 → S-5′), one added (S-ov).**

## 5. Deviations from the plan, final list

All five round-1 deviations were confirmed by the Planner (critique §A). No new deviations were introduced in round 2; the round-2 changes are test-sharpening, fixture sizing, doc precision and the ruling records above. The contract in lld-delta §1–§6 is unchanged from round 1.

## 6. Mini-round (build-time gaps)

The build agent implemented lld-delta §1–§6 verbatim and, per PRD T-10 ("run the suite at the new default first"), found three contract gaps. The orchestrator ruled on each; the Author verified every cite and patched the docs. **No code was written by the Author.**

| # | Gap | Blocking | Ruling | Where it landed |
|---|---|---|---|---|
| G-1 | The single accept `abs(n_gv − n_rv) <= eff` made the pass do **less** than D-143 on wide-gap cards: when the only sufficient equalizer narrows the gap under 1539 but not under `eff`, the helper returned `None` and the card served **bare with its full gap**. Reproduced on shipped fixtures — `_mini_league` 1600 → 977.7 (eff 700), `_v3_league` 2908.7 → 1336.5 (eff ≈ 900) — four legacy asserts red: `test_gap_sweetener.py:235`, `:330`, `:368`, `:431` (verified: each is the `assert sweet, "… was not sweetened"` line). | **Y** | **Two-tier accept.** `eff` once, trigger `> eff` unchanged; walk cheapest-first: first gate-clearing candidate with residual `<= eff` returns immediately (tier 1); else remember the first with residual `<= gap_threshold` (tier 2 = D-143) and return it after the walk; else `None`. `:918` (residual > `gap_threshold` ⇒ reject) stays the D-143 line for both tiers. At frac ≤ 0, tier 1 ≡ tier 2 ≡ today. Consequences written: never widens a served gap vs D-143; `gap_after` may exceed `eff` on tier 2 and R-C still marks; London returns X1 regardless of the tier-2 X2 ahead of it. | lld-delta §3 (rewritten: line table, walk sketch, semantics, new §3.1 "why the single rule was wrong"), §7 (new invariant bullet), §8; PRD R-A.3, G-2, §4 (pre-assert (a) → tier-2 candidate; table rows; accept 1 "X1 regardless of walk order"; new accept 6 tier-2), §5 (tier-2 known limit), §6.1 T-1/T-2/T-3 (expected values confirmed unchanged and why), **new T-11** `test_helper_tier2_fallback_narrows_when_no_candidate_reaches_eff` (S-11 drop tier 2 ⇒ `None`) and **new T-12** `test_helper_tier1_beats_tier2_regardless_of_order` (S-12 first tier-2 hit wins ⇒ X2), §9 D-173 (unshipped parallel build; see D-175) consequence (6); scope.md §3 |
| G-2 | `test_gap_sweetener_arm_c.py::test_arm_c_kill_value_is_a_byte_identical_no_op` asserts `deck(10 ** 9) == off` (`:239`); with the frac at 0.10, `eff = min(1e9, 0.10 × max)` fires. | N | **Declared re-spec.** That leg pins "huge absolute threshold ≡ off", an invariant this item retires (`≤ 0` is the master switch). The builder pins `sweetener_gap_frac = 0` for the `10 ** 9` leg only, with a dated D-173 (unshipped parallel build; see D-175) comment; the `deck(0.0)` / `deck(-1.0)` legs (`:235`, `:238`) and the literal pre-sweetener asserts stay. Named in TEST_LEDGER. | PRD R-D.10 (retired invariant), T-10 (the one declared re-spec, with reason), S-10 widened; lld-delta §5, §8; scope.md §2, §3, §5; D-173 (unshipped parallel build; see D-175) consequence (7) |
| G-3 | PRD R-D said `test_bakeoff_arm_a_golden.py` "stays green untouched" — impossible: `test_no_generation_knob_was_added_without_an_arm_a_decision` (`:724-727`) requires every `_DEFAULT_CFG` key in `_PINNED_KNOBS` (`:527`) plus a disposition row in `docs/plans/three-model-bakeoff/scope-phase2.md`. | N | Add the token `sweetener_gap_frac` to `_PINNED_KNOBS` and an **exclusion** row to scope-phase2 on the `package_floor_cross` "inert companion" precedent (`scope-phase2.md:122`, verified): inert while `sweetener_gap_threshold ≤ 0`, which `MODEL_A_PROFILE` pins. `MODEL_A_PROFILE` **not** edited; golden **not** re-captured. Those two files + scope-phase2.md are now in the build's file ownership. | PRD R-D.10, R-F.12, T-10, §7 docs table (new scope-phase2 row); lld-delta §1 (new "Arm A bookkeeping" row with the row text), §5, §8 (ownership); scope.md §2, §4 (new scope-phase2 row); D-173 (unshipped parallel build; see D-175) consequence (8) |
| — | Decision label collision: G-413 took **D-176** this run. | — | Relabel to **D-173 (unshipped parallel build; see D-175)** everywhere in this item's Author-owned docs. | `prd.md` (§9 heading + all mentions), `lld-delta.md`, `scope.md`, `reconciliation-log.md`, `status.md` — `sed` sweep, 0 remaining `D-176` in those five files. `review-round-1.md` (the Planner's committed critique) still says D-176 in four places and is **deliberately left untouched** — it is another agent's historical record; this log is the cross-reference. |

**Cite corrections in the mini-round brief:** none needed — `:235/:330/:368/:431`, `:239`, `:527`, `:727`, `scope-phase2.md:122` all verified as stated.

**Requirements NOT affected (confirmed by re-reading each against the two-tier rule):** R-A.1/2/4/5/6 (knob, helper signature, callers, shape-agnostic, byte-identity at ≤ 0 — the tiers coincide there); R-A2 (collision rules operate on the returned key, tier-agnostic); R-C (marker set from `gap_sweetener`, which both tiers populate identically); R-D's guard order (unchanged); R-E; G-1, G-3–G-7; T-2 and T-3 expected values (stated explicitly as unchanged, with the reason); T-4a/T-4b/T-4a-ov/T-5/T-6/T-7/T-8/T-9 (none depends on which tier produced the result — T-4a's `gap_after ≤ eff` holds on the London fixture because X1 is tier 1); the TestFlight checklist; the analytics answer (`features_json.gap_sweetener.gap_after` now also distinguishes tiers after the fact); the docs table rows other than the added scope-phase2 row.

### Test-delta recount (final)

| Change vs §4 | Functions | Node ids | Sabotages |
|---|---|---|---|
| Round-2 total | 19 | 24 | 12 |
| + T-11 tier-2 fallback | +1 | +1 | +1 (S-11) |
| + T-12 tier-1 precedence | +1 | +1 | +1 (S-12) |
| **New-file total** | **21** | **26** | **14** |
| Existing-suite edits | `test_bakeoff_arm_a_golden.py` `_PINNED_KNOBS` +1 token · `test_gap_sweetener_arm_c.py:239` declared re-spec (frac pinned to 0 on the `10 ** 9` leg) · everything else unedited | | |

## 7. Build-time addendum 2 (orchestrator ruling, 2026-09-02)

| # | Red at the new default | Verdict | Where it landed |
|---|---|---|---|
| 1 | `test_avoid_positions.py:391` — avoided WR handed back as the equalizer | **real defect** (gap pass never re-checked `avoid_ok`); code fix on v3/v2 (+ consensus/gen_v2 as needed); test untouched | PRD §14 G-8, LLD §9, code-walk (f) |
| 2 | `test_engine_quality_golden.py:221` `_KILL_ALL` | declared re-spec — add the knob to the kill list | PRD §14 |
| 3–6 | `test_filler_threshold.py:235`, `test_trade_gen_v2.py:1062/1098`, `test_trade_optimizer.py:348` | declared re-specs — pin frac 0 in fixtures that test other mechanics | PRD §14 |
