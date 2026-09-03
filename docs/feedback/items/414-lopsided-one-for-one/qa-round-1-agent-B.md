# QA round 1 — agent B — 2026-09-02

## Summary: PASS (5 findings — all low; test-coverage and doc-drift gaps, no code defect)

The diff `a556df32..e9723e8a` implements the PRD as amended by the orchestrator's rulings
(two-tier accept, G-8 avoid re-earn, seven declared re-specs). Full backend suite 4508 passed /
1 skipped (expected 4508 / 1). Every PRD-named sabotage (S-1 … S-9, S-5″, S-ov, S-7a/b, S-8a/b)
turned the named test RED and the tree restored green. The four legacy `test_gap_sweetener.py`
asserts are green **unedited** and provably exercise tier 2. All seven declared re-specs are pure
config pins / a registry token, each proven load-bearing by removal, none a weakened assertion.
Findings are gaps in what the suite pins (F-1 … F-4) and stale cites in the worktree's PRD /
code-walk copies (F-5); none blocks ship on its own — the orchestrator should decide whether
F-1 / F-3 warrant a test before merge.

## Environment

| Item | Value |
|---|---|
| Worktree | `…/scratchpad/wt-fb414-qa-b`, branch `qa/fb414-b`, tip `e9723e8a feedback #414 (D-173 (unshipped parallel build; see D-175)): G-8 — gap pass re-earns #360 avoid…` (confirmed via `git log --oneline -7`; 5 commits above `a556df32`) |
| Python | 3.14.4 (`/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`), pytest 9.0.3 |
| Mobile | `npm ci --no-audit --no-fund` → 801 packages; `npx tsc --noEmit` |
| DB | `data/trade_finder.db*` absent at start (nothing to remove); suite run against a fresh DB |
| Method | D-056 static + code-walk only — no simulator, no Maestro. Sabotages applied by exact-string edit, target tests run, file restored with `git checkout --`, `git status` verified clean after every item |
| Tree at end | clean except this report |

## Results

