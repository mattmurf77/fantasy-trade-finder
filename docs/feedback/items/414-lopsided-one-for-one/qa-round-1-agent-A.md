# QA round 1 — agent A — 2026-09-02

> Phase 3 static QA (D-056: no simulator, no Maestro) of group G-414 — feedback #414 "lopsided
> 1-for-1 served bare" → proportional gap-sweetener trigger (D-173 (unshipped parallel build; see D-175)). Diff under test:
> `a556df32..e9723e8a` (5 commits, tip `e9723e8a`). Contract: `prd.md` §2–§6 as amended by the
> orchestrator's build-time rulings (two-tier accept; G-8 avoid re-earn; seven declared re-specs)
> — those rulings were taken from the builder's report because the copies of `prd.md`,
> `lld-delta.md` and `reconciliation-log.md` at the group tip do not carry them (F-1).
> Agent B ran the same brief independently; nothing here was coordinated.

## Summary: PASS (7 findings — 0 blocking, 1 medium, 4 low, 2 observations)

The shipped code matches the amended contract on every point I could check statically. All 25
new node ids are real tests: every PRD-named sabotage (S-1…S-9 incl. S-4a on all four arms, S-4b,
S-ov, S-5″, S-7a/b, S-8a/b), both tier-test sabotages and the G-8 v2 sabotage went RED on the
named assertion and green again on restore. The four legacy D-143 asserts are untouched and pass
via tier 2 exactly as the ruling intended. The full suite is 4508 passed / 1 skipped, mobile
gates green. What the findings are about is **coverage the contract does not force**: the v3
G-8 avoid line, the frac-≤0 collision byte-identity (R-A2.8), the consensus collision branch and
the tier-2 "cheapest first" rule are each un-pinned — a sabotage of any of them passes the entire
suite — and the two eff-computing test helpers measure eff on post-close values rather than the
original sides. None of these is a defect in the shipped behaviour; all are cheap to close.

## Environment

| Item | Value |
|---|---|
| Worktree / branch | `scratchpad/wt-fb414-qa-a` · `qa/fb414-a` at `e9723e8a` (confirmed `git log --oneline -7`; top commit "feedback #414 (D-173 (unshipped parallel build; see D-175)): G-8 — gap pass re-earns #360 avoid on receive-side equalizers; four declared fixture re-specs") |
| Python / Node | 3.14.4 / v24.14.1 |
| Backend suite | `rm -f data/trade_finder.db{,-wal,-shm}` (the literal `db*` glob errors under zsh `nomatch` when no db exists — ran the explicit names) then `python3 -m pytest backend/tests -q -p no:cacheprovider` → **4508 passed, 1 skipped in 351.9 s** (expected 4508/1; baseline 4483/1 + 25 new node ids) |
| Mobile gates | `npm ci --no-audit --no-fund` exit 0 (801 packages); `npx tsc --noEmit` exit 0; `for f in tests/check-*.js` → 89 files, **0 FAIL**; `scripts/testid-lint.sh` → `testid-lint OK` |
| Tree at end | `git status` clean except this report (every sabotage restored with `git checkout --` and re-verified clean) |
| Sabotage harness | scratchpad `qa_a_sabotage.py` + `qa_a_sabotage_cases.py` (outside the worktree); logs `qa-a-sabotage-log.txt`, `qa-a-sabotage-broad-log.txt`, `qa-a-g8-v3-full.txt` |

Sabotage target sets: **narrow** = `test_gap_sweetener_frac.py` + `test_gap_sweetener.py` +
`test_gap_sweetener_arm_c.py` + `test_avoid_positions.py` (79 tests, ~3 s); **broad** = the 46
`backend/tests/*.py` files that `git grep` any of `close_value_gap|gap_close_target|sweetener_gap|
generate_pair_trades_v3|generate_league_suggestions|trade_card_to_dict|avoid_positions|
_generate_for_pair_v2|generate_trades(` (807 tests, ~40 s); **full** = `backend/tests` (4509).

## Results

