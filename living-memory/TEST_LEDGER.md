# Test Ledger — Fantasy Trade Finder

> **Purpose:** authoritative record of what's been tested, what shipped, what was measured, and on what version of the stack. Prevents "works on my machine / claimed earlier without evidence" failure modes.
>
> Retention: entries dated within the last 2 months (2026-06-08 onward) plus standing sections live here; older run entries are archived in [`archive/TEST_LEDGER-pre-2026-06.md`](archive/TEST_LEDGER-pre-2026-06.md).
>
> **Read at:** before claiming a result, before proposing a new test that may duplicate a prior one, before shipping a feature.
> **Write at:** immediately after running a test, regardless of outcome.
>
> Companion files: [`MISTAKES.md`](MISTAKES.md), [`DECISIONS.md`](DECISIONS.md), [`Test_League_Trade_Matches.xlsx`](../Test_League_Trade_Matches.xlsx) (sample data), [`trade_output.json`](../trade_output.json).

---
## 2026-08-19b — Give-side headliner cap (D-082); the flood C4 could not see

**Branch:** `fix/deck-give-headliner-cap`, from `origin/main` `8b7689a`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/deck-give-headliner-cap/scope.md](../docs/plans/deck-give-headliner-cap/scope.md). Decision: [D-082](DECISIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3416 passed, 1 skipped (baseline at `8b7689a`) | **3427 passed, 1 skipped, 0 failed** (+11 new) |
| `tsc --noEmit` / `testid-lint` | n/a — **zero files under `mobile/` changed** | unaffected |
| Bake-off arm-A golden + knob-inventory guard | 10 passed | 10 passed; new knob pinned to 0 in `MODEL_A_PROFILE`, **no golden re-capture needed** (kill value returns the list unchanged) |
| `test_engine_quality_golden` byte-identity vs `origin/main` | 5 knobs killed | 6 knobs killed, still byte-identical |

**What was measured, on prod, read-only (`SET TRANSACTION READ ONLY`, SELECT only).** The defect,
on the operator's own deck `deck_job_id` 2740a7fc — 22 cards, **20 distinct `centerpiece_id`s**,
C4 killed 0, and three players supplied **17 of the 22 give sides** (6 Adams / 6 `1466` / 5
Mayfield). Then the fix, replayed over **66 `deck_candidate_sets` pools of ≥20 candidates**
(1,925 served cards) in `base_score` order:

| Cap | Cards lost | Median deck size | Per-deck max repeat (median) | Decks under `_DECK_MIN_CARDS` (5) |
|---|---|---|---|---|
| 2 | 458 (23.8 %) | 29 → 24 | 6 → 2 | 0 |
| **3 (shipped)** | **194 (10.1 %)** | **29 → 26.5** | **6 → 3** | **0** |
| 4 | 62 (3.2 %) | 29 → 28 | 6 → 4 | 0 |

At the shipped default: 19 of 66 decks unchanged, worst single deck 36 → 24, 3 decks under 20
cards, per-deck worst repeat `{3:1,4:13,5:16,6:14,7:7,8:1,9:4,10:2,11:3,12:2,13:3}` → `{3:66}`.

**Evidence per D-056 (no simulator, no Maestro):** 11 new pytest cases in
`backend/tests/test_engine_quality.py` + a file:line code-walk proof in the scope block §3.1 +
a manual TestFlight checklist for the operator (§3.2), since "how the deck reads" is the one
claim no unit test can settle.

**Proven-to-fail, both applied → observed RED → reverted.** (a) default `3.0 → 0.0`: 3 behaviour
tests fail. (b) delete the `cap_give_headliners` call from `_dedup_and_sort`: 4 fail — the three
above plus `test_both_generation_paths_apply_the_give_cap`, which is the guard that arm C
(`bakeoff_runner.gen_v2_cards`) and the `trade_gen.v2` serving branch keep their own calls; both
bypass `_dedup_and_sort` entirely, so without them the bake-off would compare arms under
different deck-assembly rules.

**One pre-existing test-fixture interaction, resolved deliberately rather than by loosening an
assertion.** Every card in the C4 flood fixture gives `hub`, so C4b bound first and 4 C4 cases
went red. `_flood_deck` and `_ORTHOGONAL_GATES_OPEN` now pin `deck_give_headliner_cap = 0`, the
same isolation technique those fixtures already used for `deck_headliner_cap` — C4b has its own
fixture (`_c4b_*`) built from the real defect shape (one player for one pick, six distinct picks).

---

## 2026-08-19 — Round-2 pick recalibration (D-084); the `second` tier floor moves with it

**Branch:** `feat/round2-pick-recalibration`, from `origin/main` `93ac695`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/round2-pick-recalibration/scope.md](../docs/plans/round2-pick-recalibration/scope.md). Memo: [docs/reviews/2026-08-19-ktc-pick-value-comparison.md](../docs/reviews/2026-08-19-ktc-pick-value-comparison.md) (carried on this branch; not on main). Decision: [D-084](DECISIONS.md). Open question: [Q-019](OPEN_QUESTIONS.md). Gotcha: [G-051](GOTCHAS.md).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` | **3429 passed, 1 skipped, 0 failed** — byte-identical to the `93ac695` baseline (3429/1) |
| `tsc --noEmit` (TypeScript 5.9.3, worktree-local `npm ci`) | clean, exit 0 |
| `mobile/scripts/testid-lint.sh` | `testid-lint OK` |
| `mobile/tests/check-*.js` — `calc-pick-tiers`, `anchor-labels`, `picks-subset-invariance`, `contrast` | 4/4 pass |
| `test_tier_occupancy.py` | **47 passed** — `second` peaks at 32 against its ceiling of 35, exactly as the memo predicted |
| Bake-off knob-inventory guard | untouched — **no `trade_service._DEFAULT_CFG` key added**; `trade_service.py` is not in the diff |

**The blast radius was predicted and then measured to match, exactly.** Applying the seed + band edit before retargeting anything produced **11 failed / 3418 passed** — the same eleven the memo named on a throwaway copy, no more and no fewer. Nothing outside the predicted set moved. Retargeted: `test_pick_anchor` ×2 (1460 → 1400), `test_pin_tier_bounded` ×4 (one constant, `SECOND_LO` 1400 → 1370), `test_pick_pricing_m6b` ×3, `test_league_picks_tier` ×1, `test_power_rankings` ×1. Two extras retargeted deliberately although green: `test_tier_occupancy::test_anchor_rungs_land_in_matching_tiers` asserted `1460.0 → "second"`, a seed that no longer exists, and the `pin_tier_bounded_golden.json` fixture.

**The honest scorecard moved and was rewritten, not silenced.** `test_pick_pricing_m6b::test_the_measured_reshaping_direction_is_deflation_not_inflation` measures how far our ladder sits above DynastyProcess's real market slot prices. `delta(2026, 2)` was `< -0.40`; it is now **−0.284**, and `delta(2027, 2)` **−0.244**. Both are now pinned with `pytest.approx` rather than a loose bound so drift in *either* direction must be acknowledged, with a docstring recording that the remaining ~28 % is intentional (Option B was measured and rejected). It also records that **the ranking flipped**: 2nds are no longer the biggest outlier — a 2026 3rd now deflates hardest (−0.355 vs −0.284), which is the Q-019 residue.

**The golden fixture was re-captured against pristine code, not re-derived.** `pin_tier_bounded_golden.json` pins `edge_lo` to the `second` floor, so the floor move changed its *input*. Its docstring forbids regenerating from new code, so a separate **pristine `origin/main` worktree at 93ac695** was created and the harness validated first by re-capturing at 1400 and confirming it reproduced the checked-in golden **byte-for-byte**; only then was it re-run at 1370. Seven numbers moved, all forced by the one changed input (`elo.edge_lo`, plus ripples in `free` — his opponent in six comparisons — and `quiet`).

**Production validation, read-only** (`SET TRANSACTION READ ONLY`, SELECT only, credentials read from the gitignored `secrets.local.env`, never printed). Question: *is the overpriced 2nd costing accepted trades?* **Answer: no, not measurably.** Cards containing a 2nd are liked at **34.8 % (n=46)** vs **35.2 % (n=565)** for cards with no pick at all — Fisher **p = 1.00**; 2nds appear on only **13.7 %** of 2,184 served cards. A 3-day impression-level sample points the *opposite* way (17.6 %, n=17, p=0.26); two samples disagreeing on sign is the finding. Zero of 23 free-text passes mention a 2nd. The real signal is **1sts by side** — 1st-on-give 15.6 % liked vs 1st-on-receive 47.1 % (n=128). **D-084 is justified on the rank measurement, not on acceptance data, and no lift should be expected.**

Two incidental prod findings, out of scope and not fixed here: **`backend/database.py` on `main` is stale against prod** (26 vs 13 `deck_impressions` columns; `trade_pass_reasons` missing entirely), and **`model_arm` is 97.5 % NULL with zero `gen_v2` rows** — the bake-off is not producing labelled data.

**Not yet run: the manual TestFlight checklist** (scope §8, 10 steps). It is the only runtime evidence this change gets under D-056, and step 9 deliberately points the operator at the one odd consequence — a current-year 3rd now badges "2nd".

## 2026-08-19 — Per-round draft-pick year decay (D-079); firsts stop decaying

**Branch:** `feat/pick-year-decay`, from `origin/main` `02e27dd`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/pick-year-decay/scope.md](../docs/plans/pick-year-decay/scope.md). Review: [docs/reviews/2026-08-19-pick-year-valuation.md](../docs/reviews/2026-08-19-pick-year-valuation.md). Decision: [D-079](DECISIONS.md). Open question: [Q-018](OPEN_QUESTIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3404 passed, 1 skipped (baseline at `02e27dd`) | **3416 passed, 1 skipped, 0 failed** (+12 new) |
| `tsc --noEmit` / `testid-lint` | n/a — **zero files under `mobile/` changed** | unaffected |
| Bake-off arm-A golden + knob-inventory guard | 10 passed | 10 passed, after recording the exclusion decision |

Mid-run the change produced **8 failures, every one of them the intended behaviour change** — seven
behavioural tests asserting the old round-1 discount, plus the bake-off knob-inventory guard demanding
a written decision for the four new `_DEFAULT_CFG` keys. None were suppressed. Each of the seven was
**retargeted to assert the new intent plus a still-decaying round**, so "someone flattened every round"
now fails loudly rather than passing silently: `test_owned_picks.py`, `test_dynasty_value_pick_scale.py`,
`test_league_picks_tier.py`, `test_pick_value_scaling.py`, `test_pick_pricing_m6b.py`,
`test_pick_rung_year_labels.py`, `test_pick_values_in_suggestions.py`.

**One of those retargets was a near-miss worth recording.** `test_pick_values_in_suggestions.py` seeded
its player fixture at a hard-coded Elo `1552.0`, chosen because it matched the *old* 2029 1st value
(~1300). After the repricing that literal would have quietly turned "a player against a 1st" into
"a mid player against a 1st" and the test would still have passed — measuring nothing. The seed is now
**derived** from `pick_pool_value(1, 3)`, so the fixture moves with the ladder.

**New coverage — 12 tests in `backend/tests/test_pick_year_decay.py`:** default rates; deep-round
clamping onto `_r4`; live `model_config` reads; the `[0,1]` clamp (a rate > 1 would invert the
arbitrage); **the deploy-free revert** — all four keys at 0.85 reproducing the pre-D-079 ladder on both
value scales, including the literal 1300.1 that was the bug; a 2029 1st equalling a 2027 1st; later
rounds still decaying with round ordering intact at every horizon; **zero value gradient between any
two 1sts** (the anti-swap invariant); `compute_pick_value` on the same clock; round-aware rung
relabelling; and a no-config fallback so a DB outage cannot take pricing down.

**Code-walk proof (replaces a simulator capture, per D-056).** The evidence that *served cards* change
is `trade_service.overpay_ok` (`backend/trade_service.py:1502–1521`) flipping verdict on the operator's
actual card, impression `c67c2fd1e97cb6bf`: Adams 1138.8 vs the 2029 1st at 1300.1 → gap 161.3, ratio
0.124, under both floors (500 / 0.25) → **served**, which is what prod did. At 2117.0 → gap 978.2,
ratio 0.462, over both floors → **killed**. Asserted as the gate's boolean, not as a number.

**Prod corpus measurement (read-only, `SET TRANSACTION READ ONLY`, SELECT only).** 2048
`deck_impressions` rows with `assets_json`: **58.5 %** contain a pick; firsts are **84 %** of all pick
mentions; **99 cards (4.8 %)** moved a 1st one way and a *different-year* 1st the other — the arbitrage,
counted. Re-run that query after merge; the expected post-fix count is **0**, structurally.

**NOT run:** the manual TestFlight checklist (§3 of the scope block) — it needs the operator on a build.
Nothing here is runtime evidence from a device.

## 2026-08-19 — Decline reasons: player preference under "Neither" (branch only, NOT merged)

**Branch:** `feat/decline-reason-player-pref`, from `origin/main` `02e27dd`. **Not shipped** — not pushed, not merged. Flag `feedback.decline_reasons` unchanged (already on for all users).
Scope block: [docs/plans/decline-reason-capture/scope-player-preference.md](../docs/plans/decline-reason-capture/scope-player-preference.md). Decision: [D-080](DECISIONS.md#d-080). Contract: [SPEC §2a](../docs/plans/decline-reason-capture/SPEC.md).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` (before) | **3404 passed, 1 skipped** — baseline at `02e27dd` |
| `pytest backend/tests -q` (after) | **3417 passed, 1 skipped, 0 failed** — +13 tests, zero regressions |
| `npx tsc --noEmit` (mobile) | **clean**, exit 0 |
| `mobile/tests/check-*.js` | **56 suites, 0 failing** (the CI `mobile-typecheck` job globs all of them) |
| `mobile/scripts/testid-lint.sh` | **testid-lint OK** |
| Maestro / simulator | n/a — retired by D-056. The two `mobile/.maestro/flows/decline-reasons-*.yaml` are historical artifacts and were **not** run or extended |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| Manual TestFlight checklist | **written, NOT run** — 8 steps in scope block §3b, awaiting the operator |

**New tests: 13.** Nine `test_player_preference_*` in `backend/tests/test_decline_reasons.py` (both codes parent to `other` and not to `value`; a foreign layer-1 is a `detail_reason_mismatch` 400 that writes nothing; a layer-2-first write derives `reason='other'` from the prefix; the two directions plus the residual free text land as three distinguishable stored answers), plus four from the `_ELO_MATRIX` parametrisation growing 8 codes → 10 across both knob positions. The two existing enumerations — `test_every_specced_code_is_accepted` and `test_pass_reason_writes_elo_rule_is_pure` — were extended rather than left to pass vacuously.

**Structural suite extended, not just kept green.** `mobile/tests/check-decline-reasons.js` gains a §6 that reads the `TILES` table through the **TypeScript AST** rather than by regex, so a re-order or re-wrap of the source cannot fake a pass. It fails on either of the two silent reversions: reverting "Neither" to free-text-only (the `freeOnly` shortcut is asserted gone), or collapsing the two player codes into one (they are asserted as a pair, each committing on tap rather than opening a text box, each carrying `trades.pass-reason.l2.<code>`, with `other_text` still free and still last).

**A check that had never once executed now does.** The suite's "transcribed codes still match SPEC §2" cross-check was guarded on `fs.existsSync(SPEC.md)` — and **SPEC.md was untracked**, present only in the main checkout's working tree and committed to no branch in the repo. The guard had always taken its SKIP branch, so the transcription had never actually been compared to the spec. SPEC.md is committed on this branch and the cross-check runs and passes. Committing it also surfaced a real spec/implementation divergence: SPEC §2 wrote the free-text step as `value_other` → a second `value_other_text` code, which does not exist and which the route 400s as `invalid_detail`. Corrected in the same amendment.

**What was NOT verified here:** runtime behaviour on a device. Under D-056 that is the manual TestFlight checklist and nothing else — it is written but unrun, so no runtime claim is made about this change. The code-walk proof in scope block §3a is a file:line trace, not evidence of execution.

## 2026-08-18f — Trade-suggestion presentation v2 (additive Acquire surface, flag OFF)