| Test | Verdict | Evidence |
|---|---|---|
| Full suite `python3 -m pytest backend/tests -q -p no:cacheprovider` | **PASS** | `4508 passed, 1 skipped in 342.54s`, exit 0, zero FAILED/ERROR lines (baseline 4483/1 + 25 new node ids) |
| `backend/tests/test_gap_sweetener_frac.py` alone | **PASS** | `25 passed in 4.17s`; `--collect-only` = 25 node ids (20 functions: PRD's 18 + the two tier tests from the Gap-1 ruling; PRD §6.1 said "24" — its own arithmetic was off by one, see F-5) |
| Mobile `tsc --noEmit` | **PASS** | exit 0, no output |
| `mobile/tests/check-*.js` (89 files) | **PASS** | loop printed no `FAIL` line |
| `mobile/scripts/testid-lint.sh` | **PASS** | `testid-lint OK`, exit 0 |
| T-1 helper frac trigger (X1 1550, three pre-asserts, frac-0 half) | PASS | green; S-1 RED `assert 2225.2 == 686.2` (pre-assert (a) catches the additive eff first) |
| Tier tests (Gap-1 ruling): `tier2_fallback…`, `tier1_beats_tier2…` | PASS | green; "drop tier 2" RED `tier-2 fallback missing — card served bare`; "return tier 2 early" RED `assert ('u_w1','give') == ('X1','give')` |
| T-2 never loosens (residual in (1539, 2000]) | PASS | green; S-2 RED `assert 2000.0 == 1539.0` |
| T-3 explicit `gap_frac=0.0` × 6 literal results | PASS | green; S-3 RED on `[gap_500]`: `assert ('u_w1','give',['G','u_w1'],['R'],5853.8,6862.0,…) is None` (plus 7 more) |
| T-4a × 4 (consensus, v2, v3, arm C) | PASS | green; S-4a (consensus pre-check reverted + kwarg dropped) RED `card was served bare` on the consensus test only |
| T-4b × 4 (frac 0 brings the bare back) | PASS | green; S-4b (v3 literal `0.10` instead of `_c`) RED on v3 T-4b + T-7 v3 |
| T-4a-ov consensus epsilon window | PASS | green; S-ov (`extra_ok_fn=None`) RED `assert False` on the overshoot test (T-6 also red — its filler bar lives in the same gate fn) |
| T-5 master switch beats frac + `MODEL_A_PROFILE` absence | PASS | green; S-5″ (helper `frac×max` at thr ≤ 0 + walk bound treats thr ≤ 0 as unset + consensus `or` guard) RED `consensus sweetened under the master switch` |
| T-6 untouchable never balances; deck never empties | PASS | green; S-6 (consensus drops unclosable) RED `deck for R came back empty` |
| T-7 v3 sibling wins (with second closable card C2) | PASS | green; S-7a RED `bare card survived beside its sibling`; S-7b (`cards.remove` mid-loop) RED `second closable card came back unsweetened` |
| T-7 v2 sibling wins | PASS | green; S-7a-v2 RED `bare card survived beside its sibling` |
| T-8 payload precedence | PASS | green; S-8a RED (Tier-3 overwritten); S-8b RED (4-key dict leaked into `sweetener`) |
| T-9 seed/default parity | PASS | green; S-9 (seed row removed) RED `assert 'sweetener_gap_frac' in {…}` |
| T-10 regression / unedited proof | PASS | `git diff a556df32..e9723e8a --stat` on `test_gap_sweetener.py`, `test_engine_quality.py`, `test_knockout_refine.py`, `test_shape_knob.py`, `test_avoid_positions.py`, `bakeoff_profiles.py` = **empty**; only the two ruled re-specs (`test_bakeoff_arm_a_golden.py` 2 ±, `test_gap_sweetener_arm_c.py` +4) appear |
| G-8 avoid (v2) | PASS | removing the v2 `_gap_extra_ok` avoid line → `test_avoid_positions.py::test_shop_and_avoid_same_position_still_generates` RED (`:391`, "none brings a WR back") |
| G-8 avoid (v3) | CONFIRMED builder | removing the v3 line → `test_avoid_positions.py` + frac + gap_sweetener + arm_c + trade_optimizer = **90 passed** — nothing catches it (F-3) |
| Config-reference tuning gotcha (0.0952) | PASS | in-process `_DEFAULT_CFG` override: 0.0952 → C1 test green; 0.0951 → RED; 0.09 → RED. The floor is exact |

## Sabotage table (PRD-named + own)

| Id | Edit (file) | Target | Result | Failing assertion |
|---|---|---|---|---|
| S-1 additive frac | `gap_close_target` → `gap_threshold + frac×max` (optimizer) | T-1 | **RED** (12 fail) | `assert 2225.2 == 686.2 ± …` |
| S-2 frac replaces threshold | `return frac×max` no `min` | T-2 | **RED** (1) | `assert 2000.0 == 1539.0` |
| S-3 zero = zero tolerance | `if gap_frac <= 0: return 0.0` | T-3 gap_500 | **RED** (8) | `… is None` on `[gap_500]` |
| S-4a one caller missed | consensus pre-check `> _GAP_THR` + kwarg dropped (trade_service) | T-4a consensus | **RED** (1) | `card was served bare` |
| S-4b frac read outside `_c` | v3 `GAP_FRAC = 0.10` | T-4b v3 | **RED** (2) | `assert False` (gap_sweetener not None) |
| S-ov helper gates are enough | consensus `extra_ok_fn=None` | T-4a-ov | **RED** (2) | `assert False` |
| S-5″ threshold ≤ 0 means unset | helper + walk bound + consensus `or` guard (2 files) | T-5 | **RED** (1) | `consensus sweetened under the master switch` |
| S-6 drop the unclosable | consensus `if closed is None and _GAP_FRAC > 0: return` | T-6 | **RED** (2) | `deck for R came back empty` |
| S-7a keep both (v3) | collision branch → bare `continue` only | T-7 v3 | **RED** (1) | `bare card survived beside its sibling` |
| S-7a keep both (v2) | `else:` → `pass` | T-7 v2 | **RED** (1) | `bare card survived beside its sibling` |
| S-7b mutate mid-loop | `dropped.add(card.trade_id)` → `cards.remove(card)` | T-7 v3 | **RED** (1) | `second closable card came back unsweetened` |
| S-8a gap wins | `if gap_sweetener:` unconditional (server) | T-8 | **RED** | `{'…side':'give'} == {'…side':'receive'}` |
| S-8b whole dict | `out["sweetener"] = gap_sweetener` | T-8 | **RED** | 4-key dict ≠ 2-key dict |
| S-9 one home | seed row removed (database) | T-9 | **RED** | `'sweetener_gap_frac' in {…}` |
| S-10 fix the golden | process sabotage — verified by the empty diff-stat above | T-10 | n/a | — |
| Tier: drop tier 2 | walk bound `> gap_threshold` → `> eff` | tier2 + legacy | **RED** (7) | frac tier tests + **`test_gap_sweetener.py` `:235` / `:330` / `:368` / `:431` all RED** — the D-143 invariant proof |
| Tier: return tier 2 early | `fallback = hit` → `return hit` | tier1_beats_tier2 | **RED** (3) | `('u_w1','give') == ('X1','give')` |
| G-8 v2 avoid removed | trade_service `_gap_extra_ok` | avoid_positions | **RED** (1) | `test_shop_and_avoid_same_position_still_generates` `assert False` at `:391` |
| G-8 v3 avoid removed | trade_optimizer `_gap_extra_ok` | 5 suites | **GREEN** (90 pass) | none — builder's "NONE catches it" **confirmed** (F-3) |
| O-1 recompute `eff` per candidate (own) | `eff = gap_close_target(n_gv, n_rv, …)` inside the walk | frac + gap_sweetener + arm_c | **GREEN** (50 pass) | uncaught (F-1) |
| O-3 frac applies when thr ≤ 0, helper only (own) | helper returns `frac×max` at thr ≤ 0; caller guards intact | frac + gap_sweetener + arm_c + shape_knob | **GREEN** (63 pass) | inert by design — every caller guards on `THR > 0` (the retired S-5 argument); not a gap |
| O-4 drop v3 post-loop `dropped` filter (own) | delete `if dropped: cards = […]` | T-7 v3 | **RED** (1) | `bare card survived beside its sibling` |
| O-5 read frac outside the `GAP_THR > 0` guard (own) | move `GAP_FRAC = _c(…)` above the `if` on v3 | frac + arm-A golden | **GREEN** (35 pass) | uncaught — read has no side effect (F-4) |
| O-6 v2 collision `continue` unconditional (own) | drop `if _GAP_FRAC > 0` guard | frac + gap_sweetener | **GREEN** (41 pass) | uncaught (F-2) |
| O-7 consensus collision `return` unconditional (own) | drop `if _GAP_FRAC > 0` guard | frac + gap_sweetener | **GREEN** (41 pass) | uncaught (F-2) |
| O-9 `min(gv, rv)` instead of `max` (own) | helper | frac | **RED** (3) | `assert 598.95 == 686.2` |
| O-15 gen_v2 pre-check left at `> _GAP_THR` (own) | trade_gen_v2 | T-4a arm C | **RED** (1) | `arm C card was served bare` |

Own sabotages: 8 devised, 4 caught (O-4, O-9, O-15 and O-3-by-design), 4 not caught (O-1, O-5, O-6, O-7).

## Declared re-spec audit

Each of the seven was read in the diff and then **removed** to prove it is load-bearing.

| Test | Edit in diff | Exactly the declared pin? | Removal result |
|---|---|---|---|
| `test_gap_sweetener_arm_c.py::test_arm_c_kill_value_is_a_byte_identical_no_op` | `ts._cfg["sweetener_gap_frac"] = 0.0` inserted before `assert deck(10 ** 9) == off`, 3-line dated D-173 (unshipped parallel build; see D-175) comment | **Yes** — config overlay; assertion text and all literal pins untouched; the file's autouse `_isolate` (`:67-79`) restores `_cfg` so it cannot leak | RED: `[(['G','X1']… 1607.0…)] == [(['G'],['R']… 857.1…)]` — a 1e9 threshold now sweetens at frac 0.10, exactly the declared reason |
| `test_bakeoff_arm_a_golden.py` `_PINNED_KNOBS` | token `sweetener_gap_frac` added to the frozenset string block | **Yes** — registry token. No inline dated comment, but the block is a string literal that cannot carry one; the dated disposition lives where the test's own message directs (`docs/plans/three-model-bakeoff/scope-phase2.md` new row, "Inert companion — EXCLUDED", `MODEL_A_PROFILE` untouched). `test_model_a_profile_only_names_real_knobs` still green | RED: `test_no_generation_knob_was_added_without_an_arm_a_decision` — `_DEFAULT_CFG drifted: added=['sweetener_gap_frac']` |
| `test_engine_quality_golden.py` `_KILL_ALL` | `"sweetener_gap_frac": 0.0` + dated comment | **Yes** — kill-dict overlay; `GOLDEN_DECK` / `GOLDEN_IDEAS` literals untouched | RED: `test_all_knobs_killed_reproduces_pre_wave_deck` deck ≠ golden |
| `test_filler_threshold.py::_v3_fixture` | `ts._cfg["sweetener_gap_frac"] = 0.0` + dated comment | **Yes** — fixture-level config pin; values/assertions untouched | RED: `test_v3_junk_filler_excluded_from_padded_package` `assert None is not None` |
| `test_trade_optimizer.py::test_infeasible_only_qb_trade_never_surfaces` | same pin + dated comment | **Yes** | RED: `assert ['oW','o_w1'] == ['oW']` (the trigger pads the WR-for-WR card) |
| `test_trade_gen_v2.py::test_g6_pick_band_blocks_gap_filler_in_pipeline` | same pin + dated comment | **Yes** | RED: `knob-off should re-admit the shape (kill attribution proof)` |
| `test_trade_gen_v2.py::test_g6_stud_consolidation_with_pick_passes_pipeline` | same pin + dated comment | **Yes** | RED: `stud-consolidation … must PASS #339` |

No assertion got weaker; no fixture value was rescaled. Note the PRD's own T-10 / §4-6 text still lists `test_bakeoff_arm_a_golden.py` and `test_gap_sweetener_arm_c.py` as "unedited" — superseded by the rulings per the brief (F-5, docs only).

## Acceptance fixture re-derivation

Re-run with `backend.trade_optimizer._consensus_packages` / `gap_close_target` at `_DEFAULT_CFG`, flags OFF (`DEFAULT_FLAGS`), and separately with `trade.crown_asset` ON:

| Card | gv | rv | gap / residual | PRD says | Match |
|---|---|---|---|---|---|
| `[G] → [R]` bare | 5989.5 | 6862.0 | **872.5**; eff = min(1539, 686.2) = **686.2** → fires (does not at frac 0) | 872.5 / 686.2 | yes |
| `[G, X2=600] → [R]` | 6099.7 | 6862.0 | **762.3** — > eff, ≤ 1539 ⇒ **tier-2 candidate**, not tier 1 | 762.2 (rounding) | yes |
| `[G, X1=1550] → [R]` | 6815.3 | 6862.0 | **46.7**, `gv < rv` ⇒ tier 1, epsilon holds | 46.7 | yes |
| filler bar | — | — | `0.25 × 5989.5 = 1497.4`, `asset_floor_abs` 450 ⇒ X1 1550 clears | 1497.4 | yes |
| `[G, X1'=1700] → [R]` (T-4a-ov) | 6941.0 | 6862.0 | 79.0, `gv > rv` ⇒ helper accepts, consensus epsilon rejects | 79.0 | yes |
| prod (crown ON) bare | 5989.5 | 7251.0 | 1261.5; eff 725.1 | 1261.5 / 725.1 | yes |
| prod `[G, X1]` | 6815.3 | 7302.6 | 487.3 | 487.2 (rounding) | yes |

`_assert_london_valid` in the test file runs the three §4 pre-asserts ((a) `[G,X2]` gap > eff; (b) X1 ≥ filler bar and ≥ 450; (c) `[G,X1]` gv < rv) before any behavioural assert — verified present at `:130-146`.

**What T-4a actually asserts per arm.** Consensus uses X1 = **1550** (the PRD fixture verbatim): served `[G, X1] → [R]`, `gap_sweetener == {X1, give, 872.5, 46.7}`. v2 divergence and v3 use **X1 = 1750** (`_V_LONDON`, `:358-365`). Justification in the test comment: `filler_ok` on the boarded arms takes the bar from the *higher* board, and the fixture's +30 opp lean on G values it at 6958.8 ⇒ bar **1739.7**, so 1550 fails #141 there. **Verified empirically:** at X1 = 1550 the v3 card is served bare (`['G'] None 5989.5/6862.0`); at 1750 it sweetens (`['G','X1'] {X1, give, 872.5, 121.5} 6983.5/6862.0`). The bare shape is still the operator's report (1-for-1, gap 872.5 = 12.7 % of max, > eff, < 1539) and the PRD's T-4a row itself permits rescaling on v3. One observation: on v2/v3 the close lands at **gv 6983.5 > rv 6862.0** — the viewer ends 121.5 *behind* — which is legal on those arms (no consensus-epsilon sign rule, as the comment says) but means the v2/v3 acceptance card is an "overshoot" close, not the ≤-even close the PRD §4 table shows for 1550. Not a defect; recorded so the operator's TestFlight step 2 is read with that in mind ("near even" may be slightly against you on boarded arms).

**Arm C fixture** (rescaled per PRD): bare gap 1200 (10.7 % of 11200), eff 1120; served `[G, X1] → [R]` gap_after 601.1 ≤ 1120 — verified.

## Code-walk proofs (a)–(f)

**(a) Four callers, one `eff`.** All four read the knob via `_c` (`trade_service.py:1248-1254`: overlay → `_cfg` → `_DEFAULT_CFG`): v3 `trade_optimizer.py:715` (inside the `GAP_THR > 0 and cards` block at `:711`), v2 `trade_service.py:6915`, consensus `:7126`, gen_v2 `trade_gen_v2.py:591`; all four pass `gap_frac=` to `close_value_gap` (`trade_optimizer.py:751`, `trade_service.py:6952`, `:7255`, `trade_gen_v2.py:800`). `eff` is computed once at `:937` from the original card and never reassigned in the walk (`:963-993`) — S-4a/S-4b/O-15 prove the wiring; O-1 shows the "once" property is contract-only (F-1). Pre-check parity: gen_v2 prices with `_consensus_packages` (`:740`), the very call the helper makes at `:936`; consensus `_emit` prices with `package_value_v2(gvals, v_max, n_other, other_values)` at **`:7166-7171`** on `seed_value` — byte-for-byte the body of `_consensus_packages` (`trade_optimizer.py:108-117`). Same `(gv, rv)`, same `_GAP_THR`, same `_GAP_FRAC` ⇒ identical `gap_close_target`. (code-walk.md cites `:6389-6392` for this — that is a different loop; drift only, F-5.)

**(b) Arm A inert.** `git diff a556df32..e9723e8a -- backend/bakeoff_profiles.py` is empty; `MODEL_A_PROFILE` still pins `"sweetener_gap_threshold": 0.0` (`bakeoff_profiles.py:105`) and the new key is absent (asserted by T-5 `:543-544`). Guard order per arm: v3 `:711` `if GAP_THR > 0 and cards:` encloses the read, the kwarg and the collision; v2 `:6936` `if _GAP_THR > 0:` encloses kwarg + `else: continue`; consensus `:7231` `_GAP_THR > 0` is the **left** operand of `and`, so `gap_close_target` is not evaluated at threshold 0; gen_v2 `:739` `if _GAP_THR > 0:` encloses pre-check + kwarg. The v2/consensus/gen_v2 reads at `:6915`/`:7126`/`:591` sit outside the guard but are side-effect-free. S-5″ RED proves the guard is load-bearing; O-3 GREEN proves the guards alone hold even if the helper misbehaved. `_PINNED_KNOBS` + `scope-phase2.md` row record the exclusion.

**(c) Collision per arm.** v3 `:754-758`: on `new_key in card_keys` with `GAP_FRAC > 0`, `dropped.add(card.trade_id)` + discard the bare key, then `continue`; `dropped` declared at `:719` before the loop; `:790-791` filters `cards` once after the loop; nothing mutates `cards` inside `for card in cards` (`:739`). S-7a, S-7b, O-4 each RED. v2 `:6976-6982` `else: if _GAP_FRAC > 0: continue` before the `TradeCard(...)` build at `:6984` — S-7a-v2 RED. Consensus `:7269-7276` `else: if _GAP_FRAC > 0: return` from `_emit`; reachable only when two bares close to the same combo (1×1s enumerate first) — O-7 shows no fixture reaches it (F-2). gen_v2: no rule — sweetening happens inside `_pair_survivors` (`:739-808`, `s_give, s_recv = _ng, _nr` at `:808`) **before** `_dedup_batch` (`def :863`, called at `:1171`), so a closable bare never reaches dedup bare and the exact-key duplicate collapses there; pinned by the arm-C outcome assertion in T-4a (`:480-483`).

**(d) R-C payload.** `server.py trade_card_to_dict`: `:11812-11814` serialises Tier-3 `sweetener`; `:11818-11820` serialises `gap_sweetener` in full; **new `:11825-11827`** `if not sweetener and gap_sweetener: out["sweetener"] = {player_id, side}` — exactly two keys, only when Tier-3 is absent; a card with neither touches no key. T-8 pins all three states; S-8a/S-8b RED. Client path needs no change: `git grep gap_sweetener -- mobile/src web extension` = 0 hits; `mobile/src/api/trades.ts:86-95` validates `raw.sweetener` as `{player_id: string, side: 'give'|'receive'}` (the mirror's exact shape); `TradeCard.tsx:235-240` resolves the player from the matching side; `web/js/app.js:3655-3665` reads `card.sweetener.player_id` / `.side` identically.

**(e) G-8 avoid sites.** v3 `trade_optimizer.py:732-737` in `_gap_extra_ok`: `if _avoid and not all(avoid_ok(p, players, _avoid) for p in r): return False` (`_avoid` from `:385`); v2 `trade_service.py:6927-6932` same predicate (`_avoid` at `:6818`); consensus covered at pool construction — `_avoid` `:7084`, `_opp_pool` filtered by `avoid_ok` `:7085-7087`, `recv_pool = list(_opp_pool)` `:7088`, and the gap pass draws only from `recv_candidates=recv_pool` (`:7254`). gen_v2: `git grep avoid_positions backend/trade_gen_v2.py` = 0 hits and the call site `trade_service.py:4693` passes none — pre-existing arm-C gap, correctly reported as out of scope. The v2 site is pinned by `test_avoid_positions.py:391`; the v3 site by nothing (F-3).

**(f) Deploy-free lever.** `@app.route("/api/admin/config/<key>", methods=["PUT"])` at `server.py:18584`; `_require_cron_auth()` (`def :20950`) gates it; `set_config` (`database.py:4431`) stamps `updated_at` and inserts a `model_config_changes` row in one transaction; then `_trade_service_mod.reload_config()` at `:18607` — `trade_service.reload_config` (`:1213`) does `_cfg.update(fresh)` in place. The only other `reload_config` call is startup `:449`. `_c` reads `_cfg` live, so the PUT is visible to the next generation without restart; a raw `UPDATE model_config` is not.

**Docs consistency (step 8).** `docs/config-reference.md` `sweetener_gap_frac` row: default 0.10, two-tier accept described, master switch (`inert while sweetener_gap_threshold ≤ 0`), `PUT /api/admin/config/sweetener_gap_frac` lever, 0.0952 tuning gotcha (verified exact above), pinned-by file named — present. The stale arm-C sentence in the `sweetener_gap_threshold` row is replaced with "Arm C … runs the pass too since 2026-08-22". `docs/api-reference.md` card shape: `sweetener` comment amended (exactly `{player_id, side}`, Tier-3 wins) and a new `gap_sweetener {player_id, side, gap_before, gap_after}` block with the tier-2 note — present. `scope-phase2.md`: `sweetener_gap_frac` exclusion row citing the `package_floor_cross` rule — present.

## Findings

**F-1 — low (test gap).** *"`eff` computed once, never per candidate" is unpinned.* Repro: insert `eff = gap_close_target(n_gv, n_rv, gap_threshold, gap_frac)` after `residual = abs(n_gv - n_rv)` in `close_value_gap` → frac + gap_sweetener + arm_c suites = 50 passed. Expected: RED somewhere. Actual: GREEN. Why: in every fixture the equalizer goes on the poorer side, so `max(n_gv, n_rv)` stays the richer side's original value and the recomputed `eff` equals the original. A fixture whose close *overshoots* (the added asset pushes the give side above `rv` — the existing v2/v3 X1 = 1750 shape does this) with a residual in `(eff_orig, 0.10 × new max]` would catch it. Docstring (`trade_optimizer.py:906-910`) and PRD R-A state this as a contract.

**F-2 — low (test gap).** *The frac ≤ 0 fall-through on the v2 and consensus collision branches is untested.* Repro: make v2's `else:` an unconditional `continue` (or consensus's an unconditional `return`) → frac + gap_sweetener = 41 passed each. Expected: a frac-0 test asserting the bare survives beside its picked/seen sibling goes RED. Actual: GREEN — no fixture reaches those branches at frac 0 (the T-7 frac-0 half never triggers the absolute pass: gap 872.5 < 1539, so `closed is None`). The "byte-identical at frac ≤ 0" claim for the collision branch rests on reading, not on a test. Needs an absolute-trigger bare (gap > 1539) whose balanced key is already in `_picked_keys` / `seen`.

**F-3 — low (test gap, builder-acknowledged).** *The v3 G-8 avoid line has no test.* Repro: delete `trade_optimizer.py:736-737` → `test_avoid_positions.py`, `test_gap_sweetener_frac.py`, `test_gap_sweetener.py`, `test_gap_sweetener_arm_c.py`, `test_trade_optimizer.py` = 90 passed. The v2 twin is caught at `test_avoid_positions.py:391`. A v3 analogue (a receive-side equalizer at an avoided position on a `generate_pair_trades_v3` fixture with `avoid_positions`) would close it. Builder's report ("NONE does") is **confirmed**, not refuted.

**F-4 — low (contract-only, informational).** *"Read the frac inside the `GAP_THR > 0` guard" is undetectable by the suite.* Moving v3's `GAP_FRAC = _c(...)` above the guard leaves frac + arm-A golden green (35 passed). The read has no side effect, so only a `_c` spy or a "key deleted from `_cfg` and `_DEFAULT_CFG` at threshold 0 raises no KeyError" test could pin it. v2/consensus/gen_v2 already read outside the guard (harmlessly). No action required; noting so nobody later claims the suite proves it.

**F-5 — low (docs drift in the worktree copies).** (i) PRD T-10 and §4-6 still list `test_bakeoff_arm_a_golden.py` and `test_gap_sweetener_arm_c.py` as "unedited"; both were re-spec'd under the rulings — the PRD/LLD copies predate the second addendum (as the brief warns) and should be amended or a rulings addendum appended before ship. (ii) PRD §6.1 "24 pytest node ids / 19 functions" — actual is 25 / 20 (the PRD's own sum of its rows is 23 / 18; the two tier tests bring it to 25 / 20). (iii) `code-walk.md` (a) cites `trade_service.py:6389-6392` for `_emit`'s `gv, rv`; the computation is at `:7166-7171` (`:6385-6396` is a deck-tilt loop). (iv) PRD §6.4 step 4 / lld-delta §1 cite `server.py:18577-18601` (reload `:18600`) and `_require_cron_auth` `:20943`; after the 7-line payload block they are `:18584`, `:18607`, `:20950`. All docs-only.

