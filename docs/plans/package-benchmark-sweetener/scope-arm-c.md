# Feature Scope — Gap auto-sweetener, bake-off arm C (`trade_gen_v2`)

**Date:** 2026-08-21
**Entry point:** direct ask — the named v1 follow-up in
[scope.md](scope.md) § "Which engines get the sweetener in v1", row `arm C
(trade_gen_v2)`, promoted to priority by the measured regression below.
**Builder:** isolated worktree agent, branch `feat/gap-sweetener-arm-c`.
**Base:** stacked on `fix/package-benchmark-sweetener` @ `480cce0` —
**not** `origin/main`. `close_value_gap` does not exist on `origin/main`
at all, so this work is unbuildable there; the operator chose the stacked
branch (2026-08-21) over waiting for the Monday window.
**Merge posture:** MERGE HELD behind its parent. This branch ships only
after `fix/package-benchmark-sweetener` lands.
**Operator sign-off on waivers:** not needed (no waivers — every section
answered).

> **STATUS 2026-08-21 — COMPLETE on the branch, MERGE HELD behind the parent.**
> Built, measured and test-green on `feat/gap-sweetener-arm-c`. Not pushed,
> not merged.
>
> | Item | State |
> |---|---|
> | Sweetener hooked into `_pair_survivors` + `_Candidate` rebuild | done |
> | Equalizer universe = semantic pools (operator ruling, §0b) | done |
> | `backend/tests/test_gap_sweetener_arm_c.py` (9 tests) | done — 8/9 verified RED on the parent, 1/9 RED on the contained variant |
> | Full backend suite | **3795 passed / 1 skipped** (baseline 3786 / 1) |
> | gen2 goldens | re-verified deliberately — **did NOT move; no re-capture, no pin.** Instrumented, see §5 |
> | `sweetener_gap_threshold` = 0 byte-identical no-op | asserted directly |
> | TEST_LEDGER | written (2026-08-21b) |
> | GOTCHAS | G-053 applied (harness seed determinism) |
> | DECISIONS / CHANGELOG | **drafted, NOT applied** — [decisions-draft-arm-c.md](decisions-draft-arm-c.md) |
>
> **Owed at ship:** merge the parent FIRST, then land the two drafted
> entries (D-145 / D-146, renumber if the parent's D-142…144 shifted).

## Why now — the parent branch made arm C measurably worse

The parent does two things. Arm C inherits the first and not the second:

| | Change | Arm C |
|---|---|---|
| 1 | `_package_value_market` depth-benchmarks a multi-asset side against the TRADE's best asset (`package_bench_trade_wide`) — this WIDENS absolute consensus gaps | **inherits it**, via `_consensus_packages` at card-build time ([trade_gen_v2.py:1002](../../../backend/trade_gen_v2.py)) — its displayed `give_value`/`receive_value` move |
| 2 | Gap auto-sweetener closes gaps above one late 1st (`sweetener_gap_threshold`) | **does not run it** |

Inheriting the widener without the closer is a one-directional regression.
Re-measured on this branch tip with the committed harness
([measure_gap_distribution.py](measure_gap_distribution.py)), reproducing
TEST_LEDGER 2026-08-21a exactly:

| Fixture | Arm C cards | over 1539 | share | sweetened |
|---|---|---|---|---|
| 12-team 1QB | 22 | 3 | 13.6% | 0 |
| 16-team SF | 19 | 2 | 10.5% | 0 |

Arm C's deck is card-for-card identical before and after the parent — the
parent moves its *prices*, not its *selections* — so the entire rise is
mispricing, not a different deck. Every other served arm reads 0.0–5.3%.
Arm C is the only served arm with a double-digit over-line share and zero
sweetened cards; across the served roster (B + C + D) it alone lifts the
combined over-the-line share 1.7% → 4.1%.

---

## 0. Why this is not a copy-paste of the three existing hook sites

Arm C's structure differs from the v2-divergence, consensus and v3 paths in
three ways that each change the integration:

1. **The gap is only visible at card-build time, but every card annotation
   is computed earlier.** `_pair_survivors` returns `_Candidate` objects;
   `_consensus_packages` is called once, later, in
   `generate_league_suggestions`. Sweetening at that call site — the
   textually obvious spot — would leave ten derived fields describing the
   *unsweetened* trade. See §0a.
2. **Arm C prunes its candidate pools** rather than gating per combo, the
   same failure mode the round-2 review caught on the consensus generator
   (`49c1d76`). See §0b.
3. **Arm C's fairness notion is not the helper's.** Its band gate is
   `min(gc,rc)/max(gc,rc) ≥ 1 − gen2_band` over `consolidated_value`, a
   different functional from `_consensus_packages`. See §0c.

### 0a. Stale-annotation surface — arm C's analogue of the v3 `fit_premium` bug

The v3 path had a stale `fit_premium` on sweetened cards. Arm C's exposure
is larger. Everything below is derived from `_Candidate` fields fixed
inside `_pair_survivors`, and every one of them is wrong if the ids change
afterwards:

| Consumer | Field(s) | Breakage if sweetened late |
|---|---|---|
| `_dedup_batch` | jaccard over `give_ids`/`recv_ids` | dedup runs on pre-sweetener ids; a sweetened card can collide with a kept one |
| `_meso_variants` | `base.give_ids`, `base.give_val_opp` | variants are matched against the unsweetened give side and its opp-board value |
| `_rationale` | `user_gain`, `opp_gain`, `centerpiece`, `give_ids`, `recv_ids` | positions, `fills_needs`, `gives_from_surplus` all recomputed off stale ids |
| `classify_package_shape` → `_timeline_fit` | **`len(ids) == 1` ⇒ `"consolidation"`** | a give-side sweetener flips a 1-asset give side to 2, silently changing the shape label and the `timeline_fit` claim in the counterparty rationale — **this is the direct `fit_premium` analogue** |
| `card.health` | `joint_gain`, `split_ratio`, `ir_margin_user/opp`, `band_position`, `fairness_ratio`, `symmetry` | all seven describe the unsweetened trade |
| `card.mismatch_score` | harmonic mean of the two gains | stale |
| `card.fairness_score` | `cand.fairness_ratio` | stale — and this one is user-visible |
| `card.composite_score`, Stage 6 exposure, Stage 7 tier | `cand.score` | a sweetened card keeps the unsweetened card's rank and tier |

**Decision:** hook inside `_pair_survivors`, immediately after gate c, and
**rebuild the whole `_Candidate` from the sweetened ids**. Every consumer
above then sees one consistent trade. This is the only placement that does
not require patching ten fields individually.

### 0b. Candidate pools — arm C prunes, so pools MUST be passed

Confirmed by reading `_pair_survivors`:

- **Give side:** `give_pool = sorted(user_assets, …)[:gen2_give_pool]` —
  truncated to a knob, and `user_assets` already requires the pid be on
  BOTH boards (`opp_elo_map` ∩ `user_known`) and not untouchable.
- **Receive side:** `extras_all` holds only *divergence-positive* opponent
  assets (`uval − oval > gen2_min_divergence`); per centerpiece it is
  further sliced `[:gen2_recv_extra_pool]`. The receive universe for a
  centerpiece `cp` is exactly `{cp} ∪ extras`.

An equalizer drawn from the raw roster would put into an arm-C card an
asset that is off one board, non-divergent, or outside the pool knobs —
i.e. an asset arm C's own enumerator would never have produced. That is
the `49c1d76` defect, one layer deeper. **Decision:** pass
`give_candidates=give_pool` and `recv_candidates=extras` (the
per-centerpiece list, `cp` already being in the trade).

### 0c. Fairness threshold — pass `0.0`, gate natively

`close_value_gap` applies `ratio ≥ fairness_threshold` over
`_consensus_packages`. Arm C has no such gate; its band gate is over
`consolidated_value`. Passing `1 − gen2_band` would impose on arm C a
constraint it never had, in a value space it does not use.

**Decision:** pass `fairness_threshold=0.0` — making the helper's foreign
ratio gate inert — and re-earn arm C's real band gate inside
`extra_ok_fn`. This is the literal reading of the parent's contract
("`extra_ok_fn` — the calling path's own gate stack"), not a weakening: the
absolute-gap test and the native band test both still bind.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** No new client events, no taxonomy
  change (`backend/analytics_taxonomy.py` untouched — nothing here is
  client-emitted). Arm C sets the existing `TradeCard.gap_sweetener` field
  (`backend/trade_service.py:3731`), which is already read generically by
  both consumers — the `deck_impressions.features_json` spine
  (`backend/server.py:4161`) and the card payload
  (`backend/server.py:11035`). **No `server.py` change is required**; arm C
  simply stops being null there. The existing sweetened-vs-unsweetened
  like/pass split therefore gains an arm-C population for free.
- One new *report* counter, `gap_sweetened`, on `GenerationReport`
  (logged JSON line + telemetry `as_dict`), mirroring the existing kill
  counters. Not an analytics event.

## 2. Schema & flag scope

- New/changed tables or columns: **none.**
- New/changed feature flags: **none.**
- New `model_config` keys: **none.** Arm C reuses the parent's
  `sweetener_gap_threshold` (default 1539.0), already registered under the
  five-registration rule. Deploy-free rollback is unchanged: set it to 0.
- Arm A pins it at 0.0 via `MODEL_A_PROFILE`, so arm A is unaffected by
  construction.

## 3. Evidence scope

Per D-056 — no Maestro, no simulator, no `screens/` captures.

- **Unit / structural:** `backend/tests/test_gap_sweetener_arm_c.py`, 9
  tests. **Verify-by-revert across three trees:** 8/9 red on the parent;
  exactly 1/9 red on the *contained-pools* variant
  (`test_arm_c_equalizer_reaches_past_the_budget_slice` — the test that
  pins the §0b ruling and nothing else); 9/9 green as shipped. The ninth,
  `test_arm_c_kill_value_is_a_byte_identical_no_op`, passes on the parent
  **by design** — it asserts the threshold-0 deck IS the pre-sweetener
  deck, so green there is the claim, not missing coverage.
- **Kill-value no-op:** asserted directly, and pinned to literals (the
  organic card at 10000.0 / 11600.0, band 0.862, gap 1600.0) so the
  disabled path cannot be silently rebaselined.
- **Goldens:** re-verified deliberately — **they did not move.** Full
  disposition in §5.
- **Measured delta:** committed harness, `PYTHONHASHSEED=0` on both sides
  (G-053). 12-team **3 → 1 over the line (13.6 % → 4.6 %), p90 1665 →
  951**; 16-team holds at 2, mean gap 551 → 488. Diff confined to arm C's
  own rows.
- **Code-walk proof:** §0 above is the file:line-cited trace.
- **Manual TestFlight checklist:** arm C serves quota-capped bake-off
  slots only; it rides the parent's existing checklist
  ([testflight-checklist.md](testflight-checklist.md)) rather than adding
  a second pass. Noted there, not silently skipped.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Action |
|---|---|
| `docs/api-reference.md` | **n/a because** no route added or changed; `gap_sweetener` is already documented from the parent and arm C emits the same shape. |
| `docs/config-reference.md` | **n/a because** no new or changed knob — `sweetener_gap_threshold` already has its row from the parent. |
| `living-memory/LLD.md` | **updated** — the arm-C hook point and the "rebuild the `_Candidate`" convention. |
| `docs/architecture.md` / `living-memory/HLD.md` | **n/a because** no architecture shift: one existing helper gains one more caller inside an existing module. |
| `docs/data-dictionary.md` | **n/a because** no schema change. |
| `docs/cross-client-invariants.md` | **n/a because** no shared enum, threshold or colour changes. |
| `living-memory/DECISIONS.md` | **updated** — the three §0 decisions + the golden disposition. |
| `living-memory/TEST_LEDGER.md` | **updated** — suite result + measured arm-C delta. |
| `living-memory/CHANGELOG.md` | **updated** at ship. |

## 5. Ship gate declaration

- CI green: `pytest backend/tests` (bar: 3786 passed / 1 skipped on the
  parent — re-verified as the baseline before any edit), `tsc --noEmit`,
  `testid-lint.sh`. No mobile or TS surface is touched by this change.
- `FTF_SKIP_SIM_GATE=1` is the standing posture under D-056.
- Evidence logged in `living-memory/TEST_LEDGER.md`.
- **Merge order is load-bearing:** parent first, then this.

### Golden disposition — measured, not assumed

The brief expected the gen2 goldens to move and asked for a re-capture vs
kill-value-pin ruling. **Neither is needed: they do not move.** Established
with a probe counting arm-C sweetener invocations per file, not by reading
a green bar:

| File | `generate_league_suggestions` calls | arm-C cards | sweetener fired |
|---|---|---|---|
| `test_bakeoff_arm_a_golden.py` | 0 | 0 | 0 |
| `test_engine_quality_golden.py` · `test_engine_quality.py` | 0 | 0 | 0 |
| `test_bakeoff_runner.py` · `test_bakeoff_composition.py` · `test_bakeoff_challenger.py` | 0 | 0 | 0 |
| `test_bakeoff_serving.py` | 10 | 0 (empty decks) | 0 |
| `test_trade_gen_v2.py` (arm C's own suite, not a golden) | 36 | 57 | **10 fired, 10 closed** |

Confirmed by forcing the gap line to **1.0**, which every nonzero gap
exceeds: still **0 invocations** in every golden file. The goldens are
stable because arm C's generator is not reached in them at all — not
because their gaps happen to sit under 1539. There is no baseline to
re-capture and nothing to pin.

Where the pass does work — `test_trade_gen_v2.py`, all 40 pre-existing
assertions green on every tree:

| Tree | cards | max gap | over 1539 |
|---|---|---|---|
| parent `480cce0` | 58 | 1861.5 | **2** |
| contained pools | 57 | 1234.2 | 0 |
| shipped (widened) | 57 | 1234.2 | 0 |

**58 → 57 is real and explained.** Arm C is the only path with
`_dedup_batch` downstream, and its bucket key is `(opponent, centerpiece,
"{len(give)}x{len(recv)}")`. Sweetening changes a card's SHAPE, so it can
land in an occupied bucket and evict the lower-ranked occupant. Diffed
card-for-card on deck #11: the parent held `u_rb1 → o_wr1` (gap 1671,
over) and `u_rb2+u_wr1 → o_wr1` (gap 1861, over); the shipped tree
sweetens the first into a 2×1 which collides with the second's bucket and
evicts it — 3 cards → 2, and **both over-the-line cards gone**. This
means D-143's "narrows gaps, never shrinks the deck" does **not** hold for
arm C; recorded in D-145 rather than left as an inherited assumption.