**Branch:** `feat/trade-presentation-v2`, from `origin/main` `a7f8783`. **Not shipped** — not pushed, not merged. Flag `trades.presentation_v2` ships **OFF**.
Scope block: [docs/plans/trade-presentation-v2/scope.md](../docs/plans/trade-presentation-v2/scope.md). Decision: [D-081](DECISIONS.md#d-079--the-confidence-band-is-derived-from-provenance-because-no-confidence-field-exists).

| Gate | Result |
|---|---|
| `npx tsc --noEmit` (mobile) | **clean** — baseline at `a7f8783` was also clean, so the delta is zero new errors |
| `mobile/tests/check-*.js` (all 57) | **all pass**, including the new `check-presentation-v2.js` (**87 assertions**) |
| `npm run test:presentation-v2` | **87 PASS, 0 FAIL** |
| `bash mobile/scripts/testid-lint.sh` | **OK** (8 template-literal globs added to `testid-lint-allow.txt`, each with its constructing file:line) |
| `pytest backend/tests` | **NOT RUN** — no Python environment in this worktree. Backend delta is one `FLAG_KEYS` string + one `config/features.json` entry; `test_entitlements.test_features_json_keys_known` is the covering test and **must be green on the pushed sha before merge** |
| Maestro / simulator | **Not run.** Three flows AUTHORED (`presentation-v2-hero`, `-browse-dismiss`, `-honest-empty`) because the build brief required it — which directly contradicts D-056's "do not author, extend, or execute". Each carries a banner recording the conflict. Execution, and whether authoring was correct at all, is an **operator decision** (scope.md §6 item 1) |
| Sim gate | `FTF_SKIP_SIM_GATE=1` — standing posture under D-056 |
| Manual TestFlight | **Not run** — 12-step checklist written in scope.md §3; operator action |

**What the structural guard actually proves** (not a grep-count — these are the four things that fail silently):
1. **Flag-off byte-identity.** Both `onTodaysTrade` pass sites are ternaries on the flag passing `undefined`; both components build their control list *from the handler's presence*; `'today'` is asserted **not** to be in the static `CHIPS` array; the routes are asserted registered *and* asserted **not** flag-wrapped. A no-op-handler "simplification" — which still renders the chip — fails here.
2. **Instrumentation parity.** Shared `swipeTrade` / `postDeclineReason` imports, `SwipeSignal` imported as a type, no hand-rolled `api.post`/`api.get` in the signals hook, the three event names cross-checked against `TradesScreen`'s own source, the four signal fields, the two-part `signal_v2 && impression_id` gate, boolean-only free text, explicit `platform`, and `VIEWED_MIN_MS`/`DWELL_CAP_MS` matched against `TradesScreen`'s literals.
3. **The server cache-slot agreement.** Shared fairness helpers only, no raw threshold constants, never `force: true` — so the new surface cannot kick a second generation or serve a different card set to the same user.
4. **The design laws, executed.** The pure module is transpiled and RUN: band derivation across all four provenance combinations plus the `likesYou` promotion, "no band label contains a digit", the fairness band exposing no winner/margin, `userSideBullets` naming a concrete asset and never leaking `opponent_surplus`, `counterpartyStatement` returning a number-free single string, `partitionDeck` returning **no hero** when nothing is endorsable, browse uncapped, dismissed cards excluded from hero but retained in browse, and the empty-state copy omitting an unknown roster count rather than rendering zero. Plus source-level bans: no `TradeValueBar`, no `Meter`/`fairnessColor`, no `partner_fit`, no `match_score`, no `showPercent`, no `.slice()` in browse, no `numberOfLines` anywhere on the surface.

**Not proven by anything here, and stated so it is not mistaken for covered:** that the surface renders correctly on a device. Nothing in this branch has run on a simulator or a phone. The 12-step TestFlight checklist is the only runtime evidence available under D-056 and has not been executed.

---
## 2026-08-18e — Bake-off deck composition (three groups of ten; arm A out of the roster)

**Branch:** `feat/bakeoff-composition`, from `origin/main` `217a8e1`. **Not shipped** — not pushed, not merged. Flag `trade.bakeoff` stays **OFF**.
Scope block: [docs/plans/three-model-bakeoff/scope-composition.md](../docs/plans/three-model-bakeoff/scope-composition.md). Decision: [D-078](DECISIONS.md#d-078--a-bake-off-deck-is-composed-of-groups-and-an-unfilled-quota-is-the-finding).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` (before) | **3363 passed, 1 skipped, 0 failed** — baseline at `217a8e1` |
| `pytest backend/tests -q` (after) | **3404 passed, 1 skipped, 0 failed** — +41 tests, zero regressions |
| `npx tsc --noEmit` (mobile) | n/a — zero mobile files changed |
| `check-*.js` / `testid-lint.sh` | n/a — zero mobile files changed |
| Maestro / simulator | n/a — retired by D-056; backend-only, nothing user-visible while the flag is off |
| Sim gate | Tier 4 (backend-only); `FTF_SKIP_SIM_GATE=1` is the standing posture under D-056 |

**New tests: 41.** `backend/tests/test_bakeoff_composition.py` (31 unit) + 10 integration added to `backend/tests/test_bakeoff_serving.py` (real `server._run_trade_job`).

**Flag-off golden extended, not weakened.** `backend/tests/fixtures/bakeoff/flag_off_golden.json` is byte-for-byte unchanged and the flag-off test still asserts byte-identity against it. The four new columns (`group_key`, `group_rank`, `lane_slot`, `trade_intent`) joined Phase 3's admitted-additive list and are asserted **NULL on every row**, exactly as Phase 3's three were.

**Phase 2 verified still intact.** The arm-A golden, the R4-bypass tests and the 189-key knob-inventory guard all still pass; the four new knobs were added to `_PINNED_KNOBS`. `test_bakeoff_composition.py::test_arm_a_leaves_serving_but_phase_2_stays_intact` asserts the profile, its entry point and its knob set directly, so "arm A left by configuration, not deletion" is a tested property rather than a claim.

**Measured — three-group interleave, 500 decks (30 cards each):**

| | group 1 `current_divergence` | group 2 `current_consensus` | group 3 `gen_v2` |
|---|---|---|---|
| mean served position (of 30) | 14.48 | 14.55 | 14.48 |
| cards per deck | 10.0 | 10.0 | 10.0 |
| decks led (of 500) | 164 | 160 | 176 |

Per-lane mean served position: value 14.52, outlook (`window`) 14.48. Both distributions are flat, which is the whole point — a per-**arm** rotation instead puts arm `gen_v2` at mean position **24.5** (measured on identical inputs by `test_grouping_by_arm_would_bury_arm_c_and_the_group_draft_does_not`).

**Measured — outlook-slot under-fill** (slots left empty of 5, at the live lane ratios: divergence 80.5% value / 19.5% window, consensus 73.2% / 26.8% / 6.1% unlabelled), sweeping per-deck supply:

| surviving cards in the group's pool | divergence group | consensus group |
|---|---|---|
| 10 | 3.0 | 3.0 |
| 15 | 2.0 | 1.0 |
| 20 | 1.0 | **0.0** |
| 25 | **0.0** | 0.0 |
| 30 / 40 / 60 | 0.0 | 0.0 |

A divergence group needs ~25 surviving cards before it can expect five outlook cards; a consensus group clears at ~20. That gap is why groups 1 and 3 are the ones expected to serve short, and why the default fill policy records the hole instead of topping it up from the value lane. Pinned by `test_measured_under_fill_across_realistic_divergence_supply`.

**Two plumbing gaps closed** so the comparison is of generators, not of which post-generation steps each arm received: arm C now gets the same `_filter_by_trade_intent` and the same `classify_lane` the engine arms already get. Without the lane label, group 3's outlook quota would have under-filled **100% of the time** and read as "arm C cannot produce outlook ideas".

**Not measured here, needs Phase 4:** real per-deck supply. Every under-fill number above is from the live lane *ratios* applied to swept supply sizes, because the 3,163-card total does not say how many cards one deck's arm produces. Phase 4 dark validation writes `groups_json` on every run, so the true rate is one query away once it runs.

---
## 2026-08-18d — Three-model bake-off Phase 3 (the runner)

**Branch:** `feat/bakeoff-runner`, rebased onto `origin/main` `9d24da3` (which carries bake-off Phase 2 and tier-bounded pins). **Not shipped** — not pushed, not merged. Flag `trade.bakeoff` ships **OFF**.
Scope block: [docs/plans/three-model-bakeoff/scope-phase3.md](../docs/plans/three-model-bakeoff/scope-phase3.md).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` | **3363 passed, 1 skipped, 0 failed** — full suite re-run after the final rebase onto `9d24da3` AND after the fairness-threshold capture |
| `npx tsc --noEmit` (mobile) | n/a — zero mobile files changed |
| `check-*.js` / `testid-lint.sh` | n/a — zero mobile files changed |
| Maestro / simulator | n/a — retired by D-056; backend-only change with no user-visible surface |

**New tests: 49.** `backend/tests/test_bakeoff_runner.py` (35 unit) + `backend/tests/test_bakeoff_serving.py` (14 integration through the real `server._run_trade_job`).

**Third contamination channel closed (coordinator addition, same session).**
[The trade-logic archaeology review](../docs/reviews/2026-08-18-trade-logic-archaeology.md)
found `fairness_threshold` persisted **nowhere** — not a column, not one of the 28
`features_json` keys — while arriving per-request from the client (0.75 toggle on / 0.50 off).
A per-arm comparison spanning sessions with different client settings would have compared arms
AND thresholds at once. Now `deck_impressions.fairness_threshold` (a column, not a JSON key: the
analysis groups by it), written **per card** because the effective bar is card-dependent, and
per arm in `bakeoff_runs.arms_json`. `bakeoff_runs.config_json` snapshots the effective config
each arm ran under, since `model_config` has no `updated_at`.

The composition is proven, not assumed: `test_served_cards_record_the_threshold_they_were_generated_under`
runs the job at **0.75** and asserts the divergence card records **0.55**
(`min(requested, fairness_floor_divergence)`), the consensus card **0.75**, and the arm-C card
**NULL** — i.e. recording the requested value would have misdescribed two of the three.
`test_arm_a_config_snapshot_is_taken_inside_the_profile` pins that arm A's snapshot is taken
INSIDE `model_a()` (outside it the overlay is gone and arm A would be recorded as running on live
defaults). `test_threshold_clean_query_answers_itself_from_the_table` executes the documented
"was this comparison threshold-clean?" `GROUP BY`, so the query cannot rot into documentation-only.

**Flag-off byte-identity is proven by a CAPTURED golden, not an assertion.**
`backend/tests/support/bakeoff_harness.py` was copied into a **separate worktree detached at
pre-bake-off `origin/main` (9a20ca8)**, run there, and its output committed as
`backend/tests/fixtures/bakeoff/flag_off_golden.json`. With the flag off this branch reproduces it
byte for byte — identical served card payloads and identical `deck_impressions` rows. The only
admitted difference is the three additive columns (`model_arm`, `arm_rank`,
`fairness_threshold`), asserted NULL on every row. The harness deliberately imports nothing from `bakeoff_runner`, which is what let it run on
the pre-change SHA.

**§3.4 Channel 2 (the silent-failure risk) is tested, not asserted.**
`test_post_generation_rerankers_cannot_touch_the_merged_deck` turns every reordering layer ON and
replaces each with a spy that REVERSES the deck (F2 `_order_deck`, F3 fatigue multipliers, F5 taste,
F6 value model, F7 wildcard, F9 shaping), then asserts the served arm sequence is still the
interleaver's. Its mirror `test_rerankers_do_run_when_the_bakeoff_is_off` proves the same spies fire
with the flag off, so the bypass is a bake-off property and not a broken harness. F3 decline
suppression is asserted STILL LIVE (it only removes cards).

**§3.4 Channel 1** is guarded structurally: `test_every_swipe_k_multiplier_runs_through_the_elo_freeze`
scans `backend/server.py` for every `fit_congruence_mult` K site and fails if one is missing
`_bakeoff.elo_freeze_mult` — a new swipe path that forgot the freeze would contaminate the shared
board with no visible symptom.

**Real bug found and fixed while testing (would have been silent in prod):** `save_deck_impressions`
inserts the batch with SQLAlchemy `executemany`, which compiles the statement from the **first row's
keys**. Stamping `model_arm` only on attributed cards meant a deck led by an unattributed likes-you
injection dropped attribution for the **entire deck**. Both columns (and the arm-stamped
`policy_version`) are now written on every row, with a regression assertion in
`test_likes_you_injection_does_not_reorder_the_interleave`.

**Generation cost measured** on a synthetic 12-team / 168-asset league with 11 boarded opponents
(scratch harness, 5 repeats, medians):

| | ms | cards |
|---|---|---|
| single generation (today) | 3127 | 19 |
| bake-off fan-out (3 arms) | **7359 (2.35×)** | 140-card interleaved deck |
| — arm `baseline` | 4187 | 30 |
| — arm `current` | 2733 | 19 |
| — arm `gen_v2` | 424 | 105 |

Arm A is the slowest because its profile zeroes every gate, so more candidates survive. Arm C
over-produced **on this fixture only** — the synthetic boards carry gaussian noise, so divergence is
everywhere; PLAN.md §3.2 still expects it to under-produce in production, which is exactly what the
empty-arm rate is there to measure. Agreement on the fixture: `baseline+current` 14.

**Budget finding for the operator:** the per-opponent enumeration deadline is 1 s, so an 11-opponent
league's worst case is ~11 s per arm and ~33–45 s for the fan-out, against
`server._JOB_HARD_TIMEOUT = 60` s. Inside the limit but thin, with no margin for a slow Postgres.
Phase 4 must watch p95 job duration directly; `_JOB_HARD_TIMEOUT` may need raising before Phase 5.
`bakeoff_deck_limit` defaults to uncapped, so an interleaved deck is ~3× today's — set it before
Phase 5 unless a very long deck is wanted.

**Arm-A seam: real, not stubbed.** Phase 3 was built against a temporary local stub of
`backend/bakeoff_profiles.py` (Phase 2 had not yet landed), then **rebased onto `origin/main`, which carries Phase 2's real module** (`3760f12`). The stub was dropped in the rebase and
the runner now calls Phase 2's `model_a()` — the only supported entry point, because it applies the
pinned `MODEL_A_PROFILE` and the R4 bypass together. Arm A is therefore golden-tested against
reference SHA `92c31d5` by Phase 2's own tests, and the R4 bypass is really enforced
(`trade_service.r4_bypassed()`). Full suite re-run after the rebase.

---
## 2026-08-18c — G-049 caller-side finish: route-level proof + the ungated-signal decision

**Branch:** `feat/sweep-followups-2026-08-18` (continues the 2026-08-18b entry below). **Not shipped.**

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3216 passed, 1 skipped | **3219 passed, 1 skipped** |

Both `save_trade_swipes` gates (`swipe_trade`, `_apply_reasoned_pass`) were already in place from
2026-08-18b; this pass added the **runtime** evidence they lacked and settled the one open design
question.

**New coverage — 3 route-level tests** in `test_trade_decision_idempotency.py`. They POST
`/api/trades/swipe` twice through the Flask test client against an in-memory DB with the **real**
`save_trade_swipes` (only `record_event` / `create_notification` / `check_for_match` stubbed), so the
count is of rows the route actually wrote:
1. `test_re_posted_swipe_writes_exactly_one_set_of_swipe_decisions` — one `swipe_decisions` row, one
   `trade_decisions` row, and a `replay_from_db` + `_compute_elo` check that a restart sees exactly
   one application of `trade_k_pass`.
2. `test_route_replay_leaves_the_in_session_signal_doubled` — pins the accepted residual.
3. `test_route_replayed_like_still_runs_match_detection` — `check_for_match` called twice.

**Sabotage:** deleting the `if wrote_decision:` gate in `swipe_trade` turns tests 1 and 3 RED
(`assert 2 == 1` on real rows), alongside the existing source pin. The `inspect.getsource` pins alone
could not have caught a gate that was present but ineffective.

**Design question closed:** `RankingService.record_trade_signal` stays **before** the DB write and
**ungated** (D-073). `_trade_swipes` is derived state that `replay_from_db` rebuilds from
`swipe_decisions` at every `session_init`, and the persist block around it is best-effort by design —
gating it would trade a bounded, self-healing 2x overcount for an unbounded 0x undercount whenever
the DB is unreachable. `backend/database.py`'s docstring and `docs/data-dictionary.md` both said
callers "must skip both", which the shipped code never did; corrected to match.

**Not run:** `tsc --noEmit` / `check-*.js` / testid-lint — this pass touched backend and docs only.
**Count note:** the 2026-08-18b entry recorded 3191; the branch was rebased onto a newer `main`
mid-session (engine-quality wave + navdoc refresh), which brings `test_engine_quality.py` and
`test_engine_quality_golden.py` — hence 3216 as the real pre-change baseline. Nothing was lost.

## 2026-08-18c — Bake-off Phase 2: arm A pinned + golden (branch only, NOT merged)

Branch `feat/bakeoff-arm-a`, off `origin/main` @ `9a20ca8`. Scope block:
[`docs/plans/three-model-bakeoff/scope-phase2.md`](../docs/plans/three-model-bakeoff/scope-phase2.md).
Backend-only: `backend/bakeoff_profiles.py` (`MODEL_A_PROFILE`, `model_a()`), a thread-local
R4 bypass in `trade_service`, and `backend/tests/test_bakeoff_arm_a_golden.py`.
**Not pushed, not merged** — build-agent output; Phase 3 (`feat/bakeoff-runner`) consumes it.

| Gate | Baseline (`origin/main`) | After |
|---|---|---|
| `pytest backend/tests -q` | 3267 passed, 1 skipped (3268 collected with the new file ignored) | **3277 passed, 1 skipped, 0 failed** (250s) |
| `npx tsc --noEmit` (mobile) | n/a | **not run — zero files under `mobile/`** |
| `testid-lint.sh` | n/a | **not run — no mobile files touched** |
| Simulator gate | — | **D-056 standing posture, `FTF_SKIP_SIM_GATE=1`**; backend-only, no runtime surface |

**What the golden actually proves.** Reference SHA **`92c31d5`** (`20b40db^` on `--first-parent
main` — the last commit before the G6 wave). Captured by adding a detached worktree at that SHA,
copying the test file in, and running its `__main__` capture mode. Arm A (`MODEL_A_PROFILE` + the
R4 bypass) reproduces **30 deck cards and the asset-ideas groups byte-identically**; arm B (live
defaults) on the same fixture returns **8 cards** and different ideas.

**Board-drift immunity.** The fixture pins every generation input as a literal (player table,
`seed_elo`, `user_elo`, each opponent's `elo_ratings`, confidence counts, roster, outlook,
fairness threshold) and calls `TradeService.generate_trades` directly — no DB read, no
`ranking_service` call, no `comparison_counts`, no pin resolution. So Phase 0's pin fix,
`feat/tier-bounded-pins` and premium import cannot move it: the comparison isolates generation
logic only.

**Non-vacuity, per rule** (a golden that stopped disabling anything would otherwise still pass):
arm B records kills for **R1 2822 / R2 251 / R3 513 / R5 405** on this fixture; C1, C4 and C5 each
move the deck alone; C2 moves the asset-ideas alone. **C3 (`pick_pair_strip_frac`) is the one
profile entry the deck fixture cannot reach** — no matched-pick-pair shape survives the other gates
on a realistic league (R3 kills the candidates first) — so it is asserted at its own gate
(`pick_swap_ok`), with byte-identity already pinned by `test_engine_quality_golden.py`. Recorded as
a known gap in the scope block rather than papered over.

**Both drift alarms negative-controlled** (verified by breaking them on purpose, not by inspection):
injecting a fake `_DEFAULT_CFG` key fails the inventory test naming `shiny_new_knob`; removing
`deck_headliner_cap` from the profile produces a drift report listing the 22 dropped cards.

**Not covered:** no runtime/TestFlight evidence exists or is claimed — nothing reaches a client.
The new code is unreachable in production until Phase 3 wires a caller behind `trade.bakeoff`.

**Second rebase, same session** (onto `origin/main` `9a20ca8`, picking up the bake-off Phase 0 batch
`e8ae476`): clean, no conflicts, despite that batch touching `backend/database.py`,
`backend/server.py` and `docs/data-dictionary.md` — the same three files this work edits. Re-verified
after: both `save_trade_swipes` gates present (`server.py:11010`, `:11347`), guard intact, and
**pytest 3270 passed / 1 skipped** (the +51 over 3219 is Phase 0's own
`test_force_supersedes_running_job.py` and `test_override_pin_unpin.py`). The three route-level tests
count real rows after two POSTs, so their passing is itself the evidence the guard still works — no
second sabotage run needed.

---
## 2026-08-18d — Tier-bounded voting (a pin confines a player to a tier)

**Branch:** `feat/tier-bounded-pins`, rebased onto `origin/main` `74620a7`. **Not shipped, not pushed.**
**Scope block:** [`docs/plans/three-model-bakeoff/scope-tier-bounded.md`](../docs/plans/three-model-bakeoff/scope-tier-bounded.md) · **Decision:** [D-076](DECISIONS.md).

| Gate | Baseline (`origin/main`) | After |
|---|---|---|
| `pytest backend/tests -q` | 3280 passed, 1 skipped (`74620a7`) | **3314 passed, 1 skipped** |

The +34 is this branch's own: 33 in the new module, plus one from splitting a `test_elo_memoization.py` test in two. Suite was run green at both bases — 3267 → 3301 on `9a20ca8` before the rebase, 3280 → 3314 after it; `9a20ca8..74620a7` does not touch `ranking_service.py`, `trade_service._shrink_user_elo`/`_value_uncertainty` or `tier_config.json`, so the captured golden is unaffected by the rebase.

| `npx tsc --noEmit` (mobile) | n/a — zero files under `mobile/` in the diff | n/a |
| `mobile/scripts/testid-lint.sh` | n/a — same reason | n/a |

- **New: `backend/tests/test_pin_tier_bounded.py` — 33 tests.** The Adams scenario (pinned
  1565.28 in `second` [1400, 1575], 17 down-votes → Elo 1426.6, materially down, never outside
  the band); clamp at both edges; a pin exactly on a band boundary; a pin in a band gap; a pin
  above the top band; unranked/`None`-tier pins frozen rather than crashed or floated; a
  zero-vote pin untouched by the clamp; a clamped player climbing back into the band; both
  scoring formats plus monkeypatched bands proving the clamp reads the service's own format and
  the player's own position; the `pin_exclude_comparisons` narrowing in both directions and its
  `_value_uncertainty` sharing; monotonicity, direction-awareness, and the disclosed n=0→1
  residual; the F2 interaction both ways; the knob in both memo keys.
- **Byte identity proved by CAPTURE.** `backend/tests/fixtures/pin_tier_bounded_golden.json`
  was produced by copying the new module's own `build_service`/`snapshot` verbatim into a
  detached worktree of pristine `origin/main` (`9a20ca8`; `git diff e8ae476..9a20ca8 --
  backend/` is empty) and running it there before a line of production code changed. Asserted
  as a whole document at `pin_tier_bounded=0` + `pin_unpin_on_newer_swipe=1`. A guard test
  asserts the golden still *exhibits* the freeze (every pinned player exactly on his pin, every
  pinned count 0, the un-pinned control moved), so the proof cannot rot.
- **Mutation matrix — every guard bites.** Each mutation applied to a clean tree:
  remove the clamp → **11 fail**; drop the `min(lo,pin)`/`max(hi,pin)` widening → **2 fail**;
  let an unranked pin float free → **1 fails**; count clamped-away votes as confidence →
  **3 fail**. Restored → 33 pass.
- **Updated, not deleted:** `test_override_pin_unpin.py` (41 tests) now states the Phase 0
  configuration explicitly instead of reading today's defaults, so it keeps gating the Phase 0
  contract, which is still reachable by knob. `test_elo_memoization.py` had two tests asserting
  a pinned Elo *exactly* — that was the freeze contract; split into the memo contract
  (cold == warm, and inside the band) plus a new test asserting exactness under the kill switch.
- **Prod measured read-only** (`DATABASE_URL_PROD`, `SELECT` only under
  `default_transaction_read_only=on`), 2026-08-18. Every board replayed through the **real**
  `RankingService._compute_elo`/`_pin_bounds` via `replay_from_db`; the "today" column
  reproduces the audit's 2,721-inert figure exactly, which is what validates the replay.

  | | Comparisons | Effective | Pins | Players who move |
  |---|---|---|---|---|
  | Today (freeze) | 4,013 | 1,292 (32.2%) | 2,735 | 0 |
  | **Tier-bounded** | 4,013 | **3,938 (98.1%)** | 2,735 | **667 (24.4%)** |

  Ceiling on the second number is 739 — the pins that have ever appeared in a comparison at all
  — so **90.3% of every pin the user has ever voted on now moves**. The 72 that do not are 47
  pins below the lowest band (frozen by design) and 25 clamped hard at an edge.
- **Correction to the 2026-08-18 audit, found by the replay:** the operator's 18 Davante Adams
  comparisons are `decision_type = 'trade'`, and trade decisions have **never** entered
  `comparison_counts` for any player (`_compute_stats` walks only `_swipes`). His Elo now moves
  (1565.28 → 1530.15) but his effective value is the consensus seed 1138.8 both before and
  after. The audit's `n = 6` came from unfiltered SQL over `swipe_decisions`; it flagged its own
  confidence on that arithmetic as medium-high. The mechanism is real — the 353 → 1,666 jump in
  live *ranking* comparisons is what measures it — the per-player +12.5% is not.
- **Sim gate: Tier 4 (none, CI only).** Backend-only diff; zero files under `mobile/`.
  `qa/sim-runs/last-sim-run.json` not written — under D-056 there is nothing to run.
  `FTF_SKIP_SIM_GATE=1` is the standing posture for any push.
- **Not covered by any test here:** whether the thawed boards produce better decks. That is
  empirical and the lever is `pin_tier_bounded` — one `PUT /api/admin/config` to set and to
  undo. Also untested: the band-edge UI affordance, which is a client change and deliberately
  not built (scope §5).

---
## 2026-08-18b — Bug-sweep follow-ons (items 3/4/5) + research 6/7

**Branch:** `feat/sweep-followups-2026-08-18` (off `origin/main` `90fb19a`). **Not shipped** — awaiting operator go.

| Gate | Sweep baseline | After |
|---|---|---|
| `pytest backend/tests -q` | 3148 passed, 1 skipped | **3191 passed, 1 skipped** |
| `npx tsc --noEmit` (mobile) | clean | **clean** |
| `check-*.js` | 54 suites | **56 suites, all pass** |
| `testid-lint.sh` | OK | **OK** |

**Two false-confidence findings, both caught by sabotage rather than by review:**
1. `test_trade_decision_idempotency.py` defined its own `swipe_once()` caller, proving the *contract*
   while leaving `server.py`'s two call-site gates unpinned — both could be deleted with every test
   green. Closed with `inspect.getsource` route pins (the `test_pass_cooldown.py` idiom).
2. `check-swipe-failure-recovery.js` exempted rewinds that called `setDeck([])`. Unsound — the guard
   is a ref that outlives the deck — and its only real effect was to let the one site that forgot
   (QuickSet regen) pass. Exemption removed; scan went **4 → 9 sites**.

**Sabotage coverage:** item 3 ran 65 mutations (all RED, three initially-weak assertions rewritten
after they survived); item 4 ran 9; item 5 ran 9; the orchestrator separately sabotage-verified the
QuickSet guard clear, the picker `loading` assertion, and both new route pins.

**Prod reads (read-only, `DATABASE_URL_PROD`):** `trade_decisions` 933 rows — 40 double-writes
(0.015–0.200 s) vs 23 genuine re-decisions (147.7 s+), 738× empty band; 62 duplicate `swipe_decisions`
rows ≤1 s apart, 48 correlating with a duplicated decision.

**On-device checks owed (next build):** (1) **SignIn keyboard** — fresh install, tour on, tap the
username field: the ring must follow it up. This is the highest-value check in the batch and is a
30-second visual confirm. (2) QuickSet regen: pass a card, take the Quick-Set prompt mid-generation,
return, confirm the deck rebuilds and the card can still be passed. (3) Calculator PICK chip still
correct with the server field live.

---

## 2026-08-18 — Phase 0: board-override pins + forced regeneration (branch only, NOT merged)

Branch `feat/unpin-overrides`, rebased onto `origin/main` @ `355bddb`. Scope block:
[`docs/plans/three-model-bakeoff/scope-phase0.md`](../docs/plans/three-model-bakeoff/scope-phase0.md).
Three knobbed fixes for the defect diagnosed in
[`docs/reviews/2026-08-18-valuation-age-audit.md`](../docs/reviews/2026-08-18-valuation-age-audit.md)
plus the `force`-ignored-while-running bug from the bug-sweep ticket.
**Not pushed, not merged** — build-agent output awaiting operator review.

| Gate | Baseline (`origin/main`) | After |
|---|---|---|
| `pytest backend/tests -q` | 3175 passed, 1 skipped | **3224 passed, 1 skipped, 0 failed** (271s) |
| `npx tsc --noEmit` (mobile) | n/a | **not run — zero files under `mobile/`** |
| `mobile/scripts/testid-lint.sh` | n/a | **not run — no testIDs touched** |

- **+49 tests, zero regressions.** `test_override_pin_unpin.py` (41) and
  `test_force_supersedes_running_job.py` (8). Every knob has a behaviour test AND a
  kill-value test.
- **Kill-value byte-identity is proven against captured output, not asserted.**
  `backend/tests/fixtures/override_pin_golden.json` was produced by running the test's
  exact fixture against pristine `origin/main` **before a line of production code
  changed**, and is compared as a whole document (elo / comparison counts / shrunk elo /
  uncertainty / effective value). A companion test asserts the golden still *exhibits*
  the defect (`value > consensus` while `elo` never moved), so the proof cannot rot into
  a tautology if the fixture drifts.
- **The fixture reproduces the audited numbers exactly**: consensus value 1138.83, pinned
  board value 1385.95, and at the kill values the effective value sits at 1215.87 —
  *above* consensus purely because the player was voted on. With F1 on it is 1138.83,
  i.e. exactly consensus.
- **Mutation-checked.** Reverting the impression gate makes
  `test_a_superseded_job_writes_no_impressions` fail with **4 orphaned impression rows**;
  reverting the route gate makes `test_forced_request_while_running_spawns_a_new_job`
  fail. A control test proves the same harness *does* write impressions normally, so the
  zero-rows assertion is not vacuous.
- **Two existing test files changed, both because the contract genuinely moved, neither
  weakened.** `test_rnk_elo_golden.py`'s "an overridden player's Elo never moves" was the
  pre-F2 contract; it is now three tests (pinned against *earlier* swipes; released by a
  *newer* one; the old contract restored by the kill switch). `test_elo_memoization.py`'s
  spy reconstructed `_elo_cache_key` by hand and needed the pin knobs added after they
  were folded into the key (so a kill pulled via `PUT /api/admin/config` takes effect on
  warm sessions immediately).
- **Prod blast radius measured read-only** (`DATABASE_URL_PROD`, `SELECT` only under
  `default_transaction_read_only=on`), 2026-08-18: 4,013 comparisons, 2,721 inert
  (67.8%); 2,735 pinned entries, 739 of them carrying at least one vote. With the shipped
  defaults live comparisons stay at **1,292/4,013 (32.2%)** — F2 is inert on legacy pins
  by design. What F1 changes immediately: **6,250 of 8,026 confidence-contributing
  player-sides (77.9%) stop counting.**
- **Sim gate: Tier 4 (none, CI only).** Backend-only diff; zero files under `mobile/`.
  `qa/sim-runs/last-sim-run.json` not written — under D-056 there is nothing to run.
  `FTF_SKIP_SIM_GATE=1` is the standing posture for any push.
- **Not covered by any test here:** whether released boards actually produce better decks.
  That is an empirical question and the named lever is `pin_legacy_at_epoch` — a single
  `PUT /api/admin/config` to set and to undo. See scope §6.

---
## 2026-08-18 — Operator bug sweep B1–B5 (five fixes, two adversarial rounds)

**Branch:** `fix/bug-sweep-2026-08-18` (off `origin/main` `90fb19a`). **Ticket:** [`docs/reviews/2026-08-18-bug-sweep/ticket.md`](../docs/reviews/2026-08-18-bug-sweep/ticket.md).

| Gate | Baseline (pre-change) | After |
|---|---|---|
| `pytest backend/tests -q` | 3125 passed, 1 skipped | **3148 passed, 1 skipped** |
| `npx tsc --noEmit` (mobile) | clean | **clean** |
| `mobile/tests/check-*.js` | 48 suites, all pass | **54 suites, all pass** |
| `mobile/scripts/testid-lint.sh` | OK | **OK** |

Baseline was captured on a clean worktree **before any edit**, so every post-change result is
attributable. Note the baseline required a real `npm ci` — an initial copied `node_modules` was
stale and produced a phantom `expo-document-picker` error that was **not** a real failure.

**Six new suites** (+23 tests): `test_pick_labels_in_matches.py` (16), `test_tier_order_roundtrip.py`
(7), `check-guide-spotlight-tracking.js`, `check-tier-move-placement.js`,
`check-picker-pick-filter.js`, `check-swipe-failure-recovery.js`. None registered in
`mobile/package.json` — CI globs `tests/check-*.js`.

**Every new test was sabotage-verified RED→GREEN.** Notable, because the first attempts were not
sound:
- `check-tier-move-placement.js` was **polarity-blind** — a reviewer inverted both direction guards (shipping the opposite of the requested behavior) and all 12 assertions stayed green. Rewritten to lift the updater bodies out of source and assert real placement; the same inversion now fires 10 assertions.
- `test_digit_only_ids_skip_the_pick_query` was **vacuous** — it raised `AssertionError` inside a block guarded by `except Exception`. Rewritten against a connection spy with a positive control. See **G-050**.
- `check-swipe-failure-recovery.js` asserted the guard clear by text containment, so keying it on `ctx.tradeId` instead of `ctx.rawId` would have passed while silently restoring the bug for edited cards. Now pins `ctx.rawId`.
- `check-guide-spotlight-tracking.js` check 8 asserted only that a viewport predicate existed, and pinned an incomplete clamp. Now executes the arithmetic.

**Simulator gate:** not run — Maestro/simulator work is retired (**D-056**, 2026-08-15);
`FTF_SKIP_SIM_GATE=1` is the standing posture. TestFlight is primary QA.

**Shipped:** `main` `60105ca` (sweep) → Render **live**; `7583358` is the final tip. TestFlight
**build 117**, submitted and processing. Note the marketing version stayed **1.14.0**, not 1.14.1:
`eas.json` sets `appVersionSource: remote` and the project has an `ios/` directory, so EAS reads
`CFBundleShortVersionString` from `Info.plist` — the `app.json` bump was inert (the #131 bare-workflow
gotcha, `docs/runbook.md:452`) and was reverted so the repo states what actually shipped. A real
version bump means editing `Info.plist` and cutting another build.

**Sim gate skipped** (`FTF_SKIP_SIM_GATE=1` on all three pushes): Maestro/simulator work is retired
per **D-056**; this is the standing posture, not a deviation.

**Not covered by automation:** B1's spotlight tracking is verified structurally only — no test
exercises a real scroll, so the visual behavior rests on review plus on-device QA. B2's client-side
ordering is now behavioral, but no flow drives the multi-select chip row (TiersScreen still exposes
only four testIDs). **On-device checks owed:** (1) analyst tour on Trades — scroll during `s2.2`,
ring must track and must vanish cleanly when the card leaves the viewport; (2) Tiers **single-position**
tab (not "All" — its per-position re-spread confounds the read), chip-move a player down, confirm top
placement, then tap the same chip again and confirm nothing moves; (3) calculator "Real values" →
PICK chip shows rungs, and RB no longer lists them; (4) Matches both segments on a Sleeper league
with traded picks — expect `2026 1st` / `2026 2nd (from Jared)`; (5) force a swipe failure and
confirm the card can still be passed afterward.

---

## 2026-08-18 — Engine quality wave (D-074, renumbered from D-068) built, NOT shipped

Branch `feat/engine-pick-and-diversity` off `origin/main` @ `90fb19a`. Five knobbed
ranking/gating fixes for the two live-corpus defects (picks buying fairness for free;
one asset flooding a whole deck). **Not pushed, not merged** — build-agent output awaiting
operator review.

- **pytest 3150 passed / 1 skipped / 0 failed** (264s) on the branch tip.
  Baseline on `origin/main` before any edit: **3125 passed / 1 skipped** — so **+25 new
  tests, zero regressions**.
- **25 tests** across `backend/tests/test_engine_quality.py` (22) and
  `backend/tests/test_engine_quality_golden.py` (3). Each of the five knobs has a
  behaviour test AND a kill-value no-op test; C1 additionally pins the brief's explicit
  property, *adding a pick to a fair package does not raise composite*, with a
  fixture-validity assertion that the defect IS live at the kill value (bare 1.554 →
  padded 1.584 uncapped; 1.554 → 1.554 with C1 on).
- **Kill-value byte-identity is proven against real pre-wave output**, not asserted:
  goldens for a deck and an asset-ideas run were captured by executing the same fixtures
  in a throwaway worktree at `origin/main` @ `90fb19a`, and `test_engine_quality_golden.py`
  asserts all-five-knobs-killed reproduces them exactly. A third test asserts the goldens
  are **not** vacuous (live defaults must differ), so the proof cannot silently rot into a
  tautology. Re-capture procedure is in that file's docstring.
- **Defect B fixture deck, before/after:** the flood source headlines **21 of 36** cards
  across three counterparties uncapped; **2** with `deck_headliner_cap=2`. The fixture
  floods ACROSS opponents on purpose — a per-opponent cap of 2 would still have served six.
- **Three existing tests moved and one guard was added as a result of the wave, all
  understood:** `test_fairness_gate_golden.py::test_v2_v3_fairness_score_parity` exposed
  that C1's ties let a padded sibling evict the bare deal (fixed by the tie-break, no test
  edit); `test_outlook_direction.py` (6 tests) exposed that an EMPTY job seed map makes
  "centerpiece" degenerate to "largest player id" (fixed by disabling the cap with no seed
  map, no test edit); `test_asset_ideas.py::test_receive_direction_mirrors_grouping`
  exposed that an absolute-gap C2 band mis-ranks a 0.572-fairness bare deal above its
  0.697 sibling (fixed by re-basing the band on fairness, no test edit). **No existing
  test was weakened to make this wave pass.**
- **Sim gate: Tier 4 (none, CI only)** per the operator's build brief — backend-only diff,
  zero files under `mobile/`. `qa/sim-runs/last-sim-run.json` not written; nothing to run.
- **Not covered by any test here:** the live-corpus effect. The five defaults are reasoned
  from fixtures, not fitted to the 563-impression corpus — each knob is the named tuning
  lever and a re-run of the corpus query is the measurement.

## 2026-08-18 — Dismiss cooldown (D-067) shipped

- **pytest 3125 passed / 1 skipped / 0 failed** on the merged tree (`505ca2c`), run pre-push.
- **15 tests** in `backend/tests/test_pass_cooldown.py`; **8 named sabotages** applied → RED → reverted: `shrink-window`, `unbounded-window`, `one-window`, `fail-open`, `db-only`, `alias-only`, `ignore-amnesty`, `amnesty-everything`, `amnesty-likes`. `alias-only` REDs **only** the format-switch test — that test earns its place catching the alias trap rather than duplicating its neighbour.
- Two-sided bars included by design: the cooldown must **expire** (a 20-day dismiss returns) and the amnesty must be a **boundary** (a post-cutoff dismiss still suppresses).
- **Sim gate: n/a per D-057** (Maestro/simulator retired). No TestFlight build cut — backend-only change; mobile identical to v1.14.0 build 116.
- Deploy verified **by content** (`pass_cooldown_days` present in prod `/api/admin/config`), not by uptime.


## 2026-08-17 — Decline reason capture SHIPPED + v1.14.0 build 116 to TestFlight

**Code.** Two squash merges: backend `feat/decline-reasons-backend` @ `5056d1e`, mobile
`feat/decline-reasons-mobile` @ `4d57aae` (main `b97744c..8082aa2`), plus the gen-v2 G6 knob
reconciliation `92d2358`. Flag `feedback.decline_reasons` ships **true for all users**.

- **Merged-state backend suite: 3110 passed / 1 skipped / 0 failed** (254s), incl. 58 new tests in
  `test_decline_reasons.py` — gate + kill-switch byte-identity, progressive-write idempotency,
  impression_id fallback matrix, the mobile payload verbatim, the per-code Elo matrix with the knob
  on AND off, analytics props.
- **Mobile:** `tsc --noEmit` **clean** and `testid-lint OK` on a worktree at `main` after `npm ci`
  from main's lockfile. 38/38 mobile check suites green on the branch tip; merged mobile files were
  verified byte-identical to that tip, so the result carries.
- **Correction to an earlier claim:** the `ImportRankingsSheet.tsx` → `expo-document-picker` TS error
  previously recorded as "pre-existing on origin/main" is **not a real defect** — it is an artifact of
  a stale shared `node_modules`. A correct install yields zero TS errors.

**SIM GATE: WAIVED by operator, 2026-08-17.** Tier-1-class mobile screen change; operator waived the
requirement and accepted "green on touched flows + documented notes on the rest". The two Maestro
flows (`decline-reasons-fixed-option.yaml`, `decline-reasons-other-free-text.yaml`) were **authored
but never executed** — they were blocked on the all-on flag fixture, which this merge supplies, so
they are runnable from now on with no passing run behind them. Pushed with `FTF_SKIP_SIM_GATE=1`.
**TestFlight is the only runtime evidence this feature has.** Not covered by any executed test: the
on-device keyboard/send-button interaction, and the real device → route write path.

**Release.** EAS build `d57f593e` = **v1.14.0 build 116**, production profile, built from a clean
worktree at `main` @ `67b54f6`; status `finished`; `eas submit` uploaded to App Store Connect
(submission `e834b0bf`) during an active EAS Submit partial outage — build and submit were
deliberately decoupled for that reason.

- **Build-source trap caught (worth remembering).** The first attempt, build `e26e0fc6`/115, was
  **cancelled**: `eas build` archives the *local working directory*, and this repo's main checkout sits
  on `session-2026-08-13-notif-ship`, **141 commits behind main**. That archive contained neither
  `DeclineReasonPanel.tsx` nor `declineReasons.ts` and carried version 1.13.2 — it would have shipped
  the feature-less old app to TestFlight labelled as a downgrade. Always build from a checkout you have
  confirmed contains the feature files.
- **Prod flags verified live** post-deploy via `GET /api/feature-flags`: `feedback.decline_reasons: true`,
  `trade_gen.v2: false`, `trade.presentment_rules: true`.

---

## 2026-08-17 — 2026-08-16 feedback wave shipped (17 items, v1.13.5 build 114)

- **Merged-tree gates (orchestrator-run, integration branch):** pytest **3050 passed / 1 skipped / 0 failed**; `tsc --noEmit` clean; **48/48** `check-*.js` structural suites; `testid-lint.sh` OK.
- **Sabotage discipline:** every new behavioral test across all 7 groups proven RED on its named sabotage then green on revert (G6 14/14, G5 13/13, G3 8 sabotage classes, G2 T-P1..T-S10, G4 U-1..U-4 + BT-1, G9 U-1..U-5 + S-10a..e, G1 backend 4 + mobile 7). Phase-4 added 5 more; two of them (F-5 consensus `_emit`, F-7 hide-sites) REDded **only** the new test while the pre-existing suite stayed green — the coverage gaps were real.
- **Cross-group tripwire:** G4's `test_offer_hard_lock_330.py` (BT-1) green against G6's rewritten engine on the merged tree — the single-pin hard lock survived the presentment rewrite.
- **Sim gate: NOT run — n/a per D-056** (Maestro/simulator retired). Runtime evidence for this wave is the per-group operator TestFlight checklists on **build 114**, still owed.
- **Deploy verified by content:** `trade.presentment_rules = True` in prod `/api/feature-flags` (170 flags). Render auto-deploy did NOT fire; deploy triggered explicitly (see `docs/recovery/2026-08-16-feedback-wave-sweep.md`).
- **Owed:** operator prod-DB deck-eval replay (G6 bands on divergence boards + real like history); #339 `pick_gap_frac` tuning (no pick-carrying candidates in any corpus); TestFlight checklists; first-week `presentment-tripwire` watch.



## 2026-08-13 — Notification inbox growth surface phase 1 (SHIPPED to `main`)

- **Change:** five commits, rebased onto `3b64a44` and merged to `main` on the operator's ship directive (which also resolved the `counter_offer` four-not-five question and ratified the two adjacent dead-tap fixes). Taxonomy registration → backend inbox rows + coalescing + server-side dismiss → both clients (glyphs, routing, instrumentation, empty state) → docs. `express`-equivalent gate posture: **sim gate SKIPPED, `FTF_SKIP_SIM_GATE=1`**, per D-P1-08 restated in the build brief.
- **Backend:** `pytest backend/tests -q` → **2685 passed / 6 failed / 1 skipped**. The 6 failures are all in `test_rookie_scope.py`, are **pre-existing on `origin/main`** (verified by `git stash`-ing every change and re-running that file alone, which failed identically), and are **local-only**: CI runs Python 3.12 and is green on `main` (`gh run list --workflow ci.yml`); local is 3.14. **Not caused by this work, and not fixed by it.**
- **New:** `backend/tests/test_notif_inbox_growth.py` — 13 tests over the three things whose failure mode is silent: GD-8 coalescing (one row per league per UTC day, incl. the yesterday boundary and the dismissed-row-is-not-a-target case), the `match_expiring` idempotency gate (incl. cross-type metadata comparison and the fail-closed path), and server-side dismissal (retention, per-user scoping, and that clearing is point-in-time rather than a mute).
- **Mobile:** `npx tsc --noEmit` exit 0; `bash scripts/testid-lint.sh` OK; `node tests/check-notif-glyphs.js` **5/5**.
- **`check-notif-glyphs.js` earned its keep on its first run.** It failed immediately on `trade_accepted` / `trade_declined` — the DB writes `f"trade_{outcome}"` while only the push kind `match_accepted` was in `V2_MATCH_KINDS`, so two of the four ORIGINAL inbox types had a glyph and a dead tap. Code review had not caught it; the test did, before any of this shipped.
- **Web:** `node --check web/js/app.js` clean. **No web test harness exists**, so web's glyph map, tap router and the new `dismiss-all` call are covered only by the parity test's source-text assertions. The `switchView('matches')` fix and the dismiss round-trip have **never executed in a browser**.
- **NOT verified anywhere:** every row template, the new empty state, the empty-state invite gate, and all three analytics emitters. Nothing has rendered on a simulator or a device. The four backend write sites have not fired against a real DB — their tests exercise the DB helpers directly, not the routes.
- **Simulator gate + Maestro: WAIVED** under **D-P1-08**, restated by the operator in the build brief. No `qa/sim-runs/last-sim-run.json` written — **not fabricated**.
- **Standing caveat, unchanged and now one suite worse:** no `check-*.js` suite runs in CI (`.github/workflows/ci.yml` runs pytest, `tsc`, and testid-lint only). `check-notif-glyphs.js` therefore **gates nothing**, on a cross-client enum whose whole failure mode is silence.

---

## 2026-08-12 — Feedback #300 (position-scoped trade candidates), shipped LIT with gates waived

- **Change:** `5139b45` (PR #112), v1.13.1 **build 106**, both flags **ON**. Backend `medians` field on `/api/league/power-rankings`; mobile divider + Buyer/Seller bands + stacked-roster drill-in + Offer/Target handoff; rules A and B removed ([D-044](DECISIONS.md)); two analytics events.
- **Verified on the merged tree, re-run by the orchestrator rather than taken from agent reports:** `pytest backend/tests -q` **2610 passed / 1 skipped**; `tsc --noEmit` exit 0; `testid-lint OK`; `check-league-drill-in` 29; `check-analytics-297-302` 35; `check-single-pin-actions` 17; `check-league-candidates-300` 67; `check-picks-subset-invariance` 72; `check-analytics-300` 51. **271 structural assertions.**
- **Falsification:** 40 + 12 + 42 sabotages executed across the three build rounds. **One genuine false pass found and fixed** (S21: dropping `if (!query.isFetched) return` left the suite green because the assertion matched an identifier that also appears in the dep array). That is the **fifth** false-passing test caught in this session across five independently authored suites.
- **Simulator gate: WAIVED by operator. Maestro execution: WAIVED by operator.** `06-position-trade-candidates.yaml` is authored and **has never run**. No `last-sim-run.json` written — not fabricated. **The 44pt hit-slop treatment, the divider and the rule-A removal have never executed on a device or simulator.** The operator confirmed the shipped build behaves in TestFlight, which is the only runtime evidence in existence for this feature.
- **Analytics verified in production.** Deploy-then-probe run post-merge: 4 events posted, `{"accepted":4,"dropped":0,"rejected":[]}`, then every property read back out of `user_events.props` — both `league_pos_candidates_viewed` rows and both `league_candidate_pinned` mirror combinations `(offer, below)` / `(target, above)`. Note the trap this gate exists for: without `X-Device-Id` the response is `{"accepted":0,"dropped":0,"rejected":[{"reason":"no_identity"}]}`, which has `dropped == 0` and reads as a pass.
- **Still true and worth repeating:** none of the six `check-*.js` suites run in CI. They are `npm run`-only, so **none of the 271 assertions gate anything**.

---

## 2026-08-12 — P1 audit remediation shipped (sim gate retired by operator, not waived)

- **`express`: P1 remediation shipped — simulator gate SKIPPED, `FTF_SKIP_SIM_GATE=1`.** Not a
  one-off waiver: operator decision **D-P1-08** retires the Maestro/simulator/screenshot
  apparatus as standing policy — it consumed more budget than it returned and its quality
  degraded as the surface grew. **TestFlight is now the primary QA method.** No
  `qa/sim-runs/last-sim-run.json` written — **not fabricated**. The pre-push hook fired and was
  overridden deliberately, with the operator's explicit go. `CLAUDE.md`, `githooks/pre-push` and
  `docs/runbook.md` still describe the old policy and are **owed an update** (D-P1-08).
- **Verified instead:** full backend suite **2663 passed / 1 skipped** (3m51s) on the rebased
  tree; `npx tsc --noEmit` clean against a fresh in-worktree `npm ci`; `testid-lint` exit 0;
  `check-anchor-labels.js` 20/20; `check-invite-social-proof.js` 13/13. Baselines measured on
  this tree before editing, never quoted from another branch: 2467 → 2504 (P1-7) → 2663 (after
  rebase onto `main` plus the two pre-ship fixes).
- **NOT verified on device.** Five changed anchor rung labels, the anchor progress hint, both new
  invite surfaces and the share-image footer are visual and have never rendered on a simulator or
  a phone. This is the accepted cost of D-P1-08 and is owed on the TestFlight pass.
- **Sabotage-proven guards.** The anchor-label AST walker **false-passed on its first cut** — it
  inspected only the root of each initializer, so `key === '1_second' ? '1 2nd' : anchorLabel(key)`
  slipped through; fixed to walk the whole subtree, all five mutations now fail as intended. The
  tier-route 404 was proven to come from the flag guard rather than a missing route (body shape +
  `url_map` membership). The `league_id` scrub exemption was proven narrow three ways: an email
  under the same key is still redacted, a long digit run under any other key is still redacted,
  and the allowlist is exact-key rather than substring.
- **Analytics NOT yet proven end-to-end.** T1 registration ships in this push, but the corrected
  probe (**HLD §H-6**: `X-Device-Id`, valid envelope, `accepted > 0` **and** `dropped == 0`, then
  a read-back of `user_events.props`) runs against production **after** the Render deploy. Until
  it passes, treat every new event as unproven — the endpoint returns 200 while dropping. The
  original probe spec in this round would have passed against a broken build; that is why it was
  corrected before use.
- **Not shipped, deliberately:** email capture (built, then **reverted in full** — flag, policy,
  docs and living-memory — by operator decision: the sequencing was backwards and no
  email-sending infrastructure exists to consume it), P1-9 trade push and P1-10 Sleeper analytics
  (both still hold unanswered build-blocking decisions), P1-11 (dropped, D-P1-01).

---

## 2026-08-12 — Send in MFL + Send in ESPN shipped live (sim gate WAIVED all session, CI never ran)

- **`express`: Send in MFL + Send in ESPN + platform unlink + ESPN credential verification shipped — gates skipped by operator.** `FTF_SKIP_SIM_GATE=1` on every push (warning emitted each time); **no `qa/sim-runs/last-sim-run.json` written — not fabricated**. CI never ran: the operator directed direct-to-`main` pushes rather than PRs. `main` moved `3293f4a` → `cad99fb`.
- **Verified instead of CI**, per push: targeted backend suites (178 → 135 → 123 → 122 depending on surface), 12→18 `mobile/tests/check-*.js` including main's own P0-6/P0-7 pins, `testid-lint` exit 0, `tsc --noEmit` clean on a fresh in-worktree `npm ci`. The full ~2,400-test suite was **deliberately not run** — it stalled four separate agents mid-session.
- **Sabotage-proven guards** (each failed first, then restored): MFL pick hard-block (guard removed ⇒ the mocked write was reached with the pick silently dropped); ESPN pick + unmapped-asset hard-blocks; **cross-user unlink isolation** (removing the `WHERE user_id` clause made another user's row deletable — the security property that mattered most).
- **TestFlight 1.13.0 builds 102/103/104/105, then 1.13.1 build 107.** Every status read from `eas-cli build:list --json`, never the exit code — **`eas build` exits 0 even when the remote build ERRORED** (a concurrent session lost builds 99/100 that way). Build 106 was another session's. **Build-ordering lesson: flags are server-side, so `espn.send` could not be enabled until a build containing the lazy send-triggered auth existed (103) — enabling a flag whose client code is absent from the installed build *degrades* it.**
- **Live production verification, by content not by uptime:** `/api/feature-flags` serves `trade.send_in_mfl: true` and `espn.send: true` (neither key existed before); `DELETE /api/espn/link` and `DELETE /api/mfl/auth-link` both return 401 unauthenticated (route live and auth-gated, not 405).
- **MFL write path LIVE-VERIFIED** — a real 2-for-2 proposal succeeded from the app (`trade_sent {platform:"mfl", outcome:"proposed"}`). Because the adapter **refuses ambiguous success**, that outcome is positive evidence the real import response parsed unambiguously. `pendingTrades` also read live: field vocabulary confirmed, `FP_0002_2028_2` confirms the pick encoder against a real trade.
- **ESPN write validated without spending a real trade** — negative probes with a nonexistent `relatedTransactionId` returned 409 `TRAN_NOT_FOUND` for both `TRADE_ACCEPT` and `TRADE_DECLINE`, and `items:[]` returned 409 `TRAN_INVALID_TRADE_TEAM_COUNT` for propose. Both are validation-class errors only reachable *after* auth, so auth + envelope + `type` are all confirmed while nothing real was touched. **No real ESPN send has been made from the app — that remains owed.**
- **Sleeper iOS reachability probe: PASS 4/4** (Chrome-spoofed and honest headers × Wi-Fi and cellular, all HTTP 200), run from TestFlight build 107 and reported via `sleeper_probe_result` analytics rather than transcription. Probe shipped, run, and **deleted the same day**; result in `../docs/plans/sleeper-ios-reachability-probe-result-2026-08-12.md`.
- **Analytics correctness checked, not assumed:** `trade_sent`'s NULL top-level `platform` column initially looked like a repeat of the NULL-`platform` incident. It is not — that column is the *emitter* (`ios`/`server`), the fantasy platform lives in `props.platform`, and `sleeper_send_succeeded` behaves identically. New event names were added to `NON_INTENT_EVENTS` in the same commit that registered them.
- **Flag-mirror trap fired twice.** Any new key in `config/features.json` must be mirrored into `release.json`, `onboarding-v2.json`, and `profiles-on.json` or `test_seed_ui_test_db.py` fails (69 tests). Caught both times before push.
## 2026-08-11 — P1-7 anchor + manual unlock, derived rung labels (NOT merged, branch-only)

- **Change:** branch `p1-remediation-2026-08-11`, three commits. (1) Per-method unlock ladder — `'anchor'` gains its first arm (audit A-16: it could never unlock), `'manual'` loses its unconditional `True` (A-17), both reading `RankingService.board_override_count()`; `_tiers_rule()` extracted; `database.backfill_anchor_unlocked_formats` added as the first-unlock fan-out suppression; additive `anchor_count`/`anchor_required` on `GET /api/rankings/progress`. (2) Anchor rung labels derived from `TIER_LABEL` (five of eight had drifted, not the two the audit found) + `mobile/tests/check-anchor-labels.js` + the wizard's unlock hint + `anchors.rung.*` testIDs. (3) The `anchors-done` seed profile and its `app_user.anchors` seeder handler.
- **Verified (this worktree, re-run after every commit):** `pytest backend/tests -q` **2504 passed / 1 skipped**, against a **2467 / 1 baseline measured on this same tree before the first edit**. The +37 is fully accounted for and contains no pre-existing failures: `test_anchor_unlock.py` **29 new** (one case parametrized ×2), `test_pick_anchor.py` 17 → **18** (the D15 lane-separation assertion), `test_seed_ui_test_db.py` 69 → **76**. `npx tsc --noEmit` exit 0, no output; `testid-lint.sh` → `testid-lint OK`; `check-anchor-labels.js` **20/20**.
- **Falsification — and it earned its keep.** Every assertion in `check-anchor-labels.js` was run against a deliberately sabotaged tree. **The first cut false-passed on the single most important mutation:** re-typing a label as `label: key === '1_second' ? '1 2nd' : anchorLabel(key)` — the original defect wearing a ternary — because the assertion inspected only the *root* of each `label` initializer. This is exactly the case the design cited as the reason an AST walk beats a grep, and the AST walk fell into it anyway. Fixed to search the whole initializer subtree and to whitelist two exact initializer shapes; all five mutations (ternary, template literal, indirection through another function, `no_value → 'waivers'`, inlined `BELOW_LADDER_LABEL`, dropped `ANCHOR_TIER` key) now fail as intended. Same family as [G-035](GOTCHAS.md).
- **The seed fixture proves the unlock rather than assuming it.** `anchors-done.json` seeds `unlocked: false` deliberately — a seeded `unlocked_formats` row satisfies the monotonic floor *before* the new branch is consulted, so the obvious fixture would have gone green with the fix reverted ([G-037](GOTCHAS.md)). `_validate_anchors` now **refuses** the incoherent shape, and `test_anchors_done_actually_clears_the_unlock_bar` builds a real `RankingService` from the seeded board and asserts it clears the bar — so the fixture and the branch are proven to meet, not assumed to.
- **Sim run: none.** Per [D-P1-08](../docs/plans/audit-p1-remediation/DECISIONS-p1.md) the Maestro/simulator apparatus is retired and TestFlight is primary QA. No `last-sim-run.json` written — **not fabricated**.
- **Not verified on device, and it should be:** the wizard's new unlock hint (`anchors.unlock-hint`) and the five changed rung labels are visual changes no automated gate here can see. `check-anchor-labels.js` proves the labels are *derived*; it cannot prove they *render*. **Owed on the next TestFlight pass.**
- **Same pre-existing gap as the batch below:** none of the `mobile/tests/check-*.js` scripts run in `.github/workflows/ci.yml`, so `check-anchor-labels.js` **gates nothing** until that job is wired. It is a `npm run test:anchor-labels` a human has to remember.

## 2026-08-11 — Feedback #297/#298/#299/#302 + batch analytics (sim gate DEFERRED, operator-directed)

- **Change:** branch `feedback-integration-v2`, cut from `origin/main` @ `f65bab7`, merging `feedback-build-league-299-302` and `feedback-build-trades-297-298` plus an analytics round. #297 honest-empty lineup row; #298 single-pin deck recovery (V1) + the team-pill regenerate defect; #299 32pt League roster tiles (−47%, 728pt reclaimed on a 26-man roster, 4 → 8 players above the fold); #302 stack-header drill-in exit + the first Android `BackHandler` on that screen. Analytics: two new client events (`lineup_impact_unavailable`, `league_team_closed`), three widened props (`mode` on `find_trades_tapped` + `trade_card_viewed`, `source` on `find_trades_tapped` — the last a **bug fix**, that prop had been sent into an empty registry and popped on every row since #257).
- **Verified (merged tree, this worktree, re-run by the orchestrator — not taken from agent reports):** `pytest backend/tests -q` **2452 passed / 1 skipped**; `npx tsc --noEmit` exit 0, no output; `testid-lint.sh` → `testid-lint OK`; `check-single-pin-actions.js` **17/17**; `check-league-drill-in.js` **29/29**; `check-analytics-297-302.js` **35/35**. 81 structural assertions total.
- **Falsification:** every behavioural assertion was run against a deliberately sabotaged tree — 30 (league) + 9 (trades, four aimed at the seam #169 created) + 20 (analytics). **Four false-passing tests were caught this way and fixed**, in four independently authored suites: an ancestor-walking JSX gate check ([G-035](GOTCHAS.md)); a first-element-only testID lookup; a platform assertion that survived a sabotage leaving the lookup line in place; and three raw-source scans matched by comments naming the constructs they forbade. Treat "my test passes" as unproven here until a sabotage fails it.
- **Sim run: DEFERRED by operator** ("Good to signoff that we ship without a flag & defer the sim gate"), after the bright-line disclosure that the batch touches analytics surfaces. **No `last-sim-run.json` written — not fabricated.** Two Maestro flows authored but **NOT executed**: `mobile/.maestro/flows/league/05-drill-in-back-affordance.yaml` and `mobile/.maestro/flows/smoke/12-trades-single-pin.yaml`.
- **The Android hardware `BackHandler` was WITHDRAWN from this ship, not verified** (operator, 2026-08-11) — precisely because no Android device or emulator was involved at any point and TestFlight is iOS-only. Removing it is what closes the batch's largest unverified-code gap. Two assertions now pin the withdrawal (a live registration turns both suites red), and both were **sabotage-proven** by re-adding the effect and confirming each suite fails. `'hardware_back'` remains a reserved analytics value with no emitter. **Owed with the first non-App-Store release:** restore the effect, flip both assertions in the same commit, and exercise it on a real Android device.
- **Owed at ship, not skippable by the sim-gate deferral — the deploy-then-probe gate.** After merge + Render deploy, hand-roll one `POST /api/events` per new name with its **full** property set and assert both `dropped == 0` **and** every property echoed back out of `user_events.props`. Name-survival and prop-survival are separate silent failures: `analytics_ingest.py` pops unregistered props with only a counter bump, and `trade_card_shared.landing` is a live in-tree example of a registered name whose prop is discarded. **Do not substitute `GET /api/admin/analytics/health`** — its counters are in-process and reset on deploy.
- **Pre-existing gap, now three times larger:** none of the ten `mobile/tests/check-*.js` scripts run in `.github/workflows/ci.yml`; they are `npm run`-only. **None of the 81 assertions above gate anything** until that is wired. Proposed job in `docs/feedback/items/297-lineup-impact-single-pin/status.md` §5.5.

## 2026-08-11 — P0 remediation batch (sim gate SKIPPED, operator-directed express)

- **Change:** branch `p0-remediation-2026-08-10` — eight P0 launch blockers from the 2026-08-09 mobile UX audit (P0-1/2/3/5/6/7/8 + P0-9 test-prep), 15 code commits + merge of #169. Full corpus in `docs/plans/audit-p0-remediation/`.
- **Verified (merged tree, this worktree):** `pytest backend/tests -q` **2448 passed / 1 skipped / 0 failed** (clean worktree — the 6 environmental `test_rookie_scope` failures of the data-carrying main checkout do not reproduce here, consistent with G-030[#169]); `npx tsc --noEmit` clean; `testid-lint.sh` OK; `check-trade-text.js` 28/28; `check-card-disposition.js` 10/10; taxonomy registration verified name-by-name (16 client + 1 server, zero unregistered emissions — grep table in the W2-P07 build record).
- **Sim run: tier-1 SKIPPED entirely** (operator: "proceed without the sim gate — eating up too much usage", confirmed after bright-line disclosure: batch touches route + flag + analytics surfaces). Push via `FTF_SKIP_SIM_GATE=1`; **no `last-sim-run.json` written (not fabricated)**. Pre-skip on-sim work: app built green (Release, localhost-pinned), dedicated simulator created, pre-flight of all six new flows (every copy string + testID resolves in source), control-run evidence prepared (`git grep` at ab9368f proves the new testIDs absent pre-fix, so the flows fail by construction on the unfixed tree). Runs were blocked twice by another session holding :7001/:5001 before the operator called the skip.
- **Tier decision (recorded for the record): tier 1**, not 2 — the batch adds a screen, changes navigation, and changes rendered state on six screens; tier 2 is "mobile logic, no UI change".
- **Owed at next sim session:** the full tier-1 set + the batch's six new flows (`p0-1-quickset-unlock`, `p0-5-account-only-picker`, `p0-6-espn-copy-trade`, `trades-generation-failure`, `guide-no-false-signoff@release`, `league/invite-join`) + modified captures (`trades`, `matches@espn`, `league@quickset-done`, `leagues@account-only`, `onboarding-tour@fresh`); the P0-9 flag-pinned beat validation incl. the s5.1 proof (use the now-registered `deck_regenerated` row); analytics destination checks; re-captures + freshness sweep (note: TabNav changes are analytics-only — PNGs stay visually accurate, hash-staleness flags under the corrected manifest are false positives).
- **Toolchain gotcha (load-bearing for every future worktree build):** the standing convention of symlinking `mobile/node_modules` from the main checkout makes the app UNBUILDABLE — expo's CLI branches on whether its own directory resolves inside the project root and then requires `metro-runtime`, which is not top-level in this lockfile. Real in-worktree `npm ci` + `pod install` required; `rm -rf mobile/ios/build` also deletes RN codegen sources, so re-run `pod install` before rebuilding.

## 2026-08-11 — #169 frame E + card frame C (sim gate DEVIATION mid-run, operator-directed)

- **Change:** branch `feedback-169-e-and-card` — League Summary collapsed outlook strip (flag-dark, `outlook.odds`) + Pass/Like moved inside the top deck card + `outlook_strip_toggled` analytics event (taxonomy + tracking plan; operator rejected the dark-flag analytics waiver). Doc set (plan/HLD/LLD/PRD/scope rev 2, adversarially reviewed, 21 findings applied) in `docs/feedback/items/169-outlook-league-summary/`.
- **Verified (merged tree):** `npx tsc --noEmit` clean; `testid-lint.sh` OK; `check-card-disposition.js` 10/10 **with double sabotage proof** (guard flip → FAIL; reintroduced TradesScreen testID → FAIL; restored → pass); taxonomy test 18/18 **with sabotage proof** (event removed from allowlist → FAIL → restored). Full `pytest backend/tests -q`: **2371 passed / 6 failed / 1 skipped** — all 6 in `test_rookie_scope.py`, **proven pre-existing and environmental** (fail with origin/main-identical backend bytes in the data-carrying main checkout; 34/34 pass in a clean worktree of the same commit; G-028, fix chip filed). CI on the PR is the clean-environment authority.
- **Sim run: Tier-1 HALTED mid-gate by operator** ("proceed without sim testing — eating up too much usage"); push via `FTF_SKIP_SIM_GATE=1`; no `last-sim-run.json` written (not fabricated). **Partial on-sim evidence before the halt:** extended `06-trades-deck` positional `childOf` asserts PASSED (both disposition buttons proven inside `trades.card-top`, no scroll — fails by construction on the old layout); screenshot proof of the operator's layout; `01-signin` full pass in the final harness config; manual launch-health check. Suite-level failures across 4 attempts were ALL environmental, diagnosed in sequence: `# flags: release` fixture not loaded (guided-avatar tour overlay swallowed taps), backend process reaped by shell teardown, **disk exhaustion to 0 bytes** (25 launch crash-loops in Hermes init — G-027 adjacent; ~4 GB freed), stale Maestro XCTest driver after `simctl erase`. None traced to the change under test.
- **Owed at next sim session:** green full-suite run; post-overlay like/pass tap-through of `06-trades-deck`; the four re-captures (`trades`, `matches`, `sheets-trade-dna`, `league-summary`) + `screen-freshness.sh` sweep; on-sim verification of the three re-derived `onboarding-tour@fresh` anchors.

## 2026-08-10 — Screen-library capture suite (sim gate tier-2 evidence)

- Full consolidated sweep on FTF-iOS18 (iOS 18.4): 43 capture flows, 7 cells
  (5 profiles × release/onboarding-v2), **102 captures, rails all zero in every
  cell** (vcr_misses / sleeper_live_egress_attempts / completed_proposes /
  propose_route_hits). One flaky flow (trios@near-unlock, tab-race — settle fix
  applied, still ~50% per run) recaptured green individually. tsc clean,
  testid-lint green, screen-freshness green ×25, backend suite 2207 passed
  (fixtures commit). Mobile app-code delta this branch: testRouteEntry.ts +
  one RootNav line — exercised by every launch-arg capture cell above.
## 2026-08-10 — Feedback batch #289-#294 (sim gate DEVIATION, operator-directed bypass)

- **SHIPPED 2026-08-10.** Squash-merged as `6c304c7` via PR #103; CI green (backend-tests, mobile-typecheck, maestro-testid-lint). Render deploy **verified by content**, not by uptime: `/api/feature-flags` serves `league.picks_always_counted = true` (155 flags), which only the new build can produce. iOS **1.12.0 build 98** uploaded to App Store Connect (submission `0095a36f`).
- **Version-bump trap, cost one wasted build.** `mobile/app.json` was bumped to 1.12.0 and **build 97 still shipped as 1.11.0**. This is a bare workflow — `mobile/ios/` is tracked — so EAS reads the version from the native Xcode project and ignores the Expo config. `eas build:version:set` manages the **build number** only. The three values that actually ship are two `MARKETING_VERSION` entries in `project.pbxproj` and the literal `CFBundleShortVersionString` in `Info.plist` (PR #104, `7553874`). Bumping `app.json` is necessary for the JS layer and **not sufficient for the binary**.

- **Change:** six feedback items in three groups on branch `feedback-289-294` (base `origin/main` @ `16b1dcb`), 16 commits, 51 files, +15,738/−106. **G1 #289** MFL Draft Room resolves franchise *and* player names (four ordered tiers, never a bare id). **G2 #290/#291/#292** value-aware mock run model + `need_pressure` + mock lifecycle (`abandon_completed_mock_drafts`) + pick affordance before tap + MFL owner names in the mock. **G3 #293/#294** draft-pick value counted in every subset and position filter, behind new flag `league.picks_always_counted`, **graduated to ON at ship by operator direction** ("293/294 ship live") together with its `LAUNCHED_FLAG_DEFAULTS` entry so it is visible from first paint; the flag remains the kill switch. Plus: `mobile/scripts/sim-run.sh` flag-pin repairs, five stale "mock is OFF" doc locations corrected, D-022/D-023/D-024.
- **Suite:** baseline `2308 passed / 1 skipped` after G1+G3 → **2326 passed / 1 skipped**, exit 0 (+18, all new). `npx tsc --noEmit` **exit 0** (real `npm ci` in-worktree — the main checkout's `node_modules` is ~190 commits stale and lacks `@react-native-cookies/cookies`, which yields a phantom error). `testid-lint.sh` **exit 0**. **All nine** `mobile/tests/check-*.js` pass, including two new ones (`check-picks-subset-invariance.js` 71 assertions, `check-mock-lifecycle.js` 52).
- **Sim run: NOT PERFORMED** — operator-directed bypass (`FTF_SKIP_SIM_GATE=1`) after being presented with the coverage gap and choosing it explicitly. **This is a Tier-1 deviation and the batch's largest change is the least covered:** G2's mock engine ships with unit + distributional evidence only and **no end-to-end run**. **Both groups ship live.** G3 was built dark and graduated to ON at ship on operator direction; it keeps a per-feature kill switch (`league.picks_always_counted` -> false, no redeploy). G2 has no per-change switch — `draft.mock` was already ON and the engine change is unflagged — so its only lever turns off the whole mock feature. G2 is therefore the largest change, the least covered, AND the least reversible.
- **Why the mock flow could not run:** `d3-mock-draft-loop.yaml` was authored but is unrunnable — `backend/tests/fixtures/profiles/standard.json` declares one league (`990000000000000001`) while d1/d2/d3 all target `1312140920132497408`, which is in no profile, and the seeder writes **nothing** for `mock_drafts` or draft status. The build agent's "one `leagues[]` entry" estimate was checked and does not hold; this is real seeder work. Pre-existing, unfixed, named.
- **Uncovered by any automated test** (do not read a green suite as covering these): G3 **R-5** and **R-0.4**, and the kill-switch drill **T-S6c** (manual). G1 has **no Maestro flow at all** by design — its acceptance surface is a live check against the operator's Dependables MFL league (62846), also not yet performed.
- **Harness findings — the gate had never actually run.** Every prior ledger entry since the gate's introduction reads "NOT PERFORMED", which is why three defects survived: `--flags` *replaced* the seeded flag map instead of merging; `--flags @file` was documented but unimplemented (the literal string was exported, JSON parsing failed with a stdout warning only, and the run continued with flags OFF); and the handshake fetched `/api/feature-flags` but **only archived it, never asserting** — so a flag-ON tier could assert flag-OFF behavior and exit 0. Additionally `$!` captured the subshell rather than python under bash 3.2 (macOS system bash), so the stale-Flask assertion fired on a clear port **every time** and the EXIT trap orphaned Flask on the port for the next run to talk to. All repaired and each proven by constructing the failure first; nine consecutive runs left no orphan.
- **Failing-first evidence captured** for every behavioral test (G2 T-290-04/10/11/14, T-292-01, D-16 keying; G1 T-289-06; G3 assertions 13/14). Three separate lanes found tests that **passed on the very defect they named** — G1's collision test (its stub raised on the triggering input), G2's one-sided distributional bars (a fully collapsed `sf_tep` board scored *higher* variety than a healthy one), and G3's atomicity assertions (`picksAlwaysCounted={false}` satisfied all twelve). G2's mobile agent also found two of its own first-cut assertions passing on their defects — one because the JSX comment explaining the behavior contained the string it was grepping for.
- **G2 measured results at pinned N=1500, both formats** (`1qb_ppr` / `sf_tep`): P(#1 at 1.01) 0.4553 / 0.6380; P(#1 past pick 3) 0.0893 / 0.0420 (shipped 0.1553); P(#7 at pick ≤4) 0.0000 / 0.0000 (shipped 0.1147); median run size 5.0 / 5.0. Calibration tripwire `test_w2_16` **did not fire**.
- **Fixed in passing:** two G2 tests used fixed user+league ids against the persistent SQLite DB and accumulated rows across runs (second full run reported `cleared 5 rows, expected 3`) — would have surfaced in QA as an unreproducible failure on any machine that had run the suite before. Both now self-clear.

## 2026-08-10 — Outlook: seed-type + IDP-coverage wiring, combined post-fix calibration (NOT merged, no flag change)

- **Change:** two wiring gaps closed, then one combined re-measurement. (1) `scripts/outlook_calibration_backtest.py` gains `seed_type(fx)` and threads `playoff_seed_type` into every `run_outlook` / `get_playoff_format` call, plus a **BUG-3 A/B block** mirroring the existing BUG-1 one; same wiring in `scripts/outlook_preseason_backtest.py`. (2) `pipeline.run_outlook` now calls `strength.lineup_pricing()` and `serialize.py` emits `meta.priced_slot_coverage = {fraction, total_slots, priced_slots, unpriced_slots[], affects_strength}`. `outlook.odds` untouched, `config/features.json` untouched, no `model_config` key, mobile diff is a **type-only** addition (`OutlookPricedSlotCoverage` in `mobile/src/api/league.ts`) with no UI/behaviour change.
- **Suite:** baseline on a fresh `origin/main` reset (`234a018`) **2284 passed / 1 skipped / 0 xfailed** (301 s) → **2297 passed / 1 skipped**, exit 0 (+13). `npx tsc --noEmit` clean (node_modules symlinked from a sibling worktree, removed after). New coverage: 4 payload/coverage tests in `test_outlook_odds.py` (fraction + named unpriced slots, full-coverage league, `affects_strength` false on `trailing_scores`, **prediction-neutrality vs a run serialized without the instrument**), 9 in `test_outlook_playoff_seed_type.py` (an **AST guard** that fails if any `run_outlook`/`get_playoff_format` call in either script omits the setting, the per-fixture seed-type helper, and a load-bearing check that fixed vs reseed brackets give different title distributions and identical playoff odds), plus the `meta` contract pin in `test_outlook_route_cache.py`.
- **Sim run: NOT PERFORMED** — measurement + dark-surface wiring with zero user-visible change (`outlook.odds` false everywhere, mobile diff is a type declaration); branch left unmerged for operator review.
- **Result — in-season, 6 league-seasons / 288 team-week predictions, 10k sims:** playoff Brier **0.0997** vs climatology 0.2500 (**+60.1 %**, cluster-bootstrap 90 % CI [+47.6, +72.2] — excludes 0); title Brier **0.0732** vs 0.0764 (**+4.2 %**, CI [−13.1, +20.0] — **includes 0**). Per week 0.2012 / 0.1065 / 0.0538 / 0.0372. Split by league: all six beat climatology on playoff, **three of six lose to climatology on title**.
- **Result — preseason (week 0), 72 team-seasons:** playoff Brier **0.1968** (+21.3 %, CI **[+2.9, +39.1]**); title 0.0746 (+2.3 %, CI [−18.9, +24.5]). Preseason − week-3 paired Δ **−0.0043** (CI spans 0) — preseason still nominally better than the week-3 model. Median-match leagues 0.2326, H2H 0.1789.
- **Result — the BUG-3 wiring in isolation:** pooled title Brier **0.0733 → 0.0732**; fixed-bracket leagues only 0.0817 → 0.0815; **playoff Brier bit-identical (max \|Δ\| = 0.000000)** and `playoff_seed_type: 1` leagues **bit-identical** (value 1 == reseed == pre-fix behaviour). The bracket rule was wrong for 4 of 6 league-seasons and correcting it moved the pooled title number by 0.0001 — **a null, reported as one.**
- **Over-confidence SURVIVED the fix wave.** Preseason top bucket 0.947 predicted → **0.778** realized (n = 9; was 0.949 → 0.750, n = 8); bottom bucket 0.034 → 0.167. In-season populated buckets stay inside ±0.05 (n = 99 and n = 100). Preseason skill lower CI bound moved the **wrong** way: +4.1 % → **+2.9 %**.
- **Also re-confirmed unchanged:** bye-week μ multiplier still NO-SHIP (Δ +0.0031, CI [−0.0054, +0.0125]; mechanism OLS slope −0.218 vs the naive −1.000); random-re-pairing fallback still costs ~7 % of playoff Brier.
- **Verdict:** (1) **bands, not percentages — stands, and is better supported than before**; a 5 %-rounded playoff percentage from week 6 is an operator risk call, not a validated result (calibration is pooled, not week-stratified). (2) **Gate numbers at week 6, allow bands from week 0, never gate at week 3** — week 3 is dominated by both neighbours and is the only week where title odds lose to a constant 1/12. Report: `docs/feedback/items/169-outlook-league-summary/calibration-combined-2026-08-10.md`; dated corrections issued to the three prior #169 reports.

## 2026-08-10 — Combined post-fix outlook calibration (sim gate DEVIATION, standing operator bypass)

- **Change:** seed-type + coverage wiring and the definitive combined calibration. Mobile diff is **type-only** (`mobile/src/api/league.ts` gains the `priced_slot_coverage` payload field) — no UI, no behaviour, `outlook.odds` false everywhere.
- **Sim run: NOT PERFORMED** — `FTF_SKIP_SIM_GATE=1` under standing operator authority; the smoke suite still doesn't exist and this change class renders nothing.
- **Verified:** full suite **2297 passed / 1 skipped**, exit 0; `tsc --noEmit` clean. Deliverable `docs/feedback/items/169-outlook-league-summary/calibration-combined-2026-08-10.md`.

## 2026-08-09 — ESPN numeric-id guard fix (backend-only, merged to main)

- **Change:** `server._fetch_sleeper_league_meta` + `trade_block_service.sync_league_trade_block` now pair their `isdigit()` guard with `database.is_linked_platform_league`, so ESPN/MFL/Fleaflicker-imported leagues (numeric native ids) no longer fire Sleeper requests that 404 on `/api/session/init` (prod noise + false `vcr_misses` in FTF_TEST_MODE). Same convention as the #149/#150 proxy fix. Commit `e7d0da7`.
- **Suite:** full `pytest backend/tests -q` → **2219 passed / 1 skipped / 1 xfailed**, exit 0 (562 s) — +2 regression tests in `test_espn_link_route.py` pinning both helpers to zero Sleeper calls on a linked ESPN league.
- **Sim run: NOT PERFORMED** — backend-only, no mobile diff, no schema/API/flag surface; pre-push hook gate not triggered (no `mobile/src/` change).
- **Follow-up:** revert the two harness workarounds in worktree `~/ftf-worktrees/screens-wt` (espn.json `sleeper.trade_block:false` pin; 404-cassette sentinel + gap-guard carve-out) once that branch rebases onto this fix.

## 2026-08-09 — BUG-5: IDP/K starting slots are unpriced (fix + backtest, NOT merged, no flag change)

- **Change:** `backend/outlook/strength.py` only — IDP slot eligibility in `select_starting_lineup()` (a `DL` slot now accepts DE/DT/NT, `DB` accepts CB/S/SS/FS, `IDP_FLEX` accepts any defender) plus a new `lineup_pricing()` instrument. New `scripts/outlook_idp_pricing_backtest.py`, `backend/tests/test_outlook_idp_pricing.py`, and one records fixture. No flag, no `config/features.json`, no `model_config` key, no mobile diff; `outlook.odds` still dark.
- **Suite:** baseline on a fresh `origin/main` reset (`359a0ff`) **2217 passed / 1 skipped / 1 xfailed** (706 s) → **2247 passed / 1 skipped / 1 xfailed**, exit 0 (+30). New file alone: 30 passed in 4.8 s.
- **Sim run: NOT PERFORMED** — validation-plus-neutral-fix change class with zero user-visible surface (`outlook.odds` false everywhere, no mobile diff), branch left unmerged for operator review.
- **Damage measured:** the DynastyProcess board carries QB/RB/WR/TE only, so in the operator's **FFv3** league **8 of 15 starting slots price at exactly 0.0** — **53.3 % of slots**, covering **33.0–34.3 % of the points those teams actually scored** (Sleeper `starters_points`, weeks 1–14). FFv3 is **4 of the 6 backtested league-seasons**; Lakeview is 0 %. The unpriced third is weakly differentiating: sd 58–65 season points vs 160–211 for the priced slots.
- **Result — five-variant preseason backtest, 10k sims, split by league.** V0 status quo reproduces the published baseline exactly (pooled playoff Brier **0.1959**, +21.6 %; FFv3 0.1789; Lakeview 0.2298). **Eligibility fix: 0 of 72 predictions moved** (asserted, not assumed). **League-mean fallback Δ +0.0005** (CI [−0.0056, +0.0061]); **coverage attenuation √ Δ −0.0019** (CI [−0.0167, +0.0070]), **linear Δ +0.0042**. Lakeview bit-identical under every variant.
- **Verdict: real defect, no available fix beats the status quo.** No license-clean dynasty IDP board exists (DynastyProcess, nflverse, FantasyCalc, KTC, Sleeper `search_rank` all checked). Shipped the correctness fix + the coverage instrument; the pricing gap is documented, not papered over. Preseason ship verdict unchanged; IDP-league odds must be **labelled offence-only** before the flag lights. Report: `docs/feedback/items/169-outlook-league-summary/idp-pricing-2026-08-09.md`; gotcha G-026.

## 2026-08-09 — Dated DP value boards + preseason-source revalidation (validation only, NOT merged, no flag change)

- **Change:** no product behaviour touched. New `backend/dp_values_history.py` (research-only dated DynastyProcess boards), 24 committed board fixtures + index in `backend/tests/fixtures/dp-values-history/` (484 KB), three scripts (`scripts/dp_values_history_capture.py` — the only one that uses the network, `scripts/outlook_preseason_backtest.py`, `scripts/outlook_pick_capital_dated_values.py`), and two test files. `backend/outlook/` unchanged, `config/features.json` unchanged, `outlook.odds` still dark, no mobile diff.
- **Suite:** baseline on a fresh `origin/main` reset (`ea19d4b`) **2194 passed / 1 skipped / 1 xfailed** (151 s) → **2217 passed / 1 skipped / 1 xfailed**, exit 0 (+23). New files alone: `test_dp_values_history.py` 15 passed, `test_outlook_preseason_source.py` 8 passed, 0.5 s combined.
- **New coverage:** commit resolution (`until=`/`path=` query shape, empty-result `LookupError`), raw-URL sha pinning, `slim_csv` filtering, all three crosswalk join tiers + position-strictness, scoring-column selection, **offline path asserted against an opener that raises on any network call**, refusal-not-substitution for an uncaptured date, fixture-index integrity, **no-look-ahead invariant** (`scrape_date <= key` on all 24 boards), roster rewind to real week-1 rosters, `auto` → `roster_value` at week 0, board-is-load-bearing check, and four re-scoring guards on the committed per-team records (including a deliberate assertion that preseason title odds do **not** beat climatology, so the null cannot rot away).
- **Sim run: NOT PERFORMED** — validation-only change class with zero user-visible surface (`outlook.odds` false everywhere, no mobile diff), and the branch is left unmerged for operator review.
- **Result — preseason `roster_value`, as-of week 0, 6 league-seasons / 72 team-seasons / 6 champion events:** playoff Brier **0.1959** vs climatology 0.2500 (**+21.6 %**, cluster-bootstrap 90 % CI **[+4.1, +38.3]** — excludes 0); title Brier 0.0740 vs 0.0764 (+3.1 %, CI [−17.7, +24.9] — **includes 0, no skill**). Indistinguishable from the week-3 model (paired delta −0.0013, CI [−0.0573, +0.0470]). Over-confident at the extremes (0.9–1.0 bucket: 0.949 predicted, 0.750 realized, n = 8); beats climatology in 4/6 league-seasons. Board coverage 96.8–99.3 % roster, 100 % starting-slot; unmatched DP rows 0.2–1.8 %.
- **Result — hypothesis 1b re-test:** sub-test (i) −0.113 → **+0.076, CI spanning zero**; confound −0.349 → **−0.415**; (ii)/(iii)/buy:sell bit-identical. Verdict **WEAKENED**.
- **Verdict:** preseason **title** odds — do not render. Preseason **playoff** odds — conditional go, banded not precise, BUG-1 (G-024) first. Report: `docs/feedback/items/169-outlook-league-summary/dated-values-revalidation-2026-08-09.md`.

## 2026-08-09 — Outlook odds calibration backtest (validation only, no ship, no flag change)

- **Change:** no product code touched. Added `backend/tests/test_outlook_calibration.py` (22 permanent invariant/fixture tests + 1 strict `xfail` tracking BUG-1), two offline analysis scripts (`scripts/outlook_calibration_backtest.py`, `scripts/outlook_strength_source_compare.py`), 9 committed Sleeper fixtures, and the calibration report. `outlook.odds` remains dark.
- **Suite:** baseline **2136 passed / 1 skipped** → **2158 passed / 1 skipped / 1 xfailed**, exit 0 (142 s). New file alone: 22 passed / 1 xfailed in 3.6 s.
- **Sim run: NOT PERFORMED for the wave push** (`FTF_SKIP_SIM_GATE=1`, standing operator bypass) — the mobile diff is dark-flagged contract/nullability fixes only (`outlook.odds` false everywhere); zero user-visible change.
- **Backtest result:** as-of weeks 3/6/9/12 over 6 real captured Sleeper seasons (72 team-seasons, 6 champion events). Playoff Brier **0.1113** vs climatology 0.2500 (**+55.5 %** skill, cluster-bootstrap 90 % CI [+44.5, +65.9] — excludes 0). Title Brier **0.0725** vs 0.0764 (**+5.1 %**, CI [−13.2, +22.3] — **includes 0, no demonstrated skill**).
- **Verdict:** MARGINAL PASS, conditional — playoff odds ship-worthy after BUG-1 (median-match ingestion, G-024) is fixed; title odds not validated. Report: `docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md`.

## 2026-08-09 — ESPN round-2 ship (sim gate DEVIATION, standing operator bypass)

- **Change:** cold-load login warm-up reload + reload control + wedge hint; league picker (`espn.league_picker` ON, `GET /api/espn/my-leagues`). Push `89c61b4`, build 96.
- **Sim run: NOT PERFORMED** (`FTF_SKIP_SIM_GATE=1`, standing authority). Maestro flow WAS extended (reload control) but not executed — no runnable dev client.
- **What WAS verified:** 2136 passed / 1 skipped, exit 0 (+27); tsc clean; testid-lint OK; **fan-API shape live-verified against an authenticated fetch on the operator's real ESPN session** — caught the lowercase-"ffl" filter bug (real abbrev is "FFL") pre-merge; fixture now mirrors the real payload. Round-1 fixes field-validated by the operator's successful private-league link (league_read 200 in events, 22:44 UTC).

## 2026-08-09 — ESPN-fix + morning-batch + observability ship (sim gate DEVIATION, standing operator bypass)

- **Change:** the wave below (ESPN webview fixes, #285, #286-288, integrations docs, api_observability) merged and pushed as one; combined suite **2109 passed / 1 skipped, exit 0**, tsc clean on final branch. `FTF_SKIP_SIM_GATE=1` under standing operator authority; ESPN fix's REAL validation is the operator's TestFlight walkthrough with the private league (checklist in `docs/feedback/items/espn-webview-escape/status.md`) — build 95.

## 2026-08-09 — API observability build (flag `obs.api_events` ON; worktree agent, merged/shipped same day — see entry above)

- **Change:** operator-directed observability program (`docs/feedback/items/api-observability/status.md`): `backend/api_observability.py` — outbound wrapper around every external egress chokepoint (Sleeper REST/GraphQL incl. the 3 documented bypass sites, ESPN, MFL, Fleaflicker, DP CSVs, KTC, Anthropic, Expo, Apple/Google) + inbound Flask hooks; events land in `user_events` (`api_call`/`api_request`, `user_id='system:api'`), errors always + successes 1-in-10 sampled (`model_config obs_success_sample_n`), 30 d retention purge, admin report `GET /api/admin/analytics/apihealth`. Backend + docs only; no mobile/web changes.
- **Sim run: NOT PERFORMED** — backend-only change class, and the branch is deliberately left unmerged for operator review (build agent has no merge authority; sim gate applies at ship).
- **What WAS verified:** baseline `pytest backend/tests -q` on the release base → **2086 passed / 1 skipped, exit 0**; after build → **2109 passed / 1 skipped, exit 0** (+23 in `backend/tests/test_api_observability.py`: per-service wrapper capture with cookie/JWT-never-stored redaction assertions, inbound hook capture + exclusions, 1-in-N sampling vs errors-always, kill-switch zero-writes, poisoned-event-store failure isolation, retention purge, apihealth report + `service` filter). `tsc --noEmit` n/a (no mobile diff).

## 2026-08-09 — Design-decision batch (#270/#272 A/B, #169, #279) (sim gate DEVIATION, standing operator bypass)

- **Change:** experiment `trades_home_inline` (strip/canvas variants, operator on strip), flag `trade.position_impact` ON, experiment `aggregate_tier_labels` (operator-only), two mock-lab revisions. Batched at operator direction ("Don't push E1 until we resolve these other two items too").
- **Sim run: NOT PERFORMED.** Standing bypass (`FTF_SKIP_SIM_GATE=1`). Both experiment builds carry explicit Maestro waivers (allowlist-gated to one real account, invisible to the QA harness identity).
- **What WAS verified:** `pytest backend/tests -q` → 2072 passed / 1 skipped, exit 0 (+8 new: experiment assignment/byte-identity ×2 builds, starter_impact tier/rank ×4 incl. tie-break determinism and the pure-weight-revise switch test); `tsc --noEmit` clean on the final combined branch; testid-lint OK; config-reference merge conflict union-resolved and re-gated.

## 2026-08-09 — Feedback wave 3 (#277/#278/#280/#281, #273-275, #269/#276) (sim gate DEVIATION, standing operator bypass)

- **Change:** tier labels app-wide (+3 routes gain additive `tier`), PickAssignment future-year/sheet fixes, sheet targeting (flag `trades.sheet_targeting` ON), scroll-to-trade, inline-home mockup lab. #282 held unmerged pending operator sign-off on prod-name fixtures.
- **Sim run: NOT PERFORMED.** Standing operator bypass (`FTF_SKIP_SIM_GATE=1`); smoke suite still doesn't exist.
- **What WAS verified:** `pytest backend/tests -q` → 2059 passed / 1 skipped, exit 0 (+6 tier-route tests); `tsc --noEmit` clean after every merge and post deferred-fix; flag mirror + testid-lint green; per-branch review before each merge.

## 2026-08-08 — Feedback wave #268/#267/#265/#263/#260/#257/#172 (sim gate DEVIATION, standing operator bypass)

- **Change:** 6 fixes/features + 2 mockup labs (see CHANGELOG same date). Two new flags ON (`trades.edit_full_sheet`, `trades.intent_modes`); one additive API field (`tier` on GET /api/trade/values); intent field in trade prefs.
- **Sim run: NOT PERFORMED.** Smoke suite still doesn't exist; standing operator bypass ("You can bypass the gate and push live to testflight", 2026-08-08) via `FTF_SKIP_SIM_GATE=1`.
- **What WAS verified:** `pytest backend/tests -q` → 2053 passed / 1 skipped, exit 0 (+12 new: #268 repro, 11 intent-mode tests); `tsc --noEmit` clean after each merge and on the final combined branch; flag mirror tests green; `testid-lint.sh` OK; node tests (league-unlocks 4/4); per-branch code review before every merge. #268's fix carries a test that reproduces the exact pre-fix client request (405) and proves the corrected URL (200).

## 2026-08-08 — Context-slim batch (sim gate SKIP, express-class: docs/config only)

- express: context-overload remediation (branch `context-slim-2026-08-08`) — gates skipped by operator direction. Diff touches `mobile/src/**/CLAUDE.md` (docs), living-memory, docs/, skills, hook config — zero app code. `FTF_SKIP_SIM_GATE=1` used for the push; CI (pytest + tsc + testid-lint) is the verification gate.

## 2026-08-08 — Feedback #266/#258 fixes (sim gate DEVIATION, standing operator bypass)

- **Change:** #266 ESPN-path link buttons dead on LeaguePicker (transition-settled auto-open) + #258 MFL team-name HTML entities (startup backfill of pre-#210 stored rows). Merge `b682ee2`.
- **Sim run: NOT PERFORMED.** Same blocker as the two entries below: the 11-flow smoke suite doesn't exist. Bypass is now STANDING operator authority ("You can bypass the gate and push live to testflight", 2026-08-08) until the flows land; exercised via `FTF_SKIP_SIM_GATE=1`.
- **What WAS verified:** `pytest backend/tests -q` → 2041 passed / 1 skipped, exit 0 (+4 new backfill tests, verified failing-first); `tsc --noEmit` clean under fresh `npm ci` (includes tonight's `@react-native-cookies/cookies` dep); fix-agent reproduced both root causes in code before changing anything.

## 2026-08-08 — ESPN Connect WebView ship (sim gate DEVIATION, recorded)

- **Change:** Phase 1b ESPN cookie capture (`EspnConnectScreen`, `EspnLinkSheet` auth-error self-serve, League-tab re-sync recovery), flag `espn.webview_capture` shipped ON. Commits `989343f`/`365e815`/`81a16a2` → pushed to `main` @ `d745146`.
- **Sim run: NOT PERFORMED.** Declared tier 2, waived by operator order at merge ("Merge now and push to testflight with the flag on" + explicit gate-bypass confirmation, 2026-08-08), exercised via `FTF_SKIP_SIM_GATE=1`. Same underlying blocker as the entry below: the new native dep (`@react-native-cookies/cookies`) needs a rebuilt dev client before any Maestro run, and the smoke flows don't exist yet.
- **What WAS verified:** `tsc --noEmit` clean (post-rebase); `node tests/check-espn-cookies.js` 14/14; `pytest -k "flag or feature or taxonomy"` 149 passed (post-rebase, flag ON + release-mirror green); manual testID cross-check (flow + registry + source agree); independent adversarial review — security clean, 8 findings fixed in `365e815`.
- **Compensating control:** EAS build 90 (v1.11.0) auto-submitted to TestFlight; QA checklist in `docs/plans/espn-connect-webview/scope.md` §3 (fresh capture / OTP hint / auth-recovery, real private league 493554) is the validation gate, with the flag flip-off as rollback.

## 2026-08-08 — ESPN auto-derived draft order (sim gate DEVIATION, recorded)

- **Change:** `suggested_order` prefill on PickAssignmentScreen (+ espn_service derivation). Tier 1 by the matrix (mobile screen change).
- **Sim run: NOT PERFORMED — the required artifact cannot exist yet.** The gate's tier-1 requirement is the 11-flow smoke suite; `mobile/maestro/` contains zero flows (the mobile-testing program has built seams/scripts/testIDs, not the flows). Maestro itself IS installed.
- **Deviation authority:** operator directive to ship ("Pick up and finish 3", 2026-08-08), exercised via the documented `FTF_SKIP_SIM_GATE=1` override. Receipts per the gate spec: this entry + the deviation note in `docs/plans/draft-extensions/build-espn-auto-order.md`.
- **What WAS verified:** `pytest backend/tests -q` → 2037 passed / 1 skipped, exit 0 (+42 new tests incl. the live-captured league-11896 fixture pinning the operator's inverse-regular-season decision); `tsc --noEmit` clean; all 4 mobile AST/behaviour check scripts pass. The mobile delta is a prefill of an existing editable list — no new writes.
- **Follow-up owed:** the 11 smoke flows are now the gate's own blocking dependency — until they exist, every tier-1/2 push needs this same override. Build them or re-tier the gate.

## Table of Contents
- [2026-08-08](#2026-08-08)
- [2026-07-04](#2026-07-04)
- [2026-06-11](#2026-06-11)
- [Archive: pre-2026-06 entries](archive/TEST_LEDGER-pre-2026-06.md)
- [Manual Verification History](#manual-verification-history)
- [Custom-Skill Benchmarks](#custom-skill-benchmarks)
- [Tests Planned but Not Yet Run](#tests-planned-but-not-yet-run)
- [Verification Discipline](#verification-discipline)

---

## 2026-08-08

### ESPN Connect WebView build (worktree `espn-webview-capture` off `origin/main` @ `cb6aacb`)
- **`cd mobile && npx tsc --noEmit` → clean, exit 0** (run after both the feature commit and the review-fix commit).
- **`node mobile/tests/check-espn-cookies.js` → 14/14 checks pass** — pure extractor `pickEspnCookies` (pair/half-pair/trim/braces/multi-bag), `readEspnCookies` polls both ESPN domains, `clearEspnCookies` clears 2 names × 2 domains × 2 native stores (the fresh-login guarantee).
- **`python3 -m pytest backend/tests/ -q -k "flag or feature"` → 148 passed**; broader `-k "taxonomy or analytics or events or flag or feature or seed_ui"` → **320 passed** (new flag `espn.webview_capture` in registry + release-mirror; 4 `espn_connect_*` events in the taxonomy with prop entries).
- **testID cross-check (manual):** every id referenced by `mobile/.maestro/flows/espn-connect-capture.yaml` and the components CLAUDE.md registry resolves in `mobile/src/`. `mobile/scripts/testid-lint.sh` does not exist on this branch (`mobile/scripts/` is gitignored — see below); a tracked lint script is a separate task.
- **NOT run:** the Maestro flow itself (needs a rebuilt dev client carrying the new `@react-native-cookies/cookies` native pod) and the in-WebView login leg (waived per scope §3 — live third-party page; covered by the scope block's TestFlight QA checklist). `pod install` fails on this machine (CocoaPods 1.16.2/Ruby 4.0.3 `Unicode Normalization not appropriate for ASCII-8BIT` on the spaces-in-path repo); the EAS build regenerates the lockfile.

### Suite trajectory, 2026-07-09 → 2026-08-06
- **252 → 1466.** Reconstructed from commit messages during the living-memory revival pass; each figure is the count the committing session reported. Checkpoints: 272 → 285 → 382 → 521 (accounts P1/P2) → 558 → 632 → 781 (v1.9.0) → 855 (analytics P3/P4) → 937 (teardown W2) → 979 (owned picks) → 998 → 1025 → 1209 → 1336 (deck engine) → 1359 → 1378 → 1405 → 1445 → 1455.
- **Counts are not strictly monotonic in log order.** Parallel worktree agents committed against different baselines — the 1414/1415 pair on 2026-08-03 is the clearest example. Treat a lower count in a later commit as a branch artifact, not a regression.

### Measured live on 2026-08-08 (this checkout, `teardown-remediation` @ `30492ac`)
- **`python3 -m pytest backend/tests/ -q` → 1466 passed, 1 skipped, 41.7s.**
- **`cd mobile && npx tsc --noEmit` → clean, exit 0.**
- ⚠️ **This is the 62-commits-behind base, not the project's test posture.** The rookie-draft QA handoff cites **1685 passed / 1 skipped on `origin/main` @ `cee4324`**. Quote the origin/main number when describing the project; quote this one only when describing this checkout.
- The 1466 includes two untracked test files not yet committed: `test_espn_pick_assignment.py` (6 tests), `test_finder_config_consolidated.py` (5 tests).

### Practices worth keeping (observed in this window)
- **Failing-first is used and stated in commit messages** — `#238` lineup before/after and the `market.movers` work both note tests written failing-first; several 07-25 fixes note the regression shape was "verified failing pre-fix via stash".
- **Flag-gated waves re-run the suite twice** — once as built, then again with flags ON as a separate gate. The deck-engine waves all did this.
- **A contrast guard runs in CI-shape** — `mobile/scripts/check-contrast.js` over 13 token pairs, `npm run test:contrast`.
- **`mobile/scripts/` is gitignored**, so JS regression checks live in `mobile/tests/` instead.

## 2026-07-04

### TC-API-001 — Manual Trade Calculator endpoints (/api/trade/evaluate, /api/trade/values)
- **Test:** 8 pytest cases over an injected universal pool ([backend/tests/test_trade_evaluate.py](../backend/tests/test_trade_evaluate.py)): symmetric→even, lopsided→unfair+favors, per-player values match `elo_to_value` exactly, unknown-id graceful drop, one-sided packages (no verdict), empty→400, bogus format→default, values-endpoint shape + ETag 304.
- **Result:** **PASS 8/8**; full suite **252 green**. Real-pool smoke (local Flask, live DP data): 671 valued players; top-vs-mid → `unfair/favors: give/ratio 0.008`; mirror trade → `even/1.0`.
- **Also verified:** mobile live mode end-to-end in Expo web with a contract-shaped fetch stub (backend has no CORS, so browser-origin calls can't hit it — native is unaffected); demo mode unchanged (Bijan parity scenario byte-identical since 07-02: 2,536/2,874, +9%/+12%).
- **Not yet run:** live mode against prod from a real device (needs deploy).

### TC-API-002 — Send in Sleeper error-contract hardening (/api/sleeper/link, /api/trades/propose)
- **Test:** +6 route tests ([backend/tests/test_sleeper_write_route.py](../backend/tests/test_sleeper_write_route.py)) locking each branch the mobile `SendInSleeperButton` depends on: no-key→503 `sleeper_unconfigured`; `bad_request` (non-numeric league / no counterparty); pre-flight **expired stored token**→409 `sleeper_expired` + credential dropped (the #1 real reconnect trigger, distinct from the mid-call auth-error branch); non-auth write failure→502 `sleeper_write_failed`; rosters-fetch exception degrades to 400 `roster_not_found` (never an unhandled 500); GET surfaces `expired:true`.
- **Result:** **PASS 14/14** in the file (8 prior + 6 new); full backend suite **258 green**; mobile tsc clean. These run the real Flask handlers against a real in-memory DB + real Fernet key, mocking only the Sleeper network — so they double as the local route smoke.
- **Reviewed, no code change needed:** runtime paths already fail safe (`_fetch_league_rosters` catches all → None → structured 400; adapter maps auth vs generic failures correctly). Hardening was coverage, not bug-fixing.
- **Still deferred by design:** slice-4 calculator Send surface (needs a real counterparty); flag `trade.send_in_sleeper` stays OFF; on-device link→propose against real Sleeper (needs a full EAS build — `react-native-webview` is native — + throwaway account).

## 2026-06-11

### TC-ENG-004 — 3-team cycle clearing (find_three_team_cycles)
- **Test:** 4 pytest goldens for the dark/uncovered kidney-exchange 3-team cycle clearer — Pareto A→B→C→A detection, no-benefit→empty, <3 members→empty, lineup-feasibility blocks a roster-breaking handoff.
- **Result:** **PASS 4/4** ([backend/tests/test_three_team_cycles.py](../backend/tests/test_three_team_cycles.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Findings:** **F-1 (P3 dead code)** `find_three_team_cycles` is implemented + exported but **never called** (no caller; trade.three_team flag only in a comment). Correct + now tested — a product decision away from wiring on.
- **Artifacts:** [`qa/results/TC-ENG-004.md`](../qa/results/TC-ENG-004.md).

### TC-DB-002 — DB concurrency, write integrity, recency
- **Test:** concurrent member_rankings upserts (atomic replace), concurrent distinct trade decisions (no loss), concurrent ranking swipes (WAL under contention), check_for_match 90-day recency bound. Threaded against scratch DB.
- **Result:** **PASS 5/5.** 8 concurrent upserts → exactly 20 rows (atomic), 16 decisions all persisted, 24 swipe rows no lock errors, stale (>90d) like excluded.
- **Findings:** none at thread scale. Postgres multi-process pool saturation remains a pre-scale Render load-test follow-up (not reproducible with threads on SQLite).
- **Artifacts:** [`qa/db/tc_db_002.py`](../qa/db/tc_db_002.py), [`qa/db/_concurrency_probe.py`](../qa/db/_concurrency_probe.py), [`qa/results/TC-DB-002.md`](../qa/results/TC-DB-002.md).

### TC-INT-001 — Sleeper-boundary input handling (G-003..G-008)
- **Test:** session_init defensive handling of null roster slots, int IDs, garbage IDs, empty roster, dup IDs; passthrough error handling (bad username, parse-url).
- **Result:** **PASS 8/8.** Nulls filtered, int IDs coerced, garbage filtered, empty roster degrades gracefully, bad username → 404 (not 500).
- **Findings:** F-1 (P3) duplicate roster IDs not deduped (3→6); harmless today, one-line `dict.fromkeys` fix.
- **Artifacts:** [`qa/sec/tc_int_001.py`](../qa/sec/tc_int_001.py), [`qa/results/TC-INT-001.md`](../qa/results/TC-INT-001.md).

### TC-CFG-001 — feature flags + model_config live-tuning contract
- **Test:** flag map + FTF_FLAGS env precedence; admin config auth (401)/unknown(404)/badval(400); live write→reload→readback; reload endpoint auth.
- **Result:** **PASS 11/11.** FTF_FLAGS override wins; config write persists + reloads (v3 reads same live _cfg).
- **Findings:** **F-1 (P3 operational)** surplus floors gate *divergence* cards only — *consensus-basis* decks (cold/low-coverage leagues) are fairness-gated, so cranking surplus floors has NO effect there (use fairness_threshold/consensus_score_scale). F-2 (P3) marginal flag makes min_side_surplus_marginal the live floor. Documented in config-reference.md.
- **Artifacts:** [`qa/api/tc_cfg_001.py`](../qa/api/tc_cfg_001.py), [`qa/results/TC-CFG-001.md`](../qa/results/TC-CFG-001.md).

### TC-PERF-001 — performance: cold-start, warm latency, concurrent load
- **Test:** measured backend vs charter budgets — cold boot, cold/warm session_init, warm GET p50/p95, generate end-to-end, per-opponent enumeration bound, 8-way concurrent init+generate, error-free-under-load.
- **Result:** **PASS 9/9.** Cold boot 1.0s; warm GET p50/p95 = 20/58ms; generate 31 cards in 1.28s; 8 concurrent users 0 errors. All within budget at local scale.
- **Caveats (honest):** concurrency test shares the trade-job cache (same fixture user) → proves session/cache thread-safety, not N independent generations. Real prod risks (cold Sleeper fetch in session_init, v3 enumeration on large league) NOT exercised locally — flagged for a Render-side load test.
- **Artifacts:** [`qa/perf/tc_perf_001.py`](../qa/perf/tc_perf_001.py), [`qa/results/TC-PERF-001.md`](../qa/results/TC-PERF-001.md).

### TC-ENG-003 — engine gate config-responsiveness (admin tuning surface)
- **Test:** 4 pytest goldens proving the tuning knobs are monotone/predictable — min_side_surplus (↑→fewer cards), trade_elo_gap_max knife-edge, waiver_slot_cost erodes extra-player side, tier_mult_elite scales composite.
- **Result:** **PASS 4/4** ([backend/tests/test_engine_gates_config.py](../backend/tests/test_engine_gates_config.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Observation:** the legacy parity fixture yields 4 cards legacy / 0 v2 — v2 correctly rejects one-sided trades legacy surfaced (reinforces "kill-switch is a real downgrade").
- **Artifacts:** [`qa/results/TC-ENG-003.md`](../qa/results/TC-ENG-003.md).

### TC-API-002 — public-route auth-intent audit
- **Test:** classify all public routes read vs mutating; allowlist-check public mutations; empty/garbage-body robustness; CORS posture.
- **Result:** **PASS 4/4.** 13 public /api routes (8 read, 5 mutating); all 5 mutations intentional (session/init, demo, feedback, extension/auth, parse-url). No 5xx on garbage; CORS same-origin-only. **No unauthenticated state-mutating routes** — recon "44 none-auth" concern resolved.
- **Findings:** F-1 (P3) no rate limiting on pre-auth mutations (session/init, extension/auth); F-2 (P3 process) new `_require_initialized_session` gate (25 routes) added since TC-API-001 → those counts stale.
- **Artifacts:** [`qa/api/tc_api_002.py`](../qa/api/tc_api_002.py), [`qa/results/TC-API-002.md`](../qa/results/TC-API-002.md).

### TC-E2E-004 — cross-league flow + cross-league disposition
- **Test:** matches/all across leagues; awaiting; portfolio over 2 leagues; create match in league A, switch session to league B, disposition the A match (cross-league branch).
- **Result:** **PASS 9/9.** Cross-league accept (session on B, match in A) → 200, decision persisted on the match's own league, Elo signal queued for replay. Correctly league-scoped.
- **Findings:** none. Observation: match fires on whichever swipe completes the mirror (locate by DB state, not response id).
- **Artifacts:** [`qa/e2e/tc_e2e_004.py`](../qa/e2e/tc_e2e_004.py), [`qa/results/TC-E2E-004.md`](../qa/results/TC-E2E-004.md).

### TC-RNK-001 — Elo math golden fixtures (engine input quality)
- **Test:** 6 pytest goldens for the Elo update — exact pairwise math (K=32 → ±16), K-factor by decision type (rank 32 / like 8 / pass 4, linear), zero-sum conservation, 3-player decomposition + order preservation, override pinning, replay determinism.
- **Result:** **PASS 6/6** ([backend/tests/test_rnk_elo_golden.py](../backend/tests/test_rnk_elo_golden.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Observation:** displayed Elo is rounded to 1 decimal in `get_rankings`, and that rounded value is what's published to member_rankings + fed to `elo_to_value` — whole valuation pipeline runs at 0.1-Elo precision. Zero-sum only holds without tier overrides.
- **Artifacts:** [`qa/results/TC-RNK-001.md`](../qa/results/TC-RNK-001.md).

### TC-E2E-003 — superflex (sf_tep) format path + isolation
- **Test:** sf_tep trio→rank3→generate via X-Scoring-Format header; format-partitioned persistence; 1qb_ppr isolation; per-format independent Elo; sf_tep card validity.
- **Result:** **PASS 8/8.** +9 sf_tep rank rows, 1qb_ppr unchanged (222→222, isolated), sf_tep member_rankings 0→685, sf_tep generate → 31 valid cards. **Same player 1qb=1605 vs sf=1800 Elo** (QB premium in superflex working as intended).
- **Artifacts:** [`qa/e2e/tc_e2e_003.py`](../qa/e2e/tc_e2e_003.py), [`qa/results/TC-E2E-003.md`](../qa/results/TC-E2E-003.md).

### TC-API-001 — API consistency + doc-drift audit
- **Test:** static analysis of all 92 server.py routes (naming, error-shape taxonomy, auth-gate distribution) + doc-drift vs api-reference.md + live envelope/error-contract sampling.
- **Result:** **COMPLETE 7/8** (the 1 FAIL is the surfaced naming finding). Error contracts solid (every error body has an `error` key; 401/404/400 correct). Auth gates: session 35 / none 44 / cron 13 / bearer 1.
- **Findings:** F-1 (P2) 39 `jsonify({"error": str(e)})` raw-exception leaks; F-2 (P3) error-value vocabulary split (42 code-style vs 44 sentence-style vs 23 code+message); F-3 (P3) 2 undocumented routes (`/api/feedback/admin`, `/api/tiers/copy-from-format`); F-4 (P3) lone snake_case segment `/api/sleeper/league_users`; F-5 (P3) no envelope standard / no version prefix.
- **Docs updated this cycle:** added `/api/trades/awaiting` + stochastic-deck-order note to api-reference.md; v3-feasibility "no trades" failure mode to runbook.md.
- **Artifacts:** [`qa/api/tc_api_001.py`](../qa/api/tc_api_001.py), [`qa/results/TC-API-001.md`](../qa/results/TC-API-001.md).

### TC-E2E-002 — restart resilience (in-memory session + job loss)
- **Test:** generate a deck, restart the server process against the same DB, verify graceful degradation: stale token→401, stale job→404 (no hang), data survives, FB-46 swipe of a pre-restart card reconstructs + persists, new session fully functional.
- **Result:** **PASS 9/9.** Old job 404 in 0.00s; 646 member_rankings survived; FB-46 swipe persisted +1 decision; post-restart generate → 31 cards.
- **Findings:** none. In-memory job/session loss is a graceful degradation, not a failure mode; recon operability concern closed.
- **Artifacts:** [`qa/e2e/tc_e2e_002.py`](../qa/e2e/tc_e2e_002.py), [`qa/results/TC-E2E-002.md`](../qa/results/TC-E2E-002.md).

### TC-DB-001 — schema integrity, migration idempotency, SQLite↔Postgres parity
- **Test:** fresh-init schema parity on SQLite AND a real local Postgres (table set + per-table columns), `_migrate_db()` idempotency on both, dialect-branched upsert smoke (leagues/league_members/member_rankings/skips + the F-1 second-member upsert), and a read-only live-DB quality audit (orphans, enum domains, ISO timestamps, boolean storage, dup guards).
- **Result:** **PASS 24/24** incl. Postgres plane. Exact 24-table/all-column parity; migrations idempotent both dialects; **F-1 fix verified cross-dialect** (works on Postgres too, leagues stays 1 row).
- **Findings:** the 41 orphaned `league_members` (recon "HIGH, fix before scale") are **benign** — 0 have rankings, 0 in trade_matches; never-logged-in leaguemates. Recon item downgraded P3. data-dictionary.md confirmed in sync (24 tables; recon "22/23" was a miscount).
- **Env note:** `psycopg2-binary` (declared dep) was missing locally; installed to run the PG plane. Throwaway PG db `ftf_qa_parity` created + dropped.
- **Artifacts:** [`qa/db/tc_db_001.py`](../qa/db/tc_db_001.py), [`qa/db/_dialect_probe.py`](../qa/db/_dialect_probe.py), [`qa/results/TC-DB-001.md`](../qa/results/TC-DB-001.md), `qa/db/scratch/TC-DB-001-run.json`.

### F-1 (TC-E2E-001) RESOLVED — verified
- Commit `ddf67df` fixed the second-member `upsert_league` UNIQUE-constraint crash (dialect-aware `on_conflict_do_update` on the `sleeper_league_id` PK) + added `backend/tests/test_league_upsert.py` (3 tests). Re-verified: IntegrityError gone, TC-E2E-001 back to 67/67, regression test passes. E2E harness allowlist updated (no longer masks the error; now allowlists only the synthetic-league Sleeper 404).

### TC-SEC-001 — operator-endpoint auth enforcement
- **Test:** sweep all 8 operator routes (`/api/admin/*`, `/api/feedback/admin*`, `/api/debug/log`, `/api/feature-flags/reload`, `/api/cron/*`) across CRON_SECRET set/unset; in-proc test of `_require_cron_auth` prod branch (fail-closed) without a real Postgres; session-gate control on mutating routes.
- **Result:** **PASS 35/35.** Cron-gate enforces (401 missing/wrong/near-miss, success on match); prod fails closed (503 when secret unset); session routes 401 tokenless/bogus.
- **Refutes recon:** the discovery report's "5 unprotected admin endpoints (P0)" is **FALSE** — every route calls `_require_cron_auth()`. Lesson: recon findings are hypotheses until a TC verifies them.
- **Findings:** **F-1 (P2)** `run.py` binds `0.0.0.0` + `debug=True` with no local CRON_SECRET → operator routes exposed on LAN for local/self-host runs (prod on Render unaffected: fail-closed).
- **Artifacts:** [`qa/sec/tc_sec_001.py`](../qa/sec/tc_sec_001.py), [`qa/results/TC-SEC-001.md`](../qa/results/TC-SEC-001.md), `qa/sec/scratch/TC-SEC-001-run.json`.

### TC-ENG-002 — fairness-gate golden fixtures (1-for-1 gate + package-discount watch item)
- **Test:** 8 pytest golden fixtures in `backend/tests/` covering `package_value_v2` discount math (exact + monotone in `package_adj_gamma`), 1-for-1 gate config-driven knife-edge, discount→`fairness_score` propagation, FR8 outlook market-neutrality, and v2↔v3 fairness-floor parity + monotonicity. Self-calibrating where exact propagation is hard to hand-predict.
- **Result:** **PASS 8/8**, stable ×3; full backend suite now **178 passed** with the new file (no pollution). Graduated into the pytest suite — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job.
- **Findings:** **F-1 (P3)** `_fairness_v3` is a hand-copied mirror of v2 `_fairness` (standing TODO) — drift risk; this test now guards parity, but a shared `score_trade` extraction is the real fix (already planned in competitor-top20/03).
- **Key observation:** v3 lineup-feasibility is all-or-nothing — a roster that can't field a full QB1/RB2/WR2/TE1 lineup gets ZERO v3 cards (v2 still serves). Sharp edge worth a runbook note for "no trades" diagnosis.
- **Artifacts:** [`backend/tests/test_fairness_gate_golden.py`](../backend/tests/test_fairness_gate_golden.py), [`qa/results/TC-ENG-002.md`](../qa/results/TC-ENG-002.md).

### TC-ENG-001 — trade-engine kill-switch regression (legacy/v2/v3)
- **Test:** three FTF_FLAGS-pinned server instances (legacy / v2 / v3), ordering flags off; per-engine card-validity battery, flag-routing proof, legacy≠v2 divergence, v2→v3 top-card stability. Same user+league.
- **Result:** **PASS 30/30**, stable across 3 runs. Deck sizes legacy 13 / v2 33 / v3 33; all roster-ownership + fairness checks clean on all engines. v2's #1 trade always survives into v3; v2 top-10 → v3 overlap a deterministic 5/10.
- **Findings:** none. Observations: legacy fallback is a real UX downgrade (random opp Elo, smaller deck) not a transparent swap; v2→v3 top-10 continuity is exactly 50% (watch item if product wants tighter migration continuity).
- **Artifacts:** [`qa/eng/tc_eng_001.py`](../qa/eng/tc_eng_001.py), [`qa/results/TC-ENG-001.md`](../qa/results/TC-ENG-001.md), `qa/eng/scratch/TC-ENG-001-run.json`.

### TC-E2E-001 — full-stack happy path (automated harness)
- **Test:** session_init → trio/rank3 ×3 → trade generate (async job) → swipe → mirrored-like match (likes_you instant + two-session two-step) → disposition lifecycle (accept/accept → accepted, 409 repeat, 404 unknown, 400 bad input) → DB integrity sweep. Driven via HTTP against a local Flask on a scratch copy of `data/trade_finder.db`; mobile client timeout budgets as pass bar. Flags: v3 engine + all Tier 2 trade flags on.
- **Result:** **PASS 67/67 checks**, reproducible across runs. 31 cards in 0.8–1.5 s; cache-hit re-generate ≤4 ms; all calls within mobile budget.
- **Findings:** **F-1 (P1)** `upsert_league` keys on `(league_id, user_id)` but PK is league_id alone → IntegrityError swallowed on every second-member session_init, their league row never persisted. **F-2 (P2)** 7-day card-dedup vs unbounded match-dedup mismatch → already-accepted trade re-served then silently no-ops on like.
- **Artifacts:** harness [`qa/e2e/tc_e2e_001.py`](../qa/e2e/tc_e2e_001.py), report [`qa/results/TC-E2E-001.md`](../qa/results/TC-E2E-001.md), machine-readable run `qa/e2e/scratch/TC-E2E-001-run.json`.
- **Planned variants:** TC-E2E-002 restart-resilience, TC-E2E-003 sf_tep format, TC-E2E-004 Postgres parity.

## Manual Verification History

*Historical — predates the pytest suite. As of 2026-08-08 the project has a pytest suite of ~2000 tests (`backend/tests/`, run in CI's `backend-tests` job per `.github/workflows/ci.yml`); the ad-hoc methods below were the verification approach before that suite existed and are largely superseded. The 2026-05-21 entry that used to open this file (living-memory layer adoption, status pending) is archived in [`archive/TEST_LEDGER-pre-2026-06.md`](archive/TEST_LEDGER-pre-2026-06.md).*

| Verification artifact | What it tests |
|---|---|
| [`Test_League_Trade_Matches.xlsx`](../Test_League_Trade_Matches.xlsx) | Expected trade matches for a test league configuration |
| [`Trade_Matches.xlsx`](../Trade_Matches.xlsx) | Reference trade-match output for validation |
| `dump_mismatches.py` | DynastyProcess ↔ Sleeper player-name mismatches |
| `tmp_check_db.py`, `tmp_check_db2.py` | Ad-hoc DB integrity scripts |
| `GET /api/debug/log?n=100` | In-memory ring-buffer log (last 200 entries) for forensic checks |
| Manual smoke: `python3 run.py` → web client login → roster import → swipe → trade card | End-to-end happy-path verification |

**Caveat (historical):** at the time this table was written there was no automated regression suite, so a change that broke one of these flows was detectable only by manual re-run. That gap is closed — see the pytest suite note above. [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) Q-002 (pytest adoption) is resolved.

## Custom-Skill Benchmarks

| Skill | Benchmark | Result |
|---|---|---|
| **`project-reorganizer.skill`** | 6-phase methodology (scan, propose, cross-reference, execute, update imports, verify) vs ad-hoc reorganization | ~83% pass rate WITH skill vs ~43% WITHOUT (+40pp improvement). See [`project-reorganizer-eval-review.html`](../project-reorganizer-eval-review.html) |
| **`feature-evaluator.skill`** | Evaluates code across 7 dimensions (structure, readability, performance, error handling, security, testability, maintainability); produces severity-rated reports | Used in-repo for ongoing code review; no formal pass/fail benchmark yet |

---

## Tests Planned but Not Yet Run

See [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) and [`NEXT.md`](NEXT.md). High-priority:

- **Pytest suite for backend services** — `ranking_service.py`, `trade_service.py`, and `data_loader.py` would benefit most. Currently zero coverage.
- **Integration test for full Sleeper flow** — mock Sleeper API responses; verify session/league/roster import.
- **Elo regression test** — golden-file comparison: given a fixed sequence of swipe inputs, verify Elo outputs match a recorded baseline.
- **Trade-card generation regression** — given a fixed league snapshot, verify trade cards generated.
- **Tiered matchup engine A/B** — compare global-Elo vs tier-prioritized matchup selection on information gain per swipe.
- **Postgres migration smoke test** — `DATABASE_URL` pointing at local Postgres; run through full flow.
- **Mobile client Elo parity** — verify mobile and web compute the same Elo values for the same swipe sequence.

---

## Verification Discipline

Rules of evidence for this ledger:
- **No claim without a verification artifact.** Either a docs file, a script output, a manual screenshot, or a recorded test run.
- **State the input set.** "Tested on test-league X with N players" beats "tested it."
- **Distinguish smoke from regression.** Smoke = "it ran"; regression = "the output matches a saved baseline."
- **When manual: name the path.** Click sequence in mobile? Curl call in web? Specifics make it reproducible.
- **When fixing a bug: capture the failing input.** Add to verification artifacts.