**Observations (not findings).** v2/v3 T-4a use X1 = 1750, landing the close at gv > rv (see fixture section) — verified necessary and consistent with the PRD's rescaling latitude. O-3 GREEN is by design (caller guards), matching the reconciliation log's retirement of S-5. The tier-2 machinery is exercised by the untouched legacy suite: legacy `[G,X1]` residual **977.7** sits in `(700, 1539]` (eff = 0.10 × 7000), `[G,X2]` 1648.9 is rejected outright, so the D-143 fixtures sweeten only through tier 2 — and "drop tier 2" turns `test_gap_sweetener.py` `:235` / `:330` / `:368` / `:431` RED with the file's diff empty. That is the "never less than D-143" invariant, proven both ways.

## TestFlight checklist (operator-run)

Real league, balancing preference OFF (prod default). No mobile build needed — the current TestFlight build against the deployed backend is the surface. Log the outcome in `living-memory/TEST_LEDGER.md`.

| # | Where | Steps | Expected |
|---|---|---|---|
| 1 | Trades landing, empty canvas | Tap **Find a Trade** | The pushed model deck renders (D-171). |
| 2 | Deck | Find a 1-for-1 where the value bar shows **you ahead by roughly 8–15 %** (or build London-for-Lamb in the calculator, note the bar, then find the deck card for that pair) | The served card's **give** side carries a **second asset of yours**, the line **"+ {player} added to balance the deal"** shows under the give column, and the bar reads near even (on boarded-arm cards it may sit slightly *against* you — the close can overshoot by a small margin; that is expected). No deck card shows you ahead by more than ~10 % of its larger side without such a line — unless your roster has nothing between ~25 % of the headliner and even, in which case the card is served bare. |
| 3 | Same card | Check the added asset against your **Untouchables**; then ✕ (pick a reason), ✓, and **edit in calculator** on a balanced card | The added asset is **not** untouchable. ✕ / ✓ / edit all work on the sweetened card exactly as on any other (the id is the card's own). |
| 4 | Admin API (the deploy-free lever) | `curl -X PUT "$BASE/api/admin/config/sweetener_gap_frac" -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" -d '{"value": 0, "source": "testflight-414"}'` (`CRON_SECRET` from `secrets.local.env`; route `server.py:18584`, auth `_require_cron_auth` `:20950`) — the route calls `set_config` **and reloads `trade_service._cfg` inline** (`:18607`), so it is live on the running dyno immediately, and appends a `model_config_changes` row. Then force-regenerate the deck. **Do not** `UPDATE model_config` directly — `_cfg` loads only at start (`:449`) and via this route, so a raw update is invisible until restart and would report a false negative. | The **same pair** comes back **bare** with its full gap and no "added to balance" line. `PUT` again with `{"value": 0.10, "source": "testflight-414"}`, regenerate → balanced again. Two `model_config_changes` rows attributed to `testflight-414`. |
| 5 | DB, read-only | `SELECT features_json->'gap_sweetener' FROM deck_impressions WHERE trade_id = '<card id from step 2>'`; then join `match_swiped` / `trade_pass_layer1` on `impression_id` | The impression row carries `{player_id, side, gap_before, gap_after}` with `gap_after ≤ max(0.10 × larger side, tier-2 residual ≤ 1539)`; the swipe row joins to it. `impression_id: 'none'` on the swipe row is the PRD Appendix A gap, not this change. |