| Test | Verdict | Evidence |
|---|---|---|
| T-1 `test_helper_frac_trigger_closes_a_proportional_gap` | PASS | Green at tip. Three §4 validity pre-asserts run first (`:130-146`). S-1 → RED (`assert 2225.2 == 686.2 ± 6.9e-04` in the pre-assert; the helper leg then returns None). |
| T-2 `test_helper_frac_never_loosens_the_absolute_target` | PASS | Green. S-2 → RED `assert 2000.0 == 1539.0 where 2000.0 = gap_close_target(20000.0, 16000.0, 1539.0, 0.1)`. The (1539, 2000] residual leg (W = 4500 on a 16k/20k package) is present at `:229-234`. |
| T-3 `test_helper_frac_default_kwarg_is_byte_identical[6 ids]` | PASS | Green. Six literal cases (`mini`, `gap_500`, `unclosable`, `untouchable`, `extra_gate`, `pools`), each with explicit `gap_frac=0.0`. S-3 → RED on `[gap_500]`: `assert ('u_w1', 'give', ['G','u_w1'], ['R'], 6458.4, 7000.0, …) is None`. |
| T-4a consensus / v2 / v3 / arm C `_frac_card_is_sweetened_at_default` | PASS | All four green. S-4a on **each** arm separately → only that arm's test (plus its T-7 sibling test) RED: consensus `card was served bare`; arm C `arm C card was served bare / assert []`; v3 and v2 `card was served bare`. Arm C additionally asserts the R-A2.7 outcome invariant (`:480-483`). Fixture note: v3/v2 use X1 = **1750**, not the PRD's 1550 — see §Acceptance fixture. |
| T-4b ×4 `_sabotage_frac_zero_brings_the_bare_card_back` | PASS | Green. S-4b (all four sites read `_DEFAULT_CFG` instead of `_c`) → all four RED (`assert False where False = all(<_assert_bare_with_full_gap genexpr>)`) plus both T-7 tests and the arm-C 1e9 leg. |
| T-4a-ov `test_consensus_epsilon_window_serves_the_overshoot_bare` | PASS | Green. Asserts the helper accepts (`out[0]=="X1"`, `gv > rv`, gap ≤ eff) and the served consensus card is bare. S-ov (`extra_ok_fn=None` at the consensus site) → RED `assert False = all(… gap_sweetener is None …)`; T-6 also RED under S-ov. |
| T-5 `test_master_switch_beats_frac` | PASS | Green; asserts `"sweetener_gap_frac" not in MODEL_A_PROFILE` and threshold pin ≤ 0. S-5″ (helper returns frac×max at threshold ≤ 0 + walk bound treats ≤ 0 as unset + all four caller guards `THR > 0 or FRAC > 0`) → RED `consensus sweetened under the master switch`, and six legacy disable/kill tests RED with it. |
| T-6 `test_untouchable_never_balances_a_frac_card` | PASS | Green. S-6 (consensus drops an unclosable card when frac > 0) → RED `deck for R came back empty — the pass emptied a deck`; also reds T-4a-ov, two legacy pinned-pool tests and `test_avoid_positions…[consensus]`. |
| T-7 v3 `test_sibling_wins_over_bare_when_frac_on_v3` | PASS | Green. Deviates from the PRD's `max_cards=2` sketch on purpose (organic sibling via `v3_diversity_max_overlap=0.7`, rescue off, second closable card C2 between bare and sibling; rationale `:586-603`). S-7a → RED `bare card survived beside its sibling`; S-7b (`cards.remove` mid-loop) → RED `second closable card came back unsweetened`. |
| T-7 v2 `test_sibling_wins_over_bare_when_frac_on_v2` | PASS | Green (`max_per_opponent=2`, bare-first at frac 0 asserted). S-7a → RED `bare card survived beside its sibling`. |
| T-8 `test_payload_mirrors_gap_sweetener_into_sweetener` | PASS | Green; three states + `set(out["sweetener"]) == {"player_id","side"}`. S-8a → RED (`{'side': 'give'} != {'side': 'receive'}` — Tier-3 overwritten); S-8b → RED (`Left contains 2 more items: {'gap_after': 46.7, 'gap_before': 872.5}`). |
| T-9 `test_default_and_seed_agree` | PASS | Green. S-9 (seed row commented out) → RED `assert 'sweetener_gap_frac' in {…}`. |
| T-10 regression | PASS | Full suite 4508/1. `git diff a556df32..e9723e8a --stat` on `test_gap_sweetener.py`, `test_engine_quality.py`, `test_knockout_refine.py`, `test_shape_knob.py`, `bakeoff_profiles.py`, `mobile/`, `web/`, `extension/` → **empty**. |
| T-11 `test_helper_tier2_fallback_narrows_when_no_candidate_reaches_eff` (Gap-1) | PASS | Green; asserts `EFF < residual ≤ 1539` on the returned X2 close. Tier-A sabotage (drop tier 2) → RED `tier-2 fallback missing — card served bare`, **and the three legacy D-143 served-arm tests + the pinned-pool test go RED with it** — direct proof the two-tier accept is what keeps D-143 green. |
| T-12 `test_helper_tier1_beats_tier2_regardless_of_order` (Gap-1) | PASS | Green; non-vacuity leg (X2 alone is a valid tier-2) present. Tier-B sabotage (return first tier-2 hit) → RED `tier 2 returned early: X2`. |
| G-8 v2 avoid line | PASS | Removing the `avoid_ok` line in v2 `_gap_extra_ok` (`trade_service.py:6931-6932`) → `test_avoid_positions.py::test_shop_and_avoid_same_position_still_generates` (the `:391` test) RED (`assert False = all(… != "WR" for p in receive_player_ids …)`). Restore → green. |
| G-8 v3 avoid line | **UNCOVERED** | Removing the line at `trade_optimizer.py:736-737`: narrow set 79/79 green, broad set 807/807 green, full suite **4508 passed / 1 skipped** (301 s) — green. Builder's "NONE catches it" is **confirmed**. See F-2. |

## Sabotage table (PRD-named + own)

Every row: apply → run → record → `git checkout --` → `git status` clean. "Expected" = the test the PRD names.

| # | Sabotage (what I changed) | Set | Result | Expected test RED? |
|---|---|---|---|---|
| S-1 | `gap_close_target` returns `gap_threshold + frac × max` | narrow | 20 failed / 59 | YES — T-1 (`2225.2 == 686.2`) |
| S-2 | `gap_close_target` returns `frac × max` (no `min`) | narrow | 1 failed / 78 | YES — T-2 only (`2000.0 == 1539.0`) |
| S-3 | `if gap_frac < 0` (frac 0 ⇒ eff 0) | narrow | 10 failed / 69 | YES — T-3 `[gap_500]` |
| S-4a | consensus: pre-check `> _GAP_THR` + kwarg dropped | narrow | 1 failed / 78 | YES — T-4a consensus |
| S-4a′ | arm C: pre-check `> _GAP_THR` + kwarg dropped | narrow | 1 failed / 78 | YES — T-4a arm C |
| S-4a″ | v3: kwarg dropped | narrow | 2 failed / 77 | YES — T-4a v3 (+ T-7 v3) |
| S-4a‴ | v2: kwarg dropped | narrow | 2 failed / 77 | YES — T-4a v2 (+ T-7 v2) |
| S-4b | all four sites read `_DEFAULT_CFG["sweetener_gap_frac"]` instead of `_c` | narrow | 7 failed / 72 | YES — all four T-4b (+ T-7 ×2, arm-C 1e9 leg) |
| S-ov | consensus `extra_ok_fn=None` | narrow | 2 failed / 77 | YES — T-4a-ov (+ T-6) |
| S-5″ | helper `frac × max` at thr ≤ 0 + walk bound `gap_threshold > 0 and …` + four caller guards OR'd | narrow | 7 failed / 72 | YES — T-5 (+ 6 legacy disable/kill tests) |
| S-6 | consensus: `closed is None and _GAP_FRAC > 0 → return` | narrow | 5 failed / 74 | YES — T-6 (+ T-4a-ov, 2 legacy pinned-pool, avoid[consensus]) |
| S-7a | v3 collision block deleted + v2 `else: continue` → `pass` | narrow | 2 failed / 77 | YES — T-7 v3 + v2 |
| S-7b | v3 `dropped.add(card.trade_id)` → `cards.remove(card)` | narrow | 1 failed / 78 | YES — T-7 v3 ("second closable card came back unsweetened") |
| S-8a | `if gap_sweetener:` (unconditional mirror) | frac file | 1 failed / 24 | YES — T-8 |
| S-8b | `out["sweetener"] = gap_sweetener` | frac file | 1 failed / 24 | YES — T-8 |
| S-9 | `_MODEL_CONFIG_DEFAULTS` seed row removed | frac file | 1 failed / 24 | YES — T-9 |
| S-10 | (not a code sabotage) — audited by `git diff` on the six named suites: empty | — | — | n/a |
| Tier-A | drop tier 2 (`return None` after the walk) | narrow | 7 failed / 72 | YES — T-11 (+ T-12, T-6, 4 legacy D-143 tests) |
| Tier-B | return first tier-2 hit immediately | narrow | 3 failed / 76 | YES — T-12 (+ T-1, T-4a-ov) |
| G-8 v2 | delete the `avoid_ok` line in v2 `_gap_extra_ok` | narrow | 1 failed / 78 | YES — `test_avoid_positions.py::test_shop_and_avoid_same_position_still_generates` |
| G-8 v3 | delete the `avoid_ok` line in v3 `_gap_extra_ok` | narrow, broad, **full** | 79/79, 807/807, 4508 passed / 1 skipped (full) | **NO — nothing catches it** (F-2) |
| O-1 | recompute `eff` per candidate from `(n_gv, n_rv)` inside the walk | narrow, broad | all green | not caught (obs-2: the only observable window is a residual in `(eff, frac × overshoot-max]`, e.g. (686.2, 694.1] on the T-4a-ov fixture — narrow; note only) |
| O-2 | delete the v3 post-loop `if dropped:` filter | narrow | 1 failed / 78 | caught — T-7 v3 `bare card survived beside its sibling` |
| O-3 | v3 reads `_c("sweetener_gap_frac")` **outside** the `GAP_THR > 0` guard | narrow, broad | all green | not caught — and correctly so: the read is side-effect-free; the contract is about branches, not reads |
| O-4 | helper returns `frac × max` when `gap_threshold <= 0` (callers' guards intact) | narrow, broad | all green | not caught — inert in prod because every caller guards on `_GAP_THR > 0` before calling; only a direct helper call at threshold ≤ 0 would see it (no test does) |
| O-5 | v3 collision drops the bare **even at frac ≤ 0** (`if True:`) | narrow, broad | all green | **not caught — F-3** (R-A2.8 byte-identity at frac ≤ 0 is un-pinned) |
| O-6 | v3 collision omits `card_keys.discard(bare key)` | narrow, broad | all green | not caught — reachable only when a 2×1 bare is walked before the 1×1 that would close into its key (v3 walks 1×1s first); low value |
| O-7 | tier-2 `fallback` = **last** admitted hit instead of first | narrow, broad | all green | **not caught — F-5** (T-11 has a single tier-2 candidate) |
| O-8 | consensus `else: return` → `pass` (bare emitted beside its balanced key) | narrow, broad | all green | **not caught — F-4** |
| O-9 | `gap_close_target` uses `min(gv, rv)` | narrow | 3 failed / 76 | caught — T-1/T-2 (`598.95 == 686.2`), T-4a-ov |
| O-10 | tier-1 accept `<` instead of `<=` | narrow, broad | all green | not caught — exact-equality residual; practically unobservable; note only |

## Declared re-spec audit

Every one of the seven is a one-line config pin (or registry token) with a dated `#414 (D-173 (unshipped parallel build; see D-175))` comment; no fixture value was rescaled and no assertion got weaker.

| Re-spec | Diff (exactly) | Verdict |
|---|---|---|
| `test_gap_sweetener_arm_c.py::test_arm_c_kill_value_is_a_byte_identical_no_op` | `ts._cfg["sweetener_gap_frac"] = 0.0` inserted **between** `assert deck(-1.0) == off` and `assert deck(10 ** 9) == off` with a 3-line dated comment. The `-1.0` leg still runs at frac 0.10; the 1e9 leg pins the absolute-only regime; all literal post-asserts (`(gv, rv) == (10000.0, 11600.0)`, `fairness == 0.862`, gap 1600 > line) unchanged. `_isolate` restores `_cfg`. | Exact declared pin. Correct: at frac 0.10 a 1e9 threshold gives `eff = 0.1 × max`, so "huge threshold is a no-op" is no longer true by design. |
| `test_bakeoff_arm_a_golden.py` `_PINNED_KNOBS` | one token `sweetener_gap_frac` added to the frozenset word list (`:609`). That list is the drift guard for `test_no_generation_knob_was_added_without_an_arm_a_decision` (`:724-738`), which demands a scope-phase2 decision per new key. | Exact declared token. Golden rows untouched; `MODEL_A_PROFILE` untouched. |
| `docs/plans/three-model-bakeoff/scope-phase2.md` row | new `sweetener_gap_frac` row: "Inert companion — EXCLUDED (the `package_floor_cross` rule)", reason = read only inside the `sweetener_gap_threshold > 0` guard on every arm; profile not edited. | Matches the code (§Code-walk (b)). |
| `test_engine_quality_golden.py` `_KILL_ALL` | `"sweetener_gap_frac": 0.0` + dated comment appended to the kill dict used by `_deck(**_KILL_ALL) == GOLDEN_DECK` / `_ideas(**_KILL_ALL) == GOLDEN_IDEAS`. | Exact pin; `GOLDEN_DECK` not re-captured. Consistent with the dict's purpose (every generation knob at its kill value). |
| `test_filler_threshold.py::_v3_fixture` | `ts._cfg["sweetener_gap_frac"] = 0.0` + 4-line comment beside the existing `v3_pool_size = 2` pin. | Exact pin; fixture values and asserts unchanged. |
| `test_trade_optimizer.py::test_infeasible_only_qb_trade_never_surfaces` | same one-line pin + comment after `v3_pool_size = 2`. | Exact pin. |
| `test_trade_gen_v2.py::test_g6_pick_band_blocks_gap_filler_in_pipeline` and `::test_g6_stud_consolidation_with_pick_passes_pipeline` | one-line pin + comment at the top of each test body. | Exact pins. |

Observation: these five fixture pins also tell us the new default **does** change those five fixtures' organic decks (otherwise the pins would be unnecessary) — the pins scope the tests, they do not hide a regression, but the deck_eval readout (PRD §6.2, ship-owed) is the only place the real-board shape delta will be visible.

## "Never less than D-143" invariant

- `git diff a556df32..e9723e8a -- backend/tests/test_gap_sweetener.py` → **0 bytes**. The four asserts at `:235`, `:330`, `:368`, `:431` are green unedited (`sweet = [c for c in cards if c.gap_sweetener]; assert sweet` ×3; `assert any(c.gap_sweetener for c in free)`).
- Why they stay green is tier 2, not luck — re-derived at `_DEFAULT_CFG`, flags off:
  - `_mini_league` / `_consensus_league` (G 5400, R 7000, X1 1500, X2 600): bare 5400.0 / 7000.0, gap **1600.0**, `eff = min(1539, 700) = 700.0`. `[G, X1]` residual **977.7** → tier 1 ✗ (> 700), tier 2 ✓ (≤ 1539). `[G, X2]` residual 1648.9 → rejected by the unchanged D-143 walk bound. So the walk's only admitted candidate is a tier-2 hit and `return fallback` returns it — exactly D-143's answer.
  - `_v3_league` / v2 (G1 3500, G2 3000, R 8000, X1 2200): bare `[G1, G2] → [R]` 5091.3 / 8000.0, gap **2908.7**, `eff = min(1539, 800) = 800.0`. `[G1, G2, X1]` residual **1336.5** → tier 1 ✗ (> 800), tier 2 ✓ (≤ 1539) — the 3-for-1 those tests pin (`sorted(give) == ["G1","G2","X1"]`, `gap_after ≤ 1539`) is the tier-2 answer, so `test_gap_sweetener.py:330` / `:368` are green for the right reason. Both numbers agree with `code-walk.md`'s appendix (977.7 and 1336.5).
  - Under the Tier-A sabotage (tier 2 removed) all four of these tests went RED in one run — that is the invariant, proven from the other side.

## Acceptance fixture re-derivation

`backend.trade_optimizer._consensus_packages` at `_DEFAULT_CFG`, `DEFAULT_FLAGS` (crown off), then `trade.crown_asset: true`:

| Card | give | receive | gap | vs eff | note |
|---|---|---|---|---|---|
| `[G] → [R]` | 5989.5 | 6862.0 | **872.5** | eff = **686.2** ⇒ fires; ≤ 1539 ⇒ silent at frac 0 | matches PRD |
| `[G, X2=600] → [R]` | 6099.7 | 6862.0 | **762.3** | > 686.2 (tier-2 residual, ≤ 1539) | PRD says 762.2 — rounding only |
| `[G, X1=1550] → [R]` | 6815.3 | 6862.0 | **46.7** | ≤ 686.2; `gv < rv` ✓; ratio 0.993 | matches |
| `[G, X1′=1700] → [R]` | 6941.0 | 6862.0 | **79.0** | ≤ 686.2 but `gv > rv` ⇒ consensus epsilon rejects | matches (T-4a-ov) |
| `[G, X1=1750] → [R]` (v3/v2 fixture) | 6983.5 | 6862.0 | **121.5** | ≤ 686.2; `gv > rv` | see below |
| crown ON: bare / `[G,X2]` / `[G,X1]` / `[G,X1′]` | — | 7251.0 / 7365.6 / 7302.6 / 7278.6 | 1261.5 / 1265.9 / 487.3 / 337.6 | eff 725.1 | matches PRD ±0.1 |

Filler bar on the consensus arm: `filler_min_frac` 0.25 × 5989.5 = **1497.4**, `asset_floor_abs` 450 → X1 = 1550 clears, X2 = 600 does not. `user_gain_epsilon` = 0.0, so the consensus edge is `rv − gv ≥ 0`. All three §4 pre-asserts hold and are in the test (`_assert_london_valid`).

**T-4a on v3/v2 — what it actually asserts (X1 = 1750).** `_assert_sweetened_to_eff` checks: `gap_sweetener` present, `side == "give"`, `player_id == "X1"`, X1 in `give_player_ids`, `gap_before > eff`, `gap_after ≤ eff`, `|give_value − receive_value| ≤ eff`. It does **not** assert `gv < rv` on these arms. The inline justification (`:358-363`) is correct: `filler_ok` takes `max(user_val, opp_val)` per piece, and the fixture's `_LEAN_LONDON` puts the opponent's board on G at +30 Elo → 6958.8 → bar 0.25 × 6958.8 = **1739.7**, so X1 = 1550 is rejected as filler on v3/v2 and 1750 is the smallest round value that clears (verified: `1550 ≥ 1739.7 → False`, `1750 ≥ 1739.7 → True`). Consequence: the balanced v3/v2 card has the viewer paying **121.5 (1.8 %)** after the close rather than sitting ≥ even. That is still the operator's reported shape (a 12.7 % bare 1-for-1 that the roster can balance), and v2/v3 have no sign rule, so the test is honest — but it is a documented deviation from PRD §4-1 ("`[G, X1] → [R]` … on v3, on v2 divergence" with X1 = 1550) that the reconciliation log does not record (obs-1).

## Code-walk proofs (a)–(f)

Line numbers are the worktree at `e9723e8a` (they drift from the PRD's `48f40de5` cites by a few lines; the builder's `code-walk.md` cites match what I see).

**(a) Four callers, one `eff`.** Helper: `trade_optimizer.py:861-873` `gap_close_target` (pure; `<= 0 → gap_threshold`, else `min(gap_threshold, frac × max)`); `close_value_gap` prices the original card at `:938` via `_consensus_packages`, computes `eff` **once** at `:939`, triggers at `:940`, and the candidate walk (`:966-993`) never recomputes it (O-1 confirms a recompute is inert on every fixture, which is also why nothing pins it).
- v3 `generate_pair_trades_v3`: read `GAP_FRAC = _c("sweetener_gap_frac")` at `:715` — **inside** `if GAP_THR > 0 and cards:` (`:711`); passed `gap_frac=GAP_FRAC` at `:751`; no pre-check (the helper's own trigger).
- v2 divergence `_generate_for_pair_v2`: read `:6915` (beside `_GAP_THR`, **outside** the guard — a side-effect-free `_c` lookup; the behavioural guard is `if _GAP_THR > 0:` at `:6937`); passed `:6952`; no pre-check.
- consensus `_emit`: read `:7126`; lazy import of `gap_close_target` `:7127-7128`; pre-check `:7233-7234` `if _GAP_THR > 0 and abs(gv - rv) > gap_close_target(gv, rv, _GAP_THR, _GAP_FRAC)` — `_GAP_THR > 0` is the left operand; passed `:7255`.
- gen_v2 `_pair_survivors`: read `:591`; import `:133`; guard `:739` `if _GAP_THR > 0:`; pre-check `:743-744` on `_consensus_packages(give_ids, recv_ids, cval)` (`:740`); passed `:800`.
- Same `eff` on both sides of each pre-check: gen_v2 prices with the identical `_consensus_packages`; consensus `_emit` builds `gv, rv` from `package_value_v2(gvals, v_max, n_other, other_values)` with `v_max = max(gvals + rvals)` — the body of `_consensus_packages` verbatim. Same `(gv, rv, _GAP_THR, _GAP_FRAC)` ⇒ same number. S-4a on the consensus and arm-C sites (pre-check reverted) each went RED, so the pre-checks are load-bearing.
- Note for the brief's phrasing "all four callers read the frac INSIDE the guard": strictly only v3 does; v2/consensus/gen_v2 read beside the threshold and **branch** inside the guard. The contract (R-D, lld-delta §5) is about reachable branches, and that holds on all four.

**(b) Arm A inert.** `backend/bakeoff_profiles.py:105` still `"sweetener_gap_threshold": 0.0`; `git diff a556df32..e9723e8a -- backend/bakeoff_profiles.py` empty; `sweetener_gap_frac` absent from `MODEL_A_PROFILE` (asserted by T-5 `:543-544`). With the threshold at 0 every frac-dependent branch is behind a false guard on all four arms (see (a)); `test_bakeoff_arm_a_golden.py` green with only the `_PINNED_KNOBS` token added.

**(c) Collision rule per arm.**
- v3: `:756` `if new_key in card_keys:` (unchanged) → `:757-760` when `GAP_FRAC > 0`: `dropped.add(card.trade_id)` + discard the bare key; `continue` either way (frac ≤ 0 ⇒ today's behaviour). `dropped` declared `:719` before the loop; `:790-791` filters `cards` once **after** the loop, immediately before `return cards`. No mutation of `cards` inside `for card in cards` (`:741`). S-7b and O-2 both RED on T-7 v3.
- v2: `:6957` `if new_key not in _picked_keys:` (unchanged) → `else:` `:6976-6982` `if _GAP_FRAC > 0: continue` — the bare `TradeCard` is never built. S-7a RED on T-7 v2.
- consensus: `:7259` `if n_key not in seen:` (unchanged) → `else:` `:7268-7275` `if _GAP_FRAC > 0: return`. Reachable only when two bares close to the same combo (1×1s enumerate before 2×1s) — **no test exercises it** (O-8; F-4).
- gen_v2: none, by design — the close happens at enumeration (`:739-808`, `s_give, s_recv = _ng, _nr`) before `_dedup_batch`, so a closable bare never reaches dedup bare; T-4a arm C asserts the outcome invariant.

**(d) R-C payload precedence.** `server.py:11812-11814` serialises Tier-3 `sweetener` when set; `:11818-11820` serialises the full `gap_sweetener`; new `:11825-11827` `if not sweetener and gap_sweetener: out["sweetener"] = {"player_id": …, "side": …}`. Tier-3 wins (the `not sweetener` test), exactly two keys, `gap_sweetener` always full beside it, neither ⇒ no key touched (T-8 pins all three; S-8a/S-8b RED). Clients need no change: `mobile/src/api/trades.ts:86-95` validates `raw.sweetener` as `{player_id: string, side: 'give'|'receive'}` and discards anything else → `TradeCard.tsx:235-240` resolves the player from the named side; `web/js/app.js:3655-3665` reads `card.sweetener.player_id/side` the same way. `git grep gap_sweetener -- mobile/src web extension` → 0 hits.

**(e) G-8 avoid sites.** v3 `trade_optimizer.py:736-737` in `_gap_extra_ok` (`_avoid` built `:385`; same `avoid_ok` the organic pool uses `:389` and the 3.4 rescue passes `:678`). v2 `trade_service.py:6931-6932` (`_avoid` `:6818`). Consensus: covered at pool construction — `_avoid` `:7084`, `_opp_pool` filtered by `avoid_ok` `:7085-7087`, `recv_pool = list(_opp_pool)` `:7088`, and the gap pass draws only from `recv_candidates=recv_pool` (`:7254`). gen_v2: `generate_league_suggestions` (`trade_gen_v2.py:1018-1032`) has no `avoid_positions` parameter and `grep avoid backend/trade_gen_v2.py` → 0 — arm C has no #360 concept at all, organic or sweetened (pre-existing, out of scope; agree with the builder). **Why the v3 line matters even though nothing pins it:** v3 passes `opp_roster=opponent.roster` with no `recv_candidates`, so the helper's receive-side candidate universe is the **raw** roster minus not-interested — an avoided-position piece is reachable there whenever the opponent is the richer side, which the organic pool filter at `:389` never sees.

**(f) Deploy-free lever.** `server.py:18584` `@app.route("/api/admin/config/<key>", methods=["PUT"])` → `admin_config_update`: `_require_cron_auth()` (`:18595`, def `:20950`, header `X-Cron-Secret`), `set_config(key, float(value), source=…)` (writes the row + `model_config_changes`), then `_trade_service_mod.reload_config()` at `:18607` → `trade_service.reload_config` (`:1213-1224`) does `_cfg.update(fresh)` from `get_config()` in place. `_cfg` is otherwise loaded only at import (`server.py:449`), so a raw `UPDATE model_config` is invisible on the running dyno until restart — the checklist's warning is correct.

## Docs consistency

| Doc | Check | Result |
|---|---|---|
| `docs/config-reference.md` `sweetener_gap_frac` row | default 0.10 ✓ · `eff = min(threshold, frac × max)` computed once ✓ · **two-tier** accept + "gap_after may sit above eff on a tier-2 close" ✓ · master switch / inert while threshold ≤ 0 ✓ · not part of the D-143 pair rule ✓ · `PUT /api/admin/config/sweetener_gap_frac` reloads inline, raw UPDATE invisible ✓ · 0.0952 C1 tuning gotcha verbatim ✓ · pinned by `test_gap_sweetener_frac.py` ✓ · seeded both homes ✓ | PASS |
| `docs/config-reference.md` `sweetener_gap_threshold` row | stale "Arm C … do NOT run the pass in v1" replaced by "Arm C (`trade_gen_v2._pair_survivors`) runs the pass too since 2026-08-22 … the fit arm still does not" | PASS (fixed) |
| `docs/api-reference.md` card shape | `sweetener` comment now "Tier 3 rescue OR, since #414 (D-173 (unshipped parallel build; see D-175)), the gap auto-sweetener … exactly {player_id, side}; Tier-3 wins when both apply"; new `gap_sweetener {player_id, side, gap_before, gap_after}` OPTIONAL row, "served since 2026-08-22; documented with #414", tier-2 note | PASS |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | exclusion row present, reason matches (b) | PASS |
| `code-walk.md` | sections (a)–(f) + appendix present; cites match the tree | PASS |
| `reconciliation-log.md`, `prd.md`, `lld-delta.md` at tip | log ends at §5; no §6/§7 addenda; PRD still says single-tier accept (`abs(n_gv − n_rv) ≤ eff` at R-A.3), 19 functions / 24 node ids, D-**172**; `lld-delta.md` likewise | **F-1** |
| `living-memory/DECISIONS.md` | neither D-176 nor D-173 (unshipped parallel build; see D-175) present at tip (PRD R-F.12 says "same PR as the code"); code/docs/commits say D-173 (unshipped parallel build; see D-175), PRD §9 says D-176 | ship-owed (part of F-1) |

## Findings

**F-1 — low (docs/process): the amended contract is not in the repo at the group tip.** `reconciliation-log.md` has §1–§5 only; `prd.md` R-A.3 still specifies the single-tier accept (`abs(n_gv − n_rv) ≤ eff`), §6.1 still counts 24 node ids and names D-176; `lld-delta.md` §3 likewise. The two-tier accept, the G-8 avoid rule, S-5″, the seven declared re-specs and the D-173 (unshipped parallel build; see D-175) renumbering exist only in the builder's report and in `code-walk.md`. Expected: PRD/LLD/log amended in the same PR (PRD §7 owes D-176/173 + index row too; `DECISIONS.md` has neither at tip). Actual: absent. Repro: `grep -n '^## 6' docs/feedback/items/414-lopsided-one-for-one/reconciliation-log.md` → nothing; `grep -n 'D-17[23]' living-memory/DECISIONS.md` → nothing. Not a code defect; must land before ship or the next reader of the PRD will "fix" tier 2 out.

**F-2 — medium (test coverage): the v3 G-8 avoid re-earn is pinned by nothing.** Deleting `trade_optimizer.py:736-737` leaves the full suite 4508 passed / 1 skipped (full). The line is load-bearing (see (e): v3's receive-side equalizer universe is the raw opponent roster), so a future refactor could silently reintroduce an avoided-position receive equalizer on the v3 arm. Expected per G-8: "the gap pass re-earns #360 avoid on receive-side equalizers" on every arm, with evidence; actual evidence exists for v2 only. Repro: apply the O-row "G-8 v3" sabotage; `pytest backend/tests` green. Suggested pin: a `test_avoid_positions.py[v3]`-style fixture where the **opponent** is the richer side (`gv > rv` by more than `eff`), the only sufficient opponent-side equalizer is an avoided position, and the assertion is that the card is served bare (or closed with a non-avoided piece) — mirror of `:391` for the sweetener path.

**F-3 — low (test coverage): R-A2.8 (collision path byte-identical at frac ≤ 0) is untested.** O-5 (v3 drops the bare on collision regardless of `GAP_FRAC`) passes narrow, broad and — by construction — every test in the suite, because no fixture reaches a v3/v2 collision at frac 0: T-7's frac-0 legs have a bare gap of 1462 (< 1539) so the pass never fires there, and the legacy v3 test deliberately uses `max_cards=1` to avoid the collision (`test_gap_sweetener.py:314-318`). Expected: "at `sweetener_gap_frac ≤ 0` the collision paths are byte-identical: bare kept unsweetened, sibling kept". Suggested pin: T-7 v3 with `_V_T7["G"]` lowered so the bare gap exceeds 1539, asserting both keys present at frac 0.

**F-4 — low (test coverage): the consensus `else: return` branch (`trade_service.py:7268-7275`) is untested.** O-8 (branch neutered) passes everything. PRD R-A2.7 states an outcome invariant for consensus ("at most one card carries the balanced key and no bare survives whose balanced key is present") and asserts it nowhere; the reachable case (two bares closing to the same combo, `A→R` with `B` then `B→R` with `A`) is constructible with two ~equal give assets and is cheap to add. Until then the branch is dead-by-evidence.

**F-5 — low (test coverage): tier 2 returns the *first* (cheapest) admissible fallback, and nothing pins "first".** O-7 (keep the last) passes everything; T-11 offers a single tier-2 candidate. One extra call in T-11 with `give_candidates=["X2", "Y"]` (both tier-2, Y dearer) asserting `out[0] == "X2"` closes it.

**F-6 — low (test precision): `_assert_sweetened_to_eff` and `_eff_of` compute `eff` from post-close `card.give_value/receive_value`, not the original sides.** Contract (R-A.3, docstring `:891-895`): `eff` is fixed on the ORIGINAL card. On the v3/v2 fixture the post-close max is 6983.5 so the test's `eff` is 698.4 while the contract's is 686.2. Harmless today (`gap_after` = 121.5 on those arms, 46.7 on consensus/helper) but a tier-2 close landing in (686.2, 698.4] would be accepted by the test as "≤ eff" when it is not. Fix: compute `eff` from `gap_before` context, i.e. `gap_close_target(gv0, rv0, …)` using `_consensus_packages` on the original ids, or simply pass the fixture's `EFF`/arm-C 1120 literal.

**F-7 — observation (fixture/PRD drift, not a defect):** T-4a on v3/v2 uses X1 = 1750 (PRD §4: 1550) because the boarded arms' `filler_ok` bar is 1739.7 under the fixture's +30 opponent lean on G; the balanced card there has the viewer paying 121.5 rather than sitting ≥ even. Correctly explained inline (`test_gap_sweetener_frac.py:358-363`) but not logged as a declared deviation; belongs in the reconciliation log with the other re-specs.

Obs-2 (no action): O-1 (per-candidate `eff`) is uncatchable on the shipped fixtures because the equalizer is added to the poorer side, so `max(gv, rv)` only moves on overshoot; the observable window is a residual in `(eff, frac × overshoot-max]`. The docstring's "goalposts" rationale is right; a pin would need a hand-tuned overshoot fixture — not worth it.

## TestFlight checklist (operator-run)

Real league, balancing preference OFF (prod default), current TestFlight build against the deployed backend — no mobile build needed. Log the outcome in `living-memory/TEST_LEDGER.md`.

| # | Where | Do | Expect |
|---|---|---|---|
| 1 | Trades landing, empty canvas | Tap **Find a Trade**. | The pushed model deck renders (D-171). |
| 2 | Deck | Find a 1-for-1 where the value bar shows **you ahead by roughly 8–15 %** (or build London-for-Lamb in the calculator, note the bar, then find that pair's deck card). | The card's **give** side carries a **second asset of yours**, the line **"+ {player} added to balance the deal"** sits under the give column, and the bar reads near even. No deck card shows you ahead by more than ~10 % of its larger side without that line — unless your roster has nothing between ~25 % of the headliner and even (then it is served bare, and that is correct). |
| 3 | Same card | Check the added asset against **Untouchables**; then ✕ (pick a reason), ✓, and **edit in calculator** on the balanced card. | The added asset is **not** untouchable. All three actions behave as on any other card (the id is the card's own). |
| 4 | Admin API (the only lever) | `curl -X PUT "$BASE/api/admin/config/sweetener_gap_frac" -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" -d '{"value": 0, "source": "testflight-414"}'` — `CRON_SECRET` from `secrets.local.env`; route `backend/server.py:18584` (`_require_cron_auth` `:20950`), which calls `set_config` and **reloads `trade_service._cfg` inline** (`:18607`) so the running dyno sees it immediately and a `model_config_changes` row is written. Force-regenerate the deck. **Do not** write `model_config` directly — `_cfg` loads only at start (`:449`) and via this route, so a raw `UPDATE` reports a false negative. | The **same pair** comes back **bare** with its full gap and no "added to balance" line. Then `PUT` again with `{"value": 0.10, "source": "testflight-414"}`, regenerate → balanced again. Two `model_config_changes` rows attributed to `testflight-414`. |
| 5 | DB, read-only | `SELECT features_json->'gap_sweetener' FROM deck_impressions WHERE trade_id = '<card id from step 2>'`; then join `match_swiped` / `trade_pass_layer1` on `impression_id`. | Impression carries `{player_id, side, gap_before, gap_after}` with `gap_after ≤ 0.10 × max(side)` (or ≤ 1539 on a tier-2 close — the row's `gap_before` tells you which). If the swipe row has `impression_id: 'none'` that is the PRD Appendix A gap, not this change. |
